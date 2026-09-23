import { useState, useCallback, createContext, useContext, useMemo } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { X, AlertTriangle, Lightbulb, TrendingUp, TrendingDown, Sparkles, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import { GenericTour, TourStep } from "@/components/shared/GenericTour";

/* ── Tour Steps ── */
function buildTourSteps(t: (key: string, params?: Record<string, string | number>) => string): TourStep[] {
  return [
  {
    targetSelector: "[data-tour='ca-scope']",
    title: t("classDetail.对标范围"),
    description: t("classDetail.选择对比对象 当前显示年级内部排名"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "top",
  },
  {
    targetSelector: "[data-tour='ca-ranking']",
    title: t("classDetail.年级排名"),
    description: t("classDetail.本班年级排名 与前后班级差距一目了然"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "left",
  },
  {
    targetSelector: "[data-tour='ca-metrics']",
    title: t("classDetail.核心指标对比"),
    description: t("classDetail.多维度数据对比 颜色标记优劣势"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "left",
  },
  {
    targetSelector: "[data-tour='ca-findings']",
    title: t("classDetail.关键发现"),
    description: t("classDetail.AI智能诊断 快速定位优劣势"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "top",
  },
  {
    targetSelector: "[data-tour='ca-radar']",
    title: t("classDetail.多维度雷达图"),
    description: t("classDetail.可视化对比 红色虚线 对标班级"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "top",
  },
  {
    targetSelector: "[data-tour='ca-trend']",
    title: t("classDetail.历史趋势"),
    description: t("classDetail.近5次考试走势 看排名变化趋势"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "top",
  },
  {
    targetSelector: "[data-tour='ca-experience']",
    title: t("classDetail.可量化经验"),
    description: t("classDetail.学习优秀班级经验 可申请跟岗学习"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "left",
  },
  {
    targetSelector: "[data-tour='ca-chasing']",
    title: t("classDetail.追赶计划"),
    description: t("classDetail.系统生成完整追赶方案 点击启动执行"),
    buttonLabel: t("home.tour.complete"),
    arrowPosition: "left",
  },
  ];
}

export function CompareAnalysisTour() {
  const { t, locale } = useLocale();
  const steps = useMemo(() => buildTourSteps(t), [t]);

  return (
    <GenericTour
      storageKey="compare-analysis-tour-done"
      steps={steps}
      completeTitle={t("classDetail.对比分析引导完成")}
      completeDescription={t("classDetail.找到差距 制定计划 开始追赶")}
    />
  );
}

/* ── Inline Tip (shared dismiss context) ── */
const DISMISSED_KEY = "ca-tips-dismissed";

const typeStyles: Record<string, string> = {
  warning: "bg-amber-50 border-l-4 border-l-amber-500 text-amber-900",
  info: "bg-blue-50 border-l-4 border-l-blue-500 text-blue-900",
  hint: "bg-emerald-50 border-l-4 border-l-emerald-500 text-emerald-900",
};

interface TipDismissContextType {
  isDismissed: (id: string) => boolean;
  dismiss: (id: string) => void;
}

const TipDismissContext = createContext<TipDismissContextType>({
  isDismissed: () => false,
  dismiss: () => {},
});

export function CompareTipProvider({ children }: { children: React.ReactNode }) {
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

interface InlineTipProps {
  id: string;
  icon: React.ElementType;
  text: string;
  type: "warning" | "info" | "hint";
  show: boolean;
}

export function CompareInlineTip({ id, icon: Icon, text, type, show }: InlineTipProps) {
  const { t } = useLocale();
  const { isDismissed, dismiss } = useContext(TipDismissContext);
  if (!show || isDismissed(id)) return null;

  return (
    <div className={cn("flex items-center gap-3 px-4 py-2 rounded-xl text-sm transition-all animate-fade-in mb-3", typeStyles[type])}>
      <Icon className="w-4 h-4 shrink-0 opacity-70" />
      <span className="flex-1">{text}</span>
      <button onClick={() => dismiss(id)} className="shrink-0 opacity-50 hover:opacity-100 transition-opacity" aria-label={t("classDetail.关闭提示")}>
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}

// Re-export icons for convenience
export {
  AlertTriangle as CaTipAlert,
  Lightbulb as CaTipLightbulb,
  TrendingUp as CaTipTrendUp,
  TrendingDown as CaTipTrendDown,
  Sparkles as CaTipSparkles,
  Clock as CaTipClock,
};
