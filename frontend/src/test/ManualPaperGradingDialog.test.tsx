import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ManualPaperGradingDialog } from "@/components/grading/ManualPaperGradingDialog";

vi.mock("@/contexts/LocaleContext", () => ({
  useLocale: () => ({
    t: (key: string, values?: Record<string, string>) => key === "grading.manual.scoreMark"
      ? `score-mark-${values?.score}`
      : key,
  }),
}));

vi.mock("@/services/gradingApi", async () => {
  const actual = await vi.importActual<typeof import("@/services/gradingApi")>("@/services/gradingApi");
  return { ...actual, gradingImageUrl: (url: string) => url };
});

const result = JSON.stringify({
  type: "manual_analyze",
  version: 2,
  image_size: [800, 1200],
  blocks: [
    { slot_id: "s1", label: "1_1", bbox: [100, 100, 260, 220], max_score: 4, status: "ungraded", score: null },
    { slot_id: "s2", label: "1_2", bbox: [300, 100, 460, 220], max_score: 2, status: "ungraded", score: null },
  ],
});

const answerBoxes = () => document.querySelectorAll("[data-manual-grade-slot] rect");

describe("ManualPaperGradingDialog", () => {
  it("records correct and partial decisions by stable slot id", async () => {
    const onSave = vi.fn();
    render(
      <ManualPaperGradingDialog
        open
        filename="student_1.jpg"
        imageUrl="/student_1.jpg"
        result={result}
        hasNext
        onOpenChange={vi.fn()}
        onSave={onSave}
      />,
    );

    const boxes = answerBoxes();
    fireEvent.click(boxes[0]);
    fireEvent.click(screen.getByRole("button", { name: "grading.manual.correct" }));
    expect(screen.getByText("√")).toHaveAttribute("fill", "#FF0000");

    fireEvent.click(boxes[1]);
    fireEvent.click(screen.getByRole("button", { name: "grading.manual.partial" }));
    const partialLine = document.querySelector("[data-manual-mark='partial'] line") as SVGLineElement;
    expect(partialLine).toBeInTheDocument();
    expect(Number(partialLine.getAttribute("y2"))).toBeGreaterThan(Number(partialLine.getAttribute("y1")));
    fireEvent.change(screen.getByPlaceholderText("grading.manual.partialScore"), { target: { value: "1" } });

    fireEvent.click(screen.getByRole("button", { name: "grading.manual.save" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave.mock.calls[0][0]).toEqual({
      s1: { status: "correct", score: 4 },
      s2: { status: "partial", score: 1 },
    });
    expect(onSave.mock.calls[0][1]).toBe(false);
  });

  it("circles the whole answer region when it is unanswered", () => {
    render(
      <ManualPaperGradingDialog
        open
        filename="student_1.jpg"
        imageUrl="/student_1.jpg"
        result={result}
        onOpenChange={vi.fn()}
        onSave={vi.fn()}
      />,
    );

    fireEvent.click(answerBoxes()[0]);
    fireEvent.click(screen.getByRole("button", { name: "grading.manual.unanswered" }));

    const mark = document.querySelector("[data-manual-mark='unanswered']") as SVGEllipseElement;
    expect(mark.tagName.toLowerCase()).toBe("ellipse");
    expect(Number(mark.getAttribute("rx"))).toBeGreaterThan(80);
    expect(Number(mark.getAttribute("ry"))).toBeGreaterThan(60);
    expect(mark).toHaveAttribute("stroke", "#FF0000");
  });

  it("grades the selected region with keyboard shortcuts and advances with Enter", async () => {
    const onSave = vi.fn();
    render(
      <ManualPaperGradingDialog
        open
        filename="student_1.jpg"
        imageUrl="/student_1.jpg"
        result={result}
        onOpenChange={vi.fn()}
        onSave={onSave}
      />,
    );

    const boxes = answerBoxes();
    fireEvent.click(boxes[0]);
    fireEvent.keyDown(window, { key: "1" });
    fireEvent.keyDown(window, { key: "Enter" });
    fireEvent.keyDown(window, { key: "2" });

    fireEvent.click(screen.getByRole("button", { name: "grading.manual.save" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave.mock.calls[0][0]).toEqual({
      s1: { status: "correct", score: 4 },
      s2: { status: "wrong", score: 0 },
    });
  });

  it("dismisses the grading menu when clicking outside an answer region", async () => {
    render(
      <ManualPaperGradingDialog
        open
        filename="student_1.jpg"
        imageUrl="/student_1.jpg"
        result={result}
        onOpenChange={vi.fn()}
        onSave={vi.fn()}
      />,
    );

    fireEvent.click(answerBoxes()[0]);
    expect(screen.getByRole("button", { name: "grading.manual.correct" })).toBeInTheDocument();

    fireEvent.pointerDown(screen.getByText("student_1.jpg"));
    await waitFor(() => expect(screen.queryByRole("button", { name: "grading.manual.correct" })).not.toBeInTheDocument());
  });

  it("automatically persists a decision as soon as it is made", async () => {
    const onAutoSave = vi.fn();
    render(
      <ManualPaperGradingDialog
        open
        filename="student_1.jpg"
        imageUrl="/student_1.jpg"
        result={result}
        onOpenChange={vi.fn()}
        onSave={vi.fn()}
        onAutoSave={onAutoSave}
      />,
    );

    fireEvent.click(answerBoxes()[0]);
    fireEvent.click(screen.getByRole("button", { name: "grading.manual.correct" }));

    await waitFor(() => expect(onAutoSave).toHaveBeenCalledWith({
      s1: { status: "correct", score: 4 },
      s2: { status: "ungraded", score: null },
    }, { questionNotes: {}, paperNote: "" }));
  });

  it("shows the current page score as a mark in the upper-left of the paper", async () => {
    render(
      <ManualPaperGradingDialog
        open
        filename="student_1.jpg"
        imageUrl="/student_1.jpg"
        result={result}
        onOpenChange={vi.fn()}
        onSave={vi.fn()}
      />,
    );

    expect(screen.getByText("score-mark-0")).toBeInTheDocument();
    fireEvent.click(answerBoxes()[0]);
    fireEvent.click(screen.getByRole("button", { name: "grading.manual.correct" }));
    expect(screen.getByText("score-mark-4")).toBeInTheDocument();

    fireEvent.click(answerBoxes()[1]);
    fireEvent.click(screen.getByRole("button", { name: "grading.manual.partial" }));
    fireEvent.change(screen.getByPlaceholderText("grading.manual.partialScore"), { target: { value: "0.5" } });
    expect(screen.getByText("score-mark-4.5")).toBeInTheDocument();
  });

  it("shows the annotated paper without answer-region boxes in print preview", async () => {
    const onPrintPreview = vi.fn().mockResolvedValue("/annotated_student_1.jpg?t=123");
    render(
      <ManualPaperGradingDialog
        open
        filename="student_1.jpg"
        imageUrl="/student_1.jpg"
        result={result}
        onOpenChange={vi.fn()}
        onSave={vi.fn()}
        onPrintPreview={onPrintPreview}
      />,
    );

    fireEvent.click(answerBoxes()[0]);
    fireEvent.click(screen.getByRole("button", { name: "grading.manual.correct" }));
    fireEvent.click(screen.getByRole("button", { name: "grading.manual.printPreview" }));

    await waitFor(() => expect(onPrintPreview).toHaveBeenCalledWith({
      s1: { status: "correct", score: 4 },
      s2: { status: "ungraded", score: null },
    }, { questionNotes: {}, paperNote: "" }));
    await waitFor(() => expect(screen.getByAltText("student_1.jpg")).toHaveAttribute("src", "/annotated_student_1.jpg?t=123"));
    expect(document.querySelector("[data-manual-grade-slot]")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "grading.manual.returnToGrading" })).toBeInTheDocument();
  });

  it("prints the current decisions for the displayed page", async () => {
    const onPrint = vi.fn().mockResolvedValue(undefined);
    render(
      <ManualPaperGradingDialog
        open
        filename="student_1.jpg"
        imageUrl="/student_1.jpg"
        result={result}
        onOpenChange={vi.fn()}
        onSave={vi.fn()}
        onPrint={onPrint}
      />,
    );

    fireEvent.click(answerBoxes()[1]);
    fireEvent.click(screen.getByRole("button", { name: "grading.manual.wrong" }));
    fireEvent.click(screen.getByRole("button", { name: "grading.manual.printPage" }));

    await waitFor(() => expect(onPrint).toHaveBeenCalledWith({
      s1: { status: "ungraded", score: null },
      s2: { status: "wrong", score: 0 },
    }, { questionNotes: {}, paperNote: "" }));
  });

  it("keeps using the original paper and live SVG marks after autosave", () => {
    const savedResult = JSON.stringify({
      type: "manual_analyze",
      version: 2,
      image_size: [800, 1200],
      blocks: [
        { slot_id: "s1", label: "1_1", bbox: [100, 100, 260, 220], max_score: 4, status: "correct", score: 4 },
        { slot_id: "s2", label: "1_2", bbox: [300, 100, 460, 220], max_score: 2, status: "wrong", score: 0 },
      ],
    });
    render(
      <ManualPaperGradingDialog
        open
        filename="student_1.jpg"
        imageUrl="/student_1.jpg"
        result={savedResult}
        onOpenChange={vi.fn()}
        onSave={vi.fn()}
      />,
    );

    expect(screen.getByAltText("student_1.jpg")).toHaveAttribute("src", "/student_1.jpg");
    expect(screen.getByText("score-mark-4")).toBeInTheDocument();
    expect(answerBoxes()).toHaveLength(2);
  });

  it("keeps the live SVG mark size equal on portrait and landscape papers", () => {
    const renderedMarkSize = (filename: string, imageSize: [number, number]) => {
      const sizedResult = JSON.stringify({
        type: "manual_analyze",
        version: 2,
        image_size: imageSize,
        blocks: [
          {
            slot_id: "s1",
            label: "1_1",
            bbox: [imageSize[0] * 0.2, imageSize[1] * 0.2, imageSize[0] * 0.5, imageSize[1] * 0.35],
            max_score: 4,
            status: "ungraded",
            score: null,
          },
        ],
      });
      const view = render(
        <ManualPaperGradingDialog
          open
          filename={filename}
          imageUrl={`/${filename}`}
          result={sizedResult}
          onOpenChange={vi.fn()}
          onSave={vi.fn()}
        />,
      );
      fireEvent.click(answerBoxes()[0]);
      fireEvent.click(screen.getByRole("button", { name: "grading.manual.correct" }));
      const mark = document.querySelector("[data-manual-grade-slot] text") as SVGTextElement;
      const svg = mark.closest("svg") as SVGSVGElement;
      const paper = svg.parentElement as HTMLDivElement;
      const sourceWidth = Number(svg.getAttribute("viewBox")?.split(/\s+/)[2]);
      const displayWidth = Number.parseFloat(paper.style.width);
      const displaySize = Number(mark.getAttribute("font-size")) * displayWidth / sourceWidth;
      view.unmount();
      return displaySize;
    };

    const portraitSize = renderedMarkSize("portrait.jpg", [1200, 1800]);
    const landscapeSize = renderedMarkSize("landscape.jpg", [1800, 1200]);
    expect(portraitSize).toBeCloseTo(38, 5);
    expect(landscapeSize).toBeCloseTo(38, 5);
  });
});
