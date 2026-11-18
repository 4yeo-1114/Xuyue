import { useQuery, useQueryClient } from "@tanstack/react-query";
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { QuotaProgressBar, usedPct } from "./QuotaProgressBar";
import { fetchQuotaList } from "@/services/quotaApi";
import { RefreshCw } from "lucide-react";

export function AdminQuotaPage() {
  const queryClient = useQueryClient();

  const { data: accounts, isLoading } = useQuery({
    queryKey: ["quota", "list"],
    queryFn: fetchQuotaList,
  });

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
          <h2 className="text-xl font-semibold">批改额度</h2>
          <p className="text-sm text-muted-foreground mt-1">
            已用超过总量 105% 的账号会自动停用批改
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
    </div>
  );
}
