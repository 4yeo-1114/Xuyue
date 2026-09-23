import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import { useClasses } from "@/hooks/useClasses";
import { listStudentsByClass } from "@/services/api";
import { getPortfolio } from "@/services/wuyuApi";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Users2, UserSquare2, Loader2, School } from "lucide-react";
import { DossierPanel } from "./DossierPanel";
import { PortfolioDetailPanel } from "./PortfolioDetailPanel";
import { GrowthRecordsPanel } from "./GrowthRecordsPanel";
import { AssessmentResultPanel } from "./AssessmentResultPanel";
import { StudentIncentivePanel } from "./StudentIncentivePanel";
import { SemesterReportPanel } from "./SemesterReportPanel";
import { AiCommentPanel } from "./AiCommentPanel";
import { StudentMemoryPanel } from "./StudentMemoryPanel";
import { ClassOverviewPanel } from "./ClassOverviewPanel";

interface WuyuProfilePageProps {
  /** 全局过滤器传入的班级 ID（可为空，页内可自行切换） */
  selectedClass?: string;
  selectedSubject?: string;
  onNavChange?: (id: string) => void;
  className?: string;
}

export function WuyuProfilePage({
  selectedClass,
  className,
}: WuyuProfilePageProps) {
  const { t } = useLocale();

  const { data: classes = [] } = useClasses();
  const [classId, setClassId] = useState<string>(selectedClass || "");
  const [selectedStudentId, setSelectedStudentId] = useState<string | null>(
    null,
  );
  const [keyword, setKeyword] = useState("");
  const [view, setView] = useState<"class" | "student">("class");

  // 与全局班级选择同步
  useEffect(() => {
    if (selectedClass) setClassId(selectedClass);
  }, [selectedClass]);

  const { data: students = [], isLoading: studentsLoading } = useQuery({
    queryKey: ["students", classId],
    queryFn: () => listStudentsByClass(classId),
    enabled: !!classId,
  });

  const filteredStudents = useMemo(() => {
    const kw = keyword.trim();
    if (!kw) return students;
    return students.filter(
      (s) => s.name.includes(kw) || (s.student_number ?? "").includes(kw),
    );
  }, [students, keyword]);

  const selectedStudent =
    students.find((s) => s.id === selectedStudentId) ?? null;
  const selectedClassName = classes.find((c) => c.id === classId)?.name || "";

  const {
    data: portfolio,
    isLoading: portfolioLoading,
    isError: portfolioError,
    refetch,
  } = useQuery({
    queryKey: ["wuyu-portfolio", selectedStudentId],
    queryFn: () => getPortfolio(selectedStudentId as string, true),
    enabled: !!selectedStudentId,
  });

  // 切换班级时重置学生选择
  const handleClassChange = (v: string) => {
    setClassId(v);
    setSelectedStudentId(null);
    setKeyword("");
  };

  return (
    <div className={cn("space-y-3 animate-fade-in", className)}>
      {/* 顶部：班级选择 + 统计 */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-card border border-border/50 rounded-xl p-3 px-5">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
            <School className="w-4 h-4 text-primary" />
          </div>
          <div className="min-w-0">
            <h2 className="font-semibold text-foreground leading-tight">
              {t("wuyu.title")}
            </h2>
            <p className="text-xs text-muted-foreground truncate">
              {t("wuyu.subtitle")}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Tabs
            value={view}
            onValueChange={(v) => setView(v as "class" | "student")}
            className="shrink-0"
          >
            <TabsList className="h-9">
              <TabsTrigger value="class" className="text-xs">
                {t("wuyu.classOverview.viewClass")}
              </TabsTrigger>
              <TabsTrigger value="student" className="text-xs">
                {t("wuyu.classOverview.viewStudent")}
              </TabsTrigger>
            </TabsList>
          </Tabs>
          {students.length > 0 && (
            <Badge variant="secondary" className="shrink-0">
              {t("wuyu.studentCount", { count: students.length })}
            </Badge>
          )}
          <Select value={classId} onValueChange={handleClassChange}>
            <SelectTrigger className="w-[220px] h-9">
              <SelectValue placeholder={t("wuyu.selectClass")} />
            </SelectTrigger>
            <SelectContent>
              {classes.map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* 主体：班级总览 / 学生画像 */}
      {view === "class" ? (
        <ClassOverviewPanel classId={classId} />
      ) : (
        <div className="flex h-[calc(100vh-13rem)] rounded-xl border border-border/50 bg-card overflow-hidden">
          {/* 左：学生列表 */}
          <div className="w-[30%] min-w-[220px] border-r border-border/50 flex flex-col">
            <div className="p-3 border-b border-border/40 space-y-2">
              <p className="text-xs font-medium text-muted-foreground">
                {t("wuyu.selectStudent")}
              </p>
              <Input
                className="h-8 text-sm"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder={t("wuyu.selectStudentHint")}
              />
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {!classId ? (
                <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                  <School className="w-8 h-8 opacity-30 mb-2" />
                  <p className="text-sm">{t("wuyu.selectClassHint")}</p>
                </div>
              ) : studentsLoading ? (
                <div className="flex items-center justify-center py-12 text-muted-foreground">
                  <Loader2 className="w-5 h-5 animate-spin" />
                </div>
              ) : filteredStudents.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                  <Users2 className="w-8 h-8 opacity-30 mb-2" />
                  <p className="text-sm">
                    {keyword ? t("wuyu.empty") : t("wuyu.noStudent")}
                  </p>
                </div>
              ) : (
                filteredStudents.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => setSelectedStudentId(s.id)}
                    className={cn(
                      "w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-left text-sm transition-all",
                      selectedStudentId === s.id
                        ? "bg-primary/10 text-primary font-medium"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    <UserSquare2 className="w-4 h-4 shrink-0" />
                    <span className="flex-1 truncate">{s.name}</span>
                  </button>
                ))
              )}
            </div>
          </div>

          {/* 右：详情 Tabs */}
          <div className="flex-1 min-w-0 overflow-y-auto p-4">
            {!selectedStudent ? (
              <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                <UserSquare2 className="w-12 h-12 opacity-30 mb-3" />
                <p className="text-sm font-medium">
                  {t("wuyu.selectStudentHint")}
                </p>
              </div>
            ) : (
              <>
                {/* 学生身份条 */}
                <div className="flex items-center gap-3 mb-3 rounded-lg border border-border/50 bg-muted/30 px-4 py-3">
                  <div className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center text-base font-bold shrink-0">
                    {selectedStudent.name.charAt(0)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-semibold text-foreground truncate">
                        {selectedStudent.name}
                      </span>
                      <Badge variant="secondary" className="shrink-0">
                        {selectedClassName || t("wuyu.noClass")}
                      </Badge>
                    </div>
                    {selectedStudent.student_number ? (
                      <p className="text-xs text-muted-foreground truncate mt-0.5">
                        {t("wuyu.studentNumber")}：
                        {selectedStudent.student_number}
                      </p>
                    ) : null}
                  </div>
                </div>

                <Tabs defaultValue="overview" className="w-full">
                  <TabsList className="mb-3">
                    <TabsTrigger value="dossier">
                      {t("wuyu.tab.dossier")}
                    </TabsTrigger>
                    <TabsTrigger value="overview">
                      {t("wuyu.tab.overview")}
                    </TabsTrigger>
                    <TabsTrigger value="growth">
                      {t("wuyu.tab.growth")}
                    </TabsTrigger>
                    <TabsTrigger value="assessment">
                      {t("wuyu.tab.assessment")}
                    </TabsTrigger>
                    <TabsTrigger value="incentive">
                      {t("wuyu.tab.incentive")}
                    </TabsTrigger>
                    <TabsTrigger value="report">
                      {t("wuyu.tab.report")}
                    </TabsTrigger>
                    <TabsTrigger value="comment">
                      {t("wuyu.tab.comment")}
                    </TabsTrigger>
                    <TabsTrigger value="memory">
                      {t("wuyu.tab.memory")}
                    </TabsTrigger>
                  </TabsList>

                  <TabsContent value="dossier" className="mt-0">
                    <DossierPanel
                      studentId={selectedStudent.id}
                      studentName={selectedStudent.name}
                    />
                  </TabsContent>

                  <TabsContent value="overview" className="mt-0">
                    {portfolioLoading ? (
                      <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
                        <Loader2 className="w-6 h-6 animate-spin mb-2" />
                        <p className="text-sm">{t("wuyu.loading")}</p>
                      </div>
                    ) : portfolioError ? (
                      <div className="flex flex-col items-center justify-center py-20 border border-dashed rounded-lg text-muted-foreground">
                        <p className="text-sm mb-2">{t("wuyu.loadFailed")}</p>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => refetch()}
                        >
                          {t("wuyu.retry")}
                        </Button>
                      </div>
                    ) : portfolio ? (
                      <PortfolioDetailPanel portfolio={portfolio} />
                    ) : null}
                  </TabsContent>

                  <TabsContent value="growth" className="mt-0">
                    <GrowthRecordsPanel studentId={selectedStudent.id} />
                  </TabsContent>

                  <TabsContent value="assessment" className="mt-0">
                    <AssessmentResultPanel studentId={selectedStudent.id} />
                  </TabsContent>

                  <TabsContent value="incentive" className="mt-0">
                    <StudentIncentivePanel studentId={selectedStudent.id} />
                  </TabsContent>

                  <TabsContent value="report" className="mt-0">
                    <SemesterReportPanel
                      studentId={selectedStudent.id}
                      studentName={selectedStudent.name}
                    />
                  </TabsContent>

                  <TabsContent value="comment" className="mt-0">
                    <AiCommentPanel studentId={selectedStudent.id} />
                  </TabsContent>

                  <TabsContent value="memory" className="mt-0">
                    <StudentMemoryPanel studentId={selectedStudent.id} />
                  </TabsContent>
                </Tabs>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
