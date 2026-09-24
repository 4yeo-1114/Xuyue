import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
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
import { useLocale } from "@/contexts/LocaleContext";

export type PaperScoreItem = {
  no: number;
  title: string;
  score: number;
};

/** 原始试卷分值确认页：逐题展示 AI 识别出的分值，用户核对/修改后回填。 */
export function PaperScoreConfirmDialog({
  open,
  onOpenChange,
  items,
  loading,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  items: PaperScoreItem[];
  loading: boolean;
  onConfirm: (scores: Record<number, number>) => void;
}) {
  const { t } = useLocale();
  const [scores, setScores] = useState<Record<number, number>>({});

  useEffect(() => {
    if (open && items.length > 0) {
      const init: Record<number, number> = {};
      for (const item of items) {
        if (item.no > 0) init[item.no] = item.score;
      }
      setScores(init);
    }
  }, [open, items]);

  const total =
    Math.round(
      items.reduce((sum, item) => sum + (scores[item.no] ?? 0), 0) * 100,
    ) / 100;

  const updateScore = (no: number, raw: string) => {
    const value = parseFloat(raw);
    setScores((prev) => ({
      ...prev,
      [no]: Number.isFinite(value) && value >= 0 ? value : 0,
    }));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] w-full max-w-[min(94vw,680px)] overflow-hidden p-0">
        <DialogHeader className="border-b bg-sky-50/50 px-6 py-4 pr-14 text-left">
          <DialogTitle>{t("grading.originalPaper.dialogTitle")}</DialogTitle>
          <DialogDescription>
            {t("grading.originalPaper.dialogHint")}
          </DialogDescription>
        </DialogHeader>
        <ScrollArea className="max-h-[min(62vh,520px)] px-6 py-3">
          <div className="flex flex-col gap-1.5">
            {items.map((item) => (
              <div
                key={item.no}
                className="flex items-center gap-3 rounded border border-transparent px-2 py-1.5 hover:bg-muted/40"
              >
                <span className="w-16 shrink-0 text-sm font-semibold text-muted-foreground">
                  {t("grading.originalPaper.questionNo")} {item.no}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm" title={item.title}>
                  {item.title || "—"}
                </span>
                <div className="flex w-24 shrink-0 items-center gap-1">
                  <Input
                    type="number"
                    min={0}
                    step={0.5}
                    value={scores[item.no] ?? ""}
                    onChange={(e) => updateScore(item.no, e.target.value)}
                    className="h-8 text-right text-sm"
                  />
                  <span className="text-xs text-muted-foreground">
                    {t("grading.manualLayout.points")}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </ScrollArea>
        <DialogFooter className="flex-row items-center justify-between border-t px-6 py-3 sm:justify-between">
          <span className="text-sm font-semibold">
            {t("grading.originalPaper.total", { total })}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={loading}
            >
              {t("common.cancel")}
            </Button>
            <Button
              onClick={() => onConfirm(scores)}
              disabled={loading || items.length === 0}
              className="gap-1.5"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {t("grading.originalPaper.apply")}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
