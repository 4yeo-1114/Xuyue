import { afterEach, describe, expect, it, vi } from "vitest";
import { downloadGrowthAlbumPdf, getDossier } from "@/services/wuyuApi";

// getDossier 走 request<T>，内部会调用 getAuthToken()（读 localStorage + supabase session）。
// 单测环境无登录态，mock 掉 getAuthToken 返回 null，让请求只命中 stub 的 fetch。
vi.mock("@/services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/services/api")>();
  return { ...actual, getAuthToken: vi.fn().mockResolvedValue(null) };
});

describe("downloadGrowthAlbumPdf", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches the growth-album PDF endpoint with term and parses RFC 5987 filename", async () => {
    const blob = new Blob(["pdf"], { type: "application/pdf" });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      blob: vi.fn().mockResolvedValue(blob),
      headers: new Headers({
        "Content-Disposition":
          "attachment; filename*=UTF-8''%E6%88%90%E9%95%BF%E7%BA%AA%E5%BF%B5%E5%86%8C_%E5%BC%A0%E4%B8%89_2025-2026-1.pdf",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { blob: outBlob, filename } = await downloadGrowthAlbumPdf(
      "student_1",
      "2025-2026-1",
    );

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain(
      "/portfolio/students/student_1/growth-album/pdf?term=2025-2026-1",
    );
    expect(filename).toBe("成长纪念册_张三_2025-2026-1.pdf");
    expect(outBlob).toBe(blob);
  });

  it("falls back to a default filename when term is omitted", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      blob: vi.fn().mockResolvedValue(new Blob(["pdf"])),
      headers: new Headers(),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { filename } = await downloadGrowthAlbumPdf("student_1");

    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/growth-album/pdf");
    expect(String(url)).not.toContain("term=");
    expect(filename).toBe("成长册.pdf");
  });

  it("throws with the server detail message on failure", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: vi.fn().mockResolvedValue({ detail: "term is required" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(downloadGrowthAlbumPdf("student_1")).rejects.toThrow(
      "term is required",
    );
  });
});

describe("getDossier", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const emptyPayload = {
    student_id: "student_1",
    name: "张三",
    class_id: "class_1",
    class_name: "三年二班",
    grade: "三年级",
    term: "2025-2026-1",
    report: null,
    growth_records: [],
    memories: [],
    badges: [],
    credit_transactions: [],
    assessment_results: [],
    archive_status: null,
  };

  it("fetches the dossier endpoint with term and unwraps the data payload", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi
        .fn()
        .mockResolvedValue({ code: 0, message: "ok", data: emptyPayload }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const data = await getDossier("student_1", "2025-2026-1");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain(
      "/portfolio/students/student_1/dossier?term=2025-2026-1",
    );
    expect(data).toEqual(emptyPayload);
    expect(data.name).toBe("张三");
    expect(data.archive_status).toBeNull();
  });

  it("omits the term query when term is not provided", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi
        .fn()
        .mockResolvedValue({ code: 0, message: "ok", data: emptyPayload }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await getDossier("student_1");

    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/portfolio/students/student_1/dossier");
    expect(String(url)).not.toContain("term=");
  });

  it("preserves the full dossier shape (report, lists and archive status)", async () => {
    const payload = {
      student_id: "s1",
      name: "李四",
      class_id: "c1",
      class_name: "一班",
      grade: "一年级",
      term: "2025-2026-1",
      report: {
        student_id: "s1",
        name: "李四",
        class_id: "c1",
        term: "2025-2026-1",
        date_from: "2025-09-01",
        date_to: "2026-01-31",
        base_points: 10,
        dimensions: {},
        source_stats: {},
        growth_records_count: 0,
        total_growth_point: 0,
        raw_total: 0,
        data_status: {},
        data_sources_missing: {},
        baseline: null,
        milestones: [],
        trend: [],
        comment: { status: "absent" },
        from_snapshot: false,
        version: 1,
        credit: null,
      },
      growth_records: [
        {
          id: "gr1",
          dimension: "moral",
          growth_points: 2,
          indicator_name: "值日",
          note: "主动值日",
          occurred_at: "2025-10-01T08:00:00Z",
        },
      ],
      memories: [
        {
          id: "m1",
          image_path: "/uploads/a.jpg",
          caption: "运动会",
          created_at: "2025-10-01",
        },
      ],
      badges: [
        { id: "b1", name: "文明之星", points: 5, awarded_at: "2025-10-02" },
      ],
      credit_transactions: [
        {
          id: "t1",
          amount: 10,
          transaction_type: "badge_award",
          description: "颁章奖励",
          created_at: "2025-10-02",
        },
      ],
      assessment_results: [
        {
          id: "a1",
          definition_name: "兴趣测评",
          dimension_percents: { interest: 80 },
          labels: ["积极"],
        },
      ],
      archive_status: { status: "selected" },
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi
        .fn()
        .mockResolvedValue({ code: 0, message: "ok", data: payload }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const data = await getDossier("s1");

    expect(data.report?.version).toBe(1);
    expect(data.growth_records).toHaveLength(1);
    expect(data.growth_records[0].dimension).toBe("moral");
    expect(data.memories[0].image_path).toBe("/uploads/a.jpg");
    expect(data.badges[0].name).toBe("文明之星");
    expect(data.credit_transactions[0].amount).toBe(10);
    expect(data.assessment_results[0].dimension_percents?.interest).toBe(80);
    expect(data.archive_status?.status).toBe("selected");
  });
});
