import { useState, useEffect, useCallback, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  ArrowLeft,
  Loader2,
  Target,
  AlertTriangle,
  BookOpen,
  Users,
  CheckCircle2,
  XCircle,
  ChevronDown,
  FileStack,
  CalendarClock,
  RefreshCcw,
  Lightbulb,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  getErrorBookFolderDetail,
  getWrongQuestionDueList,
  submitWrongQuestionReview,
  getWrongQuestionVariants,
} from "@/services/gradingApi";
import type {
  WrongQuestionReviewItem,
  WrongQuestionReviewResult,
} from "@/services/gradingApi";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { toast } from "sonner";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { useLocale } from "@/contexts/LocaleContext";
import { useGlobalFilters } from "@/hooks/useGlobalFilters";
import { getKnowledgeGraph } from "@/data/knowledgeGraphData";
import { KnowledgeLectureCard } from "./KnowledgeLectureCard";

interface ErrorBookDetailProps {
  folderName: string;
  onBack: () => void;
}

interface RawQuestionStat {
  title: string;
  correct: number;
  wrong: number;
  blank: number;
  wrong_students: string[];
  knowledge_points?: string[];
  subItems?: RawQuestionStat[];
}

interface QuestionStat extends Omit<RawQuestionStat, "subItems"> {
  errorRate: number;
  total: number;
  subItems?: QuestionStat[];
}

interface QuestionPageStat {
  page_no: number;
  label: string;
  questions: QuestionStat[];
}

interface StudentStat {
  filename: string;
  source_filenames?: string[];
  correct_count: number;
  wrong_count: number;
  correct_questions: string[];
  wrong_questions: string[];
  score_total?: number | null;
  question_scores?: Record<string, number>;
}

const paperBoxName = (filename: string) => {
  const stem = String(filename || "").replace(/\.[^/.]+$/, "");
  const match = stem.match(/^(.+)_\d+$/);
  return match?.[1] || stem;
};

const extractClassId = (name: string): string => {
  const s = String(name || "");
  if (s.startsWith("cls_")) {
    const i = s.indexOf("__");
    if (i > 4) return s.slice(4, i);
  }
  return "";
};

const formatReviewDate = (iso: string | null): string => {
  if (!iso) return "--";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "--";
  return d.toLocaleDateString();
};

const isReviewOverdue = (iso: string | null): boolean => {
  if (!iso) return false;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  d.setHours(0, 0, 0, 0);
  return d.getTime() < today.getTime();
};

const isReviewDueToday = (iso: string | null): boolean => {
  if (!iso) return false;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  d.setHours(0, 0, 0, 0);
  return d.getTime() === today.getTime();
};

interface KnowledgePointChipsProps {
  kps?: string[];
  questionKey: string;
  activeKp: string | null;
  onToggle: (key: string, kp: string) => void;
}

function KnowledgePointChips({
  kps,
  questionKey,
  activeKp,
  onToggle,
}: KnowledgePointChipsProps) {
  const { t } = useLocale();
  if (!kps || kps.length === 0) return null;
  return (
    <div className="mb-3 flex flex-wrap items-center gap-1.5">
      <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
        <BookOpen className="h-3 w-3" />
        {t("grading.errorBook.knowledge.points")}:
      </span>
      {kps.map((kp) => {
        const active = activeKp === kp;
        return (
          <button
            key={kp}
            type="button"
            onClick={() => onToggle(questionKey, kp)}
            className={cn(
              "rounded-full border px-2 py-0.5 text-[11px] transition-colors",
              active
                ? "border-primary/30 bg-primary/10 text-primary"
                : "border-border/60 bg-muted/40 text-muted-foreground hover:border-primary/30 hover:bg-primary/10 hover:text-primary",
            )}
          >
            {kp}
          </button>
        );
      })}
    </div>
  );
}

