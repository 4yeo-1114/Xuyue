import { useState, useMemo, useCallback } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { X, AlertTriangle, Bell, Lightbulb } from "lucide-react";
import { cn } from "@/lib/utils";

const DISMISSED_KEY = "dashboard-tips-dismissed";

interface TipItem {
  id: string;
  icon: React.ElementType;
  text: string;
  type: "warning" | "info" | "hint";
}

interface DashboardDailyTipsProps {
  warningCount: number;
  completionRate: number;
  todoCount: number;
}

export function DashboardDailyTips({ warningCount, completionRate, todoCount }: DashboardDailyTipsProps) {
  const { t, locale } = useLocale();

  const [dismissed, setDismissed] = useState<Set<string>>(() => {
    try {
      const today = new Date().toDateString();
      const saved = localStorage.getItem(DISMISSED_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.date === today) return new Set(parsed.ids);
      }
    } catch {}
    return new Set<string>();
  });

  const dismiss = useCallback((id: string) => {
    setDismissed((prev) => {
      const next = new Set(prev);
      next.add(id);
      try {
        localStorage.setItem(DISMISSED_KEY, JSON.stringify({ date: new Date().toDateString(), ids: [...next] }));
      } catch {}
      return next;
    });
  }, []);

  const tips = useMemo<TipItem[]>(() => {
    const list: TipItem[] = [];
    if (warningCount > 10) {
      list.push({
        id: "high-warning",
        icon: AlertTriangle,
        text: t("classDetail.tipWarning", { count: warningCount }),
        type: "warning",
      });
    }
    if (completionRate < 90) {
      list.push({
        id: "low-completion",
        icon: Lightbulb,
        text: t("classDetail.tipCompletion", { rate: completionRate }),
        type: "hint",
      });
    }
    if (todoCount > 0) {
      const urgent = Math.min(1, todoCount);
      const normal = todoCount - urgent;
      list.push({
        id: "todos",
        icon: Bell,
        text: t("classDetail.tipTodos", { count: todoCount, urgent, normal }),
        type: "info",
      });
    }
    return list;
  }, [t, warningCount, completionRate, todoCount]);

  const visibleTips = tips.filter((t) => !dismissed.has(t.id));
  if (visibleTips.length === 0) return null;

  const typeStyles: Record<string, string> = {
    warning: "bg-amber-50 border-l-4 border-l-amber-500 text-amber-900",
    info: "bg-blue-50 border-l-4 border-l-blue-500 text-blue-900",
    hint: "bg-emerald-50 border-l-4 border-l-emerald-500 text-emerald-900",
  };

  return (
    <div className="space-y-2 animate-fade-in mb-4">
      {visibleTips.map((tip) => {
        const Icon = tip.icon;
        return (
          <div key={tip.id} className={cn("flex items-center gap-3 px-4 py-3 rounded-xl text-sm transition-all", typeStyles[tip.type])}>
            <Icon className="w-4 h-4 shrink-0 opacity-70" />
            <span className="flex-1">{tip.text}</span>
            <button onClick={() => dismiss(tip.id)} className="shrink-0 opacity-50 hover:opacity-100 transition-opacity" aria-label={t("classDetail.关闭提示")}>
              <X className="w-4 h-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
