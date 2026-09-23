import { Button } from "@/components/ui/button";
import { useMemo } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSubjectName } from "@/i18n";
import { Badge } from "@/components/ui/badge";
import { Target, User, BookOpen, FileQuestion, Download } from "lucide-react";
import type { TargetMode } from "./targetedData";

interface TargetedHeaderProps {
  subject: string;
  mode: TargetMode;
  onModeChange: (m: TargetMode) => void;
  onExportPDF: () => void;
  exporting: boolean;
}

export function TargetedHeader({ subject, mode, onModeChange, onExportPDF, exporting }: TargetedHeaderProps) {
  const { t, locale } = useLocale();
  const modes = useMemo(
    () => [
      { id: "person" as const, label: t("classDetail.对人靶向"), icon: User, desc: t("classDetail.针对学生个体") },
      { id: "knowledge" as const, label: t("classDetail.对点靶向"), icon: BookOpen, desc: t("classDetail.针对知识薄弱点") },
      { id: "question" as const, label: t("classDetail.对题靶向"), icon: FileQuestion, desc: t("classDetail.针对具体错题") },
    ],
    [t]
  );

  return (
    <div className="flex items-center justify-between flex-wrap gap-3">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
          <Target className="w-5 h-5 text-primary" />
        </div>
        <div>
          <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
            {t("nav.ai-targeted")}
            <Badge variant="secondary" className="text-[11px] font-normal">{translateSubjectName(locale, subject)}</Badge>
          </h2>
          <p className="text-xs text-muted-foreground">{t("classDetail.aiPrecisionDiagnosisTagline")}</p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <div className="flex bg-muted rounded-lg p-0.5" data-tour="ti-mode-switcher">
          {modes.map(m => (
            <button
              key={m.id}
              onClick={() => onModeChange(m.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                mode === m.id
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <m.icon className="w-3.5 h-3.5" />
              {m.label}
            </button>
          ))}
        </div>
        <Button variant="outline" size="sm" className="h-8 text-xs" onClick={onExportPDF} disabled={exporting}>
          <Download className="w-3.5 h-3.5 mr-1" />{exporting ? t("classDetail.导出中") : t("classDetail.导出PDF")}
        </Button>
      </div>
    </div>
  );
}
