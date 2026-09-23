import { useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface TipConfig {
  id: string;
  textKey: string;
  borderColor: string;
  bgColor: string;
}

function Tip({ tip, onClose }: { tip: TipConfig; onClose: () => void }) {
  const { t } = useLocale();
  return (
    <div className={cn("flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium animate-fade-in border-l-[3px]", tip.bgColor, tip.borderColor)}>
      <span className="flex-1 text-foreground">{t(tip.textKey)}</span>
      <button onClick={onClose} className="text-muted-foreground hover:text-foreground shrink-0">
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

export function useReviewTips() {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const dismiss = (id: string) => setDismissed(prev => new Set(prev).add(id));
  return { dismissed, dismiss };
}

export function InlineReviewTip({ tip, dismissed, onDismiss }: { tip: TipConfig; dismissed: Set<string>; onDismiss: (id: string) => void }) {
  if (dismissed.has(tip.id)) return null;
  return <Tip tip={tip} onClose={() => onDismiss(tip.id)} />;
}

export const REVIEW_TIPS = {
  highFreqError: {
    id: "cr-high-freq",
    textKey: "classDetail.作文结构20人错 建议优先讲评",
    borderColor: "border-l-destructive",
    bgColor: "bg-destructive/5",
  },
  durationWarning: {
    id: "cr-duration",
    textKey: "classDetail.建议30分钟 当前仅20分钟",
    borderColor: "border-l-warning",
    bgColor: "bg-warning/5",
  },
  pptReady: {
    id: "cr-ppt-ready",
    textKey: "classDetail.PPT已生成 15页25分钟",
    borderColor: "border-l-success",
    bgColor: "bg-success/5",
  },
  answerProgress: {
    id: "cr-answer-progress",
    textKey: "classDetail.30 36人已答 正确率61",
    borderColor: "border-l-primary",
    bgColor: "bg-primary/5",
  },
  lowUnderstand: {
    id: "cr-low-understand",
    textKey: "classDetail.听懂率66 26 似懂非懂",
    borderColor: "border-l-warning",
    bgColor: "bg-warning/5",
  },
  pendingPush: {
    id: "cr-pending-push",
    textKey: "classDetail.分层作业已生成 一键推送",
    borderColor: "border-l-primary",
    bgColor: "bg-primary/5",
  },
  pendingTracking: {
    id: "cr-pending-tracking",
    textKey: "classDetail.当堂检测待推送 作业22 00截止",
    borderColor: "border-l-warning",
    bgColor: "bg-warning/5",
  },
} as const;
