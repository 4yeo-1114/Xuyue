import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DEFAULT_DIMENSIONS,
  type EssayDimension,
  type EssayScorePayload,
} from "@/services/gradingApi";
import { Loader2, Plus, RotateCcw, Trash2 } from "lucide-react";

type TranslateFn = (
  key: string,
  params?: Record<string, string | number>,
  fallback?: string,
) => string;

/** 解析 rubric.dimensions_json；为空/非法时回退默认五维（返回副本，避免共享引用被编辑污染） */
export function parseEssayDimensions(json?: string | null): EssayDimension[] {
  if (json) {
    try {
      const parsed = JSON.parse(json);
      if (Array.isArray(parsed)) {
        const dims = parsed.filter(
          (d): d is EssayDimension =>
            !!d &&
            typeof d === "object" &&
            typeof (d as { key?: unknown }).key === "string",
        );
        if (dims.length > 0) return dims;
      }
    } catch {
      // 忽略非法 JSON，走默认
    }
  }
  return DEFAULT_DIMENSIONS.map((d) => ({ ...d }));
}

/** Rubric 弹窗内的「评分维度」配置编辑区：名称/满分/描述，支持增删行。 */
export function EssayDimensionConfigEditor({
  dimensions,
  onChange,
  t,
}: {
  dimensions: EssayDimension[];
  onChange: (dims: EssayDimension[]) => void;
  t: TranslateFn;
}) {
  const updateRow = (index: number, patch: Partial<EssayDimension>) => {
    onChange(dimensions.map((d, i) => (i === index ? { ...d, ...patch } : d)));
  };
  const removeRow = (index: number) => {
    onChange(dimensions.filter((_, i) => i !== index));
  };
  const addRow = () => {
    const order = dimensions.reduce(
      (max, d) => Math.max(max, Number(d.order) || 0),
      0,
    );
    onChange([
      ...dimensions,
      {
        key: `dim_${Date.now().toString(36)}${Math.floor(Math.random() * 1e4).toString(36)}`,
        name: t("grading.dimension.newDimension"),
        full_score: 10,
        weight: 0,
        description: "",
        order: order + 1,
      },
    ]);
  };
  const restoreDefault = () => {
    onChange(DEFAULT_DIMENSIONS.map((d) => ({ ...d })));
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Label className="text-sm font-bold text-primary">
          {t("grading.dimension.title")}
        </Label>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={restoreDefault}
            className="gap-1.5"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            {t("grading.dimension.restoreDefault")}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={addRow}
            className="gap-1.5"
          >
            <Plus className="h-3.5 w-3.5" />
            {t("grading.dimension.add")}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)_5rem_minmax(0,1.6fr)_2rem] items-center gap-2 px-1">
        <Label className="text-xs font-normal text-muted-foreground">
          {t("grading.dimension.namePlaceholder")}
        </Label>
        <Label className="text-xs font-normal text-muted-foreground">
          {t("grading.dimension.fullScoreLabel")}
        </Label>
        <Label className="text-xs font-normal text-muted-foreground">
          {t("grading.dimension.descPlaceholder")}
        </Label>
        <span />
      </div>

      {dimensions.map((d, idx) => (
        <div
          key={d.key}
          className="grid grid-cols-[minmax(0,1fr)_5rem_minmax(0,1.6fr)_2rem] items-center gap-2"
        >
          <Input
            value={d.name}
            onChange={(e) => updateRow(idx, { name: e.target.value })}
            placeholder={t("grading.dimension.namePlaceholder")}
            className="h-9 text-sm"
          />
          <Input
            type="number"
            value={
              Number.isFinite(Number(d.full_score)) ? String(d.full_score) : ""
            }
            onChange={(e) =>
              updateRow(idx, {
                full_score: Math.max(0, Number(e.target.value) || 0),
              })
            }
            aria-label={`${d.name}-${t("grading.dimension.fullScoreLabel")}`}
            className="h-9 text-sm"
          />
          <Input
            value={d.description || ""}
            onChange={(e) => updateRow(idx, { description: e.target.value })}
            placeholder={t("grading.dimension.descPlaceholder")}
            className="h-9 text-sm"
          />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-9 w-9 px-0 text-destructive hover:text-destructive"
            onClick={() => removeRow(idx)}
            aria-label={t("grading.dimension.delete")}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      ))}
    </div>
  );
}

