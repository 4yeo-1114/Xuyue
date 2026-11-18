import { API_PREFIX, API_BASE_URL } from "@/config/api";
import { readGlobalPrintPrefs } from "@/lib/globalPrintPrefs";
import {
  getAuthToken,
  submitGrading,
  getGradingRecords,
  getGradingResult,
  type GradingJobItem,
  type GradingRecentItem,
} from "@/services/api";

function buildUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return p.startsWith("http") ? p : `${API_BASE_URL}${p}`;
}

export async function gradingFetch<T = unknown>(
  path: string,
  options: Omit<RequestInit, "body"> & {
    body?: FormData | string | Record<string, unknown>;
  } = {},
): Promise<T> {
  const url = path.startsWith("/api")
    ? `${API_BASE_URL}${path}`
    : `${API_PREFIX}${path}`;
  const token = await getAuthToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (!(options.body instanceof FormData)) {
    if (
      typeof options.body === "object" &&
      options.body !== null &&
      !(options.body instanceof FormData)
    ) {
      headers["Content-Type"] = "application/json";
    }
  }
  const body =
    options.body instanceof FormData
      ? options.body
      : typeof options.body === "string"
        ? options.body
        : options.body
          ? JSON.stringify(options.body)
          : undefined;
  const res = await fetch(url, {
    ...options,
    headers: { ...headers, ...(options.headers as Record<string, string>) },
    body,
  });
  const text = await res.text();
  if (!res.ok) {
    let msg = text;
    try {
      const j = JSON.parse(text);
      msg = j.detail || j.message || text;
    } catch {
      //
    }
    const err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    // 附带 HTTP 状态码，供调用方区分 401/403（如 _require_local_admin）等语义
    (err as Error & { status?: number }).status = res.status;
    throw err;
  }
  if (!text) return undefined as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    return text as T;
  }
}

/** 快速批改：单张上传 */
export async function quickGrade(
  file: File,
): Promise<{
  ok: boolean;
  result: string;
  image_original?: string;
  image_annotated?: string;
  image_marks_only?: string;
}> {
  const form = new FormData();
  form.append("file", file);
  return gradingFetch<
    typeof quickGrade extends () => Promise<infer R> ? R : never
  >("/grading/quick", { method: "POST", body: form });
}

/** 首页最近作业列表项（与 src/services/api.ts 的 GradingRecentItem 同构，复用其定义避免双份漂移） */
export type HomeRecentItem = GradingRecentItem;

/** 快速批改：单张上传（复用 api.ts submitGrading → POST /grading/home/quick，保持原 { ok, job_id, item } 信封返回） */
export async function homeQuickGrade(
  file: File,
  anonymous = false,
): Promise<{
  ok: boolean;
  job_id: string;
  item: GradingJobItem;
}> {
  return submitGrading(file, undefined, anonymous);
}

/** 首页最近作业（复用 api.ts getGradingRecords → GET /grading/home/recent，保持原 { ok, items } 信封返回） */
export async function listHomeRecentGrades(): Promise<{
  ok: boolean;
  items: HomeRecentItem[];
}> {
  const items = await getGradingRecords();
  return { ok: true, items };
}

/** 首页作业详情（复用 api.ts getGradingResult → GET /grading/home/{job_id}，保持原 { ok, item } 信封返回） */
export async function getHomeGradeDetail(
  jobId: string,
): Promise<{ ok: boolean; item: GradingJobItem }> {
  const item = await getGradingResult(jobId);
  return { ok: true, item };
}

export async function deleteHomeGrade(jobId: string): Promise<{ ok: boolean }> {
  return gradingFetch(`/grading/home/${encodeURIComponent(jobId)}`, {
    method: "DELETE",
  });
}

/** 批量快速批改：多张上传，返回 batch_id */
export async function batchGradeStart(
  files: File[],
): Promise<{ ok: boolean; batch_id: string; total: number }> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  return gradingFetch("/grading/batch", { method: "POST", body: form });
}

/** 轮询批量批改进度 */
export async function batchGradeStatus(batch_id: string): Promise<{
  ok: boolean;
  total: number;
  completed: Array<{
    name: string;
    result: string;
    image_original?: string;
    image_annotated?: string;
    image_marks_only?: string;
  }>;
  failed: Array<{ name: string; msg: string }>;
}> {
  return gradingFetch(`/grading/batch/${batch_id}`);
}

/** 列出参照批改文件夹 */
export async function listFolders(
  classId?: string,
): Promise<{
  ok: boolean;
  folders: string[];
  meta?: Record<
    string,
    { subject?: string; grade?: string; homework_type?: string }
  >;
}> {
  const q = classId ? `?class_id=${encodeURIComponent(classId)}` : "";
  return gradingFetch(`/grading/folders${q}`);
}

/** 导出班级全部数据（zip）。GET /grading/folders/export?class_id=，返回 blob 由调用方触发浏览器下载。 */
export async function exportClassData(classId: string | number): Promise<Blob> {
  const token = await getAuthToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(
    buildUrl(
      `/api/v1/grading/folders/export?class_id=${encodeURIComponent(String(classId))}`,
    ),
    { headers },
  );
  if (!res.ok) {
    let msg = "导出失败";
    try {
      const text = await res.text();
      try {
        const j = JSON.parse(text);
        msg = j.detail || j.message || msg;
      } catch {
        msg = text || msg;
      }
    } catch {
      //
    }
    throw new Error(msg);
  }
  return await res.blob();
}

/** 导入班级数据 zip 的汇总结果，与后端 /grading/folders/import 响应逐字段对齐 */
export type ClassDataImportItem = {
  exam_name: string;
  reason: string;
};

export type ClassDataImportErrorItem = {
  name: string;
  message: string;
};

export type ClassDataImportResult = {
  ok: boolean;
  imported: string[];
  skipped: ClassDataImportItem[];
  errors: ClassDataImportErrorItem[];
};

/** 导入班级数据 zip（multipart: file + class_id），返回后端汇总结果。 */
export async function importClassData(
  file: File,
  classId: string | number,
): Promise<ClassDataImportResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("class_id", String(classId));
  return gradingFetch("/grading/folders/import", {
    method: "POST",
    body: form,
  });
}

/** 创建文件夹（R2 作业采集：可携带学科/年级/作业类型元数据） */
export async function createFolder(
  name: string,
  classId?: string,
  meta?: { subject?: string; grade?: string; homeworkType?: string },
): Promise<{ ok: boolean; name: string }> {
  return gradingFetch("/grading/folders", {
    method: "POST",
    body: {
      name,
      class_id: classId || undefined,
      subject: meta?.subject || undefined,
      grade: meta?.grade || undefined,
      homework_type: meta?.homeworkType || undefined,
    },
  });
}

export async function renameFolder(
  oldName: string,
  newName: string,
  meta?: { homeworkType?: string },
): Promise<{ ok: boolean; msg?: string }> {
  return gradingFetch("/grading/folders/rename", {
    method: "POST",
    body: {
      old_name: oldName,
      new_name: newName,
      homework_type: meta?.homeworkType || undefined,
    },
  });
}

export async function renameFolderFile(
  folderName: string,
  oldFilename: string,
  newFilename: string,
): Promise<{
  ok: boolean;
  name: string;
  filename: string;
  url: string;
  type?: string;
  msg?: string;
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/file/rename`,
    {
      method: "POST",
      body: { old_name: oldFilename, new_name: newFilename },
    },
  );
}

/** 批量删除文件夹（需登录密码确认） */
export async function deleteFolders(
  folderNames: string[],
  password: string,
): Promise<{ ok: boolean; msg?: string; deleted?: string[] }> {
  return gradingFetch("/grading/folders/delete", {
    method: "POST",
    body: { folder_names: folderNames, password },
  });
}

export type ReferenceLayoutRegion = {
  region_id?: string;
  label?: string;
  role?: string;
  order?: number;
  bbox: [number, number, number, number];
};

export type ReferenceLayoutAnswerSlot = {
  slot_id?: string;
  label?: string;
  order?: number;
  bbox?: [number, number, number, number];
  regions: ReferenceLayoutRegion[];
  has_handwriting_location?: boolean;
  max_score?: number;
};

export type ReferenceLayoutQuestion = {
  question_id: string;
  display_no: number;
  baidu_question_id?: number;
  question_type?: string;
  question_text?: string;
  regions: ReferenceLayoutRegion[];
  answer_slots: ReferenceLayoutAnswerSlot[];
};

export type ReferenceLayoutPage = {
  page_no: number;
  filename: string;
  image_url: string;
  image_size: [number, number];
  questions: ReferenceLayoutQuestion[];
};

export type ReferenceLayoutStatus = {
  confirmed: boolean;
  reviewed_pages: number[];
  stale_pages: number[];
  updated_at?: string | null;
};

/** 列出文件夹内文件 */
export async function listFolderFiles(folderName: string): Promise<{
  ok: boolean;
  files: Array<{ name: string; url: string }>;
  standard_answer: {
    name: string;
    filename: string;
    url: string;
    type?: string;
    page_no: number;
  } | null;
  standard_answers: Array<{
    name: string;
    filename: string;
    url: string;
    type?: string;
    page_no: number;
  }>;
  reference_layout?: ReferenceLayoutStatus;
  manual_layout?: ReferenceLayoutStatus;
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/files`,
  );
}

/** 仅识别标准答案并生成可人工校正的题目/作答区布局。 */
export async function prepareReferenceLayout(folderName: string): Promise<{
  ok: boolean;
  prepare_id: string;
  pages: ReferenceLayoutPage[];
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/reference-layout/prepare`,
    {
      method: "POST",
    },
  );
}

/** 读取已保存的切题布局用于查看或继续编辑，不会重新调用 OCR。 */
export async function getReferenceLayout(folderName: string): Promise<{
  ok: boolean;
  prepare_id: string;
  pages: ReferenceLayoutPage[];
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/reference-layout`,
  );
}

