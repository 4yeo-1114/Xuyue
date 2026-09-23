import { useMemo, useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Tags, UserSquare2, Loader2, ShieldCheck, UserX2, Undo2, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { listStudentsByClass } from "@/services/api";
import {
  listStudentResults,
  grantConsent,
  withdrawConsent,
  restoreConsent,
  type AssessmentResult,
} from "@/services/assessmentApi";
import { ConsentBadge, DimensionBars, EmptyState, NeedsClassPlaceholder } from "./shared";
import { Tags as TagsIcon } from "lucide-react";
import { ParentBindingDialog } from "./ParentBindingDialog";
import type { StudentInfo } from "@/types/api";

interface AssessmentResultsTabProps {
  selectedClass: string;
}

function formatTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

export function AssessmentResultsTab({ selectedClass }: AssessmentResultsTabProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [studentId, setStudentId] = useState("");
  const [includeWithdrawn, setIncludeWithdrawn] = useState(false);
  const [parentDialogOpen, setParentDialogOpen] = useState(false);
  const [parentStudentId, setParentStudentId] = useState("");

  const { data: students = [] } = useQuery({
    queryKey: ["students", selectedClass],
    queryFn: () => listStudentsByClass(selectedClass),
    enabled: !!selectedClass,
  });

  const sortedStudents = useMemo(() => {
    return [...students].sort((a, b) => a.name.localeCompare(b.name, "zh"));
  }, [students]);

  const activeStudentId = studentId || sortedStudents[0]?.id || "";

  const { data: results, isLoading } = useQuery({
    queryKey: ["assessment-results", activeStudentId, includeWithdrawn],
    queryFn: () => listStudentResults(activeStudentId, { include_withdrawn: includeWithdrawn }),
    enabled: !!activeStudentId,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["assessment-results", activeStudentId, includeWithdrawn] });

  const consentMutation = useMutation({
    mutationFn: ({ result, action }: { result: AssessmentResult; action: "grant" | "withdraw" | "restore" }) => {
      const fn =
        action === "grant"
          ? grantConsent
          : action === "withdraw"
            ? withdrawConsent
            : restoreConsent;
      return fn(result.student_id, result.id);
    },
    onSuccess: (_data, vars) => {
      const msg =
        vars.action === "grant"
          ? t("assessment.result.grantSuccess")
          : vars.action === "withdraw"
            ? t("assessment.result.withdrawSuccess")
            : t("assessment.result.restoreSuccess");
      toast.success(msg);
      invalidate();
    },
    onError: (err: Error) => toast.error(t("assessment.result.consentFailed"), { description: err.message }),
  });

  if (!selectedClass) {
    return <NeedsClassPlaceholder icon={Tags} />;
  }

  const rows = results?.rows ?? [];

  const openParentDialog = (sid: string) => {
    setParentStudentId(sid);
    setParentDialogOpen(true);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-2 min-w-[220px]">
          <Label>{t("assessment.result.student")}</Label>
          <Select value={activeStudentId} onValueChange={setStudentId}>
            <SelectTrigger className="w-[240px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {sortedStudents.map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  {s.name}（{s.student_number}）
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <label className="flex items-center gap-2 pb-2 text-sm cursor-pointer">
          <Checkbox checked={includeWithdrawn} onCheckedChange={(v) => setIncludeWithdrawn(!!v)} />
          {t("assessment.result.includeWithdrawn")}
        </label>
      </div>

      {!activeStudentId ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState icon={UserSquare2} title={t("assessment.result.selectStudent")} />
          </CardContent>
        </Card>
      ) : isLoading ? (
        <Card>
          <CardContent className="flex items-center justify-center py-16">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </CardContent>
        </Card>
      ) : rows.length === 0 ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState icon={Tags} title={t("assessment.result.empty")} />
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {rows.map((r) => {
            const consent = r.guardian_consent ?? { status: "not_required", version: 0 };
            return (
              <Card key={r.id}>
                <CardHeader className="pb-2">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <CardTitle className="text-sm">{r.definition_name || r.domain}</CardTitle>
                      <CardDescription className="mt-1 text-xs">
                        {t(`assessment.definition.domain.${r.domain}`)} · {formatTime(r.created_at)}
                      </CardDescription>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <ConsentBadge status={consent.status} />
                      {consent.version > 0 && (
                        <span className="text-[11px] text-muted-foreground">
                          {t("assessment.result.version", { version: consent.version })}
                        </span>
                      )}
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <p className="text-xs text-muted-foreground mb-2">
                      {t("assessment.result.labels")}{" "}
                      <span className="text-[11px] opacity-70">（{t("assessment.result.noJudge")}）</span>
                    </p>
                    {!r.tag_schema?.labels || r.tag_schema.labels.length === 0 ? (
                      <p className="text-xs text-muted-foreground">{t("assessment.empty")}</p>
                    ) : (
                      <div className="flex flex-wrap gap-1.5">
                        {r.tag_schema.labels.map((lb) => (
                          <span
                            key={lb}
                            className="inline-flex items-center rounded-full bg-secondary px-2.5 py-0.5 text-xs font-medium text-secondary-foreground"
                          >
                            {lb}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  <DimensionBars percents={r.tag_schema?.dimension_percents} />

                  <div className="flex flex-wrap items-center gap-1.5 pt-2 border-t border-border/60">
                    <div className="flex items-center gap-1.5">
                      <ShieldCheck className="w-4 h-4 text-muted-foreground" />
                      <span className="text-xs text-muted-foreground">{t("assessment.result.consent")}:</span>
                      <ConsentBadge status={consent.status} />
                    </div>
                    <div className="ml-auto flex flex-wrap gap-1.5">
                      {consent.status === "not_required" && (
                        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => consentMutation.mutate({ result: r, action: "grant" })}>
                          <ShieldCheck className="w-3.5 h-3.5 mr-1" />
                          {t("assessment.result.grant")}
                        </Button>
                      )}
                      {consent.status === "granted" && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 text-xs text-destructive hover:text-destructive"
                          onClick={() => consentMutation.mutate({ result: r, action: "withdraw" })}
                        >
                          <UserX2 className="w-3.5 h-3.5 mr-1" />
                          {t("assessment.result.withdraw")}
                        </Button>
                      )}
                      {consent.status === "withdrawn" && (
                        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => consentMutation.mutate({ result: r, action: "restore" })}>
                          <Undo2 className="w-3.5 h-3.5 mr-1" />
                          {t("assessment.result.restore")}
                        </Button>
                      )}
                      <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => openParentDialog(r.student_id)}>
                        <UserPlus className="w-3.5 h-3.5 mr-1" />
                        {t("assessment.result.bindParent")}
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <ParentBindingDialog
        open={parentDialogOpen}
        onOpenChange={setParentDialogOpen}
        students={sortedStudents as StudentInfo[]}
        studentId={parentStudentId}
      />
    </div>
  );
}
