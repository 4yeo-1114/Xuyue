import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLocale } from "@/contexts/LocaleContext";
import { cn } from "@/lib/utils";
import { Inbox } from "lucide-react";
import type { StudentRankingItem } from "./compareAnalysisAdapter";
import { GradeBadge } from "@/components/class-detail/GradeBadge";
import type { GradeCode } from "@/services/api";

interface RankingDashboardProps {
  rankings: StudentRankingItem[];
  examName: string;
}

const GRADE_ORDER: GradeCode[] = ["excellent", "good", "pass", "needs_work"];

export function RankingDashboard({ rankings, examName }: RankingDashboardProps) {
  const { t } = useLocale();

  const bestScore = rankings[0]?.score ?? null;

  const gradeCounts: Record<GradeCode, number> = {
    excellent: 0,
    good: 0,
    pass: 0,
    needs_work: 0,
  };
  for (const r of rankings) {
    if (r.grade && gradeCounts[r.grade] !== undefined) gradeCounts[r.grade]++;
  }

  return (
    <Card data-tour="ca-ranking" className="flex-1 min-w-[300px]">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">{t("classDetail.compare.ranking.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {rankings.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center text-sm text-muted-foreground">
            <Inbox className="mb-2 h-6 w-6" />
            {t("classDetail.暂无数据")}
            <span className="mt-1 text-[11px]">{t("classDetail.compare.ranking.noData")}</span>
          </div>
        ) : (
          <>
            <div className="flex items-center gap-6">
              <div className="relative">
                <div className="w-24 h-24 rounded-full border-4 border-primary/20 flex items-center justify-center">
                  <div className="text-center">
                    <p className="text-2xl font-bold text-primary">{rankings.length}</p>
                    <p className="text-[10px] text-muted-foreground">{t("classDetail.compare.ranking.participants")}</p>
                  </div>
                </div>
              </div>
              <div className="space-y-1.5 text-xs">
                <p className="text-muted-foreground">{t("classDetail.compare.ranking.highestScore")}<strong className="text-foreground text-base">{bestScore ?? "--"}{t("classDetail.compare.ranking.scoreSuffix")}</strong></p>
                <p className="text-muted-foreground">{t("classDetail.compare.ranking.latestExam")}<strong className="text-foreground">{examName || "--"}</strong></p>
              </div>
            </div>

            <div className="space-y-1">
              <p className="text-[11px] text-muted-foreground font-medium mb-1">{t("classDetail.compare.ranking.gradeDistribution")}</p>
              <div className="flex flex-wrap gap-1.5">
                {GRADE_ORDER.map((code) => (
                  <span key={code} className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5">
                    <GradeBadge grade={code} />
                    <span className="text-xs text-foreground">{t("classDetail.peopleUnit", { count: gradeCounts[code] })}</span>
                  </span>
                ))}
              </div>
            </div>

            <div className="space-y-1">
              <p className="text-[11px] text-muted-foreground font-medium mb-1">{t("classDetail.compare.ranking.studentRankingTitle")}</p>
              {rankings.map((r) => (
                <div key={r.studentId} className={cn(
                  "flex items-center gap-2 text-xs px-2 py-1.5 rounded",
                  r.rank <= 3 ? "bg-primary/5" : ""
                )}>
                  <span className={cn(
                    "w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold",
                    r.rank === 1 ? "bg-amber-100 text-amber-700" : r.rank === 2 ? "bg-slate-100 text-slate-600" : r.rank === 3 ? "bg-orange-100 text-orange-600" : "bg-muted text-muted-foreground"
                  )}>{r.rank}</span>
                  <span className="flex-1 text-foreground truncate">{r.studentName}</span>
                  <span className="text-muted-foreground text-[11px]">{r.studentNumber || "--"}</span>
                  <GradeBadge grade={r.grade} />
                  <span className="w-10 text-right font-semibold text-foreground">{r.score ?? "--"}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