/** 保存人工拖动、拆分后的参照答案布局。 */
export async function confirmReferenceLayout(
  folderName: string,
  prepareId: string,
  pages: ReferenceLayoutPage[],
): Promise<{
  ok: boolean;
  confirmed: boolean;
  reference_layout: ReferenceLayoutStatus;
  updated_at?: string;
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/reference-layout/confirm`,
    {
      method: "POST",
      body: { prepare_id: prepareId, pages },
    },
  );
}

/** 11.11-11 每面切完单独保存：单页并进已保存布局，其余页不动（整卷 confirm 仍可用）。 */
export async function saveReferenceLayoutPage(
  folderName: string,
  prepareId: string,
  page: ReferenceLayoutPage,
): Promise<{
  ok: boolean;
  confirmed: boolean;
  reference_layout: ReferenceLayoutStatus;
  updated_at?: string;
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/reference-layout/save-page`,
    {
      method: "POST",
      body: { prepare_id: prepareId, page },
    },
  );
}

export type ReferenceAnswerSlotItem = {
  sub_index: number;
  bbox?: [number, number, number, number];
  answer_text: string;
  /** 答题区缩略图直链（服务端按 bbox 裁好、自带下载票），空白试卷识别答题区用 */
  region_url?: string;
};

/** 标准答案识别表条目：每题逐作答区答案（多空题 slots 按空拆分）。 */
export type ReferenceAnswerEntry = {
  display_index: number;
  printed_no?: string | null;
  question_bbox?: [number, number, number, number];
  slots: ReferenceAnswerSlotItem[];
  full_answer: string;
  edited?: boolean;
};

export type ReferenceAnswerTablePage = {
  page_no: number;
  filename: string;
  updated_at?: string | null;
  error?: string;
  questions: ReferenceAnswerEntry[];
  /** 答题区框总览底图直链（与切题审查同源预览图） */
  image_url?: string;
  /** 批改图像素尺寸：答题区框按这个坐标系铺 SVG（与切题审查同款拉伸对齐） */
  image_size?: [number, number] | null;
};

/** 自动识别标准答案每道题答案（已缓存则直接返回，可手动修改后保存）。 */
export async function getReferenceAnswerTable(
  folderName: string,
  build = true,
): Promise<{ ok: boolean; pages: ReferenceAnswerTablePage[] }> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/answer-table?build=${build ? 1 : 0}`,
  );
}

/** 保存老师对识别答案的手动修改（重建识别时保留）。 */
export async function saveReferenceAnswerTable(
  folderName: string,
  pageNo: number,
  questions: Array<{
    display_index: number;
    printed_no?: string;
    slots: Array<{ sub_index: number; answer_text: string }>;
  }>,
): Promise<{
  ok: boolean;
  page_no: number;
  updated_at?: string;
  questions: ReferenceAnswerEntry[];
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/answer-table/save`,
    {
      method: "POST",
      body: { page_no: pageNo, questions },
    },
  );
}

/** 强制重新识别答案表；resetEdits=true 连手动修改一起清掉。 */
export async function rebuildReferenceAnswerTable(
  folderName: string,
  pageNo?: number,
  resetEdits = false,
): Promise<{ ok: boolean; pages: ReferenceAnswerTablePage[] }> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/answer-table/rebuild`,
    {
      method: "POST",
      body: { page_no: pageNo ?? 0, reset_edits: resetEdits },
    },
  );
}

/** 答案纸识别结果（专窗）：每行 题号+答案，供老师核对后合并进答题区 */
export type AnswerSheetRow = { no: string; answer: string };

export async function getAnswerSheetRows(
  folderName: string,
  build = true,
): Promise<{
  ok: boolean;
  pages: Array<{ page_no: number; filename: string }>;
  rows: AnswerSheetRow[];
  error?: string;
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/answer-sheet?build=${build ? 1 : 0}`,
  );
}

/** 保存答案纸识别结果（专窗点「合并进答案表」）；rescan=true 重新识别 */
export async function saveAnswerSheetRows(
  folderName: string,
  payload: { rows?: AnswerSheetRow[]; rescan?: boolean },
): Promise<{ ok: boolean; rows: AnswerSheetRow[] }> {
  const body =
    payload.rescan
      ? { rescan: true }
      : {
          by_printed_no: Object.fromEntries(
            (payload.rows || [])
              .filter((row) => (row.answer || "").trim())
              .map((row) => [row.no, row.answer]),
          ),
        };
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/answer-sheet/save`,
    { method: "POST", body },
  );
}

/** 分析第一个学生试卷框，生成自主阅卷的可编辑切题模板。
 * source=answer_card（默认）：答题卡印刷框线切题；source=reference：取标准答题区
 * （试卷手动批改，普通试卷没有答题卡框线）。 */
export async function prepareManualLayout(
  folderName: string,
  source?: "answer_card" | "reference",
): Promise<{
  ok: boolean;
  prepare_id: string;
  pages: ReferenceLayoutPage[];
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/manual-layout/prepare`,
    {
      method: "POST",
      body: source ? { source } : undefined,
    },
  );
}

/** 读取已确认的自主阅卷切题与计分规则，不重新调用百度。 */
export async function getManualLayout(folderName: string): Promise<{
  ok: boolean;
  prepare_id: string;
  pages: ReferenceLayoutPage[];
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/manual-layout`,
  );
}

/** 保存自主阅卷切题坐标与每个作答区的满分。 */
export async function confirmManualLayout(
  folderName: string,
  prepareId: string,
  pages: ReferenceLayoutPage[],
): Promise<{
  ok: boolean;
  confirmed: boolean;
  manual_layout: ReferenceLayoutStatus;
  paper_count: number;
  updated_at?: string;
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/manual-layout/confirm`,
    {
      method: "POST",
      body: { prepare_id: prepareId, pages },
    },
  );
}

/** 卷面题号层级结构：{ 第N题: { major 大题号, sub 题号（小问/小题/大题）, display 组合展示, question_text 题目文字, printed_no 印刷题号 } } */
export type QuestionStructure = Record<
  string,
  {
    major: string;
    sub: string;
    display: string;
    question_text?: string;
    sub_sub?: string;
    printed_no?: string;
  }
>;

/** 已持久化的批改记录（AI 解析、留痕 URL 等），重启后仍可从磁盘加载 */
export async function fetchGradingHistory(
  folderName: string,
  engine?: GradingEngine,
): Promise<{
  ok: boolean;
  completed: Array<{
    name: string;
    result: string;
    image_original?: string;
    image_annotated?: string;
    image_marks_only?: string;
    marks_only_filename?: string;
  }>;
  failed: Array<{ name: string; msg: string }>;
  scoring_config?: Record<string, number>;
  missing_questions?: Record<
    string,
    { page_no: number; missing: string[]; expected_count: number; actual_count: number }
  >;
  inconsistent_count?: number;
  full_score?: number | null;
  question_structure?: QuestionStructure | null;
  major_scores?: Record<string, number> | null;
  major_order?: string[] | null;
  major_titles?: Record<string, string> | null;
  paper_subs?: Record<string, { num: string; score: number }[]> | null;
  hide_score_marks?: boolean;
}> {
  // manual 系引擎（manual_reference/manual_paper）与 manual 共用 __manual.json，
  // 后端 _grading_history_path 只认 "manual"——在此归一，免得每个调用点各自防。
  const query = engine ? `?engine=${manualHistoryEngine(engine)}` : "";
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/grading-history${query}`,
  );
}

/** 已持久化的作文批改记录（仅作文批改），重启后仍可从磁盘加载 */
export async function fetchEssayGradingHistory(folderName: string): Promise<{
  ok: boolean;
  completed: Array<{
    name: string;
    result: string;
    ocr_title?: string;
    ocr_content?: string;
    score_total?: number | null;
    essay_grade?: string | null;
    dimension_scores?: Record<string, number> | null;
  }>;
  failed: Array<{ name: string; msg: string }>;
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/essay-grading-history`,
  );
}

/** 最近批改过的文件夹（跨班级聚合），供「批改历史」页展示 */
export interface RecentHistoryFolder {
  folder_name: string;
  display_name: string;
  class_id: string;
  class_name?: string;
  grade?: string;
  subject?: string;
  homework_type?: string;
  status?: string;
  updated_at: string | null;
  engines: string[];
  completed: Array<{
    name: string;
    result?: string;
    image_original?: string;
    image_annotated?: string;
    image_marks_only?: string;
    [key: string]: unknown;
  }>;
  failed_count: number;
}

/** 拉取所有班级最近批改过的文件夹及每卷结果 */
export async function fetchRecentHistory(
  limit = 100,
): Promise<{ ok: boolean; folders: RecentHistoryFolder[] }> {
  return gradingFetch(`/grading/history-recent?limit=${limit}`);
}

/** 上传到文件夹（支持图片、PDF、Word） */
export async function uploadToFolder(
  folderName: string,
  file: File,
  isStandardAnswer: boolean,
  standardPageNo?: number,
): Promise<{
  ok: boolean;
  name: string;
  filename: string;
  url: string;
  type?: string;
  page_no?: number;
}> {
  const form = new FormData();
  form.append("file", file);
  form.append("is_standard_answer", isStandardAnswer ? "true" : "false");
  if (isStandardAnswer && standardPageNo != null) {
    form.append("standard_page_no", String(standardPageNo));
  }
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/upload`,
    { method: "POST", body: form },
  );
}

/** 上传原始试卷（含每题分值的那份卷子），用于识别每题分值 */
export async function uploadOriginalPaper(
  folderName: string,
  file: File,
  originalPageNo?: number,
): Promise<{
  ok: boolean;
  name: string;
  filename: string;
  url: string;
  type?: string;
  page_no?: number;
}> {
  const form = new FormData();
  form.append("file", file);
  form.append("is_original_paper", "true");
  if (originalPageNo != null) {
    form.append("original_page_no", String(originalPageNo));
  }
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/upload`,
    { method: "POST", body: form },
  );
}

