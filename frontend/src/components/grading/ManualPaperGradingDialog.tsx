import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Circle, Eye, Loader2, Minus, Plus, Printer, Save } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { useLocale } from "@/contexts/LocaleContext";
import {
  gradingImageUrl,
  type ManualSlotDecision,
  type ManualSlotStatus,
} from "@/services/gradingApi";

type ManualBlock = {
  slot_id: string;
  title?: string;
  label?: string;
  index?: number;
  sub_index?: number;
  bbox: [number, number, number, number];
  max_score: number;
  status?: ManualSlotStatus;
  score?: number | null;
};

export type ManualAnnotations = {
  questionNotes: Record<string, string>;
  paperNote: string;
};

export type ManualPaperDirection = "save" | "prev" | "next";

type Props = {
  open: boolean;
  filename: string;
  imageUrl: string;
  result: string;
  answerKey?: Record<string, string> | null;
  saving?: boolean;
  otherPagesScore?: number;
  hasPrev?: boolean;
  hasNext?: boolean;
  printing?: boolean;
  initialQuestionNotes?: Record<string, string>;
  initialPaperNote?: string;
  onOpenChange: (open: boolean) => void;
  onSave: (decisions: Record<string, ManualSlotDecision>, direction: ManualPaperDirection, annotations: ManualAnnotations) => Promise<void> | void;
  onAutoSave?: (decisions: Record<string, ManualSlotDecision>, annotations: ManualAnnotations) => Promise<void> | void;
  onPrintPreview?: (decisions: Record<string, ManualSlotDecision>, annotations: ManualAnnotations) => Promise<string | null> | string | null;
  onPrint?: (decisions: Record<string, ManualSlotDecision>, annotations: ManualAnnotations) => Promise<void> | void;
};

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));
const MANUAL_MARK_DISPLAY_SIZE = 38;
const MANUAL_MARK_STROKE_WIDTH = 3.5;
const MANUAL_SCORE_DISPLAY_SIZE = 58;
const SMART_MARK_COLOR = "#FF0000";
const SMART_MARK_FONT_FAMILY = '"Microsoft YaHei", "Noto Sans CJK SC", sans-serif';

