import { useState, useMemo, useCallback, useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Wand2, Loader2 } from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import { LayeredHeader } from "./layered-push/LayeredHeader";
import { TierColumn } from "./layered-push/TierColumn";
import { DingTalkPreview } from "./layered-push/DingTalkPreview";
import { PushSettings } from "./layered-push/PushSettings";
import { EffectTracking } from "./layered-push/EffectTracking";
import { LayeredPushTour } from "./layered-push/LayeredPushTour";
import { TieredComposePanel } from "./layered-push/TieredComposePanel";
import {
  InlineLayeredTip,
  useLayeredTips,
  type TipConfig,
} from "./layered-push/LayeredDailyTips";
import {
  TIERS,
  WEEKDAY_KEYS,
  mergeSettings,
  nextDeadlineMs,
  type Tier,
  type LayeredPushSettings,
} from "./layered-push/layeredData";
import {
  useAutoTier,
  useLayeredRounds,
  useLayeredRoster,
  useLayeredSettings,
  useLayeredStats,
  useMoveTiers,
  useSaveLayeredSettings,
  useStartPush,
  useTestPush,
} from "@/hooks/useLayeredPush";
import {
  getDingtalkSyncStatus,
  saveLayeredPushSettings,
  type LayeredRosterStudent,
} from "@/services/api";

interface LayeredPushPageProps {
  selectedSubject: string;
  selectedClass: string;
  /** 班级显示名（钉钉徽标用） */
  selectedClassName?: string;
  schoolLevel: string;
  onNavChange: (id: string) => void;
}

function fmtTime(v?: string | null): string {
  if (!v) return "";
  return v.replace("T", " ").slice(0, 16);
}

