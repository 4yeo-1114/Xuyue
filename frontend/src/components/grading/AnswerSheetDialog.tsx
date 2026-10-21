import { useEffect, useMemo, useState } from "react";
import { Loader2, Plus, RefreshCw, Trash2, Wand2 } from "lucide-react";
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
import { cn } from "@/lib/utils";
import { useLocale } from "@/contexts/LocaleContext";
import type { AnswerSheetRow } from "@/services/gradingApi";

type Props = {
  open: boolean;
  rows: AnswerSheetRow[];
  loading?: boolean;
  saving?: boolean;
  error?: string;
  onOpenChange: (open: boolean) => void;
  onRescan: () => Promise<void> | void;
  /** 专窗核对完点「合并进答案表」：按题号把每题答案合进答题区 */
  onConfirm: (rows: AnswerSheetRow[]) => Promise<void> | void;
};

/** 答案纸识别专窗：只看答案（题号+答案），确认后与答题区按题号合并。 */
export function AnswerSheetDialog({
  open,
  rows,
  loading,
  saving,
  error,
  onOpenChange,
  onRescan,
  onConfirm,
}: Props) {
  const { t } = useLocale();
  const [drafts, setDrafts] = useState<AnswerSheetRow[] | null>(null);

  // 每次打开用最新识别结果重置草稿；打开期间老师随便改
  useEffect(() => {
    if (open) {
      setDrafts(rows.map((row) => ({ ...row })));
    } else {
      setDrafts(null);
    }
  }, [open, rows]);

  const view = useMemo(() => drafts ?? rows, [drafts, rows]);
  const dirty = useMemo(() => {
    if (!drafts) return false;
    return (
      drafts.length !== rows.length ||
      drafts.some(
        (row, index) =>
          row.no !== rows[index]?.no || row.answer !== rows[index]?.answer,
      )
    );
  }, [drafts, rows]);

  const setRow = (index: number, patch: Partial<AnswerSheetRow>) => {
    setDrafts((prev) => {
      const base = prev ?? rows.map((row) => ({ ...row }));
      return base.map((row, i) => (i === index ? { ...row, ...patch } : row));
    });
  };

  const addRow = () => {
    setDrafts((prev) => {
      const base = prev ?? rows.map((row) => ({ ...row }));
      return [...base, { no: "", answer: "" }];
    });
  };

  const removeRow = (index: number) => {
    setDrafts((prev) => {
      const base = prev ?? rows.map((row) => ({ ...row }));
      return base.filter((_, i) => i !== index);
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="answer-sheet-dialog"
        className="max-w-2xl max-h-[86vh] flex flex-col overflow-hidden"
      >
        <DialogHeader>
          <DialogTitle>{t("grading.answerSheet.title")}</DialogTitle>
          <DialogDescription>
            {t("grading.answerSheet.description")}
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center justify-between gap-2">
          <div className="text-sm text-muted-foreground">
            {t("grading.answerSheet.rowInfo", { count: view.length })}
            {dirty && (
              <span className="ml-2 text-amber-600">
                {t("grading.answerSheet.unsaved")}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={loading || saving}
              onClick={() => void onRescan()}
            >
              {loading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <RefreshCw className="w-4 h-4" />
              )}
              {t("grading.answerSheet.rescan")}
            </Button>
            <Button type="button" size="sm" variant="outline" disabled={loading || saving} onClick={addRow}>
              <Plus className="w-4 h-4" />
              {t("grading.answerSheet.addRow")}
            </Button>
          </div>
        </div>

        {/* 嵌套 flex 滚动区：别用 h-full，百分比链断了就不滚 */}
        <div className="relative flex min-h-0 flex-1 flex-col">
          {loading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-background/70">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="w-4 h-4 animate-spin" />
                {t("grading.answerSheet.loading")}
              </div>
            </div>
          )}
          <div className="min-h-0 flex-1 overflow-y-auto pr-3">
            {error ? (
              <div className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </div>
            ) : null}
            {!loading && view.length === 0 ? (
              <div className="py-10 text-center text-sm text-muted-foreground">
                {t("grading.answerSheet.empty")}
              </div>
            ) : null}
            <div className="space-y-2">
              {view.map((row, index) => (
                <div
                  key={`${index}-${row.no}`}
                  className="flex items-center gap-2 rounded-lg border px-3 py-2"
                >
                  <span className="w-12 shrink-0 text-xs text-muted-foreground">
                    {t("grading.answerSheet.noLabel")}
                  </span>
                  <Input
                    className={cn("h-8 w-16 px-2 text-center")}
                    value={row.no}
                    onChange={(event) => setRow(index, { no: event.target.value })}
                  />
                  <Textarea
                    className="min-h-[36px] flex-1 text-sm"
                    value={row.answer}
                    onChange={(event) =>
                      setRow(index, { answer: event.target.value })
                    }
                  />
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={loading || saving}
                    onClick={() => removeRow(index)}
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              ))}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("grading.answerSheet.later")}
          </Button>
          <Button
            onClick={() => void onConfirm(view.map((row) => ({ ...row })))}
            disabled={loading || saving || view.length === 0}
            className="gap-2"
          >
            {saving ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Wand2 className="w-4 h-4" />
            )}
            {t("grading.answerSheet.merge")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
