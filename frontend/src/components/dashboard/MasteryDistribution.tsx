import { useQuery } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import { useAdminAuth } from "@/hooks/useAdminAuth";
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
import { getMastery, getMasteryDistribution } from "@/services/dashboardApi";

const STACK_COLORS: Record<string, string> = {
  excellent: "#10b981",
  good: "#3b82f6",
  pass: "#f59e0b",
  needs_work: "#ef4444",
};

/** 知识掌握度：成绩等级分布堆叠图 + 知识点掌握度（真实错题分布派生口径，BE-1 聚合 API） */
export function MasteryDistribution({
  grade,
  classId,
}: {
  grade?: string;
  classId?: string;
}) {
  const { t } = useLocale();
  const { schoolId } = useAdminAuth();

  // 成绩等级分布（原有 /admin/academic/mastery，可空）
  const { data, isLoading } = useQuery({
    queryKey: ["admin-dashboard", "academic", "mastery", grade ?? ""],
    queryFn: () => getMastery(grade ? { grade } : {}),
  });

  // 知识点掌握度真实化：错题分布派生口径（school_id 必填；class_id 可选，班级维度）
  const masteryDistQuery = useQuery({
    queryKey: ["mastery-distribution", schoolId, classId ?? ""],
    queryFn: () => getMasteryDistribution(schoolId!, { class_id: classId }),
    enabled: !!schoolId,
  });

  const distribution = data?.grade_distribution ?? [];
  const masteryDist = masteryDistQuery.data ?? [];

  return (
    <Card className="h-full">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">
          {t("dashboard.academic.mastery.title")}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ||
        (masteryDistQuery.isLoading && masteryDist.length === 0) ? (
          <Skeleton className="h-[280px] w-full" />
        ) : distribution.length === 0 && masteryDist.length === 0 ? (
          <div className="flex h-[280px] flex-col items-center justify-center text-sm text-muted-foreground">
            <Inbox className="mb-2 h-6 w-6" />
            {t("dashboard.academic.noData")}
          </div>
        ) : (
          <div className="space-y-3">
            {distribution.length > 0 && (
              <div className="h-[220px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={distribution}
                    margin={{ top: 5, right: 10, bottom: 5, left: -10 }}
                  >
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="hsl(var(--border))"
                      vertical={false}
                    />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
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
                      dataKey="excellent"
                      name={t("dashboard.academic.gradeExcellent")}
                      stackId="a"
                      fill={STACK_COLORS.excellent}
                    />
                    <Bar
                      dataKey="good"
                      name={t("dashboard.academic.gradeGood")}
                      stackId="a"
                      fill={STACK_COLORS.good}
                    />
                    <Bar
                      dataKey="pass"
                      name={t("dashboard.academic.gradePass")}
                      stackId="a"
                      fill={STACK_COLORS.pass}
                    />
                    <Bar
                      dataKey="needs_work"
                      name={t("dashboard.academic.gradeNeedsWork")}
                      stackId="a"
                      fill={STACK_COLORS.needs_work}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {masteryDist.length === 0 ? (
              <p className="text-center text-xs text-muted-foreground">
                {t("dashboard.academic.masteryUnavailable")}
              </p>
            ) : (
              <div className="space-y-1.5 text-xs">
                <p className="text-[11px] text-muted-foreground">
                  {t("dashboard.academic.masteryDerived")}
                </p>
                <div className="grid gap-1.5">
                  {masteryDist.map((m) => (
                    <div
                      key={m.name}
                      className="flex items-center justify-between rounded-md border border-border/50 px-3 py-1.5"
                    >
                      <span className="truncate text-muted-foreground">
                        {m.name}
                      </span>
                      <span className="tabular-nums whitespace-nowrap">
                        {(m.mastery * 100).toFixed(0)}% ·{" "}
                        {t("dashboard.academic.weakPoints")} {m.wrong_count}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
