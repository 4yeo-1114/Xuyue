import { useLocale } from "@/contexts/LocaleContext";
import { useMemo } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import { Loader2, Sparkles, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PortfolioResponse } from "@/services/wuyuApi";
import {
  DIMENSIONS,
  DIMENSION_COLORS,
  DIMENSION_LABEL_KEY,
  tierVariant,
  toNum,
} from "./portfolioShared";

/** PolarAngleAxis tick 渲染回调实际接收的字段(recharts 根包未导出该类型,按实际使用收紧) */
interface AngleAxisTickProps {
  x: number;
  y: number;
  payload: { value: string | number };
}

/** recharts Tooltip formatter 回调实际使用字段(recharts 根包未导出 ValueType/NameType/Payload,按需收紧) */
type TooltipValue = number | string | Array<number | string>;
interface TooltipEntry {
  name?: number | string;
  value?: TooltipValue;
  payload?: unknown;
}

const INTELLECTUAL_EVENT_ORDER = [
  "wrong_question_corrected",
  "exam_rank_up",
  "targeted_report",
  "above_class_avg",
  "correction_rate_high",
  "weak_point_conquered",
];

interface PortfolioDetailPanelProps {
  portfolio: PortfolioResponse;
}

export function PortfolioDetailPanel({ portfolio }: PortfolioDetailPanelProps) {
  const { t } = useLocale();

  const radarData = useMemo(
    () =>
      DIMENSIONS.map((dim) => ({
        dim: t(DIMENSION_LABEL_KEY[dim]),
        value: toNum(portfolio.composite?.[dim]),
        hasData: portfolio.data_status?.[dim] === "has_data",
        raw: toNum(portfolio.dimensions?.[dim]),
      })),
    [portfolio, t],
  );

  const hasBaseline =
    !!portfolio.composite &&
    Object.values(portfolio.composite).some((v) => v != null);

  const trendData = portfolio.trend ?? [];

  return (
    <div className="space-y-4">
      {/* 雷达图 */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-primary" />
            <CardTitle className="text-sm font-semibold">
              {t("wuyu.overview.radar")}
            </CardTitle>
          </div>
          <CardDescription>{t("wuyu.overview.radarHint")}</CardDescription>
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
                        t("wuyu.overview.insufficient"),
                        item?.dim ?? name,
                      ];
                    }
                    return [Number(value).toFixed(1), item?.dim ?? name];
                  }}
                />
                <Radar
                  name={t("wuyu.overview.composite")}
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

      {/* 维度指标卡 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
        {DIMENSIONS.map((dim) => {
          const hasData = portfolio.data_status?.[dim] === "has_data";
          const composite = portfolio.composite?.[dim];
          const tier = portfolio.tier?.[dim];
          const rank = portfolio.rank?.[dim];
          const n = portfolio.n?.[dim];
          const percentile = portfolio.percentile?.[dim];
          const raw = toNum(portfolio.dimensions?.[dim]);
          const activity = toNum(portfolio.activity_track?.[dim]?.count);
          const color = DIMENSION_COLORS[dim];

          return (
            <Card
              key={dim}
              className={cn("overflow-hidden", !hasData && "opacity-70")}
            >
              <div className="h-1.5" style={{ backgroundColor: color }} />
              <CardContent className="pt-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-foreground">
                    {t(DIMENSION_LABEL_KEY[dim])}
                  </span>
                  {hasData ? (
                    <Badge variant={tierVariant(tier)}>{tier ?? "—"}</Badge>
                  ) : (
                    <Badge variant="outline" className="text-muted-foreground">
                      {t("wuyu.overview.insufficient")}
                    </Badge>
                  )}
                </div>

                {hasData ? (
                  <div className="space-y-1.5 text-sm">
                    <div className="flex items-baseline gap-1">
                      <span className="text-2xl font-bold text-foreground">
                        {composite != null ? toNum(composite).toFixed(1) : "—"}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        / 100
                      </span>
                    </div>
                    <div className="text-xs text-muted-foreground space-y-0.5">
                      <div className="flex justify-between">
                        <span>{t("wuyu.overview.growthPoint")}</span>
                        <span className="text-foreground">{raw}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>{t("wuyu.overview.activity")}</span>
                        <span className="text-foreground">{activity}</span>
                      </div>
                      {rank != null && (
                        <div className="flex justify-between">
                          <span>{t("wuyu.overview.rank")}</span>
                          <span className="text-foreground">
                            {rank}
                            {n ? ` / ${n}` : ""}
                          </span>
                        </div>
                      )}
                      {percentile != null && (
                        <div className="flex justify-between">
                          <span>{t("wuyu.overview.classPercentile")}</span>
                          <span className="text-foreground">
                            {toNum(percentile).toFixed(1)}%
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="py-3 text-sm text-muted-foreground">
                    {t("wuyu.overview.insufficient")}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {!hasBaseline && (
        <p className="text-xs text-muted-foreground text-center">
          {t("wuyu.overview.noBaseline")}
        </p>
      )}

      {/* 智育自动明细 */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-primary" />
            <CardTitle className="text-sm font-semibold">
              {t("wuyu.overview.intellectualDetail")}
            </CardTitle>
          </div>
          <CardDescription>
            {t("wuyu.overview.intellectualEvents")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {Object.keys(portfolio.intellectual_auto ?? {}).length === 0 ? (
            <div className="flex flex-col items-center justify-center py-6 border border-dashed rounded-lg text-muted-foreground">
              <p className="text-sm">{t("wuyu.empty")}</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
              {INTELLECTUAL_EVENT_ORDER.map((etype) => {
                const ev = portfolio.intellectual_auto?.[etype];
                if (!ev || toNum(ev.count) === 0) return null;
                return (
                  <div
                    key={etype}
                    className="flex items-center justify-between rounded-lg border border-border/50 px-3 py-2.5 text-sm"
                  >
                    <span className="text-muted-foreground">
                      {t(`wuyu.overview.event.${etype}`)}
                    </span>
                    <span className="flex items-center gap-2">
                      <Badge variant="secondary">
                        {toNum(ev.count)} {t("wuyu.overview.times")}
                      </Badge>
                      <span className="font-semibold text-foreground">
                        +{toNum(ev.points).toFixed(1)}
                      </span>
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 月度趋势 */}
      {trendData.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold">
              {t("wuyu.overview.trend")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[220px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={trendData}>
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="hsl(var(--border))"
                  />
                  <XAxis
                    dataKey="month"
                    fontSize={11}
                    stroke="hsl(var(--muted-foreground))"
                  />
                  <YAxis
                    fontSize={11}
                    stroke="hsl(var(--muted-foreground))"
                    allowDecimals={false}
                  />
                  <Tooltip
                    contentStyle={{
                      fontSize: 11,
                      borderRadius: 8,
                      border: "1px solid hsl(var(--border))",
                    }}
                  />
                  <Bar
                    dataKey="points"
                    name={t("wuyu.overview.growthPoint")}
                    fill="hsl(var(--primary))"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/** 加载态（供父级使用） */
export function DetailLoading() {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
      <Loader2 className="w-6 h-6 animate-spin mb-2" />
      <p className="text-sm">…</p>
    </div>
  );
}
