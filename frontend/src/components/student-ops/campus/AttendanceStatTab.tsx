import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, UserCheck } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";
import { useLocale } from "@/contexts/LocaleContext";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { attendanceStats, type AttendanceStats } from "@/services/studentOpsApi";
import { EmptyState } from "@/components/student-ops/shared/EmptyState";
import { LoadingRow, ErrorBox } from "./campusCommon";

/* ── 出勤统计 Tab ── */
export function AttendanceStatTab({ classId }: { classId: string }) {
  const { t } = useLocale();
  const [from, setFrom] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 30);
    return d.toISOString().slice(0, 10);
  });
  const [to, setTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [checkType, setCheckType] = useState("");

  const query = useQuery({
    queryKey: ["so-attendance-stats", classId, from, to, checkType],
    queryFn: () =>
      attendanceStats({
        classId,
        from: from || undefined,
        to: to || undefined,
        checkType: checkType || undefined,
      }),
    enabled: !!classId,
  });

  const data: AttendanceStats | undefined = query.data;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          type="date"
          className="w-[150px]"
          value={from}
          onChange={(e) => setFrom(e.target.value)}
        />
        <span className="text-xs text-muted-foreground">~</span>
        <Input
          type="date"
          className="w-[150px]"
          value={to}
          onChange={(e) => setTo(e.target.value)}
        />
        <Select value={checkType} onValueChange={setCheckType}>
          <SelectTrigger className="w-[110px]">
            <SelectValue
              placeholder={t("studentOps.campus.checkTypeMorning")}
            />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all">{t("studentOps.all")}</SelectItem>
            <SelectItem value="morning">
              {t("studentOps.campus.checkTypeMorning")}
            </SelectItem>
            <SelectItem value="afternoon">
              {t("studentOps.campus.checkTypeAfternoon")}
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardContent className="p-4">
          {query.isLoading ? (
            <LoadingRow />
          ) : query.isError ? (
            <ErrorBox />
          ) : !data ? (
            <EmptyState title={t("studentOps.campus.noAttendanceStats")} />
          ) : (
            <>
              <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mb-4">
                <StatCard
                  label={t("studentOps.campus.attendanceExpected")}
                  value={data.summary.expected}
                />
                <StatCard
                  label={t("studentOps.campus.attendancePresent")}
                  value={data.summary.present}
                />
                <StatCard
                  label={t("studentOps.campus.attendanceLeave")}
                  value={data.summary.leave}
                />
                <StatCard
                  label={t("studentOps.campus.attendanceLate")}
                  value={data.summary.late}
                />
                <StatCard
                  label={t("studentOps.campus.attendanceAbsent")}
                  value={data.summary.absent}
                  danger={data.summary.absent > 0}
                />
                <StatCard
                  label={t("studentOps.campus.attendanceAnomalyRate")}
                  value={
                    data.summary.expected
                      ? `${(data.summary.anomalyRate * 100).toFixed(1)}%`
                      : "0%"
                  }
                  danger={data.summary.anomalyRate > 0}
                />
              </div>

              {data.byDate.length > 0 && (
                <>
                  <h4 className="text-sm font-medium mb-2 flex items-center gap-1.5">
                    <BarChart3 className="h-4 w-4 text-primary" />
                    {t("studentOps.campus.attendanceByDate")}
                  </h4>
                  <div className="h-56 rounded-md border border-border/60 p-2 mb-4">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart
                        data={data.byDate}
                        margin={{ top: 5, right: 10, left: -15, bottom: 0 }}
                      >
                        <CartesianGrid
                          strokeDasharray="3 3"
                          stroke="hsl(var(--border))"
                        />
                        <XAxis
                          dataKey="date"
                          tick={{
                            fontSize: 10,
                            fill: "hsl(var(--muted-foreground))",
                          }}
                        />
                        <YAxis
                          allowDecimals={false}
                          tick={{
                            fontSize: 10,
                            fill: "hsl(var(--muted-foreground))",
                          }}
                        />
                        <Tooltip
                          contentStyle={{
                            background: "hsl(var(--card))",
                            border: "1px solid hsl(var(--border))",
                            borderRadius: 8,
                            fontSize: 12,
                          }}
                        />
                        <Legend
                          formatter={(value: string) =>
                            value === "present"
                              ? t("studentOps.campus.statusPresent")
                              : value === "leave"
                                ? t("studentOps.campus.statusLeave")
                                : value === "late"
                                  ? t("studentOps.campus.statusLate")
                                  : t("studentOps.campus.statusAbsent")
                          }
                        />
                        <Bar
                          dataKey="present"
                          stackId="s"
                          fill="hsl(142 76% 36%)"
                        />
                        <Bar
                          dataKey="leave"
                          stackId="s"
                          fill="hsl(217 91% 60%)"
                        />
                        <Bar
                          dataKey="late"
                          stackId="s"
                          fill="hsl(38 92% 50%)"
                        />
                        <Bar
                          dataKey="absent"
                          stackId="s"
                          fill="hsl(0 84% 60%)"
                        />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>

                  <h4 className="text-sm font-medium mb-2">
                    {t("studentOps.campus.attendanceByDate")}
                  </h4>
                  <div className="rounded-md border border-border/60 overflow-hidden mb-4">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>
                            {t("studentOps.campus.attendanceDate")}
                          </TableHead>
                          <TableHead>
                            {t("studentOps.campus.statusPresent")}
                          </TableHead>
                          <TableHead>
                            {t("studentOps.campus.statusLeave")}
                          </TableHead>
                          <TableHead>
                            {t("studentOps.campus.statusLate")}
                          </TableHead>
                          <TableHead>
                            {t("studentOps.campus.statusAbsent")}
                          </TableHead>
                          <TableHead>
                            {t("studentOps.campus.attendanceExpected")}
                          </TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {data.byDate.map((d) => (
                          <TableRow key={d.date}>
                            <TableCell className="font-medium">
                              {d.date}
                            </TableCell>
                            <TableCell>{d.present}</TableCell>
                            <TableCell>{d.leave}</TableCell>
                            <TableCell>{d.late}</TableCell>
                            <TableCell
                              className={
                                d.absent > 0
                                  ? "text-destructive font-medium"
                                  : ""
                              }
                            >
                              {d.absent}
                            </TableCell>
                            <TableCell>{d.total}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </>
              )}

              <h4 className="text-sm font-medium mb-2 flex items-center gap-1.5">
                <UserCheck className="h-4 w-4 text-primary" />
                {t("studentOps.campus.attendanceByStudent")}
              </h4>
              <div className="rounded-md border border-border/60 overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("studentOps.practice.student")}</TableHead>
                      <TableHead>
                        {t("studentOps.campus.statusPresent")}
                      </TableHead>
                      <TableHead>
                        {t("studentOps.campus.statusLeave")}
                      </TableHead>
                      <TableHead>{t("studentOps.campus.statusLate")}</TableHead>
                      <TableHead>
                        {t("studentOps.campus.statusAbsent")}
                      </TableHead>
                      <TableHead>
                        {t("studentOps.campus.attendanceExpected")}
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.byStudent.map((s) => (
                      <TableRow key={s.studentId}>
                        <TableCell className="font-medium">
                          {s.studentName}
                        </TableCell>
                        <TableCell>{s.present}</TableCell>
                        <TableCell>{s.leave}</TableCell>
                        <TableCell>{s.late}</TableCell>
                        <TableCell
                          className={
                            s.absent > 0 ? "text-destructive font-medium" : ""
                          }
                        >
                          {s.absent}
                        </TableCell>
                        <TableCell>{s.total}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export function StatCard({
  label,
  value,
  danger,
}: {
  label: string;
  value: string | number;
  danger?: boolean;
}) {
  return (
    <div className="rounded-lg border border-border/60 p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div
        className={`mt-1 text-xl font-semibold ${danger ? "text-destructive" : ""}`}
      >
        {value}
      </div>
    </div>
  );
}
