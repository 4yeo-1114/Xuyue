import { useEffect, useMemo, useState, useRef } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  BarChart3,
  BookOpen,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  Clock3,
  Download,
  FileInput,
  FileText,
  History,
  Loader2,
  MessageSquareText,
  PenLine,
  Presentation,
  RefreshCw,
  Route,
  Sparkles,
  Target,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { PrivacyNoticeDialog } from "@/components/common/PrivacyNoticeDialog";
import { AIGeneratedBadge } from "@/components/common/AIGeneratedBadge";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { translateSubjectName } from "@/i18n";
import { gradingImageUrl } from "@/services/gradingApi";
import {
  generateClassReviewPostClass,
  generateClassReviewPptx,
  getClassReviewReport,
  importClassReviewExams,
  listClassReviewImportableExams,
  listClassReviewSessions,
  listClassReviewSubjects,
  type ClassReviewReport,
  type ClassReviewSessionItem,
  type TargetedExamOption,
} from "@/services/api";
import { toast } from "sonner";
import {
  exportClassReviewPdf,
  hasConsolidationContent,
  hasReviewPlanContent,
  type ClassReviewPdfKind,
} from "@/utils/classReviewPdfExport";

interface ClassReviewPageProps {
  selectedSubject: string;
  selectedClass: string;
  schoolLevel: string;
  onNavChange: (id: string) => void;
  /** 讲评历史：点击某条历史记录时，切换到对应班级+科目并加载该讲评 */
  onOpenSession?: (classId: string, subject: string) => void;
}

const FALLBACK_SUBJECTS = [
  "语文",
  "数学",
  "英语",
  "科学",
  "物理",
  "化学",
  "生物",
  "历史",
  "地理",
  "政治",
];
const SUBJECT_STORAGE_PREFIX = "class-review-subject:";

function asArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((x) => String(x ?? "").trim()).filter(Boolean);
}

function SectionList({
  items,
  empty,
  tone = "slate",
}: {
  items?: unknown;
  empty?: string;
  tone?: "slate" | "blue" | "amber" | "green" | "rose";
}) {
  const { t } = useLocale();
  const emptyText = empty ?? t("classReview.emptyContent");
  const list = asArray(items);
  const toneClass = {
    slate: "border-border bg-muted/20",
    blue: "border-sky-200 bg-sky-50 text-sky-950",
    amber: "border-amber-200 bg-amber-50 text-amber-950",
    green: "border-emerald-200 bg-emerald-50 text-emerald-950",
    rose: "border-rose-200 bg-rose-50 text-rose-950",
  }[tone];
  if (!list.length)
    return <p className="text-sm text-muted-foreground">{emptyText}</p>;
  return (
    <div className="space-y-2">
      {list.map((item, index) => (
        <div
          key={`${item}-${index}`}
          className={cn(
            "rounded-md border px-3 py-2 text-sm leading-relaxed",
            toneClass,
          )}
        >
          {item}
        </div>
      ))}
    </div>
  );
}

function StatCard({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  icon: any;
}) {
  return (
    <div className="min-w-[118px] rounded-lg border border-sky-200 bg-white/85 px-3 py-2 shadow-sm transition-all duration-300 hover:-translate-y-0.5 hover:shadow-md">
      <div className="flex items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-sky-100 text-sky-700">
          <Icon className="h-3.5 w-3.5" />
        </span>
        <div>
          <p className="text-[11px] text-muted-foreground">{label}</p>
          <p className="text-base font-black leading-tight text-foreground">
            {value ?? "-"}
          </p>
        </div>
      </div>
    </div>
  );
}

function InsightPanel({
  title,
  items,
  icon: Icon,
  tone,
}: {
  title: string;
  items?: unknown;
  icon: any;
  tone: "rose" | "green" | "blue";
}) {
  const { t } = useLocale();
  const list = asArray(items);
  const toneClass = {
    rose: "border-rose-200 bg-rose-50/80 text-rose-950",
    green: "border-emerald-200 bg-emerald-50/80 text-emerald-950",
    blue: "border-sky-200 bg-sky-50/80 text-sky-950",
  }[tone];
  const iconClass = {
    rose: "bg-rose-100 text-rose-700",
    green: "bg-emerald-100 text-emerald-700",
    blue: "bg-sky-100 text-sky-700",
  }[tone];
  return (
    <div
      className={cn(
        "rounded-xl border p-4 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-md",
        toneClass,
      )}
    >
      <div className="mb-3 flex items-center gap-2">
        <span
          className={cn(
            "flex h-8 w-8 items-center justify-center rounded-lg",
            iconClass,
          )}
        >
          <Icon className="h-4 w-4" />
        </span>
        <p className="text-sm font-bold">{title}</p>
      </div>
      <div className="space-y-2">
        {list.length ? (
          list.slice(0, 5).map((item, index) => (
            <div
              key={`${item}-${index}`}
              className="rounded-lg bg-white/70 px-3 py-2 text-sm leading-relaxed shadow-sm"
            >
              {item}
            </div>
          ))
        ) : (
          <p className="text-sm opacity-70">{t("classReview.emptyContent")}</p>
        )}
      </div>
    </div>
  );
}

function KeyPointShowcase({ items }: { items?: unknown }) {
  const { t } = useLocale();
  const points = asArray(items);
  const palettes = [
    "from-amber-100 via-white to-sky-100 border-amber-200 text-amber-950",
    "from-sky-100 via-white to-emerald-100 border-sky-200 text-sky-950",
    "from-violet-100 via-white to-rose-100 border-violet-200 text-violet-950",
    "from-emerald-100 via-white to-amber-100 border-emerald-200 text-emerald-950",
  ];
  return (
    <div className="relative overflow-hidden rounded-xl border border-primary/20 bg-gradient-to-br from-primary/10 via-background to-amber-50 p-5 shadow-card">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/60 to-transparent" />
      <div className="pointer-events-none absolute -left-1/3 top-0 h-full w-1/3 animate-shimmer bg-gradient-to-r from-transparent via-white/50 to-transparent" />
      <div className="relative z-10 mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-lg font-black text-foreground">
            <Brain className="h-5 w-5 text-primary" />
            {t("classReview.focus.title")}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("classReview.focus.subtitle")}
          </p>
        </div>
        <Badge className="bg-primary text-primary-foreground">
          {t("classReview.focus.count", { count: points.length || 0 })}
        </Badge>
      </div>
      {points.length ? (
        <div className="relative z-10 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {points.slice(0, 8).map((point, index) => (
            <div
              key={`${point}-${index}`}
              className={cn(
                "group relative overflow-hidden rounded-xl border bg-gradient-to-br p-4 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-lg",
                palettes[index % palettes.length],
              )}
            >
              <div className="absolute right-3 top-3 text-4xl font-black opacity-10">
                {String(index + 1).padStart(2, "0")}
              </div>
              <div className="relative z-10">
                <div className="mb-3 flex h-8 w-8 items-center justify-center rounded-lg bg-white/75 text-sm font-black shadow-sm">
                  {index + 1}
                </div>
                <p className="text-[15px] font-bold leading-relaxed">{point}</p>
                <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/70">
                  <div className="h-full w-2/3 rounded-full bg-current opacity-50 transition-all duration-500 group-hover:w-full" />
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="relative z-10 rounded-lg border border-dashed bg-white/60 p-4 text-sm text-muted-foreground">
          {t("classReview.focus.empty")}
        </div>
      )}
    </div>
  );
}

