import { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { Sparkles, Clock, Users2, FileText, Zap, ClipboardList } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { ReviewPriority, SimilarExercise } from "./reviewData";

interface AIReviewPlanProps {
  priorities: ReviewPriority[];
  exercises: SimilarExercise[];
  sourceLabel: string;
}

export function AIReviewPlan({ priorities, exercises, sourceLabel }: AIReviewPlanProps) {
  const { t, locale } = useLocale();

  const priorityCfg = useMemo(
    () => ({
      high: { emoji: "🔴", label: t("classDetail.优先级1"), color: "border-red-200 bg-red-50/60" },
      medium: { emoji: "🟠", label: t("classDetail.优先级2"), color: "border-orange-200 bg-orange-50/60" },
      low: { emoji: "🟡", label: t("classDetail.优先级3"), color: "border-amber-200 bg-amber-50/60" },
    }),
    [t]
  );

  const totalMinutes = priorities.reduce((s, p) => s + p.suggestedMinutes, 0);
  const totalErrors = priorities.reduce((s, p) => s + p.errorCount, 0);

  return (
    <Card data-tour="cr-analysis">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-primary" />
          <CardTitle className="text-sm font-semibold">{t("classDetail.aiReviewPlanTitle")}</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Data source summary */}
        <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1"><FileText className="w-3.5 h-3.5" />{t("classDetail.dataSourceCountLabel", { source: sourceLabel })}</span>
          <span className="flex items-center gap-1"><Clock className="w-3.5 h-3.5" />{t("classDetail.suggestedReviewTimeLabel")}<strong className="text-foreground">{t("classDetail.minutesUnit", { count: totalMinutes })}</strong></span>
          <span className="flex items-center gap-1"><Users2 className="w-3.5 h-3.5" />{t("classDetail.errorPersonCountLabel")}<strong className="text-foreground">{t("classDetail.personTimesUnit", { count: totalErrors })}</strong></span>
        </div>

        {/* Priority items */}
        <div className="space-y-2" data-tour="cr-priorities">
          <p className="text-xs font-semibold text-foreground">{t("classDetail.aiPriorityTitle")}</p>
          {priorities.map((p) => {
            const cfg = priorityCfg[p.priority];
            return (
              <TooltipProvider key={p.id} delayDuration={200}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <div className={cn("rounded-lg border p-3 space-y-1.5 cursor-default", cfg.color)}>
                      <div className="flex items-center gap-2 text-xs flex-wrap">
                        <span>{cfg.emoji}</span>
                        <span className="font-semibold text-foreground">{t("classDetail.priorityTopicLabel", { priority: cfg.label, topic: p.topic })}</span>
                        <Badge variant="outline" className="text-[10px] h-4">{t("classDetail.scoreRateBadge", { rate: p.scoreRate })}</Badge>
                        <Badge variant="outline" className="text-[10px] h-4">{t("classDetail.peopleErrorBadge", { count: p.errorCount })}</Badge>
                      </div>
                      <p className="text-[11px] text-muted-foreground">{t("classDetail.typicalErrorsLabel")}{p.typicalErrors.join("、")}</p>
                      <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                        <span>{t("classDetail.suggestedDurationLabel")}<strong className="text-foreground">{t("classDetail.minutesUnit", { count: p.suggestedMinutes })}</strong></span>
                        <span>{t("classDetail.reviewMethodLabel")}<strong className="text-foreground">{p.method}</strong></span>
                      </div>
                      <div className="flex gap-1.5 mt-1">
                        <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px]">{t("classDetail.viewTypicalAnswerSheet")}</Button>
                        <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px]">{t("classDetail.viewErrorAnalysis")}</Button>
                        <Button size="sm" className="h-6 px-2 text-[10px]">{t("classDetail.addToReview")}</Button>
                      </div>
                    </div>
                  </TooltipTrigger>
                  <TooltipContent side="top" className="text-xs">{t("classDetail.clickToViewErrorsTooltip")}</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            );
          })}
        </div>

        {/* Action buttons */}
        <div className="flex gap-2 flex-wrap" data-tour="cr-actions">
          <Button size="sm" className="h-8 text-xs gap-1.5">
            <Sparkles className="w-3.5 h-3.5" />{t("classDetail.generateFullPlan")}
          </Button>
          <Button variant="outline" size="sm" className="h-8 text-xs gap-1.5">
            <Zap className="w-3.5 h-3.5" />{t("classDetail.generatePPTOneClick")}
          </Button>
          <Button variant="outline" size="sm" className="h-8 text-xs gap-1.5">
            <ClipboardList className="w-3.5 h-3.5" />{t("classDetail.导出讲评提纲")}
          </Button>
        </div>

        {/* Generated content preview */}
        <div className="rounded-lg border border-border/50 p-3 space-y-1.5">
          <p className="text-[11px] font-semibold text-foreground">{t("classDetail.generatedContentPreview")}</p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px] text-muted-foreground">
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-primary" />
              {t("classDetail.pptPreviewLine")}
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-primary" />
              {t("classDetail.similarExercisesLine", { count: exercises.length })}
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-primary" />
              {t("classDetail.studentCalloutListLine")}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
