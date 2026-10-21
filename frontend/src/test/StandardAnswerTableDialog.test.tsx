import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StandardAnswerTableDialog } from "@/components/grading/StandardAnswerTableDialog";
import type { ReferenceAnswerTablePage } from "@/services/gradingApi";

vi.mock("@/contexts/LocaleContext", () => ({
  useLocale: () => ({
    t: (key: string) => key,
  }),
}));

// 只用 gradingImageUrl 拼 <img> 直链，mock 掉避免拖入整个 API 客户端
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
        printed_no: "1",
        slots: [
          {
            sub_index: 1,
            bbox: [0, 0, 10, 10],
            answer_text: "D",
            region_url: "/api/v1/grading/folders/f/answer-table/region-image?page_no=1&x1=0&y1=0&x2=10&y2=10&ticket=t",
          },
        ],
        full_answer: "D",
      },
      {
        display_index: 8,
        printed_no: "8",
        slots: [
          { sub_index: 1, bbox: [0, 0, 10, 10], answer_text: "海日生残夜" },
          { sub_index: 2, bbox: [0, 0, 10, 10], answer_text: "江春入旧年" },
        ],
        full_answer: "海日生残夜\n江春入旧年",
        edited: true,
      },
    ],
  },
];

function renderDialog(overrides: Partial<Parameters<typeof StandardAnswerTableDialog>[0]> = {}) {
  const onSave = vi.fn().mockResolvedValue(undefined);
  const onRebuild = vi.fn().mockResolvedValue(undefined);
  const { container } = render(
    <StandardAnswerTableDialog
      open
      pages={pages}
      loading={false}
      saving={false}
      onOpenChange={vi.fn()}
      onSave={onSave}
      onRebuild={onRebuild}
      {...overrides}
    />,
  );
  return { onSave, onRebuild, container };
}

