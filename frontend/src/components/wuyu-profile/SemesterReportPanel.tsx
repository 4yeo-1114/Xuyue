import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import { toast } from "sonner";
import {
  Snowflake,
  Download,
  Eye,
  Loader2,
  FileText,
  Trophy,
  TrendingUp,
  BookOpen,
  Landmark,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import {
  getReport,
  getMonthlyReport,
  freezeReport,
  downloadReportPdf,
  downloadGrowthAlbumPdf,
  saveBlob,
  type ReportResponse,
} from "@/services/wuyuApi";
import {
  DIMENSIONS,
  DIMENSION_COLORS,
  DIMENSION_LABEL_KEY,
  formatDateTime,
  TERM_PATTERN,
} from "./portfolioShared";
import { cn } from "@/lib/utils";

interface SemesterReportPanelProps {
  studentId: string;
  studentName?: string;
}

type ReportType = "monthly" | "final" | "semester";

/** 月份正则：2025-09 */
const MONTH_PATTERN = /^\d{4}-\d{2}$/;

export function SemesterReportPanel({ studentId, studentName }: SemesterReportPanelProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();

  const [reportType, setReportType] = useState<ReportType>("monthly");
  const [term, setTerm] = useState("2025-2026-1");
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const [query, setQuery] = useState<{ type: ReportType; value: string } | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [albumDownloading, setAlbumDownloading] = useState(false);

  const isMonthly = reportType === "monthly";
  const termValid = TERM_PATTERN.test(term.trim());
  const monthValid = MONTH_PATTERN.test(month.trim());
  const inputValid = isMonthly ? monthValid : termValid;
  const inputValue = isMonthly ? month.trim() : term.trim();
  const reportTitleKey =
    reportType === "monthly"
      ? "wuyu.report.monthlyTitle"
      : reportType === "final"
        ? "wuyu.report.finalTitle"
        : "wuyu.report.title";

  const { data: report, isLoading, isError, refetch } = useQuery({
    queryKey: ["wuyu-report", studentId, query?.type, query?.value],
    queryFn: () => {
      if (!query) return Promise.reject(new Error("no query"));
      return query.type === "monthly"
        ? getMonthlyReport(studentId, query.value)
        : getReport(studentId, query.value);
    },
    enabled: !!studentId && !!query,
  });

  const freezeMut = useMutation({
    mutationFn: (termStr: string) => freezeReport(studentId, termStr),
    onSuccess: (data) => {
      toast.success(t("wuyu.report.freezeSuccess", { version: data.version ?? 1 }));
      setQuery({ type: reportType, value: term.trim() });
      queryClient.invalidateQueries({ queryKey: ["wuyu-report", studentId] });
    },
    onError: (err: any) => {
      toast.error(err?.message || "冻结失败，请稍后重试");
    },
  });

  const handleLoad = () => {
    if (!inputValid) {
      toast.error(isMonthly ? t("wuyu.report.monthInvalid") : t("wuyu.report.termInvalid"));
      return;
    }
    setQuery({ type: reportType, value: inputValue });
  };

  const handleDownload = async () => {
    const target = query?.value || term.trim();
    if (!TERM_PATTERN.test(target)) {
      toast.error(t("wuyu.report.termInvalid"));
      return;
    }
    setDownloading(true);
    try {
      const { blob, filename } = await downloadReportPdf(studentId, target);
      saveBlob(blob, filename);
      toast.success(t("wuyu.report.pdfSuccess"));
    } catch (err: any) {
      toast.error(t("wuyu.report.pdfFailed"), { description: err?.message });
    } finally {
      setDownloading(false);
    }
  };

  const handleDownloadAlbum = async () => {
    const target = query?.value || term.trim();
    if (!TERM_PATTERN.test(target)) {
      toast.error(t("wuyu.report.termInvalid"));
      return;
    }
    setAlbumDownloading(true);
    try {
      const { blob, filename } = await downloadGrowthAlbumPdf(studentId, target);
      saveBlob(blob, filename);
      toast.success(t("wuyu.report.albumPdfSuccess"));
    } catch (err: any) {
      toast.error(t("wuyu.report.albumPdfFailed"), { description: err?.message });
    } finally {
      setAlbumDownloading(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* 控制区 */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-primary" />
            <CardTitle className="text-sm font-semibold">{t(reportTitleKey)}</CardTitle>
          </div>
          <CardDescription>{t("wuyu.report.subtitle")}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col gap-3">
            {/* 报告类型切换 */}
            <div className="flex items-center gap-2">
              <Label className="text-xs w-16 shrink-0">{t("wuyu.report.type.title")}</Label>
              <Tabs value={reportType} onValueChange={(v) => setReportType(v as ReportType)}>
                <TabsList className="h-9">
                  <TabsTrigger value="monthly" className="text-xs">
                    {t("wuyu.report.type.monthly")}
                  </TabsTrigger>
                  <TabsTrigger value="final" className="text-xs">
                    {t("wuyu.report.type.final")}
                  </TabsTrigger>
                  <TabsTrigger value="semester" className="text-xs">
                    {t("wuyu.report.type.semester")}
                  </TabsTrigger>
                </TabsList>
              </Tabs>
            </div>
            <div className="flex flex-col sm:flex-row gap-3 sm:items-end">
              {isMonthly ? (
                <div className="space-y-1.5 flex-1 max-w-xs">
                  <Label className="text-xs">{t("wuyu.report.month")}</Label>
                  <Input
                    className="h-9"
                    value={month}
                    onChange={(e) => setMonth(e.target.value)}
                    placeholder={t("wuyu.report.monthPlaceholder")}
                  />
                </div>
              ) : (
                <div className="space-y-1.5 flex-1 max-w-xs">
                  <Label className="text-xs">{t("wuyu.report.term")}</Label>
                  <Input
                    className="h-9"
                    value={term}
                    onChange={(e) => setTerm(e.target.value)}
                    placeholder={t("wuyu.report.termPlaceholder")}
                  />
                </div>
              )}
              <div className="flex items-center gap-2">
                <Button size="sm" variant="outline" onClick={handleLoad} disabled={!inputValid}>
                  <Eye className="w-3.5 h-3.5 mr-1" />
                  {isMonthly ? t("wuyu.report.loadMonthly") : t("wuyu.report.load")}
                </Button>
                <Button
                  size="sm"
                  onClick={() => freezeMut.mutate(term.trim())}
                  disabled={isMonthly || !termValid || freezeMut.isPending}
                >
                  {freezeMut.isPending ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />
                  ) : (
                    <Snowflake className="w-3.5 h-3.5 mr-1" />
                  )}
                  {freezeMut.isPending ? t("wuyu.report.freezing") : t("wuyu.report.freeze")}
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={handleDownload}
                  disabled={isMonthly || downloading}
                >
                  {downloading ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />
                  ) : (
                    <Download className="w-3.5 h-3.5 mr-1" />
                  )}
                  {t("wuyu.report.downloadPdf")}
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={handleDownloadAlbum}
                  disabled={albumDownloading}
                >
                  {albumDownloading ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />
                  ) : (
                    <BookOpen className="w-3.5 h-3.5 mr-1" />
                  )}
                  {albumDownloading
                    ? t("wuyu.report.albumGenerating")
                    : t("wuyu.report.downloadAlbum")}
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 报告内容 */}
      {isLoading && (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <Loader2 className="w-6 h-6 animate-spin mb-2" />
          <p className="text-sm">{t("wuyu.loading")}</p>
        </div>
      )}
      {isError && (
        <div className="flex flex-col items-center justify-center py-16 border border-dashed rounded-lg text-muted-foreground">
          <p className="text-sm mb-2">{t("wuyu.loadFailed")}</p>
          <Button size="sm" variant="outline" onClick={() => refetch()}>
            {t("wuyu.retry")}
          </Button>
        </div>
      )}
      {!isLoading && !isError && !report && (
        <div className="flex flex-col items-center justify-center py-16 border border-dashed rounded-lg text-muted-foreground">
          <FileText className="w-8 h-8 opacity-30 mb-2" />
          <p className="text-sm">
            {isMonthly ? t("wuyu.report.monthRequired") : t("wuyu.report.termRequired")}
          </p>
        </div>
      )}
      {report && <ReportBody report={report} studentName={studentName} />}
    </div>
  );
}

