import { describe, expect, it, vi } from "vitest";

// 本仓测试环境无 VITE_SUPABASE_URL（预存在的环境性缺口）。这里只隔离 supabase 客户端本身，
// NAV_ITEMS 是纯数据、不触网；不修改任何共享测试配置，也不去碰别人的失败文件。
vi.mock("@/integrations/supabase/client", () => ({ supabase: {} }));

import { NAV_ITEMS } from "@/components/Sidebar";
import type { NavChild } from "@/components/Sidebar";
import {
  isNavItemVisible,
  isNavPageAllowed,
  isParent,
  isPlatformAdmin,
  isSchoolAdmin,
} from "@/lib/adminAccess";
import {
  TEACHER_NAV_WHITELIST,
  TEACHER_NAV_WHITELIST_SET,
  isNavAllowedForTeacher,
  isTeacherOnlyAccount,
} from "@/constants/systemRoles";
import type { AuthUser } from "@/hooks/useAuth";

const user = (...roles: string[]): AuthUser => ({
  id: "u-1",
  email: "u@example.com",
  roles,
});

/** 侧栏全部子项（id + adminOnly/parentOnly 标记），来自真实 NAV_ITEMS */
const ALL_NAV_ITEMS: NavChild[] = NAV_ITEMS.flatMap((g) => g.children ?? []);

const INDEPENDENT_TEACHER = user("任课教师");
const SCHOOL_ADMIN = user("校级管理者");
const PLATFORM_ADMIN = user("系统管理员");

/**
 * 改动前的旧谓词 —— 逐字照抄 Sidebar.tsx 改动前那一支，作为**回归对照 oracle**。
 * ⛔ 这份拷贝存在的唯一理由就是「证明新谓词对非任课教师逐条等价」，不得被新谓词替换掉。
 */
function legacyNavItemVisible(
  u: AuthUser | null | undefined,
  item: Pick<NavChild, "id" | "adminOnly" | "parentOnly">,
): boolean {
  const isAdmin = isPlatformAdmin(u);
  const isSchoolAdminUser = isSchoolAdmin(u);
  const isParentUser = isParent(u);
  return item.parentOnly
    ? isParentUser
    : item.id === "school-dashboard" || item.id === "school-warning"
      ? isSchoolAdminUser
      : !item.adminOnly || isAdmin;
}

const visibleIdsFor = (
  u: AuthUser,
  predicate: (u: AuthUser, item: NavChild) => boolean,
): string[] =>
  ALL_NAV_ITEMS.filter((item) => predicate(u, item)).map((item) => item.id);

describe("白名单单一事实源：任课教师 + 白名单内 id ⇒ 放行", () => {
  it("白名单本身非空、无重复", () => {
    expect(TEACHER_NAV_WHITELIST.length).toBeGreaterThan(0);
    expect(new Set(TEACHER_NAV_WHITELIST).size).toBe(
      TEACHER_NAV_WHITELIST.length,
    );
  });

  it("白名单内每一个 id 都放行（判据 + 侧栏项两条路径一致）", () => {
    for (const id of TEACHER_NAV_WHITELIST) {
      expect(isNavAllowedForTeacher(id), `白名单 id 应放行: ${id}`).toBe(true);
      expect(
        isNavPageAllowed(INDEPENDENT_TEACHER, id),
        `深链应放行: ${id}`,
      ).toBe(true);
    }
  });

  it("侧栏项：白名单内的 NAV_ITEMS 子项对任课教师可见", () => {
    const visible = visibleIdsFor(INDEPENDENT_TEACHER, isNavItemVisible);
    for (const id of visible) {
      expect(TEACHER_NAV_WHITELIST_SET.has(id)).toBe(true);
    }
    // 白名单里落在 NAV_ITEMS 子项上的部分必须**全部**出现在侧栏
    const whitelistChildren = ALL_NAV_ITEMS.map((i) => i.id).filter((id) =>
      TEACHER_NAV_WHITELIST_SET.has(id),
    );
    expect(whitelistChildren.length).toBeGreaterThan(0);
    expect(visible.sort()).toEqual(whitelistChildren.sort());
  });
});

describe("任课教师 + 白名单外 id ⇒ 拒绝（三个洞各一类）", () => {
  it("深链特判类：school-dashboard / school-warning 拒绝", () => {
    for (const id of ["school-dashboard", "school-warning"]) {
      expect(isNavPageAllowed(INDEPENDENT_TEACHER, id)).toBe(false);
    }
    const dashItem = ALL_NAV_ITEMS.find((i) => i.id === "school-dashboard")!;
    expect(dashItem).toBeDefined();
    expect(isNavItemVisible(INDEPENDENT_TEACHER, dashItem)).toBe(false);
  });

  it("漏标 adminOnly 类：canteen-ledger 拒绝（该 id 至今未标 adminOnly）", () => {
    const item = ALL_NAV_ITEMS.find((i) => i.id === "canteen-ledger")!;
    expect(item.adminOnly).toBeUndefined(); // 证明它靠 adminOnly 反推是拦不住的
    expect(isNavItemVisible(INDEPENDENT_TEACHER, item)).toBe(false);
    expect(isNavPageAllowed(INDEPENDENT_TEACHER, "canteen-ledger")).toBe(false);
  });

  it("跨班越权类：analytics-grade / analytics-compare 拒绝", () => {
    for (const id of ["analytics-grade", "analytics-compare"]) {
      expect(isNavPageAllowed(INDEPENDENT_TEACHER, id)).toBe(false);
      const item = ALL_NAV_ITEMS.find((i) => i.id === id)!;
      expect(isNavItemVisible(INDEPENDENT_TEACHER, item)).toBe(false);
    }
  });

  it("其余白名单外 id（parent/school/bureau/设置/系统运营）一并拒绝", () => {
    const denied = ALL_NAV_ITEMS.map((i) => i.id).filter(
      (id) => !isNavAllowedForTeacher(id),
    );
    expect(denied).toEqual(
      expect.arrayContaining([
        "parent-wuyu",
        "bureau-dashboard",
        "bureau-center",
        "settings-hardware",
        "settings-preferences",
        "settings-teacher",
      ]),
    );
    for (const id of denied) {
      expect(isNavPageAllowed(INDEPENDENT_TEACHER, id), `应拒绝: ${id}`).toBe(
        false,
      );
    }
  });

  it("未知 id（手输乱码）对任课教师同样拒绝，不静默回落", () => {
    expect(isNavPageAllowed(INDEPENDENT_TEACHER, "not-a-real-nav-id")).toBe(
      false,
    );
  });
});

