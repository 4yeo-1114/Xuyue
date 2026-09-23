import { useState, useMemo } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Users2, BookOpen, Stethoscope, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  StudentListPanel,
  type StudentSummary,
} from "./student-panorama/StudentListPanel";
import { StudentProfilePanel } from "./student-panorama/StudentProfilePanel";
import {
  StudentPanoramaTour,
  TipDismissProvider,
} from "./student-panorama/StudentPanoramaTour";
import {
  listStudentsByClass,
  listStudentAnalysis,
  runAIDiagnosis,
} from "@/services/api";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { PrivacyNoticeDialog } from "@/components/common/PrivacyNoticeDialog";
import { Download } from "lucide-react";
import { ImportScoresDialog } from "./student-panorama/ImportScoresDialog";
import { toast } from "sonner";
import { translateSubjectName } from "@/i18n";

/* ── deterministic hash ── */
function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

const WEAK_POINTS: Record<string, string[]> = {
  语文: ["作文结构", "阅读理解", "文言文翻译", "诗词鉴赏", "语言运用"],
  数学: ["函数图像", "几何证明", "概率统计", "数列求和", "立体几何"],
  英语: ["完形填空", "语法时态", "写作表达", "听力理解", "词汇运用"],
  物理: ["力学分析", "电路计算", "能量守恒", "光学原理", "波动分析"],
  化学: ["化学方程式", "氧化还原", "电化学", "有机反应", "实验设计"],
};

interface StudentPanoramaPageProps {
  selectedSubject: string;
  selectedClass: string;
  onNavChange: (id: string) => void;
  initialStudentName?: string;
  onNavigateToTargeted?: (studentName: string) => void;
}

const SUBJECTS = ["语文", "数学", "英语", "科学"];

