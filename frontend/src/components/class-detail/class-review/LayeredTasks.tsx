import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { Send, Eye, Clock } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { LayerGroup } from "./reviewData";

interface LayeredTasksProps {
  groups: LayerGroup[];
}

export function LayeredTasks({ groups }: LayeredTasksProps) {
  const { t, locale } = useLocale();

  return (
    <Card className="flex-1 min-w-[320px]" data-tour="cr-layered">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">{t("classDetail.layeredTasksTitle")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-xs">
        <div className="rounded-lg border border-border/50 p-2.5 text-[11px] text-muted-foreground">
          {t("classDetail.classTestDataLabel")}
        </div>

        {groups.map((g) => (
          <div key={g.layer} className={cn("rounded-lg border p-3 space-y-1.5", g.borderColor, g.bgColor)}>
            <div className="flex items-center gap-2">
              <Badge className={cn("text-[10px] h-5", g.bgColor, g.color, g.borderColor, "border")}>{t("classDetail.layerBadgeLabel", { layer: g.layer, label: g.label })}</Badge>
              <span className={cn("text-[11px] font-semibold", g.color)}>{t("header.studentsCount", { count: g.studentCount })}</span>
            </div>
            <p className="text-[11px] text-muted-foreground">{t("classDetail.taskColonLabel", { task: g.task })}</p>
            <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
              <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{t("classDetail.estimatedTimeLabel", { duration: g.duration })}</span>
            </div>
            <div className="flex gap-1.5 flex-wrap mt-1">
              <TooltipProvider delayDuration={200}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px] gap-1">
                      <Eye className="w-3 h-3" />{t("classDetail.previewQuestions")}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="top" className="text-xs">{t("classDetail.previewLayerContentTooltip")}</TooltipContent>
                </Tooltip>
              </TooltipProvider>
              <Button size="sm" className="h-6 px-2 text-[10px] gap-1">
                <Send className="w-3 h-3" />{t("classDetail.oneClickPush")}
              </Button>
              {g.extra && (
                <Button variant="outline" size="sm" className="h-6 px-2 text-[10px]">{g.extra}</Button>
              )}
            </div>
            <p className="text-[10px] text-muted-foreground">
              {t("classDetail.studentsColonLabel")}{g.students.slice(0, 5).join("、")}{g.students.length > 5 ? t("classDetail.etcPeopleSuffix", { count: g.students.length }) : ""}
            </p>
          </div>
        ))}

        <div className="rounded-lg border border-border/50 p-2.5 space-y-1 text-[11px] text-muted-foreground">
          <p className="font-medium text-foreground">{t("classDetail.pushSettings")}</p>
          <p>{t("classDetail.deadlineReminderLine")}</p>
        </div>

        <div className="flex gap-2 flex-wrap">
          <Button size="sm" className="h-7 text-[11px] gap-1">
            <Send className="w-3 h-3" />{t("classDetail.batchPush")}
          </Button>
          <Button variant="outline" size="sm" className="h-7 text-[11px]">{t("classDetail.personalizedAdjust")}</Button>
          <Button variant="outline" size="sm" className="h-7 text-[11px]">{t("classDetail.saveGroupPlan")}</Button>
        </div>
      </CardContent>
    </Card>
  );
}
