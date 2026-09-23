import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLocale } from "@/contexts/LocaleContext";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import type { QuestionTarget } from "./targetedData";

interface QuestionSelectorProps {
  targets: QuestionTarget[];
  selected: QuestionTarget | null;
  onSelect: (q: QuestionTarget) => void;
}

export function QuestionSelector({ targets, selected, onSelect }: QuestionSelectorProps) {
  const { t, locale } = useLocale();

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">{t("classDetail.selectTargetQuestionTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {targets.map(q => (
            <button
              key={q.id}
              onClick={() => onSelect(q)}
              className={cn(
                "w-full p-3 rounded-lg border text-left transition-all hover:shadow-sm",
                selected?.id === q.id ? "ring-2 ring-primary border-primary/30 bg-primary/5" : "border-border/50"
              )}
            >
              <div className="flex items-start justify-between mb-1.5">
                <span className="text-xs font-semibold flex-1 pr-2">{q.content}</span>
                <Badge variant={q.errorRate > 50 ? "destructive" : "secondary"} className="text-[10px] shrink-0">
                  <AlertTriangle className="w-3 h-3 mr-0.5" />{t("classDetail.errorRateLabel", { rate: q.errorRate })}
                </Badge>
              </div>
              <div className="flex items-center gap-2 text-[11px] text-muted-foreground flex-wrap">
                <span className="text-muted-foreground">{q.source}</span>
                <span className="flex items-center gap-0.5"><Users className="w-3 h-3" />{t("classDetail.peopleWrongLabel", { count: q.affectedStudents.length })}</span>
                {q.knowledgePoints.map(kp => (
                  <Badge key={kp} variant="outline" className="text-[10px] px-1.5 py-0">{kp}</Badge>
                ))}
              </div>
              <div className="mt-1.5 flex gap-1">
                {q.typicalErrors.map(e => (
                  <span key={e} className="text-[10px] px-1.5 py-0.5 rounded bg-destructive/10 text-destructive">{e}</span>
                ))}
              </div>
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
