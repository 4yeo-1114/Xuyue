import { useEffect, useMemo, useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { translateGender, translateSubjectName } from "@/i18n";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  AlertCircle,
  ClipboardList,
  Users2,
  UserPlus,
  Trash2,
  GraduationCap,
  Settings,
  ChevronLeft,
  ChevronRight,
  MoreHorizontal,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  HoverCard,
  HoverCardTrigger,
  HoverCardContent,
} from "@/components/ui/hover-card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import {
  listStudentsByClass,
  createStudent,
  deleteStudent,
  listClassTeachers,
  listStudentAnalysis,
} from "@/services/api";
import type { ClassRecord } from "@/types/api";
import { TeacherManageDialog } from "./TeacherManageDialog";
import { TodoAndQuickActions } from "@/components/home/TodoAndQuickActions";
import { ScoresTab } from "./ScoresTab";
import { ExamHistoryTab } from "./ExamHistoryTab";
import { StudentTab } from "./StudentTab";
import { WrongQuestionsTab } from "./WrongQuestionsTab";
import { useAdminAuth } from "@/hooks/useAdminAuth";
import {
  ClassWeeklyReport,
  ClassMasteryDistribution,
} from "./class-weekly/ClassWeeklyReport";
import {
  ClassScoreTrend,
  ClassAbilityRadar,
} from "./class-weekly/ClassAnalyticsPanels";

interface ClassDashboardProps {
  selectedSubject: string;
  selectedClass: string;
  onNavChange: (id: string) => void;
  /** 跳转到学生全景页并定位到指定学生（携带学生标识，避免默认展示第一个学生） */
  onNavigateToStudent?: (studentName: string) => void;
  /** 跳转到靶向提升页并定位到指定学生（携带学生标识，避免回退到上一个/默认学生） */
  onNavigateToTargeted?: (studentName: string) => void;
  /** 当前用户在班级中的角色，用于教师/学生管理权限 */
  classMeta?: ClassRecord | null;
  /** 深链定位 G2 子标签（如「错题变式推荐」→ wrong-questions），缺省 scores */
  initialTab?: string;
}

/* ── deterministic hash ── */
function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

function badgeColor(seed: number) {
  // 统一使用项目主色调 (Primary) 进行柔和渲染
  return {
    bg: "bg-primary/5",
    border: "border-primary/10",
    dot: "bg-primary",
  };
}

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

