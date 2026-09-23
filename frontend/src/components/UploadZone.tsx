import { useState, useCallback, useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { Upload, FileImage, FileText, X, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { getSubjectByName } from "@/components/SubjectTabs";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSubjectName } from "@/i18n/index";

interface UploadZoneProps {
  onFilesSelected?: (files: File[]) => void;
  onStartGrading?: (files: File[]) => void;
  selectedSubject?: string;
  className?: string;
}

export function UploadZone({
  onFilesSelected,
  onStartGrading,
  selectedSubject = "语文",
  className,
}: UploadZoneProps) {
  const { t, locale } = useLocale();
  const [isDragOver, setIsDragOver] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  const subject = getSubjectByName(selectedSubject);
  const subjectLabel = translateSubjectName(locale, selectedSubject);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      const droppedFiles = Array.from(e.dataTransfer.files);
      setFiles((prev) => [...prev, ...droppedFiles]);
      onFilesSelected?.(droppedFiles);
    },
    [onFilesSelected],
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selectedFiles = Array.from(e.target.files || []);
      setFiles((prev) => [...prev, ...selectedFiles]);
      onFilesSelected?.(selectedFiles);
    },
    [onFilesSelected],
  );

  const removeFile = useCallback((index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const clearFiles = useCallback(() => {
    setFiles([]);
  }, []);

  const filesRef = useRef<File[]>([]);
  useEffect(() => {
    filesRef.current = files;
  }, [files]);

  const onStartGradingRef = useRef(onStartGrading);
  useEffect(() => {
    onStartGradingRef.current = onStartGrading;
  }, [onStartGrading]);

  const handleStartGrading = useCallback(() => {
    if (files.length === 0) return;

    setIsUploading(true);
    setUploadProgress(0);
  }, [files.length]);

  // 模拟上传进度：组件卸载 / isUploading 变化时清理定时器，避免泄漏
  useEffect(() => {
    if (!isUploading) return;
    let tick = 0;
    const interval = window.setInterval(() => {
      tick += 1;
      const next = Math.min(tick * 10, 100);
      setUploadProgress(next);
      if (next >= 100) {
        window.clearInterval(interval);
        setIsUploading(false);
        onStartGradingRef.current?.(filesRef.current);
      }
    }, 200);
    return () => window.clearInterval(interval);
  }, [isUploading]);

  const getFileIcon = (file: File) => {
    if (file.type.startsWith("image/")) return FileImage;
    return FileText;
  };

  return (
    <div className={cn("space-y-4", className)}>
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "px-3 py-1 rounded-full text-sm font-medium text-white",
            subject?.bgColor || "bg-primary",
          )}
        >
          {subjectLabel}
        </span>
        <span className="text-sm text-muted-foreground">
          {t("grading.uploadZone.hint")}
        </span>
      </div>

      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          "relative border-2 border-dashed rounded-xl p-8 text-center transition-all duration-300",
          isDragOver
            ? cn(
                "scale-[1.02]",
                subject?.borderColor || "border-primary",
                "bg-primary/5",
              )
            : "border-border hover:border-primary/50 hover:bg-muted/50",
        )}
      >
        <input
          type="file"
          multiple
          accept="image/*,.pdf,.doc,.docx"
          onChange={handleFileInput}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
        />

        <div className="flex flex-col items-center gap-3">
          <div
            className={cn(
              "p-4 rounded-full transition-colors duration-300",
              isDragOver
                ? cn(subject?.bgColor || "bg-primary", "text-white")
                : "bg-muted text-muted-foreground",
            )}
          >
            <Upload className="w-8 h-8" />
          </div>
          <div>
            <p className="text-foreground font-medium">
              {t("grading.uploadZone.dropHint")}
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              {t("grading.uploadZone.formats")}
            </p>
          </div>
        </div>
      </div>

      {isUploading && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">
              {t("grading.uploadZone.processing")}
            </span>
            <span className="font-medium">{uploadProgress}%</span>
          </div>
          <Progress value={uploadProgress} className="h-2" />
        </div>
      )}

      {files.length > 0 && !isUploading && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-foreground">
              {t("grading.uploadZone.selectedCount", { count: files.length })}
            </p>
            <Button
              variant="ghost"
              size="sm"
              onClick={clearFiles}
              className="text-muted-foreground hover:text-destructive"
            >
              {t("grading.uploadZone.clearAll")}
            </Button>
          </div>

          <div className="space-y-2 max-h-40 overflow-y-auto">
            {files.map((file, index) => {
              const FileIcon = getFileIcon(file);
              return (
                <div
                  key={index}
                  className="flex items-center gap-3 p-3 rounded-lg bg-muted/50 group"
                >
                  <FileIcon
                    className={cn("w-5 h-5", subject?.color || "text-primary")}
                  />
                  <span className="flex-1 text-sm text-foreground truncate">
                    {file.name}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {(file.size / 1024).toFixed(1)} KB
                  </span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="w-6 h-6 opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={() => removeFile(index)}
                  >
                    <X className="w-4 h-4" />
                  </Button>
                </div>
              );
            })}
          </div>

          <Button
            onClick={handleStartGrading}
            className={cn(
              "w-full gap-2 text-white",
              subject?.bgColor || "bg-primary",
            )}
            size="lg"
          >
            <Sparkles className="w-5 h-5" />
            {t("grading.uploadZone.startSmartGrade")}
          </Button>
        </div>
      )}
    </div>
  );
}
