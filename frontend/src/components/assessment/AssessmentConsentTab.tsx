import { useMemo, useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ShieldCheck, Loader2, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { listStudentsByClass } from "@/services/api";
import {
  listClassConsents,
  grantConsent,
  withdrawConsent,
  restoreConsent,
  type ConsentOverviewRecord,
} from "@/services/assessmentApi";
import { ConsentBadge, EmptyState, NeedsClassPlaceholder } from "./shared";
import { ParentBindingDialog } from "./ParentBindingDialog";
import type { StudentInfo } from "@/types/api";

interface AssessmentConsentTabProps {
  selectedClass: string;
}

export function AssessmentConsentTab({
  selectedClass,
}: AssessmentConsentTabProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [bindingFor, setBindingFor] = useState<StudentInfo | null>(null);
  const [parentDialogOpen, setParentDialogOpen] = useState(false);

  // 保留现有 listStudentsByClass 查询，供 ParentBindingDialog 的学生下拉复用
  const { data: students = [] } = useQuery({
    queryKey: ["students", selectedClass],
    queryFn: () => listStudentsByClass(selectedClass),
    enabled: !!selectedClass,
  });

  const sortedStudents = useMemo(() => {
    return [...students].sort((a, b) => a.name.localeCompare(b.name, "zh"));
  }, [students]);

  // 班级同意状态总览：单个批量接口，替代原先逐学生 N+1 查询
  const { data: consentRows = [], isLoading } = useQuery({
    queryKey: ["assessment-consent-overview", selectedClass],
    queryFn: async () => {
      const data = await listClassConsents(selectedClass);
      return data.rows ?? [];
    },
    enabled: !!selectedClass,
  });

  const invalidateOverview = () =>
    queryClient.invalidateQueries({
      queryKey: ["assessment-consent-overview", selectedClass],
    });

  const consentMutation = useMutation({
    mutationFn: ({
      result,
      action,
    }: {
      result: ConsentOverviewRecord;
      action: "grant" | "withdraw" | "restore";
    }) => {
      const fn =
        action === "grant"
          ? grantConsent
          : action === "withdraw"
            ? withdrawConsent
            : restoreConsent;
      // 批量接口字段：student_id / result_id（最新 result 的 id），has_result=false 时不渲染操作按钮
      return fn(result.student_id, result.result_id ?? "");
    },
    onSuccess: (_data, vars) => {
      const msg =
        vars.action === "grant"
          ? t("assessment.result.grantSuccess")
          : vars.action === "withdraw"
            ? t("assessment.result.withdrawSuccess")
            : t("assessment.result.restoreSuccess");
      toast.success(msg);
      invalidateOverview();
    },
    onError: (err: Error) =>
      toast.error(t("assessment.result.consentFailed"), {
        description: err.message,
      }),
  });

  if (!selectedClass) {
    return <NeedsClassPlaceholder icon={ShieldCheck} />;
  }

  const openBind = (studentId: string) => {
    const student = sortedStudents.find((s) => s.id === studentId);
    if (!student) return;
    setBindingFor(student);
    setParentDialogOpen(true);
  };

  const rows = consentRows;

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        {t("assessment.consent.overview")}
      </p>

      {isLoading ? (
        <Card>
          <CardContent className="flex items-center justify-center py-16">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </CardContent>
        </Card>
      ) : rows.length === 0 ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState
              icon={ShieldCheck}
              title={t("assessment.result.empty")}
            />
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {rows.map((record) => {
            // 仅当存在结果时展示/操作同意状态；无结果只显示暂无结果
            const latest = record.has_result ? record : null;
            return (
              <Card key={record.student_id}>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <CardTitle className="text-sm truncate">
                        {record.student_name}
                      </CardTitle>
                      <CardDescription className="mt-0.5 text-xs">
                        {record.student_number || "—"}
                      </CardDescription>
                    </div>
                    <ConsentBadge status={record.consent_status} />
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-xs text-muted-foreground mb-2">
                    {t("assessment.consent.latestResult")}：
                    {latest
                      ? `${record.definition_name || record.domain} · ${t("assessment.result.version", { version: record.version })}`
                      : t("assessment.consent.noResult")}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {latest && record.consent_status === "not_required" && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 text-xs"
                        onClick={() =>
                          consentMutation.mutate({
                            result: record,
                            action: "grant",
                          })
                        }
                      >
                        <ShieldCheck className="w-3.5 h-3.5 mr-1" />
                        {t("assessment.result.grant")}
                      </Button>
                    )}
                    {latest && record.consent_status === "granted" && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 text-xs text-destructive hover:text-destructive"
                        onClick={() =>
                          consentMutation.mutate({
                            result: record,
                            action: "withdraw",
                          })
                        }
                      >
                        {t("assessment.result.withdraw")}
                      </Button>
                    )}
                    {latest && record.consent_status === "withdrawn" && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 text-xs"
                        onClick={() =>
                          consentMutation.mutate({
                            result: record,
                            action: "restore",
                          })
                        }
                      >
                        {t("assessment.result.restore")}
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 text-xs"
                      onClick={() => openBind(record.student_id)}
                    >
                      <UserPlus className="w-3.5 h-3.5 mr-1" />
                      {t("assessment.parent.bind")}
                    </Button>
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
        studentId={bindingFor?.id}
      />
    </div>
  );
}
