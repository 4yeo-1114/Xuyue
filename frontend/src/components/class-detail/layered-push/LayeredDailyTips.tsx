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
    <div
      className={cn(
        "flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium animate-fade-in border-l-[3px]",
        tip.bgColor,
        tip.borderColor,
      )}
    >
      <span className="flex-1 text-foreground">{t(tip.textKey)}</span>
      <button
        onClick={onClose}
        className="text-muted-foreground hover:text-foreground shrink-0"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

export function useLayeredTips() {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const dismiss = (id: string) => setDismissed((prev) => new Set(prev).add(id));
  return { dismissed, dismiss };
}

export function InlineLayeredTip({
  tip,
  dismissed,
  onDismiss,
}: {
  tip: TipConfig;
  dismissed: Set<string>;
  onDismiss: (id: string) => void;
}) {
  if (dismissed.has(tip.id)) return null;
  return <Tip tip={tip} onClose={() => onDismiss(tip.id)} />;
}

export const LAYERED_TIPS = {
  tierImbalance: {
    id: "lp-tier-imbalance",
    textKey: "layeredPush.tips.tierImbalance",
    borderColor: "border-l-warning",
    bgColor: "bg-warning/5",
  },
  timeImbalance: {
    id: "lp-time-imbalance",
    textKey: "layeredPush.tips.timeImbalance",
    borderColor: "border-l-warning",
    bgColor: "bg-warning/5",
  },
  unsyncedStudents: {
    id: "lp-unsynced",
    textKey: "layeredPush.tips.unsynced",
    borderColor: "border-l-destructive",
    bgColor: "bg-destructive/5",
  },
  lowCompletion: {
    id: "lp-low-completion",
    textKey: "layeredPush.tips.lowCompletion",
    borderColor: "border-l-destructive",
    bgColor: "bg-destructive/5",
  },
  urgeReminder: {
    id: "lp-urge-reminder",
    textKey: "layeredPush.tips.urgeReminder",
    borderColor: "border-l-warning",
    bgColor: "bg-warning/5",
  },
  interactionActive: {
    id: "lp-interaction-active",
    textKey: "layeredPush.tips.interactionActive",
    borderColor: "border-l-primary",
    bgColor: "bg-primary/5",
  },
  weeklyReport: {
    id: "lp-weekly-report",
    textKey: "layeredPush.tips.weeklyReport",
    borderColor: "border-l-primary",
    bgColor: "bg-primary/5",
  },
} as const;
