import { useQuery } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Inbox, Trophy } from "lucide-react";
import { getClassRanking } from "@/services/dashboardApi";

function fmt(n: number): string {
  return Number.isFinite(n) ? n.toFixed(1) : "0.0";
}

/** 班级排名：当前范围各班按平均分降序（列表式，含排名徽标与关键指标） */
export function ClassRanking({ grade }: { grade?: string }) {
  const { t } = useLocale();

  const { data, isLoading } = useQuery({
    queryKey: ["admin-dashboard", "academic", "ranking", grade ?? ""],
    queryFn: () => getClassRanking(grade ? { grade } : {}),
  });

  const classes = data?.classes ?? [];

  return (
    <Card className="h-full">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">
          {t("dashboard.academic.ranking.title")}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-[280px] w-full" />
        ) : classes.length === 0 ? (
          <div className="flex h-[280px] flex-col items-center justify-center text-sm text-muted-foreground">
            <Inbox className="mb-2 h-6 w-6" />
            {t("dashboard.academic.noData")}
          </div>
        ) : (
          <ol className="space-y-2">
            {classes.map((c) => (
              <li
                key={c.class_id}
                className="flex items-center gap-3 rounded-lg border border-border/50 px-3 py-2"
              >
                <span
                  className={
                    "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold tabular-nums " +
                    (c.rank === 1
                      ? "bg-primary/15 text-primary"
                      : "bg-muted text-muted-foreground")
                  }
                >
                  {c.rank}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <p className="truncate text-sm font-medium">
                      {c.class_name}
                    </p>
                    {c.rank === 1 ? (
                      <Trophy className="h-3.5 w-3.5 shrink-0 text-primary" />
                    ) : null}
                  </div>
                  <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary/80"
                      style={{
                        width: `${Math.min(100, Math.max(0, c.avg_score))}%`,
                      }}
                    />
                  </div>
                </div>
                <div className="shrink-0 text-right text-xs tabular-nums text-muted-foreground">
                  <p className="text-sm font-semibold text-foreground">
                    {fmt(c.avg_score)}
                  </p>
                  <p>
                    {t("dashboard.academic.passRate")} {fmt(c.pass_rate)}% ·{" "}
                    {t("dashboard.academic.excellentRate")} {fmt(c.excellent_rate)}%
                  </p>
                </div>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
