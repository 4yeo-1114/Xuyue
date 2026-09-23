/* ─── Deterministic data generation for 靶向提升 page ─── */

import { hash } from "../class-review/reviewData";
export { hash };

export const STUDENT_NAMES = [
  "张华", "李明", "王芳", "赵强", "陈静", "刘洋", "周涛", "吴敏",
  "孙磊", "郑亮", "马超", "胡杰", "林燕", "黄蕾", "徐刚", "何雪",
  "高峰", "罗琳", "谢宇", "邓辉", "韩雨", "唐欣", "冯凯", "曹丽",
  "彭博", "萧然", "蔡文", "潘晴", "董旭", "袁媛", "陆洋", "石鑫",
  "贾莹", "于飞", "龙腾", "钟鸣",
];

/* ── Types ── */
export type TargetMode = "person" | "knowledge" | "question";

export interface StudentCandidate {
  name: string;
  number: string;
  score: number;
  trend: number; // positive = up
  tier: "A" | "B" | "C";
  status: "warning" | "attention" | "fluctuate" | "improving" | "stable";
  weakPoints: string[];
  statusLabel: string;
}

export interface Diagnosis {
  level: string;
  coreProblems: string[];
  rootCauses: string[];
  motivation: string;
  habit: string;
  method: string;
  timeManagement: string;
  strengths: string[];
  weaknesses: string[];
  interests: string[];
}

export interface PlanStage {
  name: string;
  weeks: string;
  coreTask: string;
  dailyTasks: string[];
  resources: { videos: number; exercises: number; templates: number };
}

export interface ImprovePlan {
  planName: string;
  duration: string;
  targetFrom: number;
  targetTo: number;
  targetTier: string;
  stages: PlanStage[];
  milestoneReward: string;
  badge: string;
  buddy: string;
}

export interface TrackingDay {
  day: number;
  label: string;
  task: string;
  status: "done" | "pending" | "future";
}

export interface HistoryPlan {
  name: string;
  completionRate: number;
  improvement: number;
}

export interface EffectData {
  pushDate: string;
  completionRate: number;
  correctRate: number;
  timeSpent: number;
  expectedTime: number;
  alertLevel: "green" | "yellow" | "red";
  days: TrackingDay[];
  history: HistoryPlan[];
  totalPlans: number;
  avgCompletion: number;
}

export interface KnowledgeTarget {
  id: number;
  name: string;
  masteryRate: number;
  affectedCount: number;
  trend: number;
  affectedStudents: string[];
  commonIssue: string;
}

export interface QuestionTarget {
  id: number;
  content: string;
  errorRate: number;
  typicalErrors: string[];
  knowledgePoints: string[];
  source: string;
  affectedStudents: string[];
}

export interface VariantQuestion {
  id: number;
  level: "巩固" | "提升" | "拓展";
  content: string;
  knowledgePoint: string;
  difficulty: number;
}

/* ── Generators ── */

const SUBJECT_WEAK_POINTS: Record<string, string[]> = {
  语文: ["作文结构", "阅读理解", "文言文翻译", "古诗词鉴赏", "修辞手法", "语言运用"],
  数学: ["函数单调性", "三角变换", "向量运算", "数列求和", "概率统计", "解析几何"],
  英语: ["定语从句", "完形填空", "阅读理解", "书面表达", "语法填空", "词汇辨析"],
  科学: ["科学探究", "现象解释", "实验设计", "数据分析", "物质科学", "生命科学", "地球与宇宙"],
  物理: ["力学分析", "电路计算", "运动学", "能量守恒", "电磁感应", "光学"],
  化学: ["方程式配平", "氧化还原", "有机合成", "离子反应", "化学平衡", "电化学"],
  生物: ["遗传规律", "细胞分裂", "光合作用", "生态系统", "神经调节", "免疫调节"],
  历史: ["近代史", "古代制度", "世界大战", "改革运动", "文化史", "经济史"],
  地理: ["气候类型", "地形地貌", "人口迁移", "城市化", "农业区位", "工业区位"],
  政治: ["哲学原理", "经济常识", "政治制度", "文化生活", "法律常识", "时政分析"],
};

