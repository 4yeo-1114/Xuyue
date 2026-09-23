import type { AuthUser } from "@/hooks/useAuth";

/** 右上角/下拉中展示的教师名称：优先个人设置里的「账号名称」，否则用邮箱前缀 */
export function getTeacherDisplayName(user: AuthUser | null | undefined): string {
  if (!user) return "教师";
  const name = user.display_name?.trim();
  if (name) return name;
  return user.email?.split("@")[0] || "教师";
}
