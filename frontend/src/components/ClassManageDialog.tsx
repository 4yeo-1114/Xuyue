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
  useClasses,
  useCreateClass,
  useUpdateClass,
  useDeleteClass,
  ClassRecord,
} from "@/hooks/useClasses";
import { buildGradeLevels } from "@/i18n";
import { Plus, Pencil, Trash2, Users, LogOut } from "lucide-react";
import { leaveClass } from "@/services/api";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";

interface ClassManageDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  schoolLevel: string;
  grade: string;
  onSelectClass?: (classId: string) => void;
  onManageStudents?: (cls: ClassRecord) => void;
}

export function ClassManageDialog({
  open,
  onOpenChange,
  schoolLevel,
  grade,
  onSelectClass,
  onManageStudents,
}: ClassManageDialogProps) {
  const { t, locale } = useLocale();

  const { user } = useAuth();
  const isGlobalAdmin = useMemo(() => {
    if (!user || !user.roles) return false;
    return user.roles.some((r) =>
      ["系统管理员", "子系统管理员", "校级管理者", "年级组长"].includes(r),
    );
  }, [user]);

  const { data: classes = [], isLoading } = useClasses(schoolLevel, grade);
  const createClass = useCreateClass();
  const updateClass = useUpdateClass();
  const deleteClass = useDeleteClass();
  const queryClient = useQueryClient();

  const [isAdding, setIsAdding] = useState(false);
  const [editingClass, setEditingClass] = useState<ClassRecord | null>(null);
  const [deletingClass, setDeletingClass] = useState<ClassRecord | null>(null);
  const [leavingClass, setLeavingClass] = useState<ClassRecord | null>(null);
  const [newClassName, setNewClassName] = useState("");

  const gradeLevels = useMemo(() => buildGradeLevels(locale), [locale]);
  const currentLevel = gradeLevels.find((l) => l.id === schoolLevel);
  const currentGrade = currentLevel?.grades.find((g) => g.value === grade);

  const handleCreate = async () => {
    if (!newClassName.trim()) return;
    try {
      await createClass.mutateAsync({
        school_level: schoolLevel,
        grade,
        name: newClassName.trim(),
      });
      setNewClassName("");
      setIsAdding(false);
    } catch (e: any) {
      toast.error(e.message || t("home.toast.classCreateFailed"));
    }
  };

  const handleUpdate = async () => {
    if (!editingClass || !newClassName.trim()) return;
    try {
      await updateClass.mutateAsync({
        id: editingClass.id,
        name: newClassName.trim(),
      });
      setNewClassName("");
      setEditingClass(null);
    } catch (e: any) {
      toast.error(e.message || t("home.toast.classUpdateFailed"));
    }
  };

  const handleDelete = async () => {
    if (!deletingClass) return;
    try {
      await deleteClass.mutateAsync(deletingClass.id);
      setDeletingClass(null);
    } catch (e: any) {
      toast.error(e.message || t("home.toast.classDeleteFailed"));
    }
  };

  const handleLeave = async () => {
    if (!leavingClass) return;
    try {
      await leaveClass(leavingClass.id);
      toast.success(t("account.classManage.leaveSuccess"));
      queryClient.invalidateQueries({ queryKey: ["classes"] });
    } catch (e: any) {
      toast.error(e.message || t("account.classManage.leaveFailed"));
    }
    setLeavingClass(null);
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-[480px] max-h-[80vh] overflow-hidden flex flex-col">
          <DialogHeader className="shrink-0">
            <DialogTitle>
              {currentGrade?.label || grade} - {t("account.classManage.title")}
            </DialogTitle>
          </DialogHeader>

          <div className="flex-1 min-h-0 overflow-y-auto pr-2">
            <div className="space-y-3 py-4">
              {isLoading ? (
                <p className="text-muted-foreground text-center py-8">
                  {t("common.loading")}
                </p>
              ) : classes.length === 0 && !isAdding ? (
                <div className="text-center py-8 space-y-2">
                  <p className="text-muted-foreground">
                    {t("classDetail.暂无班级")}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {t("account.classManage.emptyHint")}
                  </p>
                </div>
              ) : (
                classes.map((cls) => (
                  <div
                    key={cls.id}
                    className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-muted/50 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <span className="font-medium">{cls.name}</span>
                      <span className="text-sm text-muted-foreground">
                        {t("account.classManage.studentCount", {
                          count: cls.student_count,
                        })}
                      </span>
                    </div>
                    <div className="flex items-center gap-1">
                      {(isGlobalAdmin ||
                        cls.is_owner ||
                        cls.my_role === "head") && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => onManageStudents?.(cls)}
                          title={t("classDetail.管理学生与教师")}
                        >
                          <Users className="w-4 h-4" />
                        </Button>
                      )}

                      {cls.my_role && !cls.is_owner && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-orange-500 hover:text-orange-600"
                          onClick={() => setLeavingClass(cls)}
                          title={t("classDetail.退出班级")}
                        >
                          <LogOut className="w-4 h-4" />
                        </Button>
                      )}

                      {(isGlobalAdmin || cls.is_owner) && (
                        <>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => {
                              setEditingClass(cls);
                              setNewClassName(cls.name);
                            }}
                            title={t("classDetail.修改班级名称")}
                          >
                            <Pencil className="w-4 h-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-destructive hover:text-destructive"
                            onClick={() => setDeletingClass(cls)}
                            title={t("classDetail.删除班级")}
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                ))
              )}

              {(isAdding || editingClass) && (
                <div className="flex items-center gap-2 p-3 rounded-lg border border-primary/30 bg-primary/5">
                  <Input
                    value={newClassName}
                    onChange={(e) => setNewClassName(e.target.value)}
                    placeholder={t("classDetail.输入班级名称 如 一班")}
                    className="flex-1"
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        editingClass ? handleUpdate() : handleCreate();
                      }
                    }}
                    autoFocus
                  />
                  <Button
                    size="sm"
                    onClick={editingClass ? handleUpdate : handleCreate}
                    disabled={
                      !newClassName.trim() ||
                      createClass.isPending ||
                      updateClass.isPending
                    }
                  >
                    {editingClass
                      ? t("account.classManage.save")
                      : t("classDetail.添加")}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setIsAdding(false);
                      setEditingClass(null);
                      setNewClassName("");
                    }}
                  >
                    {t("common.cancel")}
                  </Button>
                </div>
              )}
            </div>
          </div>

          <DialogFooter className="shrink-0">
            {!isAdding && !editingClass && (
              <Button
                onClick={() => {
                  setIsAdding(true);
                  setNewClassName("");
                }}
                className="gap-2"
              >
                <Plus className="w-4 h-4" />
                {t("account.classManage.addClass")}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation */}
      <AlertDialog
        open={!!deletingClass}
        onOpenChange={(open) => !open && setDeletingClass(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("classDetail.确认删除")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("account.classManage.deleteConfirmDesc", {
                name: deletingClass?.name || "",
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t("account.classManage.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Leave confirmation */}
      <AlertDialog
        open={!!leavingClass}
        onOpenChange={(open) => !open && setLeavingClass(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("account.classManage.leaveTitle")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t("account.classManage.leaveConfirmDesc", {
                name: leavingClass?.name || "",
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleLeave}
              className="bg-orange-500 text-white hover:bg-orange-600"
            >
              {t("account.classManage.leave")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
