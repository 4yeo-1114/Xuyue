import { cn } from "@/lib/utils";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSubjectName } from "@/i18n";

export interface Subject {
  id: string;
  name: string;
  color: string;
  bgColor: string;
  borderColor: string;
}

/** 科目内部名（中文，与数据库/筛选器一致） */
const allSubjects: Record<string, Subject> = {
  chinese: { id: "chinese", name: "语文", color: "text-rose-600", bgColor: "bg-rose-500", borderColor: "border-rose-500" },
  math: { id: "math", name: "数学", color: "text-blue-600", bgColor: "bg-blue-500", borderColor: "border-blue-500" },
  english: { id: "english", name: "英语", color: "text-emerald-600", bgColor: "bg-emerald-500", borderColor: "border-emerald-500" },
  science: { id: "science", name: "科学", color: "text-cyan-600", bgColor: "bg-cyan-500", borderColor: "border-cyan-500" },
  physics: { id: "physics", name: "物理", color: "text-violet-600", bgColor: "bg-violet-500", borderColor: "border-violet-500" },
  chemistry: { id: "chemistry", name: "化学", color: "text-orange-600", bgColor: "bg-orange-500", borderColor: "border-orange-500" },
  biology: { id: "biology", name: "生物", color: "text-teal-600", bgColor: "bg-teal-500", borderColor: "border-teal-500" },
  history: { id: "history", name: "历史", color: "text-amber-700", bgColor: "bg-amber-600", borderColor: "border-amber-600" },
  geography: { id: "geography", name: "地理", color: "text-sky-600", bgColor: "bg-sky-500", borderColor: "border-sky-500" },
  politics: { id: "politics", name: "道德与法治", color: "text-indigo-600", bgColor: "bg-indigo-500", borderColor: "border-indigo-500" },
  politicsSenior: { id: "politicsSenior", name: "思想政治", color: "text-indigo-600", bgColor: "bg-indigo-500", borderColor: "border-indigo-500" },
};

// 小学三至六年级：语文、数学、英语、科学
const primarySubjects: Subject[] = [
  allSubjects.chinese,
  allSubjects.math,
  allSubjects.english,
  allSubjects.science,
];

// 初中：语文、数学、英语、物理、化学、生物、道德与法治、历史、地理
const juniorSubjects: Subject[] = [
  allSubjects.chinese,
  allSubjects.math,
  allSubjects.english,
  allSubjects.physics,
  allSubjects.chemistry,
  allSubjects.biology,
  allSubjects.politics,
  allSubjects.history,
  allSubjects.geography,
];

// 高中：语文、数学、英语、物理、化学、生物、思想政治、历史、地理
const seniorSubjects: Subject[] = [
  allSubjects.chinese,
  allSubjects.math,
  allSubjects.english,
  allSubjects.physics,
  allSubjects.chemistry,
  allSubjects.biology,
  allSubjects.politicsSenior,
  allSubjects.history,
  allSubjects.geography,
];

export function getSubjectsBySchoolLevel(schoolLevel: string): Subject[] {
  switch (schoolLevel) {
    case "primary": return primarySubjects;
    case "junior": return juniorSubjects;
    case "senior": return seniorSubjects;
    default: return primarySubjects;
  }
}

interface SubjectTabsProps {
  selectedSubject: string;
  onSubjectChange: (subjectName: string) => void;
  schoolLevel: string;
  className?: string;
}

export function SubjectTabs({ selectedSubject, onSubjectChange, schoolLevel, className }: SubjectTabsProps) {
  const { locale } = useLocale();
  const subjects = getSubjectsBySchoolLevel(schoolLevel);
  return (
    <div className={cn("flex flex-wrap gap-2", className)}>
      {subjects.map((subject) => {
        const isSelected = selectedSubject === subject.name;
        const displayName = translateSubjectName(locale, subject.name);
        return (
          <button
            key={subject.id}
            onClick={() => onSubjectChange(subject.name)}
            className={cn(
              "relative px-5 py-2.5 rounded-lg font-medium text-sm transition-all duration-200",
              "hover:scale-105 active:scale-95",
              isSelected
                ? cn(subject.bgColor, "text-white shadow-lg")
                : "bg-muted text-muted-foreground hover:bg-muted/80"
            )}
          >
            {displayName}
            {isSelected && (
              <span className={cn(
                "absolute -bottom-1 left-1/2 -translate-x-1/2 w-6 h-1 rounded-full",
                subject.bgColor
              )} />
            )}
          </button>
        );
      })}
    </div>
  );
}

export function getSubjectByName(name: string): Subject | undefined {
  return Object.values(allSubjects).find(s => s.name === name);
}
