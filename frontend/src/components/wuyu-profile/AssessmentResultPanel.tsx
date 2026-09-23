import { useQuery } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import { Loader2, ClipboardList, ShieldCheck } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { listStudentResults } from "@/services/assessmentApi";
import { ConsentBadge, DimensionBars, EmptyState } from "@/components/assessment/shared";
import { formatDateTime } from "./portfolioShared";

interface AssessmentResultPanelProps {
  studentId: string;
}

/**
 * 测评结果面板（B 域）— 只读档案视图。
 * 展示该学生的锚点结果卡片（题组名、维度占比、行为观察标签、监护人同意状态），
 * 不做同意授予 / 撤回等管理操作。
 */
export function AssessmentResultPanel({ studentId }: AssessmentResultPanelProps) {
  const { t } = useLocale();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["wuyu-assessment-results", studentId],
    queryFn: () => listStudentResults(studentId, { include_withdrawn: true }),
    enabled: !!studentId,
  });

  const rows = data?.rows ?? [];

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <ClipboardList className="w-4 h-4 text-primary" />
          <CardTitle className="text-sm font-semibold">{t("wuyu.tab.assessment")}</CardTitle>
        </div>
        <CardDescription>{t("wuyu.assessment.subtitle")}</CardDescription>
      </CardHeader>

      <CardContent className="space-y-3">
        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <Loader2 className="w-6 h-6 animate-spin mb-2" />
            <p className="text-sm">{t("wuyu.loading")}</p>
          </div>
        ) : isError ? (
          <div className="flex flex-col items-center justify-center py-12 border border-dashed rounded-lg text-muted-foreground">
            <p className="text-sm mb-2">{t("wuyu.loadFailed")}</p>
            <Button size="sm" variant="outline" onClick={() => refetch()}>
              {t("wuyu.retry")}
            </Button>
          </div>
        ) : rows.length === 0 ? (
          <EmptyState icon={ClipboardList} title={t("wuyu.assessment.empty")} />
        ) : (
          rows.map((r) => {
            const consent = r.guardian_consent ?? { status: "not_required" as const, version: 0 };
            return (
              <div
                key={r.id}
                className="rounded-lg border border-border/50 p-4 space-y-3"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground">
                      {r.definition_name || t(`assessment.definition.domain.${r.domain}`)}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {t(`assessment.definition.domain.${r.domain}`)} · {formatDateTime(r.created_at)}
                    </p>
                  </div>
                  <ConsentBadge status={consent.status} />
                </div>

                {r.purpose ? (
                  <p className="text-xs text-muted-foreground">
                    {t("wuyu.assessment.purpose")}：{r.purpose}
                  </p>
                ) : null}

                <div>
                  <p className="text-xs text-muted-foreground mb-1.5">
                    {t("assessment.result.labels")}{" "}
                    <span className="text-[11px] opacity-70">（{t("assessment.result.noJudge")}）</span>
                  </p>
                  {r.tag_schema?.labels?.length ? (
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
                  ) : (
                    <p className="text-xs text-muted-foreground">{t("assessment.empty")}</p>
                  )}
                </div>

                <DimensionBars percents={r.tag_schema?.dimension_percents} />

                {consent.status === "withdrawn" && (
                  <p className="text-xs text-muted-foreground flex items-center gap-1">
                    <ShieldCheck className="w-3.5 h-3.5 shrink-0" />
                    {t("wuyu.assessment.withdrawnHint")}
                  </p>
                )}
              </div>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}