/** 改分弹窗内的维度分输入表单。提交时回调整分 payload（不含 filename，由上层补充）。 */
function EditScoreForm({
  dimensions,
  initialScores,
  onCancel,
  onSave,
  t,
}: {
  dimensions: EssayDimension[];
  initialScores: Record<string, number>;
  onCancel: () => void;
  onSave: (
    payload: Omit<EssayScorePayload, "filename">,
  ) => Promise<void> | void;
  t: TranslateFn;
}) {
  const [values, setValues] = useState<Record<string, string>>(() => {
    const v: Record<string, string> = {};
    for (const d of dimensions) {
      v[d.key] = String(Number(initialScores?.[d.key]) || 0);
    }
    return v;
  });
  const [submitting, setSubmitting] = useState(false);

  const dimension_scores: Record<string, number> = {};
  let total = 0;
  for (const d of dimensions) {
    const n = Math.max(0, Number(values[d.key]) || 0);
    dimension_scores[d.key] = n;
    total += n;
  }

  const submit = async (regenerate: boolean) => {
    setSubmitting(true);
    try {
      await onSave({
        dimension_scores,
        total_score: total,
        ...(regenerate ? { regenerate_report: true } : {}),
      });
    } catch {
      // 上层已 toast 错误，保持弹窗打开供修改
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <div className="space-y-3">
        {dimensions.map((d) => (
          <div key={d.key} className="flex items-center justify-between gap-3">
            <div className="min-w-0 flex-1">
              <Label className="text-sm text-foreground">{d.name}</Label>
              <p className="truncate text-xs text-muted-foreground">
                {t("grading.dimension.fullScoreLabel")}:{" "}
                {Number(d.full_score) || 0}
              </p>
            </div>
            <Input
              type="number"
              min={0}
              value={values[d.key]}
              onChange={(e) =>
                setValues((prev) => ({ ...prev, [d.key]: e.target.value }))
              }
              aria-label={`${d.name}-${t("grading.dimension.scorePlaceholder")}`}
              className="h-9 w-24 text-sm"
            />
          </div>
        ))}
        <div className="flex items-center justify-between border-t border-border pt-2">
          <span className="text-sm text-muted-foreground">
            {t("grading.dimension.sumLabel")}
          </span>
          <span className="text-base font-bold text-primary">{total}</span>
        </div>
      </div>
      <DialogFooter className="gap-2 sm:gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={submitting}
        >
          {t("common.cancel")}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => void submit(true)}
          disabled={submitting}
          className="gap-1.5"
        >
          {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
          {t("grading.dimension.saveAndRegenerate")}
        </Button>
        <Button
          type="button"
          onClick={() => void submit(false)}
          disabled={submitting}
          className="gap-1.5"
        >
          {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
          {t("grading.dimension.save")}
        </Button>
      </DialogFooter>
    </>
  );
}

/** 作文批改结果区的维度分展示卡：维度条 + 总分 + 改分入口（无 dimension_scores 时整体不渲染，兼容老数据）。 */
export function EssayDimensionScoreCard({
  dimensions,
  dimensionScores,
  totalScore,
  essayGrade,
  filename,
  onSave,
  t,
}: {
  dimensions: EssayDimension[];
  dimensionScores?: Record<string, number> | null;
  totalScore?: number | null;
  essayGrade?: string | null;
  filename: string;
  onSave: (payload: EssayScorePayload) => Promise<void> | void;
  t: TranslateFn;
}) {
  const [open, setOpen] = useState(false);

  if (
    !dimensionScores ||
    Object.keys(dimensionScores).length === 0 ||
    dimensions.length === 0
  ) {
    return null;
  }

  const handleSave = (payload: Omit<EssayScorePayload, "filename">) => {
    const result = onSave({ ...payload, filename });
    if (result && typeof (result as Promise<void>).then === "function") {
      (result as Promise<void>)
        .then(() => setOpen(false))
        .catch(() => {
          // 父级已 toast 错误，保持弹窗打开
        });
    } else {
      setOpen(false);
    }
  };

  return (
    <div className="space-y-2 rounded-xl border border-border/80 bg-card p-3 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Label className="text-sm font-semibold text-foreground">
            {t("grading.dimension.title")}
          </Label>
          {totalScore != null && (
            <span className="rounded-md bg-primary/10 px-2 py-0.5 text-sm font-bold text-primary">
              {t("grading.dimension.totalScore")}: {Number(totalScore)}
              {essayGrade ? ` · ${essayGrade}` : ""}
            </span>
          )}
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => setOpen(true)}
        >
          {t("grading.dimension.editScore")}
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {dimensions.map((d) => {
          const score = Number(dimensionScores[d.key]) || 0;
          const full = Number(d.full_score) || 0;
          const pct =
            full > 0 ? Math.min(100, Math.max(0, (score / full) * 100)) : 0;
          return (
            <div key={d.key} className="space-y-1">
              <div className="flex items-center justify-between gap-2 text-xs">
                <span className="truncate text-muted-foreground">{d.name}</span>
                <span className="shrink-0 font-medium text-foreground">
                  {score}/{full}
                </span>
              </div>
              <Progress value={pct} className="h-1.5" />
            </div>
          );
        })}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("grading.dimension.editScore")}</DialogTitle>
            <DialogDescription className="truncate">
              {filename}
            </DialogDescription>
          </DialogHeader>
          <EditScoreForm
            dimensions={dimensions}
            initialScores={dimensionScores}
            onCancel={() => setOpen(false)}
            onSave={handleSave}
            t={t}
          />
        </DialogContent>
      </Dialog>
    </div>
  );
}
