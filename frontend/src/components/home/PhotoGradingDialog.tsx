import { useState, useRef, useEffect, useCallback } from "react";
import { Camera, Trash2, Upload, Loader2, ImageIcon } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useIsMobile } from "@/hooks/use-mobile";
import { homeQuickGrade } from "@/services/gradingApi";
import { toast } from "sonner";
import { useLocale } from "@/contexts/LocaleContext";

interface PhotoGradingDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedSubject: string;
  selectedClass: string;
  selectedSchoolLevel?: string;
  selectedGrade?: string;
}

interface ImageFile {
  file: File;
  preview: string;
}

export function PhotoGradingDialog({
  open,
  onOpenChange,
  selectedSubject,
  selectedClass,
  selectedSchoolLevel = "初中",
  selectedGrade = "初一",
}: PhotoGradingDialogProps) {
  const { t, locale } = useLocale();
  const isMobile = useIsMobile();
  const [images, setImages] = useState<ImageFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [anonymous, setAnonymous] = useState(false);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Mobile: auto-trigger camera on open
  const cameraTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (open && isMobile && images.length === 0) {
      cameraTimerRef.current = setTimeout(
        () => cameraInputRef.current?.click(),
        300,
      );
    }
    return () => {
      if (cameraTimerRef.current) {
        clearTimeout(cameraTimerRef.current);
        cameraTimerRef.current = null;
      }
    };
  }, [open, isMobile]);

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files) return;
      const newImages: ImageFile[] = Array.from(files)
        .slice(0, 1)
        .map((file) => ({
          file,
          preview: URL.createObjectURL(file),
        }));
      setImages((prev) => {
        prev.forEach((img) => URL.revokeObjectURL(img.preview));
        return newImages;
      });
      e.target.value = "";
    },
    [],
  );

  const removeImage = useCallback((index: number) => {
    setImages((prev) => {
      URL.revokeObjectURL(prev[index].preview);
      return prev.filter((_, i) => i !== index);
    });
  }, []);

  const handleClose = useCallback(() => {
    images.forEach((img) => URL.revokeObjectURL(img.preview));
    setImages([]);
    onOpenChange(false);
  }, [images, onOpenChange]);

  const handleSubmit = async () => {
    if (images.length === 0) return;
    setUploading(true);

    try {
      await homeQuickGrade(images[0].file, anonymous);
      toast.success(t("home.photo.started"), {
        description: t("home.photo.startedDesc"),
        duration: 5000,
      });
      try {
        window.dispatchEvent(new Event("home-grading-updated"));
      } catch {
        //
      }
      handleClose();
    } catch (err: any) {
      toast.error(
        t("home.photo.failed", {
          message: err.message || t("home.photo.retry"),
        }),
      );
    } finally {
      setUploading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-lg max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Camera className="w-5 h-5 text-primary" />
            {isMobile
              ? t("home.photo.titleMobile")
              : t("home.photo.titleDesktop")}
          </DialogTitle>
          <DialogDescription>
            {isMobile
              ? t("home.photo.descMobile")
              : t("home.photo.descDesktop")}
          </DialogDescription>
        </DialogHeader>

        <input
          ref={cameraInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          onChange={handleFileSelect}
          className="hidden"
        />
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          onChange={handleFileSelect}
          className="hidden"
        />

        <div className="flex-1 overflow-auto">
          {images.length === 0 ? (
            <button
              type="button"
              onClick={() =>
                (isMobile ? cameraInputRef : fileInputRef).current?.click()
              }
              className="w-full border-2 border-dashed border-border rounded-xl p-10 flex flex-col items-center gap-3 hover:border-primary/40 hover:bg-primary/5 transition-colors cursor-pointer"
            >
              {isMobile ? (
                <Camera className="w-10 h-10 text-muted-foreground" />
              ) : (
                <Upload className="w-10 h-10 text-muted-foreground" />
              )}
              <span className="text-sm text-muted-foreground font-medium">
                {isMobile
                  ? t("home.photo.tapToCapture")
                  : t("home.photo.tapToSelect")}
              </span>
              <span className="text-xs text-muted-foreground/60">
                {t("home.photo.formatHint")}
              </span>
            </button>
          ) : (
            <div className="space-y-3">
              <div className="relative group rounded-xl overflow-hidden border border-border aspect-[4/5] bg-muted/20">
                <img
                  src={images[0].preview}
                  alt={t("home.photo.altHomework")}
                  className="w-full h-full object-contain bg-background"
                />
                <button
                  type="button"
                  onClick={() => removeImage(0)}
                  className="absolute top-2 right-2 w-7 h-7 rounded-full bg-destructive text-destructive-foreground flex items-center justify-center opacity-90 hover:opacity-100 transition-opacity"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground">
                  {t("home.photo.selectedCount")}
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    (isMobile ? cameraInputRef : fileInputRef).current?.click()
                  }
                  className="h-8 text-sm"
                >
                  {t("home.photo.reselect")}
                </Button>
              </div>
            </div>
          )}
        </div>

        {images.length > 0 && (
          <div className="space-y-3 mt-2">
            <div className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5">
              <div className="space-y-0.5">
                <p className="text-sm font-medium">{t("grading.anonymous")}</p>
                <p className="text-xs text-muted-foreground">
                  {t("grading.anonymousHint")}
                </p>
              </div>
              <Switch checked={anonymous} onCheckedChange={setAnonymous} />
            </div>
            <Button
              onClick={handleSubmit}
              disabled={uploading}
              className="w-full"
              size="lg"
            >
              {uploading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  {t("home.photo.starting")}
                </>
              ) : (
                <>
                  <ImageIcon className="w-4 h-4 mr-2" />
                  {t("home.photo.startGrading")}
                </>
              )}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
