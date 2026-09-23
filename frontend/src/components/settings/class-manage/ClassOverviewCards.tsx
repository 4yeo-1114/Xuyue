import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Users2, BarChart3, Layers, AlertTriangle, Clock, RefreshCw, Armchair, FileText } from "lucide-react";
import type { ClassRecord, StudentInfo } from "@/types/api";
import { useLocale } from "@/contexts/LocaleContext";

interface ClassOverviewCardsProps {
  classInfo: ClassRecord;
  students: StudentInfo[];
}

export function ClassOverviewCards({ classInfo, students }: ClassOverviewCardsProps) {
  const { t } = useLocale();
  const maleCount = students.filter((s) => (s.gender || "") === "男").length;
  const femaleCount = students.filter((s) => (s.gender || "") === "女").length;
  const tierA = students.filter((s) => (s.tier || "") === "A").length;
  const tierB = students.filter((s) => (s.tier || "") === "B").length;
  const tierC = students.filter((s) => (s.tier || "") === "C").length;
  const warningCount = students.filter((s) => (s.status || "") === "预警").length;

  const stats = [
    { label: t("settingsClass.overview.totalStudents"), value: `${students.length}`, desc: t("settingsClass.overview.people"), icon: Users2, color: "text-primary" },
    { label: t("settingsClass.overview.gender"), value: `${maleCount}/${femaleCount}`, desc: t("settingsClass.overview.genderDesc"), icon: BarChart3, color: "text-blue-500" },
    { label: t("settingsClass.overview.tier"), value: `A${tierA} B${tierB} C${tierC}`, desc: "", icon: Layers, color: "text-amber-500" },
    { label: t("settingsClass.overview.warning"), value: `${warningCount}`, desc: t("settingsClass.overview.people"), icon: AlertTriangle, color: "text-destructive" },
  ];

  return (
    <Card>
      <CardContent className="p-5 flex flex-col h-full">
        <div className="flex items-start justify-between gap-3 mb-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 min-w-0">
              <h3 className="text-lg font-semibold text-foreground truncate">{classInfo.name}</h3>
              <Badge variant="secondary" className="text-xs shrink-0">{classInfo.grade}</Badge>
            </div>
          </div>
          <div className="text-right text-xs text-muted-foreground">
            <div className="flex items-center justify-end gap-1.5"><Clock className="w-3 h-3" />{classInfo.updated_at || "-"}</div>
            <div className="flex items-center justify-end gap-1.5 mt-1"><RefreshCw className="w-3 h-3" />{t("settingsClass.overview.liveData")}</div>
          </div>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {stats.map((s) => (
            <div key={s.label} className="rounded-xl border border-border p-3">
              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground">{s.label}</p>
                <s.icon className={cn("w-4 h-4", s.color)} />
              </div>
              <div className="mt-2 flex items-end gap-1">
                <p className="text-xl font-semibold text-foreground leading-none">{s.value}</p>
                {s.desc ? <p className="text-xs text-muted-foreground">{s.desc}</p> : null}
              </div>
            </div>
          ))}
        </div>

        <div className="flex items-center justify-end gap-2 mt-auto pt-4">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button size="sm" variant="outline" className="h-8 text-sm gap-1.5" disabled>
                <Armchair className="w-4 h-4" />{t("settingsClass.overview.adjustSeating")}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t("common.comingSoon")}</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button size="sm" variant="outline" className="h-8 text-sm gap-1.5" disabled>
                <FileText className="w-4 h-4" />{t("settingsClass.overview.exportReport")}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t("common.comingSoon")}</TooltipContent>
          </Tooltip>
        </div>
      </CardContent>
    </Card>
  );
}

function cn(...classes: (string | boolean | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}
