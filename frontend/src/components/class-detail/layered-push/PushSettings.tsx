import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { useLocale } from "@/contexts/LocaleContext";
import { useToast } from "@/hooks/use-toast";
import { Bell, Send, Save, Clock } from "lucide-react";

export function PushSettings() {
  const { t } = useLocale();
  const { toast } = useToast();

  const demoToast = () => {
    toast({
      title: t("layeredPush.demoTitle"),
      description: t("layeredPush.demoDesc"),
    });
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
            />{" "}
            {t("layeredPush.pushImmediately")}
          </label>
          <label className="flex items-center gap-2 text-xs text-foreground font-medium cursor-pointer">
            <input
              type="radio"
              name="timing"
              className="accent-primary w-3 h-3"
              defaultChecked
            />
            <span>
              {t("layeredPush.scheduledPush", {
                time: t("layeredPush.mondayMorning"),
              })}
            </span>
          </label>
        </div>
      </div>

      {/* Notification strategy */}
      <div className="mb-4">
        <span className="text-xs font-medium text-foreground block mb-2">
          {t("layeredPush.notifyStrategy")}
        </span>
        <div className="space-y-1.5">
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
            <Checkbox defaultChecked className="w-3.5 h-3.5" />{" "}
            {t("layeredPush.strategyStudent")}
          </label>
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
            <Checkbox defaultChecked className="w-3.5 h-3.5" />{" "}
            {t("layeredPush.strategyParent")}
          </label>
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
            <Checkbox defaultChecked className="w-3.5 h-3.5" />{" "}
            {t("layeredPush.strategyReminder")}
          </label>
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
            <Checkbox defaultChecked className="w-3.5 h-3.5" />{" "}
            {t("layeredPush.strategyLate")}
          </label>
        </div>
      </div>

      {/* Group management */}
      <div className="mb-4">
        <span className="text-xs font-medium text-foreground block mb-2">
          {t("layeredPush.groupManagement")}
        </span>
        <div className="space-y-1.5">
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
            <Checkbox defaultChecked className="w-3.5 h-3.5" />{" "}
            {t("layeredPush.syncToChannel")}
          </label>
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
            <Checkbox className="w-3.5 h-3.5" />{" "}
            {t("layeredPush.onlyHomeworkBook")}
          </label>
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
            <Checkbox defaultChecked className="w-3.5 h-3.5" />{" "}
            {t("layeredPush.autoPraise")}
          </label>
        </div>
      </div>

      {/* Data sync */}
      <div className="mb-5">
        <span className="text-xs font-medium text-foreground block mb-2">
          {t("layeredPush.dataSync")}
        </span>
        <div className="space-y-1.5">
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
            <Checkbox defaultChecked className="w-3.5 h-3.5" />{" "}
            {t("layeredPush.syncCompletion")}
          </label>
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
            <Checkbox defaultChecked className="w-3.5 h-3.5" />{" "}
            {t("layeredPush.syncScores")}
          </label>
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
            <Checkbox defaultChecked className="w-3.5 h-3.5" />{" "}
            {t("layeredPush.syncComments")}
          </label>
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-2 mb-4">
        <Button
          variant="outline"
          size="sm"
          className="text-xs gap-1.5"
          onClick={demoToast}
        >
          <Bell className="w-3.5 h-3.5" /> {t("layeredPush.testPush")}
        </Button>
        <Button size="sm" className="text-xs gap-1.5" onClick={demoToast}>
          <Send className="w-3.5 h-3.5" /> {t("layeredPush.confirmPush")}
        </Button>
      </div>

      {/* Templates */}
      <div className="border-t border-border/50 pt-3">
        <span className="text-xs text-muted-foreground block mb-2">
          {t("layeredPush.historyTemplates")}
        </span>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="text-xs h-7 gap-1"
            onClick={demoToast}
          >
            <Save className="w-3 h-3" /> {t("layeredPush.saveStandardTemplate")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="text-xs h-7 gap-1"
            onClick={demoToast}
          >
            <Clock className="w-3 h-3" /> {t("layeredPush.loadHistory")}
          </Button>
        </div>
      </div>
    </div>
  );
}
