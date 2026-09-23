import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLocale } from "@/contexts/LocaleContext";
import { BookOpen, Layers, FileText, Lightbulb, AlertTriangle, CheckCircle2 } from "lucide-react";
import type { QuestionAnalysisQuestion, QuestionAnalysisOverview, QuestionAnalysisTier } from "./types";

interface TeachingSuggestionsProps {
  question: QuestionAnalysisQuestion;
  overview: QuestionAnalysisOverview;
  tieredPractice: QuestionAnalysisTier[];
}

export function TeachingSuggestions({ question: q, overview, tieredPractice }: TeachingSuggestionsProps) {
  const { t, locale } = useLocale();

  return (
    <Card className="flex-1 min-w-[320px]" data-tour="qa-suggestions">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Lightbulb className="w-4 h-4 text-amber-500" />
          <CardTitle className="text-sm font-semibold">{t("classDetail.AI教学建议")}</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 text-xs">
        {/* 讲评重点（真实数据） */}
        <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-3 space-y-2">
          <p className="font-semibold text-foreground flex items-center gap-1.5">
            <FileText className="w-3.5 h-3.5 text-blue-600" />{t("classDetail.reviewFocusTitle")}
          </p>
          {q.teachingStrategy ? (
            <p className="text-muted-foreground leading-relaxed">{q.teachingStrategy}</p>
          ) : (
            <p className="text-muted-foreground/60">{t("classDetail.noReviewStrategyData")}</p>
          )}
          {q.followUpExercise && (
            <p className="text-muted-foreground leading-relaxed">
              <strong className="text-foreground">{t("classDetail.followUpExerciseLabel")}</strong>{q.followUpExercise}
            </p>
          )}
        </div>

        {/* 班级整体概述（真实数据） */}
        <div className="rounded-lg border border-sky-200 bg-sky-50/50 p-3 space-y-2">
          <p className="font-semibold text-foreground flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-sky-600" />{t("classDetail.classOverallTitle")}
          </p>
          {overview.summary ? (
            <p className="text-muted-foreground leading-relaxed">{overview.summary}</p>
          ) : (
            <p className="text-muted-foreground/60">{t("classDetail.noClassOverviewData")}</p>
          )}
          {overview.weakPoints.length > 0 && (
            <div className="space-y-1">
              <p className="font-medium text-rose-600 flex items-center gap-1"><AlertTriangle className="w-3 h-3" />{t("classDetail.weakPointsTitle")}</p>
              <ul className="space-y-1 text-muted-foreground">
                {overview.weakPoints.slice(0, 4).map((w, i) => <li key={i}>• {w}</li>)}
              </ul>
            </div>
          )}
          {overview.strengths.length > 0 && (
            <div className="space-y-1">
              <p className="font-medium text-emerald-600 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" />{t("classDetail.strengthsTitle")}</p>
              <ul className="space-y-1 text-muted-foreground">
                {overview.strengths.slice(0, 3).map((s, i) => <li key={i}>• {s}</li>)}
              </ul>
            </div>
          )}
        </div>

        {/* 分层巩固（真实数据，来自 consolidation.tiered_practice） */}
        <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-3 space-y-2">
          <p className="font-semibold text-foreground flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-emerald-600" />{t("classDetail.tieredReinforcementSection")}
          </p>
          {tieredPractice.length > 0 ? (
            <div className="space-y-1.5">
              {tieredPractice.map((tier, i) => (
                <div key={i} className="rounded-md bg-white/70 p-2">
                  <p className="font-semibold text-foreground">{tier.level}</p>
                  <ul className="space-y-0.5 text-muted-foreground mt-0.5">
                    {tier.tasks.map((task, j) => <li key={j}>• {task}</li>)}
                  </ul>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-muted-foreground/60">{t("classDetail.noTieredPracticeData")}</p>
          )}
        </div>

        {/* 命题反思：依赖难度/区分度，暂未产出 → 降级 */}
        <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-3 space-y-2">
          <p className="font-semibold text-foreground flex items-center gap-1.5">
            <BookOpen className="w-3.5 h-3.5 text-amber-600" />{t("classDetail.propositionReflection")}
          </p>
          <p className="text-muted-foreground/60">{t("classDetail.propositionReflectionDesc")}</p>
        </div>
      </CardContent>
    </Card>
  );
}
