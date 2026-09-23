import { useEffect, useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { PrivacyNoticeDialog } from "@/components/common/PrivacyNoticeDialog";
import { FileText, Loader2 } from "lucide-react";
import { importTargetedExams, listTargetedImportableExams } from "@/services/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  classId: string;
  subject: string;
  onImported?: (result: {
    generated_count: number;
    failed_count: number;
    generated: Array<{ student_name: string; report_id: string }>;
  }) => void | Promise<void>;
}

export function TargetedImportExamDialog({ open, onOpenChange, classId, subject, onImported }: Props) {
  const { t } = useLocale();

  const queryClient = useQueryClient();
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [noticeOpen, setNoticeOpen] = useState(false);

  const { data: exams = [], isLoading } = useQuery({
    queryKey: ["targeted-importable-exams", classId, subject],
    queryFn: () => listTargetedImportableExams(classId, subject),
    enabled: open && !!classId && !!subject,
  });

  useEffect(() => {
    if (!open) setSelectedIds(new Set());
  }, [open]);

  const mutation = useMutation({
    mutationFn: () => importTargetedExams({
      class_id: classId,
      subject,
      exam_folder_names: Array.from(selectedIds),
    }),
    onSuccess: async (res) => {
      const failedHint = res.failed_count > 0 ? t("targeted.import.failedHint", { count: res.failed_count }) : "";
      toast.success(t("targeted.import.success", { count: res.generated_count, failed: failedHint }), {
        description: res.ignored_count > 0 ? t("targeted.import.ignored", { count: res.ignored_count }) : undefined,
      });
      await queryClient.invalidateQueries({ queryKey: ["targeted-students", classId, subject] });
      await queryClient.invalidateQueries({ queryKey: ["targeted-report", classId, subject] });
      await queryClient.refetchQueries({ queryKey: ["targeted-students", classId, subject] });
      await queryClient.refetchQueries({ queryKey: ["targeted-report", classId, subject] });
      await onImported?.({
        generated_count: res.generated_count,
        failed_count: res.failed_count,
        generated: res.generated || [],
      });
      onOpenChange(false);
    },
    onError: (err: any) => {
      toast.error(t("targeted.import.failed"), { description: err?.message || t("classReview.retry") });
    },
  });

  const toggle = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <>
    <Dialog open={open} onOpenChange={(v) => !mutation.isPending && onOpenChange(v)}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("targeted.import.title")}</DialogTitle>
          <DialogDescription>
            {t("targeted.import.description")}
          </DialogDescription>
        </DialogHeader>

        <div className="py-2">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-10 text-muted-foreground">
              <Loader2 className="mb-2 h-6 w-6 animate-spin" />
              <p className="text-sm">{t("targeted.import.loading")}</p>
            </div>
          ) : exams.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed bg-muted/20 py-10 text-muted-foreground">
              <FileText className="mb-2 h-8 w-8 opacity-30" />
              <p className="text-sm">{t("targeted.import.empty")}</p>
            </div>
          ) : (
            <ScrollArea className="h-[320px] pr-3">
              <div className="space-y-2">
                {exams.map((exam) => {
                  const selected = selectedIds.has(exam.id);
                  return (
                    <button
                      key={exam.id}
                      type="button"
                      onClick={() => toggle(exam.id)}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-colors",
                        selected ? "border-primary bg-primary/5" : "border-border bg-card hover:bg-muted/50"
                      )}
                    >
                      <Checkbox checked={selected} onCheckedChange={() => toggle(exam.id)} onClick={(e) => e.stopPropagation()} />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">{exam.name}</p>
                        <p className="mt-0.5 text-xs text-muted-foreground">{t("targeted.import.graded", { count: exam.completed_count })}</p>
                      </div>
                      <Badge variant={selected ? "default" : "secondary"} className="text-[10px]">
                        {selected ? t("targeted.import.selected") : t("targeted.import.available")}
                      </Badge>
                    </button>
                  );
                })}
              </div>
            </ScrollArea>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={mutation.isPending}>
            {t("targeted.import.cancel")}
          </Button>
          <Button onClick={() => setNoticeOpen(true)} disabled={selectedIds.size === 0 || mutation.isPending}>
            {mutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            {mutation.isPending ? t("targeted.import.analyzing") : t("targeted.import.confirm", { count: selectedIds.size })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    <PrivacyNoticeDialog
      open={noticeOpen}
      onOpenChange={setNoticeOpen}
      onConfirm={() => mutation.mutate()}
      context={t("nav.ai-targeted")}
    />
    </>
  );
}
