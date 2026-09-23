import { useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSubjectName } from "@/i18n";
import { useExams, useCreateExam, useDeleteExam } from "@/hooks/useExams";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Plus, Trash2, FileText, AlertCircle, RefreshCw } from "lucide-react";

const subjectOptions = [
  "语文",
  "数学",
  "英语",
  "科学",
  "物理",
  "化学",
  "生物",
  "历史",
  "地理",
  "政治",
];

interface ExamHistoryTabProps {
  classId: string;
}

export function ExamHistoryTab({ classId }: ExamHistoryTabProps) {
  const { t, locale } = useLocale();

  const [filterSubject, setFilterSubject] = useState<string>("all");
  const {
    data: exams = [],
    isLoading,
    isError,
    refetch,
  } = useExams(classId, filterSubject === "all" ? undefined : filterSubject);
  const createExam = useCreateExam();
  const deleteExam = useDeleteExam();

  const [isAdding, setIsAdding] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [formTitle, setFormTitle] = useState("");
  const [formSubject, setFormSubject] = useState("语文");
  const [formScore, setFormScore] = useState("100");
  const [formDate, setFormDate] = useState(
    new Date().toISOString().split("T")[0],
  );

  const handleCreate = async () => {
    if (!formTitle.trim()) return;
    await createExam.mutateAsync({
      class_id: classId,
      subject: formSubject,
      title: formTitle.trim(),
      total_score: Number(formScore) || 100,
      exam_date: formDate,
    });
    setIsAdding(false);
    setFormTitle("");
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Select value={filterSubject} onValueChange={setFilterSubject}>
          <SelectTrigger className="w-[140px]">
            <SelectValue placeholder={t("classDetail.全部学科")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("classDetail.全部学科")}</SelectItem>
            {subjectOptions.map((s) => (
              <SelectItem key={s} value={s}>
                {translateSubjectName(locale, s)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button onClick={() => setIsAdding(true)} className="gap-2">
          <Plus className="w-4 h-4" />
          {t("grading.examHistory.addExam")}
        </Button>
      </div>

      {isAdding && (
        <div className="p-4 rounded-lg border border-primary/30 bg-primary/5 space-y-3">
          <div className="flex items-center gap-3">
            <Input
              value={formTitle}
              onChange={(e) => setFormTitle(e.target.value)}
              placeholder={t("classDetail.考试名称")}
              className="flex-1"
              autoFocus
            />
            <Select value={formSubject} onValueChange={setFormSubject}>
              <SelectTrigger className="w-[100px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {subjectOptions.map((s) => (
                  <SelectItem key={s} value={s}>
                    {translateSubjectName(locale, s)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-3">
            <Input
              type="date"
              value={formDate}
              onChange={(e) => setFormDate(e.target.value)}
              className="w-[160px]"
            />
            <Input
              type="number"
              value={formScore}
              onChange={(e) => setFormScore(e.target.value)}
              placeholder={t("classDetail.满分")}
              className="w-[100px]"
            />
            <Button
              size="sm"
              onClick={handleCreate}
              disabled={!formTitle.trim() || createExam.isPending}
            >
              {t("grading.examHistory.create")}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setIsAdding(false)}
            >
              {t("common.cancel")}
            </Button>
          </div>
        </div>
      )}

      <div className="bg-card rounded-xl border border-border overflow-hidden">
        <div className="grid grid-cols-[1fr_100px_100px_120px_60px] gap-4 px-4 py-3 bg-muted/50 text-sm font-medium text-muted-foreground">
          <span>{t("classDetail.考试名称")}</span>
          <span>{t("grading.examHistory.subjectHeader")}</span>
          <span>{t("classDetail.满分")}</span>
          <span>{t("grading.examHistory.dateHeader")}</span>
          <span className="text-right">
            {t("grading.examHistory.actionHeader")}
          </span>
        </div>
        {isLoading ? (
          <p className="text-center py-8 text-muted-foreground">
            {t("common.loading")}
          </p>
        ) : isError ? (
          <div className="flex flex-col items-center justify-center py-12 rounded-lg border border-dashed bg-muted/20 text-center">
            <AlertCircle className="w-10 h-10 text-destructive/60 mb-3" />
            <p className="text-sm font-medium text-foreground mb-1">
              {t("classDetail.examsLoadFailed")}
            </p>
            <p className="text-xs text-muted-foreground mb-4">
              {t("classDetail.checkNetworkAndRetry")}
            </p>
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5"
              onClick={() => refetch()}
            >
              <RefreshCw className="w-3.5 h-3.5" />
              {t("wuyu.retry")}
            </Button>
          </div>
        ) : exams.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12">
            <FileText className="w-10 h-10 text-muted-foreground/40 mb-2" />
            <p className="text-muted-foreground">
              {t("classDetail.暂无考试记录")}
            </p>
          </div>
        ) : (
          exams.map((exam) => (
            <div
              key={exam.id}
              className="grid grid-cols-[1fr_100px_100px_120px_60px] gap-4 items-center px-4 py-3 border-t border-border hover:bg-muted/30 transition-colors"
            >
              <span className="font-medium">{exam.title}</span>
              <span className="text-sm">
                {translateSubjectName(locale, exam.subject)}
              </span>
              <span className="text-sm">{exam.total_score}</span>
              <span className="text-sm text-muted-foreground">
                {exam.exam_date}
              </span>
              <div className="flex justify-end">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 text-destructive hover:text-destructive"
                  onClick={() => setDeleting(exam.id)}
                  aria-label={t("grading.examHistory.deleteAria")}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>
          ))
        )}
      </div>

      <AlertDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("grading.examHistory.deleteTitle")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t("grading.examHistory.deleteConfirmDesc")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (deleting) {
                  deleteExam.mutate({ id: deleting, class_id: classId });
                  setDeleting(null);
                }
              }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t("grading.examHistory.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
