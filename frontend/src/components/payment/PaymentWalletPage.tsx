import { useQuery } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Wallet, TrendingDown, TrendingUp, Info, ScanLine } from "lucide-react";
import { fetchPaymentAccount, fetchPaymentUsage } from "@/services/paymentApi";

/* ── 金额格式化：后端一律「分」，展示统一到元（两位小数） ── */
export function fenToYuan(fen: number): string {
  return (Number(fen || 0) / 100).toFixed(2);
}

/** 账户状态中文标签（后端 status 取值沿用本仓习惯；未知值原样透出，不猜） */
const ACCOUNT_STATUS_LABEL: Record<string, string> = {
  active: "正常",
  frozen: "已冻结",
  closed: "已注销",
};

/* ── 指标卡 ── */
function StatCard({
  icon: Icon,
  label,
  value,
  unit,
  sub,
  color,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  color: string;
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-sm text-muted-foreground">{label}</p>
            <p className="mt-1 flex items-baseline gap-1">
              <span className="text-2xl font-semibold tabular-nums">
                {value}
              </span>
              {unit ? (
                <span className="text-sm text-muted-foreground">{unit}</span>
              ) : null}
            </p>
            {sub ? (
              <p className="mt-1 text-xs text-muted-foreground">{sub}</p>
            ) : null}
          </div>
          <div className={`rounded-xl p-2 ${color}`}>
            <Icon className="h-5 w-5" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * 我的余额（口径 B · 个人账本）。
 *
 * ⚠️ 本页数据源 = `payment_accounts` + `usage_events`，与「扫描消耗 / 用量汇总」
 * （口径 A · 平台成本核算）**不是同一本账**，数值不可比、不可相加（设计稿 §1、§9 P0-9）。
 * ⛔ 本页**只读**：Phase 1/2 的充值、购买、套餐入口一律不在此出现。
 */
export function PaymentWalletPage() {
  const { data: account, isLoading: loadingAccount } = useQuery({
    queryKey: ["payment", "account"],
    queryFn: fetchPaymentAccount,
  });

  const { data: usage, isLoading: loadingUsage } = useQuery({
    queryKey: ["payment", "usage", "wallet-overview"],
    queryFn: () => fetchPaymentUsage({ limit: 1 }),
  });

  if (loadingAccount) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-[110px] w-full" />
        <Skeleton className="h-[110px] w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* ── 口径标注（P0-9）：老师不得误认为下方「扫描消耗/用量汇总」是自己账单 ── */}
      <div className="flex items-start gap-2 rounded-lg border border-primary/20 bg-primary/5 px-4 py-3 text-sm">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
        <div className="text-muted-foreground">
          <span className="font-medium text-foreground">
            本页是你的个人账本
          </span>
          （余额与资金流水）。
          <span className="mx-1">
            侧边栏「扫描消耗 / 用量汇总」是
            <span className="font-medium text-foreground">平台成本口径</span>
            的用量统计，
          </span>
          <span className="font-medium text-foreground">
            不是你的账单，两者数值不可比、不可相加。
          </span>
        </div>
      </div>

      {/* ── 余额三卡 ── */}
      <div className="grid gap-4 md:grid-cols-3">
        <StatCard
          icon={Wallet}
          label="可用余额"
          value={`¥${fenToYuan(account?.balance_fen ?? 0)}`}
          sub="账户余额（元）"
          color="bg-primary/10 text-primary"
        />
        <StatCard
          icon={TrendingUp}
          label="累计入账"
          value={`¥${fenToYuan(account?.total_recharged_fen ?? 0)}`}
          sub="含后台人工入账 / 赠送"
          color="bg-emerald-500/10 text-emerald-600"
        />
        <StatCard
          icon={TrendingDown}
          label="累计消耗"
          value={`¥${fenToYuan(account?.total_consumed_fen ?? 0)}`}
          sub="已扣费合计（元）"
          color="bg-amber-500/10 text-amber-600"
        />
      </div>

      {/* ── 账户状态 ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">账户状态</CardTitle>
        </CardHeader>
        <CardContent className="text-sm">
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">当前状态：</span>
            <Badge variant="secondary">
              {ACCOUNT_STATUS_LABEL[account?.status ?? ""] ?? account?.status}
            </Badge>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            账户由系统在你首次使用后自动开通；余额变更的每一笔都会记入资金流水。
          </p>
        </CardContent>
      </Card>

      {/* ── 用量概览（口径 B 净额） ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <ScanLine className="h-4 w-4 text-primary" />
            我的用量
          </CardTitle>
          <CardDescription>
            口径 B：按事件净额统计（含删除冲正），与平台成本口径无关
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loadingUsage ? (
            <Skeleton className="h-16 w-full" />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="rounded-lg border p-4">
                <p className="text-sm text-muted-foreground">累计批改</p>
                <p className="mt-1 text-2xl font-semibold tabular-nums">
                  {usage?.total_grade ?? 0}
                  <span className="ml-1 text-sm font-normal text-muted-foreground">
                    份
                  </span>
                </p>
              </div>
              <div className="rounded-lg border p-4">
                <p className="text-sm text-muted-foreground">累计上传</p>
                <p className="mt-1 text-2xl font-semibold tabular-nums">
                  {usage?.total_upload ?? 0}
                  <span className="ml-1 text-sm font-normal text-muted-foreground">
                    份
                  </span>
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
