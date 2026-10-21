/** 靶向提升 · 个性化学习任务清单 API（客户功能 #15） */
import { request } from "@/services/api";

export interface TargetedTaskItem {
  id: string;
  class_id: string;
  student_id?: string | null;
  student_name: string;
  subject: string;
  report_id?: string | null;
  task_text: string;
  stage_label?: string;
  sort_order: number;
  is_done: boolean;
  done_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TargetedTaskListResult {
  tasks: TargetedTaskItem[];
  total: number;
  done: number;
}

export interface TargetedTaskSyncResult extends TargetedTaskListResult {
  ok: boolean;
  report_id: string;
  created_count: number;
  skipped_count: number;
}

export async function listTargetedTasks(params: {
  classId: string;
  subject: string;
  studentId?: string;
  studentName?: string;
  includeDone?: boolean;
}): Promise<TargetedTaskListResult> {
  const q = new URLSearchParams({
    class_id: params.classId,
    subject: params.subject,
  });
  if (params.studentId) q.set("student_id", params.studentId);
  if (params.studentName) q.set("student_name", params.studentName);
  q.set("include_done", params.includeDone === false ? "false" : "true");
  return request<TargetedTaskListResult>(
    `/targeted-improvement/tasks?${q.toString()}`,
  );
}

export async function syncTargetedTasks(body: {
  report_id?: string;
  class_id?: string;
  student_id?: string;
  student_name?: string;
  subject?: string;
}): Promise<TargetedTaskSyncResult> {
  return request<TargetedTaskSyncResult>("/targeted-improvement/tasks/sync", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateTargetedTask(
  taskId: string,
  isDone: boolean,
): Promise<TargetedTaskItem> {
  return request<TargetedTaskItem>(
    `/targeted-improvement/tasks/${encodeURIComponent(taskId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ is_done: isDone }),
    },
  );
}
