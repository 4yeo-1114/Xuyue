import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { useLocale } from "@/contexts/LocaleContext";
import {
  Users2,
  GraduationCap,
  BookOpen,
  FileText,
  Inbox,
  AlertTriangle,
  RefreshCw,
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
  getAdminDashboardTrend,
  type AdminTrendPeriod,
} from "@/services/api";

/** 各粒度默认时间跨度（天），与学校驾驶舱保持一致 */
const TREND_DAYS: Record<AdminTrendPeriod, number> = {
  daily: 30,
  weekly: 90,
  monthly: 180,
};

const TREND_LINE_COLORS: Record<"grading" | "alert" | "redemption", string> = {
  grading: "hsl(var(--primary))",
  alert: "#f59e0b",
  redemption: "#10b981",
};

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
            <Icon className="w-5 h-5 text-primary" />
          </div>
          <div>
            <p className="text-2xl font-bold text-foreground">{value}</p>
            <p className="text-xs text-muted-foreground">{label}</p>
            {sub && (
              <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function AdminDashboard() {
  const { t } = useLocale();
  const [period, setPeriod] = useState<AdminTrendPeriod>("daily");

  const { data: stats } = useQuery({
    queryKey: ["admin-stats"],
    queryFn: async () => {
      const data = await getDashboardOverview();
      return {
        users: data.users_count ?? 0,
        classes: data.class_count ?? 0,
        students: data.student_count ?? 0,
        exams: data.exams_count ?? 0,
      };
    },
  });

  const trendQuery = useQuery({
    queryKey: ["admin-trend", period],
    queryFn: () => getAdminDashboardTrend(period, TREND_DAYS[period]),
  });

  const periods = trendQuery.data?.periods ?? [];

  return (
    <div>
      <h2 className="text-xl font-bold text-foreground mb-6">
        {t("admin.dashboard.title")}
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={Users2}
          label={t("admin.dashboard.stats.teachers")}
          value={stats?.users ?? "—"}
        />
        <StatCard
          icon={BookOpen}
          label={t("admin.dashboard.stats.classes")}
          value={stats?.classes ?? "—"}
        />
        <StatCard
          icon={GraduationCap}
          label={t("admin.dashboard.stats.students")}
          value={stats?.students ?? "—"}
        />
        <StatCard
          icon={FileText}
          label={t("admin.dashboard.stats.exams")}
          value={stats?.exams ?? "—"}
        />
      </div>
      <Card className="mt-6">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <CardTitle className="text-base">
              {t("admin.dashboard.trends.title")}
            </CardTitle>
            <Tabs
              value={period}
              onValueChange={(v) => setPeriod(v as AdminTrendPeriod)}
            >
              <TabsList>
                <TabsTrigger value="daily">
                  {t("admin.dashboard.trends.period.daily")}
                </TabsTrigger>
                <TabsTrigger value="weekly">
                  {t("admin.dashboard.trends.period.weekly")}
                </TabsTrigger>
                <TabsTrigger value="monthly">
                  {t("admin.dashboard.trends.period.monthly")}
                </TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
        </CardHeader>
        <CardContent>
          {trendQuery.isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-[240px] w-full" />
              <p className="text-center text-xs text-muted-foreground">
                {t("admin.dashboard.trends.loading")}
              </p>
            </div>
          ) : trendQuery.isError ? (
            <div className="flex h-[280px] flex-col items-center justify-center text-sm text-muted-foreground">
              <AlertTriangle className="mb-2 h-6 w-6" />
              {t("admin.dashboard.trends.error")}
              <button
                type="button"
                onClick={() => trendQuery.refetch()}
                className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-border/60 px-3 py-1.5 text-xs text-foreground transition-colors hover:bg-muted"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                {t("admin.dashboard.trends.retry")}
              </button>
            </div>
          ) : periods.length === 0 ? (
            <div className="flex h-[280px] flex-col items-center justify-center text-sm text-muted-foreground">
              <Inbox className="mb-2 h-6 w-6" />
              {t("admin.dashboard.trends.empty")}
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
                    name={t("admin.dashboard.trends.series.grading")}
                    stroke={TREND_LINE_COLORS.grading}
                    strokeWidth={2.5}
                    dot={{ r: 3 }}
                    activeDot={{ r: 5 }}
                    connectNulls
                  />
                  <Line
                    type="monotone"
                    dataKey="alert_count"
                    name={t("admin.dashboard.trends.series.alert")}
                    stroke={TREND_LINE_COLORS.alert}
                    strokeWidth={2.5}
                    dot={{ r: 3 }}
                    activeDot={{ r: 5 }}
                    connectNulls
                  />
                  <Line
                    type="monotone"
                    dataKey="redemption_count"
                    name={t("admin.dashboard.trends.series.redemption")}
                    stroke={TREND_LINE_COLORS.redemption}
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
