import type { TranslationDict } from "../../types";

/** 智能生成·AI备课 中文翻译 */
export const smartGenZh: TranslationDict = {
  /* ── 头部（SmartGenHeader） ── */
  "smartGen.header.title": "智能生成",
  "smartGen.header.subtitle":
    "选择生成类型，填写教学需求，一键生成课件、学案或多媒体资源",
  "smartGen.header.classBadge": "初一(3)班语文",

  /* ── 生成类型（smartGenData.GEN_TYPE_OPTIONS） ── */
  "smartGen.genType.courseware": "互动课件",
  "smartGen.genType.worksheet": "探究学案",
  "smartGen.genType.multimedia": "视频推荐",

  /* ── 需求输入（RequirementInput） ── */
  "smartGen.requirement.title": "教学需求",
  "smartGen.requirement.labelContent": "教学内容",
  "smartGen.requirement.labelObjective": "教学目标",
  "smartGen.requirement.labelStudentProfile": "学生特点",
  "smartGen.requirement.labelRequirements": "特殊要求",
  "smartGen.requirement.analyze": "AI分析需求，推荐工具组合",
  "smartGen.requirement.recommendedCombo":
    "推荐组合：古诗文网 + ProcessOn + 剪映",
  "smartGen.requirement.featurePrefix": "功能：",
  "smartGen.requirement.outputPrefix": "生成：",
  "smartGen.requirement.integrationPlan": "AI整合计划",
  "smartGen.requirement.plan.structure":
    "结构：视频导入(2min) → 文本精读(8min) → 导图探究(10min)",
  "smartGen.requirement.plan.interaction": "互动：3处停顿讨论，1处协作填图",
  "smartGen.requirement.plan.homework":
    "作业：分层人物小传（A拓展/B标准/C基础）",
  "smartGen.requirement.aiGenerating": "AI生成中...",
  "smartGen.requirement.generate": "立即生成",
  "smartGen.requirement.useComboGenerate": "使用此组合生成",
  "smartGen.requirement.changeRecommendation": "换一组推荐",
  "smartGen.requirement.customizeTools": "自定义工具",
  "smartGen.requirement.otherOptions": "其他可选：",

  /* 推荐组合·3 个工具 */
  "smartGen.requirement.combo.name.0": "古诗文网",
  "smartGen.requirement.combo.name.1": "ProcessOn",
  "smartGen.requirement.combo.name.2": "剪映/必剪",
  "smartGen.requirement.combo.role.0": "文本基础",
  "smartGen.requirement.combo.role.1": "思维可视化",
  "smartGen.requirement.combo.role.2": "视频创作",
  "smartGen.requirement.combo.desc.0": "原文+朗读+注释+赏析",
  "smartGen.requirement.combo.desc.1": "动态思维导图，协作填空",
  "smartGen.requirement.combo.desc.2": "图文转视频，配音配乐",
  "smartGen.requirement.combo.output.0": "嵌入式文本页面，可点击查注释",
  "smartGen.requirement.combo.output.1": "可交互导图模板，课堂实时填充",
  "smartGen.requirement.combo.output.2": "视频脚本+配图建议+配音文案",

  /* 其他可选工具（EXTRA_TOOLS） */
  "smartGen.requirement.extra.0": "📹 央视纪录片",
  "smartGen.requirement.extra.1": "🎨 山海经图谱",
  "smartGen.requirement.extra.2": "📝 腾讯文档协作",
  "smartGen.requirement.extra.3": "🎤 配音工具",

  /* ── 需求输入占位 + 生成/重新生成提示（本批新增） ── */
  "smartGen.requirement.placeholderContent":
    "请输入教学内容，如：《阿长与山海经》第2课时",
  "smartGen.requirement.placeholderObjective":
    "请输入教学目标，如：分析人物形象",
  "smartGen.requirement.placeholderStudentProfile":
    "请输入学生特点，如：古文基础薄弱",
  "smartGen.requirement.placeholderRequirements":
    "请输入特殊要求，如：增加互动环节",
  "smartGen.generate.success": "教学方案生成完成！",
  "smartGen.generate.cancelled": "已取消生成",
  "smartGen.generate.rateLimited": "请求过于频繁",
  "smartGen.generate.quotaExhausted": "额度不足",
  "smartGen.generate.failed": "生成失败",
  "smartGen.generate.processError": "生成过程出错",
  "smartGen.generate.serviceError": "AI服务异常",
  "smartGen.regenerate.needGenerateFirst": "请先完成一次生成后再重新生成",

  /* ── AI 整合面板（AIIntegrationPanel） ── */
  "smartGen.aiIntegration.title": "AI优化整合",
  "smartGen.aiIntegration.generating": "正在生成...",
  "smartGen.aiIntegration.complete": "生成完成",
  "smartGen.aiIntegration.generateFullPlan": "生成完整教学方案",
  "smartGen.aiIntegration.progressGenerating": "AI正在生成教学方案...",
  "smartGen.aiIntegration.progressComplete": "✅ 生成完成",
  "smartGen.aiIntegration.progressWaiting": "等待生成",
  "smartGen.aiIntegration.stopGenerating": "停止生成",
  "smartGen.aiIntegration.streaming": "生成中...",
  "smartGen.aiIntegration.aiWill": "AI将为您：",
  "smartGen.aiIntegration.coursewareStructure":
    "预期课件结构：共18页，预计45分钟",
  "smartGen.aiIntegration.aiSuggestions": "AI优化建议",
  "smartGen.aiIntegration.suggestion1":
    "• 班级“情感把握”薄弱，建议增加1处情感分析讨论",
  "smartGen.aiIntegration.suggestion2":
    "• 建议增加《山海经》图片展示，增强直观感受",
  "smartGen.aiIntegration.acceptSuggestions": "接受建议并调整",
  "smartGen.aiIntegration.ignoreSuggestions": "忽略建议",
  "smartGen.aiIntegration.confirmFinal": "确认生成最终课件",
  "smartGen.aiIntegration.toast.confirmFinal": "已确认最终归属",
  "smartGen.aiIntegration.toast.suggestionsAccepted": "建议已采纳",
  "smartGen.aiIntegration.toast.suggestionsIgnored": "已忽略建议",
  "smartGen.aiIntegration.exporting": "导出中...",
  "smartGen.aiIntegration.exportPdf": "导出PDF",
  "smartGen.aiIntegration.preview": "预览",
  "smartGen.aiIntegration.previewPdf": "预览 PDF",
  "smartGen.aiIntegration.downloadPdf": "下载 PDF",
  "smartGen.aiIntegration.pdfPreviewTitle": "PDF 预览",
  "smartGen.aiIntegration.saveDraft": "保存草稿",
  "smartGen.aiIntegration.regenerate": "重新整合",
  "smartGen.aiIntegration.outputOptions": "生成选项：",
  "smartGen.aiIntegration.outputCoursewareOnly": "仅生成课件（PPT格式）",
  "smartGen.aiIntegration.outputFullPackage":
    "生成课件+学生学案+教师教案（完整包）",
  "smartGen.aiIntegration.outputH5": "生成课件+互动H5（学生可在线操作导图）",
  "smartGen.aiIntegration.pdfExportSuccess": "PDF导出成功！",
  "smartGen.aiIntegration.pdfExportFailed": "PDF导出失败",
  "smartGen.aiIntegration.pdfFileBase": "AI教学方案",
  "smartGen.aiIntegration.unnamed": "未命名课件",
  "smartGen.aiIntegration.downloadPptx": "下载 PPT",
  "smartGen.aiIntegration.generatingPptx": "生成 PPT 中...",
  "smartGen.aiIntegration.pptxSuccess": "PPT 已生成并下载",
  "smartGen.aiIntegration.pptxFailed": "PPT 生成失败",

  /* INTEGRATION_STEPS 5 步 */
  "smartGen.aiIntegration.step.0": "提取各工具核心内容",
  "smartGen.aiIntegration.step.1": "设计课堂流程（导入→探究→总结）",
  "smartGen.aiIntegration.step.2": "匹配互动环节（3处讨论+1处协作）",
  "smartGen.aiIntegration.step.3": "生成分层作业（基于班级学情）",
  "smartGen.aiIntegration.step.4": "优化过渡语（工具间衔接）",

  /* COURSEWARE_PREVIEW 4 区块 */
  "smartGen.aiIntegration.section.0.pages": "第1-2页",
  "smartGen.aiIntegration.section.0.source": "剪映生成",
  "smartGen.aiIntegration.section.0.content": "“1分钟看懂阿长与山海经的故事”",
  "smartGen.aiIntegration.section.0.interaction":
    "暂停讨论：你印象最深的细节？",
  "smartGen.aiIntegration.section.1.pages": "第3-10页",
  "smartGen.aiIntegration.section.1.source": "古诗文网嵌入",
  "smartGen.aiIntegration.section.1.content":
    "分段展示，点击查注释，听名家朗读",
  "smartGen.aiIntegration.section.1.interaction":
    "暂停讨论：阿长做了哪些“好事”？",
  "smartGen.aiIntegration.section.2.pages": "第11-15页",
  "smartGen.aiIntegration.section.2.source": "ProcessOn互动",
  "smartGen.aiIntegration.section.2.content": "分组填写“我-阿长-情感”关系图",
  "smartGen.aiIntegration.section.2.interaction": "实时投屏展示小组成果",
  "smartGen.aiIntegration.section.3.pages": "第16-18页",
  "smartGen.aiIntegration.section.3.source": "AI生成分层",
  "smartGen.aiIntegration.section.3.content": "情感变化曲线总结",
  "smartGen.aiIntegration.section.3.interaction":
    "A层：人物评传  B层：读后感  C层：摘抄+感想",

  /* ── 工具预览（ToolPreviewPanel） ── */
  "smartGen.toolPreview.title": "工具生成内容预览 · 3个工具协同",
  "smartGen.toolPreview.statusDone": "已获取",
  "smartGen.toolPreview.statusGenerating": "生成中",
  "smartGen.toolPreview.regenerate": "重新生成",
  "smartGen.toolPreview.addMore": "添加更多工具",

  /* TOOL_PREVIEWS 3 项 */
  "smartGen.toolPreview.item.0.tool": "古诗文网内容",
  "smartGen.toolPreview.item.0.summary": "已获取：《阿长与山海经》全文+朗读",
  "smartGen.toolPreview.item.0.detail.0": "段落划分：5段",
  "smartGen.toolPreview.item.0.detail.1": "重点注释：12处",
  "smartGen.toolPreview.item.0.detail.2": "赏析：3段",
  "smartGen.toolPreview.item.0.action.0": "预览文本",
  "smartGen.toolPreview.item.0.action.1": "调整段落",
  "smartGen.toolPreview.item.0.action.2": "选择朗读版本",
  "smartGen.toolPreview.item.1.tool": "ProcessOn思维导图",
  "smartGen.toolPreview.item.1.summary": "生成中：人物关系图模板...",
  "smartGen.toolPreview.item.1.detail.0":
    "预计：中心“我” → 分支“阿长/情感/事件”",
  "smartGen.toolPreview.item.1.detail.1": "交互点：3处学生填空",
  "smartGen.toolPreview.item.1.action.0": "查看进度",
  "smartGen.toolPreview.item.1.action.1": "调整结构",
  "smartGen.toolPreview.item.1.action.2": "更换模板",
  "smartGen.toolPreview.item.2.tool": "剪映视频脚本",
  "smartGen.toolPreview.item.2.summary": "已生成：1分钟导入视频脚本",
  "smartGen.toolPreview.item.2.detail.0": "场景1：鲁迅书房（图片）+ 旁白",
  "smartGen.toolPreview.item.2.detail.1": "场景2：阿长买书记（动画）+ 情感渲染",
  "smartGen.toolPreview.item.2.detail.2": "配乐：怀旧钢琴曲",
  "smartGen.toolPreview.item.2.action.0": "预览脚本",
  "smartGen.toolPreview.item.2.action.1": "调整时长",
  "smartGen.toolPreview.item.2.action.2": "更换风格",

  /* ── 生成历史（GenerationHistory） ── */
  "smartGen.history.title": "生成历史",
  "smartGen.history.empty": "暂无生成历史",
  "smartGen.history.statusUsed": "✅ 已使用",
  "smartGen.history.statusDraft": "⏳ 待完善",
  "smartGen.history.toolsPrefix": "工具：",
  "smartGen.history.durationPrefix": "生成时间：",
  "smartGen.history.action.view": "查看",
  "smartGen.history.action.edit": "再次编辑",
  "smartGen.history.action.share": "分享模板",
  "smartGen.history.usageStats": "工具使用统计：",
  "smartGen.history.usageStat": "{name}：{count}次",
  "smartGen.history.viewAll": "查看全部历史",
  "smartGen.history.exportReport": "导出使用报告",
  "smartGen.history.loading": "加载中...",
  "smartGen.history.loadFailed": "历史记录加载失败",
  "smartGen.history.loaded": "已回填到预览",
  "smartGen.history.clickToLoad": "点击任意一条，可回填到下方预览重新导出",

  /* GENERATION_HISTORY 4 项 */
  "smartGen.history.item.0.time": "今天 09:30",
  "smartGen.history.item.0.title": "《阿长与山海经》课件",
  "smartGen.history.item.0.tools": "古诗文网+ProcessOn+剪映",
  "smartGen.history.item.0.duration": "3分钟",
  "smartGen.history.item.1.time": "昨天 14:20",
  "smartGen.history.item.1.title": "第三单元测试卷",
  "smartGen.history.item.1.tools": "系统题库（未调用外部工具）",
  "smartGen.history.item.1.duration": "2分钟",
  "smartGen.history.item.2.time": "昨天 10:15",
  "smartGen.history.item.2.title": "《老王》互动学案",
  "smartGen.history.item.2.tools": "腾讯文档+ProcessOn",
  "smartGen.history.item.2.duration": "4分钟",
  "smartGen.history.item.3.time": "周一 16:00",
  "smartGen.history.item.3.title": "古诗文朗读合集",
  "smartGen.history.item.3.tools": "古诗文网+西窗烛",
  "smartGen.history.item.3.duration": "5分钟",

  /* TOOL_USAGE_STATS 5 项 */
  "smartGen.history.usage.0": "古诗文网",
  "smartGen.history.usage.1": "ProcessOn",
  "smartGen.history.usage.2": "剪映",
  "smartGen.history.usage.3": "央视纪录片",
  "smartGen.history.usage.4": "其他",

  /* ── 开源工具库（SceneToolLibrary） ── */
  "smartGen.toolLibrary.title": "开源工具库 · 语文场景专用",
  "smartGen.toolLibrary.viewAll": "查看全部工具",
  "smartGen.toolLibrary.applyAccess": "申请接入",
  "smartGen.toolLibrary.submitFeedback": "提交反馈",
  "smartGen.toolLibrary.rankings": "工具效果排行：",
  "smartGen.toolLibrary.usage": "使用率{usage}",
  "smartGen.toolLibrary.rank.0.name": "古诗文网",
  "smartGen.toolLibrary.rank.1.name": "ProcessOn",
  "smartGen.toolLibrary.rank.2.name": "剪映",

  /* SCENE_TOOLS 5 场景 */
  "smartGen.toolLibrary.scene.0": "文本精读",
  "smartGen.toolLibrary.scene.0.tool.0.name": "古诗文网",
  "smartGen.toolLibrary.scene.0.tool.0.desc": "全文+朗读+注释",
  "smartGen.toolLibrary.scene.0.tool.1.name": "汉典",
  "smartGen.toolLibrary.scene.0.tool.1.desc": "字词详解",
  "smartGen.toolLibrary.scene.0.tool.2.name": "国学大师",
  "smartGen.toolLibrary.scene.0.tool.2.desc": "古籍检索",
  "smartGen.toolLibrary.scene.1": "思维可视化",
  "smartGen.toolLibrary.scene.1.tool.0.name": "ProcessOn",
  "smartGen.toolLibrary.scene.1.tool.0.desc": "思维导图/流程图",
  "smartGen.toolLibrary.scene.1.tool.1.name": "XMind",
  "smartGen.toolLibrary.scene.1.tool.1.desc": "脑图工具",
  "smartGen.toolLibrary.scene.1.tool.2.name": "腾讯文档",
  "smartGen.toolLibrary.scene.1.tool.2.desc": "协作表格",
  "smartGen.toolLibrary.scene.2": "音视频创作",
  "smartGen.toolLibrary.scene.2.tool.0.name": "剪映/必剪",
  "smartGen.toolLibrary.scene.2.tool.0.desc": "短视频制作",
  "smartGen.toolLibrary.scene.2.tool.1.name": "西窗烛",
  "smartGen.toolLibrary.scene.2.tool.1.desc": "诗词朗读+意境",
  "smartGen.toolLibrary.scene.2.tool.2.name": "央视纪录片",
  "smartGen.toolLibrary.scene.2.tool.2.desc": "背景视频",
  "smartGen.toolLibrary.scene.3": "互动探究",
  "smartGen.toolLibrary.scene.3.tool.0.name": "腾讯文档",
  "smartGen.toolLibrary.scene.3.tool.0.desc": "协作批注",
  "smartGen.toolLibrary.scene.3.tool.1.name": "秀米/135",
  "smartGen.toolLibrary.scene.3.tool.1.desc": "图文排版",
  "smartGen.toolLibrary.scene.3.tool.2.name": "问卷星",
  "smartGen.toolLibrary.scene.3.tool.2.desc": "课堂检测",
  "smartGen.toolLibrary.scene.4": "图文展示",
  "smartGen.toolLibrary.scene.4.tool.0.name": "中华典藏",
  "smartGen.toolLibrary.scene.4.tool.0.desc": "古籍图谱",
  "smartGen.toolLibrary.scene.4.tool.1.name": "Canva",
  "smartGen.toolLibrary.scene.4.tool.1.desc": "海报/图文设计",
  "smartGen.toolLibrary.scene.4.tool.2.name": "微信读书",
  "smartGen.toolLibrary.scene.4.tool.2.desc": "电子书嵌入",

  /* ── 每日提示（SmartGenDailyTips） ── */
  "smartGen.tips.firstUse": "💡 输入课时，AI推荐工具",
  "smartGen.tips.studentProfile": "📊 古文薄弱52%，建议增加互动",
  "smartGen.tips.newCombo": "🆕 新组合：纪录片+图谱+协作",
  "smartGen.tips.genComplete": "✓ 课件已生成，用时3分钟",
  "smartGen.tips.toolRecommend": "📈 剪映仅用2次，尝试视频",
  "smartGen.tips.topRated": "⭐ 古诗文网95%，评价高",
  "smartGen.tips.pendingWork": "⏳ 《老王》学案待完善",

  /* ── 引导（SmartGenTour） ── */
  "smartGen.tour.step0.title": "三种生成类型",
  "smartGen.tour.step0.desc": "三种生成类型，AI+工具协同创作",
  "smartGen.tour.step1.title": "需求输入区",
  "smartGen.tour.step1.desc": "输入教学需求，AI据此分析推荐",
  "smartGen.tour.step2.title": "AI分析按钮",
  "smartGen.tour.step2.desc": "点击分析，智能匹配最佳工具组合",
  "smartGen.tour.step3.title": "推荐组合区",
  "smartGen.tour.step3.desc": "推荐工具组合，含功能和整合计划",
  "smartGen.tour.step4.title": "使用组合生成",
  "smartGen.tour.step4.desc": "一键生成，或换推荐、自定义",
  "smartGen.tour.step5.title": "生成历史",
  "smartGen.tour.step5.desc": "本周15次调用，查看编辑分享",
  "smartGen.tour.step6.title": "开源工具库",
  "smartGen.tour.step6.desc": "语文场景专用，按场景分类",
  "smartGen.tour.step7.title": "工具效果排行",
  "smartGen.tour.step7.desc": "基于使用效果排序，古诗文网95%",
  "smartGen.tour.next": "下一步",
  "smartGen.tour.done": "完成",
  "smartGen.tour.completeTitle": "智能生成引导完成！",
  "smartGen.tour.completeDesc": "输入需求→AI推荐→工具组合→一键生成→分享复用",

  /* ── 分层组卷（A/B/C 各一份） ── */
  "smartGen.tiered.title": "按层出卷",
  "smartGen.tiered.subtitle": "按当前 A/B/C 分层各生成一份分层试卷",
  "smartGen.tiered.entry": "按层出卷",
  "smartGen.tiered.generate": "生成三份分层卷",
  "smartGen.tiered.generating": "正在按层出卷…",
  "smartGen.tiered.success": "已生成 A/B/C 三份分层卷",
  "smartGen.tiered.failed": "按层出卷失败",
  "smartGen.tiered.noTiers": "该班尚未完成分层，请先自动/手动分层",
  "smartGen.tiered.pickClass": "请先选择班级",
  "smartGen.tiered.pickSubject": "选择学科",
  "smartGen.tiered.empty": "暂无分层卷，点击上方按钮生成",
  "smartGen.tiered.loadFailed": "分层卷清单加载失败",
  "smartGen.tiered.paperCount": "{count} 题",
  "smartGen.tiered.difficulty": "易 {easy} / 中 {medium} / 难 {hard}",
  "smartGen.tiered.studentCount": "{count} 人",
  "smartGen.tiered.view": "查看",
  "smartGen.tiered.print": "打印",
  "smartGen.tiered.download": "下载",
  "smartGen.tiered.openInExamGen": "在组卷中打开",
  "smartGen.tiered.previewTitle": "分层卷预览",
  "smartGen.tiered.close": "关闭",
  "smartGen.tiered.batchLabel": "批次 {id}",
  "smartGen.tiered.strategy.A": "提高 / 综合 / 压轴权重高",
  "smartGen.tiered.strategy.B": "标准难度",
  "smartGen.tiered.strategy.C": "基础巩固 / 单一知识点",
  "smartGen.tiered.tierA": "A层",
  "smartGen.tiered.tierB": "B层",
  "smartGen.tiered.tierC": "C层",
  "smartGen.aiSource.label": "题源",
  "smartGen.aiSource.ai": "AI 生成",
  "smartGen.aiSource.bank": "题库",
  "smartGen.aiSource.bankUnavailable": "没有接入题库",
  "smartGen.aiSource.bankHint": "题库功能暂未开放，请选择「AI 生成」",
  "smartGen.aiSource.settings": "AI 出题设置",
  "smartGen.aiSource.topicsLabel": "知识点",
  "smartGen.aiSource.topicsPlaceholder": "可选，多个用顿号/逗号分隔；留空按薄弱点自动选",
  "smartGen.aiSource.typesLabel": "题型",
  "smartGen.aiSource.addType": "添加题型",
  "smartGen.aiSource.countLabel": "题",
  "smartGen.aiSource.scoreLabel": "分",
  "smartGen.aiSource.aiHint": "将按各层难度策略，用所选知识点与题型由 AI 生成",
  "smartGen.aiSource.regenerate": "重新生成",
  "smartGen.aiSource.apply": "应用",
};

