import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import { useClasses } from "@/hooks/useClasses";
import { translateGradeValue } from "@/i18n";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertTriangle,
  FileText,
  Gift,
  Inbox,
  PenTool,
  School,
  Sparkles,
  Users,
  type LucideIcon,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";
import {
  getDashboardOverview,
  getDashboardTrend,
  type DashboardOverview,
  type TrendGranularity,
} from "@/services/dashboardApi";
import { AcademicComparison } from "@/components/dashboard/AcademicComparison";
import { AcademicTrend } from "@/components/dashboard/AcademicTrend";
import { ClassRanking } from "@/components/dashboard/ClassRanking";
import { MasteryDistribution } from "@/components/dashboard/MasteryDistribution";

const GRANULARITY_DAYS: Record<TrendGranularity, number> = {
  daily: 30,
  weekly: 90,
  monthly: 180,
};

const LINE_COLORS: Record<"grading" | "alert" | "redemption", string> = {
  grading: "hsl(var(--primary))",
  alert: "#f59e0b",
  redemption: "#10b981",
};

/** 全校（未选择年级）在 Select 中的占位值；Radix Select 不允许空字符串 item value */
const SCHOOL_WIDE_VALUE = "__school_wide__";

/** 年级顺序（与 i18n/index.ts 的年级序一致），用于驾驶舱年级下拉排序 */
const GRADE_ORDER: string[] = [
  "小学一年级",
  "小学二年级",
  "小学三年级",
  "小学四年级",
  "小学五年级",
  "小学六年级",
  "初一",
  "初二",
  "初三",
  "高一",
  "高二",
  "高三",
];

interface SchoolDashboardPageProps {
  grade?: string;
  classId?: string;
}

interface KpiCardProps {
  icon: LucideIcon;
  label: string;
  value: string;
  suffix?: string;
  tone?: "default" | "warning";
}

function KpiCard({ icon: Icon, label, value, suffix, tone }: KpiCardProps) {
  return (
    <div
      className={
        "p-5 rounded-xl bg-card border border-border/50 card-elevated " +
        (tone === "warning" ? "border-destructive/20" : "")
      }
    >
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icon className="w-4 h-4 shrink-0" />
        <p className="text-sm truncate">{label}</p>
      </div>
      <div className="mt-3 flex items-baseline gap-1">
        <span className="text-2xl font-semibold tabular-nums">{value}</span>
        {suffix ? (
          <span className="text-sm text-muted-foreground">{suffix}</span>
        ) : null}
      </div>
    </div>
  );
}

