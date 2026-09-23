import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Gift,
  Plus,
  Loader2,
  Pencil,
  ShoppingBag,
  ArrowDown,
  ArrowUp,
  PackageCheck,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Package,
  BarChart3,
  PackageSearch,
  TrendingUp,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  listRewardProducts,
  createRewardProduct,
  updateRewardProduct,
  createRedemption,
  listRedemptions,
  updateRedemptionStatus,
  stockStats,
  redemptionReport,
  type RewardProduct,
  type RewardProductInput,
  type Redemption,
  type StockStats,
  type RedemptionReport,
  type ReportTrendPoint,
} from "@/services/studentOpsApi";
import { ClassSelector } from "@/components/student-ops/shared/ClassSelector";
import { StudentPicker } from "@/components/student-ops/shared/StudentPicker";
import { StatusBadge } from "@/components/student-ops/shared/StatusBadge";
import { Pagination } from "@/components/student-ops/shared/Pagination";
import { EmptyState } from "@/components/student-ops/shared/EmptyState";

interface RewardSectionProps {
  classId: string;
  onClassChange: (id: string) => void;
}

export function RewardSection({ classId, onClassChange }: RewardSectionProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState("products");

  const [productType, setProductType] = useState("");
  const [keyword, setKeyword] = useState("");
  const [productPage, setProductPage] = useState(1);

  const [redemptionStatus, setRedemptionStatus] = useState("");
  const [redemptionPage, setRedemptionPage] = useState(1);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<RewardProduct | null>(null);
  const [redeemOpen, setRedeemOpen] = useState(false);
  const [redeemProduct, setRedeemProduct] = useState<RewardProduct | null>(
    null,
  );

  // 业务确认弹窗（替代原生 window.confirm，保持全站 AlertDialog 一致）
  const [confirmToggle, setConfirmToggle] = useState<{
    product: RewardProduct;
    next: boolean;
  } | null>(null);
  const [confirmStatus, setConfirmStatus] = useState<{
    id: string;
    status: "approved" | "delivered" | "cancelled";
  } | null>(null);

  const productsQuery = useQuery({
    queryKey: ["so-reward-products", productType, keyword, productPage],
    queryFn: () =>
      listRewardProducts({
        productType: productType || undefined,
        keyword: keyword || undefined,
        page: productPage,
        pageSize: 20,
      }),
  });

  const redemptionsQuery = useQuery({
    queryKey: ["so-redemptions", classId, redemptionStatus, redemptionPage],
    queryFn: () =>
      listRedemptions({
        classId: classId || undefined,
        status: redemptionStatus || undefined,
        page: redemptionPage,
        pageSize: 20,
      }),
    enabled: tab === "redemptions",
  });

  const invalidateProducts = () =>
    queryClient.invalidateQueries({ queryKey: ["so-reward-products"] });
  const invalidateRedemptions = () =>
    queryClient.invalidateQueries({ queryKey: ["so-redemptions"] });

  const statusMutation = useMutation({
    mutationFn: ({
      id,
      status,
    }: {
      id: string;
      status: "approved" | "delivered" | "cancelled";
    }) => updateRedemptionStatus(id, { status }),
    onSuccess: () => {
      toast.success(t("studentOps.success"));
      invalidateRedemptions();
      queryClient.invalidateQueries({ queryKey: ["so-credit-accounts"] });
      queryClient.invalidateQueries({ queryKey: ["so-credit-txns"] });
      invalidateProducts();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const openCreate = () => {
    setEditing(null);
    setFormOpen(true);
  };
  const openEdit = (p: RewardProduct) => {
    setEditing(p);
    setFormOpen(true);
  };
  const openRedeem = (p: RewardProduct) => {
    if (!classId) {
      toast.error(t("studentOps.rewards.requireClass"));
      return;
    }
    setRedeemProduct(p);
    setRedeemOpen(true);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
            <Gift className="h-4 w-4 text-primary" />
          </div>
          <ClassSelector value={classId} onChange={onClassChange} />
        </div>
        <Button size="sm" onClick={openCreate}>
          <Plus className="h-4 w-4 mr-1" /> {t("studentOps.rewards.create")}
        </Button>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex-wrap h-auto">
          <TabsTrigger value="products">
            {t("studentOps.rewards.products")}
          </TabsTrigger>
          <TabsTrigger value="redemptions">
            {t("studentOps.rewards.records")}
          </TabsTrigger>
          <TabsTrigger value="inventory">
            {t("studentOps.rewards.inventoryReport")}
          </TabsTrigger>
          <TabsTrigger value="report">
            {t("studentOps.rewards.redemptionReport")}
          </TabsTrigger>
        </TabsList>

        {/* 商品列表 */}
        <TabsContent value="products" className="space-y-3">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex flex-wrap items-center gap-2">
                <Select
                  value={productType}
                  onValueChange={(v) => {
                    setProductType(v);
                    setProductPage(1);
                  }}
                >
                  <SelectTrigger className="w-[150px]">
                    <SelectValue placeholder={t("studentOps.rewards.type")} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__all">{t("studentOps.all")}</SelectItem>
                    <SelectItem value="virtual">
                      {t("studentOps.rewards.typeVirtual")}
                    </SelectItem>
                    <SelectItem value="physical">
                      {t("studentOps.rewards.typePhysical")}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <Input
                  value={keyword}
                  onChange={(e) => {
                    setKeyword(e.target.value);
                    setProductPage(1);
                  }}
                  placeholder={t("studentOps.search")}
                  className="w-[180px]"
                />
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {productsQuery.isLoading ? (
                <LoadingRow />
              ) : productsQuery.isError ? (
                <ErrorBox />
              ) : productsQuery.data?.items.length === 0 ? (
                <EmptyState
                  title={t("studentOps.rewards.noProducts")}
                  action={
                    <Button size="sm" onClick={openCreate}>
                      <Plus className="h-4 w-4 mr-1" />{" "}
                      {t("studentOps.rewards.create")}
                    </Button>
                  }
                />
              ) : (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("studentOps.rewards.name")}</TableHead>
                        <TableHead>{t("studentOps.rewards.type")}</TableHead>
                        <TableHead>
                          {t("studentOps.rewards.pointsRequired")}
                        </TableHead>
                        <TableHead>{t("studentOps.rewards.stock")}</TableHead>
                        <TableHead>
                          {t("studentOps.rewards.exchangeLimit")}
                        </TableHead>
                        <TableHead>{t("studentOps.rewards.active")}</TableHead>
                        <TableHead className="text-right">
                          {t("studentOps.actions")}
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {productsQuery.data?.items.map((p) => {
                        const lowStock =
                          p.productType === "physical" &&
                          p.isActive &&
                          p.stock <= p.stockWarning;
                        return (
                          <TableRow key={p.id}>
                            <TableCell className="font-medium">
                              <div className="flex items-center gap-2">
                                <Package className="h-4 w-4 text-muted-foreground" />
                                {p.name}
                                {lowStock && (
                                  <Badge
                                    variant="outline"
                                    className="border-orange-200 bg-orange-50 text-orange-700"
                                  >
                                    <AlertTriangle className="h-3 w-3 mr-1" />
                                    {t("studentOps.rewards.lowStock")}
                                  </Badge>
                                )}
                              </div>
                            </TableCell>
                            <TableCell>
                              {p.productType === "virtual"
                                ? t("studentOps.rewards.typeVirtual")
                                : t("studentOps.rewards.typePhysical")}
                            </TableCell>
                            <TableCell>{p.pointsRequired}</TableCell>
                            <TableCell>
                              {p.productType === "virtual" ? "∞" : p.stock}
                            </TableCell>
                            <TableCell>
                              {p.exchangeLimitPerStudent === 0
                                ? t("studentOps.rewards.exchangeLimitHint")
                                : p.exchangeLimitPerStudent}
                            </TableCell>
                            <TableCell>
                              <StatusBadge
                                value={p.isActive ? "approved" : "cancelled"}
                                label={
                                  p.isActive
                                    ? t("studentOps.rewards.active")
                                    : t("studentOps.rewards.inactive")
                                }
                              />
                            </TableCell>
                            <TableCell className="text-right">
                              <div className="flex justify-end gap-1">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => openRedeem(p)}
                                  disabled={!p.isActive}
                                  aria-label={t("studentOps.rewards.exchange")}
                                >
                                  <ShoppingBag className="h-4 w-4" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => openEdit(p)}
                                  aria-label={t("studentOps.rewards.edit")}
                                >
                                  <Pencil className="h-4 w-4" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() =>
                                    setConfirmToggle({
                                      product: p,
                                      next: !p.isActive,
                                    })
                                  }
                                  aria-label={
                                    p.isActive
                                      ? t("studentOps.rewards.offShelf")
                                      : t("studentOps.rewards.onShelf")
                                  }
                                >
                                  {p.isActive ? (
                                    <ArrowDown className="h-4 w-4 text-destructive" />
                                  ) : (
                                    <ArrowUp className="h-4 w-4 text-green-600" />
                                  )}
                                </Button>
                              </div>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                  <div className="p-3">
                    <Pagination
                      page={productsQuery.data?.page || 1}
                      pageSize={productsQuery.data?.pageSize || 20}
                      total={productsQuery.data?.total || 0}
                      onPageChange={setProductPage}
                    />
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* 兑换记录 */}
        <TabsContent value="redemptions" className="space-y-3">
          <Card>
            <CardHeader className="pb-3">
              <Select
                value={redemptionStatus}
                onValueChange={(v) => {
                  setRedemptionStatus(v);
                  setRedemptionPage(1);
                }}
              >
                <SelectTrigger className="w-[160px]">
                  <SelectValue
                    placeholder={t("studentOps.rewards.statusPending")}
                  />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all">{t("studentOps.all")}</SelectItem>
                  <SelectItem value="pending">
                    {t("studentOps.rewards.statusPending")}
                  </SelectItem>
                  <SelectItem value="approved">
                    {t("studentOps.rewards.statusApproved")}
                  </SelectItem>
                  <SelectItem value="delivered">
                    {t("studentOps.rewards.statusDelivered")}
                  </SelectItem>
                  <SelectItem value="cancelled">
                    {t("studentOps.rewards.statusCancelled")}
                  </SelectItem>
                </SelectContent>
              </Select>
            </CardHeader>
            <CardContent className="p-0">
              {redemptionsQuery.isLoading ? (
                <LoadingRow />
              ) : redemptionsQuery.isError ? (
                <ErrorBox />
              ) : redemptionsQuery.data?.items.length === 0 ? (
                <EmptyState title={t("studentOps.rewards.noRecords")} />
              ) : (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("studentOps.rewards.student")}</TableHead>
                        <TableHead>{t("studentOps.rewards.product")}</TableHead>
                        <TableHead>
                          {t("studentOps.rewards.pointsSpent")}
                        </TableHead>
                        <TableHead>
                          {t("studentOps.rewards.statusPending")}
                        </TableHead>
                        <TableHead>{t("studentOps.rewards.notes")}</TableHead>
                        <TableHead className="text-right">
                          {t("studentOps.actions")}
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {redemptionsQuery.data?.items.map((r) => (
                        <TableRow key={r.id}>
                          <TableCell className="font-medium">
                            {r.studentName}
                          </TableCell>
                          <TableCell>{r.productName}</TableCell>
                          <TableCell className="text-red-500">
                            -{r.pointsSpent}
                          </TableCell>
                          <TableCell>
                            <StatusBadge
                              value={r.status}
                              label={t(
                                `studentOps.rewards.status${cap(r.status)}`,
                              )}
                            />
                          </TableCell>
                          <TableCell className="max-w-[180px] truncate text-muted-foreground">
                            {r.notes || "—"}
                          </TableCell>
                          <TableCell className="text-right">
                            <div className="flex justify-end gap-1">
                              {r.status === "pending" && (
                                <>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() =>
                                      setConfirmStatus({
                                        id: r.id,
                                        status: "approved",
                                      })
                                    }
                                    aria-label={t("studentOps.rewards.approve")}
                                  >
                                    <CheckCircle2 className="h-4 w-4 text-blue-600" />
                                  </Button>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() =>
                                      setConfirmStatus({
                                        id: r.id,
                                        status: "cancelled",
                                      })
                                    }
                                    aria-label={t("studentOps.rewards.cancel")}
                                  >
                                    <XCircle className="h-4 w-4 text-destructive" />
                                  </Button>
                                </>
                              )}
                              {r.status === "approved" && (
                                <>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() =>
                                      setConfirmStatus({
                                        id: r.id,
                                        status: "delivered",
                                      })
                                    }
                                    aria-label={t("studentOps.rewards.deliver")}
                                  >
                                    <PackageCheck className="h-4 w-4 text-green-600" />
                                  </Button>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() =>
                                      setConfirmStatus({
                                        id: r.id,
                                        status: "cancelled",
                                      })
                                    }
                                    aria-label={t("studentOps.rewards.cancel")}
                                  >
                                    <XCircle className="h-4 w-4 text-destructive" />
                                  </Button>
                                </>
                              )}
                              {(r.status === "delivered" ||
                                r.status === "cancelled") && (
                                <span className="text-xs text-muted-foreground">
                                  —
                                </span>
                              )}
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <div className="p-3">
                    <Pagination
                      page={redemptionsQuery.data?.page || 1}
                      pageSize={redemptionsQuery.data?.pageSize || 20}
                      total={redemptionsQuery.data?.total || 0}
                      onPageChange={setRedemptionPage}
                    />
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>
        {/* 库存统计 */}
        <TabsContent value="inventory" className="space-y-3">
          <InventoryReportTab />
        </TabsContent>

        {/* 兑换报表 */}
        <TabsContent value="report" className="space-y-3">
          <RedemptionReportTab classId={classId} />
        </TabsContent>
      </Tabs>

      <RewardProductFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        editing={editing}
        onSaved={invalidateProducts}
      />

      <RedemptionDialog
        open={redeemOpen}
        onOpenChange={setRedeemOpen}
        classId={classId}
        product={redeemProduct}
        onDone={() => {
          invalidateProducts();
          invalidateRedemptions();
          queryClient.invalidateQueries({ queryKey: ["so-credit-accounts"] });
          queryClient.invalidateQueries({ queryKey: ["so-credit-txns"] });
        }}
      />

      <AlertDialog
        open={!!confirmToggle}
        onOpenChange={(open) => !open && setConfirmToggle(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirmToggle?.next
                ? t("studentOps.rewards.onShelf")
                : t("studentOps.rewards.offShelf")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirmToggle?.next
                ? t("studentOps.rewards.onShelfConfirm")
                : t("studentOps.rewards.offShelfConfirm")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("studentOps.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (!confirmToggle) return;
                const { product, next } = confirmToggle;
                updateRewardProduct(product.id, { isActive: next })
                  .then(() => {
                    toast.success(t("studentOps.rewards.updateSuccess"));
                    invalidateProducts();
                  })
                  .catch((e: Error) => toast.error(e.message))
                  .finally(() => setConfirmToggle(null));
              }}
            >
              {t("studentOps.confirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={!!confirmStatus}
        onOpenChange={(open) => !open && setConfirmStatus(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirmStatus?.status === "approved"
                ? t("studentOps.rewards.approve")
                : confirmStatus?.status === "delivered"
                  ? t("studentOps.rewards.deliver")
                  : t("studentOps.rewards.cancel")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirmStatus?.status === "approved"
                ? t("studentOps.rewards.approveConfirm")
                : confirmStatus?.status === "delivered"
                  ? t("studentOps.rewards.deliverConfirm")
                  : t("studentOps.rewards.cancelConfirm")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("studentOps.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (!confirmStatus) return;
                const { id, status } = confirmStatus;
                setConfirmStatus(null);
                statusMutation.mutate({ id, status });
              }}
            >
              {t("studentOps.confirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

/* ── 库存统计 / 兑换报表 ── */

function StatCard({
  label,
  value,
  danger,
}: {
  label: string;
  value: number;
  danger?: boolean;
}) {
  return (
    <div className="rounded-lg border border-border/60 p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div
        className={`mt-1 text-xl font-semibold ${danger ? "text-destructive" : ""}`}
      >
        {value}
      </div>
    </div>
  );
}

function MiniTrend({
  data,
  label,
}: {
  data: ReportTrendPoint[];
  label: string;
}) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart
        data={data}
        margin={{ top: 5, right: 10, left: -15, bottom: 0 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
        <XAxis
          dataKey="period"
          tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
        />
        <YAxis
          allowDecimals={false}
          tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
        />
        <Tooltip
          contentStyle={{
            background: "hsl(var(--card))",
            border: "1px solid hsl(var(--border))",
            borderRadius: 8,
            fontSize: 12,
          }}
        />
        <Bar
          dataKey="count"
          name={label}
          fill="hsl(217 91% 60%)"
          radius={[3, 3, 0, 0]}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ── 库存统计 Tab ── */
function InventoryReportTab() {
  const { t } = useLocale();
  const query = useQuery({
    queryKey: ["so-stock-stats"],
    queryFn: () => stockStats(),
  });

  const stats = query.data;

  return (
    <Card>
      <CardContent className="p-4">
        {query.isLoading ? (
          <LoadingRow />
        ) : query.isError ? (
          <ErrorBox />
        ) : !stats ? (
          <EmptyState title={t("studentOps.rewards.noProducts")} />
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
              <StatCard
                label={t("studentOps.rewards.totalProducts")}
                value={stats.summary.totalProducts}
              />
              <StatCard
                label={t("studentOps.rewards.physicalProducts")}
                value={stats.summary.physicalProducts}
              />
              <StatCard
                label={t("studentOps.rewards.lowStockCount")}
                value={stats.summary.lowStockCount}
                danger={stats.summary.lowStockCount > 0}
              />
              <StatCard
                label={t("studentOps.rewards.outOfStockCount")}
                value={stats.summary.outOfStockCount}
                danger={stats.summary.outOfStockCount > 0}
              />
              <StatCard
                label={t("studentOps.rewards.totalStock")}
                value={stats.summary.totalStock}
              />
            </div>

            <div className="rounded-md border border-border/60">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("studentOps.rewards.name")}</TableHead>
                    <TableHead>{t("studentOps.rewards.type")}</TableHead>
                    <TableHead>{t("studentOps.rewards.stock")}</TableHead>
                    <TableHead>
                      {t("studentOps.rewards.stockWarning")}
                    </TableHead>
                    <TableHead>{t("studentOps.badges.status")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {stats.items.map((p) => (
                    <TableRow
                      key={p.id}
                      className={p.lowStock ? "bg-orange-50/40" : ""}
                    >
                      <TableCell className="font-medium">
                        <div className="flex items-center gap-2">
                          <Package className="h-4 w-4 text-muted-foreground" />
                          {p.name}
                        </div>
                      </TableCell>
                      <TableCell>
                        {p.productType === "virtual"
                          ? t("studentOps.rewards.typeVirtual")
                          : t("studentOps.rewards.typePhysical")}
                      </TableCell>
                      <TableCell>
                        {p.productType === "virtual" ? (
                          "∞"
                        ) : (
                          <span
                            className={
                              p.outOfStock
                                ? "text-destructive font-medium"
                                : p.lowStock
                                  ? "text-orange-600 font-medium"
                                  : ""
                            }
                          >
                            {p.stock}
                          </span>
                        )}
                      </TableCell>
                      <TableCell>{p.stockWarning}</TableCell>
                      <TableCell>
                        {p.lowStock && (
                          <Badge
                            variant="outline"
                            className="border-orange-200 bg-orange-50 text-orange-700"
                          >
                            <AlertTriangle className="h-3 w-3 mr-1" />
                            {p.outOfStock
                              ? t("studentOps.rewards.outOfStock")
                              : t("studentOps.rewards.lowStock")}
                          </Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {stats.trend.length > 0 && (
              <div className="mt-4">
                <h4 className="text-sm font-medium mb-2 flex items-center gap-1.5">
                  <TrendingUp className="h-4 w-4 text-primary" />
                  {t("studentOps.rewards.stockTrend")}
                </h4>
                <div className="h-48 rounded-md border border-border/60 p-2">
                  <MiniTrend
                    data={stats.trend}
                    label={t("studentOps.rewards.exchangeCount")}
                  />
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

/* ── 兑换报表 Tab ── */
function RedemptionReportTab({ classId }: { classId: string }) {
  const { t } = useLocale();
  const [groupBy, setGroupBy] = useState("week");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const query = useQuery({
    queryKey: ["so-redemption-report", classId, startDate, endDate, groupBy],
    queryFn: () =>
      redemptionReport({
        classId: classId || undefined,
        startDate: startDate || undefined,
        endDate: endDate || undefined,
        groupBy,
      }),
  });

  const data: RedemptionReport | undefined = query.data;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <Select value={groupBy} onValueChange={setGroupBy}>
            <SelectTrigger className="w-[130px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="week">
                {t("studentOps.rewards.trendWeek")}
              </SelectItem>
              <SelectItem value="month">
                {t("studentOps.rewards.trendMonth")}
              </SelectItem>
            </SelectContent>
          </Select>
          <Input
            type="date"
            className="w-[150px]"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
          />
          <span className="text-xs text-muted-foreground">~</span>
          <Input
            type="date"
            className="w-[150px]"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
          />
        </div>
      </CardHeader>
      <CardContent className="p-4">
        {query.isLoading ? (
          <LoadingRow />
        ) : query.isError ? (
          <ErrorBox />
        ) : !data ? (
          <EmptyState title={t("studentOps.rewards.noRecords")} />
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              <StatCard
                label={t("studentOps.rewards.totalRedemptions")}
                value={data.summary.totalRedemptions}
              />
              <StatCard
                label={t("studentOps.rewards.totalPointsSpent")}
                value={data.summary.totalPointsSpent}
              />
              <StatCard
                label={t("studentOps.rewards.activeCount")}
                value={data.summary.activeCount}
              />
              <StatCard
                label={t("studentOps.rewards.cancelledCount")}
                value={data.summary.cancelledCount}
                danger={data.summary.cancelledCount > 0}
              />
            </div>

            {data.topProducts.length > 0 && (
              <div className="mb-4">
                <h4 className="text-sm font-medium mb-2 flex items-center gap-1.5">
                  <PackageSearch className="h-4 w-4 text-primary" />
                  {t("studentOps.rewards.topProducts")}
                </h4>
                <div className="rounded-md border border-border/60 overflow-hidden">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-14">#</TableHead>
                        <TableHead>{t("studentOps.rewards.name")}</TableHead>
                        <TableHead>
                          {t("studentOps.rewards.exchangeCount")}
                        </TableHead>
                        <TableHead>
                          {t("studentOps.rewards.pointsSpent")}
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.topProducts.map((p, i) => (
                        <TableRow key={p.productId}>
                          <TableCell className="font-medium text-muted-foreground">
                            {i + 1}
                          </TableCell>
                          <TableCell className="font-medium">
                            {p.productName || "—"}
                          </TableCell>
                          <TableCell>{p.count}</TableCell>
                          <TableCell className="text-red-500">
                            -{p.pointsSpent}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </div>
            )}

            {data.statusDistribution.length > 0 && (
              <div className="mb-4">
                <h4 className="text-sm font-medium mb-2">
                  {t("studentOps.rewards.statusDistribution")}
                </h4>
                <div className="flex flex-wrap gap-2">
                  {data.statusDistribution.map((d) => (
                    <div
                      key={d.status}
                      className="flex items-center gap-2 rounded-lg border border-border/60 px-3 py-2 text-sm"
                    >
                      <StatusBadge
                        value={d.status}
                        label={t(`studentOps.rewards.status${cap(d.status)}`)}
                      />
                      <span className="font-semibold">{d.count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {data.trend.length > 0 && (
              <div>
                <h4 className="text-sm font-medium mb-2 flex items-center gap-1.5">
                  <BarChart3 className="h-4 w-4 text-primary" />
                  {t("studentOps.rewards.exchangeTrend")}
                </h4>
                <div className="h-48 rounded-md border border-border/60 p-2">
                  <MiniTrend
                    data={data.trend}
                    label={t("studentOps.rewards.exchangeCount")}
                  />
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function cap(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

function LoadingRow() {
  const { t } = useLocale();
  return (
    <div className="flex items-center justify-center py-12 text-muted-foreground">
      <Loader2 className="h-5 w-5 animate-spin mr-2" />{" "}
      {t("studentOps.loading")}
    </div>
  );
}

function ErrorBox() {
  const { t } = useLocale();
  return (
    <div className="p-4">
      <Alert variant="destructive">
        <AlertTitle>{t("studentOps.loadError")}</AlertTitle>
      </Alert>
    </div>
  );
}

/* ── 商品 创建/编辑 ── */
interface ProductFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: RewardProduct | null;
  onSaved: () => void;
}

function RewardProductFormDialog({
  open,
  onOpenChange,
  editing,
  onSaved,
}: ProductFormProps) {
  const { t } = useLocale();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [productType, setProductType] = useState("physical");
  const [pointsRequired, setPointsRequired] = useState(100);
  const [stock, setStock] = useState(10);
  const [stockWarning, setStockWarning] = useState(5);
  const [exchangeLimit, setExchangeLimit] = useState(0);
  const [isActive, setIsActive] = useState(true);

  useEffect(() => {
    if (open) {
      setName(editing?.name || "");
      setDescription(editing?.description || "");
      setProductType(editing?.productType || "physical");
      setPointsRequired(editing?.pointsRequired ?? 100);
      setStock(editing?.stock ?? 10);
      setStockWarning(editing?.stockWarning ?? 5);
      setExchangeLimit(editing?.exchangeLimitPerStudent ?? 0);
      setIsActive(editing?.isActive ?? true);
    }
  }, [open, editing]);

  const mutation = useMutation({
    mutationFn: (body: RewardProductInput) =>
      editing
        ? updateRewardProduct(editing.id, body)
        : createRewardProduct(body),
    onSuccess: () => {
      toast.success(
        editing
          ? t("studentOps.rewards.updateSuccess")
          : t("studentOps.rewards.createSuccess"),
      );
      onSaved();
      onOpenChange(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const submit = () => {
    if (!name.trim()) {
      toast.error(t("studentOps.required"));
      return;
    }
    if (!pointsRequired || pointsRequired < 1) {
      toast.error(t("studentOps.positiveNumber"));
      return;
    }
    mutation.mutate({
      name: name.trim(),
      description: description || null,
      productType,
      pointsRequired,
      stock: productType === "virtual" ? 9999 : stock,
      stockWarning,
      isActive,
      exchangeLimitPerStudent: exchangeLimit,
      sortOrder: 0,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {editing
              ? t("studentOps.rewards.edit")
              : t("studentOps.rewards.create")}
          </DialogTitle>
          <DialogDescription>
            {t("studentOps.rewards.products")}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label>{t("studentOps.rewards.name")} *</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("studentOps.rewards.namePlaceholder")}
            />
          </div>
          <div className="grid gap-2">
            <Label>{t("studentOps.rewards.description")}</Label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>{t("studentOps.rewards.type")}</Label>
              <Select value={productType} onValueChange={setProductType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="virtual">
                    {t("studentOps.rewards.typeVirtual")}
                  </SelectItem>
                  <SelectItem value="physical">
                    {t("studentOps.rewards.typePhysical")}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>{t("studentOps.rewards.pointsRequired")} *</Label>
              <Input
                type="number"
                min={1}
                value={pointsRequired}
                onChange={(e) => setPointsRequired(Number(e.target.value))}
              />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            {productType === "physical" && (
              <div className="grid gap-2">
                <Label>{t("studentOps.rewards.stock")}</Label>
                <Input
                  type="number"
                  min={0}
                  value={stock}
                  onChange={(e) => setStock(Number(e.target.value))}
                />
              </div>
            )}
            <div className="grid gap-2">
              <Label>{t("studentOps.rewards.stockWarning")}</Label>
              <Input
                type="number"
                min={0}
                value={stockWarning}
                onChange={(e) => setStockWarning(Number(e.target.value))}
              />
            </div>
            <div className="grid gap-2">
              <Label>{t("studentOps.rewards.exchangeLimit")}</Label>
              <Input
                type="number"
                min={0}
                value={exchangeLimit}
                onChange={(e) => setExchangeLimit(Number(e.target.value))}
              />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("studentOps.cancel")}
          </Button>
          <Button onClick={submit} disabled={mutation.isPending}>
            {mutation.isPending && (
              <Loader2 className="h-4 w-4 mr-1 animate-spin" />
            )}
            {t("studentOps.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ── 兑换弹窗 ── */
interface RedemptionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  classId: string;
  product: RewardProduct | null;
  onDone: () => void;
}

function RedemptionDialog({
  open,
  onOpenChange,
  classId,
  product,
  onDone,
}: RedemptionDialogProps) {
  const { t } = useLocale();
  const [studentId, setStudentId] = useState("");
  const [confirmExchange, setConfirmExchange] = useState(false);

  useEffect(() => {
    if (open) setStudentId("");
  }, [open]);

  const mutation = useMutation({
    mutationFn: () => {
      if (!product) {
        throw new Error("No product selected");
      }
      return createRedemption({
        studentId,
        productId: product.id,
      });
    },
    onSuccess: (res) => {
      toast.success(
        t("studentOps.rewards.exchangeSuccess", { balance: res.balanceAfter }),
      );
      onDone();
      onOpenChange(false);
    },
    onError: (e: Error) => {
      const msg = e.message.includes("insufficient_balance")
        ? t("studentOps.rewards.insufficientBalance")
        : e.message.includes("out_of_stock")
          ? t("studentOps.rewards.outOfStock")
          : e.message.includes("limit_exceeded")
            ? t("studentOps.rewards.limitExceeded")
            : e.message;
      toast.error(msg);
    },
  });

  const submit = () => {
    if (!studentId) {
      toast.error(t("studentOps.selectStudent"));
      return;
    }
    if (!product) return;
    setConfirmExchange(true);
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("studentOps.rewards.exchangeTitle")}</DialogTitle>
            <DialogDescription>
              {product?.name} · {t("studentOps.rewards.pointsRequired")}{" "}
              {product?.pointsRequired}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="grid gap-2">
              <Label>{t("studentOps.selectStudent")} *</Label>
              <StudentPicker
                classId={classId}
                value={studentId}
                onChange={setStudentId}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              {t("studentOps.cancel")}
            </Button>
            <Button onClick={submit} disabled={mutation.isPending || !product}>
              {mutation.isPending && (
                <Loader2 className="h-4 w-4 mr-1 animate-spin" />
              )}
              {t("studentOps.rewards.exchange")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={confirmExchange}
        onOpenChange={(open) => !open && setConfirmExchange(false)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("studentOps.rewards.exchange")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t("studentOps.rewards.exchangeConfirm", {
                points: product?.pointsRequired,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("studentOps.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (!product) return;
                setConfirmExchange(false);
                mutation.mutate();
              }}
            >
              {t("studentOps.confirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
