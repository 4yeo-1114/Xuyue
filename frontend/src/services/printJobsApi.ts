// 布置作业/打印记录（/print-jobs）——小程序布置的作业在这里看/改/删/重打。
// 后端返回裸 JSON（无 ApiResponse 信封），复用 gradingFetch 原样取包。
import { gradingFetch } from "./gradingApi";

export interface PrintJobPublic {
  job_id: string;
  status: string; // draft | pending | printing | done | failed
  title: string;
  subject: string;
  subject_label: string;
  grade: string;
  grade_label: string;
  class_name: string;
  teacher: string;
  question_count: number;
  source: string; // text | upload | ai
  page_size: string;
  page_size_label: string;
  copies: number;
  attempts: number;
  printer?: string | null;
  error?: string | null;
  created_at?: string | null;
  printed_at?: string | null;
}

export interface PrintJobUploadMeta {
  upload_id: string;
  kind: string;
  name: string;
  size: number;
  width?: number | null;
  height?: number | null;
  pages?: number | null;
}

export interface PrintJobFull extends PrintJobPublic {
  layout: string;
  note: string;
  answer_lines: number;
  upload_answer_lines: number;
  answer_lines_override?: number | null;
  questions: string[];
  question_items: Record<string, unknown>[];
  upload_ids: string[];
  uploads: PrintJobUploadMeta[];
}

export interface PrintJobUpdate {
  title?: string;
  subject?: string;
  grade?: string;
  class_name?: string;
  teacher?: string;
  copies?: number;
  questions?: string[];
  question_count?: number;
  answer_lines?: number;
  note?: string;
  upload_answer_lines?: number;
  question_items?: Record<string, unknown>[];
  answer_lines_override?: number | null;
  page_size?: string;
  layout?: string;
}

/** 我的布置记录（最新在前） */
export async function fetchPrintJobs(limit = 50): Promise<PrintJobPublic[]> {
  const data = await gradingFetch<{ jobs?: PrintJobPublic[] }>(
    `/print-jobs?limit=${encodeURIComponent(limit)}`,
  );
  return data?.jobs ?? [];
}

/** 单条完整详情（含出卷参数，编辑弹窗用） */
export async function fetchPrintJobFull(jobId: string): Promise<PrintJobFull> {
  return gradingFetch<PrintJobFull>(
    `/print-jobs/${encodeURIComponent(jobId)}/full`,
  );
}

/** 修改作业（改了出卷内容后端会重建 PDF） */
export async function updatePrintJob(
  jobId: string,
  patch: PrintJobUpdate,
): Promise<PrintJobFull> {
  return gradingFetch<PrintJobFull>(
    `/print-jobs/${encodeURIComponent(jobId)}`,
    { method: "PATCH", body: patch },
  );
}

/** 删除作业记录 */
export async function deletePrintJob(
  jobId: string,
): Promise<{ ok: boolean; job_id: string }> {
  return gradingFetch(`/print-jobs/${encodeURIComponent(jobId)}`, {
    method: "DELETE",
  });
}

/** 送出打印（reprint=true 时已打印过的可重打） */
export async function printPrintJob(
  jobId: string,
  opts: { copies?: number; reprint?: boolean } = {},
): Promise<PrintJobPublic> {
  return gradingFetch<PrintJobPublic>(
    `/print-jobs/${encodeURIComponent(jobId)}/print`,
    {
      method: "POST",
      body: { copies: opts.copies, reprint: opts.reprint ?? true },
    },
  );
}

/** 作业纸 PDF 预览（打开新窗口）。带 token，不能直接 <a href>，走 blob + object URL */
export async function previewPrintJobPdf(jobId: string): Promise<void> {
  const { getAuthToken } = await import("./api");
  const { API_PREFIX } = await import("@/config/api");
  const token = await getAuthToken();
  const res = await fetch(
    `${API_PREFIX}/print-jobs/${encodeURIComponent(jobId)}/pdf`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );
  if (!res.ok) {
    let msg = `预览失败（${res.status}）`;
    try {
      const j = await res.json();
      msg = j.detail || j.message || msg;
    } catch {
      /* 保持默认文案 */
    }
    throw new Error(msg);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank");
  // 稍后回收，给新窗口留加载时间
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
