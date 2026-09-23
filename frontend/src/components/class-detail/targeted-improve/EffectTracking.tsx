import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useMemo } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { CheckCircle2, Clock, AlertCircle, Eye, Hand, XCircle, TrendingUp, TrendingDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { EffectData } from "./targetedData";

interface EffectTrackingProps {
  data: EffectData | null;
  studentName?: string;
}

const STATUS_ICONS = {
  done: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />,
  pending: <Clock className="w-3.5 h-3.5 text-amber-500" />,
  future: <Clock className="w-3.5 h-3.5 text-muted-foreground/40" />,
};

export function EffectTracking({ data, studentName }: EffectTrackingProps) {
  const { t, locale } = useLocale();
  const alertColors = useMemo(
    () => ({
      green: { bg: "bg-emerald-50", border: "border-emerald-200", text: "text-emerald-700", label: t("classDetail.正常 按时完成 正确率达标") },
      yellow: { bg: "bg-amber-50", border: "border-amber-200", text: "text-amber-700", label: t("classDetail.关注 完成但正确率偏低") },
      red: { bg: "bg-red-50", border: "border-red-200", text: "text-destructive", label: t("classDetail.预警 未完成或严重超时") },
    }),
    [t]
  );

  if (!data) {
    return (
      <Card className="flex-1 min-w-[320px]">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold">{t("classDetail.推送执行与效果追踪")}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">{t("classDetail.trackAfterPush")}</p>
        </CardContent>
      </Card>
    );
  }

  const alert = alertColors[data.alertLevel];

  return (
    <Card className="flex-1 min-w-[320px]" data-tour="ti-tracking">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">{studentName ? t("classDetail.pushTrackingTitleWithName", { name: studentName }) : t("classDetail.推送执行与效果追踪")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-xs">
        {/* Push status */}
        <div className="rounded-lg border border-border/50 p-3 space-y-1 text-[11px]">
          <p>{t("classDetail.pushStatusLabel")}<strong className="text-foreground">{t("classDetail.pushedWithDate", { date: data.pushDate })}</strong></p>
          <p>{t("classDetail.studentSideLabel")}<Badge variant="secondary" className="text-[10px]">{t("classDetail.receivedAndViewed")}</Badge></p>
          <p>{t("classDetail.parentSideLabel")}<Badge variant="secondary" className="text-[10px]">{t("classDetail.notifiedAndConfirmed")}</Badge></p>
        </div>

        {/* Execution timeline */}
        <div className="rounded-lg border border-border/50 p-3 space-y-1.5">
          <p className="font-semibold text-foreground text-[11px]">{t("classDetail.executionTracking")}</p>
          {data.days.slice(0, 5).map(d => (
            <div key={d.day} className="flex items-center gap-2 text-[11px]">
              {STATUS_ICONS[d.status]}
              <span className="w-12 text-muted-foreground">{d.label}</span>
              <span className="text-foreground">{d.task}</span>
              <span className={cn("ml-auto text-[10px]",
                d.status === "done" ? "text-emerald-600" : d.status === "pending" ? "text-amber-600" : "text-muted-foreground"
              )}>
                {d.status === "done" ? t("classDetail.doneCheck") : d.status === "pending" ? t("classDetail.pendingLabel") : ""}
              </span>
            </div>
          ))}
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-2">
          <div className="rounded-lg border border-border/50 p-2 text-center">
            <p className="text-[10px] text-muted-foreground">{t("classDetail.completionRate")}</p>
            <p className="text-base font-bold text-foreground">{data.completionRate}%</p>
            <Progress value={data.completionRate} className="h-1 mt-1" />
          </div>
          <div className="rounded-lg border border-border/50 p-2 text-center">
            <p className="text-[10px] text-muted-foreground">{t("classDetail.correctRate")}</p>
            <p className="text-base font-bold text-foreground">{data.correctRate}%</p>
            <Progress value={data.correctRate} className="h-1 mt-1" />
          </div>
          <div className="rounded-lg border border-border/50 p-2 text-center">
            <p className="text-[10px] text-muted-foreground">{t("classDetail.timeInvested")}</p>
            <p className="text-base font-bold text-foreground">{t("classDetail.minutesLabel", { value: data.timeSpent })}</p>
            <p className="text-[10px] text-muted-foreground">{t("classDetail.expectedTimeLabel", { value: data.expectedTime })}</p>
          </div>
        </div>

        {/* Alert */}
        <div className={cn("rounded-lg border p-3", alert.bg, alert.border)}>
          <p className={cn("text-[11px] font-semibold", alert.text)}>{alert.label}</p>
        </div>

        {/* Dynamic adjustment rules */}
        <div className="rounded-lg border border-border/50 p-3 space-y-1 text-[11px] text-muted-foreground">
          <p className="font-semibold text-foreground">{t("classDetail.dynamicAdjustmentRules")}</p>
          <p>{t("classDetail.ruleLowCompletion")}</p>
          <p>{t("classDetail.ruleHighAccuracy")}</p>
          <p>{t("classDetail.ruleNoLogin")}</p>
        </div>

        {/* History */}
        <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 space-y-1.5">
          <p className="font-semibold text-foreground text-[11px]">{t("classDetail.historyPlanEffect", { total: data.totalPlans, avg: data.avgCompletion })}</p>
          {data.history.map(h => (
            <div key={h.name} className="flex items-center justify-between text-[11px]">
              <span className="text-muted-foreground">{h.name}</span>
              <div className="flex items-center gap-2">
                <span>{t("classDetail.completionRate")}<strong className="text-foreground">{h.completionRate}%</strong></span>
                <span className="flex items-center gap-0.5">
                  {h.improvement > 5 ? <TrendingUp className="w-3 h-3 text-emerald-600" /> : <TrendingDown className="w-3 h-3 text-destructive" />}
                  {t("classDetail.improvementPoints", { value: h.improvement })}
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Actions */}
        <div className="flex gap-1.5">
          <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px]"><Eye className="w-3 h-3 mr-0.5" />{t("classDetail.viewRealtimeData")}</Button>
          <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px]"><Hand className="w-3 h-3 mr-0.5" />{t("classDetail.manualIntervention")}</Button>
          <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px] text-destructive"><XCircle className="w-3 h-3 mr-0.5" />{t("classDetail.terminatePlan")}</Button>
        </div>
      </CardContent>
    </Card>
  );
}
