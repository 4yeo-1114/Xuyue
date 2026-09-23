import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Wallet,
  Plus,
  Minus,
  Loader2,
  Scale,
  TrendingUp,
  TrendingDown,
  Users,
} from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  listCreditAccounts,
  listCreditTransactions,
  manualCredit,
  creditReport,
  creditReconciliation,
} from "@/services/studentOpsApi";
import { ClassSelector } from "@/components/student-ops/shared/ClassSelector";
import { StudentPicker } from "@/components/student-ops/shared/StudentPicker";
import { StatusBadge } from "@/components/student-ops/shared/StatusBadge";
import { Pagination } from "@/components/student-ops/shared/Pagination";
import { EmptyState } from "@/components/student-ops/shared/EmptyState";

const TXN_TYPES = [
  "badge_award",
  "manual_add",
  "redemption",
  "manual_deduct",
  "adjustment",
  "practice_approved",
  "expire",
];

function txnTypeLabel(t: (typeof TXN_TYPES)[number]): string {
  const map: Record<string, string> = {
    badge_award: "studentOps.credits.typeBadgeAward",
    manual_add: "studentOps.credits.typeManualAdd",
    redemption: "studentOps.credits.typeRedemption",
    manual_deduct: "studentOps.credits.typeManualDeduct",
    adjustment: "studentOps.credits.typeAdjustment",
    practice_approved: "studentOps.credits.typePracticeApproved",
    expire: "studentOps.credits.typeExpire",
  };
  return map[t] || t;
}

interface CreditSectionProps {
  classId: string;
  onClassChange: (id: string) => void;
}

