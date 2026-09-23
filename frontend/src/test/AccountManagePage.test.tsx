import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AccountManagePage } from "@/components/settings/account-manage/AccountManagePage";

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({
    user: {
      id: "admin-1",
      email: "admin@example.com",
      display_name: "管理员",
      roles: ["系统管理员"],
    },
  }),
}));

vi.mock("@/contexts/LocaleContext", () => ({
  useLocale: (() => {
    const t = (key: string) => key;
    return () => ({ locale: "zh", t });
  })(),
}));

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
  },
}));

const accounts = [
  {
    id: "admin-1",
    email: "admin@example.com",
    display_name: "管理员",
    roles: ["系统管理员"],
    created_at: "2026-01-01",
  },
  {
    id: "teacher-1",
    email: "teacher1@example.com",
    display_name: "教师一",
    roles: ["任课教师"],
    created_at: "2026-01-01",
  },
  {
    id: "teacher-2",
    email: "teacher2@example.com",
    display_name: "教师二",
    roles: ["任课教师"],
    created_at: "2026-01-01",
  },
];

describe("AccountManagePage batch delete", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("selects multiple deletable accounts and submits them in one request", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/admin/users/batch-delete") && init?.method === "POST") {
        return {
          ok: true,
          json: async () => ({ data: { deleted_count: 2, deleted_ids: ["teacher-1", "teacher-2"] } }),
        };
      }
      return {
        ok: true,
        json: async () => ({ data: accounts }),
      };
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<AccountManagePage />);
    await screen.findByText("教师一");

    fireEvent.click(screen.getByRole("button", { name: "account.multiDelete.button" }));
    const accountCheckboxes = screen.getAllByRole("checkbox");
    expect(accountCheckboxes).toHaveLength(2);
    fireEvent.click(accountCheckboxes[0]);
    fireEvent.click(accountCheckboxes[1]);

    fireEvent.click(screen.getByRole("button", { name: "account.multiDelete.deleteSelected" }));
    fireEvent.change(screen.getByPlaceholderText("account.form.verifyPasswordPlaceholder"), {
      target: { value: "admin-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "account.multiDelete.confirm" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/admin/users/batch-delete"),
        expect.objectContaining({ method: "POST" }),
      );
    });
    const request = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/admin/users/batch-delete"));
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({
      user_ids: ["teacher-1", "teacher-2"],
      caller_password: "admin-password",
    });
  });
});
