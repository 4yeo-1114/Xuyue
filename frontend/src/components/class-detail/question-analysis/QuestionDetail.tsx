import { useLocale } from "@/contexts/LocaleContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { BoxPlotChart } from "./BoxPlotChart";
import { QualityRadarChart } from "./QualityRadarChart";
import { STATUS_KEYS } from "./QuestionList";
import type { QuestionAnalysisQuestion } from "./types";

interface QuestionDetailProps {
  question: QuestionAnalysisQuestion;
  onNavigateToStudent?: (name: string) => void;
}

function DegradedSection({ title, note }: { title: string; note: string }) {
  const { t } = useLocale();
  return (
    <div className="rounded-lg border border-dashed border-border/50 p-4 space-y-2">
      <p className="text-xs font-semibold text-foreground">{title}</p>
      <p className="text-xs text-muted-foreground/60">{note}</p>
      <p className="text-[10px] text-muted-foreground/50">
        {t("classDetail.metricNotSupported")}
      </p>
    </div>
  );
}

export function QuestionDetail({
  question: q,
  onNavigateToStudent,
}: QuestionDetailProps) {
  const { t } = useLocale();

  const distData = [
    {
      label: t("classDetail.correctWord"),
      count: q.correctCount,
      color: "#10b981",
    },
    {
      label: t("classDetail.wrongWord"),
      count: q.wrongCount,
      color: "hsl(var(--destructive))",
    },
    {
      label: t("classDetail.blankWord"),
      count: q.blankCount,
      color: "#f59e0b",
    },
  ];

  return (
    <Card data-tour="qa-detail">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2 flex-wrap">
          <CardTitle className="text-sm font-semibold">
            {t("classDetail.deepAnalysisTitle", {
              title: q.title || t("classDetail.unnamedQuestion"),
            })}
          </CardTitle>
          {q.knowledgePoint && (
            <Badge variant="outline" className="text-[11px]">
              {q.knowledgePoint}
            </Badge>
          )}
          <span
            className={cn(
              "text-xs font-semibold",
              q.scoreRate < 60
                ? "text-red-600"
                : q.scoreRate < 70
                  ? "text-amber-600"
                  : "text-foreground",
            )}
          >
            {t("classDetail.classScoreRateLabel", { rate: q.scoreRate })}{" "}
            {STATUS_KEYS[q.status] === "warning"
              ? "🔴"
              : STATUS_KEYS[q.status] === "watch"
                ? "🟠"
                : ""}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* 真实作答统计 */}
        <div className="rounded-lg border border-border/50 p-4 space-y-3">
          <p className="text-xs font-semibold text-foreground">
            {t("classDetail.answerStatsTitle")}
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center text-xs">
            <div className="p-2 rounded border border-emerald-200 bg-emerald-50/60">
              <p className="text-muted-foreground text-[11px]">
                {t("classDetail.correctWord")}
              </p>
              <p className="text-base font-bold text-emerald-700">
                {q.correctCount}
              </p>
            </div>
            <div className="p-2 rounded border border-red-200 bg-red-50/60">
              <p className="text-muted-foreground text-[11px]">
                {t("classDetail.wrongWord")}
              </p>
              <p className="text-base font-bold text-red-700">{q.wrongCount}</p>
            </div>
            <div className="p-2 rounded border border-amber-200 bg-amber-50/60">
              <p className="text-muted-foreground text-[11px]">
                {t("classDetail.blankWord")}
              </p>
              <p className="text-base font-bold text-amber-700">
                {q.blankCount}
              </p>
            </div>
            <div className="p-2 rounded border border-border/50 bg-muted/20">
              <p className="text-muted-foreground text-[11px]">
                {t("classDetail.ungradedWord")}
              </p>
              <p className="text-base font-bold text-foreground">
                {q.ungradedCount}
              </p>
            </div>
          </div>
          <div className="h-[140px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={distData}
                margin={{ top: 5, right: 5, bottom: 0, left: -20 }}
              >
                <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                <Tooltip contentStyle={{ fontSize: 11 }} />
                <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                  {distData.map((d) => (
                    <Cell key={d.label} fill={d.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="text-[11px] text-muted-foreground">
            {t("classDetail.answerSummaryLine", {
              total: q.totalCount,
              rate: q.scoreRate,
            })}
          </p>
        </div>

        {/* 错误原因（真实数据） */}
        <div
          className="rounded-lg border border-border/50 p-4 space-y-3"
          data-tour="qa-reasons"
        >
          <p className="text-xs font-semibold text-foreground">
            {t("classDetail.errorReasonsTitle")}
          </p>
          {q.reasons.length > 0 ? (
            <div className="space-y-2">
              {q.reasons.map((r) => (
                <div
                  key={r.text}
                  className="flex items-center justify-between gap-2 rounded-md bg-muted/30 px-3 py-2"
                >
                  <span className="text-xs text-foreground">{r.text}</span>
                  <span className="text-[11px] text-muted-foreground shrink-0">
                    {t("classDetail.peoplePercentLabel", {
                      count: r.count,
                      percent: q.totalCount
                        ? Math.round((r.count / q.totalCount) * 100)
                        : 0,
                    })}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground/60">
              {t("classDetail.noErrorReasonData")}
            </p>
          )}
        </div>

        {/* 典型错误（真实数据） */}
        <div
          className="rounded-lg border border-border/50 p-4 space-y-3"
          data-tour="qa-error-patterns"
        >
          <p className="text-xs font-semibold text-foreground">
            {t("classDetail.typicalErrorsDescTitle")}
          </p>
          {q.errorPatterns.length > 0 ? (
            <ul className="space-y-1.5">
              {q.errorPatterns.map((p, i) => (
                <li
                  key={i}
                  className="text-xs text-muted-foreground leading-relaxed"
                >
                  • {p}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-muted-foreground/60">
              {t("classDetail.noTypicalErrorDescData")}
            </p>
          )}
        </div>

        {/* 教学建议（真实数据） */}
        <div
          className="rounded-lg border border-primary/20 bg-primary/[0.03] p-4 space-y-3"
          data-tour="qa-strategy"
        >
          <p className="text-xs font-semibold text-foreground">
            {t("classDetail.teachingStrategyTitle")}
          </p>
          {q.teachingStrategy ? (
            <p className="text-xs text-muted-foreground leading-relaxed">
              {q.teachingStrategy}
            </p>
          ) : (
            <p className="text-xs text-muted-foreground/60">
              {t("classDetail.noTeachingStrategyData")}
            </p>
          )}
          {q.followUpExercise && (
            <p className="text-xs text-muted-foreground leading-relaxed">
              <strong className="text-foreground">
                {t("classDetail.followUpExerciseLabel")}
              </strong>
              {q.followUpExercise}
            </p>
          )}
        </div>

        {/* 测量学缺口：统一降级，严禁 mock */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="space-y-3">
            <DegradedSection
              title={t("classDetail.questionQualityAnalysis")}
              note={t("classDetail.questionQualityNote")}
            />
            <QualityRadarChart />
          </div>
          <div className="space-y-3">
            <DegradedSection
              title={t("classDetail.scoreDistributionBox")}
              note={t("classDetail.scoreDistributionNote")}
            />
            <BoxPlotChart />
            <DegradedSection
              title={t("classDetail.optionAnalysis")}
              note={t("classDetail.optionAnalysisNote")}
            />
          </div>
        </div>

        <DegradedSection
          title={t("classDetail.评分维度分析")}
          note={t("classDetail.dimensionAnalysisNote")}
        />
        <DegradedSection
          title={t("classDetail.典型答卷展示")}
          note={t("classDetail.typicalAnswerSheetsNote")}
        />
      </CardContent>
    </Card>
  );
}