export function CreditSection({ classId, onClassChange }: CreditSectionProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState("accounts");

  // 账户
  const [sortBy, setSortBy] = useState("balance_desc");
  const [acctPage, setAcctPage] = useState(1);
  // 流水
  const [txnType, setTxnType] = useState("");
  const [txnStart, setTxnStart] = useState("");
  const [txnEnd, setTxnEnd] = useState("");
  const [txnPage, setTxnPage] = useState(1);

  const [manualOpen, setManualOpen] = useState(false);
  const [reconOpen, setReconOpen] = useState(false);

  const accountsQuery = useQuery({
    queryKey: ["so-credit-accounts", classId, sortBy, acctPage],
    queryFn: () =>
      listCreditAccounts({
        classId: classId || undefined,
        sortBy,
        page: acctPage,
        pageSize: 20,
      }),
  });

  const txnsQuery = useQuery({
    queryKey: ["so-credit-txns", classId, txnType, txnStart, txnEnd, txnPage],
    queryFn: () =>
      listCreditTransactions({
        classId: classId || undefined,
        transactionType: txnType || undefined,
        startDate: txnStart || undefined,
        endDate: txnEnd || undefined,
        page: txnPage,
        pageSize: 20,
      }),
    enabled: tab === "transactions",
  });

  const reportQuery = useQuery({
    queryKey: ["so-credit-report", classId],
    queryFn: () => creditReport({ classId: classId || undefined }),
    enabled: tab === "report",
  });

  const invalidateCredit = () => {
    queryClient.invalidateQueries({ queryKey: ["so-credit-accounts"] });
    queryClient.invalidateQueries({ queryKey: ["so-credit-txns"] });
    queryClient.invalidateQueries({ queryKey: ["so-credit-report"] });
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
            <Wallet className="h-4 w-4 text-primary" />
          </div>
          <ClassSelector value={classId} onChange={onClassChange} />
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => { setReconOpen(true); }}>
            <Scale className="h-4 w-4 mr-1" /> {t("studentOps.credits.reconciliation")}
          </Button>
          <Button size="sm" onClick={() => {
            if (!classId) {
              toast.error(t("studentOps.credits.requireClass"));
              return;
            }
            setManualOpen(true);
          }}>
            <Plus className="h-4 w-4 mr-1" /> {t("studentOps.credits.manualCredit")}
          </Button>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="accounts">{t("studentOps.credits.accounts")}</TabsTrigger>
          <TabsTrigger value="transactions">{t("studentOps.credits.transactions")}</TabsTrigger>
          <TabsTrigger value="report">{t("studentOps.credits.report")}</TabsTrigger>
        </TabsList>

        {/* 账户总览 */}
        <TabsContent value="accounts" className="space-y-3">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex flex-wrap items-center gap-2">
                <Select value={sortBy} onValueChange={(v) => { setSortBy(v); setAcctPage(1); }}>
                  <SelectTrigger className="w-[180px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="balance_desc">{t("studentOps.credits.sortByBalanceDesc")}</SelectItem>
                    <SelectItem value="balance_asc">{t("studentOps.credits.sortByBalanceAsc")}</SelectItem>
                    <SelectItem value="total_earned_desc">{t("studentOps.credits.sortByEarnedDesc")}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {accountsQuery.isLoading ? (
                <LoadingRow />
              ) : accountsQuery.isError ? (
                <ErrorBox />
              ) : accountsQuery.data?.items.length === 0 ? (
                <EmptyState title={t("studentOps.credits.noAccounts")} />
              ) : (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("studentOps.credits.student")}</TableHead>
                        <TableHead>{t("studentOps.credits.class")}</TableHead>
                        <TableHead>{t("studentOps.credits.balance")}</TableHead>
                        <TableHead>{t("studentOps.credits.totalEarned")}</TableHead>
                        <TableHead>{t("studentOps.credits.totalSpent")}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {accountsQuery.data?.items.map((a) => (
                        <TableRow key={a.accountId}>
                          <TableCell className="font-medium">{a.studentName}</TableCell>
                          <TableCell>{a.className}</TableCell>
                          <TableCell className="font-semibold text-primary">{a.balance}</TableCell>
                          <TableCell className="text-green-600">+{a.totalEarned}</TableCell>
                          <TableCell className="text-red-500">-{a.totalSpent}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <div className="p-3">
                    <Pagination
                      page={accountsQuery.data?.page || 1}
                      pageSize={accountsQuery.data?.pageSize || 20}
                      total={accountsQuery.data?.total || 0}
                      onPageChange={setAcctPage}
                    />
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* 流水 */}
        <TabsContent value="transactions" className="space-y-3">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex flex-wrap items-center gap-2">
                <Select value={txnType} onValueChange={(v) => { setTxnType(v); setTxnPage(1); }}>
                  <SelectTrigger className="w-[160px]">
                    <SelectValue placeholder={t("studentOps.credits.type")} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__all">{t("studentOps.all")}</SelectItem>
                    {TXN_TYPES.map((ty) => (
                      <SelectItem key={ty} value={ty}>{t(txnTypeLabel(ty))}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input type="date" value={txnStart} onChange={(e) => { setTxnStart(e.target.value); setTxnPage(1); }} className="w-[150px]" />
                <Input type="date" value={txnEnd} onChange={(e) => { setTxnEnd(e.target.value); setTxnPage(1); }} className="w-[150px]" />
                <Button size="sm" variant="outline" onClick={() => { setTxnType(""); setTxnStart(""); setTxnEnd(""); setTxnPage(1); }}>
                  {t("studentOps.reset")}
                </Button>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {txnsQuery.isLoading ? (
                <LoadingRow />
              ) : txnsQuery.isError ? (
                <ErrorBox />
              ) : txnsQuery.data?.items.length === 0 ? (
                <EmptyState title={t("studentOps.credits.noTransactions")} />
              ) : (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("studentOps.credits.createdAt")}</TableHead>
                        <TableHead>{t("studentOps.credits.student")}</TableHead>
                        <TableHead>{t("studentOps.credits.type")}</TableHead>
                        <TableHead>{t("studentOps.credits.amount")}</TableHead>
                        <TableHead>{t("studentOps.credits.balanceAfter")}</TableHead>
                        <TableHead>{t("studentOps.credits.description")}</TableHead>
                        <TableHead>{t("studentOps.credits.operator")}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {txnsQuery.data?.items.map((tx) => (
                        <TableRow key={tx.id}>
                          <TableCell className="whitespace-nowrap">{fmtTime(tx.createdAt)}</TableCell>
                          <TableCell>{tx.studentName}</TableCell>
                          <TableCell>{t(txnTypeLabel(tx.transactionType as typeof TXN_TYPES[number]) || tx.transactionType)}</TableCell>
                          <TableCell className={tx.amount >= 0 ? "text-green-600" : "text-red-500"}>
                            {tx.amount >= 0 ? "+" : ""}{tx.amount}
                          </TableCell>
                          <TableCell>{tx.balanceAfter}</TableCell>
                          <TableCell className="max-w-[240px] truncate text-muted-foreground">{tx.description || "—"}</TableCell>
                          <TableCell>{tx.operatorName || "—"}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <div className="p-3">
                    <Pagination
                      page={txnsQuery.data?.page || 1}
                      pageSize={txnsQuery.data?.pageSize || 20}
                      total={txnsQuery.data?.total || 0}
                      onPageChange={setTxnPage}
                    />
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* 报表 */}
        <TabsContent value="report" className="space-y-3">
          {reportQuery.isLoading ? (
            <LoadingRow />
          ) : reportQuery.isError ? (
            <ErrorBox />
          ) : (
            <div className="space-y-3">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <StatCard icon={<Users />} label={t("studentOps.credits.totalStudents")} value={String(reportQuery.data?.summary.totalStudents ?? 0)} />
                <StatCard icon={<Wallet />} label={t("studentOps.credits.totalBalance")} value={String(reportQuery.data?.summary.totalBalance ?? 0)} />
                <StatCard icon={<TrendingUp />} label={t("studentOps.credits.earnedPeriod")} value={`+${reportQuery.data?.summary.totalEarnedPeriod ?? 0}`} />
                <StatCard icon={<TrendingDown />} label={t("studentOps.credits.spentPeriod")} value={`-${reportQuery.data?.summary.totalSpentPeriod ?? 0}`} />
              </div>
              <Card>
                <CardHeader className="pb-3"><CardTitle className="text-base">{t("studentOps.credits.report")}</CardTitle></CardHeader>
                <CardContent className="p-0">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("studentOps.credits.class")}</TableHead>
                        <TableHead>{t("studentOps.credits.totalStudents")}</TableHead>
                        <TableHead>{t("studentOps.credits.totalBalance")}</TableHead>
                        <TableHead>{t("studentOps.credits.avgBalance")}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(reportQuery.data?.byClass || []).map((c) => (
                        <TableRow key={c.classId}>
                          <TableCell>{c.className}</TableCell>
                          <TableCell>{c.studentCount}</TableCell>
                          <TableCell>{c.totalBalance}</TableCell>
                          <TableCell>{c.avgBalance}</TableCell>
                        </TableRow>
                      ))}
                      {(reportQuery.data?.byClass || []).length === 0 && (
                        <TableRow><TableCell colSpan={4} className="text-center text-muted-foreground">{t("studentOps.empty")}</TableCell></TableRow>
                      )}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>
      </Tabs>

      <ManualCreditDialog
        open={manualOpen}
        onOpenChange={setManualOpen}
        classId={classId}
        onDone={invalidateCredit}
      />

      <ReconciliationDialog open={reconOpen} onOpenChange={setReconOpen} classId={classId} />
    </div>
  );
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
          {icon}
        </div>
        <div>
          <div className="text-xs text-muted-foreground">{label}</div>
          <div className="text-lg font-bold">{value}</div>
        </div>
      </CardContent>
    </Card>
  );
}

function LoadingRow() {
  const { t } = useLocale();
  return (
    <div className="flex items-center justify-center py-12 text-muted-foreground">
      <Loader2 className="h-5 w-5 animate-spin mr-2" /> {t("studentOps.loading")}
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

function fmtTime(s?: string) {
  if (!s) return "—";
  return s.replace("T", " ").slice(0, 16);
}

/* ── 手动加减分弹窗 ── */
interface ManualCreditDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  classId: string;
  onDone: () => void;
}

function ManualCreditDialog({ open, onOpenChange, classId, onDone }: ManualCreditDialogProps) {
  const { t } = useLocale();
  const [studentId, setStudentId] = useState("");
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      manualCredit({
        studentId,
        amount: Number(amount),
        description: description.trim(),
      }),
    onSuccess: (res) => {
      toast.success(t("studentOps.credits.manualSuccess", { balance: res.balance }));
      onDone();
      onOpenChange(false);
      setStudentId("");
      setAmount("");
      setDescription("");
    },
    onError: (e: Error) => {
      toast.error(e.message.includes("insufficient_balance") ? t("studentOps.credits.insufficientBalance") : e.message);
    },
  });

  const submit = () => {
    if (!studentId) {
      toast.error(t("studentOps.selectStudent"));
      return;
    }
    const n = Number(amount);
    if (!amount || Number.isNaN(n) || n === 0) {
      toast.error(t("studentOps.required"));
      return;
    }
    if (!description.trim()) {
      toast.error(t("studentOps.credits.manualDescPlaceholder"));
      return;
    }
    mutation.mutate();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t("studentOps.credits.manualCredit")}</DialogTitle>
          <DialogDescription>{t("studentOps.credits.manualAddDesc")}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label>{t("studentOps.selectStudent")} *</Label>
            <StudentPicker classId={classId} value={studentId} onChange={setStudentId} />
          </div>
          <div className="grid gap-2">
            <Label>{t("studentOps.credits.manualAmount")} *</Label>
            <div className="flex items-center gap-2">
              <Input
                type="number"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder={t("studentOps.amountPlaceholder")}
              />
              <div className="flex gap-1">
                <Button type="button" variant="outline" size="sm" onClick={() => setAmount(String(Math.abs(Number(amount) || 0)))}>
                  <Plus className="h-4 w-4" />
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={() => setAmount(String(-Math.abs(Number(amount) || 0)))}>
                  <Minus className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              {t("studentOps.credits.manualDeductDesc")}
            </p>
          </div>
          <div className="grid gap-2">
            <Label>{t("studentOps.credits.description")} *</Label>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder={t("studentOps.credits.manualDescPlaceholder")} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t("studentOps.cancel")}</Button>
          <Button onClick={submit} disabled={mutation.isPending}>
            {mutation.isPending && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
            {t("studentOps.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ── 对账弹窗 ── */
interface ReconDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  classId: string;
}

function ReconciliationDialog({ open, onOpenChange, classId }: ReconDialogProps) {
  const { t } = useLocale();
  const [page, setPage] = useState(1);

  const query = useQuery({
    queryKey: ["so-credit-recon", classId, page],
    queryFn: () =>
      creditReconciliation({
        classId: classId || undefined,
        page,
        pageSize: 20,
      }),
    enabled: open,
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("studentOps.credits.reconTitle")}</DialogTitle>
          <DialogDescription>{t("studentOps.credits.reconDesc")}</DialogDescription>
        </DialogHeader>
        <div className="max-h-[60vh] overflow-auto">
          {query.isLoading ? (
            <LoadingRow />
          ) : query.isError ? (
            <ErrorBox />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("studentOps.credits.student")}</TableHead>
                  <TableHead>{t("studentOps.credits.status")}</TableHead>
                  <TableHead>{t("studentOps.credits.sumAmount")}</TableHead>
                  <TableHead>{t("studentOps.credits.accountBalance")}</TableHead>
                  <TableHead>{t("studentOps.credits.lastBalanceAfter")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(query.data?.items || []).map((r) => (
                  <TableRow key={r.studentId}>
                    <TableCell>{r.studentId.slice(0, 8)}</TableCell>
                    <TableCell>
                      <StatusBadge
                        value={r.status}
                        label={
                          r.status === "ok"
                            ? t("studentOps.credits.reconOk")
                            : r.status === "mismatch"
                              ? t("studentOps.credits.reconMismatch")
                              : t("studentOps.credits.reconNoAccount")
                        }
                      />
                    </TableCell>
                    <TableCell>{r.sumAmount}</TableCell>
                    <TableCell>{r.accountBalance}</TableCell>
                    <TableCell>{r.lastBalanceAfter ?? "—"}</TableCell>
                  </TableRow>
                ))}
                {(query.data?.items || []).length === 0 && (
                  <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground">{t("studentOps.empty")}</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </div>
        {query.data && (
          <div className="flex items-center justify-end gap-2 pt-2">
            <Button
              variant="outline"
              size="sm"
              disabled={query.data.page <= 1}
              onClick={() => setPage(query.data.page - 1)}
            >
              {t("studentOps.prevPage")}
            </Button>
            <span className="text-xs text-muted-foreground">
              {query.data.page} / {Math.max(1, Math.ceil(query.data.total / (query.data.pageSize || 20)))}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={query.data.page >= Math.max(1, Math.ceil(query.data.total / (query.data.pageSize || 20)))}
              onClick={() => setPage(query.data.page + 1)}
            >
              {t("studentOps.nextPage")}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
