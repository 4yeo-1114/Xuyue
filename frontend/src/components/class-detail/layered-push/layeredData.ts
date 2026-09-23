/* ── Deterministic data for Layered Push page ── */

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

const ALL_NAMES = [
  "王芳",
  "李明",
  "张华",
  "陈静",
  "赵雪",
  "孙悦",
  "周杰",
  "吴磊",
  "郑欣",
  "马超",
  "朱丽",
  "宋琪",
  "黄伟",
  "林佳",
  "何强",
  "罗敏",
  "梁志",
  "韩冰",
  "曹颖",
  "许航",
  "邓瑶",
  "彭浩",
  "萧然",
  "蒋蓉",
  "沈昊",
  "唐珊",
  "薛刚",
  "田甜",
  "杜鹃",
  "姜涛",
  "钟慧",
  "陆洋",
  "方圆",
  "谢峰",
  "贾莉",
  "范阳",
];

export type Tier = "A" | "B" | "C";

export interface TierStudent {
  name: string;
  score: number;
  avatar: string; // first char
  dingTalkSynced: boolean;
}

export interface TierAssignment {
  title: string;
  icon: string;
  description: string;
}

export interface TierConfig {
  tier: Tier;
  /** i18n key：分层档位标题（如 layeredPush.tier.a.label） */
  labelKey: string;
  /** i18n key：分层档位副标题 */
  subtitleKey: string;
  color: string;
  borderColor: string;
  dotColor: string;
  students: TierStudent[];
  assignments: TierAssignment[];
  estimatedMinutes: number;
  /** i18n key：截止星期（如 layeredPush.friday） */
  deadlineKey: string;
  deadlineTime: string;
  requireParentSign: boolean;
  requirePhoto: boolean;
  requireVoice: boolean;
}

const ASSIGNMENTS: Record<string, Record<Tier, TierAssignment[]>> = {
  语文: {
    A: [
      {
        title: "拓展阅读",
        icon: "📚",
        description: "《古文观止》选篇3篇，完成赏析",
      },
      { title: "创新作文", icon: "📝", description: "议论文驳论，800字以上" },
    ],
    B: [
      {
        title: "同步练习",
        icon: "📚",
        description: "单元测试卷，基础+提高部分",
      },
      { title: "常规作文", icon: "📝", description: "记叙文写作，600字以上" },
    ],
    C: [
      { title: "基础过关", icon: "📚", description: "字词抄写+简单阅读理解" },
      {
        title: "仿写练习",
        icon: "📝",
        description: "段落仿写，模仿优秀范文结构",
      },
    ],
  },
  数学: {
    A: [
      {
        title: "竞赛专练",
        icon: "🧮",
        description: "压轴题专项，函数综合应用",
      },
      {
        title: "建模实践",
        icon: "📐",
        description: "数学建模小课题，实际问题数学化",
      },
    ],
    B: [
      { title: "同步巩固", icon: "📚", description: "课后习题+变式训练" },
      {
        title: "限时测试",
        icon: "⏱️",
        description: "30分钟限时小测，检验基础",
      },
    ],
    C: [
      {
        title: "基础计算",
        icon: "🔢",
        description: "计算专项训练，确保零失误",
      },
      { title: "概念梳理", icon: "📖", description: "公式默写+基础概念填空" },
    ],
  },
  英语: {
    A: [
      {
        title: "原著阅读",
        icon: "📖",
        description: "英文原著选段精读+词汇积累",
      },
      {
        title: "写作提升",
        icon: "✍️",
        description: "议论文写作，高级句型运用",
      },
    ],
    B: [
      { title: "完形精练", icon: "📚", description: "完形填空+阅读理解各2篇" },
      { title: "语法专项", icon: "📝", description: "时态语态综合练习" },
    ],
    C: [
      { title: "单词过关", icon: "🔤", description: "核心单词听写+默写" },
      {
        title: "简单阅读",
        icon: "📖",
        description: "基础阅读理解，配合中文注释",
      },
    ],
  },
};

