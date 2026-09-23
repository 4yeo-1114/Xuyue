import { useCallback, useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
  Circle,
  Loader2,
  Play,
  Printer,
  RefreshCw,
  ScanLine,
  Sparkles,
  Square,
  UserCog,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PrinterSettingsPanel } from "@/components/shared/PrinterSettingsPanel";
import { useGlobalPrintPrefs } from "@/hooks/useGlobalPrintPrefs";
import { usePrinters } from "@/hooks/usePrinters";
import {
  browserPrintMarksPdf,
  cancelPrintMarksBatch,
  cancelReferenceGrade,
  exportMarksPdf,
  getScanImportStatus,
  listFolders,
  listScanners,
  printMarksBatchStatus,
  referenceGradeStatus,
  startPrintMarksBatch,
  startReferenceGrade,
  startScanImport,
  stopScanImport,
  triggerScan,
  type ScannerItem,
} from "@/services/gradingApi";
import { PRINTER_DEFAULT, printerOutputMode } from "@/lib/globalPrintPrefs";
import { cn } from "@/lib/utils";
import { useLocale } from "@/contexts/LocaleContext";

type SelfPrintStep = "scan" | "grade" | "print";
type SelfPrintStepState = "pending" | "running" | "done" | "error";

const SELF_PRINT_STEPS: SelfPrintStep[] = ["scan", "grade", "print"];

const INITIAL_STEP_STATES: Record<SelfPrintStep, SelfPrintStepState> = {
  scan: "pending",
  grade: "pending",
  print: "pending",
};

/** 从留痕图 URL 提取后端文件名（如 /api/v1/grading/modify/marks_only_xxx.jpg?t=123 -> marks_only_xxx.jpg） */
function marksOnlyFilenameFromUrl(url: string | undefined): string | null {
  if (!url) return null;
  const nameWithQuery = url.split("/").pop() || "";
  const name = nameWithQuery.split("?")[0];
  return name.startsWith("marks_only_") ? name : null;
}

