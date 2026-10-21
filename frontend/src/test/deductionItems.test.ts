import { describe, expect, it } from "vitest";
import {
  deductionGap,
  deductionTotal,
} from "@/components/grading/ManualPaperGradingDialog";
import type { DeductionItem } from "@/services/gradingApi";

describe("deductionTotal", () => {
  it("returns 0 for empty / missing list", () => {
    expect(deductionTotal(undefined)).toBe(0);
    expect(deductionTotal([])).toBe(0);
  });

  it("sums positive points", () => {
    const items: DeductionItem[] = [
      { label: "步骤不全", points: 1 },
      { label: "结果错", points: 1.5 },
    ];
    expect(deductionTotal(items)).toBe(2.5);
  });

  it("ignores non-numeric points safely", () => {
    const items = [
      { label: "a", points: 1 },
      { label: "b", points: Number.NaN },
    ] as DeductionItem[];
    expect(deductionTotal(items)).toBe(1);
  });
});

describe("deductionGap", () => {
  it("computes expected = max - score and gap = expected - deducted", () => {
    // 满分 5 得 2 → 应扣 3；已录 2.5 → 可补录 0.5
    const stats = deductionGap(5, 2, [
      { label: "步骤不全", points: 1 },
      { label: "结果错", points: 1.5 },
    ]);
    expect(stats.deducted).toBe(2.5);
    expect(stats.expected).toBe(3);
    expect(stats.gap).toBeCloseTo(0.5);
  });

  it("gap is 0 when deducted matches expected", () => {
    const stats = deductionGap(3, 1.5, [{ label: "错别字", points: 1.5 }]);
    expect(stats.gap).toBe(0);
  });

  it("gap is negative when over-deducted", () => {
    const stats = deductionGap(3, 1, [
      { label: "a", points: 1 },
      { label: "b", points: 1.5 },
    ]);
    expect(stats.expected).toBe(2);
    expect(stats.deducted).toBe(2.5);
    expect(stats.gap).toBeCloseTo(-0.5);
  });

  it("null score yields expected 0 (no scoring yet)", () => {
    const stats = deductionGap(5, null, [{ label: "x", points: 1 }]);
    expect(stats.expected).toBe(0);
    expect(stats.gap).toBeCloseTo(-1);
  });
});
