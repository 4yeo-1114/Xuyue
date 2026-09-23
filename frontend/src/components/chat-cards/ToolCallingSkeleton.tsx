import { Skeleton } from "@/components/ui/skeleton";
import { Sparkles } from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";

export function ToolCallingSkeleton() {
  const { t } = useLocale();
  return (
    <div className="border border-border/60 rounded-xl my-2 bg-card/80 backdrop-blur-sm overflow-hidden shadow-sm animate-fade-in">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2.5 bg-primary/5 border-b border-border/40">
        <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center animate-pulse">
          <Sparkles className="w-3.5 h-3.5 text-primary" />
        </div>
        <Skeleton className="h-4 w-20" />
        <Skeleton className="h-4 w-10 ml-auto rounded-full" />
      </div>

      {/* Rows */}
      <div className="divide-y divide-border/30">
        {[1, 2, 3].map((i) => (
          <div key={i} className="px-3 py-2.5 space-y-2">
            <div className="flex items-center gap-2">
              <Skeleton className="h-4 w-16" />
              <Skeleton className="h-3 w-12" />
              <Skeleton className="h-5 w-14 rounded-full ml-auto" />
            </div>
            <Skeleton className="h-1.5 w-full rounded-full" />
            <div className="flex gap-1.5">
              <Skeleton className="h-4 w-12 rounded-md" />
              <Skeleton className="h-4 w-16 rounded-md" />
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="flex items-center gap-2 px-3 py-2 border-t border-border/40 bg-muted/20">
        <span className="text-[11px] text-muted-foreground animate-pulse flex items-center gap-1">
          <Sparkles className="w-3 h-3" />
          {t("chatCards.toolCalling.querying")}
        </span>
      </div>
    </div>
  );
}
