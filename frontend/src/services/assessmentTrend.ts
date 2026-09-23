import type { AssessmentResult } from "@/services/assessmentApi";

/**
 * 诊断趋势纯函数 — 从锚点结果 rows 构建维度趋势序列。
 * 全部为纯计算，便于 Vitest 单元测试。
 *
 * 数据契约：listStudentResults() → rows[].tag_schema.dimension_percents
 * （Record<string, number>，0-100）+ rows[].created_at（ISO 字符串）。
 * 前端返回未排序，须按 created_at 升序。
 */

/** 评估域维度枚举（非五育域，仅此 5 维参与趋势） */
export const ASSESSMENT_DIMENSIONS = [
  "learning_style",
  "interest",
  "social_style",
  "emotion_regulation",
  "challenge_coping",
] as const;

export type AssessmentDimension = (typeof ASSESSMENT_DIMENSIONS)[number];

/** 单个趋势点：index/date 之外，各维度百分比挂在该维度名下（缺失维度为 undefined） */
export interface TrendPoint {
  /** 按 created_at 排序后的序号（从 1 开始） */
  index: number;
  /** 施测时间 ISO 字符串 */
  date: string;
  [dim: string]: number | string;
}

export interface TrendSeries {
  points: TrendPoint[];
  /** 参与趋势的评估域维度（按 ASSESSMENT_DIMENSIONS 顺序，至少一个点有值） */
  dims: AssessmentDimension[];
}

function toTime(iso: string): number {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? 0 : t;
}

/** 提取每维时间序列：按 created_at 升序，非评估域维度一律丢弃 */
export function buildTrendSeries(rows: AssessmentResult[]): TrendSeries {
  const sorted = [...rows].sort(
    (a, b) => toTime(a.created_at) - toTime(b.created_at),
  );

  const points: TrendPoint[] = sorted.map((row, i) => {
    const point: TrendPoint = {
      index: i + 1,
      date: row.created_at,
    };
    const percents = row.tag_schema?.dimension_percents ?? {};
    for (const dim of ASSESSMENT_DIMENSIONS) {
      const v = percents[dim];
      if (typeof v === "number" && Number.isFinite(v)) {
        point[dim] = v;
      }
    }
    return point;
  });

  const dims = ASSESSMENT_DIMENSIONS.filter((dim) =>
    points.some((p) => typeof p[dim] === "number"),
  );

  return { points, dims };
}

export interface DimensionDelta {
  dim: string;
  prev: number | null;
  latest: number | null;
  /** latest - prev；不足两次有效测量时为 null */
  delta: number | null;
}

/** 每个维度的「上次 vs 本次」差值（最后一个有效值 - 上一个有效值） */
export function lastTwoDelta(series: TrendSeries): DimensionDelta[] {
  const result: DimensionDelta[] = [];
  for (const dim of series.dims) {
    let prev: number | null = null;
    let latest: number | null = null;
    for (const p of series.points) {
      const v = p[dim];
      if (typeof v === "number") {
        prev = latest;
        latest = v;
      }
    }
    result.push({
      dim,
      prev,
      latest,
      delta: prev != null && latest != null ? latest - prev : null,
    });
  }
  return result;
}

/** 薄弱维度：最新一次施测百分比低于阈值（默认 60），返回维度键列表 */
export function weakDimensions(
  latest: Record<string, number>,
  threshold = 60,
): string[] {
  return Object.entries(latest)
    .filter(([, v]) => typeof v === "number" && v < threshold)
    .map(([dim]) => dim);
}

/** 最新一次施测各评估域维度百分比（无值维度不包含） */
export function latestPercents(series: TrendSeries): Record<string, number> {
  const last = series.points[series.points.length - 1];
  if (!last) return {};
  const out: Record<string, number> = {};
  for (const dim of ASSESSMENT_DIMENSIONS) {
    const v = last[dim];
    if (typeof v === "number") out[dim] = v;
  }
  return out;
}
