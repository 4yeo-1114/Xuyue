import React, {
  useState,
  useRef,
  useMemo,
  useEffect,
  useCallback,
} from "react";
import { toast } from "sonner";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSubjectName } from "@/i18n";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import {
  FileText,
  Plus,
  Trash2,
  Printer,
  Download,
  Mail,
  Check,
  ChevronsUpDown,
  Loader2,
  Edit2,
  GripVertical,
  ArrowLeft,
  Save,
  Sparkles,
  BookCopy,
  Layers,
} from "lucide-react";
import {
  getAllUsers,
  sendExamEmail,
  generateExamQuestionsByAI,
  listExamPapers,
  createExamPaper,
  updateExamPaper,
  deleteExamPaper,
  listKnowledgeData,
  listExamTemplates,
  SmartExamPaperRecord,
  ExamTemplate,
  UnitRow,
  KPRow,
} from "@/services/api";
import {
  getMasteryDistribution,
  type MasteryDistributionItem,
} from "@/services/dashboardApi";
import { useAuth } from "@/hooks/useAuth";
import { useAdminAuth } from "@/hooks/useAdminAuth";
import { normalizeExamQuestions } from "@/utils/examMathFormat";
import { readGlobalPrintPrefs } from "@/lib/globalPrintPrefs";
import { withCompatPrint } from "@/utils/printCompat";
import { QuestionBankPicker } from "@/components/question-bank/QuestionBankPicker";
import { stripHtmlText, type BankQuestion } from "@/services/questionBankApi";
import { TieredComposePanel } from "@/components/class-detail/layered-push/TieredComposePanel";

export type QuestionType =
  | "choice"
  | "fill"
  | "judge"
  | "short_answer"
  | "essay"
  | "matching"
  | "ordering"
  | "reading"
  | "cloze"
  | "calculation"
  | "application";

export interface ExamQuestion {
  id: string;
  type: QuestionType;
  stem: string; // 题干/背景材料
  content: string; // 题目内容/问题
  subQuestions?: string[]; // 简答题的多个子题内容
  options: string[]; // 选择题选项
  score: number; // 分数
  answer?: string; // 参考答案（从题库带入）
  analysis?: string; // 解析（从题库带入）
  knowledge_point?: string; // 知识点（从题库带入）
  difficulty?: number; // 难度 1-5（从题库带入）
}

const EXAM_SUBJECTS = [
  "语文",
  "数学",
  "英语",
  "科学",
  "物理",
  "化学",
  "生物",
  "政治",
  "历史",
  "地理",
] as const;
const EXAM_GRADES = [
  "一年级",
  "二年级",
  "三年级",
  "四年级",
  "五年级",
  "六年级",
  "七年级",
  "八年级",
  "九年级",
  "高一",
  "高二",
  "高三",
] as const;
const GRADE_I18N_KEYS = [
  "1",
  "2",
  "3",
  "4",
  "5",
  "6",
  "7",
  "8",
  "9",
  "10",
  "11",
  "12",
] as const;
const TERM_OPTIONS = [
  { value: "上学期", key: "examGen.term.first" },
  { value: "下学期", key: "examGen.term.second" },
] as const;
const DIFFICULTY_OPTIONS = [
  { value: "简单" as const, key: "examGen.difficulty.easy" },
  { value: "中等" as const, key: "examGen.difficulty.medium" },
  { value: "偏难" as const, key: "examGen.difficulty.hard" },
];
// 模块级常量:题型固定顺序(纯静态值)。若定义在组件体内,每次渲染都会新建引用,
// 导致分页 effect 依赖非稳定引用而无限重渲染循环。
const TYPE_ORDER: QuestionType[] = [
  "choice",
  "fill",
  "judge",
  "matching",
  "ordering",
  "short_answer",
  "reading",
  "cloze",
  "calculation",
  "application",
  "essay",
];

type Difficulty = "简单" | "中等" | "偏难";

const isQuestionType = (value: unknown): value is QuestionType =>
  typeof value === "string" && TYPE_ORDER.includes(value as QuestionType);

// 从后端 any 载荷安全收敛为强类型:仅保留结构完整的题目,替代盲目的 `as ExamQuestion[]`。
const isExamQuestion = (value: unknown): value is ExamQuestion => {
  if (typeof value !== "object" || value === null) return false;
  const q = value as Record<string, unknown>;
  return (
    typeof q.id === "string" &&
    typeof q.stem === "string" &&
    typeof q.content === "string" &&
    Array.isArray(q.options) &&
    typeof q.score === "number" &&
    isQuestionType(q.type)
  );
};

const toExamQuestions = (value: unknown): ExamQuestion[] =>
  Array.isArray(value) ? value.filter(isExamQuestion) : [];

// 判断题目是否为「空占位」：题干/内容/选项/子题均未填写。
// AI 组卷优先填充这些占位题，而非另起新题。
const isQuestionEmpty = (q: ExamQuestion): boolean =>
  !(q.stem ?? "").trim() &&
  !(q.content ?? "").trim() &&
  (q.options ?? []).every((o) => !o.trim()) &&
  (q.subQuestions ?? []).every((s) => !s.trim());

// catch(unknown) 下安全提取错误信息:Error 取 message,字符串原样,其余 undefined
const getErrorMessage = (error: unknown): string | undefined => {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  return undefined;
};

const isDifficulty = (value: unknown): value is Difficulty =>
  typeof value === "string" &&
  DIFFICULTY_OPTIONS.some((d) => d.value === value);

// ── 多知识点 + 组卷模板 辅助 ─────────────────────────────────────────────
// 年级 → 学段 / 学段中文前缀（用于派生知识点/题型模板用的「完整学科」与「学期」）
const GRADE_TO_SCHOOL_LEVEL: Record<string, string> = {
  一年级: "primary", 二年级: "primary", 三年级: "primary",
  四年级: "primary", 五年级: "primary", 六年级: "primary",
  七年级: "junior", 八年级: "junior", 九年级: "junior",
  高一: "senior", 高二: "senior", 高三: "senior",
};
const SCHOOL_LEVEL_ZH: Record<string, string> = {
  primary: "小学", junior: "初中", senior: "高中",
};
// 题型模板的中文题型名 → 前端 QuestionType
const TYPE_NAME_TO_QUESTION_TYPE: Record<string, QuestionType> = {
  选择题: "choice",
  填空题: "fill",
  判断题: "judge",
  简答题: "short_answer",
  作文: "essay",
  连线题: "matching",
  排序题: "ordering",
  阅读理解: "reading",
  完形填空: "cloze",
  计算题: "calculation",
  应用题: "application",
};

/** PG 题库题目 → 试卷题目（ExamQuestion），带答案/解析/知识点/难度扩展字段 */
function bankQuestionToExamQuestion(q: BankQuestion): ExamQuestion {
  const type = TYPE_NAME_TO_QUESTION_TYPE[q.question_type] ?? "short_answer";
  const options = Array.isArray(q.options)
    ? (q.options as unknown[]).map((o) => String(o ?? ""))
    : [];
  return {
    id: newQuestionId("q"),
    type,
    stem: stripHtmlText(q.question),
    content: "",
    options,
    score: type === "essay" ? 30 : 5,
    answer: q.answer ? stripHtmlText(q.answer) : undefined,
    analysis: q.analysis ? stripHtmlText(q.analysis) : undefined,
    knowledge_point: q.knowledge_point ?? undefined,
    difficulty: q.difficulty,
  };
}
// 题型模板未配置时的默认题型结构（与 settings 页 getDefaultQuestionTypes 对齐）
const DEFAULT_TYPE_REQUIREMENTS: Record<
  "lang" | "other",
  { type: QuestionType; count: number; score: number }[]
> = {
  lang: [
    { type: "choice", count: 10, score: 2 },
    { type: "fill", count: 10, score: 2 },
    { type: "short_answer", count: 5, score: 6 },
    { type: "essay", count: 1, score: 30 },
  ],
  other: [
    { type: "choice", count: 15, score: 3 },
    { type: "fill", count: 10, score: 2 },
    { type: "judge", count: 10, score: 1 },
    { type: "short_answer", count: 5, score: 5 },
  ],
};

/** 由年级 + 原始学科派生「完整学科」（如 小学语文 / 初中数学），用于查知识点与题型模板 */
function deriveFullSubject(grade: string, rawSubject: string): string {
  const level = GRADE_TO_SCHOOL_LEVEL[grade] ?? "primary";
  return `${SCHOOL_LEVEL_ZH[level]}${rawSubject}`;
}

/** 由年级 + 学期派生知识点库用的学期串（如 三年级下册） */
function deriveSemester(grade: string, term: string): string {
  return `${grade}${term === "上学期" ? "上册" : "下册"}`;
}

/** 由已保存试卷的题目结构派生组卷要求（题型/数量/分值） */
function requirementsFromQuestions(
  qs: ExamQuestion[],
): { type: string; count: number; score: number }[] {
  const byType: Record<string, { count: number; score: number }> = {};
  qs.forEach((q) => {
    if (!byType[q.type]) byType[q.type] = { count: 0, score: q.score || 5 };
    byType[q.type].count += 1;
  });
  return Object.entries(byType).map(([type, v]) => ({
    type,
    count: v.count,
    score: v.score,
  }));
}

/** 由题型模板派生组卷要求（跳过未知题型/数量为 0） */
function requirementsFromTemplates(
  tpls: ExamTemplate[],
): { type: string; count: number; score: number }[] {
  const out: { type: string; count: number; score: number }[] = [];
  tpls.forEach((t) => {
    const qtype = TYPE_NAME_TO_QUESTION_TYPE[t.type_name];
    if (qtype && t.default_count > 0) {
      out.push({
        type: qtype,
        count: t.default_count,
        score: t.default_score_each || 5,
      });
    }
  });
  return out;
}

// ── 题目 id 生成 / AI 题干序号清理 ────────────────────────────────────
// 时间戳 + 递增序号 + 随机后缀：同一毫秒内批量生成也绝不重复
let questionIdSeq = 0;
function newQuestionId(prefix: string): string {
  questionIdSeq += 1;
  return `${prefix}_${Date.now()}_${questionIdSeq}_${Math.random().toString(36).substring(2, 8)}`;
}

// AI 生成的题干/内容常自带 "1." "2、" 这类题号前缀，与前端自带题号叠加会「题号一样/串号」
function stripLeadingQuestionNumber(text: string): string {
  return text.replace(/^\s*\d+(?:[.、．]\s+|[.、．](?!\d))/, "");
}

/** 保证题目 id 非空且唯一（历史数据/模型输出可能带重复或空 id，会让按 id 查找的题号塌缩成同一个号） */
function ensureUniqueQuestionIds(qs: ExamQuestion[]): ExamQuestion[] {
  const used = new Set<string>();
  return qs.map((q) => {
    const id = typeof q.id === "string" && q.id ? q.id : "";
    if (id && !used.has(id)) {
      used.add(id);
      return q;
    }
    return { ...q, id: newQuestionId("q") };
  });
}

