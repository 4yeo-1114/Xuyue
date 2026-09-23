import { useMemo } from "react";
import { Button } from "@/components/ui/button";
import {
  HoverCard,
  HoverCardTrigger,
  HoverCardContent,
} from "@/components/ui/hover-card";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { handlePushExercise } from "@/utils/dingtalkActions";
import { useStudents } from "@/hooks/useStudents";
import { useLocale } from "@/contexts/LocaleContext";
import type { StudentInfo } from "@/types/api";

interface StudentMatrixPreviewProps {
  selectedSubject: string;
  selectedClass: string;
  onNavChange: (id: string) => void;
  onNavigateToTargeted?: (studentName: string) => void;
}

function hashName(name: string, subject: string, cls: string): number {
  const s = name + subject + cls;
  let h = 0;
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

function badgeColor(seed: number) {
  return {
    bg: "bg-primary/5",
    border: "border-primary/10",
    dot: "bg-primary",
  };
}

export function StudentMatrixPreview({
  selectedSubject,
  selectedClass,
  onNavChange,
  onNavigateToTargeted,
}: StudentMatrixPreviewProps) {
  const { t, locale } = useLocale();
  const { data, isLoading } = useStudents(selectedClass || undefined);
  const students = useMemo(() => {
    const list = Array.isArray(data) ? data : [];
    return list.slice(0, 6);
  }, [data]);

  return (
    <div
      data-tour="student-matrix"
      className="rounded-xl bg-card border border-border/50 p-6 card-elevated animate-fade-in"
    >
      <div className="flex items-center justify-between mb-5">
        <h3 className="text-base font-semibold text-foreground">
          {t("home.students.title")}
        </h3>
        <Button
          variant="link"
          size="sm"
          className="p-0 h-auto text-xs"
          onClick={() => onNavChange("class-students")}
        >
          {t("home.students.viewAll")}
        </Button>
      </div>

      {!selectedClass ? (
        <div className="py-8 text-center text-sm text-muted-foreground">
          {t("home.students.selectClassHint")}
        </div>
      ) : isLoading ? (
        <div className="flex items-center justify-center py-10 text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 mr-2 animate-spin" />
          {t("common.loading")}
        </div>
      ) : students.length === 0 ? (
        <div className="py-8 text-center text-sm text-muted-foreground">
          {t("home.students.empty")}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 mb-4 sm:grid-cols-3 lg:grid-cols-6">
          {students.map((s: StudentInfo) => {
            const seed = hashName(
              String(s?.name || ""),
              selectedSubject,
              selectedClass,
            );
            const c = badgeColor(seed);
            const gender = String(s?.gender || "").trim();
            const sn = String(s?.student_number || "").trim();
            return (
              <HoverCard key={s.id || s.name} openDelay={200}>
                <HoverCardTrigger asChild>
                  <button
                    className={cn(
                      "flex flex-col items-center gap-1.5 p-4 rounded-xl border transition-all duration-200 hover-scale cursor-pointer",
                      c.bg,
                      c.border,
                    )}
                  >
                    <div
                      className={cn(
                        "w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold text-white",
                        c.dot,
                      )}
                    >
                      {String(s?.name || "—")[0] || "—"}
                    </div>
                    <span className="text-sm font-medium text-foreground">
                      {s?.name || "—"}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {sn || "—"}
                    </span>
                  </button>
                </HoverCardTrigger>
                <HoverCardContent className="w-[280px] p-4" side="bottom">
                  <div className="flex items-center gap-3 mb-3">
                    <div
                      className={cn(
                        "w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold text-white",
                        c.dot,
                      )}
                    >
                      {String(s?.name || "—")[0] || "—"}
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-foreground">
                        {s?.name || "—"}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {sn
                          ? t("home.students.studentNumber", { number: sn })
                          : t("home.students.studentNumberEmpty")}
                        {gender ? t("home.students.gender", { gender }) : ""}
                      </p>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-xs h-7"
                      onClick={() => onNavChange("class-students")}
                    >
                      {t("home.students.viewPortrait")}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-xs h-7"
                      onClick={() => {
                        handlePushExercise(
                          String(s?.name || ""),
                          selectedSubject,
                        );
                        onNavigateToTargeted
                          ? onNavigateToTargeted(String(s?.name || ""))
                          : onNavChange("ai-targeted");
                      }}
                    >
                      {t("home.students.pushExercise")}
                    </Button>
                  </div>
                </HoverCardContent>
              </HoverCard>
            );
          })}
        </div>
      )}
    </div>
  );
}
