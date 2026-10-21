import type { CustomPaperMm, PrintPaperSize } from "@/services/gradingApi";

export const PRINTER_DEFAULT = "__default__";
/** 虚拟打印机：导出留痕 PDF（下载保存），不触发物理打印 */
export const PRINTER_PDF = "__pdf__";
/** 虚拟打印机：浏览器打印（导出 PDF 后在新标签页打开打印对话框） */
export const PRINTER_BROWSER = "__browser__";
export const GLOBAL_PRINT_PREFS_KEY = "grading_global_print_prefs_v1";
export const GLOBAL_PRINT_PREFS_EVENT = "grading-global-print-prefs-changed";

const VALID_PRINT_PAPER = new Set<PrintPaperSize>([
  "default",
  "a3",
  "a4",
  "a5",
  "b4",
  "b5",
  "letter",
  "legal",
  "tabloid",
  "custom",
]);

export const PRINT_PAPER_OPTIONS: { value: PrintPaperSize; label: string }[] = [
  { value: "default", label: "默认（跟随打印机驱动，不强制纸张）" },
  { value: "a3", label: "A3 — 297×420 mm（ISO）" },
  { value: "a4", label: "A4 — 210×297 mm（ISO）" },
  { value: "a5", label: "A5 — 148×210 mm（ISO）" },
  { value: "b4", label: "B4（JIS）— 257×364 mm" },
  { value: "b5", label: "B5（JIS）— 182×257 mm" },
  { value: "letter", label: "Letter — 216×279 mm（8.5×11 in）" },
  { value: "legal", label: "Legal — 216×356 mm（8.5×14 in）" },
  { value: "tabloid", label: "Tabloid — 279×432 mm（11×17 in）" },
  { value: "custom", label: "自定义 — 手动输入宽高（mm）" },
];

export type GlobalPrintPrefs = {
  printer: string;
  paper_size: PrintPaperSize;
  custom_paper_width_mm: string;
  custom_paper_height_mm: string;
  print_mode: "single" | "double";
  paper_source: number;
  /** 打印兼容开关：standard=保持原打印行为，compat=注入打印优化样式 */
  printMode?: "standard" | "compat";
  /** 兼容模式页边距（mm），0~50 */
  marginMm?: number;
  /** 打印份数，1~10 */
  copies?: number;
  /** 打印批注：开=用带错因批注的留痕图，关=普通留痕图（默认开） */
  printWrongNotes?: boolean;
};

export function parseStoredPaperSize(raw: unknown): PrintPaperSize | undefined {
  if (typeof raw !== "string") return undefined;
  const s = raw.trim().toLowerCase() as PrintPaperSize;
  return VALID_PRINT_PAPER.has(s) ? s : undefined;
}

export function readGlobalPrintPrefs(): Partial<GlobalPrintPrefs> {
  try {
    const raw = localStorage.getItem(GLOBAL_PRINT_PREFS_KEY);
    if (!raw) return {};
    const j = JSON.parse(raw);
    return {
      printer: typeof j?.printer === "string" ? j.printer : undefined,
      paper_size: parseStoredPaperSize(j?.paper_size),
      custom_paper_width_mm:
        typeof j?.custom_paper_width_mm === "string" ? j.custom_paper_width_mm : undefined,
      custom_paper_height_mm:
        typeof j?.custom_paper_height_mm === "string" ? j.custom_paper_height_mm : undefined,
      print_mode: j?.print_mode === "single" || j?.print_mode === "double" ? j.print_mode : undefined,
      paper_source: typeof j?.paper_source === "number" ? j.paper_source : undefined,
      printMode: j?.printMode === "compat" ? "compat" : "standard",
      marginMm:
        typeof j?.marginMm === "number" && Number.isFinite(j.marginMm) ? j.marginMm : undefined,
      copies: typeof j?.copies === "number" && Number.isFinite(j.copies) ? j.copies : undefined,
      printWrongNotes:
        typeof j?.printWrongNotes === "boolean" ? j.printWrongNotes : undefined,
    };
  } catch {
    return {};
  }
}

export function writeGlobalPrintPrefs(prefs: GlobalPrintPrefs): void {
  try {
    localStorage.setItem(
      GLOBAL_PRINT_PREFS_KEY,
      JSON.stringify({
        printer: prefs.printer,
        paper_size: prefs.paper_size,
        custom_paper_width_mm: prefs.custom_paper_width_mm,
        custom_paper_height_mm: prefs.custom_paper_height_mm,
        print_mode: prefs.print_mode,
        paper_source: prefs.paper_source > 0 ? prefs.paper_source : undefined,
        printMode: prefs.printMode,
        marginMm: prefs.marginMm,
        copies: prefs.copies,
        printWrongNotes: prefs.printWrongNotes,
      })
    );
    window.dispatchEvent(new CustomEvent(GLOBAL_PRINT_PREFS_EVENT));
  } catch {
    //
  }
}

export function resolvePrinterApiName(selectedPrinter: string): string | undefined {
  return selectedPrinter === PRINTER_DEFAULT ? undefined : selectedPrinter;
}

/** 打印输出方式：physical=实体打印机（后端 CUPS），pdf=导出 PDF 下载，browser=浏览器打印 */
export type PrinterOutputMode = "physical" | "pdf" | "browser";

/** 判断选中的打印机是否为虚拟输出（PDF/浏览器打印） */
export function isVirtualPrinter(selectedPrinter: string): boolean {
  return selectedPrinter === PRINTER_PDF || selectedPrinter === PRINTER_BROWSER;
}

/** 把 selectedPrinter 归一化为输出方式 */
export function printerOutputMode(selectedPrinter: string): PrinterOutputMode {
  if (selectedPrinter === PRINTER_PDF) return "pdf";
  if (selectedPrinter === PRINTER_BROWSER) return "browser";
  return "physical";
}

export function buildCustomPaperMm(
  printPaperSize: PrintPaperSize,
  customPaperWidthMm: string,
  customPaperHeightMm: string,
  onError?: (message: string) => void
): CustomPaperMm | undefined {
  if (printPaperSize !== "custom") return undefined;
  const w = Number(customPaperWidthMm);
  const h = Number(customPaperHeightMm);
  if (!Number.isFinite(w) || !Number.isFinite(h)) {
    onError?.("自定义纸张宽高必须是数字（单位 mm）");
    return undefined;
  }
  if (w < 50 || w > 1200 || h < 50 || h > 1200) {
    onError?.("自定义纸张范围应在 50~1200 mm");
    return undefined;
  }
  return { widthMm: w, heightMm: h };
}

export function defaultGlobalPrintPrefs(): GlobalPrintPrefs {
  return {
    printer: PRINTER_DEFAULT,
    paper_size: "a4",
    custom_paper_width_mm: "210",
    custom_paper_height_mm: "297",
    print_mode: "single",
    paper_source: 0,
    printMode: "standard",
    marginMm: 5,
    copies: 1,
    printWrongNotes: true,
  };
}
