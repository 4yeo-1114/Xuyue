import { useQuery } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import { Loader2, School, Users2, Trophy, BarChart3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  getClassOverview,
  type ClassOverview,
  type ClassPortfolioStudent,
} from "@/services/wuyuApi";
import {
  DIMENSIONS,
  DIMENSION_COLORS,
  DIMENSION_LABEL_KEY,
  tierVariant,
  toNum,
} from "./portfolioShared";
import { cn } from "@/lib/utils";

const TIER_ORDER = ["A+", "A", "B", "C", "D"] as const;

interface ClassOverviewPanelProps {
  classId: string;
}

/** 班级五育总览面板：五维均分卡 + 档位分布条 + 学生表（姓名/五维柱/总分/档位/排名/数据状态） */
export function ClassOverviewPanel({ classId }: ClassOverviewPanelProps) {
  const { t } = useLocale();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["wuyu-class-overview", classId],
    queryFn: () => getClassOverview(classId, "total"),
    enabled: !!classId,
  });

  if (!classId) {
    return (
      <div className="flex flex-col items-center justify-center py-24 border border-dashed rounded-xl text-muted-foreground">
        <School className="w-10 h-10 opacity-30 mb-2" />
        <p className="text-sm">{t("wuyu.classOverview.selectClassHint")}</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-muted-foreground">
        <Loader2 className="w-6 h-6 animate-spin mb-2" />
        <p className="text-sm">{t("wuyu.loading")}</p>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex flex-col items-center justify-center py-24 border border-dashed rounded-xl text-muted-foreground">
        <p className="text-sm mb-2">{t("wuyu.loadFailed")}</p>
        <Button size="sm" variant="outline" onClick={() => refetch()}>
          {t("wuyu.retry")}
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4 animate-fade-in">
      {/* 班级五维均分 */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Users2 className="w-4 h-4 text-primary" />
            <CardTitle className="text-sm font-semibold">{t("wuyu.classOverview.title")}</CardTitle>
          </div>
          <CardDescription>
            {data.class_name ? `${data.class_name} · ` : ""}
            {t("wuyu.classOverview.studentCount", { count: data.student_count ?? 0 })}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-7 gap-3">
            {DIMENSIONS.map((dim) => (
              <AvgCard
                key={dim}
                dim={dim}
                label={t(DIMENSION_LABEL_KEY[dim])}
                value={data.averages?.[dim]}
              />
            ))}
            <AvgCard
              dim="total"
              label={t("wuyu.dim.total")}
              value={data.averages?.total}
              emphasized
            />
          </div>
        </CardContent>
      </Card>

      {/* 档位分布 */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Trophy className="w-4 h-4 text-primary" />
            <CardTitle className="text-sm font-semibold">{t("wuyu.classOverview.tierDistribution")}</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <TierDistribution distribution={data.tier_distribution ?? {}} total={data.student_count ?? 0} />
        </CardContent>
      </Card>

      {/* 学生表 */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-primary" />
            <CardTitle className="text-sm font-semibold">{t("wuyu.classOverview.students")}</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          {(data.students ?? []).length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 border border-dashed rounded-lg text-muted-foreground">
              <p className="text-sm">{t("wuyu.classOverview.noStudents")}</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("wuyu.classOverview.name")}</TableHead>
                  <TableHead>{t("wuyu.classOverview.fiveDomains")}</TableHead>
                  <TableHead className="text-right">{t("wuyu.classOverview.totalGrowthPoint")}</TableHead>
                  <TableHead>{t("wuyu.classOverview.tier")}</TableHead>
                  <TableHead>{t("wuyu.classOverview.rank")}</TableHead>
                  <TableHead>{t("wuyu.classOverview.dataStatus")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(data.students ?? []).map((s) => (
                  <StudentRow key={s.student_id} student={s} />
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function AvgCard({
  dim,
  label,
  value,
  emphasized,
}: {
  dim: string;
  label: string;
  value?: number;
  emphasized?: boolean;
}) {
  const color =
    dim === "total"
      ? "hsl(var(--primary))"
      : DIMENSION_COLORS[dim as keyof typeof DIMENSION_COLORS] ?? "#94a3b8";
  return (
    <div className={cn("rounded-lg border border-border/50 px-3 py-2.5", emphasized && "bg-primary/5")}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs text-muted-foreground">{label}</span>
        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
      </div>
      <p className="text-lg font-bold text-foreground">{toNum(value).toFixed(1)}</p>
    </div>
  );
}

function TierDistribution({
  distribution,
  total,
}: {
  distribution: Record<string, number>;
  total: number;
}) {
  const max = Math.max(1, ...TIER_ORDER.map((ti) => distribution?.[ti] ?? 0));
  return (
    <div className="space-y-2">
      {TIER_ORDER.map((ti) => {
        const count = distribution?.[ti] ?? 0;
        const pct = total > 0 ? (count / total) * 100 : 0;
        return (
          <div key={ti} className="flex items-center gap-3 text-sm">
            <span className="w-8 shrink-0 font-medium text-foreground">{ti}</span>
            <div className="flex-1 h-2.5 rounded-full bg-muted overflow-hidden">
              <div
                className="h-full rounded-full bg-primary/70 transition-all"
                style={{ width: `${(count / max) * 100}%` }}
              />
            </div>
            <span className="w-14 shrink-0 text-right text-xs text-muted-foreground tabular-nums">
              {count} · {pct.toFixed(0)}%
            </span>
          </div>
        );
      })}
    </div>
  );
}

function StudentRow({ student }: { student: ClassPortfolioStudent }) {
  const { t } = useLocale();
  const hasDataCount = DIMENSIONS.filter((dim) => student.data_status?.[dim] === "has_data").length;
  const rank = student.rank?.total;
  const n = student.n?.total;
  const tier = student.tier?.total;

  return (
    <TableRow>
      <TableCell className="font-medium text-foreground">{student.name || "—"}</TableCell>
      <TableCell>
        <DomainBars student={student} />
      </TableCell>
      <TableCell className="text-right">
        <span className="font-semibold text-foreground">{toNum(student.total_growth_point).toFixed(1)}</span>
      </TableCell>
      <TableCell>
        <Badge variant={tierVariant(tier)}>{tier ?? "—"}</Badge>
      </TableCell>
      <TableCell>
        {rank != null ? (
          <span className="text-sm text-muted-foreground tabular-nums">
            {rank}
            {n != null ? ` / ${n}` : ""}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
        )}
      </TableCell>
      <TableCell>
        <Badge variant={hasDataCount === DIMENSIONS.length ? "default" : "secondary"}>
          {hasDataCount}/{DIMENSIONS.length}
        </Badge>
      </TableCell>
    </TableRow>
  );
}

/** 五维柱状迷你条（综合分 0-100，灰条=数据不足） */
function DomainBars({ student }: { student: ClassPortfolioStudent }) {
  const { t } = useLocale();
  return (
    <div className="flex items-end gap-1 h-8">
      {DIMENSIONS.map((dim) => {
        const v = student.composite?.[dim];
        const has = student.data_status?.[dim] === "has_data";
        const pct = has && v != null ? Math.max(2, Math.min(100, toNum(v))) : 4;
        return (
          <div
            key={dim}
            className={cn("w-2 rounded-sm", has ? "opacity-80" : "bg-muted")}
            style={{ height: `${pct}%`, backgroundColor: has ? DIMENSION_COLORS[dim] : undefined }}
            title={`${t(DIMENSION_LABEL_KEY[dim])}: ${
              has && v != null ? toNum(v).toFixed(1) : t("wuyu.overview.insufficient")
            }`}
          />
        );
      })}
    </div>
  );
}

export type { ClassOverview };
