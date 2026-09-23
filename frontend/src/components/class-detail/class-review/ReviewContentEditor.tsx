import { useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSubjectName } from "@/i18n";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, Maximize2, Edit3 } from "lucide-react";

interface ReviewContentEditorProps {
  subject: string;
  priorities: { topic: string }[];
}

const SLIDE_TITLE_KEYS = [
  "classDetail.slideCoverTitle",
  "classDetail.slideTodaySummary",
  "classDetail.slideEssayStructureIssues",
  "classDetail.slideTypicalVsExcellentEssay",
  "classDetail.slideStructureMnemonic",
  "classDetail.slideInClassExerciseOptimization",
  "classDetail.slideClassicalChineseWords",
  "classDetail.slideZhiVsEr",
  "classDetail.slideMnemonicExamples",
  "classDetail.slideInstantTestFillerWords",
  "classDetail.slidePoetryErrors",
  "classDetail.slideInClassDictationChallenge",
  "classDetail.slideClassSummary",
  "classDetail.slideAfterClassLeveledTasks",
  "classDetail.slideNextLessonPreview",
];

export function ReviewContentEditor({
  subject,
  priorities,
}: ReviewContentEditorProps) {
  const { t, locale } = useLocale();

  const [currentSlide, setCurrentSlide] = useState(2); // 0-indexed
  const totalSlides = SLIDE_TITLE_KEYS.length;

  return (
    <Card className="flex-1 min-w-[320px]" data-tour="cr-ppt">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <CardTitle className="text-sm font-semibold">
            {t("classDetail.pptPreviewTitle", { total: totalSlides })}
          </CardTitle>
          <div className="flex items-center gap-1.5">
            <Button
              variant="outline"
              size="sm"
              className="h-7 w-7 p-0"
              onClick={() => setCurrentSlide(Math.max(0, currentSlide - 1))}
              disabled={currentSlide === 0}
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </Button>
            <span className="text-xs text-muted-foreground min-w-[60px] text-center">
              {t("classDetail.slidePageIndicator", {
                current: currentSlide + 1,
                total: totalSlides,
              })}
            </span>
            <Button
              variant="outline"
              size="sm"
              className="h-7 w-7 p-0"
              onClick={() =>
                setCurrentSlide(Math.min(totalSlides - 1, currentSlide + 1))
              }
              disabled={currentSlide === totalSlides - 1}
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-[11px] gap-1 ml-1"
            >
              <Maximize2 className="w-3 h-3" />
              {t("classDetail.fullscreenDemo")}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Slide preview */}
        <div className="relative rounded-lg border border-border/50 bg-gradient-to-br from-muted/30 to-muted/10 aspect-[16/9] flex items-center justify-center overflow-hidden">
          <div className="text-center space-y-2 p-6">
            <p className="text-xs text-muted-foreground">
              {t("classDetail.slideNumberLabel", { number: currentSlide + 1 })}
            </p>
            <p className="text-sm font-semibold text-foreground">
              {t(SLIDE_TITLE_KEYS[currentSlide])}
            </p>
            {currentSlide === 2 && (
              <div className="grid grid-cols-2 gap-3 mt-3 text-[11px]">
                <div className="rounded border border-destructive/30 bg-destructive/5 p-2 text-left">
                  <p className="font-medium text-destructive">
                    {t("classDetail.problemEssay")}
                  </p>
                  <p className="text-muted-foreground mt-1">
                    {t("classDetail.problemEssayBody")}
                  </p>
                  <p className="text-destructive text-[10px] mt-0.5">
                    {t("classDetail.annotationSlowStart")}
                  </p>
                </div>
                <div className="rounded border border-emerald-300 bg-emerald-50 p-2 text-left">
                  <p className="font-medium text-emerald-700">
                    {t("classDetail.excellentEssay")}
                  </p>
                  <p className="text-muted-foreground mt-1">
                    {t("classDetail.excellentEssayBody")}
                  </p>
                  <p className="text-emerald-600 text-[10px] mt-0.5">
                    {t("classDetail.highlightStraightToPoint")}
                  </p>
                </div>
              </div>
            )}
            {currentSlide === 0 && (
              <div className="mt-2 text-[11px] text-muted-foreground">
                <p>
                  {t("classDetail.slideCoverSubjectLine", {
                    subject: translateSubjectName(locale, subject),
                  })}
                </p>
                <p className="mt-1">{t("classDetail.aiReviewPlanDesc")}</p>
              </div>
            )}
          </div>
          <div className="absolute bottom-2 right-2">
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-[10px] gap-1"
            >
              <Edit3 className="w-3 h-3" />
              {t("classDetail.editButton")}
            </Button>
          </div>
        </div>

        {/* Slide thumbnails */}
        <div className="flex gap-1.5 overflow-x-auto pb-1">
          {SLIDE_TITLE_KEYS.map((_, i) => (
            <button
              key={i}
              onClick={() => setCurrentSlide(i)}
              className={`shrink-0 w-16 h-10 rounded border text-[8px] flex items-center justify-center p-1 text-center transition-colors ${
                i === currentSlide
                  ? "border-primary bg-primary/10 text-primary font-medium"
                  : "border-border/40 text-muted-foreground hover:border-border"
              }`}
            >
              {i + 1}
            </button>
          ))}
        </div>

        {/* Edit actions */}
        <div className="flex gap-1.5 flex-wrap">
          <Button variant="outline" size="sm" className="h-6 text-[10px]">
            {t("classDetail.replaceTypicalEssay")}
          </Button>
          <Button variant="outline" size="sm" className="h-6 text-[10px]">
            {t("classDetail.adjustAnnotation")}
          </Button>
          <Button variant="outline" size="sm" className="h-6 text-[10px]">
            {t("classDetail.insertInteractionQuestion")}
          </Button>
          <Button variant="outline" size="sm" className="h-6 text-[10px]">
            {t("classDetail.changeTemplateStyle")}
          </Button>
          <Button variant="outline" size="sm" className="h-6 text-[10px]">
            {t("classDetail.saveMyTemplate")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