/** 上传答案纸（答案单独一张纸，空白卷模式第二上传），按印刷题号识别每题答案 */
export async function uploadAnswerSheet(
  folderName: string,
  file: File,
  answerSheetPageNo?: number,
): Promise<{
  ok: boolean;
  name: string;
  filename: string;
  url: string;
  type?: string;
  page_no?: number;
}> {
  const form = new FormData();
  form.append("file", file);
  form.append("is_answer_sheet", "true");
  if (answerSheetPageNo != null) {
    form.append("answer_sheet_page_no", String(answerSheetPageNo));
  }
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/upload`,
    { method: "POST", body: form },
  );
}

/** 上传带标准答案的答题卡（参照批改（答题卡）单上传）：按印刷框线切格，
 * 逐格读出标准答案并保存，返回答案键值（与学生作答区同编号）+ 原文行 */
export async function extractAnswerKeyFromCard(
  folderName: string,
  file: File,
): Promise<{
  ok: boolean;
  answers: Record<string, string>;
  raw: string;
}> {
  const form = new FormData();
  form.append("file", file);
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/answer-key-from-card`,
    { method: "POST", body: form },
  );
}

/** 识别原始试卷上每题的分值（返回逐题清单，供确认页核对） */
export async function recognizePaperScores(folderName: string): Promise<{
  ok: boolean;
  items: { no: number; title: string; score: number }[];
  total: number;
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/original-paper/scores`,
    { method: "POST", body: {} },
  );
}

/** 确认页提交逐题分值（写回，切题时注入每题 max_score） */
export async function applyPaperScores(
  folderName: string,
  scores: Record<number, number>,
): Promise<{ ok: boolean; count: number }> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/original-paper/scores/apply`,
    { method: "POST", body: { scores } },
  );
}

/** 开始扫描导入：监测 scan 目录，新 PDF 复制到当前文件夹 */
export async function startScanImport(
  folderName: string,
): Promise<{ ok: boolean; msg?: string; folder_name?: string }> {
  return gradingFetch("/grading/scan-import/start", {
    method: "POST",
    body: { folder_name: folderName },
  });
}

/** 停止扫描导入。deleteImported=true =「取消并清除」：删掉本次会话已导入的文件并清残留、退面数（11.9-4） */
export async function stopScanImport(
  deleteImported = false,
): Promise<{ ok: boolean; msg?: string; deleted_imported?: number; deleted_pending?: number; refunded_pages?: number }> {
  return gradingFetch("/grading/scan-import/stop", {
    method: "POST",
    body: { delete_imported: deleteImported },
  });
}

/** 扫描导入状态 */
export async function getScanImportStatus(): Promise<{
  ok: boolean;
  running: boolean;
  folder_name?: string;
  imported_count?: number;
  error?: boolean;
  error_message?: string | null;
  last_error_at?: string | null;
}> {
  return gradingFetch("/grading/scan-import/status");
}

/** 主动触发扫描仪扫描一次（可选调用）。无扫描仪或调用失败时可靠 scan-import 目录监测自动导入降级。 */
export async function triggerScan(
  folderName: string,
  scannerId?: string,
): Promise<{
  ok: boolean;
  file_name?: string;
  saved_path?: string;
  msg?: string;
}> {
  const body: { folder_name: string; scanner_id?: string } = {
    folder_name: folderName,
  };
  if (scannerId) body.scanner_id = scannerId;
  return gradingFetch("/grading/scan/trigger", {
    method: "POST",
    body,
  });
}

/** 开始参照批改 */
export type GradingEngine =
  | "aliyun"
  | "baidu"
  | "essay"
  | "smart_ref"
  | "manual"
  | "manual_reference"
  | "manual_paper";

/** manual 系引擎（答题卡自主/参照、试卷手动）在批改历史里共用 __manual.json，统一归一 */
export function manualHistoryEngine(
  engine?: GradingEngine,
): "manual" | GradingEngine | undefined {
  return engine === "manual_reference" || engine === "manual_paper"
    ? "manual"
    : engine;
}

/** 自动补全「编辑批改」依赖的逐题数据：重批缺 blocks 的旧记录（不清空其它记录） */
export async function backfillBlocks(
  folderName: string,
  engine: GradingEngine = "aliyun",
): Promise<{
  ok: boolean;
  job_id: string | null;
  total: number;
  engine?: string;
  message?: string;
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/backfill-blocks`,
    {
      method: "POST",
      body: { engine },
    },
  );
}

export async function startReferenceGrade(
  folderName: string,
  engine: GradingEngine = "aliyun",
  singleFilename?: string | null,
  selectedFilenames?: string[] | null,
  pushDingtalk: boolean = true,
): Promise<{
  ok: boolean;
  job_id: string | null;
  total: number;
  /** ① 续批：全部试卷都已批改完成，没有需要续批的（job_id 为 null） */
  skipped_all?: boolean;
  skipped?: number;
}> {
  if (engine === "essay") {
    throw new Error("作文批改请使用 startEssayGrade()");
  }
  const body: {
    engine: GradingEngine;
    filename?: string;
    filenames?: string[];
    push_dingtalk?: boolean;
  } = { engine, push_dingtalk: pushDingtalk };
  const fn = typeof singleFilename === "string" ? singleFilename.trim() : "";
  if (fn) body.filename = fn;
  if (Array.isArray(selectedFilenames) && selectedFilenames.length > 0) {
    body.filenames = selectedFilenames
      .map((x) => String(x).trim())
      .filter(Boolean);
  }
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/grade-by-reference`,
    {
      method: "POST",
      body,
    },
  );
}

/** 轮询参照批改进度 */
export async function referenceGradeStatus(
  folderName: string,
  jobId: string,
): Promise<{
  ok: boolean;
  done?: boolean;
  total: number;
  current_name?: string | null;
  in_progress?: string[];
  /** 任务引擎（aliyun/baidu/smart_ref/manual/manual_paper/answer_key），前端选文案用 */
  engine?: string | null;
  /** true=在 heavy_slot 队列里等前面的重活，还没开始批 */
  queued?: boolean;
  /** ② 预处理阶段：recognizing=正在识别试卷（phase_done/phase_total），grading=逐卷批改中 */
  phase?: string | null;
  phase_done?: number;
  phase_total?: number;
  /** ② 重试中提示（如「网络异常，正在重试(2/3)…」），有值时优先显示 */
  retry_note?: string | null;
  completed: Array<{
    name: string;
    result: string;
    image_original?: string;
    image_annotated?: string;
    image_marks_only?: string;
  }>;
  failed: Array<{ name: string; msg: string }>;
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/grade-by-reference/status/${jobId}`,
  );
}

/** 停止当前一键批改任务 */
export async function cancelReferenceGrade(
  folderName: string,
  jobId: string,
): Promise<{ ok: boolean; msg?: string }> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/grade-by-reference/cancel`,
    {
      method: "POST",
      body: { job_id: jobId },
    },
  );
}

/**
 * 手动推送一次钉钉通知（「手动推送」模式下的按钮）。
 * kind: grading_done=智能/参照批改完成 / essay=作文批改 / manual=自主阅卷
 */
export async function pushDingtalkNotify(
  folderName: string,
  kind: "grading_done" | "essay" | "manual" = "grading_done",
): Promise<{ ok: boolean; message?: string }> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/dingtalk-notify`,
    {
      method: "POST",
      body: { kind },
    },
  );
}

// ---- 答题卡按标准答案比对（manual_reference）----

export type AnswerKeySaveResult = {
  ok: boolean;
  answers: Record<string, string>;
  raw: string;
  updated_at?: string;
};

/** 保存标准答案（文字 or 图片），后端解析为 {题号_空号: 答案}。 */
export async function saveAnswerKey(
  folderName: string,
  answerText: string,
  file?: File | null,
): Promise<AnswerKeySaveResult> {
  const path = `/grading/folders/${encodeURIComponent(folderName)}/answer-key`;
  if (file) {
    const form = new FormData();
    form.append("answer_text", answerText || "");
    form.append("file", file);
    return gradingFetch<AnswerKeySaveResult>(path, {
      method: "POST",
      body: form,
    });
  }
  return gradingFetch<AnswerKeySaveResult>(path, {
    method: "POST",
    body: { answer_text: answerText },
  });
}

/** 读取已保存的标准答案（回显）。includeTable=识别答案（识别列表）一并回显补缺。 */
export async function getAnswerKey(
  folderName: string,
  includeTable = false,
): Promise<AnswerKeySaveResult> {
  return gradingFetch<AnswerKeySaveResult>(
    `/grading/folders/${encodeURIComponent(folderName)}/answer-key${
      includeTable ? "?include_table=1" : ""
    }`,
  );
}

/** 按已保存的标准答案对文件夹内每张答题卡自动比对（异步）。 */
export async function gradeByAnswerKey(
  folderName: string,
): Promise<{ ok: boolean; job_id: string; total: number }> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/grade-by-answer-key`,
    { method: "POST" },
  );
}

/** 轮询答案比对进度（与参照批改进度同构）。 */
export async function answerKeyGradeStatus(
  folderName: string,
  jobId: string,
): Promise<{
  ok: boolean;
  done?: boolean;
  total: number;
  current_name?: string | null;
  in_progress?: string[];
  /** 任务引擎（answer_key），前端选文案用 */
  engine?: string | null;
  /** true=在 heavy_slot 队列里等前面的重活，还没开始批 */
  queued?: boolean;
  completed: Array<{
    name: string;
    result: string;
    image_original?: string;
    image_annotated?: string;
    image_marks_only?: string;
  }>;
  failed: Array<{ name: string; msg: string }>;
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/grade-by-answer-key/status/${jobId}`,
  );
}

/** 停止答案比对任务 */
export async function cancelAnswerKeyGrade(
  folderName: string,
  jobId: string,
): Promise<{ ok: boolean; msg?: string }> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/grade-by-answer-key/cancel`,
    { method: "POST", body: { job_id: jobId } },
  );
}

// ---- 作文批改规则 (Essay Rubric) API ----