export function generateTierConfigs(
  classId: string,
  subject: string,
): TierConfig[] {
  const subjectAssignments = ASSIGNMENTS[subject] || ASSIGNMENTS["语文"];

  const scored = ALL_NAMES.map((name) => {
    const h = hash(name + subject + classId);
    const score = 45 + (h % 50);
    return { name, score, h };
  }).sort((a, b) => b.score - a.score);

  const aStudents = scored.filter((s) => s.score >= 80);
  const bStudents = scored.filter((s) => s.score >= 60 && s.score < 80);
  const cStudents = scored.filter((s) => s.score < 60);

  const toTierStudents = (list: typeof scored): TierStudent[] =>
    list.map((s) => ({
      name: s.name,
      score: s.score,
      avatar: s.name[0],
      dingTalkSynced: s.h % 10 !== 0,
    }));

  return [
    {
      tier: "A",
      labelKey: "layeredPush.tier.a.label",
      subtitleKey: "layeredPush.tier.a.subtitle",
      color: "bg-emerald-500/10",
      borderColor: "border-emerald-500/30",
      dotColor: "bg-emerald-500",
      students: toTierStudents(aStudents),
      assignments: subjectAssignments.A,
      estimatedMinutes: 60,
      deadlineKey: "layeredPush.friday",
      deadlineTime: "22:00",
      requireParentSign: true,
      requirePhoto: false,
      requireVoice: true,
    },
    {
      tier: "B",
      labelKey: "layeredPush.tier.b.label",
      subtitleKey: "layeredPush.tier.b.subtitle",
      color: "bg-yellow-500/10",
      borderColor: "border-yellow-500/30",
      dotColor: "bg-yellow-500",
      students: toTierStudents(bStudents),
      assignments: subjectAssignments.B,
      estimatedMinutes: 40,
      deadlineKey: "layeredPush.friday",
      deadlineTime: "22:00",
      requireParentSign: false,
      requirePhoto: true,
      requireVoice: false,
    },
    {
      tier: "C",
      labelKey: "layeredPush.tier.c.label",
      subtitleKey: "layeredPush.tier.c.subtitle",
      color: "bg-orange-500/10",
      borderColor: "border-orange-500/30",
      dotColor: "bg-orange-500",
      students: toTierStudents(cStudents),
      assignments: subjectAssignments.C,
      estimatedMinutes: 30,
      deadlineKey: "layeredPush.friday",
      deadlineTime: "20:00",
      requireParentSign: true,
      requirePhoto: false,
      requireVoice: false,
    },
  ];
}

export interface TrackingTier {
  tier: Tier;
  /** i18n key：分层档位标题 */
  labelKey: string;
  total: number;
  viewed: number;
  entered: number;
  completed: number;
  avgMinutes: number;
  feedback: { good: number; neutral: number; bad: number };
  unfinished: string[];
}

export function generateTracking(
  classId: string,
  subject: string,
): TrackingTier[] {
  const configs = generateTierConfigs(classId, subject);
  return configs.map((c) => {
    const total = c.students.length;
    const h = hash(c.tier + classId + subject);
    const viewedPct = c.tier === "A" ? 100 : c.tier === "B" ? 94 : 83;
    const enteredPct = c.tier === "A" ? 92 : c.tier === "B" ? 89 : 67;
    const completedPct = c.tier === "A" ? 100 : c.tier === "B" ? 94 : 67;
    const viewed = Math.round((total * viewedPct) / 100);
    const entered = Math.round((total * enteredPct) / 100);
    const completed = Math.round((total * completedPct) / 100);
    const unfinished = c.students.slice(completed).map((s) => s.name);
    return {
      tier: c.tier,
      labelKey: c.labelKey,
      total,
      viewed,
      entered,
      completed,
      avgMinutes: c.estimatedMinutes - 5 + (h % 10),
      feedback: {
        good: Math.round(completed * 0.7),
        neutral: Math.round(completed * 0.2),
        bad:
          completed - Math.round(completed * 0.7) - Math.round(completed * 0.2),
      },
      unfinished,
    };
  });
}

export interface DingTalkInteraction {
  groupMessages: number;
  sharedWorks: number;
  parentMessages: number;
  /** i18n key：主要话题 */
  mainTopicKey: string;
}

export function generateDingTalkInteraction(
  classId: string,
  subject: string,
): DingTalkInteraction {
  const h = hash("dingtalk" + classId + subject);
  return {
    groupMessages: 15 + (h % 20),
    sharedWorks: 3 + (h % 5),
    parentMessages: 5 + (h % 8),
    mainTopicKey: "layeredPush.interaction.mainTopic",
  };
}