export function SchoolDashboardPage({
  grade: gradeProp,
}: SchoolDashboardPageProps) {
  const { t, locale } = useLocale();
  const [granularity, setGranularity] = useState<TrendGranularity>("daily");
  // 本地年级状态："" 表示全校概览，不随教学筛选/全局筛选联动
  const [grade, setGrade] = useState<string>(gradeProp ?? "");

  // 拉全校班级，去重出该校实际存在的年级（不传筛选）
  const { data: classes = [] } = useClasses();

  const gradeOptions = useMemo(() => {
    const levelByGrade = new Map<string, string>();
    for (const c of classes) {
      if (c.grade && !levelByGrade.has(c.grade)) {
        levelByGrade.set(c.grade, c.school_level);
      }
    }
    const unique = Array.from(
      new Set(classes.map((c) => c.grade).filter(Boolean) as string[]),
    );
    const order = new Map(GRADE_ORDER.map((g, i) => [g, i]));
    unique.sort((a, b) => {
      const ai = order.get(a) ?? Number.MAX_SAFE_INTEGER;
      const bi = order.get(b) ?? Number.MAX_SAFE_INTEGER;
      if (ai !== bi) return ai - bi;
      return a.localeCompare(b, "zh-CN");
    });
    return unique.map((g) => ({
      value: g,
      label: translateGradeValue(locale, levelByGrade.get(g) ?? "primary", g),
    }));
  }, [classes, locale]);

  const gradeLabel = useMemo(() => {
    if (!grade) return "";
    return gradeOptions.find((o) => o.value === grade)?.label ?? grade;
  }, [grade, gradeOptions]);

  const filters = {
    ...(grade ? { grade } : {}),
  };

  const overviewQuery = useQuery({
    queryKey: ["admin-dashboard", "overview", grade],
    queryFn: () => getDashboardOverview(filters),
  });

  const trendQuery = useQuery({
    queryKey: ["admin-dashboard", "trend", granularity, grade],
    queryFn: () =>
      getDashboardTrend({
        granularity,
        days: GRANULARITY_DAYS[granularity],
        ...filters,
      }),
  });

  const overview: DashboardOverview | undefined = overviewQuery.data;
  const periods = trendQuery.data?.periods ?? [];

  // 五育均分：无 portfolio 数据（available=false 或 avg=null）时显示占位「暂无」，不显示 0.00
  const growthScoreText = useMemo(() => {
    if (overviewQuery.isLoading) return "…";
    if (
      !overview ||
      overview.growth_score_available === false ||
      overview.growth_score_avg === null
    ) {
      return t("dashboard.kpi.growthScoreNoData");
    }
    return overview.growth_score_avg.toFixed(2);
  }, [overviewQuery.isLoading, overview, t]);

  return (
    <div className="space-y-6">
      {/* 页头 */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold text-foreground">
            {t("dashboard.title")}
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {t("dashboard.subtitle")}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Select
            value={grade === "" ? SCHOOL_WIDE_VALUE : grade}
            onValueChange={(v) => setGrade(v === SCHOOL_WIDE_VALUE ? "" : v)}
          >
            <SelectTrigger className="w-[160px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={SCHOOL_WIDE_VALUE}>
                {t("dashboard.schoolWide")}
              </SelectItem>
              {gradeOptions.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            {grade ? (
              <span className="px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                {gradeLabel}
              </span>
            ) : null}
            {t("dashboard.overviewTitle")}
          </span>
        </div>
      </div>

      {/* 概览 KPI 卡 */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4">
        <KpiCard
          icon={School}
          label={t("dashboard.kpi.classCount")}
          value={
            overviewQuery.isLoading ? "…" : String(overview?.class_count ?? 0)
          }
        />
        <KpiCard
          icon={Users}
          label={t("dashboard.kpi.studentCount")}
          value={
            overviewQuery.isLoading ? "…" : String(overview?.student_count ?? 0)
          }
        />
        <KpiCard
          icon={FileText}
          label={t("dashboard.kpi.examsCount")}
          value={
            overviewQuery.isLoading ? "…" : String(overview?.exams_count ?? 0)
          }
        />
        <KpiCard
          icon={PenTool}
          label={t("dashboard.kpi.gradingCount")}
          value={
            overviewQuery.isLoading ? "…" : String(overview?.grading_count ?? 0)
          }
          suffix={t("dashboard.kpi.gradingUnit", {
            days: overview?.grading_days ?? 30,
          })}
        />
        <KpiCard
          icon={AlertTriangle}
          tone="warning"
          label={t("dashboard.kpi.alertCount")}
          value={
            overviewQuery.isLoading ? "…" : String(overview?.alert_count ?? 0)
          }
        />
        <KpiCard
          icon={Gift}
          label={t("dashboard.kpi.redemptionCount")}
          value={
            overviewQuery.isLoading
              ? "…"
              : String(overview?.redemption_count ?? 0)
          }
        />
        <KpiCard
          icon={Sparkles}
          label={t("dashboard.kpi.growthScoreAvg")}
          value={growthScoreText}
        />
      </div>

      {/* 学情板块（成绩学情对比 → 学情趋势 → 班级排名 → 知识掌握度） */}
      <div className="grid gap-4 xl:grid-cols-2">
        <AcademicComparison grade={grade || undefined} />
        <AcademicTrend grade={grade || undefined} />
        <ClassRanking grade={grade || undefined} />
        <MasteryDistribution grade={grade || undefined} />
      </div>

      {/* 运营走势（最底部：批改量 / 预警数 / 兑换量流水） */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div>
              <CardTitle className="text-sm font-semibold">
                {t("dashboard.trend.title")}
              </CardTitle>
              <CardDescription>
                {t("dashboard.trend.lastDays", {
                  days: GRANULARITY_DAYS[granularity],
                })}
              </CardDescription>
            </div>
            <Tabs
              value={granularity}
              onValueChange={(v) => setGranularity(v as TrendGranularity)}
            >
              <TabsList>
                <TabsTrigger value="daily">{t("dashboard.daily")}</TabsTrigger>
                <TabsTrigger value="weekly">
                  {t("dashboard.weekly")}
                </TabsTrigger>
                <TabsTrigger value="monthly">
                  {t("dashboard.monthly")}
                </TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
        </CardHeader>
        <CardContent>
          {trendQuery.isLoading ? (
            <Skeleton className="h-[280px] w-full" />
          ) : periods.length === 0 ? (
            <div className="flex h-[280px] flex-col items-center justify-center text-sm text-muted-foreground">
              <Inbox className="mb-2 h-6 w-6" />
              {t("dashboard.noData")}
            </div>
          ) : (
            <div className="h-[280px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={periods}
                  margin={{ top: 5, right: 10, bottom: 5, left: -10 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="hsl(var(--border))"
                  />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{
                      fontSize: 12,
                      borderRadius: 8,
                      border: "1px solid hsl(var(--border))",
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line
                    type="monotone"
                    dataKey="grading_count"
                    name={t("dashboard.trend.grading")}
                    stroke={LINE_COLORS.grading}
                    strokeWidth={2.5}
                    dot={{ r: 3 }}
                    activeDot={{ r: 5 }}
                    connectNulls
                  />
                  <Line
                    type="monotone"
                    dataKey="alert_count"
                    name={t("dashboard.trend.alert")}
                    stroke={LINE_COLORS.alert}
                    strokeWidth={2.5}
                    dot={{ r: 3 }}
                    activeDot={{ r: 5 }}
                    connectNulls
                  />
                  <Line
                    type="monotone"
                    dataKey="redemption_count"
                    name={t("dashboard.trend.redemption")}
                    stroke={LINE_COLORS.redemption}
                    strokeWidth={2.5}
                    dot={{ r: 3 }}
                    activeDot={{ r: 5 }}
                    connectNulls
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
