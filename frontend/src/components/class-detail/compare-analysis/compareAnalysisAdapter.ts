import type {
  ClassAnalysisReport,
  ClassAnalysisRanking,
  GradeCode,
} from "@/services/api";

/* ─── 对比分析「真实数据」视图模型 ───
 * 全部来自后端 /class-analysis/report（source_summary + analysis），
 * 绝不用伪随机 / mock 数据冒充。后端无数据源的模块由各组件降级展示。
 */

/** 班内学生排名（最近一场考试的真实名次） */
export interface StudentRankingItem {
  studentId: string;
  studentName: string;
  studentNumber: string;
  score: number | null;
  rank: number;
  /** 等级代码（后端 rankings[].grade 返回）或 null */
  grade: GradeCode | null;
}

/** 核心指标行（均分/中位/最高/最低/错误率/优秀率/及格率为真实值；标准差无数据源 → unsupported） */
export interface CoreMetricRow {
  label: string;
  value: number | null;
  unit: string;
  higherBetter: boolean;
  unsupported?: boolean;
}

/** 历史趋势点（每场考试的真实统计） */
export interface TrendPoint {
  exam: string;
  averageScore: number | null;
  medianScore: number | null;
  highestScore: number | null;
  lowestScore: number | null;
  wrongRate: number | null;
}

/** 薄弱知识点（来自 analysis.weak_points） */
export interface WeakPointItem {
  knowledgePoint: string;
  severity: "high" | "medium" | "low";
  affectedStudentCount: number;
  evidence: string;
  teachingSuggestion: string;
}

/** 总体概览（来自 overall_metrics + analysis.overall_level） */
export interface CompareOverview {
  className: string;
  level: string;
  summary: string;
  trend: string;
  scoreInterpretation: string;
  strengths: string[];
  dataNotes: string[];
  examCount: number;
  latestAverageScore: number | null;
  averageScoreChange: number | null;
  latestExamName: string;
}

function toNullableNumber(value: number | null | undefined): number | null {
  return value === null || value === undefined ? null : value;
}

/** 最近一场考试的班内学生排名 */
export function buildStudentRankings(
  report: ClassAnalysisReport,
): StudentRankingItem[] {
  const exams = report.source_summary?.exam_summaries || [];
  const latest = exams[exams.length - 1];
  if (!latest) return [];
  return (latest.rankings || [])
    .filter((item) => item.score !== null && item.score !== undefined)
    .slice()
    .sort((a, b) => a.rank - b.rank)
    .map((item) => ({
      studentId: item.student_id,
      studentName: item.student_name,
      studentNumber: item.student_number || "",
      score: toNullableNumber(item.score),
      rank: item.rank,
      grade: item.grade ?? null,
    }));
}

/** 从最近考试 rankings 计算及格率/优秀率（与后端 _rankings_pass_rate 一致：score 达标人数 / 参考总人数）。 */
function rankingRate(
  rankings: ClassAnalysisRanking[],
  threshold: number,
): number | null {
  if (!rankings || rankings.length === 0) return null;
  const passed = rankings.filter((r) => (r.score ?? 0) >= threshold).length;
  return Math.round((passed / rankings.length) * 1000) / 10;
}

/** 核心指标：真实值来自最近考试（优秀率/及格率由最近考试 rankings 计算），无数据源的测量指标显式标记 unsupported */
export function buildCoreMetrics(report: ClassAnalysisReport): CoreMetricRow[] {
  const exams = report.source_summary?.exam_summaries || [];
  const latest = exams[exams.length - 1];
  if (!latest) return [];
  const rankings = latest.rankings || [];
  return [
    {
      label: "平均分",
      value: toNullableNumber(latest.average_score),
      unit: "分",
      higherBetter: true,
    },
    {
      label: "中位数",
      value: toNullableNumber(latest.median_score),
      unit: "分",
      higherBetter: true,
    },
    {
      label: "最高分",
      value: toNullableNumber(latest.highest_score),
      unit: "分",
      higherBetter: true,
    },
    {
      label: "最低分",
      value: toNullableNumber(latest.lowest_score),
      unit: "分",
      higherBetter: true,
    },
    {
      label: "错误率",
      value: toNullableNumber(latest.wrong_rate),
      unit: "%",
      higherBetter: false,
    },
    {
      label: "优秀率",
      value: rankingRate(rankings, 85),
      unit: "%",
      higherBetter: true,
    },
    {
      label: "及格率",
      value: rankingRate(rankings, 60),
      unit: "%",
      higherBetter: true,
    },
    {
      label: "标准差",
      value: null,
      unit: "",
      higherBetter: false,
      unsupported: true,
    },
  ];
}

/** 历史趋势：每场考试的本班统计 */
export function buildHistoryTrend(report: ClassAnalysisReport): TrendPoint[] {
  return (report.source_summary?.exam_summaries || []).map((item) => ({
    exam: item.exam_name,
    averageScore: toNullableNumber(item.average_score),
    medianScore: toNullableNumber(item.median_score),
    highestScore: toNullableNumber(item.highest_score),
    lowestScore: toNullableNumber(item.lowest_score),
    wrongRate: toNullableNumber(item.wrong_rate),
  }));
}

/** 薄弱知识点 */
export function buildWeakPoints(report: ClassAnalysisReport): WeakPointItem[] {
  return (report.analysis?.weak_points || []).map((item) => ({
    knowledgePoint: item.knowledge_point,
    severity: item.severity,
    affectedStudentCount: item.affected_student_count || 0,
    evidence: item.evidence || "",
    teachingSuggestion: item.teaching_suggestion || "",
  }));
}

/** 总体概览 */
export function buildCompareOverview(
  report: ClassAnalysisReport,
  fallbackClassName = "",
): CompareOverview {
  const overall = report.analysis?.overall_level || {};
  const metrics = report.source_summary?.overall_metrics || {};
  const exams = report.source_summary?.exam_summaries || [];
  return {
    className:
      report.source_summary?.class?.class_name ||
      report.class_name ||
      fallbackClassName,
    level: overall.level || "",
    summary: overall.summary || "",
    trend: overall.trend || "",
    scoreInterpretation: overall.score_interpretation || "",
    strengths: overall.strengths || [],
    dataNotes: overall.data_notes || [],
    examCount: metrics.exam_count || 0,
    latestAverageScore: toNullableNumber(metrics.latest_average_score),
    averageScoreChange: toNullableNumber(metrics.average_score_change),
    latestExamName: exams[exams.length - 1]?.exam_name || "",
  };
}
