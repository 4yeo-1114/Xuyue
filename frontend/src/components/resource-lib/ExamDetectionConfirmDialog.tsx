import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  MapPin,
  Sparkles,
} from "lucide-react";
import { useState, useEffect } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSubjectName } from "@/i18n";

export interface ExamDetectionResult {
  detected_school_level?: string | null;
  detected_grade?: string | null;
  detected_class?: string | null;
  detected_subject?: string | null;
  detected_unit?: string | null;
  detected_chapter?: string | null;
  confidence: number;
  tags?: string[];
  estimated_question_count?: number;
  estimated_knowledge_points?: string[];
  estimated_difficulty?: number;
  source_label?: string;
}

interface CurrentContext {
  className?: string;
  grade?: string;
  subject?: string;
  schoolLevel?: string;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  detection: ExamDetectionResult;
  currentContext: CurrentContext;
  fileName: string;
  onConfirm: (
    choice: "detected" | "current" | "manual",
    manualData?: Partial<ExamDetectionResult>,
  ) => void;
}

const GRADES = [
  "一年级",
  "二年级",
  "三年级",
  "四年级",
  "五年级",
  "六年级",
  "七年级",
  "八年级",
  "九年级",
  "高一",
  "高二",
  "高三",
];
const SUBJECTS = ["语文", "数学", "英语", "科学"];

