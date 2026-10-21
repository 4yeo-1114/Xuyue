import { useState, useMemo, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSubjectName } from "@/i18n";
import { useClassLatestWrongQuestions } from "@/hooks/useWrongQuestions";
import type { WrongQuestionQueryPair } from "@/hooks/useWrongQuestions";
import { useStudents } from "@/hooks/useStudents";
import {
  getBanditWrongQuestions,
  reportBanditWrongQuestionClick,
  pickSessionFolder,
} from "@/services/banditApi";
import type { BanditRecommendItem, QuestionSource } from "@/services/banditApi";
import { AutoVariantsCard } from "./AutoVariantsCard";
import { QUESTION_TYPE_OPTIONS, splitTopics } from "@/lib/aiQuestionTypes";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  BookX,
  Search,
  AlertCircle,
  RefreshCw,
  Sparkles,
  Loader2,
  Lightbulb,
  ChevronDown,
  Check,
  Info,
  Settings2,
} from "lucide-react";
import { cn } from "@/lib/utils";

const subjectOptions = [
  "语文",
  "数学",
  "英语",
  "科学",
  "物理",
  "化学",
  "生物",
  "历史",
  "地理",
  "政治",
];

interface WrongQuestionsTabProps {
  classId: string;
}

/** bandit 变式推荐面板：按（学生, 学科, 错题题干）取变式题推荐，点击变式上报 reward=1。
 *  题源可选：ai=AI 生成（默认，可选题型/知识点）| bank=题库。
 *  hint=该错题题干原文——AI 围绕这道错题举一反三（不传则退化为按薄弱点出题）。 */
