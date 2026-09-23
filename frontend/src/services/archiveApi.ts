/**
 * 综评档案·遴选→公示→成档 API 封装（挂载 /api/v1/portfolio/archive）。
 *
 * 状态流：draft(待遴选) → selected(已遴选) → publicity(公示中) → archived(已存档)。
 * 公示中可撤回(→draft)；公示期默认 7 天（publicity_end_at = 开启 + 7 天）。
 * 复用 `@/services/api` 的 `request<T>`（fetch + Bearer token + 自动解包 {code,message,data}）。
 */
import { request } from "@/services/api";

/** 综评档案状态 */
export type ArchiveStatus = "draft" | "selected" | "publicity" | "archived";

/** 综评档案单条 */
export interface EvaluationArchive {
  id: string;
  class_id: string;
  student_id: string;
  student_name?: string | null;
  student_number?: string | null;
  term: string;
  status: ArchiveStatus;
  selected_at?: string | null;
  publicity_at?: string | null;
  publicity_end_at?: string | null;
  archived_at?: string | null;
  operator_id?: string | null;
  created_at?: string | null;
  /** 公示中且已过截止时间 → 公示已结束（前端据此渲染「已结束」徽章） */
  publicity_expired?: boolean;
}

/** 遴选请求体 */
export interface ArchiveSelectPayload {
  student_ids: string[];
  term: string;
}

/**
 * 档案列表（按班级 + 可选学期 + 可选状态过滤）。
 * 未传 class_id 时仅全局管理员可跨班查看。
 */
export async function listArchive(params: {
  class_id?: string;
  term?: string;
  status?: ArchiveStatus;
} = {}): Promise<EvaluationArchive[]> {
  const q = new URLSearchParams();
  if (params.class_id) q.set("class_id", params.class_id);
  if (params.term) q.set("term", params.term);
  if (params.status) q.set("status", params.status);
  const qs = q.toString();
  return request<EvaluationArchive[]>(`/portfolio/archive${qs ? `?${qs}` : ""}`);
}

/** 遴选：把候选学生标记为「已遴选」（POST /classes/{class_id}/archive/select） */
export async function selectArchive(
  classId: string,
  payload: ArchiveSelectPayload
): Promise<EvaluationArchive[]> {
  return request<EvaluationArchive[]>(
    `/portfolio/classes/${encodeURIComponent(classId)}/archive/select`,
    { method: "POST", body: JSON.stringify(payload) }
  );
}

/** 开启公示（POST /archive/{id}/publicity，publicity_end_at = +7 天） */
export async function publishArchive(id: string): Promise<EvaluationArchive> {
  return request<EvaluationArchive>(
    `/portfolio/archive/${encodeURIComponent(id)}/publicity`,
    { method: "POST" }
  );
}

/** 公示撤回（POST /archive/{id}/withdraw，→ draft） */
export async function withdrawArchive(id: string): Promise<EvaluationArchive> {
  return request<EvaluationArchive>(
    `/portfolio/archive/${encodeURIComponent(id)}/withdraw`,
    { method: "POST" }
  );
}

/** 成档归档（POST /archive/{id}/archive，→ archived） */
export async function archiveToFile(id: string): Promise<EvaluationArchive> {
  return request<EvaluationArchive>(
    `/portfolio/archive/${encodeURIComponent(id)}/archive`,
    { method: "POST" }
  );
}
