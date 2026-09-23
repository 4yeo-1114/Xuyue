import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Radar as RadarIcon, TrendingUp } from "lucide-react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getClassAnalysisReport, getGradeSummary } from "@/services/api";

/* ── 稳定度三色（状态色，语义固定） ── */
const STABILITY_STABLE = "#10b981";
const STABILITY_FLUCT = "#f59e0b";
const STABILITY_UNSTABLE = "#ef4444";

interface ClassScoreTrendProps {
  /** 年级名（如「小学三年级」，grade-summary 必填） */
  grade?: string;
  /** 当前班级 id */
  classId: string;
  /** 班级名（趋势序列按名对齐时的兜底） */
  className?: string;
  /** 当前学科 */
  subject: string;
}

/**
 * P4 成绩趋势增强：历次大考班级均分折线（grade-summary trendSeries）基础上，
 * 叠加排名/波动模块——年级百分位 + 稳定度三色（数据用现有 trend 接口）。
 */
export function ClassScoreTrend({
  grade,
  classId,
  className,
  subject,
}: ClassScoreTrendProps) {
  const { t } = useLocale();

  const { data, isLoading } = useQuery({
    queryKey: ["class-score-trend", grade, subject],
    queryFn: () => getGradeSummary(grade!, subject),
    enabled: !!grade && !!subject && !!classId,
  });

  const classRow = data?.classRows.find((r) => r.classId === classId);
  const series = data?.trendSeries.perClass.find(
    (p) => p.className === (classRow?.className ?? className),
  );

  const chartData = useMemo(() => {
    if (!data || !series) return [];
    return (data.trendSeries.examNames ?? []).map((exam, i) => ({
      exam,
      averageScore: series.scores[i] ?? null,
    }));
  }, [data, series]);

  /** 年级内排名与百分位（classRows 已按期末均分降序，这里再防御性排序） */
  const rankInfo = useMemo(() => {
    if (!data || !classRow) return null;
    const sorted = [...data.classRows].sort(
      (a, b) => b.averageScore - a.averageScore,
    );
    const rank = sorted.findIndex((r) => r.classId === classId) + 1;
    const count = sorted.length;
    const percentile =
      count > 1
        ? Math.round(((count - rank) / (count - 1)) * 100)
        : count === 1
          ? 100
          : null;
    return { rank, count, percentile };
  }, [data, classRow, classId]);

  /** 稳定度：历次均分的变异系数 CV，三色分级 */
  const stability = useMemo(() => {
    const scores = chartData
      .map((d) => d.averageScore)
      .filter((s): s is number => s != null);
    if (scores.length < 2) return null;
    const mean = scores.reduce((s, x) => s + x, 0) / scores.length;
    if (!mean) return null;
    const variance =
      scores.reduce((s, x) => s + (x - mean) ** 2, 0) / scores.length;
    const cv = Math.sqrt(variance) / mean;
    if (cv < 0.05)
      return {
        key: "classDetail.weeklyReport.stabilityStable",
        color: STABILITY_STABLE,
      };
    if (cv < 0.1)
      return {
        key: "classDetail.weeklyReport.stabilityFluct",
        color: STABILITY_FLUCT,
      };
    return {
      key: "classDetail.weeklyReport.stabilityUnstable",
      color: STABILITY_UNSTABLE,
    };
  }, [chartData]);

  const hasData = chartData.length > 0 || rankInfo != null;

  return (
    <Card data-tour="cw-trend" className="card-elevated">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          <TrendingUp className="h-4 w-4 text-primary" />
          {t("classDetail.weeklyReport.trendTitle")}
        </CardTitle>
        <CardDescription className="text-xs">
          {t("classDetail.weeklyReport.trendDesc")}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-[240px] w-full" />
        ) : !hasData ? (
          <div className="flex h-[200px] flex-col items-center justify-center text-sm text-muted-foreground">
            <TrendingUp className="mb-2 h-6 w-6" />
            {t("classDetail.weeklyReport.trendEmpty")}
          </div>
        ) : (
          <>
            {/* 排名 / 百分位 / 稳定度 */}
            <div className="grid grid-cols-3 gap-2">
              <div className="rounded-lg border border-border/50 bg-muted/20 p-2.5">
                <p className="text-[10px] text-muted-foreground">
                  {t("classDetail.weeklyReport.rankLabel")}
                </p>
                <p className="mt-0.5 text-sm font-bold tabular-nums text-foreground">
                  {rankInfo ? `${rankInfo.rank}/${rankInfo.count}` : "—"}
                </p>
              </div>
              <div className="rounded-lg border border-border/50 bg-muted/20 p-2.5">
                <p className="text-[10px] text-muted-foreground">
                  {t("classDetail.weeklyReport.percentile")}
                </p>
                <p className="mt-0.5 text-sm font-bold tabular-nums text-foreground">
                  {rankInfo?.percentile != null
                    ? `${rankInfo.percentile}%`
                    : "—"}
                </p>
              </div>
              <div className="rounded-lg border border-border/50 bg-muted/20 p-2.5">
                <p className="text-[10px] text-muted-foreground">
                  {t("classDetail.weeklyReport.stability")}
                </p>
                <p className="mt-0.5 flex items-center gap-1 text-sm font-bold">
                  {stability ? (
                    <>
                      <span
                        className="h-2 w-2 rounded-full"
                        style={{ backgroundColor: stability.color }}
                      />
                      <span style={{ color: stability.color }}>
                        {t(stability.key)}
                      </span>
                    </>
                  ) : (
                    <span className="text-muted-foreground">
                      {t("classDetail.weeklyReport.stabilityNoData")}
                    </span>
                  )}
                </p>
              </div>
            </div>

            {/* 历次大考均分折线 */}
            {chartData.length > 0 && (
              <div className="mt-3 h-[180px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={chartData}
                    margin={{ top: 5, right: 10, bottom: 5, left: -10 }}
                  >
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="hsl(var(--border))"
                    />
                    <XAxis dataKey="exam" tick={{ fontSize: 10 }} />
                    <YAxis
                      tick={{ fontSize: 10 }}
                      domain={["dataMin - 3", "dataMax + 3"]}
                    />
                    <Tooltip
                      contentStyle={{
                        fontSize: 11,
                        borderRadius: 8,
                        border: "1px solid hsl(var(--border))",
                      }}
                    />
                    <Line
                      type="monotone"
                      dataKey="averageScore"
                      name={t("classDetail.weeklyReport.trendAvg")}
                      stroke="hsl(var(--primary))"
                      strokeWidth={2.5}
                      dot={{ r: 3.5 }}
                      activeDot={{ r: 5 }}
                      connectNulls
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

interface ClassAbilityRadarProps {
  /** 当前班级 id */
  classId: string;
  /** 当前学科 */
  subject: string;
  /** 班级名（标题展示） */
  className?: string;
}

/**
 * P4 五维雷达班级均分叠加：本班 score（实线）vs 班级均分 classAvg（虚线），
 * 数据用现有 radar 字段（class-analysis/report 的 capability_dimensions）。
 */
export function ClassAbilityRadar({
  classId,
  subject,
  className,
}: ClassAbilityRadarProps) {
  const { t } = useLocale();

  const { data, isLoading } = useQuery({
    queryKey: ["class-analysis-report", classId, subject],
    queryFn: () => getClassAnalysisReport(classId, subject),
    enabled: !!classId && !!subject,
  });

  const dims = data?.report?.analysis?.capability_dimensions?.dims?.filter(
    (d) => d && d.name && typeof d.score === "number",
  );

  const chartData = dims?.map((d) => ({
    name: d.name,
    score: d.score,
    classAvg: typeof d.classAvg === "number" ? d.classAvg : 0,
  }));

  const hasData = !!chartData && chartData.length > 0;

  return (
    <Card data-tour="cw-radar" className="card-elevated h-full">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">
          {t("classDetail.weeklyReport.radarTitle")}
          {className ? ` · ${className}` : ""}
        </CardTitle>
        <CardDescription className="text-xs">
          {t("classDetail.weeklyReport.radarDesc")}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-[240px] w-full" />
        ) : !hasData ? (
          <div className="flex h-[220px] flex-col items-center justify-center text-sm text-muted-foreground">
            <RadarIcon className="mb-2 h-6 w-6" />
            {t("classDetail.weeklyReport.radarEmpty")}
          </div>
        ) : (
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={chartData} cx="50%" cy="50%" outerRadius="70%">
                <PolarGrid stroke="hsl(var(--border))" />
                <PolarAngleAxis
                  dataKey="name"
                  tick={{
                    fontSize: 11,
                    fill: "hsl(var(--muted-foreground))",
                  }}
                />
                <Tooltip
                  contentStyle={{
                    fontSize: 11,
                    borderRadius: 8,
                    border: "1px solid hsl(var(--border))",
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" />
                <Radar
                  name={t("classDetail.weeklyReport.legendClassAvg")}
                  dataKey="classAvg"
                  stroke="hsl(var(--muted-foreground))"
                  fill="hsl(var(--muted-foreground))"
                  fillOpacity={0.1}
                  strokeDasharray="4 4"
                />
                <Radar
                  name={t("classDetail.weeklyReport.legendThisClass")}
                  dataKey="score"
                  stroke="hsl(var(--primary))"
                  fill="hsl(var(--primary))"
                  fillOpacity={0.2}
                  strokeWidth={2}
                />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
