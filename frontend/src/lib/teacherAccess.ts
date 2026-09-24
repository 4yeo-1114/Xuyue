import type { AuthUser } from "@/hooks/useAuth";

/** 更宽角色：即使兼任任课教师，也走通用平台（他们要管整班/整级/全校） */
const WIDER_ROLES = [
  "系统管理员",
  "子系统管理员",
  "校级管理者",
  "教务管理者",
  "年级组长",
  "班主任",
] as const;

/**
 * 是否为「单科任课教师」（进入单科老师端的判定）：
 *   1. 含「任课教师」角色
 *   2. 已绑定教学科目 teaching_subject
 *   3. 不含任何更宽角色（班主任/年级组长/校管/教务/系统/子系统管理员）
 */
export function isSingleSubjectTeacher(
  user: AuthUser | null | undefined,
): boolean {
  if (!user?.roles?.length) return false;
  if (!user.teaching_subject) return false;
  if (!user.roles.includes("任课教师")) return false;
  return !user.roles.some((r) =>
    WIDER_ROLES.includes(r as (typeof WIDER_ROLES)[number]),
  );
}
