import { useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BookOpenCheck,
  BrainCircuit,
  CheckCircle2,
  ClipboardList,
  Image,
  Lightbulb,
  Minus,
  Target,
  TrendingUp,
  Users,
} from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useLocale } from "@/contexts/LocaleContext";
import { AIGeneratedBadge } from "@/components/common/AIGeneratedBadge";
import { cn } from "@/lib/utils";
import type { ClassAnalysisReport } from "@/services/api";

interface RealAnalysisDashboardProps {
  report: ClassAnalysisReport;
  onNavigateToStudent?: (studentName: string) => void;
}

function numberText(value: number | null | undefined, suffix = "") {
  return value === null || value === undefined ? "--" : `${value}${suffix}`;
}

function MetricCard({
  label,
  value,
  detail,
  icon: Icon,
  tone,
}: {
  label: string;
  value: string | number;
  detail: string;
  icon: React.ElementType;
  tone: "blue" | "green" | "amber" | "rose";
}) {
  const styles = {
    blue: "bg-blue-50 text-blue-700 border-blue-100 dark:bg-blue-950/30 dark:text-blue-300 dark:border-blue-900",
    green: "bg-emerald-50 text-emerald-700 border-emerald-100 dark:bg-emerald-950/30 dark:text-emerald-300 dark:border-emerald-900",
    amber: "bg-amber-50 text-amber-700 border-amber-100 dark:bg-amber-950/30 dark:text-amber-300 dark:border-amber-900",
    rose: "bg-rose-50 text-rose-700 border-rose-100 dark:bg-rose-950/30 dark:text-rose-300 dark:border-rose-900",
  };
  return (
    <div className="rounded-lg border bg-card p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          <p className="mt-2 text-2xl font-bold text-foreground">{value}</p>
          <p className="mt-1 text-xs text-muted-foreground">{detail}</p>
        </div>
        <span className={cn("flex h-9 w-9 items-center justify-center rounded-lg border", styles[tone])}>
          <Icon className="h-4 w-4" />
        </span>
      </div>
    </div>
  );
}

function RiskCell({ value, evidenceCount }: { value: number | null; evidenceCount: number }) {
  const { t } = useLocale();
  const style = value === null
    ? "bg-muted text-muted-foreground"
    : value >= 80
      ? "bg-rose-600 text-white"
      : value >= 60
        ? "bg-orange-400 text-orange-950"
        : value >= 30
          ? "bg-amber-200 text-amber-950"
          : "bg-emerald-100 text-emerald-800";
  return (
    <div
      className={cn("flex h-12 min-w-[76px] flex-col items-center justify-center rounded-md text-xs", style)}
      title={value === null ? t("classAnalysis.evidence.insufficient") : t("classAnalysis.evidence.riskTitle", { value, count: evidenceCount })}
    >
      <span className="font-bold">{value === null ? "--" : value}</span>
      <span className="mt-0.5 text-[10px] opacity-75">{value === null ? t("classAnalysis.evidence.insufficient") : t("classAnalysis.evidence.count", { count: evidenceCount })}</span>
    </div>
  );
}

function SeverityBadge({ severity }: { severity: "high" | "medium" | "low" }) {
  const { t } = useLocale();
  const config = severity === "high"
    ? { label: t("classAnalysis.severity.high"), className: "border-rose-200 bg-rose-50 text-rose-700" }
    : severity === "medium"
      ? { label: t("classAnalysis.severity.medium"), className: "border-amber-200 bg-amber-50 text-amber-700" }
      : { label: t("classAnalysis.severity.low"), className: "border-blue-200 bg-blue-50 text-blue-700" };
  return <Badge variant="outline" className={config.className}>{config.label}</Badge>;
}

