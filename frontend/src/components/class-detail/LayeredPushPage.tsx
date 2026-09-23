import { useState, useMemo, useCallback, useEffect, useRef } from "react";
import { Info } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { useLocale } from "@/contexts/LocaleContext";
import { LayeredHeader } from "./layered-push/LayeredHeader";
import { TierColumn } from "./layered-push/TierColumn";
import { DingTalkPreview } from "./layered-push/DingTalkPreview";
import { PushSettings } from "./layered-push/PushSettings";
import { EffectTracking } from "./layered-push/EffectTracking";
import {
  generateTierConfigs,
  generateTracking,
  generateDingTalkInteraction,
  type Tier,
  type TierConfig,
  type TierStudent,
} from "./layered-push/layeredData";
import { LayeredPushTour } from "./layered-push/LayeredPushTour";
import {
  useLayeredTips,
  InlineLayeredTip,
  LAYERED_TIPS,
} from "./layered-push/LayeredDailyTips";

interface LayeredPushPageProps {
  selectedSubject: string;
  selectedClass: string;
  schoolLevel: string;
  onNavChange: (id: string) => void;
}

export function LayeredPushPage({
  selectedSubject,
  selectedClass,
  schoolLevel,
  onNavChange,
}: LayeredPushPageProps) {
  const [tiers, setTiers] = useState<TierConfig[]>(() =>
    generateTierConfigs(selectedClass, selectedSubject),
  );
  const { dismissed, dismiss } = useLayeredTips();
  const { toast } = useToast();
  const { t } = useLocale();

  // 首屏提示：纯演示数据
  useEffect(() => {
    toast({
      title: t("classDetail.demoDataTitle"),
      description: t("classDetail.demoDataDesc"),
    });
  }, [toast, t]);

  // Reset when class/subject changes（挂载时仅由 useState 初始值生成一次；切换科目/班级时再重置）
  const firstTierGenRef = useRef(true);
  useEffect(() => {
    if (firstTierGenRef.current) {
      firstTierGenRef.current = false;
      return;
    }
    setTiers(generateTierConfigs(selectedClass, selectedSubject));
  }, [selectedClass, selectedSubject]);

  const tracking = useMemo(
    () => generateTracking(selectedClass, selectedSubject),
    [selectedClass, selectedSubject],
  );
  const interaction = useMemo(
    () => generateDingTalkInteraction(selectedClass, selectedSubject),
    [selectedClass, selectedSubject],
  );

  const handleMoveStudent = useCallback(
    (studentName: string, fromTier: Tier, toTier: Tier) => {
      if (fromTier === toTier) return;
      setTiers((prev) => {
        const next = prev.map((t) => ({ ...t, students: [...t.students] }));
        const fromIdx = next.findIndex((t) => t.tier === fromTier);
        const toIdx = next.findIndex((t) => t.tier === toTier);
        if (fromIdx === -1 || toIdx === -1) return prev;
        const studentIdx = next[fromIdx].students.findIndex(
          (s) => s.name === studentName,
        );
        if (studentIdx === -1) return prev;
        const [student] = next[fromIdx].students.splice(studentIdx, 1);
        next[toIdx].students.push(student);
        return next;
      });
    },
    [],
  );

  return (
    <div className="space-y-5 animate-fade-in pb-6">
      <LayeredPushTour />
      <LayeredHeader
        subject={selectedSubject}
        className={selectedClass}
        dingTalkConnected={false}
      />
      <div
        className="flex items-start gap-2.5 rounded-lg border border-amber-300/70 bg-amber-50 px-3 py-2.5 text-amber-800 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-300"
        role="note"
      >
        <Info className="w-4 h-4 shrink-0 mt-0.5" />
        <div className="text-xs">
          <p className="font-semibold leading-5">
            {t("classDetail.demoDataNoteTitle")}
          </p>
          <p className="text-[11px] opacity-80 mt-0.5">
            {t("classDetail.demoDataNoteDesc")}
          </p>
        </div>
      </div>
      <InlineLayeredTip
        tip={LAYERED_TIPS.unsyncedStudents}
        dismissed={dismissed}
        onDismiss={dismiss}
      />

      {/* Row 1: Three tier columns + DingTalk preview */}
      <InlineLayeredTip
        tip={LAYERED_TIPS.tierImbalance}
        dismissed={dismissed}
        onDismiss={dismiss}
      />
      <div className="grid grid-cols-4 gap-4" data-tour="lp-tiers">
        {tiers.map((t) => (
          <TierColumn
            key={t.tier}
            config={t}
            onMoveStudent={handleMoveStudent}
          />
        ))}
        <DingTalkPreview />
      </div>
      <InlineLayeredTip
        tip={LAYERED_TIPS.timeImbalance}
        dismissed={dismissed}
        onDismiss={dismiss}
      />

      {/* Row 2: Push settings + Effect tracking */}
      <div className="flex gap-4 flex-wrap">
        <PushSettings />
        <EffectTracking
          tracking={tracking}
          interaction={interaction}
          weekNum={3}
        />
      </div>
      <InlineLayeredTip
        tip={LAYERED_TIPS.lowCompletion}
        dismissed={dismissed}
        onDismiss={dismiss}
      />
      <InlineLayeredTip
        tip={LAYERED_TIPS.urgeReminder}
        dismissed={dismissed}
        onDismiss={dismiss}
      />
      <InlineLayeredTip
        tip={LAYERED_TIPS.interactionActive}
        dismissed={dismissed}
        onDismiss={dismiss}
      />
      <InlineLayeredTip
        tip={LAYERED_TIPS.weeklyReport}
        dismissed={dismissed}
        onDismiss={dismiss}
      />
    </div>
  );
}
