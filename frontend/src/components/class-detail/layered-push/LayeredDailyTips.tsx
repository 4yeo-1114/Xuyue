import { useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

/** 行内提示：text 由页面用真实数据算好传入（不再有写死的数字） */
export interface TipConfig {
  id: string;
  text: string;
  borderColor: string;
  bgColor: string;
}

function Tip({ tip, onClose }: { tip: TipConfig; onClose: () => void }) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium animate-fade-in border-l-[3px]",
        tip.bgColor,
        tip.borderColor,
      )}
    >
      <span className="flex-1 text-foreground">{tip.text}</span>
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
