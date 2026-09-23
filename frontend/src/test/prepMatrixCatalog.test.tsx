import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PrepMatrixPage } from "@/components/prep-plan/PrepMatrixPage";
import {
  TextbookCatalogPage,
  PREP_LESSON_CONTEXT_KEY,
} from "@/components/prep-plan/TextbookCatalogPage";
import type { TextbookCatalogNode } from "@/services/api";

const {
  listTextbookCatalogsMock,
  listTextbookCatalogOptionsMock,
  navigateMock,
  setSearchParamsMock,
} = vi.hoisted(() => ({
  listTextbookCatalogsMock: vi.fn(),
  listTextbookCatalogOptionsMock: vi.fn(),
  navigateMock: vi.fn(),
  setSearchParamsMock: vi.fn(),
}));

vi.mock("@/contexts/LocaleContext", () => ({
  useLocale: () => ({ t: (key: string) => key, locale: "zh" }),
}));

vi.mock("react-router-dom", async () => {
  const actual =
    await vi.importActual<typeof import("react-router-dom")>(
      "react-router-dom",
    );
  return {
    ...actual,
    useNavigate: () => navigateMock,
    useSearchParams: () => [
      new URLSearchParams({
        subject: "数学",
        grade: "初一",
        edition: "人教版",
      }),
      setSearchParamsMock,
    ],
  };
});

vi.mock("@/services/api", () => ({
  listTextbookCatalogs: listTextbookCatalogsMock,
  listTextbookCatalogOptions: listTextbookCatalogOptionsMock,
}));

/** 四维定位矩阵数据同步的默认 options（点亮「语文 × 小学六年级」等单元格） */
const matrixOptions = {
  editions: ["人教版"],
  subjects: ["语文", "数学", "英语"],
  grades: ["小学六年级", "初一"],
  pairs: [
    { subject: "语文", grade: "小学六年级", edition: "人教版", node_count: 6 },
    { subject: "数学", grade: "初一", edition: "人教版", node_count: 6 },
  ],
};

const catalog: TextbookCatalogNode[] = [
  {
    id: 1,
    name: "人教版七年级上册",
    subject: "数学",
    edition: "人教版",
    grade: "初一",
    level: "edition",
    unit_index: 1,
    parent_id: null,
  },
  {
    id: 2,
    name: "第一章 有理数",
    subject: "数学",
    edition: "人教版",
    grade: "初一",
    level: "unit",
    unit_index: 1,
    parent_id: 1,
  },
  {
    id: 3,
    name: "1.1 正数和负数",
    subject: "数学",
    edition: "人教版",
    grade: "初一",
    level: "lesson",
    unit_index: 1,
    parent_id: 2,
  },
];

describe("PrepMatrixPage", () => {
  beforeEach(() => {
    navigateMock.mockClear();
    listTextbookCatalogOptionsMock.mockReset();
    listTextbookCatalogOptionsMock.mockResolvedValue(matrixOptions);
  });

  it("渲染小学/初中两个学段区块与年级行", async () => {
    render(<PrepMatrixPage />);
    expect(screen.getByText("prepMatrix.schoolLevel.primary")).toBeTruthy();
    expect(screen.getByText("prepMatrix.schoolLevel.junior")).toBeTruthy();
    // 年级行：小学一年级~六年级、初一~初三
    expect(screen.getAllByText("一年级").length).toBeGreaterThan(0);
    expect(screen.getAllByText("七年级").length).toBeGreaterThan(0);
    // 等待异步 options 加载完成，避免未包裹 act 的状态更新告警
    await screen.findByLabelText("语文 · 六年级");
  });

  it("仅点亮有目录数据的单元格并携带 subject/grade/edition 跳转", async () => {
    render(<PrepMatrixPage />);
    // 有目录数据的「语文 · 六年级」为可点击按钮
    const cell = await screen.findByLabelText("语文 · 六年级");
    fireEvent.click(cell);
    expect(navigateMock).toHaveBeenCalledTimes(1);
    expect(navigateMock.mock.calls[0][0]).toMatch(/^\/nav\/prep-catalog\?/);
    expect(navigateMock.mock.calls[0][0]).toContain(
      "subject=%E8%AF%AD%E6%96%87",
    );
    expect(navigateMock.mock.calls[0][0]).toContain(
      "edition=%E4%BA%BA%E6%95%99%E7%89%88",
    );
  });

  it("无目录数据的单元格不可点击", async () => {
    render(<PrepMatrixPage />);
    await screen.findByLabelText("语文 · 六年级");
    // 无数据的单元格渲染为非按钮元素（title=prepMatrix.noData，且存在多个）
    const emptyCells = screen.getAllByTitle("prepMatrix.noData");
    expect(emptyCells.length).toBeGreaterThan(0);
    emptyCells.forEach((cell) => expect(cell.tagName).not.toBe("BUTTON"));
  });
});

describe("TextbookCatalogPage", () => {
  it("加载后按 parent_id 渲染目录树（册次→单元→课时）", async () => {
    listTextbookCatalogsMock.mockResolvedValue(catalog);
    render(<TextbookCatalogPage onNavChange={navigateMock} />);
    await waitFor(() => {
      expect(listTextbookCatalogsMock).toHaveBeenCalledWith({
        subject: "数学",
        grade: "初一",
        edition: "人教版",
      });
    });
    await waitFor(() => {
      expect(screen.getByText("人教版七年级上册")).toBeTruthy();
      expect(screen.getByText("第一章 有理数")).toBeTruthy();
      expect(screen.getByText("1.1 正数和负数")).toBeTruthy();
    });
  });

  it("无数据时展示空态引导文案", async () => {
    listTextbookCatalogsMock.mockResolvedValue([]);
    render(<TextbookCatalogPage onNavChange={navigateMock} />);
    await waitFor(() => {
      expect(screen.getByText("prepCatalog.emptyTitle")).toBeTruthy();
    });
  });

  it("接口失败时展示错误态与重试按钮", async () => {
    listTextbookCatalogsMock.mockRejectedValueOnce(new Error("network down"));
    render(<TextbookCatalogPage onNavChange={navigateMock} />);
    await waitFor(() => {
      expect(screen.getByText("network down")).toBeTruthy();
      expect(screen.getByText("prepCatalog.retry")).toBeTruthy();
    });
  });

  it("点击 AI 生成教案写入 sessionStorage 并跳转教案编辑", async () => {
    listTextbookCatalogsMock.mockResolvedValue(catalog);
    sessionStorage.clear();
    render(<TextbookCatalogPage onNavChange={navigateMock} />);
    const buttons = await screen.findAllByText("prepCatalog.aiGenerate");
    expect(buttons.length).toBeGreaterThan(0);
    fireEvent.click(buttons[0]);
    const ctx = JSON.parse(
      sessionStorage.getItem(PREP_LESSON_CONTEXT_KEY) || "{}",
    );
    expect(ctx.nodeName).toBe("人教版七年级上册");
    expect(ctx.subject).toBe("数学");
    expect(navigateMock).toHaveBeenCalledWith("prep-lesson");
  });
});
