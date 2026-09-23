import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DEFAULT_DIMENSIONS,
  saveManualSlotDecisions,
  saveEssayScore,
} from "@/services/gradingApi";

describe("saveManualSlotDecisions", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends the decisions payload with the legacy scores compatibility field", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: vi.fn().mockResolvedValue(JSON.stringify({ ok: true })),
    });
    vi.stubGlobal("fetch", fetchMock);

    await saveManualSlotDecisions("math-exam", "student_1.jpg", {
      "p1-q1-s1": { status: "correct", score: 2 },
    });

    const [, options] = fetchMock.mock.calls[0];
    expect(JSON.parse(options.body)).toEqual({
      filename: "student_1.jpg",
      scores: {},
      decisions: { "p1-q1-s1": { status: "correct", score: 2 } },
      generate_marks: true,
    });
  });
});

describe("saveEssayScore (A2 作文改分)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts dimension scores to the essay-grade score endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: vi.fn().mockResolvedValue(
        JSON.stringify({
          ok: true,
          completed: {
            name: "student_1.jpg",
            result: "批改结果",
            score_total: 47,
            dimension_scores: { content: 22, language: 25 },
          },
        }),
      ),
    });
    vi.stubGlobal("fetch", fetchMock);

    const res = await saveEssayScore("essay-class", {
      filename: "student_1.jpg",
      dimension_scores: { content: 22, language: 25 },
      total_score: 47,
    });

    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain(
      "/grading/folders/essay-class/essay-grade/score",
    );
    expect(JSON.parse(options.body)).toEqual({
      filename: "student_1.jpg",
      dimension_scores: { content: 22, language: 25 },
      total_score: 47,
    });
    expect(res.ok).toBe(true);
    expect(res.completed?.score_total).toBe(47);
    expect(res.completed?.dimension_scores?.content).toBe(22);
  });

  it("defaults to score-only mode unless regenerate_report is set", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: vi.fn().mockResolvedValue(JSON.stringify({ ok: true })),
    });
    vi.stubGlobal("fetch", fetchMock);

    await saveEssayScore("essay-class", {
      filename: "a.jpg",
      dimension_scores: { content: 20 },
    });

    const [, options] = fetchMock.mock.calls[0];
    expect(JSON.parse(options.body)).toEqual({
      filename: "a.jpg",
      dimension_scores: { content: 20 },
    });
    expect(JSON.parse(options.body).regenerate_report).toBeUndefined();
  });

  it("passes regenerate_report flag when re-grading is requested", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: vi.fn().mockResolvedValue(JSON.stringify({ ok: true })),
    });
    vi.stubGlobal("fetch", fetchMock);

    await saveEssayScore("essay-class", {
      filename: "a.jpg",
      dimension_scores: { content: 20 },
      regenerate_report: true,
    });

    const [, options] = fetchMock.mock.calls[0];
    expect(JSON.parse(options.body)).toEqual({
      filename: "a.jpg",
      dimension_scores: { content: 20 },
      regenerate_report: true,
    });
  });
});

describe("DEFAULT_DIMENSIONS", () => {
  it("exposes the five standard essay dimensions with 100 total score", () => {
    expect(DEFAULT_DIMENSIONS).toHaveLength(5);
    expect(DEFAULT_DIMENSIONS.map((d) => d.key)).toEqual([
      "content",
      "structure",
      "language",
      "relevance",
      "presentation",
    ]);
    expect(DEFAULT_DIMENSIONS.reduce((s, d) => s + d.full_score, 0)).toBe(100);
    expect(DEFAULT_DIMENSIONS.reduce((s, d) => s + d.weight, 0)).toBeCloseTo(1);
  });
});
