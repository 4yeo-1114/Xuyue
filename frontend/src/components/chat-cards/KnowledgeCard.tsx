import { BookOpen, ChevronDown, Users, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import type { KnowledgeCardData } from "./types";

function MasteryBar({ value }: { value: number }) {
  const color =
    value >= 80
      ? "bg-emerald-500"
      : value >= 60
        ? "bg-amber-500"
        : "bg-destructive";
  return (
    <div className="flex items-center gap-2 w-full">
      <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", color)}
          style={{ width: `${value}%` }}
        />
      </div>
      <span
        className={cn(
          "text-xs font-bold tabular-nums w-10 text-right",
          value >= 80
            ? "text-emerald-600"
            : value >= 60
              ? "text-amber-600"
              : "text-destructive",
        )}
      >
        {value}%
      </span>
    </div>
  );
}

function DifficultyStars({ difficulty }: { difficulty: string }) {
  const { t } = useLocale();
  const map: Record<string, number> = {
    [t("home.difficulty.easy")]: 1,
    [t("home.difficulty.basic")]: 1,
    [t("home.difficulty.medium")]: 2,
    [t("home.difficulty.hard")]: 3,
    [t("home.difficulty.veryHard")]: 3,
  };
  const stars = map[difficulty] || 2;
  return (
    <span className="inline-flex items-center gap-0.5 text-amber-500">
      {Array.from({ length: stars }).map((_, i) => (
        <span key={i} className="text-[10px]">
          ★
        </span>
      ))}
    </span>
  );
}

interface KnowledgeListCardProps {
  knowledgePoints: KnowledgeCardData[];
  onNavigate?: (id: string) => void;
}

export function KnowledgeListCard({
  knowledgePoints,
  onNavigate,
}: KnowledgeListCardProps) {
  const { t } = useLocale();
  const [expanded, setExpanded] = useState(false);
  const MAX_COLLAPSED = 4;
  const display = expanded
    ? knowledgePoints
    : knowledgePoints.slice(0, MAX_COLLAPSED);
  const hasMore = knowledgePoints.length > MAX_COLLAPSED;

  // Summary stats
  const weakCount = knowledgePoints.filter((k) => k.is_weak).length;
  const avgMastery = Math.round(
    knowledgePoints.reduce((s, k) => s + k.mastery, 0) /
      (knowledgePoints.length || 1),
  );

  return (
    <div className="border border-border/60 rounded-xl my-2 bg-card/80 backdrop-blur-sm overflow-hidden shadow-sm">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2.5 bg-primary/5 border-b border-border/40">
        <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center">
          <BookOpen className="w-3.5 h-3.5 text-primary" />
        </div>
        <span className="font-semibold text-sm">
          {t("chatCards.knowledge.title")}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {weakCount > 0 && (
            <Badge
              variant="destructive"
              className="text-[10px] px-1.5 py-0 h-4"
            >
              <AlertTriangle className="w-2.5 h-2.5 mr-0.5" />
              {t("chatCards.knowledge.weakBadge", { count: weakCount })}
            </Badge>
          )}
          <span className="text-[11px] text-muted-foreground">
            {t("chatCards.knowledge.avgMastery", { value: avgMastery })}
          </span>
        </div>
      </div>

      {/* Knowledge list */}
      <div className="divide-y divide-border/30">
        {display.map((data) => (
          <div
            key={data.id || data.code}
            className="px-3 py-2.5 hover:bg-accent/30 transition-colors"
          >
            {/* Row 1: name + tags */}
            <div className="flex items-center gap-2 mb-1.5">
              <span
                className={cn(
                  "font-medium text-sm",
                  data.is_weak && "text-destructive",
                )}
              >
                {data.name}
              </span>
              <span className="text-[10px] text-muted-foreground font-mono">
                {data.code}
              </span>
              {data.is_weak && (
                <Badge
                  variant="destructive"
                  className="text-[10px] px-1.5 py-0 h-4"
                >
                  {t("chatCards.knowledge.weakLabel")}
                </Badge>
              )}
              <DifficultyStars difficulty={data.difficulty} />
              <span className="text-[10px] text-muted-foreground ml-auto">
                {data.level}
              </span>
            </div>

            {/* Row 2: mastery bar */}
            <MasteryBar value={data.mastery} />

            {/* Row 3: details */}
            <div className="flex items-center gap-3 mt-1.5 text-[11px] text-muted-foreground">
              {data.related_students != null && data.related_students > 0 && (
                <span className="flex items-center gap-0.5">
                  <Users className="w-3 h-3" />
                  {t("chatCards.knowledge.relatedStudents", {
                    count: data.related_students,
                  })}
                </span>
              )}
              {data.common_errors && (
                <span className="truncate">
                  {t("chatCards.knowledge.commonErrors", {
                    errors: data.common_errors,
                  })}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Expand / Actions */}
      <div className="flex items-center gap-2 px-3 py-2 border-t border-border/40 bg-muted/20">
        {hasMore && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-[11px] text-primary hover:text-primary/80 flex items-center gap-0.5 transition-colors"
          >
            <ChevronDown
              className={cn(
                "w-3 h-3 transition-transform",
                expanded && "rotate-180",
              )}
            />
            {expanded
              ? t("chatCards.common.collapse")
              : t("chatCards.knowledge.expandAll", {
                  count: knowledgePoints.length,
                })}
          </button>
        )}
        <div className="flex gap-1.5 ml-auto">
          <button
            onClick={() => onNavigate?.("ai-targeted")}
            className="text-[11px] px-2.5 py-1 rounded-md bg-primary/10 text-primary hover:bg-primary/20 transition-colors font-medium"
          >
            {t("chatCards.knowledge.generatePractice")}
          </button>
        </div>
      </div>
    </div>
  );
}

/* Single knowledge card (backward compat) */
export function KnowledgeCard({
  data,
  onNavigate,
}: {
  data: KnowledgeCardData;
  onNavigate?: (id: string) => void;
}) {
  return <KnowledgeListCard knowledgePoints={[data]} onNavigate={onNavigate} />;
}
