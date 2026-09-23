import { useLocale } from "@/contexts/LocaleContext";

/* 命题质量雷达图：依赖难度/区分度/信度等测量学指标，后端暂未产出 → 降级展示 */
export function QualityRadarChart() {
  const { t } = useLocale();
  return (
    <div className="space-y-1">
      <p className="text-[11px] text-muted-foreground font-medium">{t("classDetail.qualityRadarTitle")}</p>
      <div className="h-[120px] rounded-lg border border-dashed border-border/60 flex flex-col items-center justify-center gap-1 text-center px-4">
        <span className="text-xs text-muted-foreground/60">{t("classDetail.metricNotSupported")}</span>
        <span className="text-[10px] text-muted-foreground/50">{t("classDetail.qualityRadarDesc")}</span>
      </div>
    </div>
  );
}
