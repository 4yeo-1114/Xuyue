import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLocale } from "@/contexts/LocaleContext";
import { Radar as RadarIcon } from "lucide-react";
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  Radar,
  Legend,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { ClassCapabilityDimensions } from "@/services/api";

interface CompareRadarProps {
  /** 本班名称（用于标题与图例） */
  className?: string;
  /** 六维能力数据（report.analysis.capability_dimensions）；无数据时保持空态 */
  capabilityDimensions?: ClassCapabilityDimensions | null;
}

/** 六维能力对比雷达：本班 score vs 班级平均 classAvg 双序列。无六维数据时降级为空态。 */
export function CompareRadar({
  className,
  capabilityDimensions,
}: CompareRadarProps) {
  const { t } = useLocale();
  const dims = capabilityDimensions?.dims?.filter(
    (d) => d && d.name && typeof d.score === "number",
  );

  const chartData = dims?.map((d) => ({
    name: d.name,
    score: d.score,
    classAvg: typeof d.classAvg === "number" ? d.classAvg : 0,
  }));

  const hasData = !!chartData && chartData.length > 0;

  return (
    <Card data-tour="ca-radar">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">
          {t("classDetail.compare.radar.title")}
          {className ? ` · ${className}` : ""}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {!hasData ? (
          <div className="flex h-[240px] flex-col items-center justify-center rounded-lg border border-dashed border-border/60 px-6 text-center">
            <RadarIcon className="mb-2 h-6 w-6 text-muted-foreground" />
            <p className="text-sm font-medium text-foreground">
              {t("classDetail.compare.radar.unsupported")}
            </p>
            <p className="mt-1 max-w-md text-xs leading-5 text-muted-foreground">
              {t("classDetail.compare.radar.unsupportedDesc")}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_240px] gap-4">
            <div className="h-[260px]">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart
                  data={chartData}
                  cx="50%"
                  cy="50%"
                  outerRadius="70%"
                >
                  <PolarGrid stroke="hsl(var(--border))" />
                  <PolarAngleAxis
                    dataKey="name"
                    tick={{
                      fontSize: 11,
                      fill: "hsl(var(--muted-foreground))",
                    }}
                  />
                  <Tooltip
                    contentStyle={{
                      fontSize: 11,
                      borderRadius: 8,
                      border: "1px solid hsl(var(--border))",
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" />
                  <Radar
                    name={t("classDetail.compare.radar.legendClassAvg")}
                    dataKey="classAvg"
                    stroke="hsl(var(--muted-foreground))"
                    fill="hsl(var(--muted-foreground))"
                    fillOpacity={0.1}
                    strokeDasharray="4 4"
                  />
                  <Radar
                    name={t("classDetail.compare.radar.legendThisClass")}
                    dataKey="score"
                    stroke="hsl(var(--primary))"
                    fill="hsl(var(--primary))"
                    fillOpacity={0.2}
                    strokeWidth={2}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>
            <div className="space-y-2 text-xs">
              {capabilityDimensions?.level ? (
                <p className="text-foreground">
                  <span className="text-muted-foreground">
                    {t("classDetail.compare.radar.levelLabel")}
                  </span>
                  <span className="ml-1 font-medium">
                    {capabilityDimensions.level}
                  </span>
                </p>
              ) : null}
              {capabilityDimensions?.summary ? (
                <p className="leading-5 text-muted-foreground">
                  {capabilityDimensions.summary}
                </p>
              ) : null}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
