import type { TranslationDict } from "../../types";

/** AI 对话知识卡片（chat-cards）中文翻译 */
export const chatCardsZh: TranslationDict = {
  /* ── 通用 ── */
  "chatCards.common.collapse": "收起",

  /* ── 知识点分析（KnowledgeListCard） ── */
  "chatCards.knowledge.title": "知识点分析",
  "chatCards.knowledge.weakBadge": "{count}个薄弱",
  "chatCards.knowledge.avgMastery": "平均掌握 {value}%",
  "chatCards.knowledge.weakLabel": "薄弱",
  "chatCards.knowledge.relatedStudents": "{count}人关联",
  "chatCards.knowledge.commonErrors": "常见错误：{errors}",
  "chatCards.knowledge.expandAll": "展开全部 {count} 个",
  "chatCards.knowledge.generatePractice": "生成练习",

  /* ── 班级概览（ClassOverviewCard） ── */
  "chatCards.classOverview.studentCount": "{count}人",
  "chatCards.classOverview.avgScore": "平均分：",
  "chatCards.classOverview.trend.rising": "上升 {count}",
  "chatCards.classOverview.trend.stable": "稳定 {count}",
  "chatCards.classOverview.trend.declining": "下滑 {count}",
  "chatCards.classOverview.needAttention": "需关注：",
  "chatCards.classOverview.studentScore": "{name}({score}分)",
  "chatCards.classOverview.weakKnowledge": "薄弱知识点：",
  "chatCards.classOverview.classDashboard": "班级仪表盘",
  "chatCards.classOverview.classPortrait": "班级画像",

  /* ── 题目难度（QuestionListCard） ── */
  "chatCards.difficulty.easy": "简单",
  "chatCards.difficulty.medium": "中等",
  "chatCards.difficulty.hard": "困难",

  /* ── 题目列表（QuestionListCard） ── */
  "chatCards.questionList.found": "找到 {count} 道题目",
  "chatCards.questionList.scoreSuffix": "{score}分",
  "chatCards.questionList.usedCount": "使用{count}次",
  "chatCards.questionList.expandAll": "展开全部 {count} 题",
  "chatCards.questionList.addToPaper": "加入组卷",
  "chatCards.questionList.questionAnalysis": "试题分析",

  /* ── 学生列表（StudentListCard） ── */
  "chatCards.studentList.title": "学生信息",
  "chatCards.studentList.studentCount": "{count}人",
  "chatCards.studentList.wrongCount": "错题{count}道",
  "chatCards.studentList.expandAll": "展开全部 {count} 人",
  "chatCards.studentList.viewDetail": "查看详情",
  "chatCards.studentList.targetedImprove": "靶向提升",
  "chatCards.studentList.risk.rising": "上升",
  "chatCards.studentList.risk.stable": "稳定",
  "chatCards.studentList.risk.declining": "下滑",

  /* ── 错题记录（WrongQuestionsCard） ── */
  "chatCards.wrongQuestions.title": "错题记录",
  "chatCards.wrongQuestions.count": "{count}道",
  "chatCards.wrongQuestions.more": "还有 {count} 道...",

  /* ── 加载骨架（ToolCallingSkeleton） ── */
  "chatCards.toolCalling.querying": "正在查询数据...",
};

/** AI 对话知识卡片（chat-cards）英文翻译 */
export const chatCardsEn: TranslationDict = {
  /* ── 通用 ── */
  "chatCards.common.collapse": "Collapse",

  /* ── 知识点分析（KnowledgeListCard） ── */
  "chatCards.knowledge.title": "Knowledge Analysis",
  "chatCards.knowledge.weakBadge": "{count} weak",
  "chatCards.knowledge.avgMastery": "Avg mastery {value}%",
  "chatCards.knowledge.weakLabel": "Weak",
  "chatCards.knowledge.relatedStudents": "{count} linked",
  "chatCards.knowledge.commonErrors": "Common errors: {errors}",
  "chatCards.knowledge.expandAll": "Expand all {count}",
  "chatCards.knowledge.generatePractice": "Generate Practice",

  /* ── 班级概览（ClassOverviewCard） ── */
  "chatCards.classOverview.studentCount": "{count} students",
  "chatCards.classOverview.avgScore": "Avg score:",
  "chatCards.classOverview.trend.rising": "Rising {count}",
  "chatCards.classOverview.trend.stable": "Stable {count}",
  "chatCards.classOverview.trend.declining": "Declining {count}",
  "chatCards.classOverview.needAttention": "Needs attention:",
  "chatCards.classOverview.studentScore": "{name} ({score} pts)",
  "chatCards.classOverview.weakKnowledge": "Weak knowledge points:",
  "chatCards.classOverview.classDashboard": "Class Dashboard",
  "chatCards.classOverview.classPortrait": "Class Portrait",

  /* ── 题目难度（QuestionListCard） ── */
  "chatCards.difficulty.easy": "Easy",
  "chatCards.difficulty.medium": "Medium",
  "chatCards.difficulty.hard": "Hard",

  /* ── 题目列表（QuestionListCard） ── */
  "chatCards.questionList.found": "Found {count} questions",
  "chatCards.questionList.scoreSuffix": "{score} pts",
  "chatCards.questionList.usedCount": "Used {count}×",
  "chatCards.questionList.expandAll": "Expand all {count}",
  "chatCards.questionList.addToPaper": "Add to Paper",
  "chatCards.questionList.questionAnalysis": "Question Analysis",

  /* ── 学生列表（StudentListCard） ── */
  "chatCards.studentList.title": "Student Information",
  "chatCards.studentList.studentCount": "{count} students",
  "chatCards.studentList.wrongCount": "{count} wrong",
  "chatCards.studentList.expandAll": "Expand all {count}",
  "chatCards.studentList.viewDetail": "View Details",
  "chatCards.studentList.targetedImprove": "Targeted Improvement",
  "chatCards.studentList.risk.rising": "Rising",
  "chatCards.studentList.risk.stable": "Stable",
  "chatCards.studentList.risk.declining": "Declining",

  /* ── 错题记录（WrongQuestionsCard） ── */
  "chatCards.wrongQuestions.title": "Wrong Questions",
  "chatCards.wrongQuestions.count": "{count}",
  "chatCards.wrongQuestions.more": "{count} more...",

  /* ── 加载骨架（ToolCallingSkeleton） ── */
  "chatCards.toolCalling.querying": "Querying data...",
};
