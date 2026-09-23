import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import { Loader2, Medal, Wallet, TrendingUp, TrendingDown } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { listBadgeAwards, listCreditTransactions } from "@/services/studentOpsApi";
import { formatDateTime } from "./portfolioShared";

interface StudentIncentivePanelProps {
  studentId: string;
}

/** 学分流水类型 → 复用激励中心（studentOps）i18n key，避免重复翻译 */
function txnTypeKey(type: string): string {
  const map: Record<string, string> = {
    badge_award: "studentOps.credits.typeBadgeAward",
    manual_add: "studentOps.credits.typeManualAdd",
    redemption: "studentOps.credits.typeRedemption",
    manual_deduct: "studentOps.credits.typeManualDeduct",
    adjustment: "studentOps.credits.typeAdjustment",
    practice_approved: "studentOps.credits.typePracticeApproved",
    expire: "studentOps.credits.typeExpire",
  };
  return map[type] || type;
}

/** 日期格式化为 YYYY-MM-DD（徽章 awardDate 为纯日期串） */
function fmtDate(v?: string | null): string {
  if (!v) return "—";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return v;
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/**
 * 激励成长面板（C 域）— 只读档案视图。
 * 徽章网格（listBadgeAwards 按 studentId 过滤）+ 学分概览（最近变动，当前余额取最近一笔 balanceAfter）。
 * 不做颁章 / 兑换 / 配置等管理操作。
 */
export function StudentIncentivePanel({ studentId }: StudentIncentivePanelProps) {
  const { t } = useLocale();

  const badgeQuery = useQuery({
    queryKey: ["wuyu-badge-awards", studentId],
    queryFn: () => listBadgeAwards({ studentId, page: 1, pageSize: 100 }),
    enabled: !!studentId,
  });

  const creditQuery = useQuery({
    queryKey: ["wuyu-credit-txns", studentId],
    queryFn: () => listCreditTransactions({ studentId, page: 1, pageSize: 100 }),
    enabled: !!studentId,
  });

  const badges = badgeQuery.data?.items ?? [];

  const txns = useMemo(() => {
    const items = creditQuery.data?.items ?? [];
    return [...items].sort((a, b) => (b.createdAt ?? "").localeCompare(a.createdAt ?? ""));
  }, [creditQuery.data?.items]);

  // 当前余额 = 最近一笔流水的 balanceAfter（credit-accounts 不支持按 studentId 查询）
  const currentBalance = txns.find((x) => x.balanceAfter != null)?.balanceAfter;
  const totalEarned = txns.filter((x) => (x.amount ?? 0) > 0).reduce((s, x) => s + (x.amount ?? 0), 0);
  const totalSpent = Math.abs(txns.filter((x) => (x.amount ?? 0) < 0).reduce((s, x) => s + (x.amount ?? 0), 0));
  const recentTxns = txns.slice(0, 8);

  return (
    <div className="space-y-3">
      {/* ── 徽章 ── */}
      <Card>
        <CardHeader className="pb-3 flex-row items-start justify-between space-y-0">
          <div>
            <div className="flex items-center gap-2">
              <Medal className="w-4 h-4 text-primary" />
              <CardTitle className="text-sm font-semibold">{t("wuyu.incentive.badges")}</CardTitle>
            </div>
            <CardDescription>{t("wuyu.incentive.badgesHint")}</CardDescription>
          </div>
          {badges.length > 0 && (
            <span className="text-xs text-muted-foreground shrink-0">
              {t("wuyu.incentive.badgesCount", { count: badges.length })}
            </span>
          )}
        </CardHeader>
        <CardContent>
          {badgeQuery.isLoading ? (
            <div className="flex flex-col items-center justify-center py-10 text-muted-foreground">
              <Loader2 className="w-6 h-6 animate-spin mb-2" />
              <p className="text-sm">{t("wuyu.loading")}</p>
            </div>
          ) : badgeQuery.isError ? (
            <div className="flex flex-col items-center justify-center py-10 border border-dashed rounded-lg text-muted-foreground">
              <p className="text-sm mb-2">{t("wuyu.loadFailed")}</p>
              <Button size="sm" variant="outline" onClick={() => badgeQuery.refetch()}>
                {t("wuyu.retry")}
              </Button>
            </div>
          ) : badges.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 border border-dashed rounded-lg text-muted-foreground">
              <Medal className="w-8 h-8 opacity-30 mb-2" />
              <p className="text-sm">{t("wuyu.incentive.badgesEmpty")}</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
              {badges.map((b) => (
                <div
                  key={b.id}
                  className="rounded-lg border border-border/50 p-3 flex flex-col items-center gap-2 text-center bg-muted/20"
                >
                  <div className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center">
                    <Medal className="w-5 h-5" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-foreground truncate">{b.badgeDefinitionName}</p>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      {t("wuyu.incentive.awardedAt")}：{fmtDate(b.awardDate)}
                    </p>
                  </div>
                  {b.reason ? (
                    <p className="text-[11px] text-muted-foreground truncate w-full" title={b.reason}>
                      {b.reason}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── 学分概览 ── */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Wallet className="w-4 h-4 text-primary" />
            <CardTitle className="text-sm font-semibold">{t("wuyu.incentive.credits")}</CardTitle>
          </div>
          <CardDescription>{t("wuyu.incentive.creditsHint")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {creditQuery.isLoading ? (
            <div className="flex flex-col items-center justify-center py-10 text-muted-foreground">
              <Loader2 className="w-6 h-6 animate-spin mb-2" />
              <p className="text-sm">{t("wuyu.loading")}</p>
            </div>
          ) : creditQuery.isError ? (
            <div className="flex flex-col items-center justify-center py-10 border border-dashed rounded-lg text-muted-foreground">
              <p className="text-sm mb-2">{t("wuyu.loadFailed")}</p>
              <Button size="sm" variant="outline" onClick={() => creditQuery.refetch()}>
                {t("wuyu.retry")}
              </Button>
            </div>
          ) : txns.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 border border-dashed rounded-lg text-muted-foreground">
              <Wallet className="w-8 h-8 opacity-30 mb-2" />
              <p className="text-sm">{t("wuyu.incentive.creditsEmpty")}</p>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="rounded-lg border border-border/50 p-3 bg-muted/20">
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
                    <Wallet className="w-3.5 h-3.5" />
                    {t("wuyu.incentive.creditsBalance")}
                  </div>
                  <div className="text-xl font-bold text-primary tabular-nums">
                    {currentBalance ?? "—"}
                  </div>
                </div>
                <div className="rounded-lg border border-border/50 p-3 bg-muted/20">
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
                    <TrendingUp className="w-3.5 h-3.5 text-green-600" />
                    {t("wuyu.incentive.creditsEarned")}
                  </div>
                  <div className="text-xl font-bold text-green-600 tabular-nums">+{totalEarned}</div>
                </div>
                <div className="rounded-lg border border-border/50 p-3 bg-muted/20">
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
                    <TrendingDown className="w-3.5 h-3.5 text-destructive" />
                    {t("wuyu.incentive.creditsSpent")}
                  </div>
                  <div className="text-xl font-bold text-destructive tabular-nums">-{totalSpent}</div>
                </div>
              </div>

              <div>
                <p className="text-xs font-medium text-muted-foreground mb-2">
                  {t("wuyu.incentive.recent")}
                </p>
                <div className="space-y-1.5">
                  {recentTxns.map((tx) => (
                    <div
                      key={tx.id}
                      className="flex items-center gap-3 rounded-lg border border-border/50 px-3 py-2"
                    >
                      <span
                        className={`w-1.5 h-7 rounded-full shrink-0 ${
                          (tx.amount ?? 0) >= 0 ? "bg-emerald-500" : "bg-destructive"
                        }`}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium text-foreground">
                            {t(txnTypeKey(tx.transactionType))}
                          </span>
                          <span className="text-[11px] text-muted-foreground">
                            {formatDateTime(tx.createdAt)}
                          </span>
                        </div>
                        {tx.description ? (
                          <p className="text-[11px] text-muted-foreground truncate mt-0.5">
                            {tx.description}
                          </p>
                        ) : null}
                      </div>
                      <div className="text-right shrink-0">
                        <span
                          className={`text-sm font-bold tabular-nums ${
                            (tx.amount ?? 0) >= 0 ? "text-green-600" : "text-destructive"
                          }`}
                        >
                          {(tx.amount ?? 0) >= 0 ? "+" : ""}
                          {tx.amount}
                        </span>
                        <p className="text-[11px] text-muted-foreground">
                          {t("wuyu.incentive.balanceAfter")}：{tx.balanceAfter ?? "—"}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
