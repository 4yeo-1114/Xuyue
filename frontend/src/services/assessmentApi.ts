/**
 * 测评域（B 域）API — 复用 api.ts 的 request<T>() 包装器：
 * fetch + Bearer token + 超时/重试 + 自动解包 {code, message, data}。
 */
import { request } from "@/services/api";

function qs(
  params?: Record<string, string | number | boolean | undefined | null>,
): string {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") {
        search.set(k, String(v));
      }
    }
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

// ── 类型定义 ──────────────────────────────────────────────

export type AssessmentDefinitionStatus = "draft" | "active" | "retired";
export type AssessmentSessionStatus =
  "pending" | "in_progress" | "submitted" | "graded" | "canceled";
export type AssessmentTestMode = "class_batch" | "self";
export type ConsentStatus = "not_required" | "granted" | "withdrawn";

export interface AssessmentOptionItem {
  key: string;
  text: string;
  dim: string;
  score?: number | null;
}

export interface AssessmentQuestionItem {
  id: string;
  dim: string;
  text: string;
  reverse_scored?: boolean | null;
  options: AssessmentOptionItem[];
}

export interface AssessmentDefinition {
  id: string;
  name: string;
  domain: string;
  grade_range: string;
  version: number;
  status: AssessmentDefinitionStatus;
  consent_required: boolean;
  description?: string | null;
  question_count: number;
  questions?: AssessmentQuestionItem[] | null;
  created_at: string;
}

export interface AssessmentDefinitionListData {
  rows: AssessmentDefinition[];
  total: number;
}

export interface AssessmentSession {
  id: string;
  student_id: string;
  student_name?: string | null;
  definition_id: string;
  definition_name?: string | null;
  test_mode: AssessmentTestMode;
  batch_id?: string | null;
  status: AssessmentSessionStatus;
  proctored_by?: string | null;
  created_by?: string | null;
  taken_at?: string | null;
  submitted_at?: string | null;
  created_at: string;
  updated_at: string;
  questions?: AssessmentQuestionItem[] | null;
}

export interface AssessmentSessionListData {
  rows: AssessmentSession[];
  total: number;
}

export interface AssessmentAnswerSubmit {
  question_id: string;
  option_key: string;
}

export interface AssessmentSubmitResult {
  result_id: string;
  session_id: string;
  labels: string[];
  dimension_percents: Record<string, number>;
  total_answered: number;
  consent_status: ConsentStatus;
}

export interface AssessmentGuardianConsent {
  status: ConsentStatus;
  version: number;
  granted_at?: string | null;
  withdrawn_at?: string | null;
}

export interface AssessmentTagSchema {
  labels?: string[];
  dimension_percents?: Record<string, number>;
  dimension_points?: Record<string, number>;
  generated_at?: string;
}

export interface AssessmentResult {
  id: string;
  student_id: string;
  definition_id?: string | null;
  definition_name?: string | null;
  domain: string;
  purpose: string;
  tag_schema: AssessmentTagSchema;
  raw_score?: unknown | null;
  guardian_consent: AssessmentGuardianConsent;
  session_id?: string | null;
  created_by?: string | null;
  created_at: string;
}

export interface AssessmentResultListData {
  rows: AssessmentResult[];
  total: number;
}

export interface AssessmentConsentOperation {
  id: string;
  guardian_consent: AssessmentGuardianConsent;
  updated_at?: string;
}

/** 批量同意总览 — 单条学生记录（取该生最新一条 result 的同意状态） */
export interface ConsentOverviewRecord {
  student_id: string;
  student_name: string;
  student_number: string | null;
  has_result: boolean;
  result_id: string | null; // 最新一条 result 的 id，无 result 则 null
  definition_name: string | null;
  domain: string | null;
  version: number; // 最新 result 的 guardian_consent.version，无则 0
  consent_status: ConsentStatus;
  created_at: string | null;
}

export interface ConsentsListData {
  rows: ConsentOverviewRecord[];
  total: number;
}

export interface ParentStudentRecord {
  id: string;
  parent_id: string;
  parent_name?: string | null;
  student_id: string;
  student_name?: string | null;
  relation: string;
  status: string;
  created_by?: string | null;
  created_at: string;
}

export interface ParentStudentListData {
  rows: ParentStudentRecord[];
  total: number;
}

// ── 7.1 题组定义 API ──────────────────────────────────────

export async function listAssessmentDefinitions(params?: {
  domain?: string;
  status?: AssessmentDefinitionStatus;
  brief?: boolean;
}): Promise<AssessmentDefinitionListData> {
  return request<AssessmentDefinitionListData>(
    `/assessment/definitions${qs({ ...params, brief: params?.brief ? "true" : undefined })}`,
  );
}

export async function getAssessmentDefinition(
  definitionId: string,
): Promise<AssessmentDefinition> {
  return request<AssessmentDefinition>(
    `/assessment/definitions/${encodeURIComponent(definitionId)}`,
  );
}

