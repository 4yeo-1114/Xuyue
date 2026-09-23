/** FastAPI 后端基础 URL。打包时 VITE_USE_RELATIVE_API=true 则用空字符串（相对路径，同源） */
const _useRelative =
  import.meta.env.VITE_USE_RELATIVE_API === "true" || import.meta.env.VITE_USE_RELATIVE_API === "1";
export const API_BASE_URL = _useRelative
  ? ""
  : (import.meta.env.VITE_API_BASE_URL || "http://localhost:6888");

/** API 版本前缀（旧接口） */
export const API_VERSION = "/api/v1";

/** 完整 API 前缀。打包时 API_BASE_URL 为空，则 API_PREFIX 为 /api/v1（相对路径） */
export const API_PREFIX =
  API_BASE_URL ? `${API_BASE_URL}${API_VERSION}` : API_VERSION;

/** 批改服务 FastAPI 基础 URL */
export const GRADING_API_BASE_URL =
  _useRelative ? "" : (import.meta.env.VITE_GRADING_API_BASE_URL || "http://localhost:6888");

/** 请求超时时间（毫秒） */
export const REQUEST_TIMEOUT = 30_000;

/** 最大重试次数 */
export const MAX_RETRIES = 2;

/** 批量任务轮询间隔（毫秒） */
export const GRADING_POLL_INTERVAL = 1500;
