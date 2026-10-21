/* ── 分层推送：类型、默认值与纯工具函数 ──
 * 数据全部来自后端（名单/设置/统计/轮次），这里只保留：
 * - 三层的展示样式与默认作业内容（首开班级的初始模板）
 * - 设置合并（stored ⊂ defaults）、截止时间计算等纯函数
 * 不再有 hash/假名单/假统计。 */

import type { LayeredPushSettings, LayeredTierContent } from "@/services/api";

export type { LayeredPushSettings, LayeredTierContent };
export type Tier = "A" | "B" | "C";

export const TIERS: Tier[] = ["A", "B", "C"];

/** 三层展示样式（label/subtitle 是 i18n key） */
export const TIER_STYLES: Record<
  Tier,
  {
    labelKey: string;
    subtitleKey: string;
    color: string;
    borderColor: string;
    dotColor: string;
  }
> = {
  A: {
    labelKey: "layeredPush.tier.a.label",
    subtitleKey: "layeredPush.tier.a.subtitle",
    color: "bg-emerald-500/10",
    borderColor: "border-emerald-500/30",
    dotColor: "bg-emerald-500",
  },
  B: {
    labelKey: "layeredPush.tier.b.label",
    subtitleKey: "layeredPush.tier.b.subtitle",
    color: "bg-yellow-500/10",
    borderColor: "border-yellow-500/30",
    dotColor: "bg-yellow-500",
  },
  C: {
    labelKey: "layeredPush.tier.c.label",
    subtitleKey: "layeredPush.tier.c.subtitle",
    color: "bg-orange-500/10",
    borderColor: "border-orange-500/30",
    dotColor: "bg-orange-500",
  },
};

/** 星期标签 i18n key（1=周一 … 7=周日），与 deadline_weekday 对齐 */
export const WEEKDAY_KEYS = [
  "",
  "layeredPush.week.1",
  "layeredPush.week.2",
  "layeredPush.week.3",
  "layeredPush.week.4",
  "layeredPush.week.5",
  "layeredPush.week.6",
  "layeredPush.week.7",
];

/** 首开班级的默认作业模板（按学科；仅作为初始值存进设置，之后可增删改） */
export const DEFAULT_ASSIGNMENTS: Record<string, Record<Tier, LayeredTierContent["assignments"]>> = {
  语文: {
    A: [
      { title: "拓展阅读", desc: "《古文观止》选篇3篇，完成赏析", icon: "📚" },
      { title: "创新作文", desc: "议论文驳论，800字以上", icon: "📝" },
    ],
    B: [
      { title: "同步练习", desc: "单元测试卷，基础+提高部分", icon: "📚" },
      { title: "常规作文", desc: "记叙文写作，600字以上", icon: "📝" },
    ],
    C: [
      { title: "基础过关", desc: "字词抄写+简单阅读理解", icon: "📚" },
      { title: "仿写练习", desc: "段落仿写，模仿优秀范文结构", icon: "📝" },
    ],
  },
  数学: {
    A: [
      { title: "竞赛专练", desc: "压轴题专项，函数综合应用", icon: "🧮" },
      { title: "建模实践", desc: "数学建模小课题，实际问题数学化", icon: "📐" },
    ],
    B: [
      { title: "同步巩固", desc: "课后习题+变式训练", icon: "📚" },
      { title: "限时测试", desc: "30分钟限时小测，检验基础", icon: "⏱️" },
    ],
    C: [
      { title: "基础计算", desc: "计算专项训练，确保零失误", icon: "🔢" },
      { title: "概念梳理", desc: "公式默写+基础概念填空", icon: "📖" },
    ],
  },
  英语: {
    A: [
      { title: "原著阅读", desc: "英文原著选段精读+词汇积累", icon: "📖" },
      { title: "写作提升", desc: "议论文写作，高级句型运用", icon: "✍️" },
    ],
    B: [
      { title: "完形精练", desc: "完形填空+阅读理解各2篇", icon: "📚" },
      { title: "语法专项", desc: "时态语态综合练习", icon: "📝" },
    ],
    C: [
      { title: "单词过关", desc: "核心单词听写+默写", icon: "🔤" },
      { title: "简单阅读", desc: "基础阅读理解，配合中文注释", icon: "📖" },
    ],
  },
};

