/**
 * 五育成长画像域（A 域）API 封装。
 *
 * 复用 `@/services/api` 的 `request<T>`（fetch + Bearer token + 自动解包 {code,message,data}）。
 * 类型均内联定义，以匹配后端 `/api/v1/portfolio/*`（见 docs/contracts/10-portfolio-contract.md §6）。
 */
import { request, getAuthToken } from "@/services/api";
import { API_BASE_URL, API_PREFIX } from "@/config/api";

// ── 枚举与基础类型 ───────────────────────────────────────

export type WuyuDimension =
  "moral" | "intellectual" | "physical" | "aesthetic" | "labor" | "ai_literacy";
export type WuyuDataStatus = "has_data" | "insufficient";
export type WuyuStatusMap = Record<string, WuyuDataStatus>;
export type WuyuCountMap = Record<string, { count: number }>;

export interface IntellectualAutoEntry {
  count: number;
  points: number;
  weight?: number;
}
export type IntellectualAutoMap = Record<string, IntellectualAutoEntry>;

export interface IntellectualEvent {
  event_type: string;
  points: number;
  occurred_at?: string | null;
  decay_weight?: number;
}

export interface TrendPoint {
  month: string;
  points: number;
  events: number;
}

export interface Baseline {
  percentile: Record<string, number | null>;
  tier: Record<string, string | null>;
  z_score: Record<string, number | null>;
  composite: Record<string, number | null>;
  rank: Record<string, number | null>;
  n: Record<string, number | null>;
}

/** GET /portfolio 响应 */
export interface PortfolioResponse {
  student_id: string;
  name: string;
  class_id: string;
  grade?: string | null;
  base_points: number;
  dimensions: Record<string, number>;
  total_growth_point: number;
  activity_track: WuyuCountMap;
  data_status: WuyuStatusMap;
  intellectual_auto: IntellectualAutoMap;
  intellectual_events: IntellectualEvent[];
  percentile?: Record<string, number | null>;
  tier?: Record<string, string | null>;
  z_score?: Record<string, number | null>;
  composite?: Record<string, number | null>;
  rank?: Record<string, number | null>;
  n?: Record<string, number | null>;
  trend?: TrendPoint[];
}

/** 学校二级指标字典定义 */
export interface IndicatorDef {
  id: string;
  dimension: WuyuDimension;
  code: string;
  name: string;
  description?: string | null;
  sort_order: number;
  is_active: boolean;
  school_id?: string | null;
}

/** 成长流水单条 */
export interface GrowthRecord {
  id: string;
  student_id: string;
  class_id: string;
  dimension: WuyuDimension;
  source_type: string;
  source_id?: string | null;
  growth_point: number;
  evidence?: Record<string, unknown> | null;
  note?: string | null;
  created_by?: string | null;
  occurred_at?: string | null;
  created_at?: string | null;
  indicator_id?: string | null;
  indicator_name?: string | null;
}

export interface GrowthRecordPage {
  rows: GrowthRecord[];
  total: number;
  page: number;
  pageSize: number;
}

export interface GrowthRecordCreatePayload {
  dimension: WuyuDimension;
  growth_point: number;
  source_id?: string | null;
  evidence?: Record<string, unknown> | null;
  note?: string | null;
  indicator_id?: string | null;
}

/** 学期报告维度明细 */
export interface ReportDimensionMeta {
  growth_records: number;
  auto_points: number;
  total: number;
  detail?: Record<string, number>;
  auto_detail?: IntellectualAutoMap;
}

export type ReportDimensions = Record<string, ReportDimensionMeta>;
export type SourceStats = Record<string, { points: number; count: number }>;

export interface Milestone {
  event_type: string;
  name: string;
  points?: number | null;
  occurred_at?: string | null;
  decay_weight?: number | null;
}

export interface CommentSection {
  status: "absent" | "pending" | "confirmed" | "ai_failed";
  content?: string | null;
  is_draft?: boolean;
  ai_model?: string | null;
  gate_flagged?: boolean;
  comment_id?: string;
  ai_content?: string | null;
  confirmed_content?: string | null;
  confirmed_by?: string | null;
  confirmed_at?: string | null;
  created_by?: string | null;
  created_at?: string | null;
}

