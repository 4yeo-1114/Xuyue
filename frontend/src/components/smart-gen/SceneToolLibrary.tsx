import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Library, Star, ExternalLink } from "lucide-react";
import { SCENE_TOOLS, TOOL_RANKINGS } from "./smartGenData";
import { useLocale } from "@/contexts/LocaleContext";

export function SceneToolLibrary() {
  const { t } = useLocale();

  return (
    <Card className="h-full" data-tour="sg-tool-library">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-1.5">
          <Library className="w-4 h-4 text-primary" />
          {t("smartGen.toolLibrary.title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {SCENE_TOOLS.map((group, gi) => (
          <div key={gi} className="space-y-1.5">
            <p className="text-xs font-medium text-foreground">【{t(`smartGen.toolLibrary.scene.${gi}`)}】</p>
            {group.tools.map((tool, ti) => (
              <div key={ti} className="flex items-center gap-2 p-1.5 rounded-md hover:bg-muted/60 transition-colors cursor-pointer group">
                <span className="text-sm">{tool.icon}</span>
                <span className="text-[11px] font-medium text-foreground">{t(`smartGen.toolLibrary.scene.${gi}.tool.${ti}.name`)}</span>
                <span className="text-[10px] text-muted-foreground">- {t(`smartGen.toolLibrary.scene.${gi}.tool.${ti}.desc`)}</span>
                <ExternalLink className="w-3 h-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity ml-auto shrink-0" />
              </div>
            ))}
          </div>
        ))}

        <div className="flex gap-2 pt-2 border-t border-border">
          <Button variant="outline" size="sm" className="text-[10px] h-6 flex-1">{t("smartGen.toolLibrary.viewAll")}</Button>
          <Button variant="outline" size="sm" className="text-[10px] h-6 flex-1">{t("smartGen.toolLibrary.applyAccess")}</Button>
          <Button variant="outline" size="sm" className="text-[10px] h-6 flex-1">{t("smartGen.toolLibrary.submitFeedback")}</Button>
        </div>

        {/* Rankings */}
        <div className="p-2.5 rounded-lg bg-muted/50 border border-border space-y-1.5" data-tour="sg-rankings">
          <p className="text-xs font-medium text-foreground">{t("smartGen.toolLibrary.rankings")}</p>
          {TOOL_RANKINGS.map((r, i) => (
            <div key={i} className="flex items-center gap-2 text-[10px]">
              <span className="font-medium text-foreground">{i + 1}. {t(`smartGen.toolLibrary.rank.${i}.name`)}</span>
              <span className="text-muted-foreground">{t("smartGen.toolLibrary.usage", { usage: r.usage })}</span>
              <span className="ml-auto">
                {Array.from({ length: 5 }, (_, j) => (
                  <Star key={j} className={`w-2.5 h-2.5 inline ${j < r.rating ? "text-primary fill-primary" : "text-muted-foreground/30"}`} />
                ))}
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