/** 智能生成·AI备课 英文翻译 */
export const smartGenEn: TranslationDict = {
  /* ── Header (SmartGenHeader) ── */
  "smartGen.header.title": "Smart Generation",
  "smartGen.header.subtitle":
    "Pick a type, fill in your needs, and generate courseware, worksheets, or multimedia in one click",
  "smartGen.header.classBadge": "Year 7 (3) Chinese",

  /* ── Generation types (GEN_TYPE_OPTIONS) ── */
  "smartGen.genType.courseware": "Interactive Courseware",
  "smartGen.genType.worksheet": "Exploration Worksheet",
  "smartGen.genType.multimedia": "Video Recommendations",

  /* ── Requirement input (RequirementInput) ── */
  "smartGen.requirement.title": "Teaching Requirements",
  "smartGen.requirement.labelContent": "Teaching Content",
  "smartGen.requirement.labelObjective": "Teaching Objectives",
  "smartGen.requirement.labelStudentProfile": "Student Profile",
  "smartGen.requirement.labelRequirements": "Special Requirements",
  "smartGen.requirement.analyze":
    "AI analyzes requirements and recommends tool combos",
  "smartGen.requirement.recommendedCombo":
    "Recommended combo: Gushiwen + ProcessOn + JianYing",
  "smartGen.requirement.featurePrefix": "Features: ",
  "smartGen.requirement.outputPrefix": "Output: ",
  "smartGen.requirement.integrationPlan": "AI Integration Plan",
  "smartGen.requirement.plan.structure":
    "Structure: video intro (2min) → close reading (8min) → mind-map exploration (10min)",
  "smartGen.requirement.plan.interaction":
    "Interaction: 3 pause-for-discussion points, 1 collaborative fill-in",
  "smartGen.requirement.plan.homework":
    "Homework: tiered character profiles (A extended / B standard / C basic)",
  "smartGen.requirement.aiGenerating": "AI generating...",
  "smartGen.requirement.generate": "Generate",
  "smartGen.requirement.useComboGenerate": "Generate with this combo",
  "smartGen.requirement.changeRecommendation": "Change recommendations",
  "smartGen.requirement.customizeTools": "Customize tools",
  "smartGen.requirement.otherOptions": "Other options: ",

  /* Recommended combo · 3 tools */
  "smartGen.requirement.combo.name.0": "Gushiwen",
  "smartGen.requirement.combo.name.1": "ProcessOn",
  "smartGen.requirement.combo.name.2": "JianYing/Bijian",
  "smartGen.requirement.combo.role.0": "Text Foundation",
  "smartGen.requirement.combo.role.1": "Visual Thinking",
  "smartGen.requirement.combo.role.2": "Video Creation",
  "smartGen.requirement.combo.desc.0":
    "Original text + audio + annotations + appreciation",
  "smartGen.requirement.combo.desc.1":
    "Dynamic mind maps, collaborative fill-in",
  "smartGen.requirement.combo.desc.2":
    "Turn text/images into video with voiceover and music",
  "smartGen.requirement.combo.output.0":
    "Embedded text page, click to view annotations",
  "smartGen.requirement.combo.output.1":
    "Interactive mind map template, fill in real time in class",
  "smartGen.requirement.combo.output.2":
    "Video script + image suggestions + voiceover copy",

  /* Extra tools (EXTRA_TOOLS) */
  "smartGen.requirement.extra.0": "📹 CCTV Documentaries",
  "smartGen.requirement.extra.1": "🎨 Shan Hai Jing Atlas",
  "smartGen.requirement.extra.2": "📝 Tencent Docs Collaboration",
  "smartGen.requirement.extra.3": "🎤 Voiceover Tools",

  /* ── Requirement placeholders + generate/regenerate toasts (this batch) ── */
  "smartGen.requirement.placeholderContent":
    "Enter teaching content, e.g. 'A Chang and the Classic of Mountains and Seas', Lesson 2",
  "smartGen.requirement.placeholderObjective":
    "Enter teaching objectives, e.g. analyze character portrayal",
  "smartGen.requirement.placeholderStudentProfile":
    "Enter student profile, e.g. weak classical Chinese foundation",
  "smartGen.requirement.placeholderRequirements":
    "Enter special requirements, e.g. add interactive activities",
  "smartGen.generate.success": "Lesson plan generated!",
  "smartGen.generate.cancelled": "Generation cancelled",
  "smartGen.generate.rateLimited": "Too many requests",
  "smartGen.generate.quotaExhausted": "Insufficient quota",
  "smartGen.generate.failed": "Generation failed",
  "smartGen.generate.processError": "Error during generation",
  "smartGen.generate.serviceError": "AI service error",
  "smartGen.regenerate.needGenerateFirst":
    "Please generate once before regenerating",

  /* ── AI integration panel (AIIntegrationPanel) ── */
  "smartGen.aiIntegration.title": "AI Integration",
  "smartGen.aiIntegration.generating": "Generating...",
  "smartGen.aiIntegration.complete": "Generation Complete",
  "smartGen.aiIntegration.generateFullPlan": "Generate a full lesson plan",
  "smartGen.aiIntegration.progressGenerating":
    "AI is generating the lesson plan...",
  "smartGen.aiIntegration.progressComplete": "✅ Complete",
  "smartGen.aiIntegration.progressWaiting": "Waiting to generate",
  "smartGen.aiIntegration.stopGenerating": "Stop generating",
  "smartGen.aiIntegration.streaming": "Generating...",
  "smartGen.aiIntegration.aiWill": "AI will:",
  "smartGen.aiIntegration.coursewareStructure":
    "Expected courseware structure: 18 pages, ~45 minutes",
  "smartGen.aiIntegration.aiSuggestions": "AI Suggestions",
  "smartGen.aiIntegration.suggestion1":
    '• The class is weak on "grasping emotions" — consider adding one emotion-analysis discussion',
  "smartGen.aiIntegration.suggestion2":
    "• Consider adding images from the Classic of Mountains and Seas to enhance visual impact",
  "smartGen.aiIntegration.acceptSuggestions": "Accept & adjust",
  "smartGen.aiIntegration.ignoreSuggestions": "Ignore",
  "smartGen.aiIntegration.confirmFinal": "Confirm final courseware",
  "smartGen.aiIntegration.toast.confirmFinal": "Final assignment confirmed",
  "smartGen.aiIntegration.toast.suggestionsAccepted": "Suggestions accepted",
  "smartGen.aiIntegration.toast.suggestionsIgnored": "Suggestions ignored",
  "smartGen.aiIntegration.exporting": "Exporting...",
  "smartGen.aiIntegration.exportPdf": "Export PDF",
  "smartGen.aiIntegration.preview": "Preview",
  "smartGen.aiIntegration.previewPdf": "Preview PDF",
  "smartGen.aiIntegration.downloadPdf": "Download PDF",
  "smartGen.aiIntegration.pdfPreviewTitle": "PDF Preview",
  "smartGen.aiIntegration.saveDraft": "Save draft",
  "smartGen.aiIntegration.regenerate": "Re-integrate",
  "smartGen.aiIntegration.outputOptions": "Output options:",
  "smartGen.aiIntegration.outputCoursewareOnly": "Courseware only (PPT)",
  "smartGen.aiIntegration.outputFullPackage":
    "Courseware + student worksheet + teacher's plan (full package)",
  "smartGen.aiIntegration.outputH5":
    "Courseware + interactive H5 (students manipulate the map online)",
  "smartGen.aiIntegration.pdfExportSuccess": "PDF exported successfully!",
  "smartGen.aiIntegration.pdfExportFailed": "PDF export failed",
  "smartGen.aiIntegration.pdfFileBase": "AI Lesson Plan",
  "smartGen.aiIntegration.unnamed": "Untitled courseware",
  "smartGen.aiIntegration.downloadPptx": "Download PPT",
  "smartGen.aiIntegration.generatingPptx": "Generating PPT...",
  "smartGen.aiIntegration.pptxSuccess": "PPT generated and downloaded",
  "smartGen.aiIntegration.pptxFailed": "Failed to generate PPT",

  /* INTEGRATION_STEPS · 5 steps */
  "smartGen.aiIntegration.step.0": "Extract core content from each tool",
  "smartGen.aiIntegration.step.1":
    "Design the class flow (intro → explore → summarize)",
  "smartGen.aiIntegration.step.2":
    "Match interaction points (3 discussions + 1 collaboration)",
  "smartGen.aiIntegration.step.3":
    "Generate tiered homework (based on class profile)",
  "smartGen.aiIntegration.step.4": "Polish transitions between tools",

  /* COURSEWARE_PREVIEW · 4 sections */
  "smartGen.aiIntegration.section.0.pages": "Pages 1-2",
  "smartGen.aiIntegration.section.0.source": "JianYing",
  "smartGen.aiIntegration.section.0.content":
    '"Understand A Chang and the Classic of Mountains and Seas in 1 minute"',
  "smartGen.aiIntegration.section.0.interaction":
    "Pause & discuss: the detail that impressed you most?",
  "smartGen.aiIntegration.section.1.pages": "Pages 3-10",
  "smartGen.aiIntegration.section.1.source": "Gushiwen embed",
  "smartGen.aiIntegration.section.1.content":
    "Show section by section, click for annotations, listen to recitation",
  "smartGen.aiIntegration.section.1.interaction":
    'Pause & discuss: what "good deeds" did A Chang do?',
  "smartGen.aiIntegration.section.2.pages": "Pages 11-15",
  "smartGen.aiIntegration.section.2.source": "ProcessOn interactive",
  "smartGen.aiIntegration.section.2.content":
    'Groups fill in the "me-A Chang-emotion" relationship map',
  "smartGen.aiIntegration.section.2.interaction":
    "Screen-share group results in real time",
  "smartGen.aiIntegration.section.3.pages": "Pages 16-18",
  "smartGen.aiIntegration.section.3.source": "AI tiered content",
  "smartGen.aiIntegration.section.3.content": "Emotion arc summary",
  "smartGen.aiIntegration.section.3.interaction":
    "A: character biography  B: reading response  C: excerpts + reflections",

  /* ── Tool preview (ToolPreviewPanel) ── */
  "smartGen.toolPreview.title":
    "Tool Output Preview · 3 Tools Working Together",
  "smartGen.toolPreview.statusDone": "Ready",
  "smartGen.toolPreview.statusGenerating": "Generating",
  "smartGen.toolPreview.regenerate": "Regenerate",
  "smartGen.toolPreview.addMore": "Add more tools",

  /* TOOL_PREVIEWS · 3 items */
  "smartGen.toolPreview.item.0.tool": "Gushiwen Content",
  "smartGen.toolPreview.item.0.summary":
    'Ready: full text of "A Chang and the Classic of Mountains and Seas" + audio',
  "smartGen.toolPreview.item.0.detail.0": "5 paragraphs",
  "smartGen.toolPreview.item.0.detail.1": "12 key annotations",
  "smartGen.toolPreview.item.0.detail.2": "3 appreciation sections",
  "smartGen.toolPreview.item.0.action.0": "Preview text",
  "smartGen.toolPreview.item.0.action.1": "Adjust paragraphs",
  "smartGen.toolPreview.item.0.action.2": "Choose audio version",
  "smartGen.toolPreview.item.1.tool": "ProcessOn Mind Map",
  "smartGen.toolPreview.item.1.summary":
    "Generating: character relationship map template...",
  "smartGen.toolPreview.item.1.detail.0":
    'Plan: center "me" → branches "A Chang / emotions / events"',
  "smartGen.toolPreview.item.1.detail.1":
    "3 student fill-in interaction points",
  "smartGen.toolPreview.item.1.action.0": "View progress",
  "smartGen.toolPreview.item.1.action.1": "Adjust structure",
  "smartGen.toolPreview.item.1.action.2": "Change template",
  "smartGen.toolPreview.item.2.tool": "JianYing Video Script",
  "smartGen.toolPreview.item.2.summary":
    "Generated: 1-minute intro video script",
  "smartGen.toolPreview.item.2.detail.0":
    "Scene 1: Lu Xun's study (image) + narration",
  "smartGen.toolPreview.item.2.detail.1":
    "Scene 2: A Chang buys the book (animation) + emotional rendering",
  "smartGen.toolPreview.item.2.detail.2": "Music: nostalgic piano",
  "smartGen.toolPreview.item.2.action.0": "Preview script",
  "smartGen.toolPreview.item.2.action.1": "Adjust duration",
  "smartGen.toolPreview.item.2.action.2": "Change style",

  /* ── Generation history (GenerationHistory) ── */
  "smartGen.history.title": "Generation History",
  "smartGen.history.empty": "No generation history yet",
  "smartGen.history.statusUsed": "✅ Used",
  "smartGen.history.statusDraft": "⏳ Draft",
  "smartGen.history.toolsPrefix": "Tools: ",
  "smartGen.history.durationPrefix": "Duration: ",
  "smartGen.history.action.view": "View",
  "smartGen.history.action.edit": "Edit again",
  "smartGen.history.action.share": "Share template",
  "smartGen.history.usageStats": "Tool usage stats:",
  "smartGen.history.usageStat": "{name}: {count} times",
  "smartGen.history.viewAll": "View all history",
  "smartGen.history.exportReport": "Export usage report",
  "smartGen.history.loading": "Loading...",
  "smartGen.history.loadFailed": "Failed to load history",
  "smartGen.history.loaded": "Loaded into preview",
  "smartGen.history.clickToLoad": "Click an item to reload it into the preview",

  /* GENERATION_HISTORY · 4 items */
  "smartGen.history.item.0.time": "Today 09:30",
  "smartGen.history.item.0.title":
    '"A Chang and the Classic of Mountains and Seas" courseware',
  "smartGen.history.item.0.tools": "Gushiwen + ProcessOn + JianYing",
  "smartGen.history.item.0.duration": "3 min",
  "smartGen.history.item.1.time": "Yesterday 14:20",
  "smartGen.history.item.1.title": "Unit 3 test paper",
  "smartGen.history.item.1.tools": "System question bank (no external tools)",
  "smartGen.history.item.1.duration": "2 min",
  "smartGen.history.item.2.time": "Yesterday 10:15",
  "smartGen.history.item.2.title": '"Old Wang" interactive worksheet',
  "smartGen.history.item.2.tools": "Tencent Docs + ProcessOn",
  "smartGen.history.item.2.duration": "4 min",
  "smartGen.history.item.3.time": "Mon 16:00",
  "smartGen.history.item.3.title": "Classical poetry audio collection",
  "smartGen.history.item.3.tools": "Gushiwen + Xichuangzhu",
  "smartGen.history.item.3.duration": "5 min",

  /* TOOL_USAGE_STATS · 5 items */
  "smartGen.history.usage.0": "Gushiwen",
  "smartGen.history.usage.1": "ProcessOn",
  "smartGen.history.usage.2": "JianYing",
  "smartGen.history.usage.3": "CCTV Documentaries",
  "smartGen.history.usage.4": "Other",

  /* ── Open-source tool library (SceneToolLibrary) ── */
  "smartGen.toolLibrary.title":
    "Open-Source Tool Library · For Chinese Classes",
  "smartGen.toolLibrary.viewAll": "View all tools",
  "smartGen.toolLibrary.applyAccess": "Apply for access",
  "smartGen.toolLibrary.submitFeedback": "Submit feedback",
  "smartGen.toolLibrary.rankings": "Tool effectiveness ranking:",
  "smartGen.toolLibrary.usage": "usage {usage}",
  "smartGen.toolLibrary.rank.0.name": "Gushiwen",
  "smartGen.toolLibrary.rank.1.name": "ProcessOn",
  "smartGen.toolLibrary.rank.2.name": "JianYing",

  /* SCENE_TOOLS · 5 scenes */
  "smartGen.toolLibrary.scene.0": "Close Reading",
  "smartGen.toolLibrary.scene.0.tool.0.name": "Gushiwen",
  "smartGen.toolLibrary.scene.0.tool.0.desc": "Full text + audio + annotations",
  "smartGen.toolLibrary.scene.0.tool.1.name": "Handian",
  "smartGen.toolLibrary.scene.0.tool.1.desc": "Word explanations",
  "smartGen.toolLibrary.scene.0.tool.2.name": "Guoxue Master",
  "smartGen.toolLibrary.scene.0.tool.2.desc": "Classical text search",
  "smartGen.toolLibrary.scene.1": "Visual Thinking",
  "smartGen.toolLibrary.scene.1.tool.0.name": "ProcessOn",
  "smartGen.toolLibrary.scene.1.tool.0.desc": "Mind maps / flowcharts",
  "smartGen.toolLibrary.scene.1.tool.1.name": "XMind",
  "smartGen.toolLibrary.scene.1.tool.1.desc": "Mind-mapping tool",
  "smartGen.toolLibrary.scene.1.tool.2.name": "Tencent Docs",
  "smartGen.toolLibrary.scene.1.tool.2.desc": "Collaborative sheets",
  "smartGen.toolLibrary.scene.2": "Audio & Video",
  "smartGen.toolLibrary.scene.2.tool.0.name": "JianYing/Bijian",
  "smartGen.toolLibrary.scene.2.tool.0.desc": "Short-video creation",
  "smartGen.toolLibrary.scene.2.tool.1.name": "Xichuangzhu",
  "smartGen.toolLibrary.scene.2.tool.1.desc": "Poetry reading + mood",
  "smartGen.toolLibrary.scene.2.tool.2.name": "CCTV Documentaries",
  "smartGen.toolLibrary.scene.2.tool.2.desc": "Background video",
  "smartGen.toolLibrary.scene.3": "Interactive Exploration",
  "smartGen.toolLibrary.scene.3.tool.0.name": "Tencent Docs",
  "smartGen.toolLibrary.scene.3.tool.0.desc": "Collaborative annotations",
  "smartGen.toolLibrary.scene.3.tool.1.name": "Xiumi/135",
  "smartGen.toolLibrary.scene.3.tool.1.desc": "Text & image layout",
  "smartGen.toolLibrary.scene.3.tool.2.name": "Wenjuanxing",
  "smartGen.toolLibrary.scene.3.tool.2.desc": "In-class quizzes",
  "smartGen.toolLibrary.scene.4": "Visual Display",
  "smartGen.toolLibrary.scene.4.tool.0.name": "Zhonghua Collection",
  "smartGen.toolLibrary.scene.4.tool.0.desc": "Classical illustrations",
  "smartGen.toolLibrary.scene.4.tool.1.name": "Canva",
  "smartGen.toolLibrary.scene.4.tool.1.desc": "Poster / graphic design",
  "smartGen.toolLibrary.scene.4.tool.2.name": "WeRead",
  "smartGen.toolLibrary.scene.4.tool.2.desc": "e-book embedding",

  /* ── Daily tips (SmartGenDailyTips) ── */
  "smartGen.tips.firstUse": "💡 Enter your lesson, AI recommends tools",
  "smartGen.tips.studentProfile":
    "📊 Weak on classical Chinese (52%) — try adding interaction",
  "smartGen.tips.newCombo": "🆕 New combo: documentary + atlas + collaboration",
  "smartGen.tips.genComplete": "✓ Courseware generated in 3 minutes",
  "smartGen.tips.toolRecommend": "📈 JianYing used only twice — try video",
  "smartGen.tips.topRated": "⭐ Gushiwen 95% — highly rated",
  "smartGen.tips.pendingWork": '⏳ "Old Wang" worksheet still in progress',

  /* ── Tour (SmartGenTour) ── */
  "smartGen.tour.step0.title": "Three generation types",
  "smartGen.tour.step0.desc":
    "Three generation types: AI + tools working together",
  "smartGen.tour.step1.title": "Requirement input",
  "smartGen.tour.step1.desc":
    "Enter teaching requirements and AI analyzes & recommends",
  "smartGen.tour.step2.title": "AI analyze button",
  "smartGen.tour.step2.desc": "Click to analyze and match the best tool combo",
  "smartGen.tour.step3.title": "Recommended combos",
  "smartGen.tour.step3.desc":
    "Recommended tool combos with features and integration plan",
  "smartGen.tour.step4.title": "Generate with the combo",
  "smartGen.tour.step4.desc":
    "Generate with one click, or change recommendations / customize",
  "smartGen.tour.step5.title": "Generation history",
  "smartGen.tour.step5.desc": "15 calls this week — view, edit, share",
  "smartGen.tour.step6.title": "Open-source tool library",
  "smartGen.tour.step6.desc": "Made for Chinese classes, grouped by scenario",
  "smartGen.tour.step7.title": "Tool effectiveness ranking",
  "smartGen.tour.step7.desc": "Ranked by effectiveness — Gushiwen 95%",
  "smartGen.tour.next": "Next",
  "smartGen.tour.done": "Done",
  "smartGen.tour.completeTitle": "Smart Generation guide complete!",
  "smartGen.tour.completeDesc":
    "Enter requirements → AI recommends → tool combos → one-click generate → share & reuse",

  /* ── Tiered compose (one paper per A/B/C) ── */
  "smartGen.tiered.title": "Tiered Compose",
  "smartGen.tiered.subtitle":
    "Generate one tiered paper per current A/B/C tier",
  "smartGen.tiered.entry": "Tiered Compose",
  "smartGen.tiered.generate": "Generate 3 tiered papers",
  "smartGen.tiered.generating": "Generating tiered papers…",
  "smartGen.tiered.success": "Generated A/B/C tiered papers",
  "smartGen.tiered.failed": "Tiered compose failed",
  "smartGen.tiered.noTiers":
    "This class has no tiers yet — run auto/manual tiering first",
  "smartGen.tiered.pickClass": "Please select a class first",
  "smartGen.tiered.pickSubject": "Select subject",
  "smartGen.tiered.empty": "No tiered papers yet — use the button above",
  "smartGen.tiered.loadFailed": "Failed to load tiered papers",
  "smartGen.tiered.paperCount": "{count} questions",
  "smartGen.tiered.difficulty": "Easy {easy} / Med {medium} / Hard {hard}",
  "smartGen.tiered.studentCount": "{count} students",
  "smartGen.tiered.view": "View",
  "smartGen.tiered.print": "Print",
  "smartGen.tiered.download": "Download",
  "smartGen.tiered.openInExamGen": "Open in Exam Gen",
  "smartGen.tiered.previewTitle": "Tiered Paper Preview",
  "smartGen.tiered.close": "Close",
  "smartGen.tiered.batchLabel": "Batch {id}",
  "smartGen.tiered.strategy.A": "Higher / comprehensive / challenge-weighted",
  "smartGen.tiered.strategy.B": "Standard difficulty",
  "smartGen.tiered.strategy.C": "Basic consolidation / single knowledge point",
  "smartGen.tiered.tierA": "Tier A",
  "smartGen.tiered.tierB": "Tier B",
  "smartGen.tiered.tierC": "Tier C",
  "smartGen.aiSource.label": "Source",
  "smartGen.aiSource.ai": "AI generated",
  "smartGen.aiSource.bank": "Question bank",
  "smartGen.aiSource.bankUnavailable": "Question bank not connected",
  "smartGen.aiSource.bankHint":
    "The question bank is not available yet — pick \"AI generated\" instead.",
  "smartGen.aiSource.settings": "AI settings",
  "smartGen.aiSource.topicsLabel": "Topics",
  "smartGen.aiSource.topicsPlaceholder":
    "Optional, comma separated; blank = use weak points",
  "smartGen.aiSource.typesLabel": "Types",
  "smartGen.aiSource.addType": "Add type",
  "smartGen.aiSource.countLabel": "Q",
  "smartGen.aiSource.scoreLabel": "pts",
  "smartGen.aiSource.aiHint":
    "AI generates papers per tier with the selected topics and types",
  "smartGen.aiSource.regenerate": "Regenerate",
  "smartGen.aiSource.apply": "Apply",
};
