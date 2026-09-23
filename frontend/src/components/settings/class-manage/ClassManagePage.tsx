import { useEffect, useMemo, useState } from "react";
import { ClassManageHeader } from "./ClassManageHeader";
import { ClassTreeNav } from "./ClassTreeNav";
import { ClassOverviewCards } from "./ClassOverviewCards";
import { StudentTable } from "./StudentTable";
import { StudentDetailPanel } from "./StudentDetailPanel";
import { PermissionsPanel } from "./PermissionsPanel";
import { DataSyncPanel } from "./DataSyncPanel";
import { StudentImportDialog } from "@/components/class-detail/StudentImportDialog";
import { GlobalStudentImportDialog } from "./GlobalStudentImportDialog";
import { useClasses } from "@/hooks/useClasses";
import { useStudents } from "@/hooks/useStudents";
import { useAuth } from "@/hooks/useAuth";
import { useQuery } from "@tanstack/react-query";
import { listClassTeachers } from "@/services/api";
import { useLocale } from "@/contexts/LocaleContext";

export function ClassManagePage() {
  const { user } = useAuth();
  const { t } = useLocale();
  const { data: dbClasses = [] } = useClasses();

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
  const [importOpen, setImportOpen] = useState(false);
  const [globalImportOpen, setGlobalImportOpen] = useState(false);

  const selectedStudent =
    (dbStudents || []).find((s) => s.id === selectedStudentId) || null;
  const totalStudents = dbClasses.reduce(
    (sum, c) => sum + (c.student_count || 0),
    0,
  );
  const activeHeadTeacherName = headTeacherByClassId[activeClassId] || "—";

  const handleBatchImport = () => setImportOpen(true);
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
    return (
      <div className="rounded-xl border border-border bg-card p-8 text-center text-muted-foreground">
        <p className="text-sm">{t("settingsClass.noClasses")}</p>
        <p className="text-xs mt-1">{t("settingsClass.noClassesHint")}</p>
      </div>
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
          onBatchImport={handleBatchImport}
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

      <StudentImportDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        classId={activeClassId}
        className={selectedClass?.name || ""}
      />

      <GlobalStudentImportDialog
        open={globalImportOpen}
        onOpenChange={setGlobalImportOpen}
      />
    </div>
  );
}
