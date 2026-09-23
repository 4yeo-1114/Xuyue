import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { FolderOpen, Folder, Users2, User, ChevronDown, ChevronRight } from "lucide-react";
import type { ClassRecord } from "@/hooks/useClasses";
import { useLocale } from "@/contexts/LocaleContext";

interface ClassTreeNavProps {
  classes: ClassRecord[];
  selectedClassId: string;
  onSelectClass: (id: string) => void;
  headTeacherByClassId?: Record<string, string>;
}

interface GradeGroup {
  grade: string;
  schoolLevel: string;
  classes: ClassRecord[];
}

export function ClassTreeNav({ classes, selectedClassId, onSelectClass, headTeacherByClassId }: ClassTreeNavProps) {
  const { t } = useLocale();
  const groups = useMemo<GradeGroup[]>(() => {
    const map = new Map<string, GradeGroup>();
    for (const dc of classes) {
      const key = `${dc.school_level}-${dc.grade}`;
      if (!map.has(key)) {
        map.set(key, { grade: dc.grade, schoolLevel: dc.school_level, classes: [] });
      }
      map.get(key)!.classes.push(dc);
    }
    return Array.from(map.values());
  }, [classes]);

  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const toggleGroup = (key: string) => setCollapsed((prev) => ({ ...prev, [key]: !prev[key] }));

  if (groups.length > 0) {
    return (
      <div className="rounded-2xl border border-border bg-card p-5">
        <h3 className="text-base font-semibold text-foreground mb-4">{t("settingsClass.tree.title")}</h3>
        <div className="max-h-[288px] overflow-y-auto pr-2 space-y-1">
          {groups.map((g) => {
            const key = `${g.schoolLevel}-${g.grade}`;
            const isOpen = !collapsed[key];
            return (
              <div key={key}>
                <button
                  onClick={() => toggleGroup(key)}
                  className="flex items-center gap-2 text-sm font-semibold text-foreground px-2 py-2 w-full text-left hover:bg-muted rounded-xl transition-colors"
                >
                  {isOpen ? <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" /> : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />}
                  <FolderOpen className="w-4 h-4 text-primary" />
                  <span>{g.grade}</span>
                  <Badge variant="outline" className="text-[10px] px-1.5 py-0 ml-auto">{t("settingsClass.tree.classesInGrade", { count: g.classes.length })}</Badge>
                </button>
                {isOpen && (
                  <div className="ml-4 pl-3 border-l border-border/60 space-y-1">
                    {g.classes.map((cls) => (
                      <ClassItem
                        key={cls.id}
                        cls={cls}
                        isSelected={cls.id === selectedClassId}
                        onSelect={onSelectClass}
                        headName={headTeacherByClassId?.[cls.id] || "—"}
                      />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  return null;
}

function ClassItem({ cls, isSelected, onSelect, headName }: { cls: ClassRecord; isSelected: boolean; onSelect: (id: string) => void; headName: string }) {
  const { t } = useLocale();

  return (
    <button
      onClick={() => onSelect(cls.id)}
      className={cn(
        "w-full text-left rounded-xl px-3 py-3 transition-colors",
        isSelected ? "bg-primary/10 border border-primary/20" : "hover:bg-muted/60"
      )}
    >
      <div className="flex items-center gap-2">
        {isSelected ? (
          <FolderOpen className="w-4 h-4 text-primary shrink-0" />
        ) : (
          <Folder className="w-4 h-4 text-muted-foreground shrink-0" />
        )}
        <span className={cn("text-sm font-semibold", isSelected ? "text-primary" : "text-foreground")}>
          {cls.name}
        </span>
      </div>
      <div className="ml-6 mt-2 space-y-1 text-xs text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <Users2 className="w-3 h-3" />
          <span>{t("settingsClass.tree.students", { count: cls.student_count })}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <User className="w-3 h-3" />
          <span>{t("settingsClass.tree.headTeacher", { name: headName })}</span>
        </div>
      </div>
    </button>
  );
}