export async function createAssessmentDefinition(body: {
  name: string;
  domain: string;
  grade_range?: string;
  version?: number;
  status?: AssessmentDefinitionStatus;
  consent_required?: boolean;
  description?: string | null;
  questions: AssessmentQuestionItem[];
}): Promise<AssessmentDefinition> {
  return request<AssessmentDefinition>("/assessment/definitions", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateAssessmentDefinition(
  definitionId: string,
  body: Partial<{
    name: string;
    domain: string;
    grade_range: string;
    version: number;
    status: AssessmentDefinitionStatus;
    consent_required: boolean;
    description: string | null;
    questions: AssessmentQuestionItem[];
  }>,
): Promise<AssessmentDefinition> {
  return request<AssessmentDefinition>(
    `/assessment/definitions/${encodeURIComponent(definitionId)}`,
    {
      method: "PUT",
      body: JSON.stringify(body),
    },
  );
}

export async function deleteAssessmentDefinition(
  definitionId: string,
): Promise<{ id: string }> {
  return request<{ id: string }>(
    `/assessment/definitions/${encodeURIComponent(definitionId)}`,
    {
      method: "DELETE",
    },
  );
}

// ── 7.2 施测会话 API ──────────────────────────────────────

export async function createAssessmentSessions(body: {
  definition_id: string;
  test_mode?: AssessmentTestMode;
  student_ids?: string[];
  student_id?: string | null;
  batch_id?: string | null;
}): Promise<AssessmentSessionListData> {
  return request<AssessmentSessionListData>("/assessment/sessions", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listAssessmentSessions(params?: {
  student_id?: string;
  status?: AssessmentSessionStatus;
}): Promise<AssessmentSessionListData> {
  return request<AssessmentSessionListData>(
    `/assessment/sessions${qs(params)}`,
  );
}

export async function getAssessmentSession(
  sessionId: string,
): Promise<AssessmentSession> {
  return request<AssessmentSession>(
    `/assessment/sessions/${encodeURIComponent(sessionId)}`,
  );
}

export async function startAssessmentSession(
  sessionId: string,
): Promise<{ id: string; status: string }> {
  return request<{ id: string; status: string }>(
    `/assessment/sessions/${encodeURIComponent(sessionId)}/start`,
    {
      method: "POST",
    },
  );
}

export async function cancelAssessmentSession(
  sessionId: string,
): Promise<{ id: string; status: string; updated_at?: string }> {
  return request<{ id: string; status: string; updated_at?: string }>(
    `/assessment/sessions/${encodeURIComponent(sessionId)}/cancel`,
    { method: "POST" },
  );
}

// ── 7.3 作答与计分 API ────────────────────────────────────

export async function submitAssessmentAnswers(
  sessionId: string,
  answers: AssessmentAnswerSubmit[],
): Promise<AssessmentSubmitResult> {
  return request<AssessmentSubmitResult>(
    `/assessment/sessions/${encodeURIComponent(sessionId)}/answers`,
    {
      method: "POST",
      body: JSON.stringify({ answers }),
    },
  );
}

// ── 7.4 锚点结果 API ──────────────────────────────────────

export async function listStudentResults(
  studentId: string,
  params?: {
    domain?: string;
    include_withdrawn?: boolean;
    include_raw?: boolean;
  },
): Promise<AssessmentResultListData> {
  return request<AssessmentResultListData>(
    `/assessment/students/${encodeURIComponent(studentId)}/results${qs({
      ...params,
      include_withdrawn: params?.include_withdrawn ? "true" : undefined,
      include_raw: params?.include_raw ? "true" : undefined,
    })}`,
  );
}

// ── 7.5 监护人同意 API ────────────────────────────────────

export async function grantConsent(
  studentId: string,
  resultId: string,
): Promise<AssessmentConsentOperation> {
  return request<AssessmentConsentOperation>(
    `/assessment/students/${encodeURIComponent(studentId)}/results/${encodeURIComponent(resultId)}/grant`,
    { method: "POST" },
  );
}

export async function withdrawConsent(
  studentId: string,
  resultId: string,
): Promise<AssessmentConsentOperation> {
  return request<AssessmentConsentOperation>(
    `/assessment/students/${encodeURIComponent(studentId)}/results/${encodeURIComponent(resultId)}/withdraw`,
    { method: "POST" },
  );
}

export async function restoreConsent(
  studentId: string,
  resultId: string,
): Promise<AssessmentConsentOperation> {
  return request<AssessmentConsentOperation>(
    `/assessment/students/${encodeURIComponent(studentId)}/results/${encodeURIComponent(resultId)}/restore`,
    { method: "POST" },
  );
}

/** 班级同意状态总览（批量，替代逐学生 N+1 查询） */
export async function listClassConsents(
  classId: string,
): Promise<ConsentsListData> {
  return request<ConsentsListData>(
    `/assessment/classes/${encodeURIComponent(classId)}/consents`,
  );
}

// ── 7.6 家长-学生绑定 API ─────────────────────────────────

export async function createParentStudent(body: {
  parent_id: string;
  student_id: string;
  relation?: string;
}): Promise<ParentStudentRecord> {
  return request<ParentStudentRecord>("/parent-students", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listParentStudents(params?: {
  parent_id?: string;
  student_id?: string;
}): Promise<ParentStudentListData> {
  return request<ParentStudentListData>(`/parent-students${qs(params)}`);
}
