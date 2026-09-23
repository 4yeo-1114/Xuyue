import { useEffect, useMemo, useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, UserPlus } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { listParentStudents, createParentStudent } from "@/services/assessmentApi";
import { getAllUsers } from "@/services/api";
import type { StudentInfo } from "@/types/api";
import { EmptyState } from "./shared";

const RELATIONS = ["guardian", "father", "mother", "other"];

interface ParentBindingDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  students: StudentInfo[];
  studentId?: string;
}

export function ParentBindingDialog({ open, onOpenChange, students, studentId }: ParentBindingDialogProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [localStudentId, setLocalStudentId] = useState("");
  const [parentUserId, setParentUserId] = useState("");
  const [relation, setRelation] = useState("guardian");

  useEffect(() => {
    if (open) {
      setLocalStudentId(studentId || students[0]?.id || "");
      setParentUserId("");
      setRelation("guardian");
    }
  }, [open, studentId, students]);

  const activeStudentId = localStudentId || studentId || "";

  const { data: users = [] } = useQuery({
    queryKey: ["all-users"],
    queryFn: () => getAllUsers(),
    enabled: open,
  });

  const { data: bindings, isLoading } = useQuery({
    queryKey: ["parent-students", activeStudentId],
    queryFn: () => listParentStudents({ student_id: activeStudentId }),
    enabled: open && !!activeStudentId,
  });

  const { mutate: doBind, isPending: binding } = useMutation({
    mutationFn: () =>
      createParentStudent({ parent_id: parentUserId, student_id: activeStudentId, relation }),
    onSuccess: () => {
      toast.success(t("assessment.parent.bindSuccess"));
      queryClient.invalidateQueries({ queryKey: ["parent-students"] });
      setParentUserId("");
    },
    onError: (err: Error) => toast.error(t("assessment.parent.bindFailed"), { description: err.message }),
  });

  const bindRows = bindings?.rows ?? [];
  const parentOptions = useMemo(() => {
    return [...users].sort((a, b) => (a.display_name || a.email).localeCompare(b.display_name || b.email));
  }, [users]);

  const canSubmit = !!activeStudentId && !!parentUserId;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <UserPlus className="w-4 h-4" />
            {t("assessment.parent.bind")}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 flex-1 min-h-0 flex flex-col">
          <div className="space-y-2">
            <Label>{t("assessment.parent.student")}</Label>
            <Select value={activeStudentId} onValueChange={setLocalStudentId}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("assessment.parent.chooseStudent")} />
              </SelectTrigger>
              <SelectContent>
                {students.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.name}（{s.student_number}）
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>{t("assessment.parent.parentUser")}</Label>
            <Select value={parentUserId} onValueChange={setParentUserId}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("assessment.parent.chooseParentUser")} />
              </SelectTrigger>
              <SelectContent>
                {parentOptions.map((u) => (
                  <SelectItem key={u.id} value={u.id}>
                    {u.display_name || u.email}（{u.email}）
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">{t("assessment.parent.parentUserHint")}</p>
          </div>

          <div className="space-y-2">
            <Label>{t("assessment.parent.relation")}</Label>
            <Select value={relation} onValueChange={setRelation}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {RELATIONS.map((r) => (
                  <SelectItem key={r} value={r}>
                    {t(`assessment.parent.relation.${r}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex-1 min-h-0 overflow-y-auto rounded-md border border-border/60 p-3 space-y-2">
            <p className="text-xs font-medium text-muted-foreground">{t("assessment.parent.bindings")}</p>
            {isLoading ? (
              <div className="flex items-center justify-center py-6">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : bindRows.length === 0 ? (
              <EmptyState icon={UserPlus} title={t("assessment.parent.empty")} className="py-6" />
            ) : (
              bindRows.map((b) => (
                <div key={b.id} className="flex items-center gap-2 rounded-md bg-muted/40 px-3 py-2 text-sm">
                  <span className="min-w-0 truncate">{b.parent_name || b.parent_id}</span>
                  <Badge variant="outline" className="text-xs">
                    {t(`assessment.parent.relation.${b.relation}`)}
                  </Badge>
                  <Badge
                    variant="outline"
                    className={
                      b.status === "active"
                        ? "bg-emerald-100 text-emerald-700 border-emerald-200"
                        : "bg-rose-100 text-rose-600 border-rose-200"
                    }
                  >
                    {b.status === "active"
                      ? t("assessment.parent.status.active")
                      : b.status}
                  </Badge>
                </div>
              ))
            )}
          </div>
        </div>

        <DialogFooter className="border-t pt-3">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("assessment.parent.cancel")}
          </Button>
          <Button disabled={!canSubmit || binding} onClick={() => doBind()}>
            {binding && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
            {binding ? t("assessment.parent.saving") : t("assessment.parent.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
