import { useEffect, useMemo, useRef, useState } from "react";
import { Frame, Loader2, RefreshCw, Save, Undo2, Upload } from "lucide-react";
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
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useLocale } from "@/contexts/LocaleContext";
import {
  gradingImageUrl,
  type ReferenceAnswerEntry,
  type ReferenceAnswerSlotItem,
  type ReferenceAnswerTablePage,
} from "@/services/gradingApi";

export type AnswerTableEdit = {
  display_index: number;
  printed_no?: string;
  slots: Array<{ sub_index: number; answer_text: string }>;
};

type Draft = { printed_no: string; slots: Record<number, string> };

type Props = {
  open: boolean;
  pages: ReferenceAnswerTablePage[];
  loading?: boolean;
  saving?: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (pageNo: number, questions: AnswerTableEdit[]) => Promise<void> | void;
  onRebuild: (resetEdits: boolean) => Promise<void> | void;
  /** 空白卷模式第二上传：答案单独一张纸，上传后按印刷题号把答案合并进本表 */
  onUploadAnswerSheets?: (files: File[]) => Promise<void> | void;
  /** 答题区框修改：和切题审查一样的框编辑器，识别错了改框，确认后按新框重建本表 */
  onEditBoxes?: (pageNo: number) => Promise<void> | void;
};

function draftKey(pageNo: number, displayIndex: number): string {
  return `${pageNo}:${displayIndex}`;
}

function originalNo(entry: ReferenceAnswerEntry): string {
  return String(entry.printed_no ?? entry.display_index ?? "").trim();
}

function entryToDraft(entry: ReferenceAnswerEntry): Draft {
  return {
    printed_no: originalNo(entry),
    slots: Object.fromEntries(
      (entry.slots || []).map((slot) => [slot.sub_index, slot.answer_text || ""]),
    ),
  };
}

function isDirty(entry: ReferenceAnswerEntry, draft?: Draft): boolean {
  if (!draft) return false;
  if ((draft.printed_no || "").trim() !== originalNo(entry)) return true;
  for (const slot of entry.slots || []) {
    if ((draft.slots[slot.sub_index] ?? "") !== (slot.answer_text || "")) return true;
  }
  return false;
}

/** 答题区缩略图：服务端按 bbox 裁好的 JPEG 直链（跨域画布裁剪会污染，只能后端裁）。
 *  框识别错了可点缩略图进切题审查同款框编辑器改框。 */
function RegionThumb({
  slot,
  pageNo,
  onEditBoxes,
}: {
  slot: ReferenceAnswerSlotItem;
  pageNo?: number;
  onEditBoxes?: (pageNo: number) => Promise<void> | void;
}) {
  const { t } = useLocale();
  const src = gradingImageUrl(slot.region_url);
  if (!src) return null;
  const img = (
    <img
      src={src}
      alt={t("grading.answerTable.regionAlt")}
      title={t("grading.answerTable.regionAlt")}
      loading="lazy"
      className="mt-1 h-14 w-24 shrink-0 rounded border bg-white object-cover"
    />
  );
  if (!onEditBoxes || pageNo == null) return img;
  return (
    <button
      type="button"
      title={t("grading.answerTable.boxEditHint")}
      onClick={() => void onEditBoxes(pageNo)}
      className="shrink-0 cursor-pointer"
    >
      {img}
    </button>
  );
}

/** 答题区框总览：整页图 + 每空 amber 虚线框（与切题审查同坐标系拉伸），一眼看清 AI 框在哪。
 *  点任意框进切题审查同款框编辑器修改。 */
