/* ── AI 出题共用选项：题型枚举 + 知识点拆分 ──
 * TieredComposePanel / AutoVariantsCard / WrongQuestionsTab 共用（题源=AI 生成时）。 */

/** 题型下拉（仿 AI 组卷题型模板，英文枚举 → 中文名） */
export const QUESTION_TYPE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "choice", label: "选择题" },
  { value: "fill", label: "填空题" },
  { value: "judge", label: "判断题" },
  { value: "short_answer", label: "简答题" },
  { value: "calculation", label: "计算题" },
  { value: "application", label: "应用题" },
  { value: "reading", label: "阅读理解" },
  { value: "essay", label: "作文" },
  { value: "matching", label: "连线匹配" },
  { value: "ordering", label: "排序题" },
  { value: "cloze", label: "完形填空" },
];

/** 知识点输入拆分（顿号/逗号/分号/换行） */
export function splitTopics(text: string): string[] {
  return text
    .split(/[、,，;；\n]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** 题型枚举 → 中文名（未知原样返回） */
export function typeLabelOf(value: string): string {
  return QUESTION_TYPE_OPTIONS.find((o) => o.value === value)?.label || value;
}
