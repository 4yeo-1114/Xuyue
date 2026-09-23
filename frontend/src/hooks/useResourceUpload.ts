import { useState, useCallback } from "react";
import { supabase } from "@/integrations/supabase/client";
import { toast } from "sonner";
import { useChunkedUpload } from "./useChunkedUpload";
import { useLocale } from "@/contexts/LocaleContext";
import { uploadResourceFiles, createResourceFolder } from "@/services/api";

const CHUNK_THRESHOLD = 10 * 1024 * 1024; // 10MB

interface UploadParams {
  file: File;
  title: string;
  description: string;
  type: string;
  tags: string[];
  isShared: boolean;
  // AI detection fields
  detected_grade?: string;
  detected_class?: string;
  detected_subject?: string;
  detected_unit?: string;
  detected_chapter?: string;
  detected_school_level?: string;
  detection_confidence?: number;
  uploaded_from_class?: string;
  uploaded_from_grade?: string;
  is_cross_class?: boolean;
  question_count?: number;
  knowledge_point_count?: number;
  difficulty?: number;
  source_label?: string;
  // 资源库文件夹名：提供后同步推入 FastAPI 资源库（与资源库页同一 service），避免跨流程数据断裂
  folderName?: string;
}

export function useResourceUpload() {
  const { t } = useLocale();
  const [isUploading, setIsUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const chunked = useChunkedUpload();

  const upload = useCallback(
    async (params: UploadParams) => {
      setIsUploading(true);
      setProgress(10);

      try {
        const {
          data: { user },
        } = await supabase.auth.getUser();
        if (!user) {
          toast.error(t("resourceLib.upload.loginRequired"));
          return false;
        }

        // Use UUID-based path to avoid Storage key issues with special/Chinese chars
        const ext = params.file.name.split(".").pop() || "bin";
        const filePath = `${user.id}/${Date.now()}_${crypto.randomUUID()}.${ext}`;
        let publicUrl: string;

        if (params.file.size > CHUNK_THRESHOLD) {
          // Large file → chunked resumable upload
          const url = await chunked.upload(
            params.file,
            "teaching-resources",
            filePath,
          );
          if (!url) {
            toast.error(t("resourceLib.upload.fileUploadFailed"));
            return false;
          }
          publicUrl = url;
        } else {
          // Small file → direct upload
          setProgress(30);
          const { error: storageError } = await supabase.storage
            .from("teaching-resources")
            .upload(filePath, params.file, { upsert: false });

          if (storageError) {
            console.error("Storage upload error:", storageError);
            toast.error(
              t("resourceLib.upload.fileUploadFailedDetail", {
                error: storageError.message,
              }),
            );
            return false;
          }

          const { data: urlData } = supabase.storage
            .from("teaching-resources")
            .getPublicUrl(filePath);
          publicUrl = urlData.publicUrl;
        }

        setProgress(70);

        // Save metadata to database
        const { error: dbError } = await supabase
          .from("teaching_resources")
          .insert({
            user_id: user.id,
            title: params.title,
            description: params.description,
            type: params.type,
            file_url: publicUrl,
            file_name: params.file.name,
            file_size: params.file.size,
            mime_type: params.file.type,
            tags: params.tags,
            is_shared: params.isShared,
            detected_grade: params.detected_grade || null,
            detected_class: params.detected_class || null,
            detected_subject: params.detected_subject || null,
            detected_unit: params.detected_unit || null,
            detected_chapter: params.detected_chapter || null,
            detected_school_level: params.detected_school_level || null,
            detection_confidence: params.detection_confidence || 0,
            uploaded_from_class: params.uploaded_from_class || null,
            uploaded_from_grade: params.uploaded_from_grade || null,
            is_cross_class: params.is_cross_class || false,
            question_count: params.question_count || 0,
            knowledge_point_count: params.knowledge_point_count || 0,
            difficulty: params.difficulty || 0,
            source_label:
              params.source_label || t("resourceLib.upload.manualUpload"),
          } as any);

        if (dbError) {
          console.error("DB insert error:", dbError);
          toast.error(
            t("resourceLib.upload.saveFailedDetail", {
              error: dbError.message,
            }),
          );
          return false;
        }

        // 统一存储后端：将文件同步推入 FastAPI 资源库（与资源库页 uploadResourceFiles 同一 service），
        // 避免上传对话框与资源库页两套存储导致跨流程数据断裂。失败仅 toast 报错，不影响 supabase 主流程。
        if (params.folderName) {
          try {
            // 文件夹不存在则先创建（已存在时后端返回 400，忽略即可）
            await createResourceFolder(params.folderName).catch(() => {});
            await uploadResourceFiles(params.folderName, [params.file]);
          } catch (pushErr) {
            console.error("Push to resource library failed:", pushErr);
            // 同步到 FastAPI 资源库失败不能静默吞掉：主流程（Supabase）已成功，但资源库页看不到该文件，
            // 需显式 toast 报错，避免 UI 只报「上传成功」却与资源库页数据不一致
            toast.error(
              t("resourceLib.upload.pushFailedDetail", {
                error:
                  pushErr instanceof Error ? pushErr.message : String(pushErr),
              }),
            );
          }
        }

        setProgress(100);
        toast.success(t("resourceLib.upload.successToast"));
        return true;
      } catch (e) {
        console.error("Upload error:", e);
        toast.error(t("resourceLib.upload.uploadErrorGeneric"));
        return false;
      } finally {
        setIsUploading(false);
        setProgress(0);
      }
    },
    [chunked, t],
  );

  return {
    upload,
    isUploading,
    progress,
    chunkedState: chunked.state,
    pauseUpload: chunked.pause,
    resumeUpload: chunked.resume,
    resetUpload: chunked.reset,
  };
}
