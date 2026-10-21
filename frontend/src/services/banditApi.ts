import { gradingFetch } from "./gradingApi";

/**
 * R6b contextual bandit 错题推荐 REST 层（LinUCB 变式推荐 + 点击上报）。
 *
 * 注意：bandit 接口返回裸 JSON（无 ApiResponse { code/message/data } 信封），
 * 故复用 gradingApi.gradingFetch（原样返回 body），而非 api.ts 的 request（会剥 .data）。
 */

/** 推荐题（PG 资产库变式题） */
export interface BanditRecommendedQuestion {
  id: string;
  question: string;
  answer: string;
  analysis: string;
  difficulty: number;
}

/** 每题推荐理由（kp 锚点 / 错因 / 置信度 / 推荐模式） */
export interface BanditRecommendReason {
  kp_name: string;
  error_types: string[];
  error_count: number;
  confidence: number;
  mode: "explore" | "exploit" | "fallback" | "ai";
  ucb_score?: number;
  /** 人话版推荐依据（服务端生成中文说明） */
  reason_text?: string;
}

export interface BanditRecommendItem {
  question: BanditRecommendedQuestion;
  reason: BanditRecommendReason;
}

export type BanditRecommendMode = "explore" | "exploit" | "fallback" | "ai";

/** 变式题/配套练习的题源选择 */
export type QuestionSource = "ai" | "bank";

export interface BanditRecommendResponse {
  mode: BanditRecommendMode;
  reason?: string;
  items: BanditRecommendItem[];
  student_id?: string;
  subject?: string;
  arm_count?: number;
}

export interface BanditClickResponse {
  success: boolean;
  clicked: boolean;
  reward: number;
}

/**
 * 变式题推荐：GET /api/v1/recommend/wrong-questions?student_id=&subject=&limit=
 * 返回同薄弱知识点（kp）的变式题 + 推荐理由；学生无错题 / PG 无匹配 → 200 fallback 空 items。
 *
 * source="bank"（默认）：题库变式题（LinUCB）；503=没接题库 → 空推荐（面板提示「没有接入题库」）。
 * source="ai"：AI 生成变式题，types=题型偏好 / topics=指定知识点（可选）。
 */
export async function getBanditWrongQuestions(
  studentId: string,
  subject: string,
  limit = 5,
  opts?: {
    source?: QuestionSource;
    types?: string[];
    topics?: string[];
    /** 单题举一反三：错题题干原文（不拆逗号），后端以此为出题锚点 */
    hint?: string;
  },
): Promise<BanditRecommendResponse> {
  const params = new URLSearchParams({
    student_id: studentId,
    subject,
    limit: String(limit),
    source: opts?.source || "bank",
  });
  if (opts?.types?.length) params.set("types", opts.types.join(","));
  if (opts?.topics?.length) params.set("topics", opts.topics.join(","));
  if (opts?.hint) params.set("hint", opts.hint);
  try {
    return await gradingFetch<BanditRecommendResponse>(
      `/recommend/wrong-questions?${params.toString()}`,
    );
  } catch (err) {
    // 优雅降级：PG 资产库未配置/未启用时后端返回 503（_guard_enabled），
    // 视为「暂无推荐」而非报错，让面板落到「暂无变式推荐」空态。
    // 其它真实错误（500 / 网络）仍照常抛出，面板显示「加载失败」。
    const status = (err as Error & { status?: number }).status;
    if (status === 503) {
      return {
        mode: "fallback",
        reason: "assets db not configured",
        items: [],
        student_id: studentId,
        subject,
      };
    }
    throw err;
  }
}

/**
 * 点击/作答反馈上报：POST /api/v1/recommend/wrong-questions/click
 * reward∈{0,1}：点击推荐变式题且参与作答记为 1（答对）；未采用/答错为 0。由调用方判定。
 */
export async function reportBanditWrongQuestionClick(
  studentId: string,
  subject: string,
  kpName: string,
  reward: 0 | 1,
): Promise<BanditClickResponse> {
  return gradingFetch<BanditClickResponse>("/recommend/wrong-questions/click", {
    method: "POST",
    body: { student_id: studentId, subject, kp_name: kpName, reward },
  });
}

// ── 客户清单#2：批改后自动配套练习 / 高频错题举一反三 ──────────────

/** 自动配套练习单题（资产库变式题或 LLM 生成） */
export interface AutoVariantItem {
  id?: string | number | null;
  question: string;
  answer: string;
  analysis?: string;
  difficulty?: number | null;
  kp_name: string;
  source?: string;
}

export interface AutoVariantWeakPoint {
  kp_name: string;
  kp_id?: string | null;
  wrong_count: number;
  student_count: number;
  titles?: string[];
  variants: AutoVariantItem[];
  skip_reason?: string | null;
}