// 掌握度滑条配色（与学生画像 Module 3.5 同阈值：80/60/50）
function kpMasteryTextColor(v: number) {
  if (v >= 80) return "text-emerald-600";
  if (v >= 60) return "text-yellow-600";
  if (v >= 50) return "text-orange-600";
  return "text-destructive";
}
function kpMasteryBarColor(v: number) {
  if (v >= 80) return "[&>div]:bg-emerald-500";
  if (v >= 60) return "[&>div]:bg-yellow-500";
  if (v >= 50) return "[&>div]:bg-orange-500";
  return "[&>div]:bg-destructive";
}

/** 按组卷要求搭建空白骨架题（供「模板成卷」后 AI 填充） */
function buildSkeleton(
  reqs: { type: string; count: number; score: number }[],
): ExamQuestion[] {
  const out: ExamQuestion[] = [];
  reqs.forEach((r) => {
    const type = r.type as QuestionType;
    for (let i = 0; i < r.count; i += 1) {
      out.push({
        id: newQuestionId(`tpl_${type}`),
        type,
        stem: "",
        content: "",
        subQuestions:
          type === "short_answer" || type === "reading"
            ? [""]
            : type === "matching"
              ? ["", "", "", ""]
              : undefined,
        options:
          type === "choice" || type === "matching" || type === "ordering"
            ? ["", "", "", ""]
            : [],
        score: r.score || (type === "essay" ? 30 : 5),
      });
    }
  });
  return out;
}

interface Props {
  onNavChange: (id: string) => void;
  selectedSubject?: string;
  selectedClass?: string;
  selectedGrade?: string;
  selectedSchoolLevel?: string;
  loadResourceId?: string;
  onResourceLoaded?: () => void;
  /** 讲评/班级分析「按薄弱点出卷」带入的知识点，进入后自动开 AI 出题弹窗并预填 */
  initialTopics?: string[];
  onTopicsConsumed?: () => void;
}

export interface ExamPaperRecord {
  id: string;
  title: string;
  subject: string;
  questions: ExamQuestion[];
  updatedAt: string;
}