/** 学分银行汇总（report dict 的 credit 键；无账户时 balance/total_earned/total_spent 为 null） */
export interface ReportCredit {
  balance: number | null;
  total_earned: number | null;
  total_spent: number | null;
  term_earned: number;
  term_spent: number;
  term_net: number;
  txn_count: number;
  by_type: Record<string, number>;
}

/** GET /report 响应 */
export interface ReportResponse {
  student_id: string;
  name: string;
  class_id: string;
  grade?: string | null;
  term: string;
  date_from: string;
  date_to: string;
  base_points: number;
  dimensions: ReportDimensions;
  source_stats: SourceStats;
  growth_records_count: number;
  total_growth_point: number;
  raw_total: number;
  data_status: WuyuStatusMap;
  data_sources_missing: Record<string, string[]>;
  baseline: Baseline | null;
  milestones: Milestone[];
  trend: TrendPoint[];
  assessment_profile?: Record<string, unknown>;
  comment: CommentSection;
  from_snapshot?: boolean;
  version?: number | null;
  credit?: ReportCredit | null;
}

/** GET /classes/{class_id} 班级总览学生项 */
export interface ClassPortfolioStudent {
  student_id: string;
  name: string;
  student_number?: string | null;
  dimensions: Record<string, number>;
  total_growth_point: number;
  activity_track: WuyuCountMap;
  data_status: WuyuStatusMap;
  percentile: Record<string, number | null>;
  tier: Record<string, string | null>;
  z_score: Record<string, number | null>;
  composite: Record<string, number | null>;
  rank: Record<string, number | null>;
  n: Record<string, number | null>;
}

export interface ClassOverview {
  class_id: string;
  school_id?: string;
  class_name?: string | null;
  grade?: string | null;
  student_count: number;
  sorted_by?: string;
  students: ClassPortfolioStudent[];
  averages: Record<string, number>;
  tier_distribution: Record<string, number>;
}

// ── API 函数 ─────────────────────────────────────────────

/** §6.1 学生五育画像（trend=true 时返回月度趋势） */
export async function getPortfolio(
  studentId: string,
  trend = false,
): Promise<PortfolioResponse> {
  return request<PortfolioResponse>(
    `/portfolio/students/${encodeURIComponent(studentId)}${trend ? "?trend=true" : ""}`,
  );
}

