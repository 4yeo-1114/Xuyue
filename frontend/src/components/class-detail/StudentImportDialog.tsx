import { useState, useRef } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Upload, FileSpreadsheet, CheckCircle2, Loader2 } from "lucide-react";
import { useImportStudents } from "@/hooks/useImportStudents";

interface StudentImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  classId: string;
  className: string;
}

export function StudentImportDialog({
  open,
  onOpenChange,
  classId,
  className,
}: StudentImportDialogProps) {
  const { t, locale } = useLocale();

  const [file, setFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const importMutation = useImportStudents();

  const reset = () => {
    setFile(null);
  };

  const handleImport = async () => {
    if (!file) return;
    try {
      await importMutation.mutateAsync({ classId, file });
      onOpenChange(false);
      reset();
    } catch (e) {
      // 错误已由 Hook 处理
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v);
        if (!v) reset();
      }}
    >
      <DialogContent className="sm:max-w-[480px] max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {t("classDetail.batchImportTitle", { className })}
          </DialogTitle>
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
              role="button"
              tabIndex={0}
              aria-label={t("classDetail.clickUploadExcel")}
              onClick={() => fileRef.current?.click()}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  fileRef.current?.click();
                }
              }}
              className="border-2 border-dashed border-muted-foreground/30 rounded-xl p-8 text-center cursor-pointer hover:border-primary/50 hover:bg-primary/5 transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
            >
              <Upload className="w-10 h-10 mx-auto mb-3 text-muted-foreground" />
              <p className="font-medium mb-1">
                {t("classDetail.clickUploadExcel")}
              </p>
              <p className="text-sm text-muted-foreground">
                {t("classDetail.excelFormatHint")}
              </p>
            </div>
            <div className="mt-4 p-3 rounded-lg bg-muted/50 text-sm text-muted-foreground">
              <p className="font-medium mb-1">
                {t("classDetail.autoDetectHeader")}
              </p>
              <ul className="list-disc list-inside space-y-1 text-xs">
                <li>{t("classDetail.importFields1")}</li>
                <li>{t("classDetail.importFields2")}</li>
              </ul>
            </div>
          </div>
        ) : (
          <div className="py-8 space-y-4">
            <div className="flex items-center gap-3 p-4 bg-primary/5 rounded-lg border border-primary/20">
              <FileSpreadsheet className="w-8 h-8 text-primary" />
              <div className="flex-1 overflow-hidden">
                <p className="font-medium truncate">{file.name}</p>
                <p className="text-xs text-muted-foreground">
                  {(file.size / 1024).toFixed(1)} KB
                </p>
              </div>
              <Button variant="ghost" size="sm" onClick={reset}>
                {t("classDetail.changeFile")}
              </Button>
            </div>
            <div className="text-sm text-muted-foreground bg-muted/50 p-3 rounded-lg">
              <p className="font-medium mb-1 italic">
                {t("classDetail.tipLabel")}
              </p>
              <ul className="list-disc list-inside space-y-1 text-xs">
                <li>{t("classDetail.nameRequiredHint")}</li>
                <li>{t("classDetail.studentIdMissingHint")}</li>
                <li>{t("classDetail.ignoreColumnsHint")}</li>
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
              <>
                <Loader2 className="w-4 h-4 animate-spin" />{" "}
                {t("classDetail.importing")}
              </>
            ) : (
              t("classDetail.开始导入")
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
