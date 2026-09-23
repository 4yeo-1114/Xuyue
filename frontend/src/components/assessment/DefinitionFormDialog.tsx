import { useEffect, useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  createAssessmentDefinition,
  updateAssessmentDefinition,
  type AssessmentDefinition,
  type AssessmentDefinitionStatus,
  type AssessmentQuestionItem,
} from "@/services/assessmentApi";

const DOMAINS = ["personality", "interest", "learning_style", "self_built_survey"] as const;
const GRADE_RANGES = ["all", "primary", "junior", "senior"] as const;
const STATUSES: AssessmentDefinitionStatus[] = ["draft", "active", "retired"];

interface DefinitionFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing?: AssessmentDefinition | null;
}

function stringifyQuestions(questions?: AssessmentQuestionItem[] | null): string {
  if (!questions || questions.length === 0) return "";
  return JSON.stringify(questions, null, 2);
}

export function DefinitionFormDialog({ open, onOpenChange, editing }: DefinitionFormDialogProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();

  const [name, setName] = useState("");
  const [domain, setDomain] = useState<string>("self_built_survey");
  const [gradeRange, setGradeRange] = useState<string>("all");
  const [status, setStatus] = useState<AssessmentDefinitionStatus>("draft");
  const [consentRequired, setConsentRequired] = useState(true);
  const [description, setDescription] = useState("");
  const [questionsText, setQuestionsText] = useState("");

  useEffect(() => {
    if (open) {
      setName(editing?.name ?? "");
      setDomain(editing?.domain ?? "self_built_survey");
      setGradeRange(editing?.grade_range ?? "all");
      setStatus(editing?.status ?? "draft");
      setConsentRequired(editing?.consent_required ?? true);
      setDescription(editing?.description ?? "");
      setQuestionsText(stringifyQuestions(editing?.questions));
    }
  }, [open, editing]);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["assessment-definitions"] });

  const { mutate: doSave, isPending: saving } = useMutation({
    mutationFn: async () => {
      let parsed: AssessmentQuestionItem[];
      try {
        const trimmed = questionsText.trim();
        if (!trimmed) throw new Error("empty");
        parsed = JSON.parse(trimmed) as AssessmentQuestionItem[];
        if (!Array.isArray(parsed) || parsed.length === 0) throw new Error("empty");
        for (const q of parsed) {
          if (!q.id || !q.dim || !q.text || !q.options || q.options.length < 2) throw new Error("invalid");
        }
      } catch {
        throw new Error("json");
      }
      const payload = {
        name: name.trim(),
        domain,
        grade_range: gradeRange,
        version: editing?.version ?? 1,
        status,
        consent_required: consentRequired,
        description: description.trim() || null,
        questions: parsed,
      };
      if (editing) {
        return updateAssessmentDefinition(editing.id, payload);
      }
      return createAssessmentDefinition(payload);
    },
    onSuccess: () => {
      toast.success(editing ? t("assessment.definition.updated") : t("assessment.definition.created"));
      invalidate();
      onOpenChange(false);
    },
    onError: (err: Error) => {
      if (err.message === "json") {
        toast.error(t("assessment.definition.form.questionsInvalid"));
      } else if (err.message === "empty") {
        toast.error(t("assessment.definition.form.questionsEmpty"));
      } else {
        toast.error(editing ? t("assessment.definition.updateFailed") : t("assessment.definition.createFailed"), {
          description: err.message,
        });
      }
    },
  });

  const nameValid = name.trim().length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {editing ? t("assessment.definition.form.title.edit") : t("assessment.definition.form.title.create")}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2 space-y-2">
              <Label htmlFor="def-name">{t("assessment.definition.form.name")}</Label>
              <Input
                id="def-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("assessment.definition.form.namePlaceholder")}
                maxLength={128}
              />
            </div>

            <div className="space-y-2">
              <Label>{t("assessment.definition.form.domain")}</Label>
              <Select value={domain} onValueChange={setDomain}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DOMAINS.map((d) => (
                    <SelectItem key={d} value={d}>
                      {t(`assessment.definition.domain.${d}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>{t("assessment.definition.form.gradeRange")}</Label>
              <Select value={gradeRange} onValueChange={setGradeRange}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {GRADE_RANGES.map((g) => (
                    <SelectItem key={g} value={g}>
                      {t(`assessment.definition.grade.${g}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>{t("assessment.definition.form.status")}</Label>
              <Select value={status} onValueChange={(v) => setStatus(v as AssessmentDefinitionStatus)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STATUSES.map((s) => (
                    <SelectItem key={s} value={s}>
                      {t(`assessment.definition.status.${s}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-end pb-1">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <Switch checked={consentRequired} onCheckedChange={setConsentRequired} />
                {t("assessment.definition.form.consentRequired")}
              </label>
            </div>

            <div className="col-span-2 space-y-2">
              <Label htmlFor="def-desc">{t("assessment.definition.form.description")}</Label>
              <Textarea
                id="def-desc"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={t("assessment.definition.form.descriptionPlaceholder")}
                rows={2}
              />
            </div>

            <div className="col-span-2 space-y-2">
              <Label htmlFor="def-questions">{t("assessment.definition.form.questions")}</Label>
              <Textarea
                id="def-questions"
                value={questionsText}
                onChange={(e) => setQuestionsText(e.target.value)}
                placeholder={t("assessment.definition.form.questionsPlaceholder")}
                rows={12}
                className="font-mono text-xs"
              />
              <p className="text-xs text-muted-foreground">{t("assessment.definition.seedHint")}</p>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("assessment.definition.form.cancel")}
          </Button>
          <Button onClick={() => doSave()} disabled={!nameValid || saving}>
            {saving && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
            {saving ? t("assessment.definition.form.saving") : t("assessment.definition.form.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
