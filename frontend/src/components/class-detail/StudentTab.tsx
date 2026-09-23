import { useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import {
  useStudents,
  useCreateStudent,
  useUpdateStudent,
  useDeleteStudent,
  StudentRecord,
} from "@/hooks/useStudents";
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
import {
  Plus,
  Pencil,
  Trash2,
  Search,
  Upload,
  AlertCircle,
  RefreshCw,
} from "lucide-react";
import { translateGender } from "@/i18n";
import { StudentImportDialog } from "./StudentImportDialog";

interface StudentTabProps {
  classId: string;
  className: string;
}

export function StudentTab({ classId, className }: StudentTabProps) {
  const { t, locale } = useLocale();

  const {
    data: students = [],
    isLoading,
    isError,
    refetch,
  } = useStudents(classId);
  const createStudent = useCreateStudent();
  const updateStudent = useUpdateStudent();
  const deleteStudent = useDeleteStudent();

  const [search, setSearch] = useState("");
  const [isAdding, setIsAdding] = useState(false);
  const [editing, setEditing] = useState<StudentRecord | null>(null);
  const [deleting, setDeleting] = useState<StudentRecord | null>(null);
  const [formName, setFormName] = useState("");
  const [formNumber, setFormNumber] = useState("");
  const [formGender, setFormGender] = useState<"男" | "女">("男");
  const [importOpen, setImportOpen] = useState(false);

  // 用项目 i18n locale 显式格式化加入时间,空值/非法值兜底占位
  const formatCreatedAt = (raw: string | null | undefined) => {
    if (!raw) return t("classDetail.noDate");
    const d = new Date(raw);
    if (Number.isNaN(d.getTime())) return t("classDetail.noDate");
    return d.toLocaleDateString(locale === "en" ? "en-US" : "zh-CN");
  };

  const filtered = students.filter(
    (s) => s.name.includes(search) || s.student_number.includes(search),
  );

  const resetForm = () => {
    setIsAdding(false);
    setEditing(null);
    setFormName("");
    setFormNumber("");
    setFormGender("男");
  };

  const handleCreate = async () => {
    if (!formName.trim()) return;
    const num = formNumber.trim();
    await createStudent.mutateAsync({
      class_id: classId,
      name: formName.trim(),
      ...(num ? { student_number: num } : {}),
      gender: formGender,
    });
    resetForm();
  };

  const handleUpdate = async () => {
    if (!editing || !formName.trim()) return;
    const num = formNumber.trim();
    await updateStudent.mutateAsync({
      id: editing.id,
      class_id: classId,
      patch: {
        name: formName.trim(),
        ...(num ? { student_number: num } : {}),
        gender: formGender,
      },
    });
    resetForm();
  };

  const handleDelete = async () => {
    if (!deleting) return;
    await deleteStudent.mutateAsync({ id: deleting.id, class_id: classId });
    setDeleting(null);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="relative w-64">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder={t("classDetail.搜索学生")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => setImportOpen(true)}
            className="gap-2"
          >
            <Upload className="w-4 h-4" />
            {t("grading.studentTab.batchImport")}
          </Button>
          <Button
            onClick={() => {
              setIsAdding(true);
              setFormName("");
              setFormNumber("");
              setFormGender("男");
            }}
            className="gap-2"
          >
            <Plus className="w-4 h-4" />
            {t("grading.studentTab.addStudent")}
          </Button>
        </div>
      </div>

      {(isAdding || editing) && (
        <div className="flex items-center gap-2 p-4 rounded-lg border border-primary/30 bg-primary/5">
          <Input
            value={formNumber}
            onChange={(e) => setFormNumber(e.target.value)}
            placeholder={t("classDetail.学号 可不填")}
            className="w-[120px]"
            autoFocus
          />
          <Input
            value={formName}
            onChange={(e) => setFormName(e.target.value)}
            placeholder={t("classDetail.姓名")}
            className="flex-1"
            onKeyDown={(e) => {
              if (e.key === "Enter") editing ? handleUpdate() : handleCreate();
            }}
          />
          <Select
            value={formGender}
            onValueChange={(v) => setFormGender(v as "男" | "女")}
          >
            <SelectTrigger className="h-9 w-[90px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="男">
                {translateGender(locale, "男")}
              </SelectItem>
              <SelectItem value="女">
                {translateGender(locale, "女")}
              </SelectItem>
            </SelectContent>
          </Select>
          <Button
            size="sm"
            onClick={editing ? handleUpdate : handleCreate}
            disabled={
              !formName.trim() ||
              createStudent.isPending ||
              updateStudent.isPending
            }
          >
            {editing ? t("grading.studentTab.save") : t("classDetail.添加")}
          </Button>
          <Button size="sm" variant="ghost" onClick={resetForm}>
            {t("grading.studentTab.cancel")}
          </Button>
        </div>
      )}

      <div className="bg-card rounded-xl border border-border overflow-hidden">
        <div className="grid grid-cols-[80px_1fr_120px_80px] gap-4 px-4 py-3 bg-muted/50 text-sm font-medium text-muted-foreground">
          <span>{t("grading.studentTab.studentNoHeader")}</span>
          <span>{t("classDetail.姓名")}</span>
          <span>{t("grading.studentTab.addedAtHeader")}</span>
          <span className="text-right">
            {t("grading.studentTab.actionHeader")}
          </span>
        </div>
        {isLoading ? (
          <p className="text-center py-8 text-muted-foreground">
            {t("common.loading")}
          </p>
        ) : isError ? (
          <div className="flex flex-col items-center justify-center py-16 rounded-lg border border-dashed bg-muted/20 text-center">
            <AlertCircle className="w-10 h-10 text-destructive/60 mb-3" />
            <p className="text-sm font-medium text-foreground mb-1">
              {t("classDetail.loadStudentsFailed")}
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
        ) : filtered.length === 0 ? (
          <p className="text-center py-8 text-muted-foreground">
            {search
              ? t("grading.studentTab.noMatch")
              : t("classDetail.暂无学生")}
          </p>
        ) : (
          filtered.map((s) => (
            <div
              key={s.id}
              className="grid grid-cols-[80px_1fr_120px_80px] gap-4 items-center px-4 py-3 border-t border-border hover:bg-muted/30 transition-colors"
            >
              <span className="font-mono text-sm">{s.student_number}</span>
              <span className="font-medium">{s.name}</span>
              <span className="text-sm text-muted-foreground">
                {formatCreatedAt(s.created_at)}
              </span>
              <div className="flex items-center justify-end gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  onClick={() => {
                    setEditing(s);
                    setFormName(s.name);
                    setFormNumber(s.student_number);
                    setFormGender(s.gender === "女" ? "女" : "男");
                  }}
                  aria-label={t("grading.studentTab.editAria")}
                >
                  <Pencil className="w-3.5 h-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 text-destructive hover:text-destructive"
                  onClick={() => setDeleting(s)}
                  aria-label={t("grading.studentTab.deleteAria")}
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
            <AlertDialogTitle>{t("classDetail.确认删除")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("grading.studentTab.deleteConfirmDesc", {
                name: deleting?.name || "",
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>
              {t("grading.studentTab.cancel")}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t("grading.studentTab.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <StudentImportDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        classId={classId}
        className={className}
      />
    </div>
  );
}
