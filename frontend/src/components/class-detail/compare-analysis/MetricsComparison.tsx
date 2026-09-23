import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLocale } from "@/contexts/LocaleContext";
import { Inbox } from "lucide-react";
import type { CoreMetricRow, WeakPointItem } from "./compareAnalysisAdapter";

interface MetricsComparisonProps {
  rows: CoreMetricRow[];
  strengths: string[];
  weakPoints: WeakPointItem[];
  examName: string;
}

export function MetricsComparison({ rows, strengths, weakPoints, examName }: MetricsComparisonProps) {
  const { t } = useLocale();

  return (
    <Card data-tour="ca-metrics" className="flex-1 min-w-[360px]">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">{t("classDetail.compare.metrics.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-xs">
        {rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center text-sm text-muted-foreground">
            <Inbox className="mb-2 h-6 w-6" />
            {t("classDetail.暂无数据")}
            <span className="mt-1 text-[11px]">{t("classDetail.compare.metrics.noData")}</span>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border/40 text-muted-foreground">
                    <th className="text-left py-1.5 font-medium">{t("classDetail.compare.metrics.metricHeader")}</th>
                    <th className="text-center py-1.5 font-medium">{t("classDetail.compare.metrics.thisClassHeader")}</th>
                    <th className="text-center py-1.5 font-medium">{t("classDetail.compare.metrics.descriptionHeader")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((m) => (
                    <tr key={m.label} className="border-b border-border/20">
                      <td className="py-1.5 font-medium text-foreground">{m.label}</td>
                      <td className="text-center font-semibold text-foreground">
                        {m.unsupported ? <span className="text-muted-foreground font-normal">{t("classDetail.compare.metrics.notSupported")}</span> : `${m.value ?? "--"}${m.unit}`}
                      </td>
                      <td className="text-center text-[11px] text-muted-foreground">
                        {m.unsupported ? t("classDetail.compare.metrics.noDataSource") : m.higherBetter ? t("classDetail.compare.metrics.higherBetter") : t("classDetail.compare.metrics.lowerBetter")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="rounded-md border border-dashed border-border/60 px-2.5 py-1.5 text-[11px] text-muted-foreground">
              {examName ? t("classDetail.compare.metrics.dataSourceLabel", { exam: examName }) : ""}{t("classDetail.compare.metrics.benchmarkNote")}
            </p>
          </>
        )}

        {(strengths.length > 0 || weakPoints.length > 0) && (
          <div data-tour="ca-findings" className="rounded-lg border border-border/50 p-3 space-y-1.5">
            <p className="text-[11px] font-semibold text-foreground">{t("classDetail.关键发现")}</p>
            {weakPoints.length > 0 && (
              <p className="text-[11px] text-muted-foreground">
                {t("classDetail.compare.metrics.findingsWeakPoints", { points: weakPoints.map((w) => w.knowledgePoint).join("、") })}
              </p>
            )}
            {strengths.length > 0 && (
              <p className="text-[11px] text-muted-foreground">
                {t("classDetail.compare.metrics.findingsStrengths", { strengths: strengths.join("、") })}
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
