import { useCallback, useEffect, useState } from "react";
import { Loader2, Plus, RefreshCw, Scissors, Users, Scale, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import {
  flowListBatches,
  flowCreateBatch,
  flowGetBatch,
  flowCutBatch,
  flowCutStatus,
  flowListTeachers,
  flowAssign,
  flowProgress,
  flowArbitrations,
  flowArbitrate,
  flowSourceFolders,
  flowBatchCrops,
  type FlowBatchItem,
  type FlowQuestionItem,
  type FlowReviewStatus,
  type FlowSourceFolder,
  type FlowCropQuestion,
} from "@/services/gradingApi";
import { FreeMarkCanvas } from "@/components/grading/flow/FreeMarkCanvas";

const STATUS_LABEL: Record<FlowReviewStatus, string> = {
  correct: "对",
  wrong: "错",
  partial: "半对",
  unanswered: "未作答",
};

export function AdminFlowGradingPage() {
  const [batches, setBatches] = useState<FlowBatchItem[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const loadBatches = useCallback(async () => {
    setLoading(true);
    try {
      const res = await flowListBatches();
      setBatches(res.items || []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadBatches();
  }, [loadBatches]);

  return (
    <div className="space-y-6">
      <CreateBatchForm onCreated={() => void loadBatches()} />

      <div className="rounded-xl border border-border bg-card">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="font-semibold text-foreground">阅卷批次</h2>
          <Button variant="outline" size="sm" onClick={loadBatches} disabled={loading}>
            <RefreshCw className={cn("mr-1 h-4 w-4", loading && "animate-spin")} /> 刷新
          </Button>
        </div>
        <div className="divide-y divide-border">
          {batches.map((b) => (
            <button
              key={b.id}
              type="button"
              onClick={() => setSelected(b.id === selected ? null : b.id)}
              className={cn(
                "flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-muted/50",
                selected === b.id && "bg-primary/5",
              )}
            >
              <div>
                <div className="font-medium text-foreground">{b.name}</div>
                <div className="text-xs text-muted-foreground">
                  {b.subject}{b.grade ? ` · ${b.grade}` : ""} · {b.review_mode === "double" ? "双评" : "单评"} · {b.total_papers} 份
                </div>
              </div>
              <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{b.status}</span>
            </button>
          ))}
          {!batches.length && (
            <div className="px-4 py-8 text-center text-muted-foreground">暂无批次</div>
          )}
        </div>
      </div>

      {selected && <BatchDetail batchId={selected} />}
    </div>
  );
}

function CreateBatchForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("");
  const [grade, setGrade] = useState("");
  const [source, setSource] = useState("");
  const [reviewMode, setReviewMode] = useState<"single" | "double">("single");
  const [classIds, setClassIds] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [sourceFolders, setSourceFolders] = useState<FlowSourceFolder[]>([]);
  const [loadingFolders, setLoadingFolders] = useState(true);

  useEffect(() => {
    let mounted = true;
    flowSourceFolders()
      .then((res) => {
        if (mounted) setSourceFolders(res.folders || []);
      })
      .catch(() => {
        if (mounted) setSourceFolders([]);
      })
      .finally(() => {
        if (mounted) setLoadingFolders(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const submit = async () => {
    if (!name.trim() || !subject.trim()) {
      setError("批次名与科目不能为空");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await flowCreateBatch({
        name: name.trim(),
        subject: subject.trim(),
        grade: grade.trim() || undefined,
        source_folder_safe: source.trim() || undefined,
        review_mode: reviewMode,
        class_ids: classIds
          .split(/[,，\s]+/)
          .map((x) => x.trim())
          .filter(Boolean),
      });
      setName("");
      setSubject("");
      setGrade("");
      setSource("");
      setClassIds("");
      onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "创建失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <h2 className="mb-3 font-semibold text-foreground">新建阅卷批次</h2>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="批次名（如：七年级数学期中）" />
        <Input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="科目（如：数学）" />
        <Input value={grade} onChange={(e) => setGrade(e.target.value)} placeholder="年级（如：七年级）" />
        <select
          value={source}
          onChange={(e) => {
            const fname = e.target.value;
            setSource(fname);
            const cls = fname.split("__", 1)[0].replace(/^cls_/, "");
            if (cls) setClassIds(cls);
          }}
          className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
        >
          <option value="">
            {loadingFolders
              ? "加载文件夹中…"
              : sourceFolders.length
                ? "选择源文件夹（已切题）"
                : "暂无文件夹（请先建文件夹并完成切题）"}
          </option>
          {sourceFolders.map((f) => (
            <option key={f.folder_name} value={f.folder_name} disabled={!f.has_layout}>
              {f.display_name}
              {f.has_layout ? "（已切题）" : "（未切题）"}
            </option>
          ))}
        </select>
        <Input value={classIds} onChange={(e) => setClassIds(e.target.value)} placeholder="班级ID（逗号分隔，可空）" />
        <select
          value={reviewMode}
          onChange={(e) => setReviewMode(e.target.value as "single" | "double")}
          className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
        >
          <option value="single">单评</option>
          <option value="double">双评</option>
        </select>
      </div>
      {error && <div className="mt-2 text-xs text-destructive">{error}</div>}
      <Button className="mt-3" onClick={submit} disabled={saving}>
        {saving ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Plus className="mr-1 h-4 w-4" />}
        创建批次
      </Button>
    </div>
  );
}

function BatchDetail({ batchId }: { batchId: string }) {
  const [questions, setQuestions] = useState<FlowQuestionItem[]>([]);
  const [batch, setBatch] = useState<FlowBatchItem | null>(null);
  const [teachers, setTeachers] = useState<Array<{ user_id: string; display_name: string }>>([]);
  const [progress, setProgress] = useState<Awaited<ReturnType<typeof flowProgress>>["items"]>([]);
  const [arbitrations, setArbitrations] = useState<Awaited<ReturnType<typeof flowArbitrations>>["items"]>([]);
  const [crops, setCrops] = useState<FlowCropQuestion[]>([]);
  const [spec, setSpec] = useState<Record<number, string[]>>({});
  const [maxTeachers, setMaxTeachers] = useState(4);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"assign" | "crops" | "progress" | "arbitration">("assign");

  const loadDetail = useCallback(async () => {
    try {
      const [d, t, p, a, c] = await Promise.all([
        flowGetBatch(batchId),
        flowListTeachers(batchId),
        flowProgress(batchId),
        flowArbitrations(batchId),
        flowBatchCrops(batchId),
      ]);
      setBatch(d.batch);
      setQuestions(d.questions || []);
      setTeachers(t.items || []);
      setProgress(p.items || []);
      setArbitrations(a.items || []);
      setCrops(c.questions || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    }
  }, [batchId]);

  useEffect(() => {
    void loadDetail();
  }, [loadDetail]);

  const doCut = async () => {
    setBusy("cut");
    setError("");
    try {
      await flowCutBatch(batchId);
      await pollCut();
    } catch (e) {
      setError(e instanceof Error ? e.message : "切割失败");
    } finally {
      setBusy("");
      await loadDetail();
    }
  };

  const pollCut = useCallback(async () => {
    for (let i = 0; i < 300; i++) {
      const s = await flowCutStatus(batchId);
      if (s.status === "done" || s.status === "error") return s;
      await new Promise((r) => setTimeout(r, 2000));
    }
    return null;
  }, [batchId]);

  const doAssign = async (mode: "random" | "specified") => {
    setBusy("assign");
    setError("");
    try {
      if (mode === "random") {
        await flowAssign(batchId, { mode: "random", max_teachers: maxTeachers });
      } else {
        const assignments = questions.map((q) => ({
          question_no: q.question_no,
          assignee_ids: spec[q.question_no] || [],
        }));
        await flowAssign(batchId, { mode: "specified", assignments });
      }
      await loadDetail();
    } catch (e) {
      setError(e instanceof Error ? e.message : "分配失败");
    } finally {
      setBusy("");
    }
  };

  const mode = batch?.review_mode || "single";

  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <h2 className="font-semibold text-foreground">{batch?.name}</h2>
          <div className="text-xs text-muted-foreground">
            状态 {batch?.status} · {mode === "double" ? "双评" : "单评"} · {batch?.total_papers} 份
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={doCut} disabled={busy === "cut"}>
            {busy === "cut" ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Scissors className="mr-1 h-4 w-4" />}
            切割归类
          </Button>
          <Button variant="outline" size="sm" onClick={loadDetail}>
            <RefreshCw className="mr-1 h-4 w-4" /> 刷新
          </Button>
        </div>
      </div>

      <div className="flex gap-1 border-b border-border px-4 pt-2">
        {(["assign", "crops", "progress", "arbitration"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={cn(
              "rounded-t-lg px-4 py-2 text-sm font-medium",
              tab === t ? "border-b-2 border-primary text-primary" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {t === "assign" ? "分配" : t === "crops" ? "切割预览" : t === "progress" ? "进度看板" : `仲裁（${arbitrations.length}）`}
          </button>
        ))}
      </div>

      {error && <div className="px-4 pt-3 text-xs text-destructive">{error}</div>}

      <div className="p-4">
        {tab === "assign" && (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <span className="text-sm text-muted-foreground">随机分配教师数（≤10）</span>
              <Input
                type="number"
                value={String(maxTeachers)}
                onChange={(e) => setMaxTeachers(Math.max(1, Math.min(10, Number(e.target.value) || 1)))}
                className="w-20"
              />
              <Button onClick={() => doAssign("random")} disabled={busy === "assign"}>
                <Users className="mr-1 h-4 w-4" /> 随机分配
              </Button>
            </div>

            <div className="rounded-lg border border-border">
              <div className="border-b border-border bg-muted/50 px-3 py-2 text-xs font-medium text-muted-foreground">指定分配（每题选老师）</div>
              <div className="divide-y divide-border">
                {questions.map((q) => {
                  const need = (q.review_mode || mode) === "double" ? 2 : 1;
                  const cur = spec[q.question_no] || [];
                  const setTeacher = (idx: number, val: string) => {
                    const next = [...cur];
                    next[idx] = val;
                    while (next.length < need) next.push("");
                    setSpec((s) => ({ ...s, [q.question_no]: next.slice(0, need) }));
                  };
                  return (
                    <div key={q.id} className="flex items-center gap-3 px-3 py-2 text-sm">
                      <span className="w-24 shrink-0">{q.display_label}</span>
                      <span className="w-16 text-xs text-muted-foreground">满分 {q.max_score}</span>
                      {Array.from({ length: need }).map((_, idx) => (
                        <select
                          key={idx}
                          value={cur[idx] || ""}
                          onChange={(e) => setTeacher(idx, e.target.value)}
                          className="rounded-lg border border-border bg-background px-2 py-1.5 text-sm"
                        >
                          <option value="">{need === 2 ? (idx === 0 ? "一评老师" : "二评老师") : "选择老师"}</option>
                          {teachers.map((t) => (
                            <option key={t.user_id} value={t.user_id}>{t.display_name}</option>
                          ))}
                        </select>
                      ))}
                    </div>
                  );
                })}
              </div>
            </div>
            <Button onClick={() => doAssign("specified")} disabled={busy === "assign"}>
              {busy === "assign" ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Check className="mr-1 h-4 w-4" />}
              提交指定分配
            </Button>
          </div>
        )}

        {tab === "crops" && (
          <div className="space-y-3">
            <div className="text-xs text-muted-foreground">
              共 {crops.length} 题、{crops.reduce((s, q) => s + q.items.length, 0)} 张裁图
            </div>
            {crops.map((q) => (
              <CropQuestionSection key={q.id} question={q} />
            ))}
            {!crops.length && (
              <div className="py-8 text-center text-muted-foreground">暂无裁图，请先「切割归类」</div>
            )}
          </div>
        )}

        {tab === "progress" && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr className="border-b border-border">
                  <th className="px-3 py-2">老师</th>
                  <th className="px-3 py-2">题目</th>
                  <th className="px-3 py-2">角色</th>
                  <th className="px-3 py-2">进度</th>
                  <th className="px-3 py-2">速度</th>
                </tr>
              </thead>
              <tbody>
                {progress.map((p) => (
                  <tr key={p.assignment_id} className="border-b border-border">
                    <td className="px-3 py-2">{p.teacher_name}</td>
                    <td className="px-3 py-2">{p.display_label}</td>
                    <td className="px-3 py-2 text-xs">{p.role}</td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <Progress value={Math.round(p.progress * 100)} className="h-2 w-28" />
                        <span className="text-xs text-muted-foreground">{p.graded_items}/{p.total_items}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">{p.speed_per_min} 张/分</td>
                  </tr>
                ))}
                {!progress.length && <tr><td colSpan={5} className="px-3 py-6 text-center text-muted-foreground">暂无分配</td></tr>}
              </tbody>
            </table>
          </div>
        )}

        {tab === "arbitration" && (
          <div className="space-y-3">
            {arbitrations.length === 0 ? (
              <div className="py-8 text-center text-muted-foreground">暂无待仲裁条目</div>
            ) : (
              arbitrations.map((a) => <ArbitrationCard key={a.item_id} item={a} onDone={loadDetail} />)
            )}
          </div>
        )}
      </div>
    </div>
  );
}

type ArbitrationItem = Awaited<ReturnType<typeof flowArbitrations>>["items"][number];

function ArbitrationCard({ item, onDone }: { item: ArbitrationItem; onDone: () => void }) {
  const [score, setScore] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const save = async () => {
    const s = Number(score);
    if (Number.isNaN(s)) {
      setError("请输入最终分数");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await flowArbitrate(item.item_id, { final_score: s });
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "仲裁失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-lg border border-border p-4">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-sm font-medium">
          第{item.question_no}题 · {item.student_name || "-"}{item.student_number ? `（${item.student_number}）` : ""}
        </div>
        <div className="flex items-center gap-3 text-sm">
          {item.reviews.map((r) => (
            <span key={r.review_id} className="text-muted-foreground">
              {r.round === 1 ? "一评" : "二评"}: <span className="font-semibold text-foreground">{r.score}</span>（{STATUS_LABEL[r.status] || r.status}）
            </span>
          ))}
        </div>
      </div>
      <div className="flex gap-4">
        <div className="min-w-0 flex-1">
          {item.crop_url ? (
            <FreeMarkCanvas imageUrl={item.crop_url} marks={item.reviews.flatMap((r) => r.marks || [])} activeType="correct" readOnly />
          ) : (
            <div className="flex h-32 items-center justify-center text-muted-foreground">无图</div>
          )}
        </div>
        <div className="flex w-[180px] shrink-0 flex-col gap-2">
          <Input type="number" inputMode="decimal" value={score} onChange={(e) => setScore(e.target.value)} placeholder="最终分数" />
          {error && <div className="text-xs text-destructive">{error}</div>}
          <Button onClick={save} disabled={saving}>
            {saving ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Scale className="mr-1 h-4 w-4" />}
            仲裁定分
          </Button>
        </div>
      </div>
    </div>
  );
}

function CropQuestionSection({ question }: { question: FlowCropQuestion }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-border">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-muted/40"
      >
        <span className="text-sm font-medium">{question.display_label}</span>
        <span className="text-xs text-muted-foreground">
          {question.items.length} 张{open ? " ▲" : " ▼"}
        </span>
      </button>
      {open && (
        <div className="grid grid-cols-3 gap-2 border-t border-border p-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8">
          {question.items.map((it) => (
            <figure key={it.item_id} className="overflow-hidden rounded border border-border bg-muted/30">
              {it.crop_url ? (
                <img
                  src={it.crop_url}
                  alt={it.student_name || it.paper_name}
                  loading="lazy"
                  className="aspect-[4/3] w-full object-contain"
                />
              ) : (
                <div className="flex aspect-[4/3] items-center justify-center text-xs text-muted-foreground">无图</div>
              )}
              <figcaption className="truncate border-t border-border bg-muted/40 px-1.5 py-1 text-center text-[11px] text-muted-foreground">
                {it.student_name || it.paper_name}
              </figcaption>
            </figure>
          ))}
        </div>
      )}
    </div>
  );
}