function ScoreTrend({ report }: { report: ClassAnalysisReport }) {
  const { t } = useLocale();
  const exams = report.source_summary.exam_summaries || [];
  return (
    <section className="rounded-lg border bg-card p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">{t("classAnalysis.trend.title")}</h3>
          <p className="mt-1 text-xs text-muted-foreground">{t("classAnalysis.trend.subtitle")}</p>
        </div>
        <TrendingUp className="h-5 w-5 text-primary" />
      </div>
      <div className="h-[280px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={exams} margin={{ top: 12, right: 16, bottom: 4, left: -10 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
            <XAxis dataKey="exam_name" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 11 }} axisLine={false} tickLine={false} domain={["auto", "auto"]} />
            <Tooltip
              contentStyle={{ borderRadius: 8, border: "1px solid hsl(var(--border))", fontSize: 12 }}
              formatter={(value: number) => [value, t("classAnalysis.averageScore")]}
            />
            <Line
              type="monotone"
              dataKey="average_score"
              name={t("classAnalysis.averageScore")}
              stroke="hsl(var(--primary))"
              strokeWidth={3}
              dot={{ r: 4, fill: "hsl(var(--primary))", strokeWidth: 2, stroke: "hsl(var(--card))" }}
              activeDot={{ r: 6 }}
              connectNulls={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

function KnowledgeHeatmap({ report }: { report: ClassAnalysisReport }) {
  const { t } = useLocale();
  const rows = report.analysis.knowledge_heatmap || [];
  const exams = report.exam_names || [];
  return (
    <section className="overflow-hidden rounded-lg border bg-card shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold"><BrainCircuit className="h-4 w-4 text-primary" />{t("classAnalysis.heatmap.title")}</h3>
          <p className="mt-1 text-xs text-muted-foreground">{t("classAnalysis.heatmap.subtitle")}</p>
        </div>
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
          <span className="h-3 w-3 rounded-sm bg-emerald-100" />{t("classAnalysis.heatmap.low")}
          <span className="h-3 w-3 rounded-sm bg-amber-200" />{t("classAnalysis.heatmap.medium")}
          <span className="h-3 w-3 rounded-sm bg-orange-400" />{t("classAnalysis.heatmap.high")}
          <span className="h-3 w-3 rounded-sm bg-rose-600" />{t("classAnalysis.heatmap.severe")}
        </div>
      </div>
      {rows.length === 0 ? (
        <div className="flex h-[240px] items-center justify-center text-sm text-muted-foreground">{t("classAnalysis.heatmap.empty")}</div>
      ) : (
        <div className="overflow-x-auto p-4">
          <table className="w-full min-w-[680px] border-separate border-spacing-2">
            <thead>
              <tr>
                <th className="w-[180px] px-2 text-left text-xs font-medium text-muted-foreground">{t("classAnalysis.knowledgePoint")}</th>
                {exams.map((exam) => <th key={exam} className="px-2 text-center text-xs font-medium text-muted-foreground">{exam}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.knowledge_point}>
                  <td className="px-2 py-1 align-middle">
                    <p className="text-sm font-medium">{row.knowledge_point}</p>
                    {row.summary ? <p className="mt-1 line-clamp-2 text-[11px] leading-4 text-muted-foreground">{row.summary}</p> : null}
                  </td>
                  {exams.map((exam) => {
                    const cell = row.values?.find((item) => item.exam_name === exam);
                    return <td key={exam} className="p-1"><RiskCell value={cell?.risk_score ?? null} evidenceCount={cell?.evidence_count || 0} /></td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function WeakPoints({ report }: { report: ClassAnalysisReport }) {
  const { t } = useLocale();
  const weakPoints = report.analysis.weak_points || [];
  return (
    <section className="rounded-lg border bg-card shadow-sm">
      <div className="border-b px-5 py-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold"><Target className="h-4 w-4 text-rose-600" />{t("classAnalysis.weakPoints.title")}</h3>
        <p className="mt-1 text-xs text-muted-foreground">{t("classAnalysis.weakPoints.subtitle")}</p>
      </div>
      {weakPoints.length === 0 ? (
        <div className="flex h-[240px] items-center justify-center text-sm text-muted-foreground">{t("classAnalysis.weakPoints.empty")}</div>
      ) : (
        <div className="divide-y">
          {weakPoints.map((item, index) => (
            <article key={`${item.knowledge_point}-${index}`} className="p-4">
              <div className="flex items-start gap-3">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-muted text-xs font-bold">{index + 1}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="text-sm font-semibold">{item.knowledge_point}</h4>
                    <SeverityBadge severity={item.severity} />
                    <span className="text-xs text-muted-foreground">{t("classAnalysis.weakPoints.affected", { count: item.affected_student_count || 0 })}</span>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-muted-foreground">{item.evidence || t("classAnalysis.weakPoints.noEvidence")}</p>
                  {item.teaching_suggestion ? (
                    <div className="mt-3 flex gap-2 rounded-md bg-blue-50 px-3 py-2 text-xs leading-5 text-blue-900 dark:bg-blue-950/30 dark:text-blue-200">
                      <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0" />{item.teaching_suggestion}
                    </div>
                  ) : null}
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function StudentWarnings({ report, onNavigateToStudent }: RealAnalysisDashboardProps) {
  const { t } = useLocale();
  const warnings = report.analysis.student_warnings || [];
  return (
    <section className="overflow-hidden rounded-lg border bg-card shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b px-5 py-4">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold"><AlertTriangle className="h-4 w-4 text-amber-600" />{t("classAnalysis.warnings.title")}</h3>
          <p className="mt-1 text-xs text-muted-foreground">{t("classAnalysis.warnings.subtitle")}</p>
        </div>
        <Badge variant="secondary">{t("classAnalysis.warnings.count", { count: warnings.length })}</Badge>
      </div>
      {warnings.length === 0 ? (
        <div className="flex h-[180px] flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
          <CheckCircle2 className="h-7 w-7 text-emerald-500" />{t("classAnalysis.warnings.empty")}
        </div>
      ) : (
        <>
        <div className="hidden overflow-x-auto md:block">
          <table className="w-full min-w-[820px] text-sm">
            <thead className="bg-muted/50 text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">{t("classAnalysis.warnings.student")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("classAnalysis.warnings.exam")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("classAnalysis.warnings.evidence")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("classAnalysis.warnings.suggestion")}</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {warnings.map((warning) => (
                <tr key={warning.student_name} className="align-top hover:bg-muted/20">
                  <td className="px-4 py-3">
                    <Button
                      variant="link"
                      className="h-auto p-0 font-semibold text-foreground"
                      onClick={() => onNavigateToStudent?.(warning.student_name)}
                    >
                      {warning.student_name}
                    </Button>
                    <div className="mt-1"><Badge variant={warning.risk_level === "high" ? "destructive" : "secondary"}>{warning.risk_level === "high" ? t("classAnalysis.warnings.continuous") : t("classAnalysis.warnings.single")}</Badge></div>
                  </td>
                  <td className="px-4 py-3 text-xs leading-5 text-muted-foreground">
                    {(warning.warning_exams || []).map((exam) => (
                      <div key={exam.exam_name}>{t("classAnalysis.warnings.examDetail", { exam: exam.exam_name, wrong: exam.wrong_count, average: exam.class_average_wrong_count })}</div>
                    ))}
                  </td>
                  <td className="max-w-[320px] px-4 py-3 text-xs leading-5">{warning.reason}</td>
                  <td className="max-w-[300px] px-4 py-3 text-xs leading-5 text-muted-foreground">{warning.suggestion}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="divide-y md:hidden">
          {warnings.map((warning) => (
            <article key={warning.student_name} className="space-y-3 p-4">
              <div className="flex items-center justify-between gap-3">
                <Button
                  variant="link"
                  className="h-auto p-0 font-semibold text-foreground"
                  onClick={() => onNavigateToStudent?.(warning.student_name)}
                >
                  {warning.student_name}
                </Button>
                <Badge variant={warning.risk_level === "high" ? "destructive" : "secondary"}>
                  {warning.risk_level === "high" ? t("classAnalysis.warnings.continuous") : t("classAnalysis.warnings.single")}
                </Badge>
              </div>
              <div className="space-y-1 rounded-md bg-muted/40 px-3 py-2 text-xs leading-5 text-muted-foreground">
                {(warning.warning_exams || []).map((exam) => (
                  <p key={exam.exam_name}>{t("classAnalysis.warnings.examDetail", { exam: exam.exam_name, wrong: exam.wrong_count, average: exam.class_average_wrong_count })}</p>
                ))}
              </div>
              <div>
                <p className="text-xs font-medium">{t("classAnalysis.warnings.basis")}</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{warning.reason}</p>
              </div>
              <div>
                <p className="text-xs font-medium">{t("classAnalysis.warnings.followUp")}</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{warning.suggestion}</p>
              </div>
            </article>
          ))}
        </div>
        </>
      )}
    </section>
  );
}

function RankingTable({ report, onNavigateToStudent }: RealAnalysisDashboardProps) {
  const { t } = useLocale();
  const exams = report.source_summary.exam_summaries || [];
  const [selectedExam, setSelectedExam] = useState(exams[exams.length - 1]?.exam_name || "");
  const activeExam = exams.find((exam) => exam.exam_name === selectedExam) || exams[exams.length - 1];
  return (
    <section className="overflow-hidden rounded-lg border bg-card shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold"><ClipboardList className="h-4 w-4 text-primary" />{t("classAnalysis.ranking.title")}</h3>
          <p className="mt-1 text-xs text-muted-foreground">{t("classAnalysis.ranking.subtitle")}</p>
        </div>
        <Select value={activeExam?.exam_name || ""} onValueChange={setSelectedExam}>
          <SelectTrigger className="h-8 w-[180px] text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>{exams.map((exam) => <SelectItem key={exam.exam_name} value={exam.exam_name}>{exam.exam_name}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      {!activeExam?.rankings?.length ? (
        <div className="flex h-[180px] items-center justify-center text-sm text-muted-foreground">{t("classAnalysis.ranking.empty")}</div>
      ) : (
        <>
        <div className="hidden max-h-[360px] overflow-auto sm:block">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-muted/95 text-xs text-muted-foreground backdrop-blur-sm">
              <tr>
                <th className="px-4 py-3 text-left font-medium">{t("classAnalysis.ranking.rank")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("classAnalysis.ranking.name")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("classAnalysis.ranking.studentNumber")}</th>
                <th className="px-4 py-3 text-right font-medium">{t("classAnalysis.ranking.score")}</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {activeExam.rankings.map((row) => (
                <tr key={row.student_id} className="hover:bg-muted/20">
                  <td className="px-4 py-2.5 font-semibold">{row.rank}</td>
                  <td className="px-4 py-2.5"><Button variant="link" className="h-auto p-0 text-foreground" onClick={() => onNavigateToStudent?.(row.student_name)}>{row.student_name}</Button></td>
                  <td className="px-4 py-2.5 text-muted-foreground">{row.student_number || "--"}</td>
                  <td className="px-4 py-2.5 text-right font-semibold">{numberText(row.score)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="max-h-[360px] divide-y overflow-auto sm:hidden">
          {activeExam.rankings.map((row) => (
            <div key={row.student_id} className="grid grid-cols-[36px_1fr_auto] items-center gap-3 px-4 py-3">
              <span className={cn(
                "flex h-7 w-7 items-center justify-center rounded-md text-xs font-bold",
                row.rank <= 3 ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground",
              )}>{row.rank}</span>
              <div className="min-w-0">
                <Button variant="link" className="h-auto max-w-full truncate p-0 text-foreground" onClick={() => onNavigateToStudent?.(row.student_name)}>{row.student_name}</Button>
                <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{row.student_number || t("classAnalysis.ranking.noStudentNumber")}</p>
              </div>
              <span className="text-base font-bold">{numberText(row.score)}</span>
            </div>
          ))}
        </div>
        </>
      )}
    </section>
  );
}

export function RealAnalysisDashboard({ report, onNavigateToStudent }: RealAnalysisDashboardProps) {
  const { locale, t } = useLocale();
  const metrics = report.source_summary.overall_metrics || {};
  const overall = report.analysis.overall_level || {};
  const examSummaries = report.source_summary.exam_summaries || [];
  const warnings = report.analysis.student_warnings || [];
  const scoreChange = metrics.average_score_change;
  const scoreChangeDetail = scoreChange === null || scoreChange === undefined
    ? t("classAnalysis.change.needTwoExams")
    : scoreChange > 0
      ? t("classAnalysis.change.up", { score: scoreChange })
      : scoreChange < 0
        ? t("classAnalysis.change.down", { score: Math.abs(scoreChange) })
        : t("classAnalysis.change.same");
  const TrendIcon = scoreChange === null || scoreChange === undefined || scoreChange === 0
    ? Minus
    : scoreChange > 0 ? ArrowUpRight : ArrowDownRight;

  const generatedTime = useMemo(() => {
    if (!report.generated_at) return "--";
    try {
      return new Date(report.generated_at).toLocaleString(locale === "en" ? "en-US" : "zh-CN");
    } catch {
      return report.generated_at;
    }
  }, [locale, report.generated_at]);

  return (
    <div className="space-y-5">
      <section className="rounded-lg border border-blue-200 bg-card px-5 py-4 shadow-sm dark:border-blue-900">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold">{t("classAnalysis.source.exams")}</span>
              {report.exam_names.map((exam, index) => (
                <Badge key={exam} variant="secondary" className="gap-1 border bg-background">
                  <span className="text-primary">{index + 1}</span>{exam}
                </Badge>
              ))}
            </div>
            <p className="mt-2 text-xs text-muted-foreground">{t("classAnalysis.source.generated", { time: generatedTime, model: report.source_summary.model || t("classAnalysis.source.qwen") })}</p>
          </div>
          <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5"><Image className="h-3.5 w-3.5" />{t("classAnalysis.source.images", { count: metrics.image_count || 0 })}</span>
            <span className="flex items-center gap-1.5"><BookOpenCheck className="h-3.5 w-3.5" />{t("classAnalysis.source.coverage", { value: numberText(metrics.image_paper_coverage_rate, "%") })}</span>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <MetricCard label={t("classAnalysis.metric.latestAverage")} value={numberText(metrics.latest_average_score)} detail={examSummaries[examSummaries.length - 1]?.exam_name || t("classAnalysis.metric.noExam")} icon={TrendingUp} tone="blue" />
        <MetricCard label={t("classAnalysis.metric.averageChange")} value={scoreChange === null || scoreChange === undefined ? "--" : `${scoreChange > 0 ? "+" : ""}${scoreChange}`} detail={scoreChangeDetail} icon={TrendIcon} tone={scoreChange !== null && scoreChange !== undefined && scoreChange < 0 ? "rose" : "green"} />
        <MetricCard label={t("classAnalysis.metric.paperCount")} value={metrics.record_paper_count || 0} detail={t("classAnalysis.metric.examCount", { count: metrics.exam_count || 0 })} icon={Users} tone="amber" />
        <MetricCard label={t("classAnalysis.metric.warningStudents")} value={warnings.length} detail={t("classAnalysis.metric.warningDetail")} icon={AlertTriangle} tone="rose" />
      </div>

      <section className="rounded-lg border bg-card shadow-sm">
        <div className="grid gap-5 p-5 lg:grid-cols-[180px_1fr]">
          <div className="flex flex-col justify-between rounded-lg bg-blue-50 p-4 dark:bg-blue-950/30">
            <div>
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-medium text-blue-700 dark:text-blue-300">{t("classAnalysis.overall.title")}</p>
                <AIGeneratedBadge />
              </div>
              <p className="mt-2 text-2xl font-bold text-blue-950 dark:text-blue-100">{overall.level || t("classAnalysis.overall.insufficient")}</p>
            </div>
            <BrainCircuit className="mt-6 h-7 w-7 text-blue-600" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold leading-6 text-foreground">{overall.summary || t("classAnalysis.overall.empty")}</p>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <div className="rounded-md border bg-muted/20 px-3 py-2.5">
                <p className="text-xs font-medium">{t("classAnalysis.overall.trend")}</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{overall.trend || t("classAnalysis.overall.noTrend")}</p>
              </div>
              <div className="rounded-md border bg-muted/20 px-3 py-2.5">
                <p className="text-xs font-medium">{t("classAnalysis.overall.scoreInterpretation")}</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{overall.score_interpretation || t("classAnalysis.overall.noScoreInterpretation")}</p>
              </div>
            </div>
            {(overall.strengths || []).length ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {(overall.strengths || []).map((item) => <Badge key={item} variant="outline" className="border-emerald-200 bg-emerald-50 text-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-200">{item}</Badge>)}
              </div>
            ) : null}
          </div>
        </div>
      </section>

      <div className="grid gap-5 xl:grid-cols-[1.05fr_0.95fr]">
        <ScoreTrend report={report} />
        <WeakPoints report={report} />
      </div>

      <KnowledgeHeatmap report={report} />
      <StudentWarnings report={report} onNavigateToStudent={onNavigateToStudent} />

      {(report.analysis.teaching_actions || []).length ? (
        <section className="rounded-lg border bg-card p-5 shadow-sm">
          <h3 className="flex items-center gap-2 text-sm font-semibold"><Lightbulb className="h-4 w-4 text-amber-500" />{t("classAnalysis.teachingActions")}</h3>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {(report.analysis.teaching_actions || []).map((action, index) => (
              <div key={`${action}-${index}`} className="flex gap-3 rounded-md border bg-muted/20 p-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-primary/10 text-xs font-bold text-primary">{index + 1}</span>
                <p className="text-xs leading-5">{action}</p>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <RankingTable report={report} onNavigateToStudent={onNavigateToStudent} />

      {(overall.data_notes || []).length ? (
        <section className="rounded-lg border border-amber-200 bg-amber-50/60 px-4 py-3 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/20 dark:text-amber-200">
          <p className="font-semibold">{t("classAnalysis.dataNotes")}</p>
          <ul className="mt-2 space-y-1">{(overall.data_notes || []).map((note) => <li key={note}>· {note}</li>)}</ul>
        </section>
      ) : null}
    </div>
  );
}
