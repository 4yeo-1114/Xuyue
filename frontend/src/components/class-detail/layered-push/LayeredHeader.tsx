import { Badge } from "@/components/ui/badge";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import {
  Layers,
  RefreshCw,
  Paperclip,
  Megaphone,
  BarChart3,
} from "lucide-react";

interface LayeredHeaderProps {
  subject: string;
  className?: string;
  dingTalkConnected: boolean;
}

export function LayeredHeader({
  subject,
  className: cls,
  dingTalkConnected,
}: LayeredHeaderProps) {
  const { t } = useLocale();
  const { toast } = useToast();

  const demoToast = () => {
    toast({
      title: t("layeredPush.demoTitle"),
      description: t("layeredPush.demoDesc"),
    });
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
                })
              : t("layeredPush.notConnected")}
          </Badge>
          <Button
            variant="outline"
            size="sm"
            className="text-xs gap-1.5"
            onClick={demoToast}
          >
            <RefreshCw className="w-3.5 h-3.5" /> {t("layeredPush.reauthorize")}
          </Button>
        </div>
      </div>

      {/* Quick DingTalk actions */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground mr-1">
          {t("layeredPush.quickActions")}
        </span>
        <Button
          variant="outline"
          size="sm"
          className="text-xs gap-1.5 h-7"
          onClick={demoToast}
        >
          <Paperclip className="w-3.5 h-3.5" /> {t("layeredPush.syncHomework")}
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="text-xs gap-1.5 h-7"
          onClick={demoToast}
        >
          <Megaphone className="w-3.5 h-3.5" /> {t("layeredPush.sendNotice")}
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="text-xs gap-1.5 h-7"
          onClick={demoToast}
        >
          <BarChart3 className="w-3.5 h-3.5" />{" "}
          {t("layeredPush.generateReport")}
        </Button>
      </div>
    </div>
  );
}
