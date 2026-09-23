/* ─── Deterministic data generation for 课堂讲评 page ─── */

export function hash(str: string): number {
  let h = 5381;
  for (let i = 0; i < str.length; i++) h = ((h << 5) + h + str.charCodeAt(i)) | 0;
  return Math.abs(h);
}

/* ── Review priority items ── */
export interface ReviewPriority {
  id: number;
  priority: "high" | "medium" | "low";
  topic: string;
  scoreRate: number;
  errorCount: number;
  totalStudents: number;
  typicalErrors: string[];
  suggestedMinutes: number;
  method: string;
}

export function generateReviewPriorities(subject: string, seed: number): ReviewPriority[] {
  const topics: Record<string, { topic: string; errors: string[]; method: string }[]> = {
    语文: [
      { topic: "作文结构", errors: ["无层次", "开头冗长", "结尾仓促"], method: "对比展示+当堂练习" },
      { topic: "文言虚词用法", errors: ["与'之'混淆", "位置判断错误"], method: "口诀记忆+即时检测" },
      { topic: "古诗词默写", errors: ["'惟'写成'唯'", "'坐'写成'座'"], method: "易错字强调+当堂默写" },
      { topic: "阅读理解主旨", errors: ["偏离中心", "概括不全"], method: "关键句圈画+对比分析" },
    ],
    数学: [
      { topic: "函数单调性判断", errors: ["定义域遗漏", "符号方向错"], method: "图形辅助+变式训练" },
      { topic: "三角恒等变换", errors: ["公式记错", "化简方向错"], method: "公式推导+限时训练" },
      { topic: "向量运算", errors: ["坐标代入错", "方向判断错"], method: "几何直观+分步验算" },
    ],
    英语: [
      { topic: "定语从句关系词", errors: ["which/that混淆", "介词+which遗漏"], method: "语法填空+改错训练" },
      { topic: "完形填空逻辑", errors: ["上下文线索忽视", "词义辨析错"], method: "语境分析+词汇归类" },
      { topic: "书面表达结构", errors: ["缺少过渡", "结尾无总结"], method: "范文对比+仿写练习" },
    ],
    科学: [
      { topic: "科学探究实验", errors: ["控制变量法混淆", "实验现象描述不全"], method: "实验视频回放+步骤拆解" },
      { topic: "自然现象解释", errors: ["原理套用错误", "因果关系倒置"], method: "生活实例分析+因果推导" },
      { topic: "数据图表分析", errors: ["读图不完整", "趋势判断错误"], method: "图表特征标记+规律总结" },
    ],
  };

  const subjectTopics = topics[subject] || topics["语文"];
  return subjectTopics.map((t, i) => {
    const h = hash(`${seed}-rp-${i}`);
    const scoreRate = i === 0 ? 40 + (h % 10) : i === 1 ? 45 + (h % 10) : 65 + (h % 15);
    const errorCount = Math.max(5, 36 - Math.round(scoreRate * 0.36));
    return {
      id: i + 1,
      priority: i === 0 ? "high" : i === 1 ? "medium" : "low",
      topic: t.topic,
      scoreRate,
      errorCount,
      totalStudents: 36,
      typicalErrors: t.errors,
      suggestedMinutes: i === 0 ? 12 : i === 1 ? 8 : 5,
      method: t.method,
    };
  });
}

/* ── Similar exercises ── */
export interface SimilarExercise {
  id: number;
  title: string;
  difficulty: string;
  targetPriority: number;
  type: string;
}

export function generateSimilarExercises(seed: number): SimilarExercise[] {
  return [
    { id: 1, title: "结构优化专项训练", difficulty: "中等", targetPriority: 1, type: "课堂互动" },
    { id: 2, title: "虚词辨析强化练习", difficulty: "基础", targetPriority: 2, type: "即时检测" },
    { id: 3, title: "易错字巩固默写", difficulty: "基础", targetPriority: 3, type: "课堂默写" },
  ];
}

/* ── Layered groups ── */
export interface LayerGroup {
  layer: "A" | "B" | "C";
  label: string;
  color: string;
  bgColor: string;
  borderColor: string;
  studentCount: number;
  students: string[];
  task: string;
  duration: string;
  extra?: string;
}

const STUDENT_NAMES = [
  "张华", "李明", "王芳", "赵强", "陈静", "刘洋", "周涛", "吴敏",
  "孙磊", "郑亮", "马超", "胡杰", "林燕", "黄蕾", "徐刚", "何雪",
  "高峰", "罗琳", "谢宇", "邓辉", "韩雨", "唐欣", "冯凯", "曹丽",
  "彭博", "萧然", "蔡文", "潘晴", "董旭", "袁媛", "陆洋", "石鑫",
  "贾莹", "于飞", "龙腾", "钟鸣",
];

export function generateLayerGroups(seed: number): LayerGroup[] {
  const h = hash(`${seed}-layer`);
  const aCount = 10 + (h % 4);
  const cCount = 11 + (h % 4);
  const bCount = 36 - aCount - cCount;

  return [
    {
      layer: "A", label: "拓展组", color: "text-emerald-700", bgColor: "bg-emerald-50", borderColor: "border-emerald-200",
      studentCount: aCount,
      students: STUDENT_NAMES.slice(0, aCount),
      task: "创新结构挑战（双线结构/倒叙结构）",
      duration: "20分钟",
    },
    {
      layer: "B", label: "巩固组", color: "text-amber-700", bgColor: "bg-amber-50", borderColor: "border-amber-200",
      studentCount: bCount,
      students: STUDENT_NAMES.slice(aCount, aCount + bCount),
      task: "标准结构训练（总分总+过渡段）",
      duration: "15分钟",
    },
    {
      layer: "C", label: "补救组", color: "text-red-700", bgColor: "bg-red-50", borderColor: "border-red-200",
      studentCount: cCount,
      students: STUDENT_NAMES.slice(aCount + bCount),
      task: "基础结构模仿（填空式作文框架）",
      duration: "25分钟 + 微课视频",
      extra: "强制观看微课",
    },
  ];
}

/* ── Tracking stats ── */
export interface TrackingStats {
  reviewCount: number;
  avgEffectRate: number;
  bestStrategy: string;
  bestStrategyRate: number;
  worstStrategy: string;
  worstStrategyRate: number;
  preScoreRate: number;
}

export function generateTrackingStats(seed: number): TrackingStats {
  const h = hash(`${seed}-track`);
  return {
    reviewCount: 10 + (h % 8),
    avgEffectRate: 72 + (h % 15),
    bestStrategy: "对比展示+当堂练习",
    bestStrategyRate: 88 + (h % 8),
    worstStrategy: "纯讲解模式",
    worstStrategyRate: 40 + (h % 10),
    preScoreRate: 45,
  };
}

/* ── Classroom connection ── */
export interface InteractionState {
  connectedStudents: number;
  totalStudents: number;
  answeredCount: number;
  correctRate: number;
  calledStudents: string[];
  voteResult: { understood: number; partial: number; lost: number };
}

export function generateInteractionState(seed: number): InteractionState {
  const h = hash(`${seed}-interact`);
  return {
    connectedStudents: 34 + (h % 3),
    totalStudents: 36,
    answeredCount: 20 + (h % 12),
    correctRate: 55 + (h % 20),
    calledStudents: ["李明", "王芳"],
    voteResult: { understood: 60 + (h % 10), partial: 20 + (h % 8), lost: 5 + (h % 8) },
  };
}
