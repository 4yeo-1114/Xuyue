import { useSystemConfig, useUpdateSystemConfig } from "@/hooks/useSystemConfig";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { useLocale } from "@/contexts/LocaleContext";
import { Loader2, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useState } from "react";

const CATEGORY_KEYS: Record<string, string> = {
  ai: "admin.config.category.ai",
  grading: "admin.config.category.grading",
  push: "admin.config.category.push",
  general: "admin.config.category.general",
};

export function AdminConfig() {
  const { data: configs = [], isLoading } = useSystemConfig();
  const updateConfig = useUpdateSystemConfig();
  const { toast } = useToast();
  const { t } = useLocale();
  const [edits, setEdits] = useState<Record<string, string>>({});

  const categories = [...new Set(configs.map((c) => c.category))];

  const handleSave = async (key: string) => {
    const raw = edits[key];
    if (raw === undefined) return;
    try {
      const parsed = JSON.parse(raw);
      await updateConfig.mutateAsync({ key, value: parsed });
      setEdits((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
      toast({
        title: t("admin.config.toast.saved"),
        description: t("admin.config.toast.savedDescription", { key }),
      });
    } catch {
      toast({
        title: t("admin.config.toast.invalidFormat"),
        description: t("admin.config.toast.invalidJson"),
        variant: "destructive",
      });
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-40">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-xl font-bold text-foreground mb-6">{t("admin.config.title")}</h2>
      <div className="space-y-6">
        {categories.map((cat) => (
          <Card key={cat}>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                {CATEGORY_KEYS[cat] ? t(CATEGORY_KEYS[cat]) : cat}
                <Badge variant="outline" className="text-xs">{cat}</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {configs
                .filter((c) => c.category === cat)
                .map((c) => {
                  const displayValue = edits[c.key] ?? JSON.stringify(c.value);
                  const isDirty = edits[c.key] !== undefined;
                  return (
                    <div key={c.id} className="flex items-start gap-4">
                      <div className="flex-1 space-y-1">
                        <Label className="text-sm font-medium">{c.label}</Label>
                        <p className="text-xs text-muted-foreground">{c.description}</p>
                        <Input
                          value={displayValue}
                          onChange={(e) => setEdits((prev) => ({ ...prev, [c.key]: e.target.value }))}
                          className="max-w-xs font-mono text-sm"
                        />
                      </div>
                      <Button
                        size="sm"
                        variant={isDirty ? "default" : "ghost"}
                        disabled={!isDirty || updateConfig.isPending}
                        onClick={() => handleSave(c.key)}
                        className="mt-6"
                      >
                        <Save className="w-3.5 h-3.5 mr-1" /> {t("admin.config.save")}
                      </Button>
                    </div>
                  );
                })}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
