import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  fetchUsageStats,
  fetchBreakdown,
  type TrendGranularity,
  type StatsDimension,
  type StatsMetric,
  type TrendPoint,
  type DimensionRow,
} from "@/services/scanBillingApi";
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
  Upload,
  ScanLine,
  Activity,
  Coins,
  Inbox,
  Download,
  FolderOpen,
  Users,
} from "lucide-react";
import { toast } from "sonner";

/* ── 色板 ── */
const COLORS = { upload: "#3b82f6", grade: "#10b981", total: "#8b5cf6" };

/* ── 计费口径：按批改份数，每面 0.5 元 ── */
const PRICE_PER_SIDE = 0.5;

/* ── Chart Tooltip ── */
interface TooltipPayloadItem {
  name?: string;
  value?: number | string;
  color?: string;
}

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border bg-card p-3 shadow-lg text-sm">
      <p className="font-medium mb-1">{label}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color }} className="tabular-nums">
          {p.name}: {p.value}
        </p>
      ))}
    </div>
  );
}

/* ── 日期工具 ── */
function iso(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

type RangeKey = "7d" | "15d" | "thisMonth" | "lastMonth" | "custom";

function rangeFor(key: RangeKey): { start: string; end: string } {
  const today = new Date();
  const end = iso(today);
  switch (key) {
    case "7d": {
      const s = new Date(today);
      s.setDate(s.getDate() - 6);
      return { start: iso(s), end };
    }
    case "15d": {
      const s = new Date(today);
      s.setDate(s.getDate() - 14);
      return { start: iso(s), end };
    }
    case "thisMonth": {
      const s = new Date(today.getFullYear(), today.getMonth(), 1);
      return { start: iso(s), end };
    }
    case "lastMonth": {
      const s = new Date(today.getFullYear(), today.getMonth() - 1, 1);
      const e = new Date(today.getFullYear(), today.getMonth(), 0);
      return { start: iso(s), end: iso(e) };
    }
    default:
      return { start: end, end };
  }
}

const RANGE_OPTIONS: { key: RangeKey; label: string }[] = [
  { key: "7d", label: "近 7 天" },
  { key: "15d", label: "近 15 天" },
  { key: "thisMonth", label: "本月" },
  { key: "lastMonth", label: "上月" },
  { key: "custom", label: "自选" },
];

/* ── 指标卡 ── */
function StatCard({
  icon: Icon,
  label,
  value,
  unit,
  sub,
  color,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  color?: string;
}) {
  return (
    <Card className="card-elevated">
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div className="space-y-1 min-w-0">
            <p className="text-sm text-muted-foreground">{label}</p>
            <div className="flex items-baseline gap-1">
              <span className="text-2xl font-semibold tabular-nums">
                {value}
              </span>
              {unit && (
                <span className="text-sm text-muted-foreground">{unit}</span>
              )}
            </div>
            {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
          </div>
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
            style={{
              backgroundColor: color
                ? `${color}15`
                : "hsl(var(--primary) / 0.1)",
            }}
          >
            <Icon
              className="w-5 h-5"
              style={{ color: color || "hsl(var(--primary))" }}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/* ── 主组件 ── */
export function ScanConsumptionPage() {
  const [rangeKey, setRangeKey] = useState<RangeKey>("15d");
  const [custom, setCustom] = useState(() => rangeFor("thisMonth"));
  const [granularity, setGranularity] = useState<TrendGranularity>("day");
  const [dimension, setDimension] = useState<StatsDimension>("all");
  const [metric, setMetric] = useState<StatsMetric>("all");

  const period = useMemo(
    () => (rangeKey === "custom" ? custom : rangeFor(rangeKey)),
    [rangeKey, custom],
  );

  const { data, isLoading } = useQuery({
    queryKey: [
      "scan-billing",
      "usage-stats",
      period.start,
      period.end,
      granularity,
      dimension,
    ],
    queryFn: () =>
      fetchUsageStats({
        start_date: period.start,
        end_date: period.end,
        granularity,
        dimension,
      }),
    enabled: period.start <= period.end,
  });

  // 文件夹明细（维度为「全部」时用作补充明细表）
  const { data: folders } = useQuery({
    queryKey: ["scan-billing", "breakdown", period.start, period.end],
    queryFn: () =>
      fetchBreakdown({
        days: Math.max(
          1,
          Math.round(
            (new Date(period.end).getTime() - new Date(period.start).getTime()) /
              86400000,
          ) + 1,
        ),
        sort_by: "total",
      }),
    enabled: dimension === "all",
  });

  const summary = data?.summary;
  const series = data?.series ?? [];

  /** 导出 CSV（对齐七牛「导出 CSV」） */
  const exportCsv = () => {
    if (!series.length) {
      toast.error("当前无数据可导出");
      return;
    }
    const header = ["时间", "上传份数", "批改份数", "费用(元)"];
    const rows = series.map((p) => [
      p.label,
      p.upload,
      p.grade,
      (p.grade * PRICE_PER_SIDE).toFixed(2),
    ]);
    const csv = [header, ...rows]
      .map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(","))
      .join("\r\n");
    // 加 BOM，避免 Excel 打开中文乱码
    const blob = new Blob(["﻿" + csv], {
      type: "text/csv;charset=utf-8;",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `用量统计_${period.start}_${period.end}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("已导出 CSV");
  };

  const dimLabel =
    dimension === "folder" ? "按文件夹" : dimension === "user" ? "按教师" : "";

  return (
    <div className="space-y-6 animate-fade-in">
      {/* 标题 + 查询条件 */}
      <div className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-foreground">扫描消耗</h2>
          <p className="text-sm text-muted-foreground mt-1">
            按批改份数计费 · 每面 {PRICE_PER_SIDE} 元 · 支持时间粒度与维度筛选、CSV 导出
          </p>
        </div>

        <Card>
          <CardContent className="p-4 flex flex-wrap items-center gap-4">
            {/* 时间范围 */}
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-muted-foreground mr-1">
                时间范围
              </span>
              {RANGE_OPTIONS.map((o) => (
                <Button
                  key={o.key}
                  variant={rangeKey === o.key ? "default" : "outline"}
                  size="sm"
                  className="h-8 text-xs"
                  onClick={() => setRangeKey(o.key)}
                >
                  {o.label}
                </Button>
              ))}
            </div>

            {/* 自选日期 */}
            {rangeKey === "custom" && (
              <div className="flex items-center gap-2">
                <Input
                  type="date"
                  value={custom.start}
                  max={custom.end}
                  onChange={(e) =>
                    setCustom((c) => ({ ...c, start: e.target.value }))
                  }
                  className="h-8 w-[140px] text-xs"
                />
                <span className="text-xs text-muted-foreground">至</span>
                <Input
                  type="date"
                  value={custom.end}
                  min={custom.start}
                  onChange={(e) =>
                    setCustom((c) => ({ ...c, end: e.target.value }))
                  }
                  className="h-8 w-[140px] text-xs"
                />
              </div>
            )}

            <div className="h-6 w-px bg-border hidden sm:block" />

            {/* 时间粒度 */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">粒度</span>
              <Select
                value={granularity}
                onValueChange={(v) => setGranularity(v as TrendGranularity)}
              >
                <SelectTrigger className="h-8 w-[88px] text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="day">按天</SelectItem>
                  <SelectItem value="week">按周</SelectItem>
                  <SelectItem value="month">按月</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* 维度 */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">维度</span>
              <Select
                value={dimension}
                onValueChange={(v) => setDimension(v as StatsDimension)}
              >
                <SelectTrigger className="h-8 w-[104px] text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部</SelectItem>
                  <SelectItem value="folder">按文件夹</SelectItem>
                  <SelectItem value="user">按教师</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <Button
              variant="outline"
              size="sm"
              className="h-8 text-xs ml-auto"
              onClick={exportCsv}
            >
              <Download className="w-3.5 h-3.5 mr-1.5" />
              导出 CSV
            </Button>
          </CardContent>
        </Card>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-[110px] w-full" />
          <Skeleton className="h-[360px] w-full" />
        </div>
      ) : (
        <>
          {/* 汇总指标 */}
          {summary && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <StatCard
                icon={ScanLine}
                label="批改份数"
                value={summary.total_grade.toLocaleString()}
                unit="份"
                sub={`${period.start} ~ ${period.end}`}
                color={COLORS.grade}
              />
              <StatCard
                icon={Coins}
                label="费用"
                value={(summary.total_grade * PRICE_PER_SIDE).toFixed(2)}
                unit="元"
                sub={`每面 ${PRICE_PER_SIDE} 元`}
                color="#f59e0b"
              />
              <StatCard
                icon={Upload}
                label="上传份数"
                value={summary.total_upload.toLocaleString()}
                unit="份"
                sub={`日均 ${summary.avg_daily_upload.toFixed(2)} 份`}
                color={COLORS.upload}
              />
              <StatCard
                icon={Activity}
                label="日均批改"
                value={summary.avg_daily_grade.toFixed(2)}
                unit="份/天"
                sub={`共 ${summary.days} 天`}
                color={COLORS.total}
              />
            </div>
          )}

          {/* 用量趋势 */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-sm font-semibold">
                    用量趋势{dimLabel && `（${dimLabel}）`}
                  </CardTitle>
                  <CardDescription>
                    {granularity === "day"
                      ? "按天"
                      : granularity === "week"
                        ? "按周"
                        : "按月"}
                    聚合，堆叠展示上传与批改份数
                  </CardDescription>
                </div>
                {/* 指标切换 */}
                <div className="flex items-center gap-1.5">
                  {(
                    [
                      { k: "all", l: "全部" },
                      { k: "upload", l: "上传" },
                      { k: "grade", l: "批改" },
                    ] as { k: StatsMetric; l: string }[]
                  ).map((o) => (
                    <Button
                      key={o.k}
                      variant={metric === o.k ? "default" : "outline"}
                      size="sm"
                      className="h-7 text-xs"
                      onClick={() => setMetric(o.k)}
                    >
                      {o.l}
                    </Button>
                  ))}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {series.length ? (
                <div className="h-[320px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={series}
                      margin={{ top: 5, right: 10, bottom: 5, left: -10 }}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="hsl(var(--border))"
                      />
                      <XAxis
                        dataKey="label"
                        tick={{ fontSize: 11 }}
                        tickLine={false}
                        axisLine={false}
                        interval="preserveStartEnd"
                      />
                      <YAxis
                        tick={{ fontSize: 11 }}
                        tickLine={false}
                        axisLine={false}
                      />
                      <Tooltip content={<ChartTooltip />} />
                      <Legend iconType="circle" iconSize={8} />
                      {(metric === "all" || metric === "upload") && (
                        <Bar
                          dataKey="upload"
                          name="上传份数"
                          stackId="a"
                          fill={COLORS.upload}
                          radius={[0, 0, 0, 0]}
                        />
                      )}
                      {(metric === "all" || metric === "grade") && (
                        <Bar
                          dataKey="grade"
                          name="批改份数"
                          stackId="a"
                          fill={COLORS.grade}
                          radius={[3, 3, 0, 0]}
                        />
                      )}
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="flex h-[320px] flex-col items-center justify-center text-sm text-muted-foreground">
                  <Inbox className="mb-2 h-6 w-6" />
                  所选时间段无用量数据
                </div>
              )}
            </CardContent>
          </Card>

          {/* 维度明细（选了具体维度时） */}
          {dimension !== "all" && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold">
                  {dimLabel}明细
                </CardTitle>
                <CardDescription>
                  共 {data?.breakdown.length ?? 0} 个{dimLabel.slice(1)}，按合计降序
                </CardDescription>
              </CardHeader>
              <CardContent>
                {data?.breakdown.length ? (
                  <DimensionTable rows={data.breakdown} dimension={dimension} />
                ) : (
                  <EmptyBlock />
                )}
              </CardContent>
            </Card>
          )}

          {/* 文件夹消耗明细（维度=全部时的补充） */}
          {dimension === "all" && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold">
                  文件夹消耗明细
                </CardTitle>
                <CardDescription>按文件夹聚合的上传与批改计数</CardDescription>
              </CardHeader>
              <CardContent>
                {folders?.length ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border/50">
                          <th className="text-left py-2 px-2 font-medium text-muted-foreground">
                            文件夹
                          </th>
                          <th className="text-right py-2 px-2 font-medium text-muted-foreground">
                            上传(份)
                          </th>
                          <th className="text-right py-2 px-2 font-medium text-muted-foreground">
                            批改(份)
                          </th>
                          <th className="text-right py-2 px-2 font-medium text-muted-foreground">
                            费用(元)
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {folders.slice(0, 20).map((f) => (
                          <tr
                            key={f.folder_safe}
                            className="border-b border-border/20 hover:bg-muted/30 transition-colors"
                          >
                            <td className="py-2.5 px-2">
                              <div className="flex items-center gap-2">
                                <FolderOpen className="w-4 h-4 text-muted-foreground shrink-0" />
                                <span className="truncate max-w-[240px]">
                                  {f.folder_name}
                                </span>
                              </div>
                            </td>
                            <td className="text-right py-2.5 px-2 tabular-nums">
                              {f.upload.toLocaleString()}
                            </td>
                            <td className="text-right py-2.5 px-2 tabular-nums">
                              {f.grade.toLocaleString()}
                            </td>
                            <td className="text-right py-2.5 px-2 tabular-nums font-medium">
                              {(f.grade * PRICE_PER_SIDE).toFixed(2)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <EmptyBlock />
                )}
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

/* ── 维度明细表 ── */
function DimensionTable({
  rows,
  dimension,
}: {
  rows: DimensionRow[];
  dimension: StatsDimension;
}) {
  const Icon = dimension === "folder" ? FolderOpen : Users;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border/50">
            <th className="text-left py-2 px-2 font-medium text-muted-foreground w-10">
              #
            </th>
            <th className="text-left py-2 px-2 font-medium text-muted-foreground">
              {dimension === "folder" ? "文件夹" : "教师"}
            </th>
            <th className="text-right py-2 px-2 font-medium text-muted-foreground">
              上传(份)
            </th>
            <th className="text-right py-2 px-2 font-medium text-muted-foreground">
              批改(份)
            </th>
            <th className="text-right py-2 px-2 font-medium text-muted-foreground">
              费用(元)
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={r.key}
              className="border-b border-border/20 hover:bg-muted/30 transition-colors"
            >
              <td className="py-2.5 px-2 text-muted-foreground">{i + 1}</td>
              <td className="py-2.5 px-2">
                <div className="flex items-center gap-2">
                  <Icon className="w-4 h-4 text-muted-foreground shrink-0" />
                  <span className="truncate max-w-[240px]">{r.name}</span>
                </div>
              </td>
              <td className="text-right py-2.5 px-2 tabular-nums">
                {r.upload.toLocaleString()}
              </td>
              <td className="text-right py-2.5 px-2 tabular-nums">
                {r.grade.toLocaleString()}
              </td>
              <td className="text-right py-2.5 px-2 tabular-nums font-medium">
                {(r.grade * PRICE_PER_SIDE).toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EmptyBlock() {
  return (
    <div className="flex h-[180px] flex-col items-center justify-center text-sm text-muted-foreground">
      <Inbox className="mb-2 h-6 w-6" />
      暂无数据
    </div>
  );
}
