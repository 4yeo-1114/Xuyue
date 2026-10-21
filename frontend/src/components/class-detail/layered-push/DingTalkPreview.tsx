import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
import { Smartphone, Eye } from "lucide-react";
import { getMessagePreview } from "@/services/api";
import type { LayeredPushSettings } from "@/services/api";
import { TIERS, TIER_STYLES, type Tier } from "./layeredData";

interface DingTalkPreviewProps {
  classId: string;
  subject: string;
  settings: LayeredPushSettings;
  /** 修改作业形式（form_type 只影响推送文案的说明方式） */
  onPatch: (updater: (prev: LayeredPushSettings) => LayeredPushSettings) => void;
}

/** 极简 markdown 渲染：只处理 **加粗**，其余按行显示 */
function renderMarkdown(text: string) {
  return text.split("\n").map((line, i) => {
    if (!line.trim()) return <div key={i} className="h-1.5" />;
    const parts = line.split(/\*\*(.+?)\*\*/g);
    return (
      <p key={i} className="leading-relaxed">
        {parts.map((p, j) =>
          j % 2 === 1 ? (
            <strong key={j} className="text-foreground font-semibold">
              {p}
            </strong>
          ) : (
            <span key={j}>{p}</span>
          ),
        )}
      </p>
    );
  });
}

export function DingTalkPreview({
  classId,
  subject,
  settings,
  onPatch,
}: DingTalkPreviewProps) {
  const { t } = useLocale();
  const [tier, setTier] = useState<Tier>("A");
  const [dialogOpen, setDialogOpen] = useState(false);

  const previewQuery = useQuery({
    queryKey: ["layered-preview", classId, subject, tier],
    queryFn: () => getMessagePreview(classId, subject, tier),
    enabled: !!classId,
  });

  const body = previewQuery.data?.body_markdown || "";
  const title = previewQuery.data?.title || "";
  const parentEnabled = settings.notify.parent;

  return (
    <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Smartphone className="w-4 h-4 text-primary" />
          <span className="text-sm font-bold text-foreground">
            {t("layeredPush.syncPreviewTitle")}
          </span>
        </div>
        {/* 预览层级切换 */}
        <div className="flex gap-1">
          {TIERS.map((tr) => (
            <button
              key={tr}
              onClick={() => setTier(tr)}
              className={cn(
                "w-5 h-5 rounded text-[10px] font-bold border transition-colors",
                tier === tr
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border/60 bg-background text-muted-foreground hover:border-primary/50",
              )}
            >
              {tr}
            </button>
          ))}
        </div>
      </div>

      {/* Student view：真实拼装的推送消息 */}
      <div className="rounded-lg bg-background border border-border/50 p-3">
        <div className="flex items-center gap-1.5 mb-2">
          <span className="text-sm">📱</span>
          <span className="text-xs font-semibold text-foreground">
            {t("layeredPush.studentReceives")}
          </span>
          <span className="text-[10px] text-muted-foreground ml-auto">
            {t(TIER_STYLES[tier].labelKey)}
          </span>
        </div>
        <div className="text-[11px] text-muted-foreground space-y-0.5">
          {previewQuery.isLoading && <p>{t("layeredPush.loading")}</p>}
          {previewQuery.isError && (
            <p className="text-destructive">
              {(previewQuery.error as Error)?.message}
            </p>
          )}
          {title && <p className="font-semibold text-foreground">{title}</p>}
          {body && renderMarkdown(body)}
        </div>
      </div>

      {/* Parent view：同一消息（或未开启家长通知） */}
      <div className="rounded-lg bg-background border border-border/50 p-3">
        <div className="flex items-center gap-1.5 mb-2">
          <span className="text-sm">📱</span>
          <span className="text-xs font-semibold text-foreground">
            {t("layeredPush.parentReceives")}
          </span>
        </div>
        <div className="text-[11px] text-muted-foreground space-y-0.5">
          {!parentEnabled ? (
            <p className="italic">{t("layeredPush.parentDisabled")}</p>
          ) : (
            <>
              <p className="text-[10px] text-muted-foreground italic">
                {t("layeredPush.parentSameMessage")}
              </p>
              {title && <p className="font-semibold text-foreground">{title}</p>}
              {body && renderMarkdown(body)}
            </>
          )}
        </div>
      </div>

      {/* Form type：持久化的偏好，影响文案说明方式 */}
      <div className="rounded-lg bg-background border border-border/50 p-3">
        <div className="flex items-center gap-1.5 mb-2">
          <span className="text-sm">📎</span>
          <span className="text-xs font-semibold text-foreground">
            {t("layeredPush.formType")}
          </span>
        </div>
        <div className="space-y-1.5">
          <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
            <input
              type="radio"
              name="form"
              className="accent-primary w-3 h-3"
              checked={settings.form_type === "dingtalk"}
              onChange={() => onPatch((p) => ({ ...p, form_type: "dingtalk" }))}
            />{" "}
            {t("layeredPush.formDingTalk")}
          </label>
          <label className="flex items-center gap-2 text-xs text-foreground font-medium cursor-pointer">
            <input
              type="radio"
              name="form"
              className="accent-primary w-3 h-3"
              checked={settings.form_type === "h5"}
              onChange={() => onPatch((p) => ({ ...p, form_type: "h5" }))}
            />{" "}
            {t("layeredPush.formH5")}
          </label>
        </div>
        <p className="text-[10px] text-muted-foreground mt-1.5">
          {t("layeredPush.h5Hint")}
        </p>
      </div>

      <Button
        variant="outline"
        size="sm"
        className="text-xs gap-1.5"
        onClick={() => setDialogOpen(true)}
      >
        <Eye className="w-3.5 h-3.5" /> {t("layeredPush.previewEffect")}
      </Button>

      {/* 完整预览（与实际推送同一拼装函数） */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {t("layeredPush.previewDialogTitle", {
                tier: t(TIER_STYLES[tier].labelKey),
              })}
            </DialogTitle>
          </DialogHeader>
          <div className="max-h-[50vh] overflow-y-auto rounded-lg border border-border/50 bg-background p-3 text-xs text-muted-foreground space-y-0.5">
            {title && <p className="font-semibold text-foreground">{title}</p>}
            {body ? (
              renderMarkdown(body)
            ) : (
              <p>{t("layeredPush.loading")}</p>
            )}
          </div>
          <p className="text-[10px] text-muted-foreground">
            {t("layeredPush.previewSameAsReal")}
          </p>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setDialogOpen(false)}>
              {t("common.close")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