describe("StandardAnswerTableDialog", () => {
  it("lists every recognized answer and marks manually edited rows", () => {
    renderDialog();

    expect(screen.getByDisplayValue("D")).toBeInTheDocument();
    expect(screen.getByDisplayValue("海日生残夜")).toBeInTheDocument();
    expect(screen.getByDisplayValue("江春入旧年")).toBeInTheDocument();
    expect(screen.getByText("grading.answerTable.edited")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "grading.answerTable.save" }),
    ).toBeDisabled();
  });

  it("saves only the edited question with slot-level texts", async () => {
    const { onSave } = renderDialog();

    fireEvent.change(screen.getByDisplayValue("D"), {
      target: { value: "正解" },
    });
    const saveButton = screen.getByRole("button", {
      name: "grading.answerTable.save",
    });
    expect(saveButton).toBeEnabled();
    fireEvent.click(saveButton);

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave).toHaveBeenCalledWith(1, [
      {
        display_index: 1,
        printed_no: "1",
        slots: [{ sub_index: 1, answer_text: "正解" }],
      },
    ]);
  });

  it("rebuild can discard all manual edits after confirm", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const { onRebuild } = renderDialog();

    fireEvent.click(
      screen.getByRole("button", { name: "grading.answerTable.rebuildReset" }),
    );
    await waitFor(() => expect(onRebuild).toHaveBeenCalledWith(true));
    confirmSpy.mockRestore();
  });

  it("shows answer-area thumbnails for slots with region_url and hides them otherwise", () => {
    renderDialog();

    const thumbs = screen.getAllByAltText("grading.answerTable.regionAlt");
    // 只有第 1 题的槽带 region_url；第 8 题两个槽没带 → 不渲染缩略图
    expect(thumbs).toHaveLength(1);
    expect(thumbs[0]).toHaveAttribute(
      "src",
      expect.stringContaining("answer-table/region-image"),
    );
  });

  it("banners a blank paper when every answer is empty", () => {
    const blankPages: ReferenceAnswerTablePage[] = [
      {
        page_no: 1,
        filename: "blank.jpg",
        questions: [
          {
            display_index: 1,
            printed_no: "1",
            slots: [
              {
                sub_index: 1,
                bbox: [0, 0, 10, 10],
                answer_text: "",
                region_url: "/region?x=1",
              },
            ],
            full_answer: "",
          },
          {
            display_index: 2,
            printed_no: "2",
            slots: [{ sub_index: 1, bbox: [0, 0, 10, 10], answer_text: "" }],
            full_answer: "",
          },
        ],
      },
    ];
    renderDialog({ pages: blankPages });

    expect(
      screen.getByText("grading.answerTable.blankPaperHint"),
    ).toBeInTheDocument();
    // 空白卷也照常展示答题区缩略图（方便后续批改定位作答区）
    expect(
      screen.getAllByAltText("grading.answerTable.regionAlt"),
    ).toHaveLength(1);
  });

  it("hides the blank-paper banner once an answer is recognized", () => {
    const pagesWithAnswer: ReferenceAnswerTablePage[] = [
      {
        page_no: 1,
        filename: "std.jpg",
        questions: [
          {
            display_index: 1,
            printed_no: "1",
            slots: [{ sub_index: 1, bbox: [0, 0, 10, 10], answer_text: "D" }],
            full_answer: "D",
          },
        ],
      },
    ];
    renderDialog({ pages: pagesWithAnswer });

    expect(
      screen.queryByText("grading.answerTable.blankPaperHint"),
    ).not.toBeInTheDocument();
  });

  it("uploads answer sheets from the dialog button", async () => {
    // 空白卷模式第二上传：答案单独一张纸 →「上传答案」按钮提交给父级处理
    const onUploadAnswerSheets = vi.fn().mockResolvedValue(undefined);
    renderDialog({ onUploadAnswerSheets });

    const button = screen.getByRole("button", {
      name: "grading.answerTable.uploadAnswers",
    });
    expect(button).toBeEnabled();
    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    expect(input).toBeTruthy();
    const file = new File(["x"], "答案.jpg", { type: "image/jpeg" });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(onUploadAnswerSheets).toHaveBeenCalledTimes(1));
    // 文件必须真的传到父级：Chrome 的 input.files 是活列表，先清 value 再读会读到空
    expect(onUploadAnswerSheets).toHaveBeenCalledWith([
      expect.objectContaining({ name: "答案.jpg" }),
    ]);
  });

  it("hides the upload-answers button when no handler is provided", () => {
    renderDialog();
    expect(
      screen.queryByRole("button", { name: "grading.answerTable.uploadAnswers" }),
    ).not.toBeInTheDocument();
  });

  it("opens the box editor from the answer-area-boxes button", async () => {
    // 「答题区框」= 切题审查同款框编辑器入口：带当前页码过去改框
    const onEditBoxes = vi.fn();
    renderDialog({ onEditBoxes });

    fireEvent.click(
      screen.getByRole("button", { name: "grading.answerTable.boxEdit" }),
    );
    await waitFor(() => expect(onEditBoxes).toHaveBeenCalledWith(1));
  });

  it("opens the box editor when a thumbnail is clicked", async () => {
    // 缩略图是框的裁片：识别错了点它就能改框
    const onEditBoxes = vi.fn();
    renderDialog({ onEditBoxes });

    fireEvent.click(
      screen.getAllByAltText("grading.answerTable.regionAlt")[0],
    );
    await waitFor(() => expect(onEditBoxes).toHaveBeenCalledWith(1));
  });

  it("hides the box-edit button and thumb wrappers when no handler is provided", () => {
    renderDialog();
    expect(
      screen.queryByRole("button", { name: "grading.answerTable.boxEdit" }),
    ).not.toBeInTheDocument();
    // 无 handler 时缩略图不包按钮（裸 <img>）
    expect(
      screen.queryByRole("button", { name: "grading.answerTable.regionAlt" }),
    ).not.toBeInTheDocument();
  });

  it("draws every slot box on the box map and opens the editor from it", async () => {
    // 答题区框总览：整页图 + amber 框 + 题号_空号标签（和切题审查一样有框）
    const pagesWithMap: ReferenceAnswerTablePage[] = [
      {
        page_no: 2,
        filename: "std2.jpg",
        image_url: "/api/v1/preview/std2.jpg",
        image_size: [1000, 1400],
        questions: [
          {
            display_index: 1,
            printed_no: "1",
            slots: [
              { sub_index: 1, bbox: [100, 200, 300, 260], answer_text: "D" },
            ],
            full_answer: "D",
          },
          {
            display_index: 8,
            printed_no: "8",
            slots: [
              { sub_index: 1, bbox: [100, 400, 300, 460], answer_text: "" },
              { sub_index: 2, bbox: [100, 500, 300, 560], answer_text: "" },
            ],
            full_answer: "",
          },
        ],
      },
    ];
    const onEditBoxes = vi.fn();
    renderDialog({ pages: pagesWithMap, onEditBoxes });

    const mapImg = screen.getByAltText("grading.answerTable.boxMapAlt");
    expect(mapImg).toBeInTheDocument();
    expect(screen.getByText("1_1")).toBeInTheDocument();
    expect(screen.getByText("8_1")).toBeInTheDocument();
    expect(screen.getByText("8_2")).toBeInTheDocument();

    // Radix 弹窗 portal 到 body：从框总览图的同级 <svg> 点（别抓 document 第一个 svg，那是 lucide 图标）
    const mapSvg = mapImg.parentElement?.querySelector("svg");
    expect(mapSvg).toBeTruthy();
    fireEvent.click(mapSvg!);
    await waitFor(() => expect(onEditBoxes).toHaveBeenCalledWith(2));
  });
});
