import { useState, useEffect, useMemo } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
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
import { Plus, Trash2, GraduationCap } from "lucide-react";
import { toast } from "sonner";
import { translateSubjectName } from "@/i18n";
import {
  listClassTeachers,
  addClassTeacher,
  deleteClassTeacher,
  patchClassTeacher,
} from "@/services/api";

function teacherRoleLabel(role: string, t: (key: string) => string) {
  switch (role) {
    case "head":
      return t("classDetail.班主任");
    case "deputy":
      return t("classDetail.副班主任");
    case "teacher":
      return t("classDetail.教师");
    default:
      return role;
  }
}

interface TeacherManageDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  classId: string;
  /** 弹窗副标题，如年级班级名 */
  subtitle?: string;
  /**
   * 当前用户能否管理协作教师（由父级根据 classMeta.my_role/is_owner 传入）。
   * 班级所有者可能不在 class_teachers 表中，此时无法在列表里匹配到本人 role，
   * 但后端仍允许其管理协作教师，故用该 prop 兜底。
   */
  canManage?: boolean;
}

export function TeacherManageDialog({
  open,
  onOpenChange,
  classId,
  subtitle,
  canManage: canManageProp,
}: TeacherManageDialogProps) {
  const { t, locale } = useLocale();

  const queryClient = useQueryClient();
  const { user } = useAuth();
  
  const { data: teachers = [], isLoading } = useQuery({
    queryKey: ["class-teachers", classId],
    queryFn: () => listClassTeachers(classId),
    enabled: open && !!classId,
  });

  const isGlobalAdmin = useMemo(() => {
    if (!user || !user.roles) return false;
    return user.roles.some((r) => ["系统管理员", "子系统管理员", "校级管理者", "年级组长"].includes(r));
  }, [user]);

  const isCurrentUserHead = useMemo(() => {
    if (!user) return false;
    const currentTeacher = teachers.find((t) => t.user_id === user.id || t.email === user.email);
    return currentTeacher?.role === "head";
  }, [user, teachers]);

  const canManage = isGlobalAdmin || isCurrentUserHead || canManageProp === true;

  const [isAdding, setIsAdding] = useState(false);
  const [newTeacherEmail, setNewTeacherEmail] = useState("");
  const [newTeacherRole, setNewTeacherRole] = useState<"head" | "deputy" | "teacher">("teacher");
  const [addLoading, setAddLoading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setIsAdding(false);
      setNewTeacherEmail("");
      setNewTeacherRole("teacher");
      setDeletingId(null);
    }
  }, [open]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["class-teachers", classId] });
  };

  const handleAdd = async () => {
    const email = newTeacherEmail.trim();
    if (!email) {
      toast.error(t("classDetail.请输入邮箱"));
      return;
    }
    setAddLoading(true);
    try {
      await addClassTeacher(classId, { email, role: newTeacherRole });
      toast.success(t("classDetail.已添加教师"));
      setNewTeacherEmail("");
      setNewTeacherRole("teacher");
      setIsAdding(false);
      invalidate();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t("classDetail.添加失败"));
    } finally {
      setAddLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!deletingId) return;
    try {
      await deleteClassTeacher(classId, deletingId);
      toast.success(t("classDetail.已移除该教师"));
      setDeletingId(null);
      invalidate();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t("classDetail.移除失败"));
    }
  };

  const handleRoleChange = async (ctId: string, role: "head" | "deputy" | "teacher") => {
    try {
      await patchClassTeacher(classId, ctId, { role });
      toast.success(t("classDetail.已更新角色"));
      invalidate();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t("classDetail.更新失败"));
    }
  };

  const deletingTeacher = deletingId ? teachers.find((t) => t.id === deletingId) : null;

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-[480px] gap-0 p-0 overflow-hidden">
          <div className="px-6 pt-6 pb-4 border-b border-border/60 bg-gradient-to-b from-sky-50/80 to-background dark:from-sky-950/20">
            <DialogHeader className="space-y-1 text-left">
              <DialogTitle className="flex items-center gap-2 text-lg">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <GraduationCap className="h-5 w-5" />
                </span>
                {t("classDetail.teacherSettings")}
              </DialogTitle>
              <DialogDescription className="text-sm text-muted-foreground pl-11">
                {subtitle || t("classDetail.管理本班协作教师 添加 调整角色或移除")}
              </DialogDescription>
            </DialogHeader>
          </div>

          <div className="space-y-3 px-6 py-4 max-h-[min(60vh,420px)] overflow-y-auto">
            {isLoading ? (
              <p className="text-muted-foreground text-center py-10">{t("common.loading")}</p>
            ) : teachers.length === 0 && !isAdding ? (
              <div className="text-center py-10 space-y-2 rounded-lg border border-dashed border-border/80 bg-muted/20">
                <p className="text-muted-foreground">{t("classDetail.noTeachers")}</p>
                <p className="text-sm text-muted-foreground">{t("classDetail.addTeacherHint")}</p>
              </div>
            ) : (
              teachers.map((teacher) => {
                const isHead = teacher.role === "head";
                const name = teacher.display_name || teacher.email?.split("@")[0] || t("classDetail.教师");
                return (
                  <div
                    key={teacher.id}
                    className="flex items-center justify-between gap-3 p-3 rounded-lg border border-border hover:bg-muted/50 transition-colors"
                  >
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      <div className="h-10 w-10 rounded-full bg-primary/15 flex items-center justify-center text-sm font-bold text-primary shrink-0">
                        {(teacher.display_name || teacher.email || "?")[0]}
                      </div>
                      <div className="min-w-0">
                        <p className="font-medium truncate">{name}</p>
                        <p className="text-xs text-muted-foreground truncate">{teacher.email}</p>
                        {teacher.subject && teacher.subject !== "__CLEAR__" ? (
                          <p className="text-xs text-muted-foreground mt-0.5">{t("classDetail.subjectLabel", { subject: translateSubjectName(locale, teacher.subject) })}</p>
                        ) : null}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {!canManage || (isHead && !isGlobalAdmin && teacher.email !== user?.email) ? (
                        <span className="text-sm font-medium text-primary px-2 py-1 rounded-md bg-primary/10">
                          {teacherRoleLabel(teacher.role, t)}
                        </span>
                      ) : (
                        <>
                          <Select
                            value={teacher.role === "head" || teacher.role === "deputy" || teacher.role === "teacher" ? teacher.role : "teacher"}
                            onValueChange={(v) => {
                              if (v === "head" || v === "deputy" || v === "teacher") handleRoleChange(teacher.id, v);
                            }}
                          >
                            <SelectTrigger className="h-9 w-[120px] text-xs">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {(isGlobalAdmin || isCurrentUserHead) && <SelectItem value="head">{t("classDetail.班主任")}</SelectItem>}
                              <SelectItem value="deputy">{t("classDetail.副班主任")}</SelectItem>
                              <SelectItem value="teacher">{t("classDetail.教师")}</SelectItem>
                            </SelectContent>
                          </Select>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-9 w-9 text-destructive hover:text-destructive"
                            onClick={() => setDeletingId(teacher.id)}
                            aria-label={t("classDetail.移除教师")}
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                );
              })
            )}

            {isAdding && (
              <div className="space-y-3 p-3 rounded-lg border border-primary/30 bg-primary/5">
                <div className="space-y-2">
                  <Label htmlFor="tm-email">{t("classDetail.teacherEmail")}</Label>
                  <Input
                    id="tm-email"
                    type="email"
                    placeholder="name@example.com"
                    value={newTeacherEmail}
                    onChange={(e) => setNewTeacherEmail(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void handleAdd();
                    }}
                    autoFocus
                  />
                </div>
                <div className="space-y-2">
                  <Label>{t("classDetail.role")}</Label>
                  <Select
                    value={newTeacherRole}
                    onValueChange={(v) => setNewTeacherRole(v as "head" | "deputy" | "teacher")}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {(isGlobalAdmin || isCurrentUserHead) && <SelectItem value="head">{t("classDetail.班主任")}</SelectItem>}
                      <SelectItem value="deputy">{t("classDetail.副班主任")}</SelectItem>
                      <SelectItem value="teacher">{t("classDetail.教师")}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-center gap-2 justify-end pt-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setIsAdding(false);
                      setNewTeacherEmail("");
                      setNewTeacherRole("teacher");
                    }}
                  >
                    {t("common.cancel")}
                  </Button>
                  <Button size="sm" onClick={() => void handleAdd()} disabled={addLoading || !newTeacherEmail.trim()}>
                    {addLoading ? t("classDetail.提交中") : t("classDetail.添加")}
                  </Button>
                </div>
              </div>
            )}
          </div>

          <DialogFooter className="px-6 py-4 border-t border-border/60 bg-muted/30">
            {canManage && !isAdding && (
              <Button
                type="button"
                className="gap-2 w-full sm:w-auto"
                onClick={() => {
                  setIsAdding(true);
                  setNewTeacherEmail("");
                  setNewTeacherRole("teacher");
                }}
              >
                <Plus className="w-4 h-4" />
                {t("classDetail.addTeacher")}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deletingId} onOpenChange={(o) => !o && setDeletingId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("classDetail.confirmRemoveTeacherTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("classDetail.confirmRemoveTeacherDesc", { name: deletingTeacher?.display_name || deletingTeacher?.email || t("classDetail.该教师") })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                void handleDelete();
              }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t("classAnalysis.dialog.remove")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
