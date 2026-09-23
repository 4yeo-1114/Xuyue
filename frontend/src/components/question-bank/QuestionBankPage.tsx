import { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
} from "lucide-react";
import {
  searchBankQuestions,
  getBankFilters,
  type BankFilters,
  type BankQuestion,
} from "@/services/questionBankApi";

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

/** 单个题目卡片 */
function QuestionCard({ q }: { q: BankQuestion }) {
  const options = Array.isArray(q.options) ? (q.options as string[]) : null;
  return (
    <Card>
      <CardContent className="pt-4 space-y-2">
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
      </CardContent>
    </Card>
  );
}

export function QuestionBankPage() {
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

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const subjects = filters?.subjects ?? [];
  const grades = filters?.grades ?? [];
  const questionTypes = filters?.question_types ?? [];
  const difficulties = filters?.difficulties ?? [];

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
                {questionTypes.map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
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
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <Inbox className="w-10 h-10 mb-3" />
          <p className="text-sm">没有符合条件的题目</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((q) => (
            <QuestionCard key={q.id} q={q} />
          ))}
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
    </div>
  );
}
