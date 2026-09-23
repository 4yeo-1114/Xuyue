import { useState, useEffect } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { CheckCircle2, XCircle, AlertTriangle, BookOpen, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { getLatestWrongQuestions, type WrongQuestionItem } from "@/services/api";
import { gradingImageUrl } from "@/services/gradingApi";

const ERROR_TYPE_BADGE: Record<string, { cls: string }> = {
  知识漏洞: { cls: "bg-destructive/15 text-destructive border-destructive/30" },
  方法缺失: { cls: "bg-orange-500/15 text-orange-700 border-orange-500/30" },
  审题失误: { cls: "bg-yellow-500/15 text-yellow-700 border-yellow-500/30" },
  计算错误: { cls: "bg-yellow-500/15 text-yellow-700 border-yellow-500/30" },
};

interface WrongQuestionDetailDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  classId: string;
  studentName: string;
  subject: string;
  category: string;
  subPoint?: string | null;
  count: number;
}

export function WrongQuestionDetailDialog({
  open, onOpenChange, classId, studentName, subject, category, subPoint, count,
}: WrongQuestionDetailDialogProps) {
  const { t } = useLocale();

  const [questions, setQuestions] = useState<WrongQuestionItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [examName, setExamName] = useState("");
  const [examDate, setExamDate] = useState("");

  useEffect(() => {
    if (open && classId && studentName && subject) {
      setLoading(true);
      getLatestWrongQuestions(classId, studentName, subject)
        .then((res) => {
          setExamName(res.exam_name);
          if (res.created_at) {
             const d = new Date(res.created_at);
             setExamDate(`${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`);
          } else {
             setExamDate("");
          }
          
          let filtered = res.questions || [];
          if (subPoint && subPoint !== category) {
             // If a specific subpoint is selected, try to filter or just show all if none match exactly
             const matched = filtered.filter(q => q.title && q.title.includes(subPoint));
             if (matched.length > 0) filtered = matched;
          }
          setQuestions(filtered);
        })
        .catch(console.error)
        .finally(() => setLoading(false));
    }
  }, [open, classId, studentName, subject, category, subPoint]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] p-0">
        <DialogHeader className="px-6 pt-6 pb-3">
          <DialogTitle className="text-base flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-primary" />
            {t("studentAnalysis.wrong.title", { student: studentName, topic: subPoint || category })}
            <Badge variant="outline" className="text-xs ml-1">{t("studentAnalysis.wrong.count", { count: questions.length })}</Badge>
          </DialogTitle>
        </DialogHeader>
        <ScrollArea className="px-6 pb-6 max-h-[calc(85vh-80px)]">
          {loading ? (
             <div className="flex flex-col items-center justify-center py-10">
               <Loader2 className="w-6 h-6 animate-spin text-muted-foreground mb-2" />
               <p className="text-sm text-muted-foreground">{t("studentAnalysis.wrong.loading")}</p>
             </div>
          ) : questions.length === 0 ? (
             <div className="text-center py-10 text-muted-foreground text-sm">
               {t("studentAnalysis.wrong.empty")}
             </div>
          ) : (
            <div className="space-y-4">
              {questions.map((q, i) => {
                const etBadge = ERROR_TYPE_BADGE["知识漏洞"];
                const questionImg = gradingImageUrl(q.image_url || undefined);
                const answerImg = gradingImageUrl(q.answer_url || undefined);
                return (
                  <div key={i} className="rounded-lg border border-border/50 bg-muted/20 p-4">
                    {/* Question header */}
                    <div className="flex items-center gap-2 mb-2 flex-wrap">
                      <span className="text-xs font-bold text-primary bg-primary/10 w-6 h-6 rounded-full flex items-center justify-center">{i + 1}</span>
                      <Badge variant="outline" className={cn("text-[10px]", etBadge.cls)}>{t("studentAnalysis.wrong.knowledgeGap")}</Badge>
                      <span className="text-[10px] text-muted-foreground ml-auto">{examName} {examDate ? `· ${examDate}` : ''}</span>
                    </div>

                    {/* Question content */}
                    <p className="text-sm text-foreground leading-relaxed mb-3 font-medium">{q.title}</p>

                    {questionImg ? (
                      <div className="mb-3 rounded-md border border-border/60 bg-white overflow-hidden">
                        <img
                          src={questionImg}
                          alt={q.title}
                          className="max-h-72 w-full object-contain"
                          loading="lazy"
                        />
                      </div>
                    ) : (
                      <p className="mb-3 text-xs text-muted-foreground">{t("studentAnalysis.profile.noImage")}</p>
                    )}

                    {answerImg && (
                      <div className="mb-3 rounded-md border border-border/60 bg-white overflow-hidden">
                        <div className="flex items-center gap-1.5 px-2 py-1 text-[11px] text-muted-foreground bg-muted/40 border-b border-border/50">
                          <AlertTriangle className="w-3 h-3" />
                          {t("studentAnalysis.profile.hasAnswerImage")}
                        </div>
                        <img
                          src={answerImg}
                          alt={`${q.title} answer`}
                          className="max-h-72 w-full object-contain"
                          loading="lazy"
                        />
                      </div>
                    )}

                    <Separator className="mb-3" />

                    {/* Analysis hint */}
                    <div className="mt-2 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                      <AlertTriangle className="w-3 h-3" />
                      {t("studentAnalysis.wrong.reason")}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
