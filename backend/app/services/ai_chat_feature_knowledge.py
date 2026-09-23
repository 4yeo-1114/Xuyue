# -*- coding: utf-8 -*-
"""叙阅产品功能知识库：供千问学习后回答功能使用类问题（非回答模板）。"""

from __future__ import annotations

from app.services.ai_chat_math_style import MATH_FORMAT_RULES
from app.services.multi_project_settings import get_project_name
from app.services.ai_chat_tutorial_semantics import _NAV_TO_INTENTS
from app.services.ai_chat_tutorials import FEATURE_TUTORIALS, GROUP_TUTORIALS, get_tutorial_by_nav_id

# 各功能子能力点（小功能）
FEATURE_SUB_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "home": (
        "全局搜索（学生/模块/快捷操作）",
        "拍照批改与扫描批改快捷入口",
        "班级统计概览卡片",
        "学生学情矩阵预览",
        "待办事项与快捷跳转",
        "新手引导",
    ),
    "class-dashboard": (
        "班级学生列表增删改",
        "教师管理（班主任/任课）",
        "学情趋势图",
        "快捷跳转讲评/靶向/分层",
    ),
    "settings-class": (
        "班级树浏览与新建班级",
        "学生花名册维护",
        "Excel 批量导入学生",
        "全局导入",
        "班级协作与权限邀请",
    ),
    "class-students": (
        "学生列表与全景画像",
        "成绩与错题概览",
        "导入成绩",
        "AI 深度诊断",
    ),
    "analytics-portrait": (
        "班级指标卡（均分/及格率/优秀率）",
        "成绩分布图",
        "迁移热力图",
        "归因预测",
        "导出班级 PDF 报告",
    ),
    "analytics-grade": (
        "年级各班横向对比",
        "学科素养趋势",
    ),
    "ai-review": (
        "选择班级与学科",
        "导入已批改考试",
        "课前概览生成",
        "课堂讲评方案",
        "二次巩固练习方案",
        "课后反馈",
        "导出讲评 PDF",
    ),
    "ai-targeted": (
        "按学生查看靶向报告",
        "导入考试数据",
        "AI 学情诊断（优势/薄弱/根因）",
        "个性化提升方案",
        "班级推荐关注名单",
        "导出诊断 PDF",
    ),
    "ai-layered": (
        "优/中/弱三档分层",
        "拖拽调整学生层次",
        "分层任务内容配置",
        "钉钉推送预览与发送",
        "推送效果追踪",
    ),
    "prep-bank": (
        "月/周/日日历视图",
        "创建与编辑备课计划",
        "按学科筛选计划",
        "删除计划",
    ),
    "prep-lesson": (
        "教案列表与新建",
        "基本信息（学年/学期/课次）",
        "AI 生成教学目标/过程/重难点",
        "分栏手动编辑",
        "自动保存",
        "导出 Word / 邮件发送",
    ),
    "prep-exam": (
        "试卷库列表",
        "新建试卷与学科设置",
        "添加题型占位（选择/填空/判断/简答/作文）",
        "AI 智能出题填充",
        "编辑题干选项与分值",
        "保存/打印/下载/邮件发送",
    ),
    "prep-video": (
        "文件夹管理",
        "上传课件/视频/文档",
        "资源预览与下载",
        "邮件发送资源",
        "跳转用于组卷",
    ),
    "grading-start": (
        "考试文件夹新建与打开",
        "智能批改",
        "参照批改（需标准答案）",
        "作文批改与 rubric 配置",
        "扫描导入与手动上传",
        "试卷框按学生归档",
        "一键批改与进度查看",
        "批改详情与改分",
        "打印留痕",
        "作文 AI 评语 PDF 打印/下载",
    ),
    "grading-errors": (
        "按考试文件夹浏览批改记录",
        "参与人数与错题率统计",
        "进入明细查看每生得分",
        "错题列表与题目错误率排行",
        "核对分数与共性错题",
    ),
    "settings-personal": (
        "修改昵称/手机/邮箱",
        "任教科目与职称",
        "修改登录密码",
    ),
    "settings-subject": (
        "知识点体系维护",
        "知识图谱编辑",
        "评分标准配置",
        "能力模型",
        "教材映射",
        "考试模板",
    ),
    "settings-hardware": (
        "打印机检测与默认设置",
        "扫描仪检测",
        "全局打印偏好（纸张/双面）",
    ),
    "settings-multi-device": (
        "学生端/家长端说明",
        "钉钉集成入口",
    ),
    "settings-preferences": (
        "千问 API Key 配置",
        "存储与缓存清理",
        "系统级维护",
    ),
}

SIDEBAR_STRUCTURE = """
## 左侧栏菜单结构（不含后台管理）

- **首页**
- **我的班级** → 班级看板、班级管理
- **学情分析** → 学生分析、班级分析、年级分析
- **AI精准教学** → 课堂讲评、靶向提升、分层推送
- **AI备课** → 备课计划、教案生成、智能组卷、资源库
- **作业批改** → 开始批改、批改详细
- **设置** → 个人设置、科目配置、硬件配置、多端管理、系统设置
"""


def _user_phrases_for_nav(nav_id: str) -> list[str]:
    phrases: list[str] = []
    for intent in _NAV_TO_INTENTS.get(nav_id, []):
        phrases.extend(intent.phrases[:8])
    tutorial = get_tutorial_by_nav_id(nav_id)
    if tutorial:
        phrases.extend(tutorial.aliases)
    seen: set[str] = set()
    out: list[str] = []
    for p in phrases:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out[:12]


