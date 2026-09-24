import { cn } from "@/lib/utils";

/** 已用占总量的百分比（0-100+，超 100 表示超量） */
function usedPct(used: number, total: number): number {
  if (total <= 0) return 0;
  return Math.round((used / total) * 100);
}

function barColor(pct: number, locked: boolean): string {
  if (locked || pct >= 105) return "bg-red-500";
  if (pct >= 100) return "bg-amber-500";
  if (pct >= 90) return "bg-amber-400";
  return "bg-emerald-500";
}

/** 额度进度条：绿色正常，90%+ 转黄，100%+ 转橙，105% 硬停转红 */
export function QuotaProgressBar({
  used,
  total,
  locked = false,
  className,
}: {
  used: number;
  total: number;
  locked?: boolean;
  className?: string;
}) {
  const pct = usedPct(used, total);
  const width = Math.min(100, Math.max(0, pct));
  return (
    <div className={cn("w-full", className)}>
      <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", barColor(pct, locked))}
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

export { usedPct };
