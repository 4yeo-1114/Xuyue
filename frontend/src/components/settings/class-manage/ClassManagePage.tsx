import { useEffect, useMemo, useState } from "react";
import { ClassManageHeader } from "./ClassManageHeader";
import { ClassTreeNav } from "./ClassTreeNav";
import { ClassOverviewCards } from "./ClassOverviewCards";
import { StudentTable } from "./StudentTable";
import { StudentDetailPanel } from "./StudentDetailPanel";
import { PermissionsPanel } from "./PermissionsPanel";
import { DataSyncPanel } from "./DataSyncPanel";
import { GlobalStudentImportDialog } from "./GlobalStudentImportDialog";
import { useClasses } from "@/hooks/useClasses";
import { useStudents } from "@/hooks/useStudents";
import { useAuth } from "@/hooks/useAuth";
import { useGlobalFilters } from "@/hooks/useGlobalFilters";
import { useQuery } from "@tanstack/react-query";
import { listClassTeachers } from "@/services/api";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { ClassManageDialog } from "@/components/ClassManageDialog";
import { Plus } from "lucide-react";

export function ClassManagePage() {
  const { user } = useAuth();
  const { t } = useLocale();
  const { schoolLevel, grade } = useGlobalFilters();
  const { data: dbClasses = [] } = useClasses();
  const [classDialogOpen, setClassDialogOpen] = useState(false);

  const [selectedClassId, setSelectedClassId] = useState<string | null>(null);
  const activeClassId = selectedClassId || dbClasses[0]?.id || "";
  const [headTeacherByClassId, setHeadTeacherByClassId] = useState<
    Record<string, string>
  >({});

  // Fetch real students for the selected DB class
  const { data: dbStudents = [] } = useStudents(activeClassId || undefined);

  const selectedClass = useMemo(() => {
    return dbClasses.find((c) => c.id === activeClassId) || null;
  }, [dbClasses, activeClassId]);

  const { data: classTeachers = [] } = useQuery({
    queryKey: ["class-teachers", activeClassId],
    queryFn: () => listClassTeachers(activeClassId),
    enabled: !!user && !!activeClassId,
  });

  const [selectedStudentId, setSelectedStudentId] = useState<string | null>(
    null,
  );
  const [globalImportOpen, setGlobalImportOpen] = useState(false);

  const selectedStudent =
    (dbStudents || []).find((s) => s.id === selectedStudentId) || null;
  const totalStudents = dbClasses.reduce(
    (sum, c) => sum + (c.student_count || 0),
    0,
  );
  const activeHeadTeacherName = headTeacherByClassId[activeClassId] || "—";

  const handleGlobalImport = () => setGlobalImportOpen(true);

  useEffect(() => {
    let canceled = false;
    const load = async () => {
      const next: Record<string, string> = {};
      await Promise.all(
        dbClasses.map(async (c) => {
          try {
            const list = await listClassTeachers(c.id);
            const head = list.find(
              (t) => (t.role || "").toLowerCase() === "head",
            );
            const name =
              head?.display_name ||
              (head?.email ? head.email.split("@")[0] : "");
            next[c.id] = name || "—";
          } catch {
            next[c.id] = "—";
          }
        }),
      );
      if (!canceled) setHeadTeacherByClassId(next);
    };
    if (user && dbClasses.length) load();
    return () => {
      canceled = true;
    };
  }, [user, dbClasses]);

  if (!user) return null;

  if (!dbClasses.length) {
    // 零班级不是死胡同：复用已有的建班能力（ClassManageDialog → useCreateClass → POST /classes），
    // ⛔ 不新造建班流程 / 不新接口。这一脚对「独立老师」（注册完零班级）是必需的。
    return (
      <>
        <div className="rounded-xl border border-border bg-card p-8 text-center text-muted-foreground">
          <p className="text-sm">{t("settingsClass.noClasses")}</p>
          <p className="text-xs mt-1">{t("settingsClass.noClassesHint")}</p>
          <Button
            className="mt-4 gap-1.5"
            size="sm"
            onClick={() => setClassDialogOpen(true)}
          >
            <Plus className="w-4 h-4" />
            {t("account.classManage.addClass")}
          </Button>
        </div>
        <ClassManageDialog
          open={classDialogOpen}
          onOpenChange={setClassDialogOpen}
          schoolLevel={schoolLevel}
          grade={grade}
        />
      </>
    );
  }

  return (
    <div className="space-y-5">
      <ClassManageHeader
        classCount={dbClasses.length}
        totalStudents={totalStudents}
        activeClassName={selectedClass?.name || ""}
        activeHeadTeacherName={activeHeadTeacherName}
        activeStudentCount={dbStudents.length}
        onBatchImport={handleGlobalImport}
      />

      <div className="grid grid-cols-[280px_1fr] gap-4">
        <ClassTreeNav
          classes={dbClasses}
          selectedClassId={activeClassId}
          onSelectClass={(id) => {
            setSelectedClassId(id);
            setSelectedStudentId(null);
          }}
          headTeacherByClassId={headTeacherByClassId}
        />
        {selectedClass && (
          <ClassOverviewCards classInfo={selectedClass} students={dbStudents} />
        )}
      </div>

      <div className="grid grid-cols-[1fr_360px] gap-4">
        <StudentTable
          classId={activeClassId}
          students={dbStudents}
          className={selectedClass?.name || ""}
          selectedStudentId={selectedStudentId}
          onSelectStudent={setSelectedStudentId}
        />
        <StudentDetailPanel student={selectedStudent} classId={activeClassId} />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <PermissionsPanel
          classId={activeClassId}
          className={selectedClass?.name || ""}
          teachers={classTeachers}
          canManageTeachers={selectedClass?.my_role === "head"}
        />
        <DataSyncPanel
          classId={activeClassId}
          className={selectedClass?.name || ""}
        />
      </div>

      <GlobalStudentImportDialog
        open={globalImportOpen}
        onOpenChange={setGlobalImportOpen}
        fallbackClassId={activeClassId}
      />
    </div>
  );
}