/** 三态：none=未生成 / ready=已有列表 / empty=生成过但无题 / failed=生成失败 */
export type AutoVariantsStatus = "none" | "ready" | "empty" | "failed";

export interface AutoVariantsResult {
  folder: string;
  status: AutoVariantsStatus;
  reason?: string;
  generated_at?: string;
  class_id?: string | null;
  exam_name?: string | null;
  subject?: string | null;
  weak_points?: AutoVariantWeakPoint[];
  items: AutoVariantItem[];
  summary?: Record<string, unknown>;
}

/** 班级 + 考试名 → folder_safe（与后端 parse_class_folder 同口径） */
export function buildAutoVariantsFolder(classId: string, examName: string): string {
  const cid = String(classId || "").trim();
  const exam = String(examName || "").trim();
  if (!cid || !exam) return "";
  return `cls_${cid}__${exam}`;
}

/**
 * 从错题列表挑「本场」考试名（出现次数最多；平手取先出现的）。
 * 无有效 exam_name 返回空串。
 */
export function pickSessionExamName(
  items: Array<{ exam_name?: string | null } | null | undefined>,
): string {
  const counts = new Map<string, number>();
  let first = "";
  for (const it of items || []) {
    const exam = String(it?.exam_name || "").trim();
    if (!exam || exam === "暂无记录") continue;
    if (!first) first = exam;
    counts.set(exam, (counts.get(exam) || 0) + 1);
  }
  if (counts.size === 0) return "";
  let best = first;
  let bestN = 0;
  for (const [exam, n] of counts) {
    if (n > bestN) {
      best = exam;
      bestN = n;
    }
  }
  return best;
}

/** 本场 folder：classId + 错题列表里的考试名 */
export function pickSessionFolder(
  classId: string,
  items: Array<{ exam_name?: string | null } | null | undefined>,
): string {
  return buildAutoVariantsFolder(classId, pickSessionExamName(items));
}

/**
 * 三态/四态判断：生成中（mutation）> 失败 > 未生成 > 已有列表/空。
 * 供卡片标题徽章与空态文案选用。
 */
export function resolveAutoVariantsState(opts: {
  data?: AutoVariantsResult | null;
  isFetching?: boolean;
  isGenerating?: boolean;
}): "loading" | "generating" | "failed" | "none" | "ready" | "empty" {
  if (opts.isGenerating) return "generating";
  if (opts.isFetching && !opts.data) return "loading";
  const status = opts.data?.status;
  if (status === "failed") return "failed";
  if (status === "none" || !opts.data) return "none";
  if (status === "empty") return "empty";
  return "ready";
}

/** 列表装配：weak_points 展开为带 kp 上下文的展示行；无 weak_points 时用扁平 items */
export function flattenAutoVariantDisplay(data?: AutoVariantsResult | null): Array<
  AutoVariantItem & { wrong_count?: number; student_count?: number }
> {
  if (!data) return [];
  const wps = data.weak_points || [];
  if (wps.length > 0) {
    const rows: Array<AutoVariantItem & { wrong_count?: number; student_count?: number }> = [];
    for (const wp of wps) {
      for (const v of wp.variants || []) {
        rows.push({
          ...v,
          kp_name: v.kp_name || wp.kp_name,
          wrong_count: wp.wrong_count,
          student_count: wp.student_count,
        });
      }
    }
    return rows;
  }
  return (data.items || []).map((it) => ({ ...it }));
}

/**
 * 读该场自动配套练习：GET /api/v1/recommend/auto-variants?folder=
 * 未生成返回 status=none（不触发生成）。
 */
export async function getAutoVariants(folder: string): Promise<AutoVariantsResult> {
  const params = new URLSearchParams({ folder });
  return gradingFetch<AutoVariantsResult>(`/recommend/auto-variants?${params.toString()}`);
}

/**
 * 手动兜底重跑：POST /api/v1/recommend/auto-variants/generate
 * force=true 强制覆盖已生成结果。
 * source="ai"：全部 AI 生成（types=题型偏好 / topics=补充知识点）；"bank"：题库变式题。
 */
export async function generateAutoVariants(
  folder: string,
  force = true,
  opts?: {
    source?: QuestionSource;
    types?: string[];
    topics?: string[];
  },
): Promise<AutoVariantsResult> {
  return gradingFetch<AutoVariantsResult>("/recommend/auto-variants/generate", {
    method: "POST",
    body: {
      folder,
      force,
      source: opts?.source,
      types: opts?.types?.length ? opts.types : undefined,
      topics: opts?.topics?.length ? opts.topics : undefined,
    },
  });
}
