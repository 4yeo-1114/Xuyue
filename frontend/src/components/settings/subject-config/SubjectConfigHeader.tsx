import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { BookMarked, Save, Download, RotateCcw, History } from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSubjectName } from "@/i18n";
import type { SubjectConfig } from "./subjectConfigData";

interface Props {
  config: SubjectConfig;
  templateCount?: number;
}

export function SubjectConfigHeader({ config, templateCount }: Props) {
  const { t, locale } = useLocale();

  return (
    <div className="flex items-center justify-between flex-wrap gap-3">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
          <BookMarked className="w-5 h-5 text-primary" />
        </div>
        <div>
          <h2 className="text-xl font-semibold text-foreground flex items-center gap-2">
            {t("settingsSubject.header.title")}
            <Badge variant="secondary" className="text-xs font-normal">{translateSubjectName(locale, config.subject)}</Badge>
            <Badge variant="outline" className="text-xs font-normal">{config.semester}</Badge>
          </h2>
          <p className="text-sm text-muted-foreground">
            {templateCount != null
              ? t("settingsSubject.header.stats", {
                  units: config.unitCount,
                  points: config.knowledgeCount,
                  templates: templateCount,
                  mastery: config.avgMastery,
                })
              : t("settingsSubject.header.statsNoTemplate", {
                  units: config.unitCount,
                  points: config.knowledgeCount,
                  mastery: config.avgMastery,
                })}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Button size="sm"><Save className="w-4 h-4 mr-1" />{t("common.save")}</Button>
        <Button variant="outline" size="sm"><Download className="w-4 h-4 mr-1" />{t("settingsSubject.header.export")}</Button>
        <Button variant="outline" size="sm"><RotateCcw className="w-4 h-4 mr-1" />{t("settingsSubject.header.resetDefault")}</Button>
        <Button variant="ghost" size="sm"><History className="w-4 h-4 mr-1" />{t("settingsSubject.header.versionHistory")}</Button>
      </div>
    </div>
  );
}
