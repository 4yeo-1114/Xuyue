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
          total: 1,
          page: 1,
          page_size: 50,
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
    expect(String(url)).toContain("page_size=50"); // limit 兼容参数归一成 page_size
    expect(res.rows).toHaveLength(1);
    expect(res.rows[0].was_result).toBe("错");
    expect(res.rows[0].new_score).toBe(2);
    expect(res.count).toBe(1);
    expect(res.total).toBe(1);
  });

  it("sends classify/search/pagination params and reads facets", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: vi.fn().mockResolvedValue(
        JSON.stringify({
          rows: [],
          total: 120,
          page: 2,
          page_size: 20,
          source_counts: { human_ai_correct: 90, vl_ink: 30 },
          folder_counts: [{ folder: "期中考试", count: 120 }],
          window_days: 30,
          include_voided: false,
        }),
      ),
    });
    vi.stubGlobal("fetch", fetchMock);

    const res = await fetchCorrectionLedger({
      source: "human_ai_correct",
      folder: "期中考试",
      changeKind: "result",
      q: "张三",
      page: 2,
      pageSize: 20,
    });

    const s = String(fetchMock.mock.calls[0][0]);
    expect(s).toContain("source=human_ai_correct");
    expect(s).toContain(`folder=${encodeURIComponent("期中考试")}`);
    expect(s).toContain("change_kind=result");
    expect(s).toContain(`q=${encodeURIComponent("张三")}`);
    expect(s).toContain("page=2");
    expect(s).toContain("page_size=20");
    expect(res.total).toBe(120);
    expect(res.page).toBe(2);
    expect(res.source_counts.human_ai_correct).toBe(90);
    expect(res.folder_counts[0].folder).toBe("期中考试");
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
