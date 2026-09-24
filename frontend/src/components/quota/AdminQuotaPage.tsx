import { useState } from "react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { QuotaProgressBar, usedPct } from "./QuotaProgressBar";
import {
  fetchQuotaList,
  fetchQuotaTiers,
  rechargeQuota,
  fetchQuotaRechargeLogs,
} from "@/services/quotaApi";
import { toast } from "sonner";
import { Coins, RefreshCw } from "lucide-react";

export function AdminQuotaPage() {
  const queryClient = useQueryClient();
  const [selectedUserId, setSelectedUserId] = useState<string>("");
  const [selectedTier, setSelectedTier] = useState<string>("");

  const { data: accounts, isLoading } = useQuery({
    queryKey: ["quota", "list"],
    queryFn: fetchQuotaList,
  });
  const { data: tiers } = useQuery({
    queryKey: ["quota", "tiers"],
    queryFn: fetchQuotaTiers,
  });
  const { data: rechargeLogs } = useQuery({
    queryKey: ["quota", "recharge-logs"],
    queryFn: () => fetchQuotaRechargeLogs(1, 50),
  });

  const recharge = useMutation({
    mutationFn: ({ userId, amount }: { userId: string; amount: number }) =>
      rechargeQuota(userId, amount),
    onSuccess: (res) => {
      toast.success(`充值成功，到账 ${res.total_pages} 面（含赠送 ${res.bonus_pages} 面）`);
      queryClient.invalidateQueries({ queryKey: ["quota", "list"] });
      queryClient.invalidateQueries({ queryKey: ["quota", "recharge-logs"] });
    },
    onError: (e) => {
      toast.error(e instanceof Error ? e.message : "充值失败");
    },
  });

  const currentTier = tiers?.find((t) => String(t.amount_yuan) === selectedTier);

  const handleRecharge = () => {
    if (!selectedUserId) {
      toast.error("请先选择要充值的账号");
      return;
    }
    if (!currentTier) {
      toast.error("请选择充值档位");
      return;
    }
    recharge.mutate({ userId: selectedUserId, amount: currentTier.amount_yuan });
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-40" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  const rows = accounts ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">额度与充值</h2>
          <p className="text-sm text-muted-foreground mt-1">
            管理员手动为账号充值批改额度；已用超过总量 105% 的账号会自动停用批改
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => queryClient.invalidateQueries({ queryKey: ["quota", "list"] })}
        >
          <RefreshCw className="w-4 h-4 mr-2" />
          刷新
        </Button>
      </div>

      {/* 充值入口 */}
      <Card className="card-elevated">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Coins className="w-5 h-5" />
            手动充值
          </CardTitle>
          <CardDescription>选择账号与档位，到账面数 = 基准 + 赠送</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Select value={selectedUserId} onValueChange={setSelectedUserId}>
              <SelectTrigger>
                <SelectValue placeholder="选择要充值的账号" />
              </SelectTrigger>
              <SelectContent>
                {rows.map((r) => (
                  <SelectItem key={r.user_id} value={r.user_id}>
                    {r.display_name || r.email || r.user_id}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={selectedTier} onValueChange={setSelectedTier}>
              <SelectTrigger>
                <SelectValue placeholder="选择充值档位" />
              </SelectTrigger>
              <SelectContent>
                {(tiers ?? []).map((t) => (
                  <SelectItem key={t.amount_yuan} value={String(t.amount_yuan)}>
                    ¥{t.amount_yuan} → {t.total_pages} 面（送 {t.bonus_pages}）
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {currentTier && (
            <p className="text-sm text-muted-foreground">
              本次到账：基准 {currentTier.base_pages} 面 + 赠送 {currentTier.bonus_pages} 面 ={" "}
              <span className="font-semibold text-foreground">{currentTier.total_pages} 面</span>
            </p>
          )}

          <Button onClick={handleRecharge} disabled={recharge.isPending}>
            {recharge.isPending ? "充值中…" : "确认充值"}
          </Button>
        </CardContent>
      </Card>

      {/* 账号额度总览 */}
      <Card>
        <CardHeader>
          <CardTitle>账号额度总览</CardTitle>
          <CardDescription>共 {rows.length} 个账号；已用超过总量 105% 即停用</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>账号</TableHead>
                <TableHead>角色</TableHead>
                <TableHead className="w-40">额度进度（已用 / 总量）</TableHead>
                <TableHead className="text-right">今日批改</TableHead>
                <TableHead className="text-right">状态</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                    暂无账号
                  </TableCell>
                </TableRow>
              ) : (
                rows.map((r) => {
                  const pct = usedPct(r.used_pages, r.total_pages);
                  return (
                    <TableRow key={r.user_id}>
                      <TableCell>
                        <div className="font-medium">{r.display_name || "未命名"}</div>
                        <div className="text-xs text-muted-foreground">{r.email}</div>
                      </TableCell>
                      <TableCell>
                        {(r.roles ?? []).join("、") || "—"}
                      </TableCell>
                      <TableCell>
                        <QuotaProgressBar used={r.used_pages} total={r.total_pages} locked={r.locked} />
                        <div className="text-xs text-muted-foreground mt-1">
                          {r.used_pages} / {r.total_pages} 面（{pct}%）
                        </div>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{r.today_pages}</TableCell>
                      <TableCell className="text-right">
                        {r.locked || pct >= 105 ? (
                          <Badge variant="destructive">已停用</Badge>
                        ) : pct >= 90 ? (
                          <Badge className="bg-amber-500 text-white">接近上限</Badge>
                        ) : (
                          <Badge variant="secondary">正常</Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* 充值流水 */}
      <Card>
        <CardHeader>
          <CardTitle>充值记录</CardTitle>
          <CardDescription>
            全平台充值流水，共 {rechargeLogs?.total ?? 0} 条（最近 50 条）
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>时间</TableHead>
                <TableHead>目标账号</TableHead>
                <TableHead className="text-right">金额</TableHead>
                <TableHead className="text-right">到账面数</TableHead>
                <TableHead>操作人</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(rechargeLogs?.items ?? []).length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                    暂无充值记录
                  </TableCell>
                </TableRow>
              ) : (
                (rechargeLogs?.items ?? []).map((log) => (
                  <TableRow key={log.id}>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {log.created_at ? new Date(log.created_at).toLocaleString("zh-CN") : "—"}
                    </TableCell>
                    <TableCell>
                      <div className="font-medium">{log.user_name || log.user_id}</div>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      ¥{log.amount_yuan}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      +{log.total_pages} 面
                      {log.bonus_pages > 0 && (
                        <span className="text-xs text-muted-foreground">
                          （含送 {log.bonus_pages}）
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {log.operator_name || "—"}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
