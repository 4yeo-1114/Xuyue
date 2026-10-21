import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Layers,
  RefreshCw,
  Paperclip,
  Megaphone,
  BarChart3,
} from "lucide-react";
import { useSendReport, useStartPush, useSyncRoster } from "@/hooks/useLayeredPush";

interface LayeredHeaderProps {
  subject: string;
  classId: string;
  /** 班级显示名（徽标用） */
  className: string;
  dingTalkConnected: boolean;
  /** 钉钉工作台入口（重新授权打开） */
  entryUrl?: string | null;
  /** 本班人数（徽标计数） */
  studentCount: number;
  /** 重新授权：打开入口 + 刷新连接状态 */
  onReauth: () => void;
}

export function LayeredHeader({
  subject,
  classId,
  className: cls,
  dingTalkConnected,
  entryUrl,
  studentCount,
  onReauth,
}: LayeredHeaderProps) {
  const { t } = useLocale();
  const syncRoster = useSyncRoster();
  const startPush = useStartPush();
  const reportMutation = useSendReport();
  const [noticeOpen, setNoticeOpen] = useState(false);
  const [noticeText, setNoticeText] = useState("");

  const sendNotice = () => {
    const text = noticeText.trim();
    if (!text) return;
    startPush.mutate({
      class_id: classId,
      subject,
      notice_only: true,
      notice_text: text,
    });
    setNoticeOpen(false);
    setNoticeText("");
  };

  return (
    <div className="space-y-3" data-tour="lp-header">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
            <Layers className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-foreground">
              {t("layeredPush.title")}
            </h2>
            <p className="text-xs text-muted-foreground">
              {t("layeredPush.subtitle")}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge
            variant="outline"
            className={
              dingTalkConnected
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 gap-1.5"
                : "border-orange-500/30 bg-orange-500/10 text-orange-700 gap-1.5"
            }
          >
            <span
              className={`w-2 h-2 rounded-full ${
                dingTalkConnected ? "bg-emerald-500" : "bg-orange-500"
              }`}
            />
            {dingTalkConnected
              ? t("layeredPush.connected", {
                  cls: cls || t("layeredPush.defaultClass"),
                  count: studentCount,
                })
              : t("layeredPush.notConnected")}
          </Badge>
          <Button
            variant="outline"
            size="sm"
            className="text-xs gap-1.5"
            onClick={onReauth}
            title={entryUrl || undefined}
          >
            <RefreshCw className="w-3.5 h-3.5" /> {t("layeredPush.reauthorize")}
          </Button>
        </div>
      </div>

      {/* Quick DingTalk actions */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-muted-foreground mr-1">
          {t("layeredPush.quickActions")}
        </span>
        <Button
          variant="outline"
          size="sm"
          className="text-xs gap-1.5 h-7"
          disabled={syncRoster.isPending}
          onClick={() => syncRoster.mutate({ class_id: classId })}
        >
          <Paperclip className="w-3.5 h-3.5" /> {t("layeredPush.syncHomework")}
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="text-xs gap-1.5 h-7"
          onClick={() => setNoticeOpen(true)}
        >
          <Megaphone className="w-3.5 h-3.5" /> {t("layeredPush.sendNotice")}
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="text-xs gap-1.5 h-7"
          disabled={reportMutation.isPending}
          onClick={() =>
            reportMutation.mutate({
              class_id: classId,
              subject,
              kind: "round",
              recipient: "self",
            })
          }
        >
          <BarChart3 className="w-3.5 h-3.5" />{" "}
          {t("layeredPush.generateReport")}
        </Button>
      </div>

      {/* 发送钉钉通知（notice_only：只发通知，不建任务） */}
      <Dialog open={noticeOpen} onOpenChange={setNoticeOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("layeredPush.noticeDialogTitle")}</DialogTitle>
          </DialogHeader>
          <Textarea
            value={noticeText}
            onChange={(e) => setNoticeText(e.target.value)}
            placeholder={t("layeredPush.noticePlaceholder")}
            rows={4}
            className="text-sm"
          />
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setNoticeOpen(false)}
            >
              {t("common.cancel")}
            </Button>
            <Button
              size="sm"
              disabled={!noticeText.trim() || startPush.isPending}
              onClick={sendNotice}
            >
              {t("common.confirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
