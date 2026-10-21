import { useState, type ChangeEvent } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  defaultGlobalPrintPrefs,
  PRINT_PAPER_OPTIONS,
  PRINTER_BROWSER,
  PRINTER_DEFAULT,
  PRINTER_PDF,
  readGlobalPrintPrefs,
  writeGlobalPrintPrefs,
  type GlobalPrintPrefs,
} from "@/lib/globalPrintPrefs";
import type { PrintPaperSize, PrinterItem } from "@/services/gradingApi";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useLocale } from "@/contexts/LocaleContext";
import { translatePrintPaperLabel } from "@/i18n";

export type PrinterSettingsPanelProps = {
  printers: PrinterItem[];
  printersLoading?: boolean;
  selectedPrinter: string;
  onSelectedPrinterChange: (value: string) => void;
  printPaperSize: PrintPaperSize;
  onPrintPaperSizeChange: (value: PrintPaperSize) => void;
  customPaperWidthMm: string;
  onCustomPaperWidthMmChange: (value: string) => void;
  customPaperHeightMm: string;
  onCustomPaperHeightMmChange: (value: string) => void;
  paperSourceId: number;
  onPaperSourceIdChange: (value: number) => void;
  printMode: "single" | "double";
  onPrintModeChange: (value: "single" | "double") => void;
  className?: string;
  selectTriggerClassName?: string;
};

