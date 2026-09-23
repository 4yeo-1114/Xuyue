import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { AlertTriangle, Send, Save, Share2, Phone, Mail, Calendar } from "lucide-react";
import type { PlanPreviewData } from "./targetedData";

interface PlanPreviewProps {
  preview: PlanPreviewData | null;
  studentName?: string;
}

export function PlanPreview({ preview, studentName }: PlanPreviewProps) {
  const { t, locale } = useLocale();

  if (!preview) {
    return (
      <Card className="flex-1 min-w-[320px]">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold">{t("classDetail.方案预览与确认")}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">{t("classDetail.previewAfterGenerate")}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="flex-1 min-w-[320px]" data-tour="ti-preview">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">{t("classDetail.planPreviewTitle", { name: studentName })}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-xs">
        {/* Content checklist */}
        <div className="rounded-lg border border-border/50 p-3 space-y-1.5">
          <p className="font-semibold text-foreground">{t("classDetail.pushContentChecklist")}</p>
          {preview.weeks.map((w, i) => (
            <p key={i} className="text-[11px] text-muted-foreground">
              {t("classDetail.weekContentLine", { week: w.week, videos: w.videos, exercises: w.exercises, templates: w.templates })}
              {w.faceBatch ? t("classDetail.faceBatchCount", { count: w.faceBatch }) : ""}
            </p>
          ))}
        </div>

        {/* Time estimate */}
        <div className="rounded-lg border border-border/50 p-3 space-y-1 text-[11px]">
          <p>{t("classDetail.estimatedTotalTimeLabel")}<strong className="text-foreground">{t("classDetail.timeRangeValue", { daily: preview.dailyTime, weekend: preview.weekendTime })}</strong></p>
          <p>{t("classDetail.estimatedCompletionLabel")}<strong className="text-foreground">{preview.completionDate}</strong></p>
        </div>

        {/* Conflict detection */}
        {preview.conflict && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 space-y-1.5">
            <p className="font-semibold text-amber-700 flex items-center gap-1.5 text-[11px]">
              <AlertTriangle className="w-3.5 h-3.5" />{t("classDetail.conflictDetection")}
            </p>
            <p className="text-[11px] text-amber-600">⚠️ {preview.conflict}</p>
            <div className="flex gap-1.5">
              <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px]"><Calendar className="w-3 h-3 mr-0.5" />{t("classDetail.adjustTime")}</Button>
              <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px]">{t("classDetail.skipConflictDay")}</Button>
            </div>
          </div>
        )}

        {/* Parent communication */}
        <div className="rounded-lg border border-border/50 p-3 space-y-1.5">
          <p className="font-semibold text-foreground text-[11px]">{t("classDetail.parentCommunication")}</p>
          <div className="flex gap-1.5">
            <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px]"><Mail className="w-3 h-3 mr-0.5" />{t("classDetail.generateNotice")}</Button>
            <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px]"><Calendar className="w-3 h-3 mr-0.5" />{t("classDetail.scheduleHomeVisit")}</Button>
            <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px]"><Phone className="w-3 h-3 mr-0.5" />{t("classDetail.phoneCommunication")}</Button>
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-1.5 pt-1">
          <Button size="sm" className="h-7 text-[11px]"><Send className="w-3 h-3 mr-1" />{t("classDetail.confirmAndPush")}</Button>
          <Button variant="outline" size="sm" className="h-7 text-[11px]"><Save className="w-3 h-3 mr-1" />{t("classDetail.saveDraft")}</Button>
          <Button variant="ghost" size="sm" className="h-7 text-[11px]"><Share2 className="w-3 h-3 mr-1" />{t("classDetail.shareToTeachingGroup")}</Button>
        </div>
      </CardContent>
    </Card>
  );
}
