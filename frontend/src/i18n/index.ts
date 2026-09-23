import type { PrintPaperSize } from "@/services/gradingApi";
import type { AppLocale, TranslationDict } from "./types";
import { zh } from "./locales/zh";
import { en } from "./locales/en";

const dictionaries: Record<AppLocale, TranslationDict> = { zh, en };

export function normalizeLocale(raw?: string | null): AppLocale {
  return String(raw || "zh").toLowerCase() === "en" ? "en" : "zh";
}

export function getDictionary(locale: AppLocale): TranslationDict {
  return dictionaries[locale] || zh;
}

export function translate(
  locale: AppLocale,
  key: string,
  params?: Record<string, string | number>,
  fallback?: string
): string {
  const dict = getDictionary(locale);
  // 英文缺键时回退到中文；中文缺键时优先用调用处传入的 fallback，最后才回退到 key 本身
  let text = dict[key] ?? (locale === "en" ? zh[key] : undefined) ?? fallback ?? key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      text = text.replace(new RegExp(`\\{${k}\\}`, "g"), String(v));
    }
  }
  return text;
}

/** 导航 id → i18n key */
export function navLabelKey(navId: string): string {
  return `nav.${navId}`;
}

/** 固定角色名翻译（数据库中的自定义角色名原样显示） */
const ROLE_KEY_MAP: Record<string, string> = {
  任课教师: "role.teacher",
  班主任: "role.headTeacher",
  年级主任: "role.gradeDirector",
  校长: "role.principal",
  学生: "role.student",
  家长: "role.parent",
};

export function translateRole(locale: AppLocale, role: string): string {
  const key = ROLE_KEY_MAP[role];
  if (!key) return role;
  return translate(locale, key, undefined, role);
}

/** 系统角色（constants/systemRoles.ts）→ 显示名 */
const SYSTEM_ROLE_KEY_MAP: Record<string, string> = {
  系统管理员: "admin.roles.systemAdmin",
  子系统管理员: "admin.roles.subsystemAdmin",
  校级管理者: "admin.roles.schoolManager",
  教务管理者: "admin.roles.academicManager",
  年级组长: "admin.roles.gradeLeader",
  班主任: "admin.roles.classTeacher",
  任课教师: "admin.roles.subjectTeacher",
  测试账号: "admin.roles.testAccount",
};

export function translateSystemRole(locale: AppLocale, role: string): string {
  const key = SYSTEM_ROLE_KEY_MAP[role];
  if (!key) return translateRole(locale, role);
  return translate(locale, key, undefined, role);
}

/** 科目内部名（中文）→ 显示名 */
const SUBJECT_NAME_TO_ID: Record<string, string> = {
  语文: "chinese",
  数学: "math",
  英语: "english",
  科学: "science",
  物理: "physics",
  化学: "chemistry",
  生物: "biology",
  历史: "history",
  地理: "geography",
  道德与法治: "politics",
  政治: "politicsShort",
  思想政治: "politicsSenior",
  信息: "info",
};

export function translateSubjectName(locale: AppLocale, name: string): string {
  const id = SUBJECT_NAME_TO_ID[name];
  if (!id) return name;
  return translate(locale, `subject.${id}`, undefined, name);
}

/** 年级 value（存库用中文）→ 显示标签 */
export function translateGradeValue(locale: AppLocale, schoolLevel: string, gradeValue: string): string {
  const levelPrefix =
    schoolLevel === "primary" ? "grade.primary." :
    schoolLevel === "junior" ? "grade.junior." :
    schoolLevel === "senior" ? "grade.senior." : "";
  if (!levelPrefix) return gradeValue;
  const idxMap: Record<string, number> = {
    一年级: 1, 二年级: 2, 三年级: 3, 四年级: 4, 五年级: 5, 六年级: 6,
    七年级: 1, 八年级: 2, 九年级: 3,
    高一: 1, 高二: 2, 高三: 3,
  };
  const idx = idxMap[gradeValue];
  if (!idx) return gradeValue;
  return translate(locale, `${levelPrefix}${idx}`, undefined, gradeValue);
}

/** 年级 value → 存库规范值（幂等：规范值原样返回；「一年级/七年级」等别名写法归一化） */
const PRIMARY_GRADE_ALIASES: Record<string, string> = {
  一年级: "小学一年级",
  二年级: "小学二年级",
  三年级: "小学三年级",
  四年级: "小学四年级",
  五年级: "小学五年级",
  六年级: "小学六年级",
};
const JUNIOR_GRADE_ALIASES: Record<string, string> = {
  初一: "初一",
  初二: "初二",
  初三: "初三",
  七年级: "初一",
  八年级: "初二",
  九年级: "初三",
};