export function LayeredPushPage({
  selectedSubject,
  selectedClass,
  selectedClassName,
  onNavChange,
}: LayeredPushPageProps) {
  const { t } = useLocale();
  const qc = useQueryClient();
  const { dismissed, dismiss } = useLayeredTips();

  const classId = selectedClass;
  const subject = selectedSubject;

  // ── 真实数据查询 ──
  const rosterQ = useLayeredRoster(classId, subject);
  const settingsQ = useLayeredSettings(classId, subject);
  const roundsQ = useLayeredRounds(classId, subject);
  const dingQ = useQuery({
    queryKey: ["dingtalk-status"],
    queryFn: getDingtalkSyncStatus,
    staleTime: 60_000,
  });

  // 推送后台发送中：4s 高频轮询统计；平时有轮次时 20s 慢轮询
  const [pushing, setPushing] = useState(false);
  const roundsCount = roundsQ.data?.length ?? 0;
  const statsQ = useLayeredStats(
    classId,
    subject,
    pushing ? 4000 : roundsCount > 0 ? 20000 : undefined,
  );
  const statsData = statsQ.data;

  useEffect(() => {
    if (!pushing || !statsData?.round_id) return;
    const pending = TIERS.reduce(
      (n, tr) => n + (statsData.tiers[tr]?.sent_pending || 0),
      0,
    );
    if (pending === 0) setPushing(false);
  }, [statsData, pushing]);

  useEffect(() => {
    if (!pushing) return;
    const id = setTimeout(() => setPushing(false), 120_000);
    return () => clearTimeout(id);
  }, [pushing]);

  // ── 设置：本地可编辑副本（防抖自动保存，仅班主任能写） ──
  const [settings, setSettings] = useState<LayeredPushSettings | null>(null);
  const settingsRef = useRef<LayeredPushSettings | null>(null);
  const hydratedKeyRef = useRef("");
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveMutation = useSaveLayeredSettings();

  const doSave = useCallback(
    (cid: string, subj: string, s: LayeredPushSettings) => {
      saveMutation.mutate({ class_id: cid, subject: subj, settings: s });
    },
    [saveMutation],
  );

  // 班级/学科切换时（或首次拉到设置时）合入默认值
  useEffect(() => {
    if (!classId) return;
    const key = `${classId}|${subject}`;
    if (hydratedKeyRef.current === key) return;
    if (settingsQ.data === undefined) return;
    hydratedKeyRef.current = key;
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    const merged = mergeSettings(settingsQ.data, subject);
    settingsRef.current = merged;
    setSettings(merged);
  }, [settingsQ.data, classId, subject]);

  // 局部更新 + 700ms 防抖保存
  const updateSettings = useCallback(
    (updater: (prev: LayeredPushSettings) => LayeredPushSettings) => {
      const prev = settingsRef.current;
      if (!prev) return;
      const next = updater(prev);
      settingsRef.current = next;
      setSettings(next);
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(() => {
        saveTimerRef.current = null;
        doSave(classId, subject, next);
      }, 700);
    },
    [classId, subject, doSave],
  );

  // 立即落盘（定时推送确认时用）
  const flushSave = useCallback(
    (s: LayeredPushSettings) => {
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
        saveTimerRef.current = null;
      }
      doSave(classId, subject, s);
    },
    [classId, subject, doSave],
  );

  // 卸载时把 700ms 窗口内的编辑直接写回（不走 hook，避免卸竞态）
  useEffect(() => {
    return () => {
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
        saveTimerRef.current = null;
        const s = settingsRef.current;
        const key = hydratedKeyRef.current;
        if (s && key) {
          const [cid, subj] = key.split("|");
          saveLayeredPushSettings({ class_id: cid, subject: subj, settings: s }).catch(
            () => undefined,
          );
        }
      }
    };
  }, []);

  // ── 分层分数线：A 线 / B 线草稿（失焦/回车提交，经防抖自动保存） ──
  const [thDraft, setThDraft] = useState<{ a: string; b: string }>({
    a: "80",
    b: "60",
  });
  useEffect(() => {
    if (!settings) return;
    setThDraft({
      a: String(settings.thresholds.a),
      b: String(settings.thresholds.b),
    });
  }, [settings?.thresholds.a, settings?.thresholds.b]);

  const commitThreshold = useCallback(
    (key: "a" | "b", raw: string) => {
      const prev = settingsRef.current;
      if (!prev) return;
      const restore = () =>
        setThDraft({
          a: String(prev.thresholds.a),
          b: String(prev.thresholds.b),
        });
      const v = Number(raw.trim());
      const other = key === "a" ? prev.thresholds.b : prev.thresholds.a;
      const ok =
        Number.isFinite(v) &&
        v >= 0 &&
        v <= 100 &&
        (key === "a" ? v > other : v < other);
      if (!ok) {
        toast.error(t("layeredPush.thresholdInvalid"));
        restore();
        return;
      }
      if (v === prev.thresholds[key]) {
        restore();
        return;
      }
      updateSettings((s) => ({
        ...s,
        thresholds: { ...s.thresholds, [key]: v },
      }));
    },
    [updateSettings, t],
  );

  // ── 分层调整：乐观更新 + 失败回滚 ──
  const moveMutation = useMoveTiers();
  const handleMoveStudent = useCallback(
    (studentId: string, fromTier: Tier, toTier: Tier) => {
      if (fromTier === toTier) return;
      const key = ["layered-roster", classId, subject];
      const prev = qc.getQueryData<LayeredRosterStudent[]>(key);
      qc.setQueryData<LayeredRosterStudent[]>(key, (old) =>
        old
          ? old.map((s) => (s.id === studentId ? { ...s, tier: toTier } : s))
          : old,
      );
      moveMutation
        .mutateAsync({
          class_id: classId,
          subject,
          moves: [{ student_id: studentId, tier: toTier }],
        })
        .catch(() => {
          if (prev) qc.setQueryData(key, prev);
        });
    },
    [classId, subject, qc, moveMutation],
  );

  const autoTierMutation = useAutoTier();
  const testPush = useTestPush();
  const pushMutation = useStartPush();

  // ── 推送确认 ──
  const [confirmOpen, setConfirmOpen] = useState(false);
  const handleConfirmPush = () => {
    if (!settings) return;
    if (settings.timing.mode === "scheduled") {
      if (!settings.timing.scheduled_at) {
        toast.error(t("layeredPush.toast.scheduledAtRequired"));
        return;
      }
      flushSave(settings);
      toast.success(
        t("layeredPush.toast.pushScheduled", {
          time: fmtTime(settings.timing.scheduled_at),
        }),
      );
      return;
    }
    setPushing(true);
    pushMutation.mutate({ class_id: classId, subject });
  };

  // ── 名单分组（按学生 id 拖拽；tier 非法/空归 B） ──
  const roster = rosterQ.data ?? [];
  const grouped = useMemo(() => {
    const g: Record<Tier, LayeredRosterStudent[]> = { A: [], B: [], C: [] };
    roster.forEach((s) => {
      const raw = (s.tier || "B").toUpperCase();
      g[raw === "A" || raw === "C" ? raw : "B"].push(s);
    });
    return g;
  }, [roster]);

  // ── 行内提示：全部由真实数据算出，无写死数字 ──
  const tips: TipConfig[] = useMemo(() => {
    const out: TipConfig[] = [];
    const warn = {
      borderColor: "border-l-warning",
      bgColor: "bg-warning/5",
    };
    const bad = {
      borderColor: "border-l-destructive",
      bgColor: "bg-destructive/5",
    };
    if (!roster.length) return out;

    const unsynced = roster.filter((s) => !s.dingtalk_synced).length;
    if (unsynced > 0) {
      out.push({
        id: "lp-unsynced",
        text: t("layeredPush.tips.unsynced", { count: unsynced }),
        ...bad,
      });
    }

    const counts: Record<Tier, number> = { A: 0, B: 0, C: 0 };
    roster.forEach((s) => {
      const raw = (s.tier || "B").toUpperCase();
      counts[raw === "A" || raw === "C" ? raw : "B"] += 1;
    });
    const top = TIERS.reduce((a, b) => (counts[a] >= counts[b] ? a : b));
    const topPct = Math.round((counts[top] / roster.length) * 100);
    if (roster.length >= 4 && topPct >= 50) {
      out.push({
        id: "lp-tier-imbalance",
        text: t("layeredPush.tips.tierImbalance", {
          tier: top,
          count: counts[top],
          pct: topPct,
        }),
        ...warn,
      });
    }

    if (settings) {
      const aMin = settings.tiers.A.estimated_minutes;
      const cMin = settings.tiers.C.estimated_minutes;
      if (aMin !== cMin) {
        out.push({
          id: "lp-time-imbalance",
          text: t("layeredPush.tips.timeImbalance", { aMin, cMin }),
          ...warn,
        });
      }

      // 最近截止（24 小时内）
      const now = Date.now();
      let soonTier: Tier | null = null;
      let soonMs = 0;
      TIERS.forEach((tr) => {
        const ms = nextDeadlineMs(settings.tiers[tr]);
        if (soonTier === null || ms < soonMs) {
          soonTier = tr;
          soonMs = ms;
        }
      });
      if (soonTier !== null && soonMs - now <= 24 * 3600 * 1000 && soonMs > now) {
        const c = settings.tiers[soonTier];
        out.push({
          id: "lp-due-soon",
          text: t("layeredPush.tips.dueSoon", {
            deadline: `${t(WEEKDAY_KEYS[c.deadline_weekday])} ${c.deadline_time}`,
          }),
          ...warn,
        });
      }
    }

    // 完成率最低的一层（仅在有真实轮次统计时）
    if (statsData?.round_id) {
      let worstTier: Tier | null = null;
      let worstPct = 101;
      TIERS.forEach((tr) => {
        const b = statsData.tiers[tr];
        if (!b || b.total === 0) return;
        const pct = Math.round((b.completed / b.total) * 100);
        if (pct < worstPct) {
          worstTier = tr;
          worstPct = pct;
        }
      });
      if (worstTier !== null && worstPct < 100) {
        out.push({
          id: "lp-low-completion",
          text: t("layeredPush.tips.lowCompletion", {
            tier: worstTier,
            pct: worstPct,
          }),
          ...bad,
        });
      }
    }
    return out;
  }, [roster, settings, statsData, t]);

  const renderTips = () =>
    tips.map((tip) => (
      <InlineLayeredTip
        key={tip.id}
        tip={tip}
        dismissed={dismissed}
        onDismiss={dismiss}
      />
    ));

  return (
    <div className="space-y-5 animate-fade-in pb-6">
      <LayeredPushTour />
      <LayeredHeader
        subject={subject}
        classId={classId}
        className={selectedClassName || ""}
        dingTalkConnected={!!dingQ.data?.configured}
        entryUrl={dingQ.data?.entry_url}
        studentCount={roster.length}
        onReauth={() => {
          const url = dingQ.data?.entry_url;
          if (url) window.open(url, "_blank", "noopener");
          else toast.error(t("layeredPush.reauthNoUrl"));
          dingQ.refetch();
        }}
      />

      {!classId && (
        <div className="rounded-xl border border-border/50 bg-card p-6 text-center text-sm text-muted-foreground">
          {t("layeredPush.pickClass")}
        </div>
      )}

      {classId && renderTips()}

      {/* 自动分层 + 分数线编辑（A 线 / B 线，改完自动保存） */}
      {classId && settings && (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-border/50 bg-card px-4 py-2.5">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-muted-foreground">
              {t("layeredPush.thresholdA")}
            </span>
            <Input
              type="number"
              min={0}
              max={100}
              step={1}
              value={thDraft.a}
              onChange={(e) => setThDraft((d) => ({ ...d, a: e.target.value }))}
              onBlur={(e) => commitThreshold("a", e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") commitThreshold("a", e.currentTarget.value);
              }}
              className="h-7 w-16 text-xs px-1.5"
            />
            <span className="text-xs text-muted-foreground">
              {t("layeredPush.thresholdB")}
            </span>
            <Input
              type="number"
              min={0}
              max={100}
              step={1}
              value={thDraft.b}
              onChange={(e) => setThDraft((d) => ({ ...d, b: e.target.value }))}
              onBlur={(e) => commitThreshold("b", e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") commitThreshold("b", e.currentTarget.value);
              }}
              className="h-7 w-16 text-xs px-1.5"
            />
            <p className="text-xs text-muted-foreground">
              {t("layeredPush.thresholds", {
                a: settings.thresholds.a,
                b: settings.thresholds.b,
              })}
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="text-xs gap-1.5"
            disabled={autoTierMutation.isPending}
            onClick={() =>
              autoTierMutation.mutate({
                class_id: classId,
                subject,
                thresholds: settings.thresholds,
              })
            }
          >
            <Wand2 className="w-3.5 h-3.5" /> {t("layeredPush.autoTierBtn")}
          </Button>
        </div>
      )}

      {/* 按层出卷：A/B/C 各一份分层卷 */}
      {classId && (
        <TieredComposePanel
          classId={classId}
          subject={subject}
          onOpenInExamGen={() => onNavChange("prep-exam")}
        />
      )}

      {/* Row 1: 三层名单/作业 + 钉钉消息预览 */}
      {classId &&
        (settingsQ.isError || rosterQ.isError ? (
          <div className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-xs text-destructive">
            {(settingsQ.error || rosterQ.error) instanceof Error
              ? ((settingsQ.error || rosterQ.error) as Error).message
              : t("layeredPush.loadFailed")}
          </div>
        ) : !settings || rosterQ.isLoading ? (
          <div className="flex items-center gap-2 text-xs text-muted-foreground py-6 justify-center">
            <Loader2 className="w-4 h-4 animate-spin" /> {t("layeredPush.loading")}
          </div>
        ) : (
          <div className="grid grid-cols-4 gap-4" data-tour="lp-tiers">
            {TIERS.map((tr) => (
              <TierColumn
                key={tr}
                tier={tr}
                students={grouped[tr]}
                content={settings.tiers[tr]}
                classId={classId}
                subject={subject}
                onMoveStudent={handleMoveStudent}
                onContentChange={(patch) =>
                  updateSettings((prev) => ({
                    ...prev,
                    tiers: {
                      ...prev.tiers,
                      [tr]: { ...prev.tiers[tr], ...patch },
                    },
                  }))
                }
                onRefreshRoster={() => rosterQ.refetch()}
              />
            ))}
            <DingTalkPreview
              classId={classId}
              subject={subject}
              settings={settings}
              onPatch={updateSettings}
            />
          </div>
        ))}

      {/* Row 2: 推送设置 + 效果追踪/推送记录 */}
      {classId && settings && (
        <div className="flex gap-4 flex-wrap">
          <PushSettings
            settings={settings}
            studentCount={roster.length}
            onPatch={updateSettings}
            onTestPush={() =>
              testPush.mutate({ class_id: classId, subject })
            }
            onOpenConfirm={() => setConfirmOpen(true)}
          />
          <EffectTracking
            stats={statsData}
            rounds={roundsQ.data ?? []}
            roster={roster}
            classId={classId}
            subject={subject}
          />
        </div>
      )}

      {/* 确认推送 */}
      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("layeredPush.confirmTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {settings?.timing.mode === "scheduled"
                ? t("layeredPush.confirmScheduledDesc", {
                    time: fmtTime(settings?.timing.scheduled_at) || "—",
                  })
                : t("layeredPush.confirmDesc", { count: roster.length })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmPush}>
              {t("common.confirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
