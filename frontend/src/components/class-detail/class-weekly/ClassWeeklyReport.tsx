import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import { useAdminAuth } from "@/hooks/useAdminAuth";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import {
  ChevronDown,
  ChevronUp,
  Database,
  FileText,
  Inbox,
  Target,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  getClassMasteryDistribution,
  type ClassMasteryPoint,
  type StudentAnalysisRecord,
} from "@/services/api";

/** 优秀线（与后端等级代码口径一致：score >= 85 → excellent） */
const EXCELLENT_LINE = 85;

/* ── 掌握度三色分级（状态色，语义固定：绿≥0.8 良好 / 黄≥0.6 需加强 / 红<0.6 薄弱） ── */
const MASTERY_GOOD = "#10b981";
const MASTERY_WARN = "#f59e0b";
const MASTERY_WEAK = "#ef4444";

function masteryTone(mastery: number): string {
  if (mastery >= 0.8) return MASTERY_GOOD;
  if (mastery >= 0.6) return MASTERY_WARN;
  return MASTERY_WEAK;
}

const MASTERY_LEGEND: Array<{ key: string; color: string }> = [
  { key: "classDetail.weeklyReport.masteryGood", color: MASTERY_GOOD },
  { key: "classDetail.weeklyReport.masteryWarn", color: MASTERY_WARN },
  { key: "classDetail.weeklyReport.masteryWeak", color: MASTERY_WEAK },
];

interface ClassWeeklyReportProps {
  /** 当前班级 id */
  classId: string;
  /** 当前学科（数据源口径展示用） */
  subject: string;
  /** 班级名（标题展示） */
  className?: string;
  /** 学生成绩画像（父级已拉取，避免重复请求） */
  studentAnalysis: StudentAnalysisRecord[];
  analysisLoading: boolean;
}

/**
 * P4 班级周报区块：班级均分 / 作业完成率 / 优秀数 3 格 + 班级共性薄弱点（按 wrong_count 排序，
 * 接 mastery-distribution）+ 数据来源标注。仅在有数据的班级显示，空态占位不渲染。
 */
