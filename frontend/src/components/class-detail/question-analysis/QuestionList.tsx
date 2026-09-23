import { useState, useMemo } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { QuestionAnalysisQuestion, QuestionStatus } from "./types";

const STATUS_CONFIG: Record<QuestionStatus, { color: string; dot: string }> = {
  预警: { color: "text-red-600 bg-red-50 border-red-200", dot: "🔴" },
  关注: { color: "text-amber-600 bg-amber-50 border-amber-200", dot: "🟠" },
  正常: { color: "text-yellow-600 bg-yellow-50 border-yellow-200", dot: "🟡" },
  优秀: {
    color: "text-emerald-600 bg-emerald-50 border-emerald-200",
    dot: "🟢",
  },
};

/** 中文状态值 → 稳定英文枚举，用于比较逻辑与 i18n key 查找 */
export const STATUS_KEYS: Record<
  QuestionStatus,
  "warning" | "watch" | "normal" | "excellent"
> = {
  预警: "warning",
  关注: "watch",
  正常: "normal",
  优秀: "excellent",
};

const STATUS_LABEL_KEYS: Record<QuestionStatus, string> = {
  预警: "questionAnalysis.status.warning",
  关注: "questionAnalysis.status.watch",
  正常: "questionAnalysis.status.normal",
  优秀: "questionAnalysis.status.excellent",
};

type SortKey = "scoreRate" | "title" | "wrongCount";
const STATUS_FILTERS: Array<QuestionStatus | "全部"> = [
  "全部",
  "预警",
  "关注",
  "正常",
  "优秀",
];

interface QuestionListProps {
  questions: QuestionAnalysisQuestion[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
}

export function QuestionList({
  questions,
  selectedKey,
  onSelect,
}: QuestionListProps) {
  const { t, locale } = useLocale();

  const [sortKey, setSortKey] = useState<SortKey>("scoreRate");
  const [statusFilter, setStatusFilter] = useState<QuestionStatus | "全部">(
    "全部",
  );

  const filtered = useMemo(() => {
    let list =
      statusFilter === "全部"
        ? questions
        : questions.filter((q) => q.status === statusFilter);
    if (sortKey === "scoreRate")
      list = [...list].sort((a, b) => a.scoreRate - b.scoreRate);
    else if (sortKey === "title")
      list = [...list].sort((a, b) => a.title.localeCompare(b.title, "zh-CN"));
    else if (sortKey === "wrongCount")
      list = [...list].sort((a, b) => b.wrongCount - a.wrongCount);
    return list;
  }, [questions, sortKey, statusFilter]);

  return (
    <Card className="flex-1 min-w-[420px]" data-tour="qa-list">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold">
            {t("classDetail.questionListTitle")}
          </CardTitle>
          <span className="text-[11px] text-muted-foreground">
            {t("classDetail.totalQuestionsLabel", { count: questions.length })}
          </span>
        </div>
        {/* Sort & filter */}
        <div className="flex flex-wrap gap-2 mt-2">
          <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
            {t("classDetail.sortColonLabel")}
            {(
              [
                ["scoreRate", t("classDetail.得分率")],
                ["wrongCount", t("classDetail.wrongCountSortLabel")],
                ["title", t("classDetail.questionTitleSortLabel")],
              ] as Array<[SortKey, string]>
            ).map(([k, label]) => (
              <Button
                key={k}
                variant={sortKey === k ? "default" : "ghost"}
                size="sm"
                className="h-6 px-2 text-[11px]"
                onClick={() => setSortKey(k)}
              >
                {label}
              </Button>
            ))}
          </div>
          <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
            {t("classDetail.statusColonLabel")}
            {STATUS_FILTERS.map((s) => (
              <Button
                key={s}
                variant={statusFilter === s ? "default" : "ghost"}
                size="sm"
                className="h-6 px-2 text-[11px]"
                onClick={() => setStatusFilter(s)}
              >
                {s === "全部" ? t("classDetail.全部") : t(STATUS_LABEL_KEYS[s])}
              </Button>
            ))}
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {/* Table header */}
        <div className="grid grid-cols-[44px_1fr_44px_44px_44px_52px_52px] gap-1 px-4 py-2 text-[11px] font-medium text-muted-foreground border-b border-border/40">
          <span>{t("classDetail.seqHeader")}</span>
          <span>{t("classDetail.questionKnowledgeHeader")}</span>
          <span>{t("classDetail.correctWord")}</span>
          <span>{t("classDetail.wrongWord")}</span>
          <span>{t("classDetail.blankWord")}</span>
          <span>{t("classDetail.得分率")}</span>
          <span>{t("classDetail.statusHeader")}</span>
        </div>
        {/* Rows */}
        <div className="max-h-[340px] overflow-y-auto">
          {filtered.length === 0 ? (
            <div className="px-4 py-8 text-center text-xs text-muted-foreground">
              {t("classDetail.noMatchingQuestions")}
            </div>
          ) : (
            filtered.map((q, idx) => {
              const cfg = STATUS_CONFIG[q.status];
              return (
                <button
                  key={q.key}
                  onClick={() => onSelect(q.key)}
                  className={cn(
                    "w-full grid grid-cols-[44px_1fr_44px_44px_44px_52px_52px] gap-1 px-4 py-2 text-xs transition-colors border-b border-border/20 text-left",
                    selectedKey === q.key
                      ? "bg-primary/5 border-l-2 border-l-primary"
                      : "hover:bg-muted/50",
                  )}
                >
                  <span className="font-medium">
                    {cfg.dot} {idx + 1}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-foreground">
                      {q.title ||
                        t("classDetail.questionFallbackTitle", {
                          number: idx + 1,
                        })}
                    </span>
                    {q.knowledgePoint && (
                      <span className="block truncate text-[10px] text-muted-foreground">
                        {q.knowledgePoint}
                      </span>
                    )}
                  </span>
                  <span className="text-emerald-600 font-semibold">
                    {q.correctCount}
                  </span>
                  <span className="text-red-600 font-semibold">
                    {q.wrongCount}
                  </span>
                  <span className="text-amber-600">{q.blankCount}</span>
                  <span
                    className={cn(
                      "font-semibold",
                      q.scoreRate < 60
                        ? "text-red-600"
                        : q.scoreRate < 70
                          ? "text-amber-600"
                          : "text-foreground",
                    )}
                  >
                    {q.scoreRate}%
                  </span>
                  <Badge
                    variant="outline"
                    className={cn(
                      "text-[10px] h-5 px-1.5 justify-center",
                      cfg.color,
                    )}
                  >
                    {t(STATUS_LABEL_KEYS[q.status])}
                  </Badge>
                </button>
              );
            })
          )}
        </div>
        {/* Legend */}
        <div className="px-4 py-2 text-[10px] text-muted-foreground flex gap-3 border-t border-border/30">
          <span>{t("classDetail.legendWarning")}</span>
          <span>{t("classDetail.legendWatch")}</span>
          <span>{t("classDetail.legendNormal")}</span>
          <span>{t("classDetail.legendExcellent")}</span>
        </div>
      </CardContent>
    </Card>
  );
}