export interface EssayRubric {
  id: string;
  name: string;
  content: string;
  summary_prompt?: string;
  comment_prompt?: string;
  rewrite_prompt?: string;
  guidance_prompt?: string;
  scoring_prompt?: string;
  topic_text?: string;
  topic_image_base64?: string;
  /** 评分维度配置（JSON 字符串数组，null/空 时后端使用默认五维） */
  dimensions_json?: string | null;
  created_at: string;
  updated_at: string;
}

/** 作文评分维度（A2 动态 Rubric）。key 与 completed.dimension_scores 的键一一对应。 */
export interface EssayDimension {
  key: string;
  name: string;
  full_score: number;
  weight: number;
  description?: string;
  order?: number;
}

/** 后端默认五维（dimensions_json 为空/无法解析时的兜底展示与编辑起点） */
export const DEFAULT_DIMENSIONS: EssayDimension[] = [
  {
    key: "content",
    name: "内容与立意",
    full_score: 25,
    weight: 0.25,
    description: "立意是否明确、材料是否充实、中心是否突出",
    order: 1,
  },
  {
    key: "structure",
    name: "结构与思路",
    full_score: 20,
    weight: 0.2,
    description: "开头/中段/结尾是否完整、过渡与层次是否清晰",
    order: 2,
  },
  {
    key: "language",
    name: "语言表达",
    full_score: 25,
    weight: 0.25,
    description: "用词、句式、文采、通顺度",
    order: 3,
  },
  {
    key: "relevance",
    name: "扣题程度",
    full_score: 15,
    weight: 0.15,
    description: "是否紧扣题目要求（结合 topic 判断偏题/跑题）",
    order: 4,
  },
  {
    key: "presentation",
    name: "卷面与篇幅",
    full_score: 15,
    weight: 0.15,
    description: "字数是否达标、卷面/书写",
    order: 5,
  },
];

/** 获取当前用户的作文批改规则列表 */
export async function getEssayRubrics(): Promise<EssayRubric[]> {
  const data = await gradingFetch<{ rubrics: EssayRubric[] }>(
    "/grading/rubrics",
  );
  return data?.rubrics || [];
}

/** 新建作文批改规则 */
export async function createEssayRubric(
  name: string,
  content: string,
  prompts?: Partial<EssayRubric>,
): Promise<EssayRubric> {
  const data = await gradingFetch<{ rubric: EssayRubric }>("/grading/rubrics", {
    method: "POST",
    body: { name, content, ...prompts },
  });
  return data.rubric;
}

/** 更新作文批改规则 */
export async function updateEssayRubric(
  id: string,
  content: string,
  name?: string,
  prompts?: Partial<EssayRubric>,
): Promise<EssayRubric> {
  const data = await gradingFetch<{ rubric: EssayRubric }>(
    `/grading/rubrics/${id}`,
    {
      method: "PUT",
      body: { content, name, ...prompts },
    },
  );
  return data.rubric;
}

/** 删除作文批改规则（批量） */
export async function deleteEssayRubrics(ids: string[]): Promise<void> {
  await gradingFetch("/grading/rubrics", {
    method: "DELETE",
    body: { ids },
  });
}

// ---- 作文批改（独立逻辑）----

export async function startEssayGrade(
  folderName: string,
  rubricText: string,
  singleFilename?: string | null,
  selectedFilenames?: string[] | null,
  prompts?: Partial<EssayRubric>,
  pushDingtalk: boolean = true,
): Promise<{ ok: boolean; job_id: string; total: number }> {
  const body: {
    rubric_text: string;
    filename?: string;
    filenames?: string[];
    summary_prompt?: string;
    comment_prompt?: string;
    rewrite_prompt?: string;
    guidance_prompt?: string;
    scoring_prompt?: string;
    topic_text?: string;
    topic_image_base64?: string;
    dimensions_json?: string | null;
    push_dingtalk?: boolean;
  } = {
    rubric_text: String(rubricText || "").trim(),
    push_dingtalk: pushDingtalk,
    ...prompts,
  };
  const fn = typeof singleFilename === "string" ? singleFilename.trim() : "";
  if (fn) body.filename = fn;
  if (Array.isArray(selectedFilenames) && selectedFilenames.length > 0) {
    body.filenames = selectedFilenames
      .map((x) => String(x).trim())
      .filter(Boolean);
  }
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/essay-grade/start`,
    {
      method: "POST",
      body,
    },
  );
}

export async function essayGradeStatus(
  folderName: string,
  jobId: string,
): Promise<{
  ok: boolean;
  total: number;
  current_name?: string | null;
  /** 任务引擎（essay），前端选文案用 */
  engine?: string | null;
  completed: Array<{
    name: string;
    result: string;
    ocr_title?: string;
    ocr_content?: string;
    score_total?: number | null;
    essay_grade?: string | null;
    dimension_scores?: Record<string, number> | null;
    dimensions?: EssayDimension[] | null;
  }>;
  failed: Array<{ name: string; msg: string }>;
  done?: boolean;
  cancelled?: boolean;
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/essay-grade/status/${jobId}`,
  );
}

export type EssayScorePayload = {
  filename: string;
  dimension_scores: Record<string, number>;
  total_score?: number;
  regenerate_report?: boolean;
};

export type EssayCompletedItem = {
  name: string;
  result: string;
  ocr_title?: string;
  ocr_content?: string;
  score_total?: number | null;
  essay_grade?: string | null;
  dimension_scores?: Record<string, number> | null;
  dimensions?: EssayDimension[] | null;
};

/** 作文改分：默认仅改分写记录（不重跑 AI）；regenerate_report=true 时用已存 OCR 重新生成点评 */
export async function saveEssayScore(
  folderName: string,
  payload: EssayScorePayload,
): Promise<{
  ok: boolean;
  msg?: string;
  completed?: EssayCompletedItem | null;
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/essay-grade/score`,
    {
      method: "POST",
      body: payload,
    },
  );
}

export type EssayResultPayload = {
  filename: string;
  result: string;
};

/** 作文文案手动修改：老师直接改 AI 写的评语/总评/建议等正文，整体替换 result */
export async function saveEssayResult(
  folderName: string,
  payload: EssayResultPayload,
): Promise<{
  ok: boolean;
  msg?: string;
  completed?: EssayCompletedItem | null;
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/essay-grade/result`,
    {
      method: "POST",
      body: payload,
    },
  );
}

export async function cancelEssayGrade(
  folderName: string,
  jobId: string,
): Promise<{ ok: boolean; msg?: string }> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/essay-grade/cancel`,
    {
      method: "POST",
      body: { job_id: jobId },
    },
  );
}

export type EssayPdfItem = {
  name: string;
  result: string;
  ocr_title?: string;
  ocr_content?: string;
  /** 留痕/原卷图片直链；下载「图片版 PDF」时用（只出图，不出批改报告） */
  image_original?: string | null;
  image_annotated?: string | null;
  image_marks_only?: string | null;
};

export async function downloadEssayGradePdf(
  folderName: string,
  items: EssayPdfItem[],
  filename?: string,
  options?: {
    /** "images" = 只出「原卷 + 留痕」图片（与预览一致）；默认 "report" = A4 文字报告 */
    mode?: "report" | "images";
    includeOriginal?: boolean;
    includeAnnotated?: boolean;
    /** 11.13 台账 #1/#2：按打印用途排版——双面=逐生独占整张纸，短边翻页=首面转 180°。
     *  仅打印走 true；下载保存保持自然页序（便于屏幕阅读）。 */
    duplexForPrint?: boolean;
  },
): Promise<Blob> {
  const token = await getAuthToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const isDoublePrint = (() => {
    try {
      return readGlobalPrintPrefs().print_mode === "double";
    } catch {
      return false;
    }
  })();
  const duplexDouble = !!options?.duplexForPrint && items.length > 1 && isDoublePrint;
  const duplexBinding =
    options?.duplexForPrint && isDoublePrint ? currentDuplexBinding() : "long";
  const res = await fetch(
    buildUrl(
      `/api/v1/grading/folders/${encodeURIComponent(folderName)}/essay-grade/pdf`,
    ),
    {
      method: "POST",
      headers,
      body: JSON.stringify({
        items,
        filename,
        mode: options?.mode ?? "report",
        include_original: options?.includeOriginal ?? true,
        include_annotated: options?.includeAnnotated ?? true,
        duplex_double: duplexDouble,
        duplex_binding: duplexBinding,
      }),
    },
  );
  if (!res.ok) {
    let msg = "下载失败";
    try {
      const text = await res.text();
      try {
        const j = JSON.parse(text);
        msg = j.detail || j.message || msg;
      } catch {
        msg = text || msg;
      }
    } catch {
      //
    }
    throw new Error(msg);
  }
  return await res.blob();
}

/** 11.13 台账 #2：双面打印的翻页方式（全局偏好）；单面打印时传 long（后端只在双面生效） */
function currentDuplexBinding(): "long" | "short" {
  try {
    return readGlobalPrintPrefs().duplex_binding === "short" ? "short" : "long";
  } catch {
    return "long";
  }
}

/** 输出留痕 PDF：把多张留痕图（modify 目录下文件名）合成一个 PDF 下载（每图一页），替代物理打印。
 *  printMode：single=单面页序原样；double/缺省=双面逐对对调送打（12→21、1234→2143，参照批改君）。 */
export async function downloadMarksPdf(
  filenames: string[],
  printMode?: "single" | "double",
): Promise<Blob> {
  const token = await getAuthToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(buildUrl(`/api/v1/grading/print-marks-pdf`), {
    method: "POST",
    headers,
    body: JSON.stringify({
      filenames,
      print_mode: printMode,
      duplex_binding: currentDuplexBinding(),
    }),
  });
  if (!res.ok) {
    let msg = "导出失败";
    try {
      const text = await res.text();
      try {
        const j = JSON.parse(text);
        msg = j.detail || j.message || msg;
      } catch {
        msg = text || msg;
      }
    } catch {
      //
    }
    throw new Error(msg);
  }
  return await res.blob();
}

/** 旋转某张试卷的原卷/留痕图（direction: left | right，每次 90°），用于纠正倒置/侧倒的扫描件。 */
export async function rotateImage(
  filename: string,
  direction: "left" | "right",
  folder?: string,
  rawName?: string,
): Promise<void> {
  const token = await getAuthToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(buildUrl(`/api/v1/grading/rotate-image`), {
    method: "POST",
    headers,
    body: JSON.stringify({ filename, direction, folder, raw_name: rawName }),
  });
  if (!res.ok) {
    let msg = "旋转失败";
    try {
      const text = await res.text();
      try {
        const j = JSON.parse(text);
        msg = j.detail || j.message || msg;
      } catch {
        msg = text || msg;
      }
    } catch {
      //
    }
    throw new Error(msg);
  }
}

/** 浏览器打印：下载留痕 PDF 并在新标签页打开，用浏览器自带打印对话框输出到本地物理打印机。 */
export async function browserPrintMarksPdf(
  filenames: string[],
  printMode?: "single" | "double",
): Promise<void> {
  const blob = await downloadMarksPdf(filenames, printMode);
  const url = URL.createObjectURL(blob);
  const win = window.open(url, "_blank");
  if (!win) {
    URL.revokeObjectURL(url);
    throw new Error("浏览器拦截了弹窗，请允许本站弹窗后重试");
  }
}

/** 触发浏览器下载 blob 为文件 */
export function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** 浏览器打开 blob 为新标签页（用于打印对话框）；被拦截时抛错 */
export function openBlobInNewTab(blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const win = window.open(url, "_blank");
  if (!win) {
    URL.revokeObjectURL(url);
    throw new Error("浏览器拦截了弹窗，请允许本站弹窗后重试");
  }
}

/** 导出留痕 PDF（下载保存），替代物理打印 */
export async function exportMarksPdf(
  filenames: string[],
  printMode?: "single" | "double",
  filename = "批改留痕.pdf",
): Promise<void> {
  const blob = await downloadMarksPdf(filenames, printMode);
  triggerBlobDownload(blob, filename);
}

/** 导出作文批改报告 PDF（下载保存），替代物理打印 */
export async function exportEssayGradePdf(
  folderName: string,
  items: EssayPdfItem[],
  filename: string,
): Promise<void> {
  const blob = await downloadEssayGradePdf(folderName, items, filename);
  triggerBlobDownload(blob, filename);
}

/** 浏览器打印作文批改报告：下载 PDF 后在新标签页打开 */
export async function browserPrintEssayGradePdf(
  folderName: string,
  items: EssayPdfItem[],
): Promise<void> {
  const blob = await downloadEssayGradePdf(folderName, items, undefined, {
    duplexForPrint: true,
  });
  openBlobInNewTab(blob);
}

export async function printEssayGradePdf(
  folderName: string,
  items: EssayPdfItem[],
  printerName?: string | null,
  paperSize: PrintPaperSize = "a4",
  customPaperMm?: CustomPaperMm,
  paperSource?: number | null,
  printMode: "single" | "double" = "single",
): Promise<{ ok: boolean; msg?: string }> {
  const body: any = {
    items,
    paper_size: paperSize,
    print_mode: printMode,
    duplex_binding: currentDuplexBinding(),
  };
  if (printerName) body.printer_name = printerName;
  if (paperSize === "custom" && customPaperMm) {
    body.custom_paper_width_mm = customPaperMm.widthMm;
    body.custom_paper_height_mm = customPaperMm.heightMm;
  }
  if (typeof paperSource === "number" && paperSource > 0)
    body.paper_source = paperSource;
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/essay-grade/print-pdf`,
    {
      method: "POST",
      body,
    },
  );
}

