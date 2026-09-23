import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  value: string;
  label?: string;
  className?: string;
}

/** 状态 → 颜色映射（通用，覆盖兑换/实践/借阅/考勤/健康等状态） */
const STATUS_TONE: Record<string, string> = {
  // 通用待处理
  pending: "bg-amber-100 text-amber-700 border-amber-200",
  // 通过 / 已审核 / 已发放 / 已归还 / 正常 / 出席
  approved: "bg-blue-100 text-blue-700 border-blue-200",
  delivered: "bg-green-100 text-green-700 border-green-200",
  returned: "bg-green-100 text-green-700 border-green-200",
  normal: "bg-green-100 text-green-700 border-green-200",
  present: "bg-green-100 text-green-700 border-green-200",
  enrolled: "bg-green-100 text-green-700 border-green-200",
  ok: "bg-green-100 text-green-700 border-green-200",
  // 驳回 / 异常 / 缺勤 / 已取消 / 不一致
  rejected: "bg-red-100 text-red-700 border-red-200",
  abnormal: "bg-red-100 text-red-700 border-red-200",
  absent: "bg-red-100 text-red-700 border-red-200",
  cancelled: "bg-gray-100 text-gray-600 border-gray-200",
  left: "bg-gray-100 text-gray-600 border-gray-200",
  mismatch: "bg-red-100 text-red-700 border-red-200",
  overdue: "bg-orange-100 text-orange-700 border-orange-200",
  no_account: "bg-gray-100 text-gray-600 border-gray-200",
  // 请假 / 待处理灰色
  leave: "bg-slate-100 text-slate-600 border-slate-200",
  borrowed: "bg-blue-100 text-blue-700 border-blue-200",
};

const DEFAULT_TONE = "bg-slate-100 text-slate-600 border-slate-200";

export function StatusBadge({ value, label, className }: StatusBadgeProps) {
  return (
    <Badge
      variant="outline"
      className={cn("font-normal", STATUS_TONE[value] || DEFAULT_TONE, className)}
    >
      {label ?? value}
    </Badge>
  );
}
