import { useCallback, useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, CornerUpLeft, Loader2, Save, Send } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  flowNextItem,
  flowSubmitReview,
  flowReviseReview,
  type FlowMark,
  type FlowNextItem,
  type FlowReviewStatus,
  type FlowTaskDetail,
} from "@/services/gradingApi";
import { FreeMarkCanvas } from "./FreeMarkCanvas";

type Props = {
  assignmentId: string;
  task: FlowTaskDetail;
  onClose: () => void;
};

/** 生成可点击打分序列：整数满分（如 5）→ [0,1,2,3,4,5]；带 0.5（如 2.5）→ [0,0.5,1,…,2.5]；档位过多退回 [0, 满分]。 */
function scoreSteps(maxScore: number): number[] {
  const max = Math.max(0, Number(maxScore) || 0);
  if (max <= 0) return [0];
  const step = Number.isInteger(max) ? 1 : 0.5;
  const steps: number[] = [];
  for (let v = 0; v <= max + 1e-9; v += step) steps.push(Number(v.toFixed(1)));
  if (steps[steps.length - 1] !== max) steps.push(max);
  return steps.length > 12 ? [0, max] : steps;
}

type PastReview = {
  review_id: string;
  item: FlowNextItem;
  score: string;
  status: FlowReviewStatus;
  marks: FlowMark[];
  comment: string;
};

const STATUS_OPTIONS: Array<{ key: FlowReviewStatus; label: string; short: string }> = [
  { key: "correct", label: "对", short: "√" },
  { key: "wrong", label: "错", short: "×" },
  { key: "partial", label: "半对", short: "半" },
  { key: "unanswered", label: "未作答", short: "○" },
];

