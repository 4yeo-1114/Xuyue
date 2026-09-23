import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  Loader2,
  RefreshCw,
  ArrowLeft,
  TrendingUp,
  FileText,
  History,
  Users,
  User,
  ChevronRight,
} from "lucide-react";
import {
  listParentStudents,
  getParentStudentOverview,
  type ParentStudent,
  type ParentOverview,
} from "@/services/wuyuApi";
import {
  DIMENSIONS,
  DIMENSION_COLORS,
  DIMENSION_LABEL_KEY,
  toNum,
  formatDateTime,
} from "@/components/wuyu-profile/portfolioShared";

/** PolarAngleAxis tick 渲染回调实际接收的字段（与 wuyu-profile 口径一致） */
interface AngleAxisTickProps {
  x: number;
  y: number;
  payload: { value: string | number };
}

type TooltipValue = number | string | Array<number | string>;
interface TooltipEntry {
  name?: number | string;
  value?: TooltipValue;
  payload?: unknown;
}

/** 孩子五育画像详情（对应家长点击单个孩子后的视图） */
function ParentStudentDetail({
  student,
  onBack,
}: {
  student: ParentStudent;
  onBack: () => void;
}) {
  const { t } = useLocale();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["parent-overview", student.student_id],
    queryFn: () => getParentStudentOverview(student.student_id, 10),
    enabled: !!student.student_id,
  });

  const radarData = useMemo(
    () =>
      DIMENSIONS.map((dim) => ({
        dim: t(DIMENSION_LABEL_KEY[dim]),
        value: toNum(data?.dimensions?.[dim]),
        hasData: data?.dimensions?.[dim] != null,
      })),
    [data, t],
  );

  const records = data?.recent_growth_records ?? [];

  const report = useMemo(() => {
    const r = data?.report;
    if (!r || typeof r !== "object") return null;
    return {
      term: r.term ?? null,
      total: r.total_growth_point ?? null,
    };
  }, [data]);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
        <Loader2 className="w-6 h-6 animate-spin mb-2" />
        <p className="text-sm">{t("parent.loading")}</p>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
        <p className="text-sm mb-3">{t("parent.loadFailed")}</p>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          <RefreshCw className="w-4 h-4 mr-1" />
          {t("parent.retry")}
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-3 animate-fade-in">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={onBack}
          className="shrink-0"
        >
          <ArrowLeft className="w-4 h-4 mr-1" />
          {t("parent.back")}
        </Button>
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold text-foreground leading-tight truncate">
            {data.name}
          </h2>
          <p className="text-xs text-muted-foreground truncate">
            {t("parent.class")} {data.class_name || data.class_id}
          </p>
        </div>
        <Badge variant="secondary" className="shrink-0">
          <TrendingUp className="w-3 h-3 mr-1" />
          {t("parent.overview.totalGrowth")}:{" "}
          {toNum(data.total_growth_point).toFixed(1)}
        </Badge>
      </div>

      {/* 五育雷达 */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-primary" />
            <CardTitle className="text-sm font-semibold">
              {t("parent.overview.radar")}
            </CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <div className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="70%">
                <PolarGrid stroke="hsl(var(--border))" />
                <PolarAngleAxis
                  dataKey="dim"
                  tick={(props: AngleAxisTickProps) => {
                    const { x, y, payload } = props;
                    const item = radarData.find((r) => r.dim === payload.value);
                    return (
                      <text
                        x={x}
                        y={y}
                        dy={4}
                        textAnchor="middle"
                        fontSize={12}
                        fill={
                          item?.hasData
                            ? "hsl(var(--foreground))"
                            : "hsl(var(--muted-foreground))"
                        }
                      >
                        {payload.value}
                      </text>
                    );
                  }}
                />
                <PolarRadiusAxis
                  angle={30}
                  domain={[0, 100]}
                  tick={false}
                  axisLine={false}
                />
                <Tooltip
                  contentStyle={{
                    fontSize: 11,
                    borderRadius: 8,
                    border: "1px solid hsl(var(--border))",
                  }}
                  formatter={(
                    value: TooltipValue,
                    name: number | string,
                    entry: TooltipEntry,
                  ) => {
                    const item = entry.payload as
                      (typeof radarData)[number] | undefined;
                    if (item && !item.hasData) {
                      return [
                        t("parent.overview.insufficient"),
                        item?.dim ?? name,
                      ];
                    }
                    return [Number(value).toFixed(1), item?.dim ?? name];
                  }}
                />
                <Radar
                  name={t("parent.overview.dimension")}
                  dataKey="value"
                  stroke="hsl(var(--primary))"
                  fill="hsl(var(--primary))"
                  fillOpacity={0.25}
                  strokeWidth={2}
                />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* 维度卡片 */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {DIMENSIONS.map((dim) => {
          const raw = data.dimensions?.[dim];
          const hasData = raw != null;
          const color = DIMENSION_COLORS[dim];
          return (
            <Card
              key={dim}
              className={cn("overflow-hidden", !hasData && "opacity-70")}
            >
              <div className="h-1.5" style={{ backgroundColor: color }} />
              <CardContent className="pt-4">
                <span className="text-sm font-medium text-foreground">
                  {t(DIMENSION_LABEL_KEY[dim])}
                </span>
                {hasData ? (
                  <div className="flex items-baseline gap-1 mt-1">
                    <span className="text-2xl font-bold text-foreground">
                      {toNum(raw).toFixed(1)}
                    </span>
                    <span className="text-xs text-muted-foreground">/ 100</span>
                  </div>
                ) : (
                  <div className="py-2 text-sm text-muted-foreground">
                    {t("parent.overview.insufficient")}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* 学期报告摘要 */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-primary" />
            <CardTitle className="text-sm font-semibold">
              {t("parent.overview.reportSummary")}
            </CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          {!data.report || Object.keys(data.report).length === 0 ? (
            <div className="flex flex-col items-center justify-center py-6 border border-dashed rounded-lg text-muted-foreground">
              <p className="text-sm">{t("parent.overview.reportEmpty")}</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {report?.term != null && (
                <div className="rounded-lg border border-border/50 px-3 py-2.5 text-sm">
                  <span className="text-muted-foreground">
                    {t("parent.overview.reportTerm")}：
                  </span>
                  <span className="font-medium text-foreground">
                    {String(report.term)}
                  </span>
                </div>
              )}
              {report?.total != null && (
                <div className="rounded-lg border border-border/50 px-3 py-2.5 text-sm">
                  <span className="text-muted-foreground">
                    {t("parent.overview.reportTotalGrowth")}：
                  </span>
                  <span className="font-medium text-foreground">
                    {toNum(report.total).toFixed(1)}
                  </span>
                </div>
              )}
              {report?.term == null && report?.total == null && (
                <div className="text-sm text-muted-foreground">
                  {t("parent.overview.reportEmpty")}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 最近成长记录 */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <History className="w-4 h-4 text-primary" />
            <CardTitle className="text-sm font-semibold">
              {t("parent.overview.recentRecords")}
            </CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          {records.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-6 border border-dashed rounded-lg text-muted-foreground">
              <p className="text-sm">{t("parent.overview.recordsEmpty")}</p>
            </div>
          ) : (
            <ul className="space-y-2">
              {records.map((rec) => {
                const color = DIMENSION_COLORS[rec.dimension];
                return (
                  <li
                    key={rec.id ?? `${rec.dimension}-${rec.occurred_at}`}
                    className="flex items-start gap-3 rounded-lg border border-border/50 px-3 py-2.5"
                  >
                    <span
                      className="mt-1 w-2 h-2 rounded-full shrink-0"
                      style={{
                        backgroundColor:
                          color ?? "hsl(var(--muted-foreground))",
                      }}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-foreground truncate">
                        {rec.note || rec.indicator_name || rec.source_type || "—"}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {t(DIMENSION_LABEL_KEY[rec.dimension])}
                        {rec.indicator_name ? ` · ${rec.indicator_name}` : ""}
                      </p>
                    </div>
                    <div className="text-right shrink-0">
                      <span className="text-sm font-semibold text-foreground">
                        +{toNum(rec.growth_point).toFixed(1)}
                      </span>
                      {rec.occurred_at && (
                        <p className="text-xs text-muted-foreground">
                          {formatDateTime(rec.occurred_at)}
                        </p>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/** 家长端：孩子五育画像（列表 + 详情） */
export function ParentPortalPage() {
  const { t } = useLocale();
  const [selected, setSelected] = useState<ParentStudent | null>(null);
  const { data = [], isLoading, isError, refetch } = useQuery({
    queryKey: ["parent-students"],
    queryFn: listParentStudents,
  });

  if (selected) {
    return (
      <ParentStudentDetail
        student={selected}
        onBack={() => setSelected(null)}
      />
    );
  }

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
        <Loader2 className="w-6 h-6 animate-spin mb-2" />
        <p className="text-sm">{t("parent.loading")}</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
        <p className="text-sm mb-3">{t("parent.loadFailed")}</p>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          <RefreshCw className="w-4 h-4 mr-1" />
          {t("parent.retry")}
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-3 animate-fade-in">
      <div className="flex items-center gap-3 bg-card border border-border/50 rounded-xl p-3 px-5">
        <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
          <User className="w-4 h-4 text-primary" />
        </div>
        <div className="min-w-0">
          <h2 className="font-semibold text-foreground leading-tight">
            {t("parent.title")}
          </h2>
          <p className="text-xs text-muted-foreground truncate">
            {t("parent.subtitle")}
          </p>
        </div>
      </div>

      {data.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 border border-dashed rounded-xl text-muted-foreground">
          <Users className="w-10 h-10 mb-3 text-muted-foreground/40" />
          <p className="text-sm">{t("parent.noStudents")}</p>
          <p className="text-xs mt-1">{t("parent.noStudentsHint")}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {data.map((student) => (
            <button
              key={student.student_id}
              onClick={() => setSelected(student)}
              className="flex items-center gap-3 p-4 rounded-xl bg-card border border-border/50 hover:border-primary/40 hover:shadow-md transition-all duration-200 hover-scale cursor-pointer text-left"
            >
              <div className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center shrink-0">
                <User className="w-5 h-5" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-medium text-foreground truncate">
                  {student.name}
                </p>
                <p className="text-xs text-muted-foreground truncate">
                  {t("parent.class")} {student.class_name || student.class_id}
                </p>
              </div>
              <ChevronRight className="w-4 h-4 shrink-0 text-muted-foreground/60" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
