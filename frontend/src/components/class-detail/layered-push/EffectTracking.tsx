import { Button } from "@/components/ui/button";
import { useLocale } from "@/contexts/LocaleContext";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { BarChart3, Phone, FileText, Bot, MessageSquare } from "lucide-react";
import type { TrackingTier, DingTalkInteraction } from "./layeredData";

interface EffectTrackingProps {
  tracking: TrackingTier[];
  interaction: DingTalkInteraction;
  weekNum: number;
}

function statusIcon(completedPct: number) {
  if (completedPct >= 95) return { icon: "🟢", color: "text-emerald-600" };
  if (completedPct >= 80) return { icon: "🟡", color: "text-yellow-600" };
  return { icon: "🟠", color: "text-orange-600" };
}

export function EffectTracking({
  tracking,
  interaction,
  weekNum,
}: EffectTrackingProps) {
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
      data-tour="lp-tracking"
    >
      <h3 className="text-sm font-bold text-foreground flex items-center gap-2 mb-4">
        <BarChart3 className="w-4 h-4 text-primary" />{" "}
        {t("layeredPush.trackingTitle", { week: weekNum })}
      </h3>

      <div className="space-y-4">
        {tracking.map((tr) => {
          const completedPct =
            tr.total > 0 ? Math.round((tr.completed / tr.total) * 100) : 0;
          const st = statusIcon(completedPct);
          return (
            <div
              key={tr.tier}
              className="rounded-lg bg-muted/30 border border-border/30 p-3 space-y-2"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-foreground">
                  {t("layeredPush.tierPeople", {
                    label: t(tr.labelKey),
                    count: tr.total,
                  })}
                </span>
                <span className="text-sm">{st.icon}</span>
              </div>

              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">
                    {t("layeredPush.viewed")}
                  </span>
                  <span className="text-foreground font-medium">
                    {Math.round((tr.viewed / tr.total) * 100)}%（
                    {tr.viewed}/{tr.total}）
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">
                    {t("layeredPush.entered")}
                  </span>
                  <span className="text-foreground font-medium">
                    {Math.round((tr.entered / tr.total) * 100)}%（
                    {tr.entered}/{tr.total}）
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">
                    {t("layeredPush.completed")}
                  </span>
                  <span className={cn("font-medium", st.color)}>
                    {completedPct}%
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">
                    {t("layeredPush.avgTime")}
                  </span>
                  <span className="text-foreground font-medium">
                    {t("layeredPush.minutesUnit", { value: tr.avgMinutes })}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-2 text-xs">
                <span className="text-muted-foreground">
                  {t("layeredPush.feedback")}
                </span>
                <span>
                  {t("layeredPush.feedbackGood", { count: tr.feedback.good })}
                </span>
                <span>
                  {t("layeredPush.feedbackNeutral", {
                    count: tr.feedback.neutral,
                  })}
                </span>
                <span>
                  {t("layeredPush.feedbackBad", { count: tr.feedback.bad })}
                </span>
              </div>

              {tr.unfinished.length > 0 && (
                <div className="flex items-center gap-2 flex-wrap">
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-xs h-6 px-2 text-orange-600 border-orange-500/30"
                    onClick={demoToast}
                  >
                    {t("layeredPush.urge", {
                      names: tr.unfinished.join("、"),
                    })}
                  </Button>
                  {tr.tier === "C" && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-xs h-6 px-2 gap-1"
                      onClick={demoToast}
                    >
                      <Phone className="w-3 h-3" />{" "}
                      {t("layeredPush.callParents")}
                    </Button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* DingTalk interaction */}
      <div
        className="mt-4 rounded-lg bg-primary/5 border border-primary/20 p-3"
        data-tour="lp-interaction"
      >
        <div className="flex items-center gap-1.5 mb-2">
          <MessageSquare className="w-3.5 h-3.5 text-primary" />
          <span className="text-xs font-semibold text-foreground">
            {t("layeredPush.interactionData")}
          </span>
        </div>
        <div className="grid grid-cols-3 gap-2 text-xs mb-2">
          <div className="text-center">
            <p className="text-lg font-bold text-foreground">
              {interaction.groupMessages}
            </p>
            <p className="text-muted-foreground">
              {t("layeredPush.groupDiscussion")}
            </p>
          </div>
          <div className="text-center">
            <p className="text-lg font-bold text-foreground">
              {interaction.sharedWorks}
            </p>
            <p className="text-muted-foreground">
              {t("layeredPush.excellentShare")}
            </p>
          </div>
          <div className="text-center">
            <p className="text-lg font-bold text-foreground">
              {interaction.parentMessages}
            </p>
            <p className="text-muted-foreground">
              {t("layeredPush.parentMessages")}
            </p>
          </div>
        </div>
        <p className="text-[11px] text-muted-foreground">
          {t("layeredPush.mainTopicLabel", {
            topic: t(interaction.mainTopicKey),
          })}
        </p>
      </div>

      {/* Actions */}
      <div className="flex gap-2 mt-4">
        <Button
          variant="outline"
          size="sm"
          className="text-xs gap-1.5"
          onClick={demoToast}
        >
          <FileText className="w-3.5 h-3.5" /> {t("layeredPush.weeklyReport")}
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="text-xs gap-1.5"
          onClick={demoToast}
        >
          {t("layeredPush.sendToManagement")}
        </Button>
      </div>

      {/* Robot broadcast */}
      <div className="mt-4 rounded-lg bg-muted/30 border border-border/30 p-3">
        <div className="flex items-center gap-1.5 mb-1.5">
          <Bot className="w-3.5 h-3.5 text-primary" />
          <span className="text-xs font-semibold text-foreground">
            {t("layeredPush.robotBroadcast")}
          </span>
        </div>
        <p className="text-[11px] text-muted-foreground italic mb-2">
          {t("layeredPush.robotMessage")}
        </p>
        <Button
          variant="ghost"
          size="sm"
          className="text-xs h-6 px-2 text-primary"
          onClick={demoToast}
        >
          {t("layeredPush.setBroadcastRule")}
        </Button>
      </div>
    </div>
  );
}
