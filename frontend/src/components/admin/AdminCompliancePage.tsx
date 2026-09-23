import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  FileJson,
  Loader2,
  RotateCcw,
  Search,
  ShieldCheck,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useLocale } from "@/contexts/LocaleContext";
import {
  buildReportCsv,
  buildReportJson,
  getAuditReport,
  listAccessLogs,
  saveBlob,
  type AccessLogItem,
  type AuditReport,
} from "@/services/complianceApi";

const PAGE_SIZE = 10;
const CURRENT_YEAR = new Date().getFullYear();
const YEAR_OPTIONS = [0, 1, 2, 3, 4].map((offset) => CURRENT_YEAR - offset);

function StatTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <p className="text-2xl font-bold text-foreground">{value}</p>
      <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
    </div>
  );
}

export function AdminCompliancePage() {
  const { t, locale } = useLocale();
  const dateLocale = locale === "en" ? "en-US" : "zh-CN";

  // 访问日志查询条件
  const [studentId, setStudentId] = useState("");
  const [action, setAction] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const [logs, setLogs] = useState<AccessLogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [logsLoading, setLogsLoading] = useState(false);

  // 年度审计报告
  const [year, setYear] = useState<string>(String(CURRENT_YEAR));
  const [report, setReport] = useState<AuditReport | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [exporting, setExporting] = useState<"csv" | "json" | null>(null);

  const runLogQuery = useCallback(
    async (query: {
      studentId: string;
      action: string;
      from: string;
      to: string;
      page: number;
    }) => {
      setLogsLoading(true);
      try {
        const data = await listAccessLogs({
          student_id: query.studentId || undefined,
          action: query.action || undefined,
          from: query.from || undefined,
          to: query.to || undefined,
          page: query.page,
          page_size: PAGE_SIZE,
        });
        setLogs(data.list ?? []);
        setTotal(data.total ?? 0);
      } catch {
        toast.error(t("admin.compliance.logs.loadFailed"));
      } finally {
        setLogsLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    void runLogQuery({ studentId: "", action: "", from: "", to: "", page: 1 });
  }, [runLogQuery]);

  const handleSearch = () => {
    setPage(1);
    void runLogQuery({ studentId, action, from, to, page: 1 });
  };

  const handleReset = () => {
    setStudentId("");
    setAction("");
    setFrom("");
    setTo("");
    setPage(1);
    void runLogQuery({ studentId: "", action: "", from: "", to: "", page: 1 });
  };

  const handlePageChange = (next: number) => {
    const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    if (next < 1 || next > pages) return;
    setPage(next);
    void runLogQuery({ studentId, action, from, to, page: next });
  };

  const fetchReport = useCallback(
    async (y: string) => {
      setReportLoading(true);
      try {
        const data = await getAuditReport({ year: Number(y) });
        setReport(data);
      } catch {
        toast.error(t("admin.compliance.report.loadFailed"));
      } finally {
        setReportLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    void fetchReport(String(CURRENT_YEAR));
  }, [fetchReport]);

  const handleYearChange = (value: string) => {
    setYear(value);
    void fetchReport(value);
  };

  const handleExportCsv = async () => {
    if (!report) return;
    setExporting("csv");
    try {
      const csv = buildReportCsv(report);
      saveBlob(
        new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }),
        `audit_report_${report.year}.csv`,
      );
      toast.success(t("admin.compliance.report.exported"));
    } catch {
      toast.error(t("admin.compliance.report.loadFailed"));
    } finally {
      setExporting(null);
    }
  };

  const handleExportJson = async () => {
    if (!report) return;
    setExporting("json");
    try {
      const json = buildReportJson(report);
      saveBlob(
        new Blob([json], { type: "application/json;charset=utf-8" }),
        `audit_report_${report.year}.json`,
      );
      toast.success(t("admin.compliance.report.exported"));
    } catch {
      toast.error(t("admin.compliance.report.loadFailed"));
    } finally {
      setExporting(null);
    }
  };

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-foreground">
          {t("admin.compliance.title")}
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          {t("admin.compliance.description")}
        </p>
      </div>

      {/* 访问日志查询 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {t("admin.compliance.logs.title")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">
                {t("admin.rights.search.label")}
              </Label>
              <Input
                className="h-9"
                value={studentId}
                onChange={(e) => setStudentId(e.target.value)}
                placeholder={t("admin.compliance.logs.studentPlaceholder")}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">
                {t("admin.compliance.logs.table.action")}
              </Label>
              <Input
                className="h-9"
                value={action}
                onChange={(e) => setAction(e.target.value)}
                placeholder={t("admin.compliance.logs.actionPlaceholder")}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">
                {t("admin.compliance.logs.from")}
              </Label>
              <Input
                className="h-9"
                type="date"
                value={from}
                onChange={(e) => setFrom(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">
                {t("admin.compliance.logs.to")}
              </Label>
              <Input
                className="h-9"
                type="date"
                value={to}
                onChange={(e) => setTo(e.target.value)}
              />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" onClick={handleSearch} disabled={logsLoading}>
              {logsLoading ? (
                <Loader2 className="w-4 h-4 mr-1 animate-spin" />
              ) : (
                <Search className="w-4 h-4 mr-1" />
              )}
              {t("admin.compliance.logs.search")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={handleReset}
              disabled={logsLoading}
            >
              <RotateCcw className="w-4 h-4 mr-1" />
              {t("admin.compliance.logs.reset")}
            </Button>
          </div>

          <div className="rounded-lg border border-border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>
                    {t("admin.compliance.logs.table.createdAt")}
                  </TableHead>
                  <TableHead>
                    {t("admin.compliance.logs.table.userId")}
                  </TableHead>
                  <TableHead>
                    {t("admin.compliance.logs.table.userRole")}
                  </TableHead>
                  <TableHead>
                    {t("admin.compliance.logs.table.action")}
                  </TableHead>
                  <TableHead>
                    {t("admin.compliance.logs.table.targetType")}
                  </TableHead>
                  <TableHead>
                    {t("admin.compliance.logs.table.targetId")}
                  </TableHead>
                  <TableHead>
                    {t("admin.compliance.logs.table.detail")}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {logs.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={7}
                      className="h-24 text-center text-muted-foreground"
                    >
                      {t("admin.compliance.logs.empty")}
                    </TableCell>
                  </TableRow>
                ) : (
                  logs.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                        {item.created_at
                          ? new Date(item.created_at).toLocaleString(dateLocale)
                          : "—"}
                      </TableCell>
                      <TableCell
                        className="font-mono text-xs max-w-[120px] truncate"
                        title={item.user_id}
                      >
                        {item.user_id || "—"}
                      </TableCell>
                      <TableCell className="text-xs">
                        {item.user_role || "—"}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-xs font-mono">
                          {item.action || "—"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs">
                        {item.target_type || "—"}
                      </TableCell>
                      <TableCell
                        className="font-mono text-xs max-w-[120px] truncate"
                        title={item.target_id}
                      >
                        {item.target_id || "—"}
                      </TableCell>
                      <TableCell
                        className="text-xs max-w-[220px] truncate"
                        title={item.detail}
                      >
                        {item.detail || "—"}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground">
              {t("admin.compliance.logs.pagination", {
                total,
                page,
                pages,
              })}
            </p>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={page <= 1 || logsLoading}
                onClick={() => handlePageChange(page - 1)}
              >
                <ChevronLeft className="w-4 h-4 mr-1" />
                {t("admin.compliance.logs.prev")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={page >= pages || logsLoading}
                onClick={() => handlePageChange(page + 1)}
              >
                {t("admin.compliance.logs.next")}
                <ChevronRight className="w-4 h-4 ml-1" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 年度审计报告 + 授权统计 */}
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4">
          <CardTitle className="text-base flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-primary" />
            {t("admin.compliance.report.title")}
          </CardTitle>
          <div className="flex flex-wrap items-center gap-2 shrink-0">
            <Select value={year} onValueChange={handleYearChange}>
              <SelectTrigger className="w-28 h-9">
                <SelectValue placeholder={t("admin.compliance.report.year")} />
              </SelectTrigger>
              <SelectContent>
                {YEAR_OPTIONS.map((y) => (
                  <SelectItem key={y} value={String(y)}>
                    {y}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              size="sm"
              variant="outline"
              disabled={!report || exporting !== null}
              onClick={handleExportCsv}
            >
              {exporting === "csv" ? (
                <Loader2 className="w-4 h-4 mr-1 animate-spin" />
              ) : (
                <Download className="w-4 h-4 mr-1" />
              )}
              {t("admin.compliance.report.exportCsv")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!report || exporting !== null}
              onClick={handleExportJson}
            >
              {exporting === "json" ? (
                <Loader2 className="w-4 h-4 mr-1 animate-spin" />
              ) : (
                <FileJson className="w-4 h-4 mr-1" />
              )}
              {t("admin.compliance.report.exportJson")}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {reportLoading ? (
            <div className="flex items-center justify-center h-24">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          ) : report ? (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <StatTile
                  label={t("admin.compliance.report.totalAccess")}
                  value={report.total_access}
                />
                <StatTile
                  label={t("admin.compliance.report.exportCount")}
                  value={report.export_count}
                />
                <StatTile
                  label={t("admin.compliance.report.deleteCount")}
                  value={report.delete_count}
                />
              </div>

              <div>
                <p className="text-sm font-medium text-foreground mb-2">
                  {t("admin.compliance.report.consent.title")}
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <StatTile
                    label={t("admin.compliance.consent.granted")}
                    value={report.consent_stats.granted}
                  />
                  <StatTile
                    label={t("admin.compliance.consent.withdrawn")}
                    value={report.consent_stats.withdrawn}
                  />
                  <StatTile
                    label={t("admin.compliance.consent.notRequired")}
                    value={report.consent_stats.not_required}
                  />
                </div>
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <div>
                  <p className="text-sm font-medium text-foreground mb-2">
                    {t("admin.compliance.report.actions.title")}
                  </p>
                  <div className="rounded-lg border border-border p-3 space-y-1.5">
                    {Object.keys(report.action_stats ?? {}).length === 0 ? (
                      <p className="text-xs text-muted-foreground">—</p>
                    ) : (
                      Object.entries(report.action_stats).map(([k, v]) => (
                        <div
                          key={k}
                          className="flex items-center justify-between text-sm"
                        >
                          <span className="font-mono text-xs text-muted-foreground">
                            {k}
                          </span>
                          <Badge variant="secondary" className="text-xs">
                            {v}
                          </Badge>
                        </div>
                      ))
                    )}
                  </div>
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground mb-2">
                    {t("admin.compliance.report.top.title")}
                  </p>
                  <div className="rounded-lg border border-border overflow-hidden">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>
                            {t("admin.compliance.report.top.table.student")}
                          </TableHead>
                          <TableHead>
                            {t("admin.compliance.report.top.table.target")}
                          </TableHead>
                          <TableHead>
                            {t("admin.compliance.report.top.table.count")}
                          </TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {(report.top_accessed ?? []).length === 0 ? (
                          <TableRow>
                            <TableCell
                              colSpan={3}
                              className="h-14 text-center text-muted-foreground text-xs"
                            >
                              —
                            </TableCell>
                          </TableRow>
                        ) : (
                          report.top_accessed.map((item, idx) => (
                            <TableRow key={`${item.student_id}-${idx}`}>
                              <TableCell className="font-mono text-xs">
                                {item.student_id}
                              </TableCell>
                              <TableCell className="text-xs">
                                {item.target_name}
                              </TableCell>
                              <TableCell className="text-xs">
                                {item.count}
                              </TableCell>
                            </TableRow>
                          ))
                        )}
                      </TableBody>
                    </Table>
                  </div>
                </div>
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground py-4 text-center">
              {t("admin.compliance.report.loadFailed")}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
