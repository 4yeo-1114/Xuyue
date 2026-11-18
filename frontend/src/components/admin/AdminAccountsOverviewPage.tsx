import { useMemo, useState } from "react";
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
import { Input } from "@/components/ui/input";
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
import { QuotaProgressBar, usedPct } from "@/components/quota/QuotaProgressBar";
import {
  fetchAdminAccountsOverview,
  AccountOverviewRow,
} from "@/services/adminOverviewApi";
import {
  Users,
  MousePointerClick,
  HardDrive,
  Search,
  RefreshCw,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  TrendingUp,
  Folder,
  FolderOpen,
} from "lucide-react";

const NUM = (n: number) => n.toLocaleString("zh-CN");

const WINDOW_OPTIONS = [
  { value: "7", label: "近 7 天" },
  { value: "30", label: "近 30 天" },
  { value: "90", label: "近 90 天" },
  { value: "365", label: "近一年" },
];

type SortKey =
  | "operations"
  | "quotaUsed"
  | "storage";

function valueOf(row: AccountOverviewRow, key: SortKey): number {
  switch (key) {
    case "operations":
      return row.usage.total_lifetime;
    case "quotaUsed":
      return row.quota.used_pages;
    case "storage":
      return row.usage.storage_mb;
  }
}

function StatCard({
  icon: Icon,
  label,
  value,
  unit,
  sub,
  accent,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <Card className={accent ? "border-primary/40 bg-primary/5" : undefined}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="space-y-1 min-w-0">
            <p className="text-xs text-muted-foreground">{label}</p>
            <div className="flex items-baseline gap-1">
              <span className="text-xl font-semibold tabular-nums">{value}</span>
              {unit && <span className="text-xs text-muted-foreground">{unit}</span>}
            </div>
            {sub && <p className="text-[11px] text-muted-foreground truncate">{sub}</p>}
          </div>
          <Icon className="w-4 h-4 text-muted-foreground/60 shrink-0" strokeWidth={1.75} />
        </div>
      </CardContent>
    </Card>
  );
}