function ReportBody({ report, studentName }: { report: ReportResponse; studentName?: string }) {
  const { t } = useLocale();
  const hasDataDim = (dim: string) => report.data_status?.[dim] === "has_data";

  return (
    <div className="space-y-4">
      {/* 概要 */}
      <Card>
        <CardContent className="pt-5">
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <span className="text-base font-semibold text-foreground">{studentName || report.name}</span>
            <Badge variant={report.from_snapshot ? "default" : "secondary"}>
              {report.from_snapshot ? t("wuyu.report.fromSnapshot") : t("wuyu.report.live")}
            </Badge>
            {report.version != null && (
              <Badge variant="outline">
                {t("wuyu.report.version")} v{report.version}
              </Badge>
            )}
            <Badge variant="outline">{report.term}</Badge>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <MetricBox label={t("wuyu.report.totalGrowth")} value={String(report.total_growth_point)} />
            <MetricBox label={t("wuyu.report.growthCount")} value={String(report.growth_records_count)} />
            <MetricBox
              label={t("wuyu.report.growthRecords")}
              value={report.date_from ? `${report.date_from} ~ ${report.date_to}` : "—"}
            />
            <MetricBox label={t("wuyu.report.sources")} value={String(Object.keys(report.source_stats ?? {}).length)} />
          </div>
        </CardContent>
      </Card>

      {/* 各维度 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold">{t("wuyu.report.dimSection", { dim: t("wuyu.title") })}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-6 gap-3">
            {DIMENSIONS.map((dim) => {
              const meta = report.dimensions?.[dim];
              const color = DIMENSION_COLORS[dim];
              const has = hasDataDim(dim);
              return (
                <div
                  key={dim}
                  className={cn(
                    "rounded-lg border border-border/50 p-3",
                    !has && "opacity-70 bg-muted/20"
                  )}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-foreground">
                      {t(DIMENSION_LABEL_KEY[dim])}
                    </span>
                    <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
                  </div>
                  {has ? (
                    <div className="text-sm space-y-1">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground text-xs">{t("wuyu.report.autoPoints")}</span>
                        <span className="text-foreground">+{meta?.auto_points ?? 0}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground text-xs">{t("wuyu.report.growthRecords")}</span>
                        <span className="text-foreground">{meta?.growth_records ?? 0}</span>
                      </div>
                      <div className="flex justify-between border-t border-border/50 pt-1 mt-1">
                        <span className="text-xs font-medium">{t("wuyu.overview.growthPoint")}</span>
                        <span className="font-bold text-foreground">{meta?.total ?? 0}</span>
                      </div>
                    </div>
                  ) : (
                    <div className="py-2 text-xs text-muted-foreground">{t("wuyu.overview.insufficient")}</div>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* 里程碑 */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Trophy className="w-4 h-4 text-primary" />
            <CardTitle className="text-sm font-semibold">{t("wuyu.report.milestones")}</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          {(report.milestones ?? []).length === 0 ? (
            <div className="flex flex-col items-center justify-center py-6 border border-dashed rounded-lg text-muted-foreground">
              <p className="text-sm">{t("wuyu.report.noMilestones")}</p>
            </div>
          ) : (
            <div className="space-y-2">
              {(report.milestones ?? []).map((m, i) => (
                <div
                  key={`${m.event_type}-${i}`}
                  className="flex items-center gap-3 rounded-lg border border-border/50 px-3 py-2 text-sm"
                >
                  <span className="text-xs text-muted-foreground shrink-0">{formatDateTime(m.occurred_at)}</span>
                  <span className="flex-1 text-foreground">{m.name}</span>
                  <Badge variant="secondary">+{m.points ?? 0}</Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 学分银行 */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Landmark className="w-4 h-4 text-primary" />
            <CardTitle className="text-sm font-semibold">{t("wuyu.report.creditBank")}</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          {report.credit?.balance != null ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <MetricBox label={t("wuyu.report.creditBalance")} value={(report.credit.balance ?? 0).toLocaleString()} />
              <MetricBox label={t("wuyu.report.creditTotalEarned")} value={(report.credit.total_earned ?? 0).toLocaleString()} />
              <MetricBox label={t("wuyu.report.creditTotalSpent")} value={(report.credit.total_spent ?? 0).toLocaleString()} />
              <MetricBox label={t("wuyu.report.creditTermEarned")} value={report.credit.term_earned.toLocaleString()} />
              <MetricBox label={t("wuyu.report.creditTermSpent")} value={report.credit.term_spent.toLocaleString()} />
              <MetricBox label={t("wuyu.report.creditTxnCount")} value={report.credit.txn_count.toLocaleString()} />
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-6 border border-dashed rounded-lg text-muted-foreground">
              <p className="text-sm">{t("wuyu.report.creditEmpty")}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 趋势 */}
      {(report.trend ?? []).length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-primary" />
              <CardTitle className="text-sm font-semibold">{t("wuyu.report.trendTitle")}</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="h-[220px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={report.trend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="month" fontSize={11} stroke="hsl(var(--muted-foreground))" />
                  <YAxis fontSize={11} stroke="hsl(var(--muted-foreground))" allowDecimals={false} />
                  <Tooltip
                    contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid hsl(var(--border))" }}
                  />
                  <Bar dataKey="points" name={t("wuyu.overview.growthPoint")} fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function MetricBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/50 px-3 py-2.5">
      <p className="text-xs text-muted-foreground mb-1">{label}</p>
      <p className="text-sm font-semibold text-foreground truncate">{value}</p>
    </div>
  );
}
