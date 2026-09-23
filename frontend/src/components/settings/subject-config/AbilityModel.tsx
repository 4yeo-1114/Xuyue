import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Radar } from "lucide-react";
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar as ReRadar,
  ResponsiveContainer,
} from "recharts";
import { useLocale } from "@/contexts/LocaleContext";
import type { AbilityDimension } from "./subjectConfigData";

interface Props {
  abilities: AbilityDimension[];
}

export function AbilityModel({ abilities }: Props) {
  const { t } = useLocale();
  const classAvgLabel = t("settingsSubject.ability.classAvg");
  const termTargetLabel = t("settingsSubject.ability.termTarget");

  const chartData = abilities.map((a) => ({
    name: a.name,
    classAvg: a.classAvg,
    target: a.target,
  }));

  return (
    <Card className="h-full overflow-auto">
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <Radar className="w-4 h-4 text-primary" />
          {t("settingsSubject.ability.title")} ·{" "}
          {t("settingsSubject.ability.titleSuffix")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="h-52">
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={chartData}>
              <PolarGrid stroke="hsl(var(--border))" />
              <PolarAngleAxis
                dataKey="name"
                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              />
              <PolarRadiusAxis
                domain={[0, 5]}
                tickCount={6}
                tick={{ fontSize: 9 }}
              />
              <ReRadar
                name={classAvgLabel}
                dataKey="classAvg"
                stroke="hsl(var(--primary))"
                fill="hsl(var(--primary))"
                fillOpacity={0.2}
                strokeWidth={2}
              />
              <ReRadar
                name={termTargetLabel}
                dataKey="target"
                stroke="hsl(var(--accent))"
                fill="none"
                strokeWidth={1.5}
                strokeDasharray="4 3"
              />
            </RadarChart>
          </ResponsiveContainer>
        </div>

        <div className="flex items-center gap-4 text-xs text-muted-foreground justify-center">
          <span className="flex items-center gap-1">
            <span className="w-3 h-0.5 bg-primary inline-block rounded" />
            {classAvgLabel}
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-0.5 bg-accent inline-block rounded border-dashed" />
            {termTargetLabel}
          </span>
        </div>

        <Separator />

        <div className="space-y-2">
          <h4 className="font-medium text-foreground">
            {t("settingsSubject.ability.dimensionDef")}
          </h4>
          <div className="space-y-1.5">
            {abilities.map((a) => (
              <div
                key={a.id}
                className="flex items-center gap-2 p-2 rounded bg-muted/40 text-xs"
              >
                <span className="font-medium text-foreground w-16 shrink-0">
                  {a.name}
                </span>
                <span className="text-muted-foreground flex-1">
                  {a.description}
                </span>
                <span className="font-mono text-primary">{a.classAvg}</span>
                <span className="text-muted-foreground">/</span>
                <span className="font-mono text-accent">{a.target}</span>
              </div>
            ))}
          </div>
        </div>

        <Separator />

        <div className="space-y-1.5">
          <h4 className="font-medium text-foreground">
            {t("settingsSubject.ability.metrics")}
          </h4>
          <p className="text-xs text-muted-foreground">
            {t("settingsSubject.ability.levelHint")}
          </p>
          {abilities.filter((a) => a.classAvg < a.target).length > 0 && (
            <div className="p-2 rounded bg-amber-50 border border-amber-200 text-xs text-amber-800">
              <span className="font-medium">
                {t("settingsSubject.ability.weakDimensions")}
              </span>
              {abilities
                .filter((a) => a.classAvg < a.target)
                .map((a) => a.name)
                .join("、")}
            </div>
          )}
        </div>

        {/* 调整维度/编辑定义/查看测评方案 无对应操作，原死按钮已移除，保持纯展示 */}
      </CardContent>
    </Card>
  );
}
