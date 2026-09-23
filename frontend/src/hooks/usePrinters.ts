import { useCallback, useEffect, useState } from "react";
import { listPrinters, type PrinterItem } from "@/services/gradingApi";

export function usePrinters(autoLoad = false) {
  const [printers, setPrinters] = useState<PrinterItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listPrinters();
      if (res.ok && res.printers) {
        setPrinters(res.printers);
      } else {
        setPrinters([]);
        setError(res.msg || "获取打印机列表失败");
      }
    } catch (e: any) {
      setPrinters([]);
      setError(e?.message || "获取打印机列表失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (autoLoad) void refresh();
  }, [autoLoad, refresh]);

  return { printers, loading, error, refresh };
}
