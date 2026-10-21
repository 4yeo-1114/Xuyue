import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useLocale } from "@/contexts/LocaleContext";
import {
  TAG_DIFFICULTY_OPTIONS,
  collectPatchFromForm,
  formatKnowledgePoints,
  parseKnowledgePointsInput,
  type QuestionTag,
  type QuestionTagPatch,
} from "./questionTagUtils";

const DIFFICULTY_CLEAR = "__all__";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 目标题数（工具条文案用） */
  count: number;
  /** 单行编辑时的已有标签（批量打标传 null，只做部分覆盖） */
  initial?: QuestionTag | null;
  /** 保存：返回是否成功（父级负责调 API） */
  onSave: (patch: QuestionTagPatch) => Promise<void> | void;
  saving?: boolean;
};

/**
 * 打标小编辑器：单元 / 知识点（多值）/ 难度（易中难）/ 题型。
 * 批量模式下空字段 = 本次不改（部分更新）；单行模式预填已有标签。
 */
export function QuestionTagEditor({
  open,
  onOpenChange,
  count,
  initial,
  onSave,
  saving,
}: Props) {
  const { t } = useLocale();
  const [unit, setUnit] = useState("");
  const [knowledgePoints, setKnowledgePoints] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [questionType, setQuestionType] = useState("");

  // 打开时回填（单行预填已有标签；批量从空开始）
  useEffect(() => {
    if (!open) return;
    setUnit(initial?.unit ?? "");
    setKnowledgePoints(formatKnowledgePoints(initial?.knowledge_points));
    setDifficulty(initial?.difficulty ?? "");
    setQuestionType(initial?.question_type ?? "");
  }, [open, initial]);

  const handleSave = async () => {
    const patch = collectPatchFromForm({
      unit,
      knowledge_points: knowledgePoints,
      difficulty,
      question_type: questionType,
    });
    // 单行编辑允许清空：四个字段都空时也提交，让父级用空 patch 覆盖语义处理
    if (initial && Object.keys(patch).length === 0) {
      await onSave({
        unit: "",
        knowledge_points: [],
        difficulty: "",
        question_type: "",
      });
      return;
    }
    await onSave(patch);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            {initial
              ? t("questionBank.tag.editTitle", undefined, "编辑标签")
              : t("questionBank.tag.batchTitle", { count }, `批量打标（${count} 题）`)}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="tag-unit">{t("questionBank.tag.unit", undefined, "单元")}</Label>
            <Input
              id="tag-unit"
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
              placeholder={t("questionBank.tag.unitPlaceholder", undefined, "例如：第一单元")}
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="tag-kp">
              {t("questionBank.tag.knowledgePoints", undefined, "知识点")}
            </Label>
            <Input
              id="tag-kp"
              value={knowledgePoints}
              onChange={(e) => setKnowledgePoints(e.target.value)}
              placeholder={t(
                "questionBank.tag.knowledgePointsPlaceholder",
                undefined,
                "多个用逗号分隔，如：分数,小数",
              )}
            />
            {parseKnowledgePointsInput(knowledgePoints).length > 0 && (
              <p className="text-xs text-muted-foreground">
                {t("questionBank.tag.knowledgePointsHint", { count: parseKnowledgePointsInput(knowledgePoints).length }, "已识别 {count} 个知识点")}
              </p>
            )}
          </div>

          <div className="space-y-1">
            <Label>{t("questionBank.tag.difficulty", undefined, "难度")}</Label>
            <Select
              value={difficulty || DIFFICULTY_CLEAR}
              onValueChange={(v) => setDifficulty(v === DIFFICULTY_CLEAR ? "" : v)}
            >
              <SelectTrigger>
                <SelectValue placeholder={t("questionBank.tag.difficultyPlaceholder", undefined, "选择难度")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={DIFFICULTY_CLEAR}>
                  {t("questionBank.tag.keepOrClear", undefined, "不改 / 清空")}
                </SelectItem>
                {TAG_DIFFICULTY_OPTIONS.map((d) => (
                  <SelectItem key={d} value={d}>
                    {t(`questionBank.tag.difficulty.${d}`, undefined, d)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label htmlFor="tag-qtype">{t("questionBank.tag.questionType", undefined, "题型")}</Label>
            <Input
              id="tag-qtype"
              value={questionType}
              onChange={(e) => setQuestionType(e.target.value)}
              placeholder={t("questionBank.tag.questionTypePlaceholder", undefined, "例如：选择题")}
            />
          </div>

          {!initial && (
            <p className="text-xs text-muted-foreground">
              {t("questionBank.tag.partialHint", undefined, "留空的字段不会修改已有标签。")}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            {t("common.cancel", undefined, "取消")}
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving
              ? t("questionBank.tag.saving", undefined, "保存中…")
              : t("questionBank.tag.apply", undefined, "应用")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
