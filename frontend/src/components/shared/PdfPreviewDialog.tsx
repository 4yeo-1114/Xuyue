import { Download } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useLocale } from "@/contexts/LocaleContext";

interface PdfPreviewDialogProps {
  open: boolean;
  onClose: () => void;
  blobUrl: string;
  filename: string;
}

export function PdfPreviewDialog({
  open,
  onClose,
  blobUrl,
  filename,
}: PdfPreviewDialogProps) {
  const { t } = useLocale();

  // 防闪错：blobUrl 为空时直接不渲染，避免空 iframe 闪一下
  if (!blobUrl) return null;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>{t("common.pdfPreviewTitle")}</DialogTitle>
        </DialogHeader>
        <iframe
          src={blobUrl}
          title={t("common.pdfPreviewTitle")}
          className="w-full h-[70vh] rounded-md border border-border"
        />
        <DialogFooter className="sm:justify-between">
          <Button asChild variant="outline" className="gap-2">
            <a href={blobUrl} download={filename}>
              <Download className="h-4 w-4" />
              {t("common.downloadPdf")}
            </a>
          </Button>
          <Button onClick={onClose}>{t("common.close")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