interface RecallPlanCardProps {
  classId: string;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

function RecallPlanCard({
  classId,
  selectedId,
  onSelect,
}: RecallPlanCardProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["wrong-question-due", classId],
    queryFn: () => getWrongQuestionDueList(classId),
    enabled: !!classId,
  });
  const dueList: WrongQuestionReviewItem[] = data?.data ?? [];

  const checkInMutation = useMutation({
    mutationFn: ({
      id,
      result,
    }: {
      id: string;
      result: WrongQuestionReviewResult;
    }) => submitWrongQuestionReview(id, result),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["wrong-question-due", classId],
      });
      queryClient.invalidateQueries({ queryKey: ["wrong-question-variants"] });
      toast.success(t("grading.errorBook.recall.reviewSuccess"));
    },
    onError: (err: any) =>
      toast.error(t("grading.errorBook.recall.reviewFailed"), {
        description: err?.message,
      }),
  });

  if (!classId) {
    return (
      <Card className="border-border/50 shadow-sm">
        <CardContent className="flex min-h-[200px] flex-col items-center justify-center gap-2 text-center text-sm text-muted-foreground">
          <CalendarClock className="h-8 w-8 text-muted-foreground/40" />
          {t("grading.errorBook.recall.noClass")}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="flex flex-col overflow-hidden border-border/50 shadow-sm">
      <CardHeader className="pb-3 shrink-0 bg-muted/10 border-b border-border/50">
        <CardTitle className="text-base flex items-center gap-2">
          <CalendarClock className="w-5 h-5 text-primary" />
          {t("grading.errorBook.recall.title")}
        </CardTitle>
        <CardDescription>
          {t("grading.errorBook.recall.subtitle")}
        </CardDescription>
      </CardHeader>
      <CardContent className="p-0 flex-1 overflow-hidden">
        <ScrollArea className="h-full max-h-[340px]">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center min-h-[180px] gap-3 text-muted-foreground text-sm">
              <Loader2 className="w-6 h-6 animate-spin text-primary/50" />
              {t("grading.errorBook.loading")}
            </div>
          ) : isError ? (
            <div className="flex flex-col items-center justify-center min-h-[180px] gap-2 text-center text-sm text-muted-foreground p-4">
              {t("grading.errorBook.recall.loadFailed")}
            </div>
          ) : dueList.length === 0 ? (
            <div className="flex flex-col items-center justify-center min-h-[180px] gap-2 text-center text-sm text-muted-foreground p-4">
              <CalendarClock className="h-8 w-8 text-muted-foreground/40" />
              {t("grading.errorBook.recall.noDue")}
            </div>
          ) : (
            <div className="divide-y divide-border/40">
              {dueList.map((item) => {
                const active = selectedId === item.id;
                const overdue = isReviewOverdue(item.next_review_at);
                const dueToday = isReviewDueToday(item.next_review_at);
                return (
                  <div
                    key={item.id}
                    className={cn(
                      "p-3.5 hover:bg-muted/30 transition-colors cursor-pointer",
                      active && "bg-primary/5",
                    )}
                    onClick={() => onSelect(item.id)}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 text-sm">
                          <span className="font-medium text-foreground truncate">
                            {item.student_name}
                          </span>
                          <span className="text-xs text-muted-foreground shrink-0">
                            {item.subject}
                          </span>
                        </div>
                        <div className="mt-1 text-sm text-foreground/80 truncate">
                          {item.question_title || item.question_ref}
                        </div>
                        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                          <span className="flex items-center gap-1">
                            <RefreshCcw className="w-3 h-3" />
                            {t("grading.errorBook.recall.nextReview", {
                              date: formatReviewDate(item.next_review_at),
                            })}
                          </span>
                          <span>
                            {t("grading.errorBook.recall.reviewCount", {
                              count: item.review_count,
                            })}
                          </span>
                          <span>
                            {t("grading.errorBook.recall.intervalDays", {
                              days: item.interval_days,
                            })}
                          </span>
                          {overdue && (
                            <span className="px-1.5 py-0.5 rounded bg-red-500/10 text-red-600 border border-red-500/20 font-medium">
                              {t("grading.errorBook.recall.overdue")}
                            </span>
                          )}
                          {!overdue && dueToday && (
                            <span className="px-1.5 py-0.5 rounded bg-orange-500/10 text-orange-600 border border-orange-500/20 font-medium">
                              {t("grading.errorBook.recall.due")}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="mt-2 flex items-center gap-1.5">
                      <span className="text-xs text-muted-foreground mr-1">
                        {t("grading.errorBook.recall.checkIn")}:
                      </span>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="h-7 px-2.5 text-xs"
                        disabled={checkInMutation.isPending}
                        onClick={(e) => {
                          e.stopPropagation();
                          checkInMutation.mutate({
                            id: item.id,
                            result: "again",
                          });
                        }}
                      >
                        {t("grading.errorBook.recall.resultAgain")}
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="h-7 px-2.5 text-xs"
                        disabled={checkInMutation.isPending}
                        onClick={(e) => {
                          e.stopPropagation();
                          checkInMutation.mutate({
                            id: item.id,
                            result: "good",
                          });
                        }}
                      >
                        {t("grading.errorBook.recall.resultGood")}
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="h-7 px-2.5 text-xs"
                        disabled={checkInMutation.isPending}
                        onClick={(e) => {
                          e.stopPropagation();
                          checkInMutation.mutate({
                            id: item.id,
                            result: "easy",
                          });
                        }}
                      >
                        {t("grading.errorBook.recall.resultEasy")}
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

interface VariantQuestionCardProps {
  selectedId: string | null;
  onMastered: () => void;
}

function VariantQuestionCard({
  selectedId,
  onMastered,
}: VariantQuestionCardProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["wrong-question-variants", selectedId],
    queryFn: () => getWrongQuestionVariants(selectedId as string),
    enabled: !!selectedId,
  });
  const variants: WrongQuestionReviewItem[] = data?.data ?? [];

  const masteredMutation = useMutation({
    mutationFn: (id: string) => submitWrongQuestionReview(id, "easy"),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["wrong-question-variants", selectedId],
      });
      toast.success(t("grading.errorBook.variants.masteredDone"));
      onMastered();
    },
    onError: (err: any) =>
      toast.error(t("grading.errorBook.variants.masterFailed"), {
        description: err?.message,
      }),
  });

  return (
    <Card className="flex flex-col overflow-hidden border-border/50 shadow-sm">
      <CardHeader className="pb-3 shrink-0 bg-muted/10 border-b border-border/50">
        <CardTitle className="text-base flex items-center gap-2">
          <Lightbulb className="w-5 h-5 text-amber-500" />
          {t("grading.errorBook.variants.title")}
        </CardTitle>
        <CardDescription>
          {t("grading.errorBook.variants.subtitle")}
        </CardDescription>
      </CardHeader>
      <CardContent className="p-0 flex-1 overflow-hidden">
        <ScrollArea className="h-full max-h-[340px]">
          {!selectedId ? (
            <div className="flex flex-col items-center justify-center min-h-[180px] gap-2 text-center text-sm text-muted-foreground p-4">
              <Lightbulb className="h-8 w-8 text-muted-foreground/40" />
              {t("grading.errorBook.variants.selectFirst")}
            </div>
          ) : isLoading ? (
            <div className="flex flex-col items-center justify-center min-h-[180px] gap-3 text-muted-foreground text-sm">
              <Loader2 className="w-6 h-6 animate-spin text-primary/50" />
              {t("grading.errorBook.loading")}
            </div>
          ) : isError ? (
            <div className="flex flex-col items-center justify-center min-h-[180px] gap-2 text-center text-sm text-muted-foreground p-4">
              {t("grading.errorBook.variants.loadFailed")}
            </div>
          ) : variants.length === 0 ? (
            <div className="flex flex-col items-center justify-center min-h-[180px] gap-2 text-center text-sm text-muted-foreground p-4">
              <Lightbulb className="h-8 w-8 text-muted-foreground/40" />
              {t("grading.errorBook.variants.noData")}
            </div>
          ) : (
            <div className="divide-y divide-border/40">
              {variants.map((v) => (
                <div
                  key={v.id}
                  className="p-3.5 hover:bg-muted/30 transition-colors"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 text-sm">
                        <span className="font-medium text-foreground truncate">
                          {v.question_title || v.question_ref}
                        </span>
                        <span className="text-xs text-muted-foreground shrink-0">
                          {v.error_type}
                        </span>
                      </div>
                      {v.reason && (
                        <div className="mt-1.5 inline-flex items-start gap-1 rounded bg-amber-50/70 px-1.5 py-0.5 text-xs text-amber-800">
                          <Lightbulb className="w-3 h-3 shrink-0 mt-0.5" />
                          <span>{v.reason}</span>
                        </div>
                      )}
                      <div className="mt-1 text-xs text-muted-foreground">
                        {t("grading.errorBook.variants.ofStudent", {
                          name: v.student_name,
                          subject: v.subject,
                        })}
                      </div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {t("grading.errorBook.recall.nextReview", {
                          date: formatReviewDate(v.next_review_at),
                        })}
                      </div>
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="h-7 px-2.5 text-xs shrink-0"
                      disabled={masteredMutation.isPending}
                      onClick={() => masteredMutation.mutate(v.id)}
                    >
                      {t("grading.errorBook.variants.mastered")}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

export function ErrorBookDetail({ folderName, onBack }: ErrorBookDetailProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const classId = extractClassId(folderName);
  const { schoolLevel, selectedSubject } = useGlobalFilters();
  const knowledgeGraph = useMemo(
    () =>
      schoolLevel && selectedSubject
        ? getKnowledgeGraph(schoolLevel, selectedSubject)
        : null,
    [schoolLevel, selectedSubject],
  );
  const [expandedLectureKp, setExpandedLectureKp] = useState<
    Record<string, string | null>
  >({});
  const handleToggleLecture = useCallback((key: string, kp: string) => {
    setExpandedLectureKp((prev) => ({
      ...prev,
      [key]: prev[key] === kp ? null : kp,
    }));
  }, []);
  const [selectedReviewId, setSelectedReviewId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [questions, setQuestions] = useState<QuestionStat[]>([]);
  const [questionPages, setQuestionPages] = useState<QuestionPageStat[]>([]);
  const [activeQuestionPage, setActiveQuestionPage] = useState<number | null>(
    null,
  );
  const [students, setStudents] = useState<StudentStat[]>([]);

  const displayFolderName = useCallback((name: string) => {
    const s = String(name || "");
    if (s.startsWith("cls_")) {
      const i = s.indexOf("__");
      if (i > 4 && i + 2 < s.length) return s.slice(i + 2);
    }
    return s;
  }, []);

  useEffect(() => {
    let mounted = true;
    const loadDetail = async () => {
      setLoading(true);
      try {
        const res = await getErrorBookFolderDetail(folderName);
        if (res.ok && mounted) {
          const processQuestion = (q: RawQuestionStat): QuestionStat => {
            const total = q.correct + q.wrong + q.blank;
            const errorCount = q.wrong + q.blank;
            const errorRate = total > 0 ? (errorCount / total) * 100 : 0;
            const subItems =
              q.subItems && q.subItems.length > 0
                ? q.subItems.map(processQuestion)
                : undefined;
            return { ...q, total, errorRate, subItems };
          };

          const processedQuestions = (res.questions || []).map(processQuestion);
          processedQuestions.sort((a, b) => b.errorRate - a.errorRate);
          setQuestions(processedQuestions);

          const processedQuestionPages: QuestionPageStat[] = (
            res.question_pages || []
          )
            .map((page) => {
              const pageQuestions = (page.questions || []).map(processQuestion);
              pageQuestions.sort((a, b) => b.errorRate - a.errorRate);
              return {
                page_no: Number(page.page_no || 1),
                label:
                  page.label ||
                  t("grading.errorBook.pageLabel", { no: page.page_no || 1 }),
                questions: pageQuestions,
              };
            })
            .filter((page) => page.questions.length > 0)
            .sort((a, b) => a.page_no - b.page_no);
          setQuestionPages(processedQuestionPages);
          setActiveQuestionPage((prev) => {
            if (processedQuestionPages.some((page) => page.page_no === prev))
              return prev;
            return processedQuestionPages[0]?.page_no ?? null;
          });

          setStudents(res.students || []);
        }
      } catch (error) {
        console.error("Failed to load error book detail:", error);
      } finally {
        if (mounted) setLoading(false);
      }
    };

    loadDetail();
    return () => {
      mounted = false;
    };
  }, [folderName, t]);

  const ERROR_LEVEL_STYLES = {
    high: {
      text: "text-red-500",
      badge: "text-red-500 bg-red-50 border-red-200",
    },
    medium: {
      text: "text-orange-500",
      badge: "text-orange-500 bg-orange-50 border-orange-200",
    },
    low: {
      text: "text-green-600",
      badge: "text-green-600 bg-green-50 border-green-200",
    },
  } as const;

  const getErrorLevel = (rate: number): keyof typeof ERROR_LEVEL_STYLES => {
    if (rate >= 60) return "high";
    if (rate >= 30) return "medium";
    return "low";
  };

  const getErrorLevelColor = (rate: number) =>
    ERROR_LEVEL_STYLES[getErrorLevel(rate)].badge;
  const getErrorLevelTextColor = (rate: number) =>
    ERROR_LEVEL_STYLES[getErrorLevel(rate)].text;

  const getProgressColor = (rate: number) => {
    if (rate >= 60) return "bg-red-500";
    if (rate >= 30) return "bg-orange-500";
    return "bg-green-500";
  };

  const selectedQuestionPage =
    questionPages.find((page) => page.page_no === activeQuestionPage) ??
    questionPages[0] ??
    null;
  const highFreqQuestions = selectedQuestionPage?.questions ?? questions;
  const hasDetailData =
    questionPages.some((page) => page.questions.length > 0) ||
    questions.length > 0 ||
    students.length > 0;

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300 h-full flex flex-col">
      <div className="shrink-0 flex items-center gap-4">
        <Button variant="ghost" size="sm" onClick={onBack} className="gap-2">
          <ArrowLeft className="w-4 h-4" /> {t("common.backToList")}
        </Button>
        <div>
          <h2 className="text-xl font-bold text-foreground flex items-center gap-2">
            <Target className="w-5 h-5 text-primary" />
            {displayFolderName(folderName)}
            {t("grading.errorBook.detailSuffix")}
          </h2>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 shrink-0">
        <RecallPlanCard
          classId={classId}
          selectedId={selectedReviewId}
          onSelect={setSelectedReviewId}
        />
        <VariantQuestionCard
          selectedId={selectedReviewId}
          onMastered={() =>
            queryClient.invalidateQueries({
              queryKey: ["wrong-question-due", classId],
            })
          }
        />
      </div>

      {loading ? (
        <div className="flex-1 flex flex-col items-center justify-center min-h-[400px]">
          <Loader2 className="w-8 h-8 animate-spin text-primary/50 mb-4" />
          <p className="text-sm text-muted-foreground animate-pulse">
            {t("grading.errorBook.analyzing")}
          </p>
        </div>
      ) : (
        <div className="flex-1 min-h-0">
          {hasDetailData ? (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 min-h-0">
              <Card className="flex flex-col overflow-hidden border-border/50 shadow-sm">
                <CardHeader className="pb-3 shrink-0 bg-muted/10 border-b border-border/50">
                  <CardTitle className="text-base flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5 text-orange-500" />
                    {t("grading.errorBook.highFreqTitle")}
                  </CardTitle>
                  <CardDescription>
                    {selectedQuestionPage
                      ? t("grading.errorBook.highFreqDescPage", {
                          label: selectedQuestionPage.label,
                        })
                      : t("grading.errorBook.highFreqDescAll")}
                  </CardDescription>
                  {questionPages.length > 1 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {questionPages.map((page) => {
                        const active =
                          page.page_no === selectedQuestionPage?.page_no;
                        const wrongCount = page.questions.reduce(
                          (sum, q) => sum + q.wrong + q.blank,
                          0,
                        );
                        return (
                          <Button
                            key={page.page_no}
                            type="button"
                            variant={active ? "default" : "outline"}
                            size="sm"
                            className={cn(
                              "h-8 rounded-full px-3 text-xs",
                              active && "shadow-sm",
                            )}
                            onClick={() => setActiveQuestionPage(page.page_no)}
                          >
                            {page.label}
                            <span
                              className={cn(
                                "ml-1.5 text-[11px]",
                                active
                                  ? "text-primary-foreground/80"
                                  : "text-muted-foreground",
                              )}
                            >
                              {t("grading.errorBook.wrongBlankCount", {
                                count: wrongCount,
                              })}
                            </span>
                          </Button>
                        );
                      })}
                    </div>
                  )}
                </CardHeader>
                <CardContent className="p-0 flex-1 overflow-hidden">
                  <ScrollArea className="h-full">
                    {highFreqQuestions.length === 0 ? (
                      <div className="p-8 text-center text-muted-foreground text-sm">
                        {t("grading.errorBook.noQuestionData")}
                      </div>
                    ) : (
                      <div className="divide-y divide-border/40">
                        <Accordion type="multiple" className="w-full">
                          {highFreqQuestions.map((q, idx) => {
                            const pageKey =
                              selectedQuestionPage?.page_no ?? "all";
                            const parentKey = `${pageKey}-${q.title}`;
                            return (
                              <AccordionItem
                                key={parentKey}
                                value={parentKey}
                                className="border-none"
                              >
                                <div className="hover:bg-muted/30 transition-colors">
                                  <AccordionTrigger className="p-4 hover:no-underline [&[data-state=open]_.chevron]:rotate-180 w-full group">
                                    <div className="flex flex-col w-full">
                                      <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-3">
                                          <span className="w-6 h-6 rounded-full bg-primary/10 text-primary flex items-center justify-center text-xs font-bold shrink-0">
                                            {idx + 1}
                                          </span>
                                          <span className="font-medium text-foreground flex items-center gap-2">
                                            {q.title}
                                            {q.errorRate === 0 && (
                                              <span className="px-2 py-0.5 rounded text-xs font-bold bg-green-500/10 text-green-600 border border-green-500/20">
                                                {t("grading.status.allCorrect")}
                                              </span>
                                            )}
                                            {q.subItems &&
                                              q.subItems.length > 0 && (
                                                <span className="text-xs text-muted-foreground font-normal bg-muted/50 px-1.5 py-0.5 rounded flex items-center gap-1 group-hover:text-primary transition-colors">
                                                  {t(
                                                    "grading.ai.subAreasCount",
                                                    {
                                                      count: q.subItems.length,
                                                    },
                                                  )}
                                                  <ChevronDown className="h-3 w-3 shrink-0 transition-transform duration-200 chevron" />
                                                </span>
                                              )}
                                            {(!q.subItems ||
                                              q.subItems.length === 0) && (
                                              <span className="text-xs text-muted-foreground font-normal bg-muted/50 px-1.5 py-0.5 rounded flex items-center gap-1 group-hover:text-primary transition-colors">
                                                {t(
                                                  "grading.ai.viewWrongDetail",
                                                )}
                                                <ChevronDown className="h-3 w-3 shrink-0 transition-transform duration-200 chevron" />
                                              </span>
                                            )}
                                          </span>
                                        </div>
                                      </div>
                                    </div>
                                  </AccordionTrigger>

                                  <AccordionContent className="pt-0 pb-4 pl-9 pr-4">
                                    <KnowledgePointChips
                                      kps={q.knowledge_points}
                                      questionKey={parentKey}
                                      activeKp={expandedLectureKp[parentKey]}
                                      onToggle={handleToggleLecture}
                                    />
                                    {expandedLectureKp[parentKey] && (
                                      <KnowledgeLectureCard
                                        kp={expandedLectureKp[parentKey]!}
                                        graph={knowledgeGraph}
                                        className="mt-3"
                                      />
                                    )}
                                    {(!q.subItems ||
                                      q.subItems.length === 0) && (
                                      <div className="pl-3 border-l-2 border-muted space-y-4">
                                        <div className="space-y-2">
                                          <div className="flex items-center justify-between">
                                            <span className="text-sm font-medium text-foreground/80">
                                              {t(
                                                "grading.errorBook.overallStats",
                                              )}
                                            </span>
                                            <div
                                              className={cn(
                                                "px-2 py-0.5 rounded text-xs font-bold border",
                                                getErrorLevelColor(q.errorRate),
                                              )}
                                            >
                                              {t(
                                                "grading.errorBook.errorRate",
                                                {
                                                  rate: q.errorRate.toFixed(1),
                                                },
                                              )}
                                            </div>
                                          </div>
                                          <div className="flex items-center gap-4 text-xs text-muted-foreground mb-2">
                                            <span className="flex items-center gap-1 text-green-600">
                                              <CheckCircle2 className="w-3.5 h-3.5" />{" "}
                                              {t("grading.ai.correctPeople", {
                                                count: q.correct,
                                              })}
                                            </span>
                                            <span className="flex items-center gap-1 text-red-500">
                                              <XCircle className="w-3.5 h-3.5" />{" "}
                                              {t("grading.ai.wrongPeople", {
                                                count: q.wrong + q.blank,
                                              })}
                                            </span>
                                          </div>
                                          <div>
                                            <Progress
                                              value={q.errorRate}
                                              className="h-1.5"
                                            />
                                          </div>
                                        </div>

                                        {q.wrong_students &&
                                          q.wrong_students.length > 0 && (
                                            <div>
                                              <div className="text-xs text-red-500 flex items-center gap-1.5 mb-2 font-medium">
                                                <Users className="w-3.5 h-3.5" />
                                                {t(
                                                  "grading.errorBook.wrongStudents",
                                                  {
                                                    count:
                                                      q.wrong_students.length,
                                                  },
                                                )}
                                              </div>
                                              <ScrollArea className="w-full whitespace-nowrap rounded-md">
                                                <div className="flex w-max space-x-1.5 pb-2">
                                                  {q.wrong_students.map(
                                                    (student) => (
                                                      <span
                                                        key={student}
                                                        className="px-2 py-1 bg-red-50/80 text-red-600 border border-red-100 rounded text-[11px]"
                                                        title={student}
                                                      >
                                                        {paperBoxName(student)}
                                                      </span>
                                                    ),
                                                  )}
                                                </div>
                                              </ScrollArea>
                                            </div>
                                          )}
                                      </div>
                                    )}

                                    {q.subItems && q.subItems.length > 0 && (
                                      <div className="space-y-4 pl-4 border-l-2 border-muted mt-2">
                                        {q.subItems.map((sub) => {
                                          const subKey = `${parentKey}-${sub.title}`;
                                          return (
                                            <div
                                              key={subKey}
                                              className="space-y-2"
                                            >
                                              <KnowledgePointChips
                                                kps={sub.knowledge_points}
                                                questionKey={subKey}
                                                activeKp={
                                                  expandedLectureKp[subKey]
                                                }
                                                onToggle={handleToggleLecture}
                                              />
                                              {expandedLectureKp[subKey] && (
                                                <KnowledgeLectureCard
                                                  kp={
                                                    expandedLectureKp[subKey]!
                                                  }
                                                  graph={knowledgeGraph}
                                                  className="mt-2"
                                                />
                                              )}
                                              <div className="flex items-center justify-between">
                                                <span className="text-sm font-medium text-foreground/80">
                                                  {sub.title}
                                                </span>
                                                <span
                                                  className={cn(
                                                    "text-xs font-semibold",
                                                    getErrorLevelTextColor(
                                                      sub.errorRate,
                                                    ),
                                                  )}
                                                >
                                                  {sub.errorRate.toFixed(1)}%
                                                </span>
                                              </div>
                                              <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                                                <span className="text-green-600">
                                                  {t("grading.ai.subCorrect", {
                                                    count: sub.correct,
                                                  })}
                                                </span>
                                                <span className="text-red-500">
                                                  {t("grading.ai.subWrong", {
                                                    count:
                                                      sub.wrong + sub.blank,
                                                  })}
                                                </span>
                                              </div>
                                              <Progress
                                                value={sub.errorRate}
                                                className="h-1"
                                              />

                                              {sub.wrong_students &&
                                                sub.wrong_students.length >
                                                  0 && (
                                                  <div className="mt-2">
                                                    <div className="text-[11px] text-red-500 flex items-center gap-1.5 mb-1.5">
                                                      <Users className="w-3 h-3" />
                                                      {t(
                                                        "grading.errorBook.wrongStudentsShort",
                                                        {
                                                          count:
                                                            sub.wrong_students
                                                              .length,
                                                        },
                                                      )}
                                                    </div>
                                                    <ScrollArea className="w-full whitespace-nowrap rounded-md">
                                                      <div className="flex w-max space-x-1.5 pb-1">
                                                        {sub.wrong_students.map(
                                                          (student) => (
                                                            <span
                                                              key={student}
                                                              className="px-1.5 py-0.5 bg-red-50/80 text-red-600 border border-red-100 rounded text-[10px]"
                                                              title={student}
                                                            >
                                                              {paperBoxName(
                                                                student,
                                                              )}
                                                            </span>
                                                          ),
                                                        )}
                                                      </div>
                                                    </ScrollArea>
                                                  </div>
                                                )}
                                            </div>
                                          );
                                        })}
                                      </div>
                                    )}
                                  </AccordionContent>
                                </div>
                              </AccordionItem>
                            );
                          })}
                        </Accordion>
                      </div>
                    )}
                  </ScrollArea>
                </CardContent>
              </Card>

              <Card className="flex flex-col overflow-hidden border-border/50 shadow-sm">
                <CardHeader className="pb-3 shrink-0 bg-muted/10 border-b border-border/50">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Users className="w-5 h-5 text-blue-500" />
                    {t("grading.errorBook.studentDetailTitle")}
                  </CardTitle>
                  <CardDescription>
                    {t("grading.errorBook.studentDetailDesc")}
                  </CardDescription>
                </CardHeader>
                <CardContent className="p-0 flex-1 overflow-hidden">
                  <ScrollArea className="h-full">
                    {students.length === 0 ? (
                      <div className="p-8 text-center text-muted-foreground text-sm">
                        {t("grading.errorBook.noStudentData")}
                      </div>
                    ) : (
                      <div className="divide-y divide-border/40">
                        {students.map((s, idx) => (
                          <div
                            key={s.filename}
                            className="p-4 hover:bg-muted/30 transition-colors"
                          >
                            <div className="mb-2 flex items-center justify-between gap-3">
                              <div className="flex min-w-0 items-center gap-3">
                                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">
                                  {idx + 1}
                                </span>
                                <span
                                  className="truncate font-medium text-foreground"
                                  title={s.filename}
                                >
                                  {paperBoxName(s.filename)}
                                </span>
                              </div>
                              <div className="flex shrink-0 items-center gap-3 text-sm">
                                <span className="text-red-500 font-semibold">
                                  {t("grading.errorBook.wrongN", {
                                    count: s.wrong_count,
                                  })}
                                </span>
                                <span className="text-green-600">
                                  {t("grading.errorBook.correctN", {
                                    count: s.correct_count,
                                  })}
                                </span>
                                <div
                                  className={cn(
                                    "flex min-w-[72px] shrink-0 flex-col items-center justify-center rounded-xl px-3 py-2 text-center shadow-sm",
                                    s.score_total !== undefined &&
                                      s.score_total !== null
                                      ? "bg-primary text-primary-foreground"
                                      : "bg-muted text-muted-foreground",
                                  )}
                                >
                                  <span className="text-[11px] font-medium leading-none opacity-90">
                                    {t("grading.errorBook.paperScore")}
                                  </span>
                                  <span className="mt-1 text-lg font-bold leading-none">
                                    {s.score_total !== undefined &&
                                    s.score_total !== null
                                      ? s.score_total
                                      : "--"}
                                  </span>
                                </div>
                              </div>
                            </div>
                            {s.wrong_questions &&
                              s.wrong_questions.length > 0 && (
                                <div className="mt-2 flex flex-wrap gap-1.5">
                                  {s.wrong_questions
                                    .filter((wq) => {
                                      if (!wq.includes("-作答区")) {
                                        const hasDetailedSub =
                                          s.wrong_questions.some((other) =>
                                            other.startsWith(wq + "-作答区"),
                                          );
                                        return !hasDetailedSub;
                                      }
                                      return true;
                                    })
                                    .map((wq) => (
                                      <span
                                        key={wq}
                                        className="px-1.5 py-0.5 bg-red-50 text-red-600 border border-red-100 rounded text-[11px]"
                                      >
                                        {wq}
                                      </span>
                                    ))}
                                </div>
                              )}
                          </div>
                        ))}
                      </div>
                    )}
                  </ScrollArea>
                </CardContent>
              </Card>
            </div>
          ) : (
            <Card className="border-border/50 shadow-sm">
              <CardContent className="flex min-h-[280px] flex-col items-center justify-center gap-3 text-center">
                <FileStack className="h-10 w-10 text-muted-foreground/40" />
                <div className="text-lg font-semibold text-foreground">
                  {t("grading.errorBook.noSmartData")}
                </div>
                <div className="max-w-md text-sm text-muted-foreground">
                  {t("grading.errorBook.noSmartHint")}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
