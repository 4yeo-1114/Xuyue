/**
 * 合规后台 + 个人信息行权（政策完善 E03+E14）API 封装。
 *
 * 复用 `@/services/api` 的 `request<T>`（fetch + Bearer token + 自动解包 {code,message,data}）。
 * 接口契约与后端 agent 锁定：路径 / 参数 / 字段名见各函数注释，不得改动。
 */
import { request, getAuthToken } from "@/services/api";
import { API_PREFIX } from "@/config/api";

// ── 类型定义（与后端契约字段一一对应） ───────────────────

export type ConsentStatus = "granted" | "withdrawn" | "not_required";

/** GET /admin/rights/data 响应 */
export interface RightsDataResponse {
  student: {
    id: string;
    name: string;
    class_name: string;
  };
  profile: Record<string, unknown>;
  growth_count: number;
  archive_count: number;
  scores_count: number;
  consent_status: ConsentStatus;
}

/** 个人信息行权「更正」请求体 */
export interface RightsCorrectPayload {
  student_id: string;
  field: string;
  value: string;
}

/** 更正 / 删除响应（契约未固定具体字段，宽松建模） */
export interface RightsActionResult {
  ok: boolean;
  [k: string]: unknown;
}

/** GET /admin/audit/access-logs 列表项 */
export interface AccessLogItem {
  id: string;
  user_id: string;
  user_role: string;
  action: string;
  target_type: string;
  target_id: string;
  detail: string;
  created_at: string;
}

/** GET /admin/audit/access-logs 分页响应 */
export interface AccessLogPage {
  list: AccessLogItem[];
  total: number;
}

/** GET /admin/audit/report 响应 */
export interface AuditReport {
  year: number;
  total_access: number;
  action_stats: Record<string, number>;
  top_accessed: Array<{
    student_id: string;
    target_name: string;
    count: number;
  }>;
  consent_stats: {
    granted: number;
    withdrawn: number;
    not_required: number;
  };
  export_count: number;
  delete_count: number;
}

export interface ListAccessLogsParams {
  student_id?: string;
  action?: string;
  from?: string;
  to?: string;
  page?: number;
  page_size?: number;
}

// ── API 函数 ─────────────────────────────────────────────

/** GET /admin/rights/data?student_id= 查询学生个人数据汇总与授权状态 */
export async function getRightsData(
  studentId: string,
): Promise<RightsDataResponse> {
  return request<RightsDataResponse>(
    `/admin/rights/data?student_id=${encodeURIComponent(studentId)}`,
  );
}

/** GET /admin/rights/data/export?student_id= 导出学生数据 CSV（浏览器下载） */
export async function exportRightsData(studentId: string): Promise<void> {
  await downloadBlob(
    `/admin/rights/data/export?student_id=${encodeURIComponent(studentId)}`,
    `rights_data_${studentId}.csv`,
  );
}

/** PUT /admin/rights/data/correct 更正学生个人数据字段 */
export async function correctRightsData(
  body: RightsCorrectPayload,
): Promise<RightsActionResult> {
  return request<RightsActionResult>("/admin/rights/data/correct", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

/** DELETE /admin/rights/data?student_id=&confirm=true 删除/匿名化学生数据 */
export async function deleteRightsData(
  studentId: string,
): Promise<RightsActionResult> {
  return request<RightsActionResult>(
    `/admin/rights/data?student_id=${encodeURIComponent(studentId)}&confirm=true`,
    { method: "DELETE" },
  );
}

/** GET /admin/audit/access-logs 访问日志查询（分页 + 过滤） */
export async function listAccessLogs(
  params: ListAccessLogsParams = {},
): Promise<AccessLogPage> {
  const q = new URLSearchParams();
  if (params.student_id) q.set("student_id", params.student_id);
  if (params.action) q.set("action", params.action);
  if (params.from) q.set("from", params.from);
  if (params.to) q.set("to", params.to);
  if (params.page) q.set("page", String(params.page));
  if (params.page_size) q.set("page_size", String(params.page_size));
  const qs = q.toString();
  return request<AccessLogPage>(
    `/admin/audit/access-logs${qs ? `?${qs}` : ""}`,
  );
}

/** GET /admin/audit/report 年度审计报告 */
export async function getAuditReport(
  params: { year?: number; school_id?: string } = {},
): Promise<AuditReport> {
  const q = new URLSearchParams();
  if (params.year) q.set("year", String(params.year));
  if (params.school_id) q.set("school_id", params.school_id);
  const qs = q.toString();
  return request<AuditReport>(`/admin/audit/report${qs ? `?${qs}` : ""}`);
}

// ── 下载辅助 ─────────────────────────────────────────────

async function downloadBlob(endpoint: string, filename: string): Promise<void> {
  const token = await getAuthToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_PREFIX}${endpoint}`, { headers });
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
  saveBlob(blob, filename);
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

/** 将年度审计报告序列化为 CSV 文本（供客户端导出 CSV） */
export function buildReportCsv(report: AuditReport): string {
  const rows: string[] = [];
  const esc = (v: unknown): string => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };

  rows.push("year,total_access,export_count,delete_count");
  rows.push(
    [report.year, report.total_access, report.export_count, report.delete_count]
      .map(esc)
      .join(","),
  );

  rows.push("");
  rows.push("consent_granted,consent_withdrawn,consent_not_required");
  rows.push(
    [
      report.consent_stats.granted,
      report.consent_stats.withdrawn,
      report.consent_stats.not_required,
    ]
      .map(esc)
      .join(","),
  );

  const actions = Object.entries(report.action_stats ?? {});
  if (actions.length) {
    rows.push("");
    rows.push("action,count");
    for (const [action, count] of actions) {
      rows.push([action, count].map(esc).join(","));
    }
  }

  const top = report.top_accessed ?? [];
  if (top.length) {
    rows.push("");
    rows.push("student_id,target_name,count");
    for (const item of top) {
      rows.push(
        [item.student_id, item.target_name, item.count].map(esc).join(","),
      );
    }
  }

  return rows.join("\n");
}

/** 序列化 JSON 文本（供客户端导出 JSON） */
export function buildReportJson(report: AuditReport): string {
  return JSON.stringify(report, null, 2);
}
