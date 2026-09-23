import type { TranslationDict } from "../../types";

/** 综评档案·遴选→公示→成档 中文翻译 */
export const archiveZh: TranslationDict = {
  "archive.tab.selection": "综评遴选",
  "archive.title": "综评遴选",
  "archive.subtitle": "班级学生候选 → 勾选遴选 → 开启公示 → 成档归档",
  "archive.term": "学年-学期",
  "archive.termPlaceholder": "如 2025-2026-1",
  "archive.termRequired": "请填写学年-学期后查看候选",
  "archive.termInvalid": "学期格式应为 学年-学年-学期，如 2025-2026-1",
  "archive.load": "查看候选",
  "archive.refresh": "刷新",
  "archive.loading": "加载中…",
  "archive.loadFailed": "候选加载失败",
  "archive.retry": "重试",
  "archive.growthPoint": "成长分",

  "archive.candidates.title": "候选学生（{count} 人，按五育综合分排序）",
  "archive.candidates.toggleAll": "全选可遴选",
  "archive.candidates.empty": "该班级暂无候选学生",

  "archive.selection.select": "遴选",
  "archive.selection.selecting": "遴选中…",
  "archive.selection.success": "已遴选 {count} 名学生",
  "archive.selection.failed": "遴选失败",
  "archive.selection.empty": "请先勾选学生",
  "archive.selection.hint": "已勾选 {count} 名学生",

  "archive.status.none": "未遴选",
  "archive.status.draft": "待遴选",
  "archive.status.selected": "已遴选",
  "archive.status.publicity": "公示中",
  "archive.status.ended": "已结束",
  "archive.status.archived": "已存档",

  "archive.publish.label": "开启公示",
  "archive.publish.success": "公示已开启",
  "archive.publish.failed": "开启公示失败",

  "archive.withdraw.label": "撤回公示",
  "archive.withdraw.success": "公示已撤回",
  "archive.withdraw.failed": "撤回失败",

  "archive.archive.label": "成档归档",
  "archive.archive.success": "已成档归档",
  "archive.archive.failed": "成档失败",
};

/** 综评档案·遴选→公示→成档 英文翻译 */
export const archiveEn: TranslationDict = {
  "archive.tab.selection": "Selection",
  "archive.title": "Portfolio Selection",
  "archive.subtitle": "Class candidates → select → publicize → archive",
  "archive.term": "School year-term",
  "archive.termPlaceholder": "e.g. 2025-2026-1",
  "archive.termRequired": "Enter a school year-term to view candidates",
  "archive.termInvalid": "Term format should be year-year-semester, e.g. 2025-2026-1",
  "archive.load": "Load candidates",
  "archive.refresh": "Refresh",
  "archive.loading": "Loading…",
  "archive.loadFailed": "Failed to load candidates",
  "archive.retry": "Retry",
  "archive.growthPoint": "Growth",

  "archive.candidates.title": "Candidates ({count}, sorted by five-domain score)",
  "archive.candidates.toggleAll": "Select all eligible",
  "archive.candidates.empty": "No candidates in this class",

  "archive.selection.select": "Select",
  "archive.selection.selecting": "Selecting…",
  "archive.selection.success": "Selected {count} student(s)",
  "archive.selection.failed": "Selection failed",
  "archive.selection.empty": "Please select students first",
  "archive.selection.hint": "{count} student(s) checked",

  "archive.status.none": "Not selected",
  "archive.status.draft": "Pending",
  "archive.status.selected": "Selected",
  "archive.status.publicity": "In publicity",
  "archive.status.ended": "Ended",
  "archive.status.archived": "Archived",

  "archive.publish.label": "Start publicity",
  "archive.publish.success": "Publicity started",
  "archive.publish.failed": "Failed to start publicity",

  "archive.withdraw.label": "Withdraw",
  "archive.withdraw.success": "Publicity withdrawn",
  "archive.withdraw.failed": "Withdraw failed",

  "archive.archive.label": "Archive",
  "archive.archive.success": "Archived",
  "archive.archive.failed": "Archive failed",
};