const STATUS_MAP: Record<string, string> = {
  warning: "预警", attention: "需关注", fluctuate: "波动大", improving: "进步中", stable: "稳定",
};

export function generateStudentCandidates(classId: string, subject: string): StudentCandidate[] {
  const weakPoints = SUBJECT_WEAK_POINTS[subject] || SUBJECT_WEAK_POINTS["语文"];
  return STUDENT_NAMES.map((name, i) => {
    const h = hash(classId + subject + name);
    const score = 45 + (h % 50);
    const trend = ((h >> 4) % 21) - 10;
    const tier: "A" | "B" | "C" = score >= 85 ? "A" : score >= 70 ? "B" : "C";
    const statuses: StudentCandidate["status"][] = ["warning", "attention", "fluctuate", "improving", "stable"];
    const status = score < 60 ? "warning" : score < 70 ? "attention" : Math.abs(trend) > 5 ? "fluctuate" : trend > 0 ? "improving" : "stable";
    const wp = [weakPoints[h % weakPoints.length], weakPoints[(h >> 3) % weakPoints.length]].filter((v, i, a) => a.indexOf(v) === i);
    return {
      name,
      number: `2023${String(i + 1).padStart(4, "0")}`,
      score,
      trend,
      tier,
      status,
      weakPoints: wp,
      statusLabel: STATUS_MAP[status],
    };
  });
}

export function generateRecommendedTargets(classId: string, subject: string): StudentCandidate[] {
  const all = generateStudentCandidates(classId, subject);
  const warning = all.find(s => s.status === "warning");
  const attention = all.find(s => s.status === "attention");
  const fluctuate = all.find(s => s.status === "fluctuate");
  const improving = all.find(s => s.status === "improving" && s.tier !== "A");
  return [warning, attention, fluctuate, improving].filter(Boolean) as StudentCandidate[];
}

export function generateDiagnosis(classId: string, subject: string, studentName: string): Diagnosis {
  const h = hash(classId + subject + studentName + "diag");
  const weakPoints = SUBJECT_WEAK_POINTS[subject] || SUBJECT_WEAK_POINTS["语文"];
  const score = 45 + (hash(classId + subject + studentName) % 50);
  const tier = score >= 85 ? "A层（拓展层）" : score >= 70 ? "B层（提高层）偏下" : "C层（基础层）";
  const motivations = ["较高（自我驱动型）", "中等（曾有进步，近期受挫）", "偏低（缺乏目标感）"];
  const habits = ["良好（有预习复习习惯）", "较差（无预习，不复习，不整理错题）", "一般（偶尔复习）"];
  const methods = ["多元化（善于归纳总结）", "单一（死记硬背，缺乏理解）", "一般（有方法意识但不稳定）"];
  const times = ["较好（作息规律）", "薄弱（拖延，熬夜，效率低）", "一般（偶尔拖延）"];
  const strengthPool = ["逻辑思维较好", "记忆力强", "善于表达", "计算能力强", "阅读速度快"];
  const weakPool = ["形象思维弱", "语言表达能力欠缺", "粗心大意", "审题不仔细", "缺乏总结能力"];
  const interestPool = ["科技类话题", "体育运动", "历史故事", "动漫文化", "音乐艺术"];

  return {
    level: tier,
    coreProblems: [weakPoints[h % weakPoints.length] + "薄弱", weakPoints[(h >> 2) % weakPoints.length] + "理解偏差"],
    rootCauses: [
      "缺乏系统训练（从未做过专项）",
      "相关阅读/练习量少，缺乏实战经验",
      "近期学习投入下降（作业时长-20%）",
    ],
    motivation: motivations[h % 3],
    habit: habits[(h >> 2) % 3],
    method: methods[(h >> 4) % 3],
    timeManagement: times[(h >> 6) % 3],
    strengths: [strengthPool[h % 5], strengthPool[(h >> 3) % 5]].filter((v, i, a) => a.indexOf(v) === i),
    weaknesses: [weakPool[h % 5], weakPool[(h >> 2) % 5]].filter((v, i, a) => a.indexOf(v) === i),
    interests: [interestPool[h % 5]],
  };
}

