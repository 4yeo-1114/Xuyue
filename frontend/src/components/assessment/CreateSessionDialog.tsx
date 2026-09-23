import { useEffect, useMemo, useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { listAssessmentDefinitions, createAssessmentSessions } from "@/services/assessmentApi";
import { listStudentsByClass } from "@/services/api";

interface CreateSessionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedClass: string;
  onCreated: () => void;
}

export function CreateSessionDialog({ open, onOpenChange, selectedClass, onCreated }: CreateSessionDialogProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [definitionId, setDefinitionId] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (open) {
      setDefinitionId("");
      setSelectedIds(new Set());
    }
  }, [open]);

  const { data: definitions } = useQuery({
    queryKey: ["assessment-definitions", "active"],
    queryFn: () => listAssessmentDefinitions({ status: "active" }),
  });

  const { data: students = [] } = useQuery({
    queryKey: ["students", selectedClass],
    queryFn: () => listStudentsByClass(selectedClass),
    enabled: open && !!selectedClass,
  });

  const activeDefinitions = definitions?.rows ?? [];
  const allSelected = students.length > 0 && selectedIds.size === students.length;

  const toggleAll = () => {
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(students.map((s) => s.id)));
    }
  };

  const toggleOne = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const { mutate: doCreate, isPending: creating } = useMutation({
    mutationFn: () =>
      createAssessmentSessions({
        definition_id: definitionId,
        test_mode: "class_batch",
        student_ids: [...selectedIds],
      }),
    onSuccess: (res) => {
      toast.success(t("assessment.session.createSuccess", { count: res.total }));
      queryClient.invalidateQueries({ queryKey: ["assessment-sessions"] });
      onCreated();
      onOpenChange(false);
    },
    onError: (err: Error) => toast.error(t("assessment.session.createFailed"), { description: err.message }),
  });

  const canSubmit = !!definitionId && selectedIds.size > 0;
  const sortedStudents = useMemo(() => {
    return [...students].sort((a, b) => a.name.localeCompare(b.name, "zh"));
  }, [students]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>{t("assessment.session.create")}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 flex-1 min-h-0 flex flex-col">
          <div className="space-y-2">
            <Label>{t("assessment.session.definition")}</Label>
            <Select value={definitionId} onValueChange={setDefinitionId}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("assessment.session.chooseDefinition")} />
              </SelectTrigger>
              <SelectContent>
                {activeDefinitions.map((d) => (
                  <SelectItem key={d.id} value={d.id}>
                    {d.name}（{t("assessment.definition.questionCount", { count: d.question_count })}）
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2 flex-1 min-h-0 flex flex-col">
            <div className="flex items-center justify-between">
              <Label>{t("assessment.session.chooseStudentsHint")}</Label>
              <Button type="button" variant="ghost" size="sm" className="h-7 text-xs" onClick={toggleAll}>
                {t("assessment.session.selectAll")}
                <span className="ml-1 text-muted-foreground">({selectedIds.size}/{students.length})</span>
              </Button>
            </div>
            <ScrollArea className="flex-1 min-h-0 rounded-md border border-border/60 p-2">
              {students.length === 0 ? (
                <p className="text-xs text-muted-foreground p-2">{t("assessment.session.empty")}</p>
              ) : (
                <div className="space-y-1">
                  {sortedStudents.map((s) => (
                    <label
                      key={s.id}
                      className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm cursor-pointer hover:bg-muted"
                    >
                      <Checkbox
                        checked={selectedIds.has(s.id)}
                        onCheckedChange={() => toggleOne(s.id)}
                      />
                      <span className="min-w-0 truncate">{s.name}</span>
                      <span className="ml-auto text-xs text-muted-foreground">{s.student_number}</span>
                    </label>
                  ))}
                </div>
              )}
            </ScrollArea>
          </div>
        </div>

        <DialogFooter className="border-t pt-3">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("assessment.definition.form.cancel")}
          </Button>
          <Button disabled={!canSubmit || creating} onClick={() => doCreate()}>
            {creating && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
            {t("assessment.session.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
