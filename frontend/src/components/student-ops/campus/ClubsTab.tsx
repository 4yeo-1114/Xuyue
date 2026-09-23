import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus, Users, CalendarCheck, Pencil, Loader2 } from "lucide-react";
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
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
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
import { ScrollArea } from "@/components/ui/scroll-area";
import { listClassTeachers } from "@/services/api";
import {
  listClubs,
  createClub,
  updateClub,
  listClubEnrollments,
  batchClubEnrollments,
  updateClubEnrollment,
  batchClubAttendance,
  type CampusClub,
} from "@/services/studentOpsApi";
import { StudentMultiPicker } from "@/components/student-ops/shared/StudentMultiPicker";
import { StatusBadge } from "@/components/student-ops/shared/StatusBadge";
import { Pagination } from "@/components/student-ops/shared/Pagination";
import { EmptyState } from "@/components/student-ops/shared/EmptyState";
import { LoadingRow, ErrorBox } from "./campusCommon";
import { failureMsg } from "./campusUtils";

/* ═══════════ 社团 ═══════════ */
export function ClubsTab({ classId }: { classId: string }) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<CampusClub | null>(null);
  const [enroll, setEnroll] = useState<CampusClub | null>(null);
  const [attendance, setAttendance] = useState<CampusClub | null>(null);

  const query = useQuery({
    queryKey: ["so-clubs", page],
    queryFn: () => listClubs({ page, pageSize: 20 }),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["so-clubs"] });

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button
          size="sm"
          onClick={() => {
            setEditing(null);
            setFormOpen(true);
          }}
        >
          <Plus className="h-4 w-4 mr-1" /> {t("studentOps.campus.clubCreate")}
        </Button>
      </div>
      <Card>
        <CardContent className="p-0">
          {query.isLoading ? (
            <LoadingRow />
          ) : query.isError ? (
            <ErrorBox />
          ) : query.data?.items.length === 0 ? (
            <EmptyState title={t("studentOps.campus.noClubs")} />
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("studentOps.campus.clubName")}</TableHead>
                    <TableHead>{t("studentOps.campus.teacher")}</TableHead>
                    <TableHead>{t("studentOps.campus.maxMembers")}</TableHead>
                    <TableHead>{t("studentOps.badges.status")}</TableHead>
                    <TableHead className="text-right">
                      {t("studentOps.actions")}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {query.data?.items.map((c) => (
                    <TableRow key={c.id}>
                      <TableCell className="font-medium">{c.name}</TableCell>
                      <TableCell>{c.teacherName || "—"}</TableCell>
                      <TableCell>
                        {c.maxMembers === 0
                          ? t("studentOps.campus.maxMembersHint")
                          : c.maxMembers}
                      </TableCell>
                      <TableCell>
                        <StatusBadge
                          value={c.isActive ? "approved" : "cancelled"}
                          label={
                            c.isActive
                              ? t("studentOps.badges.active")
                              : t("studentOps.badges.inactive")
                          }
                        />
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            title={t("studentOps.campus.members")}
                            onClick={() => setEnroll(c)}
                          >
                            <Users className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            title={t("studentOps.campus.attendance")}
                            onClick={() => setAttendance(c)}
                            disabled={!c.isActive}
                          >
                            <CalendarCheck className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setEditing(c);
                              setFormOpen(true);
                            }}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                        </div>
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

      <ClubFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        classId={classId}
        editing={editing}
        onSaved={invalidate}
      />
      <EnrollDialog
        club={enroll}
        classId={classId}
        onClose={() => setEnroll(null)}
      />
      <AttendanceDialog club={attendance} onClose={() => setAttendance(null)} />
    </div>
  );
}

