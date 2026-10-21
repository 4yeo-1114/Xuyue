import { useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { BarChart3, Phone, FileText, History, CheckCircle2 } from "lucide-react";
import type { LayeredRound, LayeredRosterStudent, LayeredStats } from "@/services/api";
import {
  usePatchTaskStatus,
  useSendReport,
  useUrgePush,
} from "@/hooks/useLayeredPush";
import { TIER_STYLES, TIERS, type Tier } from "./layeredData";

interface EffectTrackingProps {
  stats?: LayeredStats;
  rounds: LayeredRound[];
  roster: LayeredRosterStudent[];
  classId: string;
  subject: string;
}

function statusIcon(completedPct: number) {
  if (completedPct >= 95) return { icon: "🟢", color: "text-emerald-600" };
  if (completedPct >= 80) return { icon: "🟡", color: "text-yellow-600" };
  return { icon: "🟠", color: "text-orange-600" };
}

function fmtTime(v?: string | null): string {
  if (!v) return "—";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return v;
  return d.toLocaleString();
}

export function EffectTracking({
  stats,
  rounds,
  roster,
  classId,
  subject,
}: EffectTrackingProps) {
  const { t } = useLocale();
  const urgeMutation = useUrgePush();
  const patchTask = usePatchTaskStatus(classId, subject);
  const reportMutation = useSendReport();
  const [phoneTier, setPhoneTier] = useState<Tier | null>(null);

  const hasRound = !!stats?.round_id;
  const tierKeys = TIERS.filter((tr) => stats?.tiers[tr]);

  // 「电话家长」名单：本层未完成 → 按名字找回家长联系方式（PII 权限内才有值）
  const phoneTargets =
    phoneTier && stats?.tiers[phoneTier]
      ? stats.tiers[phoneTier].unfinished
          .map((u) => roster.find((s) => s.name === u.name))
          .filter((s): s is LayeredRosterStudent => !!s)
      : [];

  return (
    <div
      className="flex-1 min-w-[320px] rounded-xl border border-border/50 bg-card p-5"
      data-tour="lp-tracking"
    >
      <h3 className="text-sm font-bold text-foreground flex items-center gap-2 mb-4">
        <BarChart3 className="w-4 h-4 text-primary" />{" "}
        {hasRound
          ? t("layeredPush.trackingTitle", { week: stats?.round_index ?? 0 })
          : t("layeredPush.trackingEmptyTitle")}
      </h3>

      {!hasRound && (
        <p className="text-xs text-muted-foreground mb-1">
          {t("layeredPush.statsEmpty")}
        </p>
      )}

      <div className="space-y-4">
        {tierKeys.map((tr) => {
          const bucket = stats!.tiers[tr];
          const style = TIER_STYLES[tr];
          const completedPct =
            bucket.total > 0 ? Math.round((bucket.completed / bucket.total) * 100) : 0;
          const st = statusIcon(completedPct);
          const hiddenUnfinished = Math.max(
            0,
            bucket.total - bucket.completed - bucket.unfinished.length,
          );
          const unfinishedNames = bucket.unfinished.map((u) => u.name);

          return (
            <div
              key={tr}
              className="rounded-lg bg-muted/30 border border-border/30 p-3 space-y-2"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-foreground">
                  {t("layeredPush.tierPeople", {
                    label: t(style.labelKey),
                    count: bucket.total,
                  })}
                </span>
                <span className="text-sm">{st.icon}</span>
              </div>

              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">
                    {t("layeredPush.statSentOk")}
                  </span>
                  <span className="text-foreground font-medium">
                    {bucket.sent_ok}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">
                    {t("layeredPush.statSentFailed")}
                  </span>
                  <span
                    className={cn(
                      "font-medium",
                      bucket.sent_failed > 0
                        ? "text-destructive"
                        : "text-foreground",
                    )}
                  >
                    {bucket.sent_failed}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">
                    {t("layeredPush.statSkipped")}
                  </span>
                  <span className="text-foreground font-medium">
                    {bucket.sent_skipped}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">
                    {t("layeredPush.statPending")}
                  </span>
                  <span className="text-foreground font-medium">
                    {bucket.sent_pending}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">
                    {t("layeredPush.completed")}
                  </span>
                  <span className={cn("font-medium", st.color)}>
                    {completedPct}%（{bucket.completed}/{bucket.total}）
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">
                    {t("layeredPush.statParentSent")}
                  </span>
                  <span className="text-foreground font-medium">
                    {bucket.parent_sent_ok}
                  </span>
                </div>
              </div>

              {bucket.unfinished.length > 0 && (
                <div>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {bucket.unfinished.map((u) => (
                      <button
                        key={u.task_id}
                        title={t("layeredPush.markCompleteHint")}
                        disabled={patchTask.isPending}
                        onClick={() =>
                          patchTask.mutate({
                            task_id: u.task_id,
                            status: "completed",
                          })
                        }
                        className="inline-flex items-center gap-1 rounded-md border border-orange-500/30 bg-orange-500/10 px-1.5 py-0.5 text-[11px] text-orange-700 hover:bg-orange-500/20 disabled:opacity-50"
                      >
                        <CheckCircle2 className="w-3 h-3" />
                        {u.name}
                      </button>
                    ))}
                    {hiddenUnfinished > 0 && (
                      <span className="text-[11px] text-muted-foreground">
                        {t("layeredPush.unfinishedMore", { n: hiddenUnfinished })}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 text-xs mt-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-xs h-6 px-2 text-orange-600 border-orange-500/30"
                      disabled={urgeMutation.isPending}
                      onClick={() =>
                        urgeMutation.mutate({
                          class_id: classId,
                          subject,
                          tier: tr,
                        })
                      }
                    >
                      {t("layeredPush.urge", {
                        names:
                          unfinishedNames.length > 2
                            ? `${unfinishedNames.slice(0, 2).join("、")}${t("layeredPush.urgeEtc", { count: unfinishedNames.length })}`
                            : unfinishedNames.join("、"),
                      })}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-xs h-6 px-2 gap-1"
                      onClick={() => setPhoneTier(tr)}
                    >
                      <Phone className="w-3 h-3" /> {t("layeredPush.callParents")}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* 推送记录（真实轮次，新→旧） */}
      <div
        className="mt-4 rounded-lg bg-primary/5 border border-primary/20 p-3"
        data-tour="lp-interaction"
      >
        <div className="flex items-center gap-1.5 mb-2">
          <History className="w-3.5 h-3.5 text-primary" />
          <span className="text-xs font-semibold text-foreground">
            {t("layeredPush.roundsTitle")}
          </span>
        </div>
        {rounds.length === 0 ? (
          <p className="text-[11px] text-muted-foreground">{t("layeredPush.noRounds")}</p>
        ) : (
          <div className="space-y-1">
            {rounds.slice(0, 6).map((r) => (
              <div
                key={r.round_id}
                className="flex items-center justify-between text-[11px] text-muted-foreground"
              >
                <span>{fmtTime(r.pushed_at)}</span>
                <span className="text-foreground">
                  {t("layeredPush.roundRow", {
                    sent: r.sent_ok,
                    total: r.total,
                    completed: r.completed,
                  })}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Actions：真实报告（本人/班主任钉钉） */}
      <div className="flex gap-2 mt-4">
        <Button
          variant="outline"
          size="sm"
          className="text-xs gap-1.5"
          disabled={reportMutation.isPending}
          onClick={() =>
            reportMutation.mutate({
              class_id: classId,
              subject,
              kind: "weekly",
              recipient: "self",
            })
          }
        >
          <FileText className="w-3.5 h-3.5" /> {t("layeredPush.weeklyReport")}
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="text-xs gap-1.5"
          disabled={reportMutation.isPending}
          onClick={() =>
            reportMutation.mutate({
              class_id: classId,
              subject,
              kind: "weekly",
              recipient: "head",
            })
          }
        >
          {t("layeredPush.sendToManagement")}
        </Button>
      </div>

      {/* 电话家长 */}
      <Dialog open={phoneTier !== null} onOpenChange={(o) => !o && setPhoneTier(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {phoneTier
                ? t("layeredPush.phoneDialogTitle", {
                    tier: t(TIER_STYLES[phoneTier].labelKey),
                  })
                : ""}
            </DialogTitle>
          </DialogHeader>
          <div className="max-h-[320px] overflow-y-auto space-y-1.5">
            {phoneTargets.length === 0 && (
              <p className="text-xs text-muted-foreground">
                {t("layeredPush.piiHidden")}
              </p>
            )}
            {phoneTargets.map((s) => (
              <div
                key={s.id}
                className="flex items-center justify-between rounded-lg border border-border/50 bg-background px-3 py-2 text-xs"
              >
                <span className="font-medium text-foreground">
                  {s.name}
                  {s.parent_name && (
                    <span className="text-muted-foreground font-normal">
                      {" "}
                      · {s.parent_name}
                    </span>
                  )}
                </span>
                {s.parent_phone ? (
                  <a
                    href={`tel:${s.parent_phone}`}
                    className="text-primary hover:underline"
                  >
                    {s.parent_phone}
                  </a>
                ) : (
                  <span className="text-muted-foreground">
                    {t("layeredPush.noPhone")}
                  </span>
                )}
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setPhoneTier(null)}>
              {t("common.close")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
