import { useState, useMemo, useRef, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import { toast } from "@/hooks/use-toast";
import html2canvas from "html2canvas";
import jsPDF from "jspdf";
import {
  Loader2,
  RefreshCw,
  BarChart3,
  GitCompare,
  Trophy,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
} from "recharts";
import {
  getClassAnalysisReport,
  getGradeComparison,
  type GradeComparisonData,
} from "@/services/api";
import { CompareHeader } from "./compare-analysis/CompareHeader";
import { RankingDashboard } from "./compare-analysis/RankingDashboard";
import { MetricsComparison } from "./compare-analysis/MetricsComparison";
import { CompareRadar } from "./compare-analysis/CompareRadar";
import { ExperienceMining } from "./compare-analysis/ExperienceMining";
import { ChasingPlan } from "./compare-analysis/ChasingPlan";
import { HistoryTrend } from "./compare-analysis/HistoryTrend";
import { CompareOverviewCard } from "./compare-analysis/CompareOverviewCard";
import {
  buildStudentRankings,
  buildCoreMetrics,
  buildHistoryTrend,
  buildWeakPoints,
  buildCompareOverview,
} from "./compare-analysis/compareAnalysisAdapter";
import {
  CompareAnalysisTour,
  CompareTipProvider,
  CompareInlineTip,
  CaTipAlert,
  CaTipTrendUp,
  CaTipTrendDown,
  CaTipLightbulb,
  CaTipClock,
} from "./compare-analysis/CompareAnalysisTour";

interface CompareAnalysisPageProps {
  selectedSubject: string;
  selectedClass: string;
  schoolLevel: string;
  onNavChange: (id: string) => void;
}

export function CompareAnalysisPage({
  selectedSubject,
  selectedClass,
  schoolLevel,
  onNavChange,
}: CompareAnalysisPageProps) {
  const { t } = useLocale();

  const [exporting, setExporting] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  // 对标范围（受控）：「年级内部」已启用并触发跨班对标加载，其余范围后续接入
  const [scope, setScope] = useState("grade");

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["class-analysis-report", selectedClass, selectedSubject],
    queryFn: () => getClassAnalysisReport(selectedClass, selectedSubject),
    enabled: !!selectedClass && !!selectedSubject,
  });
  const report = data?.report ?? null;

  const {
    data: gradeData,
    isLoading: gradeLoading,
    isError: gradeError,
    refetch: refetchGrade,
  } = useQuery({
    queryKey: ["grade-comparison", selectedClass, selectedSubject],
    queryFn: () => getGradeComparison(selectedClass, selectedSubject),
    enabled: !!selectedClass && !!selectedSubject && scope === "grade",
  });

  const rankings = useMemo(
    () => (report ? buildStudentRankings(report) : []),
    [report],
  );
  const metrics = useMemo(
    () => (report ? buildCoreMetrics(report) : []),
    [report],
  );
  const trendData = useMemo(
    () => (report ? buildHistoryTrend(report) : []),
    [report],
  );
  const weakPoints = useMemo(
    () => (report ? buildWeakPoints(report) : []),
    [report],
  );
  const overview = useMemo(
    () =>
      report ? buildCompareOverview(report, t("classDetail.thisClass")) : null,
    [report, t],
  );

  const className = overview?.className ?? t("classDetail.thisClass");
  const latestExamName = overview?.latestExamName ?? "";
  const scoreDelta = overview?.averageScoreChange ?? 0;
  const trendUp = scoreDelta > 0;
  const trendDown = scoreDelta < 0;

  const handleExportPDF = useCallback(async () => {
    if (!contentRef.current || exporting) return;
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
        `${t("classDetail.compareReportFileName")}_${selectedSubject}_${new Date().toLocaleDateString()}.pdf`,
      );
    } catch (e) {
      console.error("PDF export failed:", e);
      toast({
        variant: "destructive",
        title: t("classDetail.compare.pdfExportFailed"),
      });
    } finally {
      setExporting(false);
    }
  }, [exporting, selectedSubject, t]);

  if (isLoading) {
    return (
      <CompareTipProvider>
        <CompareAnalysisTour />
        <div className="flex h-[460px] flex-col items-center justify-center gap-3 text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
          <p className="text-sm">{t("classDetail.compareAnalysisLoading")}</p>
        </div>
      </CompareTipProvider>
    );
  }

  if (isError) {
    return (
      <CompareTipProvider>
        <CompareAnalysisTour />
        <div className="flex min-h-[460px] flex-col items-center justify-center rounded-lg border border-dashed bg-card px-6 text-center">
          <BarChart3 className="h-7 w-7 text-destructive" />
          <h3 className="mt-4 text-base font-semibold">
            {t("classDetail.compareAnalysisLoadFailed")}
          </h3>
          <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">
            {t("classDetail.checkNetworkRetryLater")}
          </p>
          <Button className="mt-5 gap-2" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4" />
            {t("classDetail.reload")}
          </Button>
        </div>
      </CompareTipProvider>
    );
  }

  if (!report) {
    return (
      <CompareTipProvider>
        <CompareAnalysisTour />
        <div className="flex min-h-[460px] flex-col items-center justify-center rounded-lg border border-dashed bg-card px-6 text-center">
          <BarChart3 className="h-7 w-7 text-primary" />
          <h3 className="mt-5 text-base font-semibold">
            {t("classDetail.noAnalysisReport")}
          </h3>
          <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">
            {t("classDetail.compareAnalysisEmptyDesc")}
          </p>
          <Button
            className="mt-5 gap-2"
            onClick={() => onNavChange("analytics-portrait")}
          >
            <BarChart3 className="h-4 w-4" />
            {t("classDetail.goGenerateAnalysis")}
          </Button>
        </div>
      </CompareTipProvider>
    );
  }

  return (
    <CompareTipProvider>
      <div className="space-y-5 animate-fade-in pb-6" ref={contentRef}>
        <CompareAnalysisTour />
        <CompareHeader
          selectedSubject={selectedSubject}
          schoolLevel={schoolLevel}
          scope={scope}
          onScopeChange={setScope}
          onExportPDF={handleExportPDF}
          exporting={exporting}
        />

        {/* 同年级跨班对标（grade-comparison） */}
        <GradeComparisonBlock
          data={gradeData}
          isLoading={gradeLoading}
          isError={gradeError}
          onRetry={refetchGrade}
        />

        {/* Overall overview (analysis.overall_level) */}
        {overview ? <CompareOverviewCard overview={overview} /> : null}

        {/* Row 1: Ranking + Metrics */}
        <CompareInlineTip
          id="trend-change"
          icon={
            trendUp ? CaTipTrendUp : trendDown ? CaTipTrendDown : CaTipLightbulb
          }
          text={
            trendUp
              ? t("classDetail.avgUp", { delta: scoreDelta })
              : trendDown
                ? t("classDetail.avgDown", { delta: Math.abs(scoreDelta) })
                : t("classDetail.avgFlat")
          }
          type={trendUp ? "hint" : trendDown ? "warning" : "info"}
          show={(overview?.examCount ?? 0) >= 2}
        />
        <div className="flex gap-4 flex-wrap">
          <RankingDashboard rankings={rankings} examName={latestExamName} />
          <MetricsComparison
            rows={metrics}
            strengths={overview?.strengths ?? []}
            weakPoints={weakPoints}
            examName={latestExamName}
          />
        </div>

        {/* Findings tip */}
        <CompareInlineTip
          id="lagging-metrics"
          icon={CaTipAlert}
          text={t("classDetail.weakPointsTip", { count: weakPoints.length })}
          type="warning"
          show={weakPoints.length >= 3}
        />

        {/* Row 2: Radar comparison（六维能力，本班 vs 班级平均） */}
        <CompareRadar
          className={className}
          capabilityDimensions={report.analysis?.capability_dimensions}
        />

        {/* Trend tip */}
        <CompareInlineTip
          id="trend-tip"
          icon={
            trendUp ? CaTipTrendUp : trendDown ? CaTipTrendDown : CaTipLightbulb
          }
          text={
            (overview?.examCount ?? 0) < 2
              ? t("classDetail.trendSingleExam")
              : trendUp
                ? t("classDetail.trendUp", { delta: scoreDelta })
                : trendDown
                  ? t("classDetail.trendDown", { delta: Math.abs(scoreDelta) })
                  : t("classDetail.trendFlat")
          }
          type={
            (overview?.examCount ?? 0) < 2
              ? "info"
              : trendDown
                ? "warning"
                : "hint"
          }
          show={true}
        />

        {/* Row 2.5: History trend */}
        <HistoryTrend data={trendData} className={className} />

        {/* Experience tip */}
        <CompareInlineTip
          id="experience-tip"
          icon={CaTipLightbulb}
          text={t("classDetail.experienceUnsupported")}
          type="info"
          show={true}
        />

        {/* Row 3: Experience (degraded) + Chasing */}
        <div className="flex gap-4 flex-wrap">
          <ExperienceMining benchmarkClass={gradeData?.benchmarkClass} />
          <div className="flex-1 min-w-[320px] space-y-0">
            <CompareInlineTip
              id="chasing-not-started"
              icon={CaTipClock}
              text={
                weakPoints.length > 0
                  ? t("classDetail.catchUpSuggestions", {
                      count: weakPoints.length,
                    })
                  : t("classDetail.compare.chasing.notStartedTip")
              }
              type="warning"
              show={true}
            />
            <ChasingPlan weakPoints={weakPoints} />
          </div>
        </div>
      </div>
    </CompareTipProvider>
  );
}

