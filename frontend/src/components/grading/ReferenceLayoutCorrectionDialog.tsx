import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Maximize2,
  Minus,
  MousePointer2,
  Plus,
  RefreshCw,
  Redo2,
  Split,
  Undo2,
  X,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { useLocale } from "@/contexts/LocaleContext";
import { gradingImageUrl } from "@/services/gradingApi";
import type {
  ReferenceLayoutAnswerSlot,
  ReferenceLayoutPage,
  ReferenceLayoutQuestion,
  ReferenceLayoutRegion,
} from "@/services/gradingApi";

type EditMode = "select" | "question" | "answer" | "root-question";
type DrawKind = "root-question" | "question" | "answer";
type Selection =
  | { kind: "question"; questionId: string; regionId: string }
  | { kind: "answer"; questionId: string; slotId: string }
  | null;
type Point = [number, number];
type Box = [number, number, number, number];

type DragState = {
  mode: "move" | "resize" | "draw";
  target: Selection;
  start: Point;
  original?: Box;
  drawKind?: DrawKind;
};

type Props = {
  open: boolean;
  pages: ReferenceLayoutPage[];
  loading?: boolean;
  preparing?: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (pages: ReferenceLayoutPage[]) => Promise<void> | void;
  onReprepare: () => Promise<void> | void;
  variant?: "reference" | "manual";
  scoringEnabled?: boolean;
};

const clamp = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(max, value));

function clonePages(pages: ReferenceLayoutPage[]): ReferenceLayoutPage[] {
  return JSON.parse(JSON.stringify(pages || [])) as ReferenceLayoutPage[];
}

