import { useState, useMemo, useCallback } from "react";
import { X, Bell, AlertTriangle, Lightbulb, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import { useLocale } from "@/contexts/LocaleContext";

const DISMISSED_KEY = "daily-tips-dismissed";

interface TipItem {
  id: string;
  icon: React.ElementType;
  text: string;
  type: "welcome" | "warning" | "info" | "hint";
  /** data-tour target to highlight briefly */
  highlight?: string;
}

interface DailyTipsProps {
  selectedClass: string;
  hasWarningStudents?: boolean;
  pendingGrading?: number;
  behindSchedule?: boolean;
}

export function DailyTips({
  selectedClass,
  hasWarningStudents = true,
  pendingGrading = 12,
  behindSchedule = false,
}: DailyTipsProps) {
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
        localStorage.setItem(
          DISMISSED_KEY,
          JSON.stringify({ date: new Date().toDateString(), ids: [...next] })
        );
      } catch {}
      return next;
    });
  }, []);

  const greeting = useMemo(() => {
    const h = new Date().getHours();
    if (h < 12) return t("home.tips.greeting.morning");
    if (h < 18) return t("home.tips.greeting.afternoon");
    return t("home.tips.greeting.evening");
  }, [t, locale]);

  const tips = useMemo<TipItem[]>(() => {
    const list: TipItem[] = [];

    list.push({
      id: "welcome",
      icon: Clock,
      text: greeting,
      type: "welcome",
    });

    if (!selectedClass) {
      list.push({
        id: "no-class",
        icon: AlertTriangle,
        text: t("home.tips.noClass"),
        type: "warning",
        highlight: "[data-tour='top-filters']",
      });
    }

    if (pendingGrading > 0) {
      list.push({
        id: "pending-grading",
        icon: Bell,
        text: t("home.tips.pendingGrading", { count: pendingGrading }),
        type: "info",
        highlight: "[data-tour='grading-entry']",
      });
    }

    if (hasWarningStudents) {
      list.push({
        id: "warning-students",
        icon: AlertTriangle,
        text: t("home.tips.warningStudents"),
        type: "warning",
        highlight: "[data-tour='student-matrix']",
      });
    }

    if (behindSchedule) {
      list.push({
        id: "behind-schedule",
        icon: Lightbulb,
        text: t("home.tips.behindSchedule"),
        type: "hint",
      });
    }

    return list;
  }, [selectedClass, hasWarningStudents, pendingGrading, behindSchedule, greeting, t, locale]);

  const visibleTips = tips.filter((tip) => !dismissed.has(tip.id));

  if (visibleTips.length === 0) return null;

  const typeStyles: Record<string, string> = {
    welcome: "bg-sky-50 border-l-4 border-l-sky-500 text-sky-900",
    warning: "bg-amber-50 border-l-4 border-l-amber-500 text-amber-900",
    info: "bg-blue-50 border-l-4 border-l-blue-500 text-blue-900",
    hint: "bg-emerald-50 border-l-4 border-l-emerald-500 text-emerald-900",
  };

  return (
    <div className="space-y-2 animate-fade-in">
      {visibleTips.map((tip) => {
        const Icon = tip.icon;
        return (
          <div
            key={tip.id}
            className={cn(
              "flex items-center gap-3 px-4 py-3 rounded-xl text-sm transition-all",
              typeStyles[tip.type]
            )}
          >
            <Icon className="w-4 h-4 shrink-0 opacity-70" />
            <span className="flex-1">{tip.text}</span>
            <button
              onClick={() => dismiss(tip.id)}
              className="shrink-0 opacity-50 hover:opacity-100 transition-opacity"
              aria-label={t("home.tips.dismiss")}
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
