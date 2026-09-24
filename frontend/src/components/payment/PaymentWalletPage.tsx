import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { QuotaProgressBar, usedPct } from "@/components/quota/QuotaProgressBar";
import { fetchMyQuota, fetchQuotaTiers } from "@/services/quotaApi";
import { createPaymentOrder } from "@/services/paymentApi";
import { ApiError } from "@/services/api";
import { toast } from "sonner";
import {
  Wallet,
  Zap,
  Gauge,
  CalendarDays,
  AlertTriangle,
  ShieldCheck,
  CreditCard,
  Info,
} from "lucide-react";

/** 支付通道标识（与后端 payment channels 对齐） */
const CHANNEL_WECHAT = "wechat_pay";
const CHANNEL_ALIPAY = "alipay";

function StatCard({
  icon: Icon,
  label,
  value,
  unit,
  sub,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  unit?: string;
  sub?: string;
}) {
  return (
    <Card className="card-elevated">
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div className="space-y-1 min-w-0">
            <p className="text-sm text-muted-foreground">{label}</p>
            <div className="flex items-baseline gap-1">
              <span className="text-2xl font-semibold tabular-nums">{value}</span>
              {unit && <span className="text-sm text-muted-foreground">{unit}</span>}
            </div>
            {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
          </div>
          <Icon className="w-5 h-5 text-muted-foreground/50" strokeWidth={1.75} />
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * 我的钱包（面数口径 · 0924 需求）。
 *
 * 数据源 = `grading_quota`（1 上传图/页 = 1 面），与同事的「分余额」账本无关。
 * 充值 = 微信/支付宝下单（同事支付通道），通道确认收款后由支付桥按档位自动加面。
 * ⛔ 通道凭据未配置时后端返回 501，前端据此提示「联系管理员手动充值」。
 */
export function PaymentWalletPage() {
  const queryClient = useQueryClient();

  const { data: quota, isLoading: loadingQuota } = useQuery({
    queryKey: ["quota", "me"],
    queryFn: fetchMyQuota,
  });
  const { data: tiers } = useQuery({
    queryKey: ["quota", "tiers"],
    queryFn: fetchQuotaTiers,
  });

  const recharge = useMutation({
    mutationFn: ({ amountYuan, channel }: { amountYuan: number; channel: string }) =>
      createPaymentOrder(amountYuan * 100, channel),
    onSuccess: (res, vars) => {
      toast.success(
        `已生成 ¥${vars.amountYuan} 充值订单（${res.order_id}），支付完成后额度自动到账`,
      );
      queryClient.invalidateQueries({ queryKey: ["quota", "me"] });
      queryClient.invalidateQueries({ queryKey: ["quota", "me", "recharge-logs"] });
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 501) {
        toast.error("支付通道尚未配置，请联系管理员手动充值");
      } else {
        toast.error(e instanceof Error ? e.message : "下单失败");
      }
    },
  });

  if (loadingQuota) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-40" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
        <Skeleton className="h-40" />
      </div>
    );
  }

  if (!quota) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="w-4 h-4" />
        <AlertTitle>加载失败</AlertTitle>
        <AlertDescription>无法获取额度信息</AlertDescription>
      </Alert>
    );
  }

  const pct = quota.used_pct ?? usedPct(quota.used_pages, quota.total_pages);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">我的钱包</h2>
          <p className="text-sm text-muted-foreground mt-1">
            批改按「面」计费：1 张上传图 / 1 页 = 1 面
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-muted-foreground" />
          {quota.locked || pct >= 105 ? (
            <Badge variant="destructive">已停用</Badge>
          ) : pct >= 90 ? (
            <Badge className="bg-amber-500 text-white">接近上限</Badge>
          ) : (
            <Badge variant="secondary">额度充足</Badge>
          )}
        </div>
      </div>

      {(quota.locked || pct >= 105) && (
        <Alert variant="destructive">
          <AlertTriangle className="w-4 h-4" />
          <AlertTitle>批改额度已用尽</AlertTitle>
          <AlertDescription>
            已用面数超过总量的 105%，系统已自动停止批改功能，请及时充值。
          </AlertDescription>
        </Alert>
      )}

      {/* ── 面数余额 ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={Wallet} label="总量" value={String(quota.total_pages)} unit="面" />
        <StatCard icon={Zap} label="已用" value={String(quota.used_pages)} unit="面" />
        <StatCard
          icon={Gauge}
          label="剩余"
          value={String(Math.max(0, quota.available))}
          unit="面"
          sub={quota.available < 0 ? "已超量" : undefined}
        />
        <StatCard icon={CalendarDays} label="今日批改" value={String(quota.today_pages)} unit="面" />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>已用 / 总量</CardTitle>
          <CardDescription>已用占总量的 {pct.toFixed(1)}%</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <QuotaProgressBar
            used={quota.used_pages}
            total={quota.total_pages}
            locked={quota.locked}
          />
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>0</span>
            <span>
              总量 {quota.total_pages} 面（105% = {Math.ceil(quota.total_pages * 1.05)} 面停）
            </span>
          </div>
        </CardContent>
      </Card>

      {/* ── 充值档位 ── */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CreditCard className="h-4 w-4 text-primary" />
            充值
          </CardTitle>
          <CardDescription>
            选择档位后通过微信或支付宝支付；支付通道确认收款后额度自动到账
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-start gap-2 rounded-md border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>
              微信/支付宝通道尚未接入时，可联系管理员手动充值（到账面数 = 基准 + 赠送）。
            </span>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {(tiers ?? []).map((t) => {
              const pendingChannel = recharge.isPending ? recharge.variables?.channel : null;
              return (
                <div key={t.amount_yuan} className="rounded-lg border p-4 space-y-3">
                  <div className="flex items-baseline justify-between">
                    <span className="text-2xl font-semibold tabular-nums">¥{t.amount_yuan}</span>
                    <span className="text-sm text-muted-foreground">
                      {t.bonus_pages > 0 ? `送 ${t.bonus_pages} 面` : "无赠送"}
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    到账{" "}
                    <span className="font-semibold text-foreground">{t.total_pages} 面</span>
                    （基准 {t.base_pages} + 赠送 {t.bonus_pages}）
                  </p>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      className="flex-1 bg-emerald-600 hover:bg-emerald-700"
                      disabled={recharge.isPending}
                      onClick={() =>
                        recharge.mutate({ amountYuan: t.amount_yuan, channel: CHANNEL_WECHAT })
                      }
                    >
                      {pendingChannel === CHANNEL_WECHAT ? "下单中…" : "微信充值"}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="flex-1"
                      disabled={recharge.isPending}
                      onClick={() =>
                        recharge.mutate({ amountYuan: t.amount_yuan, channel: CHANNEL_ALIPAY })
                      }
                    >
                      {pendingChannel === CHANNEL_ALIPAY ? "下单中…" : "支付宝充值"}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