export function PrinterSettingsPanel({
  printers,
  printersLoading = false,
  selectedPrinter,
  onSelectedPrinterChange,
  printPaperSize,
  onPrintPaperSizeChange,
  customPaperWidthMm,
  onCustomPaperWidthMmChange,
  customPaperHeightMm,
  onCustomPaperHeightMmChange,
  paperSourceId,
  onPaperSourceIdChange,
  printMode,
  onPrintModeChange,
  className,
  selectTriggerClassName,
}: PrinterSettingsPanelProps) {
  const { t, locale } = useLocale();

  // 三个新增控件（打印兼容模式 / 边距 / 份数）自管理读写 globalPrintPrefs，
  // 不新增 props，避免改动上层调用方。
  const [compatMode, setCompatMode] = useState<"standard" | "compat">(() => {
    const p = readGlobalPrintPrefs();
    return p.printMode === "compat" ? "compat" : "standard";
  });
  const [marginMm, setMarginMm] = useState<number>(() => {
    const p = readGlobalPrintPrefs();
    return typeof p.marginMm === "number" ? p.marginMm : 5;
  });
  const [copies, setCopies] = useState<number>(() => {
    const p = readGlobalPrintPrefs();
    return typeof p.copies === "number" ? p.copies : 1;
  });
  const [printWrongNotes, setPrintWrongNotes] = useState<boolean>(() => {
    const p = readGlobalPrintPrefs();
    return p.printWrongNotes ?? true;
  });

  const persistPrefs = (patch: Partial<GlobalPrintPrefs>) => {
    const merged: GlobalPrintPrefs = {
      ...defaultGlobalPrintPrefs(),
      ...readGlobalPrintPrefs(),
      ...patch,
    };
    writeGlobalPrintPrefs(merged);
  };

  const handleCompatModeChange = (value: "standard" | "compat") => {
    setCompatMode(value);
    persistPrefs({ printMode: value });
  };

  const handleMarginChange = (e: ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    if (raw === "") {
      setMarginMm(0);
      persistPrefs({ marginMm: 0 });
      return;
    }
    const n = Number(raw);
    if (!Number.isFinite(n)) return;
    const clamped = Math.min(50, Math.max(0, Math.trunc(n)));
    setMarginMm(clamped);
    persistPrefs({ marginMm: clamped });
  };

  const handleCopiesChange = (e: ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    if (raw === "") {
      setCopies(1);
      persistPrefs({ copies: 1 });
      return;
    }
    const n = Number(raw);
    if (!Number.isFinite(n)) return;
    const clamped = Math.min(10, Math.max(1, Math.trunc(n)));
    setCopies(clamped);
    persistPrefs({ copies: clamped });
  };

  const handlePrintWrongNotesChange = (checked: boolean) => {
    setPrintWrongNotes(checked);
    persistPrefs({ printWrongNotes: checked });
  };

  const activePrinter =
    selectedPrinter === PRINTER_DEFAULT
      ? printers.find((p) => p.is_default)
      : printers.find((p) => p.name === selectedPrinter);

  return (
    <div className={cn("space-y-4", className)}>
      <div className="space-y-2">
        <Label className="text-sm">{t("printer.selectPrinter")}</Label>
        <Select value={selectedPrinter} onValueChange={onSelectedPrinterChange}>
          <SelectTrigger
            className={cn("w-full h-9 text-sm", selectTriggerClassName)}
          >
            <SelectValue placeholder={t("printer.defaultPrinter")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={PRINTER_DEFAULT}>
              {t("printer.defaultPrinter")}
            </SelectItem>
            <SelectItem value={PRINTER_PDF}>
              {t("printer.exportPdf")}
            </SelectItem>
            <SelectItem value={PRINTER_BROWSER}>
              {t("printer.browserPrint")}
            </SelectItem>
            {printers.map((p) => (
              <SelectItem key={p.name} value={p.name}>
                {p.name}
                {p.is_default ? t("printer.defaultSuffix") : ""}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {printersLoading ? (
          <div className="text-xs text-muted-foreground flex items-center">
            <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" />
            {t("printer.loadingList")}
          </div>
        ) : null}
        {activePrinter ? (
          <p className="text-xs text-muted-foreground">
            {t("printer.status", { status: activePrinter.status_text })}
            {activePrinter.ready ? t("printer.ready") : t("printer.notReady")}
          </p>
        ) : null}
      </div>

      <div className="space-y-2">
        <Label className="text-sm">{t("printer.paperTray")}</Label>
        <Select
          value={String(paperSourceId)}
          onValueChange={(v) => {
            const n = Number(v);
            onPaperSourceIdChange(
              Number.isFinite(n) ? Math.max(0, Math.trunc(n)) : 0,
            );
          }}
        >
          <SelectTrigger
            className={cn("w-full h-9 text-sm", selectTriggerClassName)}
          >
            <SelectValue placeholder={t("printer.autoSelect")} />
          </SelectTrigger>
          <SelectContent className="max-h-72">
            <SelectItem value="0">
              {t("printer.autoSelectRecommended")}
            </SelectItem>
            {(activePrinter?.bins || []).map((b) => (
              <SelectItem key={b.id} value={String(b.id)}>
                {t("printer.trayItem", { name: b.name, id: b.id })}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label className="text-sm">{t("printer.paperSize")}</Label>
        <Select
          value={printPaperSize}
          onValueChange={(v) => onPrintPaperSizeChange(v as PrintPaperSize)}
        >
          <SelectTrigger
            className={cn("w-full h-9 text-sm", selectTriggerClassName)}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="max-h-72">
            {PRINT_PAPER_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {translatePrintPaperLabel(locale, opt.value)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {printPaperSize === "custom" ? (
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-2">
            <Label className="text-sm">{t("printer.customWidth")}</Label>
            <Input
              value={customPaperWidthMm}
              onChange={(e) => onCustomPaperWidthMmChange(e.target.value)}
              inputMode="decimal"
              placeholder={t("printer.widthPlaceholder")}
              className={cn("h-9 text-sm", selectTriggerClassName)}
            />
          </div>
          <div className="space-y-2">
            <Label className="text-sm">{t("printer.customHeight")}</Label>
            <Input
              value={customPaperHeightMm}
              onChange={(e) => onCustomPaperHeightMmChange(e.target.value)}
              inputMode="decimal"
              placeholder={t("printer.heightPlaceholder")}
              className={cn("h-9 text-sm", selectTriggerClassName)}
            />
          </div>
        </div>
      ) : null}

      <div className="space-y-2">
        <Label className="text-sm">{t("printer.printMode")}</Label>
        <Select
          value={printMode}
          onValueChange={(v) => onPrintModeChange(v as "single" | "double")}
        >
          <SelectTrigger
            className={cn("w-full h-9 text-sm", selectTriggerClassName)}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="single">{t("printer.modeSingle")}</SelectItem>
            <SelectItem value="double">{t("printer.modeDouble")}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label className="text-sm">{t("printer.compatModeLabel")}</Label>
        <Select
          value={compatMode}
          onValueChange={(v) =>
            handleCompatModeChange(v as "standard" | "compat")
          }
        >
          <SelectTrigger
            className={cn("w-full h-9 text-sm", selectTriggerClassName)}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="standard">
              {t("printer.compatModeStandard")}
            </SelectItem>
            <SelectItem value="compat">
              {t("printer.compatModeCompat")}
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label className="text-sm">{t("printer.margin")}</Label>
          <Input
            type="number"
            min={0}
            max={50}
            value={marginMm}
            onChange={handleMarginChange}
            className={cn("h-9 text-sm", selectTriggerClassName)}
          />
        </div>
        <div className="space-y-2">
          <Label className="text-sm">{t("printer.copies")}</Label>
          <Input
            type="number"
            min={1}
            max={10}
            value={copies}
            onChange={handleCopiesChange}
            className={cn("h-9 text-sm", selectTriggerClassName)}
          />
        </div>
      </div>

      <div className="flex items-center justify-between gap-3">
        <div className="space-y-0.5">
          <Label className="text-sm">{t("printer.printWrongNotes")}</Label>
          <p className="text-xs text-muted-foreground">
            {t("printer.printWrongNotesHint")}
          </p>
        </div>
        <Switch
          checked={printWrongNotes}
          onCheckedChange={handlePrintWrongNotesChange}
        />
      </div>
    </div>
  );
}
