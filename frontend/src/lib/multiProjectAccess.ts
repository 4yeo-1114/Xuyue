import type { AuthUser } from "@/hooks/useAuth";

/**
 * 多项目管理权限判断。
 * 完全以后端返回的 `multi_project_admin`（来自 /auth/me）为准，
 * 不再在前端硬编码超管邮箱，避免与后端 env 注入判断不一致。
 */
export function isMultiProjectAdmin(user: AuthUser | null | undefined): boolean {
  if (!user) return false;
  return user.multi_project_admin === true;
}
