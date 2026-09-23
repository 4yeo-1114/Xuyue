import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FloatingChat } from "@/components/FloatingChat";
import {
  listAiChatHistory,
  getAiChatHistoryDetail,
  deleteAiChatHistory,
} from "@/services/aiChatHistoryApi";

// jsdom 未实现 scrollIntoView，FloatingChat 打开面板时会调用它
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

vi.mock("@/contexts/LocaleContext", () => ({
  useLocale: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock("@/contexts/ProjectBrandingContext", () => ({
  useProjectBranding: () => ({ projectName: "Test Project" }),
}));

vi.mock("@/services/aiChatHistoryApi", () => ({
  listAiChatHistory: vi.fn(),
  getAiChatHistoryDetail: vi.fn(),
  deleteAiChatHistory: vi.fn(),
}));

const mockList = vi.mocked(listAiChatHistory);
const mockDetail = vi.mocked(getAiChatHistoryDetail);
const mockDelete = vi.mocked(deleteAiChatHistory);

const item = {
  id: "c1",
  title: "如何批改作业",
  summary: "",
  message_count: 4,
  created_at: "2026-08-01T08:00:00Z",
  updated_at: "2026-08-01T08:00:00Z",
};

function renderChat() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <FloatingChat />
    </QueryClientProvider>,
  );
}

/** 打开悬浮窗并切到历史面板 */
async function openHistory() {
  fireEvent.click(screen.getByRole("button", { name: "chat.fab.aria" }));
  await waitFor(() => screen.getByRole("dialog"));
  fireEvent.click(screen.getByRole("button", { name: "chat.history.entry" }));
}

describe("FloatingChat history panel", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("renders the conversation list from the history API", async () => {
    mockList.mockResolvedValue({
      items: [
        item,
        { ...item, id: "c2", title: "班级数据分析", message_count: 2 },
      ],
      total: 2,
      page: 1,
      pageSize: 20,
    });

    renderChat();
    await openHistory();

    await waitFor(() =>
      expect(screen.getByText("如何批改作业")).toBeInTheDocument(),
    );
    expect(screen.getByText("班级数据分析")).toBeInTheDocument();
    expect(mockList).toHaveBeenCalledWith(1, 20);
  });

  it("shows the empty state when there is no history", async () => {
    mockList.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 });

    renderChat();
    await openHistory();

    await waitFor(() =>
      expect(screen.getByText("chat.history.empty")).toBeInTheDocument(),
    );
  });

  it("opens a conversation and renders its read-only messages", async () => {
    mockList.mockResolvedValue({
      items: [item],
      total: 1,
      page: 1,
      pageSize: 20,
    });
    mockDetail.mockResolvedValue({
      ...item,
      messages: [
        {
          id: "m1",
          role: "user",
          content: "你好，怎么批改作业？",
          model: null,
          seq: 1,
          created_at: "2026-08-01T08:00:00Z",
        },
        {
          id: "m2",
          role: "assistant",
          content: "我可以在批改模块帮你完成批改。",
          model: "gpt-4o",
          seq: 2,
          created_at: "2026-08-01T08:00:01Z",
        },
      ],
    });

    renderChat();
    await openHistory();

    await waitFor(() => screen.getByText("如何批改作业"));
    fireEvent.click(screen.getByText("如何批改作业"));

    await waitFor(() => expect(mockDetail).toHaveBeenCalledWith("c1"));
    await waitFor(() =>
      expect(screen.getByText("你好，怎么批改作业？")).toBeInTheDocument(),
    );
    expect(
      screen.getByText(/我可以在批改模块帮你完成批改/),
    ).toBeInTheDocument();
  });

  it("deletes a conversation after confirmation and refetches the list", async () => {
    mockList.mockResolvedValue({
      items: [item],
      total: 1,
      page: 1,
      pageSize: 20,
    });
    mockDelete.mockResolvedValue({ id: "c1" });

    renderChat();
    await openHistory();
    await waitFor(() => screen.getByText("如何批改作业"));

    fireEvent.click(
      screen.getByRole("button", { name: "chat.history.deleteTitle" }),
    );
    await waitFor(() =>
      expect(screen.getByText("chat.history.deleteDesc")).toBeInTheDocument(),
    );

    fireEvent.click(
      screen.getByRole("button", { name: "chat.history.deleteConfirm" }),
    );

    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith("c1"));
    // invalidate → list refetches
    await waitFor(() =>
      expect(mockList.mock.calls.length).toBeGreaterThanOrEqual(2),
    );
  });
});
