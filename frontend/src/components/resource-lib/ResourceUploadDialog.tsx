import { useState, useRef, useEffect, useMemo } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Upload,
  X,
  FileText,
  Image,
  Film,
  Music,
  File,
  Pause,
  Play,
  Zap,
  CheckCircle2,
  AlertCircle,
  Sparkles,
  Loader2,
} from "lucide-react";
import { useResourceUpload } from "@/hooks/useResourceUpload";
import { supabase } from "@/integrations/supabase/client";
import React from "react";
import { cn } from "@/lib/utils";
import {
  ExamDetectionConfirmDialog,
  ExamDetectionResult,
} from "./ExamDetectionConfirmDialog";
import { useLocale } from "@/contexts/LocaleContext";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
  onNavigateToExam?: (resourceId?: string) => void;
  currentContext?: {
    className?: string;
    grade?: string;
    subject?: string;
    schoolLevel?: string;
  };
}

const RESOURCE_TYPES = [
  "课件教案",
  "试题试卷",
  "微课视频",
  "音频",
  "图片素材",
  "模板",
  "学案",
  "其他",
];
const LESSONS = [
  "阿长与山海经",
  "从百草园到三味书屋",
  "藤野先生",
  "老王",
  "背影",
  "春",
  "济南的冬天",
  "紫藤萝瀑布",
  "其他",
];
const GRADES = ["七年级", "八年级", "九年级", "高一", "高二", "高三", "通用"];

const ACCEPT_MAP: Record<string, string> = {
  课件教案: ".pdf,.pptx,.ppt,.docx,.doc",
  试题试卷: ".pdf,.docx,.doc,.xlsx,.xls",
  微课视频: ".mp4,.webm,.mov",
  音频: ".mp3,.wav,.m4a,.ogg",
  图片素材: ".jpg,.jpeg,.png,.webp,.gif,.svg",
  模板: ".pdf,.pptx,.docx,.xlsx",
  学案: ".pdf,.docx,.doc",
  其他: "*",
};

/** Auto-detect resource type from MIME */
function detectType(mime: string): string {
  if (mime.startsWith("image/")) return "图片素材";
  if (mime.startsWith("video/")) return "微课视频";
  if (mime.startsWith("audio/")) return "音频";
  if (
    mime.includes("pdf") ||
    mime.includes("word") ||
    mime.includes("document")
  )
    return "课件教案";
  if (mime.includes("presentation") || mime.includes("powerpoint"))
    return "课件教案";
  if (mime.includes("spreadsheet") || mime.includes("excel")) return "试题试卷";
  return "其他";
}

interface FileEntry {
  id: string;
  file: File;
  title: string;
  status: "pending" | "uploading" | "success" | "error";
  error?: string;
}

function getFileIcon(mime: string) {
  if (mime.startsWith("image/"))
    return <Image className="w-5 h-5 text-primary" />;
  if (mime.startsWith("video/"))
    return <Film className="w-5 h-5 text-primary" />;
  if (mime.startsWith("audio/"))
    return <Music className="w-5 h-5 text-primary" />;
  if (mime.includes("pdf"))
    return <FileText className="w-5 h-5 text-destructive" />;
  return <File className="w-5 h-5 text-muted-foreground" />;
}

function formatSize(bytes: number) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

const UPLOAD_PURPOSES = [
  {
    id: "homework",
    labelKey: "resourceLib.upload.purpose.homework",
    icon: "📝",
    defaultType: "试题试卷",
  },
  {
    id: "exam",
    labelKey: "resourceLib.upload.purpose.exam",
    icon: "📄",
    defaultType: "试题试卷",
  },
  {
    id: "courseware",
    labelKey: "resourceLib.upload.purpose.courseware",
    icon: "📊",
    defaultType: "课件教案",
  },
  {
    id: "other",
    labelKey: "resourceLib.upload.purpose.other",
    icon: "📁",
    defaultType: "其他",
  },
];

const RESOURCE_TYPE_I18N: Record<string, string> = {
  课件教案: "resourceLib.resourceType.courseware",
  试题试卷: "resourceLib.resourceType.exam",
  微课视频: "resourceLib.resourceType.video",
  音频: "resourceLib.resourceType.audio",
  图片素材: "resourceLib.resourceType.image",
  模板: "resourceLib.resourceType.template",
  学案: "resourceLib.resourceType.worksheet",
  其他: "resourceLib.resourceType.other",
};

const GRADE_I18N: Record<string, string> = {
  七年级: "resourceLib.uploadGrade.7",
  八年级: "resourceLib.uploadGrade.8",
  九年级: "resourceLib.uploadGrade.9",
  高一: "resourceLib.uploadGrade.10",
  高二: "resourceLib.uploadGrade.11",
  高三: "resourceLib.uploadGrade.12",
  通用: "resourceLib.uploadGrade.general",
};