export function ExamGenPage({
  onNavChange,
  selectedSubject,
  selectedClass,
  loadResourceId,
  onResourceLoaded,
  initialTopics,
  onTopicsConsumed,
}: Props) {
  const { user } = useAuth();
  const { t, locale } = useLocale();

  // 「发送给他人」依赖 /auth/users/all，后端白名单只有 系统管理员/子系统管理员 两种角色，
  // 校级管理者/年级组长即使前端放行也会 403，故与后端一致的两种角色判定。
  const isGlobalAdmin = useMemo(() => {
    if (!user || !user.roles) return false;
    return user.roles.some((r) => ["系统管理员", "子系统管理员"].includes(r));
  }, [user]);

  const getQuestionTypeLabel = useCallback(
    (type: QuestionType | string) => t(`examGen.questionType.${type}`),
    [t],
  );

  const getSectionNumber = useCallback(
    (index: number) => t(`examGen.sectionNumber.${index}`),
    [t],
  );

  const defaultTitle = t("examGen.defaultTitle");
  const defaultSubject = t("examGen.defaultSubject");

  const [view, setView] = useState<"overview" | "editor">("overview");
  const [exams, setExams] = useState<SmartExamPaperRecord[]>([]);
  const [activeExamId, setActiveExamId] = useState<string | null>(null);
  const [localSubject, setLocalSubject] = useState("语文");
  const [loadingExams, setLoadingExams] = useState(false);
  // 按层出卷入口（A/B/C 分层卷）
  const [tieredOpen, setTieredOpen] = useState(false);

  // 卸载守卫:await 之后的 setState 需确认组件仍挂载,避免卸载后更新泄漏。
  const mountedRef = useRef(true);

  const fetchExams = async () => {
    try {
      setLoadingExams(true);
      const data = await listExamPapers();
      if (!mountedRef.current) return;
      setExams(data);
    } catch (e: unknown) {
      if (!mountedRef.current) return;
      toast.error(t("examGen.toast.loadFailed"), {
        description: getErrorMessage(e),
      });
    } finally {
      if (mountedRef.current) setLoadingExams(false);
    }
  };

  useEffect(() => {
    fetchExams();
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // 从资源库/上传流程跳转组卷：loadResourceId 是触发信号（含缓存破坏唯一 token）。
  // 命中已有试卷则打开对应试卷，否则新建空白试卷进入编辑器，避免跨页跳转变成死链。
  // 已处理过的 loadResourceId(避免 exams 后续更新时重复触发打开)
  const handledResourceIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!loadResourceId) {
      handledResourceIdRef.current = null;
      return;
    }
    // 跨页跳转竞态:exams 尚未加载完成时不匹配,等数据就绪后再打开对应试卷
    if (loadingExams) return;
    if (handledResourceIdRef.current === loadResourceId) return;
    handledResourceIdRef.current = loadResourceId;
    const matched = exams.find((e) => e.id === loadResourceId);
    if (matched) {
      openEditor(matched);
    } else {
      openEditor();
    }
    onResourceLoaded?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadResourceId, exams, loadingExams]);

  // 讲评/班级分析「按薄弱点出卷」：带知识点进来 → 新建空白卷 + 打开 AI 弹窗预填主题。
  // 题型走「按题型模板」出骨架（新卷没有占位题，占位模式会报「请先添加占位题」）。
  const handledTopicsRef = useRef<string | null>(null);
  useEffect(() => {
    if (!initialTopics || initialTopics.length === 0) {
      handledTopicsRef.current = null;
      return;
    }
    const token = initialTopics.join("|");
    if (handledTopicsRef.current === token) return;
    handledTopicsRef.current = token;
    openEditor();
    setTemplateMode("type");
    setAiForm((f) => ({ ...f, topic: initialTopics.join("、") }));
    setAiModalOpen(true);
    onTopicsConsumed?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialTopics]);

  const handleSaveExam = async () => {
    try {
      const questionsToSave = normalizeExamQuestions(questions, localSubject);
      if (activeExamId) {
        const res = await updateExamPaper(activeExamId, {
          title: paperTitle,
          subject: localSubject,
          questions: questionsToSave,
        });
        if (!mountedRef.current) return;
        setQuestions(toExamQuestions(res.questions));
        setExams(exams.map((e) => (e.id === activeExamId ? res : e)));
        // 保存成功后刷新已保存快照,后续编辑重新累积脏标记
        savedSnapshotRef.current = {
          title: paperTitle,
          subject: localSubject,
          questions: toExamQuestions(res.questions),
        };
        toast.success(t("examGen.toast.updated"));
      } else {
        const res = await createExamPaper({
          title: paperTitle,
          subject: localSubject,
          questions: questionsToSave,
        });
        if (!mountedRef.current) return;
        setQuestions(toExamQuestions(res.questions));
        setExams([res, ...exams]);
        setActiveExamId(res.id);
        // 保存成功后刷新已保存快照
        savedSnapshotRef.current = {
          title: paperTitle,
          subject: localSubject,
          questions: toExamQuestions(res.questions),
        };
        toast.success(t("examGen.toast.saved"));
      }
    } catch (e: unknown) {
      toast.error(t("examGen.toast.saveFailed"), {
        description: getErrorMessage(e),
      });
    }
  };

  const handleDeleteExam = async (id: string) => {
    if (!confirm(t("examGen.toast.deleteConfirm"))) return;
    try {
      await deleteExamPaper(id);
      if (!mountedRef.current) return;
      setExams(exams.filter((e) => e.id !== id));
      toast.success(t("examGen.toast.deleted"));
    } catch (e: unknown) {
      toast.error(t("examGen.toast.deleteFailed"), {
        description: getErrorMessage(e),
      });
    }
  };

  const openEditor = (exam?: SmartExamPaperRecord) => {
    // 记录进入编辑器时的已保存快照,作为脏数据判定的基准(paperTitle/localSubject/questions)
    const initialTitle = exam ? exam.title : defaultTitle;
    const initialSubject = exam ? exam.subject : selectedSubject || "语文";
    const initialQuestions = exam
      ? ensureUniqueQuestionIds(toExamQuestions(exam.questions))
      : [];
    if (exam) {
      setActiveExamId(exam.id);
    } else {
      setActiveExamId(null);
    }
    setPaperTitle(initialTitle);
    setLocalSubject(initialSubject);
    setQuestions(initialQuestions);
    savedSnapshotRef.current = {
      title: initialTitle,
      subject: initialSubject,
      questions: initialQuestions,
    };
    setActiveQuestionId(null);
    setView("editor");
  };

  // Exam Data State
  const [paperTitle, setPaperTitle] = useState(defaultTitle);
  const [questions, setQuestions] = useState<ExamQuestion[]>([]);
  const [questionBankOpen, setQuestionBankOpen] = useState(false);
  const [activeQuestionId, setActiveQuestionId] = useState<string | null>(null);

  // ── 脏数据保护:已保存快照 + 未保存变更判定 ─────────────────────────────
  // 进入编辑器时记录 paperTitle/localSubject/questions 的已保存状态,
  // 当前 state 与快照不一致即视为"有未保存变更",用于返回/关闭前的确认提示。
  const savedSnapshotRef = useRef<{
    title: string;
    subject: string;
    questions: ExamQuestion[];
  } | null>(null);

  const isDirty = useMemo(() => {
    const snap = savedSnapshotRef.current;
    if (!snap) return false;
    return (
      snap.title !== paperTitle ||
      snap.subject !== localSubject ||
      JSON.stringify(snap.questions) !== JSON.stringify(questions)
    );
  }, [paperTitle, localSubject, questions]);

  // 返回列表主路径保护:有未保存变更时先确认,避免静默丢弃。
  const handleBackToOverview = () => {
    if (isDirty) {
      const confirmed = window.confirm(
        locale === "en"
          ? "You have unsaved changes. Leave the editor and discard them?"
          : "你有未保存的修改，确定要离开并丢弃吗？",
      );
      if (!confirmed) return;
    }
    setView("overview");
  };

  // 浏览器刷新/关闭/外部跳转保护:有未保存变更时拦截卸载确认。
  // 限制:Sidebar/Breadcrumb 的 SPA 内部导航不走页面卸载,而是直接卸载本组件,
  // beforeunload 不会触发;该场景需在导航层(onNavChange/Index.tsx)统一拦截,
  // 单文件内无法同步拦截 React 卸载(详见验收报告限制说明)。
  useEffect(() => {
    if (view !== "editor" || !isDirty) return;
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [view, isDirty]);

  // Batch Delete State
  const [batchMode, setBatchMode] = useState(false);
  const [selectedQIds, setSelectedQIds] = useState<string[]>([]);

  // Batch Score State
  const [scoreModalOpen, setScoreModalOpen] = useState(false);
  const [typeScores, setTypeScores] = useState<Record<string, number>>({});

  // AI Generate State
  const [aiModalOpen, setAiModalOpen] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [aiForm, setAiForm] = useState({
    topic: "",
    grade: "一年级",
    term: "上学期",
    difficulty: "中等" as "简单" | "中等" | "偏难",
  });

  // 多知识点 + 组卷模板状态
  const [selectedKpIds, setSelectedKpIds] = useState<string[]>([]);
  const [kpUnits, setKpUnits] = useState<UnitRow[]>([]);
  const [kpList, setKpList] = useState<KPRow[]>([]);
  const [kpLoading, setKpLoading] = useState(false);
  const [kpEmpty, setKpEmpty] = useState(false);
  const [templateMode, setTemplateMode] = useState<
    "placeholder" | "paper" | "type"
  >("placeholder");
  const [templatePaperId, setTemplatePaperId] = useState<string>("");
  const [typeTemplates, setTypeTemplates] = useState<ExamTemplate[]>([]);

  // Email Dialog State
  const [sendingEmail, setSendingEmail] = useState(false);
  const [emailModalOpen, setEmailModalOpen] = useState(false);
  const [emailTargetType, setEmailTargetType] = useState<"self" | "others">(
    "self",
  );
  const [emailUserComboboxOpen, setEmailUserComboboxOpen] = useState(false);
  const [targetEmailInput, setTargetEmailInput] = useState("");
  // /auth/users/all 返回最小字段（不含 personal_email），故用户选择器只展示姓名，不承载收件人邮箱
  const [selectedUserObj, setSelectedUserObj] = useState<{
    id: string;
    email: string;
    display_name?: string | null;
  } | null>(null);
  const [usersList, setUsersList] = useState<
    {
      id: string;
      email: string;
      display_name?: string | null;
    }[]
  >([]);
  const [loadingUsers, setLoadingUsers] = useState(false);

  const previewRef = useRef<HTMLDivElement>(null);

  // Load users for email
  const fetchUsersList = async () => {
    setLoadingUsers(true);
    try {
      const users = await getAllUsers();
      if (!mountedRef.current) return;
      setUsersList(users);
    } catch (err) {
      if (!mountedRef.current) return;
      toast.error(t("examGen.toast.usersFailed"));
    } finally {
      if (mountedRef.current) setLoadingUsers(false);
    }
  };

  useEffect(() => {
    if (
      emailModalOpen &&
      emailTargetType === "others" &&
      usersList.length === 0
    ) {
      fetchUsersList();
    }
  }, [emailModalOpen, emailTargetType]);

  // 打开 AI 弹窗时，按 学科+年级+学期 加载知识点图谱与题型模板（多知识点多选 / 模板成卷用）
  useEffect(() => {
    if (!aiModalOpen) return;
    const fullSubject = deriveFullSubject(aiForm.grade, localSubject);
    const semester = deriveSemester(aiForm.grade, aiForm.term);
    let cancelled = false;
    setKpLoading(true);
    listKnowledgeData(fullSubject, semester)
      .then((d) => {
        if (cancelled) return;
        setKpUnits(d.units ?? []);
        setKpList(d.kps ?? []);
        setKpEmpty(!!d.isEmpty);
      })
      .catch(() => {
        if (cancelled) return;
        setKpUnits([]);
        setKpList([]);
        setKpEmpty(true);
      })
      .finally(() => {
        if (!cancelled) setKpLoading(false);
      });
    listExamTemplates(fullSubject)
      .then((tpls) => {
        if (!cancelled) setTypeTemplates(tpls ?? []);
      })
      .catch(() => {
        if (!cancelled) setTypeTemplates([]);
      });
    return () => {
      cancelled = true;
    };
  }, [aiModalOpen, localSubject, aiForm.grade, aiForm.term]);

  // AI 弹窗知识点树的班级掌握度滑条（与学生画像 Module 3.5 同口径：
  // 错题分布派生、按知识点名锚定；无班级/无数据时不显示滑条）
  const { schoolId } = useAdminAuth();
  const [kpMasteryByName, setKpMasteryByName] = useState<
    Record<string, MasteryDistributionItem>
  >({});
  useEffect(() => {
    if (!aiModalOpen || !selectedClass || !schoolId) {
      setKpMasteryByName({});
      return;
    }
    let cancelled = false;
    getMasteryDistribution(schoolId, { class_id: selectedClass })
      .then((items) => {
        if (cancelled) return;
        const map: Record<string, MasteryDistributionItem> = {};
        (items ?? []).forEach((it) => {
          if (it && it.name) map[it.name.trim()] = it;
        });
        setKpMasteryByName(map);
      })
      .catch(() => {
        if (!cancelled) setKpMasteryByName({});
      });
    return () => {
      cancelled = true;
    };
  }, [aiModalOpen, selectedClass, schoolId]);

  const isLanguage = localSubject === "语文" || localSubject === "英语";
  const isMathScience = ["数学", "物理", "化学", "生物", "科学"].includes(
    localSubject,
  );
  const availableTypes: QuestionType[] = [
    "choice",
    "fill",
    "judge",
    "matching",
    "ordering",
    "short_answer",
    ...(isLanguage
      ? (["reading", "cloze", "essay"] as QuestionType[])
      : []),
    ...(isMathScience
      ? (["calculation", "application"] as QuestionType[])
      : []),
  ];

  const handleAddQuestion = (type: QuestionType) => {
    setQuestions((prev) => {
      const newQ: ExamQuestion = {
        id: newQuestionId("q"),
        type,
        stem: "",
        content: "",
        subQuestions:
          type === "short_answer" || type === "reading"
            ? [""]
            : type === "matching"
              ? ["", "", "", ""]
              : undefined,
        options:
          type === "choice" ||
          type === "matching" ||
          type === "ordering"
            ? ["", "", "", ""]
            : [],
        score: type === "essay" ? 30 : 5,
      };
      // We also want to set active question ID, but doing it in setState callback is safer
      // Alternatively, we can use a separate useEffect to set active ID if needed,
      // but setTimeout works to ensure it happens after render
      setTimeout(() => setActiveQuestionId(newQ.id), 0);
      return [...prev, newQ];
    });
  };

  const handleUpdateQuestion = (id: string, updates: Partial<ExamQuestion>) => {
    setQuestions(
      questions.map((q) => (q.id === id ? { ...q, ...updates } : q)),
    );
  };

  const handleDeleteQuestion = (id: string) => {
    setQuestions(questions.filter((q) => q.id !== id));
    if (activeQuestionId === id) {
      setActiveQuestionId(null);
    }
  };

  const handleBatchDelete = () => {
    if (selectedQIds.length === 0) return;
    if (
      !confirm(
        t("examGen.toast.batchDeleteConfirm", { count: selectedQIds.length }),
      )
    )
      return;
    setQuestions(questions.filter((q) => !selectedQIds.includes(q.id)));
    if (activeQuestionId && selectedQIds.includes(activeQuestionId)) {
      setActiveQuestionId(null);
    }
    setSelectedQIds([]);
    setBatchMode(false);
  };

  const handleOpenScoreModal = () => {
    const initialScores: Record<string, number> = {};
    Object.keys(questionsByType).forEach((type) => {
      // Find the first question of this type to use as default score
      const firstQ = questionsByType[type][0];
      if (firstQ) initialScores[type] = firstQ.score;
    });
    setTypeScores(initialScores);
    setScoreModalOpen(true);
  };

  const handleApplyBatchScores = () => {
    setQuestions(
      questions.map((q) => {
        if (typeScores[q.type] !== undefined) {
          return { ...q, score: typeScores[q.type] };
        }
        return q;
      }),
    );
    setScoreModalOpen(false);
    toast.success(t("examGen.toast.batchScoreSuccess"));
  };

  const handleAiGenerate = async () => {
    // 汇总知识点：图谱多选 + 自由输入（顿号/逗号/分号/换行拆分）
    const topics: string[] = [];
    const seen = new Set<string>();
    kpList
      .filter((k) => selectedKpIds.includes(k.id))
      .forEach((k) => {
        if (!seen.has(k.name)) {
          seen.add(k.name);
          topics.push(k.name);
        }
      });
    aiForm.topic
      .split(/[、,，;；\n]+/)
      .map((s) => s.trim())
      .filter(Boolean)
      .forEach((s) => {
        if (!seen.has(s)) {
          seen.add(s);
          topics.push(s);
        }
      });
    if (topics.length === 0) {
      toast.error(t("examGen.toast.topicRequired"));
      return;
    }

    // 确定组卷要求与基础题目（手动占位 / 已有试卷 / 题型模板）
    let requirements: { type: string; count: number; score: number }[] = [];
    let baseQuestions: ExamQuestion[] = questions;

    if (templateMode === "paper") {
      const tp = exams.find((e) => e.id === templatePaperId);
      if (!tp) {
        toast.error(t("examGen.toast.templatePaperRequired"));
        return;
      }
      const tq = toExamQuestions(tp.questions);
      if (tq.length === 0) {
        toast.error(t("examGen.toast.templatePaperEmpty"));
        return;
      }
      requirements = requirementsFromQuestions(tq);
      baseQuestions = buildSkeleton(requirements);
    } else if (templateMode === "type") {
      requirements = requirementsFromTemplates(typeTemplates);
      if (requirements.length === 0) {
        const isLang = localSubject === "语文" || localSubject === "英语";
        requirements = DEFAULT_TYPE_REQUIREMENTS[isLang ? "lang" : "other"];
      }
      baseQuestions = buildSkeleton(requirements);
    } else {
      // 手动占位：找出尚未填写内容的「空占位题」，AI 生成后优先填充这些占位。
      const emptyByType: Record<string, ExamQuestion[]> = {};
      baseQuestions.forEach((q) => {
        if (!isQuestionEmpty(q)) return;
        if (!emptyByType[q.type]) emptyByType[q.type] = [];
        emptyByType[q.type].push(q);
      });
      const emptyTypes = Object.keys(emptyByType).filter(
        (type) => emptyByType[type].length > 0,
      );
      if (emptyTypes.length === 0) {
        toast.error(t("examGen.toast.placeholderRequired"));
        return;
      }
      requirements = emptyTypes.map((type) => {
        const score =
          emptyByType[type][0]?.score || (type === "essay" ? 30 : 5);
        return { type, count: emptyByType[type].length, score };
      });
    }

    try {
      setIsGenerating(true);
      const generatedQuestions = await generateExamQuestionsByAI({
        topic: topics.join("、"),
        topics,
        grade: aiForm.grade,
        term: aiForm.term,
        difficulty: aiForm.difficulty,
        subject: localSubject,
        requirements,
      });
      if (!mountedRef.current) return;

      if (!generatedQuestions || generatedQuestions.length === 0) {
        toast.error(t("examGen.toast.aiEmpty"));
        return;
      }

      // 按题型把 AI 结果分桶，依次填充空占位题；超出占位数量的余量再追加到末尾。
      const queueByType: Record<string, ExamQuestion[]> = {};
      generatedQuestions.forEach((q) => {
        if (q && isQuestionType(q.type)) {
          if (!queueByType[q.type]) queueByType[q.type] = [];
          const ai = q as ExamQuestion;
          // AI 常在题干/内容/子问题里自带 "1." "2、" 题号前缀，和前端题号叠加会串号，入桶前清掉
          queueByType[q.type].push({
            ...ai,
            stem: stripLeadingQuestionNumber(String(ai.stem ?? "")),
            content: stripLeadingQuestionNumber(String(ai.content ?? "")),
            subQuestions: ai.subQuestions?.map((s) =>
              stripLeadingQuestionNumber(String(s)),
            ),
          });
        }
      });

      setQuestions((prev) => {
        // 模板模式用全新骨架为基础（生成差不多的卷），占位模式基于现有题目
        const base = templateMode === "placeholder" ? prev : baseQuestions;
        const consumedByType: Record<string, number> = {};
        const appended: ExamQuestion[] = [];

        const next = base.map((q) => {
          if (!isQuestionEmpty(q)) return q; // 已填写的题目原样保留
          const bucket = queueByType[q.type] ?? [];
          const idx = consumedByType[q.type] ?? 0;
          if (idx < bucket.length) {
            consumedByType[q.type] = idx + 1;
            const ai = bucket[idx];
            // 保留占位题的 id 与分值，内容取自 AI 生成结果
            return {
              ...ai,
              id: q.id,
              score:
                q.score > 0
                  ? q.score
                  : Number(ai.score) || (q.type === "essay" ? 30 : 5),
            };
          }
          return q; // 该题型 AI 结果不足，保留空占位
        });

        // 余量（AI 生成数 > 占位数）追加到末尾，赋予唯一 id，避免 key 重复/编辑串题
        Object.keys(queueByType).forEach((type) => {
          const bucket = queueByType[type];
          const consumed = consumedByType[type] ?? 0;
          for (let i = consumed; i < bucket.length; i += 1) {
            appended.push({
              ...bucket[i],
              id: newQuestionId("ai"),
            });
          }
        });

        // 防御历史占位 id 重复/为空：合并结果整体再过一遍唯一化，保证预览题号不塌缩
        return ensureUniqueQuestionIds([...next, ...appended]);
      });

      toast.success(t("examGen.toast.aiSuccessMerged"));
      setAiModalOpen(false);
    } catch (err: unknown) {
      toast.error(t("examGen.toast.aiFailed"), {
        description: getErrorMessage(err),
      });
    } finally {
      if (mountedRef.current) setIsGenerating(false);
    }
  };

  const renderPdfBlob = async () => {
    if (!previewRef.current)
      throw new Error(t("examGen.toast.previewNotReady"));
    const html2canvas = (await import("html2canvas")).default;
    const { jsPDF } = await import("jspdf");

    const pdf = new jsPDF("p", "mm", "a4");
    const pdfWidth = pdf.internal.pageSize.getWidth();
    const pdfHeight = pdf.internal.pageSize.getHeight();

    // We will render each page container individually
    // This perfectly matches the visual pagination and ensures no cuts happen mid-element
    // because we already laid them out cleanly in discrete pages.
    const pageNodes = Array.from(previewRef.current.children) as HTMLElement[];

    for (let i = 0; i < pageNodes.length; i++) {
      if (i > 0) pdf.addPage();

      const canvas = await html2canvas(pageNodes[i], {
        scale: 2,
        useCORS: true,
        logging: false,
        backgroundColor: "#ffffff",
      });

      const imgData = canvas.toDataURL("image/jpeg", 1.0);

      // Calculate scale factor to fit exactly into A4 width
      const scaleFactor = pdfWidth / (pageNodes[i].offsetWidth * 2);
      const scaledHeight = pageNodes[i].offsetHeight * 2 * scaleFactor;

      // If the scaled height is somehow larger than A4 height, it will just draw off the bottom
      // but since we rely on the pagination algorithm, it shouldn't happen unless a single question is massive.
      pdf.addImage(imgData, "JPEG", 0, 0, pdfWidth, scaledHeight);
    }

    const blob = pdf.output("blob");
    const safeTitle = (paperTitle || t("examGen.pdfFallback")).replace(
      /[\\/:*?"<>|]/g,
      "_",
    );
    const filename = `${safeTitle}_${new Date().toLocaleDateString("zh-CN").replace(/\//g, "-")}.pdf`;
    return { blob, filename, pdf };
  };

  const handleDownloadPdf = async () => {
    if (questions.length === 0) {
      toast.error(t("examGen.toast.addQuestionsFirst"));
      return;
    }
    try {
      const { pdf, filename } = await renderPdfBlob();
      pdf.save(filename);
      if (!mountedRef.current) return;
      toast.success(t("examGen.toast.downloadSuccess"));
    } catch (error: unknown) {
      toast.error(t("examGen.toast.downloadFailed"), {
        description: getErrorMessage(error),
      });
    }
  };

  const handlePrint = () => {
    if (questions.length === 0) {
      toast.error(t("examGen.toast.addQuestionsFirst"));
      return;
    }
    const prefs = readGlobalPrintPrefs();
    if (prefs.printMode === "compat") {
      withCompatPrint(() => window.print(), prefs);
      return;
    }
    window.print();
  };

  const handleSendEmailClick = () => {
    if (questions.length === 0) {
      toast.error(t("examGen.toast.addQuestionsFirst"));
      return;
    }
    setTargetEmailInput("");
    setSelectedUserObj(null);
    setEmailTargetType("self");
    setEmailModalOpen(true);
  };

  const executeSendEmail = async () => {
    try {
      setSendingEmail(true);
      const { blob, filename } = await renderPdfBlob();
      const buffer = await blob.arrayBuffer();
      let binary = "";
      const bytes = new Uint8Array(buffer);
      for (let i = 0; i < bytes.length; i += 1) {
        binary += String.fromCharCode(bytes[i]);
      }
      const pdfBase64 = btoa(binary);
      const targetEmail =
        emailTargetType === "others" ? targetEmailInput : undefined;
      const res = await sendExamEmail({
        pdf_base64: pdfBase64,
        filename,
        to_email: targetEmail,
      });
      if (!mountedRef.current) return;
      toast.success(t("examGen.toast.emailSent"), {
        description: res.to_email
          ? t("examGen.toast.emailSentTo", { email: res.to_email })
          : t("examGen.toast.emailSentSelf"),
      });
      setEmailModalOpen(false);
    } catch (error: unknown) {
      toast.error(t("examGen.toast.emailFailed"), {
        description:
          getErrorMessage(error) || t("examGen.toast.emailFailedDesc"),
      });
    } finally {
      if (mountedRef.current) setSendingEmail(false);
    }
  };

  const activeQuestion = questions.find((q) => q.id === activeQuestionId);
  const totalScore = questions.reduce(
    (sum, q) => sum + (Number(q.score) || 0),
    0,
  );

  /** 预览/打印/PDF 使用规范化后的题目（数学等学科去除 LaTeX） */
  const previewQuestions = useMemo(
    () => normalizeExamQuestions(questions, localSubject),
    [questions, localSubject],
  );

  // Group questions by type for preview
  const questionsByType = useMemo(() => {
    const map: Record<string, ExamQuestion[]> = {};
    previewQuestions.forEach((q) => {
      if (!map[q.type]) map[q.type] = [];
      map[q.type].push(q);
    });
    return map;
  }, [previewQuestions]);

  const numberToChinese = useMemo(
    () => Array.from({ length: TYPE_ORDER.length }, (_, i) => getSectionNumber(i)),
    [getSectionNumber],
  );

  // 大题号按「实际存在的题型」顺序连续编号（一、二、三…），
  // 而不是 TYPE_ORDER 固定槽位——否则没出的题型会把大题号顶出空档（如「三」直接跳「九」）
  const sectionNumberIndex = useMemo(() => {
    const map: Record<string, number> = {};
    let seq = 0;
    TYPE_ORDER.forEach((type) => {
      if ((questionsByType[type]?.length ?? 0) > 0) {
        map[type] = seq;
        seq += 1;
      }
    });
    return map;
  }, [questionsByType]);

  // 小题号跨大题连续累计（1-10 选择、11-15 填空……），与纸质试卷习惯一致
  const questionNumberBase = useMemo(() => {
    const map: Record<string, number> = {};
    let acc = 0;
    TYPE_ORDER.forEach((type) => {
      const n = questionsByType[type]?.length ?? 0;
      if (n > 0) {
        map[type] = acc;
        acc += n;
      }
    });
    return map;
  }, [questionsByType]);

  /** 小题号：按题目在本题型中的位置编号；分页引用暂时落后时回退按 id 查找 */
  const getQuestionNumber = (q: ExamQuestion): number => {
    const qsOfType = questionsByType[q.type] ?? [];
    let pos = qsOfType.indexOf(q);
    if (pos < 0) pos = qsOfType.findIndex((qt) => qt.id === q.id);
    return (questionNumberBase[q.type] ?? 0) + Math.max(pos, 0) + 1;
  };

  const [paginatedQuestions, setPaginatedQuestions] = useState<
    ExamQuestion[][]
  >([]);
  const measurementContainerRef = useRef<HTMLDivElement>(null);
  // 保存上次分页计算结果,用于内容判等
  const lastPaginatedRef = useRef<ExamQuestion[][]>([]);

  // Split questions into pages based on ACTUAL rendered height via a hidden measurement container
  useEffect(() => {
    if (previewQuestions.length === 0) {
      setPaginatedQuestions((prev) =>
        prev.length === 1 && prev[0].length === 0 ? prev : [[]],
      );
      lastPaginatedRef.current = [[]];
      return;
    }

    const performPagination = () => {
      const container = measurementContainerRef.current;
      if (!container) return;

      const pages: ExamQuestion[][] = [];
      let currentPage: ExamQuestion[] = [];

      // 响应式:预览页宽度随容器缩放(max-w-[794px]),分页高度按实际渲染宽度等比换算,
      // 保证小屏下分页结果与可见页尺寸一致,内容不会被裁切。794×1122 为 A4 基准。
      const pageWidth = container.offsetWidth || 794;
      const scaleRatio = pageWidth / 794;
      const PAGE_HEIGHT = Math.round(970 * scaleRatio); // 794px 时 970px 可用高度(978 - 边距余量)
      let currentHeight = Math.round(120 * scaleRatio); // First page header height (title + info row + margins)

      // Get all question and section header elements from the hidden container
      const elements = Array.from(container.children) as HTMLElement[];
      let elemIdx = 0;

      TYPE_ORDER.forEach((type) => {
        const qs = questionsByType[type];
        if (!qs || qs.length === 0) return;

        // Process section header
        const headerEl = elements[elemIdx++];
        if (headerEl) {
          const headerHeight = headerEl.getBoundingClientRect().height + 16; // Add margin bottom
          currentHeight += headerHeight;
          if (currentHeight > PAGE_HEIGHT && currentPage.length > 0) {
            pages.push(currentPage);
            currentPage = [];
            currentHeight = headerHeight + Math.round(40 * scaleRatio); // Top margin for new page
          }
        }

        // Process each question
        qs.forEach((q) => {
          const qEl = elements[elemIdx++];
          if (qEl) {
            const qHeight = qEl.getBoundingClientRect().height + 24; // Add gap between questions

            if (
              currentHeight + qHeight > PAGE_HEIGHT &&
              currentPage.length > 0
            ) {
              pages.push(currentPage);
              currentPage = [q];
              currentHeight = Math.round(60 * scaleRatio) + qHeight; // Reset height for new page with some top padding
            } else {
              currentPage.push(q);
              currentHeight += qHeight;
            }
          } else {
            // Fallback if DOM element missing
            currentPage.push(q);
          }
        });
      });

      if (currentPage.length > 0) {
        pages.push(currentPage);
      }

      // 内容判等:与上次计算结果一致时跳过 setState,避免无意义重渲染
      const sameContent =
        pages.length === lastPaginatedRef.current.length &&
        pages.every(
          (pg, i) =>
            pg.length === lastPaginatedRef.current[i].length &&
            pg.every((q, j) => q === lastPaginatedRef.current[i][j]),
        );
      if (!sameContent) {
        lastPaginatedRef.current = pages;
        setPaginatedQuestions(pages);
      }
    };

    // We need to wait a tick for React to render the hidden container first
    // before we can measure it.
    const timer = setTimeout(performPagination, 50);
    return () => clearTimeout(timer);
  }, [previewQuestions, questionsByType]);

  if (view === "overview") {
    return (
      <div className="space-y-6">
        <Card className="border-primary/15 bg-gradient-to-r from-primary/[0.06] via-background to-background">
          <CardHeader className="pb-5">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    <FileText className="h-5 w-5" />
                  </div>
                  <div>
                    <CardTitle className="text-xl">
                      {t("examGen.title")}
                    </CardTitle>
                    <CardDescription>{t("examGen.subtitle")}</CardDescription>
                  </div>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  className="gap-2"
                  onClick={() => setTieredOpen(true)}
                >
                  <Layers className="h-4 w-4" />
                  {t("smartGen.tiered.entry")}
                </Button>
                <Button className="gap-2" onClick={() => openEditor()}>
                  <Plus className="h-4 w-4" />
                  {t("examGen.createExam")}
                </Button>
              </div>
            </div>
          </CardHeader>
        </Card>

        {/* 按层出卷弹窗：与分层推送页同一端点/面板 */}
        <Dialog
          open={tieredOpen}
          onOpenChange={(o) => {
            setTieredOpen(o);
            if (!o) fetchExams();
          }}
        >
          <DialogContent className="max-w-3xl">
            <DialogHeader>
              <DialogTitle>{t("smartGen.tiered.title")}</DialogTitle>
            </DialogHeader>
            <TieredComposePanel
              classId={selectedClass || ""}
              subject={selectedSubject || localSubject}
            />
          </DialogContent>
        </Dialog>

        {loadingExams ? (
          <Card className="border-dashed">
            <CardContent className="flex min-h-[360px] flex-col items-center justify-center gap-4 text-center">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <div className="text-sm text-muted-foreground">
                {t("examGen.loading")}
              </div>
            </CardContent>
          </Card>
        ) : exams.length === 0 ? (
          <Card className="border-dashed">
            <CardContent className="flex min-h-[360px] flex-col items-center justify-center gap-4 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <FileText className="h-8 w-8" />
              </div>
              <div className="space-y-1">
                <div className="text-lg font-semibold text-foreground">
                  {t("examGen.emptyTitle")}
                </div>
                <div className="max-w-lg text-sm text-muted-foreground">
                  {t("examGen.emptyDesc")}
                </div>
              </div>
              <Button className="gap-2" onClick={() => openEditor()}>
                <Plus className="h-4 w-4" />
                {t("examGen.createNow")}
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
            {exams.map((exam) => (
              <Card
                key={exam.id}
                className="overflow-hidden transition-all hover:-translate-y-0.5 hover:shadow-md"
              >
                <CardHeader className="space-y-3 pb-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-2">
                      <Badge variant="outline">
                        {translateSubjectName(locale, exam.subject)}
                      </Badge>
                      <CardTitle className="text-lg leading-snug">
                        {exam.title}
                      </CardTitle>
                      <CardDescription className="text-xs">
                        {t("examGen.updatedAt", {
                          time: new Date(exam.updatedAt).toLocaleString(
                            locale === "en" ? "en-US" : "zh-CN",
                            { hour12: false },
                          ),
                        })}
                      </CardDescription>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="shrink-0 text-muted-foreground hover:text-destructive"
                      onClick={() => handleDeleteExam(exam.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-3 text-xs text-muted-foreground">
                    <div className="rounded-lg bg-muted/30 p-3 text-center">
                      <div className="font-medium text-foreground text-lg">
                        {exam.questions.length}
                      </div>
                      <div className="mt-1">{t("examGen.questionCount")}</div>
                    </div>
                    <div className="rounded-lg bg-muted/30 p-3 text-center">
                      <div className="font-medium text-foreground text-lg">
                        {exam.questions.reduce(
                          (sum, q) => sum + (Number(q.score) || 0),
                          0,
                        )}
                      </div>
                      <div className="mt-1">{t("examGen.totalScore")}</div>
                    </div>
                  </div>
                  <Button
                    className="w-full gap-2"
                    onClick={() => openEditor(exam)}
                  >
                    <FileText className="h-4 w-4" />
                    {t("examGen.editExam")}
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] gap-4 animate-fade-in -m-6 p-6 overflow-hidden print:p-0 print:m-0 print:h-auto print:block">
      {/* Left Sidebar: Editor (Hidden in Print) */}
      <div className="w-[450px] flex flex-col gap-4 shrink-0 print:hidden">
        <Card className="shrink-0 shadow-sm border-border/50">
          <CardHeader className="py-4 px-5 space-y-4">
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                className="h-8 gap-1 px-2 -ml-2"
                onClick={handleBackToOverview}
              >
                <ArrowLeft className="w-4 h-4" /> {t("common.back")}
              </Button>
              <CardTitle className="text-lg flex items-center gap-2 ml-2">
                <FileText className="w-5 h-5 text-primary" />
                {t("examGen.editTitle")}
              </CardTitle>
              <div className="ml-auto">
                <Button
                  size="sm"
                  className="h-8 gap-1.5"
                  onClick={handleSaveExam}
                >
                  <Save className="w-3.5 h-3.5" /> {t("examGen.saveExam")}
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="px-5 pb-5 space-y-4">
            <div className="space-y-2">
              <Label>{t("examGen.paperTitle")}</Label>
              <Input
                value={paperTitle}
                onChange={(e) => setPaperTitle(e.target.value)}
                placeholder={t("examGen.paperTitlePlaceholder")}
              />
            </div>
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">
                  {t("examGen.subject")}
                </span>
                <Select value={localSubject} onValueChange={setLocalSubject}>
                  <SelectTrigger className="h-8 w-24 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {EXAM_SUBJECTS.map((s) => (
                      <SelectItem key={s} value={s}>
                        {translateSubjectName(locale, s)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <span className="font-medium text-primary">
                {t("examGen.totalScoreLabel", { score: totalScore })}
              </span>
            </div>

            <div className="pt-2">
              <div className="flex items-center justify-between mb-2 block">
                <Label>{t("examGen.addQuestion")}</Label>
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 text-xs text-primary"
                    onClick={() => setAiModalOpen(true)}
                  >
                    <Sparkles className="w-3 h-3 mr-1" />{" "}
                    {t("examGen.aiGenerate")}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 text-xs text-primary"
                    onClick={handleOpenScoreModal}
                  >
                    <Edit2 className="w-3 h-3 mr-1" /> {t("examGen.batchScore")}
                  </Button>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {availableTypes.map((type) => (
                  <Button
                    key={type}
                    variant="outline"
                    size="sm"
                    onClick={() => handleAddQuestion(type)}
                    className="text-xs"
                  >
                    <Plus className="w-3.5 h-3.5 mr-1" />{" "}
                    {getQuestionTypeLabel(type)}
                  </Button>
                ))}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setQuestionBankOpen(true)}
                  className="text-xs"
                >
                  <BookCopy className="w-3.5 h-3.5 mr-1" /> 从题库选题
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="flex-1 flex flex-col overflow-hidden shadow-sm border-border/50">
          <CardHeader className="py-3 px-5 border-b bg-muted/20 shrink-0 flex flex-row items-center justify-between">
            <CardTitle className="text-base">
              {t("examGen.questionList", { count: questions.length })}
            </CardTitle>
            {questions.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setBatchMode(!batchMode);
                  setSelectedQIds([]);
                }}
                className="h-7 text-xs"
              >
                {batchMode ? t("examGen.cancelBatch") : t("examGen.batchMode")}
              </Button>
            )}
          </CardHeader>
          <div className="flex-1 flex overflow-hidden">
            {/* Question List */}
            <ScrollArea className="w-1/3 border-r bg-muted/10 shrink-0 flex flex-col">
              {batchMode && (
                <div className="p-2 flex gap-2 border-b bg-muted/30 sticky top-0 z-10">
                  <Button
                    size="sm"
                    variant="outline"
                    className="flex-1 text-xs h-7"
                    onClick={() => setSelectedQIds(questions.map((q) => q.id))}
                  >
                    {t("common.selectAll")}
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    className="flex-1 text-xs h-7"
                    onClick={handleBatchDelete}
                    disabled={selectedQIds.length === 0}
                  >
                    {t("examGen.deleteSelected")}
                  </Button>
                </div>
              )}
              <div className="p-2 space-y-1">
                {questions.map((q, idx) => (
                  <div
                    key={q.id}
                    className={cn(
                      "p-2 rounded-md cursor-pointer text-xs transition-colors flex items-center justify-between group",
                      activeQuestionId === q.id
                        ? "bg-primary/10 text-primary font-medium"
                        : "hover:bg-muted",
                    )}
                    onClick={() => !batchMode && setActiveQuestionId(q.id)}
                  >
                    <div className="flex items-center gap-2 flex-1 overflow-hidden">
                      {batchMode && (
                        <input
                          type="checkbox"
                          className="shrink-0"
                          checked={selectedQIds.includes(q.id)}
                          onChange={(e) => {
                            if (e.target.checked)
                              setSelectedQIds([...selectedQIds, q.id]);
                            else
                              setSelectedQIds(
                                selectedQIds.filter((id) => id !== q.id),
                              );
                          }}
                        />
                      )}
                      <span className="truncate flex-1">
                        {idx + 1}. {getQuestionTypeLabel(q.type)}
                      </span>
                    </div>
                    <span className="text-muted-foreground shrink-0">
                      {t("examGen.scoreUnit", { score: q.score })}
                    </span>
                  </div>
                ))}
                {questions.length === 0 && (
                  <div className="text-center py-10 text-xs text-muted-foreground">
                    {t("examGen.noQuestions")}
                  </div>
                )}
              </div>
            </ScrollArea>

            {/* Active Question Editor */}
            <ScrollArea className="flex-1">
              {activeQuestion ? (
                <div className="p-4 space-y-4">
                  <div className="flex items-center justify-between">
                    <Badge variant="outline">
                      {getQuestionTypeLabel(activeQuestion.type)}
                    </Badge>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 text-xs text-destructive hover:text-destructive"
                      onClick={() => handleDeleteQuestion(activeQuestion.id)}
                    >
                      <Trash2 className="w-3.5 h-3.5 mr-1" />{" "}
                      {t("examGen.deleteQuestion")}
                    </Button>
                  </div>

                  <div className="space-y-2">
                    <Label>{t("examGen.score")}</Label>
                    <Input
                      type="number"
                      value={activeQuestion.score}
                      onChange={(e) =>
                        handleUpdateQuestion(activeQuestion.id, {
                          score: Number(e.target.value) || 0,
                        })
                      }
                    />
                  </div>

                  {(activeQuestion.type === "short_answer" ||
                    activeQuestion.type === "essay" ||
                    activeQuestion.type === "reading") && (
                    <div className="space-y-2">
                      <Label>
                        {activeQuestion.type === "reading"
                          ? t("examGen.readingMaterialLabel")
                          : t("examGen.stemLabel")}
                      </Label>
                      <Textarea
                        placeholder={t("examGen.stemPlaceholder")}
                        value={activeQuestion.stem}
                        onChange={(e) =>
                          handleUpdateQuestion(activeQuestion.id, {
                            stem: e.target.value,
                          })
                        }
                        className="min-h-[100px]"
                      />
                    </div>
                  )}

                  <div className="space-y-2">
                    <Label>
                      {activeQuestion.type === "essay"
                        ? t("examGen.essayPrompt")
                        : activeQuestion.type === "cloze"
                          ? t("examGen.clozePassageLabel")
                          : t("examGen.questionContent")}
                    </Label>
                    {(activeQuestion.type === "short_answer" ||
                      activeQuestion.type === "reading") &&
                    activeQuestion.subQuestions ? (
                      <div className="space-y-3 pt-1">
                        {(activeQuestion.subQuestions ?? []).map(
                          (sub, sIdx) => (
                            <div key={sIdx} className="flex items-start gap-2">
                              <span className="font-medium text-sm mt-2 w-6 shrink-0">
                                ({sIdx + 1})
                              </span>
                              <Textarea
                                value={sub}
                                onChange={(e) => {
                                  const newSubs = [
                                    ...(activeQuestion.subQuestions ?? []),
                                  ];
                                  newSubs[sIdx] = e.target.value;
                                  handleUpdateQuestion(activeQuestion.id, {
                                    subQuestions: newSubs,
                                  });
                                }}
                                placeholder={t(
                                  "examGen.subQuestionPlaceholder",
                                  {
                                    index: sIdx + 1,
                                  },
                                )}
                                className="min-h-[60px]"
                              />
                              <Button
                                variant="ghost"
                                size="icon"
                                className="text-destructive w-8 h-8 shrink-0 mt-1"
                                onClick={() => {
                                  const newSubs = (
                                    activeQuestion.subQuestions ?? []
                                  ).filter((_, i) => i !== sIdx);
                                  handleUpdateQuestion(activeQuestion.id, {
                                    subQuestions: newSubs,
                                  });
                                }}
                              >
                                <Trash2 className="w-4 h-4" />
                              </Button>
                            </div>
                          ),
                        )}
                        <Button
                          variant="outline"
                          size="sm"
                          className="w-full mt-2 border-dashed"
                          onClick={() => {
                            handleUpdateQuestion(activeQuestion.id, {
                              subQuestions: [
                                ...(activeQuestion.subQuestions ?? []),
                                "",
                              ],
                            });
                          }}
                        >
                          <Plus className="w-3.5 h-3.5 mr-1" />{" "}
                          {t("examGen.addSubQuestion")}
                        </Button>
                      </div>
                    ) : (
                      <Textarea
                        placeholder={t("examGen.contentPlaceholder")}
                        value={activeQuestion.content}
                        onChange={(e) =>
                          handleUpdateQuestion(activeQuestion.id, {
                            content: e.target.value,
                          })
                        }
                        className="min-h-[100px]"
                      />
                    )}
                  </div>

                  {(activeQuestion.type === "choice" ||
                    activeQuestion.type === "matching" ||
                    activeQuestion.type === "ordering" ||
                    activeQuestion.type === "cloze") &&
                    activeQuestion.options && (
                      <div className="space-y-3 pt-2">
                        <Label>
                          {activeQuestion.type === "matching"
                            ? t("examGen.matchingLeftLabel")
                            : activeQuestion.type === "ordering"
                              ? t("examGen.orderingItemsLabel")
                              : activeQuestion.type === "cloze"
                                ? t("examGen.clozeOptionsLabel")
                                : t("examGen.optionsLabel")}
                        </Label>
                        {activeQuestion.options.map((opt, oIdx) => (
                          <div key={oIdx} className="flex items-center gap-2">
                            <span className="font-medium text-sm w-6">
                              {String.fromCharCode(65 + oIdx)}.
                            </span>
                            <Input
                              value={opt}
                              onChange={(e) => {
                                const newOpts = [...activeQuestion.options];
                                newOpts[oIdx] = e.target.value;
                                handleUpdateQuestion(activeQuestion.id, {
                                  options: newOpts,
                                });
                              }}
                              placeholder={t("examGen.optionPlaceholder", {
                                letter: String.fromCharCode(65 + oIdx),
                              })}
                            />
                            <Button
                              variant="ghost"
                              size="icon"
                              className="text-destructive w-8 h-8 shrink-0"
                              onClick={() => {
                                const newOpts = activeQuestion.options.filter(
                                  (_, i) => i !== oIdx,
                                );
                                handleUpdateQuestion(activeQuestion.id, {
                                  options: newOpts,
                                });
                              }}
                            >
                              <Trash2 className="w-4 h-4" />
                            </Button>
                          </div>
                        ))}
                        {activeQuestion.options.length < 8 && (
                          <Button
                            variant="outline"
                            size="sm"
                            className="w-full mt-2 border-dashed"
                            onClick={() => {
                              handleUpdateQuestion(activeQuestion.id, {
                                options: [...activeQuestion.options, ""],
                              });
                            }}
                          >
                            <Plus className="w-3.5 h-3.5 mr-1" />{" "}
                            {t("examGen.addOption")}
                          </Button>
                        )}
                      </div>
                    )}

                  {activeQuestion.type === "matching" &&
                    activeQuestion.subQuestions && (
                      <div className="space-y-3 pt-2">
                        <Label>{t("examGen.matchingRightLabel")}</Label>
                        {(activeQuestion.subQuestions ?? []).map((sub, sIdx) => (
                          <div key={sIdx} className="flex items-center gap-2">
                            <span className="font-medium text-sm w-6 shrink-0">
                              {sIdx + 1}.
                            </span>
                            <Input
                              value={sub}
                              onChange={(e) => {
                                const newSubs = [
                                  ...(activeQuestion.subQuestions ?? []),
                                ];
                                newSubs[sIdx] = e.target.value;
                                handleUpdateQuestion(activeQuestion.id, {
                                  subQuestions: newSubs,
                                });
                              }}
                              placeholder={t("examGen.matchingRightPlaceholder", {
                                index: sIdx + 1,
                              })}
                            />
                            <Button
                              variant="ghost"
                              size="icon"
                              className="text-destructive w-8 h-8 shrink-0"
                              onClick={() => {
                                const newSubs = (
                                  activeQuestion.subQuestions ?? []
                                ).filter((_, i) => i !== sIdx);
                                handleUpdateQuestion(activeQuestion.id, {
                                  subQuestions: newSubs,
                                });
                              }}
                            >
                              <Trash2 className="w-4 h-4" />
                            </Button>
                          </div>
                        ))}
                        {(activeQuestion.subQuestions ?? []).length < 8 && (
                          <Button
                            variant="outline"
                            size="sm"
                            className="w-full mt-2 border-dashed"
                            onClick={() => {
                              handleUpdateQuestion(activeQuestion.id, {
                                subQuestions: [
                                  ...(activeQuestion.subQuestions ?? []),
                                  "",
                                ],
                              });
                            }}
                          >
                            <Plus className="w-3.5 h-3.5 mr-1" />{" "}
                            {t("examGen.matchingAddRight")}
                          </Button>
                        )}
                      </div>
                    )}
                </div>
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-muted-foreground pt-20">
                  {t("examGen.selectOrAdd")}
                </div>
              )}
            </ScrollArea>
          </div>
        </Card>
      </div>

      {/* Right Panel: Live Preview */}
      <Card className="flex-1 flex flex-col overflow-hidden shadow-sm border-border/50 print:border-none print:shadow-none bg-muted/30">
        <CardHeader className="py-3 px-5 border-b bg-white shrink-0 flex flex-row items-center justify-between print:hidden shadow-sm z-10 print-action-bar">
          <CardTitle className="text-base">
            {t("examGen.livePreview")}
          </CardTitle>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownloadPdf}
              className="h-8 gap-1.5 bg-white"
            >
              <Download className="w-3.5 h-3.5" /> {t("examGen.downloadPdf")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handlePrint}
              className="h-8 gap-1.5 bg-white"
            >
              <Printer className="w-3.5 h-3.5" /> {t("examGen.print")}
            </Button>
            <Button className="h-8 gap-1.5" onClick={handleSendEmailClick}>
              <Mail className="w-3.5 h-3.5" /> {t("examGen.sendEmail")}
            </Button>
          </div>
        </CardHeader>

        <ScrollArea className="flex-1 p-8 print:p-0 print:overflow-visible bg-muted/30">
          <div className="relative mx-auto flex w-full max-w-[794px] flex-col gap-8 print:gap-0">
            {/* Hidden container to measure actual DOM heights for pagination.
                width 与可见页保持一致(w-full 跟随同一容器),保证小屏下分页测量结果正确 */}
            <div
              ref={measurementContainerRef}
              className="absolute opacity-0 pointer-events-none w-full px-12"
              style={{ zIndex: -9999, top: 0, left: 0 }}
            >
              {TYPE_ORDER.map((type) => {
                const qs = questionsByType[type];
                if (!qs || qs.length === 0) return null;
                const sectionIndex =
                  sectionNumberIndex[type] ?? TYPE_ORDER.indexOf(type);
                const sectionScore = qs.reduce(
                  (sum, q) => sum + (Number(q.score) || 0),
                  0,
                );

                return (
                  <React.Fragment key={`measure-type-${type}`}>
                    {/* Measure Section Header */}
                    <h2 className="text-lg font-bold pt-4">
                      {t("examGen.sectionHeader", {
                        number: numberToChinese[sectionIndex],
                        type: getQuestionTypeLabel(type),
                      })}
                      <span className="text-base font-normal ml-2">
                        {t("examGen.sectionStats", {
                          count: qs.length,
                          score: sectionScore,
                        })}
                      </span>
                    </h2>

                    {/* Measure Questions */}
                    {qs.map((q, qIdx) => (
                      <div
                        key={`measure-${q.id}`}
                        className="text-base leading-relaxed mb-6"
                      >
                        <div className="flex gap-2">
                          <span className="font-medium shrink-0">
                            {(questionNumberBase[type] ?? 0) + qIdx + 1}.
                          </span>
                          <div className="flex-1">
                            {q.stem && (
                              <div className="mb-2 whitespace-pre-wrap">
                                {q.stem}
                              </div>
                            )}
                            {(q.type === "short_answer" ||
                              q.type === "reading") &&
                            q.subQuestions &&
                            q.subQuestions.length > 0 ? (
                              <div className="space-y-4">
                                {q.subQuestions.map((sub, sIdx) => (
                                  <div key={sIdx} className="space-y-2">
                                    <div className="whitespace-pre-wrap leading-relaxed">
                                      ({sIdx + 1}) {sub}
                                    </div>
                                    <div className="mt-4 pl-4">
                                      {Array.from({ length: 2 }).map((_, i) => (
                                        <div
                                          key={i}
                                          className="border-b border-gray-400 mt-8"
                                        ></div>
                                      ))}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <span className="whitespace-pre-wrap">
                                {q.content}
                                {(q.type === "choice" ||
                                  q.type === "judge") && (
                                  <span className="ml-2 font-normal">( )</span>
                                )}
                              </span>
                            )}
                          </div>
                        </div>
                        {q.type === "choice" &&
                          q.options &&
                          q.options.length > 0 && (
                            <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2 pl-6">
                              {q.options.map((opt, oIdx) => (
                                <div key={oIdx} className="flex gap-2">
                                  <span className="font-medium">
                                    {String.fromCharCode(65 + oIdx)}.
                                  </span>
                                  <span>{opt}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        {q.type === "matching" && (
                          <div className="mt-3 grid grid-cols-2 gap-6 pl-6">
                            <div className="space-y-2">
                              {q.options.map((opt, oIdx) => (
                                <div key={oIdx} className="flex gap-2">
                                  <span className="font-medium">
                                    {String.fromCharCode(65 + oIdx)}.
                                  </span>
                                  <span>{opt}</span>
                                </div>
                              ))}
                            </div>
                            <div className="space-y-2">
                              {(q.subQuestions ?? []).map((sub, sIdx) => (
                                <div key={sIdx} className="flex gap-2">
                                  <span className="font-medium">
                                    {sIdx + 1}.
                                  </span>
                                  <span>{sub}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {q.type === "ordering" && (
                          <div className="mt-3 space-y-2 pl-6">
                            {q.options.map((opt, oIdx) => (
                              <div key={oIdx} className="flex gap-2 items-center">
                                <span className="font-medium text-gray-500">
                                  ( )
                                </span>
                                <span>
                                  {oIdx + 1}. {opt}
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                        {q.type === "cloze" &&
                          q.options &&
                          q.options.length > 0 && (
                            <div className="mt-3 pl-6">
                              <span className="text-sm text-gray-600">
                                {t("examGen.clozeOptionsPrefix")}
                              </span>
                              <div className="flex flex-wrap gap-x-6 gap-y-1 mt-1">
                                {q.options.map((opt, oIdx) => (
                                  <span key={oIdx}>
                                    {String.fromCharCode(65 + oIdx)}. {opt}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                        {/* 填空题答案写在题干的「＿＿＿」里，不再画横线；计算/应用题不画线，留白作答 */}
                        {(q.type === "calculation" ||
                          q.type === "application") && (
                          <div className="mt-4 pl-6 min-h-[140px]"></div>
                        )}
                        {q.type === "essay" && (
                          <div className="mt-6 border border-gray-400 min-h-[400px] p-2 text-sm text-gray-400 text-center flex items-center justify-center">
                            {t("examGen.essayArea")}
                          </div>
                        )}
                      </div>
                    ))}
                  </React.Fragment>
                );
              })}
            </div>

            <div ref={previewRef} className="flex flex-col gap-8 print:gap-0">
              {paginatedQuestions.map((pageQs, pageIdx) => (
                <div
                  key={pageIdx}
                  className="bg-white shadow-md border print:shadow-none print:border-none print:bg-transparent"
                  style={{
                    width: "100%",
                    aspectRatio: "794 / 1122",
                    height: "auto",
                    overflow: "hidden",
                    padding: "48px 48px 96px 48px",
                    pageBreakAfter:
                      pageIdx < paginatedQuestions.length - 1
                        ? "always"
                        : "auto",
                  }}
                >
                  {/* Paper Header (Only on first page) */}
                  {pageIdx === 0 && (
                    <div className="text-center mb-8 space-y-4">
                      <h1 className="text-2xl font-bold tracking-wider">
                        {paperTitle || t("examGen.unnamedPaper")}
                      </h1>
                      <div className="flex items-center justify-center gap-8 text-sm">
                        <span>{t("examGen.paperClass")}</span>
                        <span>{t("examGen.paperName")}</span>
                        <span>{t("examGen.paperNumber")}</span>
                        <span>
                          {t("examGen.paperTotalScore", { score: totalScore })}
                        </span>
                      </div>
                    </div>
                  )}

                  {/* Questions Body */}
                  {pageQs.length === 0 ? (
                    pageIdx === 0 && (
                      <div className="text-center py-20 text-muted-foreground print:hidden">
                        {t("examGen.previewEmpty")}
                      </div>
                    )
                  ) : (
                    <div className="space-y-8">
                      {/* Render questions in this page. We still want to group them by type visually if possible,
                        or just render them in order with section headers if it's the first question of that type. */}
                      {(() => {
                        let currentType = "";
                        return pageQs.map((q, idx) => {
                          const showHeader = q.type !== currentType;
                          currentType = q.type;

                          const sectionIndex =
                            sectionNumberIndex[q.type] ?? TYPE_ORDER.indexOf(q.type);
                          const qsOfType = questionsByType[q.type] || [];
                          const sectionScore = qsOfType.reduce(
                            (sum, qt) => sum + (Number(qt.score) || 0),
                            0,
                          );
                          const qNumber = getQuestionNumber(q);

                          return (
                            <div key={q.id} className="space-y-4">
                              {showHeader && (
                                <h2 className="text-lg font-bold break-after-avoid pt-4">
                                  {t("examGen.sectionHeader", {
                                    number: numberToChinese[sectionIndex],
                                    type: getQuestionTypeLabel(q.type),
                                  })}
                                  <span className="text-base font-normal ml-2">
                                    {t("examGen.sectionStats", {
                                      count: qsOfType.length,
                                      score: sectionScore,
                                    })}
                                  </span>
                                </h2>
                              )}

                              <div className="text-base leading-relaxed break-inside-avoid print:break-inside-avoid">
                                <div className="flex gap-2">
                                  <span className="font-medium shrink-0">
                                    {qNumber}.
                                  </span>
                                  <div className="flex-1">
                                    {q.stem && (
                                      <div className="mb-2 whitespace-pre-wrap">
                                        {q.stem}
                                      </div>
                                    )}
                                    {(q.type === "short_answer" ||
                                      q.type === "reading") &&
                                    q.subQuestions &&
                                    q.subQuestions.length > 0 ? (
                                      <div className="space-y-4">
                                        {q.subQuestions.map((sub, sIdx) => (
                                          <div
                                            key={sIdx}
                                            className="space-y-2 break-inside-avoid print:break-inside-avoid"
                                          >
                                            <div className="whitespace-pre-wrap leading-relaxed">
                                              ({sIdx + 1}) {sub}
                                              {sIdx === 0 && (
                                                <span className="ml-2 text-sm text-gray-500">
                                                  (
                                                  {t("examGen.scoreUnit", {
                                                    score: q.score,
                                                  })}
                                                  )
                                                </span>
                                              )}
                                            </div>
                                            <div className="mt-4 pl-4">
                                              {Array.from({ length: 2 }).map(
                                                (_, i) => (
                                                  <div
                                                    key={i}
                                                    className="border-b border-gray-400 mt-8"
                                                  ></div>
                                                ),
                                              )}
                                            </div>
                                          </div>
                                        ))}
                                      </div>
                                    ) : (
                                      <>
                                        <span className="whitespace-pre-wrap">
                                          {q.content}
                                          {(q.type === "choice" ||
                                            q.type === "judge") && (
                                            <span className="ml-2 font-normal">
                                              ( )
                                            </span>
                                          )}
                                        </span>
                                        <span className="ml-2 text-sm text-gray-500">
                                          (
                                          {t("examGen.scoreUnit", {
                                            score: q.score,
                                          })}
                                          )
                                        </span>
                                      </>
                                    )}
                                  </div>
                                </div>

                                {q.type === "choice" &&
                                  q.options &&
                                  q.options.length > 0 && (
                                    <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2 pl-6">
                                      {q.options.map((opt, oIdx) => (
                                        <div key={oIdx} className="flex gap-2">
                                          <span className="font-medium">
                                            {String.fromCharCode(65 + oIdx)}.
                                          </span>
                                          <span>{opt}</span>
                                        </div>
                                      ))}
                                    </div>
                                  )}

                                {q.type === "matching" && (
                                  <div className="mt-3 grid grid-cols-2 gap-6 pl-6">
                                    <div className="space-y-2">
                                      {q.options.map((opt, oIdx) => (
                                        <div key={oIdx} className="flex gap-2">
                                          <span className="font-medium">
                                            {String.fromCharCode(65 + oIdx)}.
                                          </span>
                                          <span>{opt}</span>
                                        </div>
                                      ))}
                                    </div>
                                    <div className="space-y-2">
                                      {(q.subQuestions ?? []).map((sub, sIdx) => (
                                        <div key={sIdx} className="flex gap-2">
                                          <span className="font-medium">
                                            {sIdx + 1}.
                                          </span>
                                          <span>{sub}</span>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                {q.type === "ordering" && (
                                  <div className="mt-3 space-y-2 pl-6">
                                    {q.options.map((opt, oIdx) => (
                                      <div
                                        key={oIdx}
                                        className="flex gap-2 items-center"
                                      >
                                        <span className="font-medium text-gray-500">
                                          ( )
                                        </span>
                                        <span>
                                          {oIdx + 1}. {opt}
                                        </span>
                                      </div>
                                    ))}
                                  </div>
                                )}

                                {q.type === "cloze" &&
                                  q.options &&
                                  q.options.length > 0 && (
                                    <div className="mt-3 pl-6">
                                      <span className="text-sm text-gray-600">
                                        {t("examGen.clozeOptionsPrefix")}
                                      </span>
                                      <div className="flex flex-wrap gap-x-6 gap-y-1 mt-1">
                                        {q.options.map((opt, oIdx) => (
                                          <span key={oIdx}>
                                            {String.fromCharCode(65 + oIdx)}.{" "}
                                            {opt}
                                          </span>
                                        ))}
                                      </div>
                                    </div>
                                  )}

                                {/* 填空题答案写在题干的「＿＿＿」里，不再画横线；计算/应用题不画线，留白作答 */}
                                {(q.type === "calculation" ||
                                  q.type === "application") && (
                                  <div className="mt-4 pl-6 min-h-[140px]"></div>
                                )}

                                {q.type === "essay" && (
                                  <div className="mt-6 border border-gray-400 min-h-[400px] p-2 text-sm text-gray-400 text-center flex items-center justify-center">
                                    {t("examGen.essayArea")}
                                  </div>
                                )}
                              </div>
                            </div>
                          );
                        });
                      })()}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </ScrollArea>
      </Card>

      {/* Email Dialog */}
      <Dialog open={emailModalOpen} onOpenChange={setEmailModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("examGen.email.title")}</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <Tabs
              value={emailTargetType}
              onValueChange={(v) =>
                setEmailTargetType(v === "others" ? "others" : "self")
              }
              className="w-full"
            >
              <TabsList className="grid w-full grid-cols-2 mb-4">
                <TabsTrigger value="self">
                  {t("examGen.email.self")}
                </TabsTrigger>
                <TabsTrigger
                  value="others"
                  disabled={!isGlobalAdmin}
                  title={
                    !isGlobalAdmin ? t("examGen.email.adminOnly") : undefined
                  }
                >
                  {t("examGen.email.others")}
                </TabsTrigger>
              </TabsList>

              <TabsContent value="self" className="mt-0">
                <div className="text-sm text-muted-foreground p-4 bg-muted/30 rounded-md">
                  <p>{t("examGen.email.selfHint")}</p>
                </div>
              </TabsContent>

              <TabsContent value="others" className="mt-0 space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">
                    {t("examGen.email.searchUser")}
                  </label>
                  <Popover
                    open={emailUserComboboxOpen}
                    onOpenChange={setEmailUserComboboxOpen}
                  >
                    <PopoverTrigger asChild>
                      <Button
                        variant="outline"
                        role="combobox"
                        aria-expanded={emailUserComboboxOpen}
                        className="w-full justify-between font-normal"
                        disabled={loadingUsers}
                      >
                        {selectedUserObj
                          ? `${selectedUserObj.display_name || selectedUserObj.email.split("@")[0]}`
                          : loadingUsers
                            ? t("examGen.email.loadingUsers")
                            : t("examGen.email.searchPlaceholder")}
                        <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-[380px] p-0" align="start">
                      <Command>
                        <CommandInput
                          placeholder={t("examGen.email.searchInput")}
                        />
                        <CommandList>
                          <CommandEmpty>
                            {t("examGen.email.userNotFound")}
                          </CommandEmpty>
                          <CommandGroup>
                            {usersList.map((u) => (
                              <CommandItem
                                key={u.id}
                                value={u.display_name || u.email.split("@")[0]}
                                onSelect={() => {
                                  // 后端 /users/all 不含 personal_email，选择用户只作展示，不自动填收件人邮箱
                                  setSelectedUserObj(u);
                                  setEmailUserComboboxOpen(false);
                                }}
                              >
                                <Check
                                  className={cn(
                                    "mr-2 h-4 w-4",
                                    selectedUserObj?.id === u.id
                                      ? "opacity-100"
                                      : "opacity-0",
                                  )}
                                />
                                {u.display_name || u.email.split("@")[0]}
                              </CommandItem>
                            ))}
                          </CommandGroup>
                        </CommandList>
                      </Command>
                    </PopoverContent>
                  </Popover>
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium">
                    {t("examGen.email.emailAddress")}
                  </label>
                  <Input
                    type="email"
                    placeholder={t("examGen.email.recipientPlaceholder")}
                    value={targetEmailInput}
                    onChange={(e) => {
                      setTargetEmailInput(e.target.value);
                    }}
                  />
                </div>
              </TabsContent>
            </Tabs>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setEmailModalOpen(false)}
              disabled={sendingEmail}
            >
              {t("common.cancel")}
            </Button>
            <Button
              onClick={executeSendEmail}
              disabled={
                sendingEmail ||
                (emailTargetType === "others" && !targetEmailInput.trim())
              }
            >
              {sendingEmail ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Mail className="h-4 w-4 mr-2" />
              )}
              {sendingEmail
                ? t("examGen.email.sending")
                : t("examGen.email.confirmSend")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Batch Score Dialog */}
      <Dialog open={scoreModalOpen} onOpenChange={setScoreModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("examGen.scoreModal.title")}</DialogTitle>
          </DialogHeader>
          <div className="py-4 space-y-4">
            {Object.keys(typeScores).length === 0 ? (
              <div className="text-sm text-muted-foreground text-center py-4">
                {t("examGen.scoreModal.empty")}
              </div>
            ) : (
              <>
                <div className="text-sm text-muted-foreground mb-4">
                  {t("examGen.scoreModal.hint")}
                </div>
                {Object.keys(typeScores).map((type) => (
                  <div
                    key={type}
                    className="flex items-center justify-between gap-4"
                  >
                    <Label className="w-24 shrink-0">
                      {getQuestionTypeLabel(type as QuestionType)}
                    </Label>
                    <div className="flex items-center gap-2 flex-1">
                      <Input
                        type="number"
                        value={typeScores[type]}
                        onChange={(e) =>
                          setTypeScores({
                            ...typeScores,
                            [type]: Number(e.target.value) || 0,
                          })
                        }
                      />
                      <span className="text-sm text-muted-foreground shrink-0">
                        {t("examGen.scoreModal.perQuestion")}
                      </span>
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setScoreModalOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              onClick={handleApplyBatchScores}
              disabled={Object.keys(typeScores).length === 0}
            >
              {t("examGen.scoreModal.confirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* AI Generate Dialog */}
      <Dialog open={aiModalOpen} onOpenChange={setAiModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-primary" />
              {t("examGen.aiModal.title")}
            </DialogTitle>
          </DialogHeader>
          <div className="py-4 space-y-4">
            <div className="text-sm text-muted-foreground mb-4">
              {t("examGen.aiModal.hint")}
            </div>
            <div className="space-y-2">
              <Label>{t("examGen.aiModal.topic")}</Label>
              <div className="rounded-md border">
                {kpLoading ? (
                  <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {t("common.loading")}
                  </div>
                ) : kpEmpty || kpList.length === 0 ? (
                  <div className="px-3 py-3 text-xs text-muted-foreground">
                    {t("examGen.aiModal.kpEmpty")}
                  </div>
                ) : (
                  <ScrollArea className="h-56">
                    <div className="p-2">
                      {kpUnits.map((u) => {
                        const points = kpList.filter((k) => k.unit_id === u.id);
                        if (points.length === 0) return null;
                        return (
                          <div key={u.id} className="mb-2">
                            <div className="mb-1 text-xs font-medium text-muted-foreground">
                              {u.name}
                            </div>
                            <div className="flex flex-wrap gap-1.5">
                              {points.map((k) => {
                                const checked = selectedKpIds.includes(k.id);
                                const m = kpMasteryByName[k.name.trim()];
                                const pct = m
                                  ? Math.round(m.mastery * 100)
                                  : null;
                                return (
                                  <label
                                    key={k.id}
                                    title={
                                      pct !== null
                                        ? t("examGen.aiModal.kpMasteryTip", {
                                            pct,
                                            count: m.wrong_count,
                                          })
                                        : undefined
                                    }
                                    className={cn(
                                      "inline-flex cursor-pointer items-center gap-1.5 rounded-md border px-2 py-1 text-xs transition-colors",
                                      checked
                                        ? "border-primary bg-primary/10 text-primary"
                                        : "border-border hover:bg-muted",
                                    )}
                                  >
                                    <input
                                      type="checkbox"
                                      className="h-3 w-3"
                                      checked={checked}
                                      onChange={(e) => {
                                        setSelectedKpIds((prev) =>
                                          e.target.checked
                                            ? [...prev, k.id]
                                            : prev.filter((id) => id !== k.id),
                                        );
                                      }}
                                    />
                                    {k.name}
                                    {pct !== null && (
                                      <>
                                        <Progress
                                          value={pct}
                                          className={cn(
                                            "h-1.5 w-10",
                                            kpMasteryBarColor(pct),
                                          )}
                                        />
                                        <span
                                          className={cn(
                                            "text-[10px] leading-none",
                                            kpMasteryTextColor(pct),
                                          )}
                                        >
                                          {pct}%
                                        </span>
                                      </>
                                    )}
                                  </label>
                                );
                              })}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </ScrollArea>
                )}
              </div>
              {Object.keys(kpMasteryByName).length > 0 && (
                <p className="text-[10px] text-muted-foreground">
                  {t("examGen.aiModal.kpMasteryHint")}
                </p>
              )}
              <Textarea
                placeholder={t("examGen.aiModal.topicPlaceholder")}
                value={aiForm.topic}
                onChange={(e) => setAiForm({ ...aiForm, topic: e.target.value })}
                className="min-h-[56px]"
              />
              <p className="text-xs text-muted-foreground">
                {t("examGen.aiModal.topicHint")}
              </p>
            </div>

            <div className="space-y-2">
              <Label>{t("examGen.aiModal.templateMode")}</Label>
              <Select
                value={templateMode}
                onValueChange={(v) =>
                  setTemplateMode(v as "placeholder" | "paper" | "type")
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="placeholder">
                    {t("examGen.aiModal.templatePlaceholder")}
                  </SelectItem>
                  <SelectItem value="paper">
                    {t("examGen.aiModal.templatePaper")}
                  </SelectItem>
                  <SelectItem value="type">
                    {t("examGen.aiModal.templateType")}
                  </SelectItem>
                </SelectContent>
              </Select>
              {templateMode === "paper" && (
                <Select
                  value={templatePaperId}
                  onValueChange={setTemplatePaperId}
                >
                  <SelectTrigger>
                    <SelectValue
                      placeholder={t("examGen.aiModal.selectPaper")}
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {exams.length === 0 ? (
                      <div className="px-2 py-2 text-xs text-muted-foreground">
                        {t("examGen.aiModal.noPaper")}
                      </div>
                    ) : (
                      exams.map((e) => (
                        <SelectItem key={e.id} value={e.id}>
                          {e.title}
                        </SelectItem>
                      ))
                    )}
                  </SelectContent>
                </Select>
              )}
              {templateMode === "type" && (
                <div className="text-xs text-muted-foreground">
                  {typeTemplates.length === 0
                    ? t("examGen.aiModal.noTypeTemplate")
                    : typeTemplates
                        .filter(
                          (tp) =>
                            TYPE_NAME_TO_QUESTION_TYPE[tp.type_name] &&
                            tp.default_count > 0,
                        )
                        .map((tp) => `${tp.type_name}×${tp.default_count}`)
                        .join("、")}
                </div>
              )}
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>{t("examGen.aiModal.grade")}</Label>
                <Select
                  value={aiForm.grade}
                  onValueChange={(v) => setAiForm({ ...aiForm, grade: v })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {EXAM_GRADES.map((g, idx) => (
                      <SelectItem key={g} value={g}>
                        {t(`examGen.grade.${GRADE_I18N_KEYS[idx]}`)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>{t("examGen.aiModal.term")}</Label>
                <Select
                  value={aiForm.term}
                  onValueChange={(v) => setAiForm({ ...aiForm, term: v })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TERM_OPTIONS.map((term) => (
                      <SelectItem key={term.value} value={term.value}>
                        {t(term.key)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label>{t("examGen.aiModal.difficulty")}</Label>
              <Select
                value={aiForm.difficulty}
                onValueChange={(v) => {
                  if (!isDifficulty(v)) return;
                  setAiForm({ ...aiForm, difficulty: v });
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DIFFICULTY_OPTIONS.map((d) => (
                    <SelectItem key={d.value} value={d.value}>
                      {t(d.key)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setAiModalOpen(false)}
              disabled={isGenerating}
            >
              {t("common.cancel")}
            </Button>
            <Button
              onClick={handleAiGenerate}
              disabled={
                isGenerating ||
                (selectedKpIds.length === 0 && !aiForm.topic.trim()) ||
                (templateMode === "paper" && !templatePaperId)
              }
            >
              {isGenerating ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Sparkles className="w-4 h-4 mr-2" />
              )}
              {isGenerating
                ? t("examGen.aiModal.generating")
                : t("examGen.aiModal.start")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 从题库选题弹窗 */}
      <QuestionBankPicker
        open={questionBankOpen}
        onOpenChange={setQuestionBankOpen}
        initialSubject={selectedSubject}
        onAdd={(bankQs) => {
          const newQs = bankQs.map(bankQuestionToExamQuestion);
          setQuestions((prev) => [...prev, ...newQs]);
          toast.success(`已从题库加入 ${newQs.length} 题`);
        }}
      />
    </div>
  );
}
