import type { AuthUser } from "@/hooks/useAuth";

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
