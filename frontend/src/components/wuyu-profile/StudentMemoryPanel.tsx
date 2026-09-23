import { useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import { toast } from "sonner";
import { Images, Trash2, Loader2, ImagePlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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
import {
  listMemories,
  uploadMemory,
  deleteMemory,
  resolveMemoryUrl,
  type MemoryItem,
} from "@/services/wuyuApi";
import { formatDateTime } from "./portfolioShared";

interface StudentMemoryPanelProps {
  studentId: string;
}

/**
 * 学生成长印记（动态相册）— 教师上传的学生成长照片。
 * 图片网格 + 上传（含可选说明）+ 删除确认 + 空状态。仅本班教师及以上可上传/删除。
 */
export function StudentMemoryPanel({ studentId }: StudentMemoryPanelProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [caption, setCaption] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<MemoryItem | null>(null);

  const {
    data: memories = [],
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["wuyu-memories", studentId],
    queryFn: () => listMemories(studentId),
    enabled: !!studentId,
  });

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ["wuyu-memories", studentId] });
  };

  const uploadMut = useMutation({
    mutationFn: (file: File) =>
      uploadMemory(studentId, file, caption.trim() || undefined),
    onSuccess: () => {
      toast.success(t("wuyu.memory.uploadSuccess"));
      setCaption("");
      invalidateAll();
    },
    onError: (err: any) => {
      toast.error(t("wuyu.memory.uploadFailed"), { description: err?.message });
    },
  });

  const deleteMut = useMutation({
    mutationFn: (m: MemoryItem) => deleteMemory(studentId, m.id),
    onSuccess: () => {
      toast.success(t("wuyu.memory.deleteSuccess"));
      setDeleteTarget(null);
      invalidateAll();
    },
    onError: (err: any) => {
      toast.error(t("wuyu.memory.deleteFailed"), { description: err?.message });
      setDeleteTarget(null);
    },
  });

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) uploadMut.mutate(file);
    e.target.value = "";
  };

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Images className="w-4 h-4 text-primary" />
            <CardTitle className="text-sm font-semibold">
              {t("wuyu.memory.title")}
            </CardTitle>
          </div>
          <CardDescription>{t("wuyu.memory.subtitle")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* 上传区 */}
          <div className="flex flex-wrap items-center gap-2">
            <Input
              className="h-9 w-full sm:w-72 text-sm"
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              placeholder={t("wuyu.memory.captionPlaceholder")}
              disabled={uploadMut.isPending}
            />
            <Button
              size="sm"
              disabled={uploadMut.isPending}
              onClick={() => fileInputRef.current?.click()}
            >
              {uploadMut.isPending ? (
                <Loader2 className="w-4 h-4 mr-1 animate-spin" />
              ) : (
                <ImagePlus className="w-4 h-4 mr-1" />
              )}
              {t(
                uploadMut.isPending
                  ? "wuyu.memory.uploading"
                  : "wuyu.memory.upload",
              )}
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleFileChange}
            />
          </div>

          {/* 图片网格 */}
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Loader2 className="w-6 h-6 animate-spin mb-2" />
              <p className="text-sm">{t("wuyu.loading")}</p>
            </div>
          ) : isError ? (
            <div className="flex flex-col items-center justify-center py-12 border border-dashed rounded-lg text-muted-foreground">
              <p className="text-sm mb-2">{t("wuyu.loadFailed")}</p>
              <Button size="sm" variant="outline" onClick={() => refetch()}>
                {t("wuyu.retry")}
              </Button>
            </div>
          ) : memories.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 border border-dashed rounded-lg text-muted-foreground">
              <Images className="w-8 h-8 opacity-30 mb-2" />
              <p className="text-sm">{t("wuyu.memory.empty")}</p>
              <p className="text-xs mt-1">{t("wuyu.memory.emptyHint")}</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
              {memories.map((m) => (
                <div
                  key={m.id}
                  className="group relative rounded-lg border border-border/50 overflow-hidden bg-muted/20"
                >
                  <img
                    src={resolveMemoryUrl(m.thumb_url || m.download_url)}
                    alt={m.caption || ""}
                    loading="lazy"
                    className="w-full aspect-square object-cover"
                  />
                  <button
                    type="button"
                    aria-label={t("wuyu.memory.delete")}
                    title={t("wuyu.memory.delete")}
                    onClick={() => setDeleteTarget(m)}
                    className="absolute top-1.5 right-1.5 rounded-md bg-black/50 text-white p-1 opacity-70 transition-opacity group-hover:opacity-100 hover:bg-destructive focus-visible:opacity-100 focus-visible:bg-destructive focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                  <div className="px-2 py-1.5">
                    <p className="text-[11px] text-muted-foreground">
                      {formatDateTime(m.created_at)}
                    </p>
                    {m.caption ? (
                      <p
                        className="text-xs text-foreground truncate mt-0.5"
                        title={m.caption}
                      >
                        {m.caption}
                      </p>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("wuyu.memory.deleteConfirm")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t("wuyu.memory.deleteConfirmHint")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("wuyu.memory.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteTarget && deleteMut.mutate(deleteTarget)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t("wuyu.memory.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
