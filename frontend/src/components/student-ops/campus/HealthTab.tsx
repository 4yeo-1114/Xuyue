import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus, Loader2, HeartPulse, AlertTriangle, ClipboardCheck } from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";
import { useAuth } from "@/hooks/useAuth";
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
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { listStudentsByClass } from "@/services/api";
import {
  listHealthChecks,
  batchHealthChecks,
  listHealthAlerts,
  updateHealthCheck,
  type HealthAlert,
} from "@/services/studentOpsApi";
import { StatusBadge } from "@/components/student-ops/shared/StatusBadge";
import { Pagination } from "@/components/student-ops/shared/Pagination";
import { EmptyState } from "@/components/student-ops/shared/EmptyState";
import { LoadingRow, ErrorBox } from "./campusCommon";
import { cap, failureMsg } from "./campusUtils";

/* ═══════════ 晨午检 / 健康预警 ═══════════ */
export function HealthTab({ classId }: { classId: string }) {
  const { t } = useLocale();
  const [tab, setTab] = useState("checks");

  return (
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList>
        <TabsTrigger value="checks">
          {t("studentOps.campus.healthChecks")}
        </TabsTrigger>
        <TabsTrigger value="alerts">
          <HeartPulse className="h-3.5 w-3.5 mr-1" />
          {t("studentOps.campus.alerts")}
        </TabsTrigger>
      </TabsList>
      <TabsContent value="checks">
        <HealthChecksTab classId={classId} />
      </TabsContent>
      <TabsContent value="alerts">
        <HealthAlertsTab classId={classId} />
      </TabsContent>
    </Tabs>
  );
}

