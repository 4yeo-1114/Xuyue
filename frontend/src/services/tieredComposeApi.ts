/* ── 分层组卷 API（/papers/tiered-compose） ──
 * 独立成文件，避免与并行任务争抢 services/api.ts。 */
import { request } from "@/services/api";

export interface TieredComposeQuestion {
  id: string;
  type: string;
  stem: string;
  content?: string;
  options?: string[];
  score?: number;
  answer?: string;
  analysis?: string;
  knowledge_point?: string;
  difficulty?: number;
  figure?: Record<string, unknown> | null; // AI 出题图形规格
  figure_img?: string | null; // 配图 data URL（后端按 figure 规格画出）
}

export interface TieredDifficultySummary {
  easy: number;
  medium: number;
  hard: number;
  avg: number;
  count: number;
}

export interface TieredPaperMeta {
  source?: string;
  batch_id?: string;
  tier?: string;
  tier_label?: string;
  class_id?: string;
  subject?: string;
  grade?: string | null;
  round_id?: string | null;
  exam_folder?: string | null;
  band_weights?: { easy: number; medium: number; hard: number };
  kp_mode?: string | null;
  difficulty_pref?: string;
  student_count?: number;
  created_at?: string;
  [k: string]: unknown;
}

export interface TieredPaperItem {
  paper_id: string;
  title: string;
  subject: string;
  tier: string;
  tier_label?: string;
  count: number;
  difficulty: TieredDifficultySummary;
  meta?: TieredPaperMeta;
  batch_id?: string;
  created_at?: string | null;
  questions?: TieredComposeQuestion[];
}

export interface TieredComposeResult {
  batch_id?: string | null;
  class_id: string;
  subject: string;
  tiers: { A: number; B: number; C: number; unassigned?: number };
  papers: TieredPaperItem[];
  total?: number;
  round_id?: string | null;
}

/** AI 题型模板（仿 AI 组卷）：type 取 ExamQuestion 英文枚举 */
export interface TieredComposeRequirement {
  type: string;
  count: number;
  score: number;
}

/** POST /papers/tiered-compose：按 A/B/C 层各组一份卷 */
export async function tieredCompose(body: {
  class_id: string;
  subject: string;
  grade?: string;
  exam_folder?: string;
  round_id?: string;
  count?: number;
  /** 题源："ai"=AI 生成（默认）|"bank"=题库抽题 */
  source?: "ai" | "bank";
  /** AI 题源：知识点列表 */
  topics?: string[];
  /** AI 题源：题型模板 */
  requirements?: TieredComposeRequirement[];
}): Promise<TieredComposeResult> {
  return request<TieredComposeResult>("/papers/tiered-compose", {
    method: "POST",
    body: JSON.stringify(body),
    // 三份卷抽题可能偏慢；AI 出题（3 次大模型调用）更慢，放宽超时
    timeout: 300_000,
  });
}

/** GET /papers/tiered-compose/result：最近一批（或按 round）分层卷清单 */
export async function getTieredComposeResult(params: {
  class_id: string;
  subject: string;
  round_id?: string;
  limit?: number;
}): Promise<TieredComposeResult> {
  const q = new URLSearchParams({ class_id: params.class_id, subject: params.subject });
  if (params.round_id) q.set("round_id", params.round_id);
  if (params.limit != null) q.set("limit", String(params.limit));
  return request<TieredComposeResult>(
    `/papers/tiered-compose/result?${q.toString()}`,
  );
}