export function StudentPanoramaPage({
  selectedSubject,
  selectedClass,
  onNavChange,
  initialStudentName,
  onNavigateToTargeted,
}: StudentPanoramaPageProps) {
  const { t, locale } = useLocale();

  const queryClient = useQueryClient();
  const [localSubject, setLocalSubject] = useState(() => {
    try {
      const saved = localStorage.getItem("student_panorama_subject");
      return saved && SUBJECTS.includes(saved)
        ? saved
        : selectedSubject || "语文";
    } catch {
      return selectedSubject || "语文";
    }
  });
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [noticeOpen, setNoticeOpen] = useState(false);

  const handleSubjectChange = (v: string) => {
    setLocalSubject(v);
    try {
      localStorage.setItem("student_panorama_subject", v);
    } catch {
      // 存储失败（隐私模式/配额）静默忽略
    }
  };

  const {
    data: apiStudents = [],
    isLoading: studentsLoading,
    isError: studentsError,
  } = useQuery({
    queryKey: ["students", selectedClass],
    queryFn: () => listStudentsByClass(selectedClass),
    enabled: !!selectedClass,
  });

  const {
    data: analysisList = [],
    isLoading: analysisLoading,
    isError: analysisError,
  } = useQuery({
    queryKey: ["student-analysis-list", selectedClass, localSubject],
    queryFn: () => listStudentAnalysis(selectedClass, localSubject),
    enabled: !!selectedClass && !!localSubject,
  });

  const students: StudentSummary[] = useMemo(() => {
    return apiStudents.map((s) => {
      const analysis = analysisList.find((a) => a.student_name === s.name);
      return {
        name: s.name,
        studentNumber: s.student_number || "—",
        targetScore: analysis?.target_score,
        currentScore: analysis?.current_score,
      };
    });
  }, [apiStudents, analysisList]);

  const sortedNames = useMemo(() => {
    return [...students].sort((a, b) => a.name.localeCompare(b.name, "zh"));
  }, [students]);

  const [selectedName, setSelectedName] = useState<string | null>(
    initialStudentName || sortedNames[0]?.name || null,
  );

  const selectedStudent = students.find((s) => s.name === selectedName);

  const { mutate: doAIDiagnosis, isPending: isDiagnosing } = useMutation({
    mutationFn: () =>
      runAIDiagnosis({
        class_id: selectedClass,
        student_name: selectedName!,
        subject: localSubject,
      }),
    onSuccess: () => {
      toast.success(t("studentAnalysis.diagnosisSuccess"));
      queryClient.invalidateQueries({
        queryKey: ["ai-diagnosis", selectedClass, selectedName, localSubject],
      });
    },
    onError: (err: any) => {
      toast.error(t("studentAnalysis.diagnosisFailed"), {
        description: err.message,
      });
    },
  });

  return (
    <TipDismissProvider>
      <div className="space-y-3 animate-fade-in">
        <StudentPanoramaTour />

        {/* Top bar for subject selection */}
        <div className="flex items-center justify-between bg-card border border-border/50 rounded-xl p-3 px-5">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
              <BookOpen className="w-4 h-4 text-primary" />
            </div>
            <span className="font-medium text-foreground">
              {t("studentAnalysis.currentSubject")}
            </span>
            <span className="text-xl font-bold text-red-500 ml-1 bg-red-50 px-3 py-1 rounded-md">
              {translateSubjectName(locale, localSubject)}
            </span>
            <Button
              variant="outline"
              size="sm"
              className="ml-4 h-8 text-xs"
              onClick={() => setImportDialogOpen(true)}
            >
              <Download className="w-3.5 h-3.5 mr-1" />{" "}
              {t("studentAnalysis.importScores")}
            </Button>
            <Button
              size="sm"
              className="ml-2 h-8 text-xs gap-1.5"
              onClick={() => setNoticeOpen(true)}
              disabled={!selectedName || isDiagnosing}
            >
              {isDiagnosing ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Stethoscope className="w-3.5 h-3.5" />
              )}
              {isDiagnosing
                ? t("studentAnalysis.diagnosing")
                : t("studentAnalysis.diagnose")}
            </Button>
          </div>
          <Select value={localSubject} onValueChange={handleSubjectChange}>
            <SelectTrigger className="w-[180px] h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SUBJECTS.map((s) => (
                <SelectItem key={s} value={s}>
                  {translateSubjectName(locale, s)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex h-[calc(100vh-13rem)] rounded-xl border border-border/50 bg-card overflow-hidden">
          {/* Left: Student List (35%) */}
          <div
            data-tour="sp-student-list"
            className="w-[35%] border-r border-border/50 flex flex-col min-w-0"
          >
            {studentsLoading ? (
              <div className="flex flex-1 items-center justify-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                {t("classDetail.studentPanorama.loading")}
              </div>
            ) : studentsError ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-3 p-4 text-center text-sm text-muted-foreground">
                <Users2 className="h-8 w-8 opacity-30" />
                <p>{t("classDetail.studentPanorama.loadStudentsFailed")}</p>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    queryClient.invalidateQueries({
                      queryKey: ["students", selectedClass],
                    })
                  }
                >
                  {t("classDetail.studentPanorama.retry")}
                </Button>
              </div>
            ) : (
              <StudentListPanel
                students={students}
                selectedName={selectedName}
                onSelect={setSelectedName}
                initialStudentName={initialStudentName}
              />
            )}
            {!studentsLoading &&
              !studentsError &&
              (analysisLoading || analysisError) && (
                <div className="border-t border-border/50 px-3 py-2 text-[11px] text-muted-foreground">
                  {analysisLoading ? (
                    <span className="inline-flex items-center gap-1.5">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      {t("classDetail.studentPanorama.analysisLoading")}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-2">
                      {t("classDetail.studentPanorama.analysisFailed")}
                      <button
                        className="text-primary hover:underline"
                        onClick={() =>
                          queryClient.invalidateQueries({
                            queryKey: [
                              "student-analysis-list",
                              selectedClass,
                              localSubject,
                            ],
                          })
                        }
                      >
                        {t("classDetail.studentPanorama.retry")}
                      </button>
                    </span>
                  )}
                </div>
              )}
          </div>

          {/* Right: Profile Panel (65%) */}
          <div data-tour="sp-profile-panel" className="w-[65%] min-w-0">
            {selectedStudent ? (
              <StudentProfilePanel
                student={selectedStudent as any}
                selectedSubject={localSubject}
                selectedClass={selectedClass}
                classAvg={80}
                onNavChange={onNavChange}
                onNavigateToTargeted={onNavigateToTargeted}
              />
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                <Users2 className="w-12 h-12 opacity-30 mb-3" />
                <p className="text-sm font-medium">
                  {t("studentAnalysis.selectStudent")}
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
      <ImportScoresDialog
        open={importDialogOpen}
        onOpenChange={setImportDialogOpen}
        classId={selectedClass}
        subject={localSubject}
      />
      <PrivacyNoticeDialog
        open={noticeOpen}
        onOpenChange={setNoticeOpen}
        onConfirm={() => doAIDiagnosis()}
        context="学生 AI 诊断"
      />
    </TipDismissProvider>
  );
}
