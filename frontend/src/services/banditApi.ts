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
  mode: "explore" | "exploit" | "fallback";
  ucb_score?: number;
  /** 人话版推荐依据（服务端生成中文说明） */
  reason_text?: string;
}

export interface BanditRecommendItem {
  question: BanditRecommendedQuestion;
  reason: BanditRecommendReason;
}

export type BanditRecommendMode = "explore" | "exploit" | "fallback";

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
 */
export async function getBanditWrongQuestions(
  studentId: string,
  subject: string,
  limit = 5,
): Promise<BanditRecommendResponse> {
  const params = new URLSearchParams({
    student_id: studentId,
    subject,
    limit: String(limit),
  });
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
