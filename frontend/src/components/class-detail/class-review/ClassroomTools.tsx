import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { Wifi, Send, Shuffle, Vote, Users2, Timer, Mic } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { InteractionState, SimilarExercise } from "./reviewData";

interface ClassroomToolsProps {
  interaction: InteractionState;
  exercises: SimilarExercise[];
}

export function ClassroomTools({ interaction, exercises }: ClassroomToolsProps) {
  const { t, locale } = useLocale();

  const answerPct = Math.round((interaction.answeredCount / interaction.totalStudents) * 100);

  return (
    <Card className="flex-1 min-w-[320px]" data-tour="cr-tools">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold">{t("classDetail.课堂互动工具")}</CardTitle>
          <Badge variant="outline" className="text-[10px] gap-1">
            <Wifi className="w-3 h-3 text-emerald-500" />
            {t("classDetail.connectedCountLabel", { connected: interaction.connectedStudents, total: interaction.totalStudents })}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 text-xs">
        {/* Real-time quiz */}
        <div className="rounded-lg border border-border/50 p-3 space-y-2">
          <p className="font-semibold text-foreground flex items-center gap-1.5">
            <Send className="w-3.5 h-3.5 text-primary" />{t("classDetail.realtimeQuiz")}
          </p>
          <p className="text-[11px] text-muted-foreground">{t("classDetail.realtimeQuizDesc")}</p>
          <div className="flex gap-1.5 flex-wrap">
            {exercises.map((ex) => (
              <Button key={ex.id} variant="outline" size="sm" className="h-6 text-[10px]">
                {t("classDetail.pushPrefixLabel", { title: ex.title })}
              </Button>
            ))}
          </div>
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-[11px]">
              <span className="text-muted-foreground">{t("classDetail.answerProgressLabel")}</span>
              <div className="flex-1 h-2.5 bg-muted rounded-full overflow-hidden">
                <div className="h-full bg-primary/70 rounded-full transition-all" style={{ width: `${answerPct}%` }} />
              </div>
              <span className="font-medium text-foreground">{t("classDetail.answerCountFraction", { answered: interaction.answeredCount, total: interaction.totalStudents })}</span>
            </div>
            <p className="text-[11px] text-muted-foreground">
              {t("classDetail.correctRateColonLabel")}<strong className={cn(interaction.correctRate >= 70 ? "text-emerald-600" : "text-destructive")}>{interaction.correctRate}%</strong>{t("classDetail.realtimeUpdateLabel")}
            </p>
          </div>
          <div className="flex gap-1.5">
            <TooltipProvider delayDuration={200}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px]">{t("classDetail.viewAnswerDetails")}</Button>
                </TooltipTrigger>
                <TooltipContent side="top" className="text-xs">{t("classDetail.viewOptionStudentList")}</TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px]">{t("classDetail.targetedExplain")}</Button>
          </div>
        </div>

        {/* Random call */}
        <div className="rounded-lg border border-border/50 p-3 space-y-2">
          <p className="font-semibold text-foreground flex items-center gap-1.5">
            <Shuffle className="w-3.5 h-3.5 text-primary" />{t("classDetail.randomCall")}
          </p>
          <p className="text-[11px] text-muted-foreground">{t("classDetail.randomCallDesc")}</p>
          <div className="flex gap-1.5 flex-wrap">
            <TooltipProvider delayDuration={200}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button size="sm" className="h-7 text-[11px] gap-1"><Shuffle className="w-3 h-3" />{t("classDetail.startRandom")}</Button>
                </TooltipTrigger>
                <TooltipContent side="top" className="text-xs">{t("classDetail.randomTooltip")}</TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <Button variant="outline" size="sm" className="h-7 text-[11px]">{t("classDetail.specifiedCall")}</Button>
            <Button variant="outline" size="sm" className="h-7 text-[11px]">{t("classDetail.buzzMode")}</Button>
          </div>
          {interaction.calledStudents.length > 0 && (
            <p className="text-[11px] text-muted-foreground">
              {t("classDetail.calledStudentsLabel")}{interaction.calledStudents.map((s, i) => <span key={s}>{i > 0 ? " " : ""}{s}✓</span>)}
            </p>
          )}
        </div>

        {/* Instant vote */}
        <div className="rounded-lg border border-border/50 p-3 space-y-2">
          <p className="font-semibold text-foreground flex items-center gap-1.5">
            <Vote className="w-3.5 h-3.5 text-primary" />{t("classDetail.instantVote")}
          </p>
          <p className="text-[11px] text-muted-foreground">{t("classDetail.instantVoteDesc")}</p>
          <div className="flex gap-2">
            {[
              { label: t("classDetail.听懂"), pct: interaction.voteResult.understood, color: "bg-emerald-500" },
              { label: t("classDetail.似懂非懂"), pct: interaction.voteResult.partial, color: "bg-amber-500" },
              { label: t("classDetail.没懂"), pct: interaction.voteResult.lost, color: "bg-destructive" },
            ].map((v) => (
              <div key={v.label} className="flex-1 text-center">
                <div className="h-12 bg-muted rounded relative overflow-hidden">
                  <div className={cn("absolute bottom-0 w-full rounded-b", v.color)} style={{ height: `${v.pct}%` }} />
                </div>
                <p className="text-[10px] text-muted-foreground mt-1">{v.label}</p>
                <p className="text-[11px] font-semibold text-foreground">{v.pct}%</p>
              </div>
            ))}
          </div>
        </div>

        {/* Group discussion + Class record */}
        <div className="flex gap-2">
          <Button variant="outline" size="sm" className="h-7 text-[11px] gap-1 flex-1">
            <Users2 className="w-3 h-3" />{t("classDetail.groupDiscussion")}
          </Button>
          <Button variant="outline" size="sm" className="h-7 text-[11px] gap-1 flex-1">
            <Mic className="w-3 h-3" />{t("classDetail.voiceNote")}
          </Button>
          <Button variant="outline" size="sm" className="h-7 text-[11px] gap-1 flex-1">
            <Timer className="w-3 h-3" />{t("classDetail.timer")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