/** 同年级跨班对标区块：指标对比表 + 各班均分柱状图 + 本班年级排名徽章。 */
function GradeComparisonBlock({
  data,
  isLoading,
  isError,
  onRetry,
}: {
  data: GradeComparisonData | undefined;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}) {
  const { t } = useLocale();
  const title = t("classDetail.compare.gradeComparison.title");

  if (isLoading) {
    return (
      <Card data-tour="ca-grade-compare">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold">{title}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex h-[200px] items-center justify-center gap-3 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
            <p className="text-sm">
              {t("classDetail.compare.gradeComparison.loading")}
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (isError || !data) {
    return (
      <Card data-tour="ca-grade-compare">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold">{title}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex h-[200px] flex-col items-center justify-center rounded-lg border border-dashed bg-card px-6 text-center">
            <BarChart3 className="h-6 w-6 text-destructive" />
            <h3 className="mt-3 text-sm font-semibold">
              {t("classDetail.compare.gradeComparison.loadFailed")}
            </h3>
            <Button
              className="mt-4 gap-2"
              variant="outline"
              size="sm"
              onClick={onRetry}
            >
              <RefreshCw className="h-4 w-4" />
              {t("classDetail.reload")}
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  const peers = data.peerClasses ?? [];
  if (peers.length === 0) {
    return (
      <Card data-tour="ca-grade-compare">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold">{title}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex h-[200px] flex-col items-center justify-center rounded-lg border border-dashed bg-card px-6 text-center">
            <GitCompare className="h-6 w-6 text-muted-foreground" />
            <p className="mt-3 text-sm font-medium text-foreground">
              {t("classDetail.compare.gradeComparison.empty")}
            </p>
            <p className="mt-1 max-w-md text-xs leading-5 text-muted-foreground">
              {t("classDetail.compare.gradeComparison.emptyDesc")}
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const current = data.currentClass;
  const chartData = peers.map((p) => ({
    name: p.className,
    averageScore: p.averageScore,
    isCurrent: p.isCurrent,
  }));

  const renderTrend = (delta: number | null | undefined) => {
    if (delta === null || delta === undefined || delta === 0) {
      return (
        <span className="text-muted-foreground">
          {t("classDetail.compare.gradeComparison.table.trendFlat")}
        </span>
      );
    }
    const up = delta > 0;
    return (
      <span className={up ? "text-emerald-600" : "text-destructive"}>
        {up ? "↑" : "↓"}
        {t("classDetail.compare.gradeComparison.table.trendDelta", {
          delta: Math.abs(delta).toFixed(1),
        })}
      </span>
    );
  };

  return (
    <Card data-tour="ca-grade-compare">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <GitCompare className="h-4 w-4 text-primary" />
            {title}
          </CardTitle>
          <Badge variant="outline" className="gap-1">
            <Trophy className="h-3 w-3" />
            {t("classDetail.compare.gradeComparison.rankBadge", {
              rank: current?.rank ?? "--",
              total: peers.length,
            })}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 各班期末均分柱状图（本班高亮） */}
        <div className="h-[220px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={chartData}
              margin={{ top: 5, right: 10, left: -15, bottom: 0 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="hsl(var(--border))"
              />
              <XAxis
                dataKey="name"
                tick={{
                  fontSize: 10,
                  fill: "hsl(var(--muted-foreground))",
                }}
              />
              <YAxis
                tick={{
                  fontSize: 10,
                  fill: "hsl(var(--muted-foreground))",
                }}
              />
              <Tooltip
                contentStyle={{
                  fontSize: 11,
                  borderRadius: 8,
                  border: "1px solid hsl(var(--border))",
                }}
              />
              <Bar
                dataKey="averageScore"
                name={t(
                  "classDetail.compare.gradeComparison.table.averageScore",
                )}
                radius={[4, 4, 0, 0]}
              >
                {chartData.map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={
                      entry.isCurrent
                        ? "hsl(var(--primary))"
                        : "hsl(var(--muted-foreground))"
                    }
                    fillOpacity={entry.isCurrent ? 1 : 0.45}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* 指标对比表 */}
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>
                  {t("classDetail.compare.gradeComparison.table.className")}
                </TableHead>
                <TableHead className="text-center">
                  {t("classDetail.compare.gradeComparison.table.averageScore")}
                </TableHead>
                <TableHead className="text-center">
                  {t("classDetail.compare.gradeComparison.table.passRate")}
                </TableHead>
                <TableHead className="text-center">
                  {t("classDetail.compare.gradeComparison.table.highestScore")}
                </TableHead>
                <TableHead className="text-center">
                  {t("classDetail.compare.gradeComparison.table.trend")}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {peers.map((p) => (
                <TableRow
                  key={p.classId}
                  className={cn(
                    p.isCurrent ? "bg-primary/5 font-semibold" : "",
                  )}
                >
                  <TableCell className="text-foreground">
                    <span className="flex items-center gap-1.5">
                      {p.className}
                      {p.isCurrent ? (
                        <Badge
                          variant="secondary"
                          className="text-[10px] px-1.5 py-0"
                        >
                          {t(
                            "classDetail.compare.gradeComparison.table.currentClass",
                          )}
                        </Badge>
                      ) : null}
                    </span>
                  </TableCell>
                  <TableCell className="text-center">
                    {p.averageScore ?? "--"}
                  </TableCell>
                  <TableCell className="text-center">
                    {p.passRate != null ? `${p.passRate}%` : "--"}
                  </TableCell>
                  <TableCell className="text-center">
                    {p.highestScore ?? "--"}
                  </TableCell>
                  <TableCell className="text-center">
                    {renderTrend(p.trendDelta)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        {/* 年级均分/及格率 + 标杆班 */}
        <div className="flex flex-wrap gap-x-5 gap-y-1.5 text-xs">
          <span className="text-muted-foreground">
            {t("classDetail.compare.gradeComparison.gradeAvg")}：
            <strong className="text-foreground">
              {data.gradeAvg?.averageScore ?? "--"}
            </strong>
          </span>
          <span className="text-muted-foreground">
            {t("classDetail.compare.gradeComparison.gradePassRate")}：
            <strong className="text-foreground">
              {data.gradeAvg?.passRate != null
                ? `${data.gradeAvg.passRate}%`
                : "--"}
            </strong>
          </span>
          {data.benchmarkClass ? (
            <span className="text-muted-foreground">
              {t("classDetail.compare.gradeComparison.benchmark")}：
              <strong className="text-foreground">
                {data.benchmarkClass.className}
              </strong>
              <span className="ml-1">
                {data.benchmarkClass.averageScore ?? "--"}
              </span>
            </span>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