export function ClassWeeklyReport({
  classId,
  subject,
  className,
  studentAnalysis,
  analysisLoading,
}: ClassWeeklyReportProps) {
  const { t } = useLocale();
  const { schoolId } = useAdminAuth();

  const { data: mastery = [], isLoading: masteryLoading } = useQuery({
    queryKey: ["class-mastery-distribution", schoolId, classId],
    queryFn: () => getClassMasteryDistribution(schoolId!, classId),
    enabled: !!schoolId && !!classId,
  });

  const stats = useMemo(() => {
    const scored = studentAnalysis.filter(
      (a) => a.current_score != null && a.current_score !== undefined,
    );
    const avg = scored.length
      ? scored.reduce((s, a) => s + (a.current_score ?? 0), 0) / scored.length
      : null;
    const completionRate = studentAnalysis.length
      ? Math.round((scored.length / studentAnalysis.length) * 100)
      : null;
    const excellentCount = scored.filter(
      (a) => (a.current_score ?? 0) >= EXCELLENT_LINE,
    ).length;
    return {
      avg,
      completionRate,
      excellentCount,
      hasData: studentAnalysis.length > 0,
    };
  }, [studentAnalysis]);

  // 班级共性薄弱点：mastery-distribution 后端已按 wrong_count 降序返回，取前 5
  const weakPoints = mastery.slice(0, 5);

  // 只在有数据的班级显示周报区块（成绩画像或错题分布至少其一有数据）
  if (!analysisLoading && !stats.hasData && mastery.length === 0) return null;

  return (
    <Card data-tour="cw-weekly" className="card-elevated">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base font-semibold">
          <FileText className="h-4 w-4 text-primary" />
          {t("classDetail.weeklyReport.title")}
          {className ? ` · ${className}` : ""}
        </CardTitle>
        <CardDescription className="text-xs">
          {t("classDetail.weeklyReport.desc")}（{subject}）
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 3 格核心指标：班级均分 / 作业完成率 / 优秀数 */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-border/50 bg-muted/20 p-3">
            <p className="text-xs text-muted-foreground">
              {t("classDetail.班级均分")}
            </p>
            <p className="mt-1.5 text-lg font-bold tabular-nums text-foreground">
              {analysisLoading
                ? "—"
                : stats.avg != null
                  ? stats.avg.toFixed(1)
                  : "—"}
            </p>
          </div>
          <div className="rounded-xl border border-border/50 bg-muted/20 p-3">
            <p className="text-xs text-muted-foreground">
              {t("classDetail.作业完成率")}
            </p>
            <p className="mt-1.5 text-lg font-bold tabular-nums text-foreground">
              {analysisLoading
                ? "—"
                : stats.completionRate != null
                  ? `${stats.completionRate}%`
                  : "—"}
            </p>
          </div>
          <div className="rounded-xl border border-border/50 bg-muted/20 p-3">
            <p className="text-xs text-muted-foreground">
              {t("classDetail.weeklyReport.excellentCount")}
            </p>
            <p className="mt-1.5 text-lg font-bold tabular-nums text-foreground">
              {analysisLoading
                ? "—"
                : stats.hasData
                  ? `${stats.excellentCount}${t("classDetail.weeklyReport.excellentUnit")}`
                  : "—"}
            </p>
          </div>
        </div>

        {/* 班级共性薄弱点 */}
        <div>
          <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-foreground">
            <Target className="h-3.5 w-3.5 text-orange-500" />
            {t("classDetail.weeklyReport.weakPointsTitle")}
          </p>
          {masteryLoading ? (
            <Skeleton className="h-[96px] w-full" />
          ) : weakPoints.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border/60 px-3 py-3 text-xs text-muted-foreground">
              {t("classDetail.weeklyReport.weakPointsEmpty")}
            </p>
          ) : (
            <ul className="space-y-1.5">
              {weakPoints.map((m, i) => (
                <li
                  key={`${m.name}-${i}`}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border/50 bg-muted/20 px-3 py-2"
                >
                  <span className="flex min-w-0 items-center gap-2 text-xs">
                    <span className="tabular-nums text-muted-foreground">
                      {i + 1}
                    </span>
                    <span className="truncate text-foreground">{m.name}</span>
                  </span>
                  <span className="flex shrink-0 items-center gap-2.5 text-[11px] text-muted-foreground">
                    <span className="tabular-nums">
                      {t("classDetail.weeklyReport.wrongCount")} {m.wrong_count}
                    </span>
                    <span
                      className="rounded-full px-1.5 py-0.5 font-medium tabular-nums"
                      style={{
                        color: masteryTone(m.mastery),
                        backgroundColor: `${masteryTone(m.mastery)}1a`,
                      }}
                    >
                      {(m.mastery * 100).toFixed(0)}%
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* 数据来源标注 */}
        <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-border/40 pt-2.5 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <Database className="h-3 w-3" />
            {t("classDetail.weeklyReport.sourceScores")}
          </span>
          <span className="flex items-center gap-1">
            <Database className="h-3 w-3" />
            {t("classDetail.weeklyReport.sourceWrongQuestions")}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

interface ClassMasteryDistributionProps {
  /** 当前班级 id */
  classId: string;
  /** 学校 id（必填，防越权；无则禁用查询并显示空态） */
  schoolId: string | null;
}

/**
 * P4 班级知识点掌握分布：mastery-distribution（班级维度），条形展示各知识点掌握度，
 * 绿≥0.8/黄≥0.6/红<0.6 三色分级，可展开知识点明细。
 */
export function ClassMasteryDistribution({
  classId,
  schoolId,
}: ClassMasteryDistributionProps) {
  const { t } = useLocale();
  const [expand, setExpand] = useState(false);

  const { data: mastery = [], isLoading } = useQuery({
    queryKey: ["class-mastery-distribution", schoolId, classId],
    queryFn: () => getClassMasteryDistribution(schoolId!, classId),
    enabled: !!schoolId && !!classId,
  });

  // 按掌握度升序展示（薄弱在前），条形图最多 12 个，明细展示全部
  const chartData = useMemo(() => {
    return [...mastery]
      .sort((a, b) => (a.mastery ?? 0) - (b.mastery ?? 0))
      .slice(0, 12);
  }, [mastery]);

  return (
    <Card data-tour="cw-mastery" className="card-elevated">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">
          {t("classDetail.weeklyReport.masteryTitle")}
        </CardTitle>
        <CardDescription className="text-xs">
          {t("classDetail.weeklyReport.masteryDesc")}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-[220px] w-full" />
        ) : mastery.length === 0 ? (
          <div className="flex h-[180px] flex-col items-center justify-center text-sm text-muted-foreground">
            <Inbox className="mb-2 h-6 w-6" />
            {t("classDetail.weeklyReport.masteryUnavailable")}
          </div>
        ) : (
          <>
            <div className="h-[220px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={chartData}
                  margin={{ top: 5, right: 10, bottom: 5, left: -10 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="hsl(var(--border))"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 10 }}
                    interval={0}
                    angle={-18}
                    textAnchor="end"
                    height={46}
                  />
                  <YAxis
                    tick={{ fontSize: 10 }}
                    domain={[0, 1]}
                    tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                  />
                  <Tooltip
                    cursor={{ fill: "hsl(var(--muted))", opacity: 0.35 }}
                    contentStyle={{
                      fontSize: 12,
                      borderRadius: 8,
                      border: "1px solid hsl(var(--border))",
                    }}
                    formatter={(value: number, _name: string, item) => {
                      const payload = (item as { payload?: ClassMasteryPoint })
                        ?.payload;
                      return [
                        `${(value * 100).toFixed(0)}% · ${t(
                          "classDetail.weeklyReport.wrongCount",
                        )} ${payload?.wrong_count ?? ""}`,
                        t("classDetail.weeklyReport.masteryPercent"),
                      ];
                    }}
                  />
                  <Bar
                    dataKey="mastery"
                    name={t("classDetail.weeklyReport.masteryPercent")}
                    radius={[4, 4, 0, 0]}
                    maxBarSize={28}
                  >
                    {chartData.map((d, i) => (
                      <Cell
                        key={`${d.name}-${i}`}
                        fill={masteryTone(d.mastery)}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* 三色图例 */}
            <div className="mt-2 flex items-center justify-center gap-3 text-[11px] text-muted-foreground">
              {MASTERY_LEGEND.map((l) => (
                <span key={l.key} className="flex items-center gap-1">
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ backgroundColor: l.color }}
                  />
                  {t(l.key)}
                </span>
              ))}
            </div>

            {/* 展开知识点明细 */}
            <div className="mt-3">
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-full gap-1 text-xs"
                onClick={() => setExpand((v) => !v)}
                aria-expanded={expand}
                aria-label={t("classDetail.weeklyReport.expandAria")}
              >
                {expand ? (
                  <ChevronUp className="h-3.5 w-3.5" />
                ) : (
                  <ChevronDown className="h-3.5 w-3.5" />
                )}
                {expand
                  ? t("classDetail.weeklyReport.collapse")
                  : t("classDetail.weeklyReport.expand")}
              </Button>
              {expand && (
                <div className="mt-2 max-h-[220px] space-y-1 overflow-y-auto text-xs">
                  {mastery.map((m, i) => (
                    <div
                      key={`${m.name}-${i}`}
                      className="flex items-center justify-between rounded-md border border-border/50 px-3 py-1.5"
                    >
                      <span className="flex min-w-0 items-center gap-2">
                        <span
                          className="h-2 w-2 shrink-0 rounded-full"
                          style={{ backgroundColor: masteryTone(m.mastery) }}
                        />
                        <span className="truncate text-muted-foreground">
                          {m.name}
                        </span>
                      </span>
                      <span className="shrink-0 tabular-nums text-foreground">
                        {(m.mastery * 100).toFixed(0)}% ·{" "}
                        {t("classDetail.weeklyReport.wrongCount")}{" "}
                        {m.wrong_count}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
