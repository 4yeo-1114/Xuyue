import { useMemo } from "react";
import { cn } from "@/lib/utils";
import { useLocale } from "@/contexts/LocaleContext";
import { buildGradeLevels, type GradeLevelOption } from "@/i18n";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { useClasses } from "@/hooks/useClasses";
import { Settings2 } from "lucide-react";

export type GradeLevel = GradeLevelOption;

interface GradeSelectorProps {
  selectedSchoolLevel: string;
  selectedGrade: string;
  selectedClass: string;
  onSchoolLevelChange: (level: string) => void;
  onGradeChange: (grade: string) => void;
  onClassChange: (cls: string) => void;
  onManageClasses?: () => void;
  className?: string;
}

export function GradeSelector({
  selectedSchoolLevel,
  selectedGrade,
  selectedClass,
  onSchoolLevelChange,
  onGradeChange,
  onClassChange,
  onManageClasses,
  className,
}: GradeSelectorProps) {
  const { t, locale } = useLocale();
  const gradeLevels = useMemo(() => buildGradeLevels(locale), [locale]);

  const currentLevel = gradeLevels.find((l) => l.id === selectedSchoolLevel);
  const grades = currentLevel?.grades || [];

  const { data: classes = [], isLoading: classesLoading } = useClasses(
    selectedSchoolLevel,
    selectedGrade,
  );

  return (
    <div className={cn("flex items-center gap-3", className)}>
      {/* School Level Tabs */}
      <div className="flex items-center gap-1.5 bg-muted rounded-lg p-1">
        {gradeLevels.map((level) => {
          const isSelected = selectedSchoolLevel === level.id;
          return (
            <button
              key={level.id}
              onClick={() => {
                onSchoolLevelChange(level.id);
                onGradeChange(level.grades[0].value);
              }}
              className={cn(
                "px-4 py-2 rounded-md text-sm font-medium transition-all duration-200",
                isSelected
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground hover:bg-background/60",
              )}
            >
              {level.label}
            </button>
          );
        })}
      </div>

      {/* Grade Dropdown */}
      <Select value={selectedGrade} onValueChange={onGradeChange}>
        <SelectTrigger className="w-[140px]">
          <SelectValue placeholder={t("classDetail.选择年级")} />
        </SelectTrigger>
        <SelectContent>
          {grades.map((grade) => (
            <SelectItem key={grade.value} value={grade.value}>
              {grade.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Class Dropdown - from database */}
      <Select value={selectedClass} onValueChange={onClassChange}>
        <SelectTrigger className="w-[140px]">
          <SelectValue
            placeholder={
              classesLoading
                ? t("header.loadingClasses")
                : classes.length === 0
                  ? t("header.noClasses")
                  : t("classDetail.选择班级")
            }
          />
        </SelectTrigger>
        <SelectContent>
          {classes.map((cls) => (
            <SelectItem key={cls.id} value={cls.id}>
              {cls.name}（
              {t("header.studentsCount", { count: cls.student_count })}）
            </SelectItem>
          ))}
          {classes.length === 0 && (
            <div className="px-2 py-3 text-sm text-muted-foreground text-center">
              {t("header.noClassesHint")}
            </div>
          )}
        </SelectContent>
      </Select>

      {/* Manage classes button */}
      {onManageClasses && (
        <Button
          variant="ghost"
          size="icon"
          onClick={onManageClasses}
          title={t("classDetail.管理班级")}
        >
          <Settings2 className="w-4 h-4" />
        </Button>
      )}
    </div>
  );
}
