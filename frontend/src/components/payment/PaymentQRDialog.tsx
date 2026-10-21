import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { QRCodeSVG } from "qrcode.react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { fetchPaymentOrder } from "@/services/paymentApi";
import { toast } from "sonner";
import { CheckCircle2, Clock, XCircle } from "lucide-react";

/** 轮询间隔（毫秒）：回调入账后 2s 内界面就能看到「已到账」 */
const POLL_INTERVAL_MS = 2000;
/** 二维码有效期（毫秒）：超 5 分钟仍未支付则提示重新下单并停止轮询 */
const EXPIRE_MS = 5 * 60 * 1000;
/** 支付成功后自动关窗延时（毫秒），让用户看清「已到账」 */
const AUTO_CLOSE_MS = 1500;

type Phase = "scanning" | "paid" | "expired" | "failed";

/**
 * 收款弹窗（老师端充值，微信 Native 扫码 / 支付宝电脑网站收银台通用）。
 *
 * 数据流：下单返回 `pay_params.code_url`（微信二维码）或 `pay_params.pay_url`
 * （支付宝 page.pay 收银台链接）→ 微信渲染二维码、支付宝给「打开收银台」按钮
 * → 每 2s 轮询 `GET /payment/orders/{id}`；回调入账（`status=paid`）后刷新额度并自动关窗。
 * ⛔ 关窗**不取消**订单：晚付仍会通过回调入账（后端本就无取消流，属预期）。
 */
export function PaymentQRDialog({
  orderId,
  codeUrl,
  payUrl,
  amountYuan,
  channel = "wechat_pay",
  open,
  onOpenChange,
}: {
  orderId: string | null;
  codeUrl: string | null;
  payUrl?: string | null;
  amountYuan: number;
  channel?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const isAlipay = channel === "alipay";
  const queryClient = useQueryClient();
  const startedAtRef = useRef<number>(0);
  const [phase, setPhase] = useState<Phase>("scanning");

  // 每次打开（换一个订单）都重置状态与计时
  useEffect(() => {
    if (open && orderId) {
      startedAtRef.current = Date.now();
      setPhase("scanning");
    }
  }, [open, orderId]);

  const { data: order } = useQuery({
    queryKey: ["payment", "order", orderId],
    queryFn: () => fetchPaymentOrder(orderId as string),
    enabled: open && !!orderId && phase === "scanning",
    retry: false,
    refetchInterval: (query) => {
      if (phase !== "scanning") return false;
      if (Date.now() - startedAtRef.current > EXPIRE_MS) return false;
      const status = query.state.data?.status;
      if (status === "paid" || status === "failed" || status === "cancelled" || status === "refunded") {
        return false;
      }
      return POLL_INTERVAL_MS;
    },
  });

  // 状态机：轮询结果 → phase
  useEffect(() => {
    const status = order?.status;
    if (!status) return;
    if (status === "paid") setPhase("paid");
    else if (status === "failed" || status === "cancelled" || status === "refunded") setPhase("failed");
  }, [order?.status]);

  // 超时检测（轮询在 REFUSE 后会停，这里兜底把界面切到「已过期」）
  useEffect(() => {
    if (!open || phase !== "scanning") return;
    const timer = setInterval(() => {
      if (Date.now() - startedAtRef.current > EXPIRE_MS) setPhase("expired");
    }, 1000);
    return () => clearInterval(timer);
  }, [open, phase]);

  // 支付成功：刷新额度/充值记录 → 提示 → 自动关窗
  useEffect(() => {
    if (phase !== "paid") return;
    queryClient.invalidateQueries({ queryKey: ["quota", "me"] });
    queryClient.invalidateQueries({ queryKey: ["quota", "me", "recharge-logs"] });
    queryClient.invalidateQueries({ queryKey: ["payment", "account"] });
    toast.success(`充值成功，¥${amountYuan} 已到账`);
    const timer = setTimeout(() => onOpenChange(false), AUTO_CLOSE_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isAlipay ? "支付宝支付" : "微信扫码支付"} ¥{amountYuan}
          </DialogTitle>
          <DialogDescription>
            {isAlipay
              ? "在新打开的支付宝收银台完成支付，本窗口会自动确认到账"
              : "打开微信「扫一扫」，支付完成后额度自动到账"}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col items-center gap-3 py-2">
          {phase === "paid" && (
            <div className="flex flex-col items-center gap-2 py-6" data-testid="qr-paid">
              <CheckCircle2 className="h-14 w-14 text-emerald-500" strokeWidth={1.75} />
              <p className="text-base font-medium">充值成功，已到账</p>
              <p className="text-sm text-muted-foreground">正在返回额度页…</p>
            </div>
          )}

          {phase === "expired" && (
            <div className="flex flex-col items-center gap-2 py-6" data-testid="qr-expired">
              <Clock className="h-14 w-14 text-muted-foreground" strokeWidth={1.75} />
              <p className="text-base font-medium">二维码已过期</p>
              <p className="text-sm text-muted-foreground">请关闭后重新下单</p>
            </div>
          )}

          {phase === "failed" && (
            <div className="flex flex-col items-center gap-2 py-6" data-testid="qr-failed">
              <XCircle className="h-14 w-14 text-destructive" strokeWidth={1.75} />
              <p className="text-base font-medium">订单未支付成功</p>
              <p className="text-sm text-muted-foreground">可关闭后重新下单</p>
            </div>
          )}

          {phase === "scanning" &&
            (codeUrl ? (
              <>
                <div className="rounded-lg border bg-white p-3">
                  <QRCodeSVG value={codeUrl} size={220} marginSize={0} />
                </div>
                <p className="text-sm text-muted-foreground">支付完成后本窗口会自动更新</p>
              </>
            ) : payUrl ? (
              <div className="flex flex-col items-center gap-3 py-6">
                <Button
                  onClick={() => window.open(payUrl, "_blank", "noopener")}
                  className="bg-emerald-600 hover:bg-emerald-700"
                  data-testid="open-alipay-cashier"
                >
                  打开支付宝收银台
                </Button>
                <p className="text-sm text-muted-foreground">
                  若未自动打开新标签页，请点击上方按钮前往支付
                </p>
                <p className="text-sm text-muted-foreground">
                  支付完成后本窗口会自动更新
                </p>
              </div>
            ) : (
              <Skeleton className="h-[226px] w-[226px]" />
            ))}
        </div>

        {orderId && (
          <p className="break-all text-center text-xs text-muted-foreground/70">
            订单号 {orderId}
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