export function HealthChecksTab({ classId }: { classId: string }) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [checkType, setCheckType] = useState("");
  const [checkDate, setCheckDate] = useState("");
  const [createOpen, setCreateOpen] = useState(false);

  const query = useQuery({
    queryKey: ["so-health", classId, checkType, checkDate, page],
    queryFn: () =>
      listHealthChecks({
        classId: classId || undefined,
        checkType: checkType || undefined,
        checkDate: checkDate || undefined,
        page,
        pageSize: 20,
      }),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["so-health"] });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Select
            value={checkType}
            onValueChange={(v) => {
              setCheckType(v);
              setPage(1);
            }}
          >
            <SelectTrigger className="w-[120px]">
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
          <Plus className="h-4 w-4 mr-1" />{" "}
          {t("studentOps.campus.healthCreate")}
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          {query.isLoading ? (
            <LoadingRow />
          ) : query.isError ? (
            <ErrorBox />
          ) : query.data?.items.length === 0 ? (
            <EmptyState title={t("studentOps.campus.noHealth")} />
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("studentOps.practice.student")}</TableHead>
                    <TableHead>
                      {t("studentOps.campus.checkTypeMorning")}
                    </TableHead>
                    <TableHead>{t("studentOps.campus.checkDate")}</TableHead>
                    <TableHead>{t("studentOps.campus.temperature")}</TableHead>
                    <TableHead>{t("studentOps.campus.healthStatus")}</TableHead>
                    <TableHead>{t("studentOps.campus.symptoms")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {query.data?.items.map((h) => (
                    <TableRow
                      key={h.id}
                      className={h.isAlert ? "bg-red-50/40" : ""}
                    >
                      <TableCell className="font-medium">
                        {h.studentName}
                      </TableCell>
                      <TableCell>
                        {t(`studentOps.campus.checkType${cap(h.checkType)}`)}
                      </TableCell>
                      <TableCell>{h.checkDate}</TableCell>
                      <TableCell>
                        {h.temperature != null ? h.temperature : "—"}
                      </TableCell>
                      <TableCell>
                        <StatusBadge
                          value={h.healthStatus}
                          label={t(
                            `studentOps.campus.status${cap(h.healthStatus)}`,
                          )}
                        />
                      </TableCell>
                      <TableCell className="max-w-[160px] truncate">
                        {h.symptoms || "—"}
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

      <HealthCheckFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        classId={classId}
        onSaved={invalidate}
      />
    </div>
  );
}

export function HealthCheckFormDialog({
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
    Record<string, { temperature: string; status: string; symptoms: string }>
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
      const m: Record<
        string,
        { temperature: string; status: string; symptoms: string }
      > = {};
      studentsQuery.data.forEach((s) => {
        m[s.id] = { temperature: "", status: "normal", symptoms: "" };
      });
      setRows(m);
    }
  }, [open, studentsQuery.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const mutation = useMutation({
    mutationFn: () =>
      batchHealthChecks({
        classId,
        checkType,
        checkDate,
        records: Object.entries(rows).map(([studentId, r]) => ({
          studentId,
          temperature: r.temperature ? Number(r.temperature) : null,
          healthStatus: r.status,
          symptoms: r.symptoms || null,
        })),
      }),
    onSuccess: (res) => {
      if (res.failures.length > 0) toast.warning(failureMsg(res.failures));
      toast.success(
        t("studentOps.campus.healthSuccess", { count: res.successCount }),
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
          <DialogTitle>{t("studentOps.campus.healthCreate")}</DialogTitle>
          <DialogDescription>
            {t("studentOps.campus.alertDesc")}
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
                  const row = rows[s.id] || {
                    temperature: "",
                    status: "normal",
                    symptoms: "",
                  };
                  return (
                    <div
                      key={s.id}
                      className="flex flex-wrap items-center gap-2 rounded border border-border/60 px-2 py-2"
                    >
                      <span className="w-24 truncate text-sm font-medium">
                        {s.name}
                      </span>
                      <Input
                        type="number"
                        step="0.1"
                        min={34}
                        max={44}
                        className="h-8 w-24"
                        placeholder="℃"
                        value={row.temperature}
                        onChange={(e) =>
                          setRows((prev) => ({
                            ...prev,
                            [s.id]: { ...row, temperature: e.target.value },
                          }))
                        }
                      />
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
                          <SelectItem value="normal">
                            {t("studentOps.campus.statusNormal")}
                          </SelectItem>
                          <SelectItem value="abnormal">
                            {t("studentOps.campus.statusAbnormal")}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                      <Input
                        className="h-8 min-w-32 flex-1"
                        placeholder={t("studentOps.campus.symptoms")}
                        value={row.symptoms}
                        onChange={(e) =>
                          setRows((prev) => ({
                            ...prev,
                            [s.id]: { ...row, symptoms: e.target.value },
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

export function HealthAlertsTab({ classId }: { classId: string }) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [handle, setHandle] = useState<HealthAlert | null>(null);

  const query = useQuery({
    queryKey: ["so-health-alerts", classId, page],
    queryFn: () =>
      listHealthAlerts({ classId: classId || undefined, page, pageSize: 20 }),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["so-health-alerts"] });

  return (
    <div className="space-y-3">
      <Alert className="border-amber-200 bg-amber-50 text-amber-800">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle className="text-sm">
          {t("studentOps.campus.alerts")}
        </AlertTitle>
        <AlertDescription className="text-xs">
          {t("studentOps.campus.alertDesc")}
        </AlertDescription>
      </Alert>
      <Card>
        <CardContent className="p-0">
          {query.isLoading ? (
            <LoadingRow />
          ) : query.isError ? (
            <ErrorBox />
          ) : query.data?.items.length === 0 ? (
            <EmptyState title={t("studentOps.campus.noAlerts")} />
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("studentOps.practice.student")}</TableHead>
                    <TableHead>{t("studentOps.campus.checkDate")}</TableHead>
                    <TableHead>{t("studentOps.campus.temperature")}</TableHead>
                    <TableHead>
                      {t("studentOps.campus.consecutiveDays")}
                    </TableHead>
                    <TableHead>{t("studentOps.badges.status")}</TableHead>
                    <TableHead className="text-right">
                      {t("studentOps.actions")}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {query.data?.items.map((h) => (
                    <TableRow
                      key={h.id}
                      className={
                        h.consecutiveAlertDays >= 3 ? "bg-red-50/60" : ""
                      }
                    >
                      <TableCell className="font-medium">
                        {h.studentName}
                      </TableCell>
                      <TableCell>{h.checkDate}</TableCell>
                      <TableCell>{h.temperature ?? "—"}</TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            h.consecutiveAlertDays >= 3
                              ? "destructive"
                              : "outline"
                          }
                        >
                          {h.consecutiveAlertDays}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <StatusBadge
                          value={h.isHandled ? "approved" : "pending"}
                          label={
                            h.isHandled
                              ? t("studentOps.campus.isHandled")
                              : t("studentOps.campus.unhandled")
                          }
                        />
                      </TableCell>
                      <TableCell className="text-right">
                        {!h.isHandled && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setHandle(h)}
                          >
                            <ClipboardCheck className="h-4 w-4 text-blue-600" />
                          </Button>
                        )}
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

      <HandleAlertDialog
        alert={handle}
        onClose={() => setHandle(null)}
        onDone={invalidate}
      />
    </div>
  );
}

export function HandleAlertDialog({
  alert,
  onClose,
  onDone,
}: {
  alert: HealthAlert | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useLocale();
  const { user } = useAuth();
  const [notes, setNotes] = useState("");

  useEffect(() => {
    if (alert) setNotes("");
  }, [alert]);

  const mutation = useMutation({
    mutationFn: () =>
      updateHealthCheck(alert!.id, {
        isAlert: false,
        healthStatus: "normal",
        handledBy: user?.id || "",
        handleNotes: notes || null,
      }),
    onSuccess: () => {
      toast.success(t("studentOps.campus.handleSuccess"));
      onDone();
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Dialog open={!!alert} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            {t("studentOps.campus.handle")} · {alert?.studentName}
          </DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label>{t("studentOps.campus.handleNotes")}</Label>
            <Textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("studentOps.cancel")}
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            {mutation.isPending && (
              <Loader2 className="h-4 w-4 mr-1 animate-spin" />
            )}
            {t("studentOps.campus.handle")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
