# -*- coding: utf-8 -*-
"""AI 助教：各功能模块使用教程（与左侧栏一致，不含后台管理）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.services.ai_chat_tutorial_semantics import (
    _GOAL_TRIGGER,
    looks_like_goal_or_howto_question,
    rank_semantic_nav_ids,
    score_semantic_intent,
)
from app.services.multi_project_settings import get_project_name


def _brand_text(text: str) -> str:
    """将教程文案中的默认项目名替换为当前配置名称。"""
    return (text or "").replace("叙阅", get_project_name())


@dataclass(frozen=True)
class FeatureTutorial:
    nav_id: str
    jump_label: str
    title: str
    summary: str
    steps: tuple[str, ...]
    tips: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    requires_class: bool = False
    group: str = ""


def get_tutorial_by_nav_id(nav_id: str) -> Optional[FeatureTutorial]:
    for t in FEATURE_TUTORIALS:
        if t.nav_id == nav_id:
            return FeatureTutorial(
                nav_id=t.nav_id,
                jump_label=t.jump_label,
                title=t.title,
                summary=_brand_text(t.summary),
                steps=tuple(_brand_text(s) for s in t.steps),
                tips=tuple(_brand_text(x) for x in t.tips),
                aliases=t.aliases,
                requires_class=t.requires_class,
                group=t.group,
            )
    return None


# jump_label 必须与前端 FloatingChat LABEL_TO_NAV_ID 的键一致
FEATURE_TUTORIALS: tuple[FeatureTutorial, ...] = (
    FeatureTutorial(
        nav_id="home",
        jump_label="首页",
        title="首页（工作台）",
        summary="首页是叙阅的入口，可快速搜索、发起批改、查看班级概况与待办。",
        steps=(
            "在左侧栏点击「首页」进入工作台。",
            "顶部全局搜索：可搜学生姓名、功能模块或快捷操作。",
            "「拍照批改 / 扫描批改」区：快速进入批改流程（也可去「开始批改」完整操作）。",
            "统计卡片：查看班级均分、批改完成率、预警学生等概览。",
            "学生学情矩阵：预览班级学生分布，点击可跳转到学生分析。",
            "待办与快捷操作：处理待办事项，一键跳转到常用功能。",
        ),
        tips=("首次使用建议先完成「班级管理」中添加班级与学生。",),
        aliases=("工作台", "主页", "主界面"),
        group="首页",
    ),
    FeatureTutorial(
        nav_id="class-dashboard",
        jump_label="班级看板",
        title="班级看板",
        summary="查看当前班级的学生列表、教师信息、学情趋势，并快捷进入讲评、靶向等功能。",
        steps=(
            "左侧栏「我的班级」→「班级看板」。",
            "页面顶部先选择班级（必选）。",
            "查看班级学生列表，可新增/编辑/删除学生。",
            "「教师管理」：查看或维护班主任、任课教师。",
            "学情趋势图：查看近期成绩变化。",
            "使用卡片上的快捷按钮可跳转到课堂讲评、靶向提升、分层推送等。",
        ),
        requires_class=True,
        aliases=("班级仪表盘", "班级面板", "班級看板"),
        group="我的班级",
    ),
    FeatureTutorial(
        nav_id="settings-class",
        jump_label="班级管理",
        title="班级管理",
        summary="维护全校/全年级班级树、学生花名册、权限与批量导入。",
        steps=(
            "左侧栏「我的班级」→「班级管理」。",
            "左侧班级树：按学段、年级展开，点击某个班查看详情。",
            "「新建班级」：填写学段、年级、班号等信息。",
            "右侧学生表格：添加、编辑、删除学生，维护学号与家长信息。",
            "支持 Excel 批量导入学生、全局导入等（按页面按钮操作）。",
            "「权限」相关：可邀请其他教师协作管理班级。",
        ),
        aliases=("花名册", "学生管理", "添加班级", "添加学生", "导入学生"),
        group="我的班级",
    ),
    FeatureTutorial(
        nav_id="class-students",
        jump_label="学生分析",
        title="学生分析",
        summary="按学生查看个人全景画像、成绩与错题，支持 AI 深度诊断。",
        steps=(
            "左侧栏「学情分析」→「学生分析」。",
            "顶部选择班级（必选）。",
            "左侧学生列表中点击某一学生。",
            "右侧展示该生的全景画像：成绩、薄弱点、错题等。",
            "可「导入成绩」补充或更新学情数据。",
            "点击「AI 深度诊断」生成个性化分析报告。",
        ),
        requires_class=True,
        aliases=("学生名单", "学生全景", "学生画像", "个人学情"),
        group="学情分析",
    ),
    FeatureTutorial(
        nav_id="analytics-portrait",
        jump_label="班级分析",
        title="班级分析",
        summary="从班级维度查看成绩分布、迁移热力图、归因预测，可导出 PDF 报告。",
        steps=(
            "左侧栏「学情分析」→「班级分析」。",
            "顶部选择班级（必选）。",
            "查看指标卡：平均分、及格率、优秀率等。",
            "成绩分布图：了解分数段人数分布。",
            "迁移热力图 / 归因预测：分析学生层次变化与风险。",
            "需要留存时点击「导出 PDF」。",
        ),
        requires_class=True,
        aliases=("班级画像", "班级学情", "成绩分布"),
        group="学情分析",
    ),
    FeatureTutorial(
        nav_id="analytics-grade",
        jump_label="年级分析",
        title="年级分析",
        summary="年级视角横向对比各班表现与学科素养趋势。",
        steps=(
            "左侧栏「学情分析」→「年级分析」。",
            "选择年级范围（若页面提供筛选）。",
            "查看各班横向对比图表。",
            "查看学科素养或成绩趋势（依数据接入情况展示）。",
        ),
        aliases=("年级画像", "年级对比"),
        group="学情分析",
    ),
    FeatureTutorial(
        nav_id="ai-review",
        jump_label="课堂讲评",
        title="课堂讲评",
        summary="基于批改结果生成课前概览、课堂讲评方案、二次巩固与课后反馈，可导出 PDF。",
        steps=(
            "左侧栏「AI精准教学」→「课堂讲评」。",
            "顶部选择班级与学科（必选班级）。",
            "点击「导入考试」：从已批改的考试/文件夹中选择数据源。",
            "系统自动分析错题与得分概况，生成讲评方案。",
            "查看「课前」「巩固方案」「课后反馈」等板块内容。",
            "可编辑文本后保存；需要打印时使用「导出 PDF」。",
        ),
        requires_class=True,
        aliases=("智能复习", "讲评", "二次巩固", "巩固方案", "课前讲评"),
        group="AI精准教学",
    ),
    FeatureTutorial(
        nav_id="ai-targeted",
        jump_label="靶向提升",
        title="靶向提升",
        summary="针对单个学生生成学情诊断与提升方案，支持导入考试、推荐练习与导出报告。",
        steps=(
            "左侧栏「AI精准教学」→「靶向提升」。",
            "顶部选择班级、学科（必选班级）。",
            "左侧搜索并点击学生姓名。",
            "点击「导入考试」关联批改数据。",
            "查看 AI 生成的「诊断」与「提升方案」。",
            "可保存推荐名单、导出 PDF 报告。",
        ),
        requires_class=True,
        aliases=("靶向", "诊断报告", "提升方案", "针对性练习"),
        group="AI精准教学",
    ),
    FeatureTutorial(
        nav_id="ai-layered",
        jump_label="分层推送",
        title="分层推送",
        summary="将学生划分为优/中/弱等层次，生成分层任务并预览钉钉推送。",
        steps=(
            "左侧栏「AI精准教学」→「分层推送」。",
            "顶部选择班级（必选）。",
            "查看系统建议的三档分层，可拖拽学生调整层次。",
            "配置推送内容与钉钉推送预览。",
            "确认后执行推送（需已配置相关集成）。",
        ),
        requires_class=True,
        aliases=("分层", "分层作业", "钉钉推送"),
        group="AI精准教学",
    ),
    FeatureTutorial(
        nav_id="prep-bank",
        jump_label="备课计划",
        title="备课计划",
        summary="以月/周/日日历管理备课安排，创建、编辑、删除计划。",
        steps=(
            "左侧栏「AI备课」→「备课计划」。",
            "切换「月 / 周 / 日」视图浏览日历。",
            "点击某一天或「新建」按钮添加计划。",
            "填写日期、学科、计划内容并保存。",
            "点击已有计划可编辑或删除。",
        ),
        aliases=("备课日历", "教学计划", "学期计划"),
        group="AI备课",
    ),
    FeatureTutorial(
        nav_id="prep-lesson",
        jump_label="教案生成",
        title="教案生成",
        summary="AI 辅助生成教案，支持分栏编辑、自动保存、导出与邮件发送。",
        steps=(
            "左侧栏「AI备课」→「教案生成」。",
            "顶部选择班级与学科（必选班级）。",
            "在列表中选择已有教案，或点击「新建教案」。",
            "填写标题、学年、学期、课次等基本信息。",
            "点击「AI 生成」自动填充教学目标、重难点、教学过程等栏目。",
            "手动修改各栏目后点击「保存」；支持导出 Word、发送邮件。",
        ),
        requires_class=True,
        aliases=("教案", "AI教案", "备课", "生成教案"),
        group="AI备课",
    ),
    FeatureTutorial(
        nav_id="prep-exam",
        jump_label="智能组卷",
        title="智能组卷",
        summary="创建与管理试卷，支持 AI 出题、多题型编辑、打印与下载。",
        steps=(
            "左侧栏「AI备课」→「智能组卷」。",
            "在试卷列表点击「新建试卷」或打开已有试卷。",
            "设置试卷标题、学科。",
            "左侧添加题型占位（选择、填空、判断、简答、作文等）并设置分值。",
            "点击「AI 智能出题」按题型批量填充题目内容。",
            "编辑题干、选项、答案后「保存试卷」。",
            "使用「打印」「下载」「邮件发送」输出试卷。",
        ),
        aliases=("组卷", "试卷库", "出题", "我的试卷", "组卷库"),
        group="AI备课",
    ),
    FeatureTutorial(
        nav_id="prep-video",
        jump_label="资源库",
        title="资源库",
        summary="管理教学资源文件夹，上传、预览、下载课件与素材，可跳转组卷。",
        steps=(
            "左侧栏「AI备课」→「资源库」。",
            "左侧新建或选择文件夹。",
            "点击「上传」添加课件、视频、文档等资源。",
            "点击资源可在右侧预览详情、下载或发送邮件。",
            "部分资源支持「用于组卷」跳转到智能组卷。",
        ),
        aliases=("教学资源", "课件库", "素材库", "资源上传"),
        group="AI备课",
    ),
    FeatureTutorial(
        nav_id="grading-start",
        jump_label="开始批改",
        title="开始批改",
        summary="作业批改核心界面：管理考试文件夹、扫描导入、智能/参照/作文批改、打印留痕。",
        steps=(
            "左侧栏「作业批改」→「开始批改」。",
            "顶部选择班级，新建或打开一个「考试文件夹」。",
            "选择批改模式：智能批改、参照批改（需先上传标准答案）、作文批改等。",
            "「扫描导入」或手动上传学生试卷图片/PDF，按试卷框归档到各学生。",
            "勾选待批改试卷，点击「开始批改」执行 AI 批改。",
            "批改完成后可查看详情、修改分数、一键打印留痕或导出。",
            "作文模式可配置评分规则、打印 AI 评语 PDF。",
        ),
        aliases=(
            "批改作业",
            "快速批改",
            "扫描批改",
            "拍照批改",
            "智能批改",
            "参照批改",
            "作文批改",
            "打印留痕",
            "如何批改",
        ),
        group="作业批改",
    ),
    FeatureTutorial(
        nav_id="grading-errors",
        jump_label="批改详细",
        title="批改详细",
        summary="按考试文件夹查看批改结果、参与人数、错题率，进入明细查看每生得分与错题。",
        steps=(
            "左侧栏「作业批改」→「批改详细」。",
            "顶部选择班级。",
            "列表展示已批改的考试文件夹（参与人数、错题率等）。",
            "点击某个文件夹进入详情页。",
            "查看每位学生的得分、错题列表与题目错误率排行。",
            "可从此处核对分数、分析共性错题（数据来源于批改档案）。",
        ),
        aliases=(
            "历史批改",
            "批改记录",
            "批改结果",
            "错题本",
            "查看分数",
            "考试得分",
            "批改明细",
        ),
        group="作业批改",
    ),
    FeatureTutorial(
        nav_id="settings-personal",
        jump_label="个人设置",
        title="个人设置",
        summary="修改个人资料、任教信息、联系方式与登录密码。",
        steps=(
            "左侧栏「设置」→「个人设置」。",
            "修改昵称、手机号、邮箱、任教科目、职称等。",
            "在密码区域修改登录密码（需验证原密码）。",
            "保存后信息用于教案署名、系统识别等。",
        ),
        aliases=("修改密码", "个人资料", "账号设置"),
        group="设置",
    ),
    FeatureTutorial(
        nav_id="settings-subject",
        jump_label="科目配置",
        title="科目配置",
        summary="配置知识点体系、评分标准、能力模型、教材映射与考试模板。",
        steps=(
            "左侧栏「设置」→「科目配置」。",
            "选择学科进入配置页。",
            "「知识点体系」：维护单元与知识点，标记薄弱点。",
            "「评分标准 / 能力模型」：设置批改与学情相关规则。",
            "「教材映射」「考试模板」：按学科维护模板，供组卷与批改使用。",
        ),
        aliases=("学科配置", "知识点配置", "评分标准", "考试模板"),
        group="设置",
    ),
    FeatureTutorial(
        nav_id="settings-hardware",
        jump_label="硬件配置",
        title="硬件配置",
        summary="检测打印机、扫描仪，配置全局打印偏好。",
        steps=(
            "左侧栏「设置」→「硬件配置」。",
            "查看本机打印机、扫描仪连接状态。",
            "设置默认打印机、纸张、双面打印等偏好。",
            "批改留痕、试卷打印将使用此处配置。",
        ),
        aliases=("打印机", "扫描仪", "打印配置"),
        group="设置",
    ),
    FeatureTutorial(
        nav_id="settings-multi-device",
        jump_label="多端管理",
        title="多端管理",
        summary="学生端/家长端与钉钉等多端能力入口（部分功能建设中）。",
        steps=(
            "左侧栏「设置」→「多端管理」。",
            "查看学生端、家长端、钉钉集成等说明与配置入口。",
            "按页面提示完成绑定或等待后续版本更新。",
        ),
        aliases=("钉钉", "家长端", "学生端"),
        group="设置",
    ),
    FeatureTutorial(
        nav_id="settings-preferences",
        jump_label="系统设置",
        title="系统设置",
        summary="系统级配置（如 AI 模型 API）、存储清理等。",
        steps=(
            "左侧栏「设置」→「系统设置」。",
            "配置千问等大模型 API Key（AI 助教、批改依赖此项）。",
            "执行存储清理、缓存管理等维护操作。",
            "仅建议管理员或熟悉配置的用户修改。",
        ),
        aliases=("API配置", "模型配置", "千问配置"),
        group="设置",
    ),
)

# 分组概览教程
GROUP_TUTORIALS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "我的班级": (
        "我的班级",
        "包含「班级看板」与「班级管理」：看板侧重日常教学与学情概览，管理侧重班级树与学生花名册维护。",
        ("班级看板 → 日常查看与快捷操作", "班级管理 → 建班、导学生、权限"),
    ),
    "学情分析": (
        "学情分析",
        "从学生个人、班级、年级三个层级分析学习情况。",
        ("学生分析 → 个人画像", "班级分析 → 班级报告", "年级分析 → 年级对比"),
    ),
    "AI精准教学": (
        "AI精准教学",
        "基于批改数据驱动课堂讲评、个体靶向与分层推送。",
        ("课堂讲评 → 全班讲评方案", "靶向提升 → 个体诊断", "分层推送 → 分层任务"),
    ),
    "AI备课": (
        "AI备课",
        "备课计划、AI 教案、智能组卷与资源库形成完整备课闭环。",
        ("备课计划 → 日程", "教案生成 → AI 写教案", "智能组卷 → 出题", "资源库 → 素材"),
    ),
    "作业批改": (
        "作业批改",
        "「开始批改」完成扫描与 AI 批改；「批改详细」查看结果与分数。",
        ("开始批改 → 上传并批改", "批改详细 → 查分、错题"),
    ),
    "设置": (
        "设置",
        "个人资料、学科规则、硬件与系统级配置。",
        ("个人设置 / 科目配置 / 硬件配置 / 系统设置"),
    ),
}


_TUTORIAL_TRIGGER = re.compile(
    r"怎么用|如何使用|怎么使用|怎么操作|如何操作|如何使用|教程|使用说明|功能介绍|"
    r"在哪里|在哪(?!个)|如何去|怎么进入|怎么打开|步骤|操作流程|干什么|做什么|"
    r"有什么功能|能做什么|有哪些功能|包含哪些功能|如何使用叙阅|新手|入门|"
    r"如何批改|怎么批改|如何组卷|怎么组卷|如何备课|怎么备课",
    re.I,
)


def looks_like_tutorial_question(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    # 纯数据问句不走教程
    from app.services.ai_chat_access import (
        looks_like_concrete_data_request,
        looks_like_grading_exam_stats_question,
        looks_like_student_exam_score_question,
    )

    if looks_like_concrete_data_request(text):
        return False
    if looks_like_student_exam_score_question(text):
        return False
    if looks_like_grading_exam_stats_question(text):
        return False
    if f"如何使用{get_project_name()}" in text:
        return True
    if _TUTORIAL_TRIGGER.search(text) or _GOAL_TRIGGER.search(text):
        return True
    if looks_like_goal_or_howto_question(text):
        return True
    # 语义能匹配到功能意图（用户没说功能名）
    ranked = rank_semantic_nav_ids(text)
    if ranked and ranked[0][1] >= 14:
        return True
    # 「XX是什么」且能匹配到功能名
    if re.search(r"是什么|什么意思|啥意思", text) and match_tutorial(text)[0]:
        return True
    return False


def _score_tutorial(text: str, tutorial: FeatureTutorial, current_module: Optional[str]) -> int:
    score = 0
    labels = (tutorial.jump_label, tutorial.title, *tutorial.aliases)
    for label in labels:
        if label and label in text:
            score += 10 + len(label)
    if tutorial.group and tutorial.group in text:
        score += 6
    if current_module:
        if tutorial.jump_label == current_module:
            score += 8
        if _NAV_ID_TO_LABEL.get(tutorial.nav_id) == current_module:
            score += 8
    sem_score, _ = score_semantic_intent(text, tutorial.nav_id)
    score += sem_score
    return score


_NAV_ID_TO_LABEL = {t.nav_id: t.jump_label for t in FEATURE_TUTORIALS}
_LABEL_TO_NAV_ID = {t.jump_label: t.nav_id for t in FEATURE_TUTORIALS}
for t in FEATURE_TUTORIALS:
    for alias in t.aliases:
        _LABEL_TO_NAV_ID.setdefault(alias, t.nav_id)


def match_tutorial(
    text: str,
    *,
    current_module: Optional[str] = None,
) -> tuple[Optional[FeatureTutorial], list[str]]:
    """匹配教程，返回 (教程, 语义命中片段)。"""
    text = (text or "").strip()
    if not text:
        return None, []

    # 语义优先：用户按「想做什么」描述
    ranked = rank_semantic_nav_ids(text)
    if ranked and ranked[0][1] >= 18:
        top_nav, top_score, hits = ranked[0]
        if len(ranked) == 1 or top_score >= ranked[1][1] + 6:
            tutorial = get_tutorial_by_nav_id(top_nav)
            if tutorial:
                return tutorial, hits

    best: Optional[FeatureTutorial] = None
    best_score = 0
    best_hits: list[str] = []
    for tutorial in FEATURE_TUTORIALS:
        s = _score_tutorial(text, tutorial, current_module)
        _, hits = score_semantic_intent(text, tutorial.nav_id)
        if s > best_score:
            best_score = s
            best = tutorial
            best_hits = hits

    if best and best_score >= 14:
        return best, best_hits

    # 弱语义：有目标描述但分数略低
    if ranked and ranked[0][1] >= 14:
        tutorial = get_tutorial_by_nav_id(ranked[0][0])
        if tutorial:
            return tutorial, ranked[0][2]

    if _TUTORIAL_TRIGGER.search(text) or _GOAL_TRIGGER.search(text) or re.search(r"是什么|什么意思", text):
        for tutorial in FEATURE_TUTORIALS:
            if any(alias in text for alias in tutorial.aliases):
                return tutorial, []

    return None, []
