import { useMemo } from "react";
import { GenericTour, TourStep } from "@/components/shared/GenericTour";
import { useLocale } from "@/contexts/LocaleContext";

export function OnboardingTour() {
  const { t, locale } = useLocale();

  const steps = useMemo<TourStep[]>(
    () => [
      {
        targetSelector: "[data-tour='sidebar']",
        title: t("home.tour.sidebar.title"),
        description: t("home.tour.sidebar.desc"),
        buttonLabel: t("home.tour.next"),
        arrowPosition: "left",
      },
      {
        targetSelector: "[data-tour='top-filters']",
        title: t("home.tour.filters.title"),
        description: t("home.tour.filters.desc"),
        buttonLabel: t("home.tour.next"),
        arrowPosition: "top",
      },
      {
        targetSelector: "[data-tour='grading-entry']",
        title: t("home.tour.grading.title"),
        description: t("home.tour.grading.desc"),
        buttonLabel: t("home.tour.next"),
        arrowPosition: "top",
      },
      {
        targetSelector: "[data-tour='recent-files']",
        title: t("home.tour.recent.title"),
        description: t("home.tour.recent.desc"),
        buttonLabel: t("home.tour.next"),
        arrowPosition: "top",
      },
      {
        targetSelector: "[data-tour='stats-overview']",
        title: t("home.tour.stats.title"),
        description: t("home.tour.stats.desc"),
        buttonLabel: t("home.tour.next"),
        arrowPosition: "top",
      },
      {
        targetSelector: "[data-tour='student-matrix']",
        title: t("home.tour.students.title"),
        description: t("home.tour.students.desc"),
        buttonLabel: t("home.tour.complete"),
        arrowPosition: "top",
      },
    ],
    [t, locale]
  );

  return (
    <GenericTour
      storageKey="onboarding-tour-done"
      steps={steps}
      completeTitle={t("home.tour.completeTitle")}
      completeDescription={t("home.tour.completeDesc")}
    />
  );
}
