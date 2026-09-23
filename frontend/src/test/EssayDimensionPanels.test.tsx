import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  EssayDimensionConfigEditor,
  EssayDimensionScoreCard,
  parseEssayDimensions,
} from "@/components/grading/EssayDimensionPanels";
import {
  DEFAULT_DIMENSIONS,
  type EssayScorePayload,
} from "@/services/gradingApi";

const t = (key: string) => key;

const SCORES = {
  content: 20,
  structure: 15,
  language: 25,
  relevance: 12,
  presentation: 10,
};
// 20+15+25+12+10 = 82

describe("parseEssayDimensions", () => {
  it("falls back to the default five dimensions for null/empty/invalid", () => {
    expect(parseEssayDimensions(null)).toHaveLength(5);
    expect(parseEssayDimensions(undefined)).toHaveLength(5);
    expect(parseEssayDimensions("")).toHaveLength(5);
    expect(parseEssayDimensions("not-json")).toHaveLength(5);
    expect(parseEssayDimensions(JSON.stringify({ a: 1 }))).toHaveLength(5);
  });

  it("parses a valid dimensions_json array", () => {
    const dims = [
      {
        key: "a",
        name: "A",
        full_score: 10,
        weight: 0.1,
        description: "d",
        order: 1,
      },
    ];
    expect(parseEssayDimensions(JSON.stringify(dims))).toEqual(dims);
  });

  it("round-trips edited dimensions through JSON.stringify so the saved dimensions_json can be read back", () => {
    const edited = DEFAULT_DIMENSIONS.map((d, i) =>
      i === 0 ? { ...d, name: "改后维度", full_score: 30 } : d,
    );
    expect(parseEssayDimensions(JSON.stringify(edited))).toEqual(edited);
  });
});

describe("EssayDimensionConfigEditor", () => {
  it("shows the default five dimensions when the rule has no dimensions_json", () => {
    render(
      <EssayDimensionConfigEditor
        dimensions={parseEssayDimensions(null)}
        onChange={() => {}}
        t={t}
      />,
    );
    expect(
      screen.getAllByPlaceholderText("grading.dimension.namePlaceholder"),
    ).toHaveLength(5);
    expect(screen.getByDisplayValue("内容与立意")).toBeInTheDocument();
  });

  it("adds a new dimension row with full_score 10 and a unique key", () => {
    const onChange = vi.fn();
    render(
      <EssayDimensionConfigEditor
        dimensions={parseEssayDimensions(null)}
        onChange={onChange}
        t={t}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "grading.dimension.add" }),
    );
    const added = onChange.mock.calls[0][0];
    expect(added).toHaveLength(6);
    const last = added[5];
    expect(last.name).toBe("grading.dimension.newDimension");
    expect(last.full_score).toBe(10);
    expect(typeof last.key).toBe("string");
    expect(last.key).not.toBe("content");
  });

  it("deletes a row", () => {
    const onChange = vi.fn();
    render(
      <EssayDimensionConfigEditor
        dimensions={parseEssayDimensions(null)}
        onChange={onChange}
        t={t}
      />,
    );
    fireEvent.click(
      screen.getAllByRole("button", { name: "grading.dimension.delete" })[0],
    );
    const next = onChange.mock.calls[0][0];
    expect(next).toHaveLength(4);
    expect(next.some((d: { key: string }) => d.key === "content")).toBe(false);
  });

  it("restores the default dimensions", () => {
    const onChange = vi.fn();
    const custom = [
      {
        key: "x",
        name: "X",
        full_score: 100,
        weight: 1,
        description: "",
        order: 1,
      },
    ];
    render(
      <EssayDimensionConfigEditor
        dimensions={custom}
        onChange={onChange}
        t={t}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "grading.dimension.restoreDefault" }),
    );
    const next = onChange.mock.calls[0][0];
    expect(next).toHaveLength(5);
    expect(next.map((d: { key: string }) => d.key)).toEqual([
      "content",
      "structure",
      "language",
      "relevance",
      "presentation",
    ]);
  });

  it("edits a row name and full score", () => {
    const onChange = vi.fn();
    render(
      <EssayDimensionConfigEditor
        dimensions={parseEssayDimensions(null)}
        onChange={onChange}
        t={t}
      />,
    );
    fireEvent.change(
      screen.getAllByPlaceholderText("grading.dimension.namePlaceholder")[0],
      { target: { value: "主题深度" } },
    );
    expect(onChange.mock.calls[0][0][0].name).toBe("主题深度");

    fireEvent.change(
      screen.getByLabelText("内容与立意-grading.dimension.fullScoreLabel"),
      { target: { value: "30" } },
    );
    expect(onChange.mock.calls[1][0][0].full_score).toBe(30);
  });
});

