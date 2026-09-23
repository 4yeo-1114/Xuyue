/* ── 试卷分析（题目分析）域：真实数据模型与映射 ──
 *
 * 数据源：
 *   1. GET /class-review/report → ClassReviewSession 持久化的课堂讲评报告（真实批改聚合）
 *      - source_summary.high_risk_questions / strong_questions：逐题 正确/错误/空白 与原因
 *      - pre_class.question_cards：逐题知识点、典型错误、教学策略、跟进练习
 *      - pre_class.overview：班级整体概述
 *      - consolidation.tiered_practice：分层巩固练习
 *   2. GET /grading/error-book/folders/{folder}/detail（可选）：原始逐题明细（含错题学生名单）
 *
 * 伪随机 mock（analysisData.ts）已停用。难度/区分度/信度/标准差/选项分布等
 * 测量学指标后端不产出，一律降级展示，严禁 mock 填充。
 */

import type { ClassReviewReport } from "@/services/api";

export type QuestionStatus = "预警" | "关注" | "正常" | "优秀";

export interface QuestionAnalysisQuestion {
  key: string;
  title: string;
  knowledgePoint: string;
  correctCount: number;
  wrongCount: number;
  blankCount: number;
  ungradedCount: number;
  totalCount: number;
  /** 得分率，0-100 整数 */
  scoreRate: number;
  status: QuestionStatus;
  /** 后端逐题 reasons（错误原因文本 → 人数） */
  reasons: Array<{ text: string; count: number }>;
  /** 后端 question_cards.error_patterns（典型错误描述） */
  errorPatterns: string[];
  teachingStrategy?: string;
  followUpExercise?: string;
  /** 来自错题本明细的答错学生名单（可能为空） */
  wrongStudents?: string[];
}

export interface QuestionAnalysisSummary {
  validStudentCount: number;
  classAvgScore: number | null;
  answerAreaCount: number;
  correctCount: number;
  wrongCount: number;
  blankCount: number;
  questionCount: number;
  examNames: string[];
}

export interface QuestionAnalysisOverview {
  summary?: string;
  weakPoints: string[];
  strengths: string[];
  dataBasis: string[];
}

export interface QuestionAnalysisTier {
  level: string;
  tasks: string[];
}

export interface QuestionAnalysisData {
  summary: QuestionAnalysisSummary;
  questions: QuestionAnalysisQuestion[];
  overview: QuestionAnalysisOverview;
  tieredPractice: QuestionAnalysisTier[];
  importedFolderNames: string[];
  generatedAt?: string | null;
}

export function statusOfScoreRate(scoreRate: number): QuestionStatus {
  if (scoreRate < 60) return "预警";
  if (scoreRate < 70) return "关注";
  if (scoreRate < 85) return "正常";
  return "优秀";
}

/* ── 后端原始结构（仅用于安全读取，避免显式 any） ── */
interface RawQuestionStat {
  question_key?: string;
  display_title?: string;
  correct_count?: number;
  wrong_count?: number;
  blank_count?: number;
  ungraded_count?: number;
  reasons?: Record<string, number>;
}

interface RawQuestionCard {
  title?: string;
  knowledge_point?: string;
  correct_count?: number;
  wrong_count?: number;
  blank_count?: number;
  error_patterns?: string[];
  teaching_strategy?: string;
  follow_up_exercise?: string;
}

interface RawSourceSummary {
  valid_student_count?: number;
  class_avg_score?: number | null;
  answer_area_count?: number;
  correct_count?: number;
  wrong_count?: number;
  blank_count?: number;
  high_risk_questions?: RawQuestionStat[];
  strong_questions?: RawQuestionStat[];
}

interface RawOverview {
  summary?: string;
  weak_points?: string[];
  strengths?: string[];
  data_basis?: string[];
}

interface RawConsolidation {
  tiered_practice?: Array<{ level?: string; tasks?: string[] }>;
}

export interface RawFolderQuestion {
  title?: string;
  wrong_students?: string[];
}

function toNumber(value: unknown): number {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : 0;
}

function toStrArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((x) => String(x ?? "").trim()).filter(Boolean);
}

function toReasons(value: unknown): Array<{ text: string; count: number }> {
  if (!value || typeof value !== "object") return [];
  return Object.entries(value as Record<string, number>)
    .map(([text, count]) => ({ text: String(text).trim(), count: toNumber(count) }))
    .filter((x) => x.text && x.count > 0)
    .sort((a, b) => b.count - a.count);
}

