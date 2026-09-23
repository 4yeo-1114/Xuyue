import { GenericTour, type TourStep } from "@/components/shared/GenericTour";
import { useMemo } from "react";
import { useLocale } from "@/contexts/LocaleContext";

function buildTourSteps(
  t: (key: string, params?: Record<string, string | number>) => string,
): TourStep[] {
  return [
    {
      targetSelector: "[data-tour='lp-header']",
      title: t("layeredPush.tour.connectionTitle"),
      description: t("layeredPush.tour.connectionDesc"),
      buttonLabel: t("home.tour.next"),
      arrowPosition: "top",
    },
    {
      targetSelector: "[data-tour='lp-tiers']",
      title: t("layeredPush.tour.tiersTitle"),
      description: t("layeredPush.tour.tiersDesc"),
      buttonLabel: t("home.tour.next"),
      arrowPosition: "top",
    },
    {
      targetSelector: "[data-tour='lp-assignments']",
      title: t("layeredPush.tour.assignmentsTitle"),
      description: t("layeredPush.tour.assignmentsDesc"),
      buttonLabel: t("home.tour.next"),
      arrowPosition: "top",
    },
    {
      targetSelector: "[data-tour='lp-dingtalk-settings']",
      title: t("layeredPush.tour.settingsTitle"),
      description: t("layeredPush.tour.settingsDesc"),
      buttonLabel: t("home.tour.next"),
      arrowPosition: "top",
    },
    {
      targetSelector: "[data-tour='lp-push-settings']",
      title: t("layeredPush.tour.pushTitle"),
      description: t("layeredPush.tour.pushDesc"),
      buttonLabel: t("home.tour.next"),
      arrowPosition: "top",
    },
    {
      targetSelector: "[data-tour='lp-tracking']",
      title: t("layeredPush.tour.trackingTitle"),
      description: t("layeredPush.tour.trackingDesc"),
      buttonLabel: t("home.tour.next"),
      arrowPosition: "top",
    },
    {
      targetSelector: "[data-tour='lp-interaction']",
      title: t("layeredPush.tour.interactionTitle"),
      description: t("layeredPush.tour.interactionDesc"),
      buttonLabel: t("home.tour.complete"),
      arrowPosition: "top",
    },
  ];
}

export function LayeredPushTour() {
  const { t, locale } = useLocale();
  const tourSteps = useMemo(() => buildTourSteps(t), [t]);

  return (
    <GenericTour
      storageKey="layered-push-tour-done"
      steps={tourSteps}
      completeTitle={t("layeredPush.tour.completeTitle")}
      completeDescription={t("layeredPush.tour.completeDesc")}
    />
  );
}
