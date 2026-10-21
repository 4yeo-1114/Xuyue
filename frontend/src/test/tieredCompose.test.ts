import { describe, expect, it } from "vitest";

import {
  TIER_BAND_WEIGHTS,
  TIER_KP_MODE,
  TIER_ORDER,
  isSingleKp,
  planBands,
  summarizeDifficulty,
  tierStrategyKey,
} from "@/components/class-detail/layered-push/tieredCompose";

describe("TIER_BAND_WEIGHTS 层间差异", () => {
  it("A 层 hard 权重最高、C 层 easy 权重最高", () => {
    expect(TIER_BAND_WEIGHTS.A.hard).toBeGreaterThan(TIER_BAND_WEIGHTS.B.hard);
    expect(TIER_BAND_WEIGHTS.B.hard).toBeGreaterThan(TIER_BAND_WEIGHTS.C.hard);
    expect(TIER_BAND_WEIGHTS.C.easy).toBeGreaterThan(TIER_BAND_WEIGHTS.B.easy);
    expect(TIER_BAND_WEIGHTS.B.easy).toBeGreaterThan(TIER_BAND_WEIGHTS.A.easy);
  });

  it("知识点粒度：A 跨知识点 / B 不限 / C 单一", () => {
    expect(TIER_KP_MODE.A).toBe("multi");
    expect(TIER_KP_MODE.B).toBeNull();
    expect(TIER_KP_MODE.C).toBe("single");
    expect(TIER_ORDER).toEqual(["A", "B", "C"]);
  });
});

describe("planBands", () => {
  it("按权重生成指定长度的难度带序列", () => {
    const plan = planBands(10, TIER_BAND_WEIGHTS.A);
    expect(plan).toHaveLength(10);
    expect(plan.filter((b) => b === "hard").length).toBeGreaterThanOrEqual(5);
    expect(plan.filter((b) => b === "hard").length).toBeGreaterThan(
      plan.filter((b) => b === "easy").length,
    );
  });

  it("C 层 easy 占多数", () => {
    const plan = planBands(10, TIER_BAND_WEIGHTS.C);
    expect(plan).toHaveLength(10);
    expect(plan.filter((b) => b === "easy").length).toBeGreaterThanOrEqual(5);
  });

  it("count<=0 或全零权重返回空", () => {
    expect(planBands(0, TIER_BAND_WEIGHTS.B)).toEqual([]);
    expect(planBands(-3, TIER_BAND_WEIGHTS.B)).toEqual([]);
    expect(planBands(5, { easy: 0, medium: 0, hard: 0 })).toEqual([]);
    expect(planBands(NaN, TIER_BAND_WEIGHTS.B)).toEqual([]);
  });

  it("权重不归一也能按比例摊", () => {
    const plan = planBands(8, { easy: 2, medium: 2, hard: 4 });
    expect(plan).toHaveLength(8);
    expect(plan.filter((b) => b === "hard").length).toBeGreaterThanOrEqual(3);
  });
});

describe("isSingleKp", () => {
  it("无 / 或单段为单一知识点", () => {
    expect(isSingleKp("一次函数")).toBe(true);
    expect(isSingleKp("一次函数/二次函数")).toBe(false);
    expect(isSingleKp("a / b / c")).toBe(false);
    expect(isSingleKp(null)).toBe(true);
    expect(isSingleKp("")).toBe(true);
  });
});

describe("summarizeDifficulty", () => {
  it("按 1-5 分桶：≤2 易、3 中、≥4 难", () => {
    const s = summarizeDifficulty([
      { difficulty: 1 },
      { difficulty: 2 },
      { difficulty: 3 },
      { difficulty: 5 },
      { difficulty: null },
    ]);
    expect(s.easy).toBe(2);
    expect(s.medium).toBe(2);
    expect(s.hard).toBe(1);
    expect(s.count).toBe(5);
    expect(s.avg).toBeCloseTo(2.8, 1);
  });

  it("支持裸数字列表与空列表", () => {
    expect(summarizeDifficulty([1, 4, 4])).toMatchObject({
      easy: 1,
      hard: 2,
      count: 3,
    });
    expect(summarizeDifficulty([]).count).toBe(0);
    expect(summarizeDifficulty([]).avg).toBe(0);
  });
});

describe("tierStrategyKey", () => {
  it("返回 smartGen.tiered.strategy.* i18n key", () => {
    expect(tierStrategyKey("A")).toBe("smartGen.tiered.strategy.A");
    expect(tierStrategyKey("C")).toBe("smartGen.tiered.strategy.C");
  });
});
