import { useCallback, useEffect, useRef, useState } from "react";
import type { PrintPaperSize } from "@/services/gradingApi";
import {
  buildCustomPaperMm,
  defaultGlobalPrintPrefs,
  GLOBAL_PRINT_PREFS_EVENT,
  GLOBAL_PRINT_PREFS_KEY,
  readGlobalPrintPrefs,
  resolvePrinterApiName,
  writeGlobalPrintPrefs,
  type GlobalPrintPrefs,
} from "@/lib/globalPrintPrefs";

export function useGlobalPrintPrefs() {
  const defaults = defaultGlobalPrintPrefs();
  const [loaded, setLoaded] = useState(false);
  const [selectedPrinter, setSelectedPrinter] = useState(defaults.printer);
  const [printPaperSize, setPrintPaperSize] = useState<PrintPaperSize>(
    defaults.paper_size,
  );
  const [customPaperWidthMm, setCustomPaperWidthMm] = useState(
    defaults.custom_paper_width_mm,
  );
  const [customPaperHeightMm, setCustomPaperHeightMm] = useState(
    defaults.custom_paper_height_mm,
  );
  const [printMode, setPrintMode] = useState<"single" | "double">(
    defaults.print_mode,
  );
  const [paperSourceId, setPaperSourceId] = useState(defaults.paper_source);
  const [compatMode, setCompatMode] = useState<"standard" | "compat">(
    defaults.printMode,
  );
  const [marginMm, setMarginMm] = useState(defaults.marginMm);
  const [copies, setCopies] = useState(defaults.copies);
  const [printWrongNotes, setPrintWrongNotes] = useState(
    defaults.printWrongNotes ?? true,
  );
  const applyingExternalRef = useRef(false);

  const applyPrefs = useCallback((prefs: Partial<GlobalPrintPrefs>) => {
    applyingExternalRef.current = true;
    if (typeof prefs.printer === "string") setSelectedPrinter(prefs.printer);
    if (prefs.paper_size) setPrintPaperSize(prefs.paper_size);
    if (typeof prefs.custom_paper_width_mm === "string")
      setCustomPaperWidthMm(prefs.custom_paper_width_mm);
    if (typeof prefs.custom_paper_height_mm === "string")
      setCustomPaperHeightMm(prefs.custom_paper_height_mm);
    if (prefs.print_mode) setPrintMode(prefs.print_mode);
    if (typeof prefs.paper_source === "number")
      setPaperSourceId(prefs.paper_source);
    if (prefs.printMode) setCompatMode(prefs.printMode);
    if (typeof prefs.marginMm === "number") setMarginMm(prefs.marginMm);
    if (typeof prefs.copies === "number") setCopies(prefs.copies);
    if (typeof prefs.printWrongNotes === "boolean")
      setPrintWrongNotes(prefs.printWrongNotes);
    queueMicrotask(() => {
      applyingExternalRef.current = false;
    });
  }, []);

  useEffect(() => {
    applyPrefs(readGlobalPrintPrefs());
    setLoaded(true);
  }, [applyPrefs]);

  useEffect(() => {
    if (!loaded || applyingExternalRef.current) return;
    writeGlobalPrintPrefs({
      printer: selectedPrinter,
      paper_size: printPaperSize,
      custom_paper_width_mm: customPaperWidthMm,
      custom_paper_height_mm: customPaperHeightMm,
      print_mode: printMode,
      paper_source: paperSourceId,
      printMode: compatMode,
      marginMm,
      copies,
      printWrongNotes,
    });
  }, [
    loaded,
    selectedPrinter,
    printPaperSize,
    customPaperWidthMm,
    customPaperHeightMm,
    printMode,
    paperSourceId,
    compatMode,
    marginMm,
    copies,
    printWrongNotes,
  ]);

  useEffect(() => {
    const syncFromStorage = () => applyPrefs(readGlobalPrintPrefs());
    window.addEventListener(GLOBAL_PRINT_PREFS_EVENT, syncFromStorage);
    const onStorage = (e: StorageEvent) => {
      if (e.key === GLOBAL_PRINT_PREFS_KEY) syncFromStorage();
    };
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(GLOBAL_PRINT_PREFS_EVENT, syncFromStorage);
      window.removeEventListener("storage", onStorage);
    };
  }, [applyPrefs]);

  const getCustomPaperSetting = useCallback(
    (onError?: (message: string) => void) =>
      buildCustomPaperMm(
        printPaperSize,
        customPaperWidthMm,
        customPaperHeightMm,
        onError,
      ),
    [printPaperSize, customPaperWidthMm, customPaperHeightMm],
  );

  return {
    loaded,
    selectedPrinter,
    setSelectedPrinter,
    printPaperSize,
    setPrintPaperSize,
    customPaperWidthMm,
    setCustomPaperWidthMm,
    customPaperHeightMm,
    setCustomPaperHeightMm,
    printMode,
    setPrintMode,
    paperSourceId,
    setPaperSourceId,
    compatMode,
    setCompatMode,
    marginMm,
    setMarginMm,
    copies,
    setCopies,
    printWrongNotes,
    setPrintWrongNotes,
    resolvePrinterName: () => resolvePrinterApiName(selectedPrinter),
    getCustomPaperSetting,
  };
}
