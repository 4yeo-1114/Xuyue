import { request } from "./api";

/* ══════════════════════════════════════════════
   口径 B · 个人账本（独立老师支付 Phase 0，P0-6 只读投影）
   ══════════════════════════════════════════════

   ⛔ 与 `scanBillingApi.ts`（口径 A · 平台成本核算）**物理分离**：
   两者数据源不同（这里 = payment_accounts / ledger_entries / usage_events），
   ⛔ 不可合并、不可互相换算。见 docs/payment/payment-design.md §1、§7.3。

   ⚠️ 端点前缀：`request()` 内部已拼 `API_PREFIX = /api/v1`（services/api.ts:51）
   ⇒ ⛔ 不要自己再写 `/api/v1`。
   ⚠️ 越权：后端 `routers/payment.py` **不接 user_id 入参**（一律用 JWT 身份）
   ⇒ 本模块也不提供 user_id 参数。
   ⚠️ 金额单位一律是**分**（fen），展示时 ÷100；⛔ 不做四舍五入到元。
   ══════════════════════════════════════════════ */

/** 我的账户余额与状态（GET /payment/account，金额单位：分） */
export interface PaymentAccount {
  user_id: string;
  /** 当前余额（分） */
  balance_fen: number;
  /** 累计入账（分） */
  total_recharged_fen: number;
  /** 累计消耗（分） */
  total_consumed_fen: number;
  status: string;
  created_at: string | null;
  updated_at: string | null;
}

/** 一条资金流水（分） */
export interface LedgerEntry {
  id: string;
  /** 分录类型（如 grant / consume / refund） */
  entry_type: string;
  /** 金额（分），正数入账、负数出账 */
  amount_fen: number;
  /** 记账后余额（分） */
  balance_after_fen: number;
  description: string | null;
  created_at: string | null;
}

/** 流水分页（GET /payment/ledger） */
export interface LedgerPage {
  total: number;
  page: number;
  page_size: number;
  items: LedgerEntry[];
}

/** 口径 B 用量明细行（GET /payment/usage） */
export interface UsageItem {
  kind: string;
  folder_safe: string;
  subject_key: string;
  net: number;
}

/** 口径 B 用量按维度聚合行 */
export interface UsageFolderItem {
  kind: string;
  folder_safe: string;
  net: number;
}

/**
 * 我的用量（**口径 B**：`usage_events` 净额，⛔ 非口径 A 的 `grading_daily_stats`）。
 *
 * ⚠️ 与「扫描消耗 / 用量汇总」（口径 A · 平台成本）**不是同一本账**，
 * 数值不可比、不可相加 —— 页面必须显式标注（设计稿 §9 P0-9）。
 */
export interface PaymentUsage {
  total_grade: number;
  total_upload: number;
  folders: UsageFolderItem[];
  recent: UsageItem[];
}

/** 我的余额（分）+ 状态。账户由后端惰性创建（§8.1），故本调用总会成功返回账户。 */
export async function fetchPaymentAccount(): Promise<PaymentAccount> {
  return request<PaymentAccount>("/payment/account");
}

/** 我的资金流水（分页，后端已按 created_at 倒序）。page 从 1 起，page_size 上限 200。 */
export async function fetchPaymentLedger(params?: {
  page?: number;
  page_size?: number;
  entry_type?: string;
}): Promise<LedgerPage> {
  const search = new URLSearchParams();
  if (params?.page !== undefined) search.set("page", String(params.page));
  if (params?.page_size !== undefined)
    search.set("page_size", String(params.page_size));
  if (params?.entry_type) search.set("entry_type", params.entry_type);
  const q = search.toString();
  return request<LedgerPage>(`/payment/ledger${q ? `?${q}` : ""}`);
}

/** 我的用量（口径 B，净额）。limit 为近期事件条数上限，上限 200。 */
export async function fetchPaymentUsage(params?: {
  limit?: number;
}): Promise<PaymentUsage> {
  const search = new URLSearchParams();
  if (params?.limit !== undefined) search.set("limit", String(params.limit));
  const q = search.toString();
  return request<PaymentUsage>(`/payment/usage${q ? `?${q}` : ""}`);
}

/** 支付下单结果（POST /payment/orders） */
export interface PaymentOrderCreateResult {
  order_id: string;
  channel: string;
  amount_fen: number;
  status: string;
  payee_entity_id: string | null;
  pay_params: Record<string, unknown>;
}

/**
 * 下单充值（金额单位：分）。返回通道支付参数，供客户端拉起收银台。
 *
 * ⚠️ 通道凭据未配置时后端返回 501（ChannelNotConfiguredError），
 * 前端据此提示「支付通道尚未配置，请联系管理员手动充值」。
 */
export async function createPaymentOrder(
  amount_fen: number,
  channel: string,
): Promise<PaymentOrderCreateResult> {
  return request<PaymentOrderCreateResult>("/payment/orders", {
    method: "POST",
    body: JSON.stringify({ amount_fen, channel }),
  });
}
