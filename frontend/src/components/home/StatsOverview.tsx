import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  PenTool,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLocale } from "@/contexts/LocaleContext";
import { useAuth } from "@/hooks/useAuth";
import { useGlobalFilters } from "@/hooks/useGlobalFilters";
import { isPlatformAdmin } from "@/lib/adminAccess";
import { getDashboardOverview } from "@/services/dashboardApi";

interface StatsOverviewProps {
  selectedSubject: string;
  selectedClass: string;
  onNavChange: (id: string) => void;
}

function StatCard({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="p-5 rounded-xl bg-card border border-border/50 card-elevated">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icon className="w-4 h-4 shrink-0" />
        <p className="text-sm truncate">{label}</p>
      </div>
      <div className="mt-3 flex items-baseline gap-1">
        <span className="text-2xl font-semibold tabular-nums">{value}</span>
        {hint ? (
          <span className="text-sm text-muted-foreground">{hint}</span>
        ) : null}
      </div>
    </div>
  );
}

export function StatsOverview({
  selectedSubject,
  selectedClass,
  onNavChange,
}: StatsOverviewProps) {
  const { t } = useLocale();
  const { user } = useAuth();
  const { grade } = useGlobalFilters();
  const isAdmin = isPlatformAdmin(user);

  const overviewQuery = useQuery({
    queryKey: ["admin-dashboard", "home-overview", selectedClass, grade],
    queryFn: () =>
      getDashboardOverview({
        grade: grade || undefined,
        class_id: selectedClass || undefined,
      }),
    enabled: isAdmin,
    staleTime: 5 * 60 * 1000,
  });

  if (!isAdmin) {
    return (
      <div
        data-tour="stats-overview"
        className="p-5 rounded-xl bg-card border border-border/50 card-elevated"
      >
        <p className="text-sm text-muted-foreground">
          {t("home.stats.adminOnly")}
        </p>
      </div>
    );
  }

  const d = overviewQuery.data;

  return (
    <div
      data-tour="stats-overview"
      className="grid grid-cols-3 gap-4 animate-fade-in"
    >
      {/* 五育均分 */}
      <StatCard
        icon={Sparkles}
        label={t("dashboard.kpi.growthScoreAvg")}
        value={d?.growth_score_avg?.toFixed(2) ?? "…"}
      />

      {/* 近期批改量 */}
      <StatCard
        icon={PenTool}
        label={t("dashboard.kpi.gradingCount")}
        value={d ? String(d.grading_count) : "…"}
        hint={t("dashboard.kpi.gradingUnit", { days: d?.grading_days ?? 30 })}
      />

      {/* 健康预警 */}
      <div className="p-5 rounded-xl bg-card border border-destructive/20 card-elevated">
        <div className="flex items-center gap-2 text-muted-foreground">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <p className="text-sm truncate">{t("dashboard.kpi.alertCount")}</p>
        </div>
        <div className="mt-3 flex items-baseline gap-1">
          <span className="text-2xl font-semibold tabular-nums">
            {d ? String(d.alert_count) : "…"}
          </span>
        </div>
        <Button
          variant="link"
          size="sm"
          className="mt-3 p-0 h-auto text-xs"
          onClick={() => onNavChange("school-dashboard")}
        >
          {t("home.stats.goHandle")}
        </Button>
      </div>
    </div>
  );
}
