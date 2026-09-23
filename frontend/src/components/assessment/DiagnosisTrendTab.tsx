import { useMemo, useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { useQuery } from "@tanstack/react-query";
import {
  TrendingUp,
  UserSquare2,
  Loader2,
  TriangleAlert,
  ArrowUp,
  ArrowDown,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { listStudentsByClass } from "@/services/api";
import { listStudentResults } from "@/services/assessmentApi";
import {
  buildTrendSeries,
  lastTwoDelta,
  latestPercents,
  weakDimensions,
} from "@/services/assessmentTrend";
import { EmptyState, NeedsClassPlaceholder, dimensionLabelKey } from "./shared";
import { cn } from "@/lib/utils";

interface DiagnosisTrendTabProps {
  selectedClass: string;
}

/** 评估域 5 维配色（折线 / 图例 / Δ 圆点共用） */
const DIM_COLORS: Record<string, string> = {
  learning_style: "#2563eb",
  interest: "#f59e0b",
  social_style: "#10b981",
  emotion_regulation: "#8b5cf6",
  challenge_coping: "#ef4444",
};

/** 图表 X 轴短日期标签（如 8/10） */
function formatAxisLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, { month: "numeric", day: "numeric" });
}

export function DiagnosisTrendTab({ selectedClass }: DiagnosisTrendTabProps) {
  const { t } = useLocale();
  const [studentId, setStudentId] = useState("");
  const [includeWithdrawn, setIncludeWithdrawn] = useState(false);

  const { data: students = [] } = useQuery({
    queryKey: ["students", selectedClass],
    queryFn: () => listStudentsByClass(selectedClass),
    enabled: !!selectedClass,
  });

  const sortedStudents = useMemo(() => {
    return [...students].sort((a, b) => a.name.localeCompare(b.name, "zh"));
  }, [students]);

  const activeStudentId = studentId || sortedStudents[0]?.id || "";

  const { data: results, isLoading } = useQuery({
    queryKey: ["assessment-diagnosis", activeStudentId, includeWithdrawn],
    queryFn: () =>
      listStudentResults(activeStudentId, {
        include_withdrawn: includeWithdrawn,
      }),
    enabled: !!activeStudentId,
  });

  const rows = results?.rows ?? [];

  const series = useMemo(() => buildTrendSeries(rows), [rows]);
  const deltas = useMemo(() => lastTwoDelta(series), [series]);
  const latest = useMemo(() => latestPercents(series), [series]);
  const weak = useMemo(() => weakDimensions(latest), [latest]);

  if (!selectedClass) {
    return <NeedsClassPlaceholder icon={TrendingUp} />;
  }

  const chartData = series.points.map((p) => ({
    ...p,
    label: formatAxisLabel(p.date),
  }));
  const deltaByDim = Object.fromEntries(deltas.map((d) => [d.dim, d]));
  const hasTrend = series.points.length >= 2;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-2 min-w-[220px]">
          <Label>{t("assessment.result.student")}</Label>
          <Select value={activeStudentId} onValueChange={setStudentId}>
            <SelectTrigger className="w-[240px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {sortedStudents.map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  {s.name}（{s.student_number}）
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <label className="flex items-center gap-2 pb-2 text-sm cursor-pointer">
          <Checkbox
            checked={includeWithdrawn}
            onCheckedChange={(v) => setIncludeWithdrawn(!!v)}
          />
          {t("assessment.result.includeWithdrawn")}
        </label>
      </div>

      {!activeStudentId ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState
              icon={UserSquare2}
              title={t("assessment.result.selectStudent")}
            />
          </CardContent>
        </Card>
      ) : isLoading ? (
        <Card>
          <CardContent className="flex items-center justify-center py-16">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </CardContent>
        </Card>
      ) : rows.length === 0 ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState
              icon={TrendingUp}
              title={t("assessment.result.empty")}
            />
          </CardContent>
        </Card>
      ) : !hasTrend ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState
              icon={TrendingUp}
              title={t("assessment.trend.needMore")}
            />
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {/* ── 趋势折线 ── */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <CardTitle className="text-sm font-semibold">
                  {t("assessment.trend.title")}
                </CardTitle>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  {series.dims.map((dim) => (
                    <span
                      key={dim}
                      className="flex items-center gap-1 text-[11px] text-muted-foreground"
                    >
                      <span
                        className="inline-block h-2 w-2 rounded-full"
                        style={{ backgroundColor: DIM_COLORS[dim] }}
                      />
                      {t(dimensionLabelKey(dim))}
                    </span>
                  ))}
                </div>
              </div>
              <CardDescription className="text-xs">
                {t("assessment.trend.subtitle")}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-[260px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={chartData}
                    margin={{ top: 5, right: 10, bottom: 5, left: -10 }}
                  >
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="hsl(var(--border))"
                    />
                    <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                    <YAxis
                      domain={[0, 100]}
                      ticks={[0, 20, 40, 60, 80, 100]}
                      tick={{ fontSize: 10 }}
                    />
                    <Tooltip
                      contentStyle={{
                        fontSize: 11,
                        borderRadius: 8,
                        border: "1px solid hsl(var(--border))",
                      }}
                    />
                    {series.dims.map((dim) => (
                      <Line
                        key={dim}
                        type="monotone"
                        dataKey={dim}
                        name={t(dimensionLabelKey(dim))}
                        stroke={DIM_COLORS[dim]}
                        strokeWidth={2}
                        dot={{ r: 3 }}
                        activeDot={{ r: 5 }}
                        connectNulls
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>

          {/* ── 上次 vs 本次 ── */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold">
                {t("assessment.trend.deltaTitle")}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {series.dims.map((dim) => {
                const delta = deltaByDim[dim]?.delta ?? null;
                const isWeak = weak.includes(dim);
                return (
                  <div
                    key={dim}
                    className="flex flex-wrap items-center justify-between gap-2 text-sm"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span
                        className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
                        style={{ backgroundColor: DIM_COLORS[dim] }}
                      />
                      <span className="text-foreground">
                        {t(dimensionLabelKey(dim))}
                      </span>
                      {isWeak && (
                        <Badge
                          variant="outline"
                          className="border-amber-200 bg-amber-50 text-amber-700"
                        >
                          <TriangleAlert className="w-3 h-3 mr-1" />
                          {t("assessment.trend.weakBadge")}
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <span>{t("assessment.trend.deltaLabel")}</span>
                      {delta === null ? (
                        <span className="text-muted-foreground">--</span>
                      ) : delta >= 0 ? (
                        <span className="flex items-center gap-0.5 font-semibold tabular-nums text-emerald-600">
                          <ArrowUp className="w-3.5 h-3.5" />
                          {delta.toFixed(1)}%
                        </span>
                      ) : (
                        <span className="flex items-center gap-0.5 font-semibold tabular-nums text-destructive">
                          <ArrowDown className="w-3.5 h-3.5" />
                          {Math.abs(delta).toFixed(1)}%
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>

          {/* ── 薄弱维度 ── */}
          {weak.length > 0 && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-1.5 text-sm font-semibold">
                  <TriangleAlert className="w-4 h-4 text-amber-500" />
                  {t("assessment.trend.weakTitle")}
                </CardTitle>
                <CardDescription className="text-xs">
                  {t("assessment.trend.weakHint")}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-1.5">
                  {weak.map((dim) => (
                    <Badge
                      key={dim}
                      variant="outline"
                      className={cn(
                        "border-amber-200 bg-amber-50 text-amber-700",
                      )}
                    >
                      {t(dimensionLabelKey(dim))} · {latest[dim]?.toFixed(1)}%
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}

export default DiagnosisTrendTab;
