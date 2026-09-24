import { useQuery } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { QuotaProgressBar, usedPct } from "./QuotaProgressBar";
import { fetchMyQuota, fetchQuotaTiers } from "@/services/quotaApi";
import {
  Wallet,
  Zap,
  Gauge,
  CalendarDays,
  AlertTriangle,
  ShieldCheck,
} from "lucide-react";

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

export function MyQuotaPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["quota", "me"],
    queryFn: fetchMyQuota,
  });
  const { data: tiers } = useQuery({
    queryKey: ["quota", "tiers"],
    queryFn: fetchQuotaTiers,
  });

  if (isLoading) {
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

  if (error || !data) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="w-4 h-4" />
        <AlertTitle>加载失败</AlertTitle>
        <AlertDescription>
          {error instanceof Error ? error.message : "无法获取额度信息"}
        </AlertDescription>
      </Alert>
    );
  }

  const pct = data.used_pct ?? usedPct(data.used_pages, data.total_pages);

  let statusBadge = <Badge variant="secondary">额度充足</Badge>;
  let statusText = "额度充足";
  if (data.locked || pct >= 105) {
    statusBadge = <Badge variant="destructive">已停用</Badge>;
    statusText = "已超总量 105%，批改功能已停止";
  } else if (pct >= 100) {
    statusBadge = <Badge variant="destructive">已达上限</Badge>;
    statusText = "已用满总量，即将停止";
  } else if (pct >= 90) {
    statusBadge = <Badge className="bg-amber-500 text-white">接近上限</Badge>;
    statusText = "已用超过 90%，请及时充值";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">我的额度</h2>
          <p className="text-sm text-muted-foreground mt-1">
            批改按「面」计费：1 张上传图 / 1 页 = 1 面
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-muted-foreground" />
          {statusBadge}
        </div>
      </div>

      {(data.locked || pct >= 105) && (
        <Alert variant="destructive">
          <AlertTriangle className="w-4 h-4" />
          <AlertTitle>批改额度已用尽</AlertTitle>
          <AlertDescription>
            已用面数超过总量的 105%，系统已自动停止批改功能，请联系管理员充值。
          </AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={Wallet} label="总量" value={String(data.total_pages)} unit="面" />
        <StatCard icon={Zap} label="已用" value={String(data.used_pages)} unit="面" sub={statusText} />
        <StatCard
          icon={Gauge}
          label="剩余"
          value={String(Math.max(0, data.available))}
          unit="面"
          sub={data.available < 0 ? "已超量" : undefined}
        />
        <StatCard icon={CalendarDays} label="今日批改" value={String(data.today_pages)} unit="面" />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>已用 / 总量</CardTitle>
          <CardDescription>已用占总量的 {pct.toFixed(1)}%</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <QuotaProgressBar
            used={data.used_pages}
            total={data.total_pages}
            locked={data.locked}
          />
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>0</span>
            <span>总量 {data.total_pages} 面（105% = {Math.ceil(data.total_pages * 1.05)} 面停）</span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>充值档位</CardTitle>
          <CardDescription>当前为管理员手动加额，如需充值请联系管理员</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>档位（元）</TableHead>
                <TableHead>基准面数</TableHead>
                <TableHead>赠送面数</TableHead>
                <TableHead>到手总面数</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(tiers ?? []).map((t) => (
                <TableRow key={t.amount_yuan}>
                  <TableCell className="font-medium">¥{t.amount_yuan}</TableCell>
                  <TableCell>{t.base_pages}</TableCell>
                  <TableCell className={t.bonus_pages > 0 ? "text-emerald-600" : ""}>
                    {t.bonus_pages > 0 ? `+${t.bonus_pages}` : "0"}
                  </TableCell>
                  <TableCell className="font-semibold">{t.total_pages}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
