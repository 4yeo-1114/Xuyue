import { useState, useCallback, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import {
  Library,
  Upload,
  Clock,
  Users2,
  GripVertical,
  Plus,
  X,
  Download,
} from "lucide-react";
import {
  createResourceFolder,
  downloadResourceFile,
  listExams,
  resourceDownloadUrl,
  uploadResourceFiles,
} from "@/services/api";
import type { LayeredRosterStudent, LayeredTierContent } from "@/services/api";
import { TIER_STYLES, WEEKDAY_KEYS, type Tier } from "./layeredData";

/** 推送资料统一存放的资源库文件夹 */
const MATERIAL_FOLDER = "分层推送资料";

interface TierColumnProps {
  tier: Tier;
  students: LayeredRosterStudent[];
  content: LayeredTierContent;
  classId: string;
  subject: string;
  /** 拖拽调整分层（按学生 id） */
  onMoveStudent: (studentId: string, fromTier: Tier, toTier: Tier) => void;
  /** 局部更新本层内容（会自动防抖保存到后端） */
  onContentChange: (patch: Partial<LayeredTierContent>) => void;
  /** 刷新名单（重新拉成绩/分层/同步状态） */
  onRefreshRoster: () => void;
}

export function TierColumn({
  tier,
  students,
  content,
  classId,
  subject,
  onMoveStudent,
  onContentChange,
  onRefreshRoster,
}: TierColumnProps) {
  const { t } = useLocale();
  const style = TIER_STYLES[tier];
  const [dragOver, setDragOver] = useState(false);
  const [examOpen, setExamOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragStart = useCallback(
    (e: React.DragEvent, studentId: string) => {
      e.dataTransfer.setData(
        "text/plain",
        JSON.stringify({ id: studentId, fromTier: tier }),
      );
      e.dataTransfer.effectAllowed = "move";
    },
    [tier],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    setDragOver(true);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      try {
        const data = JSON.parse(e.dataTransfer.getData("text/plain"));
        if (data.id && data.fromTier && data.fromTier !== tier) {
          onMoveStudent(data.id, data.fromTier, tier);
        }
      } catch {
        /* ignore */
      }
    },
    [tier, onMoveStudent],
  );

  // ── 从试卷库选（listExams：本班真实考试记录） ──
  const examsQuery = useQuery({
    queryKey: ["exams", classId, subject],
    queryFn: () => listExams(classId, subject),
    enabled: examOpen && !!classId,
  });

  const addExam = (title: string, examDate: string, examId: string) => {
    onContentChange({
      assignments: [
        ...content.assignments,
        { title, desc: t("layeredPush.examDesc", { date: examDate }), exam_id: examId },
      ],
    });
    toast.success(t("layeredPush.toast.examAdded", { title }));
    setExamOpen(false);
  };

  const removeAssignment = (idx: number) => {
    onContentChange({ assignments: content.assignments.filter((_, i) => i !== idx) });
  };

  const addAssignment = () => {
    const title = newTitle.trim();
    if (!title) return;
    onContentChange({
      assignments: [...content.assignments, { title, desc: newDesc.trim() || undefined }],
    });
    setNewTitle("");
    setNewDesc("");
  };

  // ── 上传资料（资源库「分层推送资料」文件夹，芯片可带鉴权下载） ──
  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    try {
      try {
        await createResourceFolder(MATERIAL_FOLDER);
      } catch {
        /* 文件夹已存在则忽略 */
      }
      await uploadResourceFiles(MATERIAL_FOLDER, Array.from(files));
      const adds = Array.from(files).map((f) => ({
        name: f.name,
        url: resourceDownloadUrl(MATERIAL_FOLDER, f.name),
      }));
      const existing = new Set(content.materials.map((m) => m.name));
      onContentChange({
        materials: [
          ...content.materials,
          ...adds.filter((m) => !existing.has(m.name)),
        ],
      });
      toast.success(
        t("layeredPush.toast.uploadOk", {
          name: adds.map((m) => m.name).join("、"),
        }),
      );
    } catch (e) {
      toast.error(
        (e as { message?: string })?.message || t("layeredPush.toast.uploadFail"),
      );
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const downloadMaterial = async (name: string, url: string) => {
    try {
      await downloadResourceFile(url, name);
    } catch (e) {
      toast.error(
        (e as { message?: string })?.message || t("layeredPush.toast.uploadFail"),
      );
    }
  };

  const patchMinutes = (v: string) => {
    const n = Number(v);
    if (Number.isNaN(n)) return;
    onContentChange({ estimated_minutes: Math.min(Math.max(Math.round(n), 5), 600) });
  };

  return (
    <div
      className={cn(
        "rounded-xl border p-4 flex flex-col gap-4 min-w-0 transition-all duration-200",
        style.color,
        style.borderColor,
        dragOver && "ring-2 ring-primary/50 border-primary/50 scale-[1.01]",
      )}
      onDragOver={handleDragOver}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={cn("w-3 h-3 rounded-full", style.dotColor)} />
          <span className="text-sm font-bold text-foreground">
            {t(style.labelKey)}
          </span>
          <Badge variant="outline" className="text-[10px] h-5">
            {t("layeredPush.peopleCount", { count: students.length })}
          </Badge>
        </div>
      </div>
      <p className="text-xs text-muted-foreground -mt-2">{t(style.subtitleKey)}</p>

      {/* Student list with drag */}
      <div>
        <div className="flex items-center gap-1.5 mb-2">
          <Users2 className="w-3.5 h-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-foreground">
            {t("layeredPush.studentList")}
          </span>
        </div>
        <ScrollArea className="h-[120px]">
          <div className="space-y-1">
            {students.length === 0 && (
              <p className="text-[11px] text-muted-foreground px-1 py-1">
                {t("layeredPush.noRoster")}
              </p>
            )}
            {students.map((s) => (
              <div
                key={s.id}
                draggable
                onDragStart={(e) => handleDragStart(e, s.id)}
                className="flex items-center gap-2 text-xs py-1 px-1.5 rounded-md cursor-grab active:cursor-grabbing hover:bg-background/80 transition-colors group"
              >
                <GripVertical className="w-3 h-3 text-muted-foreground/40 group-hover:text-muted-foreground shrink-0" />
                <div
                  className={cn(
                    "w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold text-white shrink-0",
                    style.dotColor,
                  )}
                >
                  {s.name[0]}
                </div>
                <span className="text-foreground">{s.name}</span>
                <span className="text-muted-foreground ml-auto">
                  {s.score == null
                    ? "—"
                    : t("layeredPush.scorePoints", { score: s.score })}
                </span>
                {s.dingtalk_synced && (
                  <span className="text-[10px] text-emerald-600" title="已同步钉钉">
                    ✓
                  </span>
                )}
              </div>
            ))}
          </div>
        </ScrollArea>
        <Button
          variant="ghost"
          size="sm"
          className="text-xs h-6 px-2 mt-1 text-primary"
          onClick={() => onRefreshRoster()}
        >
          {t("layeredPush.updateFromDingTalk")}
        </Button>
      </div>

      {/* Assignments */}
      <div data-tour="lp-assignments">
        <span className="text-xs font-medium text-foreground block mb-2">
          {t("layeredPush.assignmentLabel")}
        </span>
        <div className="space-y-2">
          {content.assignments.length === 0 && (
            <p className="text-[11px] text-muted-foreground">
              {t("layeredPush.assignmentEmpty")}
            </p>
          )}
          {content.assignments.map((a, idx) => (
            <div
              key={`${a.title}-${idx}`}
              className="rounded-lg bg-background/60 border border-border/30 p-2.5 group"
            >
              <div className="flex items-center gap-1.5 mb-0.5">
                {a.icon && <span className="text-sm">{a.icon}</span>}
                <span className="text-xs font-semibold text-foreground">
                  {a.title}
                </span>
                <button
                  className="ml-auto text-muted-foreground/50 hover:text-destructive opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={() => removeAssignment(idx)}
                  title={t("layeredPush.remove")}
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
              {a.desc && (
                <p className="text-[11px] text-muted-foreground">{a.desc}</p>
              )}
            </div>
          ))}
        </div>

        {/* 手动添加任务 */}
        <div className="space-y-1.5 mt-2">
          <Input
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder={t("layeredPush.assignmentTitlePh")}
            className="h-7 text-xs"
          />
          <Input
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
            placeholder={t("layeredPush.assignmentDescPh")}
            className="h-7 text-xs"
            onKeyDown={(e) => e.key === "Enter" && addAssignment()}
          />
        </div>

        <div className="flex gap-2 mt-2 flex-wrap">
          <Button
            variant="outline"
            size="sm"
            className="text-xs h-7 gap-1"
            onClick={addAssignment}
            disabled={!newTitle.trim()}
          >
            <Plus className="w-3 h-3" /> {t("layeredPush.addAssignment")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="text-xs h-7 gap-1"
            onClick={() => setExamOpen(true)}
          >
            <Library className="w-3 h-3" /> {t("layeredPush.fromQuestionBank")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="text-xs h-7 gap-1"
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload className="w-3 h-3" /> {t("layeredPush.uploadFile")}
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => handleUpload(e.target.files)}
          />
        </div>

        {/* 材料（可下载） */}
        {content.materials.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap mt-2">
            <span className="text-[11px] text-muted-foreground">
              {t("layeredPush.materialsLabel")}
            </span>
            {content.materials.map((m) => (
              <span
                key={m.name}
                className="inline-flex items-center gap-1 rounded-md bg-background/70 border border-border/40 px-1.5 py-0.5 text-[10px] text-foreground group"
              >
                <button
                  className="hover:text-primary inline-flex items-center gap-0.5 max-w-[130px] truncate"
                  title={t("layeredPush.materialDownload")}
                  onClick={() => downloadMaterial(m.name, m.url)}
                >
                  <Download className="w-3 h-3 shrink-0" />
                  <span className="truncate">{m.name}</span>
                </button>
                <button
                  className="text-muted-foreground/50 hover:text-destructive"
                  onClick={() =>
                    onContentChange({
                      materials: content.materials.filter((x) => x.name !== m.name),
                    })
                  }
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Time & settings */}
      <div className="space-y-2 mt-auto">
        <div className="flex items-center gap-2 text-xs">
          <Clock className="w-3.5 h-3.5 text-muted-foreground" />
          <span className="text-muted-foreground">
            {t("layeredPush.estimatedTime")}
          </span>
          <Input
            type="number"
            min={5}
            max={600}
            value={content.estimated_minutes}
            onChange={(e) => patchMinutes(e.target.value)}
            className="h-6 w-16 text-xs px-1.5"
          />
          <span className="text-muted-foreground">
            {t("layeredPush.minutesUnitShort")}
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <Clock className="w-3.5 h-3.5 text-muted-foreground" />
          <span className="text-muted-foreground">
            {t("layeredPush.deadlineLabel")}
          </span>
          <select
            value={content.deadline_weekday}
            onChange={(e) =>
              onContentChange({ deadline_weekday: Number(e.target.value) })
            }
            className="h-6 rounded-md border border-input bg-background px-1.5 text-xs text-foreground"
          >
            {WEEKDAY_KEYS.slice(1).map((key, i) => (
              <option key={key} value={i + 1}>
                {t(key)}
              </option>
            ))}
          </select>
          <Input
            type="time"
            value={content.deadline_time}
            onChange={(e) => onContentChange({ deadline_time: e.target.value })}
            className="h-6 w-24 text-xs px-1.5"
          />
        </div>

        <div
          className="pt-2 border-t border-border/30 space-y-1.5"
          data-tour="lp-dingtalk-settings"
        >
          <span className="text-xs font-medium text-foreground">
            {t("layeredPush.dingTalkSettings")}
          </span>
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
            <Checkbox
              checked={content.require_parent_sign}
              onCheckedChange={(v) =>
                onContentChange({ require_parent_sign: v === true })
              }
              className="w-3.5 h-3.5"
            />{" "}
            {t("layeredPush.requireParentSign")}
          </label>
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
            <Checkbox
              checked={content.require_photo}
              onCheckedChange={(v) => onContentChange({ require_photo: v === true })}
              className="w-3.5 h-3.5"
            />{" "}
            {t("layeredPush.requirePhoto")}
          </label>
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
            <Checkbox
              checked={content.require_voice}
              onCheckedChange={(v) => onContentChange({ require_voice: v === true })}
              className="w-3.5 h-3.5"
            />{" "}
            {t("layeredPush.requireVoice")}
          </label>
        </div>
      </div>

      {/* 从试卷库选 */}
      <Dialog open={examOpen} onOpenChange={setExamOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("layeredPush.pickExamTitle")}</DialogTitle>
          </DialogHeader>
          <div className="max-h-[320px] overflow-y-auto space-y-1.5">
            {examsQuery.isLoading && (
              <p className="text-xs text-muted-foreground">
                {t("layeredPush.loading")}
              </p>
            )}
            {examsQuery.data && examsQuery.data.length === 0 && (
              <p className="text-xs text-muted-foreground">
                {t("layeredPush.examEmpty")}
              </p>
            )}
            {examsQuery.data?.map((ex) => (
              <button
                key={ex.id}
                className="w-full text-left rounded-lg border border-border/50 bg-background px-3 py-2 hover:border-primary/50 transition-colors"
                onClick={() => addExam(ex.title, ex.exam_date, ex.id)}
              >
                <p className="text-xs font-medium text-foreground">{ex.title}</p>
                <p className="text-[11px] text-muted-foreground">
                  {ex.exam_date} · {ex.total_score}
                  {t("layeredPush.totalScoreUnit")}
                </p>
              </button>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setExamOpen(false)}>
              {t("common.cancel")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
