import { Sparkles } from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";
import { cn } from "@/lib/utils";

interface AIGeneratedBadgeProps {
  className?: string;
}

/** AI 内容统一显式标识徽标（GB 45438《人工智能生成合成内容标识办法》） */
export function AIGeneratedBadge({ className }: AIGeneratedBadgeProps) {
  const { t } = useLocale();
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full border border-primary/25 bg-primary/10 px-2 py-0.5 text-[11px] font-semibold leading-none text-primary",
        className,
      )}
    >
      <Sparkles className="h-3 w-3" />
      {t("common.aiGenerated")}
    </span>
  );
}
