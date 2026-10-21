import { afterEach, describe, expect, it, vi } from "vitest";
import {
  fetchCorrectionLedger,
  fetchCorrectionStats,
} from "@/services/gradingApi";

describe("fetchCorrectionLedger", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("GETs /grading/correction-ledger with window and voided flags", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: vi.fn().mockResolvedValue(
        JSON.stringify({
          rows: [
            {
              id: "r1",
              created_at: "2026-10-01T12:00:00+00:00",
              paper_name: "s1.jpg",
              index: "1",
              sub_index: null,
              source: "human_ai_correct",
              was_result: "错",
              new_result: "对",
              was_score: 0,
              new_score: 2,
            },
          ],
          count: 1,
          window_days: 7,
          include_voided: true,
        }),
      ),
    });
    vi.stubGlobal("fetch", fetchMock);

    const res = await fetchCorrectionLedger({ days: 7, includeVoided: true, limit: 50 });

    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/grading/correction-ledger");
    expect(String(url)).toContain("days=7");
    expect(String(url)).toContain("include_voided=true");
    expect(String(url)).toContain("limit=50");
    expect(res.rows).toHaveLength(1);
    expect(res.rows[0].was_result).toBe("错");
    expect(res.rows[0].new_score).toBe(2);
    expect(res.count).toBe(1);
  });

  it("omits query string when no options given", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: vi.fn().mockResolvedValue(JSON.stringify({ rows: [], count: 0 })),
    });
    vi.stubGlobal("fetch", fetchMock);

    await fetchCorrectionLedger();
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/grading/correction-ledger");
    expect(String(url)).not.toContain("?");
  });
});

describe("fetchCorrectionStats", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("GETs the matrix endpoint with window", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: vi.fn().mockResolvedValue(
        JSON.stringify({
          matrix: [{ source: "human_ai_correct", was: "错", new: "对", count: 2 }],
          totals_by_source: { human_ai_correct: 2 },
          window_days: 30,
        }),
      ),
    });
    vi.stubGlobal("fetch", fetchMock);

    const res = await fetchCorrectionStats({ days: 30 });
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/grading/correction-stats");
    expect(String(url)).toContain("days=30");
    expect(res.totals_by_source.human_ai_correct).toBe(2);
  });
});
