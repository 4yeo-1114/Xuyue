import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, Rocket, CheckCircle2, Inbox } from "lucide-react";
import type { WeakPointItem } from "./compareAnalysisAdapter";

interface ChasingPlanProps {
  weakPoints: WeakPointItem[];
}

function SeverityBadge({ severity }: { severity: WeakPointItem["severity"] }) {
  const { t } = useLocale();
  const labelKey =
    severity === "high"
      ? "classDetail.compare.chasing.severity.high"
      : severity === "medium"
        ? "classDetail.compare.chasing.severity.medium"
        : "classDetail.compare.chasing.severity.low";
  const className =
    severity === "high"
      ? "border-rose-200 bg-rose-50 text-rose-700"
      : severity === "medium"
        ? "border-amber-200 bg-amber-50 text-amber-700"
        : "border-blue-200 bg-blue-50 text-blue-700";
  return (
    <Badge variant="outline" className={className}>
      {t(labelKey)}
    </Badge>
  );
}

export function ChasingPlan({ weakPoints }: ChasingPlanProps) {
  const { t } = useLocale();

  return (
    <Card data-tour="ca-chasing" className="min-w-0">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">
          {t("classDetail.compare.chasing.title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-xs">
        {weakPoints.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center text-sm text-muted-foreground">
            <Inbox className="mb-2 h-6 w-6" />
            {t("classDetail.暂无数据")}
            <span className="mt-1 text-[11px]">
              {t("classDetail.compare.chasing.noWeakPoints")}
            </span>
          </div>
        ) : (
          <>
            {/* Diagnosis */}
            <div className="rounded-lg border border-border/50 p-3 space-y-1.5">
              <p className="text-[11px] font-semibold text-foreground flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
                {t("classDetail.compare.chasing.diagnosis")}
              </p>
              <div className="space-y-1.5">
                {weakPoints.map((w, index) => (
                  <div
                    key={`${w.knowledgePoint}-${index}`}
                    className="flex items-center gap-2"
                  >
                    <SeverityBadge severity={w.severity} />
                    <span className="text-foreground font-medium">
                      {w.knowledgePoint}
                    </span>
                    <span className="text-muted-foreground ml-auto text-[10px]">
                      {t("classDetail.compare.chasing.affectedStudents", {
                        count: w.affectedStudentCount,
                      })}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Action suggestions */}
            <div className="space-y-1.5">
              <p className="text-[11px] font-semibold text-foreground flex items-center gap-1">
                <Rocket className="w-3.5 h-3.5 text-primary" />
                {t("classDetail.compare.chasing.actionSuggestions")}
              </p>
              {weakPoints.map((w, index) => (
                <div
                  key={`${w.knowledgePoint}-${index}`}
                  className="rounded-lg border border-border/40 p-2.5 space-y-1"
                >
                  <div className="flex items-center gap-2">
                    <Badge className="text-[9px] h-4 bg-primary/10 text-primary border-0">
                      {w.knowledgePoint}
                    </Badge>
                    <span className="text-foreground font-medium text-[11px]">
                      {w.teachingSuggestion ||
                        t("classDetail.compare.chasing.noTeachingSuggestion")}
                    </span>
                  </div>
                  {w.evidence ? (
                    <p className="text-[11px] text-muted-foreground pl-1">
                      {t("classDetail.compare.chasing.evidenceLabel", {
                        evidence: w.evidence,
                      })}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          </>
        )}

        {/* Process monitoring */}
        <div className="rounded-lg border border-border/50 p-3 space-y-1">
          <p className="text-[11px] font-semibold text-foreground flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
            {t("classDetail.compare.chasing.processMonitoring")}
          </p>
          <p className="text-[11px] text-muted-foreground">
            {t("classDetail.compare.chasing.monitorDesc1")}
          </p>
          <p className="text-[11px] text-muted-foreground">
            {t("classDetail.compare.chasing.monitorDesc2")}
          </p>
        </div>

        <div className="rounded-md border border-dashed border-border/60 px-3 py-2 text-[11px] text-muted-foreground">
          {t("home.chasing.pendingIntegration")}
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button size="sm" className="h-7 text-[11px] gap-1" disabled>
            <Rocket className="w-3 h-3" />
            {t("classDetail.compare.chasing.startPlan")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-[11px]"
            disabled
          >
            {t("classDetail.compare.chasing.inviteSupervisor")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-[11px]"
            disabled
          >
            {t("classDetail.compare.chasing.requestResources")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
