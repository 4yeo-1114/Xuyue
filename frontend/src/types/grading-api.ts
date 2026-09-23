// ============================
// FastAPI 批改服务接口类型定义
// 对应 POST /api/grade, /api/grade-batch 等
// ============================

/** 通用响应基础 */
interface BaseResponse {
  ok: boolean;
  msg?: string;
}

// ---- 单张批改 ----

export interface GradeResponse extends BaseResponse {
  result: string;
  image_original: string;
  image_annotated: string;
  image_marks_only: string;
}

// ---- 批量批改 ----

export interface GradeBatchSubmitResponse extends BaseResponse {
  batch_id: string;
  total: number;
}

export interface GradeBatchCompletedItem {
  index: number;
  name: string;
  image_original: string;
  image_annotated: string;
  image_marks_only: string;
  result: string;
  marks_only_filename: string;
}

export interface GradeBatchFailedItem {
  index: number;
  name: string;
  msg: string;
}

export interface GradeBatchStatusResponse extends BaseResponse {
  total: number;
  completed: GradeBatchCompletedItem[];
  failed: GradeBatchFailedItem[];
}

// ---- 文件管理 ----

export interface FolderListResponse extends BaseResponse {
  folders: string[];
}

export interface FolderCreateResponse extends BaseResponse {
  name: string;
}

export interface FolderFileItem {
  name: string;
  url: string;
}

export interface StandardAnswerInfo {
  name: string;
  filename: string;
  url: string;
}

export interface FolderFilesResponse extends BaseResponse {
  files: FolderFileItem[];
  standard_answer: StandardAnswerInfo | null;
}

export interface FileUploadResponse extends BaseResponse {
  name: string;
  filename: string;
  url: string;
}

export interface FileDeleteResponse extends BaseResponse {
  deleted: number;
}

// ---- 参照标准答案批改 ----

export interface ReferenceGradeSubmitResponse extends BaseResponse {
  job_id: string;
  total: number;
}

export interface ReferenceGradeStatusResponse extends BaseResponse {
  folder_name: string;
  total: number;
  completed: GradeBatchCompletedItem[];
  failed: GradeBatchFailedItem[];
}

// ---- 打印 ----

export interface PrintResponse extends BaseResponse {
  printed?: number;
  errors?: Array<{ filename: string; msg: string }>;
}
