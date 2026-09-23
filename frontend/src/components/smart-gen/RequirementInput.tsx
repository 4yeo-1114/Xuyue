import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Wand2, Loader2 } from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";

interface Props {
  onGenerate: (params: {
    content: string;
    objective: string;
    studentProfile: string;
    requirements: string;
  }) => void;
  isGenerating: boolean;
}

export function RequirementInput({ onGenerate, isGenerating }: Props) {
  const { t } = useLocale();
  const [content, setContent] = useState("");
  const [objective, setObjective] = useState("");
  const [studentProfile, setStudentProfile] = useState("");
  const [requirements, setRequirements] = useState("");

  const handleGenerate = () => {
    onGenerate({ content, objective, studentProfile, requirements });
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">
          {t("smartGen.requirement.title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <label className="text-sm font-medium text-foreground">
            {t("smartGen.requirement.labelContent")}
          </label>
          <Textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder={t("smartGen.requirement.placeholderContent")}
            rows={3}
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground">
              {t("smartGen.requirement.labelObjective")}
            </label>
            <Textarea
              value={objective}
              onChange={(e) => setObjective(e.target.value)}
              placeholder={t("smartGen.requirement.placeholderObjective")}
              rows={2}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground">
              {t("smartGen.requirement.labelStudentProfile")}
            </label>
            <Input
              value={studentProfile}
              onChange={(e) => setStudentProfile(e.target.value)}
              placeholder={t("smartGen.requirement.placeholderStudentProfile")}
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <label className="text-sm font-medium text-foreground">
            {t("smartGen.requirement.labelRequirements")}
          </label>
          <Textarea
            value={requirements}
            onChange={(e) => setRequirements(e.target.value)}
            placeholder={t("smartGen.requirement.placeholderRequirements")}
            rows={2}
          />
        </div>

        <div className="flex justify-end">
          <Button
            className="gap-2"
            onClick={handleGenerate}
            disabled={isGenerating || !content.trim()}
          >
            {isGenerating ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Wand2 className="w-4 h-4" />
            )}
            {isGenerating
              ? t("smartGen.requirement.aiGenerating")
              : t("smartGen.requirement.generate")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
