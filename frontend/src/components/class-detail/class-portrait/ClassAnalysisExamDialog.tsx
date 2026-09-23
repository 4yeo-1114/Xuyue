import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  FileText,
  Loader2,
  RefreshCw,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { PrivacyNoticeDialog } from "@/components/common/PrivacyNoticeDialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useLocale } from "@/contexts/LocaleContext";
import { cn } from "@/lib/utils";
import {
  generateClassAnalysis,
  listClassAnalysisImportableExams,
  type TargetedExamOption,
} from "@/services/api";

interface ClassAnalysisExamDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  classId: string;
  subject: string;
  currentFolderNames?: string[];
}

export function ClassAnalysisExamDialog({
  open,
  onOpenChange,
  classId,
  subject,
  currentFolderNames = [],
}: ClassAnalysisExamDialogProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [selectedOrder, setSelectedOrder] = useState<string[]>([]);
  const [noticeOpen, setNoticeOpen] = useState(false);
  // 仅当数据首次加载完成时预填充一次，避免 refetch(staleTime=0 + refetchOnWindowFocus)
  // 让 exams 引用变化而静默还原用户手动调整的选中顺序
  const hasPrefilledRef = useRef(false);

  const {
    data: exams = [],
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["class-analysis-importable-exams", classId, subject],
    queryFn: () => listClassAnalysisImportableExams(classId, subject),
    enabled: open && !!classId && !!subject,
  });

  const examById = useMemo(
    () => new Map(exams.map((exam) => [exam.id, exam])),
    [exams],
  );

  useEffect(() => {
    if (!open) {
      hasPrefilledRef.current = false;
      return;
    }
    if (hasPrefilledRef.current) return;
    // 等待数据真正加载完成后再按当前考试列表预填充，避免空列表把选择清空
    if (exams.length === 0) return;
    hasPrefilledRef.current = true;
    const available = new Set(exams.map((exam) => exam.id));
    setSelectedOrder(currentFolderNames.filter((id) => available.has(id)));
  }, [open, exams, currentFolderNames]);

  const mutation = useMutation({
    mutationFn: () =>
      generateClassAnalysis({
        class_id: classId,
        subject,
        exam_folder_names: selectedOrder,
      }),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({
        queryKey: ["class-analysis-report", classId, subject],
      });
      toast.success(t("classAnalysis.dialog.success"), {
        description: result.ignored_count
          ? t("classAnalysis.dialog.unmatched", { count: result.ignored_count })
          : undefined,
      });
      onOpenChange(false);
    },
    onError: (error: unknown) => {
      toast.error(t("classAnalysis.dialog.failed"), {
        description:
          error instanceof Error ? error.message : t("classAnalysis.retry"),
      });
    },
  });

  const toggle = (examId: string) => {
    setSelectedOrder((current) =>
      current.includes(examId)
        ? current.filter((id) => id !== examId)
        : [...current, examId],
    );
  };

  const move = (index: number, direction: -1 | 1) => {
    setSelectedOrder((current) => {
      const target = index + direction;
      if (target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={(value) => !mutation.isPending && onOpenChange(value)}
      >
        <DialogContent className="flex max-h-[88vh] flex-col overflow-hidden sm:max-w-4xl">
          <DialogHeader className="shrink-0">
            <DialogTitle>{t("classAnalysis.dialog.title")}</DialogTitle>
            <DialogDescription>
              {t("classAnalysis.dialog.description")}
            </DialogDescription>
          </DialogHeader>

          <div className="grid min-h-0 flex-1 gap-4 py-2 md:grid-cols-[1.15fr_0.85fr]">
            <section className="min-h-0 overflow-hidden rounded-lg border bg-card">
              <div className="flex h-11 items-center justify-between border-b px-4">
                <p className="text-sm font-semibold">
                  {t("classAnalysis.dialog.available")}
                </p>
                <span className="text-xs text-muted-foreground">
                  {t("classAnalysis.dialog.examCount", { count: exams.length })}
                </span>
              </div>
              {isLoading ? (
                <div className="flex h-[320px] items-center justify-center text-muted-foreground">
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  {t("classAnalysis.dialog.loading")}
                </div>
              ) : isError ? (
                <div className="flex h-[320px] flex-col items-center justify-center gap-2 text-muted-foreground">
                  <AlertTriangle className="h-8 w-8 opacity-40" />
                  <p className="text-sm">
                    {t("classAnalysis.dialog.loadFailed")}
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-1.5"
                    onClick={() => refetch()}
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                    {t("wuyu.retry")}
                  </Button>
                </div>
              ) : exams.length === 0 ? (
                <div className="flex h-[320px] flex-col items-center justify-center gap-2 text-muted-foreground">
                  <FileText className="h-8 w-8 opacity-40" />
                  <p className="text-sm">{t("classAnalysis.dialog.empty")}</p>
                </div>
              ) : (
                <ScrollArea className="h-[360px]">
                  <div className="space-y-1 p-2">
                    {exams.map((exam: TargetedExamOption) => {
                      const selected = selectedOrder.includes(exam.id);
                      const order = selectedOrder.indexOf(exam.id);
                      return (
                        <div
                          key={exam.id}
                          onClick={() => toggle(exam.id)}
                          className={cn(
                            "flex w-full cursor-pointer items-center gap-3 rounded-md border px-3 py-2.5 text-left transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
                            selected
                              ? "border-primary/50 bg-primary/5"
                              : "border-transparent hover:border-border hover:bg-muted/50",
                          )}
                        >
                          <Checkbox
                            checked={selected}
                            onCheckedChange={() => toggle(exam.id)}
                            onClick={(event) => event.stopPropagation()}
                            aria-label={t("classDetail.selectExamLabel", {
                              name: exam.name,
                            })}
                          />
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium">
                              {exam.name}
                            </p>
                            <p className="mt-0.5 text-xs text-muted-foreground">
                              {t("classAnalysis.dialog.gradedCount", {
                                count: exam.completed_count,
                              })}
                            </p>
                          </div>
                          {selected ? (
                            <Badge className="h-6 min-w-6 justify-center px-1.5">
                              {order + 1}
                            </Badge>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                </ScrollArea>
              )}
            </section>

            <section className="min-h-0 overflow-hidden rounded-lg border bg-muted/20">
              <div className="flex h-11 items-center justify-between border-b bg-card px-4">
                <p className="text-sm font-semibold">
                  {t("classAnalysis.dialog.order")}
                </p>
                <span className="text-xs text-muted-foreground">
                  {t("classAnalysis.dialog.examCount", {
                    count: selectedOrder.length,
                  })}
                </span>
              </div>
              <ScrollArea className="h-[360px]">
                {selectedOrder.length === 0 ? (
                  <div className="flex h-[300px] items-center justify-center px-8 text-center text-sm text-muted-foreground">
                    {t("classAnalysis.dialog.selectHint")}
                  </div>
                ) : (
                  <ol className="space-y-2 p-3">
                    {selectedOrder.map((examId, index) => {
                      const exam = examById.get(examId);
                      return (
                        <li
                          key={examId}
                          className="flex items-center gap-2 rounded-md border bg-card p-2 shadow-sm"
                        >
                          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary/10 text-xs font-bold text-primary">
                            {index + 1}
                          </span>
                          <span className="min-w-0 flex-1 truncate text-sm font-medium">
                            {exam?.name || examId}
                          </span>
                          <Button
                            type="button"
                            size="icon"
                            variant="ghost"
                            className="h-7 w-7"
                            disabled={index === 0}
                            aria-label={t("classAnalysis.dialog.moveUp")}
                            title={t("classAnalysis.dialog.moveUp")}
                            onClick={() => move(index, -1)}
                          >
                            <ArrowUp className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            type="button"
                            size="icon"
                            variant="ghost"
                            className="h-7 w-7"
                            disabled={index === selectedOrder.length - 1}
                            aria-label={t("classAnalysis.dialog.moveDown")}
                            title={t("classAnalysis.dialog.moveDown")}
                            onClick={() => move(index, 1)}
                          >
                            <ArrowDown className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            type="button"
                            size="icon"
                            variant="ghost"
                            className="h-7 w-7 text-muted-foreground hover:text-destructive"
                            aria-label={t("classAnalysis.dialog.remove")}
                            title={t("classAnalysis.dialog.remove")}
                            onClick={() => toggle(examId)}
                          >
                            <X className="h-3.5 w-3.5" />
                          </Button>
                        </li>
                      );
                    })}
                  </ol>
                )}
              </ScrollArea>
            </section>
          </div>

          <DialogFooter className="shrink-0 border-t pt-4">
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={mutation.isPending}
            >
              {t("classAnalysis.dialog.cancel")}
            </Button>
            <Button
              onClick={() => setNoticeOpen(true)}
              disabled={!selectedOrder.length || mutation.isPending}
            >
              {mutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              {mutation.isPending
                ? t("classAnalysis.dialog.analyzing")
                : t("classAnalysis.dialog.analyzeCount", {
                    count: selectedOrder.length,
                  })}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <PrivacyNoticeDialog
        open={noticeOpen}
        onOpenChange={setNoticeOpen}
        onConfirm={() => mutation.mutate()}
        context={t("classDetail.classAnalysisPrivacyContext")}
      />
    </>
  );
}
