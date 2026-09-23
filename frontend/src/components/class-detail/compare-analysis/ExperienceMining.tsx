import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLocale } from "@/contexts/LocaleContext";
import { BookOpen, Trophy } from "lucide-react";

/** 标杆班级经验挖掘：有标杆班（同年级均分最高班）时渲染真实标杆班卡片，无数据时降级为空态。 */
export function ExperienceMining({
  benchmarkClass,
}: {
  benchmarkClass?: { className: string; averageScore: number } | null;
}) {
  const { t } = useLocale();

  if (!benchmarkClass) {
    return (
      <Card data-tour="ca-experience" className="flex-1 min-w-[320px]">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold">
            {t("classDetail.compare.experience.title")}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex h-[240px] flex-col items-center justify-center rounded-lg border border-dashed border-border/60 px-6 text-center">
            <BookOpen className="mb-2 h-6 w-6 text-muted-foreground" />
            <p className="text-sm font-medium text-foreground">
              {t("classDetail.暂无数据")}
            </p>
            <p className="mt-1 max-w-md text-xs leading-5 text-muted-foreground">
              {t("classDetail.compare.experience.unsupportedDesc")}
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card data-tour="ca-experience" className="flex-1 min-w-[320px]">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">
          {t("classDetail.compare.experience.title")}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex h-[240px] flex-col items-center justify-center rounded-lg border border-border/60 px-6 text-center">
          <Trophy className="mb-2 h-6 w-6 text-primary" />
          <p className="text-base font-semibold text-foreground">
            {benchmarkClass.className}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {t("classDetail.compare.experience.benchmarkGuide", {
              className: benchmarkClass.className,
              score: benchmarkClass.averageScore,
            })}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
