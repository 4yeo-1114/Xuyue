import { User, TrendingUp, TrendingDown, Minus, ArrowRight, AlertTriangle, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import type { StudentCardData } from "./types";

function RiskBadge({ level }: { level?: string }) {
  const { t } = useLocale();
  if (!level) return null;
  const config: Record<string, { icon: typeof TrendingUp; className: string; textKey: string }> = {
    "上升": { icon: TrendingUp, className: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/20", textKey: "chatCards.studentList.risk.rising" },
    "下滑": { icon: TrendingDown, className: "bg-destructive/10 text-destructive border-destructive/20", textKey: "chatCards.studentList.risk.declining" },
    "稳定": { icon: Minus, className: "bg-muted text-muted-foreground border-border", textKey: "chatCards.studentList.risk.stable" },
  };
  const c = config[level];
  if (!c) return null;
  const Icon = c.icon;
  return (
    <span className={cn("inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full border", c.className)}>
      <Icon className="w-3 h-3" />{t(c.textKey, undefined, level)}
    </span>
  );
}

function ScoreTrend({ scores }: { scores: StudentCardData["scores"] }) {
  if (!scores || scores.length < 2) return null;
  const reversed = scores.slice(0, 4).reverse();
  return (
    <div className="flex items-center gap-1.5 mt-1">
      {reversed.map((s, i) => {
        const prev = i > 0 ? reversed[i - 1] : null;
        const up = prev ? s.score > prev.score : false;
        const down = prev ? s.score < prev.score : false;
        return (
          <span key={i} className="flex items-center gap-0.5">
            {i > 0 && <ArrowRight className="w-3 h-3 text-muted-foreground/50" />}
            <span className={cn(
              "text-xs font-semibold tabular-nums px-1.5 py-0.5 rounded",
              up && "bg-emerald-500/10 text-emerald-600",
              down && "bg-destructive/10 text-destructive",
              !up && !down && "text-foreground"
            )}>
              {s.score}
            </span>
          </span>
        );
      })}
    </div>
  );
}

interface StudentListCardProps {
  students: StudentCardData[];
  onNavigate?: (id: string) => void;
}

export function StudentListCard({ students, onNavigate }: StudentListCardProps) {
  const { t } = useLocale();
  const [expanded, setExpanded] = useState(false);
  const MAX_COLLAPSED = 3;
  const display = expanded ? students : students.slice(0, MAX_COLLAPSED);
  const hasMore = students.length > MAX_COLLAPSED;

  return (
    <div className="border border-border/60 rounded-xl my-2 bg-card/80 backdrop-blur-sm overflow-hidden shadow-sm">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2.5 bg-primary/5 border-b border-border/40">
        <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center">
          <User className="w-3.5 h-3.5 text-primary" />
        </div>
        <span className="font-semibold text-sm">{t("chatCards.studentList.title")}</span>
        <Badge variant="secondary" className="text-[10px] ml-auto">{t("chatCards.studentList.studentCount", { count: students.length })}</Badge>
      </div>

      {/* Student list */}
      <div className="divide-y divide-border/30">
        {display.map((data) => {
          const latestScore = data.scores?.[0];
          const scorePercent = latestScore ? Math.round((latestScore.score / latestScore.total) * 100) : 0;
          return (
            <div key={data.id || data.student_number} className="px-3 py-2.5 hover:bg-accent/30 transition-colors">
              {/* Row 1: name + risk */}
              <div className="flex items-center gap-2 mb-1">
                <span className="font-medium text-sm">{data.name}</span>
                <span className="text-[11px] text-muted-foreground">{data.student_number}</span>
                <RiskBadge level={data.risk_level} />
                <span className="ml-auto text-[11px] text-muted-foreground bg-muted/60 px-1.5 py-0.5 rounded">{data.class_name}</span>
              </div>

              {/* Row 2: score bar */}
              {latestScore && (
                <div className="flex items-center gap-2 mb-1.5">
                  <Progress value={scorePercent} className="h-1.5 flex-1" />
                  <span className="text-xs font-semibold tabular-nums w-16 text-right">
                    {latestScore.score}<span className="text-muted-foreground font-normal">/{latestScore.total}</span>
                  </span>
                  {data.target_score != null && (
                    <span className="text-[11px] text-primary">→{data.target_score}</span>
                  )}
                </div>
              )}

              {/* Score trend */}
              <ScoreTrend scores={data.scores} />

              {/* Weak points */}
              {data.weak_points?.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1.5">
                  {data.weak_points.map(w => (
                    <span key={w} className="text-[10px] px-1.5 py-0.5 rounded-md bg-destructive/10 text-destructive font-medium">{w}</span>
                  ))}
                  {data.wrong_count > 0 && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400 font-medium flex items-center gap-0.5">
                      <AlertTriangle className="w-2.5 h-2.5" />{t("chatCards.studentList.wrongCount", { count: data.wrong_count })}
                    </span>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Expand / Actions */}
      <div className="flex items-center gap-2 px-3 py-2 border-t border-border/40 bg-muted/20">
        {hasMore && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-[11px] text-primary hover:text-primary/80 flex items-center gap-0.5 transition-colors"
          >
            <ChevronDown className={cn("w-3 h-3 transition-transform", expanded && "rotate-180")} />
            {expanded ? t("chatCards.common.collapse") : t("chatCards.studentList.expandAll", { count: students.length })}
          </button>
        )}
        <div className="flex gap-1.5 ml-auto">
          <button onClick={() => onNavigate?.("class-students")} className="text-[11px] px-2.5 py-1 rounded-md bg-primary/10 text-primary hover:bg-primary/20 transition-colors font-medium">{t("chatCards.studentList.viewDetail")}</button>
          <button onClick={() => onNavigate?.("ai-targeted")} className="text-[11px] px-2.5 py-1 rounded-md bg-primary/10 text-primary hover:bg-primary/20 transition-colors font-medium">{t("chatCards.studentList.targetedImprove")}</button>
        </div>
      </div>
    </div>
  );
}

/* Single student card (backward compat) */
export function StudentCard({ data, onNavigate }: { data: StudentCardData; onNavigate?: (id: string) => void }) {
  return <StudentListCard students={[data]} onNavigate={onNavigate} />;
}
