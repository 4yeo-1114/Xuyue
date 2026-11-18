import { render, screen, fireEvent, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ClassOverviewPanel } from "@/components/wuyu-profile/ClassOverviewPanel";

vi.mock("@/contexts/LocaleContext", () => ({
  useLocale: () => ({
    t: (key: string, params?: Record<string, unknown>) =>
      params ? `${key}:${JSON.stringify(params)}` : key,
  }),
}));

// vi.mock 工厂会被提升，fixture 必须 vi.hoisted 提供（工厂内不能引用模块顶层 const）
const { overview } = vi.hoisted(() => {
  const s1 = {
    student_id: "s1",
    name: "丁玉珍",
    dimensions: {
      moral: 3,
      intellectual: 5.18,
      physical: 4,
      aesthetic: 5,
      labor: 6,
      ai_literacy: 5,
    },
    total_growth_point: 28.18,
    activity_track: {
      moral: { count: 2 },
      intellectual: { count: 2 },
      physical: { count: 1 },
      aesthetic: { count: 2 },
      labor: { count: 2 },
      ai_literacy: { count: 1 },
    },
    data_status: {
      moral: "has_data",
      intellectual: "has_data",
      physical: "has_data",
      aesthetic: "has_data",
      labor: "has_data",
      ai_literacy: "insufficient",
    },
    percentile: {
      moral: 34,
      intellectual: 6,
      physical: 62,
      aesthetic: 54,
      labor: 76,
      ai_literacy: null,
      total: 8,
    },
    tier: {
      moral: "C",
      intellectual: "D",
      physical: "B",
      aesthetic: "B",
      labor: "A",
      ai_literacy: null,
      total: "D",
    },
    z_score: {
      moral: -0.846,
      intellectual: -0.958,
      physical: -0.207,
      aesthetic: -0.365,
      labor: 0.525,
      ai_literacy: null,
      total: -1.027,
    },
    composite: {
      moral: 41.5,
      intellectual: 40.4,
      physical: 47.9,
      aesthetic: 46.4,
      labor: 55.3,
      ai_literacy: null,
      total: 39.7,
    },
    rank: {
      moral: 33,
      intellectual: 47,
      physical: 19,
      aesthetic: 23,
      labor: 12,
      ai_literacy: null,
      total: 46,
    },
    n: {
      moral: 50,
      intellectual: 50,
      physical: 50,
      aesthetic: 50,
      labor: 50,
      ai_literacy: 0,
      total: 50,
    },
  };
  // 变体：全维 has_data（点开后不应出现「数据不足」）
  const s2 = {
    student_id: "s2",
    name: "袁小燕",
    dimensions: { moral: 6 },
    total_growth_point: 30,
    activity_track: { moral: { count: 1 } },
    data_status: {
      moral: "has_data",
      intellectual: "has_data",
      physical: "has_data",
      aesthetic: "has_data",
      labor: "has_data",
      ai_literacy: "has_data",
    },
    percentile: {},
    tier: { total: "A+" },
    z_score: {},
    composite: {
      moral: 66.7,
      intellectual: 44.5,
      physical: 53.1,
      aesthetic: 60.4,
      labor: 69.3,
      ai_literacy: 76.6,
      total: 60,
    },
    rank: {},
    n: {},
  };
  const overview = {
    class_id: "c1",
    class_name: "小学三年级一班",
    student_count: 2,
    students: [s1, s2],
    averages: { moral: 5, total: 34.5 },
    tier_distribution: { "A+": 1 },
  };
  return { overview };
});

vi.mock("@/services/wuyuApi", () => ({
  getClassOverview: vi.fn().mockResolvedValue(overview),
}));

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ClassOverviewPanel classId="c1" />
    </QueryClientProvider>,
  );
}

describe("ClassOverviewPanel 五维表现大图弹窗", () => {
  it("点迷你柱弹出大图详情：柱状图数据 + 明细表数值 + 总计行", async () => {
    renderPanel();

    // 每行五维柱都是可点按钮（title=点击看大图）
    const triggers = await screen.findAllByTitle("wuyu.classOverview.clickHint");
    expect(triggers).toHaveLength(2);
    fireEvent.click(triggers[0]);

    // 弹窗标题 = 学生名 + 详情标题（同一 h2 内文本节点拼接，用正则匹配）
    const dialog = await screen.findByRole("dialog");
    const dlg = within(dialog);
    expect(dlg.getByText(/wuyu\.classOverview\.detailTitle/)).toBeInTheDocument();
    expect(dlg.getByText(/丁玉珍/)).toBeInTheDocument();
    // 说明文案
    expect(dlg.getByText("wuyu.classOverview.chartCaption")).toBeInTheDocument();

    // 明细表：有数据维度显示综合分一位小数（柱标签可能同文本，用 getAllByText）
    expect(dlg.getAllByText("41.5").length).toBeGreaterThanOrEqual(1);
    expect(dlg.getAllByText("55.3").length).toBeGreaterThanOrEqual(1);
    // 百分位/排名/成长分
    expect(dlg.getAllByText("34%").length).toBeGreaterThanOrEqual(1);
    expect(dlg.getAllByText("33 / 50").length).toBeGreaterThanOrEqual(1);
    expect(dlg.getAllByText("28.2").length).toBeGreaterThanOrEqual(1);
    // AI 素养不足 → 显示「数据不足」而不是数值
    expect(dlg.getAllByText("wuyu.classOverview.dataInsufficient").length).toBeGreaterThan(0);
    // 总计行：总综合分
    expect(dlg.getAllByText("39.7").length).toBeGreaterThanOrEqual(1);
  });

  it("全维有数据的学生详情里不出现「数据不足」", async () => {
    renderPanel();

    const triggers = await screen.findAllByTitle("wuyu.classOverview.clickHint");
    fireEvent.click(triggers[1]);

    const dialog = await screen.findByRole("dialog");
    const dlg = within(dialog);
    expect(dlg.getByText(/袁小燕/)).toBeInTheDocument();
    expect(dlg.getAllByText("76.6").length).toBeGreaterThanOrEqual(1);
    expect(dlg.queryByText("wuyu.classOverview.dataInsufficient")).not.toBeInTheDocument();
  });
});
