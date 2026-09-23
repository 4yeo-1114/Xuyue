import { request } from "@/services/api";

export interface DashboardOverview {
  grade: string | null;
  class_id: string | null;
  class_count: number;
  student_count: number;
  users_count?: number;
  exams_count?: number;
  grading_count: number;
  alert_count: number;
  redemption_count: number;
  growth_score_available: boolean;
  growth_score_avg: number | null;
  grading_days: number;
}

export type TrendGranularity = "daily" | "weekly" | "monthly";

export interface DashboardTrendPoint {
  period: string;
  label: string;
  grading_count: number;
  alert_count: number;
  redemption_count: number;
}

export interface DashboardTrend {
  granularity: TrendGranularity;
  days: number;
  start_date: string | null;
  end_date: string | null;
  periods: DashboardTrendPoint[];
}

/** 学校驾驶舱 KPI 总览（全校 / 年级 / 班级，管理员） */
export async function getDashboardOverview(
  params: {
    grade?: string;
    class_id?: string;
  } = {},
): Promise<DashboardOverview> {
  const q = new URLSearchParams();
  if (params.grade) q.set("grade", params.grade);
  if (params.class_id) q.set("class_id", params.class_id);
  const s = q.toString();
  return request<DashboardOverview>(
    `/admin/dashboard/overview${s ? `?${s}` : ""}`,
  );
}

/** 日 / 周 / 月粒度走势（批改量 / 预警数 / 兑换量，管理员） */
export async function getDashboardTrend(params: {
  granularity: TrendGranularity;
  days?: number;
  grade?: string;
  class_id?: string;
}): Promise<DashboardTrend> {
  const q = new URLSearchParams();
  if (params.days !== undefined && params.days !== null)
    q.set("days", String(params.days));
  if (params.grade) q.set("grade", params.grade);
  if (params.class_id) q.set("class_id", params.class_id);
  const s = q.toString();
  return request<DashboardTrend>(
    `/admin/dashboard/${params.granularity}${s ? `?${s}` : ""}`,
  );
}

// ---- 学情接口（GET /admin/academic/*，管理员；grade / class_id 可选过滤，类名/年级名为中文 label）----

/** 学情范围描述（label 为中文：全校 / 年级名 / 班级名） */
export interface AcademicScope {
  grade: string | null;
  class_id: string | null;
  label: string;
}

/** 学情聚合指标（均分 / 及格率 / 优秀率，优秀线 85 及格线 60，保留 1 位小数） */
export interface AcademicMetricSummary {
  avg_score: number;
  pass_rate: number;
  excellent_rate: number;
  score_count: number;
  student_count: number;
}

/** 成绩学情对比分组明细（全校→各年级 / 选年级→各班 / 选班级→该班 1 条） */
export interface AcademicComparisonItem extends AcademicMetricSummary {
  key: string;
  label: string;
}

/** GET /admin/academic/overview 返回：当前范围 summary + 分组 items */
export interface AcademicOverview {
  scope: AcademicScope;
  summary: AcademicMetricSummary;
  items: AcademicComparisonItem[];
}

/** 学情趋势单月点（按 exam_date 所在月份聚合，period 形如 YYYY-MM） */
export interface AcademicTrendPoint {
  period: string;
  label: string;
  avg_score: number;
  pass_rate: number;
  excellent_rate: number;
  score_count: number;
}

/** GET /admin/academic/trend 返回：月聚合序列（最近 limit 个月，升序） */
export interface AcademicTrend {
  points: AcademicTrendPoint[];
}

/** 班级排名单行（按 avg_score 降序；class_name 取 classes.name，不拼年级） */
export interface ClassRankingItem {
  rank: number;
  class_id: string;
  class_name: string;
  grade: string;
  avg_score: number;
  pass_rate: number;
  excellent_rate: number;
  student_count: number;
}

