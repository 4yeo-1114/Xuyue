import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  fetchEstimate,
  fetchBill,
  fetchPricing,
  type BillingItem,
  type BillingResult,
  type PricingItem,
} from "@/services/scanBillingApi";
import {
  Wallet,
  HardDrive,
  ScanLine,
  Inbox,
  Info,
  ChevronDown,
  ChevronRight,
  Coins,
  Percent,
  CalendarClock,
} from "lucide-react";

/* ── 金额格式化 ── */
function money(v: number, currency = "CNY"): string {
  const sym = currency === "CNY" ? "¥" : "";
  return `${sym}${v.toFixed(4)}`;
}

/* ── 指标卡 ── */
function StatCard({
  icon: Icon,
  label,
  value,
  unit,
  sub,
  color,
  highlight,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  color?: string;
  highlight?: boolean;
}) {
  return (
    <Card className={highlight ? "card-elevated border-primary/30" : "card-elevated"}>
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div className="space-y-1 min-w-0">
            <p className="text-sm text-muted-foreground">{label}</p>
            <div className="flex items-baseline gap-1">
              <span className="text-2xl font-semibold tabular-nums">
                {value}
              </span>
              {unit && (
                <span className="text-sm text-muted-foreground">{unit}</span>
              )}
            </div>
            {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
          </div>
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
            style={{
              backgroundColor: color
                ? `${color}15`
                : "hsl(var(--primary) / 0.1)",
            }}
          >
            <Icon
              className="w-5 h-5"
              style={{ color: color || "hsl(var(--primary))" }}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/* ── 计费明细表（预估 / 账单共用） ── */
function BillingTable({ result }: { result: BillingResult }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border/50">
            <th className="w-8" />
            <th className="text-left py-2 px-2 font-medium text-muted-foreground">
              计费项
            </th>
            <th className="text-left py-2 px-2 font-medium text-muted-foreground">
              类别
            </th>
            <th className="text-right py-2 px-2 font-medium text-muted-foreground">
              用量
            </th>
            <th className="text-right py-2 px-2 font-medium text-muted-foreground">
              免费额度
            </th>
            <th className="text-right py-2 px-2 font-medium text-muted-foreground">
              应计费量
            </th>
            <th className="text-right py-2 px-2 font-medium text-muted-foreground">
              金额
            </th>
          </tr>
        </thead>
        <tbody>
          {result.items.map((it) => (
            <BillingRow
              key={it.key}
              item={it}
              currency={result.currency}
              expanded={expanded === it.key}
              onToggle={() =>
                setExpanded((e) => (e === it.key ? null : it.key))
              }
            />
          ))}
          <tr className="border-t-2 border-border/60">
            <td />
            <td className="py-3 px-2 font-semibold">合计</td>
            <td colSpan={4} />
            <td className="py-3 px-2 text-right font-semibold tabular-nums text-primary">
              {money(result.total_amount, result.currency)}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function BillingRow({
  item,
  currency,
  expanded,
  onToggle,
}: {
  item: BillingItem;
  currency: string;
  expanded: boolean;
  onToggle: () => void;
}) {
  const hasSegments = item.segments.length > 0;
  return (
    <>
      <tr
        className="border-b border-border/20 hover:bg-muted/30 transition-colors cursor-pointer"
        onClick={onToggle}
      >
        <td className="py-2.5 pl-2">
          {hasSegments ? (
            expanded ? (
              <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
            )
          ) : null}
        </td>
        <td className="py-2.5 px-2">
          <span className="font-medium">{item.label}</span>
        </td>
        <td className="py-2.5 px-2">
          <Badge variant="secondary" className="text-[11px] font-normal">
            {item.category}
          </Badge>
        </td>
        <td className="text-right py-2.5 px-2 tabular-nums">
          {item.raw_quantity.toLocaleString()}
          {item.basis === "monthly_avg" && (
            <span className="text-xs text-muted-foreground ml-1">GB·日均</span>
          )}
        </td>
        <td className="text-right py-2.5 px-2 tabular-nums text-muted-foreground">
          {item.free_quota > 0 ? item.free_quota.toLocaleString() : "—"}
        </td>
        <td className="text-right py-2.5 px-2 tabular-nums">
          {item.billable_units.toLocaleString()}
          <span className="text-xs text-muted-foreground ml-1">
            {item.unit}
          </span>
        </td>
        <td className="text-right py-2.5 px-2 tabular-nums font-medium">
          {money(item.amount, currency)}
          {item.proration !== undefined && item.proration < 1 && (
            <span className="text-[11px] text-muted-foreground ml-1">
              ×{item.proration.toFixed(2)}
            </span>
          )}
        </td>
      </tr>
      {expanded && hasSegments && (
        <tr className="bg-muted/20">
          <td />
          <td colSpan={6} className="py-2 px-2">
            <div className="text-xs text-muted-foreground space-y-1">
              <p className="font-medium text-foreground/80">阶梯分段（累进）</p>
              {item.segments.map((s, i) => (
                <p key={i} className="tabular-nums">
                  {s.from.toLocaleString()} ~{" "}
                  {s.to === null ? "不限" : s.to.toLocaleString()} {item.unit}：
                  {s.quantity.toLocaleString()} × {s.price} ={" "}
                  {money(s.amount, currency)}
                </p>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

/* ── 抵扣顺序说明条 ── */
function DeductionOrderBar({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground bg-muted/40 rounded-lg px-3 py-2">
      <Info className="w-3.5 h-3.5 shrink-0" />
      <span>
        抵扣顺序：<span className="text-foreground/80">{label}</span>
      </span>
    </div>
  );
}

/* ── 价格表 ── */
function PricingTable({ items, currency }: { items: PricingItem[]; currency: string }) {
  const sym = currency === "CNY" ? "¥" : "";
  return (
    <div className="space-y-4">
      {items.map((it) => (
        <div key={it.key} className="border border-border/50 rounded-lg p-3">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span className="text-sm font-medium">{it.label}</span>
            <Badge variant="secondary" className="text-[11px] font-normal">
              {it.category}
            </Badge>
            <span className="text-xs text-muted-foreground">
              单位：{it.unit} · {it.basis_label} · {it.round_up_label}
            </span>
            {it.free_quota > 0 && (
              <Badge
                variant="outline"
                className="text-[11px] font-normal text-emerald-600 border-emerald-600/30"
              >
                免费额度 {it.free_quota.toLocaleString()} {it.unit}
              </Badge>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {it.tiers.map((t, i) => (
              <span
                key={i}
                className="text-xs tabular-nums bg-muted/50 rounded px-2 py-1"
              >
                {t.up_to === null
                  ? "以上"
                  : `0 ~ ${t.up_to.toLocaleString()}`}
                ：{sym}
                {t.price}/{it.unit}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ── 主组件 ── */
export function UsageSummaryPage() {
  const [billMonth, setBillMonth] = useState<string>("");

  const { data: pricing } = useQuery({
    queryKey: ["scan-billing", "pricing"],
    queryFn: fetchPricing,
    staleTime: 10 * 60 * 1000,
  });

  const { data: estimate, isLoading: loadingEst } = useQuery({
    queryKey: ["scan-billing", "estimate"],
    queryFn: () => fetchEstimate(),
  });

  const { data: bill, isLoading: loadingBill } = useQuery({
    queryKey: ["scan-billing", "bill", billMonth],
    queryFn: () => fetchBill(billMonth ? { month: billMonth } : undefined),
  });

  if (loadingEst) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-[110px] w-full" />
        <Skeleton className="h-[300px] w-full" />
      </div>
    );
  }

  // 可选月份：近 12 个月
  const monthOptions: string[] = [];
  const now = new Date();
  for (let i = 0; i < 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    monthOptions.push(
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`,
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* 标题 */}
      <div>
        <h2 className="text-lg font-semibold text-foreground">用量汇总</h2>
        <p className="text-sm text-muted-foreground mt-1">
          按量计费预估与月度账单 · 计费模型对齐七牛云对象存储口径
        </p>
      </div>

      {/* 汇总指标 */}
      {estimate && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            icon={Wallet}
            label="本月预估费用"
            value={money(estimate.total_amount, estimate.currency)}
            sub={estimate.period_label}
            color="#8b5cf6"
            highlight
          />
          <StatCard
            icon={Coins}
            label="AI 批改处理"
            value={estimate.usage.grade.toLocaleString()}
            unit="次"
            sub="本月累计"
            color="#10b981"
          />
          <StatCard
            icon={ScanLine}
            label="上传请求"
            value={estimate.usage.upload.toLocaleString()}
            unit="次"
            sub="本月累计"
            color="#3b82f6"
          />
          <StatCard
            icon={HardDrive}
            label="存储日均"
            value={estimate.storage.avg_gb.toFixed(4)}
            unit="GB"
            sub={`${estimate.storage.elapsed_days}/${estimate.storage.days_in_month} 天`}
            color="#f59e0b"
          />
        </div>
      )}

      {/* 按量计费预估 */}
      {estimate && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <CardTitle className="text-sm font-semibold">
                  按量计费预估
                </CardTitle>
                <CardDescription>
                  {estimate.period_label} · 未出账，仅供参考，非最终账单
                </CardDescription>
              </div>
              <DeductionOrderBar label="免费额度 → 资源包 → 阶梯价格" />
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <BillingTable result={estimate} />
            <p className="text-xs text-muted-foreground flex items-start gap-1.5">
              <Percent className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              {estimate.note}
            </p>
          </CardContent>
        </Card>
      )}

      {/* 月度账单 */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle className="text-sm font-semibold">月度账单</CardTitle>
              <CardDescription>
                {bill?.settle_note || "按量付费，当月使用次月结算"}
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <CalendarClock className="w-4 h-4 text-muted-foreground" />
              <Select
                value={billMonth || (bill?.month ?? "")}
                onValueChange={setBillMonth}
              >
                <SelectTrigger className="h-8 w-[130px] text-xs">
                  <SelectValue placeholder="选择月份" />
                </SelectTrigger>
                <SelectContent>
                  {monthOptions.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loadingBill ? (
            <Skeleton className="h-[200px] w-full" />
          ) : bill ? (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-3">
                <Badge
                  variant={bill.settled ? "default" : "secondary"}
                  className="text-[11px]"
                >
                  {bill.settled ? "已结算" : "预估中"}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  账单月份 {bill.month} · 存储日均{" "}
                  {bill.storage.avg_gb.toFixed(4)} GB
                </span>
              </div>
              <BillingTable result={bill} />
            </div>
          ) : (
            <div className="flex h-[180px] flex-col items-center justify-center text-sm text-muted-foreground">
              <Inbox className="mb-2 h-6 w-6" />
              暂无账单数据
            </div>
          )}
        </CardContent>
      </Card>

      {/* 计费规则与价格表 */}
      {pricing && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <CardTitle className="text-sm font-semibold">
                  计费规则与价格表
                </CardTitle>
                <CardDescription>{pricing.note}</CardDescription>
              </div>
              <DeductionOrderBar label={pricing.deduction_order_label} />
            </div>
          </CardHeader>
          <CardContent>
            <PricingTable items={pricing.items} currency={pricing.currency} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