/** 11.13 台账 #3：按需生成作文留痕「只保留分数」变体（「打印批注」关时用）。
 * 已生成的会复用；返回 files[原文件名] = { marks_only_filename, image_marks_only } 或 { error }。 */
export async function ensureEssayScoreOnlyMarksApi(
  folderName: string,
  files: string[],
): Promise<{
  ok?: boolean;
  files: Record<
    string,
    { marks_only_filename?: string; image_marks_only?: string; error?: string }
  >;
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/essay-grade/score-only-marks`,
    {
      method: "POST",
      body: { files },
    },
  );
}

/** 打印机项（用于下拉与状态展示） */
export type PrinterItem = {
  name: string;
  is_default: boolean;
  status: number;
  status_text: string;
  ready: boolean;
  bins?: Array<{ id: number; name: string }>;
};

/** 获取本机打印机列表及状态 */
export async function listPrinters(): Promise<{
  ok: boolean;
  msg?: string;
  printers: PrinterItem[];
}> {
  return gradingFetch("/grading/printers");
}

/** 扫描仪项 */
export type ScannerItem = {
  id: string;
  name: string;
  manufacturer?: string;
  available: boolean;
};

/** 获取本机可用扫描仪列表 */
export async function listScanners(): Promise<{
  ok: boolean;
  msg?: string;
  scanners: ScannerItem[];
}> {
  return gradingFetch("/grading/scanners");
}

/** 纸张预设，与后端 /grading/print-marks 一致 */
export type PrintPaperSize =
  | "default"
  | "a3"
  | "a4"
  | "a5"
  | "b4"
  | "b5"
  | "letter"
  | "legal"
  | "tabloid"
  | "custom";

export type CustomPaperMm = {
  widthMm: number;
  heightMm: number;
};

/** 打印单张留痕图（filename 为 modify 目录下文件名；printerName 可选，不传用默认打印机） */
export async function printMarks(
  filename: string,
  printerName?: string | null,
  paperSize: PrintPaperSize = "a4",
  customPaperMm?: CustomPaperMm,
  paperSource?: number | null,
): Promise<{ ok: boolean; msg?: string }> {
  const body: any = {
    filename,
    paper_size: paperSize,
  };
  if (printerName) body.printer_name = printerName;
  if (paperSize === "custom" && customPaperMm) {
    body.custom_paper_width_mm = customPaperMm.widthMm;
    body.custom_paper_height_mm = customPaperMm.heightMm;
  }
  if (typeof paperSource === "number" && paperSource > 0)
    body.paper_source = paperSource;
  return gradingFetch("/grading/print-marks", { method: "POST", body });
}

/** 测试打印第一步：上传试卷（图片/PDF/Word）→ AI 批改 → 生成留痕，返回留痕文件名（第二步用 printMarks 打印） */
export async function printTestMarksGrade(
  file: File,
): Promise<{ ok: boolean; result?: string; marks_only_filename?: string }> {
  const form = new FormData();
  form.append("file", file);
  return gradingFetch("/grading/print-test-marks/grade", {
    method: "POST",
    body: form,
  });
}

/** 一键打印多张留痕图，按 filenames 顺序打印；printerName 可选 */
export async function printMarksBatch(
  filenames: string[],
  printerName?: string | null,
  paperSize: PrintPaperSize = "a4",
  customPaperMm?: CustomPaperMm,
  paperSource?: number | null,
): Promise<{
  ok: boolean;
  printed: number;
  errors: Array<{ filename: string; msg: string }>;
}> {
  const body: any = {
    filenames,
    paper_size: paperSize,
    duplex_binding: currentDuplexBinding(),
  };
  if (printerName) body.printer_name = printerName;
  if (paperSize === "custom" && customPaperMm) {
    body.custom_paper_width_mm = customPaperMm.widthMm;
    body.custom_paper_height_mm = customPaperMm.heightMm;
  }
  if (typeof paperSource === "number" && paperSource > 0)
    body.paper_source = paperSource;
  return gradingFetch("/grading/print-marks-batch", { method: "POST", body });
}

/** 启动后台批量打印任务，返回 job_id（可轮询/可取消） */
export async function startPrintMarksBatch(
  filenames: string[],
  printerName?: string | null,
  printMode: "single" | "double" = "single",
  paperSize: PrintPaperSize = "a4",
  customPaperMm?: CustomPaperMm,
  paperSource?: number | null,
): Promise<{ ok: boolean; job_id: string; total: number }> {
  const body: any = {
    filenames,
    print_mode: printMode,
    duplex_binding: currentDuplexBinding(),
    paper_size: paperSize,
  };
  if (printerName) body.printer_name = printerName;
  if (paperSize === "custom" && customPaperMm) {
    body.custom_paper_width_mm = customPaperMm.widthMm;
    body.custom_paper_height_mm = customPaperMm.heightMm;
  }
  if (typeof paperSource === "number" && paperSource > 0)
    body.paper_source = paperSource;
  return gradingFetch("/grading/print-marks-batch/start", {
    method: "POST",
    body,
  });
}

/** 查询后台批量打印任务状态 */
export async function printMarksBatchStatus(jobId: string): Promise<{
  ok: boolean;
  total: number;
  printed: number;
  errors: Array<{ filename: string; msg: string }>;
  done: boolean;
  cancelled: boolean;
  print_mode?: "single" | "double";
}> {
  return gradingFetch(`/grading/print-marks-batch/status/${jobId}`);
}

/** 取消后台批量打印任务 */
export async function cancelPrintMarksBatch(
  jobId: string,
): Promise<{ ok: boolean; msg?: string }> {
  return gradingFetch("/grading/print-marks-batch/cancel", {
    method: "POST",
    body: { job_id: jobId },
  });
}

/** 删除文件夹内文件（含标准答案） */
export async function deleteFolderFile(
  folderName: string,
  filename: string,
): Promise<{ ok: boolean }> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/file/${encodeURIComponent(filename)}`,
    { method: "DELETE" },
  );
}

