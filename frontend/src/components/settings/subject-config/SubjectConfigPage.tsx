import { useState, useMemo } from "react";
import { getSubjectConfig } from "./subjectConfigData";
import { SubjectConfigHeader } from "./SubjectConfigHeader";
import { SubjectSwitcher } from "./SubjectSwitcher";
import { KnowledgePreview } from "./KnowledgePreview";
import { KnowledgePointEditor } from "./KnowledgePointEditor";
import { ScoringStandards } from "./ScoringStandards";
import { AbilityModel } from "./AbilityModel";
import { TextbookMappingPanel } from "./TextbookMappingPanel";
import { ExamTemplateEditor } from "./ExamTemplateEditor";
import { useKnowledgeData } from "@/hooks/useKnowledgeData";
import { useExamTemplates } from "@/hooks/useExamTemplates";
import { Button } from "@/components/ui/button";
import { Loader2, DatabaseZap } from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";
import { translateGradeValue, translateSubjectName, translateSchoolLevel } from "@/i18n";
import type { AppLocale } from "@/i18n/types";

function gradeToSemester(
  grade: string,
  locale: AppLocale,
  schoolLevel: string,
  t: (key: string, params?: Record<string, string | number>) => string,
): string {
  const gradePart = translateGradeValue(locale, schoolLevel, grade);
  return t("settingsSubject.page.semesterSuffix", { grade: gradePart });
}

interface Props {
  selectedSubject: string;
  selectedSchoolLevel: string;
  selectedGrade: string;
  onSubjectChange: (subject: string) => void;
}

export function SubjectConfigPage({ selectedSubject, selectedSchoolLevel, selectedGrade, onSubjectChange }: Props) {
  const { t, locale } = useLocale();
  const fullSubject = `${translateSchoolLevel("zh", selectedSchoolLevel)}${selectedSubject}`;
  const displaySubject = `${translateSchoolLevel(locale, selectedSchoolLevel)}${translateSubjectName(locale, selectedSubject)}`;
  const semester = gradeToSemester(selectedGrade, locale, selectedSchoolLevel, t);

  const config = useMemo(() => getSubjectConfig(fullSubject), [fullSubject]);
  const { units, isEmpty, isLoading, seed, isSeeding, createKP, updateKP, deleteKP } = useKnowledgeData(fullSubject, semester);
  const { templates: examTemplates } = useExamTemplates(fullSubject);
  const [selectedKnowledgeId, setSelectedKnowledgeId] = useState<string | null>(null);

  const displayUnits = units.length > 0 ? units : config.units;
  const knowledgeCount = displayUnits.reduce((s, u) => s + u.knowledgePoints.length, 0);
  const avgMastery = knowledgeCount > 0
    ? Math.round(displayUnits.flatMap(u => u.knowledgePoints).reduce((s, k) => s + k.mastery, 0) / knowledgeCount)
    : 0;

  const displayConfig = {
    ...config,
    subject: displaySubject,
    semester,
    units: displayUnits,
    unitCount: displayUnits.length,
    knowledgeCount,
    avgMastery,
  };

  const selectedPoint = useMemo(() => {
    return displayUnits.flatMap(u => u.knowledgePoints).find(k => k.id === selectedKnowledgeId) ?? null;
  }, [displayUnits, selectedKnowledgeId]);

  const handleSaveKP = (data: Record<string, any>) => {
    if (!selectedKnowledgeId) return;
    updateKP.mutate({
      id: selectedKnowledgeId,
      name: data.name,
      code: data.code,
      level: data.level,
      mastery: data.mastery,
      is_weak: data.mastery < 60,
      hours: data.hours,
      key_point: data.keyPoint,
      difficulty: data.difficulty,
      common_errors: data.commonErrors,
      prerequisite: data.prerequisite,
      postrequisite: data.postrequisite,
      related: data.related,
      resources: data.resources,
    });
  };

  const handleDeleteKP = () => {
    if (!selectedKnowledgeId) return;
    deleteKP.mutate(selectedKnowledgeId, {
      onSuccess: () => setSelectedKnowledgeId(null),
    });
  };

  const handleCreateKP = (data: { unitId: string; code: string; name: string; level: string }) => {
    createKP.mutate(data);
  };

  return (
    <div className="space-y-5 max-w-[1400px]">
      <SubjectConfigHeader config={displayConfig} templateCount={examTemplates.length || undefined} />

      {!isLoading && isEmpty && (
        <div className="flex items-center gap-3 p-4 rounded-lg border border-dashed border-primary/30 bg-primary/5">
          <DatabaseZap className="w-5 h-5 text-primary" />
          <div className="flex-1">
            <p className="text-sm font-medium text-foreground">{t("settingsSubject.page.noDbData")}</p>
            <p className="text-xs text-muted-foreground">{t("settingsSubject.page.demoDataHint")}</p>
          </div>
          <Button size="sm" onClick={() => seed()} disabled={isSeeding}>
            {isSeeding && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
            {t("settingsSubject.page.importDefaults")}
          </Button>
        </div>
      )}

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-primary" />
          <span className="ml-2 text-sm text-muted-foreground">{t("settingsSubject.page.loadingKnowledge")}</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <SubjectSwitcher
          selectedSchoolLevel={selectedSchoolLevel}
          selectedSubject={selectedSubject}
          onSubjectChange={onSubjectChange}
        />
        <div className="lg:col-span-2">
          <KnowledgePreview
            units={displayUnits}
            selectedKnowledgeId={selectedKnowledgeId}
            onSelectKnowledge={setSelectedKnowledgeId}
            onCreateKP={handleCreateKP}
            subjectLabel={`${displaySubject}（${semester}）${t("settingsSubject.page.knowledgePreview")}`}
          />
        </div>
      </div>

      <ExamTemplateEditor fullSubject={fullSubject} rawSubject={selectedSubject} displaySubject={displaySubject} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <KnowledgePointEditor
          point={selectedPoint}
          onSave={handleSaveKP}
          onDelete={handleDeleteKP}
          isSaving={updateKP.isPending}
          isDeleting={deleteKP.isPending}
          isDbMode={units.length > 0}
        />
        <ScoringStandards dimensions={displayConfig.scoring} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <AbilityModel abilities={displayConfig.abilities} />
        <TextbookMappingPanel mappings={displayConfig.textbooks} />
      </div>
    </div>
  );
}
