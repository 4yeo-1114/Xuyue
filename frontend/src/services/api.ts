import { API_PREFIX, REQUEST_TIMEOUT, MAX_RETRIES } from "@/config/api";
import { supabase } from "@/integrations/supabase/client";
import type {
  ApiResponse,
  ClassInfo,
  ClassRecord,
  StudentInfo,
  ClassTeacherRecord,
} from "@/types/api";
import type { WarningAlert } from "@/types/bureau";

// ---- 基础请求工具 ----

const AUTH_TOKEN_KEY = "grade_buddy_access_token";

/** 获取当前用户的 JWT token（优先使用后端登录 token，否则 Supabase session） */
export async function getAuthToken(): Promise<string | null> {
  const local =
    typeof localStorage !== "undefined"
      ? localStorage.getItem(AUTH_TOKEN_KEY)
      : null;
  if (local) return local;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

/** 带认证、超时和重试的 fetch 封装 */
export async function request<T>(
  endpoint: string,
  options: RequestInit & { timeout?: number } = {},
  retries = MAX_RETRIES,
): Promise<T> {
  const token = await getAuthToken();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(
    () => controller.abort(),
    options.timeout || REQUEST_TIMEOUT,
  );

  try {
    const response = await fetch(`${API_PREFIX}${endpoint}`, {
      ...options,
      headers,
      signal: controller.signal,
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      let message: string;
      if (typeof errorBody.detail === "string") {
        message = errorBody.detail;
      } else if (Array.isArray(errorBody.detail) && errorBody.detail[0]?.msg) {
        message = errorBody.detail[0].msg;
      } else {
        message = errorBody.message || `请求失败: ${response.status}`;
      }
      throw new ApiError(response.status, message);
    }

    const data: ApiResponse<T> = await response.json();
    return data.data;
  } catch (error) {
    if (error instanceof ApiError) throw error;

    if (retries > 0 && !(error instanceof DOMException)) {
      return request<T>(endpoint, options, retries - 1);
    }

    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(408, "请求超时，请稍后重试");
    }

    throw new ApiError(0, "网络错误，请检查连接");
  } finally {
    clearTimeout(timeoutId);
  }
}

/** 自定义 API 错误 */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** /auth 下部分接口直接返回 JSON 体（非 { data } 包裹） */
async function authRequest<T>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  const token = await getAuthToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const response = await fetch(`${API_PREFIX}${endpoint}`, {
    ...options,
    headers,
  });
  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    let message: string;
    if (typeof errorBody.detail === "string") {
      message = errorBody.detail;
    } else if (Array.isArray(errorBody.detail) && errorBody.detail[0]?.msg) {
      message = errorBody.detail[0].msg;
    } else {
      message = errorBody.message || `请求失败: ${response.status}`;
    }
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}

export interface UserProfile {
  id: string;
  email: string;
  display_name?: string | null;
  phone?: string | null;
  teaching_subject?: string | null;
  job_title?: string | null;
}