export function generateImprovePlan(classId: string, subject: string, studentName: string): ImprovePlan {
  const h = hash(classId + subject + studentName + "plan");
  const score = 45 + (hash(classId + subject + studentName) % 50);
  const weakPoints = SUBJECT_WEAK_POINTS[subject] || SUBJECT_WEAK_POINTS["语文"];
  const wp1 = weakPoints[h % weakPoints.length];
  const wp2 = weakPoints[(h >> 3) % weakPoints.length];
  const targetTo = Math.min(95, score + 7 + (h % 5));
  const buddyIdx = (hash(classId + subject + studentName) + 5) % STUDENT_NAMES.length;

  return {
    planName: `${wp1}突破+${wp2}训练计划`,
    duration: "4周",
    targetFrom: score,
    targetTo,
    targetTier: targetTo >= 85 ? "A层" : "B层",
    stages: [
      {
        name: "基础重建", weeks: "Week 1-2", coreTask: `建立${wp1}基本概念，养成整理习惯`,
        dailyTasks: [`观看微课《${wp1}方法论》（15分钟）`, `完成${wp1}填空练习2题（10分钟）`, `归纳整理：记录当日要点`],
        resources: { videos: 3, exercises: 20, templates: 5 },
      },
      {
        name: "应用提升", weeks: "Week 3", coreTask: `完整应用+限时训练`,
        dailyTasks: [`完整${wp1}综合题1套（限时40分钟）`, `AI批改+教师面批`, `优秀范例分析2篇`],
        resources: { videos: 2, exercises: 10, templates: 3 },
      },
      {
        name: "巩固迁移", weeks: "Week 4", coreTask: `综合应用，稳定输出`,
        dailyTasks: [`模拟测试（全真环境）`, `${wp2}专项训练（结合兴趣话题）`, `错题回顾与归纳`],
        resources: { videos: 1, exercises: 10, templates: 2 },
      },
    ],
    milestoneReward: "完成阶段一→表扬信给家长",
    badge: `${wp1}大师`,
    buddy: STUDENT_NAMES[buddyIdx],
  };
}

export function generateEffectData(classId: string, subject: string, studentName: string): EffectData {
  const h = hash(classId + subject + studentName + "effect");
  const days: TrackingDay[] = Array.from({ length: 7 }, (_, i) => ({
    day: i + 1,
    label: i === 0 ? "今日" : i === 1 ? "明日" : `Day${i + 1}`,
    task: i % 2 === 0 ? "微课+练习" : "专项训练",
    status: i === 0 ? "done" : i < 3 ? "pending" : "future",
  }));

  return {
    pushDate: "2024-01-15 20:00",
    completionRate: 20 + (h % 40),
    correctRate: 60 + (h % 30),
    timeSpent: 25 + (h % 20),
    expectedTime: 30,
    alertLevel: h % 3 === 0 ? "green" : h % 3 === 1 ? "yellow" : "green",
    days,
    history: [
      { name: "古诗词突破计划", completionRate: 85 + (h % 10), improvement: 10 + (h % 8) },
      { name: "阅读理解专项", completionRate: 65 + (h % 15), improvement: 5 + (h % 5) },
      { name: "基础巩固训练", completionRate: 40 + (h % 15), improvement: 2 + (h % 3) },
    ],
    totalPlans: 3,
    avgCompletion: 65 + (h % 15),
  };
}

