import type { AuthUser } from "@/hooks/useAuth";
import {
  isNavAllowedForTeacher,
  isTeacherOnlyAccount,
} from "@/constants/systemRoles";

/** 可进入「后台管理」的角色 */
export const PLATFORM_ADMIN_ROLES = ["系统管理员", "子系统管理员"] as const;

export function isPlatformAdmin(user: AuthUser | null | undefined): boolean {
  if (!user?.roles?.length) return false;
  return user.roles.some((r) =>
    PLATFORM_ADMIN_ROLES.includes(r as (typeof PLATFORM_ADMIN_ROLES)[number]),
  );
}

/** 可进入「学校驾驶舱」的校级角色（平台管理员 + 校级管理者 / 年级组长） */
export const SCHOOL_ADMIN_ROLES = ["校级管理者", "年级组长"] as const;

export function isSchoolAdmin(user: AuthUser | null | undefined): boolean {
  if (!user?.roles?.length) return false;
  return (
    isPlatformAdmin(user) ||
    user.roles.some((r) =>
      SCHOOL_ADMIN_ROLES.includes(r as (typeof SCHOOL_ADMIN_ROLES)[number]),
    )
  );
}

/** 家长角色（可进入「家长端 → 孩子五育画像」） */
export const PARENT_ROLE = "家长" as const;

export function isParent(user: AuthUser | null | undefined): boolean {
  if (!user?.roles?.length) return false;
  return user.roles.some((r) => r === PARENT_ROLE);
}

/** 侧栏导航项的最小形状（与 Sidebar.NavChild 的可判定字段对齐） */
export interface NavVisibilityItem {
  id: string;
  adminOnly?: boolean;
  parentOnly?: boolean;
}

/**
 * 侧栏导航项可见性 —— **唯一权威判据**。
 *
 * - 「仅任课教师」账号（独立老师）⇒ 只放行 `TEACHER_NAV_WHITELIST` 内的功能域。
 *   这是本函数的**唯一**新增语义：不再靠 `adminOnly` 反推（漏标一个就漏一个）。
 * - 其他角色 ⇒ 走下面这支，谓词与改动前**逐字一致**，⛔ 不得顺手重构。
 */
export function isNavItemVisible(
  user: AuthUser | null | undefined,
  item: NavVisibilityItem,
): boolean {
  if (isTeacherOnlyAccount(user?.roles)) {
    return isNavAllowedForTeacher(item.id);
  }
  return item.parentOnly
    ? isParent(user)
    : item.id === "school-dashboard" || item.id === "school-warning"
      ? isSchoolAdmin(user)
      : !item.adminOnly || isPlatformAdmin(user);
}

/**
 * 深链闸（`/nav/:navId` 直接手输）—— 渲染层用**同一个**白名单。
 *
 * 其他角色一律放行（行为不变：未知 id 仍落到「功能开发中」占位，不抛白屏）。
 */
export function isNavPageAllowed(
  user: AuthUser | null | undefined,
  navId: string,
): boolean {
  if (!isTeacherOnlyAccount(user?.roles)) return true;
  return isNavAllowedForTeacher(navId);
}
