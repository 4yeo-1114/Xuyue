import {
  Users,
  TrendingUp,
  TrendingDown,
  Minus,
  AlertTriangle,
} from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";
import type { ClassOverviewData } from "./types";

export function ClassOverviewCard({
  data,
  onNavigate,
}: {
  data: ClassOverviewData;
  onNavigate?: (id: string) => void;
}) {
  const { t } = useLocale();
  return (
    <div className="border border-border/60 rounded-xl my-2 bg-card/80 backdrop-blur-sm overflow-hidden shadow-sm">
      <div className="flex items-center gap-2 px-3 py-2.5 bg-primary/5 border-b border-border/40">
        <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center">
          <Users className="w-3.5 h-3.5 text-primary" />
        </div>
        <span className="font-semibold text-sm">{data.class_name}</span>
        <span className="text-[11px] text-muted-foreground">
          {t("chatCards.classOverview.studentCount", {
            count: data.student_count,
          })}
        </span>
      </div>
      <div className="px-3 py-2.5 space-y-2">
        {data.avg_score > 0 && (
          <div className="text-xs">
            {t("chatCards.classOverview.avgScore")}
            <strong className="text-base">{data.avg_score}</strong>
          </div>
        )}
        {data.risk_stats &&
          data.risk_stats.rising +
            data.risk_stats.stable +
            data.risk_stats.declining >
            0 && (
            <div className="flex items-center gap-3 text-xs">
              <span className="flex items-center gap-0.5 text-emerald-600">
                <TrendingUp className="w-3 h-3" />
                {t("chatCards.classOverview.trend.rising", {
                  count: data.risk_stats.rising,
                })}
              </span>
              <span className="flex items-center gap-0.5 text-muted-foreground">
                <Minus className="w-3 h-3" />
                {t("chatCards.classOverview.trend.stable", {
                  count: data.risk_stats.stable,
                })}
              </span>
              <span className="flex items-center gap-0.5 text-destructive">
                <TrendingDown className="w-3 h-3" />
                {t("chatCards.classOverview.trend.declining", {
                  count: data.risk_stats.declining,
                })}
              </span>
            </div>
          )}
        {data.weak_students?.length > 0 && (
          <div className="text-xs">
            <span className="text-destructive flex items-center gap-1 mb-1">
              <AlertTriangle className="w-3 h-3" />
              {t("chatCards.classOverview.needAttention")}
            </span>
            <div className="flex flex-wrap gap-1">
              {data.weak_students.map((s, index) => (
                <span
                  key={`${s.name}-${index}`}
                  className="bg-destructive/10 text-destructive text-[10px] px-1.5 py-0.5 rounded-md"
                >
                  {t("chatCards.classOverview.studentScore", {
                    name: s.name,
                    score: s.score,
                  })}
                </span>
              ))}
            </div>
          </div>
        )}
        {data.weak_knowledge?.length > 0 && (
          <div className="text-xs">
            <span className="text-muted-foreground">
              {t("chatCards.classOverview.weakKnowledge")}
            </span>
            <div className="flex flex-wrap gap-1 mt-0.5">
              {data.weak_knowledge.map((k) => (
                <span
                  key={k}
                  className="bg-amber-500/10 text-amber-700 dark:text-amber-400 text-[10px] px-1.5 py-0.5 rounded-md"
                >
                  {k}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
      <div className="flex gap-1.5 px-3 py-2 border-t border-border/40 bg-muted/20">
        <button
          onClick={() => onNavigate?.("class-dashboard")}
          className="text-[11px] px-2.5 py-1 rounded-md bg-primary/10 text-primary hover:bg-primary/20 transition-colors font-medium"
        >
          {t("chatCards.classOverview.classDashboard")}
        </button>
        <button
          onClick={() => onNavigate?.("analytics-portrait")}
          className="text-[11px] px-2.5 py-1 rounded-md bg-primary/10 text-primary hover:bg-primary/20 transition-colors font-medium"
        >
          {t("chatCards.classOverview.classPortrait")}
        </button>
      </div>
    </div>
  );
}
