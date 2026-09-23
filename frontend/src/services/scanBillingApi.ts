import { request } from "./api";

/* ══════════════════════════════════════════════
   用量统计（对齐七牛云「用量统计」页）
   ══════════════════════════════════════════════ */

export type TrendGranularity = "day" | "week" | "month";
export type StatsDimension = "all" | "folder" | "user";
export type StatsMetric = "all" | "upload" | "grade";

/** 趋势点 */
export interface TrendPoint {
  period: string;
  label: string;
  upload: number;
  grade: number;
}

/** 用量统计汇总 */
export interface UsageSummaryStats {
  total_upload: number;
  total_grade: number;
  total: number;
  avg_daily_upload: number;
  avg_daily_grade: number;
  avg_daily_total: number;
  peak_day: string | null;
  peak_value: number;
  days: number;
}

/** 维度明细行（按文件夹 / 按教师） */
export interface DimensionRow {
  key: string;
  name: string;
  upload: number;
  grade: number;
  total: number;
}

/** 用量统计返回 */
export interface UsageStatsData {
  period: { start: string; end: string };
  granularity: TrendGranularity;
  dimension: StatsDimension;
  metric: StatsMetric;
  summary: UsageSummaryStats;
  series: TrendPoint[];
  breakdown: DimensionRow[];
}

export async function fetchUsageStats(params: {
  start_date: string;
  end_date: string;
  granularity?: TrendGranularity;
  dimension?: StatsDimension;
  metric?: StatsMetric;
  user_id?: string;
}): Promise<UsageStatsData> {
  const search = new URLSearchParams({
    start_date: params.start_date,
    end_date: params.end_date,
    granularity: params.granularity || "day",
    dimension: params.dimension || "all",
    metric: params.metric || "all",
  });
  if (params.user_id) search.set("user_id", params.user_id);
  return request<UsageStatsData>(`/scan-billing/usage-stats?${search}`);
}

/* ══════════════════════════════════════════════
   计费用量（对齐七牛云计费模型）
   ══════════════════════════════════════════════ */

/** 累进阶梯档位 */
export interface PriceTier {
  up_to: number | null;
  price: number;
}

/** 计费项规则（GET /scan-billing/pricing） */
export interface PricingItem {
  key: string;
  label: string;
  category: string;
  unit: string;
  basis: "monthly_avg" | "cumulative";
  basis_label: string;
  round_up: boolean;
  round_up_label: string;
  free_quota: number;
  resource_pack: number;
  tiers: PriceTier[];
}

export interface PricingData {
  currency: string;
  note: string;
  deduction_order: string[];
  deduction_order_label: string;
  items: PricingItem[];
}

export async function fetchPricing(): Promise<PricingData> {
  return request<PricingData>("/scan-billing/pricing");
}

/** 阶梯分段明细 */
export interface FeeSegment {
  from: number;
  to: number | null;
  quantity: number;
  price: number;
  amount: number;
}

/** 单个计费项的计算结果 */
export interface BillingItem {
  key: string;
  label: string;
  category: string;
  unit: string;
  basis: string;
  raw_quantity: number;
  billed_units: number;
  free_quota: number;
  resource_pack: number;
  billable_units: number;
  segments: FeeSegment[];
  amount: number;
  /** 存储类按月折算系数 */
  proration?: number;
}

/** 按量计费预估 / 月账单 */
export interface BillingResult {
  currency: string;
  note: string;
  deduction_order: string[];
  items: BillingItem[];
  total_amount: number;
  period: { start: string; end: string };
  period_label: string;
  storage: { avg_gb: number; elapsed_days: number; days_in_month: number };
  usage: { upload: number; grade: number };
  is_estimate: boolean;
  /** 仅 /bill 返回 */
  month?: string;
  settled?: boolean;
  settle_note?: string;
}

/** 按量计费预估（本月至今） */
export async function fetchEstimate(params?: {
  user_id?: string;
}): Promise<BillingResult> {
  const search = new URLSearchParams();
  if (params?.user_id) search.set("user_id", params.user_id);
  const q = search.toString();
  return request<BillingResult>(`/scan-billing/estimate${q ? `?${q}` : ""}`);
}

/** 月度账单（month 为 YYYY-MM，缺省取上月） */
export async function fetchBill(params?: {
  month?: string;
  user_id?: string;
}): Promise<BillingResult> {
  const search = new URLSearchParams();
  if (params?.month) search.set("month", params.month);
  if (params?.user_id) search.set("user_id", params.user_id);
  const q = search.toString();
  return request<BillingResult>(`/scan-billing/bill${q ? `?${q}` : ""}`);
}

/* ══════════════════════════════════════════════
   辅助统计（趋势 / 明细 / 排名）
   ══════════════════════════════════════════════ */

/** 文件夹消耗明细 */
export interface BreakdownItem {
  folder_safe: string;
  folder_name: string;
  upload: number;
  grade: number;
  total: number;
}

export async function fetchBreakdown(params?: {
  days?: number;
  user_id?: string;
  sort_by?: "upload" | "grade" | "total";
}): Promise<BreakdownItem[]> {
  const search = new URLSearchParams();
  if (params?.days) search.set("days", String(params.days));
  if (params?.user_id) search.set("user_id", params.user_id);
  if (params?.sort_by) search.set("sort_by", params.sort_by);
  const q = search.toString();
  return request<BreakdownItem[]>(`/scan-billing/breakdown${q ? `?${q}` : ""}`);
}

/** 教师排名 */
export interface UserRankingItem {
  rank: number;
  user_id: string;
  display_name: string | null;
  email: string | null;
  upload: number;
  grade: number;
  total: number;
}

export async function fetchUserRanking(params?: {
  days?: number;
  limit?: number;
}): Promise<UserRankingItem[]> {
  const search = new URLSearchParams();
  if (params?.days) search.set("days", String(params.days));
  if (params?.limit) search.set("limit", String(params.limit));
  const q = search.toString();
  return request<UserRankingItem[]>(`/scan-billing/user-ranking${q ? `?${q}` : ""}`);
}
