import { useState, useCallback } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { Library, Upload, Clock, Users2, GripVertical } from "lucide-react";
import type { TierConfig, Tier } from "./layeredData";

interface TierColumnProps {
  config: TierConfig;
  onMoveStudent: (studentName: string, fromTier: Tier, toTier: Tier) => void;
}

export function TierColumn({ config, onMoveStudent }: TierColumnProps) {
  const { t } = useLocale();
  const {
    tier,
    labelKey,
    subtitleKey,
    color,
    borderColor,
    dotColor,
    students,
    assignments,
    estimatedMinutes,
    deadlineKey,
    deadlineTime,
    requireParentSign,
    requirePhoto,
    requireVoice,
  } = config;
  const [dragOver, setDragOver] = useState(false);
  const { toast } = useToast();

  const demoToast = () => {
    toast({
      title: t("layeredPush.demoTitle"),
      description: t("layeredPush.demoDesc"),
    });
  };

  const handleDragStart = useCallback(
    (e: React.DragEvent, studentName: string) => {
      e.dataTransfer.setData(
        "text/plain",
        JSON.stringify({ name: studentName, fromTier: tier }),
      );
      e.dataTransfer.effectAllowed = "move";
    },
    [tier],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      try {
        const data = JSON.parse(e.dataTransfer.getData("text/plain"));
        if (data.name && data.fromTier) {
          onMoveStudent(data.name, data.fromTier, tier);
        }
      } catch {
        /* ignore */
      }
    },
    [tier, onMoveStudent],
  );

  return (
    <div
      className={cn(
        "rounded-xl border p-4 flex flex-col gap-4 min-w-0 transition-all duration-200",
        color,
        borderColor,
        dragOver && "ring-2 ring-primary/50 border-primary/50 scale-[1.01]",
      )}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={cn("w-3 h-3 rounded-full", dotColor)} />
          <span className="text-sm font-bold text-foreground">
            {t(labelKey)}
          </span>
          <Badge variant="outline" className="text-[10px] h-5">
            {t("layeredPush.peopleCount", { count: students.length })}
          </Badge>
        </div>
      </div>
      <p className="text-xs text-muted-foreground -mt-2">{t(subtitleKey)}</p>

      {/* Student list with drag */}
      <div>
        <div className="flex items-center gap-1.5 mb-2">
          <Users2 className="w-3.5 h-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-foreground">
            {t("layeredPush.studentList")}
          </span>
        </div>
        <ScrollArea className="h-[120px]">
          <div className="space-y-1">
            {students.map((s) => (
              <div
                key={s.name}
                draggable
                onDragStart={(e) => handleDragStart(e, s.name)}
                className="flex items-center gap-2 text-xs py-1 px-1.5 rounded-md cursor-grab active:cursor-grabbing hover:bg-background/80 transition-colors group"
              >
                <GripVertical className="w-3 h-3 text-muted-foreground/40 group-hover:text-muted-foreground shrink-0" />
                <div
                  className={cn(
                    "w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold text-white shrink-0",
                    dotColor,
                  )}
                >
                  {s.avatar}
                </div>
                <span className="text-foreground">{s.name}</span>
                <span className="text-muted-foreground ml-auto">
                  {t("layeredPush.scorePoints", { score: s.score })}
                </span>
                {s.dingTalkSynced && (
                  <span className="text-[10px] text-emerald-600">✓</span>
                )}
              </div>
            ))}
          </div>
        </ScrollArea>
        <Button
          variant="ghost"
          size="sm"
          className="text-xs h-6 px-2 mt-1 text-primary"
          onClick={demoToast}
        >
          {t("layeredPush.updateFromDingTalk")}
        </Button>
      </div>

      {/* Assignments */}
      <div data-tour="lp-assignments">
        <span className="text-xs font-medium text-foreground block mb-2">
          {t("layeredPush.assignmentLabel")}
        </span>
        <div className="space-y-2">
          {assignments.map((a) => (
            <div
              key={a.title}
              className="rounded-lg bg-background/60 border border-border/30 p-2.5"
            >
              <div className="flex items-center gap-1.5 mb-0.5">
                <span className="text-sm">{a.icon}</span>
                <span className="text-xs font-semibold text-foreground">
                  {a.title}
                </span>
              </div>
              <p className="text-[11px] text-muted-foreground">
                {a.description}
              </p>
            </div>
          ))}
        </div>
        <div className="flex gap-2 mt-2">
          <Button
            variant="outline"
            size="sm"
            className="text-xs h-7 gap-1"
            onClick={demoToast}
          >
            <Library className="w-3 h-3" /> {t("layeredPush.fromQuestionBank")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="text-xs h-7 gap-1"
            onClick={demoToast}
          >
            <Upload className="w-3 h-3" /> {t("layeredPush.uploadFile")}
          </Button>
        </div>
      </div>

      {/* Time & settings */}
      <div className="space-y-2 mt-auto">
        <div className="flex items-center gap-2 text-xs">
          <Clock className="w-3.5 h-3.5 text-muted-foreground" />
          <span className="text-muted-foreground">
            {t("layeredPush.estimatedTime")}
          </span>
          <span className="font-medium text-foreground">
            {t("layeredPush.minutes", { minutes: estimatedMinutes })}
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <Clock className="w-3.5 h-3.5 text-muted-foreground" />
          <span className="text-muted-foreground">
            {t("layeredPush.deadlineLabel")}
          </span>
          <span className="font-medium text-foreground">
            {t(deadlineKey)} {deadlineTime}
          </span>
        </div>

        <div
          className="pt-2 border-t border-border/30 space-y-1.5"
          data-tour="lp-dingtalk-settings"
        >
          <span className="text-xs font-medium text-foreground">
            {t("layeredPush.dingTalkSettings")}
          </span>
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
            <Checkbox
              defaultChecked={requireParentSign}
              className="w-3.5 h-3.5"
            />{" "}
            {t("layeredPush.requireParentSign")}
          </label>
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
            <Checkbox defaultChecked={requirePhoto} className="w-3.5 h-3.5" />{" "}
            {t("layeredPush.requirePhoto")}
          </label>
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
            <Checkbox defaultChecked={requireVoice} className="w-3.5 h-3.5" />{" "}
            {t("layeredPush.requireVoice")}
          </label>
        </div>
      </div>
    </div>
  );
}
