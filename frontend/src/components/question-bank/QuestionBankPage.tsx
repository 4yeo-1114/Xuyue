import { useState, useEffect, useMemo, useCallback } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import {
  BookCopy,
  Search,
  Loader2,
  ChevronLeft,
  ChevronRight,
  Inbox,
  PlugZap,
  Tags,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { useLocale } from "@/contexts/LocaleContext";
import {
  searchBankQuestions,
  getBankFilters,
  fetchQuestionTags,
  batchUpdateQuestionTags,
  type BankFilters,
  type BankQuestion,
  type QuestionTag,
  type QuestionTagPatch,
} from "@/services/questionBankApi";
import {
  TAG_DIFFICULTY_OPTIONS,
  questionTagKey,
  questionTagSource,
  filterQuestionsByTags,
  hasVisibleTags,
  type QuestionTagFilter,
} from "./questionTagUtils";
import { QuestionTagEditor } from "./QuestionTagEditor";

const PAGE_SIZE = 20;

/** 难度（1-5）→ 星级 */
const DIFFICULTY_STARS: Record<number, string> = {
  1: "★☆☆☆☆",
  2: "★★☆☆☆",
  3: "★★★☆☆",
  4: "★★★★☆",
  5: "★★★★★",
};

function difficultyLabel(d: number): string {
  return DIFFICULTY_STARS[d] ?? `难度 ${d}`;
}

/** 题干剥离 HTML 标签，取纯文本（题库题干可能含 <p> 等标签） */
function stripHtml(html: string): string {
  return html.replace(/<[^>]*>/g, "").replace(/&nbsp;/g, " ").trim();
}

/** 行上标签徽章（未打标不占位） */
function TagBadges({
  tag,
  onEdit,
}: {
  tag?: QuestionTag;
  onEdit: () => void;
}) {
  const { t } = useLocale();
  if (!hasVisibleTags(tag)) return null;
  return (
    <button
      type="button"
      onClick={onEdit}
      className="flex items-center gap-1 flex-wrap cursor-pointer hover:opacity-80"
      title={t("questionBank.tag.editTitle", undefined, "编辑标签")}
    >
      {tag?.unit && (
        <Badge variant="outline" className="text-violet-600 border-violet-200">
          {t("questionBank.tag.unitShort", undefined, "单元")}: {tag.unit}
        </Badge>
      )}
      {(tag?.knowledge_points ?? []).map((kp) => (
        <Badge key={kp} variant="outline" className="text-blue-600 border-blue-200">
          {kp}
        </Badge>
      ))}
      {tag?.difficulty && (
        <Badge variant="outline" className="text-amber-600 border-amber-200">
          {t(`questionBank.tag.difficulty.${tag.difficulty}`, undefined, tag.difficulty)}
        </Badge>
      )}
      {tag?.question_type && (
        <Badge variant="outline" className="text-emerald-600 border-emerald-200">
          {tag.question_type}
        </Badge>
      )}
    </button>
  );
}

/** 单个题目卡片 */
function QuestionCard({
  q,
  selected,
  tag,
  onToggleSelect,
  onEditTag,
}: {
  q: BankQuestion;
  selected: boolean;
  tag?: QuestionTag;
  onToggleSelect: (q: BankQuestion) => void;
  onEditTag: (q: BankQuestion) => void;
}) {
  const { t } = useLocale();
  const options = Array.isArray(q.options) ? (q.options as string[]) : null;
  return (
    <Card className={selected ? "border-primary/50 bg-primary/5" : undefined}>
      <CardContent className="pt-4 space-y-2">
        <div className="flex items-start gap-2">
          <Checkbox
            checked={selected}
            onCheckedChange={() => onToggleSelect(q)}
            aria-label={t("questionBank.tag.selectRow", undefined, "选择该题")}
            className="mt-1"
          />
          <div className="flex-1 space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              {q.question_type && <Badge variant="secondary">{q.question_type}</Badge>}
              {q.difficulty != null && (
                <span className="text-xs text-amber-600">
                  {difficultyLabel(q.difficulty)}
                </span>
              )}
              {q.grade && <Badge variant="outline">{q.grade}</Badge>}
              {q.knowledge_point && (
                <Badge variant="outline" className="text-blue-600 border-blue-200">
                  {q.knowledge_point}
                </Badge>
              )}
            </div>

            {/* 本地标签覆盖层徽章（点击编辑） */}
            <TagBadges tag={tag} onEdit={() => onEditTag(q)} />

            <p className="text-sm font-medium leading-relaxed whitespace-pre-wrap">
              {stripHtml(q.question)}
            </p>

            {options && options.length > 0 && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1">
                {options.map((opt, i) => (
                  <div key={i} className="text-xs text-muted-foreground">
                    {opt}
                  </div>
                ))}
              </div>
            )}

            <div className="text-sm">
              <span className="text-muted-foreground">答案：</span>
              <span className="text-green-700 font-medium">{stripHtml(q.answer)}</span>
            </div>

            {q.analysis && (
              <details className="text-sm">
                <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                  解析
                </summary>
                <p className="mt-1 text-muted-foreground leading-relaxed whitespace-pre-wrap">
                  {stripHtml(q.analysis)}
                </p>
              </details>
            )}

            <div>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs text-muted-foreground"
                onClick={() => onEditTag(q)}
              >
                <Tags className="w-3 h-3 mr-1" />
                {hasVisibleTags(tag)
                  ? t("questionBank.tag.editTitle", undefined, "编辑标签")
                  : t("questionBank.tag.addTitle", undefined, "打标签")}
              </Button>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function QuestionBankPage() {
  const { t } = useLocale();
  const [filters, setFilters] = useState<BankFilters | null>(null);
  const [subject, setSubject] = useState("");
  const [grade, setGrade] = useState("");
  const [questionType, setQuestionType] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [knowledgePoint, setKnowledgePoint] = useState("");
  const [keywordInput, setKeywordInput] = useState("");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);

  const [items, setItems] = useState<BankQuestion[]>([]);
  const [total, setTotal] = useState(0);
  const [enabled, setEnabled] = useState(true);
  const [loading, setLoading] = useState(false);

  // ── 批量打标状态 ──
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [tagMap, setTagMap] = useState<Record<string, QuestionTag>>({});
  const [tagFilter, setTagFilter] = useState<QuestionTagFilter>({});
  const [batchOpen, setBatchOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<BankQuestion | null>(null);
  const [savingTags, setSavingTags] = useState(false);

  // 首次加载筛选下拉枚举值
  useEffect(() => {
    let cancelled = false;
    getBankFilters()
      .then((f) => {
        if (!cancelled) setFilters(f);
      })
      .catch(() => {
        if (!cancelled) setFilters({ subjects: [], grades: [], question_types: [], difficulties: [] });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // 条件变化 → 检索
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    searchBankQuestions({
      subject: subject || undefined,
      grade: grade || undefined,
      question_type: questionType || undefined,
      difficulty: difficulty ? Number(difficulty) : undefined,
      knowledge_point: knowledgePoint || undefined,
      keyword: keyword || undefined,
      page,
      page_size: PAGE_SIZE,
    })
      .then((res) => {
        if (cancelled) return;
        setItems(res.items);
        setTotal(res.total);
        setEnabled(res.enabled !== false);
      })
      .catch(() => {
        if (!cancelled) {
          setItems([]);
          setTotal(0);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [subject, grade, questionType, difficulty, knowledgePoint, keyword, page]);

  // 当前页 keys → 拉标签（徽章）
  const pageKeys = useMemo(
    () => items.map((q) => questionTagKey(q)).filter(Boolean),
    [items],
  );

  useEffect(() => {
    if (pageKeys.length === 0) return;
    let cancelled = false;
    fetchQuestionTags(pageKeys)
      .then((tags) => {
        if (cancelled) return;
        setTagMap((prev) => ({ ...prev, ...tags }));
      })
      .catch(() => {
        // 标签拉取失败不阻塞列表
      });
    return () => {
      cancelled = true;
    };
  }, [pageKeys.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const subjects = filters?.subjects ?? [];
  const grades = filters?.grades ?? [];
  const questionTypes = filters?.question_types ?? [];
  const difficulties = filters?.difficulties ?? [];

  const toggleSelect = useCallback((q: BankQuestion) => {
    const key = questionTagKey(q);
    if (!key) return;
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const allPageKeys = pageKeys;
  const allPageSelected = allPageKeys.length > 0 && allPageKeys.every((k) => selectedKeys.has(k));
  const somePageSelected = allPageKeys.some((k) => selectedKeys.has(k));

  const toggleSelectAllPage = () => {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (allPageSelected) {
        allPageKeys.forEach((k) => next.delete(k));
      } else {
        allPageKeys.forEach((k) => next.add(k));
      }
      return next;
    });
  };

  // 标签本地筛选后的展示列表
  const visibleItems = useMemo(
    () => filterQuestionsByTags(items, tagMap, tagFilter, questionTagKey),
    [items, tagMap, tagFilter],
  );

  const applyBatchTags = async (patch: QuestionTagPatch) => {
    if (selectedKeys.size === 0) return;
    setSavingTags(true);
    try {
      const keys = Array.from(selectedKeys);
      const res = await batchUpdateQuestionTags(keys, {
        ...patch,
        source: patch.source ?? "pg",
      });
      setTagMap((prev) => ({ ...prev, ...res.tags }));
      toast.success(
        t("questionBank.tag.batchApplied", { count: res.updated }, `已为 ${res.updated} 题打标`),
      );
      setBatchOpen(false);
      setSelectedKeys(new Set());
    } catch {
      toast.error(t("questionBank.tag.saveFailed", undefined, "标签保存失败"));
    } finally {
      setSavingTags(false);
    }
  };

  const applySingleTag = async (patch: QuestionTagPatch) => {
    if (!editTarget) return;
    const key = questionTagKey(editTarget);
    if (!key) return;
    setSavingTags(true);
    try {
      const res = await batchUpdateQuestionTags([key], {
        ...patch,
        source: patch.source ?? questionTagSource(editTarget),
      });
      setTagMap((prev) => ({ ...prev, ...res.tags }));
      toast.success(t("questionBank.tag.saved", undefined, "标签已保存"));
      setEditTarget(null);
    } catch {
      toast.error(t("questionBank.tag.saveFailed", undefined, "标签保存失败"));
    } finally {
      setSavingTags(false);
    }
  };

  const tagFilterActive =
    !!(tagFilter.unit || tagFilter.knowledge_point || tagFilter.difficulty || tagFilter.question_type);

  return (
    <div className="p-6 space-y-4 max-w-5xl mx-auto">
      {/* 标题 */}
      <div className="flex items-center gap-2">
        <BookCopy className="w-6 h-6 text-primary" />
        <h1 className="text-xl font-semibold">题库</h1>
        {!enabled && (
          <Badge variant="outline" className="text-amber-600 border-amber-300">
            数据未接入
          </Badge>
        )}
        {enabled && total > 0 && (
          <span className="text-sm text-muted-foreground">共 {total} 题</span>
        )}
      </div>

      {/* 筛选栏 */}
      <Card>
        <CardContent className="pt-4 space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Select
              value={subject || "all"}
              onValueChange={(v) => {
                setSubject(v === "all" ? "" : v);
                setPage(1);
              }}
            >
              <SelectTrigger>
                <SelectValue placeholder="全部学科" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部学科</SelectItem>
                {subjects.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select
              value={grade || "all"}
              onValueChange={(v) => {
                setGrade(v === "all" ? "" : v);
                setPage(1);
              }}
            >
              <SelectTrigger>
                <SelectValue placeholder="全部学段" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部学段</SelectItem>
                {grades.map((g) => (
                  <SelectItem key={g} value={g}>
                    {g}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select
              value={questionType || "all"}
              onValueChange={(v) => {
                setQuestionType(v === "all" ? "" : v);
                setPage(1);
              }}
            >
              <SelectTrigger>
                <SelectValue placeholder="全部题型" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部题型</SelectItem>
                {questionTypes.map((qt) => (
                  <SelectItem key={qt} value={qt}>
                    {qt}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select
              value={difficulty || "all"}
              onValueChange={(v) => {
                setDifficulty(v === "all" ? "" : v);
                setPage(1);
              }}
            >
              <SelectTrigger>
                <SelectValue placeholder="全部难度" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部难度</SelectItem>
                {difficulties.map((d) => (
                  <SelectItem key={d} value={String(d)}>
                    {difficultyLabel(d)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col sm:flex-row gap-2">
            <Input
              placeholder="知识点关键词"
              value={knowledgePoint}
              onChange={(e) => setKnowledgePoint(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") setPage(1);
              }}
              className="sm:flex-1"
            />
            <Input
              placeholder="题干关键词"
              value={keywordInput}
              onChange={(e) => setKeywordInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  setKeyword(keywordInput);
                  setPage(1);
                }
              }}
              className="sm:flex-1"
            />
            <Button
              onClick={() => {
                setKeyword(keywordInput);
                setPage(1);
              }}
            >
              <Search className="w-4 h-4 mr-1" />
              搜索
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* 标签筛选（本地过滤当前列表） */}
      <Card>
        <CardContent className="pt-4 space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <Tags className="w-4 h-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">
              {t("questionBank.tag.filterTitle", undefined, "按标签筛选")}
            </span>
            {tagFilterActive && (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs"
                onClick={() => setTagFilter({})}
              >
                <X className="w-3 h-3 mr-1" />
                {t("questionBank.tag.filterClear", undefined, "清除")}
              </Button>
            )}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <Input
              placeholder={t("questionBank.tag.unit", undefined, "单元")}
              value={tagFilter.unit ?? ""}
              onChange={(e) => setTagFilter((f) => ({ ...f, unit: e.target.value }))}
            />
            <Input
              placeholder={t("questionBank.tag.knowledgePoints", undefined, "知识点")}
              value={tagFilter.knowledge_point ?? ""}
              onChange={(e) => setTagFilter((f) => ({ ...f, knowledge_point: e.target.value }))}
            />
            <Select
              value={tagFilter.difficulty || "all"}
              onValueChange={(v) =>
                setTagFilter((f) => ({ ...f, difficulty: v === "all" ? "" : v }))
              }
            >
              <SelectTrigger>
                <SelectValue placeholder={t("questionBank.tag.difficulty", undefined, "难度")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">
                  {t("questionBank.tag.allDifficulties", undefined, "全部难度")}
                </SelectItem>
                {TAG_DIFFICULTY_OPTIONS.map((d) => (
                  <SelectItem key={d} value={d}>
                    {t(`questionBank.tag.difficulty.${d}`, undefined, d)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              placeholder={t("questionBank.tag.questionType", undefined, "题型")}
              value={tagFilter.question_type ?? ""}
              onChange={(e) => setTagFilter((f) => ({ ...f, question_type: e.target.value }))}
            />
          </div>
        </CardContent>
      </Card>

      {/* 本页全选 + 已选计数 */}
      {enabled && items.length > 0 && (
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <Checkbox
              checked={allPageSelected}
              onCheckedChange={toggleSelectAllPage}
              aria-label={t("questionBank.tag.selectAll", undefined, "本页全选")}
            />
            <span className="text-muted-foreground">
              {t("questionBank.tag.selectAll", undefined, "本页全选")}
            </span>
          </label>
          {selectedKeys.size > 0 && (
            <span className="text-sm text-primary">
              {t("questionBank.tag.selectedCount", { count: selectedKeys.size }, `已选 ${selectedKeys.size} 题`)}
            </span>
          )}
          {somePageSelected && !allPageSelected && (
            <span className="text-xs text-muted-foreground">
              (本页 {allPageKeys.filter((k) => selectedKeys.has(k)).length}/{allPageKeys.length})
            </span>
          )}
        </div>
      )}

      {/* 列表 */}
      {loading ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground">
          <Loader2 className="w-6 h-6 animate-spin mr-2" />
          加载中…
        </div>
      ) : !enabled ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <PlugZap className="w-10 h-10 mb-3 text-amber-500" />
          <p className="text-sm">题库数据暂未接入</p>
          <p className="text-xs mt-1">接入后即可浏览、筛选并检索题库题目</p>
        </div>
      ) : visibleItems.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <Inbox className="w-10 h-10 mb-3" />
          <p className="text-sm">
            {tagFilterActive
              ? t("questionBank.tag.filterEmpty", undefined, "没有符合标签筛选的题目")
              : "没有符合条件的题目"}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {visibleItems.map((q) => {
            const key = questionTagKey(q);
            return (
              <QuestionCard
                key={q.id || key}
                q={q}
                selected={selectedKeys.has(key)}
                tag={tagMap[key]}
                onToggleSelect={toggleSelect}
                onEditTag={setEditTarget}
              />
            );
          })}
        </div>
      )}

      {/* 分页 */}
      {enabled && total > 0 && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            第 {page} / {totalPages} 页
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1 || loading}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              <ChevronLeft className="w-4 h-4 mr-1" />
              上一页
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages || loading}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              下一页
              <ChevronRight className="w-4 h-4 ml-1" />
            </Button>
          </div>
        </div>
      )}

      {/* 浮出批量打标工具条 */}
      {selectedKeys.size > 0 && !batchOpen && !editTarget && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 shadow-lg rounded-full border bg-background px-4 py-2 flex items-center gap-3">
          <Tags className="w-4 h-4 text-primary" />
          <span className="text-sm">
            {t("questionBank.tag.selectedCount", { count: selectedKeys.size }, `已选 ${selectedKeys.size} 题`)}
          </span>
          <Button size="sm" onClick={() => setBatchOpen(true)}>
            {t("questionBank.tag.batchButton", undefined, "批量打标")}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setSelectedKeys(new Set())}
          >
            {t("questionBank.tag.clearSelection", undefined, "取消选择")}
          </Button>
        </div>
      )}

      {/* 批量打标编辑器 */}
      <QuestionTagEditor
        open={batchOpen}
        onOpenChange={setBatchOpen}
        count={selectedKeys.size}
        initial={null}
        onSave={applyBatchTags}
        saving={savingTags}
      />

      {/* 单行快速编辑 */}
      <QuestionTagEditor
        open={!!editTarget}
        onOpenChange={(open) => {
          if (!open) setEditTarget(null);
        }}
        count={1}
        initial={editTarget ? tagMap[questionTagKey(editTarget)] ?? null : null}
        onSave={applySingleTag}
        saving={savingTags}
      />
    </div>
  );
}
