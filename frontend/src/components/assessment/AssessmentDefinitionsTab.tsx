import { useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ClipboardList, Plus, Pencil, Trash2, Power, PowerOff, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import {
  listAssessmentDefinitions,
  deleteAssessmentDefinition,
  updateAssessmentDefinition,
  type AssessmentDefinition,
  type AssessmentDefinitionStatus,
} from "@/services/assessmentApi";
import { DefinitionStatusBadge, EmptyState } from "./shared";
import { DefinitionFormDialog } from "./DefinitionFormDialog";

const STATUS_OPTIONS: AssessmentDefinitionStatus[] = ["active", "draft", "retired"];

export function AssessmentDefinitionsTab() {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<AssessmentDefinitionStatus>("active");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<AssessmentDefinition | null>(null);
  const [deleting, setDeleting] = useState<AssessmentDefinition | null>(null);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["assessment-definitions", statusFilter],
    queryFn: () => listAssessmentDefinitions({ status: statusFilter }),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["assessment-definitions"] });

  const { mutate: doToggle, isPending: toggling } = useMutation({
    mutationFn: (d: AssessmentDefinition) =>
      updateAssessmentDefinition(d.id, {
        status: d.status === "active" ? "retired" : "active",
      }),
    onSuccess: (_data, d) => {
      toast.success(
        d.status === "active" ? t("assessment.definition.deactivated") : t("assessment.definition.activated")
      );
      invalidate();
    },
    onError: (err: Error) => {
      toast.error(t("assessment.definition.updateFailed"), { description: err.message });
    },
  });

  const { mutate: doDelete, isPending: deletingP } = useMutation({
    mutationFn: (id: string) => deleteAssessmentDefinition(id),
    onSuccess: () => {
      toast.success(t("assessment.definition.deleted"));
      invalidate();
      setDeleting(null);
    },
    onError: (err: Error) => {
      toast.error(t("assessment.definition.deleteFailed"), { description: err.message });
      setDeleting(null);
    },
  });

  const rows = data?.rows ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as AssessmentDefinitionStatus)}>
            <SelectTrigger className="w-[160px] h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUS_OPTIONS.map((s) => (
                <SelectItem key={s} value={s}>
                  {t(`assessment.definition.status.${s}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="ghost" size="sm" onClick={() => refetch()}>
            {t("assessment.refresh")}
          </Button>
        </div>
        <Button
          size="sm"
          onClick={() => {
            setEditing(null);
            setFormOpen(true);
          }}
        >
          <Plus className="w-4 h-4 mr-1" />
          {t("assessment.definition.create")}
        </Button>
      </div>

      {rows.length === 0 ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState
              icon={ClipboardList}
              title={t("assessment.definition.empty")}
              hint={t("assessment.definition.seedHint")}
            />
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {rows.map((d) => (
            <Card key={d.id} className="flex flex-col">
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <CardTitle className="text-sm leading-snug truncate">{d.name}</CardTitle>
                    <CardDescription className="mt-1 text-xs">
                      {t(`assessment.definition.domain.${d.domain}`)} ·{" "}
                      {t(`assessment.definition.grade.${d.grade_range}`)} · v{d.version}
                    </CardDescription>
                  </div>
                  <DefinitionStatusBadge status={d.status} />
                </div>
              </CardHeader>
              <CardContent className="flex-1">
                <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-0.5">
                    {t("assessment.definition.questionCount", { count: d.question_count })}
                  </span>
                  {d.consent_required && (
                    <span className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-0.5">
                      {t("assessment.definition.consentRequired")}
                    </span>
                  )}
                </div>
                {d.description ? (
                  <p className="mt-2 text-xs text-muted-foreground line-clamp-2">{d.description}</p>
                ) : null}
              </CardContent>
              <div className="flex items-center gap-1 px-4 pb-4 border-t pt-3">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => {
                    setEditing(d);
                    setFormOpen(true);
                  }}
                >
                  <Pencil className="w-3.5 h-3.5 mr-1" />
                  {t("assessment.definition.edit")}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs"
                  disabled={toggling}
                  onClick={() => doToggle(d)}
                >
                  {d.status === "active" ? (
                    <PowerOff className="w-3.5 h-3.5 mr-1" />
                  ) : (
                    <Power className="w-3.5 h-3.5 mr-1" />
                  )}
                  {d.status === "active"
                    ? t("assessment.definition.deactivate")
                    : t("assessment.definition.activate")}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs text-destructive hover:text-destructive"
                  onClick={() => setDeleting(d)}
                >
                  <Trash2 className="w-3.5 h-3.5 mr-1" />
                  {t("assessment.definition.delete")}
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <DefinitionFormDialog open={formOpen} onOpenChange={setFormOpen} editing={editing} />

      <AlertDialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("assessment.definition.delete")}</AlertDialogTitle>
            <AlertDialogDescription>
              {deleting ? t("assessment.definition.deleteConfirm", { name: deleting.name }) : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("assessment.definition.form.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              disabled={deletingP}
              className="bg-destructive text-white hover:bg-destructive/90"
              onClick={() => deleting && doDelete(deleting.id)}
            >
              {deletingP && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
              {t("assessment.definition.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
