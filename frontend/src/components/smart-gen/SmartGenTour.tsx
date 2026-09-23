import { useMemo } from "react";
import { GenericTour, TourStep } from "@/components/shared/GenericTour";
import { useLocale } from "@/contexts/LocaleContext";

export function SmartGenTour() {
  const { t } = useLocale();

  const steps = useMemo<TourStep[]>(() => [
    {
      targetSelector: "[data-tour='sg-gen-types']",
      title: t("smartGen.tour.step0.title"),
      description: t("smartGen.tour.step0.desc"),
      buttonLabel: t("smartGen.tour.next"),
      arrowPosition: "top",
    },
    {
      targetSelector: "[data-tour='sg-requirement']",
      title: t("smartGen.tour.step1.title"),
      description: t("smartGen.tour.step1.desc"),
      buttonLabel: t("smartGen.tour.next"),
      arrowPosition: "top",
    },
    {
      targetSelector: "[data-tour='sg-analyze-btn']",
      title: t("smartGen.tour.step2.title"),
      description: t("smartGen.tour.step2.desc"),
      buttonLabel: t("smartGen.tour.next"),
      arrowPosition: "top",
    },
    {
      targetSelector: "[data-tour='sg-recommendation']",
      title: t("smartGen.tour.step3.title"),
      description: t("smartGen.tour.step3.desc"),
      buttonLabel: t("smartGen.tour.next"),
      arrowPosition: "top",
    },
    {
      targetSelector: "[data-tour='sg-generate-btn']",
      title: t("smartGen.tour.step4.title"),
      description: t("smartGen.tour.step4.desc"),
      buttonLabel: t("smartGen.tour.next"),
      arrowPosition: "top",
    },
    {
      targetSelector: "[data-tour='sg-history']",
      title: t("smartGen.tour.step5.title"),
      description: t("smartGen.tour.step5.desc"),
      buttonLabel: t("smartGen.tour.next"),
      arrowPosition: "top",
    },
    {
      targetSelector: "[data-tour='sg-tool-library']",
      title: t("smartGen.tour.step6.title"),
      description: t("smartGen.tour.step6.desc"),
      buttonLabel: t("smartGen.tour.next"),
      arrowPosition: "top",
    },
    {
      targetSelector: "[data-tour='sg-rankings']",
      title: t("smartGen.tour.step7.title"),
      description: t("smartGen.tour.step7.desc"),
      buttonLabel: t("smartGen.tour.done"),
      arrowPosition: "top",
    },
  ], [t]);

  return (
    <GenericTour
      storageKey="smart-gen-tour-done"
      steps={steps}
      completeTitle={t("smartGen.tour.completeTitle")}
      completeDescription={t("smartGen.tour.completeDesc")}
    />
  );
}
