import { cn } from "@/lib/utils";
import { useLocale } from "@/contexts/LocaleContext";
import type { GradeCode } from "@/services/api";

const GRADE_STYLES: Record<GradeCode, string> = {
  excellent: "bg-emerald-500 text-white",
  good: "bg-sky-500 text-white",
  pass: "bg-amber-500 text-white",
  needs_work: "bg-red-500 text-white",
};

interface GradeBadgeProps {
  grade: GradeCode | null | undefined;
  className?: string;
}

/** 等级徽标：后端返回等级代码，前端只映射文案与颜色；无等级显示「—」 */
export function GradeBadge({ grade, className }: GradeBadgeProps) {
  const { t } = useLocale();
  if (!grade) {
    return (
      <span
        className={cn(
          "inline-flex items-center text-xs text-muted-foreground",
          className,
        )}
      >
        —
      </span>
    );
  }
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold leading-none",
        GRADE_STYLES[grade],
        className,
      )}
    >
      {t(`grade.${grade}`)}
    </span>
  );
}
