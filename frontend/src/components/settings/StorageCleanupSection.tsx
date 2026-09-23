import { useState } from "react";
import { Trash2, Loader2, HardDriveDownload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { cleanupGradingData } from "@/services/api";
import { toast } from "sonner";
import { useLocale } from "@/contexts/LocaleContext";

const DETAIL_KEYS = [
  "temp",
  "project_temp",
  "scan",
  "modify_orphans",
  "home_img_orphans",
  "ai_diagnosis",
  "history_legacy",
] as const;

function formatBytes(bytes: number): string {
  const size = Math.max(0, bytes);
  if (size < 1024) return `${size} B`;
  if (size < 1024 ** 2) return `${(size / 1024).toFixed(1)} KB`;
  if (size < 1024 ** 3) return `${(size / 1024 ** 2).toFixed(1)} MB`;
  return `${(size / 1024 ** 3).toFixed(2)} GB`;
}

export function StorageCleanupSection() {
  const { t } = useLocale();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [lastResult, setLastResult] = useState<{ bytes: number; files: number } | null>(null);

  const detailLabel = (key: string) => {
    const known = DETAIL_KEYS.find((k) => k === key);
    if (known) return t(`settings.storage.detail.${known}`);
    return key;
  };

  const handleCleanup = async () => {
    setLoading(true);
    try {
      const res = await cleanupGradingData();
      setLastResult({ bytes: res.freed_bytes, files: res.deleted_files });
      const detailLines = Object.entries(res.details || {})
        .filter(([, stat]) => (stat?.files || 0) > 0)
        .map(([key, stat]) =>
          t("settings.storage.detail.line", {
            label: detailLabel(key),
            files: stat.files,
            size: formatBytes(stat.bytes),
          })
        )
        .join("\n");
      toast.success(t("settings.storage.toast.freed", { size: res.freed_bytes_human }), {
        description:
          res.deleted_files > 0
            ? `${t("settings.storage.toast.deleted", { count: res.deleted_files })}${detailLines ? `\n${detailLines}` : ""}`
            : t("settings.storage.toast.noJunk"),
      });
      setConfirmOpen(false);
    } catch (e: any) {
      toast.error(t("settings.storage.toast.failed"), {
        description: e?.message || t("settings.storage.toast.retry"),
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <HardDriveDownload className="w-4 h-4 text-primary" />
            {t("settings.storage.title")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground leading-relaxed">{t("settings.storage.description")}</p>
          {lastResult && (
            <p className="text-xs text-emerald-600">
              {t("settings.storage.lastCleanup", {
                size: formatBytes(lastResult.bytes),
                count: lastResult.files,
              })}
            </p>
          )}
          <div className="flex justify-end">
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => setConfirmOpen(true)}
              disabled={loading}
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              {t("settings.storage.startCleanup")}
            </Button>
          </div>
        </CardContent>
      </Card>

      <AlertDialog open={confirmOpen} onOpenChange={(open) => !loading && setConfirmOpen(open)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("settings.storage.confirmTitle")}</AlertDialogTitle>
            <AlertDialogDescription className="space-y-2 text-left">
              <span className="block">{t("settings.storage.confirmWillClean")}</span>
              <span className="block text-xs text-muted-foreground">{t("settings.storage.confirmItems")}</span>
              <span className="block text-xs font-medium text-foreground">{t("settings.storage.confirmWillKeep")}</span>
              <span className="block text-xs text-muted-foreground">{t("settings.storage.confirmHint")}</span>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={loading}>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              disabled={loading}
              onClick={(e) => {
                e.preventDefault();
                void handleCleanup();
              }}
            >
              {loading ? t("settings.storage.cleaning") : t("settings.storage.startCleanup")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
