import { GenericTour, TourStep } from "@/components/shared/GenericTour";
import { useMemo } from "react";
import { useLocale } from "@/contexts/LocaleContext";

function buildTourSteps(t: (key: string, params?: Record<string, string | number>) => string): TourStep[] {
  return [
  {
    targetSelector: "[data-tour='cr-header']",
    title: t("classDetail.数据来源选择"),
    description: t("classDetail.选择讲评数据来源 当前为昨日作业"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "top",
  },
  {
    targetSelector: "[data-tour='cr-analysis']",
    title: t("classDetail.AI分析完成"),
    description: t("classDetail.AI自动分析 建议讲评30分钟 涉及错误58人次"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "top",
  },
  {
    targetSelector: "[data-tour='cr-priorities']",
    title: t("classDetail.讲评重点列表"),
    description: t("classDetail.按优先级排序的讲评重点 点击查看典型错误"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "top",
  },
  {
    targetSelector: "[data-tour='cr-actions']",
    title: t("classDetail.生成方案"),
    description: t("classDetail.一键生成完整讲评方案和课件"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "top",
  },
  {
    targetSelector: "[data-tour='cr-ppt']",
    title: t("classDetail.讲评PPT预览"),
    description: t("classDetail.自动生成的讲评课件 对比展示问题与优秀"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "top",
  },
  {
    targetSelector: "[data-tour='cr-tools']",
    title: t("classDetail.课堂互动工具"),
    description: t("classDetail.课堂互动工具 实时了解学生掌握情况"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "left",
  },
  {
    targetSelector: "[data-tour='cr-layered']",
    title: t("classDetail.课后分层巩固"),
    description: t("classDetail.基于课堂效果 自动生成分层作业 一键推送"),
    buttonLabel: t("home.tour.next"),
    arrowPosition: "top",
  },
  {
    targetSelector: "[data-tour='cr-tracking']",
    title: t("classDetail.讲评效果追踪"),
    description: t("classDetail.数据闭环 追踪讲评效果 自动复盘"),
    buttonLabel: t("home.tour.complete"),
    arrowPosition: "left",
  },
  ];
}

export function ClassReviewTour() {
  const { t, locale } = useLocale();
  const tourSteps = useMemo(() => buildTourSteps(t), [t]);

  return (
    <GenericTour
      storageKey="class-review-tour-done"
      steps={tourSteps}
      completeTitle={t("classDetail.课堂讲评引导完成")}
      completeDescription={t("classDetail.AI生成方案 课堂互动 分层巩固 效果追踪")}
    />
  );
}
