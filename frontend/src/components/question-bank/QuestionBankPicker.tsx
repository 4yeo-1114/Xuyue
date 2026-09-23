import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
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
import { Checkbox } from "@/components/ui/checkbox";
import {
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
  stripHtmlText,
  type BankFilters,
  type BankQuestion,
} from "@/services/questionBankApi";

const PAGE_SIZE = 10;

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 预填学科（来自组卷页当前学科） */
  initialSubject?: string;
  /** 确认加入：把选中的题库题原样交给组卷页转换 */
  onAdd: (questions: BankQuestion[]) => void;
}

export function QuestionBankPicker({
  open,
  onOpenChange,
  initialSubject,
  onAdd,
}: Props) {
  const [filters, setFilters] = useState<BankFilters | null>(null);
  const [subject, setSubject] = useState("");
  const [questionType, setQuestionType] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [keywordInput, setKeywordInput] = useState("");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);

  const [items, setItems] = useState<BankQuestion[]>([]);
  const [total, setTotal] = useState(0);
  const [enabled, setEnabled] = useState(true);
  const [loading, setLoading] = useState(false);
  // 跨页多选：id → 题目对象
  const [selectedMap, setSelectedMap] = useState<Map<string, BankQuestion>>(
    new Map(),
  );

  // 打开时重置筛选/选择并加载枚举
  useEffect(() => {
    if (!open) return;
    setSubject(initialSubject || "");
    setQuestionType("");
    setDifficulty("");
    setKeywordInput("");
    setKeyword("");
    setPage(1);
    setSelectedMap(new Map());
    let cancelled = false;
    getBankFilters()
      .then((f) => {
        if (!cancelled) setFilters(f);
      })
      .catch(() => {
        if (!cancelled)
          setFilters({ subjects: [], grades: [], question_types: [], difficulties: [] });
      });
    return () => {
      cancelled = true;
    };
  }, [open, initialSubject]);

  // 检索
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    searchBankQuestions({
      subject: subject || undefined,
      question_type: questionType || undefined,
      difficulty: difficulty ? Number(difficulty) : undefined,
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
  }, [open, subject, questionType, difficulty, keyword, page]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const toggleSelect = (q: BankQuestion) => {
    setSelectedMap((prev) => {
      const next = new Map(prev);
      if (next.has(q.id)) next.delete(q.id);
      else next.set(q.id, q);
      return next;
    });
  };

  const handleConfirm = () => {
    if (selectedMap.size === 0) return;
    onAdd(Array.from(selectedMap.values()));
    onOpenChange(false);
  };

  const subjects = filters?.subjects ?? [];
  const questionTypes = filters?.question_types ?? [];
  const difficulties = filters?.difficulties ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>从题库选题</DialogTitle>
        </DialogHeader>

        {/* 筛选栏 */}
        <div className="space-y-2">
          <div className="grid grid-cols-3 gap-2">
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
                    难度 {d}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex gap-2">
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
              className="flex-1"
            />
            <Button
              size="sm"
              onClick={() => {
                setKeyword(keywordInput);
                setPage(1);
              }}
            >
              <Search className="w-4 h-4 mr-1" />
              搜索
            </Button>
          </div>
        </div>

        {/* 列表 */}
        <div className="flex-1 overflow-y-auto min-h-[200px] border rounded-md">
          {loading ? (
            <div className="flex items-center justify-center py-16 text-muted-foreground">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              加载中…
            </div>
          ) : !enabled ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <PlugZap className="w-8 h-8 mb-2 text-amber-500" />
              <p className="text-sm">题库数据暂未接入</p>
            </div>
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <Inbox className="w-8 h-8 mb-2" />
              <p className="text-sm">没有符合条件的题目</p>
            </div>
          ) : (
            <ul className="divide-y">
              {items.map((q) => {
                const checked = selectedMap.has(q.id);
                return (
                  <li
                    key={q.id}
                    className={`flex gap-3 px-3 py-2.5 hover:bg-muted/40 cursor-pointer ${
                      checked ? "bg-primary/5" : ""
                    }`}
                    onClick={() => toggleSelect(q)}
                  >
                    <Checkbox
                      checked={checked}
                      onCheckedChange={() => toggleSelect(q)}
                      className="mt-0.5"
                    />
                    <div className="flex-1 min-w-0 space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        {q.question_type && (
                          <Badge variant="secondary">{q.question_type}</Badge>
                        )}
                        {q.difficulty != null && (
                          <span className="text-xs text-amber-600">
                            难度 {q.difficulty}
                          </span>
                        )}
                        {q.knowledge_point && (
                          <span className="text-xs text-blue-600 truncate max-w-[200px]">
                            {q.knowledge_point}
                          </span>
                        )}
                      </div>
                      <p className="text-sm leading-relaxed line-clamp-2">
                        {stripHtmlText(q.question)}
                      </p>
                      <p className="text-xs text-muted-foreground line-clamp-1">
                        答案：{stripHtmlText(q.answer)}
                      </p>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* 分页 */}
        {enabled && total > 0 && (
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">
              第 {page} / {totalPages} 页 · 共 {total} 题
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1 || loading}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages || loading}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleConfirm} disabled={selectedMap.size === 0}>
            加入试卷（{selectedMap.size}）
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
