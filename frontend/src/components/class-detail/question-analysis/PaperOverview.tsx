import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLocale } from "@/contexts/LocaleContext";
import type { QuestionAnalysisSummary } from "./types";

function DegradedMetric({ label }: { label: string }) {
  const { t } = useLocale();
  return (
    <div className="rounded-lg border border-dashed border-border/60 p-2.5 text-center">
      <p className="text-muted-foreground text-[11px]">{label}</p>
      <p className="text-lg font-bold text-muted-foreground/60 mt-0.5">--</p>
      <span className="inline-block mt-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-muted/50 text-muted-foreground/70">{t("classDetail.metricNotSupported")}</span>
    </div>
  );
}

export function PaperOverview({ summary }: { summary: QuestionAnalysisSummary }) {
  const { t } = useLocale();

  const answered = summary.correctCount + summary.wrongCount;
  const correctRate = answered > 0 ? Math.round((summary.correctCount / answered) * 100) : null;

  return (
    <Card className="flex-1 min-w-[320px]" data-tour="qa-overview">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">{t("classDetail.试卷质量概览")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-xs">
        {/* 真实作答概况 */}
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground">
          <span>{t("classDetail.validStudentCountColonLabel")}<strong className="text-foreground">{t("header.studentsCount", { count: summary.validStudentCount })}</strong></span>
          <span>{t("classDetail.questionCountColonLabel")}<strong className="text-foreground">{t("classDetail.questionUnit", { count: summary.questionCount })}</strong></span>
          <span>{t("classDetail.answerAreaCountLabel")}<strong className="text-foreground">{t("classDetail.countSuffixUnit", { count: summary.answerAreaCount })}</strong></span>
        </div>

        {/* 作答分布（真实数据） */}
        <div>
          <p className="text-muted-foreground mb-2 font-medium">{t("classDetail.answerDistribution")}</p>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-muted-foreground">
            <span>{t("classDetail.correctColonLabel")}<strong className="text-emerald-600">{summary.correctCount}</strong></span>
            <span>{t("classDetail.wrongColonLabel")}<strong className="text-red-600">{summary.wrongCount}</strong></span>
            <span>{t("classDetail.blankColonLabel")}<strong className="text-amber-600">{summary.blankCount}</strong></span>
            <span>{t("classDetail.correctRateColonLabel")}<strong className="text-foreground">{correctRate != null ? `${correctRate}%` : "--"}</strong></span>
            <span>{t("classDetail.classAvgScoreColonLabel")}<strong className="text-foreground">{summary.classAvgScore != null ? t("classDetail.scorePoints", { score: summary.classAvgScore }) : "--"}</strong></span>
          </div>
        </div>

        {/* 教育测量学指标：后端暂未产出 → 降级 */}
        <div>
          <p className="text-muted-foreground mb-2 font-medium">{t("classDetail.qualityMetricsTitle")}</p>
          <div className="grid grid-cols-3 gap-2">
            <DegradedMetric label={t("classDetail.难度")} />
            <DegradedMetric label={t("classDetail.区分度")} />
            <DegradedMetric label={t("classDetail.信度")} />
          </div>
          <p className="text-[11px] text-muted-foreground/70 mt-2">
            {t("classDetail.metricsNotSupportedDesc")}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
