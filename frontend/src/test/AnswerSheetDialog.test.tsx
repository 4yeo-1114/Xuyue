import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AnswerSheetDialog } from "@/components/grading/AnswerSheetDialog";
import type { AnswerSheetRow } from "@/services/gradingApi";

vi.mock("@/contexts/LocaleContext", () => ({
  useLocale: () => ({
    t: (key: string, params?: Record<string, unknown>) =>
      params ? `${key}:${JSON.stringify(params)}` : key,
  }),
}));

const rows: AnswerSheetRow[] = [
  { no: "1", answer: "D" },
  { no: "2", answer: "海日生残夜" },
];

function renderDialog(
  overrides: Partial<Parameters<typeof AnswerSheetDialog>[0]> = {},
) {
  const onOpenChange = vi.fn();
  const onRescan = vi.fn().mockResolvedValue(undefined);
  const onConfirm = vi.fn().mockResolvedValue(undefined);
  render(
    <AnswerSheetDialog
      open
      rows={rows}
      loading={false}
      saving={false}
      onOpenChange={onOpenChange}
      onRescan={onRescan}
      onConfirm={onConfirm}
      {...overrides}
    />,
  );
  return { onOpenChange, onRescan, onConfirm };
}

describe("AnswerSheetDialog", () => {
  it("lists every recognized row with question number and answer", () => {
    renderDialog();

    expect(screen.getByDisplayValue("1")).toBeInTheDocument();
    expect(screen.getByDisplayValue("D")).toBeInTheDocument();
    expect(screen.getByDisplayValue("2")).toBeInTheDocument();
    expect(screen.getByDisplayValue("海日生残夜")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "grading.answerSheet.merge" }),
    ).toBeEnabled();
  });

  it("confirms with edited drafts (question numbers are editable)", async () => {
    const { onConfirm } = renderDialog();

    // 把第 2 行题号改成 3、答案改掉——专窗核对后按这些题号合并
    fireEvent.change(screen.getByDisplayValue("2"), {
      target: { value: "3" },
    });
    fireEvent.change(screen.getByDisplayValue("海日生残夜"), {
      target: { value: "江春入旧年" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "grading.answerSheet.merge" }),
    );

    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    expect(onConfirm).toHaveBeenCalledWith([
      { no: "1", answer: "D" },
      { no: "3", answer: "江春入旧年" },
    ]);
  });

  it("adds an empty row", () => {
    renderDialog();

    fireEvent.click(
      screen.getByRole("button", { name: "grading.answerSheet.addRow" }),
    );
    // 原 2 行 + 新空行
    expect(document.querySelectorAll("textarea")).toHaveLength(3);
  });

  it("removes a row via its trash button", () => {
    renderDialog();
    const trashButtons = screen
      .getAllByRole("button")
      .filter((b) => !b.textContent?.trim());
    // 行内只有删除按钮是无文字的小按钮（重扫/加行/合并都带文案）
    expect(trashButtons.length).toBeGreaterThanOrEqual(2);
    fireEvent.click(trashButtons[0]);
    expect(screen.queryByDisplayValue("1")).not.toBeInTheDocument();
    expect(screen.getByDisplayValue("2")).toBeInTheDocument();
  });

  it("triggers rescan", async () => {
    const { onRescan } = renderDialog();
    fireEvent.click(
      screen.getByRole("button", { name: "grading.answerSheet.rescan" }),
    );
    await waitFor(() => expect(onRescan).toHaveBeenCalledTimes(1));
  });

  it("shows loading overlay and empty state", () => {
    const { rerender } = render(
      <AnswerSheetDialog
        open
        rows={[]}
        loading={false}
        saving={false}
        onOpenChange={vi.fn()}
        onRescan={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );
    expect(
      screen.getByText("grading.answerSheet.empty"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "grading.answerSheet.merge" }),
    ).toBeDisabled();

    rerender(
      <AnswerSheetDialog
        open
        rows={[]}
        loading
        saving={false}
        onOpenChange={vi.fn()}
        onRescan={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );
    expect(
      screen.getByText("grading.answerSheet.loading"),
    ).toBeInTheDocument();
  });

  it("surfaces scan errors", () => {
    renderDialog({ error: "VL 超时" });
    expect(screen.getByText("VL 超时")).toBeInTheDocument();
  });
});
