import { describe, expect, it } from "vitest";

import {
  ASSESSMENT_DIMENSIONS,
  buildTrendSeries,
  lastTwoDelta,
  latestPercents,
  weakDimensions,
} from "@/services/assessmentTrend";
import type { AssessmentResult } from "@/services/assessmentApi";

function makeRow(
  id: string,
  createdAt: string,
  dimensionPercents: Record<string, number>,
): AssessmentResult {
  return {
    id,
    student_id: "stu-1",
    definition_id: "def-1",
    definition_name: "自我认识问卷",
    domain: "personality",
    purpose: "class",
    tag_schema: { dimension_percents: dimensionPercents },
    guardian_consent: { status: "granted", version: 1 },
    created_at: createdAt,
  } as AssessmentResult;
}

const fullPercents = {
  learning_style: 70,
  interest: 55,
  social_style: 80,
  emotion_regulation: 45,
  challenge_coping: 62,
};

describe("buildTrendSeries", () => {
  it("sorts rows by created_at ascending regardless of input order", () => {
    const rows = [
      makeRow("r2", "2026-08-19T10:00:00Z", fullPercents),
      makeRow("r1", "2026-08-10T09:00:00Z", fullPercents),
      makeRow("r3", "2026-08-20T08:00:00Z", fullPercents),
    ];
    const series = buildTrendSeries(rows);
    expect(series.points.map((p) => p.date)).toEqual([
      "2026-08-10T09:00:00Z",
      "2026-08-19T10:00:00Z",
      "2026-08-20T08:00:00Z",
    ]);
    expect(series.points.map((p) => p.index)).toEqual([1, 2, 3]);
  });

  it("extracts the 5 assessment dims and drops non-assessment keys", () => {
    const rows = [
      makeRow("r1", "2026-08-10T09:00:00Z", {
        learning_style: 70,
        interest: 55,
        social_style: 80,
        emotion_regulation: 45,
        challenge_coping: 62,
        // 非评估域维度，应被丢弃
        wuyu_moral: 90,
        academic_perf: 33,
      }),
    ];
    const series = buildTrendSeries(rows);
    expect(series.points[0]).not.toHaveProperty("wuyu_moral");
    expect(series.points[0]).not.toHaveProperty("academic_perf");
    expect(series.dims).toEqual([...ASSESSMENT_DIMENSIONS]);
  });

  it("only includes dims that appear in at least one point", () => {
    const rows = [
      makeRow("r1", "2026-08-10T09:00:00Z", { learning_style: 70 }),
      makeRow("r2", "2026-08-19T10:00:00Z", { interest: 55 }),
    ];
    const series = buildTrendSeries(rows);
    expect(series.dims.sort()).toEqual(["interest", "learning_style"]);
  });

  it("keeps rows without dimension_percents as empty points", () => {
    const rows = [
      makeRow("r1", "2026-08-10T09:00:00Z", fullPercents),
      makeRow("r2", "2026-08-19T10:00:00Z", {}),
    ];
    const series = buildTrendSeries(rows);
    expect(series.points).toHaveLength(2);
    expect(series.points[1].learning_style).toBeUndefined();
    expect(series.dims).toEqual([...ASSESSMENT_DIMENSIONS]);
  });

  it("does not mutate the input rows array", () => {
    const rows = [
      makeRow("r2", "2026-08-19T10:00:00Z", fullPercents),
      makeRow("r1", "2026-08-10T09:00:00Z", fullPercents),
    ];
    const before = rows.map((r) => r.id);
    buildTrendSeries(rows);
    expect(rows.map((r) => r.id)).toEqual(before);
  });

  it("returns empty series for empty input", () => {
    const series = buildTrendSeries([]);
    expect(series.points).toEqual([]);
    expect(series.dims).toEqual([]);
  });
});

describe("lastTwoDelta", () => {
  it("computes latest - previous for each dim", () => {
    const series = buildTrendSeries([
      makeRow("r1", "2026-08-10T09:00:00Z", fullPercents),
      makeRow("r2", "2026-08-19T10:00:00Z", {
        learning_style: 80,
        interest: 45,
        social_style: 80,
        emotion_regulation: 40,
        challenge_coping: 50,
      }),
    ]);
    const deltas = lastTwoDelta(series);
    const byDim = Object.fromEntries(deltas.map((d) => [d.dim, d]));
    expect(byDim.learning_style.delta).toBe(10);
    expect(byDim.interest.delta).toBe(-10);
    expect(byDim.social_style.delta).toBe(0);
    expect(byDim.emotion_regulation.delta).toBe(-5);
    expect(byDim.challenge_coping.delta).toBe(-12);
    expect(byDim.learning_style.latest).toBe(80);
    expect(byDim.learning_style.prev).toBe(70);
  });

  it("returns null delta when a dim has only one measurement", () => {
    const series = buildTrendSeries([
      makeRow("r1", "2026-08-10T09:00:00Z", { learning_style: 70 }),
      makeRow("r2", "2026-08-19T10:00:00Z", { interest: 55 }),
    ]);
    const deltas = lastTwoDelta(series);
    const byDim = Object.fromEntries(deltas.map((d) => [d.dim, d]));
    expect(byDim.learning_style.delta).toBeNull();
    expect(byDim.learning_style.prev).toBeNull();
    expect(byDim.interest.delta).toBeNull();
  });

  it("uses the two most recent valid measurements when middle points lack the dim", () => {
    const series = buildTrendSeries([
      makeRow("r1", "2026-08-10T09:00:00Z", { learning_style: 70 }),
      makeRow("r2", "2026-08-19T10:00:00Z", {}),
      makeRow("r3", "2026-08-20T08:00:00Z", { learning_style: 90 }),
    ]);
    const deltas = lastTwoDelta(series);
    expect(deltas.find((d) => d.dim === "learning_style")).toMatchObject({
      prev: 70,
      latest: 90,
      delta: 20,
    });
  });

  it("returns empty for empty series", () => {
    expect(lastTwoDelta({ points: [], dims: [] })).toEqual([]);
  });
});

describe("weakDimensions", () => {
  it("marks dims below threshold (default 60), boundary excluded", () => {
    const latest = {
      learning_style: 70,
      interest: 55,
      emotion_regulation: 60,
      challenge_coping: 45,
    };
    expect(weakDimensions(latest).sort()).toEqual([
      "challenge_coping",
      "interest",
    ]);
  });

  it("honors custom threshold", () => {
    const latest = { learning_style: 70, interest: 55, social_style: 80 };
    expect(weakDimensions(latest, 75).sort()).toEqual([
      "interest",
      "learning_style",
    ]);
  });

  it("returns empty when nothing is weak", () => {
    expect(weakDimensions({ learning_style: 100, interest: 61 })).toEqual([]);
  });

  it("ignores non-number values", () => {
    expect(weakDimensions({ interest: 55 } as Record<string, number>)).toEqual([
      "interest",
    ]);
  });
});

describe("latestPercents", () => {
  it("returns the last point's assessment dims only", () => {
    const series = buildTrendSeries([
      makeRow("r1", "2026-08-10T09:00:00Z", { learning_style: 70 }),
      makeRow("r2", "2026-08-19T10:00:00Z", {
        interest: 55,
        emotion_regulation: 40,
      }),
    ]);
    expect(latestPercents(series)).toEqual({
      interest: 55,
      emotion_regulation: 40,
    });
  });

  it("returns empty object for empty series", () => {
    expect(latestPercents({ points: [], dims: [] })).toEqual({});
  });
});
