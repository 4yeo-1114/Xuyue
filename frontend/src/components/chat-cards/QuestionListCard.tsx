import { ClipboardList, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import type { QuestionListData } from "./types";

function difficultyLabel(d: number) {
  if (d <= 0.3) return { textKey: "chatCards.difficulty.easy", cls: "bg-emerald-500/10 text-emerald-600" };
  if (d <= 0.7) return { textKey: "chatCards.difficulty.medium", cls: "bg-amber-500/10 text-amber-600" };
  return { textKey: "chatCards.difficulty.hard", cls: "bg-destructive/10 text-destructive" };
}

export function QuestionListCard({ data, onNavigate }: { data: QuestionListData; onNavigate?: (id: string) => void }) {
  const { t } = useLocale();
  const [expanded, setExpanded] = useState(false);
  if (!data.questions?.length) return null;

  const stats = { easy: 0, medium: 0, hard: 0 };
  data.questions.forEach(q => {
    if (q.difficulty <= 0.3) stats.easy++;
    else if (q.difficulty <= 0.7) stats.medium++;
    else stats.hard++;
  });

  const display = expanded ? data.questions : data.questions.slice(0, 5);
  const hasMore = data.questions.length > 5;

  return (
    <div className="border border-border/60 rounded-xl my-2 bg-card/80 backdrop-blur-sm overflow-hidden shadow-sm">
      <div className="flex items-center gap-2 px-3 py-2.5 bg-primary/5 border-b border-border/40">
        <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center">
          <ClipboardList className="w-3.5 h-3.5 text-primary" />
        </div>
        <span className="font-semibold text-sm">{t("chatCards.questionList.found", { count: data.total })}</span>
        <div className="ml-auto flex gap-1.5">
          {stats.easy > 0 && <Badge variant="secondary" className="text-[10px] bg-emerald-500/10 text-emerald-600 border-0">{t("chatCards.difficulty.easy")} {stats.easy}</Badge>}
          {stats.medium > 0 && <Badge variant="secondary" className="text-[10px] bg-amber-500/10 text-amber-600 border-0">{t("chatCards.difficulty.medium")} {stats.medium}</Badge>}
          {stats.hard > 0 && <Badge variant="secondary" className="text-[10px] bg-destructive/10 text-destructive border-0">{t("chatCards.difficulty.hard")} {stats.hard}</Badge>}
        </div>
      </div>

      <div className="divide-y divide-border/30">
        {display.map((q, i) => {
          const dl = difficultyLabel(q.difficulty);
          return (
            <div key={q.id || i} className="px-3 py-2 text-xs hover:bg-accent/30 transition-colors">
              <div className="flex items-start gap-1.5">
                <span className="text-muted-foreground shrink-0 font-mono w-4 text-right">{i + 1}</span>
                <span className="line-clamp-2 flex-1">{q.content}</span>
              </div>
              <div className="flex items-center gap-2 mt-1 ml-5.5 text-[11px] text-muted-foreground">
                <span className={cn("px-1.5 py-0.5 rounded", dl.cls)}>{t(dl.textKey)}</span>
                <span>{q.type}</span>
                <span>{t("chatCards.questionList.scoreSuffix", { score: q.score })}</span>
                <span>{t("chatCards.questionList.usedCount", { count: q.use_count })}</span>
              </div>
              {q.knowledge_points?.length > 0 && (
                <div className="flex gap-1 flex-wrap mt-1 ml-5.5">
                  {q.knowledge_points.map(kp => (
                    <span key={kp} className="bg-muted/60 px-1.5 py-0.5 rounded text-[10px]">{kp}</span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="flex items-center gap-2 px-3 py-2 border-t border-border/40 bg-muted/20">
        {hasMore && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-[11px] text-primary hover:text-primary/80 flex items-center gap-0.5 transition-colors"
          >
            <ChevronDown className={cn("w-3 h-3 transition-transform", expanded && "rotate-180")} />
            {expanded ? t("chatCards.common.collapse") : t("chatCards.questionList.expandAll", { count: data.total })}
          </button>
        )}
        <div className="flex gap-1.5 ml-auto">
          <button onClick={() => onNavigate?.("prep-exam")} className="text-[11px] px-2.5 py-1 rounded-md bg-primary/10 text-primary hover:bg-primary/20 transition-colors font-medium">{t("chatCards.questionList.addToPaper")}</button>
          <button onClick={() => onNavigate?.("analytics-questions")} className="text-[11px] px-2.5 py-1 rounded-md bg-primary/10 text-primary hover:bg-primary/20 transition-colors font-medium">{t("chatCards.questionList.questionAnalysis")}</button>
        </div>
      </div>
    </div>
  );
}