export function ClubFormDialog({
  open,
  onOpenChange,
  classId,
  editing,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  classId: string;
  editing: CampusClub | null;
  onSaved: () => void;
}) {
  const { t } = useLocale();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [teacherId, setTeacherId] = useState("");
  const [maxMembers, setMaxMembers] = useState(30);
  const [isActive, setIsActive] = useState(true);

  const teachersQuery = useQuery({
    queryKey: ["class-teachers", classId],
    queryFn: () => listClassTeachers(classId),
    enabled: !!classId && open,
  });

  useEffect(() => {
    if (open) {
      setName(editing?.name || "");
      setDescription(editing?.description || "");
      setTeacherId(editing?.teacherId || "");
      setMaxMembers(editing?.maxMembers ?? 30);
      setIsActive(editing?.isActive ?? true);
    }
  }, [open, editing]);

  const mutation = useMutation({
    mutationFn: () => {
      const body = {
        name: name.trim(),
        description: description || null,
        teacherId: teacherId || null,
        maxMembers,
        isActive,
      };
      return editing ? updateClub(editing.id, body) : createClub(body);
    },
    onSuccess: () => {
      toast.success(
        editing
          ? t("studentOps.badges.updateSuccess")
          : t("studentOps.campus.clubCreate"),
      );
      onSaved();
      onOpenChange(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const submit = () => {
    if (!name.trim()) {
      toast.error(t("studentOps.required"));
      return;
    }
    mutation.mutate();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            {editing
              ? t("studentOps.campus.clubEdit")
              : t("studentOps.campus.clubCreate")}
          </DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label>{t("studentOps.campus.clubName")} *</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("studentOps.campus.clubNamePlaceholder")}
            />
          </div>
          <div className="grid gap-2">
            <Label>{t("studentOps.campus.clubDescription")}</Label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>{t("studentOps.campus.teacher")}</Label>
              <Select value={teacherId} onValueChange={setTeacherId}>
                <SelectTrigger>
                  <SelectValue placeholder="—" />
                </SelectTrigger>
                <SelectContent>
                  {(teachersQuery.data ?? []).map((tc) => (
                    <SelectItem key={tc.user_id} value={tc.user_id}>
                      {tc.display_name || tc.email}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>{t("studentOps.campus.maxMembers")}</Label>
              <Input
                type="number"
                min={0}
                value={maxMembers}
                onChange={(e) => setMaxMembers(Number(e.target.value))}
              />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("studentOps.cancel")}
          </Button>
          <Button onClick={submit} disabled={mutation.isPending}>
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

/* ── 社团成员 / 报名 ── */
export function EnrollDialog({
  club,
  classId,
  onClose,
}: {
  club: CampusClub | null;
  classId: string;
  onClose: () => void;
}) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string[]>([]);
  const [enrolledAt, setEnrolledAt] = useState(() =>
    new Date().toISOString().slice(0, 10),
  );
  const [confirmLeave, setConfirmLeave] = useState<string | null>(null);

  const membersQuery = useQuery({
    queryKey: ["so-club-members", club?.id, page],
    queryFn: () =>
      listClubEnrollments(club!.id, { status: "enrolled", page, pageSize: 20 }),
    enabled: !!club,
  });

  useEffect(() => {
    if (club) {
      setPage(1);
      setSelected([]);
      setEnrolledAt(new Date().toISOString().slice(0, 10));
    }
  }, [club]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["so-club-members"] });
    queryClient.invalidateQueries({ queryKey: ["so-clubs"] });
  };

  const enrollMutation = useMutation({
    mutationFn: () =>
      batchClubEnrollments({
        clubId: club!.id,
        studentIds: selected,
        enrolledAt,
      }),
    onSuccess: (res) => {
      if (res.failures.length > 0) {
        toast.warning(failureMsg(res.failures));
      }
      toast.success(
        t("studentOps.campus.enrollSuccess", { count: res.successCount }),
      );
      invalidate();
      setSelected([]);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const leaveMutation = useMutation({
    mutationFn: (id: string) => updateClubEnrollment(id, { status: "left" }),
    onSuccess: () => {
      toast.success(t("studentOps.success"));
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <>
      <Dialog open={!!club} onOpenChange={(o) => !o && onClose()}>
        <DialogContent className="max-w-xl max-h-[86vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{club?.name}</DialogTitle>
            <DialogDescription>
              {t("studentOps.campus.enrollTitle")}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            {club && (
              <div className="grid gap-2">
                <Label>{t("studentOps.badges.selectStudents")}</Label>
                <StudentMultiPicker
                  classId={classId}
                  selected={selected}
                  onChange={setSelected}
                />
                <div className="flex items-end gap-2">
                  <div className="grid flex-1 gap-1">
                    <Label className="text-xs">
                      {t("studentOps.campus.enrollDate")}
                    </Label>
                    <Input
                      type="date"
                      value={enrolledAt}
                      onChange={(e) => setEnrolledAt(e.target.value)}
                      className="h-9"
                    />
                  </div>
                  <Button
                    size="sm"
                    onClick={() => enrollMutation.mutate()}
                    disabled={enrollMutation.isPending || selected.length === 0}
                  >
                    {enrollMutation.isPending && (
                      <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                    )}
                    {t("studentOps.campus.enrollMembers")}
                  </Button>
                </div>
              </div>
            )}
            <div className="space-y-2">
              <Label>
                {t("studentOps.campus.members")}（
                {membersQuery.data?.total ?? 0}）
              </Label>
              <ScrollArea className="max-h-56 rounded-md border border-border/60">
                <div className="p-2">
                  {membersQuery.isLoading ? (
                    <LoadingRow />
                  ) : membersQuery.data?.items.length === 0 ? (
                    <div className="py-6 text-center text-sm text-muted-foreground">
                      {t("studentOps.empty")}
                    </div>
                  ) : (
                    membersQuery.data?.items.map((m) => (
                      <div
                        key={m.id}
                        className="flex items-center justify-between gap-2 rounded px-2 py-1.5 hover:bg-accent/60"
                      >
                        <span className="text-sm">{m.studentName}</span>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setConfirmLeave(m.id)}
                        >
                          {t("studentOps.campus.leave")}
                        </Button>
                      </div>
                    ))
                  )}
                </div>
              </ScrollArea>
              <div className="flex justify-end">
                <Pagination
                  page={membersQuery.data?.page || 1}
                  pageSize={membersQuery.data?.pageSize || 20}
                  total={membersQuery.data?.total || 0}
                  onPageChange={setPage}
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={onClose}>
              {t("studentOps.close")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={!!confirmLeave}
        onOpenChange={(open) => !open && setConfirmLeave(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("studentOps.campus.leave")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("studentOps.campus.leaveConfirm")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("studentOps.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (!confirmLeave) return;
                const targetId = confirmLeave;
                setConfirmLeave(null);
                leaveMutation.mutate(targetId);
              }}
            >
              {t("studentOps.confirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

/* ── 社团考勤 ── */
export function AttendanceDialog({
  club,
  onClose,
}: {
  club: CampusClub | null;
  onClose: () => void;
}) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [sessionDate, setSessionDate] = useState(() =>
    new Date().toISOString().slice(0, 10),
  );
  const [statusMap, setStatusMap] = useState<Record<string, string>>({});

  const membersQuery = useQuery({
    queryKey: ["so-club-members", club?.id, 1],
    queryFn: () =>
      listClubEnrollments(club!.id, {
        status: "enrolled",
        page: 1,
        pageSize: 200,
      }),
    enabled: !!club,
  });

  useEffect(() => {
    if (club) {
      setSessionDate(new Date().toISOString().slice(0, 10));
    }
  }, [club]);

  useEffect(() => {
    if (club && membersQuery.data) {
      const m: Record<string, string> = {};
      membersQuery.data.items.forEach((e) => {
        m[e.studentId] = "present";
      });
      setStatusMap(m);
    }
  }, [club, membersQuery.data]);

  const mutation = useMutation({
    mutationFn: () =>
      batchClubAttendance({
        clubId: club!.id,
        sessionDate,
        records: Object.entries(statusMap).map(([studentId, attendStatus]) => ({
          studentId,
          attendStatus,
        })),
      }),
    onSuccess: (res) => {
      if (res.failures.length > 0) toast.warning(failureMsg(res.failures));
      toast.success(
        t("studentOps.campus.attendanceSuccess", { count: res.successCount }),
      );
      queryClient.invalidateQueries({ queryKey: ["so-club-attendance"] });
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const hasMembers = (membersQuery.data?.items.length ?? 0) > 0;

  return (
    <Dialog open={!!club} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl max-h-[86vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {t("studentOps.campus.attendance")} · {club?.name}
          </DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid w-48 gap-1">
            <Label className="text-xs">
              {t("studentOps.campus.sessionDate")}
            </Label>
            <Input
              type="date"
              value={sessionDate}
              onChange={(e) => setSessionDate(e.target.value)}
            />
          </div>
          {membersQuery.isLoading ? (
            <LoadingRow />
          ) : !hasMembers ? (
            <EmptyState title={t("studentOps.campus.attendanceEmpty")} />
          ) : (
            <>
              <ScrollArea className="max-h-64 rounded-md border border-border/60">
                <div className="p-2 space-y-1">
                  {membersQuery.data?.items.map((m) => (
                    <div
                      key={m.id}
                      className="flex items-center justify-between gap-2 rounded px-2 py-1.5 hover:bg-accent/60"
                    >
                      <span className="text-sm">{m.studentName}</span>
                      <Select
                        value={statusMap[m.studentId] || "present"}
                        onValueChange={(v) =>
                          setStatusMap((prev) => ({
                            ...prev,
                            [m.studentId]: v,
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
                          <SelectItem value="absent">
                            {t("studentOps.campus.statusAbsent")}
                          </SelectItem>
                          <SelectItem value="leave">
                            {t("studentOps.campus.statusLeave")}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  ))}
                </div>
              </ScrollArea>
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
                  {t("studentOps.save")}
                </Button>
              </DialogFooter>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
