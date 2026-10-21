import { useState } from "react";
import { Loader2, RefreshCw, Trash2, PenLine, Check } from "lucide-react";
import { AIGeneratedBadge } from "@/components/common/AIGeneratedBadge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useLocale } from "@/contexts/LocaleContext";
import { cn } from "@/lib/utils";
import type { WrongAnnotation } from "@/services/gradingApi";

export type WrongAnnotationCardProps = {
  /** 题号 key（与后端 wrong_annotations 键一致） */
  questionKey: string;
  /** 当前批注；null/undefined = 还没有 */
  annotation?: WrongAnnotation | null;
  /** 该题是否判错/半对（错题才有「重新生成」） */
  wrong?: boolean;
  /** 正在生成（该题） */
  regenerating?: boolean;
  /** 编辑文本（老师改过 → edited=true，来源不变） */
  onEditText: (text: string) => void;
  /** 重新生成 AI 稿 */
  onRegenerate?: () => void;
  /** 改为手动（来源置 manual） */
  onMarkManual: () => void;
  /** 删除批注 */
  onDelete: () => void;
  /** 整卡置灰（如该题已改判成对） */
  muted?: boolean;
  className?: string;
};

/** 判错原因批注编辑卡：文本 + AI/手动徽标 + 编辑/重生成/改手动/删除。 */
export function WrongAnnotationCard({
  questionKey,
  annotation,
  wrong = true,
  regenerating = false,
  onEditText,
  onRegenerate,
  onMarkManual,
  onDelete,
  muted = false,
  className,
}: WrongAnnotationCardProps) {
  const { t } = useLocale();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  const text = annotation?.text ?? "";
  const source = annotation?.source ?? "manual";
  const edited = annotation?.edited ?? false;
  const has = Boolean(annotation && (annotation.text || annotation.source));

  const startEdit = () => {
    setDraft(text);
    setEditing(true);
  };
  const commitEdit = () => {
    setEditing(false);
    if (draft !== text) onEditText(draft.trim());
  };

  return (
    <div
      className={cn(
        "rounded-lg border border-orange-200 bg-orange-50/60 px-2.5 py-2",
        muted && "opacity-60",
        className,
      )}
      data-question-key={questionKey}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[11px] font-semibold text-orange-700">
          {t("grading.wrongAnnotation.title", undefined, "错因批注")}
        </span>
        {has && source === "ai" && !edited && <AIGeneratedBadge />}
        {has && source === "ai" && edited && (
          <span className="inline-flex items-center rounded-full border border-orange-300 bg-orange-100 px-2 py-0.5 text-[10px] font-medium text-orange-800">
            {t("grading.wrongAnnotation.aiEdited", undefined, "AI稿·已编辑")}
          </span>
        )}
        {has && source === "manual" && (
          <span className="inline-flex items-center rounded-full border border-border/70 bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
            {t("grading.wrongAnnotation.manual", undefined, "手动批注")}
          </span>
        )}
        <span className="ml-auto flex items-center gap-1">
          {regenerating ? (
            <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" />
              {t("grading.wrongAnnotation.generating", undefined, "生成中…")}
            </span>
          ) : (
            <>
              {!editing && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 px-1.5 text-[11px] text-muted-foreground"
                  onClick={startEdit}
                >
                  <PenLine className="h-3 w-3 mr-0.5" />
                  {t("grading.wrongAnnotation.edit", undefined, "编辑")}
                </Button>
              )}
              {wrong && onRegenerate && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 px-1.5 text-[11px] text-muted-foreground"
                  onClick={onRegenerate}
                >
                  <RefreshCw className="h-3 w-3 mr-0.5" />
                  {t("grading.wrongAnnotation.regenerate", undefined, "重新生成")}
                </Button>
              )}
              {has && source === "ai" && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 px-1.5 text-[11px] text-muted-foreground"
                  onClick={onMarkManual}
                >
                  {t("grading.wrongAnnotation.toManual", undefined, "改为手动")}
                </Button>
              )}
              {has && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 px-1.5 text-[11px] text-destructive/80 hover:text-destructive"
                  onClick={onDelete}
                >
                  <Trash2 className="h-3 w-3 mr-0.5" />
                  {t("grading.wrongAnnotation.delete", undefined, "删除")}
                </Button>
              )}
            </>
          )}
        </span>
      </div>
      {editing ? (
        <div className="mt-1.5 space-y-1">
          <Textarea
            value={draft}
            autoFocus
            onChange={(e) => setDraft(e.target.value)}
            placeholder={t(
              "grading.wrongAnnotation.placeholder",
              undefined,
              "写给学生看的一句错因（会打印在该题下方）",
            )}
            className="min-h-[48px] text-xs leading-relaxed"
          />
          <div className="flex justify-end gap-1">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-[11px]"
              onClick={() => setEditing(false)}
            >
              {t("common.cancel", undefined, "取消")}
            </Button>
            <Button
              type="button"
              size="sm"
              className="h-6 px-2 text-[11px]"
              onClick={commitEdit}
            >
              <Check className="h-3 w-3 mr-0.5" />
              {t("common.confirm", undefined, "确定")}
            </Button>
          </div>
        </div>
      ) : has ? (
        <div
          className={cn(
            "mt-1 cursor-text whitespace-pre-wrap text-xs leading-relaxed text-orange-900",
            !text && "italic text-muted-foreground",
          )}
          onClick={startEdit}
        >
          {text ||
            t("grading.wrongAnnotation.empty", undefined, "（未填写，点击编辑）")}
        </div>
      ) : (
        <div className="mt-1 flex items-center gap-2">
          <span className="text-xs italic text-muted-foreground">
            {wrong
              ? t(
                  "grading.wrongAnnotation.notGenerated",
                  undefined,
                  "暂无批注，可点「重新生成」或手动编写",
                )
              : t(
                  "grading.wrongAnnotation.manualOnly",
                  undefined,
                  "可手动编写批注",
                )}
          </span>
          {!editing && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-6 px-1.5 text-[11px]"
              onClick={startEdit}
            >
              <PenLine className="h-3 w-3 mr-0.5" />
              {t("grading.wrongAnnotation.write", undefined, "手动编写")}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