export function FlowGradingWorkbench({ assignmentId, task, onClose }: Props) {
  const [item, setItem] = useState<FlowNextItem | null>(null);
  const [marks, setMarks] = useState<FlowMark[]>([]);
  const [status, setStatus] = useState<FlowReviewStatus>("correct");
  const [score, setScore] = useState("");
  const [comment, setComment] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  // 已提交的上一张栈（后进先出），供「上一张」回看/修改
  const [past, setPast] = useState<PastReview[]>([]);
  // 非空 = 正在回看/修改某张已提交的 review（review_id）
  const [reviewingId, setReviewingId] = useState<string | null>(null);

  const maxScore = item?.max_score ?? task.max_score ?? 0;
  const isReviewing = reviewingId !== null;

  const loadNext = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await flowNextItem(assignmentId);
      if (!res.claimed) {
        setItem(null);
        setDone(true);
        return;
      }
      setItem(res);
      setMarks([]);
      setScore("");
      setComment("");
      setStatus("correct");
      setReviewingId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "取题失败");
    } finally {
      setLoading(false);
    }
  }, [assignmentId]);

  useEffect(() => {
    void loadNext();
  }, [loadNext]);

  const applyScore = (v: number) => {
    const value = Math.max(0, Math.min(v, maxScore));
    setScore(String(value));
    setStatus(value >= maxScore ? "correct" : value <= 0 ? "wrong" : "partial");
  };

  const onScoreInput = (raw: string) => {
    setScore(raw);
    const v = Number(raw);
    if (raw === "" || Number.isNaN(v)) return;
    setStatus(v >= maxScore ? "correct" : v <= 0 ? "wrong" : "partial");
  };

  /** 点 √/×/半对/未作答 标记：同时给出对应分数（对=满分、错/未答=0、半对=一半）。 */
  const pickStatus = (s: FlowReviewStatus) => {
    setStatus(s);
    if (s === "correct") setScore(String(maxScore));
    else if (s === "wrong" || s === "unanswered") setScore("0");
    else setScore((maxScore / 2).toFixed(1).replace(/\.0$/, ""));
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target instanceof Element ? e.target : null;
      if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
      if (e.key === "1") {
        setStatus("correct");
        setScore(String(maxScore));
      } else if (e.key === "2") {
        setStatus("wrong");
        setScore("0");
      } else if (e.key === "3") {
        setStatus("partial");
        setScore((maxScore / 2).toFixed(1).replace(/\.0$/, ""));
      } else if (e.key === "4") {
        setStatus("unanswered");
        setScore("0");
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [maxScore]);

  const submit = async () => {
    if (!item?.item_id || isReviewing) return;
    const s = Number(score);
    if (Number.isNaN(s)) {
      setError("请输入有效分数");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const res = await flowSubmitReview({
        assignment_id: assignmentId,
        item_id: item.item_id,
        score: s,
        status,
        marks,
        comment: comment || undefined,
      });
      setPast((p) => [...p, { review_id: res.review_id, item, score, status, marks, comment }]);
      await loadNext();
    } catch (e) {
      setError(e instanceof Error ? e.message : "提交失败");
    } finally {
      setSubmitting(false);
    }
  };

  const goPrev = () => {
    if (past.length === 0) return;
    const last = past[past.length - 1];
    setPast((p) => p.slice(0, -1));
    setReviewingId(last.review_id);
    setItem(last.item);
    setScore(last.score);
    setStatus(last.status);
    setMarks(last.marks);
    setComment(last.comment);
    setError("");
  };

  const saveRevise = async () => {
    if (reviewingId === null) return;
    const s = Number(score);
    if (Number.isNaN(s)) {
      setError("请输入有效分数");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await flowReviseReview(reviewingId, {
        score: s,
        status,
        marks,
        comment: comment || undefined,
      });
      await loadNext();
    } catch (e) {
      setError(e instanceof Error ? e.message : "修改失败");
    } finally {
      setSubmitting(false);
    }
  };

  const resume = () => {
    setReviewingId(null);
    void loadNext();
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="left-1/2 top-1/2 flex h-[96vh] w-[98vw] max-w-[1600px] -translate-x-1/2 -translate-y-1/2 flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="flex shrink-0 flex-row items-center justify-between gap-3 border-b border-border px-4 py-3">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={onClose}>
              <ChevronLeft className="h-4 w-4" /> 返回
            </Button>
            <DialogTitle className="text-base">
              {task.batch_name} · {task.display_label}（满分 {maxScore}）
            </DialogTitle>
            {isReviewing && (
              <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">回看修改中</span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <div className="text-sm text-muted-foreground">
              {item ? `学生：${item.student_name || "-"}${item.student_number ? `（${item.student_number}）` : ""}` : ""}
            </div>
            <Button variant="outline" size="sm" onClick={goPrev} disabled={past.length === 0 || submitting}>
              <ChevronLeft className="h-4 w-4" /> 上一张
            </Button>
            <Button size="sm" onClick={isReviewing ? resume : submit} disabled={submitting || (!item && !isReviewing)}>
              {isReviewing ? "继续批改" : "下一张"}
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </DialogHeader>

        {done ? (
          <div className="flex flex-1 items-center justify-center text-muted-foreground">
            该题已全部批改完成，无待批条目。
          </div>
        ) : loading && !item ? (
          <div className="flex flex-1 items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="flex min-h-0 flex-1">
            {/* 左侧打分 / 盖章 */}
            <aside className="flex w-[340px] shrink-0 flex-col gap-3 overflow-y-auto border-r border-border p-4">
              <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2.5">
                <div className="mb-1 text-xs font-semibold text-emerald-700">标准答案</div>
                <div
                  className={cn(
                    "max-h-44 overflow-y-auto break-words text-sm font-medium leading-relaxed text-emerald-900",
                    !(item?.standard_answer || task.standard_answer) && "text-slate-400",
                  )}
                >
                  {item?.standard_answer || task.standard_answer || "（未设置）"}
                </div>
              </div>

              <div>
                <div className="mb-1 text-xs text-muted-foreground">对错标记</div>
                <div className="grid grid-cols-4 gap-1.5">
                  {STATUS_OPTIONS.map((opt) => (
                    <button
                      key={opt.key}
                      type="button"
                      onClick={() => pickStatus(opt.key)}
                      className={cn(
                        "flex flex-col items-center gap-0.5 rounded-lg border px-1 py-1.5 text-sm transition-colors",
                        status === opt.key
                          ? "border-primary bg-primary/10 font-semibold text-primary"
                          : "border-border hover:bg-muted",
                      )}
                    >
                      <span className="text-lg leading-none text-[#FF0000]">{opt.short}</span>
                      <span className="text-xs">{opt.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <div className="mb-1 text-xs text-muted-foreground">打分（满分 {maxScore}，快捷键 1/2/3/4）</div>
                <div className="flex flex-wrap gap-1.5">
                  {scoreSteps(maxScore).map((step) => {
                    const active = status !== "unanswered" && Math.abs(Number(score) - step) < 1e-9;
                    return (
                      <button
                        key={step}
                        type="button"
                        onClick={() => applyScore(step)}
                        className={cn(
                          "h-9 min-w-[2.5rem] rounded-md border text-sm font-semibold tabular-nums transition-colors",
                          active
                            ? step >= maxScore
                              ? "border-emerald-600 bg-emerald-600 text-white"
                              : step <= 0
                                ? "border-red-600 bg-red-600 text-white"
                                : "border-blue-600 bg-blue-600 text-white"
                            : "border-border bg-card text-foreground hover:bg-muted",
                        )}
                      >
                        {step}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <div className="mb-1 text-xs text-muted-foreground">输入分数</div>
                <Input
                  type="number"
                  inputMode="decimal"
                  value={score}
                  onChange={(e) => onScoreInput(e.target.value)}
                  placeholder="输入分数"
                  className="h-9 text-sm"
                />
              </div>

              <div>
                <div className="mb-1 text-xs text-muted-foreground">批注</div>
                <Textarea value={comment} onChange={(e) => setComment(e.target.value)} placeholder="可留批注" rows={2} />
              </div>

              <Button
                variant="outline"
                size="sm"
                onClick={() => setMarks((m) => m.slice(0, -1))}
                disabled={!marks.length || isReviewing}
              >
                <CornerUpLeft className="mr-1 h-4 w-4" /> 撤销最后一个章
              </Button>

              {error && <div className="text-xs text-destructive">{error}</div>}

              {isReviewing ? (
                <div className="mt-auto flex flex-col gap-2">
                  <Button onClick={saveRevise} disabled={submitting}>
                    {submitting ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Save className="mr-1 h-4 w-4" />}
                    保存修改
                  </Button>
                  <Button variant="outline" onClick={resume} disabled={submitting}>
                    <ChevronRight className="mr-1 h-4 w-4" /> 继续批改
                  </Button>
                </div>
              ) : (
                <Button onClick={submit} disabled={submitting || !item} className="mt-auto">
                  {submitting ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Send className="mr-1 h-4 w-4" />}
                  提交并下一张
                </Button>
              )}
            </aside>

            {/* 中央裁图 + 留痕 */}
            <div className="flex min-w-0 flex-1 flex-col">
              <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto bg-muted/20 p-4">
                {item?.crop_url ? (
                  <FreeMarkCanvas
                    imageUrl={item.crop_url}
                    marks={marks}
                    activeType={status}
                    readOnly={isReviewing}
                    onMarksChange={setMarks}
                  />
                ) : (
                  <div className="text-muted-foreground">无可显示的裁图</div>
                )}
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
