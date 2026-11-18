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
  const actual = await vi.importActual<typeof import("@/services/gradingApi")>(
    "@/services/gradingApi",
  );
  return {
    ...actual,
    gradingImageUrl: (url: string) => url,
  };
});

type Box = [number, number, number, number];

function makeQ(
  questionId: string,
  displayNo: number,
  regionLabel: string,
  slotLabels: string[],
  yBase: number,
) {
  return {
    question_id: questionId,
    display_no: displayNo,
    question_type: "",
    question_text: "",
    regions: [
      {
        region_id: `${questionId}-r`,
        label: regionLabel,
        role: "question" as const,
        order: 1,
        bbox: [100, yBase, 300, yBase + 80] as Box,
      },
    ],
    answer_slots: slotLabels.map((label, index) => ({
      slot_id: `${questionId}-s${index}`,
      label,
      order: index + 1,
      bbox: [120, yBase + 100 + index * 60, 260, yBase + 140 + index * 60] as Box,
      regions: [],
      max_score: 1,
    })),
  };
}

function makePage(pageNo: number, questions: ReturnType<typeof makeQ>[]): ReferenceLayoutPage {
  return {
    page_no: pageNo,
    filename: `paper-${pageNo}.jpg`,
    image_url: `/paper-${pageNo}.jpg`,
    image_size: [800, 1200] as [number, number],
    questions,
  };
}

const moveUpButtons = () =>
  screen.getAllByRole("button", { name: "grading.layout.moveUp" });
const moveDownButtons = () =>
  screen.getAllByRole("button", { name: "grading.layout.moveDown" });

async function confirmAndCapture(onConfirm: ReturnType<typeof vi.fn>) {
  fireEvent.click(
    screen.getByRole("button", { name: /grading\.layout\.confirm/ }),
  );
  await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
  return onConfirm.mock.calls[0][0] as ReferenceLayoutPage[];
}

describe("ReferenceLayoutCorrectionDialog 手动排序（11.11-1）", () => {
  it("下移交换相邻题并整卷全局重编号，标签跟着新题号走", async () => {
    const onConfirm = vi.fn();
    const pages = [
      makePage(1, [
        makeQ("q1", 1, "1-A", ["1_1"], 100),
        makeQ("q2", 2, "2-A", ["2_1"], 400),
      ]),
    ];
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

    // 第 1 题下移（第 1 题的下移按钮）
    fireEvent.click(moveDownButtons()[0]);
    const saved = await confirmAndCapture(onConfirm);

    const questions = saved[0].questions;
    // 数组序 = 老师的排法：q2 在前；题号全局连续重编
    expect(questions.map((q) => q.question_id)).toEqual(["q2", "q1"]);
    expect(questions.map((q) => q.display_no)).toEqual([1, 2]);
    // question_id 不变（后端按 q-{原号} 认领原题的锚）
    // 区域/作答区标签跟新题号
    expect(questions[0].regions[0].label).toBe("1-A");
    expect(questions[0].answer_slots[0].label).toBe("1_1");
    expect(questions[1].regions[0].label).toBe("2-A");
    expect(questions[1].answer_slots[0].label).toBe("2_1");
  });

  it("上移/下移边界按钮禁用", () => {
    const pages = [
      makePage(1, [makeQ("q1", 1, "1-A", ["1_1"], 100)]),
    ];
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
    expect(moveUpButtons()[0]).toBeDisabled();
    expect(moveDownButtons()[0]).toBeDisabled();
  });

  it("跨页全局连续编号：P2 的题在 P1 重排后接着编，不按页各自从头来", async () => {
    const onConfirm = vi.fn();
    // 卷面号本来就乱：P1 是 5、9，P2 是 12
    const pages = [
      makePage(1, [
        makeQ("q5", 5, "5-A", ["5_1"], 100),
        makeQ("q9", 9, "9-A", ["9_1"], 400),
      ]),
      makePage(2, [makeQ("q12", 12, "12-A", ["12_1"], 100)]),
    ];
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

    // P1 第 1 题下移 → P1 变 9、5；重编号后 P1=1,2，P2 接着 3
    fireEvent.click(moveDownButtons()[0]);
    const saved = await confirmAndCapture(onConfirm);

    expect(
      saved[0].questions.map((q) => [q.question_id, q.display_no]),
    ).toEqual([
      ["q9", 1],
      ["q5", 2],
    ]);
    expect(
      saved[1].questions.map((q) => [q.question_id, q.display_no]),
    ).toEqual([["q12", 3]]);
  });

  it("无 question_id 的旧数据：重编号前先补铸号 q-{原号}", async () => {
    const onConfirm = vi.fn();
    const legacy = makeQ("", 4, "4-A", ["4_1"], 400);
    const pages = [makePage(1, [makeQ("q5", 5, "5-A", ["5_1"], 100), legacy])];
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

    // 第 1 题下移 → [旧题(4), q5]；旧题铸号 q-4（原号），题号变 1
    fireEvent.click(moveDownButtons()[0]);
    const saved = await confirmAndCapture(onConfirm);

    const questions = saved[0].questions;
    expect(questions.map((q) => q.question_id)).toEqual(["q-4", "q5"]);
    expect(questions.map((q) => q.display_no)).toEqual([1, 2]);
  });

  it("新增题目框的题号取整卷最大号+1（不按页从头撞号）", async () => {
    const onConfirm = vi.fn();
    const pages = [
      makePage(1, [makeQ("q1", 1, "1-A", ["1_1"], 100)]),
      makePage(2, [makeQ("q2", 7, "7-A", ["7_1"], 100)]),
    ];
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

    // 在 P1 画一个新题框：整卷最大号是 7，新题应为 8（不是 P1 的 2）
    fireEvent.click(
      screen.getByRole("button", { name: /grading\.layout\.addQuestion/ }),
    );
    const stage = screen.getByTestId("reference-layout-stage");
    const renderedWidth = Number(stage.getAttribute("width"));
    const renderedHeight = Number(stage.getAttribute("height"));
    const clientPoint = (x: number, y: number) => ({
      clientX: (x * renderedWidth) / 800,
      clientY: (y * renderedHeight) / 1200,
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
    fireEvent.pointerDown(stage, clientPoint(400, 600));
    fireEvent.pointerMove(window, clientPoint(500, 700));
    fireEvent.pointerUp(window, clientPoint(500, 700));

    const saved = await confirmAndCapture(onConfirm);
    const added = saved[0].questions[saved[0].questions.length - 1];
    expect(added.display_no).toBe(8);
  });
});