/** 一键清空文件夹内试卷（需用户名+密码校验） */
export async function clearFolderFiles(
  folderName: string,
  username: string,
  password: string,
): Promise<{ ok: boolean; deleted: number }> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/files/clear`,
    {
      method: "POST",
      body: { username, password },
    },
  );
}

/** 批改结果图片完整 URL。
 * C6/H2：后端返回的文件/图片直链已自带 ?ticket= 短时下载票（或为普通路径），
 * img 标签无法带 Authorization Header，这里原样透传，不再把长期 JWT 拼进 URL。 */
export function gradingImageUrl(path: string | undefined): string {
  if (!path) return "";
  return path.startsWith("http") ? path : buildUrl(path);
}

/** 带鉴权获取批改文件为 Blob（用于 PDF 预览等） */
export async function fetchGradingFileBlob(path: string): Promise<Blob> {
  const url = path.startsWith("http") ? path : buildUrl(path);
  const token = await getAuthToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(url, { headers });
  if (!res.ok) throw new Error("加载文件失败");
  return res.blob();
}

/** 带鉴权获取批改文件为 ArrayBuffer（供 pdfjs 使用）。URL 与 gradingFetch 一致 */
export async function fetchGradingFileArrayBuffer(
  path: string,
  signal?: AbortSignal,
): Promise<ArrayBuffer> {
  const p = path.startsWith("/") ? path : `/${path}`;
  const url = p.startsWith("http")
    ? p
    : p.startsWith("/api")
      ? `${API_BASE_URL}${p}`
      : `${API_PREFIX}${p}`;
  const token = await getAuthToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(url, { headers, signal });
  if (!res.ok) {
    const text = await res.text();
    let msg = "加载文件失败";
    try {
      const j = JSON.parse(text);
      msg = j.detail || j.message || msg;
    } catch {
      if (res.status === 401) msg = "未登录或已过期";
      else if (res.status === 404) msg = "文件不存在";
    }
    throw new Error(msg);
  }
  return res.arrayBuffer();
}

/** 打包版：请求退出本机叙阅程序 */
export async function exitPackagedApp(): Promise<{
  ok: boolean;
  msg?: string;
}> {
  return gradingFetch("/system/exit", { method: "POST" });
}

// ---- 错题本 (Error Book) ----

export async function getErrorBookFolderStats(folderName: string): Promise<{
  ok: boolean;
  student_count: number;
  question_count: number;
  error_rate: number;
}> {
  return gradingFetch(
    `/grading/error-book/folders/${encodeURIComponent(folderName)}/stats`,
  );
}

export async function getErrorBookFolderDetail(folderName: string): Promise<{
  ok: boolean;
  source_engine?: string;
  questions: Array<{
    title: string;
    correct: number;
    wrong: number;
    blank: number;
    wrong_students: string[];
    subItems?: Array<{
      title: string;
      correct: number;
      wrong: number;
      blank: number;
      wrong_students: string[];
    }>;
  }>;
  question_pages?: Array<{
    page_no: number;
    label: string;
    questions: Array<{
      title: string;
      correct: number;
      wrong: number;
      blank: number;
      wrong_students: string[];
      subItems?: Array<{
        title: string;
        correct: number;
        wrong: number;
        blank: number;
        wrong_students: string[];
      }>;
    }>;
  }>;
  students: Array<{
    filename: string;
    source_filenames?: string[];
    correct_count: number;
    wrong_count: number;
    correct_questions: string[];
    wrong_questions: string[];
    score_total?: number | null;
    question_scores?: Record<string, number>;
  }>;
  scoring_config?: Record<string, number> | null;
}> {
  return gradingFetch(
    `/grading/error-book/folders/${encodeURIComponent(folderName)}/detail`,
  );
}

export async function saveManualGrade(
  folderName: string,
  filename: string,
  scores: Record<string, number | string>,
  generateMarks: boolean = true,
  questionNotes?: Record<string, string>,
  paperNote?: string,
  pushDingtalk: boolean = true,
  deductionItems?: DeductionItemsMap,
): Promise<{ ok: boolean; message?: string; item?: any }> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/manual-grade`,
    {
      method: "POST",
      body: {
        filename,
        scores,
        generate_marks: generateMarks,
        question_notes: questionNotes,
        paper_note: paperNote,
        push_dingtalk: pushDingtalk,
        // 省略 = 本次不改扣分项（后端 None 语义）；显式传（哪怕空对象）= 整体覆盖
        ...(deductionItems !== undefined ? { deduction_items: deductionItems } : {}),
      },
    },
  );
}

export type ManualSlotStatus =
  "ungraded" | "correct" | "wrong" | "unanswered" | "partial";

export type ManualSlotDecision = {
  status: ManualSlotStatus;
  score?: number | null;
};

/** 判错原因批注：item 级 wrong_annotations 映射的一条（key=题号） */
export type WrongAnnotation = {
  text: string;
  source: "ai" | "manual";
  edited: boolean;
  generated_at?: string;
};

export type WrongAnnotationsMap = Record<string, WrongAnnotation>;

/** 结构化扣分项一条：label=扣了什么，points=扣了多少（正数） */
export type DeductionItem = {
  label: string;
  points: number;
};

/** 结构化扣分项映射：key 与统分键一致（「第N题」「第N题-作答区M」） */
export type DeductionItemsMap = Record<string, DeductionItem[]>;

export async function saveManualSlotDecisions(
  folderName: string,
  filename: string,
  decisions: Record<string, ManualSlotDecision>,
  generateMarks: boolean = true,
  questionNotes?: Record<string, string>,
  paperNote?: string,
  pushDingtalk: boolean = true,
  wrongAnnotations?: WrongAnnotationsMap,
  deductionItems?: DeductionItemsMap,
): Promise<{ ok: boolean; message?: string; item?: any }> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/manual-grade`,
    {
      method: "POST",
      // Keep the legacy scores object so running backends that have not yet reloaded
      // the decisions-aware validator still accept this request.
      body: {
        filename,
        scores: {},
        decisions,
        generate_marks: generateMarks,
        question_notes: questionNotes,
        paper_note: paperNote,
        push_dingtalk: pushDingtalk,
        // 省略 = 本次不改批注（后端 None 语义）；显式传（哪怕空对象）= 整体覆盖
        ...(wrongAnnotations !== undefined ? { wrong_annotations: wrongAnnotations } : {}),
        // 省略 = 本次不改扣分项；显式传 = 整体覆盖
        ...(deductionItems !== undefined ? { deduction_items: deductionItems } : {}),
      },
    },
  );
}

export async function clearManualGrade(
  folderName: string,
  filename: string,
): Promise<{ ok: boolean; message?: string; item?: any }> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/manual-grade/clear`,
    {
      method: "POST",
      body: { filename },
    },
  );
}

/** 老师手动修正智能批改（baidu/smart_ref/aliyun）逐题对错，后端重画留痕并更新摘要 */
export async function correctAiBlocks(
  folderName: string,
  filename: string,
  engine: GradingEngine,
  blocks: Array<{
    index: number;
    sub_index?: number | null;
    result: "对" | "错" | "未作答";
    [key: string]: unknown;
  }>,
  questionNotes?: Record<string, string>,
  paperNote?: string,
  wrongAnnotations?: WrongAnnotationsMap,
  deductionItems?: DeductionItemsMap,
): Promise<{ ok: boolean; message?: string; item?: any }> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/ai-correct`,
    {
      method: "POST",
      body: {
        filename,
        engine,
        blocks,
        question_notes: questionNotes,
        paper_note: paperNote,
        // 省略 = 本次不改批注；显式传 = 整体覆盖保存
        ...(wrongAnnotations !== undefined ? { wrong_annotations: wrongAnnotations } : {}),
        // 省略 = 本次不改扣分项；显式传 = 整体覆盖保存
        ...(deductionItems !== undefined ? { deduction_items: deductionItems } : {}),
      },
    },
  );
}

/** 判错原因批注：AI 生成/重生成（单题或整卷），同步返回完整 wrong_annotations */
export async function generateWrongAnnotation(
  folderName: string,
  filename: string,
  engine: GradingEngine,
  questionKey?: string,
): Promise<{
  ok: boolean;
  wrong_annotations: WrongAnnotationsMap;
  generated: WrongAnnotationsMap;
  marks_with_wrong_notes_filename?: string | null;
  image_marks_with_wrong_notes?: string | null;
  annotated_with_wrong_notes_filename?: string | null;
  image_annotated_with_wrong_notes?: string | null;
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/wrong-annotation/generate`,
    {
      method: "POST",
      body: {
        filename,
        engine,
        ...(questionKey ? { question_key: questionKey } : {}),
      },
    },
  );
}

/** 判错原因批注：保存老师编辑/手写/删除后的整体映射（轻量，不重画留痕） */
export async function saveWrongAnnotations(
  folderName: string,
  filename: string,
  engine: GradingEngine,
  wrongAnnotations: WrongAnnotationsMap,
): Promise<{
  ok: boolean;
  wrong_annotations: WrongAnnotationsMap;
  marks_with_wrong_notes_filename?: string | null;
  image_marks_with_wrong_notes?: string | null;
  annotated_with_wrong_notes_filename?: string | null;
  image_annotated_with_wrong_notes?: string | null;
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/wrong-annotation/save`,
    {
      method: "POST",
      body: { filename, engine, wrong_annotations: wrongAnnotations },
    },
  );
}

/** 首页作业判错批注：整体覆盖保存 */
export async function saveHomeWrongAnnotations(
  jobId: string,
  wrongAnnotations: WrongAnnotationsMap,
): Promise<{ ok: boolean; wrong_annotations: WrongAnnotationsMap }> {
  return gradingFetch(
    `/grading/home/${encodeURIComponent(jobId)}/wrong-annotation/save`,
    {
      method: "POST",
      body: { wrong_annotations: wrongAnnotations },
    },
  );
}

/** 首页作业手动修正逐题对错/得分/评语（改小程序批改记录的主通道，进改分台账） */
export interface HomeAiCorrectBlock {
  index: number | string;
  sub_index?: number | string | null;
  result?: "对" | "错" | "半对" | "未作答";
  comment?: string;
  score?: number | null;
  partial_ratio?: number | null;
}

export async function correctHomeAiBlocks(
  jobId: string,
  blocks: HomeAiCorrectBlock[],
): Promise<{ ok: boolean; message?: string; item?: GradingJobItem }> {
  return gradingFetch(`/grading/home/${encodeURIComponent(jobId)}/ai-correct`, {
    method: "POST",
    body: { blocks },
  });
}

/** 首页作业判错批注：AI 生成/重生成（带 questionKey 单题覆盖，不带整卷补齐） */
export async function generateHomeWrongAnnotation(
  jobId: string,
  questionKey?: string,
): Promise<{
  ok: boolean;
  wrong_annotations: WrongAnnotationsMap;
  generated: WrongAnnotationsMap;
}> {
  return gradingFetch(
    `/grading/home/${encodeURIComponent(jobId)}/wrong-annotation/generate`,
    {
      method: "POST",
      body: { ...(questionKey ? { question_key: questionKey } : {}) },
    },
  );
}

/** 用文本大模型为整张试卷生成「整卷总评」（编辑批改里的 AI 总评） */
export async function aiPaperSummary(
  folderName: string,
  filename: string,
  engine: GradingEngine,
): Promise<{ ok: boolean; summary?: string; detail?: string }> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/ai-paper-summary`,
    {
      method: "POST",
      body: { filename, engine },
    },
  );
}