function isAuthError(e: any): boolean {
  return e?.status === 401 || e?.status === 403;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function HardwareConfigPage() {
  const { t } = useLocale();
  const printPrefs = useGlobalPrintPrefs();
  const {
    printers,
    loading: printersLoading,
    error: printersError,
    refresh: refreshPrinters,
  } = usePrinters(true);
  const [scanners, setScanners] = useState<ScannerItem[]>([]);
  const [scannersLoading, setScannersLoading] = useState(false);
  const [scannersError, setScannersError] = useState<string | null>(null);

  // ── 自助文印（扫描 → 批阅 → 打印 状态机）──
  const [folders, setFolders] = useState<string[]>([]);
  const [foldersLoading, setFoldersLoading] = useState(false);
  const [selectedFolder, setSelectedFolder] = useState("");
  const [selfPrinting, setSelfPrinting] = useState(false);
  const [stepStates, setStepStates] =
    useState<Record<SelfPrintStep, SelfPrintStepState>>(INITIAL_STEP_STATES);
  const selfPrintActiveRef = useRef(false);
  /** 当前正在执行/出错的步骤，用于 catch 时标红对应状态点 */
  const selfPrintStepRef = useRef<SelfPrintStep>("scan");
  const selfPrintGradeJobRef = useRef<string | null>(null);
  const selfPrintPrintJobRef = useRef<string | null>(null);

  const loadFolders = useCallback(async () => {
    setFoldersLoading(true);
    try {
      const res = await listFolders();
      if (res.ok) {
        setFolders(res.folders || []);
        setSelectedFolder((prev) => prev || res.folders?.[0] || "");
      } else {
        toast.error(t("grading.selfPrint.foldersLoadFailed"));
      }
    } catch (e: any) {
      toast.error(e?.message || t("grading.selfPrint.foldersLoadFailed"));
    } finally {
      setFoldersLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadFolders();
  }, [loadFolders]);

  useEffect(() => {
    return () => {
      selfPrintActiveRef.current = false;
      if (selectedFolder) void stopScanImport().catch(() => {});
    };
  }, [selectedFolder]);

  const refreshScanners = useCallback(async () => {
    setScannersLoading(true);
    setScannersError(null);
    try {
      const res = await listScanners();
      if (res.ok) {
        setScanners(res.scanners || []);
      } else {
        setScanners([]);
        setScannersError(res.msg || t("settings.hardware.scannerListFailed"));
      }
    } catch (e: any) {
      setScanners([]);
      setScannersError(e?.message || t("settings.hardware.scannerListFailed"));
    } finally {
      setScannersLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void refreshScanners();
  }, [refreshScanners]);

  const currentPrinter =
    printPrefs.selectedPrinter === PRINTER_DEFAULT
      ? printers.find((p) => p.is_default)
      : printers.find((p) => p.name === printPrefs.selectedPrinter);

  // ---- 自助文印状态机：扫描 → 批阅 → 打印 ----
  const pollScanImport = async (): Promise<{
    imported: number;
    error: boolean;
  }> => {
    // 每 2s 轮询一次，最多等 90s（防止扫描物未放入时无限等待）
    const maxTries = 45;
    for (let i = 0; i < maxTries; i++) {
      if (!selfPrintActiveRef.current) return { imported: 0, error: true };
      let st: Awaited<ReturnType<typeof getScanImportStatus>> | null = null;
      try {
        st = await getScanImportStatus();
      } catch (e: any) {
        if (isAuthError(e)) throw e;
      }
      if (st && st.ok) {
        if (st.error) return { imported: st.imported_count || 0, error: true };
        if ((st.imported_count || 0) > 0)
          return { imported: st.imported_count || 0, error: false };
      }
      await sleep(2000);
    }
    // 超时降级：直接继续批阅已有文件
    return { imported: 0, error: false };
  };

  const pollGradeStatus = async (
    folder: string,
    jobId: string,
  ): Promise<Awaited<ReturnType<typeof referenceGradeStatus>> | null> => {
    // 最多等 10 分钟
    const maxTries = 300;
    for (let i = 0; i < maxTries; i++) {
      if (!selfPrintActiveRef.current) return null;
      let st: Awaited<ReturnType<typeof referenceGradeStatus>> | null = null;
      try {
        st = await referenceGradeStatus(folder, jobId);
      } catch (e: any) {
        if (isAuthError(e)) throw e;
      }
      if (st && st.ok) {
        const done =
          !!st.done ||
          (st.total > 0 &&
            (st.completed?.length || 0) + (st.failed?.length || 0) >= st.total);
        if (done) return st;
      }
      await sleep(2000);
    }
    return null;
  };

  const pollPrintStatus = async (
    jobId: string,
  ): Promise<Awaited<ReturnType<typeof printMarksBatchStatus>> | null> => {
    const maxTries = 300;
    for (let i = 0; i < maxTries; i++) {
      if (!selfPrintActiveRef.current) return null;
      let st: Awaited<ReturnType<typeof printMarksBatchStatus>> | null = null;
      try {
        st = await printMarksBatchStatus(jobId);
      } catch (e: any) {
        if (isAuthError(e)) throw e;
      }
      if (st && st.ok && st.done) return st;
      await sleep(2000);
    }
    return null;
  };

  const markCurrentStepError = () => {
    setStepStates((prev) => ({
      ...prev,
      [selfPrintStepRef.current]: "error",
    }));
  };

  const runSelfPrint = async () => {
    if (!selectedFolder) {
      toast.error(t("grading.selfPrint.error.noFolder"));
      return;
    }
    if (selfPrinting) return;
    selfPrintActiveRef.current = true;
    setSelfPrinting(true);
    setStepStates({ ...INITIAL_STEP_STATES, scan: "running" });
    try {
      // 步骤 1：扫描（有可用扫描仪时主动触发一次；失败降级靠 scan-import 目录监测自动导入）
      selfPrintStepRef.current = "scan";
      const scannerId = scanners.find((s) => s.available)?.id;
      if (scannerId) {
        try {
          await triggerScan(selectedFolder, scannerId);
        } catch (e: any) {
          if (isAuthError(e)) {
            markCurrentStepError();
            toast.error(t("grading.selfPrint.error.auth"));
            return;
          }
          // 触发失败：不阻塞流程，继续启动目录监测
        }
      }
      if (!selfPrintActiveRef.current) return;
      await startScanImport(selectedFolder);
      const scanResult = await pollScanImport();
      if (!selfPrintActiveRef.current) return;
      if (scanResult.error) {
        markCurrentStepError();
        toast.error(t("grading.selfPrint.error.scan"));
        return;
      }
      setStepStates({ scan: "done", grade: "running", print: "pending" });

      // 步骤 2：批阅（参照答案批改引擎）
      selfPrintStepRef.current = "grade";
      const gradeRes = await startReferenceGrade(selectedFolder, "aliyun");
      if (!gradeRes.ok || !gradeRes.job_id) {
        throw new Error(t("grading.selfPrint.error.gradeStart"));
      }
      selfPrintGradeJobRef.current = gradeRes.job_id;
      const gradeSt = await pollGradeStatus(selectedFolder, gradeRes.job_id);
      if (!selfPrintActiveRef.current) return;
      selfPrintGradeJobRef.current = null;
      if (!gradeSt) {
        throw new Error(t("grading.selfPrint.error.gradeTimeout"));
      }
      const filenames = (gradeSt.completed || [])
        .map((c) => marksOnlyFilenameFromUrl(c.image_marks_only))
        .filter((x): x is string => !!x);
      if (filenames.length === 0) {
        // 没有可打印的留痕：流程收尾
        setStepStates({ scan: "done", grade: "done", print: "done" });
        toast.error(t("grading.toast.noPrintableMarks"));
        return;
      }
      setStepStates({ scan: "done", grade: "done", print: "running" });

      // 步骤 3：打印
      selfPrintStepRef.current = "print";
      const customPaper = printPrefs.getCustomPaperSetting((msg) =>
        toast.error(msg),
      );
      if (printPrefs.printPaperSize === "custom" && !customPaper) {
        markCurrentStepError();
        toast.error(t("grading.selfPrint.error.customPaper"));
        return;
      }
      const outputMode = printerOutputMode(printPrefs.selectedPrinter);
      if (outputMode === "pdf" || outputMode === "browser") {
        if (outputMode === "pdf") {
          await exportMarksPdf(filenames);
          toast.success(t("grading.toast.pdfDownloaded"));
        } else {
          await browserPrintMarksPdf(filenames);
          toast.success(t("grading.selfPrint.done"));
        }
        setStepStates({ scan: "done", grade: "done", print: "done" });
        return;
      }
      const printRes = await startPrintMarksBatch(
        filenames,
        printPrefs.resolvePrinterName(),
        printPrefs.printMode,
        printPrefs.printPaperSize,
        customPaper,
        printPrefs.paperSourceId > 0 ? printPrefs.paperSourceId : undefined,
      );
      if (!printRes.ok || !printRes.job_id) {
        throw new Error(t("grading.selfPrint.error.printStart"));
      }
      selfPrintPrintJobRef.current = printRes.job_id;
      const printSt = await pollPrintStatus(printRes.job_id);
      if (!selfPrintActiveRef.current) return;
      selfPrintPrintJobRef.current = null;
      if (!printSt) {
        throw new Error(t("grading.selfPrint.error.printTimeout"));
      }
      setStepStates({ scan: "done", grade: "done", print: "done" });
      toast.success(t("grading.selfPrint.done"));
    } catch (e: any) {
      markCurrentStepError();
      if (isAuthError(e)) {
        toast.error(t("grading.selfPrint.error.auth"));
      } else {
        toast.error(e?.message || t("grading.selfPrint.error.generic"));
      }
    } finally {
      selfPrintActiveRef.current = false;
      setSelfPrinting(false);
    }
  };

  const stopSelfPrint = () => {
    if (!selfPrinting) return;
    selfPrintActiveRef.current = false;
    setSelfPrinting(false);
    if (selectedFolder) {
      void stopScanImport().catch(() => {});
    }
    if (selfPrintGradeJobRef.current && selectedFolder) {
      void cancelReferenceGrade(
        selectedFolder,
        selfPrintGradeJobRef.current,
      ).catch(() => {});
      selfPrintGradeJobRef.current = null;
    }
    if (selfPrintPrintJobRef.current) {
      void cancelPrintMarksBatch(selfPrintPrintJobRef.current).catch(() => {});
      selfPrintPrintJobRef.current = null;
    }
    toast.info(t("grading.selfPrint.cancelled"));
  };

  const stepDot = (state: SelfPrintStepState) => {
    switch (state) {
      case "done":
        return <CheckCircle2 className="w-4 h-4 text-emerald-500" />;
      case "running":
        return <Loader2 className="w-4 h-4 animate-spin text-primary" />;
      case "error":
        return <XCircle className="w-4 h-4 text-destructive" />;
      default:
        return <Circle className="w-4 h-4 text-muted-foreground/50" />;
    }
  };

  const stepLabel = (step: SelfPrintStep) =>
    t(
      step === "scan"
        ? "grading.selfPrint.stepScan"
        : step === "grade"
          ? "grading.selfPrint.stepGrade"
          : "grading.selfPrint.stepPrint",
    );

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
          <UserCog className="w-5 h-5 text-primary" />
        </div>
        <div>
          <h2 className="text-xl font-semibold text-foreground">
            {t("settings.hardware.title")}
          </h2>
          <p className="text-sm text-muted-foreground">
            {t("settings.hardware.subtitle")}
          </p>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <Printer className="w-4 h-4 text-primary" />
                {t("settings.hardware.printer")}
              </CardTitle>
              <CardDescription className="mt-1">
                {t("settings.hardware.printerDesc")}
              </CardDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => void refreshPrinters()}
              disabled={printersLoading}
            >
              {printersLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <RefreshCw className="w-4 h-4" />
              )}
              {t("settings.hardware.refreshList")}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {printersError ? (
            <p className="text-sm text-destructive">{printersError}</p>
          ) : null}
          {currentPrinter ? (
            <div className="flex items-center gap-2 text-sm">
              <span
                className={cn(
                  "w-2 h-2 rounded-full shrink-0",
                  currentPrinter.ready
                    ? "bg-emerald-500"
                    : "bg-muted-foreground/50",
                )}
              />
              <span className="text-muted-foreground">
                {t("settings.hardware.current", { name: currentPrinter.name })}
                {currentPrinter.is_default
                  ? t("settings.hardware.systemDefault")
                  : ""}{" "}
                · {currentPrinter.status_text}
              </span>
            </div>
          ) : null}
          <PrinterSettingsPanel
            printers={printers}
            printersLoading={printersLoading}
            selectedPrinter={printPrefs.selectedPrinter}
            onSelectedPrinterChange={printPrefs.setSelectedPrinter}
            printPaperSize={printPrefs.printPaperSize}
            onPrintPaperSizeChange={printPrefs.setPrintPaperSize}
            customPaperWidthMm={printPrefs.customPaperWidthMm}
            onCustomPaperWidthMmChange={printPrefs.setCustomPaperWidthMm}
            customPaperHeightMm={printPrefs.customPaperHeightMm}
            onCustomPaperHeightMmChange={printPrefs.setCustomPaperHeightMm}
            paperSourceId={printPrefs.paperSourceId}
            onPaperSourceIdChange={printPrefs.setPaperSourceId}
            printMode={printPrefs.printMode}
            onPrintModeChange={printPrefs.setPrintMode}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <ScanLine className="w-4 h-4 text-primary" />
                {t("settings.hardware.scanner")}
              </CardTitle>
              <CardDescription className="mt-1">
                {t("settings.hardware.scannerDesc")}
              </CardDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => void refreshScanners()}
              disabled={scannersLoading}
            >
              {scannersLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <RefreshCw className="w-4 h-4" />
              )}
              {t("settings.hardware.refreshList")}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {scannersLoading && scanners.length === 0 ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
              <Loader2 className="w-4 h-4 animate-spin" />
              {t("settings.hardware.detecting")}
            </div>
          ) : null}
          {scannersError ? (
            <p className="text-sm text-destructive mb-3">{scannersError}</p>
          ) : null}
          {!scannersLoading && scanners.length === 0 && !scannersError ? (
            <p className="text-sm text-muted-foreground py-2">
              {t("settings.hardware.noScanner")}
              <span className="text-destructive">
                {t("settings.hardware.noScannerHint")}
              </span>
            </p>
          ) : null}
          {scanners.length > 0 ? (
            <ul className="space-y-2">
              {scanners.map((scanner) => (
                <li
                  key={scanner.id || scanner.name}
                  className="flex items-start justify-between gap-3 rounded-lg border border-border/60 bg-muted/20 px-3 py-2.5"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                      {scanner.name}
                    </p>
                    {scanner.manufacturer ? (
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {t("settings.hardware.manufacturer", {
                          name: scanner.manufacturer,
                        })}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span
                      className={cn(
                        "w-2 h-2 rounded-full",
                        scanner.available
                          ? "bg-emerald-500"
                          : "bg-muted-foreground/50",
                      )}
                    />
                    <span
                      className={cn(
                        "text-xs",
                        scanner.available
                          ? "text-emerald-600"
                          : "text-muted-foreground",
                      )}
                    >
                      {scanner.available
                        ? t("settings.hardware.available")
                        : t("settings.hardware.unavailable")}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-primary" />
            {t("grading.selfPrint.title")}
          </CardTitle>
          <CardDescription className="mt-1">
            {t("grading.selfPrint.desc")}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">
              {t("grading.selfPrint.folder")}
            </Label>
            <Select
              value={selectedFolder}
              onValueChange={setSelectedFolder}
              disabled={selfPrinting}
            >
              <SelectTrigger className="w-full">
                <SelectValue
                  placeholder={t("grading.selfPrint.folderPlaceholder")}
                />
              </SelectTrigger>
              <SelectContent>
                {folders.map((f) => (
                  <SelectItem key={f} value={f}>
                    {f}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-3">
            {SELF_PRINT_STEPS.map((step, idx) => (
              <div key={step} className="flex items-center gap-2 flex-1">
                <span
                  className={cn(
                    "flex items-center gap-1.5 text-sm",
                    stepStates[step] === "error"
                      ? "text-destructive"
                      : stepStates[step] === "running"
                        ? "text-foreground"
                        : "text-muted-foreground",
                  )}
                >
                  {stepDot(stepStates[step])}
                  {stepLabel(step)}
                </span>
                {idx < SELF_PRINT_STEPS.length - 1 ? (
                  <span className="h-px flex-1 bg-border" />
                ) : null}
              </div>
            ))}
          </div>

          <div className="flex items-center gap-2">
            {selfPrinting ? (
              <Button
                variant="outline"
                className="gap-1.5"
                onClick={stopSelfPrint}
              >
                <Square className="w-4 h-4" />
                {t("grading.selfPrint.stop")}
              </Button>
            ) : (
              <Button
                className="gap-1.5"
                onClick={() => void runSelfPrint()}
                disabled={!selectedFolder || foldersLoading}
              >
                {foldersLoading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Play className="w-4 h-4" />
                )}
                {t("grading.selfPrint.start")}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
