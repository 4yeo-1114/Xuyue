import { request } from "./api";

/* ══════════════════════════════════════════════
   批改额度 / 充值（0924 需求）
   ══════════════════════════════════════════════ */

/* 后端接口就绪前先跑 mock；接好后把 USE_MOCK 改成 false 即切真实接口。 */
const USE_MOCK = false;

/** 账号额度（GET /quota/me） */
export interface QuotaUsage {
  total_pages: number; // 累计充值总面数
  used_pages: number; // 已用面数
  available: number; // 剩余可用（total - used，可为负）
  used_pct: number; // 已用占总量的百分比（0-100+）
  locked: boolean; // 是否触发 105% 硬停
  today_pages: number; // 当天已批改页数
}

/** 充值档位（GET /quota/tiers） */
export interface QuotaTier {
  amount_yuan: number;
  base_pages: number;
  bonus_pages: number;
  total_pages: number;
}

/** 管理端账号额度总览（GET /admin/quota/list） */
export interface QuotaAccountRow {
  user_id: string;
  display_name: string | null;
  email: string | null;
  roles: string[] | null;
  total_pages: number;
  used_pages: number;
  today_pages: number;
  locked: boolean;
}

/** 充值结果（POST /admin/quota/recharge） */
export interface RechargeResult {
  ok: boolean;
  base_pages: number;
  bonus_pages: number;
  total_pages: number;
  new_total: number;
}

/** 充值流水（GET /admin/quota/recharge-logs） */
export interface QuotaRechargeLog {
  id: string;
  user_id: string;
  user_name: string | null;
  amount_yuan: number;
  base_pages: number;
  bonus_pages: number;
  total_pages: number;
  operator_name: string | null;
  created_at: string | null;
}

/** 充值流水分页结果 */
export interface QuotaRechargeLogPage {
  total: number;
  page: number;
  page_size: number;
  items: QuotaRechargeLog[];
}

/* ── mock 数据（前端联调用，后端就绪后随 USE_MOCK 一并删除） ── */

const MOCK_TIERS: QuotaTier[] = [
  { amount_yuan: 100, base_pages: 300, bonus_pages: 0, total_pages: 300 },
  { amount_yuan: 500, base_pages: 1500, bonus_pages: 100, total_pages: 1600 },
  { amount_yuan: 1000, base_pages: 3000, bonus_pages: 300, total_pages: 3300 },
  { amount_yuan: 2000, base_pages: 6000, bonus_pages: 1500, total_pages: 7500 },
  { amount_yuan: 5000, base_pages: 15000, bonus_pages: 5000, total_pages: 20000 },
];

let mockMyQuota: QuotaUsage = {
  total_pages: 1600,
  used_pages: 820,
  available: 780,
  used_pct: 51.25,
  locked: false,
  today_pages: 36,
};

let mockAccounts: QuotaAccountRow[] = [
  { user_id: "u1", display_name: "测试老师01", email: "t01@test.cn", roles: ["班主任"], total_pages: 2000, used_pages: 0, today_pages: 0, locked: false },
  { user_id: "u2", display_name: "测试老师02", email: "t02@test.cn", roles: ["班主任"], total_pages: 2000, used_pages: 120, today_pages: 12, locked: false },
  { user_id: "u3", display_name: "测试老师03", email: "t03@test.cn", roles: ["班主任"], total_pages: 2000, used_pages: 2100, today_pages: 40, locked: true },
  { user_id: "u4", display_name: "张三", email: "zhang@demo.cn", roles: ["班主任"], total_pages: 1600, used_pages: 820, today_pages: 36, locked: false },
];

const _delay = (ms = 200) => new Promise((r) => setTimeout(r, ms));

export async function fetchMyQuota(): Promise<QuotaUsage> {
  if (USE_MOCK) {
    await _delay();
    return { ...mockMyQuota };
  }
  return request<QuotaUsage>("/quota/me");
}

export async function fetchQuotaTiers(): Promise<QuotaTier[]> {
  if (USE_MOCK) {
    await _delay();
    return [...MOCK_TIERS];
  }
  return request<QuotaTier[]>("/quota/tiers");
}

export async function fetchQuotaList(): Promise<QuotaAccountRow[]> {
  if (USE_MOCK) {
    await _delay();
    return mockAccounts.map((a) => ({ ...a }));
  }
  return request<QuotaAccountRow[]>("/admin/quota/list");
}

export async function rechargeQuota(
  userId: string,
  amountYuan: number,
): Promise<RechargeResult> {
  if (USE_MOCK) {
    await _delay(400);
    const tier = MOCK_TIERS.find((t) => t.amount_yuan === amountYuan);
    if (!tier) {
      throw new Error("未找到对应充值档位");
    }
    const row = mockAccounts.find((a) => a.user_id === userId);
    if (row) {
      row.total_pages += tier.total_pages;
      row.locked = false;
    }
    return {
      ok: true,
      base_pages: tier.base_pages,
      bonus_pages: tier.bonus_pages,
      total_pages: tier.total_pages,
      new_total: row ? row.total_pages : tier.total_pages,
    };
  }
  return request<RechargeResult>("/admin/quota/recharge", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, amount_yuan: amountYuan }),
  });
}

export async function fetchQuotaRechargeLogs(
  page = 1,
  pageSize = 50,
  filterUserId?: string,
): Promise<QuotaRechargeLogPage> {
  if (USE_MOCK) {
    await _delay();
    return { total: 0, page, page_size: pageSize, items: [] };
  }
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (filterUserId) params.set("filter_user_id", filterUserId);
  return request<QuotaRechargeLogPage>(
    `/admin/quota/recharge-logs?${params.toString()}`,
  );
}
