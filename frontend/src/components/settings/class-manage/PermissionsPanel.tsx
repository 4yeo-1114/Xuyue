import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { GraduationCap, Settings } from "lucide-react";
import type { ClassTeacherRecord } from "@/types/api";
import { TeacherManageDialog } from "@/components/class-detail/TeacherManageDialog";
import { useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSubjectName } from "@/i18n";

interface PermissionsPanelProps {
  classId: string;
  teachers: ClassTeacherRecord[];
  className: string;
  canManageTeachers?: boolean;
}

function teacherRoleLabel(t: (key: string) => string, role: string) {
  switch ((role || "").toLowerCase()) {
    case "head":
      return t("settingsClass.permissions.roleHead");
    case "deputy":
      return t("settingsClass.permissions.roleDeputy");
    case "teacher":
      return t("settingsClass.permissions.roleTeacher");
    default:
      return role;
  }
}

const ROLE_GROUPS = [
  { role: "head", labelKey: "settingsClass.permissions.roleHead" },
  { role: "deputy", labelKey: "settingsClass.permissions.roleDeputy" },
  { role: "teacher", labelKey: "settingsClass.permissions.roleTeacher" },
] as const;

export function PermissionsPanel({ classId, teachers, className, canManageTeachers }: PermissionsPanelProps) {
  const { t, locale } = useLocale();
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-2xl border border-border bg-card p-5">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="min-w-0">
          <h3 className="text-base font-semibold text-foreground truncate">{t("settingsClass.permissions.title")}</h3>
          <p className="text-sm text-muted-foreground mt-0.5 truncate">{className}</p>
        </div>
        {canManageTeachers && (
          <Button size="sm" variant="outline" className="h-9 text-sm gap-1.5" onClick={() => setOpen(true)}>
            <Settings className="w-4 h-4" />{t("settingsClass.permissions.teacherSettings")}
          </Button>
        )}
      </div>

      {ROLE_GROUPS.map(({ role, labelKey }) => {
        const list = teachers.filter((t) => t.role === role);
        if (list.length === 0) return null;
        return (
          <div key={role} className="mb-5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-semibold text-foreground/90">{t(labelKey)} · {list.length}</span>
            </div>
            <div className="space-y-2">
              {list.map((teacher) => (
                <div key={teacher.id} className="flex items-center gap-3 p-3 rounded-xl border border-border/60 hover:bg-muted/40 transition-colors">
                  <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                    <GraduationCap className="w-4 h-4 text-primary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-semibold text-foreground truncate">
                        {teacher.display_name || teacher.email?.split("@")[0] || t("settingsClass.permissions.teacherFallback")}
                      </span>
                      <span className="text-xs text-muted-foreground">· {teacherRoleLabel(t, teacher.role)}</span>
                      {teacher.subject && teacher.subject !== "__CLEAR__" ? (
                        <span className="text-xs text-muted-foreground">· {translateSubjectName(locale, teacher.subject)}</span>
                      ) : null}
                    </div>
                    <p className="text-xs text-muted-foreground truncate">{teacher.email}</p>
                  </div>
                </div>
              ))}
            </div>
            <Separator className="mt-3" />
          </div>
        );
      })}

      <TeacherManageDialog open={open} onOpenChange={setOpen} classId={classId} subtitle={className} canManage={canManageTeachers} />
    </div>
  );
}
