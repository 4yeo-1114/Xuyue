import { request } from "./api";

/* ══════════════════════════════════════════════
   账号总览（0924 需求三 · 平台管理员看全账号用量/花销/充值）
   GET /admin/accounts/overview
   ══════════════════════════════════════════════ */

export interface AccountUsageOverview {
  upload_lifetime: number;
  grade_lifetime: number;
  upload_recent: number;
  grade_recent: number;
  upload_today: number;
  grade_today: number;
  total_lifetime: number;
  total_recent: number;
  total_today: number;
  storage_mb: number;
}

export interface AccountQuotaOverview {
  total_pages: number;
  used_pages: number;
  available: number;
  used_pct: number;
  today_pages: number;
  locked: boolean;
}

export interface AccountRechargeOverview {
  amount_yuan_total: number;
  pages_total: number;
  count: number;
  last_at: string | null;
}

export interface AccountCostOverview {
  grading_price_per_face: number;
  grading_cost_yuan: number;
  note: string;
}

export interface AccountWalletOverview {
  balance_yuan: number;
  total_recharged_yuan: number;
  total_consumed_yuan: number;
}

export interface AccountOverviewRow {
  user_id: string;
  display_name: string | null;
  email: string | null;
  phone: string | null;
  /** 分组（前端「文件夹」筛选）：邮箱域名；后端缺省时前端兜底为「未分组」 */
  group?: string;
  roles: string[] | null;
  teaching_subject: string | null;
  teaching_grade: string | null;
  created_at: string | null;
  usage: AccountUsageOverview;
  quota: AccountQuotaOverview;
  recharge: AccountRechargeOverview;
  cost: AccountCostOverview;
  wallet: AccountWalletOverview;
}

export interface AccountOverviewSummary {
  total_upload_lifetime: number;
  total_grade_lifetime: number;
  total_operations_lifetime: number;
  recharge_yuan_total: number;
  recharge_pages_total: number;
  grading_cost_yuan_total: number;
  wallet_balance_yuan_total: number;
  wallet_recharged_yuan_total: number;
  wallet_consumed_yuan_total: number;
}

export interface AccountOverviewData {
  window_days: number;
  stat_start: string;
  scope_note: string;
  grading_price_per_face: number;
  total_accounts: number;
  summary: AccountOverviewSummary;
  items: AccountOverviewRow[];
}

export async function fetchAdminAccountsOverview(
  days = 30,
): Promise<AccountOverviewData> {
  const params = new URLSearchParams({ days: String(days) });
  return request<AccountOverviewData>(
    `/admin/accounts/overview?${params.toString()}`,
  );
}
