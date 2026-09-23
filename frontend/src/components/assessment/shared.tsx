import { type LucideIcon } from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import type { AssessmentSessionStatus, ConsentStatus, AssessmentDefinitionStatus } from "@/services/assessmentApi";

/* ── 维度键 → i18n key ── */
const DIM_KEY_MAP: Record<string, string> = {
  learning_style: "assessment.dim.learning_style",
  interest: "assessment.dim.interest",
  social_style: "assessment.dim.social_style",
  emotion_regulation: "assessment.dim.emotion_regulation",
  challenge_coping: "assessment.dim.challenge_coping",
};

export function dimensionLabelKey(dim: string): string {
  return DIM_KEY_MAP[dim] || `assessment.dim.${dim}`;
}

/* ── 空态占位 ── */
export function EmptyState({
  icon: Icon,
  title,
  hint,
  className,
}: {
  icon: LucideIcon;
  title: string;
  hint?: string;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center py-16 text-center", className)}>
      <Icon className="w-10 h-10 text-muted-foreground/30 mb-3" />
      <p className="text-sm font-medium text-foreground">{title}</p>
      {hint ? <p className="text-xs text-muted-foreground mt-1 max-w-sm">{hint}</p> : null}
    </div>
  );
}

/* ── 需要选择班级的占位 ── */
export function NeedsClassPlaceholder({ icon }: { icon: LucideIcon }) {
  const { t } = useLocale();
  return (
    <EmptyState
      icon={icon}
      title={t("assessment.selectClassFirst")}
      hint={t("assessment.selectClassHint")}
    />
  );
}

/* ── 题组状态徽章 ── */
export function DefinitionStatusBadge({ status }: { status: AssessmentDefinitionStatus }) {
  const { t } = useLocale();
  const map: Record<AssessmentDefinitionStatus, string> = {
    draft: "assessment.definition.status.draft",
    active: "assessment.definition.status.active",
    retired: "assessment.definition.status.retired",
  };
  const style: Record<AssessmentDefinitionStatus, string> = {
    draft: "bg-muted text-muted-foreground",
    active: "bg-emerald-100 text-emerald-700 border-emerald-200",
    retired: "bg-slate-100 text-slate-500 border-slate-200",
  };
  return (
    <Badge variant="outline" className={cn("border-transparent", style[status])}>
      {t(map[status])}
    </Badge>
  );
}

/* ── 会话状态徽章 ── */
export function SessionStatusBadge({ status }: { status: AssessmentSessionStatus }) {
  const { t } = useLocale();
  const map: Record<AssessmentSessionStatus, string> = {
    pending: "assessment.session.status.pending",
    in_progress: "assessment.session.status.in_progress",
    submitted: "assessment.session.status.submitted",
    graded: "assessment.session.status.graded",
    canceled: "assessment.session.status.canceled",
  };
  const style: Record<AssessmentSessionStatus, string> = {
    pending: "bg-slate-100 text-slate-600 border-slate-200",
    in_progress: "bg-sky-100 text-sky-700 border-sky-200",
    submitted: "bg-emerald-100 text-emerald-700 border-emerald-200",
    graded: "bg-violet-100 text-violet-700 border-violet-200",
    canceled: "bg-rose-100 text-rose-600 border-rose-200",
  };
  return (
    <Badge variant="outline" className={cn("border-transparent", style[status])}>
      {t(map[status])}
    </Badge>
  );
}

/* ── 监护人同意状态徽章 ── */
export function ConsentBadge({ status }: { status: ConsentStatus }) {
  const { t } = useLocale();
  const map: Record<ConsentStatus, string> = {
    not_required: "assessment.result.consent.not_required",
    granted: "assessment.result.consent.granted",
    withdrawn: "assessment.result.consent.withdrawn",
  };
  const style: Record<ConsentStatus, string> = {
    not_required: "bg-slate-100 text-slate-500 border-slate-200",
    granted: "bg-emerald-100 text-emerald-700 border-emerald-200",
    withdrawn: "bg-rose-100 text-rose-600 border-rose-200",
  };
  return (
    <Badge variant="outline" className={cn("border-transparent", style[status])}>
      {t(map[status])}
    </Badge>
  );
}

/* ── 维度占比可视化（Progress 条） ── */
export function DimensionBars({
  percents,
  points,
  className,
}: {
  percents?: Record<string, number>;
  points?: Record<string, number>;
  className?: string;
}) {
  const { t } = useLocale();
  const entries = Object.entries(percents || {});
  if (entries.length === 0) {
    return <p className="text-xs text-muted-foreground">{t("assessment.empty")}</p>;
  }
  const sorted = entries.sort((a, b) => b[1] - a[1]);
  return (
    <div className={cn("space-y-2.5", className)}>
      {sorted.map(([dim, pct]) => (
        <div key={dim}>
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="text-muted-foreground">{t(dimensionLabelKey(dim))}</span>
            <span className="font-medium tabular-nums">
              {points?.[dim] != null ? `${pct.toFixed(1)}% · ${points[dim]} 题` : `${pct.toFixed(1)}%`}
            </span>
          </div>
          <Progress value={pct} className="h-2" />
        </div>
      ))}
    </div>
  );
}
