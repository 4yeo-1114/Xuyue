import { useCallback, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  School,
  TrendingUp,
  Users,
  Target,
  BookOpen,
  AlertCircle,
  BarChart3,
  LineChart as LineChartIcon,
  Activity,
  Loader2,
  RefreshCw,
  FileDown,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";
import html2canvas from "html2canvas";
import jsPDF from "jspdf";
import { toast } from "@/hooks/use-toast";
import { getGradeSummary } from "@/services/api";
import { normalizeGrade } from "@/i18n";

interface GradeAnalysisPageProps {
  selectedSubject: string;
  schoolLevel: string;
  selectedGrade: string;
  onNavChange: (id: string) => void;
}

/** 多班折线色板（超出后循环使用） */
const LINE_COLORS = [
  "#6366f1",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#06b6d4",
  "#a855f7",
  "#ec4899",
  "#84cc16",
];

function formatNumber(value: number | null | undefined, digits = 1): string {
  if (value == null || Number.isNaN(Number(value))) return "--";
  return Number(value).toFixed(digits);
}

function severityBadgeClass(severity: string): string {
  switch (severity) {
    case "high":
      return "bg-red-500/10 text-red-600 border-red-500/30";
    case "medium":
      return "bg-orange-500/10 text-orange-600 border-orange-500/30";
    default:
      return "bg-emerald-500/10 text-emerald-600 border-emerald-500/30";
  }
}

/** 从班级名末尾提取班号（如"演示-小学五年级1班" → 1），提取不到返回 null */
function classNumber(name: string): number | null {
  const m = name.match(/(\d+)班$/);
  return m ? Number(m[1]) : null;
}

/**
 * 按班号升序比较班级名；班号相同或提取不到时按 className localeCompare 兜底。
 * 排序时以原始索引作稳定兜底（见 classRows 排序逻辑）。
 */
function compareByClassNumber(a: string, b: string): number {
  const na = classNumber(a);
  const nb = classNumber(b);
  if (na != null && nb != null && na !== nb) return na - nb;
  return a.localeCompare(b, "zh-CN");
}

export function GradeAnalysisPage({
  selectedSubject,
  schoolLevel,
  selectedGrade,
  onNavChange,
}: GradeAnalysisPageProps) {
  const { t } = useLocale();

  const [exporting, setExporting] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["grade-summary", selectedGrade, selectedSubject],
    queryFn: () => getGradeSummary(normalizeGrade(selectedGrade), selectedSubject),
    enabled: !!selectedGrade && !!selectedSubject,
  });

  // 后端 classRows 按期末均分降序返回，前端按班号升序重排（稳定排序）
  const classRows = useMemo(() => {
    const rows = data?.classRows ?? [];
    return rows
      .map((row, idx) => ({ row, idx }))
      .sort((a, b) => {
        const cmp = compareByClassNumber(a.row.className, b.row.className);
        return cmp !== 0 ? cmp : a.idx - b.idx;
      })
      .map(({ row }) => row);
  }, [data]);
  const weakPoints = data?.weakPointsTop5 ?? [];
  const trend = data?.trendSeries;

  // 趋势 perClass 按 classRows 排序后的班级名对齐（找不到的班级保持相对位置末尾）
  const sortedPerClass = useMemo(() => {
    const perClass = trend?.perClass ?? [];
    const byName = new Map(perClass.map((c) => [c.className, c]));
    const seen = new Set<string>();
    const found: typeof perClass = [];
    for (const name of classRows.map((c) => c.className)) {
      const item = byName.get(name);
      if (item && !seen.has(name)) {
        found.push(item);
        seen.add(name);
      }
    }
    const notFound = perClass.filter((c) => !seen.has(c.className));
    return [...found, ...notFound];
  }, [trend, classRows]);

  const hasRealData =
    classRows.length > 0 ||
    weakPoints.length > 0 ||
    (trend?.examNames.length ?? 0) > 0;

  const barChartData = useMemo(
    () =>
      classRows.map((c) => ({
        className: c.className,
        averageScore: c.averageScore,
        passRate: c.passRate,
      })),
    [classRows],
  );

  const trendChartData = useMemo(() => {
    const names = trend?.examNames ?? [];
    return names.map((exam, idx) => {
      const row: Record<string, string | number | null> = { exam };
      sortedPerClass.forEach((c) => {
        row[c.className] = c.scores?.[idx] ?? null;
      });
      return row;
    });
  }, [trend, sortedPerClass]);

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
        `${t("classDetail.gradeAnalysisBriefFileName")}_${selectedGrade}_${selectedSubject}_${new Date().toLocaleDateString()}.pdf`,
      );
    } catch (e) {
      console.error("PDF export failed:", e);
      toast({
        variant: "destructive",
        title: t("classDetail.gradeAnalysisExportFailed"),
      });
    } finally {
      setExporting(false);
    }
  }, [exporting, selectedGrade, selectedSubject, t]);

  const severityLabel = (severity: string) =>
    severity === "high"
      ? t("classDetail.gradeAnalysisSeverityHigh")
      : severity === "medium"
        ? t("classDetail.gradeAnalysisSeverityMedium")
        : t("classDetail.gradeAnalysisSeverityLow");

  return (
    <div
      ref={contentRef}
      className="space-y-6 animate-in fade-in duration-300 pb-6"
    >
      {/* 头部 */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground tracking-tight flex items-center gap-2">
            <School className="w-6 h-6 text-primary" />
            {t("classDetail.gradeAnalysisTitle")}
          </h1>
          <p className="text-sm text-muted-foreground mt-1.5 flex items-center gap-2">
            {t("classDetail.gradeAnalysisCurrentView")}
            <span className="font-medium text-foreground">
              {schoolLevel} {selectedGrade || t("classDetail.全部年级")}{" "}
              {selectedSubject || t("classDetail.全部学科")}
            </span>
            <span className="text-muted-foreground/50">|</span>
            {t("classDetail.gradeAnalysisSubtitle")}
          </p>
        </div>
        <div className="flex gap-2 items-center">
          <Button
            variant="outline"
            className="gap-2 bg-card"
            disabled
            title={t("classDetail.metricDetailPending")}
          >
            <BookOpen className="w-4 h-4" />
            {t("classDetail.gradeAnalysisSubjectReport")}
            <span className="text-[10px] font-normal text-muted-foreground/80">
              {t("classDetail.metricDetailPending")}
            </span>
          </Button>
          <Button
            className="gap-2"
            onClick={handleExportPDF}
            disabled={!hasRealData || exporting || isLoading}
            title={
              hasRealData
                ? t("classDetail.gradeAnalysisGenerateBrief")
                : t("classDetail.gradeAnalysisEmptyData")
            }
          >
            {exporting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <FileDown className="w-4 h-4" />
            )}
            {exporting
              ? t("classDetail.gradeAnalysisExporting")
              : t("classDetail.gradeAnalysisGenerateBrief")}
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex min-h-[360px] flex-col items-center justify-center gap-3 rounded-lg border border-dashed bg-card text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
          <p className="text-sm">{t("classDetail.gradeAnalysisLoading")}</p>
        </div>
      ) : isError ? (
        <div className="flex min-h-[360px] flex-col items-center justify-center rounded-lg border border-dashed bg-card px-6 text-center">
          <AlertCircle className="h-7 w-7 text-destructive" />
          <h3 className="mt-4 text-base font-semibold">
            {t("classDetail.gradeAnalysisLoadFailed")}
          </h3>
          <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">
            {t("classDetail.checkNetworkRetryLater")}
          </p>
          <Button className="mt-5 gap-2" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4" />
            {t("classDetail.gradeAnalysisRetry")}
          </Button>
        </div>
      ) : (
        <>
          {/* 数据看板 */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              {
                title: t("classDetail.本年级总人数"),
                icon: Users,
                color: "text-blue-500",
                bg: "bg-blue-500/10",
                value: data ? `${data.totalStudents}` : "--",
              },
              {
                title: t("classDetail.学科均分"),
                icon: BarChart3,
                color: "text-primary",
                bg: "bg-primary/10",
                value: data ? formatNumber(data.subjectAverage) : "--",
              },
              {
                title: t("classDetail.及格率"),
                icon: Target,
                color: "text-emerald-500",
                bg: "bg-emerald-500/10",
                value: data ? `${formatNumber(data.passRate)}%` : "--",
              },
              {
                title: t("classDetail.需关注人数"),
                icon: AlertCircle,
                color: "text-orange-500",
                bg: "bg-orange-500/10",
                value: data ? `${data.attentionCount}` : "--",
              },
            ].map((item, idx) => (
              <Card
                key={idx}
                className="border-border/50 shadow-sm overflow-hidden"
              >
                <CardContent className="p-5 flex items-center gap-4">
                  <div
                    className={cn(
                      "w-12 h-12 rounded-xl flex items-center justify-center shrink-0",
                      item.bg,
                    )}
                  >
                    <item.icon className={cn("w-6 h-6", item.color)} />
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground font-medium">
                      {item.title}
                    </p>
                    <h3 className="text-2xl font-bold mt-1 text-foreground">
                      {item.value}
                    </h3>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* 左侧：班级横向对比 */}
            <Card className="lg:col-span-2 border-border/50 shadow-sm flex flex-col">
              <CardHeader className="pb-2 border-b border-border/40 shrink-0">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base flex items-center gap-2">
                    <BarChart3 className="w-5 h-5 text-primary" />
                    {t("classDetail.gradeAnalysisClassComparisonTitle")}
                  </CardTitle>
                  {classRows.length > 0 && (
                    <div className="flex items-center gap-2 text-xs text-muted-foreground bg-muted/30 px-2 py-1 rounded-md">
                      <Activity className="w-3.5 h-3.5" />
                      {t("classDetail.gradeAnalysisReadyData")}
                    </div>
                  )}
                </div>
                <CardDescription>
                  {t("classDetail.gradeAnalysisClassComparisonDesc")}
                </CardDescription>
              </CardHeader>
              <CardContent className="flex-1 flex flex-col p-4 min-h-[300px]">
                {classRows.length === 0 ? (
                  <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
                    <div className="w-20 h-20 rounded-full bg-muted/40 flex items-center justify-center mb-4 border border-dashed border-border">
                      <BarChart3 className="w-10 h-10 text-muted-foreground/30" />
                    </div>
                    <h3 className="text-base font-semibold text-foreground mb-1">
                      {t("classDetail.gradeAnalysisNoComparisonData")}
                    </h3>
                    <p className="text-sm text-muted-foreground max-w-sm">
                      {t("classDetail.gradeAnalysisNoComparisonDesc")}
                    </p>
                  </div>
                ) : (
                  <>
                    <div className="h-[260px] w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          data={barChartData}
                          margin={{
                            top: 5,
                            right: 10,
                            bottom: 5,
                            left: -10,
                          }}
                        >
                          <CartesianGrid
                            strokeDasharray="3 3"
                            stroke="hsl(var(--border))"
                          />
                          <XAxis dataKey="className" tick={{ fontSize: 11 }} />
                          <YAxis tick={{ fontSize: 10 }} domain={[0, 100]} />
                          <Tooltip
                            contentStyle={{
                              fontSize: 11,
                              borderRadius: 8,
                              border: "1px solid hsl(var(--border))",
                            }}
                          />
                          <Legend wrapperStyle={{ fontSize: 12 }} />
                          <Bar
                            dataKey="averageScore"
                            name={t("classDetail.gradeAnalysisAvgScore")}
                            fill="#6366f1"
                            radius={[4, 4, 0, 0]}
                          />
                          <Bar
                            dataKey="passRate"
                            name={t("classDetail.gradeAnalysisPassRate")}
                            fill="#10b981"
                            radius={[4, 4, 0, 0]}
                          />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                    <div className="mt-4 overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b border-border/40 text-muted-foreground">
                            <th className="text-left py-1.5 font-medium">
                              {t("classDetail.gradeAnalysisClassName")}
                            </th>
                            <th className="text-center py-1.5 font-medium">
                              {t("classDetail.gradeAnalysisAvgScore")}
                            </th>
                            <th className="text-center py-1.5 font-medium">
                              {t("classDetail.gradeAnalysisPassRate")}
                            </th>
                            <th className="text-center py-1.5 font-medium">
                              {t("classDetail.gradeAnalysisExcellentRate")}
                            </th>
                            <th className="text-center py-1.5 font-medium">
                              {t("classDetail.gradeAnalysisHighestScore")}
                            </th>
                            <th className="text-center py-1.5 font-medium">
                              {t("classDetail.gradeAnalysisTrendDelta")}
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {classRows.map((c) => (
                            <tr
                              key={c.classId}
                              className="border-b border-border/20"
                            >
                              <td className="py-1.5 text-foreground font-medium">
                                {c.className}
                              </td>
                              <td className="text-center text-foreground">
                                {formatNumber(c.averageScore)}
                              </td>
                              <td className="text-center text-muted-foreground">
                                {formatNumber(c.passRate)}%
                              </td>
                              <td className="text-center text-muted-foreground">
                                {formatNumber(c.excellentRate)}%
                              </td>
                              <td className="text-center text-muted-foreground">
                                {formatNumber(c.highestScore, 0)}
                              </td>
                              <td className="text-center">
                                {c.trendDelta > 0 ? (
                                  <span className="text-emerald-600 font-medium">
                                    ↑{c.trendDelta.toFixed(1)}
                                  </span>
                                ) : c.trendDelta < 0 ? (
                                  <span className="text-destructive font-medium">
                                    ↓{Math.abs(c.trendDelta).toFixed(1)}
                                  </span>
                                ) : (
                                  <span className="text-muted-foreground">
                                    0
                                  </span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>

            {/* 右侧：历次大考趋势 */}
            <Card className="border-border/50 shadow-sm flex flex-col">
              <CardHeader className="pb-2 border-b border-border/40 shrink-0">
                <CardTitle className="text-base flex items-center gap-2">
                  <LineChartIcon className="w-5 h-5 text-primary" />
                  {t("classDetail.gradeAnalysisTrendTitle")}
                </CardTitle>
                <CardDescription>
                  {t("classDetail.gradeAnalysisTrendDesc")}
                </CardDescription>
              </CardHeader>
              <CardContent className="flex-1 flex flex-col p-4 min-h-[300px]">
                {(trend?.examNames.length ?? 0) === 0 ||
                (trend?.perClass.length ?? 0) === 0 ? (
                  <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
                    <div className="w-16 h-16 rounded-full bg-muted/40 flex items-center justify-center mb-4 border border-dashed border-border">
                      <TrendingUp className="w-8 h-8 text-muted-foreground/30" />
                    </div>
                    <h3 className="text-sm font-semibold text-foreground mb-1">
                      {t("classDetail.gradeAnalysisTrendNotActive")}
                    </h3>
                    <p className="text-xs text-muted-foreground">
                      {t("classDetail.gradeAnalysisTrendNotActiveDesc")}
                    </p>
                  </div>
                ) : (
                  <div className="h-[280px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart
                        data={trendChartData}
                        margin={{
                          top: 5,
                          right: 10,
                          bottom: 5,
                          left: -10,
                        }}
                      >
                        <CartesianGrid
                          strokeDasharray="3 3"
                          stroke="hsl(var(--border))"
                        />
                        <XAxis dataKey="exam" tick={{ fontSize: 10 }} />
                        <YAxis
                          tick={{ fontSize: 10 }}
                          domain={["dataMin - 3", "dataMax + 3"]}
                        />
                        <Tooltip
                          contentStyle={{
                            fontSize: 11,
                            borderRadius: 8,
                            border: "1px solid hsl(var(--border))",
                          }}
                        />
                        <Legend wrapperStyle={{ fontSize: 11 }} />
                        {sortedPerClass.map((c, i) => (
                          <Line
                            key={c.className}
                            type="monotone"
                            dataKey={c.className}
                            name={c.className}
                            stroke={LINE_COLORS[i % LINE_COLORS.length]}
                            strokeWidth={2}
                            dot={{ r: 3 }}
                            activeDot={{ r: 5 }}
                            connectNulls
                          />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* 底部：年级共性薄弱点 Top5 */}
          <Card className="border-border/50 shadow-sm">
            <CardHeader className="pb-2 border-b border-border/40 shrink-0">
              <CardTitle className="text-base flex items-center gap-2">
                <Target className="w-5 h-5 text-orange-500" />
                {t("classDetail.gradeAnalysisWeakPointsTitle")}
              </CardTitle>
              <CardDescription>
                {t("classDetail.gradeAnalysisWeakPointsDesc")}
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              {weakPoints.length === 0 ? (
                <div className="flex flex-col items-center justify-center p-10 text-center">
                  <div className="w-16 h-16 rounded-xl bg-orange-500/5 flex items-center justify-center mb-3">
                    <Target className="w-8 h-8 text-orange-500/30" />
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {t("classDetail.gradeAnalysisNoClusterData")}
                  </p>
                </div>
              ) : (
                <ul className="divide-y divide-border/40">
                  {weakPoints.map((w, idx) => (
                    <li
                      key={`${w.knowledge_point}-${idx}`}
                      className="flex items-center justify-between gap-4 px-5 py-3"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <span className="w-6 h-6 shrink-0 rounded-full bg-muted/40 flex items-center justify-center text-xs font-semibold text-muted-foreground">
                          {idx + 1}
                        </span>
                        <span className="text-sm font-medium text-foreground truncate">
                          {w.knowledge_point}
                        </span>
                      </div>
                      <div className="flex items-center gap-4 shrink-0">
                        <span className="text-xs text-muted-foreground whitespace-nowrap">
                          {t("classDetail.gradeAnalysisRiskScore")}{" "}
                          {formatNumber(w.avgRisk, 0)}
                        </span>
                        <span className="text-xs text-muted-foreground whitespace-nowrap">
                          {t("classDetail.gradeAnalysisAffectedClasses")}{" "}
                          {w.affectedClasses}
                        </span>
                        <span
                          className={cn(
                            "text-[11px] px-2 py-0.5 rounded-full border",
                            severityBadgeClass(w.severity),
                          )}
                        >
                          {severityLabel(w.severity)}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
