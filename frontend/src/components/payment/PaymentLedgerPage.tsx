import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
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
import { ChevronLeft, ChevronRight, Receipt, Inbox, ScanLine, Info } from "lucide-react";
import { fetchMyQuota, fetchMyQuotaRechargeLogs, type MyQuotaRechargeLog } from "@/services/quotaApi";

const PAGE_SIZE = 20;

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
 * 我的流水（面数口径 · 0924 需求）。
 *
 * 数据源 = `grading_quota_recharge_logs`（充值记录）+ `grading_quota`（消费概览）。
 * ⛔ 与同事的「分余额资金流水」无关 —— 本页展示「面」从哪来（充值）、花到哪（消耗）。
 */
export function PaymentLedgerPage() {
  const [page, setPage] = useState(1);

  const { data: quota, isLoading: loadingQuota } = useQuery({
    queryKey: ["quota", "me"],
    queryFn: fetchMyQuota,
  });

  const {
    data: logs,
    isLoading: loadingLogs,
    isError: logsError,
  } = useQuery({
    queryKey: ["quota", "me", "recharge-logs", page],
    queryFn: () => fetchMyQuotaRechargeLogs(page, PAGE_SIZE),
  });

  const total = logs?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const items: MyQuotaRechargeLog[] = logs?.items ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2 rounded-lg border border-primary/20 bg-primary/5 px-4 py-3 text-sm">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
        <div className="text-muted-foreground">
          这里是你的批改额度流水（面数口径）。下方「充值记录」展示额度从哪来，
          「消费概览」展示额度花到哪。侧边栏「扫描消耗 / 用量汇总」是平台成本口径的统计，
          与你的个人额度账单不同。
        </div>
      </div>

      {/* ── 消费概览 ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <ScanLine className="h-4 w-4 text-primary" />
            消费概览
          </CardTitle>
          <CardDescription>批改按「面」计费：1 张上传图 / 1 页 = 1 面</CardDescription>
        </CardHeader>
        <CardContent>
          {loadingQuota ? (
            <Skeleton className="h-16 w-full" />
          ) : (
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="rounded-lg border p-4">
                <p className="text-sm text-muted-foreground">累计已用</p>
                <p className="mt-1 text-2xl font-semibold tabular-nums">
                  {quota?.used_pages ?? 0}
                  <span className="ml-1 text-sm font-normal text-muted-foreground">面</span>
                </p>
              </div>
              <div className="rounded-lg border p-4">
                <p className="text-sm text-muted-foreground">今日批改</p>
                <p className="mt-1 text-2xl font-semibold tabular-nums">
                  {quota?.today_pages ?? 0}
                  <span className="ml-1 text-sm font-normal text-muted-foreground">面</span>
                </p>
              </div>
              <div className="rounded-lg border p-4">
                <p className="text-sm text-muted-foreground">剩余可用</p>
                <p className="mt-1 text-2xl font-semibold tabular-nums">
                  {Math.max(0, quota?.available ?? 0)}
                  <span className="ml-1 text-sm font-normal text-muted-foreground">面</span>
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── 充值记录 ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Receipt className="h-4 w-4 text-primary" />
            充值记录
          </CardTitle>
          <CardDescription>
            共 {total} 笔 · 第 {page} / {pageCount} 页
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loadingLogs ? (
            <Skeleton className="h-40 w-full" />
          ) : logsError ? (
            <EmptyState icon={Inbox} text="充值记录加载失败，请稍后重试" />
          ) : items.length === 0 ? (
            <EmptyState icon={Inbox} text="暂无充值记录" />
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[180px]">时间</TableHead>
                    <TableHead className="w-[110px] text-right">金额（元）</TableHead>
                    <TableHead className="w-[110px] text-right">基准面</TableHead>
                    <TableHead className="w-[110px] text-right">赠送面</TableHead>
                    <TableHead className="w-[110px] text-right">总面数</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell className="text-muted-foreground">
                        {shortTime(row.created_at)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums font-medium">
                        ¥{row.amount_yuan}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">
                        {row.base_pages}
                      </TableCell>
                      <TableCell
                        className={`text-right tabular-nums ${
                          row.bonus_pages > 0 ? "text-emerald-600" : "text-muted-foreground"
                        }`}
                      >
                        {row.bonus_pages > 0 ? `+${row.bonus_pages}` : "0"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums font-semibold">
                        +{row.total_pages}
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
    </div>
  );
}
