import { useEffect, useMemo, useState } from "react";
import {
  Camera,
  Printer,
  ScanLine,
  FileText,
  Eye,
  Settings,
  RefreshCw,
  Loader2,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { useIsMobile } from "@/hooks/use-mobile";
import {
  deleteHomeGrade,
  getHomeGradeDetail,
  listHomeRecentGrades,
  gradingImageUrl,
  type HomeRecentItem,
} from "@/services/gradingApi";
import type { GradingJobItem } from "@/services/api";
import { toast } from "sonner";
import { useGlobalPrintPrefs } from "@/hooks/useGlobalPrintPrefs";
import { usePrinters } from "@/hooks/usePrinters";
import { PrinterSettingsPanel } from "@/components/shared/PrinterSettingsPanel";
import { PRINTER_DEFAULT } from "@/lib/globalPrintPrefs";
import { useLocale } from "@/contexts/LocaleContext";
import {
  parseAiResultBlocks,
  type AiResultBlock,
} from "@/utils/aiResultBlocks";

interface GradingEntrySectionProps {
  selectedSubject: string;
  selectedClass: string;
  onPhotoClick?: () => void;
}

function imgUrl(p?: string | null) {
  return gradingImageUrl(p || undefined);
}

function formatRelativeTime(
  iso: string,
  t: (key: string, params?: Record<string, string | number>) => string,
) {
  if (!iso) return "";
  const ts = new Date(iso).getTime();
  if (!Number.isFinite(ts)) return iso;
  const diff = Date.now() - ts;
  const min = Math.floor(diff / 60000);
  if (min < 1) return t("home.grading.timeJustNow");
  if (min < 60) return t("home.grading.timeMinutesAgo", { min });
  const hr = Math.floor(min / 60);
  if (hr < 24) return t("home.grading.timeHoursAgo", { hr });
  return new Date(ts).toLocaleString();
}

export function GradingEntrySection({
  selectedSubject,
  selectedClass,
  onPhotoClick,
}: GradingEntrySectionProps) {
  const { t, locale } = useLocale();
  const isMobile = useIsMobile();

  const entryButtons = useMemo(
    () => [
      {
        icon: Camera,
        label: isMobile
          ? t("home.grading.photoMobile")
          : t("home.grading.photoDesktop"),
        desc: isMobile
          ? t("home.grading.photoDescMobile")
          : t("home.grading.photoDescDesktop"),
        color: "bg-primary/10 text-primary",
        onClick: onPhotoClick,
      },
    ],
    [isMobile, t, locale, onPhotoClick],
  );

  const [recent, setRecent] = useState<HomeRecentItem[]>([]);
  const [recentLoading, setRecentLoading] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detail, setDetail] = useState<GradingJobItem | null>(null);
  const [detailShowOriginal, setDetailShowOriginal] = useState(false);
  const detailAiBlocks = useMemo(
    () => parseAiResultBlocks(detail?.result || "", t),
    [detail?.result, t],
  );
  const renderAiStatusCounts = (b: AiResultBlock) => {
    if (!b.subItems || b.subItems.length === 0) return null;

    let correct = 0;
    let wrong = 0;
    let partial = 0;
    b.subItems.forEach((sub) => {
      if (sub.status === "correct") correct++;
      else if (sub.status === "wrong" || sub.status === "blank") wrong++;
      else if (sub.status === "partial") partial++;
    });

    if (correct === 0 && wrong === 0 && partial === 0) return null;

    return (
      <div className="flex gap-1.5 text-[11px] font-medium ml-2">
        {correct > 0 && (
          <span className="text-green-600 bg-green-100/50 px-1.5 py-0.5 rounded border border-green-200/50">
            {t("home.grading.correctCount", { count: correct })}
          </span>
        )}
        {partial > 0 && (
          <span className="text-amber-600 bg-amber-100/50 px-1.5 py-0.5 rounded border border-amber-200/50">
            {t("home.grading.partialCount", { count: partial })}
          </span>
        )}
        {wrong > 0 && (
          <span className="text-red-600 bg-red-100/50 px-1.5 py-0.5 rounded border border-red-200/50">
            {t("home.grading.wrongCount", { count: wrong })}
          </span>
        )}
      </div>
    );
  };

  const loadRecent = useMemo(() => {
    return async () => {
      setRecentLoading(true);
      try {
        const r = await listHomeRecentGrades();
        setRecent(r.items || []);
      } catch {
        setRecent([]);
      } finally {
        setRecentLoading(false);
      }
    };
  }, []);

  useEffect(() => {
    void loadRecent();
  }, [loadRecent]);

  const hasInProgress = useMemo(() => {
    return recent.some((it) => {
      const st = String(it.status || "").toLowerCase();
      return st && st !== "done" && st !== "failed" && st !== "cancelled";
    });
  }, [recent]);

  useEffect(() => {
    if (!hasInProgress) return;
    const t = window.setInterval(() => void loadRecent(), 2000);
    return () => window.clearInterval(t);
  }, [hasInProgress, loadRecent]);

  useEffect(() => {
    const onUpdated = () => void loadRecent();
    try {
      window.addEventListener("home-grading-updated", onUpdated as any);
    } catch {
      //
    }
    return () => {
      try {
        window.removeEventListener("home-grading-updated", onUpdated as any);
      } catch {
        //
      }
    };
  }, [loadRecent]);

  const openDetail = async (id: string) => {
    setDetailOpen(true);
    setDetail(null);
    setDetailShowOriginal(false);
    setDetailLoading(true);
    try {
      const r = await getHomeGradeDetail(id);
      setDetail(r.item);
    } catch (e) {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const deleteRecent = async (id: string) => {
    if (!id) return;
    if (!window.confirm(t("home.grading.deleteConfirm"))) return;
    try {
      await deleteHomeGrade(id);
      toast.success(t("home.grading.deleted"));
      await loadRecent();
    } catch (e: any) {
      toast.error(
        e?.message ? String(e.message) : t("home.grading.deleteFailed"),
      );
    }
  };

  const [printSettingsOpen, setPrintSettingsOpen] = useState(false);
  const printPrefs = useGlobalPrintPrefs();
  const {
    printers,
    loading: printersLoading,
    refresh: refreshPrinters,
  } = usePrinters();

  const openPrintSettings = async () => {
    setPrintSettingsOpen(true);
    await refreshPrinters();
  };

  const currentPrinter =
    printPrefs.selectedPrinter === PRINTER_DEFAULT
      ? printers.find((p) => p.is_default)
      : printers.find((p) => p.name === printPrefs.selectedPrinter);

  useEffect(() => {
    void refreshPrinters();
  }, [refreshPrinters]);

  return (
    <div className="rounded-xl bg-primary/5 border border-primary/10 p-6 animate-fade-in">
      <h3 className="text-base font-semibold text-foreground mb-4">
        {t("home.grading.title")}
      </h3>

      <div className="flex flex-col gap-6 lg:flex-row lg:gap-6">
        <div className="lg:w-[420px]">
          <div
            data-tour="grading-entry"
            className="grid grid-cols-1 gap-4 mb-6"
          >
            {entryButtons.map((item) => (
              <button
                key={item.label}
                className="flex flex-col items-center gap-2 p-5 rounded-xl bg-card border border-border/50 hover:border-primary/30 hover:shadow-md transition-all duration-200 hover-scale cursor-pointer"
                onClick={item.onClick}
              >
                <div
                  className={cn(
                    "w-12 h-12 rounded-xl flex items-center justify-center",
                    item.color,
                  )}
                >
                  <item.icon className="w-6 h-6" />
                </div>
                <span className="text-sm font-medium text-foreground">
                  {item.label}
                </span>
                <span className="text-xs text-muted-foreground">
                  {item.desc}
                </span>
              </button>
            ))}
          </div>

          <div className="flex flex-col gap-3 text-sm">
            <span className="text-muted-foreground font-medium">
              {t("home.grading.hardwareStatus")}
            </span>
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Printer className="w-4 h-4 text-muted-foreground" />
                <span className="text-foreground">
                  {t("home.grading.printer")}
                </span>
                <span className="inline-flex items-center gap-1">
                  <span
                    className={cn(
                      "w-2 h-2 rounded-full",
                      currentPrinter?.ready
                        ? "bg-emerald-500 animate-pulse"
                        : "bg-muted-foreground/50",
                    )}
                  />
                  <span
                    className={cn(
                      "text-xs font-medium",
                      currentPrinter?.ready
                        ? "text-emerald-600"
                        : "text-muted-foreground",
                    )}
                  >
                    {currentPrinter?.ready
                      ? t("home.grading.statusOnline")
                      : currentPrinter
                        ? t("home.grading.statusUnavailable")
                        : t("home.grading.statusUndetected")}
                  </span>
                </span>
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs gap-1"
                onClick={openPrintSettings}
              >
                <Settings className="w-3 h-3" />{" "}
                {t("home.grading.printSettings")}
              </Button>
            </div>
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <ScanLine className="w-4 h-4 text-muted-foreground" />
                <span className="text-foreground">
                  {t("home.grading.scanner")}
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  <span className="text-emerald-600 text-xs font-medium">
                    {t("home.grading.statusOnline")}
                  </span>
                </span>
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs gap-1"
                disabled
              >
                <RefreshCw className="w-3 h-3" /> {t("home.grading.connected")}
              </Button>
            </div>
          </div>
        </div>

        <div className="hidden lg:block w-px bg-border/70 self-stretch" />

        <div data-tour="recent-files" className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-3 mb-3">
            <h4 className="text-sm font-medium text-muted-foreground">
              {t("home.grading.recentTitle")}
            </h4>
            {hasInProgress ? (
              <span className="text-xs text-muted-foreground">
                {t("home.grading.gradingInProgress")}
              </span>
            ) : null}
          </div>
          {recentLoading ? (
            <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              {t("common.loading")}
            </div>
          ) : recent.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              {t("home.grading.noRecords")}
            </div>
          ) : (
            <div className="space-y-2">
              {recent.map((file) => {
                const st = String(file.status || "").toLowerCase();
                const inProg =
                  st && st !== "done" && st !== "failed" && st !== "cancelled";
                const pct =
                  typeof file.progress === "number"
                    ? Math.max(0, Math.min(100, Math.round(file.progress)))
                    : null;
                const canView = st === "done" && file.ok !== false;
                return (
                  <div
                    key={file.id}
                    className="flex items-center justify-between py-2 px-3 rounded-lg bg-card/60 hover:bg-card transition-colors"
                  >
                    <div className="flex items-center gap-2 text-sm min-w-0">
                      <FileText className="w-4 h-4 text-primary/60 shrink-0" />
                      <span className="text-foreground truncate">
                        {file.name}
                      </span>
                      <span className="text-muted-foreground text-xs shrink-0">
                        {formatRelativeTime(file.created_at, t)}
                      </span>
                      {inProg ? (
                        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground shrink-0">
                          <Loader2 className="w-3 h-3 animate-spin" />
                          {pct != null
                            ? `${pct}%`
                            : t("home.grading.inProgress")}
                        </span>
                      ) : st === "failed" || file.ok === false ? (
                        <span className="text-xs text-red-600 shrink-0">
                          {t("home.grading.failed")}
                        </span>
                      ) : null}
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs gap-1"
                        disabled={!canView}
                        onClick={() => void openDetail(file.id)}
                      >
                        <Eye className="w-3 h-3" /> {t("home.grading.view")}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs gap-1 text-destructive hover:text-destructive"
                        onClick={() => void deleteRecent(file.id)}
                      >
                        <Trash2 className="w-3 h-3" />{" "}
                        {t("home.grading.delete")}
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <Dialog
        open={detailOpen}
        onOpenChange={(o) => {
          setDetailOpen(o);
          if (!o) setDetail(null);
        }}
      >
        <DialogContent className="max-h-[92vh] w-full max-w-[min(96vw,1120px)] flex flex-col gap-0 overflow-hidden p-0 sm:max-w-[min(96vw,1120px)]">
          <div className="shrink-0 border-b bg-muted/30 px-6 py-4 pr-14">
            <DialogHeader className="space-y-1 text-left">
              <DialogTitle className="text-lg">
                {t("home.grading.previewTitle")}
              </DialogTitle>
              <DialogDescription
                className="truncate"
                title={detail?.name || ""}
              >
                {detail?.name || "—"}
              </DialogDescription>
            </DialogHeader>
          </div>
          <div className="grid min-h-0 flex-1 grid-cols-1 gap-0 lg:grid-cols-2 lg:divide-x lg:min-h-[min(76vh,calc(92vh-6rem))]">
            <div className="flex min-h-0 flex-col gap-3 bg-muted/15 p-4 lg:h-full">
              <div className="flex shrink-0 items-center justify-between gap-2">
                <Label className="text-sm font-semibold text-foreground">
                  {t("home.grading.markPreview")}
                </Label>
                <div className="flex items-center gap-2">
                  {detail?.image_original && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setDetailShowOriginal((v) => !v)}
                      className="shrink-0"
                    >
                      {detailShowOriginal
                        ? t("home.grading.viewGraded")
                        : t("home.grading.viewOriginal")}
                    </Button>
                  )}
                </div>
              </div>
              <ScrollArea className="h-[min(52vh,480px)] w-full rounded-xl border border-border/80 bg-background shadow-inner lg:h-[min(68vh,calc(92vh-11rem))]">
                <div className="flex min-h-[200px] items-center justify-center p-4">
                  {detailLoading ? (
                    <div className="text-sm text-muted-foreground flex items-center">
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      {t("common.loading")}
                    </div>
                  ) : detail?.image_annotated ? (
                    <a
                      href={imgUrl(
                        detailShowOriginal
                          ? detail.image_original
                          : detail.image_annotated,
                      )}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-block max-w-full"
                    >
                      <img
                        src={imgUrl(
                          detailShowOriginal
                            ? detail.image_original
                            : detail.image_annotated,
                        )}
                        alt={
                          detailShowOriginal
                            ? t("home.grading.altOriginal")
                            : t("home.grading.altMarked")
                        }
                        className="max-h-[min(64vh,720px)] w-auto max-w-full object-contain"
                      />
                    </a>
                  ) : (
                    <div className="text-sm text-muted-foreground">
                      {t("home.grading.noMarkPreview")}
                    </div>
                  )}
                </div>
              </ScrollArea>
            </div>
            <div className="flex min-h-0 flex-col gap-3 p-4 lg:h-full">
              <Label className="shrink-0 text-sm font-semibold text-foreground">
                {t("home.grading.aiAnalysis")}
              </Label>
              <ScrollArea className="h-[min(52vh,480px)] w-full rounded-xl border border-border/80 bg-card p-4 text-sm leading-relaxed shadow-sm lg:h-[min(68vh,calc(92vh-11rem))]">
                {detailLoading ? (
                  <div className="text-sm text-muted-foreground flex items-center">
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    {t("common.loading")}
                  </div>
                ) : (
                  <div className="space-y-3">
                    {detailAiBlocks.map((b, idx) => (
                      <div key={`${b.title}-${idx}`}>
                        {idx > 0 && (
                          <div className="mb-3 border-t border-border/70" />
                        )}
                        <div className="mb-1.5 flex items-center">
                          <div className="text-xs font-semibold text-muted-foreground">
                            {b.title}
                          </div>
                          {renderAiStatusCounts(b)}
                        </div>
                        <div className="space-y-1.5">
                          {b.subItems && b.subItems.length > 0 ? (
                            b.subItems.map((sub, subIdx) => (
                              <div
                                key={subIdx}
                                className={cn(
                                  "whitespace-pre-wrap rounded-md px-2.5 py-1.5",
                                  sub.status === "wrong" ||
                                    sub.status === "blank"
                                    ? "bg-red-50 text-red-900 border border-red-100"
                                    : sub.status === "partial"
                                      ? "bg-amber-50 text-amber-900 border border-amber-100"
                                      : "text-foreground/95",
                                )}
                              >
                                {sub.content}
                              </div>
                            ))
                          ) : (
                            <p className="whitespace-pre-wrap text-foreground/95 px-2.5">
                              {b.content}
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </ScrollArea>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={printSettingsOpen} onOpenChange={setPrintSettingsOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("home.grading.printerSettingsTitle")}</DialogTitle>
            <DialogDescription>
              {t("home.grading.printerSettingsDesc")}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
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
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setPrintSettingsOpen(false)}
            >
              {t("home.grading.done")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
