import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Clock, Loader2 } from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";
import { toast } from "sonner";
import {
  listAiGenerationHistory,
  getAiGenerationHistory,
  AiGenerationHistoryItem,
} from "@/services/api";

interface Props {
  /** 生成完成后自增，触发列表重新拉取 */
  refreshSignal: number;
  onLoad: (item: AiGenerationHistoryItem) => void;
}

function formatTime(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}`;
}

export function GenerationHistory({ refreshSignal, onLoad }: Props) {
  const { t } = useLocale();
  const [loadingId, setLoadingId] = useState<string | null>(null);

  const { data: items = [], isLoading, isError } = useQuery({
    queryKey: ["ai-generation-history", refreshSignal],
    queryFn: listAiGenerationHistory,
  });

  const genTypeLabel = (gt: string) => t(`smartGen.genType.${gt}`, undefined, gt);

  const handleClick = async (id: string) => {
    setLoadingId(id);
    try {
      const detail = await getAiGenerationHistory(id);
      onLoad(detail);
      toast.success(t("smartGen.history.loaded"));
    } catch (e: any) {
      toast.error(t("smartGen.history.loadFailed"), { description: e?.message });
    } finally {
      setLoadingId(null);
    }
  };

  return (
    <Card className="h-full" data-tour="sg-history">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-1.5">
          <Clock className="w-4 h-4 text-primary" />
          {t("smartGen.history.title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          <div className="flex items-center gap-2 text-xs text-muted-foreground py-4">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            {t("smartGen.history.loading")}
          </div>
        ) : isError ? (
          <p className="text-xs text-muted-foreground">
            {t("smartGen.history.loadFailed")}
          </p>
        ) : items.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            {t("smartGen.history.empty")}
          </p>
        ) : (
          <div className="max-h-[480px] overflow-y-auto space-y-1.5 pr-1">
            {items.map((item) => (
              <button
                key={item.id}
                type="button"
                disabled={loadingId === item.id}
                onClick={() => handleClick(item.id)}
                className="w-full text-left rounded-lg border border-border p-2.5 hover:bg-muted/60 transition-colors disabled:opacity-60"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-foreground truncate flex-1">
                    {item.title || t("smartGen.aiIntegration.unnamed")}
                  </span>
                  <Badge variant="secondary" className="text-[9px] shrink-0">
                    {genTypeLabel(item.gen_type)}
                  </Badge>
                </div>
                <div className="flex items-center gap-2 mt-1 text-[10px] text-muted-foreground">
                  <span className="truncate">
                    {item.subject || "—"}
                    {item.grade ? ` · ${item.grade}` : ""}
                  </span>
                  <span className="ml-auto shrink-0">
                    {formatTime(item.created_at)}
                  </span>
                </div>
                {loadingId === item.id && (
                  <div className="flex items-center gap-1 mt-1 text-[10px] text-primary">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    {t("smartGen.history.loading")}
                  </div>
                )}
              </button>
            ))}
          </div>
        )}

        <p className="text-[10px] text-muted-foreground border-t border-border pt-2">
          {t("smartGen.history.clickToLoad")}
        </p>
      </CardContent>
    </Card>
  );
}
