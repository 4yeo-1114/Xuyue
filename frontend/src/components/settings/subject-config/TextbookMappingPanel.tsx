import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { BookText, ArrowRightLeft, FolderPlus, RefreshCw, AlertCircle } from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";
import type { TextbookMapping } from "./subjectConfigData";

interface Props {
  mappings: TextbookMapping[];
}

export function TextbookMappingPanel({ mappings }: Props) {
  const { t } = useLocale();

  return (
    <Card className="h-full overflow-auto">
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <BookText className="w-4 h-4 text-primary" />
          {t("settingsSubject.textbook.title")} · {t("settingsSubject.textbook.titleVersion")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="p-3 rounded-lg bg-muted/50 border border-border">
          <h4 className="font-medium text-foreground text-sm mb-1">{t("settingsSubject.textbook.standards")}</h4>
          <p className="text-xs text-muted-foreground">
            {t("settingsSubject.textbook.coverageLabel")}<span className="text-primary font-medium">85%</span>
          </p>
          <p className="text-xs text-muted-foreground">{t("settingsSubject.textbook.uncovered", { n: 15 })}</p>
        </div>

        <div className="space-y-2">
          <h4 className="font-medium text-foreground">{t("settingsSubject.textbook.mapping")}</h4>
          {mappings.map((m, i) => (
            <div key={i} className="p-2.5 rounded-lg bg-muted/30 border border-border space-y-1 text-xs">
              <div className="flex items-center gap-2">
                <Badge variant="secondary" className="text-[10px] h-4 px-1">{m.unitName}</Badge>
                <span className="font-medium text-foreground">{m.lessonName}</span>
              </div>
              <div className="flex flex-wrap gap-x-3 text-muted-foreground">
                <span>{t("settingsSubject.textbook.standardPrefix")}{m.standards[0]}</span>
              </div>
              <div className="flex flex-wrap gap-1">
                {m.knowledgeIds.map(k => <Badge key={k} variant="outline" className="text-[10px] h-4 px-1">{k}</Badge>)}
                {m.abilities.map(a => <Badge key={a} variant="outline" className="text-[10px] h-4 px-1 border-primary/30 text-primary">{a}</Badge>)}
              </div>
              <div className="text-muted-foreground">{t("settingsSubject.textbook.literacyPrefix")}{m.literacy}</div>
            </div>
          ))}
        </div>

        <Separator />

        <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 space-y-1.5">
          <div className="flex items-center gap-1.5 text-sm font-medium text-amber-800">
            <AlertCircle className="w-3.5 h-3.5" />
            {t("settingsSubject.textbook.versionMgmt")}
          </div>
          <p className="text-xs text-amber-700">{t("settingsSubject.textbook.currentVersion")}{t("settingsSubject.textbook.currentVersionValue")}</p>
          <p className="text-xs text-amber-700">{t("settingsSubject.textbook.detectedVersion")}{t("settingsSubject.textbook.detectedVersionValue")}</p>
          <p className="text-xs text-amber-700">{t("settingsSubject.textbook.diff")}{t("settingsSubject.textbook.diffValue")}</p>
          <div className="flex gap-1.5 pt-0.5">
            <Button variant="outline" size="sm" className="h-6 text-xs bg-white">{t("settingsSubject.textbook.viewDiff")}</Button>
            <Button size="sm" className="h-6 text-xs"><RefreshCw className="w-3 h-3 mr-0.5" />{t("settingsSubject.textbook.oneClickUpgrade")}</Button>
          </div>
        </div>

        <Separator />

        <div className="space-y-1.5">
          <h4 className="font-medium text-foreground">{t("settingsSubject.textbook.schoolSupplement")}</h4>
          <div className="text-xs text-muted-foreground space-y-0.5">
            <p>{t("settingsSubject.textbook.supplement1")}</p>
            <p>{t("settingsSubject.textbook.supplement2")}</p>
          </div>
          <Button variant="outline" size="sm" className="h-7 text-xs"><FolderPlus className="w-3 h-3 mr-1" />{t("settingsSubject.textbook.manageSupplement")}</Button>
        </div>

        <Separator />

        <div className="space-y-1.5">
          <h4 className="font-medium text-foreground flex items-center gap-1.5">
            <ArrowRightLeft className="w-3.5 h-3.5" />
            {t("settingsSubject.textbook.crossDisciplinary")}
          </h4>
          <div className="text-xs text-muted-foreground space-y-0.5">
            <p>{t("settingsSubject.textbook.crossHistory")}<span className="text-primary font-medium">60%</span></p>
            <p>{t("settingsSubject.textbook.crossArt")}<span className="text-primary font-medium">40%</span></p>
          </div>
          <div className="flex gap-1.5">
            <Button variant="outline" size="sm" className="h-7 text-xs">{t("settingsSubject.textbook.viewCrossSuggestions")}</Button>
            <Button variant="outline" size="sm" className="h-7 text-xs">{t("settingsSubject.textbook.designFusion")}</Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