export function ExamDetectionConfirmDialog({
  open,
  onOpenChange,
  detection,
  currentContext,
  fileName,
  onConfirm,
}: Props) {
  const { t, locale } = useLocale();
  const [mode, setMode] = useState<"detected" | "current" | "manual">(
    "detected",
  );
  const [manualGrade, setManualGrade] = useState(
    detection.detected_grade || currentContext.grade || "",
  );
  const [manualClass, setManualClass] = useState(
    detection.detected_class || currentContext.className || "",
  );
  const [manualSubject, setManualSubject] = useState(
    detection.detected_subject || currentContext.subject || "",
  );

  // 多份文件先后弹出确认框时，detection 变化需重置手动归属字段，避免新文件误归属旧班级
  useEffect(() => {
    setManualGrade(detection.detected_grade || currentContext.grade || "");
    setManualClass(detection.detected_class || currentContext.className || "");
    setManualSubject(
      detection.detected_subject || currentContext.subject || "",
    );
  }, [detection, currentContext]);

  const detectedLabel = [
    detection.detected_grade,
    detection.detected_class,
    detection.detected_subject,
    detection.detected_unit,
  ]
    .filter(Boolean)
    .join("");
  const currentLabel = [
    currentContext.grade,
    currentContext.className,
    currentContext.subject,
  ]
    .filter(Boolean)
    .join("");

  const confidenceColor =
    detection.confidence >= 0.8
      ? "text-green-600"
      : detection.confidence >= 0.5
        ? "text-amber-600"
        : "text-red-500";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <Sparkles className="w-4 h-4 text-primary" />
            {t("resourceLib.examDetection.title")}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="text-sm text-muted-foreground">
            {t("resourceLib.examDetection.file")}
            <span className="text-foreground font-medium">{fileName}</span>
          </div>

          <div className="rounded-lg border border-primary/30 bg-primary/5 p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-foreground flex items-center gap-1">
                <Sparkles className="w-3 h-3 text-primary" />
                {t("resourceLib.examDetection.result")}
              </span>
              <Badge
                variant="outline"
                className={`text-[10px] ${confidenceColor}`}
              >
                {t("resourceLib.examDetection.confidence", {
                  percent: Math.round(detection.confidence * 100),
                })}
              </Badge>
            </div>
            <p className="text-sm font-semibold text-foreground">
              {detectedLabel || t("resourceLib.examDetection.noResult")}
            </p>
            {detection.estimated_question_count && (
              <div className="flex gap-2 text-[10px] text-muted-foreground">
                <span>
                  {t("resourceLib.examDetection.approxQuestions", {
                    count: detection.estimated_question_count,
                  })}
                </span>
                {detection.estimated_knowledge_points?.length && (
                  <span>
                    {t("resourceLib.examDetection.knowledgePoints", {
                      count: detection.estimated_knowledge_points.length,
                    })}
                  </span>
                )}
                {detection.estimated_difficulty != null && (
                  <span>
                    {t("resourceLib.examDetection.difficulty", {
                      value: detection.estimated_difficulty.toFixed(2),
                    })}
                  </span>
                )}
              </div>
            )}
          </div>

          <div className="rounded-lg border border-border bg-muted/30 p-3 space-y-1">
            <span className="text-xs font-medium text-muted-foreground flex items-center gap-1">
              <MapPin className="w-3 h-3" />
              {t("resourceLib.examDetection.currentContext")}
            </span>
            <p className="text-sm text-foreground">
              {currentLabel || t("resourceLib.examDetection.noClass")}
            </p>
          </div>

          {detectedLabel && currentLabel && detectedLabel !== currentLabel && (
            <div className="flex items-center gap-2 text-xs text-amber-600 bg-amber-50 dark:bg-amber-950/20 rounded-lg px-3 py-2">
              <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
              {t("resourceLib.examDetection.mismatch")}
            </div>
          )}

          <div className="space-y-2">
            <Label className="text-xs font-medium">
              {t("resourceLib.examDetection.chooseMethod")}
            </Label>

            <button
              type="button"
              onClick={() => setMode("detected")}
              aria-pressed={mode === "detected"}
              className={`w-full text-left rounded-lg border p-3 transition-all ${
                mode === "detected"
                  ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                  : "border-border hover:border-primary/30"
              }`}
            >
              <div className="flex items-center gap-2">
                {mode === "detected" && (
                  <CheckCircle2 className="w-4 h-4 text-primary flex-shrink-0" />
                )}
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {t("resourceLib.examDetection.toDetected")}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {detectedLabel ||
                      t("resourceLib.examDetection.noDetection")}
                  </p>
                </div>
              </div>
            </button>

            <button
              type="button"
              onClick={() => setMode("current")}
              aria-pressed={mode === "current"}
              className={`w-full text-left rounded-lg border p-3 transition-all ${
                mode === "current"
                  ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                  : "border-border hover:border-primary/30"
              }`}
            >
              <div className="flex items-center gap-2">
                {mode === "current" && (
                  <CheckCircle2 className="w-4 h-4 text-primary flex-shrink-0" />
                )}
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {t("resourceLib.examDetection.toCurrent")}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {currentLabel || t("resourceLib.examDetection.noClass")}
                  </p>
                </div>
              </div>
            </button>

            <button
              type="button"
              onClick={() => setMode("manual")}
              aria-pressed={mode === "manual"}
              className={`w-full text-left rounded-lg border p-3 transition-all ${
                mode === "manual"
                  ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                  : "border-border hover:border-primary/30"
              }`}
            >
              <div className="flex items-center gap-2">
                {mode === "manual" && (
                  <CheckCircle2 className="w-4 h-4 text-primary flex-shrink-0" />
                )}
                <p className="text-sm font-medium text-foreground">
                  {t("resourceLib.examDetection.manual")}
                </p>
              </div>
            </button>

            {mode === "manual" && (
              <div className="grid grid-cols-3 gap-2 pt-1">
                <div className="space-y-1">
                  <Label className="text-[10px]">
                    {t("resourceLib.examDetection.grade")}
                  </Label>
                  <Select value={manualGrade} onValueChange={setManualGrade}>
                    <SelectTrigger className="h-7 text-[11px]">
                      <SelectValue
                        placeholder={t(
                          "resourceLib.examDetection.gradePlaceholder",
                        )}
                      />
                    </SelectTrigger>
                    <SelectContent>
                      {GRADES.map((g) => (
                        <SelectItem key={g} value={g} className="text-xs">
                          {g}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label
                    htmlFor="exam-detection-manual-class"
                    className="text-[10px]"
                  >
                    {t("resourceLib.examDetection.class")}
                  </Label>
                  <input
                    id="exam-detection-manual-class"
                    className="h-7 w-full rounded-md border border-input bg-background px-2 text-[11px]"
                    value={manualClass}
                    onChange={(e) => setManualClass(e.target.value)}
                    placeholder={t(
                      "resourceLib.examDetection.classPlaceholder",
                    )}
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-[10px]">
                    {t("resourceLib.examDetection.subject")}
                  </Label>
                  <Select
                    value={manualSubject}
                    onValueChange={setManualSubject}
                  >
                    <SelectTrigger className="h-7 text-[11px]">
                      <SelectValue
                        placeholder={t(
                          "resourceLib.examDetection.subjectPlaceholder",
                        )}
                      />
                    </SelectTrigger>
                    <SelectContent>
                      {SUBJECTS.map((s) => (
                        <SelectItem key={s} value={s} className="text-xs">
                          {translateSubjectName(locale, s)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
          >
            {t("common.cancel")}
          </Button>
          <Button
            size="sm"
            className="gap-1"
            onClick={() => {
              if (mode === "manual") {
                onConfirm("manual", {
                  detected_grade: manualGrade,
                  detected_class: manualClass,
                  detected_subject: manualSubject,
                });
              } else {
                onConfirm(mode);
              }
              onOpenChange(false);
            }}
          >
            {t("common.confirm")} <ArrowRight className="w-3.5 h-3.5" />
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
