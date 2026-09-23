import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus, Loader2 } from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { ScrollArea } from "@/components/ui/scroll-area";
import { listStudentsByClass } from "@/services/api";
import { batchAttendance, listAttendance } from "@/services/studentOpsApi";
import { StatusBadge } from "@/components/student-ops/shared/StatusBadge";
import { Pagination } from "@/components/student-ops/shared/Pagination";
import { EmptyState } from "@/components/student-ops/shared/EmptyState";
import { LoadingRow, ErrorBox } from "./campusCommon";
import { cap, failureMsg } from "./campusUtils";

/* ── 请假管理 / 出勤统计 ── */

const ATT_STATUS_LABEL_KEYS: Record<string, string> = {
  present: "studentOps.campus.statusPresent",
  leave: "studentOps.campus.statusLeave",
  late: "studentOps.campus.statusLate",
  absent: "studentOps.campus.statusAbsent",
};

/* ── 请假管理 Tab ── */
export function LeaveManageTab({ classId }: { classId: string }) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [checkType, setCheckType] = useState("");
  const [checkDate, setCheckDate] = useState("");
  const [createOpen, setCreateOpen] = useState(false);

  const query = useQuery({
    queryKey: ["so-attendance", classId, status, checkType, checkDate, page],
    queryFn: () =>
      listAttendance({
        classId: classId || undefined,
        status: status || undefined,
        checkType: checkType || undefined,
        date: checkDate || undefined,
        page,
        pageSize: 20,
      }),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["so-attendance"] });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Select
            value={status}
            onValueChange={(v) => {
              setStatus(v);
              setPage(1);
            }}
          >
            <SelectTrigger className="w-[120px]">
              <SelectValue placeholder={t("studentOps.campus.statusPresent")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all">{t("studentOps.all")}</SelectItem>
              <SelectItem value="present">
                {t("studentOps.campus.statusPresent")}
              </SelectItem>
              <SelectItem value="leave">
                {t("studentOps.campus.statusLeave")}
              </SelectItem>
              <SelectItem value="late">
                {t("studentOps.campus.statusLate")}
              </SelectItem>
              <SelectItem value="absent">
                {t("studentOps.campus.statusAbsent")}
              </SelectItem>
            </SelectContent>
          </Select>
          <Select
            value={checkType}
            onValueChange={(v) => {
              setCheckType(v);
              setPage(1);
            }}
          >
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
          <Input
            type="date"
            className="w-[150px]"
            value={checkDate}
            onChange={(e) => {
              setCheckDate(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <Button
          size="sm"
          onClick={() => setCreateOpen(true)}
          disabled={!classId}
        >
          <Plus className="h-4 w-4 mr-1" /> {t("studentOps.campus.leaveCreate")}
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          {query.isLoading ? (
            <LoadingRow />
          ) : query.isError ? (
            <ErrorBox />
          ) : query.data?.items.length === 0 ? (
            <EmptyState title={t("studentOps.campus.noAttendance")} />
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("studentOps.practice.student")}</TableHead>
                    <TableHead>
                      {t("studentOps.campus.attendanceDate")}
                    </TableHead>
                    <TableHead>
                      {t("studentOps.campus.attendanceCheckType")}
                    </TableHead>
                    <TableHead>{t("studentOps.badges.status")}</TableHead>
                    <TableHead>
                      {t("studentOps.campus.attendanceReason")}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {query.data?.items.map((a) => (
                    <TableRow key={a.id}>
                      <TableCell className="font-medium">
                        {a.studentName}
                      </TableCell>
                      <TableCell>{a.date}</TableCell>
                      <TableCell>
                        {t(`studentOps.campus.checkType${cap(a.checkType)}`)}
                      </TableCell>
                      <TableCell>
                        <StatusBadge
                          value={a.status}
                          label={t(
                            ATT_STATUS_LABEL_KEYS[a.status] ||
                              "studentOps.campus.statusPresent",
                          )}
                        />
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate text-muted-foreground">
                        {a.reason || "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <div className="p-3">
                <Pagination
                  page={query.data?.page || 1}
                  pageSize={query.data?.pageSize || 20}
                  total={query.data?.total || 0}
                  onPageChange={setPage}
                />
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <LeaveFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        classId={classId}
        onSaved={invalidate}
      />
    </div>
  );
}

export function LeaveFormDialog({
  open,
  onOpenChange,
  classId,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  classId: string;
  onSaved: () => void;
}) {
  const { t } = useLocale();
  const [checkType, setCheckType] = useState("morning");
  const [checkDate, setCheckDate] = useState(() =>
    new Date().toISOString().slice(0, 10),
  );
  const [rows, setRows] = useState<
    Record<string, { status: string; reason: string }>
  >({});

  const studentsQuery = useQuery({
    queryKey: ["students", classId],
    queryFn: () => listStudentsByClass(classId),
    enabled: !!classId && open,
  });

  useEffect(() => {
    if (open) {
      setCheckType("morning");
      setCheckDate(new Date().toISOString().slice(0, 10));
      setRows({});
    }
  }, [open]);

  useEffect(() => {
    if (open && studentsQuery.data) {
      const m: Record<string, { status: string; reason: string }> = {};
      studentsQuery.data.forEach((s) => {
        m[s.id] = { status: "present", reason: "" };
      });
      setRows(m);
    }
  }, [open, studentsQuery.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const mutation = useMutation({
    mutationFn: () =>
      batchAttendance({
        classId,
        checkType,
        date: checkDate,
        records: Object.entries(rows).map(([studentId, r]) => ({
          studentId,
          status: r.status,
          reason: r.reason || null,
        })),
      }),
    onSuccess: (res) => {
      if (res.failures.length > 0) toast.warning(failureMsg(res.failures));
      toast.success(
        t("studentOps.campus.attendanceSuccess", { count: res.successCount }),
      );
      onSaved();
      onOpenChange(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const students = studentsQuery.data ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl max-h-[86vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("studentOps.campus.leaveCreate")}</DialogTitle>
          <DialogDescription>
            {t("studentOps.campus.attendanceFormDesc")}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <Select value={checkType} onValueChange={setCheckType}>
              <SelectTrigger className="w-[130px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="morning">
                  {t("studentOps.campus.checkTypeMorning")}
                </SelectItem>
                <SelectItem value="afternoon">
                  {t("studentOps.campus.checkTypeAfternoon")}
                </SelectItem>
              </SelectContent>
            </Select>
            <Input
              type="date"
              className="w-[150px]"
              value={checkDate}
              onChange={(e) => setCheckDate(e.target.value)}
            />
          </div>
          {studentsQuery.isLoading ? (
            <LoadingRow />
          ) : (
            <ScrollArea className="max-h-72 rounded-md border border-border/60">
              <div className="p-2 space-y-2">
                {students.map((s) => {
                  const row = rows[s.id] || { status: "present", reason: "" };
                  return (
                    <div
                      key={s.id}
                      className="flex flex-wrap items-center gap-2 rounded border border-border/60 px-2 py-2"
                    >
                      <span className="w-24 truncate text-sm font-medium">
                        {s.name}
                      </span>
                      <Select
                        value={row.status}
                        onValueChange={(v) =>
                          setRows((prev) => ({
                            ...prev,
                            [s.id]: { ...row, status: v },
                          }))
                        }
                      >
                        <SelectTrigger className="h-8 w-24">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="present">
                            {t("studentOps.campus.statusPresent")}
                          </SelectItem>
                          <SelectItem value="leave">
                            {t("studentOps.campus.statusLeave")}
                          </SelectItem>
                          <SelectItem value="late">
                            {t("studentOps.campus.statusLate")}
                          </SelectItem>
                          <SelectItem value="absent">
                            {t("studentOps.campus.statusAbsent")}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                      <Input
                        className="h-8 min-w-32 flex-1"
                        placeholder={t("studentOps.campus.attendanceReason")}
                        value={row.reason}
                        onChange={(e) =>
                          setRows((prev) => ({
                            ...prev,
                            [s.id]: { ...row, reason: e.target.value },
                          }))
                        }
                      />
                    </div>
                  );
                })}
              </div>
            </ScrollArea>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("studentOps.cancel")}
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || students.length === 0}
          >
            {mutation.isPending && (
              <Loader2 className="h-4 w-4 mr-1 animate-spin" />
            )}
            {t("studentOps.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
