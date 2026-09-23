import { GenericTour, type TourStep } from "@/components/shared/GenericTour";
import { useMemo } from "react";
import { useLocale } from "@/contexts/LocaleContext";

function buildTourSteps(t: (key: string, params?: Record<string, string | number>) => string): TourStep[] {
  return [
  {
    targetSelector: "[data-tour='ti-mode-switcher']",
    title: t("classDetail.靶向对象选择"),
    description: t("classDetail.选择靶向对象类型 当前为对人靶向"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "top",
  },
  {
    targetSelector: "[data-tour='ti-recommended']",
    title: t("classDetail.AI推荐靶向对象"),
    description: t("classDetail.AI推荐需关注学生 点击卡片查看详情"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "top",
  },
  {
    targetSelector: "[data-tour='ti-diagnosis']",
    title: t("classDetail.AI深度诊断"),
    description: t("classDetail.学业诊断 错因分析 学习品质 个性特征 全面画像"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "top",
  },
  {
    targetSelector: "[data-tour='ti-plan']",
    title: t("classDetail.个性化提升方案"),
    description: t("classDetail.4周提升计划 分阶段循序渐进 目标 9分"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "top",
  },
  {
    targetSelector: "[data-tour='ti-motivation']",
    title: t("classDetail.激励策略"),
    description: t("classDetail.里程碑 成就系统 同伴互助 提高学习动力"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "top",
  },
  {
    targetSelector: "[data-tour='ti-preview']",
    title: t("classDetail.方案预览与确认"),
    description: t("classDetail.预览推送内容 检测时间冲突 准备家长沟通"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "top",
  },
  {
    targetSelector: "[data-tour='ti-tracking']",
    title: t("classDetail.推送执行与效果追踪"),
    description: t("classDetail.推送执行 每日追踪 动态调整 历史效果"),
    buttonLabel: t("home.tour.complete"),
    arrowPosition: "top",
  },
  ];
}

export function TargetedImproveTour() {
  const { t, locale } = useLocale();
  const tourSteps = useMemo(() => buildTourSteps(t), [t]);

  return (
    <GenericTour
      storageKey="targeted-improve-tour-done"
      steps={tourSteps}
      completeTitle={t("classDetail.靶向提升引导完成")}
      completeDescription={t("classDetail.AI诊断 生成方案 推送执行 效果追踪 动态调整")}
    />
  );
}
