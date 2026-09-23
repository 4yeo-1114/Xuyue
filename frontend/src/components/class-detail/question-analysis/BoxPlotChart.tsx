import { useLocale } from "@/contexts/LocaleContext";

/* 箱线图：依赖标准差/四分位等统计指标，后端暂未产出 → 降级展示 */
export function BoxPlotChart() {
  const { t } = useLocale();
  return (
    <div className="space-y-1">
      <p className="text-[11px] text-muted-foreground font-medium">{t("classDetail.boxPlotTitle")}</p>
      <div className="h-[100px] rounded-lg border border-dashed border-border/60 flex flex-col items-center justify-center gap-1 text-center px-4">
        <span className="text-xs text-muted-foreground/60">{t("classDetail.metricNotSupported")}</span>
        <span className="text-[10px] text-muted-foreground/50">{t("classDetail.boxPlotNotSupportedDesc")}</span>
      </div>
    </div>
  );
}
