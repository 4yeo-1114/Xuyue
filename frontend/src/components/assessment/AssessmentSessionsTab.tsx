import { useMemo, useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Play, XCircle, Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import { listStudentsByClass } from "@/services/api";
import {
  listAssessmentSessions,
  cancelAssessmentSession,
  type AssessmentSession,
  type AssessmentSessionStatus,
} from "@/services/assessmentApi";
import {
  SessionStatusBadge,
  EmptyState,
  NeedsClassPlaceholder,
} from "./shared";
import { ClipboardList as ClipboardIcon } from "lucide-react";
import { CreateSessionDialog } from "./CreateSessionDialog";
import { AnswerSheetDialog } from "./AnswerSheetDialog";

const STATUS_OPTIONS: Array<AssessmentSessionStatus | "all"> = [
  "all",
  "pending",
  "in_progress",
  "submitted",
  "graded",
  "canceled",
];

interface AssessmentSessionsTabProps {
  selectedClass: string;
}

function formatTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

export function AssessmentSessionsTab({
  selectedClass,
}: AssessmentSessionsTabProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<
    AssessmentSessionStatus | "all"
  >("all");
  const [createOpen, setCreateOpen] = useState(false);
  const [answerSession, setAnswerSession] = useState<AssessmentSession | null>(
    null,
  );
  const [cancelTarget, setCancelTarget] = useState<AssessmentSession | null>(
    null,
  );

  const { data: students = [] } = useQuery({
    queryKey: ["students", selectedClass],
    queryFn: () => listStudentsByClass(selectedClass),
    enabled: !!selectedClass,
  });

  const studentIds = useMemo(
    () => new Set(students.map((s) => s.id)),
    [students],
  );

  const { data: allSessions, isLoading } = useQuery({
    queryKey: ["assessment-sessions", statusFilter],
    queryFn: () =>
      listAssessmentSessions(
        statusFilter === "all" ? {} : { status: statusFilter },
      ),
    enabled: !!selectedClass,
  });

  const sessions = useMemo(() => {
    const rows = allSessions?.rows ?? [];
    return rows.filter((s) => studentIds.has(s.student_id));
  }, [allSessions, studentIds]);

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["assessment-sessions"] });

  const { mutate: doCancel, isPending: canceling } = useMutation({
    mutationFn: async () => {
      if (!cancelTarget) return;
      await cancelAssessmentSession(cancelTarget.id);
    },
    onSuccess: () => {
      toast.success(t("assessment.session.cancelSuccess"));
      invalidate();
      setCancelTarget(null);
    },
    onError: (err: Error) =>
      toast.error(t("assessment.session.cancelFailed"), {
        description: err.message,
      }),
  });

  if (!selectedClass) {
    return <NeedsClassPlaceholder icon={ClipboardIcon} />;
  }

  const canAnswer = (s: AssessmentSession) =>
    s.status === "pending" || s.status === "in_progress";
  const canCancel = (s: AssessmentSession) =>
    s.status === "pending" || s.status === "in_progress";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <Select
          value={statusFilter}
          onValueChange={(v) =>
            setStatusFilter(v as AssessmentSessionStatus | "all")
          }
        >
          <SelectTrigger className="w-[160px] h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((s) => (
              <SelectItem key={s} value={s}>
                {s === "all"
                  ? t("assessment.session.filter.all")
                  : t(`assessment.session.status.${s}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="w-4 h-4 mr-1" />
          {t("assessment.session.create")}
        </Button>
      </div>

      {isLoading ? (
        <Card>
          <CardContent className="flex items-center justify-center py-16">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </CardContent>
        </Card>
      ) : sessions.length === 0 ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState
              icon={ClipboardIcon}
              title={t("assessment.session.empty")}
            />
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0 divide-y divide-border/60">
            {sessions.map((s) => (
              <div
                key={s.id}
                className="flex flex-wrap items-center gap-3 px-4 py-3"
              >
                <div className="flex-1 min-w-[180px]">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">
                      {s.student_name || "—"}
                    </span>
                    <SessionStatusBadge status={s.status} />
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {s.definition_name || "—"} ·{" "}
                    {t(`assessment.session.testMode.${s.test_mode}`)}
                  </p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    {t("assessment.session.takenAt")}: {formatTime(s.taken_at)}{" "}
                    · {t("assessment.session.submittedAt")}:{" "}
                    {formatTime(s.submitted_at)}
                  </p>
                </div>
                <div className="flex items-center gap-1.5">
                  {canAnswer(s) && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs"
                      onClick={() => setAnswerSession(s)}
                    >
                      <Play className="w-3.5 h-3.5 mr-1" />
                      {s.status === "in_progress"
                        ? t("assessment.session.answer")
                        : t("assessment.session.start")}
                    </Button>
                  )}
                  {canCancel(s) && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 text-xs text-destructive hover:text-destructive"
                      onClick={() => setCancelTarget(s)}
                    >
                      <XCircle className="w-3.5 h-3.5 mr-1" />
                      {t("assessment.session.cancel")}
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <CreateSessionDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        selectedClass={selectedClass}
        onCreated={invalidate}
      />
      <AnswerSheetDialog
        session={answerSession}
        open={!!answerSession}
        onOpenChange={(o) => !o && setAnswerSession(null)}
        onSubmitted={invalidate}
      />

      <AlertDialog
        open={!!cancelTarget}
        onOpenChange={(o) => !o && setCancelTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("assessment.session.cancel")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {cancelTarget
                ? `${t("assessment.session.cancelConfirm")}（${cancelTarget.student_name || ""}）`
                : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>
              {t("assessment.definition.form.cancel")}
            </AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-white hover:bg-destructive/90"
              disabled={canceling}
              onClick={() => doCancel()}
            >
              {canceling && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
              {t("assessment.session.cancel")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
