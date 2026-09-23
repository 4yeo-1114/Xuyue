import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ClipboardList,
  Plus,
  Loader2,
  ImagePlus,
  X,
  CheckCircle2,
  XCircle,
  CalendarDays,
  MapPin,
  Clock,
} from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  listPracticeRecords,
  createPracticeRecord,
  reviewPracticeRecord,
  uploadEvidence,
  getFileUrl,
  resolveFileUrl,
  type PracticeRecord,
  type PracticeInput,
  type EvidenceImage,
} from "@/services/studentOpsApi";
import { ClassSelector } from "@/components/student-ops/shared/ClassSelector";
import { StudentPicker } from "@/components/student-ops/shared/StudentPicker";
import { StatusBadge } from "@/components/student-ops/shared/StatusBadge";
import { Pagination } from "@/components/student-ops/shared/Pagination";
import { EmptyState } from "@/components/student-ops/shared/EmptyState";

const PRACTICE_TYPES = ["housework", "volunteer", "talent", "study_tour"] as const;

interface PracticeSectionProps {
  classId: string;
  onClassChange: (id: string) => void;
}

export function PracticeSection({ classId, onClassChange }: PracticeSectionProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [practiceType, setPracticeType] = useState("");
  const [status, setStatus] = useState("");

  const [createOpen, setCreateOpen] = useState(false);
  const [detail, setDetail] = useState<PracticeRecord | null>(null);
  const [review, setReview] = useState<{ record: PracticeRecord; mode: "approved" | "rejected" } | null>(null);

  const query = useQuery({
    queryKey: ["so-practice", classId, practiceType, status, page],
    queryFn: () =>
      listPracticeRecords({
        classId: classId || undefined,
        practiceType: practiceType || undefined,
        status: status || undefined,
        page,
        pageSize: 20,
      }),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["so-practice"] });
    queryClient.invalidateQueries({ queryKey: ["so-credit-accounts"] });
    queryClient.invalidateQueries({ queryKey: ["so-credit-txns"] });
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
            <ClipboardList className="h-4 w-4 text-primary" />
          </div>
          <ClassSelector value={classId} onChange={onClassChange} />
        </div>
        <Button size="sm" onClick={() => setCreateOpen(true)} disabled={!classId}>
          <Plus className="h-4 w-4 mr-1" /> {t("studentOps.practice.create")}
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center gap-2">
            <Select value={practiceType} onValueChange={(v) => { setPracticeType(v); setPage(1); }}>
              <SelectTrigger className="w-[150px]">
                <SelectValue placeholder={t("studentOps.practice.type")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all">{t("studentOps.all")}</SelectItem>
                {PRACTICE_TYPES.map((pt) => (
                  <SelectItem key={pt} value={pt}>
                    {t(`studentOps.practice.type${cap(pt)}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={status} onValueChange={(v) => { setStatus(v); setPage(1); }}>
              <SelectTrigger className="w-[140px]">
                <SelectValue placeholder={t("studentOps.practice.statusPending")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all">{t("studentOps.all")}</SelectItem>
                <SelectItem value="pending">{t("studentOps.practice.statusPending")}</SelectItem>
                <SelectItem value="approved">{t("studentOps.practice.statusApproved")}</SelectItem>
                <SelectItem value="rejected">{t("studentOps.practice.statusRejected")}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {query.isLoading ? (
            <LoadingRow />
          ) : query.isError ? (
            <ErrorBox />
          ) : query.data?.items.length === 0 ? (
            <EmptyState title={t("studentOps.practice.noRecords")} />
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("studentOps.practice.student")}</TableHead>
                    <TableHead>{t("studentOps.practice.type")}</TableHead>
                    <TableHead>{t("studentOps.practice.titleField")}</TableHead>
                    <TableHead>{t("studentOps.practice.date")}</TableHead>
                    <TableHead>{t("studentOps.practice.durationHours")}</TableHead>
                    <TableHead>{t("studentOps.practice.evidence")}</TableHead>
                    <TableHead>{t("studentOps.badges.status")}</TableHead>
                    <TableHead className="text-right">{t("studentOps.actions")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {query.data?.items.map((r) => (
                    <TableRow key={r.id} className="cursor-pointer" onClick={() => setDetail(r)}>
                      <TableCell className="font-medium">{r.studentName}</TableCell>
                      <TableCell>{t(`studentOps.practice.type${cap(r.practiceType)}`)}</TableCell>
                      <TableCell className="max-w-[180px] truncate">{r.title}</TableCell>
                      <TableCell>{r.practiceDate}</TableCell>
                      <TableCell>{r.durationHours ?? "—"}</TableCell>
                      <TableCell>
                        {r.evidenceImages && r.evidenceImages.length > 0 ? (
                          <div className="flex gap-1">
                            {r.evidenceImages.slice(0, 3).map((ev, i) => (
                              <EvidenceThumb key={i} url={ev.url} />
                            ))}
                            {r.evidenceImages.length > 3 && (
                              <span className="text-xs text-muted-foreground self-center">
                                +{r.evidenceImages.length - 3}
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <StatusBadge
                          value={r.status}
                          label={t(`studentOps.practice.status${cap(r.status)}`)}
                        />
                      </TableCell>
                      <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                        {r.status === "pending" && (
                          <div className="flex justify-end gap-1">
                            <Button variant="ghost" size="sm" onClick={() => setReview({ record: r, mode: "approved" })}>
                              <CheckCircle2 className="h-4 w-4 text-green-600" />
                            </Button>
                            <Button variant="ghost" size="sm" onClick={() => setReview({ record: r, mode: "rejected" })}>
                              <XCircle className="h-4 w-4 text-destructive" />
                            </Button>
                          </div>
                        )}
                        {r.status !== "pending" && (
                          <span className="text-xs text-muted-foreground">
                            {r.reviewedAt ? r.reviewedAt.slice(0, 10) : "—"}
                          </span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <div className="p-3">
                <Pagination
                  page={query.data?.page || 1}
                  pageSize={query.data?.pageSize || 20}
                  total={query.data?.total || 0}
                  onPageChange={setPage}
                />
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <PracticeFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        classId={classId}
        onSaved={() => {
          invalidate();
          setCreateOpen(false);
        }}
      />

      <PracticeDetailDialog record={detail} onClose={() => setDetail(null)} />

      <ReviewDialog
        review={review}
        onClose={() => setReview(null)}
        onDone={invalidate}
      />
    </div>
  );
}

function cap(s: string): string {
  if (!s) return "";
  return s
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join("");
}

function LoadingRow() {
  const { t } = useLocale();
  return (
    <div className="flex items-center justify-center py-12 text-muted-foreground">
      <Loader2 className="h-5 w-5 animate-spin mr-2" /> {t("studentOps.loading")}
    </div>
  );
}

function ErrorBox() {
  const { t } = useLocale();
  return (
    <div className="p-4">
      <Alert variant="destructive">
        <AlertTitle>{t("studentOps.loadError")}</AlertTitle>
      </Alert>
    </div>
  );
}

/** 图片缩略图：先取 ticket 直链再渲染 */
function EvidenceThumb({ url, className }: { url: string; className?: string }) {
  const { data } = useQuery({
    queryKey: ["so-ev-url", url],
    queryFn: () => getFileUrl(url),
  });
  if (!data) {
    return <div className={`h-10 w-10 rounded bg-muted animate-pulse ${className ?? ""}`} />;
  }
  return (
    <img
      src={resolveFileUrl(data.downloadUrl)}
      alt=""
      className={`h-10 w-10 rounded object-cover ${className ?? ""}`}
    />
  );
}

/* ── 实践详情 ── */
function PracticeDetailDialog({ record, onClose }: { record: PracticeRecord | null; onClose: () => void }) {
  const { t } = useLocale();
  return (
    <Dialog open={!!record} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{record?.title}</DialogTitle>
          <DialogDescription>
            {record ? t(`studentOps.practice.type${cap(record.practiceType)}`) : ""}
            {record?.studentName ? ` · ${record.studentName}` : ""}
          </DialogDescription>
        </DialogHeader>
        {record && (
          <div className="grid gap-3 text-sm">
            <div className="flex flex-wrap gap-4 text-muted-foreground">
              <span className="flex items-center gap-1">
                <CalendarDays className="h-4 w-4" /> {record.practiceDate}
              </span>
              {record.durationHours != null && (
                <span className="flex items-center gap-1">
                  <Clock className="h-4 w-4" /> {record.durationHours} h
                </span>
              )}
              {record.location && (
                <span className="flex items-center gap-1">
                  <MapPin className="h-4 w-4" /> {record.location}
                </span>
              )}
            </div>
            {record.description && <p className="text-muted-foreground">{record.description}</p>}
            {record.reviewComment && (
              <p className="text-muted-foreground">
                {t("studentOps.practice.reviewComment")}：{record.reviewComment}
              </p>
            )}
            {record.evidenceImages && record.evidenceImages.length > 0 && (
              <div className="grid grid-cols-3 gap-2">
                {record.evidenceImages.map((ev, i) => (
                  <EvidenceThumb key={i} url={ev.url} className="h-20 w-full" />
                ))}
              </div>
            )}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t("studentOps.close")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ── 新建实践 ── */
interface PracticeFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  classId: string;
  onSaved: () => void;
}

function PracticeFormDialog({ open, onOpenChange, classId, onSaved }: PracticeFormProps) {
  const { t } = useLocale();
  const [studentId, setStudentId] = useState("");
  const [practiceType, setPracticeType] = useState("housework");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [practiceDate, setPracticeDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [durationHours, setDurationHours] = useState("");
  const [location, setLocation] = useState("");
  const [images, setImages] = useState<EvidenceImage[]>([]);

  useEffect(() => {
    if (open) {
      setStudentId("");
      setPracticeType("housework");
      setTitle("");
      setDescription("");
      setPracticeDate(new Date().toISOString().slice(0, 10));
      setDurationHours("");
      setLocation("");
      setImages([]);
    }
  }, [open]);

  const mutation = useMutation({
    mutationFn: (body: PracticeInput) => createPracticeRecord(body),
    onSuccess: () => {
      toast.success(t("studentOps.practice.createSuccess"));
      onSaved();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const submit = () => {
    if (!studentId) {
      toast.error(t("studentOps.practice.requireStudent"));
      return;
    }
    if (!title.trim()) {
      toast.error(t("studentOps.practice.requireTitle"));
      return;
    }
    mutation.mutate({
      studentId,
      practiceType,
      title: title.trim(),
      description: description || null,
      practiceDate,
      durationHours: durationHours ? Number(durationHours) : null,
      location: location || null,
      evidenceImages: images.length ? images : null,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[88vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("studentOps.practice.create")}</DialogTitle>
          <DialogDescription>{t("studentOps.practice.uploadHint")}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>{t("studentOps.practice.student")} *</Label>
              <StudentPicker classId={classId} value={studentId} onChange={setStudentId} />
            </div>
            <div className="grid gap-2">
              <Label>{t("studentOps.practice.type")}</Label>
              <Select value={practiceType} onValueChange={setPracticeType}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {PRACTICE_TYPES.map((pt) => (
                    <SelectItem key={pt} value={pt}>
                      {t(`studentOps.practice.type${cap(pt)}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-2">
            <Label>{t("studentOps.practice.titleField")} *</Label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t("studentOps.practice.titlePlaceholder")} />
          </div>
          <div className="grid gap-2">
            <Label>{t("studentOps.practice.description")}</Label>
            <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div className="grid gap-2">
              <Label>{t("studentOps.practice.date")}</Label>
              <Input type="date" value={practiceDate} onChange={(e) => setPracticeDate(e.target.value)} />
            </div>
            <div className="grid gap-2">
              <Label>{t("studentOps.practice.durationHours")}</Label>
              <Input type="number" min={0} step={0.5} value={durationHours} onChange={(e) => setDurationHours(e.target.value)} />
            </div>
            <div className="grid gap-2">
              <Label>{t("studentOps.practice.location")}</Label>
              <Input value={location} onChange={(e) => setLocation(e.target.value)} />
            </div>
          </div>
          <EvidenceUploader value={images} onChange={setImages} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t("studentOps.cancel")}</Button>
          <Button onClick={submit} disabled={mutation.isPending}>
            {mutation.isPending && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
            {t("studentOps.practice.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ── 图片上传 ── */
function EvidenceUploader({ value, onChange }: { value: EvidenceImage[]; onChange: (v: EvidenceImage[]) => void }) {
  const { t } = useLocale();
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const remaining = 9 - value.length;
    if (remaining <= 0) return;
    const toUpload = Array.from(files).slice(0, remaining);
    setUploading(true);
    let ok = 0;
    const uploaded: EvidenceImage[] = [];
    for (const f of toUpload) {
      try {
        const res = await uploadEvidence(f);
        uploaded.push({ url: res.url, thumbUrl: res.thumbUrl, uploadAt: new Date().toISOString() });
        ok++;
      } catch (e) {
        toast.error((e as Error).message || t("studentOps.practice.uploadFailed"));
      }
    }
    if (ok > 0) {
      onChange([...value, ...uploaded]);
      toast.success(t("studentOps.practice.uploadSuccess"));
    }
    setUploading(false);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div className="grid gap-2">
      <Label>{t("studentOps.practice.evidence")}</Label>
      <div className="flex flex-wrap gap-2">
        {value.map((img, i) => (
          <div key={i} className="relative">
            <EvidenceThumb url={img.url} className="h-16 w-16" />
            <button
              type="button"
              onClick={() => onChange(value.filter((_, idx) => idx !== i))}
              className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-destructive text-white"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        ))}
        {value.length < 9 && (
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={uploading}
            className="flex h-16 w-16 flex-col items-center justify-center gap-1 rounded-lg border border-dashed text-muted-foreground hover:bg-accent/60 disabled:opacity-50"
          >
            {uploading ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <ImagePlus className="h-5 w-5" />
            )}
            <span className="text-[10px]">{t("studentOps.practice.uploadEvidence")}</span>
          </button>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        multiple
        hidden
        onChange={(e) => handleFiles(e.target.files)}
      />
      <p className="text-xs text-muted-foreground">{t("studentOps.practice.uploadHint")}</p>
    </div>
  );
}

/* ── 审核 ── */
interface ReviewDialogProps {
  review: { record: PracticeRecord; mode: "approved" | "rejected" } | null;
  onClose: () => void;
  onDone: () => void;
}

function ReviewDialog({ review, onClose, onDone }: ReviewDialogProps) {
  const { t } = useLocale();
  const [comment, setComment] = useState("");
  const mode = review?.mode;

  useEffect(() => {
    if (review) setComment("");
  }, [review]);

  const mutation = useMutation({
    mutationFn: () =>
      reviewPracticeRecord(review!.record.id, {
        status: review!.mode,
        reviewComment: comment || null,
      }),
    onSuccess: () => {
      toast.success(
        mode === "approved"
          ? t("studentOps.practice.approveSuccess")
          : t("studentOps.practice.rejectSuccess")
      );
      onDone();
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Dialog open={!!review} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            {mode === "approved" ? t("studentOps.practice.approve") : t("studentOps.practice.reject")}
          </DialogTitle>
          <DialogDescription>
            {review?.record.studentName} · {review?.record.title}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label>{t("studentOps.practice.reviewComment")}</Label>
            <Textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder={t("studentOps.practice.reviewCommentPlaceholder")}
              rows={3}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t("studentOps.cancel")}</Button>
          <Button
            variant={mode === "rejected" ? "destructive" : "default"}
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            {mutation.isPending && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
            {mode === "approved" ? t("studentOps.practice.approve") : t("studentOps.practice.reject")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
