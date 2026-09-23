import { useCallback, useEffect, useState } from "react";
import { History, Loader2, Play, RefreshCw, Save } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import {
  flowMyTasks,
  flowTaskDetail,
  flowTaskHistory,
  flowTaskSpeed,
  flowReviseReview,
  type FlowTaskItem,
  type FlowTaskDetail,
  type FlowHistoryItem,
  type FlowReviewStatus,
} from "@/services/gradingApi";
import { FlowGradingWorkbench } from "./FlowGradingWorkbench";
import { FreeMarkCanvas } from "./FreeMarkCanvas";

const STATUS_LABEL: Record<FlowReviewStatus, string> = {
  correct: "对",
  wrong: "错",
  partial: "半对",
  unanswered: "未作答",
};

function statusBadge(status: FlowReviewStatus) {
  const color =
    status === "correct" ? "text-green-600" : status === "wrong" ? "text-red-600" : "text-amber-600";
  return <span className={cn("font-semibold", color)}>{STATUS_LABEL[status]}</span>;
}

export function FlowTeacherTasksPage() {
  const [tasks, setTasks] = useState<FlowTaskItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState<FlowTaskDetail | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await flowMyTasks();
      setTasks(res.items || []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openWorkbench = async (task: FlowTaskItem) => {
    try {
      const detail = await flowTaskDetail(task.assignment_id);
      setActive({ ...task, ...detail });
    } catch {
      setActive({ ...task, standard_answer: null });
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground">流水阅卷 · 我的批改任务</h1>
          <p className="text-sm text-muted-foreground">领取同题全年级答题卡，对照标准答案流水批改</p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={cn("mr-1 h-4 w-4", loading && "animate-spin")} /> 刷新
        </Button>
      </div>

      {loading && !tasks.length ? (
        <div className="flex justify-center py-20 text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      ) : tasks.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border p-16 text-center text-muted-foreground">
          暂无分配给你的批改任务
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {tasks.map((t) => (
            <TaskCard key={t.assignment_id} task={t} onStart={() => openWorkbench(t)} />
          ))}
        </div>
      )}

      {active && (
        <FlowGradingWorkbench assignmentId={active.assignment_id} task={active} onClose={() => setActive(null)} />
      )}
    </div>
  );
}

function TaskCard({ task, onStart }: { task: FlowTaskItem; onStart: () => void }) {
  const [historyOpen, setHistoryOpen] = useState(false);
  const percent = Math.round((task.progress || 0) * 100);

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm text-muted-foreground">{task.subject} · {task.batch_name}</div>
          <div className="mt-1 text-lg font-semibold text-foreground">{task.display_label}</div>
          <div className="mt-0.5 text-xs text-muted-foreground">
            {task.review_mode === "double" ? "双评" : "单评"}
            {task.role === "first" ? " · 一评" : task.role === "second" ? " · 二评" : ""} · 满分 {task.max_score}
          </div>
        </div>
        <Button onClick={onStart} size="sm">
          <Play className="mr-1 h-4 w-4" /> 开始批改
        </Button>
      </div>

      <div className="mt-4">
        <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
          <span>进度</span>
          <span>
            {task.graded_items}/{task.total_items}（{percent}%）
          </span>
        </div>
        <Progress value={percent} />
      </div>

      <Button variant="ghost" size="sm" className="mt-3" onClick={() => setHistoryOpen(true)}>
        <History className="mr-1 h-4 w-4" /> 批改历史 / 速度
      </Button>

      {historyOpen && (
        <HistoryDialog task={task} onClose={() => setHistoryOpen(false)} />
      )}
    </div>
  );
}

function HistoryDialog({ task, onClose }: { task: FlowTaskItem; onClose: () => void }) {
  const [items, setItems] = useState<FlowHistoryItem[]>([]);
  const [speed, setSpeed] = useState<{ speed_per_min: number; rolling_speed_per_min: number; total_items: number; graded_items: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [revising, setRevising] = useState<FlowHistoryItem | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [h, s] = await Promise.all([flowTaskHistory(task.assignment_id), flowTaskSpeed(task.assignment_id)]);
      setItems(h.items || []);
      setSpeed(s);
    } finally {
      setLoading(false);
    }
  }, [task.assignment_id]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>{task.display_label} · 批改历史</DialogTitle>
        </DialogHeader>

        {speed && (
          <div className="flex flex-wrap gap-6 rounded-lg bg-muted/50 px-4 py-3 text-sm">
            <div>
              进度 <span className="font-semibold">{speed.graded_items}/{speed.total_items}</span>
            </div>
            <div>
              平均速度 <span className="font-semibold">{speed.speed_per_min}</span> 张/分钟
            </div>
            <div>
              近10分钟 <span className="font-semibold">{speed.rolling_speed_per_min}</span> 张/分钟
            </div>
          </div>
        )}

        {loading ? (
          <div className="flex justify-center py-10"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
        ) : items.length === 0 ? (
          <div className="py-10 text-center text-muted-foreground">暂无批改记录</div>
        ) : (
          <div className="max-h-[60vh] overflow-y-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-muted text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">学生</th>
                  <th className="px-3 py-2">分数</th>
                  <th className="px-3 py-2">结果</th>
                  <th className="px-3 py-2">批改时间</th>
                  <th className="px-3 py-2">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it) => (
                  <tr key={it.review_id} className="border-t border-border">
                    <td className="px-3 py-2">{it.student_name || "-"}{it.student_number ? `（${it.student_number}）` : ""}</td>
                    <td className="px-3 py-2 font-semibold">{it.score}</td>
                    <td className="px-3 py-2">{statusBadge(it.status)}</td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">{it.submitted_at ? new Date(it.submitted_at).toLocaleString() : "-"}</td>
                    <td className="px-3 py-2">
                      {it.is_current ? (
                        <Button variant="outline" size="sm" onClick={() => setRevising(it)}>修改</Button>
                      ) : (
                        <span className="text-xs text-muted-foreground">已改分</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {revising && (
          <ReviseDialog item={revising} onClose={() => setRevising(null)} onSaved={load} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function ReviseDialog({ item, onClose, onSaved }: { item: FlowHistoryItem; onClose: () => void; onSaved: () => void }) {
  const [score, setScore] = useState(String(item.score));
  const [status, setStatus] = useState<FlowReviewStatus>(item.status);
  const [comment, setComment] = useState(item.comment || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const save = async () => {
    const s = Number(score);
    if (Number.isNaN(s)) {
      setError("请输入有效分数");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await flowReviseReview(item.review_id, { score: s, status, comment });
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "修改失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>修改批改 · {item.student_name || "-"}</DialogTitle>
        </DialogHeader>
        <div className="flex gap-4">
          <div className="min-w-0 flex-1">
            {item.crop_url ? (
              <FreeMarkCanvas imageUrl={item.crop_url} marks={item.marks || []} activeType={status} readOnly />
            ) : (
              <div className="flex h-40 items-center justify-center text-muted-foreground">无图</div>
            )}
          </div>
          <div className="flex w-[200px] shrink-0 flex-col gap-3">
            <div className="grid grid-cols-2 gap-2">
              {(Object.keys(STATUS_LABEL) as FlowReviewStatus[]).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setStatus(s)}
                  className={cn(
                    "rounded-lg border px-2 py-1.5 text-sm",
                    status === s ? "border-primary bg-primary/10 text-primary font-semibold" : "border-border hover:bg-muted",
                  )}
                >
                  {STATUS_LABEL[s]}
                </button>
              ))}
            </div>
            <Input type="number" inputMode="decimal" value={score} onChange={(e) => setScore(e.target.value)} placeholder="分数" />
            <Textarea value={comment} onChange={(e) => setComment(e.target.value)} placeholder="批注" rows={2} />
            {error && <div className="text-xs text-destructive">{error}</div>}
            <Button onClick={save} disabled={saving}>
              {saving ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Save className="mr-1 h-4 w-4" />}
              保存修改
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