function buildQuestion(
  stat: RawQuestionStat,
  card?: RawQuestionCard,
  folder?: RawFolderQuestion
): QuestionAnalysisQuestion {
  const title = String(stat.display_title || stat.question_key || card?.title || "").trim();
  const correct = toNumber(stat.correct_count ?? card?.correct_count);
  const wrong = toNumber(stat.wrong_count ?? card?.wrong_count);
  const blank = toNumber(stat.blank_count ?? card?.blank_count);
  const ungraded = toNumber(stat.ungraded_count);
  const total = Math.max(1, correct + wrong + blank + ungraded);
  const scoreRate = Math.round((correct / total) * 100);
  return {
    key: String(stat.question_key || title || "unknown"),
    title,
    knowledgePoint: String(card?.knowledge_point ?? "").trim(),
    correctCount: correct,
    wrongCount: wrong,
    blankCount: blank,
    ungradedCount: ungraded,
    totalCount: total,
    scoreRate,
    status: statusOfScoreRate(scoreRate),
    reasons: toReasons(stat.reasons),
    errorPatterns: toStrArray(card?.error_patterns),
    teachingStrategy: String(card?.teaching_strategy ?? "").trim() || undefined,
    followUpExercise: String(card?.follow_up_exercise ?? "").trim() || undefined,
    wrongStudents: toStrArray(folder?.wrong_students),
  };
}

/** 将 /class-review/report（+ 可选错题本原始明细）映射为页面数据模型 */
export function buildQuestionAnalysisData(
  report: ClassReviewReport,
  folderQuestions?: RawFolderQuestion[]
): QuestionAnalysisData {
  const sourceSummary = (report.source_summary ?? {}) as RawSourceSummary;
  const preClass = (report.pre_class ?? {}) as { overview?: RawOverview; question_cards?: RawQuestionCard[] };
  const consolidation = (report.consolidation ?? {}) as RawConsolidation;
  const overview = preClass.overview ?? {};

  const cards = Array.isArray(preClass.question_cards) ? preClass.question_cards : [];
  const cardByTitle = new Map<string, RawQuestionCard>();
  for (const c of cards) {
    const t = String(c?.title ?? "").trim();
    if (t) cardByTitle.set(t, c);
  }
  const folderByTitle = new Map<string, RawFolderQuestion>();
  for (const f of folderQuestions ?? []) {
    const t = String(f?.title ?? "").trim();
    if (t) folderByTitle.set(t, f);
  }

  const seen = new Set<string>();
  const questions: QuestionAnalysisQuestion[] = [];
  const stats = [
    ...(Array.isArray(sourceSummary.high_risk_questions) ? sourceSummary.high_risk_questions : []),
    ...(Array.isArray(sourceSummary.strong_questions) ? sourceSummary.strong_questions : []),
  ];
  for (const stat of stats) {
    const title = String(stat.display_title || stat.question_key || "").trim();
    if (!title) continue;
    const key = String(stat.question_key || title);
    if (seen.has(key)) continue;
    seen.add(key);
    questions.push(buildQuestion(stat, cardByTitle.get(title), folderByTitle.get(title)));
  }

  // 逐题统计为空（如旧报告只存了 question_cards）时回退到 question_cards
  if (questions.length === 0) {
    for (const card of cards) {
      const title = String(card?.title ?? "").trim();
      if (!title || seen.has(title)) continue;
      seen.add(title);
      questions.push(buildQuestion({ display_title: title }, card, folderByTitle.get(title)));
    }
  }

  questions.sort((a, b) => b.wrongCount - a.wrongCount || b.scoreRate - a.scoreRate);

  return {
    summary: {
      validStudentCount: toNumber(sourceSummary.valid_student_count),
      classAvgScore: sourceSummary.class_avg_score != null ? toNumber(sourceSummary.class_avg_score) : null,
      answerAreaCount: toNumber(sourceSummary.answer_area_count),
      correctCount: toNumber(sourceSummary.correct_count),
      wrongCount: toNumber(sourceSummary.wrong_count),
      blankCount: toNumber(sourceSummary.blank_count),
      questionCount: questions.length,
      examNames: Array.isArray(report.exam_names) ? report.exam_names.map(String) : [],
    },
    questions,
    overview: {
      summary: String(overview.summary ?? "").trim() || undefined,
      weakPoints: toStrArray(overview.weak_points),
      strengths: toStrArray(overview.strengths),
      dataBasis: toStrArray(overview.data_basis),
    },
    tieredPractice: Array.isArray(consolidation.tiered_practice)
      ? consolidation.tiered_practice.map((g) => ({
          level: String(g?.level ?? "").trim() || "练习",
          tasks: toStrArray(g?.tasks),
        }))
      : [],
    importedFolderNames: Array.isArray(report.imported_folder_names) ? report.imported_folder_names.map(String) : [],
    generatedAt: report.generated_at ?? null,
  };
}
