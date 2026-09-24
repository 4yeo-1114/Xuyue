import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ChevronLeft, ChevronRight, Receipt, Inbox, Info } from "lucide-react";
import {
  fetchPaymentLedger,
  fetchPaymentUsage,
  type LedgerEntry,
} from "@/services/paymentApi";
import { fenToYuan } from "./PaymentWalletPage";

const PAGE_SIZE = 20;

/** 分录类型中文标签（后端取值沿用本仓习惯；未知类型原样透出，⛔ 不猜） */
const ENTRY_TYPE_LABEL: Record<string, string> = {
  grant: "入账",
  consume: "消耗",
  refund: "退款",
  adjust: "调整",
};

/** 用量事件类型中文标签 */
const KIND_LABEL: Record<string, string> = {
  grade: "批改",
  upload: "上传",
};

function entryTypeLabel(t: string): string {
  return ENTRY_TYPE_LABEL[t] ?? t;
}

function kindLabel(k: string): string {
  return KIND_LABEL[k] ?? k;
}

/** 金额展示：正数前置 +，负数带 -（单位：元） */
function signedYuan(fen: number): string {
  const v = Number(fen || 0);
  return `${v > 0 ? "+" : ""}${fenToYuan(v)}`;
}

/** 时间展示：仅取到分钟，避免秒级噪声（后端 ISO 串） */
function shortTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** 空态（本仓习惯：图标 + 一句说明） */
function EmptyState({
  icon: Icon,
  text,
}: {
  icon: React.ElementType;
  text: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
      <Icon className="mb-3 h-8 w-8 opacity-50" />
      <p className="text-sm">{text}</p>
    </div>
  );
}

/**
 * 我的资金流水（口径 B · 个人账本，只读）。
 *
 * ⚠️ 数据源 = `ledger_entries`，与口径 A（扫描消耗 / 用量汇总）**不是同一本账**（设计稿 §1）。
 * ⛔ 只读：无充值、无购买、无退款申请入口（Phase 1/2 待通道拍定）。
 */
export function PaymentLedgerPage() {
  const [page, setPage] = useState(1);

  const {
    data: ledger,
    isLoading: loadingLedger,
    isError: ledgerError,
  } = useQuery({
    queryKey: ["payment", "ledger", page],
    queryFn: () => fetchPaymentLedger({ page, page_size: PAGE_SIZE }),
  });

  const { data: usage, isLoading: loadingUsage } = useQuery({
    queryKey: ["payment", "usage", "ledger-detail"],
    queryFn: () => fetchPaymentUsage({ limit: 50 }),
  });

  const total = ledger?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const items: LedgerEntry[] = ledger?.items ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2 rounded-lg border border-primary/20 bg-primary/5 px-4 py-3 text-sm">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
        <div className="text-muted-foreground">
          这里是你的资金流水与用量明细（口径 B · 个人账本）。 侧边栏「扫描消耗 /
          用量汇总」是平台成本口径的统计，不是你的账单。
        </div>
      </div>

      {/* ── 资金流水 ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Receipt className="h-4 w-4 text-primary" />
            资金流水
          </CardTitle>
          <CardDescription>
            共 {total} 笔 · 第 {page} / {pageCount} 页
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loadingLedger ? (
            <Skeleton className="h-40 w-full" />
          ) : ledgerError ? (
            <EmptyState icon={Inbox} text="流水加载失败，请稍后重试" />
          ) : items.length === 0 ? (
            <EmptyState icon={Inbox} text="暂无流水记录" />
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[160px]">时间</TableHead>
                    <TableHead className="w-[100px]">类型</TableHead>
                    <TableHead className="w-[120px] text-right">
                      金额（元）
                    </TableHead>
                    <TableHead className="w-[120px] text-right">
                      记账后余额（元）
                    </TableHead>
                    <TableHead>说明</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell className="text-muted-foreground">
                        {shortTime(row.created_at)}
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary">
                          {entryTypeLabel(row.entry_type)}
                        </Badge>
                      </TableCell>
                      <TableCell
                        className={`text-right tabular-nums ${
                          row.amount_fen >= 0
                            ? "text-emerald-600"
                            : "text-amber-600"
                        }`}
                      >
                        {signedYuan(row.amount_fen)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">
                        {fenToYuan(row.balance_after_fen)}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {row.description || "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {pageCount > 1 ? (
                <div className="mt-4 flex items-center justify-end gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    <ChevronLeft className="mr-1 h-4 w-4" />
                    上一页
                  </Button>
                  <span className="text-sm text-muted-foreground tabular-nums">
                    {page} / {pageCount}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page >= pageCount}
                    onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
                  >
                    下一页
                    <ChevronRight className="ml-1 h-4 w-4" />
                  </Button>
                </div>
              ) : null}
            </>
          )}
        </CardContent>
      </Card>

      {/* ── 用量明细（口径 B 净额） ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">用量明细</CardTitle>
          <CardDescription>
            按文件夹汇总的净用量（批改 / 上传计数，含删除冲正）
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loadingUsage ? (
            <Skeleton className="h-40 w-full" />
          ) : (usage?.folders?.length ?? 0) === 0 ? (
            <EmptyState icon={Inbox} text="暂无用量记录" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[120px]">类型</TableHead>
                  <TableHead>文件夹</TableHead>
                  <TableHead className="w-[120px] text-right">净用量</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {usage?.folders?.map((row) => (
                  <TableRow key={`${row.kind}-${row.folder_safe}`}>
                    <TableCell>
                      <Badge variant="secondary">{kindLabel(row.kind)}</Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {row.folder_safe || "—"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {row.net}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