/** §6.2 成长记录列表（分页 + 可选维度/日期过滤） */
export async function listGrowthRecords(
  studentId: string,
  params: {
    dimension?: WuyuDimension;
    date_from?: string;
    date_to?: string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<GrowthRecordPage> {
  const q = new URLSearchParams();
  if (params.dimension) q.set("dimension", params.dimension);
  if (params.date_from) q.set("date_from", params.date_from);
  if (params.date_to) q.set("date_to", params.date_to);
  if (params.page) q.set("page", String(params.page));
  if (params.pageSize) q.set("pageSize", String(params.pageSize));
  const qs = q.toString();
  return request<GrowthRecordPage>(
    `/portfolio/students/${encodeURIComponent(studentId)}/growth-records${qs ? `?${qs}` : ""}`,
  );
}

/** §6.2 学校二级指标字典列表（按维度过滤，可含停用项） */
export async function listIndicators(
  dimension?: WuyuDimension,
  options: { includeInactive?: boolean } = {},
): Promise<IndicatorDef[]> {
  const q = new URLSearchParams();
  if (dimension) q.set("dimension", dimension);
  if (options.includeInactive) q.set("include_inactive", "true");
  const qs = q.toString();
  return request<IndicatorDef[]>(`/portfolio/indicators${qs ? `?${qs}` : ""}`);
}

/** §6.3 手动录入成长记录（source_type=manual，后端幂等） */
export async function createGrowthRecord(
  studentId: string,
  body: GrowthRecordCreatePayload,
): Promise<GrowthRecord> {
  return request<GrowthRecord>(
    `/portfolio/students/${encodeURIComponent(studentId)}/growth-records`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

/**
 * 删除一条成长记录（仅手动录入记录，后端已实现）。
 *
 * 端点：`DELETE /portfolio/students/{student_id}/growth-records/{record_id}`
 * 后端返回 { code, message, data: { id, deleted: true } }，经 request<T> 解包后返回 { id, deleted }；
 * 记录不存在时后端返回 404。
 */
export async function deleteGrowthRecord(
  studentId: string,
  recordId: string,
): Promise<{ id: string; deleted: boolean }> {
  return request<{ id: string; deleted: boolean }>(
    `/portfolio/students/${encodeURIComponent(studentId)}/growth-records/${encodeURIComponent(recordId)}`,
    { method: "DELETE" },
  );
}

/** §6.4 学期报告（快照优先 → 实时聚合） */
export async function getReport(
  studentId: string,
  term: string,
  version?: number,
): Promise<ReportResponse> {
  const q = new URLSearchParams({ term });
  if (version) q.set("version", String(version));
  return request<ReportResponse>(
    `/portfolio/students/${encodeURIComponent(studentId)}/report?${q.toString()}`,
  );
}

/** §6.4b 月度报告（实时聚合，term=YYYY-MM，返回结构与 /report 一致） */
export async function getMonthlyReport(
  studentId: string,
  month: string,
): Promise<ReportResponse> {
  const q = new URLSearchParams({ month });
  return request<ReportResponse>(
    `/portfolio/students/${encodeURIComponent(studentId)}/monthly-report?${q.toString()}`,
  );
}

/** §6.5 冻结学期报告为快照（幂等新增版本） */
export async function freezeReport(
  studentId: string,
  term: string,
): Promise<ReportResponse> {
  return request<ReportResponse>(
    `/portfolio/students/${encodeURIComponent(studentId)}/report/freeze`,
    { method: "POST", body: JSON.stringify({ term }) },
  );
}

/** §6.6 查看 AI 评语 */
export async function getComment(
  studentId: string,
  term: string,
): Promise<CommentSection> {
  return request<CommentSection>(
    `/portfolio/students/${encodeURIComponent(studentId)}/report/comment?term=${encodeURIComponent(term)}`,
  );
}

/** §6.7 生成 AI 评语（含禁词闸门 fail-closed） */
export async function generateComment(
  studentId: string,
  term: string,
): Promise<CommentSection> {
  return request<CommentSection>(
    `/portfolio/students/${encodeURIComponent(studentId)}/report/comment/generate`,
    { method: "POST", body: JSON.stringify({ term }) },
  );
}

/** §6.8 确认评语（可修改文本；含禁词会 422 拒绝） */
export async function confirmComment(
  studentId: string,
  term: string,
  content?: string,
): Promise<CommentSection> {
  return request<CommentSection>(
    `/portfolio/students/${encodeURIComponent(studentId)}/report/comment/confirm`,
    {
      method: "POST",
      body: JSON.stringify({ term, content: content ?? null }),
    },
  );
}

/** §6.9 下载学期报告 PDF（二进制 blob，不走 request 解包） */
export async function downloadReportPdf(
  studentId: string,
  term: string,
  version?: number,
): Promise<{ blob: Blob; filename: string }> {
  const token = await getAuthToken();
  const q = new URLSearchParams({ term });
  if (version) q.set("version", String(version));
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(
    `${API_PREFIX}/portfolio/students/${encodeURIComponent(studentId)}/report/pdf?${q.toString()}`,
    { headers },
  );
  if (!res.ok) {
    let msg = `下载失败: ${res.status}`;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : msg;
    } catch {
      // ignore
    }
    throw new Error(msg);
  }
  const blob = await res.blob();
  // 解析 Content-Disposition filename，兼容 RFC 5987 `filename*=UTF-8''...`
  let filename = `学期成长报告_${term}.pdf`;
  const cd = res.headers.get("Content-Disposition") || "";
  const star = cd.match(/filename\*=UTF-8''([^;]+)/i);
  if (star) {
    try {
      filename = decodeURIComponent(star[1]);
    } catch {
      // keep default
    }
  } else {
    const plain = cd.match(/filename="?([^";]+)"?/i);
    if (plain) filename = plain[1];
  }
  return { blob, filename };
}

/** §6.9b 下载成长册 PDF（二进制 blob，不走 request 解包；term 缺省时后端按全量窗口处理） */
export async function downloadGrowthAlbumPdf(
  studentId: string,
  term?: string,
): Promise<{ blob: Blob; filename: string }> {
  const token = await getAuthToken();
  const q = new URLSearchParams();
  if (term) q.set("term", term);
  const qs = q.toString();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(
    `${API_PREFIX}/portfolio/students/${encodeURIComponent(studentId)}/growth-album/pdf${qs ? `?${qs}` : ""}`,
    { headers },
  );
  if (!res.ok) {
    let msg = `下载失败: ${res.status}`;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : msg;
    } catch {
      // ignore
    }
    throw new Error(msg);
  }
  const blob = await res.blob();
  // 解析 Content-Disposition filename，兼容 RFC 5987 `filename*=UTF-8''...`
  let filename = term ? `成长册_${term}.pdf` : "成长册.pdf";
  const cd = res.headers.get("Content-Disposition") || "";
  const star = cd.match(/filename\*=UTF-8''([^;]+)/i);
  if (star) {
    try {
      filename = decodeURIComponent(star[1]);
    } catch {
      // keep default
    }
  } else {
    const plain = cd.match(/filename="?([^";]+)"?/i);
    if (plain) filename = plain[1];
  }
  return { blob, filename };
}

