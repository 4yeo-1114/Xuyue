import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export interface TypicalErrorItem {
  key: string;
  title: string;
  count: number;
  percent: number;
  description?: string;
  students?: string[];
}

interface TypicalErrorsProps {
  errors: TypicalErrorItem[];
  questionKnowledge: string;
}

export function TypicalErrors({
  errors,
  questionKnowledge,
}: TypicalErrorsProps) {
  const { t, locale } = useLocale();
  const [viewing, setViewing] = useState<TypicalErrorItem | null>(null);

  return (
    <Card className="flex-1 min-w-[320px]" data-tour="qa-errors">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">
          {t("classDetail.typicalErrorsBase")}
          {errors.length
            ? t("classDetail.topCountLabel", { count: errors.length })
            : ""}
          {questionKnowledge
            ? t("classDetail.knowledgeParenthesized", {
                name: questionKnowledge,
              })
            : ""}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-xs">
        {errors.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border/60 p-4 text-center text-muted-foreground/60">
            {t("classDetail.noTypicalErrorData")}
          </div>
        ) : (
          errors.map((e) => (
            <div
              key={e.key}
              className="rounded-lg border border-border/40 p-3 space-y-1.5"
            >
              <div className="flex items-center justify-between">
                <span className="font-semibold text-foreground">
                  {e.title}
                  {e.count > 0 && (
                    <span className="text-muted-foreground font-normal">
                      {t("classDetail.countWithPct", {
                        count: e.count,
                        pct: e.percent > 0 ? `，${e.percent}%` : "",
                      })}
                    </span>
                  )}
                </span>
                {e.percent > 0 && (
                  <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
                    <div
                      className={cn(
                        "h-full rounded-full",
                        e.percent > 40
                          ? "bg-red-500"
                          : e.percent > 25
                            ? "bg-amber-500"
                            : "bg-blue-500",
                      )}
                      style={{ width: `${Math.min(e.percent, 100)}%` }}
                    />
                  </div>
                )}
              </div>
              {e.description && (
                <p className="text-muted-foreground">{e.description}</p>
              )}
              <div className="flex gap-2 pt-1">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 px-2 text-[10px]"
                      disabled={!e.students?.length}
                      onClick={() => setViewing(e)}
                    >
                      {t("classDetail.viewListLabel")}
                      {e.students?.length
                        ? t("classDetail.countWithPct", {
                            count: e.students.length,
                            pct: "",
                          })
                        : ""}
                    </Button>
                  </TooltipTrigger>
                  {!e.students?.length && (
                    <TooltipContent>
                      {t("classDetail.studentListEmpty")}
                    </TooltipContent>
                  )}
                </Tooltip>
              </div>
            </div>
          ))
        )}
      </CardContent>

      <Dialog
        open={!!viewing}
        onOpenChange={(open) => {
          if (!open) setViewing(null);
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("classDetail.studentListDialogTitle")}</DialogTitle>
          </DialogHeader>
          {viewing?.students?.length ? (
            <div className="flex flex-wrap gap-1.5 max-h-64 overflow-y-auto pr-1">
              {viewing.students.map((name) => (
                <span
                  key={name}
                  className="rounded-md bg-muted/40 border border-border/50 px-2 py-1 text-xs text-foreground"
                >
                  {name}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground/60">
              {t("classDetail.studentListEmpty")}
            </p>
          )}
        </DialogContent>
      </Dialog>
    </Card>
  );
}
