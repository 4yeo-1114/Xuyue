import { useState, useMemo, useEffect } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAdminAuth } from "@/hooks/useAdminAuth";
import {
  getStudentAnalysis,
  updateStudentAnalysis,
  getStudentScoreHistory,
  deleteExamHistory,
  listStudentsByClass,
} from "@/services/api";
import { getAIDiagnosis, getLatestWrongQuestions } from "@/services/api";
import { getMasteryDistribution } from "@/services/dashboardApi";
import { gradingImageUrl } from "@/services/gradingApi";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Tooltip as UITooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import {
  Target,
  Phone,
  Pencil,
  Clock,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Stethoscope,
  Eye,
  CalendarDays,
  CheckCircle2,
  ArrowRight,
  TrendingUp,
  Settings2,
  Trash2,
  RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  Radar,
} from "recharts";
import type { StudentSummary } from "./StudentListPanel";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { WrongQuestionDetailDialog } from "./WrongQuestionDetailDialog";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";

/* ── helpers ── */
function masteryColor(v: number) {
  if (v >= 80) return "text-emerald-600";
  if (v >= 60) return "text-yellow-600";
  if (v >= 50) return "text-orange-600";
  return "text-destructive";
}

function masteryBarColor(v: number) {
  if (v >= 80) return "[&>div]:bg-emerald-500";
  if (v >= 60) return "[&>div]:bg-yellow-500";
  if (v >= 50) return "[&>div]:bg-orange-500";
  return "[&>div]:bg-destructive";
}

function masteryBadge(v: number, t: (key: string) => string) {
  if (v >= 80)
    return {
      label: t("studentAnalysis.mastery.good"),
      cls: "bg-emerald-500/15 text-emerald-700",
    };
  if (v >= 60)
    return {
      label: t("studentAnalysis.mastery.improve"),
      cls: "bg-yellow-500/15 text-yellow-700",
    };
  if (v >= 50)
    return {
      label: t("studentAnalysis.mastery.weak"),
      cls: "bg-orange-500/15 text-orange-700",
    };
  return {
    label: t("studentAnalysis.mastery.severe"),
    cls: "bg-destructive/15 text-destructive",
  };
}

/* ── Sub-dimension data per subject ── */
const SUB_DIMS: Record<string, Record<string, string[]>> = {
  语文: {
    作文结构: ["开头结尾", "段落衔接", "论点论据", "结构布局"],
    阅读理解: ["信息提取", "推理判断", "主旨概括", "鉴赏评价"],
    基础知识: ["字词辨析", "成语运用", "标点符号", "语病辨析"],
    古诗文: ["实词虚词", "句式翻译", "诗词鉴赏", "文化常识"],
    语言表达: ["修辞手法", "句式变换", "词语运用", "标点符号", "语段概括"],
    创新思维: ["发散思维", "批判性思考", "跨学科联系", "创意表达"],
  },
  数学: {
    计算能力: ["整数运算", "分数运算", "方程求解", "不等式"],
    逻辑推理: ["充分必要", "反证法", "归纳推理", "演绎推理"],
    空间想象: ["三视图", "截面分析", "旋转体", "空间坐标"],
    数据分析: ["统计量计算", "概率计算", "回归分析", "数据解读"],
    建模应用: ["方程建模", "函数建模", "不等式建模", "优化问题"],
    创新思维: ["一题多解", "数形结合", "转化思想", "类比推理"],
  },
  英语: {
    听力理解: ["短对话", "长对话", "独白理解", "信息记录"],
    口语表达: ["日常会话", "话题陈述", "看图说话", "角色扮演"],
    阅读理解: ["细节理解", "推理判断", "主旨大意", "词义猜测"],
    写作能力: ["应用文", "议论文", "记叙文", "图表作文"],
    词汇语法: ["词汇辨析", "时态语态", "从句运用", "非谓语"],
    翻译能力: ["英译中", "中译英", "长句翻译", "文化翻译"],
  },
};

/* ── 查询失败内联提示（与左侧学生列表加载失败处理对齐）── */
function InlineQueryError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  const { t } = useLocale();
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-destructive/30 bg-destructive/5 p-4 text-sm text-muted-foreground">
      <AlertTriangle className="h-5 w-5 text-destructive/60" />
      <p className="text-center">{message}</p>
      <Button size="sm" variant="outline" className="gap-1.5" onClick={onRetry}>
        <RefreshCw className="h-3.5 w-3.5" />
        {t("classDetail.studentPanorama.retry")}
      </Button>
    </div>
  );
}

