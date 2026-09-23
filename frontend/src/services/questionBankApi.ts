import { gradingFetch } from "./gradingApi";

/**
 * 题库 REST 层（PG 资产库只读，P0 融合）。
 *
 * 后端路由 app/routers/school_assets.py，前缀 /api/v1/school-assets。
 * 返回裸 JSON（无 ApiResponse { code/message/data } 信封），故复用
 * gradingFetch（原样返回 body），而非 api.ts 的 request（会剥 .data）。
 *
 * 优雅降级：ASSETS_DB_ENABLED=false / PG 不可达时后端返回 503，
 * 这里 catch 503 返回空数据 + enabled=false，让页面落到「题库未接入」空态，
 * 真实 500 / 网络错误仍照常抛出。
 */

/** 题库题目（对齐后端 repo._question_to_dict 白名单列） */
export interface BankQuestion {
  id: string;
  subject: string;
  grade: string | null;
  question_type: string;
  question: string;
  options: unknown;
  answer: string;
  analysis: string | null;
  knowledge_point: string | null;
  difficulty: number;
  source: string;
  raw_id: string;
  unique_key: string;
  curriculum: string | null;
  difficulty_source: string | null;
  esl_level: number | null;
  quality_flag: string | null;
  ai_verdict: string | null;
  ai_confidence: string | null;
  ai_judge_source: string | null;
}

export interface BankQuestionSearchParams {
  subject?: string;
  grade?: string;
  question_type?: string;
  difficulty?: number;
  knowledge_point?: string;
  keyword?: string;
  page?: number;
  page_size?: number;
}

export interface BankQuestionSearchResponse {
  items: BankQuestion[];
  total: number;
  page: number;
  page_size: number;
  /** false = 题库未接入（503 降级），页面据此展示提示 */
  enabled?: boolean;
}

export interface BankFilters {
  subjects: string[];
  grades: string[];
  question_types: string[];
  difficulties: number[];
}

/** 题库多条件检索 + 分页：GET /school-assets/questions/search */
export async function searchBankQuestions(
  params: BankQuestionSearchParams,
): Promise<BankQuestionSearchResponse> {
  const qs = new URLSearchParams();
  if (params.subject) qs.set("subject", params.subject);
  if (params.grade) qs.set("grade", params.grade);
  if (params.question_type) qs.set("question_type", params.question_type);
  if (params.difficulty != null) qs.set("difficulty", String(params.difficulty));
  if (params.knowledge_point) qs.set("knowledge_point", params.knowledge_point);
  if (params.keyword) qs.set("keyword", params.keyword);
  qs.set("page", String(params.page || 1));
  qs.set("page_size", String(params.page_size || 20));

  try {
    return await gradingFetch<BankQuestionSearchResponse>(
      `/school-assets/questions/search?${qs.toString()}`,
    );
  } catch (err) {
    const status = (err as Error & { status?: number }).status;
    if (status === 503) {
      return {
        items: [],
        total: 0,
        page: params.page || 1,
        page_size: params.page_size || 20,
        enabled: false,
      };
    }
    throw err;
  }
}

/** 筛选下拉枚举值：GET /school-assets/filters */
export async function getBankFilters(): Promise<BankFilters> {
  try {
    return await gradingFetch<BankFilters>("/school-assets/filters");
  } catch (err) {
    const status = (err as Error & { status?: number }).status;
    if (status === 503) {
      return { subjects: [], grades: [], question_types: [], difficulties: [] };
    }
    throw err;
  }
}

/** 剥离 HTML 标签取纯文本（题库题干/答案可能含 <p>/<br> 等标签） */
export function stripHtmlText(html: string): string {
  return html
    .replace(/<[^>]*>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .trim();
}