export function ClassDashboard({
  selectedSubject,
  selectedClass,
  onNavChange,
  onNavigateToStudent,
  onNavigateToTargeted,
  classMeta,
  initialTab,
}: ClassDashboardProps) {
  const { t, locale } = useLocale();
  const { schoolId } = useAdminAuth();

  const [addStudentOpen, setAddStudentOpen] = useState(false);
  const [addTab, setAddTab] = useState<"single" | "batch">("single");
  const [singleName, setSingleName] = useState("");
  const [singleNumber, setSingleNumber] = useState("");
  const [singleGender, setSingleGender] = useState<"男" | "女">("男");
  const [addLoading, setAddLoading] = useState(false);
  const [deleteMode, setDeleteMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [teacherSettingsOpen, setTeacherSettingsOpen] = useState(false);
  const [page, setPage] = useState(0);

  // G2 成绩标签子页：支持深链定位（如「错题变式推荐」→ wrong-questions），缺省 scores
  const [g2Tab, setG2Tab] = useState(initialTab ?? "scores");
  useEffect(() => {
    setG2Tab(initialTab ?? "scores");
  }, [initialTab]);

  const queryClient = useQueryClient();

  const canManageTeachers = classMeta?.my_role === "head";
  // 学生管理（添加/删除）后端仅允许 head，副班主任操作会 403，故前端与后端对齐
  const canManageStudents = classMeta?.my_role === "head";
  const classTitle = useMemo(() => {
    const grade = (classMeta?.grade || "").trim();
    const name = (classMeta?.name || "").trim();
    if (!grade || !name) return "";
    const gradeText = grade.includes("年级") ? grade : `${grade}年级`;
    return `${gradeText}—${name}`;
  }, [classMeta?.grade, classMeta?.name]);

  const {
    data: classTeachers = [],
    isLoading: teachersLoading,
    isError: teachersError,
    refetch: refetchTeachers,
  } = useQuery({
    queryKey: ["class-teachers", selectedClass],
    queryFn: () => listClassTeachers(selectedClass),
    enabled: !!selectedClass,
  });

  const {
    data: apiStudents = [],
    isLoading: studentsLoading,
    isError: studentsError,
    refetch: refetchStudents,
  } = useQuery({
    queryKey: ["students", selectedClass],
    queryFn: () => listStudentsByClass(selectedClass),
    enabled: !!selectedClass,
  });

  // Zone-1 核心指标：基于学生画像（目标分/当前分）推导班级均分、预警学生与成绩覆盖度
  const { data: studentAnalysis = [], isLoading: analysisLoading } = useQuery({
    queryKey: ["student-analysis", "list", selectedClass, selectedSubject],
    queryFn: () => listStudentAnalysis(selectedClass, selectedSubject),
    enabled: !!selectedClass && !!selectedSubject,
  });

  // 查询失败静默兜底：toast 提示
  useEffect(() => {
    if (teachersError) toast.error(t("classDetail.loadTeachersFailed"));
  }, [teachersError]);

  useEffect(() => {
    if (studentsError) toast.error(t("classDetail.loadStudentsFailed"));
  }, [studentsError]);

  // 切换班级后重置分页，避免停留在上一班级的空白页
  useEffect(() => {
    setPage(0);
  }, [selectedClass]);

  /* ── 仅使用接口学生，带 id 用于删除 ── */
  const students = useMemo(() => {
    return apiStudents.map((s) => ({
      id: s.id,
      name: s.name,
      student_number: s.student_number,
      gender: s.gender,
    }));
  }, [apiStudents]);

  /* ── Zone-1 核心指标：由学生画像（target/current score）推导 ── */
  const metrics = useMemo(() => {
    const scored = studentAnalysis.filter(
      (a) => a.current_score != null && a.current_score !== undefined,
    );
    const avg = scored.length
      ? scored.reduce((sum, a) => sum + (a.current_score ?? 0), 0) /
        scored.length
      : null;
    const warningCount = studentAnalysis.filter(
      (a) =>
        a.target_score != null &&
        a.target_score !== undefined &&
        a.current_score != null &&
        a.current_score !== undefined &&
        (a.current_score ?? 0) < (a.target_score ?? 0),
    ).length;
    // 后端无独立“作业完成率”端点，以已录入当前成绩的学生占比近似
    const completionRate = studentAnalysis.length
      ? Math.round((scored.length / studentAnalysis.length) * 100)
      : null;
    return {
      avg,
      warningCount,
      completionRate,
      hasData: studentAnalysis.length > 0,
    };
  }, [studentAnalysis]);

  const toggleDeleteSelection = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleConfirmDelete = async () => {
    if (selectedIds.size === 0) {
      setDeleteConfirmOpen(false);
      return;
    }
    setDeleteLoading(true);
    try {
      for (const id of selectedIds) {
        await deleteStudent(id);
      }
      toast.success(
        t("classDetail.已删除N名学生", { count: selectedIds.size }),
      );
      setSelectedIds(new Set());
      setDeleteMode(false);
      setDeleteConfirmOpen(false);
      queryClient.invalidateQueries({ queryKey: ["students", selectedClass] });
      queryClient.invalidateQueries({ queryKey: ["classes"] });
      // 删除后页码收敛，避免停留在空白页
      setPage((p) =>
        Math.min(
          p,
          Math.max(
            0,
            Math.ceil((students.length - selectedIds.size) / PAGE_SIZE) - 1,
          ),
        ),
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("classDetail.删除失败"));
    } finally {
      setDeleteLoading(false);
    }
  };

  const handleAddSingle = async () => {
    const name = singleName.trim();
    const student_number = singleNumber.trim();
    if (!name) {
      toast.error(t("classDetail.请填写姓名"));
      return;
    }
    setAddLoading(true);
    try {
      await createStudent({
        class_id: selectedClass,
        name,
        ...(student_number ? { student_number } : {}),
        gender: singleGender,
      });
      toast.success(t("classDetail.添加成功"));
      setSingleName("");
      setSingleNumber("");
      setSingleGender("男");
      setAddStudentOpen(false);
      queryClient.invalidateQueries({ queryKey: ["students", selectedClass] });
      queryClient.invalidateQueries({ queryKey: ["classes"] });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("classDetail.添加失败"));
    } finally {
      setAddLoading(false);
    }
  };

  const studentCount = students.length;
  const PAGE_SIZE = 30; // 6 cols * 5 rows
  const totalPages = Math.ceil(studentCount / PAGE_SIZE);
  const pagedStudents = students.slice(
    page * PAGE_SIZE,
    (page + 1) * PAGE_SIZE,
  );

  return (
    <div className="space-y-5 animate-fade-in">
      {classTitle && (
        <div>
          <h1 className="text-xl font-bold text-foreground">{classTitle}</h1>
        </div>
      )}

      {/* ═══ P4: 班级周报（均分/完成率/优秀数 + 共性薄弱点 + 数据来源标注）═══ */}
      <ClassWeeklyReport
        classId={selectedClass}
        subject={selectedSubject}
        className={classMeta?.name}
        studentAnalysis={studentAnalysis}
        analysisLoading={analysisLoading}
      />

      {/* ═══ Zone 1: Core Metrics ═══ */}
      <div
        data-tour="db-metrics"
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
      >
        {/* Average score */}
        <div className="p-5 rounded-xl bg-card border border-border/50 card-elevated">
          <p className="text-sm text-muted-foreground mb-1">
            {t("classDetail.班级均分")}
          </p>
          <div className="mt-3 text-sm text-muted-foreground">
            {analysisLoading
              ? t("classDetail.暂无数据")
              : metrics.avg != null
                ? `${metrics.avg.toFixed(1)}${t("grading.unit.score")}`
                : t("classDetail.暂无数据")}
          </div>
          <div className="mt-2 flex items-center gap-1.5 text-xs">
            <Button
              variant="link"
              size="sm"
              className="p-0 h-auto text-xs"
              disabled
            >
              {t("classDetail.查看详情")} →
            </Button>
            <span className="text-[10px] text-muted-foreground/70">
              {t("classDetail.metricDetailPending")}
            </span>
          </div>
        </div>

        {/* Completion rate */}
        <div className="p-5 rounded-xl bg-card border border-border/50 card-elevated">
          <p className="text-sm text-muted-foreground mb-1">
            {t("classDetail.作业完成率")}
          </p>
          <div className="mt-3 text-sm text-muted-foreground">
            {analysisLoading
              ? t("classDetail.暂无数据")
              : metrics.completionRate != null
                ? `${metrics.completionRate}%`
                : t("classDetail.暂无数据")}
          </div>
          <div className="mt-2 flex items-center gap-1.5 text-xs">
            <Button
              variant="link"
              size="sm"
              className="p-0 h-auto text-xs"
              disabled
            >
              {t("classDetail.查看详情")} →
            </Button>
            <span className="text-[10px] text-muted-foreground/70">
              {t("classDetail.metricDetailPending")}
            </span>
          </div>
        </div>

        {/* Warning students */}
        <div className="p-5 rounded-xl bg-card border border-destructive/20 card-elevated">
          <p className="text-sm text-muted-foreground mb-1">
            {t("classDetail.预警学生")}
          </p>
          <div className="mt-3 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-muted-foreground/60" />
            <span className="text-sm text-muted-foreground">
              {analysisLoading
                ? t("classDetail.暂无数据")
                : metrics.hasData
                  ? `${metrics.warningCount}${t("grading.unit.person")}`
                  : t("classDetail.暂无数据")}
            </span>
          </div>
          <div className="mt-3 flex items-center gap-1.5 text-xs">
            <Button
              variant="link"
              size="sm"
              className="p-0 h-auto text-xs text-muted-foreground"
              disabled
            >
              {t("classDetail.goHandle")} →
            </Button>
            <span className="text-[10px] text-muted-foreground/70">
              {t("classDetail.metricDetailPending")}
            </span>
          </div>
        </div>
      </div>

      {/* ═══ 教师信息 ═══ */}
      <div
        data-tour="db-teachers"
        className="rounded-xl bg-card border border-border/50 p-6 card-elevated"
      >
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <GraduationCap className="w-4 h-4 text-primary" />
            {t("classDetail.teacherInfo", { count: classTeachers.length })}
          </h3>
          {canManageTeachers && (
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 h-8 text-xs"
              onClick={() => setTeacherSettingsOpen(true)}
            >
              <Settings className="w-3.5 h-3.5" />
              {t("classDetail.teacherSettings")}
            </Button>
          )}
        </div>
        <p className="text-xs text-muted-foreground mb-4">
          {t("classDetail.teacherInfoHint")}
        </p>

        {teachersLoading ? (
          <div className="flex items-center justify-center py-8 text-muted-foreground gap-2">
            <Loader2 className="w-4 h-4 animate-spin" />
            {t("classDetail.loadingTeachers")}
          </div>
        ) : teachersError ? (
          <div className="flex flex-col items-center justify-center py-8 rounded-lg border border-dashed bg-muted/20 text-center">
            <p className="text-sm text-muted-foreground mb-2">
              {t("classDetail.loadTeachersFailed")}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetchTeachers()}
            >
              {t("wuyu.retry")}
            </Button>
          </div>
        ) : classTeachers.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 rounded-lg border border-dashed bg-muted/20 text-center">
            <GraduationCap className="w-10 h-10 text-muted-foreground/50 mb-2" />
            <p className="text-sm text-muted-foreground">
              {t("classDetail.noTeachersData")}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2.5 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
            {classTeachers.map((teacher) => (
              <div
                key={teacher.id}
                className="relative flex flex-col items-center gap-1 p-3 rounded-xl border border-border/80 bg-muted/20 hover:bg-muted/40 transition-colors"
              >
                <div className="w-9 h-9 rounded-full bg-primary/80 flex items-center justify-center text-xs font-bold text-primary-foreground">
                  {(teacher.display_name || teacher.email || "?")[0]}
                </div>
                <span className="text-xs font-medium text-foreground truncate w-full text-center">
                  {teacher.display_name ||
                    teacher.email?.split("@")[0] ||
                    t("classDetail.教师")}
                </span>
                <span className="text-[10px] text-muted-foreground truncate w-full text-center">
                  {teacher.subject && teacher.subject !== "__CLEAR__"
                    ? translateSubjectName(locale, teacher.subject)
                    : "—"}
                </span>
                <span className="text-[10px] font-medium text-primary">
                  {teacherRoleLabel(teacher.role, t)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ═══ P4: 知识点掌握分布 + 成绩趋势增强 + 能力雷达叠加 ═══ */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <ClassMasteryDistribution classId={selectedClass} schoolId={schoolId} />
        <ClassScoreTrend
          grade={classMeta?.grade}
          classId={selectedClass}
          className={classMeta?.name}
          subject={selectedSubject}
        />
        <ClassAbilityRadar
          classId={selectedClass}
          subject={selectedSubject}
          className={classMeta?.name}
        />
      </div>

      {/* ═══ Zone 2: 学生信息 ═══ */}
      <div
        data-tour="db-matrix"
        className="rounded-xl bg-card border border-border/50 p-6 card-elevated"
      >
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-base font-semibold text-foreground">
            {t("classDetail.studentInfo", { count: studentCount })}
          </h3>
          <div className="flex items-center gap-2">
            {canManageStudents && (
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5 h-8 text-xs"
                onClick={() => {
                  setAddStudentOpen(true);
                  setAddTab("single");
                }}
              >
                <UserPlus className="w-3.5 h-3.5" />
                {t("settingsClass.table.addStudent")}
              </Button>
            )}
            {canManageStudents &&
              students.length > 0 &&
              (deleteMode ? (
                selectedIds.size > 0 ? (
                  <Button
                    variant="destructive"
                    size="sm"
                    className="gap-1.5 h-8 text-xs"
                    onClick={() => setDeleteConfirmOpen(true)}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    {t("grading.action.batchDelete", {
                      count: selectedIds.size,
                    })}
                  </Button>
                ) : (
                  <Button
                    variant="secondary"
                    size="sm"
                    className="gap-1.5 h-8 text-xs"
                    onClick={() => {
                      setDeleteMode(false);
                      setSelectedIds(new Set());
                    }}
                  >
                    {t("common.cancel")}
                  </Button>
                )
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5 h-8 text-xs"
                  onClick={() => setDeleteMode(true)}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  {t("classDetail.deleteStudent")}
                </Button>
              ))}
          </div>
        </div>
        <p className="text-xs text-muted-foreground mb-4">
          {t("classDetail.hoverStudentHint")}
        </p>

        {studentsLoading ? (
          <div className="flex flex-col items-center justify-center py-16 rounded-lg border border-dashed bg-muted/20 text-center">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground/60 mb-3" />
            <p className="text-sm text-muted-foreground">
              {t("classDetail.studentListLoading")}
            </p>
          </div>
        ) : studentsError ? (
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
              onClick={() => refetchStudents()}
            >
              <RefreshCw className="w-3.5 h-3.5" />
              {t("wuyu.retry")}
            </Button>
          </div>
        ) : students.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 rounded-lg border border-dashed bg-muted/20 text-center">
            <Users2 className="w-12 h-12 text-muted-foreground/50 mb-3" />
            <p className="text-sm font-medium text-foreground mb-1">
              {t("classDetail.暂无学生")}
            </p>
            <p className="text-xs text-muted-foreground mb-4">
              {t("classDetail.addStudentHint")}
            </p>
            {canManageStudents && (
              <Button
                size="sm"
                className="gap-1.5"
                onClick={() => {
                  setAddStudentOpen(true);
                  setAddTab("single");
                }}
              >
                <UserPlus className="w-3.5 h-3.5" />
                {t("settingsClass.table.addStudent")}
              </Button>
            )}
          </div>
        ) : (
          <div className="flex flex-col">
            {/* Grid */}
            <div className="grid grid-cols-2 gap-2.5 min-h-[300px] content-start md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
              {pagedStudents.map((s) => {
                const seed = hash(
                  String(s.name || "") + selectedSubject + selectedClass,
                );
                const c = badgeColor(seed);
                const isSelected = selectedIds.has(s.id);
                return (
                  <HoverCard
                    key={s.id}
                    openDelay={200}
                    open={deleteMode ? false : undefined}
                  >
                    <HoverCardTrigger asChild>
                      {deleteMode ? (
                        <div
                          className={cn(
                            "relative flex flex-col items-center gap-1 p-3 rounded-xl border transition-all duration-200 hover-scale cursor-pointer text-left h-[84px]",
                            c.bg,
                            c.border,
                            isSelected && "ring-2 ring-primary ring-offset-2",
                          )}
                          onClick={() => toggleDeleteSelection(s.id)}
                        >
                          <div
                            className="absolute left-2 top-2 z-10"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <Checkbox
                              checked={isSelected}
                              onCheckedChange={() =>
                                toggleDeleteSelection(s.id)
                              }
                            />
                          </div>
                          <div
                            className={cn(
                              "w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold text-white shrink-0",
                              c.dot,
                            )}
                          >
                            {String(s.name || "—")[0] || "—"}
                          </div>
                          <span className="text-xs font-medium text-foreground truncate w-full text-center mt-auto">
                            {s.name}
                          </span>
                        </div>
                      ) : (
                        <button
                          className={cn(
                            "relative flex flex-col items-center gap-1 p-3 rounded-xl border transition-all duration-200 hover-scale cursor-pointer text-left h-[84px]",
                            c.bg,
                            c.border,
                          )}
                          onClick={() => {
                            if (onNavigateToStudent)
                              onNavigateToStudent(s.name);
                            else onNavChange("class-students");
                          }}
                        >
                          <div
                            className={cn(
                              "w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold text-white shrink-0",
                              c.dot,
                            )}
                          >
                            {String(s.name || "—")[0] || "—"}
                          </div>
                          <span className="text-xs font-medium text-foreground truncate w-full text-center mt-auto">
                            {s.name}
                          </span>
                        </button>
                      )}
                    </HoverCardTrigger>
                    <HoverCardContent className="w-[260px] p-4" side="bottom">
                      <div className="flex items-center gap-3 mb-3">
                        <div
                          className={cn(
                            "w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white",
                            c.dot,
                          )}
                        >
                          {String(s.name || "—")[0] || "—"}
                        </div>
                        <div>
                          <p className="text-sm font-semibold text-foreground">
                            {s.name}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {String(s.student_number || "").trim()
                              ? t("home.students.studentNumber", {
                                  number: String(s.student_number).trim(),
                                })
                              : t("home.students.studentNumberEmpty")}
                            {String(s.gender || "").trim()
                              ? t("home.students.gender", {
                                  gender: String(s.gender).trim(),
                                })
                              : ""}
                          </p>
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          className="text-xs h-7"
                          onClick={() =>
                            onNavigateToStudent
                              ? onNavigateToStudent(s.name)
                              : onNavChange("class-students")
                          }
                        >
                          {t("home.students.viewPortrait")}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="text-xs h-7"
                          onClick={() =>
                            onNavigateToTargeted
                              ? onNavigateToTargeted(s.name)
                              : onNavChange("ai-targeted")
                          }
                        >
                          {t("home.students.pushExercise")}
                        </Button>
                      </div>
                    </HoverCardContent>
                  </HoverCard>
                );
              })}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4 pt-3 border-t border-border shrink-0">
                <div className="flex items-center gap-1">
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={page === 0 || totalPages === 0}
                    aria-label={t("grading.dashboard.prevPageAria")}
                  >
                    <ChevronLeft className="w-3.5 h-3.5" />
                  </Button>

                  <div className="flex items-center gap-1">
                    {Array.from({ length: totalPages }, (_, i) => {
                      if (
                        i === 0 ||
                        i === totalPages - 1 ||
                        (i >= page - 1 && i <= page + 1)
                      ) {
                        return (
                          <Button
                            key={i}
                            size="sm"
                            variant={page === i ? "default" : "outline"}
                            className="h-7 w-7 p-0 text-sm"
                            onClick={() => setPage(i)}
                          >
                            {i + 1}
                          </Button>
                        );
                      }
                      if (i === page - 2 || i === page + 2) {
                        return (
                          <div
                            key={i}
                            className="h-7 w-7 flex items-center justify-center text-muted-foreground"
                          >
                            <MoreHorizontal className="w-3 h-3" />
                          </div>
                        );
                      }
                      return null;
                    })}
                  </div>

                  <Button
                    variant="outline"
                    size="icon"
                    className="h-7 w-7"
                    onClick={() =>
                      setPage((p) => Math.min(totalPages - 1, p + 1))
                    }
                    disabled={page === totalPages - 1 || totalPages === 0}
                    aria-label={t("grading.dashboard.nextPageAria")}
                  >
                    <ChevronRight className="w-3.5 h-3.5" />
                  </Button>
                </div>
                <span className="text-xs text-muted-foreground">
                  {t("classDetail.totalCount", { count: studentCount })}
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ═══ Zone G2: 成绩标签子页面（成绩/考试/学生/错题）═══ */}
      <div
        data-tour="db-g2"
        className="rounded-xl bg-card border border-border/50 p-6 card-elevated"
      >
        <h3 className="text-base font-semibold text-foreground flex items-center gap-2 mb-4">
          <ClipboardList className="w-4 h-4 text-primary" />
          {t("grading.g2.title")}
        </h3>
        <Tabs value={g2Tab} onValueChange={setG2Tab}>
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="scores">{t("grading.g2.scores")}</TabsTrigger>
            <TabsTrigger value="exams">{t("grading.g2.exams")}</TabsTrigger>
            <TabsTrigger value="students">
              {t("grading.g2.students")}
            </TabsTrigger>
            <TabsTrigger value="wrong-questions">
              {t("grading.g2.wrongQuestions")}
            </TabsTrigger>
          </TabsList>
          <TabsContent value="scores">
            <ScoresTab
              classId={selectedClass}
              initialSubject={selectedSubject}
            />
          </TabsContent>
          <TabsContent value="exams">
            <ExamHistoryTab classId={selectedClass} />
          </TabsContent>
          <TabsContent value="students">
            <StudentTab
              classId={selectedClass}
              className={classMeta?.name || ""}
            />
          </TabsContent>
          <TabsContent value="wrong-questions">
            <WrongQuestionsTab classId={selectedClass} />
          </TabsContent>
        </Tabs>
      </div>

      {/* ═══ Zone 3: Todo + Quick Actions ═══ */}
      <TodoAndQuickActions
        selectedSubject={selectedSubject}
        selectedClass={selectedClass}
        onNavChange={onNavChange}
      />

      <TeacherManageDialog
        open={teacherSettingsOpen}
        onOpenChange={setTeacherSettingsOpen}
        classId={selectedClass}
        canManage={canManageTeachers}
        subtitle={
          classMeta?.name
            ? t("classDetail.manageTeachersSubtitle", { name: classMeta.name })
            : t("classDetail.管理本班协作教师 添加 调整角色或移除")
        }
      />

      {/* 添加学生弹窗 */}
      <Dialog open={addStudentOpen} onOpenChange={setAddStudentOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("settingsClass.table.addStudent")}</DialogTitle>
            <DialogDescription>
              {t("classDetail.addStudentDescription")}
            </DialogDescription>
          </DialogHeader>
          <Tabs
            value={addTab}
            onValueChange={(v) => setAddTab(v as "single" | "batch")}
          >
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="single">
                {t("classDetail.addSingle")}
              </TabsTrigger>
              <TabsTrigger value="batch">
                {t("classDetail.addBatch")}
              </TabsTrigger>
            </TabsList>
            <TabsContent value="single" className="space-y-4 pt-4">
              <div className="space-y-2">
                <Label htmlFor="student-number">
                  {t("wuyu.studentNumber")}
                </Label>
                <Input
                  id="student-number"
                  placeholder={t("classDetail.可不填")}
                  value={singleNumber}
                  onChange={(e) => setSingleNumber(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="student-name">{t("classDetail.姓名")}</Label>
                <Input
                  id="student-name"
                  placeholder={t("classDetail.必填")}
                  value={singleName}
                  onChange={(e) => setSingleName(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label>{t("settingsClass.table.colGender")}</Label>
                <Select
                  value={singleGender}
                  onValueChange={(v) => setSingleGender(v as "男" | "女")}
                >
                  <SelectTrigger>
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
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setAddStudentOpen(false)}
                >
                  {t("common.cancel")}
                </Button>
                <Button onClick={handleAddSingle} disabled={addLoading}>
                  {addLoading ? t("classDetail.添加中") : t("classDetail.确定")}
                </Button>
              </DialogFooter>
            </TabsContent>
            <TabsContent value="batch" className="pt-4">
              <div className="rounded-lg border border-dashed bg-muted/30 p-6 text-center text-sm text-muted-foreground">
                {t("classDetail.batchComingSoon")}
              </div>
            </TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>

      {/* 删除学生确认弹窗 */}
      <AlertDialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("classDetail.确认删除")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("classDetail.confirmDeleteStudents", {
                count: selectedIds.size,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteLoading}>
              {t("common.cancel")}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                handleConfirmDelete();
              }}
              disabled={deleteLoading}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteLoading
                ? t("classDetail.删除中")
                : t("classDetail.确认删除")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