interface StudentProfilePanelProps {
  student: StudentSummary;
  selectedSubject: string;
  selectedClass: string;
  classAvg: number;
  onNavChange: (id: string) => void;
  onNavigateToTargeted?: (studentName: string) => void;
}

export function StudentProfilePanel({
  student,
  selectedSubject,
  selectedClass,
  classAvg,
  onNavChange,
  onNavigateToTargeted,
}: StudentProfilePanelProps) {
  const { t, locale } = useLocale();
  const analysisLabel = (value: string) =>
    t(`studentAnalysis.label.${value}`, undefined, value);

  const queryClient = useQueryClient();
  // Safe destructuring with fallback values to prevent white screen
  const name = student?.name || t("studentAnalysis.profile.unknown");
  const studentNumber = student?.studentNumber || "—";

  const [expandedDim, setExpandedDim] = useState<string | null>(null);
  const [wrongDialog, setWrongDialog] = useState<{
    open: boolean;
    category: string;
    subPoint: string | null;
    count: number;
  }>({ open: false, category: "", subPoint: null, count: 0 });
  const [manageHistoryOpen, setManageHistoryOpen] = useState(false);

  /* ── Score history (Up to 9 entries from DB) ── */
  const {
    data: scoreHistoryData,
    isError: scoreHistoryError,
    refetch: refetchScoreHistory,
  } = useQuery({
    queryKey: ["student-score-history", selectedClass, name, selectedSubject],
    queryFn: () => getStudentScoreHistory(selectedClass, name, selectedSubject),
    enabled: !!selectedClass && !!name && !!selectedSubject,
  });

  const { mutate: handleDeleteExam } = useMutation({
    mutationFn: (examName: string) =>
      deleteExamHistory(selectedClass, name, selectedSubject, examName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["student-score-history"] });
      queryClient.invalidateQueries({
        queryKey: ["student-latest-wrong-questions"],
      });
      queryClient.invalidateQueries({ queryKey: ["student-analysis"] });
      queryClient.invalidateQueries({ queryKey: ["student-analysis-list"] });
      toast.success(t("studentAnalysis.profile.deleteSuccess"));
    },
    onError: (err: any) => {
      toast.error(t("studentAnalysis.profile.deleteFailed"), {
        description: err.message,
      });
    },
  });

  const scoreHistory: any[] = useMemo(() => {
    if (!scoreHistoryData || scoreHistoryData.length === 0) return [];

    // Fill up to 9 slots from the left to make sure lines start from left
    const result = scoreHistoryData.map((item, index) => {
      const d = new Date(item.created_at);
      const mmdd = `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      // Add index to avoid duplicated categories collapsing the chart
      return {
        date: `${item.exam_name || mmdd} `,
        score: item.score,
        classAvg: item.class_avg || classAvg || 0, // Using real class avg if available
      };
    });

    // Pad the rest with empty data to ensure it aligns left
    while (result.length < 9) {
      result.push({
        date: `  ${result.length}  `, // Invisible unique placeholder
        score: null as any,
        classAvg: null as any,
      });
    }

    return result;
  }, [scoreHistoryData, classAvg]);

  const {
    data: aiDiagnosisData,
    isError: aiDiagnosisError,
    refetch: refetchAIDiagnosis,
  } = useQuery({
    queryKey: ["ai-diagnosis", selectedClass, name, selectedSubject],
    queryFn: () => getAIDiagnosis(selectedClass, name, selectedSubject),
    enabled: !!selectedClass && !!name && !!selectedSubject,
  });

  /* ── 掌握度真实化（BE-1）：无 AI 诊断时用错题分布派生聚合，替代硬编码 0 分 ── */
  const { schoolId } = useAdminAuth();
  // 学生行复用父级同 key 查询（TanStack Query 同 key 去重，不重复发请求），拿 student_id
  const { data: studentRows = [] } = useQuery({
    queryKey: ["students", selectedClass],
    queryFn: () => listStudentsByClass(selectedClass),
    enabled: !!selectedClass,
  });
  const studentId = useMemo(
    () => studentRows.find((s) => s.name === name)?.id,
    [studentRows, name],
  );

  const studentMasteryQuery = useQuery({
    queryKey: ["mastery-distribution", schoolId, "student", studentId ?? ""],
    queryFn: () =>
      getMasteryDistribution(schoolId!, { student_id: studentId! }),
    enabled: !!schoolId && !!studentId,
  });
  const classMasteryQuery = useQuery({
    queryKey: ["mastery-distribution", schoolId, "class", selectedClass],
    queryFn: () =>
      getMasteryDistribution(schoolId!, { class_id: selectedClass }),
    enabled: !!schoolId && !!selectedClass,
  });

  /* ── Radar data (6 dimensions) ── */
  const radarDims = useMemo(() => {
    if (aiDiagnosisData && aiDiagnosisData.length > 0) {
      return aiDiagnosisData;
    }
    const dims =
      selectedSubject === "数学"
        ? [
            "计算能力",
            "逻辑推理",
            "空间想象",
            "数据分析",
            "建模应用",
            "创新思维",
          ]
        : selectedSubject === "英语"
          ? [
              "听力理解",
              "口语表达",
              "阅读理解",
              "写作能力",
              "词汇语法",
              "翻译能力",
            ]
          : [
              "作文结构",
              "阅读理解",
              "基础知识",
              "古诗文",
              "语言表达",
              "创新思维",
            ];
    const subjectKey =
      Object.keys(SUB_DIMS).find((k) => selectedSubject.includes(k)) || "语文";
    // 错题分布派生掌握度 → 知识点名 → 0-100
    const studentByKp = new Map(
      (studentMasteryQuery.data ?? []).map((i) => [
        i.name,
        Math.round(i.mastery * 100),
      ]),
    );
    const classByKp = new Map(
      (classMasteryQuery.data ?? []).map((i) => [
        i.name,
        Math.round(i.mastery * 100),
      ]),
    );
    return dims.map((dim) => {
      const subs = SUB_DIMS[subjectKey]?.[dim] ?? [
        "基础",
        "应用",
        "综合",
        "拓展",
      ];
      const subDims = subs.map((sub) => ({
        name: sub,
        mastery: studentByKp.has(sub) ? studentByKp.get(sub)! : 0,
      }));
      const matched = subDims.filter((s) => studentByKp.has(s.name));
      const student =
        matched.length > 0
          ? Math.round(
              matched.reduce((acc, s) => acc + s.mastery, 0) / matched.length,
            )
          : 0;
      const classMatched = subs.filter((sub) => classByKp.has(sub));
      const classVal =
        classMatched.length > 0
          ? Math.round(
              classMatched.reduce((acc, sub) => acc + classByKp.get(sub)!, 0) /
                classMatched.length,
            )
          : 0;
      return { dim, student, class: classVal, subDims };
    });
  }, [
    name,
    selectedSubject,
    aiDiagnosisData,
    studentMasteryQuery.data,
    classMasteryQuery.data,
  ]);

  const belowAvg = radarDims.filter((d) => d.student < d.class).length;
  const aboveAvg = radarDims.filter((d) => d.student > d.class).length;

  /* ── Sub-dimension mastery ── */
  const getSubDimMastery = (dim: string) => {
    const dimData = radarDims.find((d) => d.dim === dim);
    if (dimData && dimData.subDims && dimData.subDims.length > 0) {
      return dimData.subDims;
    }
    const subjectKey =
      Object.keys(SUB_DIMS).find((k) => selectedSubject.includes(k)) || "语文";
    const subs = SUB_DIMS[subjectKey]?.[dim] || [
      "基础",
      "应用",
      "综合",
      "拓展",
    ];
    return subs.map((sub) => ({
      name: sub,
      mastery: 0,
    }));
  };

  /* ── Wrong questions (from API) ── */
  const {
    data: latestWrongQuestions,
    isError: wrongQuestionsError,
    refetch: refetchWrongQuestions,
  } = useQuery({
    queryKey: [
      "student-latest-wrong-questions",
      selectedClass,
      name,
      selectedSubject,
    ],
    queryFn: () =>
      getLatestWrongQuestions(selectedClass, name, selectedSubject),
    enabled: !!selectedClass && !!name && !!selectedSubject,
  });

  const totalWrong = latestWrongQuestions?.questions?.length || 0;

  const goToTargeted = () =>
    onNavigateToTargeted
      ? onNavigateToTargeted(name)
      : onNavChange("ai-targeted");

  /* ── Goal ── */
  const {
    data: analysisData,
    isError: analysisError,
    refetch: refetchAnalysis,
  } = useQuery({
    queryKey: ["student-analysis", selectedClass, name, selectedSubject],
    queryFn: () => getStudentAnalysis(selectedClass, name, selectedSubject),
    enabled: !!selectedClass && !!name && !!selectedSubject,
  });

  const { mutate: saveAnalysis } = useMutation({
    mutationFn: updateStudentAnalysis,
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["student-analysis", selectedClass, name, selectedSubject],
      });
      queryClient.invalidateQueries({
        queryKey: ["student-analysis-list", selectedClass, selectedSubject],
      });
      toast.success(t("studentAnalysis.profile.saveSuccess"));
    },
    onError: (err: any) => {
      toast.error(t("studentAnalysis.profile.saveFailed"), {
        description: err.message,
      });
    },
  });

  const [inputTarget, setInputTarget] = useState<string>("");
  const [inputCurrent, setInputCurrent] = useState<string>("");

  useEffect(() => {
    if (analysisData) {
      setInputTarget(
        analysisData.target_score != null
          ? String(analysisData.target_score)
          : "",
      );
      setInputCurrent(
        analysisData.current_score != null
          ? String(analysisData.current_score)
          : "",
      );
    }
  }, [analysisData]);

  const handleSaveScore = () => {
    saveAnalysis({
      class_id: selectedClass,
      student_name: name,
      subject: selectedSubject,
      target_score: inputTarget !== "" ? parseInt(inputTarget, 10) : null,
      current_score: inputCurrent !== "" ? parseInt(inputCurrent, 10) : null,
    });
  };

  const targetScoreVal =
    analysisData?.target_score != null ? analysisData.target_score : null;
  const currentScoreVal =
    analysisData?.current_score != null ? analysisData.current_score : null;

  const hasBothScores = targetScoreVal != null && currentScoreVal != null;
  const goalProgress = hasBothScores
    ? Math.round((currentScoreVal / (targetScoreVal || 1)) * 100) || 0
    : 0;
  const gap = hasBothScores ? targetScoreVal - currentScoreVal : 0;
  const needSpeedUp =
    hasBothScores && gap > 0 && targetScoreVal
      ? Math.round((gap / (targetScoreVal * 0.5)) * 100)
      : 0;

  return (
    <div className="h-full overflow-y-auto px-5 py-4 space-y-5">
      {/* ═══ Header: Identity ═══ */}
      <div className="rounded-xl bg-card border border-border/50 p-5">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-full flex items-center justify-center text-xl font-bold text-white bg-primary">
            {name[0]}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-lg font-bold text-foreground">{name}</h2>
            </div>
            <p className="text-sm text-muted-foreground mt-0.5">
              {t("studentAnalysis.profile.studentNumber", {
                number: studentNumber,
              })}
            </p>
          </div>
        </div>

        <div className="flex gap-2 mt-4 flex-wrap">
          <UITooltip>
            <TooltipTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5 text-xs"
                disabled
              >
                <Phone className="w-3.5 h-3.5" />{" "}
                {t("studentAnalysis.profile.contactParent")}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t("common.comingSoon")}</TooltipContent>
          </UITooltip>
        </div>
      </div>

      {/* ═══ Module 1: Score History ═══ */}
      <div
        data-tour="sp-score-history"
        className="rounded-xl bg-card border border-border/50 p-5"
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-primary" />{" "}
            {t("studentAnalysis.profile.scoreHistory")}
          </h3>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-xs text-muted-foreground hover:text-foreground"
            onClick={() => setManageHistoryOpen(true)}
          >
            <Settings2 className="w-3.5 h-3.5 mr-1" />{" "}
            {t("studentAnalysis.profile.manage")}
          </Button>
        </div>

        {scoreHistoryError && (
          <InlineQueryError
            message={t("studentAnalysis.profile.scoreHistoryFailed")}
            onRetry={refetchScoreHistory}
          />
        )}

        {/* Visual Chain List */}
        {scoreHistoryData && scoreHistoryData.length > 0 && (
          <div className="flex items-center gap-2 overflow-x-auto pb-4 mb-2 scrollbar-thin scrollbar-thumb-muted scrollbar-track-transparent">
            {scoreHistoryData.map((item, idx) => {
              const isLatest = idx === scoreHistoryData.length - 1;
              return (
                <div
                  key={item.id || idx}
                  className="flex items-center shrink-0"
                >
                  <div className="flex flex-col items-center justify-center min-w-[72px]">
                    <div
                      className={cn(
                        "w-12 h-12 rounded-xl border-[3px] flex items-center justify-center font-black text-lg shadow-sm relative z-10 transition-all",
                        isLatest
                          ? "border-primary bg-primary text-primary-foreground shadow-md scale-110"
                          : "border-primary/60 bg-primary/10 text-primary hover:bg-primary/20 hover:border-primary/80",
                      )}
                    >
                      {item.score}
                    </div>
                    <div
                      className={cn(
                        "text-xs mt-2 w-[72px] text-center truncate px-1",
                        isLatest
                          ? "text-primary font-bold"
                          : "text-muted-foreground font-medium",
                      )}
                      title={item.exam_name}
                    >
                      {item.exam_name || t("studentAnalysis.profile.unnamed")}
                    </div>
                  </div>
                  {idx < scoreHistoryData.length - 1 && (
                    <div className="w-10 h-[3px] bg-primary/30 mx-1 -mt-6 rounded-full" />
                  )}
                </div>
              );
            })}
          </div>
        )}

        <div className="h-[180px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={scoreHistory}
              margin={{ top: 15, right: 30, left: -20, bottom: 0 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="hsl(var(--border))"
                opacity={0.6}
                vertical={false}
              />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                stroke="hsl(var(--border))"
                padding={{ left: 10, right: 10 }}
                type="category"
                allowDuplicatedCategory={false}
                axisLine={false}
                tickLine={false}
                dy={10}
              />
              <YAxis
                domain={[0, 120]}
                ticks={[0, 20, 40, 60, 80, 100, 120]}
                tickCount={7}
                interval={0}
                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                stroke="hsl(var(--border))"
                axisLine={false}
                tickLine={false}
                dx={-10}
              />
              <Tooltip
                contentStyle={{
                  fontSize: 12,
                  borderRadius: 8,
                  border: "none",
                  boxShadow:
                    "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)",
                }}
                formatter={(v: number, name: string) => [
                  t("studentAnalysis.profile.points", { value: v }),
                  name === "score"
                    ? t("studentAnalysis.profile.studentScore")
                    : t("studentAnalysis.profile.classAverage"),
                ]}
                labelFormatter={(label) => String(label).trim()}
                cursor={{
                  stroke: "hsl(var(--primary))",
                  strokeWidth: 1,
                  strokeDasharray: "4 4",
                  opacity: 0.2,
                }}
              />
              <ReferenceLine
                y={60}
                stroke="hsl(var(--destructive))"
                strokeDasharray="4 4"
                strokeWidth={1}
                opacity={0.6}
              />
              <Line
                type="monotone"
                dataKey="classAvg"
                stroke="hsl(var(--muted-foreground))"
                strokeWidth={2}
                strokeDasharray="4 4"
                dot={false}
                name={t("studentAnalysis.profile.classAverage")}
              />
              <Line
                type="monotone"
                dataKey="score"
                stroke="hsl(var(--primary))"
                strokeWidth={3}
                dot={{ r: 4, fill: "hsl(var(--background))", strokeWidth: 2 }}
                activeDot={{
                  r: 6,
                  fill: "hsl(var(--primary))",
                  strokeWidth: 0,
                }}
                name="score"
                label={{
                  position: "top",
                  fill: "hsl(var(--primary))",
                  fontSize: 12,
                  fontWeight: 600,
                  dy: -8,
                }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ═══ Module 2: Learning Goal (Enhanced) ═══ */}
      <div
        data-tour="sp-learning-goal"
        className="rounded-xl bg-card border border-border/50 p-5"
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Target className="w-4 h-4 text-primary" />{" "}
            {t("studentAnalysis.profile.learningGoal")}
          </h3>
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs"
            onClick={handleSaveScore}
          >
            {t("studentAnalysis.profile.saveScore")}
          </Button>
        </div>

        {analysisError && (
          <div className="mb-3">
            <InlineQueryError
              message={t("studentAnalysis.profile.goalFailed")}
              onRetry={refetchAnalysis}
            />
          </div>
        )}

        <div className="flex items-center gap-6 mb-3">
          <div className="flex-1">
            <p className="text-xs text-muted-foreground mb-1">
              {t("studentAnalysis.profile.targetScore")}
            </p>
            <div className="flex items-center gap-1">
              <Input
                type="number"
                value={inputTarget}
                onChange={(e) => setInputTarget(e.target.value)}
                onWheel={(e) => (e.target as HTMLElement).blur()}
                className="h-8 w-20 text-lg font-bold px-2"
              />
              <span className="text-sm font-medium text-foreground">
                {t("studentAnalysis.profile.points", { value: "" }).trim()}
              </span>
            </div>
          </div>
          <div className="flex-1">
            <p className="text-xs text-muted-foreground mb-1">
              {t("studentAnalysis.profile.current")}
            </p>
            <div className="flex items-center gap-1">
              <Input
                type="number"
                value={inputCurrent}
                onChange={(e) => setInputCurrent(e.target.value)}
                onWheel={(e) => (e.target as HTMLElement).blur()}
                className="h-8 w-20 text-lg font-bold text-primary px-2"
              />
              <span className="text-sm font-medium text-primary">
                {t("studentAnalysis.profile.points", { value: "" }).trim()}
              </span>
            </div>
          </div>
          <div className="flex-1">
            <p className="text-xs text-muted-foreground mb-1">
              {t("studentAnalysis.profile.gap")}
            </p>
            <p
              className={cn(
                "text-xl font-bold mt-1",
                !hasBothScores
                  ? "text-muted-foreground text-sm"
                  : currentScoreVal >= targetScoreVal
                    ? "text-emerald-600"
                    : "text-destructive",
              )}
            >
              {!hasBothScores
                ? t("studentAnalysis.profile.noData")
                : currentScoreVal >= targetScoreVal
                  ? t("studentAnalysis.profile.achieved")
                  : t("studentAnalysis.profile.gapPoints", { value: gap })}
            </p>
          </div>
        </div>

        {/* Progress bar */}
        <div className="relative mb-1 mt-4">
          <Progress
            value={goalProgress}
            className={cn(
              "h-3 rounded-full",
              goalProgress >= 100
                ? "[&>div]:bg-emerald-500"
                : goalProgress >= 80
                  ? "[&>div]:bg-yellow-500"
                  : "[&>div]:bg-orange-500",
            )}
          />
          <span className="absolute right-0 -top-5 text-[11px] text-muted-foreground font-medium">
            {currentScoreVal ?? "-"}/{targetScoreVal ?? "-"}
          </span>
        </div>

        {/* Breakthrough points */}
        {aiDiagnosisData && aiDiagnosisData.length > 0 && (
          <div className="mt-4 pt-3 border-t border-border/50">
            <p className="text-xs font-medium text-foreground mb-2">
              {t("studentAnalysis.profile.breakthrough")}
            </p>
            <div className="space-y-1.5">
              {aiDiagnosisData.slice(0, 2).map((dimData: any) => {
                const current = dimData.student;
                const target = Math.min(current + 25, 90);
                return (
                  <div
                    key={dimData.dim}
                    className="flex items-center gap-2 text-xs"
                  >
                    <span className="text-muted-foreground">•</span>
                    <span className="text-foreground">
                      {analysisLabel(dimData.dim)}
                    </span>
                    <span className={cn("font-medium", masteryColor(current))}>
                      {current}%
                    </span>
                    <ArrowRight className="w-3 h-3 text-muted-foreground" />
                    <span className="text-emerald-600 font-medium">
                      {t("studentAnalysis.profile.targetPercent", {
                        value: target,
                      })}
                    </span>
                  </div>
                );
              })}
            </div>
            <Button
              variant="outline"
              size="sm"
              className="text-xs h-7 mt-3 gap-1"
              onClick={goToTargeted}
            >
              {t("studentAnalysis.profile.viewPath")}{" "}
              <ArrowRight className="w-3 h-3" />
            </Button>
          </div>
        )}
      </div>

      {/* ═══ Module 3: Radar Chart (Clickable Drill-down) ═══ */}
      <div
        data-tour="sp-radar"
        className="rounded-xl bg-card border border-border/50 p-5"
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Target className="w-4 h-4 text-primary" />{" "}
            {t("studentAnalysis.profile.radar")}
          </h3>
          <span className="text-[11px] text-muted-foreground">
            {t("studentAnalysis.profile.lastDiagnosis")}
          </span>
        </div>
        {aiDiagnosisError && (
          <InlineQueryError
            message={t("studentAnalysis.profile.radarFailed")}
            onRetry={refetchAIDiagnosis}
          />
        )}
        <div className="h-[220px]">
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={radarDims} cx="50%" cy="50%" outerRadius="70%">
              <PolarGrid stroke="hsl(var(--border))" />
              <PolarAngleAxis
                dataKey="dim"
                tickFormatter={analysisLabel}
                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              />
              <Radar
                name={t("studentAnalysis.profile.classAverage")}
                dataKey="class"
                stroke="hsl(var(--muted-foreground))"
                fill="hsl(var(--muted-foreground))"
                fillOpacity={0.1}
                strokeDasharray="4 4"
              />
              <Radar
                name={t("studentAnalysis.profile.personal")}
                dataKey="student"
                stroke="hsl(var(--primary))"
                fill="hsl(var(--primary))"
                fillOpacity={0.2}
                strokeWidth={2}
              />
            </RadarChart>
          </ResponsiveContainer>
        </div>

        <p className="text-xs text-muted-foreground mt-2 mb-3">
          {t("studentAnalysis.profile.radarComparison", {
            below: belowAvg,
            above: aboveAvg,
          })}
        </p>
        <p className="text-[11px] text-primary/70 mb-2 flex items-center gap-1">
          <Eye className="w-3 h-3" /> {t("studentAnalysis.profile.radarHint")}
        </p>

        {/* Dimension bars with drill-down */}
        <div className="space-y-1">
          {radarDims.map((d) => {
            const isExpanded = expandedDim === d.dim;
            const subDims = getSubDimMastery(d.dim);
            return (
              <Collapsible
                key={d.dim}
                open={isExpanded}
                onOpenChange={() => setExpandedDim(isExpanded ? null : d.dim)}
              >
                <CollapsibleTrigger className="w-full">
                  <div className="flex items-center gap-2 py-1.5 px-1 rounded hover:bg-muted/50 transition-colors cursor-pointer">
                    {isExpanded ? (
                      <ChevronDown className="w-3 h-3 text-muted-foreground shrink-0" />
                    ) : (
                      <ChevronRight className="w-3 h-3 text-muted-foreground shrink-0" />
                    )}
                    <span className="text-xs text-foreground w-16 truncate text-left">
                      {analysisLabel(d.dim)}
                    </span>
                    <Progress
                      value={d.student}
                      className={cn("h-1.5 flex-1", masteryBarColor(d.student))}
                    />
                    <span
                      className={cn(
                        "text-xs w-8 text-right font-medium",
                        masteryColor(d.student),
                      )}
                    >
                      {d.student}%
                    </span>
                  </div>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <div className="ml-5 pl-3 border-l-2 border-border/50 space-y-1.5 py-1.5">
                    {subDims.map((sub) => {
                      const mb = masteryBadge(sub.mastery, t);
                      return (
                        <div key={sub.name} className="flex items-center gap-2">
                          <span className="text-[11px] text-foreground/80 w-16 truncate">
                            {analysisLabel(sub.name)}
                          </span>
                          <Progress
                            value={sub.mastery}
                            className={cn(
                              "h-1 flex-1",
                              masteryBarColor(sub.mastery),
                            )}
                          />
                          <span
                            className={cn(
                              "text-[11px] w-7 text-right font-medium",
                              masteryColor(sub.mastery),
                            )}
                          >
                            {sub.mastery}%
                          </span>
                          <Badge
                            variant="outline"
                            className={cn(
                              "text-[9px] h-4 px-1 border-0",
                              mb.cls,
                            )}
                          >
                            {mb.label}
                          </Badge>
                          {sub.mastery < 50 && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-5 text-[10px] px-1.5 text-primary hover:text-primary"
                              onClick={(e) => {
                                e.stopPropagation();
                                goToTargeted();
                              }}
                            >
                              {t("studentAnalysis.profile.diagnose")}
                            </Button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </CollapsibleContent>
              </Collapsible>
            );
          })}
        </div>

        <div className="flex justify-end mt-3">
          <Button
            variant="outline"
            size="sm"
            className="text-xs h-7 gap-1"
            onClick={goToTargeted}
          >
            {t("studentAnalysis.profile.rediagnose")}
          </Button>
        </div>
      </div>

      {/* ═══ Module 4: Wrong Questions (Smart Classification) ═══ */}
      <div
        data-tour="sp-wrong-timeline"
        className="rounded-xl bg-card border border-border/50 p-5"
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Pencil className="w-4 h-4 text-primary" />{" "}
            {t("studentAnalysis.profile.recentWrong", { count: totalWrong })}
          </h3>
          <div className="text-[11px] text-muted-foreground flex items-center gap-1 bg-muted/30 px-2 py-1 rounded-md">
            <Clock className="w-3 h-3" />{" "}
            {t("studentAnalysis.profile.latestWrong", {
              exam:
                latestWrongQuestions?.exam_name ||
                t("studentAnalysis.profile.noRecord"),
            })}
          </div>
        </div>

        {wrongQuestionsError && (
          <div className="mb-3">
            <InlineQueryError
              message={t("studentAnalysis.profile.wrongQuestionsFailed")}
              onRetry={refetchWrongQuestions}
            />
          </div>
        )}

        <div className="space-y-4">
          {!latestWrongQuestions?.questions ||
          latestWrongQuestions.questions.length === 0 ? (
            <div className="py-8 text-center text-muted-foreground text-sm bg-muted/20 rounded-lg border border-dashed">
              <CheckCircle2 className="w-8 h-8 mx-auto opacity-20 mb-2" />
              {t("studentAnalysis.profile.noWrong")}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-[400px] overflow-y-auto pr-2 custom-scrollbar">
              {latestWrongQuestions.questions.map((q: any, idx: number) => (
                <div
                  key={idx}
                  className="group relative rounded-lg border border-border/60 bg-muted/10 overflow-hidden hover:border-primary/40 hover:shadow-sm transition-all"
                >
                  <div className="absolute top-2 left-2 bg-background/90 backdrop-blur-sm text-xs font-medium px-2 py-1 rounded shadow-sm z-10 border border-border/50">
                    {q.title}
                  </div>
                  <div className="aspect-[4/3] bg-muted/30 relative flex items-center justify-center p-2">
                    {q.image_url ? (
                      <img
                        src={gradingImageUrl(q.image_url)}
                        alt={q.title}
                        className="max-w-full max-h-full object-contain rounded-sm mix-blend-multiply"
                        onError={(e) => {
                          (e.target as HTMLImageElement).style.display = "none";
                          (
                            e.target as HTMLImageElement
                          ).nextElementSibling?.classList.remove("hidden");
                        }}
                      />
                    ) : null}
                    <div
                      className={
                        q.image_url
                          ? "hidden text-muted-foreground/50 text-xs"
                          : "text-muted-foreground/50 text-xs"
                      }
                    >
                      {t("studentAnalysis.profile.noImage")}
                    </div>
                  </div>
                  {q.answer_url && (
                    <div className="border-t border-border/50 bg-muted/20 p-2 flex items-center justify-between text-[11px] text-muted-foreground">
                      <span>{t("studentAnalysis.profile.hasAnswerImage")}</span>
                      <button
                        className="text-primary hover:underline"
                        onClick={() =>
                          setWrongDialog({
                            open: true,
                            category: t(
                              "studentAnalysis.profile.recentWrongCategory",
                            ),
                            subPoint: q.title,
                            count: 1,
                          })
                        }
                      >
                        {t("studentAnalysis.profile.viewDetails")}
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Wrong Question Detail Dialog */}
      <WrongQuestionDetailDialog
        open={wrongDialog.open}
        onOpenChange={(open) => setWrongDialog((prev) => ({ ...prev, open }))}
        studentName={name}
        classId={selectedClass}
        subject={selectedSubject}
        category={wrongDialog.category}
        subPoint={wrongDialog.subPoint}
        count={wrongDialog.count}
      />

      {/* Manage History Dialog */}
      <Dialog open={manageHistoryOpen} onOpenChange={setManageHistoryOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {t("studentAnalysis.profile.manageHistory")}
            </DialogTitle>
            <DialogDescription>
              {t("studentAnalysis.profile.manageHistoryDescription")}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 mt-4 max-h-[300px] overflow-y-auto pr-2">
            {!scoreHistoryData || scoreHistoryData.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">
                {t("studentAnalysis.profile.noHistory")}
              </p>
            ) : (
              scoreHistoryData.map((item) => (
                <div
                  key={item.id || item.exam_name}
                  className="flex items-center justify-between bg-muted/30 p-3 rounded-lg border border-border/50"
                >
                  <div className="flex flex-col">
                    <span className="text-sm font-medium text-foreground">
                      {item.exam_name ||
                        t("studentAnalysis.profile.unnamedExam")}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {t("studentAnalysis.profile.enteredAt", {
                        time: new Date(item.created_at).toLocaleString(
                          locale === "en" ? "en-US" : "zh-CN",
                        ),
                      })}
                    </span>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 w-8 p-0 text-destructive hover:text-destructive hover:bg-destructive/10"
                    aria-label={t("classDetail.deleteHistoryAria")}
                    onClick={() => {
                      if (
                        window.confirm(
                          t("studentAnalysis.profile.deleteConfirm", {
                            exam: item.exam_name,
                          }),
                        )
                      ) {
                        handleDeleteExam(item.exam_name);
                      }
                    }}
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              ))
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