/** 保存作文「老师总评」并重绘卷面（尾批用老师总评替换，仅最后一页显示） */
export async function saveEssayNote(
  folderName: string,
  filename: string,
  paperNote: string,
): Promise<{ ok: boolean; message?: string; item?: any }> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/essay-note`,
    {
      method: "POST",
      body: { filename, paper_note: paperNote },
    },
  );
}

export async function saveScoringConfig(
  folderName: string,
  scoringConfig: any,
  fullScore?: number | null,
  questionStructure?: QuestionStructure | null,
  majorScores?: Record<string, number> | null,
  majorOrder?: string[] | null,
  majorTitles?: Record<string, string> | null,
  paperSubs?: Record<string, { num: string; score: number }[]> | null,
  hideScoreMarks?: boolean | null,
): Promise<{ ok: boolean; message?: string }> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/scoring-config`,
    {
      method: "POST",
      body: {
        scoring_config: scoringConfig,
        full_score: fullScore ?? undefined,
        question_structure: questionStructure ?? undefined,
        major_scores: majorScores ?? undefined,
        major_order: majorOrder ?? undefined,
        major_titles: majorTitles ?? undefined,
        paper_subs: paperSubs ?? undefined,
        // 「留痕不显示分数」开关（11.11-6）：null/undefined 不动已有持久值
        hide_score_marks: hideScoreMarks ?? undefined,
      },
    },
  );
}