def build_feature_knowledge_for_prompt() -> str:
    """完整功能知识库文本，注入千问 system prompt。"""
    project_name = get_project_name()
    lines = [
        f"# {project_name}产品功能知识库",
        "",
        "以下为产品真实能力说明，供你理解后**用自己的语言**回答用户，禁止照搬下文当作回复模板。",
        "",
        SIDEBAR_STRUCTURE.strip(),
        "",
        "---",
        "",
    ]

    current_group = ""
    for t in FEATURE_TUTORIALS:
        if t.group and t.group != current_group:
            current_group = t.group
            g = GROUP_TUTORIALS.get(current_group)
            if g:
                lines.append(f"## 分组：{current_group}")
                lines.append(g[1])
                lines.append("")

        lines.append(f"### {t.jump_label}（跳转名：`{t.jump_label}`）")
        lines.append(f"- **位置**：左侧栏 → {t.group or '首页'} → {t.jump_label}")
        lines.append(f"- **用途**：{t.summary}")
        if t.requires_class:
            lines.append("- **前置条件**：页面顶部需先选择班级")
        subs = FEATURE_SUB_CAPABILITIES.get(t.nav_id, ())
        if subs:
            lines.append("- **子功能/能力点**：")
            for s in subs:
                lines.append(f"  - {s}")
        phrases = _user_phrases_for_nav(t.nav_id)
        if phrases:
            lines.append(f"- **用户常见说法（语义映射）**：{'、'.join(phrases)}")
        lines.append("- **操作流程参考**（回答时可重组，勿逐字复述）：")
        for i, step in enumerate(t.steps, 1):
            lines.append(f"  {i}. {step}")
        if t.tips:
            lines.append(f"- **提示**：{'；'.join(t.tips)}")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 语义理解对照（用户不说功能名时）",
        "",
        "| 用户想做的事（举例） | 对应跳转名 |",
        "|---------------------|------------|",
        "| 学生个人分析/诊断报告/提升方案 | 靶向提升 |",
        "| 课堂讲评/讲错题/巩固练习 | 课堂讲评 |",
        "| 分层作业/按水平推送 | 分层推送 |",
        "| 学生画像/单个学生学情 | 学生分析 |",
        "| 班级整体报告/成绩分布 | 班级分析 |",
        "| 批改作业/扫描试卷/作文批改 | 开始批改 |",
        "| 查分数/批改结果/错题统计 | 批改详细 |",
        "| 写教案/教学设计 | 教案生成 |",
        "| 组卷/出题/单元测验 | 智能组卷 |",
        "| 导入学生/建班/花名册 | 班级管理 |",
        "| 备课日历/教学计划 | 备课计划 |",
        "| 上传课件/教学资源 | 资源库 |",
    ])
    return "\n".join(lines)


def build_semantic_hint_for_prompt(user_text: str) -> str:
    """轻量语义提示，帮助模型定位意图（非固定回答）。"""
    from app.services.ai_chat_tutorial_semantics import rank_semantic_nav_ids

    text = (user_text or "").strip()
    if not text:
        return ""
    ranked = rank_semantic_nav_ids(text)
    if not ranked or ranked[0][1] < 10:
        return ""
    lines = ["【语义参考】用户问题可能涉及以下功能（请结合知识库自行组织回答）："]
    for nav_id, score, hits in ranked[:3]:
        if score < 10:
            continue
        t = get_tutorial_by_nav_id(nav_id)
        if not t:
            continue
        hit_str = f"（关键词：{'、'.join(hits[:3])}）" if hits else ""
        lines.append(f"- {t.jump_label}{hit_str}")
    return "\n".join(lines) if len(lines) > 1 else ""


TUTORIAL_ANSWER_INSTRUCTIONS = """
## 功能使用类问题 — 回答规则

1. **必须先理解用户意图**：用户往往描述「想做什么」，不会说左侧栏功能名；对照知识库中的「用户常见说法」与「语义理解对照」定位功能。
2. **必须由你亲自撰写回答**：结合用户具体问题，用自然语言分步说明；禁止输出与知识库完全相同的固定段落。
3. **结构建议**（可灵活调整）：先一句话点明「这对应系统中的 XX 功能」→ 分步骤操作指引 → 必要提醒（如先选班级）→ 1~2 个 `[[跳转:跳转名]]`。
4. **跳转名**必须与知识库中各功能的「跳转名」完全一致。
5. **禁止**编造知识库中不存在的按钮、菜单或能力。
6. **禁止**调用数据查询工具；功能使用问题只依据知识库作答。
7. 若用户问题跨多个功能，可简要说明关系并分别指引。
""" + MATH_FORMAT_RULES


def build_tutorial_system_prompt(
    user_text: str = "",
    *,
    current_module_label: str = "",
) -> str:
    """构建功能问答专用 system prompt（知识库 + 作答规则，非模板答案）。"""
    project_name = get_project_name()
    parts = [
        f'你是"{project_name} AI 助教"，专业的教学咨询顾问，负责解答产品功能使用问题。',
        TUTORIAL_ANSWER_INSTRUCTIONS.strip(),
    ]
    if current_module_label:
        parts.append(f"\n用户当前正在使用「{current_module_label}」页面。")
    sem = build_semantic_hint_for_prompt(user_text)
    if sem:
        parts.append(sem)
    parts.append(build_feature_knowledge_for_prompt())
    return "\n".join(p for p in parts if p)
