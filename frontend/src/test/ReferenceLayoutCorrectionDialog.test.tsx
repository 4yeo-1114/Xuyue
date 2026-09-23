import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ReferenceLayoutCorrectionDialog } from "@/components/grading/ReferenceLayoutCorrectionDialog";
import type { ReferenceLayoutPage } from "@/services/gradingApi";

vi.mock("@/contexts/LocaleContext", () => ({
  useLocale: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock("@/services/gradingApi", async () => {
  const actual = await vi.importActual<typeof import("@/services/gradingApi")>("@/services/gradingApi");
  return {
    ...actual,
    gradingImageUrl: (url: string) => url,
  };
});

const pages: ReferenceLayoutPage[] = [
  {
    page_no: 1,
    filename: "paper-1.jpg",
    image_url: "/paper-1.jpg",
    image_size: [800, 1200] as [number, number],
    questions: [
      {
        question_id: "q1",
        display_no: 1,
        question_type: "",
        question_text: "",
        regions: [
          {
            region_id: "r1",
            label: "1-A",
            role: "question",
            order: 1,
            bbox: [100, 100, 300, 300] as [number, number, number, number],
          },
        ],
        answer_slots: [],
      },
    ],
  },
];

describe("ReferenceLayoutCorrectionDialog", () => {
  it("enables add-answer only after a question is selected", () => {
    render(
      <ReferenceLayoutCorrectionDialog
        open
        pages={pages}
        loading={false}
        preparing={false}
        onOpenChange={vi.fn()}
        onConfirm={vi.fn()}
        onReprepare={vi.fn()}
      />,
    );

    const addAnswerButton = screen.getByRole("button", {
      name: /grading\.layout\.addAnswer/,
    });
    expect(addAnswerButton).toBeDisabled();

    fireEvent.click(
      screen.getByRole("button", {
        name: /grading\.layout\.question/,
      }),
    );

    expect(
      screen.getByRole("button", {
        name: /grading\.layout\.addAnswer/,
      }),
    ).toBeEnabled();
  });

  it("adds consecutive answer regions with visible labels and saves them", async () => {
    const onConfirm = vi.fn();
    render(
      <ReferenceLayoutCorrectionDialog
        open
        pages={pages}
        loading={false}
        preparing={false}
        onOpenChange={vi.fn()}
        onConfirm={onConfirm}
        onReprepare={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /grading\.layout\.question/ }));
    fireEvent.click(screen.getByRole("button", { name: /grading\.layout\.addAnswer/ }));

    const stage = screen.getByTestId("reference-layout-stage");
    expect(stage).toHaveAttribute("data-edit-mode", "answer");
    expect(stage).toHaveAttribute("data-draw-question-id", "q1");
    const renderedWidth = Number(stage.getAttribute("width"));
    const renderedHeight = Number(stage.getAttribute("height"));
    const clientPoint = (x: number, y: number) => ({
      clientX: x * renderedWidth / 800,
      clientY: y * renderedHeight / 1200,
    });
    vi.spyOn(stage, "getBoundingClientRect").mockReturnValue({
      x: 0,
      y: 0,
      left: 0,
      top: 0,
      right: renderedWidth,
      bottom: renderedHeight,
      width: renderedWidth,
      height: renderedHeight,
      toJSON: () => ({}),
    } as DOMRect);

    fireEvent.pointerDown(stage, clientPoint(120, 120));
    fireEvent.pointerMove(window, clientPoint(180, 180));
    expect(screen.getByTestId("reference-layout-preview-box")).toBeInTheDocument();
    fireEvent.pointerUp(window, clientPoint(180, 180));
    await waitFor(() => expect(screen.getByText("1_1")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /1_1/ })).toBeInTheDocument();

    fireEvent.pointerDown(stage, clientPoint(200, 200));
    fireEvent.pointerMove(window, clientPoint(260, 260));
    fireEvent.pointerUp(window, clientPoint(260, 260));
    await waitFor(() => expect(screen.getByText("1_2")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /1_2/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /grading\.layout\.confirm/ }));
    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    const savedPages = onConfirm.mock.calls[0][0] as ReferenceLayoutPage[];
    expect(savedPages[0].questions[0].answer_slots.map((slot) => slot.label)).toEqual(["1_1", "1_2"]);
  });

  it("sets one score for every answer region in a question", async () => {
    const onConfirm = vi.fn();
    const scoringPages: ReferenceLayoutPage[] = JSON.parse(JSON.stringify(pages));
    scoringPages[0].questions[0].answer_slots = [
      { slot_id: "s1", label: "1_1", order: 1, bbox: [120, 150, 180, 210], regions: [], max_score: 1 },
      { slot_id: "s2", label: "1_2", order: 2, bbox: [200, 150, 260, 210], regions: [], max_score: 1 },
    ];
    render(
      <ReferenceLayoutCorrectionDialog
        open
        pages={scoringPages}
        loading={false}
        preparing={false}
        variant="manual"
        scoringEnabled
        onOpenChange={vi.fn()}
        onConfirm={onConfirm}
        onReprepare={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("grading.manualLayout.score"), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "grading.manualLayout.applyQuestionScore" }));
    fireEvent.click(screen.getByRole("button", { name: /grading\.layout\.confirm/ }));

    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    const savedPages = onConfirm.mock.calls[0][0] as ReferenceLayoutPage[];
    expect(savedPages[0].questions[0].answer_slots.map((slot) => slot.max_score)).toEqual([3, 3]);
  });
});
