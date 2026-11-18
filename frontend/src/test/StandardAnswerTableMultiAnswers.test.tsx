import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StandardAnswerTableDialog } from "@/components/grading/StandardAnswerTableDialog";
import type { ReferenceAnswerTablePage } from "@/services/gradingApi";

vi.mock("@/contexts/LocaleContext", () => ({
  useLocale: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock("@/services/gradingApi", () => ({
  gradingImageUrl: (path: string) => path || "",
}));

const pages: ReferenceAnswerTablePage[] = [
  {
    page_no: 1,
    filename: "std.jpg",
    questions: [
      {
        display_index: 1,
        printed_no: "27",
        slots: [
          { sub_index: 1, bbox: [0, 0, 10, 10], answer_text: "There is a gym" },
        ],
        full_answer: "There is a gym",
      },
      {
        display_index: 2,
        printed_no: "28",
        slots: [
          { sub_index: 1, bbox: [0, 0, 10, 10], answer_text: "甲" },
          { sub_index: 2, bbox: [0, 0, 10, 10], answer_text: "乙" },
        ],
        full_answer: "甲\n乙",
      },
    ],
  },
];

function renderDialog() {
  const onSave = vi.fn().mockResolvedValue(undefined);
  const onRebuild = vi.fn().mockResolvedValue(undefined);
  render(
    <StandardAnswerTableDialog
      open
      pages={pages}
      loading={false}
      saving={false}
      onOpenChange={vi.fn()}
      onSave={onSave}
      onRebuild={onRebuild}
    />,
  );
  return { onSave };
}

describe("StandardAnswerTableDialog 多个可接受答案（11.11-12 前半）", () => {
  it("展示 | 分隔的设置口径说明", () => {
    renderDialog();
    expect(
      screen.getByText("grading.answerTable.multiAnswerHint"),
    ).toBeInTheDocument();
  });

  it("答案里写了 | 就把可接受答案拆出来亮牌（确认系统认到了）", () => {
    renderDialog();
    fireEvent.change(screen.getByDisplayValue("There is a gym"), {
      target: { value: "There is a gym|There's a gym" },
    });
    expect(screen.getByText("grading.answerTable.acceptedVariants:")).toBeInTheDocument();
    expect(screen.getByText("1. There is a gym")).toBeInTheDocument();
    expect(screen.getByText("2. There's a gym")).toBeInTheDocument();
  });

  it("单答案不亮牌；带空段的「答案|」也不算多解", () => {
    renderDialog();
    fireEvent.change(screen.getByDisplayValue("There is a gym"), {
      target: { value: "Just one answer" },
    });
    expect(
      screen.queryByText("grading.answerTable.acceptedVariants:"),
    ).not.toBeInTheDocument();

    fireEvent.change(screen.getByDisplayValue("Just one answer"), {
      target: { value: "Just one answer|" },
    });
    expect(
      screen.queryByText("grading.answerTable.acceptedVariants:"),
    ).not.toBeInTheDocument();
  });

  it("多空题每一空独立亮牌", () => {
    renderDialog();
    fireEvent.change(screen.getByDisplayValue("甲"), {
      target: { value: "甲一|甲二" },
    });
    expect(screen.getByText("1. 甲一")).toBeInTheDocument();
    expect(screen.getByText("2. 甲二")).toBeInTheDocument();
    // 另一空没写 |，不亮
    expect(screen.getAllByText("grading.answerTable.acceptedVariants:")).toHaveLength(1);
  });
});
