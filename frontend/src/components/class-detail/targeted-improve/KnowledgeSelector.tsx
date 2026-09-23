import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLocale } from "@/contexts/LocaleContext";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { TrendingUp, TrendingDown, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import type { KnowledgeTarget } from "./targetedData";

interface KnowledgeSelectorProps {
  targets: KnowledgeTarget[];
  selected: KnowledgeTarget | null;
  onSelect: (t: KnowledgeTarget) => void;
}

export function KnowledgeSelector({ targets, selected, onSelect }: KnowledgeSelectorProps) {
  const { t, locale } = useLocale();

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">{t("classDetail.selectTargetKnowledgeTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {targets.map(target => (
            <button
              key={target.id}
              onClick={() => onSelect(target)}
              className={cn(
                "w-full flex items-center gap-3 p-3 rounded-lg border text-left transition-all hover:shadow-sm",
                selected?.id === target.id ? "ring-2 ring-primary border-primary/30 bg-primary/5" : "border-border/50"
              )}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-semibold">{target.name}</span>
                  <Badge variant={target.masteryRate < 50 ? "destructive" : "secondary"} className="text-[10px]">
                    {t("classDetail.masteryRateLabel", { rate: target.masteryRate })}
                  </Badge>
                </div>
                <Progress value={target.masteryRate} className="h-1.5 mb-1" />
                <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                  <span className="flex items-center gap-0.5">
                    <Users className="w-3 h-3" />{t("classDetail.peopleWeakLabel", { count: target.affectedCount })}
                  </span>
                  <span className="flex items-center gap-0.5">
                    {target.trend > 0 ? <TrendingUp className="w-3 h-3 text-emerald-600" /> : <TrendingDown className="w-3 h-3 text-destructive" />}
                    {target.trend > 0 ? "+" : ""}{target.trend}%
                  </span>
                  <span>{target.commonIssue}</span>
                </div>
              </div>
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
