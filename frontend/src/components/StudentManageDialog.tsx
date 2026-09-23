import { useState, useMemo } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { useAuth } from "@/hooks/useAuth";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
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
  useStudents,
  useCreateStudent,
  useUpdateStudent,
  useDeleteStudent,
  StudentRecord,
} from "@/hooks/useStudents";
import { ClassRecord } from "@/hooks/useClasses";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { translateGender } from "@/i18n";
import { toast } from "sonner";

interface StudentManageDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  classInfo: ClassRecord | null;
}

export function StudentManageDialog({
  open,
  onOpenChange,
  classInfo,
}: StudentManageDialogProps) {
  const { t, locale } = useLocale();

  const { user } = useAuth();
  const isGlobalAdmin = useMemo(() => {
    if (!user || !user.roles) return false;
    return user.roles.some((r) =>
      ["系统管理员", "子系统管理员", "校级管理者", "年级组长"].includes(r),
    );
  }, [user]);

  const canManage =
    isGlobalAdmin || classInfo?.is_owner || classInfo?.my_role === "head";

  const { data: students = [], isLoading } = useStudents(classInfo?.id);
  const createStudent = useCreateStudent();
  const updateStudent = useUpdateStudent();
  const deleteStudent = useDeleteStudent();

  const [isAdding, setIsAdding] = useState(false);
  const [editingStudent, setEditingStudent] = useState<StudentRecord | null>(
    null,
  );
  const [deletingStudent, setDeletingStudent] = useState<StudentRecord | null>(
    null,
  );
  const [formName, setFormName] = useState("");
  const [formNumber, setFormNumber] = useState("");
  const [formGender, setFormGender] = useState<"男" | "女">("男");

  const resetForm = () => {
    setIsAdding(false);
    setEditingStudent(null);
    setFormName("");
    setFormNumber("");
    setFormGender("男");
  };

  const handleCreate = async () => {
    if (!classInfo || !formName.trim()) return;
    const num = formNumber.trim();
    try {
      await createStudent.mutateAsync({
        class_id: classInfo.id,
        name: formName.trim(),
        ...(num ? { student_number: num } : {}),
        gender: formGender,
      });
      resetForm();
    } catch (e: any) {
      toast.error(e.message || t("account.toast.studentCreateFailed"));
    }
  };

  const handleUpdate = async () => {
    if (!editingStudent || !classInfo || !formName.trim()) return;
    try {
      await updateStudent.mutateAsync({
        id: editingStudent.id,
        class_id: classInfo.id,
        patch: {
          name: formName.trim(),
          student_number: formNumber.trim(),
          gender: formGender,
        },
      });
      resetForm();
    } catch (e: any) {
      toast.error(e.message || t("account.toast.studentUpdateFailed"));
    }
  };

  const handleDelete = async () => {
    if (!deletingStudent || !classInfo) return;
    try {
      await deleteStudent.mutateAsync({
        id: deletingStudent.id,
        class_id: classInfo.id,
      });
      setDeletingStudent(null);
    } catch (e: any) {
      toast.error(e.message || t("account.toast.studentDeleteFailed"));
    }
  };

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={(v) => {
          onOpenChange(v);
          if (!v) resetForm();
        }}
      >
        <DialogContent className="sm:max-w-[540px] max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {t("classDetail.studentManageTitle", {
                name: classInfo?.name || "",
              })}
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-2 py-4">
            {/* Header */}
            <div className="grid grid-cols-[80px_1fr_80px] gap-2 px-3 text-sm text-muted-foreground font-medium">
              <span>{t("grading.studentTab.studentNoHeader")}</span>
              <span>{t("classDetail.姓名")}</span>
              <span className="text-right">
                {t("grading.studentTab.actionHeader")}
              </span>
            </div>

            {isLoading ? (
              <p className="text-muted-foreground text-center py-8">
                {t("common.loading")}
              </p>
            ) : students.length === 0 && !isAdding ? (
              <p className="text-muted-foreground text-center py-8">
                {t("classDetail.noStudentsAddHint")}
              </p>
            ) : (
              students.map((s) => (
                <div
                  key={s.id}
                  className="grid grid-cols-[80px_1fr_80px] gap-2 items-center p-3 rounded-lg border border-border hover:bg-muted/50 transition-colors"
                >
                  <span className="text-sm font-mono">{s.student_number}</span>
                  <span className="font-medium">{s.name}</span>
                  <div className="flex items-center justify-end gap-1">
                    {canManage && (
                      <>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={() => {
                            setEditingStudent(s);
                            setFormName(s.name);
                            setFormNumber(s.student_number);
                            setFormGender(s.gender === "女" ? "女" : "男");
                          }}
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-destructive hover:text-destructive"
                          onClick={() => setDeletingStudent(s)}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </>
                    )}
                  </div>
                </div>
              ))
            )}

            {/* Add / Edit form */}
            {(isAdding || editingStudent) && (
              <div className="flex items-center gap-2 p-3 rounded-lg border border-primary/30 bg-primary/5">
                <Input
                  value={formNumber}
                  onChange={(e) => setFormNumber(e.target.value)}
                  placeholder={t("classDetail.学号 可不填")}
                  className="w-[80px]"
                  autoFocus
                />
                <Input
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder={t("classDetail.姓名")}
                  className="flex-1"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      editingStudent ? handleUpdate() : handleCreate();
                    }
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
                  onClick={editingStudent ? handleUpdate : handleCreate}
                  disabled={
                    !formName.trim() ||
                    createStudent.isPending ||
                    updateStudent.isPending
                  }
                >
                  {editingStudent
                    ? t("grading.studentTab.save")
                    : t("classDetail.添加")}
                </Button>
                <Button size="sm" variant="ghost" onClick={resetForm}>
                  {t("grading.studentTab.cancel")}
                </Button>
              </div>
            )}
          </div>

          <DialogFooter>
            {canManage && !isAdding && !editingStudent && (
              <Button onClick={() => setIsAdding(true)} className="gap-2">
                <Plus className="w-4 h-4" />
                {t("classDetail.addStudent")}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={!!deletingStudent}
        onOpenChange={(open) => !open && setDeletingStudent(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("classDetail.确认删除")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("classDetail.confirmDeleteStudent", {
                name: deletingStudent?.name || "",
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t("common.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