function parsePayload(result: string): { blocks: ManualBlock[]; imageSize: [number, number] } {
  try {
    const parsed = JSON.parse(result || "{}");
    const rawBlocks = Array.isArray(parsed.blocks) ? parsed.blocks : [];
    const blocks = rawBlocks
      .filter((item: unknown): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
      .map((item, index: number) => ({
        ...item,
        slot_id: String(item.slot_id || `slot-${index + 1}`),
        bbox: Array.isArray(item.bbox) && item.bbox.length >= 4 ? item.bbox.slice(0, 4).map(Number) : [0, 0, 1, 1],
        max_score: Number(item.max_score || 1),
        status: String(item.status || "ungraded") as ManualSlotStatus,
        score: item.score == null ? null : Number(item.score),
      })) as ManualBlock[];
    const size = Array.isArray(parsed.image_size) && parsed.image_size.length >= 2
      ? [Math.max(1, Number(parsed.image_size[0])), Math.max(1, Number(parsed.image_size[1]))] as [number, number]
      : [1, 1] as [number, number];
    return { blocks, imageSize: size };
  } catch {
    return { blocks: [], imageSize: [1, 1] };
  }
}

function decisionScore(decision: ManualSlotDecision | undefined, maxScore: number): number {
  if (!decision || decision.status === "ungraded") return 0;
  if (decision.status === "correct") return maxScore;
  if (decision.status === "partial") return Number(decision.score || 0);
  return 0;
}

/** 把作答区归并到「题号」：优先 index，其次 label 的数字前缀（如 "3_2" → "3"），最后退回 slot_id。 */
function questionKeyOf(block: ManualBlock): string {
  if (block.index != null) return String(block.index);
  const labelMatch = String(block.label || "").match(/^(\d+)/);
  if (labelMatch) return labelMatch[1];
  return block.slot_id;
}

/** 从标准答案里取当前作答区对应的参考答案：优先 label「N_M」，其次 index_sub_index。 */
function answerKeyFor(block: ManualBlock, answerKey: Record<string, string> | null | undefined): string | undefined {
  if (!answerKey) return undefined;
  const label = String(block.label || "").trim();
  if (label && /^\d+_\d+$/.test(label)) {
    const hit = answerKey[label];
    if (hit != null) return hit;
  }
  if (block.index != null) {
    const sub = block.sub_index != null ? String(block.sub_index) : "1";
    const hit = answerKey[`${block.index}_${sub}`];
    if (hit != null) return hit;
    if (sub !== "1") {
      const first = answerKey[`${block.index}_1`];
      if (first != null) return first;
    }
  }
  return undefined;
}

/** 生成可点击的打分值序列：整数满分（如 5）→ [0,1,2,3,4,5]；带 0.5（如 2.5）→ [0,0.5,1,…,2.5]；步数过多时退回 [0, 满分]。 */
function scoreSteps(maxScore: number): number[] {
  const max = Math.max(0, Number(maxScore) || 0);
  if (max <= 0) return [0];
  const step = Number.isInteger(max) ? 1 : 0.5;
  const steps: number[] = [];
  for (let v = 0; v <= max + 1e-9; v += step) {
    steps.push(Number(v.toFixed(1)));
  }
  if (steps[steps.length - 1] !== max) steps.push(max);
  return steps.length > 12 ? [0, max] : steps;
}

export function ManualPaperGradingDialog({
  open,
  filename,
  imageUrl,
  result,
  answerKey,
  saving = false,
  otherPagesScore = 0,
  hasPrev = false,
  hasNext = false,
  printing = false,
  initialQuestionNotes,
  initialPaperNote,
  onOpenChange,
  onSave,
  onAutoSave,
  onPrintPreview,
  onPrint,
}: Props) {
  const { t } = useLocale();
  const payload = useMemo(() => parsePayload(result), [result]);
  const [decisions, setDecisions] = useState<Record<string, ManualSlotDecision>>({});
  const [selectedSlotId, setSelectedSlotId] = useState<string | null>(null);
  const [paperZoom, setPaperZoom] = useState(1);
  const [printPreviewUrl, setPrintPreviewUrl] = useState<string | null>(null);
  const [preparingPrintPreview, setPreparingPrintPreview] = useState(false);
  const [questionNotes, setQuestionNotes] = useState<Record<string, string>>({});
  const [paperNote, setPaperNote] = useState("");
  const decisionsRef = useRef<Record<string, ManualSlotDecision>>({});
  const questionNotesRef = useRef<Record<string, string>>({});
  const paperNoteRef = useRef("");
  const wasOpenRef = useRef(false);
  const initializedFilenameRef = useRef<string | null>(null);
  const onAutoSaveRef = useRef(onAutoSave);
  const pendingAutoSaveRef = useRef<{ decisions: Record<string, ManualSlotDecision>; annotations: ManualAnnotations } | null>(null);
  const autoSavePromiseRef = useRef<Promise<void> | null>(null);

  useEffect(() => {
    onAutoSaveRef.current = onAutoSave;
  }, [onAutoSave]);

  const buildSnapshot = useCallback(
    (): { decisions: Record<string, ManualSlotDecision>; annotations: ManualAnnotations } => ({
      decisions: decisionsRef.current,
      annotations: {
        questionNotes: questionNotesRef.current,
        paperNote: paperNoteRef.current,
      },
    }),
    [],
  );

  const flushAutoSave = useCallback(async () => {
    while (true) {
      const inFlight = autoSavePromiseRef.current;
      if (inFlight) {
        await inFlight;
        continue;
      }
      const pending = pendingAutoSaveRef.current;
      const save = onAutoSaveRef.current;
      if (!pending || !save) return;
      pendingAutoSaveRef.current = null;
      const savePromise = Promise.resolve(save(pending.decisions, pending.annotations)).catch(() => undefined);
      autoSavePromiseRef.current = savePromise;
      await savePromise;
      autoSavePromiseRef.current = null;
    }
  }, []);

  const scheduleAutoSave = useCallback(() => {
    if (!onAutoSaveRef.current) return;
    pendingAutoSaveRef.current = buildSnapshot();
    void flushAutoSave();
  }, [buildSnapshot, flushAutoSave]);

  const updateDecisions = useCallback((updater: (current: Record<string, ManualSlotDecision>) => Record<string, ManualSlotDecision>) => {
    const next = updater(decisionsRef.current);
    decisionsRef.current = next;
    setDecisions(next);
    scheduleAutoSave();
  }, [scheduleAutoSave]);

  const updateQuestionNote = useCallback((key: string, value: string) => {
    const next = { ...questionNotesRef.current, [key]: value };
    questionNotesRef.current = next;
    setQuestionNotes(next);
    scheduleAutoSave();
  }, [scheduleAutoSave]);

  const updatePaperNote = useCallback((value: string) => {
    paperNoteRef.current = value;
    setPaperNote(value);
    scheduleAutoSave();
  }, [scheduleAutoSave]);

  useEffect(() => {
    const shouldInitialize = open && (!wasOpenRef.current || initializedFilenameRef.current !== filename);
    if (shouldInitialize) {
      const initial: Record<string, ManualSlotDecision> = {};
      payload.blocks.forEach((block) => {
        initial[block.slot_id] = {
          status: block.status || "ungraded",
          score: block.score,
        };
      });
      decisionsRef.current = initial;
      setDecisions(initial);
      const notes: Record<string, string> = initialQuestionNotes ?? {};
      questionNotesRef.current = notes;
      setQuestionNotes(notes);
      paperNoteRef.current = initialPaperNote ?? "";
      setPaperNote(initialPaperNote ?? "");
      setSelectedSlotId(null);
      setPaperZoom(1);
      setPrintPreviewUrl(null);
      initializedFilenameRef.current = filename;
    }
    if (!open) initializedFilenameRef.current = null;
    wasOpenRef.current = open;
  }, [filename, initialPaperNote, initialQuestionNotes, open, payload]);

  const selectedBlock = payload.blocks.find((block) => block.slot_id === selectedSlotId) || null;
  const selectedDecision = selectedBlock ? decisions[selectedBlock.slot_id] : null;
  const selectedScore = selectedBlock
    ? selectedDecision?.status === "correct"
      ? selectedBlock.max_score
      : selectedDecision?.status === "partial"
        ? Number(selectedDecision?.score || 0)
        : 0
    : 0;
  const selectedIsUnanswered = selectedDecision?.status === "unanswered";
  const selectedReference = selectedBlock ? answerKeyFor(selectedBlock, answerKey) : undefined;
  const selectedSteps = selectedBlock ? scoreSteps(selectedBlock.max_score) : [];
  const basePaperWidth = useMemo(
    () => clamp(payload.imageSize[0], 1280, 1500),
    [payload.imageSize],
  );
  const basePaperHeight = useMemo(
    () => basePaperWidth * (payload.imageSize[1] / payload.imageSize[0]),
    [basePaperWidth, payload.imageSize],
  );
  const pageScore = payload.blocks.reduce(
    (sum, block) => sum + decisionScore(decisions[block.slot_id], block.max_score),
    0,
  );
  const maxScore = payload.blocks.reduce((sum, block) => sum + block.max_score, 0);
  const questionGroups = useMemo(() => {
    const groups: Record<string, ManualBlock[]> = {};
    for (const block of payload.blocks) {
      const key = questionKeyOf(block);
      (groups[key] ??= []).push(block);
    }
    return Object.entries(groups).map(([key, blocks]) => {
      const title = blocks[0]?.title;
      const label = title
        ? title.split("-")[0]
        : /^\d+$/.test(key)
          ? `第${key}题`
          : key;
      return { key, label, blocks };
    });
  }, [payload.blocks]);
  const completedCount = payload.blocks.filter((block) => decisions[block.slot_id]?.status !== "ungraded").length;
  const hasInvalidPartial = payload.blocks.some((block) => {
    const decision = decisions[block.slot_id];
    if (decision?.status !== "partial") return false;
    const score = Number(decision.score);
    return !Number.isFinite(score) || score < 0 || score > block.max_score;
  });
  const scoreMarkValue = Number(pageScore.toFixed(2)).toString();
  const scoreMarkLabel = t("grading.manual.scoreMark", { score: scoreMarkValue });
  const paperDisplayScale = basePaperWidth / payload.imageSize[0];
  const scoreMarkX = Math.max(32, payload.imageSize[0] * 0.035);
  const scoreMarkY = Math.max(96, payload.imageSize[1] * 0.12);
  const scoreMarkFontSize = MANUAL_SCORE_DISPLAY_SIZE / paperDisplayScale;
  const scoreMarkUnderlineStart = scoreMarkX + scoreMarkFontSize * 2.7;
  const scoreMarkUnderlineWidth = scoreMarkFontSize * Math.max(0.72, scoreMarkValue.length * 0.62);

  const setStatus = useCallback((block: ManualBlock, status: ManualSlotStatus) => {
    updateDecisions((current) => ({
      ...current,
      [block.slot_id]: {
        status,
        score: status === "correct"
          ? block.max_score
          : status === "wrong" || status === "unanswered"
            ? 0
            : status === "partial"
              ? current[block.slot_id]?.score ?? null
        : null,
      },
    }));
  }, [updateDecisions]);

  /** 按具体分值打分：满分→对，0→错，中间→半对。未作答仍走 setStatus(block,"unanswered")。 */
  const applyScore = useCallback((block: ManualBlock, value: number) => {
    const max = block.max_score;
    const v = clamp(Number(value) || 0, 0, max);
    updateDecisions((current) => ({
      ...current,
      [block.slot_id]: {
        status: v >= max ? "correct" : v <= 0 ? "wrong" : "partial",
        score: v,
      },
    }));
  }, [updateDecisions]);

  const handleSave = useCallback(async (direction: ManualPaperDirection) => {
    await flushAutoSave();
    await onSave(decisionsRef.current, direction, buildSnapshot().annotations);
  }, [buildSnapshot, flushAutoSave, onSave]);

  const handlePrintPreview = useCallback(async () => {
    if (printPreviewUrl) {
      setPrintPreviewUrl(null);
      return;
    }
    if (!onPrintPreview) return;
    setPreparingPrintPreview(true);
    try {
      await flushAutoSave();
      const url = await onPrintPreview(decisionsRef.current, buildSnapshot().annotations);
      if (url) {
        setSelectedSlotId(null);
        setPrintPreviewUrl(url);
      }
    } finally {
      setPreparingPrintPreview(false);
    }
  }, [buildSnapshot, flushAutoSave, onPrintPreview, printPreviewUrl]);

  const handlePrint = useCallback(async () => {
    if (!onPrint) return;
    await flushAutoSave();
    await onPrint(decisionsRef.current, buildSnapshot().annotations);
  }, [buildSnapshot, flushAutoSave, onPrint]);

  const selectNextSlot = useCallback(() => {
    if (!selectedSlotId || payload.blocks.length === 0) return;
    const currentIndex = payload.blocks.findIndex((block) => block.slot_id === selectedSlotId);
    if (currentIndex < 0 || currentIndex >= payload.blocks.length - 1) return;
    setSelectedSlotId(payload.blocks[currentIndex + 1].slot_id);
  }, [payload.blocks, selectedSlotId]);

  useEffect(() => {
    if (!open || !selectedBlock) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      if (target?.closest("input, textarea, select, [contenteditable='true']")) return;

      const statusByKey: Record<string, ManualSlotStatus> = {
        "1": "correct",
        "2": "wrong",
        "3": "unanswered",
        "4": "partial",
      };
      const status = statusByKey[event.key];
      if (status) {
        event.preventDefault();
        setStatus(selectedBlock, status);
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        selectNextSlot();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, selectNextSlot, selectedBlock, setStatus]);

  useEffect(() => {
    if (!open || printPreviewUrl) return;
    const handleNavKey = (event: KeyboardEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
      if (event.key === "ArrowLeft" && hasPrev) {
        event.preventDefault();
        void handleSave("prev");
      } else if (event.key === "ArrowRight" && hasNext) {
        event.preventDefault();
        void handleSave("next");
      }
    };
    window.addEventListener("keydown", handleNavKey);
    return () => window.removeEventListener("keydown", handleNavKey);
  }, [open, printPreviewUrl, hasPrev, hasNext, handleSave]);

  const renderMark = (block: ManualBlock) => {
    const decision = decisions[block.slot_id];
    if (!decision || decision.status === "ungraded") return null;
    const [x1, y1, x2, y2] = block.bbox;
    const size = MANUAL_MARK_DISPLAY_SIZE / paperDisplayScale;
    const x = Math.min(payload.imageSize[0] - size, x2 - size * 0.25);
    const y = Math.min(payload.imageSize[1] - size, Math.max(y1, y2 - size));
    const strokeWidth = MANUAL_MARK_STROKE_WIDTH / paperDisplayScale;
    if (decision.status === "unanswered") {
      const pad = Math.max(4, strokeWidth * 2);
      return (
        <ellipse
          data-manual-mark="unanswered"
          cx={(x1 + x2) / 2}
          cy={(y1 + y2) / 2}
          rx={Math.max(1, (x2 - x1) / 2 + pad)}
          ry={Math.max(1, (y2 - y1) / 2 + pad)}
          fill="none"
          stroke={SMART_MARK_COLOR}
          strokeWidth={strokeWidth}
        />
      );
    }
    if (decision.status === "partial") {
      return (
        <g data-manual-mark="partial">
          <text x={x} y={y + size * 0.82} fill={SMART_MARK_COLOR} fontSize={size} fontFamily={SMART_MARK_FONT_FAMILY}>√</text>
          <line
            x1={x + size * 0.28}
            y1={y + size * 0.43}
            x2={x + size * 0.62}
            y2={y + size * 0.52}
            stroke={SMART_MARK_COLOR}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
          />
        </g>
      );
    }
    return (
      <text x={x} y={y + size * 0.82} fill={SMART_MARK_COLOR} fontSize={size} fontFamily={SMART_MARK_FONT_FAMILY}>
        {decision.status === "correct" ? "√" : "×"}
      </text>
    );
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) void flushAutoSave();
        onOpenChange(nextOpen);
      }}
    >
      <DialogContent
        className="left-1/2 top-1/2 flex h-[96vh] w-[98vw] max-w-[1800px] -translate-x-1/2 -translate-y-1/2 flex-col gap-0 overflow-hidden p-0"
        onPointerDownCapture={(event) => {
          if (printPreviewUrl) return;
          if (!selectedSlotId) return;
          const target = event.target instanceof Element ? event.target : null;
          if (!target?.closest("[data-manual-grade-slot], [data-manual-grade-menu]")) {
            setSelectedSlotId(null);
          }
        }}
      >
        <DialogHeader className="shrink-0 border-b bg-slate-950 px-6 py-3 pr-14 text-left text-white">
          <div className="flex flex-wrap items-center gap-4">
            <div className="min-w-0 flex-1">
              <DialogTitle className="truncate text-lg text-white">{t("grading.manual.gradingTitle")}</DialogTitle>
              <DialogDescription className="truncate text-slate-300">{filename}</DialogDescription>
            </div>
            <div className="text-right text-sm">
              <div className="font-semibold text-white">{t("grading.manual.paperScore", { score: pageScore.toFixed(1), max: maxScore.toFixed(1) })}</div>
              <div className="text-xs text-slate-300">{t("grading.manual.gradedSlots", { done: completedCount, total: payload.blocks.length })}</div>
              <div className="text-xs text-teal-300">{t("grading.manual.boxScore", { score: (otherPagesScore + pageScore).toFixed(1) })}</div>
            </div>
            <div className="flex items-center gap-1 rounded-md border border-slate-700 bg-slate-900/70 p-1">
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8 text-white hover:bg-slate-700 hover:text-white"
                disabled={paperZoom <= 0.5}
                title={t("grading.layout.zoomOut")}
                aria-label={t("grading.layout.zoomOut")}
                onClick={() => setPaperZoom((current) => clamp(Number((current - 0.1).toFixed(2)), 0.5, 2.5))}
              >
                <Minus className="h-4 w-4" />
              </Button>
              <span className="w-12 text-center text-xs font-semibold tabular-nums text-slate-200">{Math.round(paperZoom * 100)}%</span>
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8 text-white hover:bg-slate-700 hover:text-white"
                disabled={paperZoom >= 2.5}
                title={t("grading.layout.zoomIn")}
                aria-label={t("grading.layout.zoomIn")}
                onClick={() => setPaperZoom((current) => clamp(Number((current + 0.1).toFixed(2)), 0.5, 2.5))}
              >
                <Plus className="h-4 w-4" />
              </Button>
            </div>
            <Button
              variant="outline"
              size="sm"
              disabled={saving || printing || preparingPrintPreview}
              onClick={() => void handlePrintPreview()}
              className="gap-1.5 border-slate-600 bg-slate-900/70 text-white hover:bg-slate-700 hover:text-white"
            >
              {preparingPrintPreview ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
              {printPreviewUrl ? t("grading.manual.returnToGrading") : t("grading.manual.printPreview")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={saving || printing || preparingPrintPreview || !onPrint}
              onClick={() => void handlePrint()}
              className="gap-1.5 border-slate-600 bg-slate-900/70 text-white hover:bg-slate-700 hover:text-white"
            >
              {printing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Printer className="h-4 w-4" />}
              {t("grading.manual.printPage")}
            </Button>
            <div className="flex items-center gap-1 rounded-md border border-slate-700 bg-slate-900/70 p-1">
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8 text-white hover:bg-slate-700 hover:text-white disabled:opacity-40"
                disabled={saving || !hasPrev}
                title={t("grading.manual.prevPaper")}
                aria-label={t("grading.manual.prevPaper")}
                onClick={() => void handleSave("prev")}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8 text-white hover:bg-slate-700 hover:text-white disabled:opacity-40"
                disabled={saving || !hasNext}
                title={t("grading.manual.nextPaper")}
                aria-label={t("grading.manual.nextPaper")}
                onClick={() => void handleSave("next")}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
            <Button variant="secondary" size="sm" disabled={saving || hasInvalidPartial} onClick={() => void handleSave("save")} className="gap-1.5">
              <Save className="h-4 w-4" />{t("grading.manual.save")}
            </Button>
          </div>
        </DialogHeader>

        <div className="flex min-h-0 flex-1 overflow-hidden">
          <div className="min-h-0 flex-1 overflow-auto overscroll-contain bg-slate-300 p-6">
            <div className="flex min-h-full w-max min-w-full justify-center pb-6">
            <div
              className="relative shrink-0 bg-white shadow-xl"
              style={{
                width: `${basePaperWidth * paperZoom}px`,
                height: `${basePaperHeight * paperZoom}px`,
              }}
            >
              <img src={gradingImageUrl(printPreviewUrl || imageUrl)} alt={filename} className="absolute inset-0 h-full w-full select-none object-fill" draggable={false} />
              {!printPreviewUrl && <svg viewBox={`0 0 ${payload.imageSize[0]} ${payload.imageSize[1]}`} className="absolute inset-0 h-full w-full">
                <g pointerEvents="none">
                  <text
                    x={scoreMarkX}
                    y={scoreMarkY}
                    fill="#dc2626"
                    fontSize={scoreMarkFontSize}
                    fontWeight="700"
                    fontFamily="cursive"
                  >
                    {scoreMarkLabel}
                  </text>
                  <path
                    d={`M ${scoreMarkUnderlineStart} ${scoreMarkY + scoreMarkFontSize * 0.18} H ${scoreMarkUnderlineStart + scoreMarkUnderlineWidth}`}
                    fill="none"
                    stroke="#dc2626"
                    strokeWidth={Math.max(2, scoreMarkFontSize * 0.055)}
                    strokeLinecap="round"
                  />
                </g>
                {payload.blocks.map((block) => {
                  const [x1, y1, x2, y2] = block.bbox;
                  const status = decisions[block.slot_id]?.status || "ungraded";
                  const color = status === "correct" ? "#059669" : status === "wrong" ? "#dc2626" : status === "unanswered" ? "#ea580c" : status === "partial" ? "#0284c7" : "#d97706";
                  return (
                    <g
                      key={block.slot_id}
                      data-manual-grade-slot
                      className="cursor-pointer"
                      onClick={() => setSelectedSlotId(block.slot_id)}
                    >
                      <rect
                        x={x1} y={y1} width={Math.max(1, x2 - x1)} height={Math.max(1, y2 - y1)}
                        fill={color} fillOpacity={selectedSlotId === block.slot_id ? 0.16 : 0.06}
                        stroke={color} strokeWidth={selectedSlotId === block.slot_id ? 6 : 3}
                        strokeDasharray={status === "ungraded" ? "14 8" : undefined}
                      />
                      {renderMark(block)}
                    </g>
                  );
                })}
              </svg>}
              </div>
            </div>
          </div>
          {!printPreviewUrl && (
            <div data-manual-grade-menu className="flex w-80 min-h-0 shrink-0 flex-col overflow-hidden border-l border-slate-300 bg-white">
              <div className="shrink-0 border-b border-slate-200 bg-slate-50 px-4 py-3">
                <div className="text-sm font-semibold">{t("grading.manual.scorePanel")}</div>
                {selectedBlock ? (
                  <div className="mt-2 space-y-3">
                    <div className="flex items-center justify-between gap-2 text-sm">
                      <span className="truncate font-medium text-slate-700">{selectedBlock.label || selectedBlock.title}</span>
                      <span className="shrink-0 text-xs text-slate-500">{t("grading.manual.fullScore", { score: selectedBlock.max_score })}</span>
                    </div>
                    <div className="rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-2">
                      <div className="text-xs text-emerald-800">
                        <span className="font-semibold">{t("grading.manual.referenceAnswer")}：</span>
                        <span className={cn("break-words font-medium", !selectedReference && "text-slate-400")}>
                          {selectedReference || t("grading.manual.noReference")}
                        </span>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedSteps.map((step) => {
                        const active = !selectedIsUnanswered && Math.abs(step - selectedScore) < 1e-9;
                        return (
                          <button
                            key={step}
                            type="button"
                            onClick={() => applyScore(selectedBlock, step)}
                            className={cn(
                              "h-9 min-w-[2.5rem] rounded-md border text-sm font-semibold tabular-nums transition-colors",
                              active
                                ? step >= selectedBlock.max_score
                                  ? "border-emerald-600 bg-emerald-600 text-white"
                                  : step <= 0
                                    ? "border-red-600 bg-red-600 text-white"
                                    : "border-blue-600 bg-blue-600 text-white"
                                : "border-slate-300 bg-white text-slate-700 hover:border-slate-400 hover:bg-slate-100",
                            )}
                          >
                            {step}
                          </button>
                        );
                      })}
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        type="button"
                        size="sm"
                        variant={selectedIsUnanswered ? "secondary" : "outline"}
                        className="h-9 shrink-0 gap-1"
                        onClick={() => setStatus(selectedBlock, selectedIsUnanswered ? "ungraded" : "unanswered")}
                      >
                        <Circle className="h-3.5 w-3.5" />
                        {t("grading.manual.unanswered")}
                      </Button>
                      <Input
                        type="number"
                        min="0"
                        max={selectedBlock.max_score}
                        step="0.5"
                        className="h-9 flex-1 text-sm"
                        value={selectedIsUnanswered ? "" : (selectedDecision?.score ?? "")}
                        placeholder={t("grading.manual.scoreInputPlaceholder", { max: selectedBlock.max_score })}
                        onChange={(event) => {
                          const raw = event.target.value;
                          if (raw === "") {
                            setStatus(selectedBlock, "ungraded");
                            return;
                          }
                          const value = Number(raw);
                          if (!Number.isFinite(value)) return;
                          applyScore(selectedBlock, value);
                        }}
                      />
                    </div>
                  </div>
                ) : (
                  <div className="mt-2 text-xs text-slate-400">{t("grading.manual.selectSlot")}</div>
                )}
              </div>
              <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
                <div className="shrink-0 border-b border-slate-200 px-4 py-2.5">
                  <div className="text-sm font-semibold">老师批注</div>
                </div>
                <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
                  {questionGroups.map((group) => (
                    <div key={group.key} className="space-y-1.5 rounded-md border px-3 py-2">
                      <span className="text-xs font-medium text-slate-700">{group.label}</span>
                      <Input
                        value={questionNotes[group.key] ?? ""}
                        onChange={(e) => updateQuestionNote(group.key, e.target.value)}
                        placeholder="该题批注…"
                        className="h-8 text-sm"
                      />
                    </div>
                  ))}
                  <div className="space-y-1.5 rounded-md border px-3 py-2">
                    <span className="text-xs font-medium text-slate-700">试卷总评</span>
                    <Textarea
                      value={paperNote}
                      onChange={(e) => updatePaperNote(e.target.value)}
                      placeholder="整卷总评（写卷面底部）"
                      className="min-h-[72px] text-sm"
                    />
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
