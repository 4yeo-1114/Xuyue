import { useState, useCallback, useRef } from "react";
import { toast } from "sonner";
import { useLocale } from "@/contexts/LocaleContext";
import { aiGenerateResource } from "@/services/api";

interface GenerateParams {
  genType: string;
  subject?: string;
  grade?: string;
  content: string;
  objective: string;
  studentProfile: string;
  requirements: string;
}

/**
 * AI 智能生成（互动课件/探究学案/多媒体资源）。
 * 原实现调用 Supabase Edge Function `generate-courseware`（本系统无 Supabase，恒失败），
 * 现改为调用本系统后端 `/ai-resources/generate`（通义千问），返回结构化 Markdown 供渲染。
 */
export function useAIGenerate() {
  const { t } = useLocale();
  const [isGenerating, setIsGenerating] = useState(false);
  const [streamedContent, setStreamedContent] = useState("");
  const [title, setTitle] = useState("");
  const [progress, setProgress] = useState(0);
  const cancelledRef = useRef(false);

  const generate = useCallback(
    async (params: GenerateParams) => {
      cancelledRef.current = false;
      setIsGenerating(true);
      setStreamedContent("");
      setTitle("");
      setProgress(10);

      try {
        const result = await aiGenerateResource({
          gen_type: params.genType,
          subject: params.subject,
          grade: params.grade,
          content: params.content,
          objective: params.objective,
          student_profile: params.studentProfile,
          requirements: params.requirements,
        });

        if (cancelledRef.current) return;
        setStreamedContent(result.markdown || "");
        setTitle(result.title || "");
        setProgress(100);
        toast.success(t("smartGen.generate.success"));
      } catch (e: any) {
        toast.error(t("smartGen.generate.failed"), {
          description: e?.message,
        });
      } finally {
        if (!cancelledRef.current) setIsGenerating(false);
      }
    },
    [t],
  );

  const cancel = useCallback(() => {
    cancelledRef.current = true;
    setIsGenerating(false);
  }, []);

  const reset = useCallback(() => {
    cancelledRef.current = true;
    setStreamedContent("");
    setTitle("");
    setProgress(0);
    setIsGenerating(false);
  }, []);

  /** 从生成历史回填：不调用后端，直接把已落库的标题/正文渲染到面板 */
  const loadExisting = useCallback((newTitle: string, newContent: string) => {
    cancelledRef.current = false;
    setStreamedContent(newContent);
    setTitle(newTitle);
    setProgress(100);
    setIsGenerating(false);
  }, []);

  return {
    isGenerating,
    streamedContent,
    title,
    progress,
    generate,
    cancel,
    reset,
    loadExisting,
  };
}
