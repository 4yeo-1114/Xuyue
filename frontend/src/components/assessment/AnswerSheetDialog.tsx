import { useEffect, useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, CheckCircle2 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  getAssessmentSession,
  startAssessmentSession,
  submitAssessmentAnswers,
  type AssessmentSession,
  type AssessmentSubmitResult,
} from "@/services/assessmentApi";
import { ConsentBadge, DimensionBars } from "./shared";

interface AnswerSheetDialogProps {
  session: AssessmentSession | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmitted: () => void;
}

export function AnswerSheetDialog({ session, open, onOpenChange, onSubmitted }: AnswerSheetDialogProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [started, setStarted] = useState(false);
  const [result, setResult] = useState<AssessmentSubmitResult | null>(null);

  const sessionId = session?.id ?? null;

  // 打开时拉取会话详情（含题面），pending 状态自动 start
  const { data: detail, isLoading } = useQuery({
    queryKey: ["assessment-session", sessionId],
    queryFn: () => getAssessmentSession(sessionId!),
    enabled: open && !!sessionId,
  });

  useEffect(() => {
    if (!open) {
      setAnswers({});
      setResult(null);
      setStarted(false);
      return;
    }
    setResult(null);
    // 会话已提交则展示只读，不触发 start
    if (session && (session.status === "submitted" || session.status === "graded")) {
      setStarted(true);
    }
  }, [open, session]);

  const { mutate: doStart, isPending: starting } = useMutation({
    mutationFn: () => startAssessmentSession(sessionId!),
    onSuccess: () => {
      setStarted(true);
      queryClient.invalidateQueries({ queryKey: ["assessment-sessions"] });
    },
    onError: (err: Error) => toast.error(t("assessment.session.startFailed"), { description: err.message }),
  });

  const { mutate: doSubmit, isPending: submitting } = useMutation({
    mutationFn: () => submitAssessmentAnswers(sessionId!, Object.entries(answers).map(([qid, opt]) => ({ question_id: qid, option_key: opt }))),
    onSuccess: (res) => {
      setResult(res);
      toast.success(t("assessment.answer.submitSuccess"));
      queryClient.invalidateQueries({ queryKey: ["assessment-sessions"] });
      queryClient.invalidateQueries({ queryKey: ["assessment-results"] });
      onSubmitted();
    },
    onError: (err: Error) => toast.error(t("assessment.answer.submitFailed"), { description: err.message }),
  });

  const questions = detail?.questions ?? session?.questions ?? [];
  const alreadySubmitted = !!detail && (detail.status === "submitted" || detail.status === "graded");

  const allAnswered = questions.every((q) => answers[q.id]);

  const handleSubmit = () => {
    if (!allAnswered) {
      toast.warning(t("assessment.answer.completeAll"));
      return;
    }
    toast(t("assessment.answer.submitConfirm"), {
      action: {
        label: t("assessment.answer.submit"),
        onClick: () => doSubmit(),
      },
    });
  };

  const canAnswer = started && !alreadySubmitted;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {t("assessment.answer.title")}
            <span className="text-xs font-normal text-muted-foreground">
              {detail?.definition_name ?? session?.definition_name}
            </span>
          </DialogTitle>
        </DialogHeader>

        {isLoading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : alreadySubmitted ? (
          <div className="flex flex-col items-center justify-center py-20 gap-2">
            <CheckCircle2 className="w-10 h-10 text-emerald-500" />
            <p className="text-sm text-muted-foreground">{t("assessment.answer.alreadySubmitted")}</p>
          </div>
        ) : (
          <>
            <div className="rounded-lg bg-muted/50 px-4 py-3 text-sm text-muted-foreground">
              {t("assessment.answer.guide")}
            </div>

            {!started ? (
              <div className="flex flex-col items-center justify-center py-16 gap-2">
                <p className="text-sm text-muted-foreground">
                  {t("assessment.session.status.pending")}
                </p>
                <Button size="sm" disabled={starting} onClick={() => doStart()}>
                  {starting && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
                  {t("assessment.session.start")}
                </Button>
              </div>
            ) : (
              <ScrollArea className="flex-1 min-h-0 pr-3">
                <div className="space-y-5 py-2">
                  {questions.map((q, idx) => (
                    <div key={q.id} className="space-y-2">
                      <p className="text-sm font-medium">
                        <span className="text-muted-foreground mr-1.5">{idx + 1}.</span>
                        {q.text}
                      </p>
                      <RadioGroup
                        value={answers[q.id] ?? ""}
                        onValueChange={(v) => setAnswers((prev) => ({ ...prev, [q.id]: v }))}
                        className="space-y-1.5"
                      >
                        {q.options.map((opt) => (
                          <div key={opt.key} className="flex items-start gap-2 rounded-md border border-border/60 px-3 py-2">
                            <RadioGroupItem value={opt.key} id={`${q.id}-${opt.key}`} className="mt-0.5" />
                            <Label
                              htmlFor={`${q.id}-${opt.key}`}
                              className="text-sm font-normal cursor-pointer"
                            >
                              {opt.text}
                            </Label>
                          </div>
                        ))}
                      </RadioGroup>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}

            <DialogFooter className="pt-3 border-t mt-2">
              {canAnswer && (
                <Button disabled={submitting} onClick={handleSubmit}>
                  {submitting && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
                  {submitting ? t("assessment.answer.submitting") : t("assessment.answer.submit")}
                </Button>
              )}
            </DialogFooter>
          </>
        )}

        {result && (
          <div className="rounded-xl border border-border/60 p-4 space-y-4 bg-card">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold">{t("assessment.answer.result")}</p>
              <ConsentBadge status={result.consent_status} />
            </div>
            <div>
              <p className="text-xs text-muted-foreground mb-2">
                {t("assessment.answer.labels")} · {t("assessment.answer.totalAnswered", { count: result.total_answered })}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {result.labels.length === 0 ? (
                  <span className="text-xs text-muted-foreground">{t("assessment.empty")}</span>
                ) : (
                  result.labels.map((lb) => (
                    <span
                      key={lb}
                      className="inline-flex items-center rounded-full bg-secondary px-2.5 py-0.5 text-xs font-medium text-secondary-foreground"
                    >
                      {lb}
                    </span>
                  ))
                )}
              </div>
            </div>
            <DimensionBars percents={result.dimension_percents} />
            <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
              {t("assessment.answer.close")}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