/** GET /admin/academic/class-ranking 返回：当前范围各班排名 */
export interface ClassRanking {
  scope: { grade: string | null; label: string };
  classes: ClassRankingItem[];
}

/** 成绩等级分布单行（excellent/good/pass/needs_work 数量） */
export interface GradeDistributionItem {
  grade: string;
  label: string;
  excellent: number;
  good: number;
  pass: number;
  needs_work: number;
  total: number;
}

/** 知识点掌握度单行（avg_mastery 0-1，weak_points 薄弱点数） */
export interface MasteryItem {
  grade: string;
  label: string;
  avg_mastery: number;
  weak_points: number;
}

/** GET /admin/academic/mastery 返回：等级分布（有数据）+ 知识点掌握度（当前为空，感知空态） */
export interface MasteryOverview {
  mastery_available: boolean;
  grade_distribution: GradeDistributionItem[];
  mastery: MasteryItem[];
}

/** 成绩学情对比：当前范围 summary + 分组明细（柱状图数据源） */
export async function getAcademicOverview(
  params: { grade?: string; class_id?: string } = {},
): Promise<AcademicOverview> {
  const q = new URLSearchParams();
  if (params.grade) q.set("grade", params.grade);
  if (params.class_id) q.set("class_id", params.class_id);
  const s = q.toString();
  return request<AcademicOverview>(
    `/admin/academic/overview${s ? `?${s}` : ""}`,
  );
}

/** 学情趋势：按考试日期月聚合（最近 limit 个月，默认 12） */
export async function getAcademicTrend(
  params: { grade?: string; class_id?: string; limit?: number } = {},
): Promise<AcademicTrend> {
  const q = new URLSearchParams();
  if (params.grade) q.set("grade", params.grade);
  if (params.class_id) q.set("class_id", params.class_id);
  if (params.limit !== undefined && params.limit !== null)
    q.set("limit", String(params.limit));
  const s = q.toString();
  return request<AcademicTrend>(`/admin/academic/trend${s ? `?${s}` : ""}`);
}

/** 班级排名：当前范围（全校 / 指定年级）各班按均分降序 */
export async function getClassRanking(
  params: { grade?: string } = {},
): Promise<ClassRanking> {
  const q = new URLSearchParams();
  if (params.grade) q.set("grade", params.grade);
  const s = q.toString();
  return request<ClassRanking>(
    `/admin/academic/class-ranking${s ? `?${s}` : ""}`,
  );
}

/** 知识掌握度 / 成绩等级分布 */
export async function getMastery(
  params: { grade?: string; class_id?: string } = {},
): Promise<MasteryOverview> {
  const q = new URLSearchParams();
  if (params.grade) q.set("grade", params.grade);
  if (params.class_id) q.set("class_id", params.class_id);
  const s = q.toString();
  return request<MasteryOverview>(`/admin/academic/mastery${s ? `?${s}` : ""}`);
}

// ---- 班级/学生知识点掌握度聚合（BE-1：错题分布派生口径，GET /class-analysis/mastery-distribution）----

/** 单个知识点掌握度聚合行（mastery = 1 - wrong_count/total，相对口径；锚点是 name 非 id） */
export interface MasteryDistributionItem {
  knowledge_point_id: string | null;
  name: string;
  mastery: number; // 0-1，错题占比相对口径（非满分率）
  wrong_count: number;
  total: number;
}

/** 班级 / 学生知识点掌握度聚合（school_id 必填；class_id / student_id 二选一可选） */
export async function getMasteryDistribution(
  schoolId: string,
  params: { class_id?: string; student_id?: string } = {},
): Promise<MasteryDistributionItem[]> {
  const q = new URLSearchParams({ school_id: schoolId });
  if (params.class_id) q.set("class_id", params.class_id);
  if (params.student_id) q.set("student_id", params.student_id);
  return request<MasteryDistributionItem[]>(
    `/class-analysis/mastery-distribution?${q.toString()}`,
  );
}
