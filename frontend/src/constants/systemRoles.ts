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

export type SystemRole = (typeof SYSTEM_ROLES)[number];

/** 独立老师账号所绑定的既有角色（⛔ 不新增角色） */
export const INDEPENDENT_TEACHER_ROLE = "任课教师" as const;

/**
 * 「独立老师」可见的功能域白名单 —— 单一权威事实源。
 *
 * 适用对象：**仅角色集合全为「任课教师」的账号**（公网自助注册进来的个体老师）。
 * 其他角色（校级管理者 / 年级组长 / 系统管理员 / 班主任 / 家长 / 教务管理者 / 测试账号）
 * ⛔ 完全不受本白名单约束，行为与改动前逐字一致。
 *
 * 留：独立老师在自己班上能自己完成的事 + 自己的用量。
 * 去：对独立老师无意义或已确认越权的功能域。
 *   - parent-wuyu / school-dashboard / school-warning / bureau-* / settings-teacher 等：越权或无意义
 *   - canteen-ledger：全平台食堂台账，与个体老师无关
 *   - analytics-grade / analytics-compare：后端跨班越权（教一个班即取全年级数据），
 *     口径收敛前不放行（**可逆决定**，收敛后加回），见 class_analysis.py
 *   - settings-hardware / settings-preferences：设备与平台级配置
 *   - settings-multi-device 保留：确认为静态引导页（无数据面）
 */
export const TEACHER_NAV_WHITELIST = [
  "home",
  "whats-new",
  "class-dashboard",
  "settings-class",
  "class-students",
  "analytics-portrait",
  "analytics-questions",
  "class-knowledge",
  "ai-review",
  "ai-targeted",
  "ai-layered",
  "prep-matrix",
  "prep-catalog",
  "prep-bank",
  "prep-lesson",
  "prep-compose",
  "prep-exam",
  "prep-video",
  "prep-question-bank",
  "grading-start",
  "grading-history",
  "grading-errors",
  "flow-tasks",
  "wuyu-profile",
  "assessment",
  "student-ops",
  "settings-personal",
  "settings-subject",
  "my-quota",
  "settings-exam",
  "settings-multi-device",
  "scan-consumption",
  "usage-summary",
  "payment-wallet",
  "payment-ledger",
] as const;

/** 白名单的 O(1) 判据（与 TEACHER_NAV_WHITELIST 同源，勿另建第二份） */
export const TEACHER_NAV_WHITELIST_SET: ReadonlySet<string> = new Set(
  TEACHER_NAV_WHITELIST,
);

/**
 * 是否为「仅任课教师」账号（独立老师）。
 *
 * 判据刻意取**最保守的一侧**：角色集合非空、且**每一项都是「任课教师」**。
 * 只要多出任何一个其他角色（含「测试账号」「班主任」），即判定为不受白名单约束 ⇒
 * ⛔ 不会因为本次改动收窄任何其他角色的可见性（硬约束：其他角色行为必须一条不少）。
 * 「测试账号」当前行为与任课教师相同（非 adminOnly 全可见），本单**不改动**它 ——
 * 它不可自助注册，不构成本单要堵的洞，改动它属于「顺手改别人那一支」。
 */
export function isTeacherOnlyAccount(
  roles: readonly string[] | null | undefined,
): boolean {
  if (!roles?.length) return false;
  return roles.every((r) => r === INDEPENDENT_TEACHER_ROLE);
}

/** 独立老师是否可访问某功能域 id（仅白名单内放行） */
export function isNavAllowedForTeacher(navId: string): boolean {
  return TEACHER_NAV_WHITELIST_SET.has(navId);
}
