/**
 * Knowledge graph data structures and mock data generators
 * for all grade × subject combinations.
 */

export interface KnowledgeNode {
  id: string;
  name: string;
  cluster: string;
  /** depth level in tree (0=root category) */
  level: number;
  /** ring in radial graph: 1=basic, 2=core, 3=advanced */
  ring: 1 | 2 | 3;
  /** class mastery 0-100 */
  mastery: number;
  parentId?: string;
  prerequisites: string[];
  followups: string[];
  /** score weight */
  weight: number;
  /** class hours */
  hours: number;
  /** node type for icon */
  nodeType: "reading" | "writing" | "memorize" | "apply" | "compute" | "experiment" | "listen" | "speak";
}

export interface KnowledgeLink {
  source: string;
  target: string;
  type: "prerequisite" | "followup" | "parallel";
  strength: number; // 0-1
}

export interface KnowledgeGraphData {
  subject: string;
  stage: string;
  totalNodes: number;
  clusters: string[];
  nodes: KnowledgeNode[];
  links: KnowledgeLink[];
}

/* ── Deterministic hash for stable mastery values ── */
function hashStr(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

function mastery(id: string, base: number, range: number = 40): number {
  return Math.max(15, Math.min(98, base + (hashStr(id) % range) - range / 2));
}

/* ═══════════════════════════════════════════
   Chinese (语文) knowledge graphs
   ═══════════════════════════════════════════ */

function chinesePrimary(): KnowledgeGraphData {
  const nodes: KnowledgeNode[] = [
    { id: "pinyin", name: "拼音", cluster: "字词基础", level: 1, ring: 1, mastery: mastery("pinyin", 88), parentId: "c_base", prerequisites: [], followups: ["literacy"], weight: 10, hours: 12, nodeType: "memorize" },
    { id: "literacy", name: "识字写字", cluster: "字词基础", level: 1, ring: 1, mastery: mastery("literacy", 82), parentId: "c_base", prerequisites: ["pinyin"], followups: ["vocabulary"], weight: 15, hours: 20, nodeType: "memorize" },
    { id: "vocabulary", name: "词语积累", cluster: "字词基础", level: 1, ring: 1, mastery: mastery("vocabulary", 78), parentId: "c_base", prerequisites: ["literacy"], followups: ["sentence"], weight: 10, hours: 15, nodeType: "memorize" },
    { id: "sentence", name: "句子运用", cluster: "字词基础", level: 1, ring: 2, mastery: mastery("sentence", 72), parentId: "c_base", prerequisites: ["vocabulary"], followups: ["paragraph"], weight: 10, hours: 10, nodeType: "apply" },
    { id: "punctuation", name: "标点符号", cluster: "字词基础", level: 1, ring: 1, mastery: mastery("punctuation", 80), parentId: "c_base", prerequisites: [], followups: ["sentence"], weight: 5, hours: 6, nodeType: "apply" },
    { id: "reading_aloud", name: "朗读背诵", cluster: "阅读理解", level: 1, ring: 1, mastery: mastery("reading_aloud", 85), parentId: "c_read", prerequisites: ["pinyin"], followups: ["comprehension"], weight: 8, hours: 15, nodeType: "reading" },
    { id: "comprehension", name: "课文理解", cluster: "阅读理解", level: 1, ring: 2, mastery: mastery("comprehension", 68), parentId: "c_read", prerequisites: ["reading_aloud", "vocabulary"], followups: ["extract_info"], weight: 15, hours: 20, nodeType: "reading" },
    { id: "extract_info", name: "信息提取", cluster: "阅读理解", level: 1, ring: 2, mastery: mastery("extract_info", 62), parentId: "c_read", prerequisites: ["comprehension"], followups: [], weight: 10, hours: 10, nodeType: "reading" },
    { id: "paragraph", name: "段落写作", cluster: "写话习作", level: 1, ring: 2, mastery: mastery("paragraph", 60), parentId: "c_write", prerequisites: ["sentence"], followups: ["picture_writing"], weight: 10, hours: 12, nodeType: "writing" },
    { id: "picture_writing", name: "看图写话", cluster: "写话习作", level: 1, ring: 2, mastery: mastery("picture_writing", 58), parentId: "c_write", prerequisites: ["paragraph"], followups: ["diary"], weight: 10, hours: 10, nodeType: "writing" },
    { id: "diary", name: "日记周记", cluster: "写话习作", level: 1, ring: 3, mastery: mastery("diary", 55), parentId: "c_write", prerequisites: ["picture_writing"], followups: [], weight: 8, hours: 8, nodeType: "writing" },
    { id: "poetry_recite", name: "古诗文背诵", cluster: "古诗文", level: 1, ring: 1, mastery: mastery("poetry_recite", 75), parentId: "c_poetry", prerequisites: [], followups: ["poetry_understand"], weight: 10, hours: 15, nodeType: "memorize" },
    { id: "poetry_understand", name: "古诗文理解", cluster: "古诗文", level: 1, ring: 2, mastery: mastery("poetry_understand", 60), parentId: "c_poetry", prerequisites: ["poetry_recite"], followups: [], weight: 8, hours: 10, nodeType: "reading" },
    { id: "oral_comm", name: "口语交际", cluster: "口语交际", level: 1, ring: 2, mastery: mastery("oral_comm", 70), parentId: "c_oral", prerequisites: ["sentence"], followups: [], weight: 5, hours: 8, nodeType: "speak" },
  ];
  const links: KnowledgeLink[] = [
    { source: "pinyin", target: "literacy", type: "prerequisite", strength: 0.9 },
    { source: "literacy", target: "vocabulary", type: "prerequisite", strength: 0.8 },
    { source: "vocabulary", target: "sentence", type: "prerequisite", strength: 0.7 },
    { source: "sentence", target: "paragraph", type: "prerequisite", strength: 0.8 },
    { source: "paragraph", target: "picture_writing", type: "prerequisite", strength: 0.7 },
    { source: "picture_writing", target: "diary", type: "followup", strength: 0.6 },
    { source: "pinyin", target: "reading_aloud", type: "prerequisite", strength: 0.7 },
    { source: "reading_aloud", target: "comprehension", type: "prerequisite", strength: 0.8 },
    { source: "comprehension", target: "extract_info", type: "followup", strength: 0.7 },
    { source: "poetry_recite", target: "poetry_understand", type: "prerequisite", strength: 0.8 },
    { source: "comprehension", target: "poetry_understand", type: "parallel", strength: 0.5 },
    { source: "sentence", target: "oral_comm", type: "parallel", strength: 0.4 },
  ];
  return { subject: "语文", stage: "小学", totalNodes: nodes.length, clusters: ["字词基础", "阅读理解", "写话习作", "古诗文", "口语交际"], nodes, links };
}

function chineseSenior(): KnowledgeGraphData {
  const n = (id: string, name: string, cluster: string, ring: 1|2|3, base: number, pre: string[], fol: string[], w: number, h: number, t: KnowledgeNode["nodeType"], parentId?: string): KnowledgeNode =>
    ({ id, name, cluster, level: 1, ring, mastery: mastery(id, base), parentId, prerequisites: pre, followups: fol, weight: w, hours: h, nodeType: t });

  const nodes: KnowledgeNode[] = [
    // 语言积累与建构
    n("hanzi", "汉字汉语", "语言积累与建构", 1, 82, [], ["grammar"], 5, 6, "memorize"),
    n("grammar", "语法修辞", "语言积累与建构", 1, 75, ["hanzi"], ["logic"], 8, 8, "apply"),
    n("logic", "逻辑推理", "语言积累与建构", 2, 62, ["grammar"], [], 8, 6, "apply"),
    // 文学阅读与写作
    n("poetry_appreciation", "诗歌鉴赏", "文学阅读与写作", 2, 68, [], ["poetry_image", "poetry_language", "poetry_emotion"], 15, 12, "reading"),
    n("poetry_image", "形象意境", "文学阅读与写作", 2, 75, ["poetry_appreciation"], [], 5, 4, "reading", "poetry_appreciation"),
    n("poetry_language", "语言技巧", "文学阅读与写作", 2, 62, ["poetry_appreciation"], ["poetry_emotion"], 5, 4, "reading", "poetry_appreciation"),
    n("poetry_emotion", "思想情感", "文学阅读与写作", 3, 58, ["poetry_language"], ["culture_common"], 5, 4, "reading", "poetry_appreciation"),
    n("prose_reading", "散文阅读", "文学阅读与写作", 2, 72, [], [], 10, 8, "reading"),
    n("novel_reading", "小说阅读", "文学阅读与写作", 2, 65, [], ["novel_plot", "novel_character", "novel_theme"], 12, 10, "reading"),
    n("novel_plot", "情节结构", "文学阅读与写作", 2, 70, ["novel_reading"], [], 4, 3, "reading", "novel_reading"),
    n("novel_character", "人物形象", "文学阅读与写作", 2, 68, ["novel_reading"], [], 4, 3, "reading", "novel_reading"),
    n("novel_theme", "环境主题", "文学阅读与写作", 3, 55, ["novel_reading"], [], 4, 3, "reading", "novel_reading"),
    n("drama", "戏剧阅读", "文学阅读与写作", 3, 45, [], [], 6, 4, "reading"),
    // 思辨性阅读与表达
    n("argumentative_read", "论述类文本", "思辨性阅读与表达", 2, 52, ["logic"], ["argumentative_write"], 12, 10, "reading"),
    n("argumentative_write", "议论文写作", "思辨性阅读与表达", 3, 48, ["argumentative_read"], [], 15, 12, "writing"),
    // 实用性阅读与交流
    n("practical_read", "实用类文本", "实用性阅读与交流", 2, 70, [], [], 8, 6, "reading"),
    n("practical_write", "应用文写作", "实用性阅读与交流", 2, 65, ["practical_read"], [], 8, 6, "writing"),
    // 文言文阅读
    n("classical_words", "实词120个", "文言文阅读", 1, 60, [], ["classical_function"], 10, 12, "memorize"),
    n("classical_function", "虚词18个", "文言文阅读", 2, 55, ["classical_words"], ["classical_sentence"], 8, 10, "memorize"),
    n("classical_sentence", "特殊句式", "文言文阅读", 2, 50, ["classical_function"], [], 8, 8, "apply"),
    n("culture_common", "文化常识", "文言文阅读", 2, 65, [], [], 6, 6, "memorize"),
    // 古诗文默写
    n("dictation_required", "必背篇目", "古诗文默写", 1, 72, [], [], 8, 10, "memorize"),
    n("dictation_optional", "选背篇目", "古诗文默写", 2, 60, ["dictation_required"], [], 5, 6, "memorize"),
  ];

  const links: KnowledgeLink[] = [
    { source: "hanzi", target: "grammar", type: "prerequisite", strength: 0.8 },
    { source: "grammar", target: "logic", type: "prerequisite", strength: 0.7 },
    { source: "logic", target: "argumentative_read", type: "prerequisite", strength: 0.8 },
    { source: "argumentative_read", target: "argumentative_write", type: "prerequisite", strength: 0.9 },
    { source: "poetry_appreciation", target: "poetry_image", type: "prerequisite", strength: 0.7 },
    { source: "poetry_appreciation", target: "poetry_language", type: "prerequisite", strength: 0.7 },
    { source: "poetry_language", target: "poetry_emotion", type: "prerequisite", strength: 0.8 },
    { source: "poetry_emotion", target: "culture_common", type: "followup", strength: 0.5 },
    { source: "novel_reading", target: "novel_plot", type: "prerequisite", strength: 0.7 },
    { source: "novel_reading", target: "novel_character", type: "prerequisite", strength: 0.7 },
    { source: "novel_reading", target: "novel_theme", type: "prerequisite", strength: 0.6 },
    { source: "prose_reading", target: "poetry_emotion", type: "parallel", strength: 0.5 },
    { source: "novel_theme", target: "drama", type: "parallel", strength: 0.4 },
    { source: "classical_words", target: "classical_function", type: "prerequisite", strength: 0.9 },
    { source: "classical_function", target: "classical_sentence", type: "prerequisite", strength: 0.8 },
    { source: "dictation_required", target: "dictation_optional", type: "followup", strength: 0.6 },
    { source: "practical_read", target: "practical_write", type: "prerequisite", strength: 0.7 },
  ];

  return { subject: "语文", stage: "高中", totalNodes: nodes.length, clusters: ["语言积累与建构", "文学阅读与写作", "思辨性阅读与表达", "实用性阅读与交流", "文言文阅读", "古诗文默写"], nodes, links };
}

/* ═══════════════════════════════════════════
   Math knowledge graph
   ═══════════════════════════════════════════ */

function mathPrimary(): KnowledgeGraphData {
  const n = (id: string, name: string, cluster: string, ring: 1|2|3, base: number, pre: string[], fol: string[], w: number, h: number): KnowledgeNode =>
    ({ id, name, cluster, level: 1, ring, mastery: mastery(id, base), prerequisites: pre, followups: fol, weight: w, hours: h, nodeType: "compute" });

  const nodes = [
    n("addition", "加减法", "数与运算", 1, 90, [], ["multiplication"], 10, 15),
    n("multiplication", "乘除法", "数与运算", 1, 85, ["addition"], ["mixed_ops"], 12, 15),
    n("mixed_ops", "混合运算", "数与运算", 2, 75, ["multiplication"], ["fractions"], 10, 10),
    n("fractions", "分数小数", "数与运算", 2, 68, ["mixed_ops"], ["ratio"], 12, 12),
    n("ratio", "比与比例", "数与运算", 3, 60, ["fractions"], [], 8, 8),
    n("measurement", "量与计量", "图形与测量", 1, 80, [], ["perimeter"], 8, 10),
    n("perimeter", "周长面积", "图形与测量", 2, 72, ["measurement", "multiplication"], ["volume"], 12, 12),
    n("volume", "体积容积", "图形与测量", 3, 58, ["perimeter"], [], 8, 8),
    n("shapes_2d", "平面图形", "图形与测量", 1, 82, [], ["perimeter", "symmetry"], 10, 10),
    n("symmetry", "对称平移", "图形与测量", 2, 70, ["shapes_2d"], [], 6, 6),
    n("patterns", "找规律", "统计与概率", 1, 78, [], ["bar_chart"], 6, 8),
    n("bar_chart", "条形统计图", "统计与概率", 2, 72, ["patterns"], ["possibility"], 8, 8),
    n("possibility", "可能性", "统计与概率", 2, 65, ["bar_chart"], [], 6, 6),
    n("word_problems", "应用题", "解决问题", 2, 60, ["mixed_ops"], ["multi_step"], 15, 15),
    n("multi_step", "多步骤问题", "解决问题", 3, 52, ["word_problems", "fractions"], [], 10, 10),
  ];

  const links: KnowledgeLink[] = [
    { source: "addition", target: "multiplication", type: "prerequisite", strength: 0.9 },
    { source: "multiplication", target: "mixed_ops", type: "prerequisite", strength: 0.9 },
    { source: "mixed_ops", target: "fractions", type: "prerequisite", strength: 0.8 },
    { source: "fractions", target: "ratio", type: "prerequisite", strength: 0.7 },
    { source: "measurement", target: "perimeter", type: "prerequisite", strength: 0.8 },
    { source: "perimeter", target: "volume", type: "prerequisite", strength: 0.7 },
    { source: "shapes_2d", target: "perimeter", type: "prerequisite", strength: 0.6 },
    { source: "shapes_2d", target: "symmetry", type: "followup", strength: 0.5 },
    { source: "patterns", target: "bar_chart", type: "prerequisite", strength: 0.6 },
    { source: "bar_chart", target: "possibility", type: "followup", strength: 0.5 },
    { source: "mixed_ops", target: "word_problems", type: "prerequisite", strength: 0.8 },
    { source: "word_problems", target: "multi_step", type: "prerequisite", strength: 0.8 },
    { source: "multiplication", target: "perimeter", type: "parallel", strength: 0.4 },
  ];

  return { subject: "数学", stage: "小学", totalNodes: nodes.length, clusters: ["数与运算", "图形与测量", "统计与概率", "解决问题"], nodes, links };
}

function mathSenior(): KnowledgeGraphData {
  const n = (id: string, name: string, cluster: string, ring: 1|2|3, base: number, pre: string[], fol: string[], w: number, h: number): KnowledgeNode =>
    ({ id, name, cluster, level: 1, ring, mastery: mastery(id, base), prerequisites: pre, followups: fol, weight: w, hours: h, nodeType: "compute" });

  const nodes = [
    n("sets", "集合", "代数", 1, 85, [], ["functions"], 6, 8),
    n("functions", "函数概念", "代数", 1, 78, ["sets"], ["quadratic", "exponential"], 12, 15),
    n("quadratic", "二次函数", "代数", 2, 70, ["functions"], ["inequalities"], 10, 10),
    n("exponential", "指数对数", "代数", 2, 65, ["functions"], ["derivative"], 10, 10),
    n("inequalities", "不等式", "代数", 2, 68, ["quadratic"], [], 8, 8),
    n("sequences", "数列", "代数", 2, 62, ["functions"], ["series"], 10, 10),
    n("series", "级数求和", "代数", 3, 50, ["sequences"], [], 8, 8),
    n("derivative", "导数", "代数", 3, 55, ["exponential", "quadratic"], ["integral"], 15, 15),
    n("integral", "积分初步", "代数", 3, 45, ["derivative"], [], 10, 10),
    n("trig_basic", "三角函数", "三角", 2, 65, ["functions"], ["trig_identity"], 12, 12),
    n("trig_identity", "三角恒等", "三角", 2, 58, ["trig_basic"], ["trig_solve"], 8, 8),
    n("trig_solve", "解三角形", "三角", 3, 52, ["trig_identity"], [], 10, 10),
    n("vectors_2d", "平面向量", "几何", 1, 72, [], ["vectors_3d", "analytic_line"], 10, 10),
    n("analytic_line", "直线方程", "几何", 2, 68, ["vectors_2d"], ["conic"], 10, 10),
    n("conic", "圆锥曲线", "几何", 3, 48, ["analytic_line"], [], 15, 15),
    n("vectors_3d", "空间向量", "几何", 2, 60, ["vectors_2d"], ["solid_geometry"], 10, 10),
    n("solid_geometry", "立体几何", "几何", 2, 55, ["vectors_3d"], [], 12, 12),
    n("probability", "概率", "统计与概率", 1, 75, [], ["distribution"], 8, 8),
    n("distribution", "分布与期望", "统计与概率", 2, 60, ["probability", "sequences"], [], 10, 10),
    n("counting", "排列组合", "统计与概率", 2, 58, ["probability"], ["distribution"], 10, 10),
  ];

  const links: KnowledgeLink[] = [
    { source: "sets", target: "functions", type: "prerequisite", strength: 0.9 },
    { source: "functions", target: "quadratic", type: "prerequisite", strength: 0.9 },
    { source: "functions", target: "exponential", type: "prerequisite", strength: 0.8 },
    { source: "functions", target: "sequences", type: "prerequisite", strength: 0.7 },
    { source: "functions", target: "trig_basic", type: "prerequisite", strength: 0.7 },
    { source: "quadratic", target: "inequalities", type: "followup", strength: 0.6 },
    { source: "quadratic", target: "derivative", type: "prerequisite", strength: 0.8 },
    { source: "exponential", target: "derivative", type: "prerequisite", strength: 0.8 },
    { source: "derivative", target: "integral", type: "prerequisite", strength: 0.9 },
    { source: "sequences", target: "series", type: "prerequisite", strength: 0.8 },
    { source: "trig_basic", target: "trig_identity", type: "prerequisite", strength: 0.8 },
    { source: "trig_identity", target: "trig_solve", type: "prerequisite", strength: 0.7 },
    { source: "vectors_2d", target: "analytic_line", type: "prerequisite", strength: 0.7 },
    { source: "vectors_2d", target: "vectors_3d", type: "prerequisite", strength: 0.8 },
    { source: "analytic_line", target: "conic", type: "prerequisite", strength: 0.8 },
    { source: "vectors_3d", target: "solid_geometry", type: "prerequisite", strength: 0.7 },
    { source: "probability", target: "counting", type: "parallel", strength: 0.6 },
    { source: "counting", target: "distribution", type: "prerequisite", strength: 0.7 },
  ];

  return { subject: "数学", stage: "高中", totalNodes: nodes.length, clusters: ["代数", "三角", "几何", "统计与概率"], nodes, links };
}

/* ═══════════════════════════════════════════
   English knowledge graph
   ═══════════════════════════════════════════ */

function englishGraph(): KnowledgeGraphData {
  const n = (id: string, name: string, cluster: string, ring: 1|2|3, base: number, pre: string[], fol: string[], w: number, h: number, t: KnowledgeNode["nodeType"]): KnowledgeNode =>
    ({ id, name, cluster, level: 1, ring, mastery: mastery(id, base), prerequisites: pre, followups: fol, weight: w, hours: h, nodeType: t });

  const nodes = [
    // Listening
    n("listening_basic", "听力理解基础", "听力", 1, 75, [], ["listening_detail"], 8, 10, "listen"),
    n("listening_detail", "细节捕捉", "听力", 2, 68, ["listening_basic"], ["listening_infer"], 8, 8, "listen"),
    n("listening_infer", "推理判断", "听力", 3, 55, ["listening_detail"], [], 8, 8, "listen"),
    // Speaking
    n("pronunciation", "语音语调", "口语", 1, 72, [], ["oral_express"], 6, 8, "speak"),
    n("oral_express", "口语表达", "口语", 2, 65, ["pronunciation"], ["oral_discuss"], 8, 8, "speak"),
    n("oral_discuss", "话题讨论", "口语", 3, 50, ["oral_express"], [], 6, 6, "speak"),
    // Reading
    n("vocabulary_core", "核心词汇", "阅读", 1, 70, [], ["grammar_basic", "reading_comp"], 12, 15, "memorize"),
    n("grammar_basic", "基础语法", "阅读", 1, 72, ["vocabulary_core"], ["grammar_complex"], 10, 12, "apply"),
    n("grammar_complex", "复杂句式", "阅读", 2, 58, ["grammar_basic"], [], 10, 10, "apply"),
    n("reading_comp", "阅读理解", "阅读", 2, 65, ["vocabulary_core"], ["reading_cloze"], 15, 15, "reading"),
    n("reading_cloze", "完形填空", "阅读", 2, 60, ["reading_comp", "grammar_basic"], [], 10, 10, "reading"),
    n("reading_7c", "七选五", "阅读", 3, 52, ["reading_comp"], [], 8, 8, "reading"),
    // Writing
    n("writing_basic", "基础写作", "写作", 2, 62, ["grammar_basic", "vocabulary_core"], ["writing_essay"], 10, 10, "writing"),
    n("writing_essay", "篇章写作", "写作", 3, 48, ["writing_basic", "grammar_complex"], ["writing_continue"], 12, 12, "writing"),
    n("writing_continue", "续写/概写", "写作", 3, 42, ["writing_essay"], [], 10, 10, "writing"),
  ];

  const links: KnowledgeLink[] = [
    { source: "listening_basic", target: "listening_detail", type: "prerequisite", strength: 0.8 },
    { source: "listening_detail", target: "listening_infer", type: "prerequisite", strength: 0.7 },
    { source: "pronunciation", target: "oral_express", type: "prerequisite", strength: 0.8 },
    { source: "oral_express", target: "oral_discuss", type: "prerequisite", strength: 0.7 },
    { source: "vocabulary_core", target: "grammar_basic", type: "prerequisite", strength: 0.8 },
    { source: "vocabulary_core", target: "reading_comp", type: "prerequisite", strength: 0.8 },
    { source: "grammar_basic", target: "grammar_complex", type: "prerequisite", strength: 0.8 },
    { source: "reading_comp", target: "reading_cloze", type: "prerequisite", strength: 0.7 },
    { source: "reading_comp", target: "reading_7c", type: "followup", strength: 0.6 },
    { source: "grammar_basic", target: "writing_basic", type: "prerequisite", strength: 0.7 },
    { source: "writing_basic", target: "writing_essay", type: "prerequisite", strength: 0.8 },
    { source: "writing_essay", target: "writing_continue", type: "prerequisite", strength: 0.7 },
    { source: "listening_basic", target: "pronunciation", type: "parallel", strength: 0.5 },
    { source: "reading_comp", target: "writing_basic", type: "parallel", strength: 0.5 },
  ];

  return { subject: "英语", stage: "通用", totalNodes: nodes.length, clusters: ["听力", "口语", "阅读", "写作"], nodes, links };
}

/* ═══════════════════════════════════════════
   Science (科学) knowledge graph
   ═══════════════════════════════════════════ */
function sciencePrimary(): KnowledgeGraphData {
  const nodes: KnowledgeNode[] = [
    // 科学探究（集群名对齐报告知识点「科学探究」）
    { id: "observe_ask", name: "观察与提问", cluster: "科学探究", level: 1, ring: 1, mastery: mastery("observe_ask", 85), parentId: "c_inquiry", prerequisites: [], followups: ["make_hypothesis"], weight: 10, hours: 10, nodeType: "apply" },
    { id: "make_hypothesis", name: "作出假设", cluster: "科学探究", level: 1, ring: 1, mastery: mastery("make_hypothesis", 78), parentId: "c_inquiry", prerequisites: ["observe_ask"], followups: ["collect_evidence"], weight: 8, hours: 8, nodeType: "apply" },
    { id: "collect_evidence", name: "收集证据", cluster: "科学探究", level: 1, ring: 2, mastery: mastery("collect_evidence", 72), parentId: "c_inquiry", prerequisites: ["make_hypothesis"], followups: ["draw_conclusion"], weight: 10, hours: 12, nodeType: "apply" },
    { id: "draw_conclusion", name: "得出结论", cluster: "科学探究", level: 1, ring: 2, mastery: mastery("draw_conclusion", 68), parentId: "c_inquiry", prerequisites: ["collect_evidence"], followups: ["experiment_design"], weight: 8, hours: 8, nodeType: "apply" },
    // 生命科学（对齐「生命科学」）
    { id: "plant_world", name: "植物世界", cluster: "生命科学", level: 1, ring: 1, mastery: mastery("plant_world", 82), parentId: "c_life", prerequisites: [], followups: ["animal_world"], weight: 10, hours: 12, nodeType: "memorize" },
    { id: "animal_world", name: "动物世界", cluster: "生命科学", level: 1, ring: 1, mastery: mastery("animal_world", 78), parentId: "c_life", prerequisites: ["plant_world"], followups: ["human_body"], weight: 10, hours: 12, nodeType: "memorize" },
    { id: "human_body", name: "人体奥秘", cluster: "生命科学", level: 1, ring: 2, mastery: mastery("human_body", 70), parentId: "c_life", prerequisites: ["animal_world"], followups: [], weight: 8, hours: 8, nodeType: "reading" },
    // 物质科学（对齐「物质科学」）
    { id: "matter_feature", name: "物体的特征", cluster: "物质科学", level: 1, ring: 1, mastery: mastery("matter_feature", 84), parentId: "c_matter", prerequisites: [], followups: ["material_explore"], weight: 10, hours: 10, nodeType: "memorize" },
    { id: "material_explore", name: "材料探秘", cluster: "物质科学", level: 1, ring: 2, mastery: mastery("material_explore", 74), parentId: "c_matter", prerequisites: ["matter_feature"], followups: ["water_air"], weight: 8, hours: 10, nodeType: "apply" },
    { id: "water_air", name: "水与空气", cluster: "物质科学", level: 1, ring: 2, mastery: mastery("water_air", 70), parentId: "c_matter", prerequisites: ["material_explore"], followups: ["weather_climate"], weight: 8, hours: 8, nodeType: "apply" },
    // 地球与宇宙（对齐「地球与宇宙」）
    { id: "weather_climate", name: "天气与气候", cluster: "地球与宇宙", level: 1, ring: 1, mastery: mastery("weather_climate", 78), parentId: "c_earth", prerequisites: ["water_air"], followups: ["season_change"], weight: 8, hours: 10, nodeType: "reading" },
    { id: "season_change", name: "四季更替", cluster: "地球与宇宙", level: 1, ring: 2, mastery: mastery("season_change", 72), parentId: "c_earth", prerequisites: ["weather_climate"], followups: ["sun_moon"], weight: 8, hours: 8, nodeType: "reading" },
    { id: "sun_moon", name: "太阳与月球", cluster: "地球与宇宙", level: 1, ring: 3, mastery: mastery("sun_moon", 66), parentId: "c_earth", prerequisites: ["season_change"], followups: [], weight: 6, hours: 6, nodeType: "reading" },
    // 科学实验（节点直接命名为报告知识点「实验设计/现象解释/科学概念」，精确命中 100 分）
    { id: "experiment_design", name: "实验设计", cluster: "科学实验", level: 1, ring: 2, mastery: mastery("experiment_design", 76), parentId: "c_lab", prerequisites: ["draw_conclusion"], followups: ["phenomenon_explain"], weight: 10, hours: 12, nodeType: "experiment" },
    { id: "phenomenon_explain", name: "现象解释", cluster: "科学实验", level: 1, ring: 2, mastery: mastery("phenomenon_explain", 70), parentId: "c_lab", prerequisites: ["experiment_design"], followups: ["science_concept"], weight: 8, hours: 10, nodeType: "apply" },
    { id: "science_concept", name: "科学概念", cluster: "科学实验", level: 1, ring: 3, mastery: mastery("science_concept", 64), parentId: "c_lab", prerequisites: ["phenomenon_explain"], followups: [], weight: 8, hours: 8, nodeType: "memorize" },
  ];
  const links: KnowledgeLink[] = [
    { source: "observe_ask", target: "make_hypothesis", type: "prerequisite", strength: 0.9 },
    { source: "make_hypothesis", target: "collect_evidence", type: "prerequisite", strength: 0.8 },
    { source: "collect_evidence", target: "draw_conclusion", type: "prerequisite", strength: 0.8 },
    { source: "draw_conclusion", target: "experiment_design", type: "prerequisite", strength: 0.8 },
    { source: "experiment_design", target: "phenomenon_explain", type: "prerequisite", strength: 0.8 },
    { source: "phenomenon_explain", target: "science_concept", type: "prerequisite", strength: 0.8 },
    { source: "plant_world", target: "animal_world", type: "prerequisite", strength: 0.8 },
    { source: "animal_world", target: "human_body", type: "prerequisite", strength: 0.7 },
    { source: "matter_feature", target: "material_explore", type: "prerequisite", strength: 0.8 },
    { source: "material_explore", target: "water_air", type: "prerequisite", strength: 0.7 },
    { source: "water_air", target: "weather_climate", type: "prerequisite", strength: 0.6 },
    { source: "weather_climate", target: "season_change", type: "prerequisite", strength: 0.7 },
    { source: "season_change", target: "sun_moon", type: "prerequisite", strength: 0.6 },
    { source: "observe_ask", target: "plant_world", type: "parallel", strength: 0.5 },
    { source: "collect_evidence", target: "phenomenon_explain", type: "parallel", strength: 0.5 },
    { source: "matter_feature", target: "experiment_design", type: "parallel", strength: 0.4 },
  ];
  return { subject: "科学", stage: "小学", totalNodes: nodes.length, clusters: ["科学探究", "生命科学", "物质科学", "地球与宇宙", "科学实验"], nodes, links };
}

/* ═══════════════════════════════════════════
   Generic science (physics/chemistry/biology)
   ═══════════════════════════════════════════ */

function physicsGraph(): KnowledgeGraphData {
  const n = (id: string, name: string, cluster: string, ring: 1|2|3, base: number, pre: string[], fol: string[]): KnowledgeNode =>
    ({ id, name, cluster, level: 1, ring, mastery: mastery(id, base), prerequisites: pre, followups: fol, weight: 10, hours: 8, nodeType: "experiment" });

  const nodes = [
    n("mechanics_basic", "力学基础", "力学", 1, 75, [], ["newton"]),
    n("newton", "牛顿运动定律", "力学", 2, 68, ["mechanics_basic"], ["energy"]),
    n("energy", "功和能量", "力学", 2, 62, ["newton"], ["momentum"]),
    n("momentum", "动量", "力学", 3, 52, ["energy"], []),
    n("kinematics", "运动学", "力学", 1, 78, [], ["newton"]),
    n("electrostatics", "静电学", "电磁", 1, 70, [], ["circuits"]),
    n("circuits", "电路", "电磁", 2, 65, ["electrostatics"], ["magnetism"]),
    n("magnetism", "磁场", "电磁", 2, 58, ["circuits"], ["em_induction"]),
    n("em_induction", "电磁感应", "电磁", 3, 48, ["magnetism"], []),
    n("waves", "机械波", "波动与光", 2, 60, ["mechanics_basic"], ["optics"]),
    n("optics", "光学", "波动与光", 2, 65, ["waves"], []),
    n("thermo", "热学", "热学", 2, 68, [], []),
  ];

  const links: KnowledgeLink[] = [
    { source: "kinematics", target: "newton", type: "prerequisite", strength: 0.9 },
    { source: "mechanics_basic", target: "newton", type: "prerequisite", strength: 0.9 },
    { source: "newton", target: "energy", type: "prerequisite", strength: 0.8 },
    { source: "energy", target: "momentum", type: "prerequisite", strength: 0.8 },
    { source: "electrostatics", target: "circuits", type: "prerequisite", strength: 0.8 },
    { source: "circuits", target: "magnetism", type: "prerequisite", strength: 0.7 },
    { source: "magnetism", target: "em_induction", type: "prerequisite", strength: 0.8 },
    { source: "mechanics_basic", target: "waves", type: "prerequisite", strength: 0.6 },
    { source: "waves", target: "optics", type: "followup", strength: 0.6 },
  ];

  return { subject: "物理", stage: "通用", totalNodes: nodes.length, clusters: ["力学", "电磁", "波动与光", "热学"], nodes, links };
}

function chemistryGraph(): KnowledgeGraphData {
  const n = (id: string, name: string, cluster: string, ring: 1|2|3, base: number, pre: string[], fol: string[]): KnowledgeNode =>
    ({ id, name, cluster, level: 1, ring, mastery: mastery(id, base), prerequisites: pre, followups: fol, weight: 10, hours: 8, nodeType: "experiment" });

  const nodes = [
    n("atom_structure", "原子结构", "物质结构", 1, 78, [], ["periodic_table"]),
    n("periodic_table", "元素周期表", "物质结构", 1, 75, ["atom_structure"], ["chemical_bond"]),
    n("chemical_bond", "化学键", "物质结构", 2, 65, ["periodic_table"], []),
    n("mole", "物质的量", "化学计量", 1, 70, [], ["stoichiometry"]),
    n("stoichiometry", "化学计量", "化学计量", 2, 60, ["mole"], []),
    n("acid_base", "酸碱盐", "化学反应", 1, 72, [], ["ion_reaction"]),
    n("ion_reaction", "离子反应", "化学反应", 2, 62, ["acid_base"], ["redox"]),
    n("redox", "氧化还原", "化学反应", 2, 58, ["ion_reaction"], ["electrochem"]),
    n("electrochem", "电化学", "化学反应", 3, 48, ["redox"], []),
    n("organic_basic", "有机基础", "有机化学", 2, 55, [], ["organic_reaction"]),
    n("organic_reaction", "有机反应", "有机化学", 3, 45, ["organic_basic"], []),
  ];

  const links: KnowledgeLink[] = [
    { source: "atom_structure", target: "periodic_table", type: "prerequisite", strength: 0.9 },
    { source: "periodic_table", target: "chemical_bond", type: "prerequisite", strength: 0.8 },
    { source: "mole", target: "stoichiometry", type: "prerequisite", strength: 0.9 },
    { source: "acid_base", target: "ion_reaction", type: "prerequisite", strength: 0.8 },
    { source: "ion_reaction", target: "redox", type: "prerequisite", strength: 0.8 },
    { source: "redox", target: "electrochem", type: "prerequisite", strength: 0.8 },
    { source: "organic_basic", target: "organic_reaction", type: "prerequisite", strength: 0.8 },
  ];

  return { subject: "化学", stage: "通用", totalNodes: nodes.length, clusters: ["物质结构", "化学计量", "化学反应", "有机化学"], nodes, links };
}

/* ═══════════════════════════════════════════
   Fallback generic graph
   ═══════════════════════════════════════════ */
function genericGraph(subject: string): KnowledgeGraphData {
  const n = (id: string, name: string, cluster: string, ring: 1|2|3, base: number): KnowledgeNode =>
    ({ id, name, cluster, level: 1, ring, mastery: mastery(id + subject, base), prerequisites: [], followups: [], weight: 10, hours: 8, nodeType: "apply" });

  const nodes = [
    n("basics", "基础知识", "基础", 1, 78),
    n("core_a", "核心模块A", "核心", 2, 65),
    n("core_b", "核心模块B", "核心", 2, 60),
    n("core_c", "核心模块C", "核心", 2, 55),
    n("advanced_a", "拓展模块A", "拓展", 3, 48),
    n("advanced_b", "拓展模块B", "拓展", 3, 42),
  ];

  nodes[1].prerequisites = ["basics"];
  nodes[2].prerequisites = ["basics"];
  nodes[3].prerequisites = ["basics"];
  nodes[4].prerequisites = ["core_a"];
  nodes[5].prerequisites = ["core_b"];

  const links: KnowledgeLink[] = [
    { source: "basics", target: "core_a", type: "prerequisite", strength: 0.8 },
    { source: "basics", target: "core_b", type: "prerequisite", strength: 0.7 },
    { source: "basics", target: "core_c", type: "prerequisite", strength: 0.7 },
    { source: "core_a", target: "advanced_a", type: "prerequisite", strength: 0.7 },
    { source: "core_b", target: "advanced_b", type: "prerequisite", strength: 0.6 },
    { source: "core_a", target: "core_b", type: "parallel", strength: 0.4 },
  ];

  return { subject, stage: "通用", totalNodes: nodes.length, clusters: ["基础", "核心", "拓展"], nodes, links };
}

/* ═══════════════════════════════════════════
   Main resolver
   ═══════════════════════════════════════════ */
export function getKnowledgeGraph(schoolLevel: string, subject: string): KnowledgeGraphData {
  const isPrimary = schoolLevel === "primary";
  const isSenior = schoolLevel === "senior";

  if (subject === "语文") return isPrimary ? chinesePrimary() : chineseSenior();
  if (subject === "数学") return isPrimary ? mathPrimary() : mathSenior();
  if (subject === "英语" || subject === "外语") return englishGraph();
  if (subject === "科学") return sciencePrimary();
  if (subject === "物理") return physicsGraph();
  if (subject === "化学") return chemistryGraph();
  return genericGraph(subject);
}

/* ── Build tree structure from flat nodes ── */
export interface TreeNode {
  id: string;
  name: string;
  mastery: number;
  children: TreeNode[];
  isCluster: boolean;
}

export function buildTree(data: KnowledgeGraphData): TreeNode[] {
  const clusters = data.clusters.map(c => ({
    id: `cluster_${c}`,
    name: c,
    mastery: 0,
    children: [] as TreeNode[],
    isCluster: true,
  }));

  const clusterMap = new Map(clusters.map(c => [c.name, c]));

  for (const node of data.nodes) {
    const parent = clusterMap.get(node.cluster);
    if (parent) {
      parent.children.push({
        id: node.id,
        name: node.name,
        mastery: node.mastery,
        children: [],
        isCluster: false,
      });
    }
  }

  // Compute cluster average mastery
  for (const cluster of clusters) {
    if (cluster.children.length > 0) {
      cluster.mastery = Math.round(
        cluster.children.reduce((s, c) => s + c.mastery, 0) / cluster.children.length
      );
    }
  }

  return clusters;
}