function TeachingTimeline({ flow }: { flow?: unknown }) {
  const { t } = useLocale();
  const steps = Array.isArray(flow) ? flow : [];
  if (!steps.length)
    return (
      <p className="text-sm text-muted-foreground">
        {t("classReview.timeline.empty")}
      </p>
    );
  return (
    <div className="relative space-y-3 pl-5">
      <div className="absolute bottom-3 left-2 top-3 w-px bg-gradient-to-b from-primary via-sky-300 to-emerald-300" />
      {steps.map((step: any, index: number) => (
        <div
          key={index}
          className="relative rounded-xl border bg-card p-4 shadow-sm transition-all duration-300 hover:-translate-y-0.5 hover:shadow-md"
        >
          <span className="absolute -left-[23px] top-5 flex h-5 w-5 items-center justify-center rounded-full border-2 border-background bg-primary text-[10px] font-bold text-primary-foreground">
            {index + 1}
          </span>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-bold text-foreground">
              {step.step ||
                t("classReview.timeline.step", { index: index + 1 })}
            </p>
            <Badge variant="secondary" className="gap-1">
              <Clock3 className="h-3 w-3" />
              {t("classReview.timeline.minutes", {
                value: step.minutes || "-",
              })}
            </Badge>
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            <div className="rounded-lg bg-sky-50 px-3 py-2 text-sm text-sky-950">
              <span className="font-semibold">
                {t("classReview.timeline.teacher")}
              </span>
              {step.teacher_action || t("classReview.timeline.none")}
            </div>
            <div className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-950">
              <span className="font-semibold">
                {t("classReview.timeline.student")}
              </span>
              {step.student_action || t("classReview.timeline.none")}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function ImportExamDialog({
  open,
  onOpenChange,
  classId,
  subject,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  classId: string;
  subject: string;
}) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [noticeOpen, setNoticeOpen] = useState(false);
  const {
    data: exams = [],
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["class-review-importable-exams", classId, subject],
    queryFn: () => listClassReviewImportableExams(classId, subject),
    enabled: open && !!classId && !!subject,
  });

  useEffect(() => {
    if (!open) setSelectedIds(new Set());
  }, [open]);

  const mutation = useMutation({
    mutationFn: () =>
      importClassReviewExams({
        class_id: classId,
        subject,
        exam_folder_names: Array.from(selectedIds),
      }),
    onSuccess: (res) => {
      if (res.pending) {
        toast.warning(t("classReview.import.pending"), {
          description: t("classReview.import.pendingDesc"),
        });
        return;
      }
      toast.success(t("classReview.import.success"), {
        description:
          res.ignored_count > 0
            ? t("classReview.import.ignored", { count: res.ignored_count })
            : undefined,
      });
      queryClient.invalidateQueries({
        queryKey: ["class-review-report", classId, subject],
      });
      onOpenChange(false);
    },
    onError: (err: any) => {
      toast.error(t("classReview.import.failed"), {
        description: err?.message || t("classReview.retry"),
      });
    },
  });

  const toggle = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={(v) => !mutation.isPending && onOpenChange(v)}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{t("classReview.import.title")}</DialogTitle>
            <DialogDescription>
              {t("classReview.import.description")}
            </DialogDescription>
          </DialogHeader>
          <div className="py-2">
            {isLoading ? (
              <div className="flex flex-col items-center justify-center py-10 text-muted-foreground">
                <Loader2 className="mb-2 h-6 w-6 animate-spin" />
                <p className="text-sm">{t("classReview.import.loading")}</p>
              </div>
            ) : isError ? (
              <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed bg-muted/20 py-10 text-muted-foreground">
                <AlertTriangle className="mb-1 h-8 w-8 opacity-40" />
                <p className="text-sm">{t("classReview.import.loadFailed")}</p>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5"
                  onClick={() => refetch()}
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  {t("wuyu.retry")}
                </Button>
              </div>
            ) : exams.length === 0 ? (
              <div className="flex flex-col items-center justify-center rounded-lg border border-dashed bg-muted/20 py-10 text-muted-foreground">
                <FileText className="mb-2 h-8 w-8 opacity-30" />
                <p className="text-sm">{t("classReview.import.empty")}</p>
              </div>
            ) : (
              <ScrollArea className="h-[320px] pr-3">
                <div className="space-y-2">
                  {exams.map((exam: TargetedExamOption) => {
                    const selected = selectedIds.has(exam.id);
                    return (
                      <button
                        key={exam.id}
                        type="button"
                        onClick={() => toggle(exam.id)}
                        className={cn(
                          "flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-colors",
                          selected
                            ? "border-primary bg-primary/5"
                            : "border-border bg-card hover:bg-muted/50",
                        )}
                      >
                        <Checkbox
                          checked={selected}
                          onCheckedChange={() => toggle(exam.id)}
                          onClick={(e) => e.stopPropagation()}
                        />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium">
                            {exam.name}
                          </p>
                          <p className="mt-0.5 text-xs text-muted-foreground">
                            {t("classReview.import.graded", {
                              count: exam.completed_count,
                            })}
                          </p>
                        </div>
                        <Badge
                          variant={selected ? "default" : "secondary"}
                          className="text-[10px]"
                        >
                          {selected
                            ? t("classReview.import.selected")
                            : t("classReview.import.available")}
                        </Badge>
                      </button>
                    );
                  })}
                </div>
              </ScrollArea>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={mutation.isPending}
            >
              {t("classReview.cancel")}
            </Button>
            <Button
              onClick={() => setNoticeOpen(true)}
              disabled={selectedIds.size === 0 || mutation.isPending}
            >
              {mutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              {mutation.isPending
                ? t("classReview.import.analyzing")
                : t("classReview.import.confirm", { count: selectedIds.size })}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <PrivacyNoticeDialog
        open={noticeOpen}
        onOpenChange={setNoticeOpen}
        onConfirm={() => mutation.mutate()}
        context="课堂回顾"
      />
    </>
  );
}

function PostClassDialog({
  open,
  onOpenChange,
  classId,
  subject,
  report,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  classId: string;
  subject: string;
  report: ClassReviewReport | null;
}) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const keyPoints = asArray(report?.pre_class?.review_plan?.key_points);
  const weakPoints = asArray(report?.pre_class?.overview?.weak_points);
  const options = Array.from(new Set([...keyPoints, ...weakPoints]));
  const [taught, setTaught] = useState<Set<string>>(new Set());
  const [mastered, setMastered] = useState<Set<string>>(new Set());
  const [unresolved, setUnresolved] = useState<Set<string>>(new Set());
  const [overall, setOverall] = useState<
    "excellent" | "met" | "partial" | "reteach"
  >("met");
  const [notes, setNotes] = useState("");
  const [noticeOpen, setNoticeOpen] = useState(false);

  useEffect(() => {
    if (!open) {
      setTaught(new Set());
      setMastered(new Set());
      setUnresolved(new Set());
      setOverall("met");
      setNotes("");
    }
  }, [open]);

  const mutation = useMutation({
    mutationFn: () =>
      generateClassReviewPostClass({
        class_id: classId,
        subject,
        taught_points: Array.from(taught),
        mastered_points: Array.from(mastered),
        unresolved_points: Array.from(unresolved),
        overall_effect: t(`classReview.post.effect.${overall}`),
        teacher_notes: notes,
      }),
    onSuccess: () => {
      toast.success(t("classReview.post.success"));
      queryClient.invalidateQueries({
        queryKey: ["class-review-report", classId, subject],
      });
      onOpenChange(false);
    },
    onError: (err: any) => {
      toast.error(t("classReview.post.failed"), {
        description: err?.message || t("classReview.retry"),
      });
    },
  });

  const toggle = (
    setter: (v: Set<string>) => void,
    current: Set<string>,
    item: string,
  ) => {
    const next = new Set(current);
    if (next.has(item)) next.delete(item);
    else next.add(item);
    setter(next);
  };

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={(v) => !mutation.isPending && onOpenChange(v)}
      >
        <DialogContent className="flex max-h-[86vh] flex-col overflow-hidden sm:max-w-3xl">
          <DialogHeader className="shrink-0">
            <DialogTitle>{t("classReview.post.title")}</DialogTitle>
            <DialogDescription>
              {t("classReview.post.description")}
            </DialogDescription>
          </DialogHeader>
          <div className="min-h-0 flex-1 overflow-y-auto pr-3">
            <div className="space-y-4 py-2">
              <div className="grid gap-3 md:grid-cols-3">
                {[
                  {
                    title: t("classReview.post.taught"),
                    set: taught,
                    setter: setTaught,
                  },
                  {
                    title: t("classReview.post.mastered"),
                    set: mastered,
                    setter: setMastered,
                  },
                  {
                    title: t("classReview.post.unresolved"),
                    set: unresolved,
                    setter: setUnresolved,
                  },
                ].map((group) => (
                  <div
                    key={group.title}
                    className="rounded-xl border bg-card/80 p-3 shadow-sm"
                  >
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <p className="text-sm font-semibold">{group.title}</p>
                      <Badge variant="secondary" className="text-[10px]">
                        {group.set.size}/{options.length}
                      </Badge>
                    </div>
                    <div className="max-h-[260px] overflow-y-auto pr-2">
                      <div className="space-y-2">
                        {options.length ? (
                          options.map((item) => (
                            <label
                              key={item}
                              className="flex items-start gap-2 rounded-md px-2 py-1.5 text-xs transition-colors hover:bg-muted/60"
                            >
                              <Checkbox
                                checked={group.set.has(item)}
                                onCheckedChange={() =>
                                  toggle(group.setter, group.set, item)
                                }
                              />
                              <span className="leading-relaxed">{item}</span>
                            </label>
                          ))
                        ) : (
                          <p className="text-xs text-muted-foreground">
                            {t("classReview.post.importFirst")}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="space-y-2">
                <Label>{t("classReview.post.overall")}</Label>
                <Select
                  value={overall}
                  onValueChange={(value) => setOverall(value as typeof overall)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="excellent">
                      {t("classReview.post.effect.excellent")}
                    </SelectItem>
                    <SelectItem value="met">
                      {t("classReview.post.effect.met")}
                    </SelectItem>
                    <SelectItem value="partial">
                      {t("classReview.post.effect.partial")}
                    </SelectItem>
                    <SelectItem value="reteach">
                      {t("classReview.post.effect.reteach")}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>{t("classReview.post.notes")}</Label>
                <Textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder={t("classReview.post.notesPlaceholder")}
                  className="min-h-[110px]"
                />
              </div>
            </div>
          </div>
          <DialogFooter className="shrink-0 border-t pt-4">
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={mutation.isPending}
            >
              {t("classReview.cancel")}
            </Button>
            <Button
              onClick={() => setNoticeOpen(true)}
              disabled={mutation.isPending || !report}
            >
              {mutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              {t("classReview.post.generate")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <PrivacyNoticeDialog
        open={noticeOpen}
        onOpenChange={setNoticeOpen}
        onConfirm={() => mutation.mutate()}
        context="课后讲评"
      />
    </>
  );
}

export function ClassReviewPage({
  selectedSubject,
  selectedClass,
  onOpenSession,
}: ClassReviewPageProps) {
  const { t, locale } = useLocale();

  const storageKey = `${SUBJECT_STORAGE_PREFIX}${selectedClass}`;
  const [subject, setSubject] = useState(() => {
    try {
      return localStorage.getItem(storageKey) || selectedSubject || "语文";
    } catch {
      return selectedSubject || "语文";
    }
  });
  const [importOpen, setImportOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [postOpen, setPostOpen] = useState(false);
  const [exportingKind, setExportingKind] = useState<ClassReviewPdfKind | null>(
    null,
  );

  const { data: subjectOptions = FALLBACK_SUBJECTS } = useQuery({
    queryKey: ["class-review-subjects"],
    queryFn: listClassReviewSubjects,
  });
  const availableSubjects = useMemo(() => {
    const base = subjectOptions.length ? subjectOptions : FALLBACK_SUBJECTS;
    return base.includes(subject) ? base : [subject, ...base];
  }, [subject, subjectOptions]);

  const lastGlobalSubject = useRef(selectedSubject);

  // Handle external selectedSubject changes
  useEffect(() => {
    if (selectedSubject && selectedSubject !== lastGlobalSubject.current) {
      setSubject(selectedSubject);
      lastGlobalSubject.current = selectedSubject;
    }
  }, [selectedSubject]);

  // 切换班级时按班级键回读该班级已存的科目偏好（key 已带 classId），
  // 避免沿用上一班级的科目并覆盖新班级已存偏好。必须在写入 effect 之前声明。
  useEffect(() => {
    let saved: string | null = null;
    try {
      saved = localStorage.getItem(storageKey);
    } catch {
      // ignore
    }
    setSubject(saved || selectedSubject || "语文");
    lastGlobalSubject.current = selectedSubject;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedClass]);

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, subject);
    } catch {
      // ignore
    }
  }, [storageKey, subject]);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["class-review-report", selectedClass, subject],
    queryFn: () => getClassReviewReport(selectedClass, subject),
    enabled: !!selectedClass && !!subject,
  });

  // 讲评历史列表：打开抽屉时按需加载
  const {
    data: sessions = [],
    isLoading: sessionsLoading,
    isError: sessionsError,
    refetch: refetchSessions,
  } = useQuery({
    queryKey: ["class-review-sessions"],
    queryFn: listClassReviewSessions,
    enabled: historyOpen,
  });

  const report = data?.report || null;
  const preClass = report?.pre_class || {};
  const overview = preClass.overview || {};
  const plan = preClass.review_plan || {};
  const cards = Array.isArray(preClass.question_cards)
    ? preClass.question_cards
    : [];
  const summary = report?.source_summary || {};
  const questionAccuracy = Array.isArray(summary.question_accuracy)
    ? summary.question_accuracy
    : [];
  const questionStudents = summary.question_students || {};
  const tracking = report?.tracking || {};
  const consolidation = report?.consolidation || {};
  const allWrongImages = preClass.all_wrong_images || [];

  // Group wrong images by student
  const studentWrongImages = allWrongImages.reduce((acc: any, img: any) => {
    if (!acc[img.student_name]) {
      acc[img.student_name] = [];
    }
    acc[img.student_name].push(img);
    return acc;
  }, {});

  const studentNames = Object.keys(studentWrongImages);

  const [wrongImageStudent, setWrongImageStudent] = useState<string | null>(
    null,
  );
  /** 点准确率卡片展开的题目集合（question_key），每题独立展开/收起，互不影响 */
  const [expandedAccuracyKeys, setExpandedAccuracyKeys] = useState<Set<string>>(
    new Set(),
  );
  /** 仅用户主动查看「错题关联」时才加载图片，避免影响 PDF 导出 */
  const [wrongImagesActive, setWrongImagesActive] = useState(false);
  /** 生成讲评 PPT 的加载态（PPT 生成较慢，独立于 PDF 导出） */
  const [pptGenerating, setPptGenerating] = useState(false);

  const reviewPlanExportable = hasReviewPlanContent(report);
  const consolidationExportable = hasConsolidationContent(report);

  const handleExportPdf = async (kind: ClassReviewPdfKind) => {
    if (!report || exportingKind) return;
    if (kind === "review_plan" && !reviewPlanExportable) return;
    if (kind === "consolidation" && !consolidationExportable) return;
    setExportingKind(kind);
    try {
      await exportClassReviewPdf(kind, report, subject);
      toast.success(
        kind === "review_plan"
          ? t("classReview.export.reviewSuccess")
          : t("classReview.export.consolidationSuccess"),
      );
    } catch (err: any) {
      toast.error(t("classReview.export.failed"), {
        description: err?.message || t("classReview.retry"),
      });
    } finally {
      setExportingKind(null);
    }
  };

  const downloadPpt = (blob: Blob, baseName: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const date = new Date().toLocaleDateString("zh-CN").replace(/\//g, "-");
    a.href = url;
    a.download = `${baseName}_${date}.pptx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const handleGeneratePpt = async () => {
    if (!report || pptGenerating || exportingKind) return;
    setPptGenerating(true);
    try {
      const blob = await generateClassReviewPptx(selectedClass, subject);
      downloadPpt(blob, `${subject}_课堂讲评PPT`);
      toast.success(t("classReview.generatePpt.success"));
    } catch (err: any) {
      toast.error(t("classReview.generatePpt.failed"), {
        description: err?.message || t("classReview.retry"),
      });
    } finally {
      setPptGenerating(false);
    }
  };

  /** 单题 PPT：由「原题」旁的按钮触发，传入该题 question_key */
  const handleGenerateQuestionPpt = async (q: any, title: string) => {
    if (!report || pptGenerating || exportingKind) return;
    setPptGenerating(true);
    try {
      const blob = await generateClassReviewPptx(
        selectedClass,
        subject,
        q.question_key,
      );
      downloadPpt(blob, `${title}_讲评PPT`);
      toast.success(t("classReview.generatePpt.success"));
    } catch (err: any) {
      toast.error(t("classReview.generatePpt.failed"), {
        description: err?.message || t("classReview.retry"),
      });
    } finally {
      setPptGenerating(false);
    }
  };

  const activateWrongImages = (studentName?: string) => {
    setWrongImagesActive(true);
    if (studentName) setWrongImageStudent(studentName);
    else if (!wrongImageStudent && studentNames.length > 0)
      setWrongImageStudent(studentNames[0]);
  };

  return (
    <div className="space-y-5 pb-6 animate-fade-in">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <Presentation className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h2 className="flex items-center gap-2 text-xl font-bold text-foreground">
              {t("classReview.title")}
              <Badge variant="secondary" className="text-[11px] font-normal">
                {translateSubjectName(locale, subject)}
              </Badge>
            </h2>
            <p className="text-sm text-muted-foreground">
              {t("classReview.subtitle")}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={subject} onValueChange={setSubject}>
            <SelectTrigger className="h-9 w-[140px] text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {availableSubjects.map((item) => (
                <SelectItem key={item} value={item}>
                  {translateSubjectName(locale, item)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={() => setPostOpen(true)}
            disabled={!report}
          >
            <ClipboardCheck className="h-4 w-4" />
            {t("classReview.classEffect")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={handleGeneratePpt}
            disabled={!report || !!pptGenerating || !!exportingKind}
          >
            {pptGenerating ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Presentation className="h-4 w-4" />
            )}
            {t("classReview.generatePpt")}
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="gap-2"
                disabled={!report || !!exportingKind}
              >
                {exportingKind ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Download className="h-4 w-4" />
                )}
                {t("classReview.exportPdf")}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-40">
              <DropdownMenuItem
                disabled={!reviewPlanExportable || !!exportingKind}
                onClick={() => handleExportPdf("review_plan")}
              >
                {t("classReview.reviewPlan")}
              </DropdownMenuItem>
              <DropdownMenuItem
                disabled={!consolidationExportable || !!exportingKind}
                onClick={() => handleExportPdf("consolidation")}
              >
                {t("classReview.consolidation")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={() => setHistoryOpen(true)}
          >
            <History className="h-4 w-4" />
            {t("classReview.history")}
          </Button>
          <Button
            size="sm"
            className="gap-2"
            onClick={() => setImportOpen(true)}
          >
            <FileInput className="h-4 w-4" />
            {t("classReview.importExams")}
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex h-[400px] flex-col items-center justify-center gap-3 text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin" />
          <p className="text-sm">{t("common.loading")}</p>
        </div>
      ) : isError ? (
        <div className="flex h-[400px] flex-col items-center justify-center gap-4 text-center">
          <div className="rounded-full bg-destructive/10 p-4">
            <AlertTriangle className="h-8 w-8 text-destructive" />
          </div>
          <div>
            <h3 className="font-semibold text-foreground">
              {t("classDetail.reviewReportLoadFailed")}
            </h3>
            <p className="mt-1 text-sm text-muted-foreground max-w-[280px]">
              {t("classDetail.checkNetworkAndRetry")}
            </p>
          </div>
          <Button variant="outline" className="gap-2" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4" />
            {t("wuyu.retry")}
          </Button>
        </div>
      ) : !report ? (
        <div className="flex h-[400px] flex-col items-center justify-center gap-4 text-center">
          <div className="rounded-full bg-muted/30 p-4">
            <BookOpen className="h-8 w-8 text-muted-foreground/50" />
          </div>
          <div>
            <h3 className="font-semibold text-foreground">
              {t("classReview.emptyTitle", {
                subject: translateSubjectName(locale, subject),
              })}
            </h3>
            <p className="mt-1 text-sm text-muted-foreground max-w-[280px]">
              {t("classReview.emptyDescription")}
            </p>
          </div>
          <Button
            onClick={() => setImportOpen(true)}
            className="mt-2 bg-gradient-to-r from-emerald-500 to-sky-500 hover:from-emerald-600 hover:to-sky-600 text-white"
          >
            {t("classReview.emptyAction")}
          </Button>
        </div>
      ) : (
        <>
          <Card className="overflow-hidden border-sky-200 bg-gradient-to-r from-sky-50 via-white to-emerald-50/70 shadow-sm">
            <CardContent className="p-4">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="min-w-0 flex-1">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-sky-100 text-sky-700">
                      <FileText className="h-4 w-4" />
                    </span>
                    <div>
                      <p className="text-base font-bold text-foreground">
                        {t("classReview.dataBasis")}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {t("classReview.dataBasisSubtitle")}
                      </p>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {(report.exam_names || []).map((name) => (
                      <Badge
                        key={name}
                        variant="secondary"
                        className="border border-sky-200 bg-white/80 text-sky-900"
                      >
                        {name}
                      </Badge>
                    ))}
                  </div>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2 lg:justify-end">
                  <StatCard
                    label={t("classReview.importExams")}
                    value={report.exam_names?.length || 0}
                    icon={FileText}
                  />
                  <StatCard
                    label={t("classReview.validStudents")}
                    value={summary.valid_student_count || 0}
                    icon={CheckCircle2}
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="overflow-hidden border-amber-200/80 bg-gradient-to-br from-amber-50/40 via-white to-sky-50/40 shadow-sm">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-base flex items-center gap-2">
                    <BarChart3 className="h-5 w-5 text-amber-500" />
                    {t("classReview.accuracy.title")}
                  </CardTitle>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {t("classReview.accuracy.subtitle")}
                  </p>
                </div>
                <Badge variant="secondary" className="shrink-0">
                  {questionAccuracy.length}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              {questionAccuracy.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  {t("classReview.accuracy.empty")}
                </p>
              ) : (
                <div className="grid gap-2 md:grid-cols-2">
                  {questionAccuracy.map((q: any, idx: number) => {
                    const accuracy = Number(q.accuracy) || 0;
                    const correct = Number(q.correct_count) || 0;
                    const wrong = Number(q.wrong_count) || 0;
                    const blank = Number(q.blank_count) || 0;
                    // 题号优先用统分题号（real_number，如「三、2（1）」），
                    // 其次用后端给的 display_title（「第N题」）；不再用数组下标自编题号。
                    const title =
                      q.real_number ||
                      q.display_title ||
                      q.question_key;
                    const toneClass =
                      accuracy >= 80
                        ? "text-emerald-600"
                        : accuracy >= 60
                          ? "text-amber-600"
                          : "text-rose-600";
                    const barClass =
                      accuracy >= 80
                        ? "bg-emerald-500"
                        : accuracy >= 60
                          ? "bg-amber-500"
                          : "bg-rose-500";
                    const qKey = q.question_key || `${title}-${idx}`;
                    const students = questionStudents[q.question_key];
                    const isExpanded = expandedAccuracyKeys.has(qKey);
                    return (
                      <div
                        key={qKey}
                        className="cursor-pointer rounded-lg border border-border/60 bg-white/80 p-3 shadow-sm transition-all hover:shadow-md"
                        onClick={() =>
                          setExpandedAccuracyKeys((prev) => {
                            const next = new Set(prev);
                            if (next.has(qKey)) {
                              next.delete(qKey);
                            } else {
                              next.add(qKey);
                            }
                            return next;
                          })
                        }
                        title={t("classReview.accuracy.viewStudents")}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span
                            className="min-w-0 truncate text-sm font-medium"
                            title={title}
                          >
                            {title}
                          </span>
                          <span
                            className={cn(
                              "shrink-0 text-sm font-black",
                              toneClass,
                            )}
                          >
                            {accuracy}%
                          </span>
                        </div>
                        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                          <div
                            className={cn("h-full rounded-full", barClass)}
                            style={{ width: `${accuracy}%` }}
                          />
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                          <span className="text-emerald-600">
                            {t("classReview.accuracy.correct", {
                              count: correct,
                            })}
                          </span>
                          <span className="text-rose-500">
                            {t("classReview.accuracy.wrong", { count: wrong })}
                          </span>
                          {blank > 0 && (
                            <span>
                              {t("classReview.accuracy.blank", { count: blank })}
                            </span>
                          )}
                          <span className="ml-auto flex items-center gap-1">
                            {t("classReview.accuracy.total", {
                              count: correct + wrong + blank,
                            })}
                            {isExpanded ? (
                              <ChevronDown className="h-3.5 w-3.5" />
                            ) : (
                              <ChevronRight className="h-3.5 w-3.5" />
                            )}
                          </span>
                        </div>
                        {isExpanded && (
                          <div className="mt-2 space-y-2 border-t border-border/60 pt-2 text-xs">
                            {q.question_text ? (
                              <div className="rounded-md border border-border/50 bg-muted/30 p-2">
                                <div className="mb-1 flex items-center justify-between gap-1">
                                  <span className="flex items-center gap-1 text-[11px] font-medium text-muted-foreground">
                                    <BookOpen className="h-3.5 w-3.5" />
                                    原题
                                  </span>
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    className="h-6 gap-1 px-2 text-[11px]"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleGenerateQuestionPpt(q, title);
                                    }}
                                    disabled={!report || !!pptGenerating || !!exportingKind}
                                  >
                                    {pptGenerating ? (
                                      <Loader2 className="h-3 w-3 animate-spin" />
                                    ) : (
                                      <Presentation className="h-3 w-3" />
                                    )}
                                    {t("classReview.generateQuestionPpt")}
                                  </Button>
                                </div>
                                <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-foreground">
                                  {q.question_text}
                                </p>
                              </div>
                            ) : null}
                            {students &&
                            (students.correct_students?.length ||
                              students.wrong_students?.length ||
                              students.blank_students?.length) ? (
                              <>
                                {students.correct_students?.length > 0 && (
                                  <div className="flex gap-1.5">
                                    <span className="shrink-0 font-medium text-emerald-600">
                                      {t(
                                        "classReview.accuracy.correctStudents",
                                      )}
                                      （{students.correct_students.length}）
                                    </span>
                                    <span className="text-muted-foreground">
                                      {students.correct_students.join("、")}
                                    </span>
                                  </div>
                                )}
                                {students.wrong_students?.length > 0 && (
                                  <div className="flex gap-1.5">
                                    <span className="shrink-0 font-medium text-rose-500">
                                      {t("classReview.accuracy.wrongStudents")}（{students.wrong_students.length}）
                                    </span>
                                    <span className="text-muted-foreground">
                                      {students.wrong_students.join("、")}
                                    </span>
                                  </div>
                                )}
                                {students.blank_students?.length > 0 && (
                                  <div className="flex gap-1.5">
                                    <span className="shrink-0 font-medium text-muted-foreground">
                                      {t("classReview.accuracy.blankStudents")}（{students.blank_students.length}）
                                    </span>
                                    <span className="text-muted-foreground">
                                      {students.blank_students.join("、")}
                                    </span>
                                  </div>
                                )}
                              </>
                            ) : (
                              <span className="text-muted-foreground">
                                {t("classReview.accuracy.studentsEmpty")}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden border-primary/20 bg-gradient-to-br from-background via-sky-50/40 to-amber-50/50 shadow-card">
            <div className="pointer-events-none absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-amber-400 to-emerald-400" />
            <CardHeader className="pb-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
                      <Sparkles className="h-4 w-4" />
                    </span>
                    {t("classReview.generatedTitle")}
                    <AIGeneratedBadge />
                  </CardTitle>
                  <p className="mt-2 text-sm text-muted-foreground">
                    {t("classReview.generatedSubtitle")}
                  </p>
                </div>
                <div className="flex items-center gap-2 rounded-lg border bg-background/80 px-3 py-2 text-sm shadow-sm">
                  <Clock3 className="h-4 w-4 text-primary" />
                  <span>
                    {t("classReview.suggestedDuration", {
                      duration: plan.duration || t("classReview.pending"),
                    })}
                  </span>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="relative overflow-hidden rounded-xl border border-primary/20 bg-background/90 p-5 shadow-sm">
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/50 to-transparent" />
                <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold uppercase tracking-wide text-primary">
                      {t("classReview.brief")}
                    </p>
                    <p className="mt-2 text-lg font-bold leading-relaxed text-foreground">
                      {overview.summary || t("classReview.generatedSummary")}
                    </p>
                  </div>
                  <div className="grid min-w-[260px] grid-cols-2 gap-2 text-center text-xs">
                    <div className="rounded-lg bg-rose-50 px-3 py-2 text-rose-900">
                      <p className="text-muted-foreground">
                        {t("classReview.weaknesses")}
                      </p>
                      <p className="mt-1 text-lg font-black">
                        {asArray(overview.weak_points).length}
                      </p>
                    </div>
                    <div className="rounded-lg bg-emerald-50 px-3 py-2 text-emerald-900">
                      <p className="text-muted-foreground">
                        {t("classReview.strengths")}
                      </p>
                      <p className="mt-1 text-lg font-black">
                        {asArray(overview.strengths).length}
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              <KeyPointShowcase items={plan.key_points} />

              <div className="grid gap-4 lg:grid-cols-3">
                <InsightPanel
                  title={t("classReview.classWeaknesses")}
                  items={overview.weak_points}
                  icon={AlertTriangle}
                  tone="rose"
                />
                <InsightPanel
                  title={t("classReview.classStrengths")}
                  items={overview.strengths}
                  icon={CheckCircle2}
                  tone="green"
                />
                <InsightPanel
                  title={t("classReview.evidence")}
                  items={overview.data_basis}
                  icon={BarChart3}
                  tone="blue"
                />
              </div>

              <div className="grid gap-4 xl:grid-cols-[0.8fr_1.2fr]">
                <div className="space-y-4">
                  <div className="rounded-xl border bg-card p-4 shadow-sm transition-all duration-300 hover:shadow-md">
                    <p className="mb-3 flex items-center gap-2 text-sm font-bold">
                      <Target className="h-4 w-4 text-primary" />
                      {t("classReview.objectives")}
                    </p>
                    <SectionList items={plan.objectives} />
                  </div>
                  <div className="rounded-xl border bg-card p-4 shadow-sm transition-all duration-300 hover:shadow-md">
                    <p className="mb-3 flex items-center gap-2 text-sm font-bold">
                      <PenLine className="h-4 w-4 text-primary" />
                      {t("classReview.blackboard")}
                    </p>
                    <SectionList items={plan.blackboard_design} />
                  </div>
                  <div className="rounded-xl border bg-card p-4 shadow-sm transition-all duration-300 hover:shadow-md">
                    <p className="mb-3 flex items-center gap-2 text-sm font-bold">
                      <MessageSquareText className="h-4 w-4 text-primary" />
                      {t("classReview.interactions")}
                    </p>
                    <SectionList
                      items={plan.interaction_questions}
                      tone="blue"
                    />
                  </div>
                </div>
                <div className="rounded-xl border bg-background/80 p-4 shadow-sm">
                  <p className="mb-4 flex items-center gap-2 text-sm font-bold">
                    <Route className="h-4 w-4 text-primary" />
                    {t("classReview.timeline.title")}
                  </p>
                  <TeachingTimeline flow={plan.teaching_flow} />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card
            data-pdf-exclude
            onMouseEnter={() => setWrongImagesActive(true)}
          >
            <CardHeader>
              <CardTitle className="text-base">
                {t("classReview.wrongImages.title")}
              </CardTitle>
              <p className="text-sm text-muted-foreground mt-1">
                {t("classReview.wrongImages.description")}
              </p>
            </CardHeader>
            <CardContent>
              {studentNames.length > 0 ? (
                <div className="space-y-4">
                  <div className="flex flex-wrap gap-2">
                    {studentNames.map((name) => (
                      <Button
                        key={name}
                        variant={
                          wrongImageStudent === name ? "default" : "outline"
                        }
                        size="sm"
                        onClick={() => activateWrongImages(name)}
                        className="rounded-full"
                      >
                        {name}
                      </Button>
                    ))}
                  </div>

                  {wrongImagesActive &&
                    wrongImageStudent &&
                    studentWrongImages[wrongImageStudent] && (
                      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3 mt-4">
                        {studentWrongImages[wrongImageStudent].map(
                          (img: any, idx: number) => (
                            <div
                              key={idx}
                              className="group relative rounded-lg border border-border/60 bg-muted/10 overflow-hidden hover:border-primary/40 hover:shadow-sm transition-all"
                            >
                              <div className="absolute top-2 left-2 bg-background/90 backdrop-blur-sm text-xs font-medium px-2 py-1 rounded shadow-sm z-10 border border-border/50">
                                {img.title}
                              </div>
                              <div className="h-32 md:h-40 bg-muted/30 relative flex items-center justify-center p-2">
                                {img.image_url ? (
                                  <img
                                    src={gradingImageUrl(img.image_url)}
                                    alt={img.title}
                                    className="max-w-full max-h-full object-contain rounded-sm mix-blend-multiply"
                                    onError={(e) => {
                                      (
                                        e.target as HTMLImageElement
                                      ).style.display = "none";
                                      (
                                        e.target as HTMLImageElement
                                      ).nextElementSibling?.classList.remove(
                                        "hidden",
                                      );
                                    }}
                                  />
                                ) : null}
                                <div
                                  className={
                                    img.image_url
                                      ? "hidden text-muted-foreground/50 text-xs"
                                      : "text-muted-foreground/50 text-xs"
                                  }
                                >
                                  {t("classReview.wrongImages.emptyImage")}
                                </div>
                              </div>
                              {img.answer_url && (
                                <div className="border-t border-border/50 bg-muted/20 p-2 flex flex-col gap-2 text-[11px] text-muted-foreground">
                                  <span className="font-medium text-foreground">
                                    {t("classReview.wrongImages.answerArea")}
                                  </span>
                                  <div className="relative flex items-center justify-center bg-white rounded border border-border/50 p-1 max-h-24 overflow-hidden">
                                    <img
                                      src={gradingImageUrl(img.answer_url)}
                                      alt={t(
                                        "classReview.wrongImages.answerAlt",
                                        { title: img.title },
                                      )}
                                      className="max-w-full max-h-full object-contain mix-blend-multiply"
                                      onError={(e) => {
                                        (
                                          e.target as HTMLImageElement
                                        ).style.display = "none";
                                      }}
                                    />
                                  </div>
                                </div>
                              )}
                            </div>
                          ),
                        )}
                      </div>
                    )}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {t("classReview.wrongImages.empty")}
                </p>
              )}
              {studentNames.length > 0 && !wrongImagesActive ? (
                <p className="text-xs text-muted-foreground mt-3">
                  {t("classReview.wrongImages.loadHint")}
                </p>
              ) : null}
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden border-emerald-200/80 bg-gradient-to-br from-background via-emerald-50/60 to-amber-50/70 shadow-card">
            <div className="pointer-events-none absolute inset-x-0 top-0 h-1.5 bg-gradient-to-r from-emerald-400 via-sky-400 to-amber-400" />
            <div className="pointer-events-none absolute -left-1/3 top-0 h-full w-1/3 animate-shimmer bg-gradient-to-r from-transparent via-white/45 to-transparent" />
            <CardHeader className="relative z-10 pb-4">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <CardTitle className="flex items-center gap-3 text-xl font-black text-foreground">
                    <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500 to-sky-500 text-white shadow-md">
                      <RefreshCw className="h-5 w-5" />
                    </span>
                    {t("classReview.postSection.title")}
                  </CardTitle>
                  <p className="mt-2 text-sm text-muted-foreground">
                    {t("classReview.postSection.subtitle")}
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-2 border-emerald-200 bg-white/80 shadow-sm hover:bg-emerald-50"
                  onClick={() => setPostOpen(true)}
                >
                  <ClipboardCheck className="h-4 w-4" />
                  {t("classReview.postSection.action")}
                </Button>
              </div>
            </CardHeader>
            <CardContent className="relative z-10 p-4 pt-0">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="group relative overflow-hidden rounded-2xl border border-sky-200 bg-white/88 p-5 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-lg">
                  <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-sky-500 to-emerald-400" />
                  <div className="mb-4 flex items-center justify-between gap-3">
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wide text-sky-600">
                        {t("classReview.tracking.eyebrow")}
                      </p>
                      <div className="mt-1 flex items-center gap-2">
                        <h3 className="text-2xl font-black text-sky-950">
                          {t("classReview.tracking.title")}
                        </h3>
                        <AIGeneratedBadge />
                      </div>
                    </div>
                    <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-sky-100 text-sky-700 shadow-sm transition-transform duration-300 group-hover:rotate-6 group-hover:scale-105">
                      <BarChart3 className="h-5 w-5" />
                    </span>
                  </div>
                  <div className="rounded-xl border border-sky-200 bg-gradient-to-br from-sky-50 to-white p-4">
                    <p className="text-[15px] font-bold leading-relaxed text-sky-950">
                      {tracking.summary || t("classReview.tracking.empty")}
                    </p>
                    {tracking.quality_score !== undefined ? (
                      <div className="mt-3 inline-flex items-center gap-2 rounded-full border border-sky-200 bg-white px-3 py-1 text-xs font-bold text-sky-800">
                        <Sparkles className="h-3.5 w-3.5" />
                        {t("classReview.tracking.score", {
                          score: tracking.quality_score,
                        })}
                      </div>
                    ) : null}
                  </div>
                  <div className="mt-4 grid gap-3">
                    <div className="rounded-xl border border-emerald-200 bg-emerald-50/70 p-3 transition-all duration-300 hover:bg-emerald-50">
                      <p className="mb-2 flex items-center gap-2 text-sm font-black text-emerald-900">
                        <CheckCircle2 className="h-4 w-4" />
                        {t("classReview.tracking.strengths")}
                      </p>
                      <SectionList
                        items={tracking.strengths}
                        empty={t("classReview.tracking.strengthsEmpty")}
                        tone="green"
                      />
                    </div>
                    <div className="rounded-xl border border-rose-200 bg-rose-50/70 p-3 transition-all duration-300 hover:bg-rose-50">
                      <p className="mb-2 flex items-center gap-2 text-sm font-black text-rose-900">
                        <AlertTriangle className="h-4 w-4" />
                        {t("classReview.tracking.problems")}
                      </p>
                      <SectionList
                        items={tracking.problems}
                        empty={t("classReview.tracking.problemsEmpty")}
                        tone="rose"
                      />
                    </div>
                    <div className="rounded-xl border border-sky-200 bg-sky-50/70 p-3 transition-all duration-300 hover:bg-sky-50">
                      <p className="mb-2 flex items-center gap-2 text-sm font-black text-sky-900">
                        <Target className="h-4 w-4" />
                        {t("classReview.tracking.improvements")}
                      </p>
                      <SectionList
                        items={tracking.improvement_suggestions}
                        empty={t("classReview.tracking.improvementsEmpty")}
                        tone="blue"
                      />
                    </div>
                  </div>
                </div>

                <div className="group relative overflow-hidden rounded-2xl border border-amber-200 bg-white/88 p-5 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-lg">
                  <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-amber-400 to-rose-400" />
                  <div className="mb-4 flex items-center justify-between gap-3">
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wide text-amber-600">
                        {t("classReview.reteaching.eyebrow")}
                      </p>
                      <div className="mt-1 flex items-center gap-2">
                        <h3 className="text-2xl font-black text-amber-950">
                          {t("classReview.reteaching.title")}
                        </h3>
                        <AIGeneratedBadge />
                      </div>
                    </div>
                    <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-amber-100 text-amber-700 shadow-sm transition-transform duration-300 group-hover:-rotate-6 group-hover:scale-105">
                      <Route className="h-5 w-5" />
                    </span>
                  </div>
                  <div className="rounded-xl border border-amber-200 bg-gradient-to-br from-amber-50 to-white p-4">
                    <p className="text-[15px] font-bold leading-relaxed text-amber-950">
                      {consolidation.summary ||
                        t("classReview.reteaching.empty")}
                    </p>
                  </div>
                  <div className="mt-4 space-y-3">
                    <div className="rounded-xl border border-amber-200 bg-amber-50/70 p-3 transition-all duration-300 hover:bg-amber-50">
                      <p className="mb-2 flex items-center gap-2 text-sm font-black text-amber-900">
                        <Target className="h-4 w-4" />
                        {t("classReview.reteaching.points")}
                      </p>
                      <SectionList
                        items={consolidation.reteaching_points}
                        empty={t("classReview.reteaching.pointsEmpty")}
                        tone="amber"
                      />
                    </div>
                    <div className="rounded-xl border border-sky-200 bg-sky-50/70 p-3 transition-all duration-300 hover:bg-sky-50">
                      <p className="mb-2 flex items-center gap-2 text-sm font-black text-sky-900">
                        <RefreshCw className="h-4 w-4" />
                        {t("classReview.reteaching.adjustments")}
                      </p>
                      <SectionList
                        items={consolidation.lesson_adjustments}
                        empty={t("classReview.reteaching.adjustmentsEmpty")}
                        tone="blue"
                      />
                    </div>
                    {(Array.isArray(consolidation.tiered_practice)
                      ? consolidation.tiered_practice
                      : []
                    ).map((group: any, index: number) => (
                      <div
                        key={index}
                        className="rounded-xl border bg-gradient-to-br from-white to-muted/20 p-3 shadow-sm transition-all duration-300 hover:-translate-y-0.5 hover:shadow-md"
                      >
                        <p className="mb-2 flex items-center gap-2 text-sm font-black">
                          <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-primary/10 text-xs text-primary">
                            {index + 1}
                          </span>
                          {group.level ||
                            t("classReview.reteaching.level", {
                              index: index + 1,
                            })}
                        </p>
                        <SectionList
                          items={group.tasks}
                          empty={t("classReview.reteaching.tasksEmpty")}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </>
      )}

      <ImportExamDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        classId={selectedClass}
        subject={subject}
      />
      <PostClassDialog
        open={postOpen}
        onOpenChange={setPostOpen}
        classId={selectedClass}
        subject={subject}
        report={report}
      />

      <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
        <DialogContent className="sm:max-w-lg max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <History className="h-5 w-5 text-primary" />
              {t("classReview.history")}
            </DialogTitle>
            <DialogDescription>
              {t("classReview.historySubtitle")}
            </DialogDescription>
          </DialogHeader>
          <div className="min-h-0 flex-1 overflow-y-auto pr-1 -mr-1">
            {sessionsLoading ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : sessionsError ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <AlertTriangle className="h-8 w-8 text-destructive/70" />
                <p className="mt-3 text-sm text-muted-foreground">
                  {t("classDetail.checkNetworkAndRetry")}
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-3 gap-2"
                  onClick={() => refetchSessions()}
                >
                  <RefreshCw className="h-4 w-4" />
                  {t("wuyu.retry")}
                </Button>
              </div>
            ) : sessions.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <History className="h-8 w-8 text-muted-foreground/50" />
                <p className="mt-3 text-sm font-medium text-foreground">
                  {t("classReview.historyEmpty")}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {t("classReview.historyEmptyHint")}
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {sessions.map((item: ClassReviewSessionItem) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      // 先写好目标班级的科目偏好，再切换班级，避免被旧偏好覆盖
                      try {
                        localStorage.setItem(
                          `${SUBJECT_STORAGE_PREFIX}${item.class_id}`,
                          item.subject,
                        );
                      } catch {
                        // ignore
                      }
                      onOpenSession?.(item.class_id, item.subject);
                      setHistoryOpen(false);
                    }}
                    className="w-full rounded-lg border border-border/60 bg-card p-3 text-left transition-colors hover:border-primary/40 hover:bg-muted/40"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="truncate text-sm font-semibold text-foreground">
                            {item.class_name || item.class_id}
                          </span>
                          <Badge
                            variant="secondary"
                            className="shrink-0 text-[11px] font-normal"
                          >
                            {translateSubjectName(locale, item.subject)}
                          </Badge>
                          {item.grade ? (
                            <Badge
                              variant="outline"
                              className="shrink-0 text-[11px] font-normal text-muted-foreground"
                            >
                              {item.grade}
                            </Badge>
                          ) : null}
                        </div>
                        {item.exam_names && item.exam_names.length > 0 ? (
                          <p className="mt-1 truncate text-xs text-muted-foreground">
                            {item.exam_names.join(" · ")}
                          </p>
                        ) : null}
                      </div>
                      <div className="shrink-0 text-right">
                        {item.updated_at ? (
                          <p className="text-[11px] text-muted-foreground">
                            {new Date(item.updated_at).toLocaleString("zh-CN", {
                              month: "2-digit",
                              day: "2-digit",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </p>
                        ) : null}
                        <ChevronRight className="ml-auto mt-1 h-4 w-4 text-muted-foreground" />
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
