import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { KnowledgeLectureCard } from "@/components/grading/KnowledgeLectureCard";
import { getKnowledgeGraph } from "@/data/knowledgeGraphData";

vi.mock("@/contexts/LocaleContext", () => ({
  useLocale: () => ({
    t: (key: string) => `[${key}]`,
  }),
}));

const graph = getKnowledgeGraph("primary", "语文");

describe("KnowledgeLectureCard", () => {
  it("renders lecture info for a matched knowledge point", () => {
    const { container } = render(
      <KnowledgeLectureCard kp="拼音" graph={graph} />,
    );
    expect(container.textContent).toContain("拼音");
    expect(container.textContent).toContain("字词基础"); // cluster
    expect(container.textContent).toContain("识字写字"); // followup resolved
    expect(container.textContent).toContain(
      "[grading.errorBook.knowledge.lectureTitle]",
    );
  });

  it("falls back to the not-mapped hint when no node matches", () => {
    const { container } = render(
      <KnowledgeLectureCard kp="现代文阅读" graph={graph} />,
    );
    expect(container.textContent).toContain("现代文阅读");
    expect(container.textContent).toContain(
      "[grading.errorBook.knowledge.notMapped]",
    );
  });

  it("shows the knowledge point name when the graph is unavailable", () => {
    const { container } = render(
      <KnowledgeLectureCard kp="拼音" graph={null} />,
    );
    expect(container.textContent).toContain("拼音");
    expect(container.textContent).toContain(
      "[grading.errorBook.knowledge.noGraph]",
    );
  });
});
