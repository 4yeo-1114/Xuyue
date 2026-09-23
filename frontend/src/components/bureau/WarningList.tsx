import { useState } from "react";
import { AlertTriangle, AlertCircle, CheckCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useLocale } from "@/contexts/LocaleContext";
import type { WarningAlert, WarningLevel } from "@/types/bureau";

interface WarningListProps {
  warnings: WarningAlert[];
  onFilterChange?: (level: WarningLevel | "all") => void;
}

const levelConfig = {
  red: {
    icon: AlertTriangle,
    labelKey: "bureau.warning.level.red",
    bg: "bg-red-50 border-red-200",
    badge: "border-red-200 bg-red-100 text-red-700",
    text: "text-red-800",
    value: "text-red-600",
  },
  yellow: {
    icon: AlertCircle,
    labelKey: "bureau.warning.level.yellow",
    bg: "bg-amber-50 border-amber-200",
    badge: "border-amber-200 bg-amber-100 text-amber-700",
    text: "text-amber-800",
    value: "text-amber-600",
  },
  green: {
    icon: CheckCircle,
    labelKey: "bureau.warning.level.green",
    bg: "bg-emerald-50 border-emerald-200",
    badge: "border-emerald-200 bg-emerald-100 text-emerald-700",
    text: "text-emerald-800",
    value: "text-emerald-600",
  },
};

export function WarningList({ warnings, onFilterChange }: WarningListProps) {
  const { t } = useLocale();
  const [activeFilter, setActiveFilter] = useState<WarningLevel | "all">("all");

  const filtered =
    activeFilter === "all"
      ? warnings
      : warnings.filter((w) => w.level === activeFilter);

  const handleFilter = (level: WarningLevel | "all") => {
    setActiveFilter(level);
    onFilterChange?.(level);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {(["all", "red", "yellow", "green"] as const).map((level) => (
          <Button
            key={level}
            variant={activeFilter === level ? "default" : "outline"}
            size="sm"
            onClick={() => handleFilter(level)}
            className={cn(
              activeFilter === level && level !== "all"
                ? level === "red"
                  ? "bg-red-600 hover:bg-red-700"
                  : level === "yellow"
                    ? "bg-amber-500 hover:bg-amber-600"
                    : "bg-emerald-600 hover:bg-emerald-700"
                : "",
            )}
          >
            {level === "all"
              ? t("bureau.warning.filterAll")
              : t(levelConfig[level].labelKey)}
            {level !== "all" && (
              <span className="ml-1.5 text-xs opacity-70">
                ({warnings.filter((w) => w.level === level).length})
              </span>
            )}
          </Button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="flex items-center justify-center py-12 text-sm text-slate-400">
          {t("bureau.warning.empty")}
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {filtered.map((w) => {
            const cfg = levelConfig[w.level];
            const Icon = cfg.icon;
            return (
              <Card key={w.id} className={cn("border shadow-sm", cfg.bg)}>
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Icon className={cn("h-4 w-4", cfg.value)} />
                      <Badge variant="outline" className={cn(cfg.badge)}>
                        {t(cfg.labelKey)}
                      </Badge>
                    </div>
                  </div>
                  <div className="mt-3 space-y-1.5">
                    <div className={cn("text-sm font-semibold", cfg.text)}>
                      {w.schoolName}
                    </div>
                    {w.className ? (
                      <div className="text-xs font-medium text-slate-600">
                        {w.className}
                      </div>
                    ) : null}
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                      <span>
                        {w.grade} · {w.subject}
                      </span>
                      <span>
                        {t("bureau.warning.metric", { metric: w.metric })}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-sm">
                      <span className="text-slate-500">
                        {t("bureau.warning.currentValue")}
                        <strong className={cn(cfg.value)}>{w.value}</strong>
                      </span>
                      <span className="text-slate-400">
                        {t("bureau.warning.threshold", {
                          threshold: w.threshold,
                        })}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
