// ============================
// 前后端统一数据结构定义
// Python 工程师可据此实现 FastAPI Pydantic models
// ============================

/** 学段 */
export type SchoolLevel = "primary" | "junior" | "senior";

/** 批改任务状态 */
export type GradingStatus = "pending" | "processing" | "completed" | "failed";

/** 错题类型 */
export type ErrorType =
  "spelling" | "grammar" | "calculation" | "logic" | "concept" | "other";

/** 严重程度 */
export type Severity = "minor" | "moderate" | "major";

// ---- 请求类型 ----

/** 提交批改请求 */
export interface GradingSubmitRequest {
  school_level: SchoolLevel;
  grade: string;
  class_id: string;
  subject: string;
  /** Supabase Storage 中的文件路径列表 */
  file_urls: string[];
}

// ---- 响应类型 ----

/** 通用 API 响应包装 */
export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

/** 提交批改任务响应 */
export interface GradingSubmitResponse {
  task_id: string;
  status: GradingStatus;
}

/** 错题详情 */
export interface ErrorDetail {
  id: string;
  question_number: string;
  error_type: ErrorType;
  severity: Severity;
  description: string;
  correct_answer?: string;
  student_answer?: string;
  suggestion: string;
}

/** 批注 */
export interface Annotation {
  id: string;
  /** 页码（从1开始） */
  page: number;
  /** 坐标区域 [x, y, width, height] */
  region: [number, number, number, number];
  content: string;
  type: "correction" | "comment" | "highlight";
}

/** 批改结果 */
export interface GradingResult {
  task_id: string;
  status: GradingStatus;
  score?: number;
  total_score: number;
  annotations: Annotation[];
  errors: ErrorDetail[];
  summary?: string;
  created_at: string;
  completed_at?: string;
}

/** 学生信息 */
export interface StudentInfo {
  id: string;
  class_id: string;
  user_id: string;
  name: string;
  student_number: string;
  gender?: string | null;
  tier?: string | null;
  status?: string | null;
  birthday?: string | null;
  phone?: string | null;
  parent_name?: string | null;
  parent_phone?: string | null;
  address?: string | null;
  enroll_date?: string | null;
  seat_row?: number | null;
  seat_col?: number | null;
  cadre_role?: string | null;
  notes?: string | null;
  /** 钉钉成员 userid（已同步钉钉的学生有值） */
  dingtalk_userid?: string | null;
  created_at?: string;
  updated_at?: string;
}

/** 班级信息 */
export interface ClassInfo {
  id: string;
  name: string;
  grade: string;
  school_level: SchoolLevel;
  student_count: number;
}

/** 班级记录（与后端 /classes 接口一致） */
export interface ClassRecord {
  id: string;
  user_id: string;
  school_level: string;
  grade: string;
  name: string;
  student_count: number;
  created_at: string;
  updated_at: string;
  my_role?: string | null;
  is_owner?: boolean;
}

/** 班级教师（任课/班主任等） */
export interface ClassTeacherRecord {
  id: string;
  user_id: string;
  email: string;
  display_name?: string | null;
  role: string;
  subject?: string | null;
}

export interface UserProfile {
  id: string;
  email: string;
  display_name?: string | null;
  phone?: string | null;
  teaching_subject?: string | null;
  job_title?: string | null;
  personal_email?: string | null;
}