function VariantRecommendPanel({
  studentId,
  subject,
  hint,
}: {
  studentId: string;
  subject: string;
  hint?: string;
}) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [clickedIds, setClickedIds] = useState<Set<string>>(new Set());
  // 题源：ai=AI 生成（默认）；bank=题库（没接题库时给明确提示）
  const [source, setSource] = useState<QuestionSource>("ai");
  const [showOpts, setShowOpts] = useState(false);
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [topicText, setTopicText] = useState("");
  const [appliedTopics, setAppliedTopics] = useState<string[]>([]);

  const applyOpts = () => setAppliedTopics(splitTopics(topicText));

  const { data, isLoading, isFetching, isError, refetch } = useQuery({
    queryKey: [
      "bandit-recommend",
      studentId,
      subject,
      source,
      selectedTypes.join(","),
      appliedTopics.join(","),
      hint || "",
    ],
    queryFn: () =>
      getBanditWrongQuestions(studentId, subject, 5, {
        source,
        types: selectedTypes,
        topics: appliedTopics,
        hint: hint || undefined,
      }),
  });

  const clickMutation = useMutation({
    mutationFn: (item: BanditRecommendItem) =>
      reportBanditWrongQuestionClick(
        studentId,
        subject,
        item.reason.kp_name,
        1,
      ),
    onSuccess: (_data, item) => {
      setClickedIds((prev) => new Set(prev).add(item.question.id));
      queryClient.invalidateQueries({
        queryKey: ["bandit-recommend", studentId, subject],
      });
      toast.success(t("classDetail.变式推荐上报成功"));
    },
    onError: () => toast.error(t("classDetail.变式推荐上报失败")),
  });

  const items = data?.items ?? [];
  const mode = data?.mode;

  const modeLabel = (m?: string) =>
    m === "explore"
      ? t("classDetail.recommendMode.explore")
      : m === "exploit"
        ? t("classDetail.recommendMode.exploit")
        : m === "fallback"
          ? t("classDetail.recommendMode.fallback")
          : m === "ai"
            ? t("classDetail.recommendMode.ai")
            : m;

  return (
    <div className="mt-2 rounded-lg border border-border/60 bg-muted/20 p-3 space-y-2">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-1.5 text-xs font-medium text-foreground">
          <Sparkles className="w-3.5 h-3.5 text-amber-500" />
          {t("classDetail.变式推荐")}
          {mode && (
            <Badge variant="outline" className="text-[10px]">
              {modeLabel(mode)}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <Select
            value={source}
            onValueChange={(v) => setSource(v as QuestionSource)}
          >
            <SelectTrigger className="h-7 w-[100px] text-xs">
              <SelectValue placeholder={t("smartGen.aiSource.label")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ai">{t("smartGen.aiSource.ai")}</SelectItem>
              <SelectItem value="bank">{t("smartGen.aiSource.bank")}</SelectItem>
            </SelectContent>
          </Select>
          {source === "ai" && (
            <>
              <Button
                size="sm"
                variant="outline"
                className="h-7 gap-1 px-2 text-xs"
                onClick={() => setShowOpts((v) => !v)}
              >
                <Settings2 className="w-3 h-3" />
                {t("smartGen.aiSource.settings")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-7 gap-1 px-2 text-xs"
                disabled={isFetching || clickMutation.isPending}
                onClick={() => refetch()}
              >
                {isFetching ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <RefreshCw className="w-3 h-3" />
                )}
                {t("smartGen.aiSource.regenerate")}
              </Button>
            </>
          )}
        </div>
      </div>

      {source === "ai" && showOpts && (
        <div className="rounded-md border border-border/50 bg-card/60 p-2 space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="w-14 shrink-0 text-xs font-medium">
              {t("smartGen.aiSource.topicsLabel")}
            </span>
            <Input
              className="h-7 text-xs"
              placeholder={t("smartGen.aiSource.topicsPlaceholder")}
              value={topicText}
              onChange={(e) => setTopicText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") applyOpts();
              }}
            />
            <Button
              size="sm"
              variant="outline"
              className="h-7 px-2 text-xs"
              onClick={applyOpts}
            >
              {t("smartGen.aiSource.apply")}
            </Button>
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="w-14 shrink-0 text-xs font-medium">
              {t("smartGen.aiSource.typesLabel")}
            </span>
            {QUESTION_TYPE_OPTIONS.map((o) => {
              const active = selectedTypes.includes(o.value);
              return (
                <Button
                  key={o.value}
                  size="sm"
                  variant={active ? "default" : "outline"}
                  className="h-6 px-2 text-xs"
                  onClick={() =>
                    setSelectedTypes((prev) =>
                      active
                        ? prev.filter((v) => v !== o.value)
                        : [...prev, o.value],
                    )
                  }
                >
                  {o.label}
                </Button>
              );
            })}
          </div>
        </div>
      )}

      {source === "bank" ? (
        <div className="rounded-md border border-dashed border-amber-500/50 bg-amber-500/5 px-3 py-5 text-center text-xs text-amber-600">
          {t("smartGen.aiSource.bankUnavailable")}
          <div className="mt-1 text-muted-foreground">
            {t("smartGen.aiSource.bankHint")}
          </div>
        </div>
      ) : isLoading || isFetching ? (
        <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin text-primary/60" />
          {isFetching && !isLoading
            ? t("classDetail.变式推荐生成中")
            : t("common.loading")}
        </div>
      ) : isError ? (
        <div className="flex flex-col items-center gap-2 py-4 text-center">
          <p className="text-sm text-muted-foreground">
            {t("classDetail.变式推荐加载失败")}
          </p>
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5"
            onClick={() => refetch()}
          >
            <RefreshCw className="w-3.5 h-3.5" />
            {t("wuyu.retry")}
          </Button>
        </div>
      ) : items.length === 0 ? (
        <p className="py-4 text-center text-sm text-muted-foreground">
          {t("classDetail.暂无变式推荐")}
        </p>
      ) : (
        <div className="space-y-2">
          {items.map((item) => {
            const isClicked = clickedIds.has(item.question.id);
            return (
              <button
                key={item.question.id}
                type="button"
                disabled={clickMutation.isPending}
                onClick={() => clickMutation.mutate(item)}
                className={cn(
                  "w-full text-left rounded-md border border-border/50 bg-card p-2.5 hover:bg-primary/5 transition-colors",
                  isClicked && "opacity-70",
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm leading-relaxed whitespace-pre-line">
                    {item.question.question}
                  </p>
                  <Check
                    className={cn(
                      "w-4 h-4 shrink-0 mt-0.5",
                      isClicked ? "text-primary" : "text-transparent",
                    )}
                  />
                </div>
                <div className="mt-1.5 flex items-center gap-2 flex-wrap text-xs text-muted-foreground">
                  <Badge variant="secondary" className="text-[10px]">
                    {item.reason.kp_name}
                  </Badge>
                  <span>
                    {t("classDetail.推荐置信度", {
                      value: Math.round(item.reason.confidence * 100),
                    })}
                  </span>
                  {item.reason.error_count > 0 && (
                    <span>
                      {t("classDetail.错题次数", {
                        count: item.reason.error_count,
                      })}
                    </span>
                  )}
                </div>
                <div className="mt-2 rounded-md border border-primary/20 bg-primary/5 p-2">
                  <div className="flex items-center gap-1 text-[11px] font-medium text-primary">
                    <Info className="w-3.5 h-3.5" />
                    {t("classDetail.推荐依据")}
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
                    {item.reason.reason_text || t("classDetail.暂无变式推荐")}
                  </p>
                  {item.reason.error_types &&
                    item.reason.error_types.length > 0 && (
                      <div className="mt-1.5 flex items-center gap-1.5 flex-wrap">
                        <span className="text-[11px] text-muted-foreground">
                          {t("classDetail.错因")}：
                        </span>
                        {item.reason.error_types.map((et) => (
                          <Badge
                            key={et}
                            variant="secondary"
                            className="text-[10px]"
                          >
                            {et}
                          </Badge>
                        ))}
                      </div>
                    )}
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function WrongQuestionsTab({ classId }: WrongQuestionsTabProps) {
  const { t, locale } = useLocale();

  const [filterSubject, setFilterSubject] = useState<string>("all");
  const [filterStudent, setFilterStudent] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data: students = [] } = useStudents(classId);

  // /latest 按（学生, 科目）返回最近一场考试错题，班级视角需逐对查询合并；
  // 「全部学生 × 全部学科」对逐学生+逐学科来说请求过多，引导用户收窄范围。
  const tooManyPairs = filterStudent === "all" && filterSubject === "all";

  // 深链/默认进入「全部学生 × 全部学科」是空态死路：学生列表就绪后自动收窄到第一个学生，
  // 让错题卡片与「变式推荐」直接可见（用户仍可手动切换学生/学科）。
  useEffect(() => {
    if (filterStudent === "all" && filterSubject === "all" && students.length > 0) {
      setFilterStudent(students[0].id);
    }
  }, [students, filterStudent, filterSubject]);

  const pairs: WrongQuestionQueryPair[] = useMemo(() => {
    const targetStudents =
      filterStudent === "all"
        ? students
        : students.filter((s) => s.id === filterStudent);
    const subjects = filterSubject === "all" ? subjectOptions : [filterSubject];
    return targetStudents.flatMap((st) =>
      subjects.map((sub) => ({
        studentId: st.id,
        studentName: st.name,
        subject: sub,
      })),
    );
  }, [students, filterStudent, filterSubject]);

  const {
    data: items = [],
    isLoading,
    isError,
    refetch,
  } = useClassLatestWrongQuestions(
    tooManyPairs ? undefined : classId,
    tooManyPairs ? [] : pairs,
  );

  const filtered = items.filter(
    (q) =>
      !search ||
      (q.title || "").includes(search) ||
      q.student_name.includes(search) ||
      q.subject.includes(search),
  );

  // 本场自动配套练习：classId + 错题列表里的考试名 → folder_safe
  const sessionFolder = useMemo(
    () => pickSessionFolder(classId, items),
    [classId, items],
  );

  return (
    <div className="space-y-4">
      <AutoVariantsCard folder={sessionFolder} />
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative w-64">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder={t("classDetail.搜索错题")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>
        <Select value={filterSubject} onValueChange={setFilterSubject}>
          <SelectTrigger className="w-[120px]">
            <SelectValue placeholder={t("classDetail.全部学科")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("classDetail.全部学科")}</SelectItem>
            {subjectOptions.map((s) => (
              <SelectItem key={s} value={s}>
                {translateSubjectName(locale, s)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={filterStudent} onValueChange={setFilterStudent}>
          <SelectTrigger className="w-[120px]">
            <SelectValue placeholder={t("classDetail.全部学生")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("classDetail.全部学生")}</SelectItem>
            {students.map((s) => (
              <SelectItem key={s.id} value={s.id}>
                {s.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {tooManyPairs ? (
        <div className="flex flex-col items-center justify-center h-[260px] rounded-lg border border-dashed bg-muted/20 text-center">
          <BookX className="w-10 h-10 text-muted-foreground/40 mb-3" />
          <p className="text-sm font-medium text-foreground mb-1">
            {t("classDetail.请选择学科或学生查看错题")}
          </p>
        </div>
      ) : isLoading ? (
        <p className="text-center py-8 text-muted-foreground">
          {t("common.loading")}
        </p>
      ) : isError ? (
        <div className="flex flex-col items-center justify-center h-[300px] rounded-lg border border-dashed bg-muted/20 text-center">
          <AlertCircle className="w-10 h-10 text-destructive/60 mb-3" />
          <p className="text-sm font-medium text-foreground mb-1">
            {t("classDetail.wrongQuestionsLoadFailed")}
          </p>
          <p className="text-xs text-muted-foreground mb-4">
            {t("classDetail.checkNetworkAndRetry")}
          </p>
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5"
            onClick={() => refetch()}
          >
            <RefreshCw className="w-3.5 h-3.5" />
            {t("wuyu.retry")}
          </Button>
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-[300px] bg-card rounded-xl border border-border">
          <BookX className="w-10 h-10 text-muted-foreground/40 mb-2" />
          <p className="text-muted-foreground">
            {t("classDetail.noWrongQuestions")}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((q, idx) => {
            const cardKey = `${q.student_id}|${q.subject}|${idx}`;
            const isExpanded = expanded === cardKey;
            const date = q.created_at
              ? new Date(q.created_at).toLocaleDateString()
              : "";
            return (
              <div
                key={cardKey}
                className="p-4 bg-card rounded-xl border border-border space-y-2"
              >
                <div className="flex items-start justify-between gap-2 flex-wrap">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="px-2 py-0.5 rounded text-xs font-medium bg-primary/10 text-primary">
                      {translateSubjectName(locale, q.subject)}
                    </span>
                    <span className="text-sm text-muted-foreground">
                      {q.student_name}
                    </span>
                    {q.exam_name && (
                      <span className="text-xs text-muted-foreground">
                        {q.exam_name}
                      </span>
                    )}
                    {date && (
                      <span className="text-xs text-muted-foreground">
                        {date}
                      </span>
                    )}
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-1.5 shrink-0"
                    onClick={() => setExpanded(isExpanded ? null : cardKey)}
                  >
                    <Lightbulb className="w-3.5 h-3.5 text-amber-500" />
                    {t("classDetail.变式推荐")}
                    <ChevronDown
                      className={cn(
                        "w-3.5 h-3.5 transition-transform",
                        isExpanded && "rotate-180",
                      )}
                    />
                  </Button>
                </div>
                <p className="text-sm">{q.title || t("classDetail.unnamedQuestion")}</p>
                {q.image_url && (
                  <img
                    src={q.image_url}
                    alt={q.title}
                    className="max-h-48 w-full rounded-md border border-border/60 bg-white object-contain"
                    loading="lazy"
                  />
                )}
                {q.knowledge_point_name && (
                  <Badge variant="secondary" className="text-[10px] gap-1">
                    <Sparkles className="w-3 h-3" />
                    {t("classDetail.knowledgePoint")}: {q.knowledge_point_name}
                  </Badge>
                )}
                {isExpanded && (
                  <VariantRecommendPanel
                    studentId={q.student_id}
                    subject={q.subject}
                    hint={q.title || ""}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