const LESSON_I18N: Record<string, string> = {
  阿长与山海经: "resourceLib.upload.lesson.aChangAndShanHaiJing",
  从百草园到三味书屋: "resourceLib.upload.lesson.fromBaiCaoYuanToSanWeiShuWu",
  藤野先生: "resourceLib.upload.lesson.mrFujino",
  老王: "resourceLib.upload.lesson.oldWang",
  背影: "resourceLib.upload.lesson.theBack",
  春: "resourceLib.upload.lesson.spring",
  济南的冬天: "resourceLib.upload.lesson.winterInJinan",
  紫藤萝瀑布: "resourceLib.upload.lesson.wisteriaWaterfall",
  其他: "resourceLib.upload.lesson.other",
};

interface ExamParseResult {
  questionCount: number;
  knowledgePoints: string[];
  difficultyDist: { easy: number; medium: number; hard: number };
}

/** analyze-resource 边缘函数响应体（tags/类型/课文/年级为可选，error 为函数级失败标记） */
interface AnalyzeResourceResult {
  tags?: string[];
  resourceType?: string;
  relatedLesson?: string;
  suggestedGrade?: string;
  error?: string;
}

export function ResourceUploadDialog({
  open,
  onOpenChange,
  onSuccess,
  onNavigateToExam,
  currentContext,
}: Props) {
  const { t } = useLocale();
  const {
    upload,
    isUploading,
    progress,
    chunkedState,
    pauseUpload,
    resumeUpload,
    resetUpload,
  } = useResourceUpload();
  const fileInputRef = useRef<HTMLInputElement>(null);
  // AI 分析 15s 超时定时器句柄：卸载时清理 + 每次 race 结束后清理，避免 timer 泄漏
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  // 资源库文件夹名：上传后同步写入资源库（FastAPI），保证上传对话框与资源库页跨流程数据一致
  const uploadFolderName = useMemo(() => {
    const ctx = currentContext;
    if (!ctx) return "教学资源";
    const parts = [ctx.grade, ctx.className, ctx.subject].filter(Boolean);
    return parts.length ? `教学资源-${parts.join("-")}` : "教学资源";
  }, [currentContext]);

  const [files, setFiles] = useState<FileEntry[]>([]);
  const [description, setDescription] = useState("");
  const [type, setType] = useState("其他");
  const [tagInput, setTagInput] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [isShared, setIsShared] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [currentIndex, setCurrentIndex] = useState(-1);
  const [relatedLesson, setRelatedLesson] = useState("");
  const [grade, setGrade] = useState("");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [aiTagsGenerated, setAiTagsGenerated] = useState(false);
  const [uploadComplete, setUploadComplete] = useState(false);
  const [uploadPurpose, setUploadPurpose] = useState("homework");
  const [examParseResult, setExamParseResult] =
    useState<ExamParseResult | null>(null);
  const [examDetection, setExamDetection] =
    useState<ExamDetectionResult | null>(null);
  const [showDetectionConfirm, setShowDetectionConfirm] = useState(false);
  const [confirmedDetection, setConfirmedDetection] =
    useState<Partial<ExamDetectionResult> | null>(null);
  const [isDetecting, setIsDetecting] = useState(false);

  const isChunkedUploading =
    chunkedState.status === "uploading" || chunkedState.status === "paused";
  const isBatchUploading = currentIndex >= 0;

  const resetForm = () => {
    setFiles([]);
    setDescription("");
    setType("其他");
    setTagInput("");
    setTags([]);
    setIsShared(false);
    setCurrentIndex(-1);
    setRelatedLesson("");
    setGrade("");
    setIsAnalyzing(false);
    setAiTagsGenerated(false);
    setUploadComplete(false);
    setUploadPurpose("homework");
    setExamParseResult(null);
    setExamDetection(null);
    setShowDetectionConfirm(false);
    setConfirmedDetection(null);
    setIsDetecting(false);
    resetUpload();
  };

  /** AI analyze first file to extract tags and metadata (with 15s timeout) */
  const analyzeFile = async (file: File, title: string) => {
    setIsAnalyzing(true);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    try {
      const result = await Promise.race([
        supabase.functions.invoke<AnalyzeResourceResult>("analyze-resource", {
          body: {
            fileName: file.name,
            mimeType: file.type,
            fileSize: formatSize(file.size),
            title,
          },
        }),
        new Promise<never>((_, reject) => {
          timeoutRef.current = setTimeout(
            () => reject(new Error("timeout")),
            15000,
          );
        }),
      ]);

      const { data, error } = result;
      if (!error && data && !data.error) {
        if (data.tags?.length) {
          setTags(data.tags);
          setAiTagsGenerated(true);
        }
        if (data.resourceType && RESOURCE_TYPES.includes(data.resourceType)) {
          setType(data.resourceType);
        }
        const relatedLesson = data.relatedLesson;
        if (relatedLesson) {
          const match = LESSONS.find((l) => relatedLesson.includes(l));
          if (match) setRelatedLesson(match);
        }
        const suggestedGrade = data.suggestedGrade;
        if (suggestedGrade) {
          const match = GRADES.find((g) => suggestedGrade.includes(g));
          if (match) setGrade(match);
        }
      }
    } catch (e: any) {
      if (e?.message === "timeout") {
        console.warn("AI analyze timed out");
      } else {
        console.error("AI analyze error:", e);
      }
    } finally {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      setIsAnalyzing(false);
    }
  };

  /** AI analyze exam content for attribution detection (with 15s timeout) */
  const analyzeExamContent = async (file: File, title: string) => {
    setIsDetecting(true);
    setIsAnalyzing(true); // Also mark tags as analyzing for exam uploads
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    try {
      const result = await Promise.race([
        supabase.functions.invoke<ExamDetectionResult & { error?: string }>(
          "analyze-exam-content",
          {
            body: {
              fileName: file.name,
              mimeType: file.type,
              fileSize: formatSize(file.size),
              title,
              currentContext,
            },
          },
        ),
        new Promise<never>((_, reject) => {
          timeoutRef.current = setTimeout(
            () => reject(new Error("timeout")),
            15000,
          );
        }),
      ]);

      const { data, error } = result;
      if (!error && data && !data.error && data.confidence > 0) {
        setExamDetection(data);

        // Use tags from detection (this is the only tag source for exam uploads)
        const tags = data.tags;
        if (tags?.length) {
          setTags((prev) => [...new Set([...prev, ...tags])]);
          setAiTagsGenerated(true);
        }

        // Check if detection matches current context
        const detectedLabel = [
          data.detected_grade,
          data.detected_class,
          data.detected_subject,
        ]
          .filter(Boolean)
          .join("");
        const currentLabel = [
          currentContext?.grade,
          currentContext?.className,
          currentContext?.subject,
        ]
          .filter(Boolean)
          .join("");

        if (
          data.confidence >= 0.8 &&
          (detectedLabel === currentLabel || !currentLabel)
        ) {
          setConfirmedDetection(data);
        } else if (data.confidence >= 0.5) {
          setShowDetectionConfirm(true);
        }
      }
    } catch (e: any) {
      if (e?.message === "timeout") {
        console.warn("Exam content analysis timed out");
      } else {
        console.error("Exam content analysis error:", e);
      }
    } finally {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      setIsDetecting(false);
      setIsAnalyzing(false); // Always clear analyzing state
    }
  };

  const addFiles = (newFiles: File[]) => {
    const valid = newFiles.filter((f) => {
      if (f.size > 100 * 1024 * 1024) return false;
      return !files.some(
        (existing) =>
          existing.file.name === f.name && existing.file.size === f.size,
      );
    });
    if (valid.length < newFiles.length) {
      const skipped = newFiles.length - valid.length;
      if (skipped > 0)
        alert(t("resourceLib.upload.skippedFiles", { count: skipped }));
    }
    const entries: FileEntry[] = valid.map((f) => ({
      id: crypto.randomUUID(),
      file: f,
      title: f.name.replace(/\.[^.]+$/, ""),
      status: "pending" as const,
    }));
    setFiles((prev) => [...prev, ...entries]);

    // Auto-detect type from first file (MIME) and trigger AI analysis ONLY for single-file uploads.
    // 批量上传（一次选择多份）不触发 AI 识别：避免第一份文件的识别归属元数据被套用到整批文件，
    // 统一归属当前班级（与 UI 承诺一致）。批量文件仍按首份 MIME 自动识别资源类型（非 AI）。
    if (valid.length > 0 && files.length === 0) {
      const first = valid[0];
      const title = first.name.replace(/\.[^.]+$/, "");

      if (uploadPurpose === "exam") {
        // Keep exam uploads as exam type; don't let MIME auto-detection override it
        setType("试题试卷");
      } else {
        setType(detectType(first.type));
      }

      // 仅单文件上传触发 AI 识别
      if (valid.length === 1) {
        if (uploadPurpose === "exam") {
          // Exam uploads: only call analyzeExamContent (it already returns tags)
          analyzeExamContent(first, title);
        } else {
          // Non-exam uploads: call generic analyzeFile
          analyzeFile(first, title);
        }
      }
    }
  };

  const removeFile = (id: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== id));
  };

  const updateTitle = (id: string, title: string) => {
    setFiles((prev) => prev.map((f) => (f.id === id ? { ...f, title } : f)));
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const list = e.target.files;
    if (!list?.length) return;
    addFiles(Array.from(list));
    e.target.value = "";
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    const list = e.dataTransfer.files;
    if (list?.length) addFiles(Array.from(list));
  };

  const addTag = () => {
    const tagVal = tagInput.trim().replace(/^#/, "");
    if (tagVal && !tags.includes(`#${tagVal}`)) {
      setTags((prev) => [...prev, `#${tagVal}`]);
    }
    setTagInput("");
  };

  const resourceTypeLabel = (value: string) =>
    RESOURCE_TYPE_I18N[value] ? t(RESOURCE_TYPE_I18N[value]) : value;

  const gradeLabel = (value: string) =>
    GRADE_I18N[value] ? t(GRADE_I18N[value]) : value;

  const lessonLabel = (value: string) =>
    LESSON_I18N[value] ? t(LESSON_I18N[value]) : value;

  const handleSubmit = async () => {
    if (files.length === 0) return;
    const pending = files.filter((f) => f.status === "pending");
    if (pending.length === 0) return;

    for (let i = 0; i < files.length; i++) {
      const entry = files[i];
      if (entry.status !== "pending") continue;

      setCurrentIndex(i);
      setFiles((prev) =>
        prev.map((f, idx) => (idx === i ? { ...f, status: "uploading" } : f)),
      );

      // Build detection metadata
      // 批量上传（>1 份）：不套用单份识别元数据，统一归属当前班级（批量不跑 AI 识别，仅按 MIME 定类型）
      const isBatch = files.length > 1;
      let det = isBatch ? null : confirmedDetection || examDetection;

      // 低置信度（<0.5）或无可信识别：归属字段改用当前班级，不覆盖为识别出的错误班级，
      // 与 UI「识别置信度较低，将归属到当前班级」承诺一致（is_cross_class=false）
      const lowConfidence = det ? (det.confidence ?? 0) < 0.5 : true;
      if (lowConfidence) {
        det = {
          ...(det || {}),
          detected_grade: currentContext?.grade,
          detected_class: currentContext?.className,
          detected_subject: currentContext?.subject,
          detected_school_level: currentContext?.schoolLevel,
        };
      }

      const isCrossClass =
        det?.detected_class && currentContext?.className
          ? det.detected_class !== currentContext.className
          : false;

      const ok = await upload({
        file: entry.file,
        title: entry.title,
        description,
        type,
        tags: [
          ...tags,
          ...(relatedLesson ? [`#${relatedLesson}`] : []),
          ...(grade ? [`#${grade}`] : []),
        ],
        isShared,
        detected_grade: det?.detected_grade || undefined,
        detected_class: det?.detected_class || undefined,
        detected_subject: det?.detected_subject || undefined,
        detected_unit: det?.detected_unit || undefined,
        detected_chapter: det?.detected_chapter || undefined,
        detected_school_level: det?.detected_school_level || undefined,
        detection_confidence: det?.confidence || 0,
        uploaded_from_class: currentContext?.className || undefined,
        uploaded_from_grade: currentContext?.grade || undefined,
        is_cross_class: isCrossClass,
        question_count: det?.estimated_question_count || 0,
        knowledge_point_count: det?.estimated_knowledge_points?.length || 0,
        difficulty: det?.estimated_difficulty || 0,
        source_label: det?.source_label || t("resourceLib.upload.manualUpload"),
        folderName: uploadFolderName,
      });

      setFiles((prev) =>
        prev.map((f, idx) =>
          idx === i
            ? {
                ...f,
                status: ok ? "success" : "error",
                error: ok ? undefined : t("resourceLib.upload.uploadError"),
              }
            : f,
        ),
      );
    }

    setCurrentIndex(-1);
    setUploadComplete(true);

    // If exam purpose, show parse preview from real detection metadata (no fake data, no leaked timer)
    if (uploadPurpose === "exam") {
      const det = confirmedDetection || examDetection;
      // estimated_difficulty 兼容 0-1 与 0-100 两种量纲
      const rawDifficulty =
        typeof det?.estimated_difficulty === "number"
          ? det.estimated_difficulty
          : 0;
      const diffPct =
        rawDifficulty > 1
          ? Math.min(100, rawDifficulty)
          : Math.round(rawDifficulty * 100);
      const hard = Math.max(0, Math.min(100, diffPct));
      const easy = Math.round((100 - hard) / 2);
      setExamParseResult({
        questionCount: det?.estimated_question_count || 0,
        knowledgePoints: det?.estimated_knowledge_points || [],
        difficultyDist: { easy, medium: 100 - hard - easy, hard },
      });
    }
  };

  const handleClose = () => {
    if (uploadComplete) {
      resetForm();
      onOpenChange(false);
      onSuccess?.();
    } else {
      // 中途关闭：先中止进行中的分块上传，再重置全部状态（currentIndex / 文件列表 / 上传态），
      // 避免重开对话框时卡在 uploading 或 batch progress
      if (isChunkedUploading) {
        pauseUpload();
      }
      resetForm();
      onOpenChange(false);
    }
  };

  const successCount = files.filter((f) => f.status === "success").length;
  const errorCount = files.filter((f) => f.status === "error").length;
  const pendingCount = files.filter((f) => f.status === "pending").length;
  const allFailed = uploadComplete && successCount === 0 && errorCount > 0;

  return (
    <>
      <Dialog open={open} onOpenChange={handleClose}>
        <DialogContent className="sm:max-w-lg max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Upload className="w-5 h-5 text-primary" />
              {t("resourceLib.upload.title")}
              {files.length > 0 && (
                <Badge variant="secondary" className="text-[10px]">
                  {t("resourceLib.upload.fileCount", { count: files.length })}
                </Badge>
              )}
            </DialogTitle>
          </DialogHeader>

          {/* Upload complete state */}
          {uploadComplete ? (
            <div className="flex flex-col items-center gap-4 py-8">
              <div
                className={cn(
                  "w-16 h-16 rounded-full flex items-center justify-center",
                  allFailed
                    ? "bg-destructive/10"
                    : "bg-green-100 dark:bg-green-900/30",
                )}
              >
                {allFailed ? (
                  <AlertCircle className="w-8 h-8 text-destructive" />
                ) : (
                  <CheckCircle2 className="w-8 h-8 text-green-600" />
                )}
              </div>
              <div className="text-center space-y-1">
                <p className="text-lg font-semibold text-foreground">
                  {allFailed
                    ? t("resourceLib.upload.failed")
                    : successCount < files.length
                      ? t("resourceLib.upload.partialSuccess")
                      : t("resourceLib.upload.success")}
                </p>
                <p className="text-sm text-muted-foreground">
                  {allFailed ? (
                    t("resourceLib.upload.allFailed", { count: errorCount })
                  ) : (
                    <>
                      {t("resourceLib.upload.successCount", {
                        count: successCount,
                      })}
                      {errorCount > 0 &&
                        t("resourceLib.upload.failedCount", {
                          count: errorCount,
                        })}
                    </>
                  )}
                </p>
                {uploadPurpose === "exam" ? (
                  <p className="text-xs text-primary font-medium">
                    {t("resourceLib.upload.examSaved")}
                  </p>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    {t("resourceLib.upload.addedToList")}
                  </p>
                )}
              </div>

              {/* Exam parse preview */}
              {uploadPurpose === "exam" && examParseResult && (
                <div className="w-full border rounded-lg p-3 space-y-2 bg-muted/30">
                  <p className="text-xs font-medium text-foreground flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-primary" />
                    {t("resourceLib.upload.parsePreview")}
                  </p>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div className="rounded-md bg-card border p-2">
                      <p className="text-lg font-bold text-primary">
                        {examParseResult.questionCount}
                      </p>
                      <p className="text-[10px] text-muted-foreground">
                        {t("resourceLib.upload.questionCount")}
                      </p>
                    </div>
                    <div className="rounded-md bg-card border p-2">
                      <p className="text-lg font-bold text-foreground">
                        {examParseResult.knowledgePoints.length}
                      </p>
                      <p className="text-[10px] text-muted-foreground">
                        {t("resourceLib.upload.knowledgePoints")}
                      </p>
                    </div>
                    <div className="rounded-md bg-card border p-2">
                      <div className="flex justify-center gap-1 text-[10px]">
                        <Badge
                          variant="outline"
                          className="text-[8px] border-green-300 text-green-600"
                        >
                          {t("resourceLib.upload.difficultyEasy", {
                            percent: examParseResult.difficultyDist.easy,
                          })}
                        </Badge>
                        <Badge
                          variant="outline"
                          className="text-[8px] border-amber-300 text-amber-600"
                        >
                          {t("resourceLib.upload.difficultyMedium", {
                            percent: examParseResult.difficultyDist.medium,
                          })}
                        </Badge>
                        <Badge
                          variant="outline"
                          className="text-[8px] border-red-300 text-red-600"
                        >
                          {t("resourceLib.upload.difficultyHard", {
                            percent: examParseResult.difficultyDist.hard,
                          })}
                        </Badge>
                      </div>
                      <p className="text-[10px] text-muted-foreground mt-0.5">
                        {t("resourceLib.upload.difficultyDist")}
                      </p>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {examParseResult.knowledgePoints.map((kp) => (
                      <Badge
                        key={kp}
                        variant="secondary"
                        className="text-[9px]"
                      >
                        {kp}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex gap-2">
                {uploadPurpose === "exam" &&
                  examParseResult &&
                  onNavigateToExam && (
                    <Button
                      variant="default"
                      className="gap-1.5"
                      onClick={() => {
                        onOpenChange(false);
                        resetForm();
                        onNavigateToExam();
                      }}
                    >
                      <Sparkles className="w-4 h-4" />
                      {t("resourceLib.upload.goExam")}
                    </Button>
                  )}
                <Button
                  variant={
                    uploadPurpose === "exam" && examParseResult
                      ? "outline"
                      : "default"
                  }
                  onClick={handleClose}
                  className="gap-1"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  {t("resourceLib.upload.done")}
                </Button>
              </div>
            </div>
          ) : (
            <>
              <ScrollArea className="flex-1 pr-2">
                <div className="space-y-4">
                  {/* Upload purpose selector */}
                  <div className="space-y-1.5">
                    <Label className="text-xs">
                      {t("resourceLib.upload.purpose")}
                    </Label>
                    <div className="grid grid-cols-4 gap-2">
                      {UPLOAD_PURPOSES.map((p) => (
                        <button
                          type="button"
                          key={p.id}
                          onClick={() => {
                            setUploadPurpose(p.id);
                            if (p.id === "exam") setType("试题试卷");
                            else setType(p.defaultType);
                          }}
                          aria-pressed={uploadPurpose === p.id}
                          className={cn(
                            "flex flex-col items-center gap-1 p-2 rounded-lg border transition-all text-center",
                            uploadPurpose === p.id
                              ? p.id === "exam"
                                ? "border-primary bg-primary/10 ring-1 ring-primary/30 shadow-sm"
                                : "border-primary bg-primary/5 ring-1 ring-primary/20"
                              : "border-border hover:border-primary/30 hover:bg-muted/30",
                          )}
                        >
                          <span className="text-lg">{p.icon}</span>
                          <span
                            className={cn(
                              "text-[10px] font-medium leading-tight",
                              uploadPurpose === p.id
                                ? "text-primary"
                                : "text-foreground",
                            )}
                          >
                            {t(p.labelKey)}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* File drop zone */}
                  <div
                    role="button"
                    tabIndex={0}
                    aria-label={t("resourceLib.upload.dropHint")}
                    onClick={() => fileInputRef.current?.click()}
                    onKeyDown={(e) => {
                      // 键盘可访问性：Enter/Space 触发文件选择
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        fileInputRef.current?.click();
                      }
                    }}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                    className={`border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${isDragging ? "border-primary bg-primary/5 scale-[1.01]" : "border-border hover:border-primary/50 hover:bg-muted/30"}`}
                  >
                    <Upload className="w-6 h-6 text-muted-foreground mx-auto mb-1.5" />
                    <p className="text-sm text-muted-foreground">
                      {t("resourceLib.upload.dropHint")}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {t("resourceLib.upload.formatHint")}
                    </p>
                    <input
                      ref={fileInputRef}
                      type="file"
                      multiple
                      className="hidden"
                      accept={ACCEPT_MAP[type] || "*"}
                      onChange={handleFileChange}
                    />
                  </div>

                  {/* File list */}
                  {files.length > 0 && (
                    <div className="border border-border rounded-lg max-h-[140px] overflow-y-auto">
                      <div className="divide-y divide-border">
                        {files.map((entry) => (
                          <div
                            key={entry.id}
                            className="flex items-center gap-2 px-3 py-2"
                          >
                            <div className="flex-shrink-0">
                              {entry.status === "success" ? (
                                <CheckCircle2 className="w-5 h-5 text-green-500" />
                              ) : entry.status === "error" ? (
                                <AlertCircle className="w-5 h-5 text-destructive" />
                              ) : entry.status === "uploading" ? (
                                <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                              ) : (
                                getFileIcon(entry.file.type)
                              )}
                            </div>
                            <div className="flex-1 min-w-0">
                              <Input
                                value={entry.title}
                                onChange={(e) =>
                                  updateTitle(entry.id, e.target.value)
                                }
                                className="h-6 text-xs border-none p-0 shadow-none focus-visible:ring-0"
                                disabled={entry.status !== "pending"}
                              />
                              <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                                <span>{formatSize(entry.file.size)}</span>
                                <Badge
                                  variant="outline"
                                  className="text-[8px] h-3.5 px-1"
                                >
                                  {resourceTypeLabel(
                                    detectType(entry.file.type),
                                  )}
                                </Badge>
                                {entry.file.size > 10 * 1024 * 1024 && (
                                  <Badge
                                    variant="secondary"
                                    className="text-[8px] h-3.5 px-1 gap-0.5"
                                  >
                                    <Zap className="w-2 h-2" />
                                    {t("resourceLib.upload.chunked")}
                                  </Badge>
                                )}
                              </div>
                            </div>
                            {entry.status === "pending" && (
                              <Button
                                variant="ghost"
                                size="sm"
                                aria-label={t("common.delete")}
                                className="h-5 w-5 p-0 flex-shrink-0"
                                onClick={() => removeFile(entry.id)}
                              >
                                <X className="w-3.5 h-3.5" />
                              </Button>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* AI Exam Detection Status */}
                  {files.length > 0 && uploadPurpose === "exam" && (
                    <div className="space-y-1.5">
                      {isDetecting && (
                        <div className="flex items-center gap-2 p-2.5 rounded-lg bg-primary/5 border border-primary/20">
                          <Loader2 className="w-3.5 h-3.5 text-primary animate-spin" />
                          <span className="text-xs text-primary font-medium">
                            {t("resourceLib.upload.detecting")}
                          </span>
                        </div>
                      )}
                      {confirmedDetection && !isDetecting && (
                        <div className="p-2.5 rounded-lg bg-primary/5 border border-primary/20 space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-medium text-foreground flex items-center gap-1">
                              <Sparkles className="w-3 h-3 text-primary" />
                              {t("resourceLib.upload.detected")}
                            </span>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-5 text-[10px] text-primary"
                              onClick={() => setShowDetectionConfirm(true)}
                            >
                              {t("resourceLib.upload.modify")}
                            </Button>
                          </div>
                          <p className="text-xs text-foreground">
                            🏷️{" "}
                            {[
                              confirmedDetection.detected_grade,
                              confirmedDetection.detected_class,
                              confirmedDetection.detected_subject,
                              confirmedDetection.detected_unit,
                            ]
                              .filter(Boolean)
                              .join(" · ")}
                          </p>
                          {confirmedDetection.detected_class &&
                            currentContext?.className &&
                            confirmedDetection.detected_class !==
                              currentContext.className && (
                              <p className="text-[10px] text-muted-foreground">
                                {t("resourceLib.upload.crossClassUpload", {
                                  className: currentContext.className,
                                })}
                              </p>
                            )}
                        </div>
                      )}
                      {examDetection &&
                        !confirmedDetection &&
                        !isDetecting &&
                        examDetection.confidence < 0.5 && (
                          <div className="flex items-center gap-2 p-2.5 rounded-lg bg-muted/50 border border-border">
                            <AlertCircle className="w-3.5 h-3.5 text-muted-foreground" />
                            <span className="text-[10px] text-muted-foreground">
                              {t("resourceLib.upload.lowConfidence")}
                            </span>
                          </div>
                        )}
                    </div>
                  )}

                  {/* AI Tags Section */}
                  {files.length > 0 && (
                    <div className="space-y-1.5">
                      <div className="flex items-center gap-1.5">
                        <Label className="text-xs">
                          {t("resourceLib.upload.tags")}
                        </Label>
                        {isAnalyzing && (
                          <span className="flex items-center gap-1 text-[10px] text-primary">
                            <Loader2 className="w-3 h-3 animate-spin" />
                            {t("resourceLib.upload.aiAnalyzing")}
                          </span>
                        )}
                        {aiTagsGenerated && !isAnalyzing && (
                          <Badge
                            variant="secondary"
                            className="text-[9px] gap-0.5 bg-primary/10 text-primary"
                          >
                            <Sparkles className="w-2.5 h-2.5" />
                            {t("resourceLib.upload.aiTags")}
                          </Badge>
                        )}
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {tags.map((tag) => (
                          <Badge
                            key={tag}
                            variant="secondary"
                            className="text-[10px] gap-0.5"
                          >
                            {tag}
                            <X
                              className="w-3 h-3 cursor-pointer"
                              onClick={() =>
                                setTags((prev) => prev.filter((x) => x !== tag))
                              }
                            />
                          </Badge>
                        ))}
                      </div>
                      <div className="flex gap-1.5">
                        <Input
                          placeholder={t(
                            "resourceLib.upload.addTagPlaceholder",
                          )}
                          value={tagInput}
                          onChange={(e) => setTagInput(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              e.preventDefault();
                              addTag();
                            }
                          }}
                          className="h-7 text-xs flex-1"
                        />
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-[10px]"
                          onClick={addTag}
                        >
                          {t("resourceLib.upload.addTag")}
                        </Button>
                      </div>
                    </div>
                  )}

                  {/* Type + Related Lesson + Grade row */}
                  {files.length > 0 && (
                    <div className="grid grid-cols-3 gap-2">
                      <div className="space-y-1">
                        <Label className="text-[10px]">
                          {t("resourceLib.upload.resourceType")}
                        </Label>
                        <Select value={type} onValueChange={setType}>
                          <SelectTrigger className="h-7 text-[11px]">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {RESOURCE_TYPES.map((rt) => (
                              <SelectItem
                                key={rt}
                                value={rt}
                                className="text-xs"
                              >
                                {resourceTypeLabel(rt)}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1">
                        <Label className="text-[10px]">
                          {t("resourceLib.upload.relatedLesson")}
                        </Label>
                        <Select
                          value={relatedLesson}
                          onValueChange={setRelatedLesson}
                        >
                          <SelectTrigger className="h-7 text-[11px]">
                            <SelectValue
                              placeholder={t("resourceLib.upload.selectLesson")}
                            />
                          </SelectTrigger>
                          <SelectContent>
                            {LESSONS.map((l) => (
                              <SelectItem key={l} value={l} className="text-xs">
                                {lessonLabel(l)}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1">
                        <Label className="text-[10px]">
                          {t("resourceLib.upload.applicableGrade")}
                        </Label>
                        <Select value={grade} onValueChange={setGrade}>
                          <SelectTrigger className="h-7 text-[11px]">
                            <SelectValue
                              placeholder={t("resourceLib.upload.selectGrade")}
                            />
                          </SelectTrigger>
                          <SelectContent>
                            {GRADES.map((g) => (
                              <SelectItem key={g} value={g} className="text-xs">
                                {gradeLabel(g)}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                  )}

                  {/* Description */}
                  {files.length > 0 && (
                    <div className="space-y-1">
                      <Label className="text-[10px]">
                        {t("resourceLib.upload.description")}
                      </Label>
                      <Textarea
                        placeholder={t(
                          "resourceLib.upload.descriptionPlaceholder",
                        )}
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        className="text-xs min-h-[48px]"
                      />
                    </div>
                  )}

                  {/* Share toggle */}
                  {files.length > 0 && (
                    <div className="flex items-center justify-between">
                      <div>
                        <Label className="text-xs">
                          {t("resourceLib.upload.shareToGroup")}
                        </Label>
                        <p className="text-[10px] text-muted-foreground">
                          {t("resourceLib.upload.shareHint")}
                        </p>
                      </div>
                      <Switch
                        checked={isShared}
                        onCheckedChange={setIsShared}
                      />
                    </div>
                  )}

                  {/* Chunked upload progress */}
                  {isChunkedUploading && (
                    <div className="space-y-2 p-3 rounded-lg bg-muted/40 border border-border">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground flex items-center gap-1">
                          <Zap className="w-3 h-3 text-primary" />
                          {t("resourceLib.upload.chunkedUploading")}
                        </span>
                        <span className="font-medium text-foreground">
                          {chunkedState.uploaded} / {chunkedState.total}
                        </span>
                      </div>
                      <Progress value={chunkedState.progress} className="h-2" />
                      <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                        <span>
                          {t("resourceLib.upload.speed", {
                            speed: chunkedState.speed,
                          })}
                        </span>
                        <span>{chunkedState.progress}%</span>
                      </div>
                      <div className="flex gap-1.5">
                        {chunkedState.status === "uploading" ? (
                          <Button
                            variant="outline"
                            size="sm"
                            className="text-[10px] h-6 gap-1"
                            onClick={pauseUpload}
                          >
                            <Pause className="w-3 h-3" />
                            {t("resourceLib.upload.pause")}
                          </Button>
                        ) : (
                          <Button
                            variant="outline"
                            size="sm"
                            className="text-[10px] h-6 gap-1"
                            onClick={resumeUpload}
                          >
                            <Play className="w-3 h-3" />
                            {t("resourceLib.upload.resume")}
                          </Button>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Simple progress for small files */}
                  {isUploading && !isChunkedUploading && (
                    <div className="space-y-1">
                      <Progress value={progress} className="h-2" />
                      <p className="text-[10px] text-muted-foreground text-center">
                        {progress < 30
                          ? t("resourceLib.upload.progressPrepare")
                          : progress < 70
                            ? t("resourceLib.upload.progressUploading")
                            : progress < 100
                              ? t("resourceLib.upload.progressSaving")
                              : t("resourceLib.upload.progressDone")}
                      </p>
                    </div>
                  )}

                  {/* Batch progress */}
                  {isBatchUploading && (
                    <p className="text-xs text-muted-foreground text-center">
                      {t("resourceLib.upload.batchProgress", {
                        current: currentIndex + 1,
                        total: files.length,
                        done: successCount,
                      })}
                    </p>
                  )}

                  {/* Error state */}
                  {chunkedState.status === "error" && (
                    <div className="p-2 rounded bg-destructive/10 text-destructive text-xs">
                      {t("resourceLib.upload.chunkedError", {
                        error: chunkedState.error,
                      })}
                    </div>
                  )}
                </div>
              </ScrollArea>

              <DialogFooter>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onOpenChange(false)}
                  disabled={isBatchUploading}
                >
                  {t("common.cancel")}
                </Button>
                <Button
                  size="sm"
                  onClick={handleSubmit}
                  disabled={
                    pendingCount === 0 || isBatchUploading || isAnalyzing
                  }
                >
                  {isBatchUploading
                    ? t("resourceLib.upload.uploading", {
                        done: successCount,
                        total: files.length,
                      })
                    : files.length > 0
                      ? `${t("resourceLib.upload.uploadBtn")} (${files.length})`
                      : t("resourceLib.upload.uploadBtn")}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* Detection confirm dialog */}
      {examDetection && (
        <ExamDetectionConfirmDialog
          open={showDetectionConfirm}
          onOpenChange={setShowDetectionConfirm}
          detection={examDetection}
          currentContext={currentContext || {}}
          fileName={files[0]?.file.name || ""}
          onConfirm={(choice, manualData) => {
            if (choice === "detected") {
              setConfirmedDetection(examDetection);
            } else if (choice === "current") {
              setConfirmedDetection({
                detected_grade: currentContext?.grade,
                detected_class: currentContext?.className,
                detected_subject: currentContext?.subject,
                detected_school_level: currentContext?.schoolLevel,
                confidence: 1,
              });
            } else if (choice === "manual" && manualData) {
              setConfirmedDetection({
                ...manualData,
                confidence: 1,
              });
            }
          }}
        />
      )}
    </>
  );
}
