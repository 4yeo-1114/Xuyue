import { useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { StudentCandidate, ImprovePlan, EffectData, PlanPreviewData } from "./targetedData";

export interface TipConfig {
  id: string;
  text: string;
  borderColor: string;
  bgColor: string;
}

function Tip({ tip, onClose }: { tip: TipConfig; onClose: () => void }) {
  return (
    <div className={cn("flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium animate-fade-in border-l-[3px]", tip.bgColor, tip.borderColor)}>
      <span className="flex-1 text-foreground">{tip.text}</span>
      <button onClick={onClose} className="text-muted-foreground hover:text-foreground shrink-0">
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

export function useTargetedTips() {
  const { t, locale } = useLocale();

  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const dismiss = (id: string) => setDismissed(prev => new Set(prev).add(id));
  return { dismissed, dismiss };
}

export function InlineTargetedTip({ tip, dismissed, onDismiss }: { tip: TipConfig; dismissed: Set<string>; onDismiss: (id: string) => void }) {
  if (dismissed.has(tip.id)) return null;
  return <Tip tip={tip} onClose={() => onDismiss(tip.id)} />;
}

/** Generate dynamic tips based on current data */
export function generateTargetedTips(
  student: StudentCandidate | null,
  plan: ImprovePlan | undefined,
  effectData: EffectData | null,
  planPreview: PlanPreviewData | null,
  t: (key: string, params?: Record<string, string | number>) => string,
) {
  const name = student?.name || t("classDetail.学生");
  const score = student?.score ?? 0;
  const targetDelta = plan ? (plan.targetTo - plan.targetFrom) : 0;

  return {
    warningStudent: {
      id: "ti-warning-student",
      text: score < 60
        ? t("classDetail.tipWarningGenerate", { name, score })
        : t("classDetail.tipWarningDiagnose", { name, score }),
      borderColor: "border-l-destructive",
      bgColor: "bg-destructive/5",
    } as TipConfig,

    planGenerated: {
      id: "ti-plan-generated",
      text: plan
        ? t("classDetail.tipPlanGenerated", { duration: plan.duration, delta: targetDelta, from: plan.targetFrom, to: plan.targetTo })
        : t("classDetail.方案待生成"),
      borderColor: "border-l-success",
      bgColor: "bg-success/5",
    } as TipConfig,

    timeConflict: {
      id: "ti-time-conflict",
      text: planPreview?.conflict
        ? t("classDetail.tipTimeConflict", { conflict: planPreview.conflict })
        : t("classDetail.暂无时间冲突"),
      borderColor: "border-l-warning",
      bgColor: "bg-warning/5",
    } as TipConfig,

    lowCompletion: {
      id: "ti-low-completion",
      text: effectData
        ? t("classDetail.tipLowCompletion", {
            name,
            rate: effectData.completionRate,
            suffix: effectData.completionRate < 50 ? t("classDetail.建议关注") : t("classDetail.继续保持"),
          })
        : t("classDetail.完成率待追踪"),
      borderColor: effectData && effectData.completionRate < 50 ? "border-l-destructive" : "border-l-warning",
      bgColor: effectData && effectData.completionRate < 50 ? "bg-destructive/5" : "bg-warning/5",
    } as TipConfig,

    parentComm: {
      id: "ti-parent-comm",
      text: t("classDetail.tipParentComm", { name }),
      borderColor: "border-l-primary",
      bgColor: "bg-primary/5",
    } as TipConfig,

    historyEffect: {
      id: "ti-history-effect",
      text: effectData
        ? t("classDetail.tipHistoryEffect", { total: effectData.totalPlans, avg: effectData.avgCompletion })
        : t("classDetail.暂无历史方案"),
      borderColor: "border-l-primary",
      bgColor: "bg-primary/5",
    } as TipConfig,

    noLogin: {
      id: "ti-no-login",
      text: effectData && effectData.completionRate < 40
        ? t("classDetail.tipLowEngagement", { name })
        : t("classDetail.tipNormalEngagement", { name }),
      borderColor: "border-l-warning",
      bgColor: "bg-warning/5",
    } as TipConfig,
  };
}
