import { useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useLocale } from "@/contexts/LocaleContext";

export interface SmartGenTip {
  id: string;
  textKey: string;
  borderColor: string;
  bgColor: string;
}

export const SMART_GEN_TIPS: Record<string, SmartGenTip> = {
  firstUse: {
    id: "sg-first-use",
    textKey: "smartGen.tips.firstUse",
    borderColor: "border-l-blue-500",
    bgColor: "bg-blue-50 dark:bg-blue-950/30",
  },
  studentProfile: {
    id: "sg-student-profile",
    textKey: "smartGen.tips.studentProfile",
    borderColor: "border-l-yellow-500",
    bgColor: "bg-yellow-50 dark:bg-yellow-950/30",
  },
  newCombo: {
    id: "sg-new-combo",
    textKey: "smartGen.tips.newCombo",
    borderColor: "border-l-blue-500",
    bgColor: "bg-blue-50 dark:bg-blue-950/30",
  },
  genComplete: {
    id: "sg-gen-complete",
    textKey: "smartGen.tips.genComplete",
    borderColor: "border-l-green-500",
    bgColor: "bg-green-50 dark:bg-green-950/30",
  },
  toolRecommend: {
    id: "sg-tool-recommend",
    textKey: "smartGen.tips.toolRecommend",
    borderColor: "border-l-blue-500",
    bgColor: "bg-blue-50 dark:bg-blue-950/30",
  },
  topRated: {
    id: "sg-top-rated",
    textKey: "smartGen.tips.topRated",
    borderColor: "border-l-green-500",
    bgColor: "bg-green-50 dark:bg-green-950/30",
  },
  pendingWork: {
    id: "sg-pending-work",
    textKey: "smartGen.tips.pendingWork",
    borderColor: "border-l-yellow-500",
    bgColor: "bg-yellow-50 dark:bg-yellow-950/30",
  },
};

export function useSmartGenTips() {
  const today = new Date().toDateString();
  const [dismissed, setDismissed] = useState<Record<string, boolean>>(() => {
    try {
      const raw = localStorage.getItem("sg-tips-dismissed");
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed._date === today) return parsed;
      }
    } catch {}
    return { _date: today };
  });

  const dismiss = (id: string) => {
    setDismissed((prev) => {
      const next = { ...prev, [id]: true };
      try { localStorage.setItem("sg-tips-dismissed", JSON.stringify(next)); } catch {}
      return next;
    });
  };

  return { dismissed, dismiss };
}

interface InlineSmartGenTipProps {
  tip: SmartGenTip;
  dismissed: Record<string, boolean>;
  onDismiss: (id: string) => void;
}

export function InlineSmartGenTip({ tip, dismissed, onDismiss }: InlineSmartGenTipProps) {
  const { t } = useLocale();
  if (dismissed[tip.id]) return null;
  return (
    <div className={cn(
      "flex items-center justify-between px-3 py-2 rounded-lg border-l-4 text-xs animate-fade-in",
      tip.borderColor, tip.bgColor
    )}>
      <span className="text-foreground font-medium">{t(tip.textKey)}</span>
      <button onClick={() => onDismiss(tip.id)} className="text-muted-foreground hover:text-foreground ml-2 shrink-0">
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
