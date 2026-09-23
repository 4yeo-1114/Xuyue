import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RefreshCw, Plus, Loader2, CheckCircle2 } from "lucide-react";
import { TOOL_PREVIEWS } from "./smartGenData";
import { useLocale } from "@/contexts/LocaleContext";

export function ToolPreviewPanel() {
  const { t } = useLocale();

  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">{t("smartGen.toolPreview.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {TOOL_PREVIEWS.map((tp, ti) => (
          <div key={tp.idx} className="p-3 rounded-lg border border-border space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-lg">{tp.icon}</span>
              <span className="text-xs font-semibold text-foreground">【{tp.idx}/{tp.total}】{t(`smartGen.toolPreview.item.${ti}.tool`)}</span>
              {tp.status === "done" ? (
                <Badge variant="default" className="text-[9px] gap-0.5"><CheckCircle2 className="w-2.5 h-2.5" />{t("smartGen.toolPreview.statusDone")}</Badge>
              ) : (
                <Badge variant="secondary" className="text-[9px] gap-0.5"><Loader2 className="w-2.5 h-2.5 animate-spin" />{t("smartGen.toolPreview.statusGenerating")}</Badge>
              )}
            </div>
            <p className="text-[11px] text-muted-foreground pl-7">
              {tp.status === "done" ? "✅" : "⏳"} {t(`smartGen.toolPreview.item.${ti}.summary`)}
            </p>
            {tp.details.map((d, i) => (
              <p key={i} className="text-[10px] text-muted-foreground pl-7">{t(`smartGen.toolPreview.item.${ti}.detail.${i}`)}</p>
            ))}
            <div className="flex gap-1.5 pl-7 flex-wrap">
              {tp.actions.map((a, i) => (
                <Button key={i} variant="outline" size="sm" className="text-[10px] h-5 px-2">{t(`smartGen.toolPreview.item.${ti}.action.${i}`)}</Button>
              ))}
            </div>
          </div>
        ))}

        <div className="flex gap-2 pt-1 border-t border-border">
          <Button variant="outline" size="sm" className="text-[10px] h-6 gap-1 flex-1">
            <RefreshCw className="w-3 h-3" />{t("smartGen.toolPreview.regenerate")}
          </Button>
          <Button variant="outline" size="sm" className="text-[10px] h-6 gap-1 flex-1">
            <Plus className="w-3 h-3" />{t("smartGen.toolPreview.addMore")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
