import { useFeatureFlags } from "@/hooks/useFeatureFlags";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateFeatureFlag } from "@/services/api";
import { Card, CardContent } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { useLocale } from "@/contexts/LocaleContext";
import { Loader2 } from "lucide-react";

export function AdminFeatures() {
  const { data: flags = [], isLoading } = useFeatureFlags();
  const qc = useQueryClient();
  const { toast } = useToast();
  const { t } = useLocale();

  const toggleFlag = useMutation({
    mutationFn: ({ key, enabled }: { key: string; enabled: boolean }) =>
      updateFeatureFlag(key, enabled),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["feature-flags"] });
      toast({ title: t("admin.features.toast.updated") });
    },
    onError: (err: any) => {
      toast({ title: t("admin.common.actionFailed"), description: err.message, variant: "destructive" });
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-40">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-xl font-bold text-foreground mb-4">{t("admin.features.title")}</h2>
      <p className="text-sm text-muted-foreground mb-6">{t("admin.features.description")}</p>

      <Card>
        <CardContent className="p-0 divide-y divide-border">
          {flags.map((flag) => (
            <div key={flag.key} className="flex items-center justify-between px-5 py-4">
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium text-foreground">{flag.label}</span>
                <Badge variant="outline" className="text-xs font-mono">{flag.key}</Badge>
              </div>
              <Switch
                checked={flag.enabled}
                onCheckedChange={(checked) => toggleFlag.mutate({ key: flag.key, enabled: checked })}
              />
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