/** §6.10 班级画像总览（sort: total / name） */
export async function getClassOverview(
  classId: string,
  sort: "total" | "name" = "total",
): Promise<ClassOverview> {
  return request<ClassOverview>(
    `/portfolio/classes/${encodeURIComponent(classId)}?sort=${sort}`,
  );
}

/** 学生成长印记（动态相册）单条 */
export interface MemoryItem {
  id: string;
  student_id: string;
  class_id?: string;
  image_path: string;
  download_url?: string | null;
  thumb_url?: string | null;
  caption?: string | null;
  source_type?: string;
  created_by?: string | null;
  created_at?: string | null;
}

/** §6.11 学生成长印记列表（按时间倒序） */
export async function listMemories(studentId: string): Promise<MemoryItem[]> {
  return request<MemoryItem[]>(
    `/portfolio/students/${encodeURIComponent(studentId)}/memories`,
  );
}

/** §6.11 上传成长照片（multipart/form-data：file + caption） */
export async function uploadMemory(
  studentId: string,
  file: File,
  caption?: string,
): Promise<MemoryItem> {
  const formData = new FormData();
  formData.append("file", file);
  if (caption) formData.append("caption", caption);

  const token = await getAuthToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(
    `${API_PREFIX}/portfolio/students/${encodeURIComponent(studentId)}/memories`,
    { method: "POST", headers, body: formData },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "上传失败");
  }
  const json = await res.json();
  return json.data as MemoryItem;
}

/** §6.11 删除成长照片 */
export async function deleteMemory(
  studentId: string,
  memoryId: string,
): Promise<unknown> {
  return request<unknown>(
    `/portfolio/students/${encodeURIComponent(studentId)}/memories/${encodeURIComponent(memoryId)}`,
    { method: "DELETE" },
  );
}

