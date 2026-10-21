/** 靶向任务清单纯函数：plan 解析预览 / 进度 / 筛选（供 UI 与 vitest 复用） */

export type TaskFilter = "all" | "pending" | "done";

export interface PlanTaskCandidate {
  task_text: string;
  stage_label: string;
  sort_order: number;
}

/** plan_json → 任务候选（与后端 _extract_tasks_from_plan 同口径，用于前端预览/测试） */
export function extractTasksFromPlan(plan: unknown): PlanTaskCandidate[] {
  if (!plan || typeof plan !== "object") return [];
  const p = plan as Record<string, unknown>;
  const collected: PlanTaskCandidate[] = [];
  const seen = new Set<string>();

  const push = (items: unknown, stageLabel: string) => {
    if (!Array.isArray(items)) return;
    for (const item of items) {
      const text = String(item ?? "")
        .trim()
        .replace(/\s+/g, " ");
      if (!text || seen.has(text)) continue;
      seen.add(text);
      collected.push({
        task_text: text,
        stage_label: stageLabel,
        sort_order: collected.length,
      });
    }
  };

  const phases = Array.isArray(p.phases) ? p.phases : [];
  phases.forEach((phase, idx) => {
    if (!phase || typeof phase !== "object") return;
    const ph = phase as Record<string, unknown>;
    const label = String(ph.title || ph.name || `阶段${idx + 1}`).trim();
    const src =
      ph.student_tasks || ph.studentTasks || ph.dailyTasks || ph.daily_tasks || [];
    push(src, label || `阶段${idx + 1}`);
  });

  const stages = Array.isArray(p.stages) ? p.stages : [];
  stages.forEach((stage, idx) => {
    if (!stage || typeof stage !== "object") return;
    const st = stage as Record<string, unknown>;
    const label = String(st.name || st.title || `阶段${idx + 1}`).trim();
    const src = st.dailyTasks || st.daily_tasks || st.student_tasks || [];
    push(src, label || `阶段${idx + 1}`);
  });

  push(p.daily_routine || p.dailyRoutine || [], "日常");
  return collected;
}

export interface TaskProgress {
  total: number;
  done: number;
  percent: number;
}

export function calcTaskProgress(tasks: Array<{ is_done: boolean }>): TaskProgress {
  const total = tasks.length;
  const done = tasks.filter((t) => t.is_done).length;
  return {
    total,
    done,
    percent: total === 0 ? 0 : Math.round((done / total) * 100),
  };
}

export function filterTasks<T extends { is_done: boolean }>(
  tasks: T[],
  filter: TaskFilter,
): T[] {
  if (filter === "pending") return tasks.filter((t) => !t.is_done);
  if (filter === "done") return tasks.filter((t) => t.is_done);
  return tasks;
}