function defaultTierContent(tier: Tier, subject: string): LayeredTierContent {
  const subjectKey = DEFAULT_ASSIGNMENTS[subject] ? subject : "语文";
  const defaults: Record<Tier, { minutes: number; time: string; sign: boolean; photo: boolean; voice: boolean }> = {
    A: { minutes: 60, time: "22:00", sign: true, photo: false, voice: true },
    B: { minutes: 40, time: "22:00", sign: false, photo: true, voice: false },
    C: { minutes: 30, time: "20:00", sign: true, photo: false, voice: false },
  };
  const d = defaults[tier];
  return {
    assignments: DEFAULT_ASSIGNMENTS[subjectKey][tier],
    materials: [],
    estimated_minutes: d.minutes,
    deadline_weekday: 5,
    deadline_time: d.time,
    require_parent_sign: d.sign,
    require_photo: d.photo,
    require_voice: d.voice,
  };
}

/** 本班（本学科）默认设置——后端未存过时用它 */
export function buildDefaultSettings(subject: string): LayeredPushSettings {
  return {
    thresholds: { a: 80, b: 60 },
    timing: { mode: "now", scheduled_at: null, fired_at: null },
    notify: { student: true, parent: true, reminder24h: true, late: true },
    form_type: "h5",
    tiers: {
      A: defaultTierContent("A", subject),
      B: defaultTierContent("B", subject),
      C: defaultTierContent("C", subject),
    },
    templates: [],
  };
}

function mergeTierContent(
  base: LayeredTierContent,
  stored: Partial<LayeredTierContent> | undefined | null,
): LayeredTierContent {
  if (!stored || typeof stored !== "object") return base;
  const minutes = Number(stored.estimated_minutes);
  const weekday = Number(stored.deadline_weekday);
  return {
    ...base,
    ...stored,
    assignments: Array.isArray(stored.assignments) ? stored.assignments : base.assignments,
    materials: Array.isArray(stored.materials) ? stored.materials : base.materials,
    // 存量 JSON 可能缺字段/类型不对，读侧兜底成合法值
    estimated_minutes: Number.isFinite(minutes)
      ? Math.min(Math.max(Math.round(minutes), 5), 600)
      : base.estimated_minutes,
    deadline_weekday: Number.isFinite(weekday)
      ? Math.min(Math.max(Math.round(weekday), 1), 7)
      : base.deadline_weekday,
    deadline_time: /^\d{1,2}:\d{2}$/.test(String(stored.deadline_time || ""))
      ? String(stored.deadline_time)
      : base.deadline_time,
    require_parent_sign: !!stored.require_parent_sign,
    require_photo: !!stored.require_photo,
    require_voice: !!stored.require_voice,
  };
}

/** 后端返回的设置（可能缺字段/缺层）与默认值深合并 */
export function mergeSettings(
  stored: Partial<LayeredPushSettings> | null | undefined,
  subject: string,
): LayeredPushSettings {
  const base = buildDefaultSettings(subject);
  if (!stored || typeof stored !== "object") return base;
  return {
    thresholds: { ...base.thresholds, ...(stored.thresholds || {}) },
    timing: { ...base.timing, ...(stored.timing || {}) },
    notify: { ...base.notify, ...(stored.notify || {}) },
    form_type:
      stored.form_type === "dingtalk" || stored.form_type === "h5"
        ? stored.form_type
        : base.form_type,
    tiers: {
      A: mergeTierContent(base.tiers.A, stored.tiers?.A),
      B: mergeTierContent(base.tiers.B, stored.tiers?.B),
      C: mergeTierContent(base.tiers.C, stored.tiers?.C),
    },
    templates: Array.isArray(stored.templates) ? stored.templates : [],
  };
}

/** 下一个截止时刻（ms 时间戳；已过点顺延下周）。与后端 _next_deadline_date 同口径。 */
export function nextDeadlineMs(content: LayeredTierContent, now: Date = new Date()): number {
  let hh = 22;
  let mm = 0;
  const parts = String(content.deadline_time || "22:00").split(":");
  const h = Number(parts[0]);
  const m = Number(parts[1]);
  if (!Number.isNaN(h)) hh = h;
  if (!Number.isNaN(m)) mm = m;
  const due = new Date(now);
  due.setHours(hh, mm, 0, 0);
  const target = Math.min(Math.max(Number(content.deadline_weekday) || 5, 1), 7);
  const todayMonBased = ((now.getDay() + 6) % 7) + 1;
  const days = (target - todayMonBased + 7) % 7;
  due.setDate(now.getDate() + days);
  if (due.getTime() <= now.getTime()) due.setDate(due.getDate() + 7);
  return due.getTime();
}