export interface LessonPlanApiRecord {
  id: string;
  user_id: string;
  class_id: string;
  school_year: string;
  term: string;
  grade?: string | null;
  subject: string;
  title: string;
  teaching_content: string;
  teaching_objectives: string;
  key_points: string;
  difficult_points: string;
  teaching_preparation: string;
  teaching_process: string;
  collective_preparation_advice: string;
  blackboard_design: string;
  teaching_reflection: string;
  main_author: string;
  deputy_author: string;
  lesson_sequence: string;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export async function updateProfile(body: {
  display_name?: string | null;
  phone?: string | null;
  teaching_subject?: string | null;
  job_title?: string | null;
  personal_email?: string | null;
}): Promise<UserProfile> {
  return authRequest<UserProfile>("/auth/me", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function changePassword(body: {
  old_password: string;
  new_password: string;
}): Promise<{ ok: boolean }> {
  return authRequest<{ ok: boolean }>("/auth/change-password", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ---- 批改相关 API ----
// 说明：后端批改链路为「文件夹 + 首页图片批改任务」模型，不存在 /grading/submit、/grading/records、
// /grading/result/{taskId} 端点。以下三个函数对齐真实端点（POST /grading/home/quick、
// GET /grading/home/recent、GET /grading/home/{job_id}），参数/返回类型以后端实际返回结构为准。

/** 后端批改作业状态（/grading/home/* 真实 schema） */
export type GradingJobStatus =
  "queued" | "running" | "rendering" | "done" | "failed" | "cancelled";

/** 首页图片批改作业（POST /grading/home/quick 与 GET /grading/home/{job_id} 返回的 item） */
export interface GradingJobItem {
  ok?: boolean;
  id: string;
  name: string;
  created_at: string;
  engine?: string;
  status: GradingJobStatus | string;
  progress?: number | null;
  message?: string;
  result?: string;
  image_original?: string | null;
  image_annotated?: string | null;
  image_marks_only?: string | null;
  upload_filename?: string;
  files?: {
    upload?: string;
    image_original?: string | null;
    image_annotated?: string | null;
    image_marks_only?: string | null;
    json?: string;
  };
  /** 判错原因批注（题号 → 批注）；首页作业记录里由异步生成/手动编辑维护 */
  wrong_annotations?: Record<
    string,
    {
      text: string;
      source: "ai" | "manual";
      edited: boolean;
      generated_at?: string;
    }
  > | null;
  /** 逐题判定块（百度/千问批改落盘的 blocks）；手动修正按 (index, sub_index) 对齐 */
  blocks?: Array<{
    index: number | string;
    sub_index?: number | string | null;
    result?: string;
    comment?: string;
    score?: number | null;
    partial_ratio?: number | null;
  }> | null;
}

/** 首页最近作业列表项（GET /grading/home/recent 的 items） */
export interface GradingRecentItem {
  id: string;
  name: string;
  created_at: string;
  status?: string;
  progress?: number | null;
  message?: string;
  ok?: boolean;
}

/** 批改端点返回原始 JSON（不走 { code, message, data } 包装），鉴权/错误解析与 request 对齐 */
async function gradingRequest<T>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  const token = await getAuthToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_PREFIX}${endpoint}`, { ...options, headers });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    let message: string;
    if (typeof errorBody.detail === "string") {
      message = errorBody.detail;
    } else if (Array.isArray(errorBody.detail) && errorBody.detail[0]?.msg) {
      message = errorBody.detail[0].msg;
    } else {
      message = errorBody.message || `请求失败: ${res.status}`;
    }
    throw new ApiError(res.status, message);
  }
  return (await res.json()) as T;
}

/** 提交批改任务：上传单张试卷图片，启动后台批改，返回 job_id（真实端点 POST /grading/home/quick） */
export async function submitGrading(
  file: File,
  filename?: string,
  anonymous = false,
): Promise<{ ok: boolean; job_id: string; item: GradingJobItem }> {
  const formData = new FormData();
  formData.append("file", file, filename ?? file.name);
  if (anonymous) formData.append("anonymous", "true");
  return gradingRequest<{ ok: boolean; job_id: string; item: GradingJobItem }>(
    "/grading/home/quick",
    { method: "POST", body: formData },
  );
}

/** 获取批改记录列表：真实端点 GET /grading/home/recent（返回最近 10 条作业，后端无分页/筛选） */
export async function getGradingRecords(): Promise<GradingRecentItem[]> {
  const data = await gradingRequest<{
    ok: boolean;
    items: GradingRecentItem[];
  }>("/grading/home/recent");
  return data.items ?? [];
}

/** 获取单个批改结果：真实端点 GET /grading/home/{job_id}（轮询 job 状态与结果） */
export async function getGradingResult(
  taskId: string,
): Promise<GradingJobItem> {
  const data = await gradingRequest<{ ok: boolean; item: GradingJobItem }>(
    `/grading/home/${encodeURIComponent(taskId)}`,
  );
  return data.item;
}

// ---- 班级 API（我的班级，走 FastAPI） ----

/** 获取当前用户的班级列表 */
export async function listClasses(params?: {
  school_level?: string;
  grade?: string;
}): Promise<ClassRecord[]> {
  const search = new URLSearchParams();
  if (params?.school_level) search.set("school_level", params.school_level);
  if (params?.grade) search.set("grade", params.grade);
  const q = search.toString();
  return request<ClassRecord[]>(`/classes${q ? `?${q}` : ""}`);
}

/** 创建班级 */
export async function createClass(body: {
  school_level: string;
  grade: string;
  name: string;
}): Promise<ClassRecord> {
  return request<ClassRecord>("/classes", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** 更新班级名称 */
export async function updateClass(
  id: string,
  body: { name: string },
): Promise<ClassRecord> {
  return request<ClassRecord>(`/classes/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

/** 删除班级 */
export async function deleteClass(id: string): Promise<void> {
  return request<void>(`/classes/${id}`, { method: "DELETE" });
}

// ---- 学生画像/分析 API ----
export interface StudentAnalysisRecord {
  id?: string;
  class_id: string;
  student_name: string;
  subject: string;
  target_score?: number | null;
  current_score?: number | null;
}

export async function getStudentAnalysis(
  classId: string,
  studentName: string,
  subject: string,
): Promise<StudentAnalysisRecord> {
  const params = new URLSearchParams({
    class_id: classId,
    student_name: studentName,
    subject: subject,
  });
  return request<StudentAnalysisRecord>(
    `/student-analysis?${params.toString()}`,
  );
}

export async function listStudentAnalysis(
  classId: string,
  subject: string,
): Promise<StudentAnalysisRecord[]> {
  const params = new URLSearchParams({
    class_id: classId,
    subject: subject,
  });
  return request<StudentAnalysisRecord[]>(
    `/student-analysis/list?${params.toString()}`,
  );
}

export async function updateStudentAnalysis(body: {
  class_id: string;
  student_name: string;
  subject: string;
  target_score?: number;
  current_score?: number;
}): Promise<StudentAnalysisRecord> {
  return request<StudentAnalysisRecord>("/student-analysis", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface StudentScoreHistoryRecord {
  id: string;
  exam_name: string;
  score: number;
  class_avg?: number | null;
  created_at: string;
}

export async function getStudentScoreHistory(
  classId: string,
  studentName: string,
  subject: string,
): Promise<StudentScoreHistoryRecord[]> {
  const params = new URLSearchParams({
    class_id: classId,
    student_name: studentName,
    subject: subject,
  });
  return request<StudentScoreHistoryRecord[]>(
    `/student-analysis/score-history?${params.toString()}`,
  );
}

export async function deleteExamHistory(
  classId: string,
  studentName: string,
  subject: string,
  examName: string,
): Promise<void> {
  const params = new URLSearchParams({
    class_id: classId,
    student_name: studentName,
    subject: subject,
    exam_name: examName,
  });
  return request<void>(
    `/student-analysis/score-history/exam?${params.toString()}`,
    {
      method: "DELETE",
    },
  );
}

export async function importStudentScores(body: {
  class_id: string;
  subject: string;
  exam_name: string;
  record_id?: string | null;
  class_avg?: number;
  scores: { student_name: string; score: number }[];
}): Promise<{ ok: boolean; imported_count: number; refreshed?: boolean }> {
  return request<{ ok: boolean; imported_count: number; refreshed?: boolean }>(
    "/student-analysis/import-scores",
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export async function importStudentScoresExcel(
  classId: string,
  subject: string,
  examName: string,
  file: File,
): Promise<{ ok: boolean; imported_count: number; refreshed?: boolean }> {
  const formData = new FormData();
  formData.append("class_id", classId);
  formData.append("subject", subject);
  formData.append("exam_name", examName);
  formData.append("file", file);

  const token = await getAuthToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(
    `${API_PREFIX}/student-analysis/import-scores/excel`,
    {
      method: "POST",
      headers,
      body: formData,
    },
  );

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "导入失败");
  }
  const json = await res.json();
  return json.data;
}

export async function getAIDiagnosis(
  classId: string,
  studentName: string,
  subject: string,
): Promise<any[]> {
  const params = new URLSearchParams({
    class_id: classId,
    student_name: studentName,
    subject: subject,
  });
  return request<any[]>(`/student-analysis/ai-diagnosis?${params.toString()}`);
}

export async function runAIDiagnosis(body: {
  class_id: string;
  student_name: string;
  subject: string;
}): Promise<any[]> {
  return request<any[]>("/student-analysis/ai-diagnosis", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface WrongQuestionItem {
  title: string;
  image_url?: string | null;
  answer_url?: string | null;
  /** 知识点锚点（P3-B3 已加列；回填前多为 null，前端有值才显示 chip） */
  knowledge_point_id?: string | null;
  /** 知识点名称锚点（来自 wrong_question_kp_bridge.kp_name，DB 主源覆盖 75.1%；有值才显示 chip） */
  knowledge_point_name?: string | null;
}

/** 班级错题列表聚合项：/latest 按（学生, 科目）返回最近一场考试错题，前端补全上下文 */
export interface ClassWrongQuestionItem extends WrongQuestionItem {
  student_id: string;
  student_name: string;
  subject: string;
  exam_name: string;
  created_at: string | null;
}

export interface WrongQuestionResponse {
  exam_name: string;
  questions: WrongQuestionItem[];
  created_at: string | null;
}

export async function getLatestWrongQuestions(
  classId: string,
  studentName: string,
  subject: string,
): Promise<WrongQuestionResponse> {
  const params = new URLSearchParams({
    class_id: classId,
    student_name: studentName,
    subject: subject,
  });
  return request<WrongQuestionResponse>(
    `/student-analysis/wrong-questions/latest?${params.toString()}`,
  );
}

// ---- 教案 API ----

// ---- 靶向提升 API ----

export interface TargetedStudentItem {
  id: string;
  name: string;
  student_number: string;
  current_score?: number | null;
  score_trend?: number;
  wrong_question_count?: number;
  weak_points?: string[];
  has_report?: boolean;
  updated_at?: string | null;
}

export interface TargetedReport {
  id: string;
  class_id: string;
  student_id?: string | null;
  student_name: string;
  student_number?: string | null;
  subject: string;
  diagnosis_text?: string;
  plan_text?: string;
  diagnosis?: any;
  plan?: any;
  source_summary?: any;
  exam_names?: string[];
  imported_folder_names?: string[];
  generated_at?: string | null;
  updated_at?: string | null;
}

export interface TargetedExamOption {
  id: string;
  name: string;
  completed_count: number;
  updated_at?: number;
}

export async function listTargetedSubjects(): Promise<string[]> {
  return request<string[]>("/targeted-improvement/subjects");
}

export async function listTargetedStudents(
  classId: string,
  subject: string,
): Promise<{
  students: TargetedStudentItem[];
  recommended_names: string[];
}> {
  const params = new URLSearchParams({ class_id: classId, subject });
  return request<{
    students: TargetedStudentItem[];
    recommended_names: string[];
  }>(`/targeted-improvement/students?${params.toString()}`);
}

export async function saveTargetedRecommendations(body: {
  class_id: string;
  subject: string;
  student_names: string[];
}): Promise<{ ok: boolean; recommended_names: string[] }> {
  return request<{ ok: boolean; recommended_names: string[] }>(
    "/targeted-improvement/recommendations",
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export async function getTargetedReport(
  classId: string,
  subject: string,
  studentName: string,
): Promise<{ report: TargetedReport | null }> {
  const params = new URLSearchParams({
    class_id: classId,
    subject,
    student_name: studentName,
  });
  return request<{ report: TargetedReport | null }>(
    `/targeted-improvement/report?${params.toString()}`,
  );
}

export async function listTargetedImportableExams(
  classId: string,
  subject: string,
): Promise<TargetedExamOption[]> {
  const params = new URLSearchParams({ class_id: classId, subject });
  return request<TargetedExamOption[]>(
    `/targeted-improvement/importable-exams?${params.toString()}`,
  );
}

export async function importTargetedExams(body: {
  class_id: string;
  subject: string;
  exam_folder_names: string[];
}): Promise<{
  ok: boolean;
  generated_count: number;
  failed_count: number;
  ignored_count: number;
  generated: Array<{ student_name: string; report_id: string }>;
  failed: Array<{ student_name: string; message: string }>;
  ignored_papers: Array<{ folder_name: string; filename: string }>;
}> {
  return request("/targeted-improvement/import-exams", {
    method: "POST",
    body: JSON.stringify(body),
    timeout: 600_000,
  });
}

/** 学情驱动内容推荐：弱项知识点 → 知识点 → 教学资源映射（按知识点分组，每组最多 3 条） */
export interface TeachingResourceItem {
  id: string;
  title: string;
  description?: string;
  type?: string;
  file_url: string;
  file_name?: string;
  difficulty?: number | null;
  knowledge_point_count?: number | null;
  question_count?: number | null;
  detected_subject?: string | null;
  detected_unit?: string | null;
  tags?: string[];
}

export interface RecommendedContentGroup {
  knowledge_point_id: string;
  knowledge_point_name: string;
  code?: string;
  is_weak?: boolean;
  mastery?: number;
  related?: string[];
  resources: TeachingResourceItem[];
}

export async function getRecommendationContent(
  classId: string,
  subject: string,
  studentId: string,
): Promise<RecommendedContentGroup[]> {
  const params = new URLSearchParams({
    class_id: classId,
    subject,
    student_id: studentId,
  });
  return request<RecommendedContentGroup[]>(
    `/targeted-improvement/recommendations/content?${params.toString()}`,
  );
}

/** 复测：对同一学生再跑一次 AI 诊断，返回 before(原诊断)/after(新诊断) 掌握率对比 */
export async function reevaluateDiagnosis(body: {
  class_id: string;
  student_id: string;
  subject: string;
}): Promise<{
  class_id: string;
  student_id: string;
  student_name: string;
  subject: string;
  before: any;
  after: any;
}> {
  return request("/targeted-improvement/re-evaluate", {
    method: "POST",
    body: JSON.stringify(body),
    timeout: 120_000,
  });
}

// ---- 课堂讲评 API ----

export interface ClassReviewReport {
  id: string;
  class_id: string;
  subject: string;
  title?: string;
  exam_names?: string[];
  imported_folder_names?: string[];
  source_summary?: any;
  pre_class?: any;
  tracking?: any;
  consolidation?: any;
  post_feedback?: any;
  generated_at?: string | null;
  updated_at?: string | null;
}

export async function listClassReviewSubjects(): Promise<string[]> {
  return request<string[]>("/class-review/subjects");
}

/** 课堂讲评历史：每班每科一条会话记录 */
export interface ClassReviewSessionItem {
  id: string;
  class_id: string;
  class_name: string;
  grade?: string;
  subject: string;
  title?: string;
  exam_names?: string[];
  imported_folder_names?: string[];
  generated_at?: string | null;
  updated_at?: string | null;
}

export async function listClassReviewSessions(): Promise<
  ClassReviewSessionItem[]
> {
  return request<ClassReviewSessionItem[]>("/class-review/sessions");
}

export async function getClassReviewReport(
  classId: string,
  subject: string,
): Promise<{ report: ClassReviewReport | null }> {
  const params = new URLSearchParams({ class_id: classId, subject });
  return request<{ report: ClassReviewReport | null }>(
    `/class-review/report?${params.toString()}`,
  );
}

/** 生成课堂讲评 PPT：POST /class-review/generate-pptx 返回二进制 .pptx（带鉴权，返回 Blob 供下载） */
export async function generateClassReviewPptx(
  classId: string,
  subject: string,
  questionKey?: string,
): Promise<Blob> {
  const token = await getAuthToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_PREFIX}/class-review/generate-pptx`, {
    method: "POST",
    headers,
    body: JSON.stringify(
      questionKey
        ? { class_id: classId, subject, question_key: questionKey }
        : { class_id: classId, subject },
    ),
  });

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    const message =
      (typeof errorBody.detail === "string" && errorBody.detail) ||
      errorBody.message ||
      "生成讲评 PPT 失败";
    throw new Error(message);
  }
  return res.blob();
}

export async function listClassReviewImportableExams(
  classId: string,
  subject: string,
): Promise<TargetedExamOption[]> {
  const params = new URLSearchParams({ class_id: classId, subject });
  return request<TargetedExamOption[]>(
    `/class-review/importable-exams?${params.toString()}`,
  );
}

export async function importClassReviewExams(body: {
  class_id: string;
  subject: string;
  exam_folder_names: string[];
}): Promise<{
  ok: boolean;
  report?: ClassReviewReport;
  pending?: boolean;
  completed_count?: number;
  record_count?: number;
  ignored_count: number;
  ignored_papers: Array<{ folder_name: string; filename: string }>;
}> {
  return request("/class-review/import-exams", {
    method: "POST",
    body: JSON.stringify(body),
    timeout: 180000,
  });
}

export async function generateClassReviewPostClass(body: {
  class_id: string;
  subject: string;
  taught_points: string[];
  mastered_points: string[];
  unresolved_points: string[];
  overall_effect: string;
  teacher_notes: string;
}): Promise<{ ok: boolean; report: ClassReviewReport }> {
  return request("/class-review/post-class", {
    method: "POST",
    body: JSON.stringify(body),
    timeout: 180000,
  });
}

// ---- 班级分析 API ----

export interface ClassAnalysisRanking {
  student_id: string;
  student_name: string;
  student_number?: string;
  score: number | null;
  rank: number;
  /** 等级代码（excellent/good/pass/needs_work）或 null；后端在 /class-analysis/report 的 rankings[].grade 返回 */
  grade?: GradeCode | null;
}

export interface ClassAnalysisExamSummary {
  exam_name: string;
  folder_name: string;
  order: number;
  participant_count: number;
  record_paper_count: number;
  average_score: number | null;
  median_score: number | null;
  highest_score: number | null;
  lowest_score: number | null;
  answer_area_count: number;
  wrong_count: number;
  blank_count: number;
  wrong_rate: number | null;
  rankings: ClassAnalysisRanking[];
}

export interface ClassAnalysisReport {
  id: string;
  class_id: string;
  class_name?: string;
  subject: string;
  exam_names: string[];
  imported_folder_names: string[];
  source_summary: {
    class?: {
      class_id?: string;
      class_name?: string;
      school_level?: string;
      grade?: string;
      student_count?: number;
    };
    overall_metrics?: {
      exam_count?: number;
      latest_average_score?: number | null;
      average_score_change?: number | null;
      record_paper_count?: number;
      image_count?: number;
      image_paper_coverage_rate?: number;
    };
    exam_summaries?: ClassAnalysisExamSummary[];
    ignored_paper_count?: number;
    vision_batch_count?: number;
    model?: string;
  };
  analysis: {
    overall_level?: {
      level?: string;
      summary?: string;
      trend?: string;
      score_interpretation?: string;
      strengths?: string[];
      data_notes?: string[];
    };
    knowledge_heatmap?: Array<{
      knowledge_point: string;
      values: Array<{
        exam_name: string;
        risk_score: number | null;
        evidence_count: number;
      }>;
      summary?: string;
    }>;
    weak_points?: Array<{
      knowledge_point: string;
      severity: "high" | "medium" | "low";
      affected_student_count: number;
      affected_students?: string[];
      evidence_exam_names?: string[];
      evidence?: string;
      teaching_suggestion?: string;
    }>;
    student_warnings?: Array<{
      student_id?: string;
      student_name: string;
      student_number?: string;
      risk_level: "high" | "medium";
      total_wrong_count?: number;
      warning_exams?: Array<{
        exam_name: string;
        wrong_count: number;
        class_average_wrong_count: number;
        warning_threshold: number;
        score?: number | null;
        rank?: number | null;
        top_wrong_titles?: string[];
      }>;
      reason?: string;
      suggestion?: string;
    }>;
    teaching_actions?: string[];
    /** 六维能力评测（跨班对标用）：维度名/本班得分/班级平均（学科对齐维度名） */
    capability_dimensions?: ClassCapabilityDimensions;
  };
  generated_at?: string;
  updated_at?: string;
}

export async function listClassAnalysisSubjects(): Promise<string[]> {
  return request<string[]>("/class-analysis/subjects");
}

export async function getClassAnalysisReport(
  classId: string,
  subject: string,
): Promise<{ report: ClassAnalysisReport | null }> {
  const params = new URLSearchParams({ class_id: classId, subject });
  return request<{ report: ClassAnalysisReport | null }>(
    `/class-analysis/report?${params.toString()}`,
  );
}

// ---- 班级知识点掌握度聚合（P4：由错题分布派生） ----
// 契约：GET /class-analysis/mastery-distribution?school_id=<必填>&class_id= → ApiResponse(data=[
//   { knowledge_point_id, name, mastery, wrong_count, total }
// ])。锚点是 name（id 多 NULL）；mastery = 1 - wrong_count/total（错题占比越低→掌握度越高），
// 由错题分布派生（非测评满分率）；后端已按 wrong_count 降序返回。
/** 知识点掌握度单点（GET /class-analysis/mastery-distribution 返回项） */
export interface ClassMasteryPoint {
  knowledge_point_id: string | null;
  name: string;
  /** 0-1，由错题分布派生（相对口径、真实但粗） */
  mastery: number;
  /** 该知识点错题数 */
  wrong_count: number;
  /** 当前范围内错题总数 */
  total: number;
}

/** 班级/学校知识点掌握度聚合：school_id 必填（防越权），class_id 班级维度 */
export async function getClassMasteryDistribution(
  schoolId: string,
  classId?: string,
): Promise<ClassMasteryPoint[]> {
  const params = new URLSearchParams({ school_id: schoolId });
  if (classId) params.set("class_id", classId);
  return request<ClassMasteryPoint[]>(
    `/class-analysis/mastery-distribution?${params.toString()}`,
  );
}

// ---- 跨班对标（年级内部对比）API ----

/** 六维能力单个维度（能力雷达用） */
export interface ClassCapabilityDimension {
  name: string;
  score: number;
  classAvg: number;
}

/** 六维能力评测结构（report.analysis.capability_dimensions） */
export interface ClassCapabilityDimensions {
  dims?: ClassCapabilityDimension[];
  level?: string;
  summary?: string;
}

/** 跨班对标：同年级某班的聚合指标 */
export interface GradeComparisonPeerClass {
  classId: string;
  className: string;
  averageScore: number;
  passRate: number;
  highestScore: number;
  trendDelta: number;
  isCurrent: boolean;
}

/** 跨班对标接口返回（GET /class-analysis/grade-comparison） */
export interface GradeComparisonData {
  currentClass: {
    classId: string;
    className: string;
    averageScore: number;
    passRate: number;
    rank: number;
    trendDelta: number;
    highestScore: number;
  };
  gradeAvg: {
    averageScore: number;
    passRate: number;
  };
  peerClasses: GradeComparisonPeerClass[];
  benchmarkClass: { className: string; averageScore: number } | null;
}

/** 获取同年级跨班对标数据 */
export async function getGradeComparison(
  classId: string,
  subject: string,
): Promise<GradeComparisonData> {
  const params = new URLSearchParams({ class_id: classId, subject });
  return request<GradeComparisonData>(
    `/class-analysis/grade-comparison?${params.toString()}`,
  );
}

export async function listClassAnalysisImportableExams(
  classId: string,
  subject: string,
): Promise<TargetedExamOption[]> {
  const params = new URLSearchParams({ class_id: classId, subject });
  return request<TargetedExamOption[]>(
    `/class-analysis/importable-exams?${params.toString()}`,
  );
}

export async function generateClassAnalysis(body: {
  class_id: string;
  subject: string;
  exam_folder_names: string[];
}): Promise<{
  ok: boolean;
  report: ClassAnalysisReport;
  ignored_count: number;
  ignored_papers: Array<{ folder_name: string; filename: string }>;
}> {
  return request("/class-analysis/analyze", {
    method: "POST",
    body: JSON.stringify(body),
    timeout: 900_000,
  });
}

// ---- 年级分析 API（跨班聚合） ----
// 契约：GET /class-analysis/grade-summary?grade=&subject= 返回 ApiResponse(data={...})，
// 前端 request 已解包 data，故 getGradeSummary 直接返回聚合对象本身。

/** 年级聚合：单班指标行 */
export interface GradeClassRow {
  classId: string;
  className: string;
  averageScore: number;
  passRate: number;
  excellentRate: number;
  highestScore: number | null;
  trendDelta: number;
}

/** 年级聚合：单班趋势序列 */
export interface GradeTrendPerClass {
  className: string;
  /** 与 examNames 对齐；无该次考试数据时为 null */
  scores: Array<number | null>;
}

/** 年级聚合：历次大考多班趋势 */
export interface GradeTrendSeries {
  examNames: string[];
  perClass: GradeTrendPerClass[];
}

/** 年级聚合：跨班共性薄弱点 */
export interface GradeWeakPoint {
  knowledge_point: string;
  avgRisk: number;
  affectedClasses: number;
  severity: "high" | "medium" | "low";
}

/** 年级聚合接口返回结构 */
export interface GradeSummaryData {
  grade: string;
  subject: string;
  totalStudents: number;
  subjectAverage: number;
  passRate: number;
  attentionCount: number;
  classRows: GradeClassRow[];
  trendSeries: GradeTrendSeries;
  weakPointsTop5: GradeWeakPoint[];
}

/** 年级分析聚合：同一年级多班核心指标、多班趋势、跨班薄弱点 */
export async function getGradeSummary(
  grade: string,
  subject: string,
): Promise<GradeSummaryData> {
  const params = new URLSearchParams({ grade, subject });
  return request<GradeSummaryData>(
    `/class-analysis/grade-summary?${params.toString()}`,
  );
}

// ---- 成绩等级 API（E04 隐私优先成绩单） ----
// 契约：等级代码由后端计算并返回（前端只映射文案，不做分数→等级换算）：
//   score>=85 → excellent / >=70 → good / >=60 → pass / <60 → needs_work；score 为空 → grade 为 null。
/** 成绩等级代码（VARCHAR 代码，不是中文文案） */
export type GradeCode = "excellent" | "good" | "pass" | "needs_work";

/** 后端成绩读写接口返回项：{ student_id, score, grade }（grade 为等级代码或 null） */
export interface ExamScoreApiItem {
  student_id: string;
  score: number | null;
  grade: GradeCode | null;
}

/** 按 exam 批量读分：GET /student-analysis/exam-scores?exam_id=... */
export async function getExamScores(
  examId: string,
): Promise<ExamScoreApiItem[]> {
  const params = new URLSearchParams({ exam_id: examId });
  return request<ExamScoreApiItem[]>(
    `/student-analysis/exam-scores?${params.toString()}`,
  );
}

/**
 * 按 exam 批量写分（upsert）：POST /student-analysis/exam-scores
 * body = [{ exam_id, student_id, score }]（JSON 数组），返回 upsert 后的 [{ student_id, score, grade }]
 */
export async function upsertExamScores(
  examId: string,
  scores: { student_id: string; score: number | null }[],
): Promise<void> {
  return request<void>("/student-analysis/exam-scores", {
    method: "POST",
    body: JSON.stringify(
      scores.map((s) => ({
        exam_id: examId,
        student_id: s.student_id,
        score: s.score,
      })),
    ),
  });
}

export async function listLessonPlans(params: {
  class_id: string;
  subject?: string;
}): Promise<LessonPlanApiRecord[]> {
  const search = new URLSearchParams();
  search.set("class_id", params.class_id);
  if (params.subject) search.set("subject", params.subject);
  return request<LessonPlanApiRecord[]>(`/lesson-plans?${search.toString()}`);
}

export async function createLessonPlan(body: {
  class_id: string;
  school_year?: string | null;
  term?: string | null;
  grade?: string | null;
  subject: string;
  title?: string;
  teaching_content?: string;
  teaching_objectives?: string;
  key_points?: string;
  difficult_points?: string;
  teaching_preparation?: string;
  teaching_process?: string;
  collective_preparation_advice?: string;
  blackboard_design?: string;
  teaching_reflection?: string;
  main_author?: string;
  deputy_author?: string;
  lesson_sequence?: string;
  completed_at?: string | null;
}): Promise<LessonPlanApiRecord> {
  return request<LessonPlanApiRecord>("/lesson-plans", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateLessonPlan(
  id: string,
  body: {
    school_year?: string | null;
    term?: string | null;
    grade?: string | null;
    subject?: string;
    title?: string;
    teaching_content?: string;
    teaching_objectives?: string;
    key_points?: string;
    difficult_points?: string;
    teaching_preparation?: string;
    teaching_process?: string;
    collective_preparation_advice?: string;
    blackboard_design?: string;
    teaching_reflection?: string;
    main_author?: string;
    deputy_author?: string;
    lesson_sequence?: string;
    completed_at?: string | null;
  },
): Promise<LessonPlanApiRecord> {
  return request<LessonPlanApiRecord>(`/lesson-plans/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteLessonPlan(id: string): Promise<void> {
  return request<void>(`/lesson-plans/${id}`, {
    method: "DELETE",
  });
}

export async function sendLessonPlanEmail(
  id: string,
  body: { pdf_base64: string; filename?: string; to_email?: string },
): Promise<{ ok: boolean; to_email?: string }> {
  return request<{ ok: boolean; to_email?: string }>(
    `/lesson-plans/${id}/send-email`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export async function sendExamEmail(body: {
  pdf_base64: string;
  filename?: string;
  to_email?: string;
}): Promise<{ ok: boolean; to_email?: string }> {
  return request<{ ok: boolean; to_email?: string }>(`/exams/send-email`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface AIGenerateExamRequest {
  topic?: string;
  topics?: string[];
  grade: string;
  term: string;
  difficulty: "简单" | "中等" | "偏难";
  subject?: string;
  requirements: { type: string; count: number; score: number }[];
}

export async function generateExamQuestionsByAI(
  body: AIGenerateExamRequest,
): Promise<any[]> {
  return request<any[]>("/exams/ai-generate", {
    method: "POST",
    body: JSON.stringify(body),
    timeout: 180_000, // 3 minutes timeout for AI generation
  });
}

// ---- 智能组卷试卷库 API ----
// 卷头可编辑字段（11.9-2）：只存老师改过的键，缺省键=前端默认文案
export interface ExamHeaderFields {
  class?: string;
  name?: string;
  number?: string;
  totalScore?: string;
}

export interface SmartExamPaperRecord {
  id: string;
  title: string;
  subject: string;
  questions: any[];
  header_fields?: ExamHeaderFields | null;
  updatedAt: string;
}

export async function listExamPapers(): Promise<SmartExamPaperRecord[]> {
  return request<SmartExamPaperRecord[]>("/exams/papers");
}

export async function createExamPaper(body: {
  title: string;
  subject: string;
  questions: any[];
  header_fields?: ExamHeaderFields | null;
}): Promise<SmartExamPaperRecord> {
  return request<SmartExamPaperRecord>("/exams/papers", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateExamPaper(
  id: string,
  body: {
    title: string;
    subject: string;
    questions: any[];
    header_fields?: ExamHeaderFields | null;
  },
): Promise<SmartExamPaperRecord> {
  return request<SmartExamPaperRecord>(`/exams/papers/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteExamPaper(id: string): Promise<void> {
  return request<void>(`/exams/papers/${id}`, {
    method: "DELETE",
  });
}

// ---- 考试记录 API（成绩管理页，走 FastAPI exams 表 CRUD，取代前端直连 Supabase） ----

export interface ExamRecord {
  id: string;
  user_id: string;
  class_id: string;
  subject: string;
  title: string;
  total_score: number;
  exam_date: string;
  created_at: string;
  updated_at: string;
}

/** 按班级列出考试记录（可按学科过滤），按 exam_date 降序 */
export async function listExams(
  classId: string,
  subject?: string,
): Promise<ExamRecord[]> {
  const params = new URLSearchParams({ class_id: classId });
  if (subject) params.set("subject", subject);
  return request<ExamRecord[]>(`/exams?${params.toString()}`);
}

/** 创建考试记录 */
export async function createExam(body: {
  class_id: string;
  subject: string;
  title: string;
  total_score: number;
  exam_date: string;
}): Promise<ExamRecord> {
  return request<ExamRecord>("/exams", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** 删除考试记录 */
export async function deleteExam(id: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/exams/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

// ---- 题型模板 API（组卷默认题型，走 FastAPI 取代 Supabase 直连） ----
export interface ExamTemplate {
  id: string;
  subject: string;
  type_name: string;
  default_count: number;
  default_score_each: number;
  sort_order: number;
}

/** 按学科列出题型模板（按 sort_order 升序） */
export async function listExamTemplates(
  subject: string,
): Promise<ExamTemplate[]> {
  const params = new URLSearchParams({ subject });
  return request<ExamTemplate[]>(`/exam-templates?${params.toString()}`);
}

/** 创建题型模板（user_id 由后端从当前登录用户取） */
export async function createExamTemplate(body: {
  subject: string;
  type_name: string;
  default_count: number;
  default_score_each: number;
  sort_order: number;
}): Promise<ExamTemplate> {
  return request<ExamTemplate>("/exam-templates", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** 更新题型模板 */
export async function updateExamTemplate(
  id: string,
  body: {
    type_name?: string;
    default_count?: number;
    default_score_each?: number;
  },
): Promise<ExamTemplate> {
  return request<ExamTemplate>(`/exam-templates/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

/** 删除题型模板 */
export async function deleteExamTemplate(id: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/exam-templates/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

/** 重排题型模板（orderedIds 顺序即新 sort_order） */
export async function reorderExamTemplates(
  orderedIds: string[],
): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/exam-templates/reorder", {
    method: "PATCH",
    body: JSON.stringify({ ordered_ids: orderedIds }),
  });
}

/** 批量初始化题型模板 */
export async function seedExamTemplates(
  subject: string,
  rows: {
    type_name: string;
    default_count: number;
    default_score_each: number;
    sort_order: number;
  }[],
): Promise<{ ok: boolean; inserted: number }> {
  return request<{ ok: boolean; inserted: number }>("/exam-templates/seed", {
    method: "POST",
    body: JSON.stringify({ subject, rows }),
  });
}

// ---- 知识点/单元 API（学科配置页，走 FastAPI 取代 Supabase 直连）----

/** subject_units 表原始行（后端返回原始行，前端按 unit_id 组装 Unit） */
export interface UnitRow {
  id: string;
  user_id: string;
  subject: string;
  semester: string;
  unit_index: number;
  name: string;
  subtitle: string | null;
}

/** knowledge_points 表原始行（后端返回原始行，前端按 unit_id 组装 KnowledgePoint） */
export interface KPRow {
  id: string;
  user_id: string;
  unit_id: string;
  code: string;
  name: string;
  level: string | null;
  mastery: number;
  is_weak: boolean;
  prerequisite: string[] | null;
  postrequisite: string[] | null;
  related: string[] | null;
  hours: number;
  key_point: string | null;
  difficulty: string | null;
  common_errors: string | null;
  resources: { type: string; name: string }[] | null;
}

/** GET /knowledge-data 返回：units/kps 均为原始行，isEmpty 为空态标记 */
export interface KnowledgeDataResponse {
  units: UnitRow[];
  kps: KPRow[];
  isEmpty: boolean;
}

/** 按学科+学期聚合查询单元与知识点（user_id 由后端从当前登录用户取） */
export async function listKnowledgeData(
  subject: string,
  semester: string,
): Promise<KnowledgeDataResponse> {
  const params = new URLSearchParams({ subject, semester });
  return request<KnowledgeDataResponse>(`/knowledge-data?${params.toString()}`);
}

/** 创建单条知识点（其余字段由后端取默认值） */
export async function createKnowledgePoint(body: {
  unit_id: string;
  code: string;
  name: string;
  level: string;
}): Promise<KPRow> {
  return request<KPRow>("/knowledge-data/knowledge-points", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** 更新知识点（body 为 KPRow 字段子集，id 在路径上） */
export async function updateKnowledgePoint(
  id: string,
  body: Partial<Omit<KPRow, "id" | "user_id">>,
): Promise<KPRow> {
  return request<KPRow>(
    `/knowledge-data/knowledge-points/${encodeURIComponent(id)}`,
    {
      method: "PATCH",
      body: JSON.stringify(body),
    },
  );
}

/** 删除知识点 */
export async function deleteKnowledgePoint(
  id: string,
): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(
    `/knowledge-data/knowledge-points/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  );
}

/** 事务初始化：批量插入 units + kps（user_id 由后端取，失败整体回滚） */
export async function seedKnowledgeData(body: {
  subject: string;
  semester: string;
  units: {
    unit_index: number;
    name: string;
    subtitle?: string | null;
    knowledgePoints: {
      code: string;
      name: string;
      level: string;
      mastery: number;
      is_weak: boolean;
      prerequisite: string[];
      postrequisite: string[];
      related: string[];
      hours: number;
      key_point: string;
      difficulty: string;
      common_errors: string;
      resources: { type: string; name: string }[];
    }[];
  }[];
}): Promise<{ units: UnitRow[]; kps: KPRow[] }> {
  return request<{ units: UnitRow[]; kps: KPRow[] }>("/knowledge-data/seed", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ---- 教材目录 & 教案模板 API ----
export interface TextbookCatalogNode {
  id: number | string;
  name: string;
  subject: string;
  edition: string;
  grade: string;
  level: "edition" | "unit" | "lesson";
  unit_index: number | null;
  parent_id: number | string | null;
}

export async function listTextbookCatalogs(params: {
  subject: string;
  edition?: string;
  grade?: string;
}): Promise<TextbookCatalogNode[]> {
  const search = new URLSearchParams();
  search.set("subject", params.subject);
  if (params.edition) search.set("edition", params.edition);
  if (params.grade) search.set("grade", params.grade);
  return request<TextbookCatalogNode[]>(
    `/textbook-catalogs?${search.toString()}`,
  );
}

/** 教材目录可用维度组合（学科×年级×版本 + 节点数），供四维定位矩阵同步真实目录数据 */
export interface TextbookCatalogPair {
  subject: string;
  grade?: string | null;
  edition?: string | null;
  node_count: number;
}

export interface TextbookCatalogOptions {
  editions: string[];
  subjects: string[];
  grades: string[];
  pairs: TextbookCatalogPair[];
}

export async function listTextbookCatalogOptions(): Promise<TextbookCatalogOptions> {
  return request<TextbookCatalogOptions>("/textbook-catalogs/options");
}

export interface LessonPlanTemplate {
  id: number | string;
  name: string;
  category: string;
  structure: Record<string, unknown>;
  description: string;
  is_active: boolean;
}

export async function listLessonPlanTemplates(): Promise<LessonPlanTemplate[]> {
  return request<LessonPlanTemplate[]>("/lesson-plan-templates");
}

// ---- AI 备课（分步确认式生成） ----
export interface AiGenerateOutlineRequest {
  subject: string;
  grade?: string;
  edition?: string;
  unit_name?: string;
  lesson_title: string;
  lesson_sequence?: string;
}

/** AI 备课第一步：生成教学大纲（不落库，供老师确认） */
export interface AiGenerateOutlineResult {
  title?: string;
  objectives?: string;
  key_points?: string;
  difficult_points?: string;
  process_summary?: Array<{ step?: string; point?: string }>;
}

export async function aiGenerateLessonPlanOutline(
  body: AiGenerateOutlineRequest,
): Promise<AiGenerateOutlineResult> {
  return request<AiGenerateOutlineResult>("/lesson-plans/ai-generate/outline", {
    method: "POST",
    body: JSON.stringify(body),
    timeout: 180_000, // AI 生成超时放宽到 3 分钟
  });
}

export interface AiGenerateFullRequest {
  class_id: string;
  outline: string;
  subject: string;
  grade?: string;
  edition?: string;
  unit_name?: string;
  lesson_title: string;
  lesson_sequence?: string;
}

/** AI 备课第二步：按确认大纲生成完整教案并落库 */
export async function aiGenerateLessonPlanFull(
  body: AiGenerateFullRequest,
): Promise<LessonPlanApiRecord> {
  return request<LessonPlanApiRecord>("/lesson-plans/ai-generate/full", {
    method: "POST",
    body: JSON.stringify(body),
    timeout: 180_000,
  });
}

// ---- AI 智能生成（互动课件 / 探究学案 / 多媒体资源） ----
export interface AiGenerateResourceRequest {
  gen_type: string;
  subject?: string;
  grade?: string;
  content: string;
  objective: string;
  student_profile: string;
  requirements: string;
}

export interface AiGenerateResourceResult {
  title: string;
  markdown: string;
}

export async function aiGenerateResource(
  body: AiGenerateResourceRequest,
): Promise<AiGenerateResourceResult> {
  return request<AiGenerateResourceResult>("/ai-resources/generate", {
    method: "POST",
    body: JSON.stringify(body),
    timeout: 180_000, // AI 生成超时放宽到 3 分钟
  });
}

/** 生成 PPT 课件：POST /ai-resources/generate-pptx 返回二进制 .pptx（带鉴权，返回 Blob 供下载） */
export async function generateCoursewarePptx(body: {
  title: string;
  markdown: string;
  subject?: string;
  grade?: string;
}): Promise<Blob> {
  const token = await getAuthToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_PREFIX}/ai-resources/generate-pptx`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    const message =
      (typeof errorBody.detail === "string" && errorBody.detail) ||
      errorBody.message ||
      "生成 PPT 失败";
    throw new Error(message);
  }
  return res.blob();
}

// ---- AI 生成历史（智能生成课件/学案/多媒体资源） ----
export interface AiGenerationHistorySummary {
  id: string;
  gen_type: string;
  subject: string;
  grade: string;
  title: string;
  created_at: string | null;
}

export interface AiGenerationHistoryItem extends AiGenerationHistorySummary {
  content: string;
}

export async function listAiGenerationHistory(): Promise<
  AiGenerationHistorySummary[]
> {
  return request<AiGenerationHistorySummary[]>("/ai-resources/history");
}

export async function getAiGenerationHistory(
  id: string,
): Promise<AiGenerationHistoryItem> {
  return request<AiGenerationHistoryItem>(`/ai-resources/history/${id}`);
}

// ---- 备课计划 API ----
export interface PrepPlanRecord {
  id: string;
  date: string;
  subject: string;
  content: string;
  completed: boolean;
  created_at?: string;
  updated_at?: string;
}

export async function listPrepPlans(
  start_date?: string,
  end_date?: string,
): Promise<PrepPlanRecord[]> {
  const params = new URLSearchParams();
  if (start_date) params.append("start_date", start_date);
  if (end_date) params.append("end_date", end_date);
  const q = params.toString();
  return request<PrepPlanRecord[]>(`/prep-plans${q ? `?${q}` : ""}`);
}

export async function createPrepPlan(body: {
  date: string;
  subject: string;
  content: string;
  completed?: boolean;
}): Promise<PrepPlanRecord> {
  return request<PrepPlanRecord>("/prep-plans", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updatePrepPlan(
  id: string,
  body: Partial<{
    date: string;
    subject: string;
    content: string;
    completed: boolean;
  }>,
): Promise<PrepPlanRecord> {
  return request<PrepPlanRecord>(`/prep-plans/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deletePrepPlan(id: string): Promise<void> {
  return request<void>(`/prep-plans/${id}`, {
    method: "DELETE",
  });
}

/** 班级教师列表 */
export async function listClassTeachers(
  classId: string,
): Promise<ClassTeacherRecord[]> {
  return request<ClassTeacherRecord[]>(
    `/classes/${encodeURIComponent(classId)}/teachers`,
  );
}

/** 添加协作教师（班主任 / 副班主任 / 教师） */
export async function addClassTeacher(
  classId: string,
  body: { email: string; role: "head" | "deputy" | "teacher" },
): Promise<ClassTeacherRecord> {
  return request<ClassTeacherRecord>(
    `/classes/${encodeURIComponent(classId)}/teachers`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

/** 修改协作教师类型 */
export async function patchClassTeacher(
  classId: string,
  ctId: string,
  body: { role: "head" | "deputy" | "teacher" },
): Promise<ClassTeacherRecord> {
  return request<ClassTeacherRecord>(
    `/classes/${encodeURIComponent(classId)}/teachers/${encodeURIComponent(ctId)}`,
    { method: "PATCH", body: JSON.stringify(body) },
  );
}

/** 移除协作教师 */
export async function deleteClassTeacher(
  classId: string,
  ctId: string,
): Promise<void> {
  return request<void>(
    `/classes/${encodeURIComponent(classId)}/teachers/${encodeURIComponent(ctId)}`,
    { method: "DELETE" },
  );
}

export async function leaveClass(classId: string): Promise<void> {
  return request<void>(`/classes/${encodeURIComponent(classId)}/leave`, {
    method: "POST",
  });
}

// ---- 资源库 API ----

/** 把多级相对路径逐段 URL 编码，但保留段与段之间的「/」（用于路径参数，如「一年级/语文」）。 */
function encodePath(p: string): string {
  return p.split("/").map(encodeURIComponent).join("/");
}

export interface ResourceFolder {
  name: string;
  created_at: string;
}

export interface ResourceFile {
  name: string;
  size: number;
  modified_at: string;
  url: string;
  cover_url?: string | null;
}

export async function listResourceFolders(
  path?: string,
): Promise<ResourceFolder[]> {
  const q = path ? `?path=${encodeURIComponent(path)}` : "";
  return request<ResourceFolder[]>(`/resources/folders${q}`);
}

export async function createResourceFolder(
  name: string,
  path?: string,
): Promise<ResourceFolder> {
  return request<ResourceFolder>("/resources/folders", {
    method: "POST",
    body: JSON.stringify({ name, path: path || "" }),
  });
}

export async function deleteResourceFolder(name: string): Promise<void> {
  return request<void>(`/resources/folders/${encodePath(name)}`, {
    method: "DELETE",
  });
}

export async function listResourceFiles(
  folderName: string,
): Promise<ResourceFile[]> {
  return request<ResourceFile[]>(
    `/resources/folders/${encodePath(folderName)}/files`,
  );
}

export async function uploadResourceFiles(
  folderName: string,
  files: File[],
): Promise<void> {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append("files", file);
  });

  const token = await getAuthToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(
    `${API_PREFIX}/resources/folders/${encodePath(folderName)}/files`,
    {
      method: "POST",
      headers,
      body: formData,
    },
  );

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    const message = errorBody.detail || errorBody.message || "上传失败";
    throw new Error(message);
  }
}

export async function deleteResourceFile(
  folderName: string,
  fileName: string,
): Promise<void> {
  return request<void>(
    `/resources/folders/${encodePath(folderName)}/files/${encodeURIComponent(fileName)}`,
    {
      method: "DELETE",
    },
  );
}

export async function renameResourceFile(
  folderName: string,
  fileName: string,
  newName: string,
): Promise<void> {
  return request<void>(
    `/resources/folders/${encodePath(folderName)}/files/${encodeURIComponent(fileName)}/rename`,
    {
      method: "PUT",
      body: JSON.stringify({ new_name: newName }),
    },
  );
}

export async function sendResourcesEmail(
  folderName: string,
  files: string[],
  toEmail?: string,
): Promise<{ ok: boolean; to_email?: string }> {
  return request<{ ok: boolean; to_email?: string }>("/resources/send-email", {
    method: "POST",
    body: JSON.stringify({ folder_name: folderName, files, to_email: toEmail }),
  });
}

export async function getAllUsers(): Promise<UserProfile[]> {
  return request<UserProfile[]>("/auth/users/all");
}

// ---- 学生 API（保留旧接口名兼容） ----

/** 获取班级列表（旧接口，按 grade_id；新逻辑请用 listClasses） */
export async function getClasses(gradeId?: string): Promise<ClassInfo[]> {
  const query = gradeId ? `?grade_id=${gradeId}` : "";
  return request<ClassInfo[]>(`/classes${query}`);
}

/** 获取学生列表（当前班级，走 FastAPI 后端） */
export async function listStudentsByClass(
  classId: string,
): Promise<StudentInfo[]> {
  if (!classId) return [];
  return request<StudentInfo[]>(
    `/students?class_id=${encodeURIComponent(classId)}`,
  );
}

/** 添加学生到班级 */
export async function createStudent(body: {
  class_id: string;
  name: string;
  student_number?: string;
  gender?: string;
}): Promise<StudentInfo> {
  return request<StudentInfo>("/students", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateStudent(
  studentId: string,
  body: Partial<{
    name: string;
    student_number: string;
    gender: string;
    tier: string;
    status: string;
    birthday: string;
    phone: string;
    parent_name: string;
    parent_phone: string;
    address: string;
    enroll_date: string;
    seat_row: number | null;
    seat_col: number | null;
    cadre_role: string;
    notes: string;
  }>,
): Promise<StudentInfo> {
  return request<StudentInfo>(`/students/${encodeURIComponent(studentId)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function batchCreateStudents(body: {
  class_id: string;
  students: { name: string; student_number: string; gender?: string }[];
}): Promise<number> {
  return request<number>("/students/batch", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** 删除学生 */
export async function importStudents(
  classId: string,
  file: File,
): Promise<number> {
  const formData = new FormData();
  formData.append("class_id", classId);
  formData.append("file", file);

  const token = await getAuthToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_PREFIX}/students/import`, {
    method: "POST",
    headers,
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "导入失败");
  }
  const json = await res.json();
  return json.data;
}

export async function globalImportStudents(
  file: File,
  fallbackClassId?: string,
): Promise<number> {
  const formData = new FormData();
  formData.append("file", file);
  if (fallbackClassId) {
    formData.append("fallback_class_id", fallbackClassId);
  }

  const token = await getAuthToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_PREFIX}/students/import/global`, {
    method: "POST",
    headers,
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "导入失败");
  }
  const json = await res.json();
  return json.data;
}

export async function deleteStudent(studentId: string): Promise<void> {
  return request<void>(`/students/${encodeURIComponent(studentId)}`, {
    method: "DELETE",
  });
}

export async function clearStudents(classId: string): Promise<void> {
  return request<void>(`/students/clear/${encodeURIComponent(classId)}`, {
    method: "DELETE",
  });
}

/** 批量导入管理员用户（Excel） */
export async function batchImportAdminUsers(
  file: File,
  callerPassword: string,
): Promise<{ success_count: number; errors: string[] }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("caller_password", callerPassword);

  const token = await getAuthToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_PREFIX}/admin/users/batch-import`, {
    method: "POST",
    headers,
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "导入失败");
  }
  const json = await res.json();
  return json.data;
}

/** 获取学生列表（旧接口名，兼容） */
export async function getStudents(classId: string): Promise<StudentInfo[]> {
  return listStudentsByClass(classId);
}

export interface GradingDataCleanupResult {
  ok: boolean;
  freed_bytes: number;
  freed_bytes_human: string;
  deleted_files: number;
  details: Record<string, { files: number; bytes: number }>;
}

/** 清理 grading_data 中的临时文件与孤儿缓存 */
export async function cleanupGradingData(): Promise<GradingDataCleanupResult> {
  return request<GradingDataCleanupResult>("/system/cleanup-grading-data", {
    method: "POST",
  });
}

export interface AdminUserBrief {
  id: string;
  email: string;
  display_name?: string | null;
  roles?: string[];
  created_at?: string | null;
}

export interface GradingFolderStat {
  folder_safe: string;
  folder_name: string;
  upload_count: number;
  grade_count: number;
}

export interface GradingStatsResponse {
  start_date: string;
  end_date: string;
  selected_user: {
    user_id: string;
    display_name?: string | null;
    email?: string | null;
    folders: GradingFolderStat[];
    total_upload: number;
    total_grade: number;
  } | null;
  all_users_summary: {
    total_upload: number;
    total_grade: number;
    users: Array<{
      user_id: string;
      display_name?: string | null;
      email?: string | null;
      upload_count: number;
      grade_count: number;
    }>;
  };
}

export async function listAdminUsers(): Promise<AdminUserBrief[]> {
  return request<AdminUserBrief[]>("/admin/users");
}

export interface DashboardOverview {
  users_count: number;
  class_count: number;
  student_count: number;
  exams_count: number;
  [k: string]: unknown;
}

export async function getDashboardOverview(): Promise<DashboardOverview> {
  return request<DashboardOverview>("/admin/dashboard/overview");
}

// ---- 管理端数据看板趋势（日 / 周 / 月聚合：批改量 / 预警数 / 兑换量）----

/** 趋势粒度：按天 / 按周 / 按月（GET /admin/dashboard/{period}） */
export type AdminTrendPeriod = "daily" | "weekly" | "monthly";

/** 单个时间桶（天 / 周 / 月）的聚合值 */
export interface AdminTrendPoint {
  period: string;
  label: string;
  grading_count: number;
  alert_count: number;
  redemption_count: number;
}

/** GET /admin/dashboard/{daily|weekly|monthly} 返回结构（request 已解包 { data }） */
export interface AdminTrendData {
  granularity: AdminTrendPeriod;
  days: number;
  start_date: string | null;
  end_date: string | null;
  periods: AdminTrendPoint[];
}

/** 管理端数据看板趋势：按天 / 周 / 月聚合批改量 / 预警数 / 兑换量 */
export async function getAdminDashboardTrend(
  period: AdminTrendPeriod,
  days?: number,
): Promise<AdminTrendData> {
  const params = new URLSearchParams();
  if (days !== undefined && days !== null) params.set("days", String(days));
  const q = params.toString();
  return request<AdminTrendData>(
    `/admin/dashboard/${period}${q ? `?${q}` : ""}`,
  );
}

export async function fetchAdminGradingStats(params: {
  start_date: string;
  end_date: string;
  user_id: string;
}): Promise<GradingStatsResponse> {
  const q = new URLSearchParams({
    start_date: params.start_date,
    end_date: params.end_date,
    user_id: params.user_id,
  });
  return request<GradingStatsResponse>(`/admin/grading-stats?${q.toString()}`);
}

// ---- 学校预警中心 API（GET /school/warnings，校级管理员；返回 summary + warnings + schoolName） ----

/** 学校预警汇总计数（summary 字段） */
export interface SchoolWarningSummary {
  total: number;
  red: number;
  yellow: number;
  green: number;
}

/** 学校预警中心接口返回结构（request 已解包 { data }） */
export interface SchoolWarningsData {
  summary: SchoolWarningSummary;
  warnings: WarningAlert[];
  schoolName: string;
}

/** 获取学校版预警列表与汇总（真实后端接口，不 mock） */
export async function getSchoolWarnings(): Promise<SchoolWarningsData> {
  return request<SchoolWarningsData>("/school/warnings");
}

// ---- 功能开关 API（E08 学校级 AI 管控；后端 MySQL 为唯一事实源） ----

/** 功能开关项（GET /feature-flags 返回的 data 数组元素） */
export interface FeatureFlagItem {
  key: string;
  label: string;
  enabled: boolean;
  scope: string;
  scope_id: string | null;
}

/** 获取全部功能开关（登录用户） */
export async function getFeatureFlags(): Promise<FeatureFlagItem[]> {
  return request<FeatureFlagItem[]>("/feature-flags");
}

/** 更新功能开关（仅系统管理员/子系统管理员） */
export async function updateFeatureFlag(
  key: string,
  enabled: boolean,
): Promise<{ key: string; enabled: boolean }> {
  return request<{ key: string; enabled: boolean }>(
    `/feature-flags/${encodeURIComponent(key)}`,
    { method: "PATCH", body: JSON.stringify({ enabled }) },
  );
}

// ---- 食堂电子台账 API（P0-4 纯软件 MVP，防篡改设计 = 只增不改） ----

/** 台账记录类型常量（后端 GET/POST /canteen/records 按 type 必填校验） */
export const CANTEEN_RECORD_TYPES = [
  "health_check",
  "sample",
  "accompany",
  "disinfection",
  "menu",
] as const;

export type CanteenRecordType = (typeof CANTEEN_RECORD_TYPES)[number];

/** 创建台账请求体（宽松 schema：type + date + 各类型专属字段，必填校验见后端） */
export interface CanteenRecordPayload {
  type: CanteenRecordType;
  date: string;
  // 晨检 health_check
  staff_name?: string;
  temperature?: number;
  health_status?: string;
  pass?: boolean;
  // 留样 sample
  meal_type?: string;
  dish_name?: string;
  sample_qty?: number;
  sampler_name?: string;
  storage_temp?: number;
  review_result?: string;
  // 陪餐 accompany
  person_name?: string;
  person_role?: string;
  comments?: string;
  // 消毒 disinfection
  area?: string;
  method?: string;
  operator_name?: string;
  result?: string;
  // 菜谱 menu
  dishes?: string;
  nutrition_note?: string;
}

/** 台账记录项（GET /canteen/records 的 items 元素：公共字段 + 各类型专属字段） */
export interface CanteenRecordItem {
  id: string;
  type: CanteenRecordType;
  date: string;
  occurred_at?: string | null;
  created_by?: string | null;
  // 晨检
  staff_name?: string | null;
  temperature?: number | null;
  health_status?: string | null;
  pass?: boolean | null;
  // 留样
  meal_type?: string | null;
  dish_name?: string | null;
  sample_qty?: number | null;
  sampler_name?: string | null;
  storage_temp?: number | null;
  review_result?: string | null;
  // 陪餐
  person_name?: string | null;
  person_role?: string | null;
  comments?: string | null;
  // 消毒
  area?: string | null;
  method?: string | null;
  operator_name?: string | null;
  result?: string | null;
  // 菜谱
  dishes?: string | null;
  nutrition_note?: string | null;
}

/** 创建一条食堂台账记录（返回落库后的记录，含 id） */
export async function createCanteenRecord(
  payload: CanteenRecordPayload,
): Promise<CanteenRecordItem> {
  return request<CanteenRecordItem>("/canteen/records", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** 分页查询某类型台账记录（type 必填，page_size 上限 100） */
export async function listCanteenRecords(params: {
  type: CanteenRecordType;
  page?: number;
  page_size?: number;
}): Promise<{
  type: string;
  items: CanteenRecordItem[];
  total: number;
  page: number;
  page_size: number;
}> {
  const search = new URLSearchParams();
  search.set("type", params.type);
  if (params.page !== undefined) search.set("page", String(params.page));
  if (params.page_size !== undefined)
    search.set("page_size", String(params.page_size));
  return request(`/canteen/records?${search.toString()}`);
}

// ---- 钉钉通讯录同步 ----

export interface DingtalkDepartment {
  dept_id: number;
  name: string;
  parent_id?: number;
}

export interface DingtalkSyncStatus {
  configured: boolean;
  synced_class_count: number;
  synced_student_count: number;
  /** 钉钉工作台入口链接（未配置时为 null） */
  entry_url?: string | null;
}

export interface DingtalkSyncResult {
  scope?: "class" | "student";
  departments: number;
  classes_created: number;
  classes_updated: number;
  students_created: number;
  students_updated: number;
}

export interface DingtalkSyncPayload {
  dept_id: number;
  school_level: "primary" | "junior" | "senior";
  grade: string;
  /** 同步范围：class=整班名单（默认） / student=只同步单个学生 */
  scope?: "class" | "student";
  /** scope=student 时必填：要同步的钉钉成员 userid */
  student_userid?: string;
}

/** 钉钉部门成员（选择「只同步单个学生」用） */
export interface DingtalkDeptUser {
  userid: string;
  name: string;
  mobile?: string;
}

/** 查询钉钉接入状态与已同步数量 */
export async function getDingtalkSyncStatus(): Promise<DingtalkSyncStatus> {
  return request<DingtalkSyncStatus>("/dingtalk/status");
}

/** 拉取钉钉全公司部门（选择器用） */
export async function listDingtalkDepartments(): Promise<DingtalkDepartment[]> {
  return request<DingtalkDepartment[]>("/dingtalk/departments");
}

/** 拉取某钉钉部门的成员列表（同步单个学生时选择用） */
export async function listDingtalkDeptUsers(
  deptId: number,
): Promise<DingtalkDeptUser[]> {
  return request<DingtalkDeptUser[]>(
    `/dingtalk/departments/${deptId}/users`,
  );
}

/** 同步指定钉钉部门（及其子部门）为班级+学生 */
export async function syncDingtalkClasses(
  payload: DingtalkSyncPayload,
): Promise<DingtalkSyncResult> {
  return request<DingtalkSyncResult>("/dingtalk/sync", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ---- 分层推送（nav/ai-layered）----

/** 分层名单行：学生 + 平均分 + 当前分层 + 钉钉同步状态（家长联系方式仅班主任可见） */
export interface LayeredRosterStudent {
  id: string;
  name: string;
  student_number?: string | null;
  tier?: string | null;
  score?: number | null;
  dingtalk_synced: boolean;
  parent_name?: string | null;
  parent_phone?: string | null;
}

/** 单层作业内容（存 system_config，读侧合并默认值） */
export interface LayeredTierContent {
  assignments: {
    title: string;
    desc?: string | null;
    icon?: string | null;
    exam_id?: string | null;
  }[];
  materials: { name: string; url: string }[];
  estimated_minutes: number;
  deadline_weekday: number; // 1=周一 … 7=周日
  deadline_time: string;
  require_parent_sign: boolean;
  require_photo: boolean;
  require_voice: boolean;
}

/** 分层推送设置（与后端 LayeredPushSettings 同构） */
export interface LayeredPushSettings {
  thresholds: { a: number; b: number };
  timing: { mode: "now" | "scheduled"; scheduled_at?: string | null; fired_at?: string | null };
  notify: { student: boolean; parent: boolean; reminder24h: boolean; late: boolean };
  form_type: "dingtalk" | "h5";
  tiers: Record<string, LayeredTierContent>;
  templates: { name: string; saved_at?: string | null; snapshot: Record<string, unknown> }[];
}

/** 最近一轮统计中的单层桶 */
export interface LayeredStatsTier {
  total: number;
  sent_ok: number;
  sent_failed: number;
  sent_skipped: number;
  sent_pending: number;
  parent_sent_ok: number;
  completed: number;
  unfinished: { task_id: string; name: string }[];
  read_count: number | null;
}

/** GET /layered-push/stats：最近一轮分层统计（未推送时 tiers 为空） */
export interface LayeredStats {
  round_id: string | null;
  round_index: number;
  rounds: number;
  tiers: Record<string, LayeredStatsTier>;
  updated_at?: string | null;
}

/** GET /layered-push/rounds：历史轮次（新→旧） */
export interface LayeredRound {
  round_id: string;
  total: number;
  sent_ok: number;
  sent_failed: number;
  completed: number;
  pushed_at?: string | null;
}

/** 真实名单（学生 + 平均分 + 分层 + 钉钉同步状态） */
export async function getLayeredRoster(
  classId: string,
  subject?: string,
): Promise<LayeredRosterStudent[]> {
  const params = new URLSearchParams({ class_id: classId });
  if (subject) params.set("subject", subject);
  return request<LayeredRosterStudent[]>(`/layered-push/roster?${params.toString()}`);
}

/** 按平均分自动分层（score≥a→A，≥b→B，其余 C；无成绩保持原分层） */
export async function autoTier(payload: {
  class_id: string;
  subject?: string;
  thresholds?: { a?: number; b?: number };
}): Promise<{ updated: number; no_score: number; tiers: Record<string, string[]> }> {
  return request("/layered-push/tiers/auto", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** 批量/拖拽调整分层 */
export async function batchMoveTiers(payload: {
  class_id: string;
  moves: { student_id: string; tier: "A" | "B" | "C" }[];
}): Promise<{ updated: number }> {
  return request("/layered-push/tiers/batch", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** 读取本班分层推送设置（未存过返回 null） */
export async function getLayeredPushSettings(
  classId: string,
  subject?: string,
): Promise<LayeredPushSettings | null> {
  const params = new URLSearchParams({ class_id: classId });
  if (subject) params.set("subject", subject);
  return request<LayeredPushSettings | null>(
    `/layered-push/settings?${params.toString()}`,
  );
}

/** 全量保存本班分层推送设置（仅班主任） */
export async function saveLayeredPushSettings(payload: {
  class_id: string;
  subject?: string;
  settings: LayeredPushSettings;
}): Promise<{ saved: boolean }> {
  return request("/layered-push/settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

/** 预览某一层真实会发出的钉钉消息（与推送同一拼装函数） */
export async function getMessagePreview(
  classId: string,
  subject: string,
  tier: string,
): Promise<{ title: string; body_markdown: string }> {
  const params = new URLSearchParams({ class_id: classId, tier });
  if (subject) params.set("subject", subject);
  return request(`/layered-push/message-preview?${params.toString()}`);
}

/** 测试推送：给当前老师本人发配置摘要，验证钉钉通道 */
export async function testPush(payload: {
  class_id: string;
  subject?: string;
}): Promise<{ ok: boolean; message: string }> {
  return request("/layered-push/test-push", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** 确认推送：立即返回轮次，后台线程逐学生发送并回写结果 */
export async function startPush(payload: {
  class_id: string;
  subject?: string;
  notice_only?: boolean;
  notice_text?: string;
}): Promise<{
  round_id: string;
  total: number;
  created_tasks: number;
  notice_only?: boolean;
}> {
  return request("/layered-push/push", {
    method: "POST",
    body: JSON.stringify(payload),
    timeout: 30000,
  });
}

/** 催交：对最近一轮未完成的学生（+家长）发提醒 */
export async function urgePush(payload: {
  class_id: string;
  subject?: string;
  tier?: "A" | "B" | "C";
}): Promise<{ sent: number; failed: number }> {
  return request("/layered-push/urge", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** 最近一轮的分层推送统计 */
export async function getLayeredStats(
  classId: string,
  subject?: string,
): Promise<LayeredStats> {
  const params = new URLSearchParams({ class_id: classId });
  if (subject) params.set("subject", subject);
  return request<LayeredStats>(`/layered-push/stats?${params.toString()}`);
}

/** 历史推送轮次（新→旧） */
export async function listLayeredRounds(
  classId: string,
  subject?: string,
): Promise<LayeredRound[]> {
  const params = new URLSearchParams({ class_id: classId });
  if (subject) params.set("subject", subject);
  return request<LayeredRound[]>(`/layered-push/rounds?${params.toString()}`);
}

/** 教师标记任务完成/未完成（完成状态以教师为准） */
export async function patchLayeredTaskStatus(
  taskId: string,
  status: "pending" | "completed",
): Promise<{ id: string; status: string }> {
  return request(`/layered-push/tasks/${encodeURIComponent(taskId)}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

/** 生成真实统计报告并发钉钉（本人/班主任） */
export async function sendLayeredReport(payload: {
  class_id: string;
  subject?: string;
  kind?: "weekly" | "round";
  recipient?: "self" | "head";
}): Promise<{ ok: boolean; message: string }> {
  return request("/layered-push/report", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** 按班级绑定的钉钉部门整班刷新名单（仅班主任） */
export async function syncLayeredRoster(payload: {
  class_id: string;
}): Promise<{ created: number; updated: number; total: number }> {
  return request("/layered-push/sync-roster", {
    method: "POST",
    body: JSON.stringify(payload),
    timeout: 60000,
  });
}

/** 资源文件下载链接（相对 API_PREFIX，配合 downloadResourceFile 带票下载） */
export function resourceDownloadUrl(folderName: string, fileName: string): string {
  return `/resources/folders/${encodePath(folderName)}/files/${encodeURIComponent(fileName)}/download`;
}

/** 带鉴权下载资源文件并触发浏览器保存 */
export async function downloadResourceFile(
  urlPath: string,
  fileName: string,
): Promise<void> {
  const token = await getAuthToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_PREFIX}${urlPath}`, { headers });
  if (!res.ok) throw new ApiError(res.status, `下载失败: ${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  a.click();
  URL.revokeObjectURL(url);
}
