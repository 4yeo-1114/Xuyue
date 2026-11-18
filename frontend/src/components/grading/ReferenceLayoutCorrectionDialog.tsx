import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
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
  /** 打开时落点页（从识别列表「答题区框」跳进来改某页的框用）；缺省第一页 */
  initialPageNo?: number;
  onOpenChange: (open: boolean) => void;
  onConfirm: (pages: ReferenceLayoutPage[]) => Promise<void> | void;
  /** 11.11-11 每面切完单独保存：离开一页/关闭弹窗时把那一页静默落盘（其余页不动） */
  onSavePage?: (page: ReferenceLayoutPage) => Promise<void> | void;
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

// 多选集的成员键（11.10-1）：同一题的不同区域/作答区是不同成员，删题时按 questionId 去重
function selectionKey(target: Selection): string {
  if (!target) return "";
  return target.kind === "question"
    ? `q:${target.questionId}:${target.regionId}`
    : `a:${target.questionId}:${target.slotId}`;
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

// 11.11-1 手动排序后全局重编号：整卷（页号升序 × 页内数组序）连续 1..N，
// 报告「第N题」跟老师的排法走；question_id 不变（后端按 q-{原号} 认领原题）。
// 无 question_id 的旧数据先补铸号 q-{现号}——现号就是原号，铸完再换新号。
function renumberAllQuestions(
  pages: ReferenceLayoutPage[],
): ReferenceLayoutPage[] {
  const assigned = new Map<
    number,
    Array<{ displayNo: number; questionId: string }>
  >();
  let counter = 0;
  [...pages]
    .sort((a, b) => (a.page_no ?? 0) - (b.page_no ?? 0))
    .forEach((page) => {
      assigned.set(
        page.page_no,
        page.questions.map((question) => {
          counter += 1;
          return {
            displayNo: counter,
            questionId: question.question_id || `q-${question.display_no}`,
          };
        }),
      );
    });
  return pages.map((page) => ({
    ...page,
    questions: page.questions.map((question, index) => {
      const next = assigned.get(page.page_no)?.[index];
      if (!next) return question;
      const displayNo = next.displayNo;
      // 区域/作答区标签跟题号走：{题号}-{A..} / {题号}_{序}
      const regions = question.regions.map((region, regionIndex) => ({
        ...region,
        label: `${displayNo}-${String.fromCharCode(65 + regionIndex)}`,
        order: regionIndex + 1,
      }));
      const answerSlots = question.answer_slots.map((slot, slotIndex) => {
        const label = `${displayNo}_${slotIndex + 1}`;
        return {
          ...slot,
          order: slotIndex + 1,
          label,
          regions: slot.regions.map((region, regionIndex) => ({
            ...region,
            label:
              regionIndex === 0 ? label : `${label}_${regionIndex + 1}`,
            order: regionIndex + 1,
          })),
        };
      });
      return {
        ...question,
        question_id: next.questionId,
        display_no: displayNo,
        regions,
        answer_slots: answerSlots,
      };
    }),
  }));
}

export function ReferenceLayoutCorrectionDialog({
  open,
  pages,
  loading = false,
  preparing = false,
  initialPageNo,
  onOpenChange,
  onConfirm,
  onSavePage,
  onReprepare,
  variant = "reference",
  scoringEnabled = false,
}: Props) {
  const { t } = useLocale();
  const [workingPages, setWorkingPages] = useState<ReferenceLayoutPage[]>([]);
  const [pageIndex, setPageIndex] = useState(0);
  const [selection, setSelection] = useState<Selection>(null);
  // 多选集（11.10-1）：Ctrl/⌘+点 加入/移出，Del/删除按钮一次性删掉整个集合
  const [multiSelections, setMultiSelections] = useState<Selection[]>([]);
  // 目标题目（11.10-3）：分题/作答区画给谁。持久保存——选中态变成槽/区域后不丢，
  // 工具按钮和绘制目标都跟着它走，不用每框一次就回点「选择」重新选题
  const [targetQuestionId, setTargetQuestionId] = useState<string | null>(null);
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

  // 11.11-11 每面切完单独保存：保存串行队列 + 每页「已保存基线」（当前内容≠基线=有未保存修改）
  const saveChainRef = useRef<Promise<void>>(Promise.resolve());
  const baselineRef = useRef<Record<number, string>>({});
  const [saveStatus, setSaveStatus] = useState<{
    phase: "saving" | "saved" | "error";
    pageNo: number;
  } | null>(null);

  useEffect(() => {
    if (!open) return;
    setWorkingPages(clonePages(pages));
    baselineRef.current = Object.fromEntries(
      pages.map((item) => [item.page_no, JSON.stringify(item)]),
    );
    setSaveStatus(null);
    // 落点页：从识别列表点的那页的框进来的就停在那页，找不到退回第一页
    setPageIndex(Math.max(0, pages.findIndex((item) => item.page_no === initialPageNo)));
    setSelection(null);
    setMultiSelections([]);
    setTargetQuestionId(null);
    setEditMode("select");
    setZoom(1);
    setHistory([]);
    setFuture([]);
    setQuestionScoreDrafts({});
  }, [open, pages, initialPageNo]);

  const isPageDirty = useCallback((item: ReferenceLayoutPage) => {
    return JSON.stringify(item) !== (baselineRef.current[item.page_no] ?? "");
  }, []);

  const enqueueSavePage = useCallback(
    (item: ReferenceLayoutPage | undefined) => {
      if (!onSavePage || !item || !isPageDirty(item)) return;
      if (!(item.questions || []).length) return; // 空页不落盘（整卷确认也会拒）
      const snapshot = clonePages([item])[0];
      saveChainRef.current = saveChainRef.current.then(async () => {
        setSaveStatus({ phase: "saving", pageNo: snapshot.page_no });
        try {
          await onSavePage(snapshot);
          baselineRef.current[snapshot.page_no] = JSON.stringify(snapshot);
          setSaveStatus({ phase: "saved", pageNo: snapshot.page_no });
        } catch {
          // 失败保留 dirty 状态；父级已 toast，老师可点「确认保存」整体重试
          setSaveStatus({ phase: "error", pageNo: snapshot.page_no });
        }
      });
    },
    [isPageDirty, onSavePage],
  );

  // 关闭=把所有还没落盘的页补存一遍（X/取消/ESC 都走这里）
  const handleOpenChange = useCallback(
    (next: boolean) => {
      if (!next) {
        for (const item of workingPagesRef.current) {
          enqueueSavePage(item);
        }
      }
      onOpenChange(next);
    },
    [enqueueSavePage, onOpenChange],
  );

  // 「已保存」提示 4 秒后自动收起，别一直挂在标题栏
  useEffect(() => {
    if (saveStatus?.phase !== "saved") return;
    const timer = window.setTimeout(() => {
      setSaveStatus((cur) => (cur?.phase === "saved" ? null : cur));
    }, 4000);
    return () => window.clearTimeout(timer);
  }, [saveStatus]);

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

  // 11.11-1 手动排序：上移/下移交换页内相邻题；每次排完整卷全局重编号，
  // 题号=老师的排法（课堂讲评「第N题」跟它走），question_id 不动
  const moveQuestion = useCallback(
    (questionIndex: number, delta: -1 | 1) => {
      commit((current) =>
        renumberAllQuestions(
          current.map((page, index) => {
            if (index !== pageIndex) return page;
            const target = questionIndex + delta;
            if (
              questionIndex < 0 ||
              target < 0 ||
              target >= page.questions.length
            ) {
              return page;
            }
            const questions = [...page.questions];
            [questions[questionIndex], questions[target]] = [
              questions[target],
              questions[questionIndex],
            ];
            return { ...page, questions };
          }),
        ),
      );
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
      setMultiSelections([]);
      setTargetQuestionId(question.question_id);
    },
    [],
  );

  // Ctrl/⌘+点 加入/移出多选集（11.10-1）；普通点走单选路径
  const toggleMulti = useCallback(
    (target: Selection) => {
      if (!target) return;
      const key = selectionKey(target);
      const exists = multiSelections.some((item) => selectionKey(item) === key);
      setMultiSelections((prev) =>
        exists
          ? prev.filter((item) => selectionKey(item) !== key)
          : [...prev, target],
      );
      if (exists) {
        if (selection && selectionKey(selection) === key) setSelection(null);
      } else {
        setSelection(target);
        setTargetQuestionId(target.questionId);
      }
    },
    [multiSelections, selection],
  );

  const startDrag = useCallback(
    (event: React.PointerEvent, target: Selection, mode: "move" | "resize") => {
      if (!target || !page) return;
      event.preventDefault();
      event.stopPropagation();
      // Ctrl/⌘+点=多选切换（11.10-1），不进入拖拽
      if (event.ctrlKey || event.metaKey) {
        toggleMulti(target);
        return;
      }
      setSelection(target);
      setMultiSelections([]);
      setTargetQuestionId(target.questionId);
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
    [findQuestion, page, pointFromEvent, toggleMulti, workingPages],
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
      forQuestionId: string | null = null,
    ) => {
      if (!page || editMode === "select") return;
      const point = pointFromEvent(event);
      let target: Selection = null;
      if (drawKind !== "root-question") {
        if (!forQuestionId) return;
        const targetQuestion = findQuestion(forQuestionId);
        if (!targetQuestion) return;
        const bounds = questionBounds(targetQuestion);
        // 11.10-3：作答区仍须落在题目范围内（防画飞）；分题新框放宽——
        // 题目框在分题模式下改成可拖动微调后，重叠拆分的起笔常落在已有题框上，
        // 而目标题目本来就明确，起笔不必卡在范围内
        if (
          drawKind === "answer" &&
          (!bounds || !pointInBox(point, bounds))
        ) {
          return;
        }
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
        // 11.11-1：新题号取整卷最大号+1（按页取会和别的页撞号）
        const displayNo =
          Math.max(
            0,
            ...workingPagesRef.current.flatMap((item) =>
              item.questions.map((question) => question.display_no || 0),
            ),
          ) + 1;
        const question = makeQuestion(displayNo, box);
        commit((current) =>
          current.map((item, index) =>
            index === pageIndex
              ? { ...item, questions: [...item.questions, question] }
              : item,
          ),
        );
        setSelection(makeQuestionSelection(question));
        setMultiSelections([]);
        setTargetQuestionId(question.question_id);
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
        setMultiSelections([]);
        setTargetQuestionId(question.question_id);
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
        setMultiSelections([]);
        setTargetQuestionId(question.question_id);
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

  // 目标题目（11.10-3）：画完一个作答区/题框后选中态变成槽/区域也算数，
  // 工具按钮与绘制目标跟着持久目标走——不再画一次就灰掉、逼着回点「选择」
  const selectedQuestion = useMemo(() => {
    const id =
      targetQuestionId ??
      (selection?.kind === "question" ? selection.questionId : null);
    return id ? findQuestion(id) : null;
  }, [findQuestion, selection, targetQuestionId]);
  const activeQuestionId = selection?.questionId ?? null;
  const drawQuestionId =
    editMode === "question" || editMode === "answer"
      ? (selectedQuestion?.question_id ?? null)
      : null;
  const multiKeySet = useMemo(
    () =>
      new Set(
        multiSelections.filter(Boolean).map((item) => selectionKey(item)),
      ),
    [multiSelections],
  );
  // 高亮判定（11.10-1）：单选或在多选集里都算选中
  const multiHas = (target: Selection) =>
    Boolean(target) && multiKeySet.has(selectionKey(target));

  const removeSelected = () => {
    if (!page) return;
    // 多选集优先（11.10-1）：一次删掉整个集合；没多选就删当前单选
    const targets: Selection[] = multiSelections.length
      ? multiSelections
      : selection
        ? [selection]
        : [];
    if (!targets.length) return;
    const questionIds = new Set<string>();
    const slotIdsByQuestion = new Map<string, Set<string>>();
    for (const target of targets) {
      if (!target) continue;
      if (target.kind === "question") {
        questionIds.add(target.questionId);
      } else {
        const slots =
          slotIdsByQuestion.get(target.questionId) ?? new Set<string>();
        slots.add(target.slotId);
        slotIdsByQuestion.set(target.questionId, slots);
      }
    }
    // Keep at least one question in the page; accidental deletion should
    // never create a layout that the backend cannot grade.
    if (
      page.questions.length &&
      page.questions.every((question) => questionIds.has(question.question_id))
    ) {
      questionIds.delete(page.questions[0].question_id);
    }
    if (!questionIds.size && !slotIdsByQuestion.size) return;
    // 整批一个撤销步（11.10-1）：题框+作答区删除合成一次 commit
    commit((current) =>
      current.map((item, index) => {
        if (index !== pageIndex) return item;
        return {
          ...item,
          questions: item.questions
            .filter((question) => !questionIds.has(question.question_id))
            .map((question) => {
              const slots = slotIdsByQuestion.get(question.question_id);
              if (!slots || !slots.size) return question;
              return renumberAnswerSlots({
                ...question,
                answer_slots: question.answer_slots.filter(
                  (slot) => !slots.has(slot.slot_id),
                ),
              });
            }),
        };
      }),
    );
    if (targetQuestionId && questionIds.has(targetQuestionId)) {
      setTargetQuestionId(null);
    }
    if (questionIds.size) {
      setEditMode("select");
    }
    // 单删作答区沿用旧行为：落回所属题目；多选/删题一律清空
    const only = targets.length === 1 ? targets[0] : null;
    const parentQuestion =
      only?.kind === "answer" && !questionIds.has(only.questionId)
        ? findQuestion(only.questionId)
        : null;
    if (parentQuestion) {
      setSelection(makeQuestionSelection(parentQuestion));
      setMultiSelections([]);
      setTargetQuestionId(parentQuestion.question_id);
    } else {
      setSelection(null);
      setMultiSelections([]);
    }
  };

  // Del/Backspace 删除快捷键（11.10-1）：输入框/IME 打字时不劫持按键
  const removeSelectedRef = useRef(removeSelected);
  useEffect(() => {
    removeSelectedRef.current = removeSelected;
  });
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Delete" && event.key !== "Backspace") return;
      if (event.isComposing) return;
      const el = event.target as HTMLElement | null;
      const tag = (el?.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea" || el?.isContentEditable) {
        return;
      }
      event.preventDefault();
      removeSelectedRef.current();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open]);

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
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="left-1/2 top-1/2 flex h-[96vh] w-[98vw] max-w-[1800px] -translate-x-1/2 -translate-y-1/2 flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="shrink-0 border-b bg-slate-950 px-6 py-4 text-left text-white">
          <DialogTitle className="flex items-center gap-2 text-lg text-white">
            <Split className="h-5 w-5 text-teal-300" />
            {variant === "manual"
              ? t("grading.manualLayout.title")
              : t("grading.layout.title")}
            {/* 11.11-11 顶部保存状态提示：每面切完自动落盘，让老师一眼看到存没存 */}
            {saveStatus && (
              <span
                className={cn(
                  "ml-3 text-sm font-normal",
                  saveStatus.phase === "saving" && "text-teal-300",
                  saveStatus.phase === "saved" && "text-emerald-300",
                  saveStatus.phase === "error" && "text-red-300",
                )}
              >
                {saveStatus.phase === "saving" &&
                  t("grading.layout.savingPage", { page: saveStatus.pageNo })}
                {saveStatus.phase === "saved" &&
                  t("grading.layout.savedPage", { page: saveStatus.pageNo })}
                {saveStatus.phase === "error" &&
                  t("grading.layout.saveFailedPage", { page: saveStatus.pageNo })}
              </span>
            )}
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
                    title={isPageDirty(item) ? t("grading.layout.unsavedDot", { page: item.page_no }) : undefined}
                    onClick={() => {
                      // 11.11-11 每面切完单独保存：离开这页前先把改动静默落盘
                      enqueueSavePage(workingPagesRef.current[pageIndex]);
                      setPageIndex(index);
                      setSelection(null);
                      setMultiSelections([]);
                      setTargetQuestionId(null);
                      setEditMode("select");
                    }}
                  >
                    P{item.page_no}
                    {isPageDirty(item) && (
                      <span
                        aria-hidden
                        className="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-amber-400"
                      />
                    )}
                  </Button>
                ))}
              </div>
            </div>
            <ScrollArea className="min-h-0 flex-1 px-3 py-3">
              <div className="space-y-2">
                {page?.questions.map((question, questionIndex) => (
                  <div
                    key={question.question_id}
                    className="rounded-lg border border-slate-200 bg-slate-50 p-2"
                  >
                    <div className="flex w-full items-center gap-1">
                      <button
                        type="button"
                        className={cn(
                          "flex min-w-0 flex-1 items-center gap-2 rounded px-2 py-1.5 text-left text-sm font-semibold",
                          activeQuestionId === question.question_id ||
                            multiHas(makeQuestionSelection(question))
                            ? "bg-teal-100 text-teal-900"
                            : "hover:bg-slate-100",
                        )}
                        onClick={(event) => {
                          // 左侧功能栏多选删除（11.10-1）：Ctrl/⌘+点 加入/移出多选集
                          if (event.ctrlKey || event.metaKey) {
                            toggleMulti(makeQuestionSelection(question));
                            return;
                          }
                          selectQuestion(question);
                        }}
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
                      <button
                        type="button"
                        className="flex h-6 w-6 shrink-0 items-center justify-center rounded text-slate-500 hover:bg-slate-200 disabled:opacity-30 disabled:hover:bg-transparent"
                        disabled={questionIndex === 0}
                        title={t("grading.layout.moveUp")}
                        onClick={() => moveQuestion(questionIndex, -1)}
                      >
                        <ChevronUp className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        className="flex h-6 w-6 shrink-0 items-center justify-center rounded text-slate-500 hover:bg-slate-200 disabled:opacity-30 disabled:hover:bg-transparent"
                        disabled={
                          !page || questionIndex >= page.questions.length - 1
                        }
                        title={t("grading.layout.moveDown")}
                        onClick={() => moveQuestion(questionIndex, 1)}
                      >
                        <ChevronDown className="h-3.5 w-3.5" />
                      </button>
                    </div>
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
                            (selection?.kind === "question" &&
                              selection.regionId === region.region_id) ||
                              multiHas({
                                kind: "question",
                                questionId: question.question_id,
                                regionId: region.region_id || "",
                              })
                              ? "bg-blue-100 font-semibold text-blue-800"
                              : "text-slate-600 hover:bg-slate-100",
                          )}
                          onClick={(event) => {
                            // 左侧功能栏多选删除（11.10-1）：Ctrl/⌘+点 加入/移出多选集
                            if (event.ctrlKey || event.metaKey) {
                              toggleMulti({
                                kind: "question",
                                questionId: question.question_id,
                                regionId: region.region_id || "",
                              });
                              return;
                            }
                            selectQuestion(question, region.region_id);
                          }}
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
                              (selection?.kind === "answer" &&
                                selection.slotId === slot.slot_id) ||
                                multiHas({
                                  kind: "answer",
                                  questionId: question.question_id,
                                  slotId: slot.slot_id || "",
                                })
                                ? "bg-amber-100 font-semibold text-amber-800"
                                : "text-slate-600 hover:bg-slate-100",
                            )}
                            onClick={(event) => {
                              // 左侧功能栏多选删除（11.10-1）：Ctrl/⌘+点 加入/移出多选集
                              if (event.ctrlKey || event.metaKey) {
                                toggleMulti({
                                  kind: "answer",
                                  questionId: question.question_id,
                                  slotId: slot.slot_id || "",
                                });
                                return;
                              }
                              setSelection({
                                kind: "answer",
                                questionId: question.question_id,
                                slotId: slot.slot_id || "",
                              });
                              setMultiSelections([]);
                              setTargetQuestionId(question.question_id);
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
                                placeholder="1"
                                value={slot.max_score ?? ""}
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
                  setTargetQuestionId(selectedQuestion.question_id);
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
                disabled={!selection && !multiSelections.length}
                onClick={removeSelected}
                title={`${t("grading.layout.deleteSelected")} (Del / Backspace)`}
                className="gap-1.5"
              >
                <X className="h-4 w-4" />
                {t("grading.layout.deleteSelected")}
                {multiSelections.length > 1
                  ? ` (${multiSelections.length})`
                  : ""}
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
                        if (editMode === "select") {
                          // 空白处点一下清选择（11.10-1）：多选从零开始
                          setSelection(null);
                          setMultiSelections([]);
                          return;
                        }
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
                          const focused =
                            selection?.kind === "question" &&
                            selection.regionId === region.region_id;
                          const active = focused || multiHas(target);
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
                                  // Ctrl/⌘+点=多选切换（11.10-1）
                                  if (event.ctrlKey || event.metaKey) {
                                    event.preventDefault();
                                    event.stopPropagation();
                                    toggleMulti(target);
                                    return;
                                  }
                                  if (
                                    editMode === "select" ||
                                    editMode === "question"
                                  ) {
                                    // 11.10-3：题框在分题模式下也能拖动/微调，不用回点「选择」
                                    startDrag(event, target, "move");
                                    return;
                                  }
                                  // 作答区模式：起笔落在题区内=框选作答区
                                  //（不拦截，冒泡到 svg 起画），保持原行为
                                }}
                              />
                              {renderLabel(
                                region.label || String(question.display_no),
                                box[0],
                                box[1],
                                "#2563eb",
                              )}
                              {focused &&
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
                          const focused =
                            selection?.kind === "answer" &&
                            selection.slotId === slot.slot_id;
                          const active = focused || multiHas(target);
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
                                  // Ctrl/⌘+点=多选切换（11.10-1）
                                  if (event.ctrlKey || event.metaKey) {
                                    event.preventDefault();
                                    event.stopPropagation();
                                    toggleMulti(target);
                                    return;
                                  }
                                  // 11.10-3：作答区任意模式下都能拖动/微调，不用回点「选择」
                                  startDrag(event, target, "move");
                                }}
                              />
                              {renderLabel(
                                slot.label || `${question.display_no}_1`,
                                box[0],
                                box[1],
                                "#b45309",
                              )}
                              {focused &&
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
            onClick={() => handleOpenChange(false)}
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
