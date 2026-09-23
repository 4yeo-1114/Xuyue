import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLocale } from "@/contexts/LocaleContext";
import { cn } from "@/lib/utils";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { Inbox } from "lucide-react";
import type { TrendPoint } from "./compareAnalysisAdapter";

interface HistoryTrendProps {
  data: TrendPoint[];
  className: string;
}

export function HistoryTrend({ data, className }: HistoryTrendProps) {
  const { t } = useLocale();

  const lastTwo = data.length >= 2 ? data.slice(-2) : null;
  const prevAvg = lastTwo?.[0]?.averageScore;
  const latestAvg = lastTwo?.[1]?.averageScore;
  const scoreDelta =
    prevAvg != null && latestAvg != null ? latestAvg - prevAvg : null;
  const chartData = data.map((d) => ({
    exam: d.exam,
    averageScore: d.averageScore,
  }));

  return (
    <Card data-tour="ca-trend">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <CardTitle className="text-sm font-semibold">
            {t("classDetail.compare.trend.title", { className })}
          </CardTitle>
          <div className="flex gap-3 text-[11px] text-muted-foreground">
            <span>
              {t("classDetail.compare.trend.scoreDeltaLabel")}
              {scoreDelta === null ? (
                <strong className="text-muted-foreground">--</strong>
              ) : (
                <strong
                  className={cn(
                    scoreDelta >= 0 ? "text-emerald-600" : "text-destructive",
                  )}
                >
                  {scoreDelta >= 0 ? "↑" : "↓"}
                  {t("classDetail.compare.trend.scoreDeltaValue", {
                    delta: Math.abs(scoreDelta).toFixed(1),
                  })}
                </strong>
              )}
            </span>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {data.length === 0 ? (
          <div className="flex h-[240px] flex-col items-center justify-center text-sm text-muted-foreground">
            <Inbox className="mb-2 h-6 w-6" />
            {t("classDetail.暂无数据")}
            <span className="mt-1 text-[11px]">
              {t("classDetail.compare.trend.noMultipleExams")}
            </span>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="space-y-2">
              <p className="text-xs font-semibold text-foreground">
                {t("classDetail.compare.trend.avgTrend")}
              </p>
              <div className="h-[220px]">
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
                      name={className}
                      stroke="hsl(var(--primary))"
                      strokeWidth={2.5}
                      dot={{ r: 4 }}
                      activeDot={{ r: 6 }}
                      connectNulls
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="space-y-2">
              <p className="text-xs font-semibold text-foreground">
                {t("classDetail.compare.trend.rankTrend")}
              </p>
              <div className="h-[220px] flex flex-col items-center justify-center rounded-lg border border-dashed border-border/60 px-6 text-center">
                <Inbox className="mb-2 h-5 w-5 text-muted-foreground" />
                <p className="text-sm font-medium text-foreground">
                  {t("classDetail.compare.trend.rankUnsupported")}
                </p>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  {t("classDetail.compare.trend.rankNoDataSource")}
                </p>
              </div>
            </div>
          </div>
        )}

        {data.length > 0 && (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border/40 text-muted-foreground">
                  <th className="text-left py-1.5 font-medium">
                    {t("classDetail.compare.trend.exam")}
                  </th>
                  <th className="text-center py-1.5 font-medium">
                    {t("classDetail.compare.trend.avgScore")}
                  </th>
                  <th className="text-center py-1.5 font-medium">
                    {t("classDetail.compare.trend.medianScore")}
                  </th>
                  <th className="text-center py-1.5 font-medium">
                    {t("classDetail.compare.trend.highestScore")}
                  </th>
                  <th className="text-center py-1.5 font-medium">
                    {t("classDetail.compare.trend.lowestScore")}
                  </th>
                  <th className="text-center py-1.5 font-medium">
                    {t("classDetail.compare.trend.wrongRate")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.map((d, i) => (
                  <tr
                    key={d.exam}
                    className={cn(
                      "border-b border-border/20",
                      i === data.length - 1 ? "bg-primary/5 font-semibold" : "",
                    )}
                  >
                    <td className="py-1.5 text-foreground">{d.exam}</td>
                    <td className="text-center text-foreground">
                      {d.averageScore ?? "--"}
                    </td>
                    <td className="text-center text-muted-foreground">
                      {d.medianScore ?? "--"}
                    </td>
                    <td className="text-center text-muted-foreground">
                      {d.highestScore ?? "--"}
                    </td>
                    <td className="text-center text-muted-foreground">
                      {d.lowestScore ?? "--"}
                    </td>
                    <td className="text-center text-muted-foreground">
                      {d.wrongRate ?? "--"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