function nextId(prefix: string): string {
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${random}`;
}

function normalizeBox(box: Box, width: number, height: number): Box {
  const x1 = clamp(Math.min(box[0], box[2]), 0, Math.max(0, width - 1));
  const y1 = clamp(Math.min(box[1], box[3]), 0, Math.max(0, height - 1));
  const x2 = clamp(Math.max(box[0], box[2]), x1 + 1, Math.max(x1 + 1, width));
  const y2 = clamp(Math.max(box[1], box[3]), y1 + 1, Math.max(y1 + 1, height));
  return [Math.round(x1), Math.round(y1), Math.round(x2), Math.round(y2)];
}

function pointInBox(point: Point, box: Box): boolean {
  return (
    point[0] >= box[0] &&
    point[0] <= box[2] &&
    point[1] >= box[1] &&
    point[1] <= box[3]
  );
}

function questionBounds(question: ReferenceLayoutQuestion): Box | null {
  const boxes = [
    ...question.regions.map((region) => region.bbox),
    ...question.answer_slots
      .map((slot) => slotBox(slot))
      .filter((box): box is Box => Boolean(box)),
  ];
  if (!boxes.length) return null;
  let [x1, y1, x2, y2] = boxes[0];
  boxes.slice(1).forEach(([rx1, ry1, rx2, ry2]) => {
    x1 = Math.min(x1, rx1);
    y1 = Math.min(y1, ry1);
    x2 = Math.max(x2, rx2);
    y2 = Math.max(y2, ry2);
  });
  return [x1, y1, x2, y2];
}

function makeQuestionSelection(question: ReferenceLayoutQuestion): Selection {
  return {
    kind: "question",
    questionId: question.question_id,
    regionId: question.regions[0]?.region_id || "",
  };
}

function boxFromRegion(region: ReferenceLayoutRegion): Box {
  return [...region.bbox] as Box;
}

function slotBox(slot: ReferenceLayoutAnswerSlot): Box | null {
  if (slot.bbox && slot.bbox.length >= 4) return [...slot.bbox] as Box;
  const first = slot.regions?.[0];
  return first?.bbox ? ([...first.bbox] as Box) : null;
}

function makeRegion(
  question: ReferenceLayoutQuestion,
  box: Box,
): ReferenceLayoutRegion {
  const order =
    Math.max(0, ...question.regions.map((region) => region.order ?? 0)) + 1;
  return {
    region_id: nextId("region"),
    label: `${question.display_no}-${String.fromCharCode(64 + order)}`,
    role: "question",
    order,
    bbox: box,
  };
}

function makeSlot(
  question: ReferenceLayoutQuestion,
  box: Box,
): ReferenceLayoutAnswerSlot {
  const order =
    Math.max(0, ...question.answer_slots.map((slot) => slot.order ?? 0)) + 1;
  const region: ReferenceLayoutRegion = {
    region_id: nextId("answer-region"),
    label: `${question.display_no}_${order}`,
    role: "answer",
    order: 1,
    bbox: box,
  };
  return {
    slot_id: nextId("slot"),
    label: `${question.display_no}_${order}`,
    order,
    bbox: box,
    regions: [region],
    has_handwriting_location: false,
    max_score: 1,
  };
}

function renumberAnswerSlots(
  question: ReferenceLayoutQuestion,
): ReferenceLayoutQuestion {
  return {
    ...question,
    answer_slots: question.answer_slots.map((slot, index) => {
      const order = index + 1;
      const label = `${question.display_no}_${order}`;
      const regions = slot.regions.length
        ? slot.regions.map((region, regionIndex) => ({
            ...region,
            region_id: region.region_id || nextId("answer-region"),
            label: regionIndex === 0 ? label : `${label}_${regionIndex + 1}`,
            order: regionIndex + 1,
          }))
        : slot.bbox
          ? [
              {
                region_id: nextId("answer-region"),
                label,
                role: "answer",
                order: 1,
                bbox: slot.bbox,
              },
            ]
          : [];
      return {
        ...slot,
        order,
        label,
        regions,
      };
    }),
  };
}

function makeQuestion(displayNo: number, box: Box): ReferenceLayoutQuestion {
  const questionId = nextId("question");
  return {
    question_id: questionId,
    display_no: displayNo,
    question_type: "",
    question_text: "",
    regions: [
      {
        region_id: nextId("region"),
        label: `${displayNo}-A`,
        role: "question",
        order: 1,
        bbox: box,
      },
    ],
    answer_slots: [],
  };
}

export function ReferenceLayoutCorrectionDialog({
  open,
  pages,
  loading = false,
  preparing = false,
  onOpenChange,
  onConfirm,
  onReprepare,
  variant = "reference",
  scoringEnabled = false,
}: Props) {
  const { t } = useLocale();
  const [workingPages, setWorkingPages] = useState<ReferenceLayoutPage[]>([]);
  const [pageIndex, setPageIndex] = useState(0);
  const [selection, setSelection] = useState<Selection>(null);
  const [answerTargetQuestionId, setAnswerTargetQuestionId] = useState<
    string | null
  >(null);
  const [editMode, setEditMode] = useState<EditMode>("select");
  const [zoom, setZoom] = useState(1);
  const [fitScale, setFitScale] = useState(1);
  const [history, setHistory] = useState<ReferenceLayoutPage[][]>([]);
  const [future, setFuture] = useState<ReferenceLayoutPage[][]>([]);
  const [previewBox, setPreviewBox] = useState<Box | null>(null);
  const [questionScoreDrafts, setQuestionScoreDrafts] = useState<
    Record<string, string>
  >({});
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const stageRef = useRef<SVGSVGElement | null>(null);
  const dragRef = useRef<DragState | null>(null);
  // 始终持有最新 workingPages，供 commit 记录历史而不破坏其引用稳定性
  const workingPagesRef = useRef<ReferenceLayoutPage[]>([]);
  useEffect(() => {
    workingPagesRef.current = workingPages;
  }, [workingPages]);

  useEffect(() => {
    if (!open) return;
    setWorkingPages(clonePages(pages));
    setPageIndex(0);
    setSelection(null);
    setAnswerTargetQuestionId(null);
    setEditMode("select");
    setZoom(1);
    setHistory([]);
    setFuture([]);
    setQuestionScoreDrafts({});
  }, [open, pages]);

  const page = workingPages[pageIndex] ?? null;
  const imageWidth = page?.image_size?.[0] || 1;
  const imageHeight = page?.image_size?.[1] || 1;
  const scale = fitScale * zoom;
  const stageWidth = Math.max(1, Math.round(imageWidth * scale));
  const stageHeight = Math.max(1, Math.round(imageHeight * scale));

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport || !page) return;
    const updateFit = () => {
      const availableWidth = Math.max(320, viewport.clientWidth - 44);
      const availableHeight = Math.max(320, viewport.clientHeight - 44);
      setFitScale(
        Math.min(1, availableWidth / imageWidth, availableHeight / imageHeight),
      );
    };
    updateFit();
    const observer = new ResizeObserver(updateFit);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [page, imageWidth, imageHeight]);

  const commit = useCallback(
    (updater: (current: ReferenceLayoutPage[]) => ReferenceLayoutPage[]) => {
      // 避免在 setState updater 内调用其他 setState（React 要求 updater 纯函数）
      setHistory((items) => [
        ...items.slice(-29),
        clonePages(workingPagesRef.current),
      ]);
      setFuture([]);
      setWorkingPages((current) => updater(current));
    },
    [],
  );

  const updateQuestion = useCallback(
    (
      questionId: string,
      updater: (question: ReferenceLayoutQuestion) => ReferenceLayoutQuestion,
      recordHistory = true,
    ) => {
      const apply = (current: ReferenceLayoutPage[]) =>
        current.map((item, index) => {
          if (index !== pageIndex) return item;
          return {
            ...item,
            questions: item.questions.map((question) =>
              question.question_id === questionId
                ? updater(question)
                : question,
            ),
          };
        });
      if (recordHistory) commit(apply);
      else setWorkingPages(apply);
    },
    [commit, pageIndex],
  );

  const pointFromEvent = useCallback(
    (event: React.PointerEvent): Point => {
      const svg = stageRef.current;
      if (!svg) return [0, 0];
      const rect = svg.getBoundingClientRect();
      return [
        (event.clientX - rect.left) / Math.max(0.01, scale),
        (event.clientY - rect.top) / Math.max(0.01, scale),
      ];
    },
    [scale],
  );

  const findQuestion = useCallback(
    (questionId: string) => {
      return (
        page?.questions.find(
          (question) => question.question_id === questionId,
        ) ?? null
      );
    },
    [page],
  );

  const selectQuestion = useCallback(
    (question: ReferenceLayoutQuestion, regionId?: string) => {
      setSelection({
        kind: "question",
        questionId: question.question_id,
        regionId: regionId || question.regions[0]?.region_id || "",
      });
      if (editMode === "answer") {
        setAnswerTargetQuestionId(question.question_id);
      }
    },
    [editMode],
  );

  const startDrag = useCallback(
    (event: React.PointerEvent, target: Selection, mode: "move" | "resize") => {
      if (!target || !page) return;
      event.preventDefault();
      event.stopPropagation();
      setSelection(target);
      const point = pointFromEvent(event);
      let original: Box | undefined;
      const question = findQuestion(target.questionId);
      if (target.kind === "question") {
        original = question?.regions.find(
          (region) => region.region_id === target.regionId,
        )
          ? boxFromRegion(
              question.regions.find(
                (region) => region.region_id === target.regionId,
              )!,
            )
          : undefined;
      } else {
        const slot = question?.answer_slots.find(
          (item) => item.slot_id === target.slotId,
        );
        original = slot ? slotBox(slot) || undefined : undefined;
      }
      if (original) {
        setHistory((items) => [...items.slice(-29), clonePages(workingPages)]);
        setFuture([]);
        dragRef.current = { mode, target, start: point, original };
      }
    },
    [findQuestion, page, pointFromEvent, workingPages],
  );

  const updateTargetBox = useCallback(
    (target: Selection, box: Box) => {
      if (!target) return;
      const normalized = normalizeBox(box, imageWidth, imageHeight);
      updateQuestion(
        target.questionId,
        (question) => {
          if (target.kind === "question") {
            return {
              ...question,
              regions: question.regions.map((region) =>
                region.region_id === target.regionId
                  ? { ...region, bbox: normalized }
                  : region,
              ),
            };
          }
          return {
            ...question,
            answer_slots: question.answer_slots.map((slot) => {
              if (slot.slot_id !== target.slotId) return slot;
              return {
                ...slot,
                bbox: normalized,
                regions: slot.regions?.length
                  ? slot.regions.map((region, index) =>
                      index === 0 ? { ...region, bbox: normalized } : region,
                    )
                  : [
                      {
                        region_id: nextId("answer-region"),
                        label: slot.label || `${question.display_no}_1`,
                        bbox: normalized,
                        role: "answer",
                        order: 1,
                      },
                    ],
              };
            }),
          };
        },
        false,
      );
    },
    [imageHeight, imageWidth, updateQuestion],
  );

  useEffect(() => {
    const handleMove = (event: PointerEvent) => {
      const drag = dragRef.current;
      if (!drag || !drag.original) return;
      const svg = stageRef.current;
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      const point: Point = [
        (event.clientX - rect.left) / Math.max(0.01, scale),
        (event.clientY - rect.top) / Math.max(0.01, scale),
      ];
      const dx = point[0] - drag.start[0];
      const dy = point[1] - drag.start[1];
      const original = drag.original;
      const next: Box =
        drag.mode === "resize"
          ? [original[0], original[1], original[2] + dx, original[3] + dy]
          : [
              original[0] + dx,
              original[1] + dy,
              original[2] + dx,
              original[3] + dy,
            ];
      updateTargetBox(drag.target, next);
    };
    const handleUp = () => {
      if (dragRef.current?.mode !== "draw") {
        dragRef.current = null;
      }
    };
    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
    return () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
    };
  }, [scale, updateTargetBox]);

  const startDraw = useCallback(
    (
      event: React.PointerEvent,
      drawKind: DrawKind,
      targetQuestionId: string | null = null,
    ) => {
      if (!page || editMode === "select") return;
      const point = pointFromEvent(event);
      let target: Selection = null;
      if (drawKind !== "root-question") {
        if (!targetQuestionId) return;
        const targetQuestion = findQuestion(targetQuestionId);
        if (!targetQuestion) return;
        const bounds = questionBounds(targetQuestion);
        if (!bounds || !pointInBox(point, bounds)) return;
        target = makeQuestionSelection(targetQuestion);
      }
      event.preventDefault();
      event.stopPropagation();
      dragRef.current = { mode: "draw", target, start: point, drawKind };
      setPreviewBox(null);
    },
    [editMode, findQuestion, page, pointFromEvent],
  );

  useEffect(() => {
    const handleMove = (event: PointerEvent) => {
      const drag = dragRef.current;
      if (!drag || drag.mode !== "draw") return;
      const svg = stageRef.current;
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      const point: Point = [
        (event.clientX - rect.left) / Math.max(0.01, scale),
        (event.clientY - rect.top) / Math.max(0.01, scale),
      ];
      setPreviewBox(
        normalizeBox(
          [drag.start[0], drag.start[1], point[0], point[1]],
          imageWidth,
          imageHeight,
        ),
      );
    };
    const handleUp = (event: PointerEvent) => {
      const drag = dragRef.current;
      if (!drag || drag.mode !== "draw" || !drag.drawKind) return;
      const svg = stageRef.current;
      dragRef.current = null;
      setPreviewBox(null);
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      const end: Point = [
        (event.clientX - rect.left) / Math.max(0.01, scale),
        (event.clientY - rect.top) / Math.max(0.01, scale),
      ];
      const box = normalizeBox(
        [drag.start[0], drag.start[1], end[0], end[1]],
        imageWidth,
        imageHeight,
      );
      if (box[2] - box[0] < 12 || box[3] - box[1] < 12) {
        return;
      }
      if (drag.drawKind === "root-question") {
        const displayNo =
          Math.max(0, ...page.questions.map((item) => item.display_no || 0)) +
          1;
        const question = makeQuestion(displayNo, box);
        commit((current) =>
          current.map((item, index) =>
            index === pageIndex
              ? { ...item, questions: [...item.questions, question] }
              : item,
          ),
        );
        setSelection(makeQuestionSelection(question));
      } else if (drag.drawKind === "question") {
        const question =
          drag.target?.kind === "question"
            ? findQuestion(drag.target.questionId)
            : null;
        if (!question) return;
        const region = makeRegion(question, box);
        updateQuestion(question.question_id, (item) => ({
          ...item,
          regions: [...item.regions, region],
        }));
        setSelection({
          kind: "question",
          questionId: question.question_id,
          regionId: region.region_id || "",
        });
      } else {
        const question =
          drag.target?.kind === "question"
            ? findQuestion(drag.target.questionId)
            : null;
        if (!question) return;
        const slot = makeSlot(question, box);
        updateQuestion(question.question_id, (item) => ({
          ...renumberAnswerSlots({
            ...item,
            answer_slots: [...item.answer_slots, slot],
          }),
        }));
        setSelection({
          kind: "answer",
          questionId: question.question_id,
          slotId: slot.slot_id || "",
        });
        setAnswerTargetQuestionId(question.question_id);
      }
      setEditMode(drag.drawKind === "root-question" ? "select" : drag.drawKind);
    };
    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
    return () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
    };
  }, [
    commit,
    findQuestion,
    imageHeight,
    imageWidth,
    page,
    scale,
    updateQuestion,
    pageIndex,
  ]);

  const undo = () => {
    const previous = history[history.length - 1];
    if (!previous) return;
    setFuture((next) => [clonePages(workingPages), ...next].slice(0, 30));
    setWorkingPages(clonePages(previous));
    setHistory((items) => items.slice(0, -1));
  };

  const redo = () => {
    const next = future[0];
    if (!next) return;
    setHistory((previous) =>
      [...previous, clonePages(workingPages)].slice(-30),
    );
    setWorkingPages(clonePages(next));
    setFuture((items) => items.slice(1));
  };

  const selectedQuestion = useMemo(
    () =>
      selection?.kind === "question"
        ? findQuestion(selection.questionId)
        : null,
    [findQuestion, selection],
  );
  const activeQuestionId = selection?.questionId ?? null;
  const drawQuestionId =
    editMode === "question"
      ? (selectedQuestion?.question_id ?? null)
      : editMode === "answer"
        ? answerTargetQuestionId
        : null;

  const removeSelected = () => {
    if (!selection || !page) return;
    if (selection.kind === "question") {
      // Keep at least one question in the page; accidental deletion should
      // never create a layout that the backend cannot grade.
      if (page.questions.length <= 1) return;
      commit((current) =>
        current.map((item, index) =>
          index === pageIndex
            ? {
                ...item,
                questions: item.questions.filter(
                  (question) => question.question_id !== selection.questionId,
                ),
              }
            : item,
        ),
      );
      if (answerTargetQuestionId === selection.questionId) {
        setAnswerTargetQuestionId(null);
      }
      setSelection(null);
      setEditMode("select");
    } else {
      const question = findQuestion(selection.questionId);
      updateQuestion(selection.questionId, (currentQuestion) =>
        renumberAnswerSlots({
          ...currentQuestion,
          answer_slots: currentQuestion.answer_slots.filter(
            (slot) => slot.slot_id !== selection.slotId,
          ),
        }),
      );
      if (question) {
        setSelection(makeQuestionSelection(question));
        setAnswerTargetQuestionId(question.question_id);
      } else {
        setSelection(null);
      }
    }
  };

  const setSlotMaxScore = (
    questionId: string,
    slotId: string,
    value: string,
  ) => {
    const parsed = Number(value);
    updateQuestion(questionId, (question) => ({
      ...question,
      answer_slots: question.answer_slots.map((slot) =>
        slot.slot_id === slotId
          ? { ...slot, max_score: Number.isFinite(parsed) ? parsed : 0 }
          : slot,
      ),
    }));
  };

  const applyQuestionScore = (question: ReferenceLayoutQuestion) => {
    const parsed = Number(questionScoreDrafts[question.question_id]);
    if (!Number.isFinite(parsed) || parsed <= 0) return;
    updateQuestion(question.question_id, (item) => ({
      ...item,
      answer_slots: item.answer_slots.map((slot) => ({
        ...slot,
        max_score: parsed,
      })),
    }));
  };

  const renderLabel = (label: string, x: number, y: number, color: string) => {
    const fontSize = Math.max(11, 19 / Math.max(0.01, scale));
    const width = Math.max(25, label.length * fontSize * 0.65 + 12);
    return (
      <g pointerEvents="none">
        <rect
          x={x}
          y={Math.max(0, y - fontSize - 8)}
          width={width}
          height={fontSize + 8}
          rx={4 / Math.max(0.01, scale)}
          fill={color}
          opacity={0.94}
        />
        <text
          x={x + 6 / Math.max(0.01, scale)}
          y={Math.max(fontSize, y - 6 / Math.max(0.01, scale))}
          fill="white"
          fontSize={fontSize}
          fontWeight="700"
        >
          {label}
        </text>
      </g>
    );
  };

  const renderHandle = (x: number, y: number, target: Selection) => (
    <circle
      cx={x}
      cy={y}
      r={Math.max(6, 9 / Math.max(0.01, scale))}
      fill="white"
      stroke="#0f766e"
      strokeWidth={Math.max(2, 3 / Math.max(0.01, scale))}
      className="cursor-nwse-resize"
      onPointerDown={(event) => startDrag(event, target, "resize")}
    />
  );

  const handleConfirm = async () => {
    await onConfirm(workingPages);
  };

  const handleReprepare = async () => {
    if (loading || preparing) return;
    await onReprepare();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="left-1/2 top-1/2 flex h-[96vh] w-[98vw] max-w-[1800px] -translate-x-1/2 -translate-y-1/2 flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="shrink-0 border-b bg-slate-950 px-6 py-4 text-left text-white">
          <DialogTitle className="flex items-center gap-2 text-lg text-white">
            <Split className="h-5 w-5 text-teal-300" />
            {variant === "manual"
              ? t("grading.manualLayout.title")
              : t("grading.layout.title")}
          </DialogTitle>
          <DialogDescription className="sr-only">
            {variant === "manual"
              ? t("grading.manualLayout.description")
              : t("grading.layout.description")}
          </DialogDescription>
        </DialogHeader>

        <div className="flex min-h-0 flex-1 bg-slate-100">
          <aside
            className={cn(
              "flex shrink-0 flex-col border-r bg-white",
              scoringEnabled ? "w-[360px]" : "w-[270px]",
            )}
          >
            <div className="border-b px-4 py-3">
              <div className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
                {t("grading.layout.pages")}
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {workingPages.map((item, index) => (
                  <Button
                    key={item.page_no}
                    size="sm"
                    variant={index === pageIndex ? "default" : "outline"}
                    onClick={() => {
                      setPageIndex(index);
                      setSelection(null);
                      setAnswerTargetQuestionId(null);
                      setEditMode("select");
                    }}
                  >
                    P{item.page_no}
                  </Button>
                ))}
              </div>
            </div>
            <ScrollArea className="min-h-0 flex-1 px-3 py-3">
              <div className="space-y-2">
                {page?.questions.map((question) => (
                  <div
                    key={question.question_id}
                    className="rounded-lg border border-slate-200 bg-slate-50 p-2"
                  >
                    <button
                      type="button"
                      className={cn(
                        "flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm font-semibold",
                        activeQuestionId === question.question_id
                          ? "bg-teal-100 text-teal-900"
                          : "hover:bg-slate-100",
                      )}
                      onClick={() => selectQuestion(question)}
                    >
                      <span className="flex h-6 w-6 items-center justify-center rounded bg-blue-600 text-xs font-bold text-white">
                        {question.display_no}
                      </span>
                      <span className="truncate">
                        {t("grading.layout.question")}
                      </span>
                      <span className="ml-auto text-xs text-slate-500">
                        {question.regions.length} +{" "}
                        {question.answer_slots.length}
                      </span>
                    </button>
                    {scoringEnabled && (
                      <div className="mt-2 flex items-center gap-2 border-t border-slate-200 pt-2">
                        <Input
                          type="number"
                          min="0.01"
                          step="0.5"
                          className="h-7 w-20 border-2 border-sky-300 bg-sky-50/70 px-2 text-xs font-medium text-slate-800 shadow-sm focus-visible:border-sky-500 focus-visible:ring-2 focus-visible:ring-sky-200"
                          value={
                            questionScoreDrafts[question.question_id] || ""
                          }
                          placeholder={t("grading.manualLayout.score")}
                          onChange={(event) =>
                            setQuestionScoreDrafts((current) => ({
                              ...current,
                              [question.question_id]: event.target.value,
                            }))
                          }
                        />
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="h-7 flex-1 px-2 text-xs"
                          disabled={
                            !question.answer_slots.length ||
                            Number(questionScoreDrafts[question.question_id]) <=
                              0
                          }
                          onClick={() => applyQuestionScore(question)}
                        >
                          {t("grading.manualLayout.applyQuestionScore")}
                        </Button>
                      </div>
                    )}
                    <div className="mt-1 space-y-1 pl-2">
                      {question.regions.map((region) => (
                        <button
                          type="button"
                          key={region.region_id}
                          className={cn(
                            "block w-full rounded px-2 py-1 text-left text-xs",
                            selection?.kind === "question" &&
                              selection.regionId === region.region_id
                              ? "bg-blue-100 font-semibold text-blue-800"
                              : "text-slate-600 hover:bg-slate-100",
                          )}
                          onClick={() =>
                            selectQuestion(question, region.region_id)
                          }
                        >
                          {region.label || `${question.display_no}-A`} ·{" "}
                          {t("grading.layout.contentRegion")}
                        </button>
                      ))}
                      {question.answer_slots.map((slot) => (
                        <div
                          key={slot.slot_id}
                          className="flex items-center gap-1"
                        >
                          <button
                            type="button"
                            className={cn(
                              "block min-w-0 flex-1 rounded px-2 py-1 text-left text-xs",
                              selection?.kind === "answer" &&
                                selection.slotId === slot.slot_id
                                ? "bg-amber-100 font-semibold text-amber-800"
                                : "text-slate-600 hover:bg-slate-100",
                            )}
                            onClick={() => {
                              setSelection({
                                kind: "answer",
                                questionId: question.question_id,
                                slotId: slot.slot_id || "",
                              });
                              setAnswerTargetQuestionId(question.question_id);
                            }}
                          >
                            {slot.label || `${question.display_no}_1`} ·{" "}
                            {t("grading.layout.answerRegion")}
                          </button>
                          {scoringEnabled && (
                            <div className="flex shrink-0 items-center gap-1">
                              <Input
                                aria-label={`${slot.label || slot.slot_id} ${t("grading.manualLayout.maxScore")}`}
                                type="number"
                                min="0.01"
                                step="0.5"
                                className="h-7 w-16 px-1 text-center text-xs"
                                value={slot.max_score ?? 1}
                                onChange={(event) =>
                                  setSlotMaxScore(
                                    question.question_id,
                                    slot.slot_id || "",
                                    event.target.value,
                                  )
                                }
                              />
                              <span className="text-[11px] text-slate-500">
                                {t("grading.manualLayout.points")}
                              </span>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </aside>

          <section className="flex min-w-0 flex-1 flex-col">
            <div className="flex shrink-0 flex-wrap items-center gap-2 border-b bg-white px-4 py-2">
              <Button
                size="sm"
                variant={editMode === "select" ? "default" : "outline"}
                onClick={() => setEditMode("select")}
                className="gap-1.5"
              >
                <MousePointer2 className="h-4 w-4" />
                {t("grading.layout.select")}
              </Button>
              <Button
                size="sm"
                variant={editMode === "question" ? "default" : "outline"}
                disabled={!selectedQuestion}
                onClick={() => setEditMode("question")}
                className="gap-1.5"
              >
                <Split className="h-4 w-4" />
                {t("grading.layout.splitQuestion")}
              </Button>
              <Button
                size="sm"
                variant={editMode === "root-question" ? "default" : "outline"}
                onClick={() => setEditMode("root-question")}
                className="gap-1.5"
              >
                <Plus className="h-4 w-4" />
                {t("grading.layout.addQuestion")}
              </Button>
              <Button
                size="sm"
                variant={editMode === "answer" ? "default" : "outline"}
                disabled={!selectedQuestion}
                onClick={() => {
                  if (!selectedQuestion) return;
                  setAnswerTargetQuestionId(selectedQuestion.question_id);
                  setEditMode("answer");
                }}
                className="gap-1.5"
              >
                <Plus className="h-4 w-4" />
                {t("grading.layout.addAnswer")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={!selection}
                onClick={removeSelected}
                className="gap-1.5"
              >
                <X className="h-4 w-4" />
                {t("grading.layout.deleteSelected")}
              </Button>
              <div className="ml-auto flex items-center gap-1">
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={undo}
                  disabled={!history.length}
                  title={t("grading.layout.undo")}
                >
                  <Undo2 className="h-4 w-4" />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={redo}
                  disabled={!future.length}
                  title={t("grading.layout.redo")}
                >
                  <Redo2 className="h-4 w-4" />
                </Button>
                <div className="mx-1 h-5 w-px bg-slate-200" />
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={() =>
                    setZoom((value) => clamp(value * 0.85, 0.35, 3))
                  }
                  title={t("grading.layout.zoomOut")}
                >
                  <Minus className="h-4 w-4" />
                </Button>
                <span className="w-12 text-center text-xs font-semibold text-slate-600">
                  {Math.round(zoom * 100)}%
                </span>
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={() =>
                    setZoom((value) => clamp(value * 1.18, 0.35, 3))
                  }
                  title={t("grading.layout.zoomIn")}
                >
                  <Plus className="h-4 w-4" />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={() => setZoom(1)}
                  title={t("grading.layout.resetZoom")}
                >
                  <Maximize2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <div
              ref={viewportRef}
              className="min-h-0 flex-1 overflow-auto bg-slate-300 p-5"
              onWheel={(event) => {
                if (variant === "manual") return;
                event.preventDefault();
                setZoom((value) =>
                  clamp(value * (event.deltaY < 0 ? 1.1 : 0.9), 0.35, 3),
                );
              }}
            >
              {page ? (
                <div className="flex min-w-max min-h-full items-start justify-center">
                  <div
                    className="relative shrink-0 bg-white shadow-xl"
                    style={{ width: stageWidth, height: stageHeight }}
                  >
                    <img
                      src={gradingImageUrl(page.image_url)}
                      alt={`${t("grading.layout.standardAnswer")} P${page.page_no}`}
                      className="absolute inset-0 block select-none object-fill"
                      style={{ width: stageWidth, height: stageHeight }}
                      draggable={false}
                    />
                    <svg
                      ref={stageRef}
                      data-testid="reference-layout-stage"
                      data-edit-mode={editMode}
                      data-draw-question-id={drawQuestionId || ""}
                      width={stageWidth}
                      height={stageHeight}
                      viewBox={`0 0 ${imageWidth} ${imageHeight}`}
                      className={cn(
                        "absolute inset-0",
                        editMode !== "select" && "cursor-crosshair",
                      )}
                      onPointerDown={(event) => {
                        if (editMode === "root-question") {
                          startDraw(event, "root-question");
                          return;
                        }
                        if (drawQuestionId && editMode !== "select") {
                          startDraw(event, editMode, drawQuestionId);
                        }
                      }}
                    >
                      {page.questions.flatMap((question) =>
                        question.regions.map((region) => {
                          const box = boxFromRegion(region);
                          const target: Selection = {
                            kind: "question",
                            questionId: question.question_id,
                            regionId: region.region_id || "",
                          };
                          const active =
                            selection?.kind === "question" &&
                            selection.regionId === region.region_id;
                          return (
                            <g key={region.region_id}>
                              <rect
                                x={box[0]}
                                y={box[1]}
                                width={box[2] - box[0]}
                                height={box[3] - box[1]}
                                fill="#2563eb"
                                fillOpacity={active ? 0.12 : 0.04}
                                stroke="#2563eb"
                                strokeWidth={active ? 4 / scale : 2.5 / scale}
                                onPointerDown={(event) => {
                                  if (editMode === "select") {
                                    startDrag(event, target, "move");
                                    return;
                                  }
                                  if (drawQuestionId === question.question_id) {
                                    startDraw(
                                      event,
                                      editMode,
                                      question.question_id,
                                    );
                                  }
                                }}
                              />
                              {renderLabel(
                                region.label || String(question.display_no),
                                box[0],
                                box[1],
                                "#2563eb",
                              )}
                              {active &&
                                editMode === "select" &&
                                renderHandle(box[2], box[3], target)}
                            </g>
                          );
                        }),
                      )}
                      {page.questions.flatMap((question) =>
                        question.answer_slots.map((slot) => {
                          const box = slotBox(slot);
                          if (!box) return null;
                          const target: Selection = {
                            kind: "answer",
                            questionId: question.question_id,
                            slotId: slot.slot_id || "",
                          };
                          const active =
                            selection?.kind === "answer" &&
                            selection.slotId === slot.slot_id;
                          return (
                            <g key={slot.slot_id}>
                              <rect
                                x={box[0]}
                                y={box[1]}
                                width={box[2] - box[0]}
                                height={box[3] - box[1]}
                                fill="#f59e0b"
                                fillOpacity={active ? 0.2 : 0.08}
                                stroke="#d97706"
                                strokeWidth={active ? 4 / scale : 2.5 / scale}
                                strokeDasharray={`${8 / scale} ${5 / scale}`}
                                onPointerDown={(event) => {
                                  if (
                                    editMode === "select" ||
                                    editMode === "answer"
                                  ) {
                                    startDrag(event, target, "move");
                                  }
                                }}
                              />
                              {renderLabel(
                                slot.label || `${question.display_no}_1`,
                                box[0],
                                box[1],
                                "#b45309",
                              )}
                              {active &&
                                (editMode === "select" ||
                                  editMode === "answer") &&
                                renderHandle(box[2], box[3], target)}
                            </g>
                          );
                        }),
                      )}
                      {previewBox && (
                        <rect
                          data-testid="reference-layout-preview-box"
                          x={previewBox[0]}
                          y={previewBox[1]}
                          width={previewBox[2] - previewBox[0]}
                          height={previewBox[3] - previewBox[1]}
                          fill={editMode === "answer" ? "#f59e0b" : "#2563eb"}
                          fillOpacity={0.12}
                          stroke={editMode === "answer" ? "#d97706" : "#2563eb"}
                          strokeWidth={3 / scale}
                          strokeDasharray={`${10 / scale} ${6 / scale}`}
                        />
                      )}
                    </svg>
                  </div>
                </div>
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-slate-500">
                  {t("grading.layout.empty")}
                </div>
              )}
            </div>
          </section>
        </div>

        <DialogFooter className="shrink-0 border-t bg-white px-6 py-3">
          <div className="mr-auto text-xs text-slate-500">
            {page
              ? t("grading.layout.currentPage", {
                  page: page.page_no,
                  count: page.questions.length,
                })
              : ""}
          </div>
          <Button
            variant="outline"
            onClick={() => void handleReprepare()}
            disabled={loading || preparing}
            className="gap-2"
          >
            <RefreshCw className={cn("h-4 w-4", preparing && "animate-spin")} />
            {preparing
              ? t("grading.layout.repreparing")
              : t("grading.layout.reprepare")}
          </Button>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={loading || preparing}
          >
            {t("common.cancel")}
          </Button>
          <Button
            onClick={() => void handleConfirm()}
            disabled={loading || preparing || !workingPages.length}
            className="gap-2"
          >
            {loading ? (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
            ) : null}
            {loading ? t("grading.layout.saving") : t("grading.layout.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
