import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useMemo } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSchoolLevel, translateSubjectName } from "@/i18n";
import { Button } from "@/components/ui/button";
import { Presentation, FileDown, Loader2 } from "lucide-react";

interface ReviewHeaderProps {
  selectedSubject: string;
  schoolLevel: string;
  selectedSource: string;
  onSourceChange: (v: string) => void;
  onExportPDF?: () => void;
  exporting?: boolean;
}

export function ReviewHeader({ selectedSubject, schoolLevel, selectedSource, onSourceChange, onExportPDF, exporting }: ReviewHeaderProps) {
  const { t, locale } = useLocale();
  const sourceOptions = useMemo(
    () => [
      { value: "homework", label: t("classDetail.昨日作业") },
      { value: "weekly-errors", label: t("classDetail.本周错题") },
      { value: "exam-final", label: t("classDetail.期末模拟") },
      { value: "exam-mid", label: t("classDetail.期中考试") },
    ],
    [t]
  );
  const schoolLabel = translateSchoolLevel(locale, schoolLevel) || t("classDetail.高中");

  return (
    <div className="rounded-xl border border-border/50 bg-card p-4" data-tour="cr-header">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
            <Presentation className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-foreground">{t("classDetail.classReviewTitle")}</h2>
            <p className="text-xs text-muted-foreground">{t("classDetail.aiReviewPlanSubtitle", { school: schoolLabel, subject: translateSubjectName(locale, selectedSubject) })}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-muted-foreground">{t("classDetail.dataSourceLabel")}</span>
          <Select value={selectedSource} onValueChange={onSourceChange}>
            <SelectTrigger className="w-28 h-8 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              {sourceOptions.map((s) => (
                <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {onExportPDF && (
            <Button variant="outline" size="sm" className="h-8 text-xs gap-1.5" onClick={onExportPDF} disabled={exporting}>
              {exporting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileDown className="w-3.5 h-3.5" />}
              {exporting ? t("classDetail.导出中2") : t("classDetail.导出讲评提纲")}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
