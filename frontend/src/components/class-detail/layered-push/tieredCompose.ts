/* ── 分层组卷：难度权重 / 难度概况 纯函数 ──
 * 与后端 app/services/paper_composer.py 的 TIER_BAND_WEIGHTS / difficulty_summary 同口径，
 * 供 LayeredPushPage / ExamGenPage 展示层间差异与难度概况；不发请求。 */

export type TierName = "A" | "B" | "C";
export type Band = "easy" | "medium" | "hard";

export interface BandWeights {
  easy: number;
  medium: number;
  hard: number;
}

export interface DifficultySummary {
  easy: number;
  medium: number;
  hard: number;
  avg: number;
  count: number;
}

/** A=提高/综合/压轴；B=标准；C=基础巩固（与后端 TIER_BAND_WEIGHTS 一致） */
export const TIER_BAND_WEIGHTS: Record<TierName, BandWeights> = {
  A: { easy: 0.1, medium: 0.35, hard: 0.55 },
  B: { easy: 0.25, medium: 0.5, hard: 0.25 },
  C: { easy: 0.55, medium: 0.35, hard: 0.1 },
};

/** 知识点粒度：A 跨知识点 / B 不限 / C 单一知识点（与后端 TIER_KP_MODE 一致） */
export const TIER_KP_MODE: Record<TierName, "multi" | null | "single"> = {
  A: "multi",
  B: null,
  C: "single",
};

export const TIER_ORDER: TierName[] = ["A", "B", "C"];

/** 层显示名（中文固定；页面文案走 i18n） */
export const TIER_LABELS: Record<TierName, string> = {
  A: "A层",
  B: "B层",
  C: "C层",
};

/** 按显式权重生成难度带序列（长度 count），不足 1 按四舍五入摊 */
export function planBands(count: number, weights: BandWeights): Band[] {
  if (!Number.isFinite(count) || count <= 0) return [];
  const w: BandWeights = {
    easy: Math.max(0, Number(weights?.easy) || 0),
    medium: Math.max(0, Number(weights?.medium) || 0),
    hard: Math.max(0, Number(weights?.hard) || 0),
  };
  const total = w.easy + w.medium + w.hard;
  if (total <= 0) return [];
  let easyN = Math.round((count * w.easy) / total);
  let hardN = Math.round((count * w.hard) / total);
  if (easyN + hardN > count) hardN = Math.max(0, count - easyN);
  let mediumN = count - easyN - hardN;
  if (mediumN < 0) {
    hardN = Math.max(0, count - easyN);
    mediumN = count - easyN - hardN;
  }
  return [
    ...Array<Band>(easyN).fill("easy"),
    ...Array<Band>(mediumN).fill("medium"),
    ...Array<Band>(hardN).fill("hard"),
  ];
}

/** knowledge_point 是否单一知识点（无 / 分隔或只有一个有效段） */
export function isSingleKp(kp?: string | null): boolean {
  if (!kp) return true;
  const segs = String(kp)
    .split("/")
    .map((s) => s.trim())
    .filter(Boolean);
  return segs.length <= 1;
}

/**
 * 难度概况：difficulty 1-5，≤2 易、3 中、≥4 难（与后端 difficulty_summary 一致）。
 * 入参可为 {difficulty} 列表或裸数字列表。
 */
export function summarizeDifficulty(
  items: Array<{ difficulty?: number | null } | number | null | undefined>,
): DifficultySummary {
  let easy = 0;
  let medium = 0;
  let hard = 0;
  let total = 0;
  let n = 0;
  for (const it of items || []) {
    let d = 3;
    if (typeof it === "number") d = it;
    else if (it && typeof it === "object" && it.difficulty != null) {
      const v = Number(it.difficulty);
      if (Number.isFinite(v)) d = v;
    }
    total += d;
    n += 1;
    if (d <= 2) easy += 1;
    else if (d >= 4) hard += 1;
    else medium += 1;
  }
  return {
    easy,
    medium,
    hard,
    avg: n ? Math.round((total / n) * 100) / 100 : 0,
    count: n,
  };
}

/** 层间差异一句话描述（i18n key，页面用 t() 翻译） */
export function tierStrategyKey(tier: TierName): string {
  return `smartGen.tiered.strategy.${tier}`;
}
