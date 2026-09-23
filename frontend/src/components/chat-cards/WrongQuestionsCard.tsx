import { FileQuestion } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSubjectName } from "@/i18n";
import type { WrongQuestionData } from "./types";

export function WrongQuestionsCard({ data, onNavigate }: { data: { questions: WrongQuestionData[] }; onNavigate?: (id: string) => void }) {
  const { locale, t } = useLocale();
  if (!data.questions?.length) return null;
  return (
    <div className="border border-border/60 rounded-xl my-2 bg-card/80 backdrop-blur-sm overflow-hidden shadow-sm">
      <div className="flex items-center gap-2 px-3 py-2.5 bg-primary/5 border-b border-border/40">
        <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center">
          <FileQuestion className="w-3.5 h-3.5 text-primary" />
        </div>
        <span className="font-semibold text-sm">{t("chatCards.wrongQuestions.title")}</span>
        <Badge variant="secondary" className="text-[10px] ml-auto">{t("chatCards.wrongQuestions.count", { count: data.questions.length })}</Badge>
      </div>
      <div className="divide-y divide-border/30">
        {data.questions.slice(0, 3).map((q, i) => (
          <div key={i} className="px-3 py-2 text-xs space-y-0.5">
            <div className="flex gap-1.5">
              <span className="bg-muted px-1.5 py-0.5 rounded">{translateSubjectName(locale, q.subject)}</span>
              <span className="bg-amber-500/10 text-amber-700 dark:text-amber-400 px-1.5 py-0.5 rounded">{q.error_type}</span>
              {q.student_name && <span className="text-muted-foreground">{q.student_name}</span>}
            </div>
            <div className="text-muted-foreground line-clamp-2">{q.content}</div>
          </div>
        ))}
      </div>
      {data.questions.length > 3 && <div className="text-[11px] text-muted-foreground px-3 py-1.5">{t("chatCards.wrongQuestions.more", { count: data.questions.length - 3 })}</div>}
      <div className="flex gap-1.5 px-3 py-2 border-t border-border/40 bg-muted/20">
        <button onClick={() => onNavigate?.("analytics-questions")} className="text-[11px] px-2.5 py-1 rounded-md bg-primary/10 text-primary hover:bg-primary/20 transition-colors font-medium">{t("chatCards.questionList.questionAnalysis")}</button>
      </div>
    </div>
  );
}
