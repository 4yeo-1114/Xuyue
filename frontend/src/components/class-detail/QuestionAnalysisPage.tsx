import { useState, useMemo, useRef, useCallback, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import html2canvas from "html2canvas";
import jsPDF from "jspdf";
import { toast } from "sonner";
import { AlertTriangle, FileText, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getClassReviewReport } from "@/services/api";
import { getErrorBookFolderDetail } from "@/services/gradingApi";
import { AnalysisHeader } from "./question-analysis/AnalysisHeader";
import { PaperOverview } from "./question-analysis/PaperOverview";
import { QuestionList } from "./question-analysis/QuestionList";
import { QuestionDetail } from "./question-analysis/QuestionDetail";
import {
  TypicalErrors,
  type TypicalErrorItem,
} from "./question-analysis/TypicalErrors";
import { TeachingSuggestions } from "./question-analysis/TeachingSuggestions";
import { QuestionAnalysisTour } from "./question-analysis/QuestionAnalysisTour";
import {
  buildQuestionAnalysisData,
  type QuestionAnalysisData,
} from "./question-analysis/types";

interface QuestionAnalysisPageProps {
  selectedSubject: string;
  selectedClass: string;
  schoolLevel: string;
  onNavChange: (id: string) => void;
  onNavigateToStudent?: (name: string) => void;
}

export function QuestionAnalysisPage({
  selectedSubject,
  selectedClass,
  schoolLevel,
  onNavChange,
  onNavigateToStudent,
}: QuestionAnalysisPageProps) {
  const { t } = useLocale();

  const [selectedQuestionKey, setSelectedQuestionKey] = useState<string | null>(
    null,
  );
  const [exporting, setExporting] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);

  const {
    data: reportData,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["class-review-report", selectedClass, selectedSubject],
    queryFn: () => getClassReviewReport(selectedClass, selectedSubject),
    enabled: !!selectedClass && !!selectedSubject,
  });
  const report = reportData?.report ?? null;

  // 原始逐题明细（错题本）：提供错题学生名单，可选增强
  const firstFolder = report?.imported_folder_names?.[0];
  const { data: folderDetail } = useQuery({
    queryKey: ["error-book-folder-detail", firstFolder],
    queryFn: () => getErrorBookFolderDetail(firstFolder as string),
    enabled: !!firstFolder,
    retry: 1,
  });

  const analysis = useMemo<QuestionAnalysisData | null>(() => {
    if (!report) return null;
    return buildQuestionAnalysisData(report, folderDetail?.questions ?? []);
  }, [report, folderDetail]);

  // Auto-select the lowest score-rate question only when nothing is selected yet,
  // or the current selection no longer exists. Never override a user's manual pick.
  useEffect(() => {
    if (!analysis || analysis.questions.length === 0) {
      setSelectedQuestionKey(null);
      return;
    }
    setSelectedQuestionKey((prev) => {
      if (prev && analysis.questions.some((q) => q.key === prev)) return prev;
      const sorted = [...analysis.questions].sort(
        (a, b) => a.scoreRate - b.scoreRate,
      );
      return sorted[0].key;
    });
  }, [analysis]);

  const selectedQuestion = useMemo(
    () =>
      analysis?.questions.find((q) => q.key === selectedQuestionKey) ?? null,
    [analysis, selectedQuestionKey],
  );

  const typicalErrors = useMemo<TypicalErrorItem[]>(() => {
    if (!selectedQuestion) return [];
    const items: TypicalErrorItem[] = [];
    const seen = new Set<string>();
    for (const r of selectedQuestion.reasons) {
      if (seen.has(r.text)) continue;
      seen.add(r.text);
      items.push({
        key: r.text,
        title: r.text,
        count: r.count,
        percent: selectedQuestion.totalCount
          ? Math.round((r.count / selectedQuestion.totalCount) * 100)
          : 0,
        students: selectedQuestion.wrongStudents,
      });
    }
    for (const p of selectedQuestion.errorPatterns) {
      if (seen.has(p)) continue;
      seen.add(p);
      items.push({
        key: p,
        title: p,
        count: 0,
        percent: 0,
        description: p,
        students: selectedQuestion.wrongStudents,
      });
    }
    return items.slice(0, 5);
  }, [selectedQuestion]);

  const handleExportPDF = useCallback(async () => {
    if (!contentRef.current || exporting || !analysis) return;
    setExporting(true);
    try {
      const canvas = await html2canvas(contentRef.current, {
        scale: 2,
        useCORS: true,
        logging: false,
        backgroundColor: "#ffffff",
      });
      const imgData = canvas.toDataURL("image/jpeg", 0.92);
      const pageWidth = 210;
      const pageHeight = 297;
      const imgWidth = pageWidth;
      const imgHeight = (canvas.height * imgWidth) / canvas.width;
      const pdf = new jsPDF("p", "mm", "a4");
      let heightLeft = imgHeight;
      let position = 0;
      pdf.addImage(imgData, "JPEG", 0, position, imgWidth, imgHeight);
      heightLeft -= pageHeight;
      while (heightLeft > 0) {
        position -= pageHeight;
        pdf.addPage();
        pdf.addImage(imgData, "JPEG", 0, position, imgWidth, imgHeight);
        heightLeft -= pageHeight;
      }
      pdf.save(
        `${t("classDetail.questionReportFileName")}_${selectedClass}_${selectedSubject}_${new Date().toLocaleDateString()}.pdf`,
      );
      toast.success(t("classDetail.exportReportSuccess"));
    } catch (e) {
      console.error("PDF export failed:", e);
      toast.error(t("classDetail.exportReportFailed"));
    } finally {
      setExporting(false);
    }
  }, [exporting, analysis, selectedClass, selectedSubject]);

  if (isLoading) {
    return (
      <div className="flex h-[400px] flex-col items-center justify-center gap-3 text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
        <p className="text-sm">{t("common.loading")}</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex h-[300px] flex-col items-center justify-center gap-3 text-center text-muted-foreground">
        <AlertTriangle className="h-6 w-6 text-destructive" />
        <p className="text-sm">
          {t("classDetail.loadFailedWith", {
            message:
              error instanceof Error
                ? error.message
                : t("classDetail.unknownError"),
          })}
        </p>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          {t("wuyu.retry")}
        </Button>
      </div>
    );
  }

  if (!report || !analysis) {
    return (
      <div className="flex h-[400px] flex-col items-center justify-center gap-4 text-center animate-fade-in">
        <div className="rounded-full bg-muted/30 p-4">
          <FileText className="h-8 w-8 text-muted-foreground/50" />
        </div>
        <div>
          <h3 className="font-semibold text-foreground">
            {t("classDetail.noQuestionAnalysisReport")}
          </h3>
          <p className="mt-1 text-sm text-muted-foreground max-w-[320px]">
            {t("classDetail.questionAnalysisEmptyDesc")}
          </p>
        </div>
        <Button onClick={() => onNavChange("ai-review")} className="mt-2">
          {t("classDetail.goClassReview")}
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in pb-6" ref={contentRef}>
      <QuestionAnalysisTour />

      <AnalysisHeader
        selectedSubject={selectedSubject}
        schoolLevel={schoolLevel}
        examNames={analysis.summary.examNames}
        onExportPDF={handleExportPDF}
        exporting={exporting}
      />

      {/* Row 1: Paper overview + Question list */}
      <div className="flex gap-4 flex-wrap">
        <PaperOverview summary={analysis.summary} />
        <div className="flex-1 min-w-[420px] space-y-2">
          <QuestionList
            questions={analysis.questions}
            selectedKey={selectedQuestionKey}
            onSelect={setSelectedQuestionKey}
          />
        </div>
      </div>

      {/* Row 2: Selected question detail */}
      {selectedQuestion && (
        <QuestionDetail
          question={selectedQuestion}
          onNavigateToStudent={onNavigateToStudent}
        />
      )}

      {/* Row 3: Typical errors + Teaching suggestions */}
      {selectedQuestion && (
        <div className="flex gap-4 flex-wrap">
          <TypicalErrors
            errors={typicalErrors}
            questionKnowledge={selectedQuestion.knowledgePoint}
          />
          <TeachingSuggestions
            question={selectedQuestion}
            overview={analysis.overview}
            tieredPractice={analysis.tieredPractice}
          />
          {selectedQuestion.wrongStudents &&
            selectedQuestion.wrongStudents.length > 0 && (
              <Card className="flex-1 min-w-[300px]">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-semibold">
                    {t("questionAnalysis.wrongStudents.title")}
                    <span className="ml-1.5 text-xs font-normal text-muted-foreground">
                      {t("questionAnalysis.wrongStudents.count", {
                        count: selectedQuestion.wrongStudents.length,
                      })}
                    </span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="max-h-56 overflow-y-auto pr-1">
                  <div className="flex flex-wrap gap-1.5">
                    {selectedQuestion.wrongStudents.map((name) => (
                      <span
                        key={name}
                        className="rounded-md bg-muted/40 border border-border/50 px-2 py-1 text-xs text-foreground"
                      >
                        {name}
                      </span>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
        </div>
      )}
    </div>
  );
}
