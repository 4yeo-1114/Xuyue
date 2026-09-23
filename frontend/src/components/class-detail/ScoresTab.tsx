import { useEffect, useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSubjectName } from "@/i18n";
import { useExams } from "@/hooks/useExams";
import { useExamScores, useUpsertExamScores } from "@/hooks/useExamScores";
import { useStudents } from "@/hooks/useStudents";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { GradeBadge } from "@/components/class-detail/GradeBadge";
import { Save, AlertTriangle, RefreshCw } from "lucide-react";
import { toast } from "@/hooks/use-toast";

const subjectOptions = [
  "语文",
  "数学",
  "英语",
  "科学",
  "物理",
  "化学",
  "生物",
  "历史",
  "地理",
  "政治",
];

interface ScoresTabProps {
  classId: string;
  /** 顶部全局筛选传入的默认学科；变化时联动同步本地学科选择 */
  initialSubject?: string;
}

export function ScoresTab({ classId, initialSubject }: ScoresTabProps) {
  const { t, locale } = useLocale();

  const [selectedSubject, setSelectedSubject] = useState(
    initialSubject ?? "语文",
  );

  useEffect(() => {
    if (initialSubject) setSelectedSubject(initialSubject);
  }, [initialSubject]);
  const [selectedExamId, setSelectedExamId] = useState<string>("");
  const [editScores, setEditScores] = useState<Record<string, string>>({});
  const [showGrade, setShowGrade] = useState(false);

  // 切换考试/学科时清空未保存的编辑分数，防止 A 考试/学科数据串写到 B
  useEffect(() => {
    setEditScores({});
  }, [selectedExamId, selectedSubject]);

  const {
    data: exams = [],
    isError: examsError,
    refetch: refetchExams,
  } = useExams(classId, selectedSubject);
  const {
    data: students = [],
    isError: studentsError,
    refetch: refetchStudents,
  } = useStudents(classId);
  const {
    data: scores = [],
    isSuccess: scoresIsSuccess,
    isError: scoresIsError,
    isLoading: scoresIsLoading,
    refetch: refetchScores,
  } = useExamScores(selectedExamId || undefined);
  const upsertScores = useUpsertExamScores();

  const scoreMap = new Map(scores.map((s) => [s.student_id, s.score]));
  const gradeMap = new Map(scores.map((s) => [s.student_id, s.grade]));
  const scoresLoaded = !selectedExamId || scoresIsSuccess;

  const handleSave = () => {
    if (!selectedExamId) return;
    if (!scoresLoaded) {
      toast({ title: t("classDetail.scoresNotLoadedSaveHint") });
      return;
    }
    const scoreEntries = students.map((s) => ({
      student_id: s.id,
      score:
        editScores[s.id] !== undefined
          ? editScores[s.id] === ""
            ? null
            : Number(editScores[s.id])
          : (scoreMap.get(s.id) ?? null),
    }));
    upsertScores.mutate({ exam_id: selectedExamId, scores: scoreEntries });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Select
          value={selectedSubject}
          onValueChange={(v) => {
            setSelectedSubject(v);
            setSelectedExamId("");
          }}
        >
          <SelectTrigger className="w-[120px]">
            <SelectValue placeholder={t("classDetail.选择学科")} />
          </SelectTrigger>
          <SelectContent>
            {subjectOptions.map((s) => (
              <SelectItem key={s} value={s}>
                {translateSubjectName(locale, s)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={selectedExamId} onValueChange={setSelectedExamId}>
          <SelectTrigger className="w-[240px]">
            <SelectValue
              placeholder={
                exams.length === 0
                  ? t("classDetail.暂无考试记录")
                  : t("classDetail.选择考试")
              }
            />
          </SelectTrigger>
          <SelectContent>
            {exams.map((e) => (
              <SelectItem key={e.id} value={e.id}>
                {t("classDetail.examTitleDate", {
                  title: e.title,
                  date: e.exam_date,
                })}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {selectedExamId && (
          <>
            <Button
              onClick={handleSave}
              disabled={upsertScores.isPending || !scoresLoaded}
              className="gap-2"
            >
              <Save className="w-4 h-4" />
              {t("classDetail.saveScores")}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setShowGrade((v) => !v)}
              className="gap-1"
            >
              {showGrade
                ? t("classDetail.viewScore")
                : t("classDetail.viewGrade")}
            </Button>
          </>
        )}
      </div>

      {(examsError || studentsError) && (
        <div className="flex items-start gap-2 rounded-lg border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <div className="space-y-1">
            {examsError && <p>{t("classDetail.examsLoadFailed")}</p>}
            {studentsError && <p>{t("classDetail.loadStudentsFailed")}</p>}
            <p className="text-muted-foreground">
              {t("classDetail.accessDeniedDataHint")}
            </p>
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1 text-xs"
              onClick={() => {
                refetchExams();
                refetchStudents();
              }}
            >
              <RefreshCw className="w-3.5 h-3.5" />
              {t("wuyu.retry")}
            </Button>
          </div>
        </div>
      )}

      {selectedExamId && scoresIsError && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <AlertTriangle className="w-4 h-4" />
          <span>{t("classDetail.scoresLoadFailed")}</span>
          <span className="text-muted-foreground">
            {t("classDetail.accessDeniedDataHint")}
          </span>
          <Button
            size="sm"
            variant="ghost"
            className="h-6 gap-1 text-xs"
            onClick={() => refetchScores()}
          >
            <RefreshCw className="w-3.5 h-3.5" />
            {t("wuyu.retry")}
          </Button>
        </div>
      )}

      {!selectedExamId ? (
        <div className="flex flex-col items-center justify-center h-[300px] bg-card rounded-xl border border-border">
          <p className="text-muted-foreground">
            {t("classDetail.selectSubjectAndExam")}
          </p>
        </div>
      ) : (
        <div className="bg-card rounded-xl border border-border overflow-hidden">
          <div className="grid grid-cols-[80px_1fr_150px] gap-4 px-4 py-3 bg-muted/50 text-sm font-medium text-muted-foreground">
            <span>{t("wuyu.studentNumber")}</span>
            <span>{t("classDetail.姓名")}</span>
            <span>{t("classDetail.score")}</span>
          </div>
          {scoresIsLoading ? (
            <p className="text-center py-8 text-muted-foreground">
              {t("classDetail.scoresLoading")}
            </p>
          ) : scoresIsError ? (
            <p className="text-center py-8 text-muted-foreground">
              {t("classDetail.scoresLoadFailed")}
            </p>
          ) : students.length === 0 ? (
            <p className="text-center py-8 text-muted-foreground">
              {t("classDetail.暂无学生")}
            </p>
          ) : (
            students.map((s) => {
              const existing = scoreMap.get(s.id);
              const val =
                editScores[s.id] ??
                (existing !== null && existing !== undefined
                  ? String(existing)
                  : "");
              return (
                <div
                  key={s.id}
                  className="grid grid-cols-[80px_1fr_150px] gap-4 items-center px-4 py-2 border-t border-border"
                >
                  <span className="font-mono text-sm">{s.student_number}</span>
                  <span className="font-medium">{s.name}</span>
                  {showGrade ? (
                    <div className="flex items-center">
                      <GradeBadge grade={gradeMap.get(s.id) ?? null} />
                    </div>
                  ) : (
                    <div className="flex items-center gap-1.5">
                      <Input
                        type="number"
                        value={val}
                        onChange={(e) =>
                          setEditScores((prev) => ({
                            ...prev,
                            [s.id]: e.target.value,
                          }))
                        }
                        placeholder="--"
                        className="h-8 flex-1 min-w-0"
                      />
                      <GradeBadge
                        grade={gradeMap.get(s.id) ?? null}
                        className="shrink-0"
                      />
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
