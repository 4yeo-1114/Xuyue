import { useLocale } from "@/contexts/LocaleContext";
import { translateSchoolLevel, translateSubjectName } from "@/i18n";
import { Button } from "@/components/ui/button";
import { ListChecks, FileDown, Loader2 } from "lucide-react";

interface AnalysisHeaderProps {
  selectedSubject: string;
  schoolLevel: string;
  examNames: string[];
  onExportPDF?: () => void;
  exporting?: boolean;
}

export function AnalysisHeader({ selectedSubject, schoolLevel, examNames, onExportPDF, exporting }: AnalysisHeaderProps) {
  const { t, locale } = useLocale();
  const schoolLabel = translateSchoolLevel(locale, schoolLevel) || t("classDetail.高中");

  return (
    <div className="rounded-xl border border-border/50 bg-card p-4" data-tour="qa-header">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
            <ListChecks className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-foreground">{t("classDetail.questionAnalysisTitle")}</h2>
            <p className="text-xs text-muted-foreground">{t("classDetail.questionAnalysisSubtitle", { school: schoolLabel, subject: translateSubjectName(locale, selectedSubject) })}</p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {examNames.length > 0 && (
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-muted-foreground">{t("classDetail.dataSourceColonLabel")}</span>
              <div className="flex flex-wrap gap-1">
                {examNames.map((name) => (
                  <span key={name} className="text-[11px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground">{name}</span>
                ))}
              </div>
            </div>
          )}
          {onExportPDF && (
            <Button variant="outline" size="sm" className="h-8 text-xs gap-1.5" onClick={onExportPDF} disabled={exporting}>
              {exporting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileDown className="w-3.5 h-3.5" />}
              {exporting ? t("classDetail.导出中2") : t("classDetail.导出分析报告")}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
