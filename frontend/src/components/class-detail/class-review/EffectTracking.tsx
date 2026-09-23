import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { BarChart3, TrendingUp, BookOpen, History } from "lucide-react";
import type { TrackingStats } from "./reviewData";

interface EffectTrackingProps {
  stats: TrackingStats;
}

export function EffectTracking({ stats }: EffectTrackingProps) {
  const { t, locale } = useLocale();

  return (
    <Card className="flex-1 min-w-[320px]" data-tour="cr-tracking">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">{t("classDetail.effectTrackingTitle")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-xs">
        {/* Instant test */}
        <div className="rounded-lg border border-border/50 p-3 space-y-1.5">
          <p className="font-semibold text-foreground flex items-center gap-1.5">
            <BarChart3 className="w-3.5 h-3.5 text-primary" />{t("classDetail.inClassTest")}
          </p>
          <p className="text-[11px] text-muted-foreground">{t("classDetail.inClassTestDesc")}</p>
          <div className="flex gap-2">
            <Button size="sm" className="h-7 text-[11px]">{t("classDetail.pushInClassTest")}</Button>
            <span className="text-[11px] text-muted-foreground flex items-center">{t("classDetail.statusWaitingLabel")}</span>
          </div>
        </div>

        {/* Homework tracking */}
        <div className="rounded-lg border border-border/50 p-3 space-y-1.5">
          <p className="font-semibold text-foreground flex items-center gap-1.5">
            <BookOpen className="w-3.5 h-3.5 text-primary" />{t("classDetail.homeworkDeadlineTitle")}
          </p>
          <div className="grid grid-cols-2 gap-2 text-[11px] text-muted-foreground">
            <span>{t("classDetail.completionRateColonLabel")}<strong className="text-foreground">{t("classDetail.waitingDataLabel")}</strong></span>
            <span>{t("classDetail.correctRateColonLabel")}<strong className="text-foreground">{t("classDetail.waitingDataLabel")}</strong></span>
          </div>
        </div>

        {/* Effect comparison */}
        <div className="rounded-lg border border-border/50 p-3 space-y-1.5">
          <p className="font-semibold text-foreground flex items-center gap-1.5">
            <TrendingUp className="w-3.5 h-3.5 text-primary" />{t("classDetail.effectComparison")}
          </p>
          <div className="grid grid-cols-3 gap-2 text-center text-[11px]">
            <div className="p-2 rounded border border-border/40">
              <p className="text-muted-foreground">{t("classDetail.beforeReview")}</p>
              <p className="text-base font-bold text-destructive">{stats.preScoreRate}%</p>
            </div>
            <div className="p-2 rounded border border-border/40">
              <p className="text-muted-foreground">{t("classDetail.afterReview")}</p>
              <p className="text-base font-bold text-muted-foreground">?</p>
              <p className="text-[10px] text-muted-foreground">{t("classDetail.pendingTest")}</p>
            </div>
            <div className="p-2 rounded border border-border/40">
              <p className="text-muted-foreground">{t("classDetail.improvementTarget")}</p>
              <p className="text-base font-bold text-emerald-600">&gt;20%</p>
            </div>
          </div>
        </div>

        {/* AI review suggestions */}
        <div className="rounded-lg border border-border/50 p-3 space-y-1.5">
          <p className="font-semibold text-foreground">{t("classDetail.reviewRetrospectiveTitle")}</p>
          <div className="space-y-1 text-[11px] text-muted-foreground">
            <p>{t("classDetail.ruleHighEffect")}</p>
            <p>{t("classDetail.ruleMediumEffect")}</p>
            <p>{t("classDetail.ruleLowEffect")}</p>
          </div>
        </div>

        {/* My review archive */}
        <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 space-y-1.5">
          <p className="font-semibold text-foreground flex items-center gap-1.5">
            <History className="w-3.5 h-3.5 text-primary" />{t("classDetail.myReviewArchive")}
          </p>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
            <span>{t("classDetail.termReviewCountLabel")}<strong className="text-foreground">{t("classDetail.timesUnit", { count: stats.reviewCount })}</strong></span>
            <span>{t("classDetail.avgEffectRateLabel")}<strong className="text-foreground">{stats.avgEffectRate}%</strong></span>
            <span>{t("classDetail.bestStrategyColonLabel")}<strong className="text-emerald-600">{t("classDetail.strategyValueWithRate", { strategy: stats.bestStrategy, rate: stats.bestStrategyRate })}</strong></span>
            <span>{t("classDetail.worstStrategyColonLabel")}<strong className="text-destructive">{t("classDetail.strategyValueWithRate", { strategy: stats.worstStrategy, rate: stats.worstStrategyRate })}</strong></span>
          </div>
          <div className="flex gap-1.5 mt-1">
            <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px]">{t("classDetail.viewHistoryArchive")}</Button>
            <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px]">{t("classDetail.optimizeStrategy")}</Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