function BoxMap({
  page,
  onEditBoxes,
}: {
  page: ReferenceAnswerTablePage;
  onEditBoxes?: (pageNo: number) => Promise<void> | void;
}) {
  const { t } = useLocale();
  const src = gradingImageUrl(page.image_url);
  const size = page.image_size;
  const boxes = useMemo(() => {
    const list: Array<{
      key: string;
      label: string;
      bbox: [number, number, number, number];
    }> = [];
    for (const entry of page.questions || []) {
      for (const slot of entry.slots || []) {
        if (!slot.bbox) continue;
        list.push({
          key: `${entry.display_index}:${slot.sub_index}`,
          label: `${originalNo(entry)}_${slot.sub_index}`,
          bbox: slot.bbox,
        });
      }
    }
    return list;
  }, [page]);
  if (!src || !size || size[0] <= 0 || size[1] <= 0 || !boxes.length) return null;
  const [imageWidth, imageHeight] = size;
  // 字号/描边按批改图宽度定比例：SVG viewBox 会整体缩放到显示尺寸
  const fontSize = Math.max(imageWidth * 0.02, 11);
  const labelH = fontSize * 1.35;
  return (
    <div
      className="relative mb-3 overflow-hidden rounded-md border bg-white"
      style={{ aspectRatio: `${imageWidth} / ${imageHeight}` }}
    >
      {/* 预览图尺寸可能与批改图不同：object-fill 拉满坐标系（与切题审查编辑器同款对齐） */}
      <img
        src={src}
        alt={t("grading.answerTable.boxMapAlt")}
        className="absolute inset-0 h-full w-full"
        style={{ objectFit: "fill" }}
      />
      <svg
        viewBox={`0 0 ${imageWidth} ${imageHeight}`}
        className={cn(
          "absolute inset-0 h-full w-full",
          onEditBoxes && "cursor-pointer",
        )}
        onClick={onEditBoxes ? () => void onEditBoxes(page.page_no) : undefined}
      >
        {boxes.map((box) => {
          const [x1, y1, x2, y2] = box.bbox;
          const w = Math.max(x2 - x1, 1);
          const h = Math.max(y2 - y1, 1);
          const labelW = fontSize * 0.62 * box.label.length + fontSize * 0.5;
          const labelY = Math.max(y1 - labelH, 0);
          return (
            <g key={box.key}>
              <rect
                x={x1}
                y={y1}
                width={w}
                height={h}
                fill="none"
                stroke="#d97706"
                strokeWidth={Math.max(imageWidth * 0.003, 2)}
                strokeDasharray={`${imageWidth * 0.012} ${imageWidth * 0.008}`}
                rx={Math.max(imageWidth * 0.004, 2)}
              />
              {/* 标签贴框上缘外侧：底色块 + 白粗字（与切题审查 renderLabel 同款） */}
              <rect
                x={x1}
                y={labelY}
                width={labelW}
                height={labelH}
                fill="#d97706"
                rx={Math.max(imageWidth * 0.003, 2)}
              />
              <text
                x={x1 + fontSize * 0.25}
                y={labelY + labelH * 0.76}
                fill="#fff"
                fontSize={fontSize}
                fontWeight={700}
              >
                {box.label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/** 标准答案识别表：自动列出每道题识别出的答案，识别有误可手动修改后保存。 */
export function StandardAnswerTableDialog({
  open,
  pages,
  loading,
  saving,
  onOpenChange,
  onSave,
  onRebuild,
  onUploadAnswerSheets,
  onEditBoxes,
}: Props) {
  const { t } = useLocale();
  const [activePageNo, setActivePageNo] = useState<number | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [uploadingAnswers, setUploadingAnswers] = useState(false);
  const answerInputRef = useRef<HTMLInputElement>(null);

  const handleAnswerFiles = async (files: File[]) => {
    if (!files.length || !onUploadAnswerSheets || uploadingAnswers) return;
    setUploadingAnswers(true);
    try {
      await onUploadAnswerSheets(files);
    } finally {
      setUploadingAnswers(false);
    }
  };

  const activePage = useMemo(() => {
    if (!pages.length) return null;
    return (
      pages.find((page) => page.page_no === activePageNo) || pages[0] || null
    );
  }, [pages, activePageNo]);

  // 空白卷模式：全部作答区都没识别到答案文字 → 只展示答题区，提示可手填
  // （只看识别结果不看草稿：手填保存后 answer_text 会带上文字，横幅自然消失）
  const blankPaper = useMemo(() => {
    const entries = activePage?.questions || [];
    if (!entries.length) return false;
    return entries.every((entry) =>
      (entry.slots || []).every((slot) => !(slot.answer_text || "").trim()),
    );
  }, [activePage]);

  useEffect(() => {
    if (!open) return;
    if (activePageNo == null && pages.length) {
      setActivePageNo(pages[0].page_no);
    }
  }, [open, pages, activePageNo]);

  const dirtyEdits = useMemo(() => {
    if (!activePage) return [] as AnswerTableEdit[];
    const edits: AnswerTableEdit[] = [];
    for (const entry of activePage.questions || []) {
      if (!entry || !isDirty(entry, drafts[draftKey(activePage.page_no, entry.display_index)])) {
        continue;
      }
      const draft = drafts[draftKey(activePage.page_no, entry.display_index)]!;
      edits.push({
        display_index: entry.display_index,
        printed_no: (draft.printed_no || "").trim() || undefined,
        slots: (entry.slots || []).map((slot) => ({
          sub_index: slot.sub_index,
          answer_text: draft.slots[slot.sub_index] ?? "",
        })),
      });
    }
    return edits;
  }, [activePage, drafts]);

  const setSlotText = (
    pageNo: number,
    entry: ReferenceAnswerEntry,
    subIndex: number,
    value: string,
  ) => {
    const key = draftKey(pageNo, entry.display_index);
    setDrafts((prev) => {
      const base = prev[key] || entryToDraft(entry);
      return {
        ...prev,
        [key]: { ...base, slots: { ...base.slots, [subIndex]: value } },
      };
    });
  };

  const setPrintedNo = (
    pageNo: number,
    entry: ReferenceAnswerEntry,
    value: string,
  ) => {
    const key = draftKey(pageNo, entry.display_index);
    setDrafts((prev) => {
      const base = prev[key] || entryToDraft(entry);
      return { ...prev, [key]: { ...base, printed_no: value } };
    });
  };

  const handleSave = async () => {
    if (!activePage || saving || loading || !dirtyEdits.length) return;
    try {
      await onSave(activePage.page_no, dirtyEdits);
      setDrafts((prev) => {
        const next = { ...prev };
        for (const edit of dirtyEdits) {
          delete next[draftKey(activePage.page_no, edit.display_index)];
        }
        return next;
      });
    } catch {
      // 保存失败保留草稿，老师可继续改
    }
  };

  const handleRebuild = async (resetEdits: boolean) => {
    if (loading || saving) return;
    if (
      resetEdits &&
      !window.confirm(t("grading.answerTable.resetConfirm"))
    ) {
      return;
    }
    if (resetEdits) setDrafts({});
    await onRebuild(resetEdits);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="standard-answer-table-dialog"
        className="max-w-3xl max-h-[86vh] flex flex-col overflow-hidden"
      >
        <DialogHeader>
          <DialogTitle>{t("grading.answerTable.title")}</DialogTitle>
          <DialogDescription>
            {t("grading.answerTable.description")}
          </DialogDescription>
        </DialogHeader>

        {pages.length > 1 && (
          <div className="flex flex-wrap items-center gap-2">
            {pages.map((page) => (
              <Button
                key={page.page_no}
                type="button"
                size="sm"
                variant={
                  activePage?.page_no === page.page_no ? "default" : "outline"
                }
                onClick={() => setActivePageNo(page.page_no)}
              >
                {t("grading.answerTable.pageTab", { page: page.page_no })}
              </Button>
            ))}
          </div>
        )}

        <div className="flex items-center justify-between gap-2">
          <div className="text-sm text-muted-foreground">
            {activePage
              ? t("grading.answerTable.pageInfo", {
                  page: activePage.page_no,
                  count: (activePage.questions || []).length,
                })
              : ""}
            {dirtyEdits.length > 0 && (
              <span className="ml-2 text-amber-600">
                {t("grading.answerTable.unsaved", { count: dirtyEdits.length })}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {onEditBoxes && activePage && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={loading || saving}
                title={t("grading.answerTable.boxEditHint")}
                onClick={() => void onEditBoxes(activePage.page_no)}
              >
                <Frame className="w-4 h-4" />
                {t("grading.answerTable.boxEdit")}
              </Button>
            )}
            {onUploadAnswerSheets && (
              <>
                <input
                  ref={answerInputRef}
                  type="file"
                  accept="image/*,.pdf,.doc,.docx"
                  multiple
                  className="hidden"
                  onChange={(event) => {
                    // 先快照再清 value：Chrome 的 input.files 是活列表，先清 value 会把
                    // 刚选的文件也清空 → 后面读到 length=0 静默 return（点上传答案没反应的根因）
                    const files = Array.from(event.target.files || []);
                    event.target.value = "";
                    void handleAnswerFiles(files);
                  }}
                />
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={loading || saving || uploadingAnswers}
                  onClick={() => answerInputRef.current?.click()}
                >
                  {uploadingAnswers ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Upload className="w-4 h-4" />
                  )}
                  {t("grading.answerTable.uploadAnswers")}
                </Button>
              </>
            )}
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={loading || saving}
              onClick={() => void handleRebuild(false)}
            >
              {loading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <RefreshCw className="w-4 h-4" />
              )}
              {t("grading.answerTable.rebuild")}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={loading || saving}
              onClick={() => void handleRebuild(true)}
            >
              <Undo2 className="w-4 h-4" />
              {t("grading.answerTable.rebuildReset")}
            </Button>
          </div>
        </div>

        {/* 滚动区用嵌套 flex：滚动区自己当 flex 子项拿高度开 overflow-y-auto。
            别用 h-full 百分比高度——对 flex 派生高度解析失败会回退 auto，永远不滚 */}
        <div className="relative flex min-h-0 flex-1 flex-col">
          {loading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-background/70">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="w-4 h-4 animate-spin" />
                {t("grading.answerTable.loading")}
              </div>
            </div>
          )}
          <div className="min-h-0 flex-1 overflow-y-auto pr-3">
            {activePage?.error ? (
              <div className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {activePage.error}
              </div>
            ) : null}
            {!loading && (activePage?.questions || []).length === 0 ? (
              <div className="py-10 text-center text-sm text-muted-foreground">
                {t("grading.answerTable.empty")}
              </div>
            ) : null}
            {blankPaper && !loading ? (
              <div className="mb-3 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-800">
                {t("grading.answerTable.blankPaperHint")}
              </div>
            ) : null}
            {activePage && !loading ? (
              <BoxMap page={activePage} onEditBoxes={onEditBoxes} />
            ) : null}
            <div className="space-y-3">
              {(activePage?.questions || []).map((entry) => {
                const key = draftKey(
                  activePage!.page_no,
                  entry.display_index,
                );
                const draft = drafts[key] || entryToDraft(entry);
                const dirty = isDirty(entry, drafts[key]);
                return (
                  <div
                    key={key}
                    className={cn(
                      "rounded-lg border px-3 py-2",
                      dirty && "border-amber-400/80 bg-amber-50/40",
                    )}
                  >
                    <div className="mb-1 flex items-center gap-1 text-sm font-medium">
                      <span>{t("grading.answerTable.noLabel")}</span>
                      <Input
                        className="h-7 w-16 px-2 text-center"
                        value={draft.printed_no}
                        onChange={(event) =>
                          setPrintedNo(activePage!.page_no, entry, event.target.value)
                        }
                      />
                      <span>{t("grading.answerTable.questionSuffix")}</span>
                      {entry.edited && (
                        <Badge variant="secondary" className="ml-1">
                          {t("grading.answerTable.edited")}
                        </Badge>
                      )}
                    </div>
                    {(entry.slots || []).length <= 1 ? (
                      <div className="flex items-start gap-2">
                        <RegionThumb
                          slot={(entry.slots || [])[0] ?? { sub_index: 1, answer_text: "" }}
                          pageNo={activePage!.page_no}
                          onEditBoxes={onEditBoxes}
                        />
                        <Textarea
                          className="min-h-[44px] flex-1 text-sm"
                          value={
                            draft.slots[(entry.slots || [])[0]?.sub_index ?? 1] ?? ""
                          }
                          onChange={(event) =>
                            setSlotText(
                              activePage!.page_no,
                              entry,
                              (entry.slots || [])[0]?.sub_index ?? 1,
                              event.target.value,
                            )
                          }
                        />
                      </div>
                    ) : (
                      <div className="space-y-1.5">
                        {(entry.slots || []).map((slot, slotIndex) => (
                          <div
                            key={slot.sub_index}
                            className="flex items-start gap-2"
                          >
                            <span className="mt-1.5 w-10 shrink-0 text-xs text-muted-foreground">
                              {t("grading.answerTable.blank", {
                                index: slotIndex + 1,
                              })}
                            </span>
                            <RegionThumb
                              slot={slot}
                              pageNo={activePage!.page_no}
                              onEditBoxes={onEditBoxes}
                            />
                            <Textarea
                              className="min-h-[36px] flex-1 text-sm"
                              value={draft.slots[slot.sub_index] ?? ""}
                              onChange={(event) =>
                                setSlotText(
                                  activePage!.page_no,
                                  entry,
                                  slot.sub_index,
                                  event.target.value,
                                )
                              }
                            />
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("grading.answerTable.close")}
          </Button>
          <Button
            onClick={() => void handleSave()}
            disabled={loading || saving || dirtyEdits.length === 0}
            className="gap-2"
          >
            {saving ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            {t("grading.answerTable.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
