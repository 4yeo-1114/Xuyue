import { useState, useCallback, useRef } from "react";
import { supabase } from "@/integrations/supabase/client";
import * as tus from "tus-js-client";
import { useLocale } from "@/contexts/LocaleContext";

const CHUNK_SIZE = 5 * 1024 * 1024; // 5MB per chunk

export interface ChunkedUploadState {
  progress: number;        // 0-100
  speed: string;           // e.g. "2.3 MB/s"
  uploaded: string;        // e.g. "12.5 MB"
  total: string;           // e.g. "85 MB"
  status: "idle" | "uploading" | "paused" | "success" | "error";
  error?: string;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

export function useChunkedUpload() {
  const { t } = useLocale();
  const [state, setState] = useState<ChunkedUploadState>({
    progress: 0, speed: "", uploaded: "0", total: "0", status: "idle",
  });
  const uploadRef = useRef<tus.Upload | null>(null);
  const startTimeRef = useRef<number>(0);
  const lastBytesRef = useRef<number>(0);
  const lastTimeRef = useRef<number>(0);

  const upload = useCallback(async (
    file: File,
    bucketName: string,
    filePath: string,
  ): Promise<string | null> => {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session?.access_token) {
      setState(s => ({ ...s, status: "error", error: t("resourceLib.upload.loginRequired") }));
      return null;
    }

    const projectId = import.meta.env.VITE_SUPABASE_PROJECT_ID;
    const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;

    return new Promise((resolve, reject) => {
      startTimeRef.current = Date.now();
      lastBytesRef.current = 0;
      lastTimeRef.current = Date.now();

      setState({
        progress: 0,
        speed: t("resourceLib.upload.speedCalculating"),
        uploaded: "0",
        total: formatBytes(file.size),
        status: "uploading",
      });

      const tusUpload = new tus.Upload(file, {
        endpoint: `${supabaseUrl}/storage/v1/upload/resumable`,
        retryDelays: [0, 1000, 3000, 5000, 10000],
        chunkSize: CHUNK_SIZE,
        headers: {
          authorization: `Bearer ${session.access_token}`,
          "x-upsert": "true",
        },
        uploadDataDuringCreation: true,
        removeFingerprintOnSuccess: true,
        metadata: {
          bucketName,
          objectName: filePath,
          contentType: file.type,
          cacheControl: "3600",
        },
        onError(error) {
          console.error("TUS upload error:", error);
          setState(s => ({
            ...s,
            status: "error",
            error: error.message || t("resourceLib.upload.uploadError"),
          }));
          resolve(null);
        },
        onProgress(bytesUploaded, bytesTotal) {
          const now = Date.now();
          const elapsed = (now - lastTimeRef.current) / 1000;
          let speed = "";
          if (elapsed > 0.5) {
            const bytesPerSec = (bytesUploaded - lastBytesRef.current) / elapsed;
            speed = formatBytes(bytesPerSec) + "/s";
            lastBytesRef.current = bytesUploaded;
            lastTimeRef.current = now;
          }
          setState(s => ({
            ...s,
            progress: Math.round((bytesUploaded / bytesTotal) * 100),
            uploaded: formatBytes(bytesUploaded),
            total: formatBytes(bytesTotal),
            ...(speed ? { speed } : {}),
          }));
        },
        onSuccess() {
          setState(s => ({ ...s, progress: 100, status: "success" }));
          // Build public URL
          const { data } = supabase.storage.from(bucketName).getPublicUrl(filePath);
          resolve(data.publicUrl);
        },
      });

      uploadRef.current = tusUpload;

      // Check for previous uploads to resume
      tusUpload.findPreviousUploads().then((prev) => {
        if (prev.length > 0) {
          tusUpload.resumeFromPreviousUpload(prev[0]);
        }
        tusUpload.start();
      });
    });
  }, [t]);

  const pause = useCallback(() => {
    uploadRef.current?.abort();
    setState(s => ({ ...s, status: "paused" }));
  }, []);

  const resume = useCallback(() => {
    if (uploadRef.current) {
      setState(s => ({ ...s, status: "uploading" }));
      uploadRef.current.start();
    }
  }, []);

  const reset = useCallback(() => {
    uploadRef.current = null;
    setState({ progress: 0, speed: "", uploaded: "0", total: "0", status: "idle" });
  }, []);

  return { state, upload, pause, resume, reset };
}
