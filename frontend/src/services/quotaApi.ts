import { request } from "./api";

/* ══════════════════════════════════════════════
   批改额度（0924 需求；充值/档位/流水 20261111 随「余额/充值/支付整体移除」删掉）
   ══════════════════════════════════════════════ */

/* 后端接口就绪前先跑 mock；接好后把 USE_MOCK 改成 false 即切真实接口。 */
const USE_MOCK = false;

/** 账号额度（GET /quota/me） */
export interface QuotaUsage {
  total_pages: number; // 额度总面数（0 = 无限额）
  used_pages: number; // 已用面数
  available: number; // 剩余可用（total - used，可为负）
  used_pct: number; // 已用占总量的百分比（0-100+）
  locked: boolean; // 是否触发 105% 硬停
  today_pages: number; // 当天已批改页数
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

/* ── mock 数据（前端联调用，后端就绪后随 USE_MOCK 一并删除） ── */

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

export async function fetchQuotaList(): Promise<QuotaAccountRow[]> {
  if (USE_MOCK) {
    await _delay();
    return mockAccounts.map((a) => ({ ...a }));
  }
  return request<QuotaAccountRow[]>("/admin/quota/list");
}
