import { describe, expect, it, vi } from "vitest";
import { render, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

// 本仓测试环境无 VITE_SUPABASE_URL（预存在的环境性缺口），隔离 supabase 客户端本身。
vi.mock("@/integrations/supabase/client", () => ({ supabase: {} }));

/** 当前账号注入点：Sidebar 读 useAuth().user，用 hoisted 句柄在每例前改写 */
const h = vi.hoisted(() => ({ user: null as unknown }));

vi.mock("@/hooks/useAuth", () => ({ useAuth: () => ({ user: h.user }) }));
vi.mock("@/contexts/ProjectBrandingContext", () => ({
  useProjectBranding: () => ({ projectName: "test" }),
}));
vi.mock("@/contexts/LocaleContext", () => ({
  useLocale: () => ({
    t: (_k: string, _o?: unknown, fallback?: string) => fallback ?? _k,
    locale: "zh",
  }),
}));
vi.mock("@/hooks/useFeatureFlags", () => ({
  useFeatureFlags: () => ({ data: [] }),
}));
vi.mock("@/services/gradingApi", () => ({ exitPackagedApp: vi.fn() }));
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));
vi.mock("@/components/BrandLogo", () => ({ BrandLogo: () => null }));

import { Sidebar, NAV_ITEMS } from "@/components/Sidebar";
import { isNavItemVisible } from "@/lib/adminAccess";
import type { AuthUser } from "@/hooks/useAuth";

const PAYMENT_IDS = ["payment-wallet", "payment-ledger"] as const;

const makeUser = (...roles: string[]): AuthUser => ({
  id: "u-1",
  email: "u@example.com",
  roles,
});

const TEACHER_ONLY = makeUser("任课教师");
const CLASS_TEACHER = makeUser("班主任");
const PLATFORM_ADMIN = makeUser("系统管理员");
const SCHOOL_ADMIN = makeUser("校级管理者");
const GRADE_LEADER = makeUser("年级组长");

const ALL_GROUP_IDS = NAV_ITEMS.map((g) => g.id);

/* ── 路径 A：谓词 isNavItemVisible（与界面同一判据） ── */
function predicateVisibleIds(u: AuthUser): string[] {
  return NAV_ITEMS.flatMap((g) => g.children ?? [])
    .filter((item) => isNavItemVisible(u, item))
    .map((item) => item.id)
    .sort();
}

function predicateHasPayment(u: AuthUser): Record<string, boolean> {
  const all = NAV_ITEMS.flatMap((g) => g.children ?? []);
  return Object.fromEntries(
    PAYMENT_IDS.map((id) => {
      const item = all.find((i) => i.id === id);
      if (!item) throw new Error(`NAV_ITEMS 里找不到 ${id}`);
      return [id, isNavItemVisible(u, item)];
    }),
  );
}

/* ── 路径 B：真实渲染 <Sidebar>，收集它实际给出的 nav id ──
 * Sidebar 有自己的过滤层（filteredNavItems = isNavItemVisible × featureKey 开关），
 * 所以「谓词放行」不等于「侧栏渲染出来」——必须真渲染一次才算数。
 * 做法：先把所有分组置为展开（localStorage 预置），然后点击 nav 内每一个**叶子**
 * 按钮（其最近 li 不含 ul），记录 onNavChange 收到的 id = 实际渲染出的 nav id 集合。 */
function renderedNavIds(u: AuthUser | null): string[] {
  h.user = u;
  localStorage.setItem(
    "sidebar-expanded-groups",
    JSON.stringify(ALL_GROUP_IDS),
  );
  const clicked: string[] = [];
  const { container } = render(
    <MemoryRouter>
      <Sidebar activeNavId="home" onNavChange={(id) => clicked.push(id)} />
    </MemoryRouter>,
  );
  const nav = container.querySelector("nav");
  if (!nav) throw new Error("Sidebar 未渲染出 <nav>");
  const buttons = Array.from(nav.querySelectorAll("button"));
  for (const b of buttons) {
    const li = b.closest("li");
    if (li && li.querySelector("ul")) continue; // 分组折叠按钮，不是 nav 目标
    fireEvent.click(b);
  }
  return Array.from(new Set(clicked)).sort();
}

describe("验收：余额/流水入口对所有登录角色可见（2026-09-30「所有账号都要可以支付」）", () => {
  it("三类账号 × 两条路径的实测输出（原文打印，供人工核对）", () => {
    const samples: Array<[string, AuthUser]> = [
      ["任课教师(独立老师)", TEACHER_ONLY],
      ["班主任(校内老师)", CLASS_TEACHER],
      ["系统管理员", PLATFORM_ADMIN],
    ];
    for (const [label, u] of samples) {
      const pred = predicateHasPayment(u);
      const rendered = renderedNavIds(u);
      // eslint-disable-next-line no-console
      console.log(
        `[实测] ${label} | isNavItemVisible=${JSON.stringify(pred)} | 侧栏实际渲染nav ids=${JSON.stringify(rendered)}`,
      );
      expect(rendered.length).toBeGreaterThan(0);
    }
  });

  it("独立老师：两条路径都必须放行余额/流水", () => {
    expect(predicateHasPayment(TEACHER_ONLY)).toEqual({
      "payment-wallet": true,
      "payment-ledger": true,
    });
    const rendered = renderedNavIds(TEACHER_ONLY);
    for (const id of PAYMENT_IDS) expect(rendered).toContain(id);
  });

  it("2026-09-30 放开：非任课教师角色同样可见 payment-wallet / payment-ledger", () => {
    const nonTeachers: Array<[string, AuthUser]> = [
      ["班主任", CLASS_TEACHER],
      ["校级管理者", SCHOOL_ADMIN],
      ["年级组长", GRADE_LEADER],
    ];
    for (const [label, u] of nonTeachers) {
      const pred = predicateHasPayment(u);
      expect(pred, `${label} 谓词应放行`).toEqual({
        "payment-wallet": true,
        "payment-ledger": true,
      });
      const rendered = renderedNavIds(u);
      for (const id of PAYMENT_IDS) {
        expect(rendered, `${label} 侧栏应渲染 ${id}`).toContain(id);
      }
    }
  });

  it("平台管理员仍可见（既有 adminOnly 语义，行为不变）", () => {
    expect(predicateHasPayment(PLATFORM_ADMIN)).toEqual({
      "payment-wallet": true,
      "payment-ledger": true,
    });
    const rendered = renderedNavIds(PLATFORM_ADMIN);
    for (const id of PAYMENT_IDS) expect(rendered).toContain(id);
  });

  it("回归：校内老师未被误伤其他入口（抽样）", () => {
    const rendered = renderedNavIds(CLASS_TEACHER);
    expect(rendered).toEqual(
      expect.arrayContaining(["home", "settings-personal"]),
    );
  });
});
