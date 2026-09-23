/** 账号管理可选系统角色（顺序即列表分组顺序） */
export const SYSTEM_ROLES = [
  "系统管理员",
  "子系统管理员",
  "校级管理者",
  "教务管理者",
  "年级组长",
  "班主任",
  "任课教师",
  "测试账号",
] as const;

/** 与「任课教师」系统权限相同的角色（无后台/校级全局权限，按班级协作访问） */
export const TEACHER_LEVEL_SYSTEM_ROLES = ["任课教师", "测试账号"] as const;

export type SystemRole = (typeof SYSTEM_ROLES)[number];
