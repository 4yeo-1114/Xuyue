import { request } from "./api";

/* ══════════════════════════════════════════════
   账号总览（0924 需求三 · 平台管理员看全账号用量/额度/存储）
   GET /admin/accounts/overview
   （充值/钱包/花销 20261111 随「余额/充值/支付整体移除」删掉）
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
}

export interface AccountOverviewSummary {
  total_upload_lifetime: number;
  total_grade_lifetime: number;
  total_operations_lifetime: number;
}

export interface AccountOverviewData {
  window_days: number;
  stat_start: string;
  scope_note: string;
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
