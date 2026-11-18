import { useCallback, useEffect, useState } from "react";
import {
  ClipboardList,
  Loader2,
  Pencil,
  Printer,
  RefreshCw,
  Trash2,
  FileText,
} from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { useLocale } from "@/contexts/LocaleContext";
import {
  fetchPrintJobs,
  fetchPrintJobFull,
  updatePrintJob,
  deletePrintJob,
  printPrintJob,
  previewPrintJobPdf,
  type PrintJobPublic,
  type PrintJobFull,
} from "@/services/printJobsApi";

const STATUS_LABEL: Record<string, string> = {
  draft: "待预览",
  pending: "排队中",
  printing: "打印中",
  done: "已完成",
  failed: "失败",
};

function formatTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function statusBadgeVariant(
  status: string,
): "default" | "secondary" | "destructive" | "outline" {
  if (status === "done") return "default";
  if (status === "failed") return "destructive";
  if (status === "printing" || status === "pending") return "secondary";
  return "outline";
}

/** 结构化题目的展示/编辑文案（去题型前缀，选项并进 content 首行之后） */
function questionItemText(item: Record<string, unknown>): string {
  return String(item?.content ?? "");
}

export default function PrintJobsPage() {
  const { t } = useLocale();
  const [jobs, setJobs] = useState<PrintJobPublic[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // 编辑弹窗
  const [editing, setEditing] = useState<PrintJobFull | null>(null);
  const [editSaving, setEditSaving] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editClass, setEditClass] = useState("");
  const [editTeacher, setEditTeacher] = useState("");
  const [editCopies, setEditCopies] = useState(1);
  const [editNote, setEditNote] = useState("");
  const [editQuestionsText, setEditQuestionsText] = useState("");
  const [editItems, setEditItems] = useState<Record<string, unknown>[]>([]);

  // 删除确认
  const [deleting, setDeleting] = useState<PrintJobPublic | null>(null);
  const [busyId, setBusyId] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const rows = await fetchPrintJobs(100);
      setJobs(rows);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg || t("grading.printJobs.loadError"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const openEdit = async (job: PrintJobPublic) => {
    try {
      const full = await fetchPrintJobFull(job.job_id);
      setEditing(full);
      setEditTitle(full.title || "");
      setEditClass(full.class_name || "");
      setEditTeacher(full.teacher || "");
      setEditCopies(full.copies || 1);
      setEditNote(full.note || "");
      setEditQuestionsText((full.questions || []).join("\n"));
      setEditItems(full.question_items || []);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("grading.printJobs.loadError"));
    }
  };

  const saveEdit = async () => {
    if (!editing) return;
    setEditSaving(true);
    try {
      const patch: Parameters<typeof updatePrintJob>[1] = {
        title: editTitle,
        class_name: editClass,
        teacher: editTeacher,
        copies: editCopies,
        note: editNote,
      };
      if (editing.source !== "upload") {
        if ((editing.question_items || []).length > 0) {
          // AI 结构化题目：只改 content，题型/分值/选项原样保留
          patch.question_items = editItems;
        } else {
          patch.questions = editQuestionsText
            .split("\n")
            .map((s) => s.trim())
            .filter(Boolean);
        }
      }
      await updatePrintJob(editing.job_id, patch);
      toast.success(t("grading.printJobs.saved"));
      setEditing(null);
      void load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("grading.printJobs.saveError"));
    } finally {
      setEditSaving(false);
    }
  };

  const doPrint = async (job: PrintJobPublic) => {
    setBusyId(job.job_id);
    try {
      await printPrintJob(job.job_id, { reprint: true });
      toast.success(t("grading.printJobs.printQueued"));
      void load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("grading.printJobs.saveError"));
    } finally {
      setBusyId("");
    }
  };

  const doPreview = async (job: PrintJobPublic) => {
    setBusyId(job.job_id);
    try {
      await previewPrintJobPdf(job.job_id);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("grading.printJobs.loadError"));
    } finally {
      setBusyId("");
    }
  };

  const doDelete = async () => {
    if (!deleting) return;
    setBusyId(deleting.job_id);
    try {
      await deletePrintJob(deleting.job_id);
      toast.success(t("grading.printJobs.deleted"));
      setDeleting(null);
      void load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("grading.printJobs.saveError"));
    } finally {
      setBusyId("");
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle className="flex items-center gap-2">
              <ClipboardList className="h-5 w-5" />
              {t("grading.printJobs.title")}
            </CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              {t("grading.printJobs.subtitle")}
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
            {loading ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            {t("grading.printJobs.refresh")}
          </Button>
        </CardHeader>
        <CardContent>
          {error ? (
            <div className="mb-3 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          ) : null}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("grading.printJobs.colTitle")}</TableHead>
                <TableHead>{t("grading.printJobs.colMeta")}</TableHead>
                <TableHead>{t("grading.printJobs.colCount")}</TableHead>
                <TableHead>{t("grading.printJobs.colSource")}</TableHead>
                <TableHead>{t("grading.printJobs.colStatus")}</TableHead>
                <TableHead>{t("grading.printJobs.colTime")}</TableHead>
                <TableHead className="text-right">
                  {t("grading.printJobs.colActions")}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && jobs.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                    <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                  </TableCell>
                </TableRow>
              ) : jobs.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                    {t("grading.printJobs.empty")}
                  </TableCell>
                </TableRow>
              ) : (
                jobs.map((job) => (
                  <TableRow key={job.job_id}>
                    <TableCell className="max-w-[220px]">
                      <div className="truncate font-medium">{job.title || "—"}</div>
                      <div className="truncate text-xs text-muted-foreground">
                        {job.teacher || "—"}
                        {job.class_name ? ` · ${job.class_name}` : ""}
                      </div>
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-sm">
                      {job.subject_label || "—"}
                      {job.grade_label ? ` / ${job.grade_label}` : ""}
                      <div className="text-xs text-muted-foreground">
                        {job.page_size_label || job.page_size}
                      </div>
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-sm">
                      {t("grading.printJobs.questionCount", {
                        count: job.question_count,
                        copies: job.copies,
                      })}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {job.source === "ai"
                          ? t("grading.printJobs.sourceAi")
                          : job.source === "upload"
                            ? t("grading.printJobs.sourceUpload")
                            : t("grading.printJobs.sourceText")}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={statusBadgeVariant(job.status)}>
                        {STATUS_LABEL[job.status] || job.status}
                      </Badge>
                      {job.error ? (
                        <div className="mt-1 max-w-[160px] truncate text-xs text-destructive">
                          {job.error}
                        </div>
                      ) : null}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                      {formatTime(job.created_at)}
                      {job.printed_at ? (
                        <div className="text-xs">
                          {t("grading.printJobs.printedAt", {
                            time: formatTime(job.printed_at),
                          })}
                        </div>
                      ) : null}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          title={t("grading.printJobs.preview")}
                          disabled={busyId === job.job_id}
                          onClick={() => void doPreview(job)}
                        >
                          <FileText className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          title={t("grading.printJobs.edit")}
                          disabled={job.status === "printing"}
                          onClick={() => void openEdit(job)}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          title={t("grading.printJobs.print")}
                          disabled={busyId === job.job_id || job.status === "printing"}
                          onClick={() => void doPrint(job)}
                        >
                          <Printer className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          title={t("grading.printJobs.delete")}
                          disabled={job.status === "printing"}
                          onClick={() => setDeleting(job)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* 编辑弹窗 */}
      <Dialog open={!!editing} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>{t("grading.printJobs.editTitle")}</DialogTitle>
          </DialogHeader>
          {editing ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>{t("grading.printJobs.colTitle")}</Label>
                  <Input
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                  />
                </div>
                <div>
                  <Label>{t("grading.printJobs.fieldClass")}</Label>
                  <Input
                    value={editClass}
                    onChange={(e) => setEditClass(e.target.value)}
                  />
                </div>
                <div>
                  <Label>{t("grading.printJobs.fieldTeacher")}</Label>
                  <Input
                    value={editTeacher}
                    onChange={(e) => setEditTeacher(e.target.value)}
                  />
                </div>
                <div>
                  <Label>{t("grading.printJobs.fieldCopies")}</Label>
                  <Input
                    type="number"
                    min={1}
                    max={50}
                    value={editCopies}
                    onChange={(e) =>
                      setEditCopies(Math.max(1, Math.min(50, Number(e.target.value) || 1)))
                    }
                  />
                </div>
              </div>

              <div>
                <Label>{t("grading.printJobs.fieldNote")}</Label>
                <Input value={editNote} onChange={(e) => setEditNote(e.target.value)} />
              </div>

              {editing.source === "upload" ? (
                <div className="rounded-md border bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
                  {t("grading.printJobs.uploadSourceHint")}
                </div>
              ) : (editing.question_items || []).length > 0 ? (
                <div className="space-y-2">
                  <Label>{t("grading.printJobs.fieldItems")}</Label>
                  {editItems.map((item, i) => (
                    <textarea
                      key={i}
                      className="min-h-[64px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                      value={questionItemText(item)}
                      onChange={(e) => {
                        const next = [...editItems];
                        next[i] = { ...item, content: e.target.value };
                        setEditItems(next);
                      }}
                    />
                  ))}
                </div>
              ) : (
                <div>
                  <Label>{t("grading.printJobs.fieldQuestions")}</Label>
                  <textarea
                    className="min-h-[160px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    value={editQuestionsText}
                    onChange={(e) => setEditQuestionsText(e.target.value)}
                  />
                </div>
              )}
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>
              {t("grading.printJobs.cancel")}
            </Button>
            <Button onClick={() => void saveEdit()} disabled={editSaving}>
              {editSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              {t("grading.printJobs.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 删除确认 */}
      <AlertDialog open={!!deleting} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("grading.printJobs.deleteTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("grading.printJobs.deleteDesc", { title: deleting?.title || "" })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("grading.printJobs.cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void doDelete()}>
              {t("grading.printJobs.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