export function generateKnowledgeTargets(classId: string, subject: string): KnowledgeTarget[] {
  const weakPoints = SUBJECT_WEAK_POINTS[subject] || SUBJECT_WEAK_POINTS["语文"];
  return weakPoints.map((name, i) => {
    const h = hash(classId + subject + name);
    const masteryRate = 30 + (h % 50);
    const affectedCount = Math.max(3, Math.round((100 - masteryRate) * 0.36));
    const students = STUDENT_NAMES.slice(0, affectedCount);
    return {
      id: i + 1,
      name,
      masteryRate,
      affectedCount,
      trend: ((h >> 4) % 11) - 5,
      affectedStudents: students,
      commonIssue: i % 3 === 0 ? "教学方法需调整" : i % 3 === 1 ? "前置知识不扎实" : "练习量不足",
    };
  }).sort((a, b) => a.masteryRate - b.masteryRate);
}

export function generateQuestionTargets(classId: string, subject: string): QuestionTarget[] {
  const weakPoints = SUBJECT_WEAK_POINTS[subject] || SUBJECT_WEAK_POINTS["语文"];
  const questions = [
    "下列关于{kp}的说法，正确的是？",
    "阅读下面材料，分析{kp}的核心要点。",
    "请运用{kp}的方法，解答以下问题。",
    "关于{kp}，以下哪项理解有误？",
    "结合{kp}知识，完成以下综合题。",
  ];
  return questions.map((q, i) => {
    const h = hash(classId + subject + `q${i}`);
    const kp = weakPoints[i % weakPoints.length];
    const errorRate = 30 + (h % 45);
    const affectedCount = Math.max(3, Math.round(errorRate * 0.36));
    return {
      id: i + 1,
      content: q.replace("{kp}", kp),
      errorRate,
      typicalErrors: ["概念混淆", "计算/书写错误", "审题不清"].slice(0, 2 + (h % 2)),
      knowledgePoints: [kp, weakPoints[(i + 1) % weakPoints.length]],
      source: i % 2 === 0 ? "期中考试第" + (i + 3) + "题" : "周测第" + (i + 1) + "题",
      affectedStudents: STUDENT_NAMES.slice(0, affectedCount),
    };
  }).sort((a, b) => b.errorRate - a.errorRate);
}

export function generateVariantQuestions(classId: string, subject: string, questionId: number): VariantQuestion[] {
  const weakPoints = SUBJECT_WEAK_POINTS[subject] || SUBJECT_WEAK_POINTS["语文"];
  const h = hash(classId + subject + `var${questionId}`);
  const kp = weakPoints[questionId % weakPoints.length];
  return [
    { id: 1, level: "巩固", content: `换情境练习：在新的场景下应用${kp}的基本方法。`, knowledgePoint: kp, difficulty: 2 },
    { id: 2, level: "提升", content: `换角度分析：从不同维度理解${kp}的深层逻辑。`, knowledgePoint: kp, difficulty: 3 },
    { id: 3, level: "拓展", content: `综合应用：结合${kp}与${weakPoints[(questionId + 2) % weakPoints.length]}完成复合题。`, knowledgePoint: kp, difficulty: 4 },
  ];
}

/* ── Preview plan summary ── */
export interface PlanPreviewData {
  weeks: { week: string; videos: number; exercises: number; templates: number; faceBatch?: number }[];
  dailyTime: string;
  weekendTime: string;
  completionDate: string;
  conflict: string | null;
}

export function generatePlanPreview(plan: ImprovePlan): PlanPreviewData {
  return {
    weeks: plan.stages.map((s, i) => ({
      week: s.weeks,
      ...s.resources,
      faceBatch: i > 0 ? 1 : undefined,
    })),
    dailyTime: "每日30分钟",
    weekendTime: "周末1小时",
    completionDate: "4周后",
    conflict: "与数学竞赛辅导时间冲突（周三晚）",
  };
}