describe("EssayDimensionScoreCard", () => {
  it("renders dimension bars and total score for graded essay data", () => {
    render(
      <EssayDimensionScoreCard
        dimensions={DEFAULT_DIMENSIONS}
        dimensionScores={SCORES}
        totalScore={82}
        filename="student_1.jpg"
        onSave={vi.fn()}
        t={t}
      />,
    );
    expect(screen.getByText("内容与立意")).toBeInTheDocument();
    expect(screen.getByText("20/25")).toBeInTheDocument();
    expect(screen.getByText("25/25")).toBeInTheDocument();
    expect(
      screen.getByText("grading.dimension.totalScore: 82"),
    ).toBeInTheDocument();

    const bars = document.querySelectorAll('[role="progressbar"]');
    expect(bars).toHaveLength(5);
    // content 20/25 → 80% → indicator translateX(-20%)
    const indicators = document.querySelectorAll(
      '[role="progressbar"] [class*="bg-primary"]',
    );
    expect(indicators[0].getAttribute("style")).toContain("translateX(-20%)");
  });

  it("renders nothing for legacy data without dimension_scores", () => {
    const { container } = render(
      <EssayDimensionScoreCard
        dimensions={DEFAULT_DIMENSIONS}
        dimensionScores={null}
        totalScore={82}
        filename="a.jpg"
        onSave={vi.fn()}
        t={t}
      />,
    );
    expect(container).toBeEmptyDOMElement();

    const { container: c2 } = render(
      <EssayDimensionScoreCard
        dimensions={DEFAULT_DIMENSIONS}
        dimensionScores={undefined}
        totalScore={null}
        filename="a.jpg"
        onSave={vi.fn()}
        t={t}
      />,
    );
    expect(c2).toBeEmptyDOMElement();
  });

  it("opens the edit dialog, saves new scores with the correct payload and refreshes", async () => {
    const onSaveImpl = vi.fn(async () => {});
    function Harness() {
      const [state, setState] = useState<{
        ds: Record<string, number>;
        total: number;
      }>({ ds: SCORES, total: 82 });
      const handleSave = async (p: EssayScorePayload) => {
        setState({ ds: p.dimension_scores, total: p.total_score ?? 0 });
        await onSaveImpl(p);
      };
      return (
        <EssayDimensionScoreCard
          dimensions={DEFAULT_DIMENSIONS}
          dimensionScores={state.ds}
          totalScore={state.total}
          filename="a.jpg"
          onSave={handleSave}
          t={t}
        />
      );
    }
    render(<Harness />);

    fireEvent.click(
      screen.getByRole("button", { name: "grading.dimension.editScore" }),
    );

    const contentInput = screen.getByLabelText(
      "内容与立意-grading.dimension.scorePlaceholder",
    ) as HTMLInputElement;
    expect(contentInput.value).toBe("20");
    fireEvent.change(contentInput, { target: { value: "22" } });

    fireEvent.click(
      screen.getByRole("button", { name: "grading.dimension.save" }),
    );

    await waitFor(() => expect(onSaveImpl).toHaveBeenCalledTimes(1));
    const payload = onSaveImpl.mock.calls[0][0];
    expect(payload.filename).toBe("a.jpg");
    expect(payload.dimension_scores.content).toBe(22);
    expect(payload.total_score).toBe(84); // 22+15+25+12+10
    expect(payload.regenerate_report).toBeUndefined();

    // 成功后分数刷新
    await waitFor(() => expect(screen.getByText("22/25")).toBeInTheDocument());
    expect(
      screen.getByText("grading.dimension.totalScore: 84"),
    ).toBeInTheDocument();
    // 弹窗关闭
    await waitFor(() =>
      expect(
        screen.queryByLabelText(
          "内容与立意-grading.dimension.scorePlaceholder",
        ),
      ).not.toBeInTheDocument(),
    );
  });

  it("sends regenerate_report through the save & re-grade button", async () => {
    const onSaveImpl = vi.fn(async () => {});
    function Harness() {
      const [state, setState] = useState<{
        ds: Record<string, number>;
        total: number;
      }>({ ds: SCORES, total: 82 });
      const handleSave = async (p: EssayScorePayload) => {
        setState({ ds: p.dimension_scores, total: p.total_score ?? 0 });
        await onSaveImpl(p);
      };
      return (
        <EssayDimensionScoreCard
          dimensions={DEFAULT_DIMENSIONS}
          dimensionScores={state.ds}
          totalScore={state.total}
          filename="a.jpg"
          onSave={handleSave}
          t={t}
        />
      );
    }
    render(<Harness />);

    fireEvent.click(
      screen.getByRole("button", { name: "grading.dimension.editScore" }),
    );
    fireEvent.click(
      screen.getByRole("button", {
        name: "grading.dimension.saveAndRegenerate",
      }),
    );

    await waitFor(() => expect(onSaveImpl).toHaveBeenCalledTimes(1));
    expect(onSaveImpl.mock.calls[0][0].regenerate_report).toBe(true);
  });
});
