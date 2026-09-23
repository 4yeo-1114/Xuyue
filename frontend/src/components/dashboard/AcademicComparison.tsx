import { useQuery } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Inbox } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";
import {
  getAcademicOverview,
  type AcademicComparisonItem,
} from "@/services/dashboardApi";

const BAR_COLORS: Record<string, string> = {
  avg_score: "hsl(var(--primary))",
  pass_rate: "#10b981",
  excellent_rate: "#f59e0b",
};

function fmt(n: number): string {
  return Number.isFinite(n) ? n.toFixed(1) : "0.0";
}

function fmtInt(n: number): string {
  return Number.isFinite(n) ? String(Math.round(n)) : "0";
}

/** 成绩学情对比：全校=各年级均分/及格率/优秀率对比，选年级=该年级各班对比 */
export function AcademicComparison({ grade }: { grade?: string }) {
  const { t } = useLocale();

  const { data, isLoading } = useQuery({
    queryKey: ["admin-dashboard", "academic", "overview", grade ?? ""],
    queryFn: () => getAcademicOverview(grade ? { grade } : {}),
  });

  const summary = data?.summary;
  const items: AcademicComparisonItem[] = data?.items ?? [];

  return (
    <Card className="h-full">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">
          {t("dashboard.academic.comparison.title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 当前范围汇总 */}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div className="rounded-lg border border-border/50 px-3 py-2">
            <p className="text-xs text-muted-foreground">
              {t("dashboard.academic.avgScore")}
            </p>
            <p className="mt-1 text-lg font-semibold tabular-nums">
              {summary ? fmt(summary.avg_score) : "—"}
            </p>
          </div>
          <div className="rounded-lg border border-border/50 px-3 py-2">
            <p className="text-xs text-muted-foreground">
              {t("dashboard.academic.passRate")}
            </p>
            <p className="mt-1 text-lg font-semibold tabular-nums">
              {summary ? `${fmt(summary.pass_rate)}%` : "—"}
            </p>
          </div>
          <div className="rounded-lg border border-border/50 px-3 py-2">
            <p className="text-xs text-muted-foreground">
              {t("dashboard.academic.excellentRate")}
            </p>
            <p className="mt-1 text-lg font-semibold tabular-nums">
              {summary ? `${fmt(summary.excellent_rate)}%` : "—"}
            </p>
          </div>
          <div className="rounded-lg border border-border/50 px-3 py-2">
            <p className="text-xs text-muted-foreground">
              {t("dashboard.academic.studentCount")}
            </p>
            <p className="mt-1 text-lg font-semibold tabular-nums">
              {summary ? fmtInt(summary.student_count) : "—"}
            </p>
          </div>
        </div>

        {isLoading ? (
          <Skeleton className="h-[240px] w-full" />
        ) : items.length === 0 ? (
          <div className="flex h-[240px] flex-col items-center justify-center text-sm text-muted-foreground">
            <Inbox className="mb-2 h-6 w-6" />
            {t("dashboard.academic.noData")}
          </div>
        ) : (
          <div className="h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={items}
                margin={{ top: 5, right: 10, bottom: 5, left: -10 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="hsl(var(--border))"
                  vertical={false}
                />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                <YAxis
                  tick={{ fontSize: 11 }}
                  domain={[0, 100]}
                  allowDecimals={false}
                />
                <Tooltip
                  cursor={{ fill: "hsl(var(--muted))", opacity: 0.35 }}
                  contentStyle={{
                    fontSize: 12,
                    borderRadius: 8,
                    border: "1px solid hsl(var(--border))",
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar
                  dataKey="avg_score"
                  name={t("dashboard.academic.avgScore")}
                  fill={BAR_COLORS.avg_score}
                  radius={[4, 4, 0, 0]}
                />
                <Bar
                  dataKey="pass_rate"
                  name={t("dashboard.academic.passRate")}
                  fill={BAR_COLORS.pass_rate}
                  radius={[4, 4, 0, 0]}
                />
                <Bar
                  dataKey="excellent_rate"
                  name={t("dashboard.academic.excellentRate")}
                  fill={BAR_COLORS.excellent_rate}
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
