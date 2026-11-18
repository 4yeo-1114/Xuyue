import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Loader2,
  FileText,
  Printer,
  Download,
  Layers,
  Eye,
  Settings2,
  Plus,
  X,
} from "lucide-react";
import {
  tieredCompose,
  getTieredComposeResult,
  type TieredComposeResult,
  type TieredPaperItem,
  type TieredComposeRequirement,
} from "@/services/tieredComposeApi";
import {
  TIER_ORDER,
  TIER_LABELS,
  tierStrategyKey,
  type TierName,
} from "./tieredCompose";
import {
  QUESTION_TYPE_OPTIONS,
  splitTopics,
  typeLabelOf,
} from "@/lib/aiQuestionTypes";

/** 常用学科（与 ExamGenPage EXAM_SUBJECTS 对齐的子集，够选卷用） */
const SUBJECT_OPTIONS = [
  "语文",
  "数学",
  "英语",
  "科学",
  "物理",
  "化学",
  "生物",
  "政治",
  "历史",
  "地理",
];

/** 题源：ai=AI 生成（可选题型/知识点）；bank=题库抽题 */
export type TieredQuestionSource = "ai" | "bank";

/** 缺省题型模板：每层合计 10 题（与 count 缺省一致） */
const DEFAULT_REQS: TieredComposeRequirement[] = [
  { type: "choice", count: 4, score: 3 },
  { type: "fill", count: 2, score: 2 },
  { type: "judge", count: 2, score: 1 },
  { type: "short_answer", count: 2, score: 5 },
];

interface TieredComposePanelProps {
  classId: string;
  subject: string;
  /** 跳到组卷页（可选；ExamGenPage 自身不传） */
  onOpenInExamGen?: (paperId: string) => void;
}

function difficultyLine(
  t: (k: string, p?: Record<string, unknown>) => string,
  d?: { easy: number; medium: number; hard: number },
): string {
  if (!d) return "";
  return t("smartGen.tiered.difficulty", {
    easy: d.easy,
    medium: d.medium,
    hard: d.hard,
  });
}

