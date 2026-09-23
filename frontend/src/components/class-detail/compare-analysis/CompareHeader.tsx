import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useMemo } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSchoolLevel } from "@/i18n";
import { Button } from "@/components/ui/button";
import { GitCompare, FileDown, Loader2 } from "lucide-react";

interface CompareHeaderProps {
  selectedSubject: string;
  schoolLevel: string;
  /** 当前对标范围（受控）；「年级内部」已启用，其余范围保持 disabled */
  scope?: string;
  onScopeChange?: (scope: string) => void;
  onExportPDF?: () => void;
  exporting?: boolean;
}

export function CompareHeader({
  selectedSubject,
  schoolLevel,
  scope = "grade",
  onScopeChange,
  onExportPDF,
  exporting,
}: CompareHeaderProps) {
  const { t, locale } = useLocale();
  const scopeOptions = useMemo(
    () => [
      { value: "grade", label: t("classDetail.年级内部"), disabled: false },
      { value: "cross-grade", label: t("classDetail.跨年级"), disabled: true },
      {
        value: "inter-school",
        label: t("classDetail.校际联盟"),
        disabled: true,
      },
      { value: "history", label: t("classDetail.历史同期"), disabled: true },
    ],
    [t],
  );
  const schoolLabel =
    translateSchoolLevel(locale, schoolLevel) || t("classDetail.高中");

  return (
    <div className="rounded-xl border border-border/50 bg-card p-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
            <GitCompare className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-foreground">
              {t("classDetail.compare.header.title")}
            </h2>
            <p className="text-xs text-muted-foreground">
              {t("classDetail.compare.header.subtitle", {
                school: schoolLabel,
                subject: selectedSubject,
              })}
            </p>
          </div>
        </div>
        <div data-tour="ca-scope" className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-muted-foreground">
            {t("classDetail.对标范围")}
          </span>
          <Select
            value={scope}
            onValueChange={(value) => onScopeChange?.(value)}
          >
            <SelectTrigger
              aria-label={t("classDetail.对标范围")}
              className="w-36 h-8 text-xs"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {scopeOptions.map((s) => (
                <SelectItem key={s.value} value={s.value} disabled={s.disabled}>
                  {s.label}
                  {s.disabled
                    ? t("classDetail.compare.header.unsupportedSuffix")
                    : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {onExportPDF && (
            <Button
              variant="outline"
              size="sm"
              className="h-8 text-xs gap-1.5"
              onClick={onExportPDF}
              disabled={exporting}
            >
              {exporting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <FileDown className="w-3.5 h-3.5" />
              )}
              {exporting
                ? t("classDetail.compare.header.exporting")
                : t("classDetail.导出对比报告")}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
