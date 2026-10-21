import { describe, expect, it } from "vitest";
import {
  buildAutoVariantsFolder,
  pickSessionExamName,
  pickSessionFolder,
  resolveAutoVariantsState,
  flattenAutoVariantDisplay,
} from "@/services/banditApi";
import type { AutoVariantsResult } from "@/services/banditApi";

describe("buildAutoVariantsFolder", () => {
  it("builds cls_{classId}__{examName}", () => {
    expect(buildAutoVariantsFolder("C1", "月考")).toBe("cls_C1__月考");
    expect(buildAutoVariantsFolder("C1", "  期中  ")).toBe("cls_C1__期中");
  });

  it("returns empty when class or exam missing", () => {
    expect(buildAutoVariantsFolder("", "月考")).toBe("");
    expect(buildAutoVariantsFolder("C1", "")).toBe("");
    expect(buildAutoVariantsFolder("  ", "  ")).toBe("");
  });
});

describe("pickSessionExamName / pickSessionFolder", () => {
  it("picks the most frequent exam_name", () => {
    const items = [
      { exam_name: "月考" },
      { exam_name: "月考" },
      { exam_name: "期中" },
      { exam_name: "暂无记录" },
      { exam_name: "" },
      null,
    ];
    expect(pickSessionExamName(items)).toBe("月考");
    expect(pickSessionFolder("C1", items)).toBe("cls_C1__月考");
  });

  it("keeps first occurrence on tie and ignores invalid", () => {
    expect(pickSessionExamName([{ exam_name: "A" }, { exam_name: "B" }])).toBe("A");
    expect(pickSessionExamName([{ exam_name: "暂无记录" }, {}])).toBe("");
    expect(pickSessionFolder("C1", [])).toBe("");
  });
});

describe("resolveAutoVariantsState", () => {
  const ready: AutoVariantsResult = {
    folder: "cls_C1__月考",
    status: "ready",
    items: [{ id: 1, question: "q", answer: "a", kp_name: "kp" }],
  };

  it("generating wins over everything", () => {
    expect(
      resolveAutoVariantsState({ data: ready, isGenerating: true, isFetching: true }),
    ).toBe("generating");
  });

  it("loading when fetching with no data", () => {
    expect(resolveAutoVariantsState({ isFetching: true })).toBe("loading");
  });

  it("maps status to failed / none / empty / ready", () => {
    expect(
      resolveAutoVariantsState({
        data: { folder: "f", status: "failed", items: [], reason: "x" },
      }),
    ).toBe("failed");
    expect(
      resolveAutoVariantsState({ data: { folder: "f", status: "none", items: [] } }),
    ).toBe("none");
    expect(resolveAutoVariantsState({ data: null })).toBe("none");
    expect(
      resolveAutoVariantsState({ data: { folder: "f", status: "empty", items: [] } }),
    ).toBe("empty");
    expect(resolveAutoVariantsState({ data: ready })).toBe("ready");
  });
});

describe("flattenAutoVariantDisplay", () => {
  it("expands weak_points with kp context", () => {
    const data: AutoVariantsResult = {
      folder: "cls_C1__月考",
      status: "ready",
      items: [],
      weak_points: [
        {
          kp_name: "一元二次方程",
          wrong_count: 5,
          student_count: 4,
          variants: [
            { id: "a", question: "q1", answer: "A", kp_name: "一元二次方程" },
            { id: "b", question: "q2", answer: "B", kp_name: "一元二次方程" },
          ],
        },
        {
          kp_name: "因式分解",
          wrong_count: 2,
          student_count: 2,
          variants: [{ id: "c", question: "q3", answer: "C", kp_name: "" }],
        },
      ],
    };
    const rows = flattenAutoVariantDisplay(data);
    expect(rows).toHaveLength(3);
    expect(rows[0].wrong_count).toBe(5);
    expect(rows[2].kp_name).toBe("因式分解"); // 空 kp 回填 weak_point 名
    expect(rows[2].student_count).toBe(2);
  });

  it("falls back to flat items and handles null", () => {
    const data: AutoVariantsResult = {
      folder: "f",
      status: "ready",
      items: [{ id: 1, question: "q", answer: "a", kp_name: "kp" }],
      weak_points: [],
    };
    expect(flattenAutoVariantDisplay(data)).toHaveLength(1);
    expect(flattenAutoVariantDisplay(null)).toEqual([]);
  });
});
