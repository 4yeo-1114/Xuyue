import { describe, expect, it } from "vitest";
import {
  calcTaskProgress,
  extractTasksFromPlan,
  filterTasks,
} from "@/components/class-detail/targeted-improve/taskListUtils";

describe("extractTasksFromPlan", () => {
  it("extracts student_tasks from AI phases with stage labels", () => {
    const rows = extractTasksFromPlan({
      phases: [
        { title: "基础重建", student_tasks: ["任务A", "  任务B  ", ""] },
        { title: "巩固迁移", student_tasks: ["任务C"] },
      ],
    });
    expect(rows.map((r) => r.task_text)).toEqual(["任务A", "任务B", "任务C"]);
    expect(rows[0].stage_label).toBe("基础重建");
    expect(rows[2].stage_label).toBe("巩固迁移");
    expect(rows[2].sort_order).toBe(2);
  });

  it("extracts dailyTasks from demo stages and dedupes daily_routine", () => {
    const rows = extractTasksFromPlan({
      stages: [{ name: "基础重建", dailyTasks: ["观看微课"] }],
      daily_routine: ["每日复习", "观看微课"],
    });
    const texts = rows.map((r) => r.task_text);
    expect(texts).toEqual(["观看微课", "每日复习"]);
    expect(rows[1].stage_label).toBe("日常");
  });

  it("returns empty for null / non-object / empty plan", () => {
    expect(extractTasksFromPlan(null)).toEqual([]);
    expect(extractTasksFromPlan("x")).toEqual([]);
    expect(extractTasksFromPlan({})).toEqual([]);
  });
});

describe("calcTaskProgress", () => {
  it("computes total/done/percent", () => {
    expect(
      calcTaskProgress([
        { is_done: true },
        { is_done: false },
        { is_done: true },
        { is_done: false },
      ]),
    ).toEqual({ total: 4, done: 2, percent: 50 });
  });

  it("handles empty list as 0%", () => {
    expect(calcTaskProgress([])).toEqual({ total: 0, done: 0, percent: 0 });
  });
});

describe("filterTasks", () => {
  const tasks = [
    { id: "1", is_done: true },
    { id: "2", is_done: false },
    { id: "3", is_done: false },
  ];

  it("filters all / pending / done", () => {
    expect(filterTasks(tasks, "all")).toHaveLength(3);
    expect(filterTasks(tasks, "pending").map((t) => t.id)).toEqual(["2", "3"]);
    expect(filterTasks(tasks, "done").map((t) => t.id)).toEqual(["1"]);
  });
});