export function AdminAccountsOverviewPage() {
  const queryClient = useQueryClient();
  const [windowDays, setWindowDays] = useState(30);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [groupFilter, setGroupFilter] = useState("all");
  const [sortKey, setSortKey] = useState<SortKey>("operations");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["admin", "accounts-overview", windowDays],
    queryFn: () => fetchAdminAccountsOverview(windowDays),
  });

  const allRoles = useMemo(() => {
    const set = new Set<string>();
    (data?.items ?? []).forEach((r) => (r.roles ?? []).forEach((x) => set.add(x)));
    return Array.from(set).sort();
  }, [data]);

  /** 文件夹分组：邮箱域名 → 账号数（数量降序）。批量创建的账号共享域名，点进去就是那一批。 */
  const groups = useMemo(() => {
    const map = new Map<string, number>();
    (data?.items ?? []).forEach((r) => {
      const g = r.group || "未分组";
      map.set(g, (map.get(g) ?? 0) + 1);
    });
    return Array.from(map.entries()).sort(
      (a, b) => b[1] - a[1] || a[0].localeCompare(b[0]),
    );
  }, [data]);

  const rows = useMemo(() => {
    let list = [...(data?.items ?? [])];
    if (groupFilter !== "all") {
      list = list.filter((r) => (r.group || "未分组") === groupFilter);
    }
    const q = search.trim().toLowerCase();
    if (q) {
      list = list.filter(
        (r) =>
          (r.display_name ?? "").toLowerCase().includes(q) ||
          (r.email ?? "").toLowerCase().includes(q) ||
          (r.phone ?? "").toLowerCase().includes(q) ||
          (r.teaching_subject ?? "").toLowerCase().includes(q) ||
          (r.teaching_grade ?? "").toLowerCase().includes(q),
      );
    }
    if (roleFilter !== "all") {
      list = list.filter((r) => (r.roles ?? []).includes(roleFilter));
    }
    list.sort((a, b) => {
      const va = valueOf(a, sortKey);
      const vb = valueOf(b, sortKey);
      return sortDir === "desc" ? vb - va : va - vb;
    });
    return list;
  }, [data, groupFilter, search, roleFilter, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-56" />
        <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
        <Skeleton className="h-96" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-muted-foreground">
          加载失败，请确认账号为系统管理员/子系统管理员后重试
          <div className="mt-4">
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              <RefreshCw className="w-4 h-4 mr-2" />重试
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  const s = data.summary;
  const selected = rows.find((r) => r.user_id === selectedId) ?? null;

  return (
    <div className="space-y-5">
      {/* 标题 + 窗口 + 刷新 */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-semibold">账号总览</h2>
          <p className="text-sm text-muted-foreground mt-1">
            操作用量 / 面数额度 / 存储一览 · {data.scope_note}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={String(windowDays)} onValueChange={(v) => setWindowDays(Number(v))}>
            <SelectTrigger className="w-[120px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {WINDOW_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="sm"
            onClick={() => queryClient.invalidateQueries({ queryKey: ["admin", "accounts-overview"] })}
          >
            <RefreshCw className="w-4 h-4 mr-2" />刷新
          </Button>
        </div>
      </div>

      {/* 汇总卡片 */}
      <div className="grid grid-cols-2 gap-3">
        <StatCard icon={Users} label="账号总数" value={NUM(data.total_accounts)} unit="个" accent />
        <StatCard
          icon={MousePointerClick}
          label="9月起累计操作(上传+批改)"
          value={NUM(s.total_operations_lifetime)}
          unit="次"
          sub={`上传 ${NUM(s.total_upload_lifetime)} / 批改 ${NUM(s.total_grade_lifetime)}`}
        />
      </div>

      {/* 文件夹分组（邮箱域名）：点文件夹只看该批账号 */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-muted-foreground flex items-center gap-1 shrink-0">
          <Folder className="w-3.5 h-3.5" />
          文件夹
        </span>
        <button
          type="button"
          onClick={() => setGroupFilter("all")}
          className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs transition-colors ${
            groupFilter === "all"
              ? "border-primary/50 bg-primary/10 text-primary font-medium"
              : "bg-card hover:bg-muted/60 text-muted-foreground"
          }`}
        >
          {groupFilter === "all" ? (
            <FolderOpen className="w-3.5 h-3.5" />
          ) : (
            <Folder className="w-3.5 h-3.5" />
          )}
          全部账号
          <span className="tabular-nums">({data.total_accounts})</span>
        </button>
        {groups.map(([g, count]) => (
          <button
            key={g}
            type="button"
            onClick={() => setGroupFilter(groupFilter === g ? "all" : g)}
            title={`只看邮箱域名为 ${g} 的账号`}
            className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs transition-colors ${
              groupFilter === g
                ? "border-primary/50 bg-primary/10 text-primary font-medium"
                : "bg-card hover:bg-muted/60 text-muted-foreground"
            }`}
          >
            {groupFilter === g ? (
              <FolderOpen className="w-3.5 h-3.5" />
            ) : (
              <Folder className="w-3.5 h-3.5" />
            )}
            {g}
            <span className="tabular-nums">({count})</span>
          </button>
        ))}
        {groups.length <= 1 && (
          <span className="text-[11px] text-muted-foreground/70">
            同一批批量创建的账号（同邮箱域名）会归到一个文件夹
          </span>
        )}
      </div>

      {/* 筛选 */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[220px] max-w-sm">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索姓名 / 邮箱 / 手机 / 科目 / 年级"
            className="pl-8"
          />
        </div>
        <Select value={roleFilter} onValueChange={setRoleFilter}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="全部角色" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部角色</SelectItem>
            {allRoles.map((r) => (
              <SelectItem key={r} value={r}>
                {r}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-xs text-muted-foreground">共 {rows.length} 个账号</span>
      </div>

      {/* 明细表 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-primary" />
            账号明细
          </CardTitle>
          <CardDescription>点击列头排序，点击行查看该账号完整明细</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="min-w-[200px]">账号 / 角色</TableHead>
                <TableHead>任教</TableHead>
                <SortableHead
                  label="操作用量"
                  sub="9月起(上传/批改)"
                  active={sortKey === "operations"}
                  dir={sortDir}
                  onClick={() => toggleSort("operations")}
                />
                <SortableHead
                  label="面数额度"
                  sub="已用/总量"
                  active={sortKey === "quotaUsed"}
                  dir={sortDir}
                  onClick={() => toggleSort("quotaUsed")}
                />
                <SortableHead
                  label="存储"
                  sub="MB"
                  active={sortKey === "storage"}
                  dir={sortDir}
                  onClick={() => toggleSort("storage")}
                />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground py-10">
                    暂无账号
                  </TableCell>
                </TableRow>
              ) : (
                rows.map((r) => {
                  const pct = usedPct(r.quota.used_pages, r.quota.total_pages);
                  const active = r.user_id === selectedId;
                  return (
                    <TableRow
                      key={r.user_id}
                      className={`cursor-pointer ${active ? "bg-primary/5" : ""}`}
                      onClick={() => setSelectedId(active ? null : r.user_id)}
                    >
                      <TableCell>
                        <div className="font-medium">{r.display_name || "未命名"}</div>
                        <div className="text-xs text-muted-foreground">{r.email}</div>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {(r.roles ?? []).map((role) => (
                            <Badge key={role} variant="secondary" className="text-[10px]">
                              {role}
                            </Badge>
                          ))}
                        </div>
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                        {r.teaching_grade ?? "—"} {r.teaching_subject ?? ""}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        <div className="font-medium">{NUM(r.usage.total_lifetime)}</div>
                        <div className="text-xs text-muted-foreground">
                          {NUM(r.usage.upload_lifetime)} / {NUM(r.usage.grade_lifetime)}
                        </div>
                        <div className="text-[11px] text-muted-foreground/70">
                          {data.window_days}天 {NUM(r.usage.total_recent)} · 今日 {NUM(r.usage.total_today)}
                        </div>
                      </TableCell>
                      <TableCell className="min-w-[140px]">
                        <QuotaProgressBar
                          used={r.quota.used_pages}
                          total={r.quota.total_pages}
                          locked={r.quota.locked}
                        />
                        <div className="text-xs text-muted-foreground mt-1">
                          {NUM(r.quota.used_pages)} / {NUM(r.quota.total_pages)}（{pct}%）
                        </div>
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-xs text-muted-foreground">
                        {NUM(r.usage.storage_mb)} MB
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* 选中账号详情 */}
      {selected && <AccountDetailCard row={selected} windowDays={data.window_days} />}
    </div>
  );
}

function SortableHead({
  label,
  sub,
  active,
  dir,
  onClick,
}: {
  label: string;
  sub?: string;
  active: boolean;
  dir: "asc" | "desc";
  onClick: () => void;
}) {
  return (
    <TableHead
      className={`text-right cursor-pointer select-none whitespace-nowrap ${active ? "text-primary" : ""}`}
      onClick={onClick}
    >
      <div className="inline-flex flex-col items-end">
        <span className="inline-flex items-center gap-1">
          {label}
          {active ? (
            dir === "desc" ? (
              <ArrowDown className="w-3 h-3" />
            ) : (
              <ArrowUp className="w-3 h-3" />
            )
          ) : (
            <ArrowUpDown className="w-3 h-3 opacity-40" />
          )}
        </span>
        {sub && <span className="text-[10px] text-muted-foreground font-normal">{sub}</span>}
      </div>
    </TableHead>
  );
}

function DetailItem({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-md border bg-muted/30 px-3 py-2">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className="text-sm font-medium tabular-nums">{value}</p>
      {sub && <p className="text-[11px] text-muted-foreground">{sub}</p>}
    </div>
  );
}

function AccountDetailCard({ row, windowDays }: { row: AccountOverviewRow; windowDays: number }) {
  return (
    <Card className="border-primary/30">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <HardDrive className="h-4 w-4 text-primary" />
          {row.display_name || "未命名"} · 明细
        </CardTitle>
        <CardDescription>
          {row.email}
          {row.phone ? ` · ${row.phone}` : ""}
          {(row.roles ?? []).length ? ` · ${row.roles.join("、")}` : ""}
          {row.created_at ? ` · 注册于 ${new Date(row.created_at).toLocaleString("zh-CN")}` : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2">操作用量（口径 A · grading_daily_stats）</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <DetailItem label="9月起上传" value={NUM(row.usage.upload_lifetime)} />
            <DetailItem label="9月起批改" value={NUM(row.usage.grade_lifetime)} />
            <DetailItem
              label={`近 ${windowDays} 天操作`}
              value={NUM(row.usage.total_recent)}
              sub={`上传 ${NUM(row.usage.upload_recent)} / 批改 ${NUM(row.usage.grade_recent)}`}
            />
            <DetailItem
              label="今日操作"
              value={NUM(row.usage.total_today)}
              sub={`上传 ${NUM(row.usage.upload_today)} / 批改 ${NUM(row.usage.grade_today)}`}
            />
          </div>
        </div>

        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2">面数额度（面数口径）</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <DetailItem label="总量" value={NUM(row.quota.total_pages)} />
            <DetailItem label="已用" value={NUM(row.quota.used_pages)} />
            <DetailItem
              label="剩余"
              value={NUM(Math.max(0, row.quota.available))}
              sub={row.quota.available < 0 ? "已超量" : undefined}
            />
            <DetailItem
              label="状态"
              value={row.quota.locked ? "已停用(105%)" : `${row.quota.used_pct}%`}
            />
          </div>
        </div>

        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2">存储</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <DetailItem label="存储占用" value={`${NUM(row.usage.storage_mb)} MB`} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
