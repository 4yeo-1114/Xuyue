import { GenericTour, TourStep } from "@/components/shared/GenericTour";
import { useMemo } from "react";
import { useLocale } from "@/contexts/LocaleContext";

function buildTourSteps(
  t: (key: string, params?: Record<string, string | number>) => string,
): TourStep[] {
  return [
    {
      targetSelector: "[data-tour='qa-header']",
      title: t("classDetail.考试选择器"),
      description: t("classDetail.选择要分析的考试 查看原卷或导出报告"),
      buttonLabel: t("home.tour.next"),
      arrowPosition: "top",
    },
    {
      targetSelector: "[data-tour='qa-overview']",
      title: t("classDetail.试卷质量概览"),
      description: t("classDetail.试卷整体质量 难度 区分度 信度一目了然"),
      buttonLabel: t("home.tour.next"),
      arrowPosition: "top",
    },
    {
      targetSelector: "[data-tour='qa-list']",
      title: t("classDetail.题目列表"),
      description: t("classDetail.题目列表 颜色标记掌握情况 点击查看深度分析"),
      buttonLabel: t("home.tour.next"),
      arrowPosition: "left",
    },
    {
      targetSelector: "[data-tour='qa-detail']",
      title: t("classDetail.单题深度分析"),
      description: t("classDetail.选中题目详细分析 质量 分布 能力层级"),
      buttonLabel: t("home.tour.next"),
      arrowPosition: "top",
    },
    {
      targetSelector: "[data-tour='qa-errors']",
      title: t("classDetail.班级典型错误TOP5"),
      description: t("classDetail.班级共性错误 点击查看名单 推送练习"),
      buttonLabel: t("home.tour.next"),
      arrowPosition: "top",
    },
    {
      targetSelector: "[data-tour='qa-suggestions']",
      title: t("classDetail.AI教学建议"),
      description: t("classDetail.系统生成讲评方案 分层补救 命题反思"),
      buttonLabel: t("home.tour.complete"),
      arrowPosition: "left",
    },
  ];
}

export function QuestionAnalysisTour() {
  const { t, locale } = useLocale();
  const tourSteps = useMemo(() => buildTourSteps(t), [t]);

  return (
    <GenericTour
      storageKey="question-analysis-tour-done"
      steps={tourSteps}
      completeTitle={t("classDetail.题目分析引导完成")}
      completeDescription={t("classDetail.找到失分点 对比典型卷 按建议教学")}
    />
  );
}