export function normalizeGrade(grade?: string | null): string {
  const g = (grade || "").trim();
  if (!g) return g;
  if (JUNIOR_GRADE_ALIASES[g]) return JUNIOR_GRADE_ALIASES[g];
  if (PRIMARY_GRADE_ALIASES[g]) return PRIMARY_GRADE_ALIASES[g];
  return g; // 已是规范值（小学一年级/初一/高一）或未知写法，原样返回
}

/** 年级规范值 → 下拉「原始写法」（一年级/七年级/高一）。用于把历史存成规范值的筛选状态拉回下拉可识别的值。 */
const DENORMALIZE_GRADE_MAP: Record<string, string> = {
  小学一年级: "一年级",
  小学二年级: "二年级",
  小学三年级: "三年级",
  小学四年级: "四年级",
  小学五年级: "五年级",
  小学六年级: "六年级",
  初一: "七年级",
  初二: "八年级",
  初三: "九年级",
};

export function denormalizeGrade(grade?: string | null): string {
  const g = (grade || "").trim();
  return DENORMALIZE_GRADE_MAP[g] ?? g;
}

export function translateSchoolLevel(locale: AppLocale, levelId: string): string {
  return translate(locale, `school.${levelId}`, undefined, levelId);
}

export interface GradeLevelOption {
  id: string;
  label: string;
  grades: { value: string; label: string }[];
}

const GRADE_VALUES_BY_LEVEL: Record<string, string[]> = {
  primary: ["一年级", "二年级", "三年级", "四年级", "五年级", "六年级"],
  junior: ["七年级", "八年级", "九年级"],
  senior: ["高一", "高二", "高三"],
};

export function buildGradeLevels(locale: AppLocale): GradeLevelOption[] {
  return (["primary", "junior", "senior"] as const).map((id) => ({
    id,
    label: translateSchoolLevel(locale, id),
    grades: (GRADE_VALUES_BY_LEVEL[id] || []).map((value) => ({
      value,
      label: translateGradeValue(locale, id, value),
    })),
  }));
}

/** 打印纸张选项 value → 显示标签 */
export function translatePrintPaperLabel(locale: AppLocale, value: PrintPaperSize): string {
  return translate(locale, `printer.paper.${value}`, undefined, value);
}

/** 性别（存库用中文）→ 显示标签 */
const GENDER_KEY_MAP: Record<string, string> = {
  男: "settingsClass.gender.male",
  女: "settingsClass.gender.female",
};

export function translateGender(locale: AppLocale, gender: string): string {
  const key = GENDER_KEY_MAP[gender];
  if (!key) return gender;
  return translate(locale, key, undefined, gender);
}

/** 学生状态（存库用中文）→ 显示标签 */
const STUDENT_STATUS_KEY_MAP: Record<string, string> = {
  正常: "settingsClass.status.normal",
  预警: "settingsClass.status.warning",
  转出: "settingsClass.status.transferred",
  休学: "settingsClass.status.suspended",
};

export function translateStudentStatus(locale: AppLocale, status: string): string {
  const key = STUDENT_STATUS_KEY_MAP[status];
  if (!key) return status;
  return translate(locale, key, undefined, status);
}

/** 分层字母（A/B/C）→ 显示标签；detailed 为详情页下拉选项 */
export function translateTierLabel(locale: AppLocale, tier: string, detailed = false): string {
  if (detailed) {
    const detailKeys: Record<string, string> = {
      A: "settingsClass.detail.tierA",
      B: "settingsClass.detail.tierB",
      C: "settingsClass.detail.tierC",
    };
    const detailKey = detailKeys[tier];
    if (detailKey) return translate(locale, detailKey, undefined, `${tier}层`);
  }
  const tableKeys: Record<string, string> = {
    A: "settingsClass.table.tierA",
    B: "settingsClass.table.tierB",
    C: "settingsClass.table.tierC",
  };
  const tableKey = tableKeys[tier];
  if (tableKey) return translate(locale, tableKey, undefined, `${tier}层`);
  return translate(locale, "settingsClass.table.tierSuffix", { tier }, `${tier}层`);
}
