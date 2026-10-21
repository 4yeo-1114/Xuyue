import { useState } from "react";
import { toast } from "sonner";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Bell, Send, Save, Clock } from "lucide-react";
import type { LayeredPushSettings } from "@/services/api";

interface PushSettingsProps {
  settings: LayeredPushSettings;
  /** 本班人数（确认推送文案用） */
  studentCount: number;
  /** 局部更新设置（页面负责防抖保存） */
  onPatch: (updater: (prev: LayeredPushSettings) => LayeredPushSettings) => void;
  /** 测试推送（给当前老师本人发配置摘要） */
  onTestPush: () => void;
  /** 打开「确认推送」对话框 */
  onOpenConfirm: () => void;
}

function fmtDateTime(v?: string | null): string {
  if (!v) return "";
  return v.replace("T", " ").slice(0, 16);
}

export function PushSettings({
  settings,
  studentCount,
  onPatch,
  onTestPush,
  onOpenConfirm,
}: PushSettingsProps) {
  const { t } = useLocale();
  const [templateOpen, setTemplateOpen] = useState(false);

  const timing = settings.timing;
  const notify = settings.notify;

  const setMode = (mode: "now" | "scheduled") =>
    onPatch((prev) => ({
      ...prev,
      timing: { ...prev.timing, mode },
    }));

  const setScheduledAt = (v: string) =>
    onPatch((prev) => ({
      ...prev,
      // 改时间 = 重新武装定时（清掉已触发标记）
      timing: { ...prev.timing, scheduled_at: v || null, fired_at: null },
    }));

  const toggleNotify = (key: keyof LayeredPushSettings["notify"]) =>
    onPatch((prev) => ({
      ...prev,
      notify: { ...prev.notify, [key]: !prev.notify[key] },
    }));

  const saveTemplate = () => {
    const now = new Date();
    const name = `${now.getMonth() + 1}/${now.getDate()} ${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
    const { templates: _prevTemplates, ...snapshot } = settings;
    onPatch((prev) => ({
      ...prev,
      templates: [
        { name, saved_at: now.toISOString(), snapshot: snapshot as unknown as Record<string, unknown> },
        ...prev.templates,
      ].slice(0, 20),
    }));
    toast.success(t("layeredPush.toast.templateSaved", { name }));
  };

  const loadTemplate = (snapshot: Record<string, unknown>) => {
    onPatch((prev) => ({
      ...prev,
      ...(snapshot as unknown as Partial<LayeredPushSettings>),
      templates: prev.templates,
    }));
    setTemplateOpen(false);
    toast.success(t("layeredPush.toast.templateLoaded"));
  };

  return (
    <div
      className="flex-1 min-w-[320px] rounded-xl border border-border/50 bg-card p-5"
      data-tour="lp-push-settings"
    >
      <h3 className="text-sm font-bold text-foreground flex items-center gap-2 mb-4">
        <Bell className="w-4 h-4 text-primary" />{" "}
        {t("layeredPush.pushSettingsTitle")}
      </h3>

      {/* Push timing */}
      <div className="mb-4">
        <span className="text-xs font-medium text-foreground block mb-2">
          {t("layeredPush.pushTiming")}
        </span>
        <div className="space-y-1.5">
          <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
            <input
              type="radio"
              name="timing"
              className="accent-primary w-3 h-3"
              checked={timing.mode === "now"}
              onChange={() => setMode("now")}
            />{" "}
            {t("layeredPush.pushImmediately")}
          </label>
          <label className="flex items-center gap-2 text-xs text-foreground font-medium cursor-pointer">
            <input
              type="radio"
              name="timing"
              className="accent-primary w-3 h-3"
              checked={timing.mode === "scheduled"}
              onChange={() => setMode("scheduled")}
            />
            <span>{t("layeredPush.scheduledPushLabel")}</span>
          </label>
          {timing.mode === "scheduled" && (
            <div className="flex items-center gap-2 pl-5">
              <Input
                type="datetime-local"
                value={timing.scheduled_at || ""}
                onChange={(e) => setScheduledAt(e.target.value)}
                className="h-7 text-xs w-[200px]"
              />
            </div>
          )}
          {timing.mode === "scheduled" && timing.scheduled_at && (
            <p className="text-[11px] text-muted-foreground pl-5">
              {timing.fired_at
                ? t("layeredPush.firedNote", { time: fmtDateTime(timing.fired_at) })
                : t("layeredPush.scheduledPending", {
                    time: fmtDateTime(timing.scheduled_at),
                  })}
            </p>
          )}
        </div>
      </div>

      {/* Notification strategy */}
      <div className="mb-4">
        <span className="text-xs font-medium text-foreground block mb-2">
          {t("layeredPush.notifyStrategy")}
        </span>
        <div className="space-y-1.5">
          <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
            <Checkbox
              checked={notify.student}
              onCheckedChange={() => toggleNotify("student")}
              className="w-3.5 h-3.5"
            />{" "}
            {t("layeredPush.strategyStudent")}
          </label>
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
            <Checkbox
              checked={notify.parent}
              onCheckedChange={() => toggleNotify("parent")}
              className="w-3.5 h-3.5"
            />{" "}
            {t("layeredPush.strategyParent")}
          </label>
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
            <Checkbox
              checked={notify.reminder24h}
              onCheckedChange={() => toggleNotify("reminder24h")}
              className="w-3.5 h-3.5"
            />{" "}
            {t("layeredPush.strategyReminder")}
          </label>
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
            <Checkbox
              checked={notify.late}
              onCheckedChange={() => toggleNotify("late")}
              className="w-3.5 h-3.5"
            />{" "}
            {t("layeredPush.strategyLate")}
          </label>
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-2 mb-4">
        <Button
          variant="outline"
          size="sm"
          className="text-xs gap-1.5"
          onClick={onTestPush}
        >
          <Bell className="w-3.5 h-3.5" /> {t("layeredPush.testPush")}
        </Button>
        <Button size="sm" className="text-xs gap-1.5" onClick={onOpenConfirm}>
          <Send className="w-3.5 h-3.5" /> {t("layeredPush.confirmPush")}
        </Button>
        <span className="self-center text-[11px] text-muted-foreground">
          {t("layeredPush.studentCountHint", { count: studentCount })}
        </span>
      </div>

      {/* Templates */}
      <div className="border-t border-border/50 pt-3">
        <span className="text-xs text-muted-foreground block mb-2">
          {t("layeredPush.historyTemplates")}
          {settings.templates.length > 0 &&
            `（${settings.templates.length}）`}
        </span>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="text-xs h-7 gap-1"
            onClick={saveTemplate}
          >
            <Save className="w-3 h-3" /> {t("layeredPush.saveStandardTemplate")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="text-xs h-7 gap-1"
            onClick={() => setTemplateOpen(true)}
            disabled={settings.templates.length === 0}
          >
            <Clock className="w-3 h-3" /> {t("layeredPush.loadHistory")}
          </Button>
        </div>
      </div>

      {/* 加载模板 */}
      <Dialog open={templateOpen} onOpenChange={setTemplateOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("layeredPush.templatesDialogTitle")}</DialogTitle>
          </DialogHeader>
          <div className="max-h-[320px] overflow-y-auto space-y-1.5">
            {settings.templates.map((tpl, i) => (
              <div
                key={`${tpl.name}-${i}`}
                className="rounded-lg border border-border/50 bg-background px-3 py-2 flex items-center gap-2"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-foreground">{tpl.name}</p>
                  {tpl.saved_at && (
                    <p className="text-[11px] text-muted-foreground">
                      {t("layeredPush.savedAt", {
                        time: fmtDateTime(tpl.saved_at),
                      })}
                    </p>
                  )}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-xs h-6 px-2"
                  onClick={() => loadTemplate(tpl.snapshot)}
                >
                  {t("layeredPush.loadTemplate")}
                </Button>
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setTemplateOpen(false)}
            >
              {t("common.close")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
