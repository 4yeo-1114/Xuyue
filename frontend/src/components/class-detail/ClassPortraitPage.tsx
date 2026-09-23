import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  FileDown,
  FileSearch,
  Loader2,
  RefreshCw,
  AlertCircle,
  ClipboardList,
} from "lucide-react";
import html2canvas from "html2canvas";
import jsPDF from "jspdf";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSubjectName } from "@/i18n";
import {
  getClassAnalysisReport,
  listClassAnalysisSubjects,
} from "@/services/api";
import { SelectionPanel } from "@/components/wuyu-profile/SelectionPanel";
import { ClassAnalysisExamDialog } from "./class-portrait/ClassAnalysisExamDialog";
import { RealAnalysisDashboard } from "./class-portrait/RealAnalysisDashboard";

const FALLBACK_SUBJECTS = [
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
const SUBJECT_STORAGE_PREFIX = "class-analysis-subject:";

function storedSubject(classId: string, fallback: string) {
  try {
    return (
      localStorage.getItem(`${SUBJECT_STORAGE_PREFIX}${classId}`) || fallback
    );
  } catch {
    return fallback;
  }
}

interface ClassPortraitPageProps {
  selectedSubject: string;
  selectedClass: string;
  onNavigateToStudent?: (studentName: string) => void;
}

export function ClassPortraitPage({
  selectedSubject,
  selectedClass,
  onNavigateToStudent,
}: ClassPortraitPageProps) {
  const { locale, t } = useLocale();
  const [subject, setSubject] = useState(() =>
    storedSubject(selectedClass, selectedSubject || "语文"),
  );
  const [examDialogOpen, setExamDialogOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const reportRef = useRef<HTMLDivElement>(null);
  const lastGlobalSubject = useRef(selectedSubject);
  const lastClassId = useRef(selectedClass);

  useEffect(() => {
    if (selectedClass !== lastClassId.current) {
      lastClassId.current = selectedClass;
      lastGlobalSubject.current = selectedSubject;
      setSubject(storedSubject(selectedClass, selectedSubject || "语文"));
      return;
    }
    if (selectedSubject && selectedSubject !== lastGlobalSubject.current) {
      lastGlobalSubject.current = selectedSubject;
      setSubject(selectedSubject);
    }
  }, [selectedClass, selectedSubject]);

  useEffect(() => {
    if (!selectedClass || !subject) return;
    try {
      localStorage.setItem(
        `${SUBJECT_STORAGE_PREFIX}${selectedClass}`,
        subject,
      );
    } catch {
      // Browser storage can be unavailable in privacy-restricted environments.
    }
  }, [selectedClass, subject]);

  const { data: subjects = FALLBACK_SUBJECTS } = useQuery({
    queryKey: ["class-analysis-subjects"],
    queryFn: listClassAnalysisSubjects,
  });

  const { data, isLoading, isError, isFetching, refetch } = useQuery({
    queryKey: ["class-analysis-report", selectedClass, subject],
    queryFn: () => getClassAnalysisReport(selectedClass, subject),
    enabled: !!selectedClass && !!subject,
  });
  const report = data?.report || null;

  const exportPdf = useCallback(async () => {
    if (!reportRef.current || !report || exporting) return;
    setExporting(true);
    try {
      const canvas = await html2canvas(reportRef.current, {
        scale: 1.6,
        useCORS: true,
        logging: false,
        backgroundColor: "#ffffff",
      });
      const imageData = canvas.toDataURL("image/jpeg", 0.92);
      const pageWidth = 210;
      const pageHeight = 297;
      const imageHeight = (canvas.height * pageWidth) / canvas.width;
      const pdf = new jsPDF("p", "mm", "a4");
      let remaining = imageHeight;
      let position = 0;
      pdf.addImage(imageData, "JPEG", 0, position, pageWidth, imageHeight);
      remaining -= pageHeight;
      while (remaining > 0) {
        position -= pageHeight;
        pdf.addPage();
        pdf.addImage(imageData, "JPEG", 0, position, pageWidth, imageHeight);
        remaining -= pageHeight;
      }
      pdf.save(
        `${t("classAnalysis.fileName")}_${translateSubjectName(locale, subject)}_${new Date().toLocaleDateString(locale === "en" ? "en-US" : "zh-CN")}.pdf`,
      );
      toast.success(t("classAnalysis.exportSuccess"));
    } catch (error: unknown) {
      toast.error(t("classAnalysis.exportFailed"), {
        description:
          error instanceof Error ? error.message : t("classAnalysis.retry"),
      });
    } finally {
      setExporting(false);
    }
  }, [exporting, locale, report, subject, t]);

  return (
    <div className="space-y-5 pb-8 animate-fade-in">
      <Tabs defaultValue="analysis" className="space-y-5">
        <TabsList className="grid w-full max-w-md grid-cols-2">
          <TabsTrigger value="analysis" className="gap-1.5">
            <BarChart3 className="h-4 w-4" />
            {t("classAnalysis.title")}
          </TabsTrigger>
          <TabsTrigger value="selection" className="gap-1.5">
            <ClipboardList className="h-4 w-4" />
            {t("archive.tab.selection")}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="analysis" className="mt-0 space-y-5">
          <header className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-center gap-3">
              <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
                <BarChart3 className="h-5 w-5" />
              </span>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-xl font-bold text-foreground">
                    {t("classAnalysis.title")}
                  </h2>
                  <Badge variant="secondary">
                    {translateSubjectName(locale, subject)}
                  </Badge>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  {t("classAnalysis.subtitle")}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Select value={subject} onValueChange={setSubject}>
                <SelectTrigger className="h-9 w-[140px] text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(subjects.length ? subjects : FALLBACK_SUBJECTS).map(
                    (item) => (
                      <SelectItem key={item} value={item}>
                        {translateSubjectName(locale, item)}
                      </SelectItem>
                    ),
                  )}
                </SelectContent>
              </Select>
              <Button
                variant="outline"
                size="sm"
                className="gap-2"
                onClick={() => refetch()}
                disabled={isFetching}
                title={t("classAnalysis.refreshTitle")}
              >
                <RefreshCw
                  className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`}
                />
                {t("classAnalysis.refresh")}
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="gap-2"
                onClick={exportPdf}
                disabled={!report || exporting}
              >
                {exporting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <FileDown className="h-4 w-4" />
                )}
                {t("classAnalysis.exportPdf")}
              </Button>
              <Button
                size="sm"
                className="gap-2"
                onClick={() => setExamDialogOpen(true)}
              >
                <FileSearch className="h-4 w-4" />
                {report
                  ? t("classAnalysis.reanalyze")
                  : t("classAnalysis.selectExams")}
              </Button>
            </div>
          </header>

          {isLoading ? (
            <div className="flex h-[460px] flex-col items-center justify-center gap-3 text-muted-foreground">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
              <p className="text-sm">{t("classAnalysis.loading")}</p>
            </div>
          ) : isError ? (
            <div className="flex min-h-[460px] flex-col items-center justify-center rounded-lg border border-dashed bg-card px-6 text-center">
              <span className="flex h-14 w-14 items-center justify-center rounded-lg bg-destructive/10 text-destructive">
                <AlertCircle className="h-7 w-7" />
              </span>
              <h3 className="mt-5 text-base font-semibold">
                {t("classDetail.portraitLoadFailed")}
              </h3>
              <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">
                {t("classDetail.checkNetworkAndRetry")}
              </p>
              <Button
                className="mt-5 gap-2"
                variant="outline"
                onClick={() => refetch()}
                disabled={isFetching}
              >
                <RefreshCw
                  className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`}
                />
                {t("wuyu.retry")}
              </Button>
            </div>
          ) : !report ? (
            <div className="flex min-h-[460px] flex-col items-center justify-center rounded-lg border border-dashed bg-card px-6 text-center">
              <span className="flex h-14 w-14 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <BarChart3 className="h-7 w-7" />
              </span>
              <h3 className="mt-5 text-base font-semibold">
                {t("classAnalysis.emptyTitle", {
                  subject: translateSubjectName(locale, subject),
                })}
              </h3>
              <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">
                {t("classAnalysis.emptyDescription")}
              </p>
              <Button
                className="mt-5 gap-2"
                onClick={() => setExamDialogOpen(true)}
              >
                <FileSearch className="h-4 w-4" />
                {t("classAnalysis.selectExams")}
              </Button>
            </div>
          ) : (
            <div ref={reportRef}>
              <RealAnalysisDashboard
                key={report.id}
                report={report}
                onNavigateToStudent={onNavigateToStudent}
              />
            </div>
          )}
        </TabsContent>

        <TabsContent value="selection" className="mt-0">
          <SelectionPanel classId={selectedClass} />
        </TabsContent>
      </Tabs>

      <ClassAnalysisExamDialog
        open={examDialogOpen}
        onOpenChange={setExamDialogOpen}
        classId={selectedClass}
        subject={subject}
        currentFolderNames={report?.imported_folder_names || []}
      />
    </div>
  );
}
