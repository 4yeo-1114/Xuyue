import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { BookOpen, Plus, Star, Upload, CheckCircle2 } from "lucide-react";
import { getSubjectsBySchoolLevel } from "@/components/SubjectTabs";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSubjectName, translateSchoolLevel } from "@/i18n";

interface Props {
  selectedSchoolLevel: string;
  selectedSubject: string;
  onSubjectChange: (subject: string) => void;
}

export function SubjectSwitcher({ selectedSchoolLevel, selectedSubject, onSubjectChange }: Props) {
  const { t, locale } = useLocale();
  const subjects = getSubjectsBySchoolLevel(selectedSchoolLevel);
  const levelLabel = translateSchoolLevel(locale, selectedSchoolLevel);

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-primary" />
          {t("settingsSubject.switcher.title")}
          <Badge variant="outline" className="text-[10px] h-5 font-normal">{levelLabel}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {subjects.map((s) => {
          const isActive = s.name === selectedSubject;
          return (
            <button
              key={s.name}
              onClick={() => onSubjectChange(s.name)}
              className={`w-full text-left p-3 rounded-lg border transition-colors ${
                isActive
                  ? "bg-primary/5 border-primary/20"
                  : "bg-muted/50 border-border hover:bg-muted"
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {isActive && <Star className="w-4 h-4 text-primary fill-primary" />}
                  <span className="font-medium text-foreground text-sm">{levelLabel}{translateSubjectName(locale, s.name)}</span>
                  {isActive && <Badge className="text-[10px] h-5">{t("settingsSubject.switcher.currentEditing")}</Badge>}
                </div>
              </div>
              {isActive && (
                <div className="flex items-center gap-2 mt-1.5 text-xs text-muted-foreground">
                  <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                  <span>{t("settingsSubject.switcher.selectedHint")}</span>
                </div>
              )}
            </button>
          );
        })}

        <div className="flex gap-2 pt-1">
          <Button variant="outline" size="sm" className="text-xs border-dashed flex-1">
            <Plus className="w-3.5 h-3.5 mr-1" />{t("settingsSubject.switcher.addSubject")}
          </Button>
          <Button variant="outline" size="sm" className="text-xs border-dashed flex-1">
            <Upload className="w-3.5 h-3.5 mr-1" />{t("settingsSubject.switcher.importExternal")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
