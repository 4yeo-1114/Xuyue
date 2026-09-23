/* ── Mock data for 智能生成 ── */

export type GenType = "courseware" | "worksheet" | "multimedia";

export const GEN_TYPE_OPTIONS: { value: GenType; label: string; icon: string }[] = [
  { value: "courseware", label: "互动课件", icon: "📊" },
  { value: "worksheet", label: "探究学案", icon: "📋" },
  { value: "multimedia", label: "视频推荐", icon: "🎬" },
];

export interface ToolRecommendation {
  icon: string;
  name: string;
  role: string;
  description: string;
  output: string;
}

export const RECOMMENDED_COMBO: ToolRecommendation[] = [
  { icon: "📜", name: "古诗文网", role: "文本基础", description: "原文+朗读+注释+赏析", output: "嵌入式文本页面，可点击查注释" },
  { icon: "🧠", name: "ProcessOn", role: "思维可视化", description: "动态思维导图，协作填空", output: "可交互导图模板，课堂实时填充" },
  { icon: "🎬", name: "剪映/必剪", role: "视频创作", description: "图文转视频，配音配乐", output: "视频脚本+配图建议+配音文案" },
];

export const EXTRA_TOOLS = ["📹 央视纪录片", "🎨 山海经图谱", "📝 腾讯文档协作", "🎤 配音工具"];

export interface ToolPreview {
  idx: number;
  total: number;
  tool: string;
  icon: string;
  status: "done" | "generating" | "pending";
  summary: string;
  details: string[];
  actions: string[];
}

export const TOOL_PREVIEWS: ToolPreview[] = [
  {
    idx: 1, total: 3, tool: "古诗文网内容", icon: "📜", status: "done",
    summary: "已获取：《阿长与山海经》全文+朗读",
    details: ["段落划分：5段", "重点注释：12处", "赏析：3段"],
    actions: ["预览文本", "调整段落", "选择朗读版本"],
  },
  {
    idx: 2, total: 3, tool: "ProcessOn思维导图", icon: "🧠", status: "generating",
    summary: "生成中：人物关系图模板...",
    details: ["预计：中心\"我\" → 分支\"阿长/情感/事件\"", "交互点：3处学生填空"],
    actions: ["查看进度", "调整结构", "更换模板"],
  },
  {
    idx: 3, total: 3, tool: "剪映视频脚本", icon: "🎬", status: "done",
    summary: "已生成：1分钟导入视频脚本",
    details: ["场景1：鲁迅书房（图片）+ 旁白", "场景2：阿长买书记（动画）+ 情感渲染", "配乐：怀旧钢琴曲"],
    actions: ["预览脚本", "调整时长", "更换风格"],
  },
];

export interface IntegrationStep {
  label: string;
  done: boolean;
}

export const INTEGRATION_STEPS: IntegrationStep[] = [
  { label: "提取各工具核心内容", done: true },
  { label: "设计课堂流程（导入→探究→总结）", done: true },
  { label: "匹配互动环节（3处讨论+1处协作）", done: true },
  { label: "生成分层作业（基于班级学情）", done: false },
  { label: "优化过渡语（工具间衔接）", done: false },
];

export interface CoursewareSection {
  pages: string;
  source: string;
  content: string;
  interaction?: string;
}

export const COURSEWARE_PREVIEW: CoursewareSection[] = [
  { pages: "第1-2页", source: "剪映生成", content: "\"1分钟看懂阿长与山海经的故事\"", interaction: "暂停讨论：你印象最深的细节？" },
  { pages: "第3-10页", source: "古诗文网嵌入", content: "分段展示，点击查注释，听名家朗读", interaction: "暂停讨论：阿长做了哪些\"好事\"？" },
  { pages: "第11-15页", source: "ProcessOn互动", content: "分组填写\"我-阿长-情感\"关系图", interaction: "实时投屏展示小组成果" },
  { pages: "第16-18页", source: "AI生成分层", content: "情感变化曲线总结", interaction: "A层：人物评传  B层：读后感  C层：摘抄+感想" },
];

export interface HistoryItem {
  time: string;
  title: string;
  tools: string;
  duration: string;
  status: "used" | "draft";
}

export const GENERATION_HISTORY: HistoryItem[] = [
  { time: "今天 09:30", title: "《阿长与山海经》课件", tools: "古诗文网+ProcessOn+剪映", duration: "3分钟", status: "used" },
  { time: "昨天 14:20", title: "第三单元测试卷", tools: "系统题库（未调用外部工具）", duration: "2分钟", status: "used" },
  { time: "昨天 10:15", title: "《老王》互动学案", tools: "腾讯文档+ProcessOn", duration: "4分钟", status: "draft" },
  { time: "周一 16:00", title: "古诗文朗读合集", tools: "古诗文网+西窗烛", duration: "5分钟", status: "used" },
];

export const TOOL_USAGE_STATS = [
  { name: "古诗文网", count: 5 },
  { name: "ProcessOn", count: 4 },
  { name: "剪映", count: 2 },
  { name: "央视纪录片", count: 3 },
  { name: "其他", count: 1 },
];

export interface SceneToolGroup {
  scene: string;
  tools: { icon: string; name: string; desc: string }[];
}

export const SCENE_TOOLS: SceneToolGroup[] = [
  { scene: "文本精读", tools: [
    { icon: "📜", name: "古诗文网", desc: "全文+朗读+注释" },
    { icon: "📖", name: "汉典", desc: "字词详解" },
    { icon: "🔍", name: "国学大师", desc: "古籍检索" },
  ]},
  { scene: "思维可视化", tools: [
    { icon: "🧠", name: "ProcessOn", desc: "思维导图/流程图" },
    { icon: "🗺️", name: "XMind", desc: "脑图工具" },
    { icon: "📊", name: "腾讯文档", desc: "协作表格" },
  ]},
  { scene: "音视频创作", tools: [
    { icon: "🎬", name: "剪映/必剪", desc: "短视频制作" },
    { icon: "🎵", name: "西窗烛", desc: "诗词朗读+意境" },
    { icon: "📹", name: "央视纪录片", desc: "背景视频" },
  ]},
  { scene: "互动探究", tools: [
    { icon: "📝", name: "腾讯文档", desc: "协作批注" },
    { icon: "🎨", name: "秀米/135", desc: "图文排版" },
    { icon: "📋", name: "问卷星", desc: "课堂检测" },
  ]},
  { scene: "图文展示", tools: [
    { icon: "🖼️", name: "中华典藏", desc: "古籍图谱" },
    { icon: "🎨", name: "Canva", desc: "海报/图文设计" },
    { icon: "📚", name: "微信读书", desc: "电子书嵌入" },
  ]},
];

export const TOOL_RANKINGS = [
  { name: "古诗文网", usage: "85%", rating: 5 },
  { name: "ProcessOn", usage: "72%", rating: 5 },
  { name: "剪映", usage: "45%", rating: 4 },
];
