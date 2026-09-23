import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ChevronDown, ChevronRight, FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import { useLocale } from "@/contexts/LocaleContext";
import type { ScoringDimension } from "./subjectConfigData";

interface Props {
  dimensions: ScoringDimension[];
}

export function ScoringStandards({ dimensions }: Props) {
  const { t } = useLocale();
  const [expandedId, setExpandedId] = useState<string | null>(
    dimensions[0]?.id ?? null,
  );
  const totalScore = dimensions.reduce((s, d) => s + d.maxScore, 0);

  return (
    <Card className="h-full overflow-auto">
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <FileText className="w-4 h-4 text-primary" />
          {t("settingsSubject.scoring.title")} · 七年级作文（记叙文）
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {dimensions.map((dim) => {
          const isOpen = expandedId === dim.id;
          return (
            <div
              key={dim.id}
              className="border border-border rounded-lg overflow-hidden"
            >
              <button
                onClick={() => setExpandedId(isOpen ? null : dim.id)}
                className="w-full flex items-center gap-2 px-3 py-2 hover:bg-muted/40 text-left transition-colors"
              >
                {isOpen ? (
                  <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
                )}
                <span className="text-sm font-medium flex-1">{dim.name}</span>
                <Badge variant="secondary" className="text-xs">
                  {t("settingsSubject.scoring.points", { n: dim.maxScore })}
                </Badge>
              </button>
              {isOpen && (
                <div className="px-3 pb-3 space-y-1">
                  {dim.levels.map((lv, i) => (
                    <div
                      key={i}
                      className={cn(
                        "flex items-start gap-2 p-2 rounded text-xs",
                        i === 0
                          ? "bg-emerald-50 border border-emerald-100"
                          : i === 1
                            ? "bg-blue-50 border border-blue-100"
                            : i === 2
                              ? "bg-muted/50 border border-border"
                              : i === 3
                                ? "bg-amber-50 border border-amber-100"
                                : "bg-red-50 border border-red-100",
                      )}
                    >
                      <Badge
                        variant="outline"
                        className="text-[10px] h-4 px-1 shrink-0"
                      >
                        {lv.label}
                      </Badge>
                      <span className="text-muted-foreground shrink-0">
                        （{lv.range}）
                      </span>
                      <span className="flex-1">{lv.description}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}

        <div className="text-xs text-muted-foreground pt-1">
          {t("settingsSubject.scoring.totalConvert", { total: totalScore })}
        </div>

        <Separator />

        <div className="p-3 rounded-lg bg-primary/5 border border-primary/10 space-y-1.5">
          <h4 className="text-sm font-medium text-foreground">
            {t("settingsSubject.scoring.aiCalibration")}
          </h4>
          <p className="text-xs text-muted-foreground">
            {t("settingsSubject.scoring.consistencyLabel")}
            <span className="text-primary font-medium">87%</span>
          </p>
        </div>

        <div className="space-y-1.5">
          <h4 className="text-sm font-medium text-foreground">
            {t("settingsSubject.scoring.samples")}
          </h4>
          <p className="text-xs text-muted-foreground">
            {t("settingsSubject.scoring.uploadedSamples")}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
