import { Button } from "@/components/ui/button";
import { useLocale } from "@/contexts/LocaleContext";
import { useToast } from "@/hooks/use-toast";
import { Smartphone, Eye } from "lucide-react";

export function DingTalkPreview() {
  const { t } = useLocale();
  const { toast } = useToast();

  const demoToast = () => {
    toast({
      title: t("layeredPush.demoTitle"),
      description: t("layeredPush.demoDesc"),
    });
  };

  return (
    <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <Smartphone className="w-4 h-4 text-primary" />
        <span className="text-sm font-bold text-foreground">
          {t("layeredPush.syncPreviewTitle")}
        </span>
      </div>

      {/* Student view */}
      <div className="rounded-lg bg-background border border-border/50 p-3">
        <div className="flex items-center gap-1.5 mb-2">
          <span className="text-sm">📱</span>
          <span className="text-xs font-semibold text-foreground">
            {t("layeredPush.studentReceives")}
          </span>
        </div>
        <div className="space-y-1 text-[11px] text-muted-foreground">
          <p>{t("layeredPush.studentMsg1")}</p>
          <p>{t("layeredPush.studentMsg2")}</p>
          <p>{t("layeredPush.studentMsg3")}</p>
        </div>
      </div>

      {/* Parent view */}
      <div className="rounded-lg bg-background border border-border/50 p-3">
        <div className="flex items-center gap-1.5 mb-2">
          <span className="text-sm">📱</span>
          <span className="text-xs font-semibold text-foreground">
            {t("layeredPush.parentReceives")}
          </span>
        </div>
        <div className="space-y-1 text-[11px] text-muted-foreground">
          <p>{t("layeredPush.parentMsg1")}</p>
          <p>{t("layeredPush.parentMsg2")}</p>
          <p>{t("layeredPush.parentMsg3")}</p>
        </div>
      </div>

      {/* Form type */}
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
            />{" "}
            {t("layeredPush.formDingTalk")}
          </label>
          <label className="flex items-center gap-2 text-xs text-foreground font-medium cursor-pointer">
            <input
              type="radio"
              name="form"
              className="accent-primary w-3 h-3"
              defaultChecked
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
        onClick={demoToast}
      >
        <Eye className="w-3.5 h-3.5" /> {t("layeredPush.previewEffect")}
      </Button>
    </div>
  );
}
