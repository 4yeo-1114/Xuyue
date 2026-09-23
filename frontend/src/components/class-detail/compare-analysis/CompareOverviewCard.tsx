import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useLocale } from "@/contexts/LocaleContext";
import { BrainCircuit } from "lucide-react";
import type { CompareOverview } from "./compareAnalysisAdapter";

interface CompareOverviewCardProps {
  overview: CompareOverview;
}

const LEVEL_TONE: Record<string, string> = {
  "优秀": "border-emerald-200 bg-emerald-50 text-emerald-700",
  "良好": "border-blue-200 bg-blue-50 text-blue-700",
  "中等": "border-amber-200 bg-amber-50 text-amber-700",
  "需提升": "border-rose-200 bg-rose-50 text-rose-700",
  "数据不足": "border-muted bg-muted text-muted-foreground",
};

/** 总体概览：映射后端 analysis.overall_level（评级/总结/趋势/分数解读/优势/数据说明）。 */
export function CompareOverviewCard({ overview }: CompareOverviewCardProps) {
  const { t } = useLocale();
  const tone = overview.level ? LEVEL_TONE[overview.level] : "border-muted bg-muted text-muted-foreground";

  return (
    <Card className="border-primary/20" data-tour="ca-overview">
      <CardContent className="p-4">
        <div className="grid gap-4 lg:grid-cols-[180px_1fr]">
          <div className="flex flex-col justify-between rounded-lg bg-primary/5 p-4">
            <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <BrainCircuit className="h-3.5 w-3.5" />{t("classDetail.compare.overview.overallLevel")}
            </p>
            <p className="mt-2 text-2xl font-bold text-foreground">{overview.level || t("classDetail.compare.overview.noLevel")}</p>
            <p className="mt-1 text-[11px] text-muted-foreground">{t("classDetail.compare.overview.referenceExams", { count: overview.examCount })}</p>
          </div>
          <div className="min-w-0 space-y-2 text-xs">
            {overview.summary ? <p className="leading-5 text-foreground">{overview.summary}</p> : null}
            <div className="grid gap-2 md:grid-cols-2">
              {overview.trend ? (
                <div className="rounded-md border bg-muted/20 px-3 py-2">
                  <p className="text-[11px] font-medium text-muted-foreground">{t("classDetail.compare.overview.trend")}</p>
                  <p className="mt-1 leading-5 text-foreground">{overview.trend}</p>
                </div>
              ) : null}
              {overview.scoreInterpretation ? (
                <div className="rounded-md border bg-muted/20 px-3 py-2">
                  <p className="text-[11px] font-medium text-muted-foreground">{t("classDetail.compare.overview.scoreInterpretation")}</p>
                  <p className="mt-1 leading-5 text-foreground">{overview.scoreInterpretation}</p>
                </div>
              ) : null}
            </div>
            {overview.strengths.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {overview.strengths.map((s) => (
                  <Badge key={s} variant="outline" className="border-emerald-200 bg-emerald-50 text-emerald-800">{s}</Badge>
                ))}
              </div>
            ) : null}
            {overview.level ? <Badge variant="outline" className={tone}>{overview.level}</Badge> : null}
          </div>
        </div>
        {overview.dataNotes.length > 0 ? (
          <div className="mt-3 rounded-md border border-amber-200 bg-amber-50/60 px-3 py-2 text-[11px] leading-5 text-amber-900">
            <p className="font-semibold">{t("classDetail.compare.overview.dataNotes")}</p>
            <ul className="mt-1 space-y-0.5">{overview.dataNotes.map((note) => <li key={note}>· {note}</li>)}</ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