describe("任课教师 + 用户点名要留的用量入口 ⇒ 放行（反向锁死）", () => {
  it("scan-consumption / usage-summary 保留", () => {
    for (const id of ["scan-consumption", "usage-summary"]) {
      expect(isNavAllowedForTeacher(id)).toBe(true);
      expect(isNavPageAllowed(INDEPENDENT_TEACHER, id)).toBe(true);
      const item = ALL_NAV_ITEMS.find((i) => i.id === id)!;
      expect(isNavItemVisible(INDEPENDENT_TEACHER, item)).toBe(true);
    }
  });
});

describe("其他角色不受白名单约束（回归闸）", () => {
  const NON_TEACHER_ROLES: string[][] = [
    ["校级管理者"],
    ["年级组长"],
    ["系统管理员"],
    ["子系统管理员"],
    ["教务管理者"],
    ["班主任"],
    ["测试账号"],
    ["家长"],
    [],
  ];

  it("「仅任课教师」判据：多一个角色就不再受白名单约束", () => {
    expect(isTeacherOnlyAccount(["任课教师"])).toBe(true);
    expect(isTeacherOnlyAccount(["任课教师", "任课教师"])).toBe(true);
    expect(isTeacherOnlyAccount(["任课教师", "班主任"])).toBe(false);
    expect(isTeacherOnlyAccount(["班主任"])).toBe(false);
    expect(isTeacherOnlyAccount(["测试账号"])).toBe(false);
    expect(isTeacherOnlyAccount([])).toBe(false);
    expect(isTeacherOnlyAccount(undefined)).toBe(false);
  });

  it.each(NON_TEACHER_ROLES)(
    "角色 %j：新谓词与改动前旧谓词的可见 id 差集为空",
    (...roles: string[]) => {
      const u = user(...roles);
      const now = visibleIdsFor(u, isNavItemVisible);
      const before = visibleIdsFor(u, legacyNavItemVisible);
      expect(now).toEqual(before);
    },
  );

  it("具体回归样本：校级管理者 / 系统管理员 / 测试账号 没丢任何页面", () => {
    const schoolAdminVisible = visibleIdsFor(SCHOOL_ADMIN, isNavItemVisible);
    expect(schoolAdminVisible).toEqual(
      visibleIdsFor(SCHOOL_ADMIN, legacyNavItemVisible),
    );
    expect(schoolAdminVisible).toEqual(
      expect.arrayContaining([
        "school-dashboard",
        "school-warning",
        "canteen-ledger",
        "analytics-grade",
        "analytics-compare",
      ]),
    );

    const platformAdminVisible = visibleIdsFor(
      PLATFORM_ADMIN,
      isNavItemVisible,
    );
    expect(platformAdminVisible).toEqual(
      visibleIdsFor(PLATFORM_ADMIN, legacyNavItemVisible),
    );
    expect(platformAdminVisible).toEqual(
      expect.arrayContaining(["bureau-dashboard", "bureau-center"]),
    );

    // 测试账号：本次刻意不改它的行为（它不可自助注册，不构成本单要堵的洞）
    const testAccount = user("测试账号");
    expect(visibleIdsFor(testAccount, isNavItemVisible)).toEqual(
      visibleIdsFor(testAccount, legacyNavItemVisible),
    );
    expect(isNavPageAllowed(testAccount, "school-dashboard")).toBe(true);
  });

  it("深链闸对其他角色一律放行（含未知 id，行为不变）", () => {
    for (const roles of NON_TEACHER_ROLES) {
      const u = user(...roles);
      for (const id of [
        ...ALL_NAV_ITEMS.map((i) => i.id),
        "not-a-real-nav-id",
      ]) {
        expect(
          isNavPageAllowed(u, id),
          `角色 ${roles.join("/")} 应放行 ${id}`,
        ).toBe(true);
      }
    }
  });

  it("任课教师这一支确实被收窄了（不是空转：差集非空且恰为白名单外）", () => {
    const now = visibleIdsFor(INDEPENDENT_TEACHER, isNavItemVisible);
    const before = visibleIdsFor(INDEPENDENT_TEACHER, legacyNavItemVisible);
    const removed = before.filter((id) => !now.includes(id));
    const expected = before.filter((id) => !isNavAllowedForTeacher(id));
    expect(expected.length).toBeGreaterThan(0); // 有洞可堵
    expect(removed.sort()).toEqual(expected.sort());
  });
});
