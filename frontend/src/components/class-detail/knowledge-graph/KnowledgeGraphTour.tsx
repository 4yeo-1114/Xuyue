import { useState, useCallback, createContext, useContext, useMemo } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { X, AlertTriangle, Lightbulb, BarChart3, Users, BookOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import { GenericTour, TourStep } from "@/components/shared/GenericTour";

/* ── Tour Steps ── */
function buildTourSteps(t: (key: string, params?: Record<string, string | number>) => string): TourStep[] {
  return [
  {
    targetSelector: "[data-tour='kg-tree']",
    title: t("classDetail.知识点目录"),
    description: t("classDetail.知识点层级结构 颜色标记掌握情况"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "left",
  },
  {
    targetSelector: "[data-tour='kg-radial']",
    title: t("classDetail.径向知识图谱"),
    description: t("classDetail.可视化知识网络 圆点 知识点 连线 关联关系 颜色 掌握度"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "top",
  },
  {
    targetSelector: "[data-tour='kg-center']",
    title: t("classDetail.综合掌握度"),
    description: t("classDetail.班级整体掌握度62 点击任意节点查看详情"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "left",
  },
  {
    targetSelector: "[data-tour='kg-detail']",
    title: t("classDetail.详情面板"),
    description: t("classDetail.点击知识点 右侧显示详细分析和教学建议"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "left",
  },
  {
    targetSelector: "[data-tour='kg-students']",
    title: t("classDetail.学生分布"),
    description: t("classDetail.该知识点学生掌握分布 22人薄弱需重点关注"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "left",
  },
  {
    targetSelector: "[data-tour='kg-resources']",
    title: t("classDetail.推荐资源"),
    description: t("classDetail.系统推荐针对性资源 微课练习教案一键使用"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "left",
  },
  {
    targetSelector: "[data-tour='kg-actions']",
    title: t("classDetail.快捷操作"),
    description: t("classDetail.快速开展针对性教学 多种方式灵活选择"),
    buttonLabel: t("home.tour.complete"),
    arrowPosition: "left",
  },
  ];
}

export function KnowledgeGraphTour() {
  const { t, locale } = useLocale();
  const steps = useMemo(() => buildTourSteps(t), [t]);

  return (
    <GenericTour
      storageKey="knowledge-graph-tour-done"
      steps={steps}
      completeTitle={t("classDetail.知识图谱引导完成")}
      completeDescription={t("classDetail.红色节点优先教学 连线发现知识断层")}
    />
  );
}

/* ── Inline Tip System ── */
const DISMISSED_KEY = "kg-tips-dismissed";

const typeStyles: Record<string, string> = {
  warning: "bg-red-50 border-l-4 border-l-red-500 text-red-900",
  info: "bg-blue-50 border-l-4 border-l-blue-500 text-blue-900",
  hint: "bg-emerald-50 border-l-4 border-l-emerald-500 text-emerald-900",
  amber: "bg-amber-50 border-l-4 border-l-amber-500 text-amber-900",
};

interface TipDismissContextType {
  isDismissed: (id: string) => boolean;
  dismiss: (id: string) => void;
}

const TipDismissContext = createContext<TipDismissContextType>({
  isDismissed: () => false,
  dismiss: () => {},
});

export function KGTipProvider({ children }: { children: React.ReactNode }) {
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

interface KGInlineTipProps {
  id: string;
  icon: React.ElementType;
  text: string;
  type: "warning" | "info" | "hint" | "amber";
  show: boolean;
}

export function KGInlineTip({ id, icon: Icon, text, type, show }: KGInlineTipProps) {
  const { t } = useLocale();
  const { isDismissed, dismiss } = useContext(TipDismissContext);
  if (!show || isDismissed(id)) return null;

  return (
    <div className={cn("flex items-center gap-3 px-4 py-2 rounded-xl text-sm transition-all animate-fade-in mb-2", typeStyles[type])}>
      <Icon className="w-4 h-4 shrink-0 opacity-70" />
      <span className="flex-1">{text}</span>
      <button onClick={() => dismiss(id)} className="shrink-0 opacity-50 hover:opacity-100 transition-opacity" aria-label={t("classDetail.关闭提示")}>
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}

export { AlertTriangle as KGTipAlert, Lightbulb as KGTipLightbulb, BarChart3 as KGTipChart, Users as KGTipUsers, BookOpen as KGTipBook };