/** 下载试卷为 .txt（题干+选项+答案），不依赖 PDF 库 */
function downloadPaperTxt(paper: TieredPaperItem) {
  const lines: string[] = [paper.title, ""];
  (paper.questions || []).forEach((q, i) => {
    // 题干两段：stem=背景材料（可能空）、content=具体问题（AI 出题约定），拼全才不缺题干
    lines.push(`${i + 1}. ${[q.stem, q.content].filter(Boolean).join("\n")}`);
    // 有配图的题标注位置（txt 放不下真图；打印/预览/PDF 里有真图）
    if (q.figure_img) lines.push("   【图】");
    // 选项横排一行（A. x  B. x  C. x  D. x），跟卷面一致
    if ((q.options || []).length) {
      lines.push(
        `   ${(q.options || [])
          .map((opt, oi) => `${String.fromCharCode(65 + oi)}. ${opt}`)
          .join("    ")}`,
      );
    }
    if (q.answer) lines.push(`   【答案】${q.answer}`);
    if (q.analysis) lines.push(`   【解析】${q.analysis}`);
    lines.push("");
  });
  const blob = new Blob([lines.join("\n")], {
    type: "text/plain;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${paper.title || "分层卷"}.txt`;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * 分层组卷面板：生成按钮 + A/B/C 三份卷卡片（查看/打印/下载）。
 * LayeredPushPage 与 ExamGenPage 共用。
 */
export function TieredComposePanel({
  classId,
  subject,
  onOpenInExamGen,
}: TieredComposePanelProps) {
  const { t } = useLocale();
  const [subj, setSubj] = useState(subject);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<TieredComposeResult | null>(null);
  const [preview, setPreview] = useState<TieredPaperItem | null>(null);
  // 题源：ai=AI 生成（默认，仿 AI 组卷可选题型/知识点）；bank=题库
  const [source, setSource] = useState<TieredQuestionSource>("ai");
  const [showAiOpts, setShowAiOpts] = useState(false);
  const [topicText, setTopicText] = useState("");
  const [reqs, setReqs] = useState<TieredComposeRequirement[]>(DEFAULT_REQS);

  const papers = result?.papers ?? [];
  const typeLabel = typeLabelOf;

  const runCompose = useCallback(async () => {
    if (!classId) {
      toast.error(t("smartGen.tiered.pickClass"));
      return;
    }
    const useSubj = subj || subject;
    if (!useSubj) {
      toast.error(t("smartGen.tiered.pickSubject"));
      return;
    }
    if (source === "bank") {
      toast.error(t("smartGen.aiSource.bankUnavailable"));
      return;
    }
    setBusy(true);
    try {
      const validReqs = reqs.filter((r) => (r.count || 0) > 0);
      const res = await tieredCompose({
        class_id: classId,
        subject: useSubj,
        source: "ai",
        topics: splitTopics(topicText),
        requirements: validReqs.length ? validReqs : undefined,
        count: validReqs.reduce((s, r) => s + (r.count || 0), 0) || undefined,
      });
      setResult(res);
      toast.success(t("smartGen.tiered.success"));
    } catch (e: unknown) {
      const msg =
        e && typeof e === "object" && "message" in e
          ? String((e as { message?: unknown }).message ?? "")
          : "";
      if (msg.includes("分层")) {
        toast.error(t("smartGen.tiered.noTiers"));
      } else {
        toast.error(t("smartGen.tiered.failed"), { description: msg });
      }
    } finally {
      setBusy(false);
    }
  }, [classId, subj, subject, source, topicText, reqs, t]);

  // 初次挂载拉最近一批（有则展示，无则空态）
  useEffect(() => {
    if (!classId) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await getTieredComposeResult({
          class_id: classId,
          subject: subj || subject,
        });
        if (!cancelled && res?.papers?.length) setResult(res);
      } catch {
        // 静默：空态即可
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [classId, subj, subject]);

  const handlePrint = useCallback((paper: TieredPaperItem) => {
    setPreview(paper);
    // 等预览弹窗渲染后再 print
    setTimeout(() => window.print(), 120);
  }, []);

  return (
    <Card className="border-border/50">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Layers className="h-4 w-4" />
            </div>
            <div>
              <CardTitle className="text-base">
                {t("smartGen.tiered.title")}
              </CardTitle>
              <p className="text-xs text-muted-foreground">
                {t("smartGen.tiered.subtitle")}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Select value={subj} onValueChange={setSubj}>
              <SelectTrigger className="w-[120px] h-8 text-xs">
                <SelectValue placeholder={t("smartGen.tiered.pickSubject")} />
              </SelectTrigger>
              <SelectContent>
                {SUBJECT_OPTIONS.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={source}
              onValueChange={(v) => setSource(v as TieredQuestionSource)}
            >
              <SelectTrigger className="w-[110px] h-8 text-xs">
                <SelectValue placeholder={t("smartGen.aiSource.label")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ai">{t("smartGen.aiSource.ai")}</SelectItem>
                <SelectItem value="bank">{t("smartGen.aiSource.bank")}</SelectItem>
              </SelectContent>
            </Select>
            {source === "ai" && (
              <Button
                variant="outline"
                size="sm"
                className="h-8 gap-1 text-xs"
                onClick={() => setShowAiOpts((v) => !v)}
              >
                <Settings2 className="h-3.5 w-3.5" />
                {t("smartGen.aiSource.settings")}
              </Button>
            )}
            <Button
              size="sm"
              className="gap-1.5 text-xs"
              disabled={busy || !classId || source === "bank"}
              onClick={runCompose}
            >
              {busy ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Layers className="h-3.5 w-3.5" />
              )}
              {busy ? t("smartGen.tiered.generating") : t("smartGen.tiered.generate")}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {source === "bank" ? (
          <div className="rounded-lg border border-dashed border-amber-500/50 bg-amber-500/5 px-4 py-6 text-center text-xs text-amber-600">
            {t("smartGen.aiSource.bankUnavailable")}
            <div className="mt-1 text-muted-foreground">
              {t("smartGen.aiSource.bankHint")}
            </div>
          </div>
        ) : showAiOpts ? (
          <div className="rounded-lg border border-border/50 bg-muted/20 p-3 space-y-2">
            <div className="flex items-center gap-2">
              <span className="w-14 shrink-0 text-xs font-medium">
                {t("smartGen.aiSource.topicsLabel")}
              </span>
              <Input
                className="h-8 text-xs"
                placeholder={t("smartGen.aiSource.topicsPlaceholder")}
                value={topicText}
                onChange={(e) => setTopicText(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium">
                  {t("smartGen.aiSource.typesLabel")}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 gap-1 px-2 text-xs"
                  onClick={() =>
                    setReqs((rs) => [
                      ...rs,
                      { type: "short_answer", count: 1, score: 5 },
                    ])
                  }
                >
                  <Plus className="h-3 w-3" />
                  {t("smartGen.aiSource.addType")}
                </Button>
              </div>
              {reqs.map((r, i) => (
                <div key={i} className="flex items-center gap-2">
                  <Select
                    value={r.type}
                    onValueChange={(v) =>
                      setReqs((rs) =>
                        rs.map((x, xi) => (xi === i ? { ...x, type: v } : x)),
                      )
                    }
                  >
                    <SelectTrigger className="h-8 w-[120px] text-xs">
                      <SelectValue>{typeLabel(r.type)}</SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {QUESTION_TYPE_OPTIONS.map((o) => (
                        <SelectItem key={o.value} value={o.value}>
                          {o.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Input
                    type="number"
                    min={1}
                    max={50}
                    className="h-8 w-[72px] text-xs"
                    value={r.count}
                    onChange={(e) =>
                      setReqs((rs) =>
                        rs.map((x, xi) =>
                          xi === i
                            ? { ...x, count: Math.max(1, Number(e.target.value) || 1) }
                            : x,
                        ),
                      )
                    }
                  />
                  <span className="text-xs text-muted-foreground">
                    {t("smartGen.aiSource.countLabel")}
                  </span>
                  <Input
                    type="number"
                    min={0.5}
                    max={100}
                    step={0.5}
                    className="h-8 w-[72px] text-xs"
                    value={r.score}
                    onChange={(e) =>
                      setReqs((rs) =>
                        rs.map((x, xi) =>
                          xi === i
                            ? { ...x, score: Number(e.target.value) || 1 }
                            : x,
                        ),
                      )
                    }
                  />
                  <span className="text-xs text-muted-foreground">
                    {t("smartGen.aiSource.scoreLabel")}
                  </span>
                  {reqs.length > 1 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0 text-muted-foreground"
                      onClick={() =>
                        setReqs((rs) => rs.filter((_, xi) => xi !== i))
                      }
                    >
                      <X className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              {t("smartGen.aiSource.aiHint")}
            </p>
          </div>
        ) : null}
        {busy && papers.length === 0 ? (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t("smartGen.tiered.generating")}
          </div>
        ) : papers.length === 0 ? (
          <div className="rounded-lg border border-dashed px-4 py-8 text-center text-xs text-muted-foreground">
            {t("smartGen.tiered.empty")}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            {TIER_ORDER.map((tier: TierName) => {
              const paper = papers.find((p) => p.tier === tier);
              if (!paper) return null;
              return (
                <div
                  key={paper.paper_id}
                  className="rounded-xl border border-border/50 bg-card p-3 space-y-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <Badge variant="outline" className="text-xs">
                      {TIER_LABELS[tier]}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {t("smartGen.tiered.paperCount", { count: paper.count })}
                    </span>
                  </div>
                  <div className="text-sm font-medium leading-snug line-clamp-2">
                    {paper.title}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {difficultyLine(t, paper.difficulty)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {t(tierStrategyKey(tier))}
                  </p>
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 gap-1 px-2 text-xs"
                      onClick={() => setPreview(paper)}
                    >
                      <Eye className="h-3 w-3" />
                      {t("smartGen.tiered.view")}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 gap-1 px-2 text-xs"
                      onClick={() => handlePrint(paper)}
                    >
                      <Printer className="h-3 w-3" />
                      {t("smartGen.tiered.print")}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 gap-1 px-2 text-xs"
                      onClick={() => downloadPaperTxt(paper)}
                    >
                      <Download className="h-3 w-3" />
                      {t("smartGen.tiered.download")}
                    </Button>
                    {onOpenInExamGen && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 gap-1 px-2 text-xs"
                        onClick={() => onOpenInExamGen(paper.paper_id)}
                      >
                        <FileText className="h-3 w-3" />
                        {t("smartGen.tiered.openInExamGen")}
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>

      {/* 预览/打印弹窗 */}
      <Dialog open={!!preview} onOpenChange={(o) => !o && setPreview(null)}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto print:max-w-none print:max-h-none print:shadow-none">
          <DialogHeader>
            <DialogTitle className="print:block">
              {preview?.title || t("smartGen.tiered.previewTitle")}
            </DialogTitle>
          </DialogHeader>
          {preview && (
            <div className="space-y-3 text-sm">
              <p className="text-xs text-muted-foreground">
                {difficultyLine(t, preview.difficulty)} ·{" "}
                {t("smartGen.tiered.paperCount", { count: preview.count })}
              </p>
              {(preview.questions || []).map((q, i) => (
                <div key={q.id || i} className="rounded-lg border p-3 space-y-1">
                  {/* stem=背景材料、content=具体问题（AI 出题时 stem 常为空）——两段都画，缺一就丢题干 */}
                  <div className="font-medium whitespace-pre-wrap">
                    {i + 1}. {[q.stem, q.content].filter(Boolean).join("\n")}
                  </div>
                  {/* 配图（后端按 figure 规格画的真图）：贴题干下、选项前 */}
                  {q.figure_img && (
                    <div className="pl-4 py-1 break-inside-avoid print:break-inside-avoid">
                      <img
                        src={q.figure_img}
                        alt="题图"
                        className="max-w-[320px] w-full h-auto"
                      />
                    </div>
                  )}
                  {/* 选项横排（flex-wrap 一排一排排，长选项自动换行），不竖着叠 */}
                  {(q.options || []).length > 0 && (
                    <div className="flex flex-wrap gap-x-6 gap-y-1 pl-4 text-muted-foreground">
                      {(q.options || []).map((opt, oi) => (
                        <div key={oi} className="whitespace-pre-wrap">
                          {String.fromCharCode(65 + oi)}. {opt}
                        </div>
                      ))}
                    </div>
                  )}
                  {q.answer && (
                    <div className="pl-4 text-xs text-emerald-600">
                      【答案】{q.answer}
                    </div>
                  )}
                  {q.analysis && (
                    <div className="pl-4 text-xs text-muted-foreground">
                      【解析】{q.analysis}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          <DialogFooter className="print:hidden">
            <Button variant="outline" size="sm" onClick={() => setPreview(null)}>
              {t("smartGen.tiered.close")}
            </Button>
            {preview && (
              <Button
                size="sm"
                className="gap-1"
                onClick={() => downloadPaperTxt(preview)}
              >
                <Download className="h-3.5 w-3.5" />
                {t("smartGen.tiered.download")}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
