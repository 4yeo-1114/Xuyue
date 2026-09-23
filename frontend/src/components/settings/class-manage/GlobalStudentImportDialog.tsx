import { useState, useRef } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Upload, FileSpreadsheet, Loader2 } from "lucide-react";
import { useGlobalImportStudents } from "@/hooks/useImportStudents";
import { useLocale } from "@/contexts/LocaleContext";

interface GlobalStudentImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function GlobalStudentImportDialog({ open, onOpenChange }: GlobalStudentImportDialogProps) {
  const { t } = useLocale();
  const [file, setFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const importMutation = useGlobalImportStudents();

  const reset = () => {
    setFile(null);
  };

  const handleImport = async () => {
    if (!file) return;
    try {
      await importMutation.mutateAsync({ file });
      onOpenChange(false);
      reset();
    } catch (e) {
      // Error handled by hook
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) reset(); }}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("settingsClass.import.title")}</DialogTitle>
        </DialogHeader>

        {!file ? (
          <div className="py-8">
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.xls"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) setFile(f);
                e.target.value = "";
              }}
            />
            <div
              onClick={() => fileRef.current?.click()}
              className="border-2 border-dashed border-muted-foreground/30 rounded-xl p-8 text-center cursor-pointer hover:border-primary/50 hover:bg-primary/5 transition-colors"
            >
              <Upload className="w-10 h-10 mx-auto mb-3 text-muted-foreground" />
              <p className="font-medium mb-1">{t("settingsClass.import.uploadHint")}</p>
              <p className="text-sm text-muted-foreground">
                {t("settingsClass.import.formatHint")}
              </p>
            </div>
            <div className="mt-4 p-3 rounded-lg bg-muted/50 text-sm text-muted-foreground">
              <p className="font-medium mb-1">{t("settingsClass.import.headerHint")}</p>
              <ul className="list-disc list-inside space-y-1 text-xs">
                <li>{t("settingsClass.import.header1")}</li>
                <li>{t("settingsClass.import.header2")}</li>
                <li>{t("settingsClass.import.header3")}</li>
              </ul>
            </div>
          </div>
        ) : (
          <div className="py-8 space-y-4">
            <div className="flex items-center gap-3 p-4 bg-primary/5 rounded-lg border border-primary/20">
              <FileSpreadsheet className="w-8 h-8 text-primary" />
              <div className="flex-1 overflow-hidden">
                <p className="font-medium truncate">{file.name}</p>
                <p className="text-xs text-muted-foreground">{(file.size / 1024).toFixed(1)} KB</p>
              </div>
              <Button variant="ghost" size="sm" onClick={reset}>{t("settingsClass.import.change")}</Button>
            </div>
            <div className="text-sm text-muted-foreground bg-muted/50 p-3 rounded-lg">
              <p className="font-medium mb-1 italic">{t("settingsClass.import.tipTitle")}</p>
              <ul className="list-disc list-inside space-y-1 text-xs">
                <li>{t("settingsClass.import.tip1")}</li>
                <li>{t("settingsClass.import.tip2")}</li>
                <li>{t("settingsClass.import.tip3")}</li>
              </ul>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={importMutation.isPending}
          >
            {t("common.cancel")}
          </Button>
          <Button
            onClick={handleImport}
            disabled={!file || importMutation.isPending}
            className="gap-2"
          >
            {importMutation.isPending ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> {t("settingsClass.import.importing")}</>
            ) : (
              t("settingsClass.import.start")
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