/** 将后端生成的下载直链拼成可访问的完整 URL */
export function resolveMemoryUrl(downloadUrl?: string | null): string {
  if (!downloadUrl) return "";
  if (/^https?:\/\//.test(downloadUrl)) return downloadUrl;
  return `${API_BASE_URL}${downloadUrl}`;
}

/** 触发浏览器下载 Blob */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ── 综评档案 dossier（G3 聚合只读） ──────────────────────

/** 综评档案中的成长记录条目（dossier.growth_records[]） */
export interface DossierGrowthRecord {
  id?: string;
  dimension?: WuyuDimension;
  growth_points?: number;
  indicator_name?: string | null;
  note?: string | null;
  occurred_at?: string | null;
  evidence?: Record<string, unknown> | null;
}

/** 综评档案中的成长印记照片条目（dossier.memories[]） */
export interface DossierMemoryItem {
  id?: string;
  image?: string | null;
  image_path?: string | null;
  url?: string | null;
  download_url?: string | null;
  thumb_url?: string | null;
  caption?: string | null;
  created_at?: string | null;
}

/** 综评档案中的奖章条目（dossier.badges[]） */
export interface DossierBadgeItem {
  id?: string;
  name?: string;
  badge_name?: string;
  points?: number;
  points_awarded?: number;
  awarded_at?: string | null;
  award_date?: string | null;
  reason?: string | null;
}

/** 综评档案中的学分流水条目（dossier.credit_transactions[]） */
export interface DossierCreditTransaction {
  id?: string;
  amount: number;
  transaction_type?: string;
  description?: string | null;
  balance_after?: number | null;
  created_at?: string | null;
}

/** 综评档案中的测评结果条目（dossier.assessment_results[]） */
export interface DossierAssessmentResult {
  id?: string;
  definition_name?: string;
  dimension_percents?: Record<string, number>;
  labels?: string[];
  created_at?: string | null;
}

/** 成档状态（遴选/公示/成档），未成档时为 null */
export interface DossierArchiveStatus {
  status: string;
  phase?: string;
  submitted_at?: string | null;
  archived_at?: string | null;
  decided_at?: string | null;
  [key: string]: unknown;
}

/** GET /portfolio/students/{student_id}/dossier 响应 */
export interface DossierResponse {
  student_id: string;
  name: string;
  class_id: string;
  class_name?: string | null;
  grade?: string | null;
  term: string;
  /** 学期报告全量（compute_report_for_student），可能为 null */
  report: ReportResponse | null;
  growth_records: DossierGrowthRecord[];
  memories: DossierMemoryItem[];
  badges: DossierBadgeItem[];
  credit_transactions: DossierCreditTransaction[];
  assessment_results: DossierAssessmentResult[];
  archive_status: DossierArchiveStatus | null;
}

/**
 * §6.12 综评档案聚合（学生完整档案，只读展示）。
 * term 缺省时后端按当前学期聚合。
 */
export async function getDossier(
  studentId: string,
  term?: string,
): Promise<DossierResponse> {
  const q = term ? `?term=${encodeURIComponent(term)}` : "";
  return request<DossierResponse>(
    `/portfolio/students/${encodeURIComponent(studentId)}/dossier${q}`,
  );
}

// ── 家长端（孩子五育画像）──────────────────────────

/** 家长绑定孩子列表项 */
export interface ParentStudent {
  student_id: string;
  name: string;
  class_id: string;
  class_name?: string | null;
  grade?: string | null;
}

/** 家长端概览中的成长记录条目（复用 _growth_record_dict 口径） */
export interface ParentGrowthRecord {
  id: string;
  dimension: WuyuDimension;
  source_type: string;
  growth_point: number;
  note?: string | null;
  indicator_name?: string | null;
  occurred_at?: string | null;
}

/** 家长端学期报告摘要 */
export interface ParentReportSummary {
  term?: string | null;
  total_growth_point?: number | null;
}

/** GET /portfolio/parent/students/{id}/overview 响应 */
export interface ParentOverview {
  student_id: string;
  name: string;
  class_id: string;
  class_name?: string | null;
  grade?: string | null;
  /** 无数据维度为 null（前端据此显示「数据不足」） */
  dimensions: Record<string, number | null>;
  total_growth_point: number;
  recent_growth_records: ParentGrowthRecord[];
  report: ParentReportSummary | null;
}

/** §6.10b 家长查看已绑定孩子列表（家长身份以 parent_students 绑定表为准） */
export async function listParentStudents(): Promise<ParentStudent[]> {
  return request<ParentStudent[]>("/portfolio/parent/students");
}

/** §6.10b 家长查看绑定孩子五育画像概览（recent=最近成长记录条数） */
export async function getParentStudentOverview(
  studentId: string,
  recent = 10,
): Promise<ParentOverview> {
  return request<ParentOverview>(
    `/portfolio/parent/students/${encodeURIComponent(studentId)}/overview?recent=${recent}`,
  );
}
