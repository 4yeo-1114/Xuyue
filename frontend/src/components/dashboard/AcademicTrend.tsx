import { useQuery } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Inbox } from "lucide-react";
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
import { getAcademicTrend } from "@/services/dashboardApi";

const LINE_COLORS: Record<string, string> = {
  avg_score: "hsl(var(--primary))",
  pass_rate: "#10b981",
  excellent_rate: "#f59e0b",
};

/** 学情趋势：按考试日期月聚合的均分 / 及格率 / 优秀率折线 */
export function AcademicTrend({ grade }: { grade?: string }) {
  const { t } = useLocale();

  const { data, isLoading } = useQuery({
    queryKey: ["admin-dashboard", "academic", "trend", grade ?? ""],
    queryFn: () => getAcademicTrend(grade ? { grade } : {}),
  });

  const points = data?.points ?? [];

  return (
    <Card className="h-full">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">
          {t("dashboard.academic.trend.title")}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-[280px] w-full" />
        ) : points.length === 0 ? (
          <div className="flex h-[280px] flex-col items-center justify-center text-sm text-muted-foreground">
            <Inbox className="mb-2 h-6 w-6" />
            {t("dashboard.academic.noData")}
          </div>
        ) : (
          <div className="h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={points}
                margin={{ top: 5, right: 10, bottom: 5, left: -10 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="hsl(var(--border))"
                />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                <YAxis
                  tick={{ fontSize: 11 }}
                  domain={[0, 100]}
                  allowDecimals={false}
                />
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
                  dataKey="avg_score"
                  name={t("dashboard.academic.avgScore")}
                  stroke={LINE_COLORS.avg_score}
                  strokeWidth={2.5}
                  dot={{ r: 3 }}
                  activeDot={{ r: 5 }}
                  connectNulls
                />
                <Line
                  type="monotone"
                  dataKey="pass_rate"
                  name={t("dashboard.academic.passRate")}
                  stroke={LINE_COLORS.pass_rate}
                  strokeWidth={2.5}
                  dot={{ r: 3 }}
                  activeDot={{ r: 5 }}
                  connectNulls
                />
                <Line
                  type="monotone"
                  dataKey="excellent_rate"
                  name={t("dashboard.academic.excellentRate")}
                  stroke={LINE_COLORS.excellent_rate}
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
  );
}
