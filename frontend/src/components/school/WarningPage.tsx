import { useQuery } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import {
  AlertTriangle,
  CheckCircle2,
  Inbox,
  RefreshCw,
  ShieldAlert,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { WarningList } from "@/components/bureau/WarningList";
import { getSchoolWarnings } from "@/services/api";

interface StatCardProps {
  icon: LucideIcon;
  label: string;
  value: number | string;
  tone: "default" | "red" | "yellow" | "green";
}

const toneClasses: Record<
  StatCardProps["tone"],
  { icon: string; value: string; card: string }
> = {
  default: { icon: "text-primary", value: "text-foreground", card: "" },
  red: {
    icon: "text-red-600",
    value: "text-red-600",
    card: "border-red-200",
  },
  yellow: {
    icon: "text-amber-600",
    value: "text-amber-600",
    card: "border-amber-200",
  },
  green: {
    icon: "text-emerald-600",
    value: "text-emerald-600",
    card: "border-emerald-200",
  },
};

function StatCard({ icon: Icon, label, value, tone }: StatCardProps) {
  const cls = toneClasses[tone];
  return (
    <Card className={cn("border-border/50", cls.card)}>
      <CardContent className="p-5">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Icon className={cn("h-4 w-4", cls.icon)} />
          <p className="text-sm truncate">{label}</p>
        </div>
        <div className="mt-3">
          <span
            className={cn("text-2xl font-semibold tabular-nums", cls.value)}
          >
            {value}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

/** 学校版预警中心：接真实后端 GET /school/warnings，展示 summary + 预警列表 */
export function WarningPage() {
  const { t } = useLocale();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["school-warnings"],
    queryFn: getSchoolWarnings,
    staleTime: 30_000,
  });

  const summary = data?.summary;
  const warnings = data?.warnings ?? [];

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500 pb-10">
      {/* 页头 */}
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <ShieldAlert className="w-6 h-6 text-primary" />
            {t("schoolWarning.title")}
          </h2>
          <p className="text-muted-foreground mt-1">
            {t("schoolWarning.subtitle")}
          </p>
        </div>
        {data?.schoolName ? (
          <span className="inline-flex items-center gap-1.5">
            <span className="px-3 py-1 rounded-full bg-primary/10 text-primary font-medium text-xs">
              {data.schoolName}
            </span>
          </span>
        ) : null}
      </div>

      {/* 统计卡 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={AlertTriangle}
          label={t("schoolWarning.stats.total")}
          value={isLoading ? "…" : (summary?.total ?? 0)}
          tone="default"
        />
        <StatCard
          icon={AlertTriangle}
          label={t("schoolWarning.stats.red")}
          value={isLoading ? "…" : (summary?.red ?? 0)}
          tone="red"
        />
        <StatCard
          icon={AlertTriangle}
          label={t("schoolWarning.stats.yellow")}
          value={isLoading ? "…" : (summary?.yellow ?? 0)}
          tone="yellow"
        />
        <StatCard
          icon={CheckCircle2}
          label={t("schoolWarning.stats.green")}
          value={isLoading ? "…" : (summary?.green ?? 0)}
          tone="green"
        />
      </div>

      {/* 预警列表 */}
      {isLoading ? (
        <Card>
          <CardContent className="p-6 space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </CardContent>
        </Card>
      ) : isError ? (
        <Card>
          <CardContent className="p-8 text-center text-muted-foreground">
            <Inbox className="w-8 h-8 mx-auto mb-2 text-muted-foreground/40" />
            <p className="text-sm">{t("schoolWarning.loadError")}</p>
            <Button
              variant="outline"
              size="sm"
              className="mt-3 gap-1.5"
              onClick={() => refetch()}
            >
              <RefreshCw className="w-3.5 h-3.5" />
              {t("schoolWarning.retry")}
            </Button>
          </CardContent>
        </Card>
      ) : (
        <WarningList warnings={warnings} />
      )}
    </div>
  );
}
