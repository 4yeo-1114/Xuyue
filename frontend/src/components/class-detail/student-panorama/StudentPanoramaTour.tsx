import { useState, useCallback, createContext, useContext, useMemo } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { X, AlertTriangle, Lightbulb, Pencil, CheckCircle2, BarChart3 } from "lucide-react";
import { cn } from "@/lib/utils";
import { GenericTour, TourStep } from "@/components/shared/GenericTour";

/* ── Tour Steps ── */
function buildTourSteps(t: (key: string, params?: Record<string, string | number>) => string): TourStep[] {
  return [
  {
    targetSelector: "[data-tour='sp-student-list']",
    title: t("studentAnalysis.tour.listTitle"),
    description: t("studentAnalysis.tour.listDescription"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "left",
  },
  {
    targetSelector: "[data-tour='sp-profile-panel']",
    title: t("studentAnalysis.tour.profileTitle"),
    description: t("studentAnalysis.tour.profileDescription"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "left",
  },
  {
    targetSelector: "[data-tour='sp-score-history']",
    title: t("studentAnalysis.tour.historyTitle"),
    description: t("studentAnalysis.tour.historyDescription"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "top",
  },
  {
    targetSelector: "[data-tour='sp-learning-goal']",
    title: t("studentAnalysis.tour.goalTitle"),
    description: t("studentAnalysis.tour.goalDescription"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "top",
  },
  {
    targetSelector: "[data-tour='sp-radar']",
    title: t("studentAnalysis.tour.radarTitle"),
    description: t("studentAnalysis.tour.radarDescription"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "top",
  },
  {
    targetSelector: "[data-tour='sp-wrong-timeline']",
    title: t("studentAnalysis.tour.wrongTitle"),
    description: t("studentAnalysis.tour.wrongDescription"),
    buttonLabel: t("home.tour.complete"),
    arrowPosition: "top",
  },
  ];
}

/* ── Tour-only wrapper (no more daily tips here) ── */
export function StudentPanoramaTour() {
  const { t } = useLocale();
  const steps = useMemo(() => buildTourSteps(t), [t]);

  return (
    <GenericTour
      storageKey="student-panorama-tour-done"
      steps={steps}
      completeTitle={t("studentAnalysis.tour.completeTitle")}
      completeDescription={t("studentAnalysis.tour.completeDescription")}
    />
  );
}

/* ── Inline Tip Component ── */
const DISMISSED_KEY = "sp-tips-dismissed";

const typeStyles: Record<string, string> = {
  warning: "bg-amber-50 border-l-4 border-l-amber-500 text-amber-900",
  info: "bg-blue-50 border-l-4 border-l-blue-500 text-blue-900",
  hint: "bg-emerald-50 border-l-4 border-l-emerald-500 text-emerald-900",
};

interface InlineTipProps {
  id: string;
  icon: React.ElementType;
  text: string;
  type: "warning" | "info" | "hint";
  show: boolean;
}

// Shared dismiss state via context
interface TipDismissContextType {
  isDismissed: (id: string) => boolean;
  dismiss: (id: string) => void;
}

const TipDismissContext = createContext<TipDismissContextType>({
  isDismissed: () => false,
  dismiss: () => {},
});

export function TipDismissProvider({ children }: { children: React.ReactNode }) {
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

  const isDismissed = useCallback((id: string) => dismissed.has(id), [dismissed]);

  const value = useMemo(() => ({ isDismissed, dismiss }), [isDismissed, dismiss]);

  return (
    <TipDismissContext.Provider value={value}>
      {children}
    </TipDismissContext.Provider>
  );
}

export function InlineTip({ id, icon: Icon, text, type, show }: InlineTipProps) {
  const { t } = useLocale();
  const { isDismissed, dismiss } = useContext(TipDismissContext);

  if (!show || isDismissed(id)) return null;

  return (
    <div className={cn("flex items-center gap-3 px-4 py-2 rounded-xl text-sm transition-all animate-fade-in mb-3", typeStyles[type])}>
      <Icon className="w-4 h-4 shrink-0 opacity-70" />
      <span className="flex-1">{text}</span>
      <button onClick={() => dismiss(id)} className="shrink-0 opacity-50 hover:opacity-100 transition-opacity" aria-label={t("studentAnalysis.tour.close")}>
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}

// Re-export icons for use in ProfilePanel
export { AlertTriangle as TipAlertTriangle, Lightbulb as TipLightbulb, Pencil as TipPencil, CheckCircle2 as TipCheckCircle2, BarChart3 as TipBarChart3 };