export async function applyScoringConfig(
  folderName: string,
  scoringConfig: any,
  fullScore?: number | null,
  questionStructure?: QuestionStructure | null,
  majorScores?: Record<string, number> | null,
  majorOrder?: string[] | null,
  majorTitles?: Record<string, string> | null,
  paperSubs?: Record<string, { num: string; score: number }[]> | null,
  pushDingtalk: boolean = true,
): Promise<{
  ok: boolean;
  message?: string;
  applied_count?: number;
  question_titles?: string[];
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/scoring-config/apply`,
    {
      method: "POST",
      body: {
        scoring_config: scoringConfig,
        full_score: fullScore ?? undefined,
        question_structure: questionStructure ?? undefined,
        major_scores: majorScores ?? undefined,
        major_order: majorOrder ?? undefined,
        major_titles: majorTitles ?? undefined,
        paper_subs: paperSubs ?? undefined,
        push_dingtalk: pushDingtalk,
      },
    },
  );
}

/** AI 自动分配分值：返回 { 题目键: 满分 }，需用户确认后再「应用统分」 */
export async function autoScoringConfig(folderName: string): Promise<{
  ok: boolean;
  message?: string;
  scoring_config?: Record<string, number>;
  question_titles?: string[];
  full_score?: number;
  question_structure?: QuestionStructure;
  major_scores?: Record<string, number>;
  major_order?: string[];
  major_titles?: Record<string, string>;
  paper_subs?: Record<string, { num: string; score: number }[]>;
}> {
  return gradingFetch(
    `/grading/folders/${encodeURIComponent(folderName)}/scoring-config/auto`,
    {
      method: "POST",
    },
  );
}

// ---- 错题遗忘曲线复习 + 举一反三变式题推荐 (student-analysis) ----

export type WrongQuestionReviewItem = {
  id: string;
  class_id: string;
  student_id: string | null;
  student_name: string;
  subject: string;
  question_ref: string;
  question_title: string | null;
  image_url: string | null;
  error_type: string;
  review_count: number;
  last_reviewed_at: string | null;
  next_review_at: string | null;
  interval_days: number;
  created_at: string | null;
  /** 变式题推荐依据（同科目同类错题的举一反三说明） */
  reason?: string;
};

export type WrongQuestionReviewResult = "again" | "good" | "easy";

/** 到期复习列表：next_review_at <= 今天（subject 缺省返回班级各科目） */
export async function getWrongQuestionDueList(
  classId: string,
  subject?: string,
): Promise<{ code: number; message: string; data: WrongQuestionReviewItem[] }> {
  const params = new URLSearchParams({ class_id: classId });
  if (subject) params.set("subject", subject);
  return gradingFetch(
    `/student-analysis/wrong-questions/due?${params.toString()}`,
  );
}

/** 复习打卡：按简易 SM-2（again/good/easy）推进下次复习时间 */
export async function submitWrongQuestionReview(
  id: string,
  result: WrongQuestionReviewResult,
): Promise<{ code: number; message: string; data: WrongQuestionReviewItem }> {
  return gradingFetch(
    `/student-analysis/wrong-questions/${encodeURIComponent(id)}/review`,
    {
      method: "POST",
      body: { result },
    },
  );
}

/** 变式题推荐：同 subject + 同 error_type 的历史错题 top5 */
export async function getWrongQuestionVariants(
  id: string,
): Promise<{ code: number; message: string; data: WrongQuestionReviewItem[] }> {
  return gradingFetch(
    `/student-analysis/wrong-questions/${encodeURIComponent(id)}/variants`,
  );
}

// ── 流水阅卷 / 集体阅卷（flow）──

export type FlowReviewStatus = "correct" | "wrong" | "partial" | "unanswered";
export type FlowMark = { x: number; y: number; type: FlowReviewStatus };

export type FlowTaskItem = {
  assignment_id: string;
  batch_id: string;
  batch_name: string;
  subject: string;
  question_no: number;
  display_label: string;
  max_score: number;
  role: "single" | "first" | "second" | "arbiter";
  review_mode: "single" | "double";
  total_items: number;
  graded_items: number;
  progress: number;
};

export type FlowTaskDetail = FlowTaskItem & { standard_answer?: string | null };

export type FlowNextItem = {
  ok: boolean;
  claimed: boolean;
  item_id?: string;
  student_name?: string;
  student_number?: string;
  paper_name?: string;
  crop_url?: string;
  full_paper_url?: string;
  max_score?: number;
  standard_answer?: string | null;
  question_no?: number;
  display_label?: string;
};

export type FlowHistoryItem = {
  review_id: string;
  item_id: string;
  student_name: string;
  student_number: string;
  paper_name: string;
  crop_url?: string;
  score: number;
  status: FlowReviewStatus;
  comment?: string | null;
  marks?: FlowMark[] | null;
  round: number;
  is_current: boolean;
  revised_from?: string | null;
  submitted_at?: string | null;
};

export async function flowMyTasks(): Promise<{ ok: boolean; items: FlowTaskItem[] }> {
  return gradingFetch("/grading/flow/tasks");
}

export async function flowTaskDetail(
  assignmentId: string,
): Promise<{ ok: boolean } & FlowTaskDetail> {
  return gradingFetch(`/grading/flow/tasks/${encodeURIComponent(assignmentId)}`);
}

export async function flowNextItem(assignmentId: string): Promise<FlowNextItem> {
  return gradingFetch(`/grading/flow/tasks/${encodeURIComponent(assignmentId)}/next`);
}

export async function flowSubmitReview(payload: {
  assignment_id: string;
  item_id: string;
  score: number;
  status: FlowReviewStatus;
  marks?: FlowMark[];
  comment?: string;
}): Promise<{
  ok: boolean;
  review_id: string;
  finalized: boolean;
  final_score: number | null;
  need_arbitration: boolean;
}> {
  return gradingFetch("/grading/flow/reviews", { method: "POST", body: payload });
}

export async function flowReviseReview(
  reviewId: string,
  payload: { score?: number; status?: FlowReviewStatus; marks?: FlowMark[]; comment?: string },
): Promise<{ ok: boolean; review_id: string; final_score: number | null }> {
  return gradingFetch(`/grading/flow/reviews/${encodeURIComponent(reviewId)}/revise`, {
    method: "POST",
    body: payload,
  });
}

export async function flowTaskHistory(
  assignmentId: string,
): Promise<{ ok: boolean; items: FlowHistoryItem[] }> {
  return gradingFetch(`/grading/flow/tasks/${encodeURIComponent(assignmentId)}/history`);
}

export async function flowTaskSpeed(assignmentId: string): Promise<{
  ok: boolean;
  total_items: number;
  graded_items: number;
  progress: number;
  speed_per_min: number;
  rolling_speed_per_min: number;
  recent: Array<{ submitted_at: string | null; score: number }>;
}> {
  return gradingFetch(`/grading/flow/tasks/${encodeURIComponent(assignmentId)}/speed`);
}

// ── 管理端（运维）──

export type FlowBatchItem = {
  id: string;
  name: string;
  subject: string;
  grade?: string | null;
  status: string;
  review_mode: string;
  total_papers: number;
  created_at?: string | null;
};

export type FlowQuestionItem = {
  id: string;
  question_no: number;
  display_label: string;
  max_score: number;
  review_mode: string | null;
  status: string;
  total_items: number;
  graded_items: number;
};

export async function flowCreateBatch(payload: {
  name: string;
  subject: string;
  grade?: string;
  class_ids?: string[];
  source_folder_safe?: string;
  review_mode?: "single" | "double";
  resolver?: "roster" | "barcode";
  auto_objective?: boolean;
}): Promise<{ ok: boolean; batch_id: string; name: string; status: string }> {
  return gradingFetch("/admin/flow/batches", { method: "POST", body: payload });
}

export async function flowListBatches(): Promise<{ ok: boolean; items: FlowBatchItem[] }> {
  return gradingFetch("/admin/flow/batches");
}

export type FlowSourceFolder = {
  folder_name: string;
  display_name: string;
  has_layout: boolean;
};

export async function flowSourceFolders(): Promise<{ ok: boolean; folders: FlowSourceFolder[] }> {
  return gradingFetch("/admin/flow/source-folders");
}

export async function flowGetBatch(batchId: string): Promise<{
  ok: boolean;
  batch: FlowBatchItem;
  questions: FlowQuestionItem[];
}> {
  return gradingFetch(`/admin/flow/batches/${encodeURIComponent(batchId)}`);
}

export async function flowCutBatch(batchId: string): Promise<{ ok: boolean; status: string }> {
  return gradingFetch(`/admin/flow/batches/${encodeURIComponent(batchId)}/cut`, {
    method: "POST",
  });
}

export type FlowCropItem = {
  item_id: string;
  student_name: string | null;
  student_number: string | null;
  paper_name: string;
  crop_url: string;
  status: string;
};

export type FlowCropQuestion = {
  id: string;
  question_no: number;
  display_label: string;
  crop_dir: string | null;
  items: FlowCropItem[];
};

export async function flowBatchCrops(batchId: string): Promise<{ ok: boolean; questions: FlowCropQuestion[] }> {
  return gradingFetch(`/admin/flow/batches/${encodeURIComponent(batchId)}/crops`);
}

export async function flowCutStatus(batchId: string): Promise<{
  ok: boolean;
  status: string;
  processed: number;
  total: number;
  errors: Array<{ paper_name?: string; msg?: string }>;
  error_message?: string | null;
}> {
  return gradingFetch(`/admin/flow/batches/${encodeURIComponent(batchId)}/cut/status`);
}

export async function flowListTeachers(
  batchId: string,
  subject?: string,
): Promise<{
  ok: boolean;
  items: Array<{ user_id: string; display_name: string; teaching_subject?: string }>;
}> {
  const q = subject ? `?subject=${encodeURIComponent(subject)}` : "";
  return gradingFetch(`/admin/flow/batches/${encodeURIComponent(batchId)}/teachers${q}`);
}

export async function flowAssign(
  batchId: string,
  payload: {
    mode: "specified" | "random";
    max_teachers?: number;
    assignments?: Array<{ question_no: number; assignee_ids: string[] }>;
  },
): Promise<{ ok: boolean; created: Array<{ question_no: number; role: string; assignee_user_id: string }> }> {
  return gradingFetch(`/admin/flow/batches/${encodeURIComponent(batchId)}/assign`, {
    method: "POST",
    body: payload,
  });
}

export async function flowProgress(batchId: string): Promise<{
  ok: boolean;
  items: Array<{
    assignment_id: string;
    teacher_id: string;
    teacher_name: string;
    question_no: number;
    display_label: string;
    role: string;
    review_mode: string;
    total_items: number;
    graded_items: number;
    progress: number;
    speed_per_min: number;
    rolling_speed_per_min: number;
    last_submitted_at?: string | null;
  }>;
}> {
  return gradingFetch(`/admin/flow/batches/${encodeURIComponent(batchId)}/progress`);
}

export async function flowQuestionReviews(batchId: string, questionId: string): Promise<{
  ok: boolean;
  items: Array<{
    item_id: string;
    student_name: string;
    student_number: string;
    paper_name: string;
    crop_url: string;
    final_score: number | null;
    final_status: string | null;
    status: string;
    reviews: Array<{
      review_id: string;
      round: number;
      score: number;
      status: FlowReviewStatus;
      marks?: FlowMark[] | null;
      comment?: string | null;
      reviewer_user_id: string;
      submitted_at?: string | null;
    }>;
  }>;
}> {
  return gradingFetch(
    `/admin/flow/batches/${encodeURIComponent(batchId)}/questions/${encodeURIComponent(questionId)}/reviews`,
  );
}

export async function flowArbitrations(batchId: string): Promise<{
  ok: boolean;
  items: Array<{
    item_id: string;
    question_no: number | null;
    display_label: string;
    max_score: number;
    student_name: string;
    student_number: string;
    paper_name: string;
    crop_url: string;
    reviews: Array<{
      review_id: string;
      round: number;
      score: number;
      status: FlowReviewStatus;
      marks?: FlowMark[] | null;
      comment?: string | null;
      reviewer_user_id: string;
      submitted_at?: string | null;
    }>;
  }>;
}> {
  return gradingFetch(`/admin/flow/batches/${encodeURIComponent(batchId)}/arbitrations`);
}

export async function flowArbitrate(
  itemId: string,
  payload: { final_score: number; final_status?: FlowReviewStatus; reason?: string },
): Promise<{ ok: boolean; arbitration_id: string; final_score: number }> {
  return gradingFetch(`/admin/flow/arbitrations/${encodeURIComponent(itemId)}`, {
    method: "POST",
    body: payload,
  });
}

/** 修正/复核记账明细行（台账查看页） */
export type CorrectionLedgerRow = {
  id?: string | null;
  created_at?: string | null;
  paper_name?: string | null;
  folder_safe?: string | null;
  engine?: string | null;
  index?: string | null;
  sub_index?: string | null;
  source?: string | null;
  was_result?: string | null;
  new_result?: string | null;
  was_comment?: string | null;
  new_comment?: string | null;
  was_score?: number | null;
  new_score?: number | null;
  subject_family?: string | null;
  voided?: boolean;
};

/** 台账分类 chip/考试下拉的计数（各自维度不含自身过滤） */
export type CorrectionLedgerFacets = {
  source_counts?: Record<string, number>;
  folder_counts?: Array<{ folder?: string | null; count?: number }>;
};

/** 改分/评语台账明细：GET /grading/correction-ledger（分类/搜索/分页） */
export async function fetchCorrectionLedger(opts?: {
  days?: number;
  includeVoided?: boolean;
  /** 来源分类精确匹配（human_ai_correct/form_guard/vl_ink/…） */
  source?: string;
  /** 考试文件夹（folder_safe）精确匹配 */
  folder?: string;
  /** 改动类型：result 改判定 / score 改分 / comment 改评语 */
  changeKind?: string;
  /** 关键词模糊搜：学生卷名/考试名/评语 */
  q?: string;
  page?: number;
  pageSize?: number;
  /** 兼容旧调用：等价 pageSize */
  limit?: number;
}): Promise<{
  rows: CorrectionLedgerRow[];
  /** 过滤后总条数（分页母数） */
  count: number;
  total: number;
  page: number;
  page_size: number;
  source_counts: Record<string, number>;
  folder_counts: Array<{ folder?: string | null; count?: number }>;
  window_days: number;
  include_voided: boolean;
}> {
  const params = new URLSearchParams();
  if (opts?.days != null) params.set("days", String(opts.days));
  if (opts?.includeVoided) params.set("include_voided", "true");
  if (opts?.source) params.set("source", opts.source);
  if (opts?.folder) params.set("folder", opts.folder);
  if (opts?.changeKind) params.set("change_kind", opts.changeKind);
  if (opts?.q) params.set("q", opts.q);
  if (opts?.page != null) params.set("page", String(opts.page));
  const size = opts?.pageSize ?? opts?.limit;
  if (size != null) params.set("page_size", String(size));
  const qs = params.toString();
  // 端点包 ApiResponse{code,message,data}；按项目惯例在此拆信封（tolerant：裸 JSON 原样回）
  const json = await gradingFetch<{
    data?: CorrectionLedgerResponse;
    rows?: CorrectionLedgerRow[];
  }>(`/grading/correction-ledger${qs ? `?${qs}` : ""}`);
  const raw = (json?.data ?? json) as Partial<CorrectionLedgerResponse> & {
    rows?: CorrectionLedgerRow[];
  };
  const rows = raw.rows || [];
  const total = raw.total ?? raw.count ?? rows.length;
  return {
    rows,
    count: total,
    total,
    page: raw.page ?? 1,
    page_size: raw.page_size ?? rows.length,
    source_counts: raw.source_counts || {},
    folder_counts: raw.folder_counts || [],
    window_days: raw.window_days ?? 30,
    include_voided: Boolean(raw.include_voided),
  };
}

type CorrectionLedgerResponse = {
  rows: CorrectionLedgerRow[];
  count: number;
  total: number;
  page: number;
  page_size: number;
  source_counts: Record<string, number>;
  folder_counts: Array<{ folder?: string | null; count?: number }>;
  window_days: number;
  include_voided: boolean;
};

/** 改分/评语台账矩阵统计：GET /grading/correction-stats */
export async function fetchCorrectionStats(opts?: {
  days?: number;
  includeVoided?: boolean;
}): Promise<{
  matrix: Array<{
    source?: string | null;
    subject_family?: string | null;
    was?: string | null;
    new?: string | null;
    count?: number;
  }>;
  totals_by_source: Record<string, number>;
  window_days: number;
}> {
  const params = new URLSearchParams();
  if (opts?.days != null) params.set("days", String(opts.days));
  if (opts?.includeVoided) params.set("include_voided", "true");
  const qs = params.toString();
  // 同 fetchCorrectionLedger：端点包 ApiResponse 信封，在此拆掉（tolerant）
  const json = await gradingFetch<{
    data?: {
      matrix: Array<{
        source?: string | null;
        subject_family?: string | null;
        was?: string | null;
        new?: string | null;
        count?: number;
      }>;
      totals_by_source: Record<string, number>;
      window_days: number;
    };
  }>(`/grading/correction-stats${qs ? `?${qs}` : ""}`);
  return (json?.data ?? json) as {
    matrix: Array<{
      source?: string | null;
      subject_family?: string | null;
      was?: string | null;
      new?: string | null;
      count?: number;
    }>;
    totals_by_source: Record<string, number>;
    window_days: number;
  };
}
