import { useEffect, useMemo, useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Save, X, Trash2, UserCircle } from "lucide-react";
import type { StudentInfo } from "@/types/api";
import { useDeleteStudent, useUpdateStudent } from "@/hooks/useStudents";
import { toast } from "sonner";
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
import { useLocale } from "@/contexts/LocaleContext";
import { translateGender, translateStudentStatus, translateTierLabel } from "@/i18n";

interface StudentDetailPanelProps {
  student: StudentInfo | null;
  classId: string;
}

const STATUS_VALUES = ["正常", "预警", "转出", "休学"] as const;
const TIER_VALUES = ["A", "B", "C"] as const;
const GENDER_VALUES = ["男", "女"] as const;

export function StudentDetailPanel({ student, classId }: StudentDetailPanelProps) {
  const { t, locale } = useLocale();
  const updateStudent = useUpdateStudent();
  const deleteStudent = useDeleteStudent();
  const [confirmDelete, setConfirmDelete] = useState(false);

  const [form, setForm] = useState({
    student_number: "",
    name: "",
    gender: "男",
    birthday: "",
    enroll_date: "",
    status: "正常",
    tier: "B",
    phone: "",
    parent_name: "",
    parent_phone: "",
    address: "",
    seat_row: "",
    seat_col: "",
    cadre_role: "",
    notes: "",
  });

  const original = useMemo(() => {
    if (!student) return null;
    return {
      student_number: student.student_number || "",
      name: student.name || "",
      gender: (student.gender || "男") as "男" | "女",
      birthday: student.birthday || "",
      enroll_date: student.enroll_date || "",
      status: student.status || "正常",
      tier: student.tier || "B",
      phone: student.phone || "",
      parent_name: student.parent_name || "",
      parent_phone: student.parent_phone || "",
      address: student.address || "",
      seat_row: student.seat_row != null ? String(student.seat_row) : "",
      seat_col: student.seat_col != null ? String(student.seat_col) : "",
      cadre_role: student.cadre_role || "",
      notes: student.notes || "",
    };
  }, [student]);

  useEffect(() => {
    if (original) setForm(original);
  }, [original]);

  if (!student) {
    return (
      <div className="rounded-2xl border border-border bg-card p-6 flex items-center justify-center h-full min-h-[420px]">
        <div className="text-center text-muted-foreground">
          <UserCircle className="w-12 h-12 mx-auto mb-2 opacity-30" />
          <p className="text-sm">{t("settingsClass.detail.emptyHint")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-border bg-card overflow-y-auto h-[685px]">
      <div className="sticky top-0 z-20 bg-card px-5 pt-5 pb-3 border-b border-border shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <h3 className="text-base font-semibold text-foreground truncate">{t("settingsClass.detail.title")}</h3>
            <p className="text-sm text-muted-foreground mt-0.5 truncate">{student.student_number} · {student.name}</p>
          </div>
        <div className="flex items-center gap-1">
          <Button
            size="sm"
            className="h-8 text-sm gap-1.5"
            onClick={async () => {
              const patch: Partial<StudentInfo> = {
                student_number: form.student_number.trim(),
                name: form.name.trim(),
                gender: form.gender,
                birthday: form.birthday.trim() || null,
                enroll_date: form.enroll_date.trim() || null,
                status: form.status,
                tier: form.tier,
                phone: form.phone.trim() || null,
                parent_name: form.parent_name.trim() || null,
                parent_phone: form.parent_phone.trim() || null,
                address: form.address.trim() || null,
                seat_row: form.seat_row ? Number(form.seat_row) : null,
                seat_col: form.seat_col ? Number(form.seat_col) : null,
                cadre_role: form.cadre_role.trim() || null,
                notes: form.notes.trim() || null,
              };
              if (!patch.student_number || !patch.name) {
                toast.error(t("settingsClass.detail.toast.required"));
                return;
              }
              await updateStudent.mutateAsync({ id: student.id, class_id: classId, patch });
            }}
            disabled={updateStudent.isPending}
          >
            <Save className="w-4 h-4" />
            {updateStudent.isPending ? t("settingsClass.detail.saving") : t("settingsClass.detail.save")}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-8 text-sm gap-1.5"
            onClick={() => original && setForm(original)}
          >
            <X className="w-4 h-4" />{t("common.cancel")}
          </Button>
        </div>
        </div>
      </div>

      <div className="px-5 py-4">
      <Section title={t("settingsClass.detail.basicInfo")}>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("settingsClass.table.colNumber")} value={form.student_number} onChange={(v) => setForm((p) => ({ ...p, student_number: v }))} />
          <Field label={t("settingsClass.table.colName")} value={form.name} onChange={(v) => setForm((p) => ({ ...p, name: v }))} />
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">{t("settingsClass.table.colGender")}</label>
            <Select value={form.gender} onValueChange={(v) => setForm((p) => ({ ...p, gender: v as "男" | "女" }))}>
              <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
              <SelectContent>
                {GENDER_VALUES.map((gender) => (
                  <SelectItem key={gender} value={gender}>{translateGender(locale, gender)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Field label={t("settingsClass.detail.birthday")} value={form.birthday} onChange={(v) => setForm((p) => ({ ...p, birthday: v }))} placeholder={t("settingsClass.detail.birthdayPlaceholder")} />
        </div>
      </Section>

      <Section title={t("settingsClass.detail.enrollmentInfo")}>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("settingsClass.detail.enrollDate")} value={form.enroll_date} onChange={(v) => setForm((p) => ({ ...p, enroll_date: v }))} placeholder={t("settingsClass.detail.enrollDatePlaceholder")} />
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">{t("settingsClass.detail.status")}</label>
            <Select value={form.status} onValueChange={(v) => setForm((p) => ({ ...p, status: v }))}>
              <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
              <SelectContent>
                {STATUS_VALUES.map((status) => (
                  <SelectItem key={status} value={status}>{translateStudentStatus(locale, status)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </Section>

      <Section title={t("settingsClass.detail.contact")}>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("settingsClass.detail.studentPhone")} value={form.phone} onChange={(v) => setForm((p) => ({ ...p, phone: v }))} placeholder={t("settingsClass.detail.optional")} />
          <Field label={t("settingsClass.detail.parentName")} value={form.parent_name} onChange={(v) => setForm((p) => ({ ...p, parent_name: v }))} placeholder={t("settingsClass.detail.optional")} />
          <Field label={t("settingsClass.detail.parentPhone")} value={form.parent_phone} onChange={(v) => setForm((p) => ({ ...p, parent_phone: v }))} placeholder={t("settingsClass.detail.optional")} />
          <Field label={t("settingsClass.detail.address")} value={form.address} onChange={(v) => setForm((p) => ({ ...p, address: v }))} placeholder={t("settingsClass.detail.optional")} />
        </div>
      </Section>

      <Section title={t("settingsClass.detail.classInfo")}>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">{t("settingsClass.detail.currentTier")}</label>
            <Select value={form.tier} onValueChange={(v) => setForm((p) => ({ ...p, tier: v }))}>
              <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
              <SelectContent>
                {TIER_VALUES.map((tier) => (
                  <SelectItem key={tier} value={tier}>{translateTierLabel(locale, tier, true)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">{t("settingsClass.detail.seatRow")}</label>
              <Input value={form.seat_row} onChange={(e) => setForm((p) => ({ ...p, seat_row: e.target.value }))} className="h-9 text-sm" placeholder={t("settingsClass.detail.optional")} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">{t("settingsClass.detail.seatCol")}</label>
              <Input value={form.seat_col} onChange={(e) => setForm((p) => ({ ...p, seat_col: e.target.value }))} className="h-9 text-sm" placeholder={t("settingsClass.detail.optional")} />
            </div>
          </div>
          <Field label={t("settingsClass.detail.cadre")} value={form.cadre_role} onChange={(v) => setForm((p) => ({ ...p, cadre_role: v }))} placeholder={t("settingsClass.detail.optional")} />
        </div>
      </Section>

      <Section title={t("settingsClass.detail.notes")}>
        <Textarea
          value={form.notes}
          onChange={(e) => setForm((p) => ({ ...p, notes: e.target.value }))}
          placeholder={t("settingsClass.detail.notesPlaceholder")}
          className="text-sm min-h-[84px]"
        />
      </Section>

      <div className="mt-4 pt-3 border-t border-border">
        <Button size="sm" variant="destructive" className="h-8 text-sm gap-1.5" onClick={() => setConfirmDelete(true)}>
          <Trash2 className="w-4 h-4" />{t("settingsClass.detail.deleteStudent")}
        </Button>
      </div>
      </div>

      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("settingsClass.detail.confirmDeleteTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("settingsClass.detail.confirmDeleteDesc", { name: student.name })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={async (e) => {
                e.preventDefault();
                await deleteStudent.mutateAsync({ id: student.id, class_id: classId });
                setConfirmDelete(false);
              }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={deleteStudent.isPending}
            >
              {deleteStudent.isPending ? t("settingsClass.detail.deleting") : t("common.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <h4 className="text-sm font-semibold text-foreground mb-2">{title}</h4>
      {children}
      <Separator className="mt-3" />
    </div>
  );
}

function Field({ label, value, placeholder, onChange }: { label: string; value: string; placeholder?: string; onChange?: (v: string) => void }) {
  return (
    <div>
      <label className="text-xs text-muted-foreground mb-1 block">{label}</label>
      <Input value={value} onChange={(e) => onChange?.(e.target.value)} placeholder={placeholder} className="h-9 text-sm" />
    </div>
  );
}
