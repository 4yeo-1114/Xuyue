# -*- coding: utf-8 -*-
"""AI 助教教程：用户自然语言意图 → 功能模块语义映射。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TutorialSemanticIntent:
    """用户可能的说法 → 对应功能 nav_id。"""

    nav_id: str
    phrases: tuple[str, ...] = ()
    patterns: tuple[str, ...] = ()
    negative_patterns: tuple[str, ...] = ()


# 用户按「想做什么」提问，而非功能正式名称
TUTORIAL_SEMANTIC_INTENTS: tuple[TutorialSemanticIntent, ...] = (
    TutorialSemanticIntent(
        "ai-targeted",
        phrases=(
            "个人分析报告",
            "学生分析报告",
            "个人分析",
            "学情诊断",
            "诊断报告",
            "提升方案",
            "提升计划",
            "薄弱点分析",
            "针对性提升",
            "针对性辅导",
            "个体诊断",
            "学生诊断",
            "学习诊断",
            "补弱",
            "查漏补缺",
            "个性化方案",
            "一人一案",
        ),
        patterns=(
            r"学生?.{0,8}(个人|个体).{0,8}(分析|报告|诊断)",
            r"(分析|诊断).{0,8}(报告|方案).{0,8}学生",
            r"怎么.{0,8}(提升|补弱|诊断).{0,8}学生",
            r"学生.{0,12}(薄弱|短板|弱项)",
            r"针对.{0,6}学生.{0,8}(练|提升|辅导)",
        ),
        negative_patterns=(
            r"查(询)?",
            r"告诉我",
            r"总结|汇总",
            r"[\u4e00-\u9fa5·]{2,4}的",
            r"(数学|语文|英语|物理|化学).{0,8}(报告|分析|诊断|方案)",
        ),
    ),
    TutorialSemanticIntent(
        "ai-review",
        phrases=(
            "课堂讲评",
            "讲评方案",
            "评讲",
            "讲错题",
            "错题讲评",
            "试卷讲评",
            "巩固练习",
            "二次巩固",
            "课后巩固",
            "课前概览",
            "讲评课件",
            "统一讲评",
        ),
        patterns=(
            r"怎么.{0,8}讲评",
            r"(课堂|试卷|考试).{0,8}讲评",
            r"讲.{0,6}(错题|试卷)",
            r"巩固.{0,6}(方案|练习)",
        ),
    ),
    TutorialSemanticIntent(
        "ai-layered",
        phrases=(
            "分层推送",
            "分层作业",
            "分层教学",
            "分层任务",
            "优等生",
            "后进生",
            "学困生",
            "钉钉推送",
            "推送作业",
        ),
        patterns=(
            r"分层.{0,8}(推送|作业|教学)",
            r"按.{0,4}(层次|水平).{0,8}推送",
            r"不同层次.{0,8}学生",
        ),
    ),
    TutorialSemanticIntent(
        "class-students",
        phrases=(
            "学生画像",
            "个人画像",
            "全景画像",
            "学生全景",
            "单个学生",
            "某个学生",
            "学生详情",
            "学生档案",
            "学生学情",
            "深度诊断",
        ),
        patterns=(
            r"某个?学生.{0,12}(情况|表现|学情|怎么样)",
            r"学生.{0,8}(画像|全景|档案)",
            r"查看.{0,6}学生.{0,8}(详情|情况)",
        ),
        negative_patterns=(r"分析报告", r"提升方案", r"靶向"),
    ),
    TutorialSemanticIntent(
        "analytics-portrait",
        phrases=(
            "班级报告",
            "班级画像",
            "班级整体",
            "成绩分布",
            "班级学情",
            "班级概况",
            "整体分析",
            "归因分析",
            "迁移分析",
        ),
        patterns=(
            r"班级.{0,8}(整体|概况|报告|画像|学情)",
            r"全班.{0,8}(情况|分析|表现)",
            r"成绩分布",
            r"导出.{0,6}班级.{0,6}报告",
        ),
        negative_patterns=(r"年级",),
    ),
    TutorialSemanticIntent(
        "analytics-grade",
        phrases=(
            "年级分析",
            "年级对比",
            "年级报告",
            "各班对比",
            "横向对比",
            "年级学情",
        ),
        patterns=(
            r"年级.{0,8}(分析|对比|报告|学情)",
            r"各班.{0,8}(对比|排名)",
            r"横向对比",
        ),
    ),
    TutorialSemanticIntent(
        "class-dashboard",
        phrases=(
            "班级看板",
            "班级面板",
            "班级总览",
            "班级动态",
            "班级教师",
            "班主任",
        ),
        patterns=(
            r"班级.{0,6}(看板|总览|概况)",
            r"查看班级.{0,8}学生列表",
        ),
        negative_patterns=(r"管理", r"导入", r"新建班"),
    ),
    TutorialSemanticIntent(
        "settings-class",
        phrases=(
            "添加班级",
            "新建班级",
            "导入学生",
            "批量导入",
            "花名册",
            "学生名单",
            "班级权限",
            "邀请老师",
        ),
        patterns=(
            r"(添加|新建|创建).{0,6}班级",
            r"(导入|批量).{0,8}学生",
            r"维护.{0,6}(花名册|学生)",
            r"班级.{0,6}管理",
        ),
    ),
    TutorialSemanticIntent(
        "grading-start",
        phrases=(
            "批改作业",
            "改作业",
            "扫描批改",
            "拍照批改",
            "智能批改",
            "参照批改",
            "作文批改",
            "上传试卷",
            "扫描试卷",
            "打印留痕",
            "留痕打印",
            "自动批改",
        ),
        patterns=(
            r"(批改|改).{0,8}(作业|试卷|作文)",
            r"扫描.{0,8}(试卷|作业)",
            r"拍照.{0,8}批改",
            r"上传.{0,8}试卷",
            r"打印.{0,8}(留痕|批改)",
        ),
        negative_patterns=(r"查看.{0,8}分数", r"多少分"),
    ),
    TutorialSemanticIntent(
        "grading-errors",
        phrases=(
            "批改结果",
            "批改记录",
            "批改详细",
            "考试分数",
            "查看分数",
            "得分情况",
            "错题率",
            "错题统计",
            "谁考了多少",
        ),
        patterns=(
            r"查看.{0,8}(分数|成绩|批改结果)",
            r"(在哪|哪里|如何).{0,8}(看|查).{0,8}(分数|成绩)",
            r"学生.{0,8}(考了多少|多少分|分数)",
            r"批改.{0,8}(记录|结果|明细)",
            r"考试.{0,8}(分数|成绩).{0,8}在哪",
            r"错题.{0,8}(统计|分析|率)",
        ),
        negative_patterns=(r"怎么批改", r"如何批改", r"开始批改"),
    ),
    TutorialSemanticIntent(
        "prep-lesson",
        phrases=(
            "写教案",
            "教案",
            "备课",
            "教学设计",
            "教学目标",
            "教学过程",
            "课堂设计",
        ),
        patterns=(
            r"(写|生成|做|出).{0,8}教案",
            r"AI.{0,6}教案",
            r"备课.{0,8}教案",
            r"教学设计",
        ),
        negative_patterns=(r"计划", r"日历"),
    ),
    TutorialSemanticIntent(
        "prep-exam",
        phrases=(
            "组卷",
            "出题",
            "命题",
            "生成试卷",
            "练习卷",
            "试卷",
            "题目",
            "考题",
            "单元测试",
            "单元测验",
            "测验卷",
            "卷子",
        ),
        patterns=(
            r"(组卷|出题|命题)",
            r"(生成|制作|出).{0,8}(试卷|卷子|试题|测验)",
            r"(单元|月考|期中|期末).{0,6}(卷|测)",
            r"出.{0,6}(一份|一张).{0,8}(卷|测)",
        ),
    ),
    TutorialSemanticIntent(
        "prep-bank",
        phrases=(
            "备课计划",
            "教学计划",
            "学期计划",
            "周计划",
            "备课日历",
            "日程安排",
        ),
        patterns=(
            r"备课.{0,6}计划",
            r"(学期|周|月).{0,6}计划",
            r"教学.{0,6}日历",
        ),
    ),
    TutorialSemanticIntent(
        "prep-video",
        phrases=(
            "资源库",
            "教学资源",
            "课件",
            "素材",
            "上传课件",
            "教学视频",
            "备课资源",
        ),
        patterns=(
            r"(上传|管理).{0,8}(课件|资源|素材)",
            r"资源库",
            r"教学资源",
        ),
    ),
    TutorialSemanticIntent(
        "settings-subject",
        phrases=(
            "知识点",
            "知识图谱",
            "评分标准",
            "能力模型",
            "考试模板",
            "教材映射",
            "科目配置",
        ),
        patterns=(
            r"配置.{0,8}(知识点|评分|模板)",
            r"知识点.{0,8}(体系|配置)",
            r"评分标准",
        ),
    ),
    TutorialSemanticIntent(
        "settings-hardware",
        phrases=("打印机", "扫描仪", "打印配置", "硬件", "连接打印机"),
        patterns=(r"打印(机|配置)", r"扫描(仪|设备)", r"硬件配置"),
    ),
    TutorialSemanticIntent(
        "settings-personal",
        phrases=("修改密码", "个人资料", "手机号", "邮箱", "昵称", "职称"),
        patterns=(r"修改密码", r"个人(资料|信息|设置)", r"绑定手机"),
    ),
    TutorialSemanticIntent(
        "settings-preferences",
        phrases=("API", "千问", "模型配置", "系统配置", "清理缓存", "存储清理"),
        patterns=(r"API\s*Key", r"千问", r"系统设置", r"清理.{0,6}(缓存|存储)"),
    ),
    TutorialSemanticIntent(
        "home",
        phrases=("首页", "工作台", "快捷入口", "待办", "全局搜索"),
        patterns=(r"从哪开始", r"刚登录", r"第一次用", r"新手入门"),
    ),
)

_GOAL_TRIGGER = re.compile(
    r"怎么做|如何做|怎样做|怎样才能|怎么弄|怎么搞|如何实现|怎么生成|怎么出|怎么写|怎么查|"
    r"想要|我需要|帮我|能不能|可以吗|有没有办法|用什么功能|用哪个功能|在哪个|从哪|"
    r"如何获取|怎么获得|怎么看到|怎么查看|怎么制作|怎么创建|怎么添加|怎么导入|"
    r"有没有功能|什么功能|哪个模块|去哪",
    re.I,
)

_NAV_TO_INTENTS: dict[str, list[TutorialSemanticIntent]] = {}
for _intent in TUTORIAL_SEMANTIC_INTENTS:
    _NAV_TO_INTENTS.setdefault(_intent.nav_id, []).append(_intent)


def score_semantic_intent(text: str, nav_id: str) -> tuple[int, list[str]]:
    """返回 (分数, 命中的语义片段)。"""
    text = (text or "").strip()
    if not text:
        return 0, []
    hits: list[str] = []
    score = 0
    for intent in _NAV_TO_INTENTS.get(nav_id, []):
        for neg in intent.negative_patterns:
            if re.search(neg, text):
                return 0, []
        for phrase in intent.phrases:
            if phrase and phrase in text:
                hits.append(phrase)
                score += 14 + min(len(phrase), 12)
        for pat in intent.patterns:
            m = re.search(pat, text)
            if m:
                hits.append(m.group(0))
                score += 18
    return score, hits


def rank_semantic_nav_ids(text: str) -> list[tuple[str, int, list[str]]]:
    """按语义分数降序返回 [(nav_id, score, hits)]。"""
    seen: set[str] = set()
    ranked: list[tuple[str, int, list[str]]] = []
    for intent in TUTORIAL_SEMANTIC_INTENTS:
        if intent.nav_id in seen:
            continue
        seen.add(intent.nav_id)
        s, hits = score_semantic_intent(text, intent.nav_id)
        if s > 0:
            ranked.append((intent.nav_id, s, hits))
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked


def looks_like_goal_or_howto_question(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    from app.services.ai_chat_access import looks_like_concrete_data_request

    if looks_like_concrete_data_request(text):
        return False
    if _GOAL_TRIGGER.search(text):
        return True
    ranked = rank_semantic_nav_ids(text)
    return bool(ranked and ranked[0][1] >= 14)


def build_semantic_mapping_hint(text: str, nav_id: str, hits: list[str]) -> str:
    """生成「您想做的事 → 对应功能」说明。"""
    from app.services.ai_chat_tutorials import get_tutorial_by_nav_id

    tutorial = get_tutorial_by_nav_id(nav_id)
    if not tutorial:
        return ""
    goal = (text or "").strip().rstrip("？?。.")
    if hits:
        core = f"这属于系统中的 **{tutorial.jump_label}** 功能（与您描述相关的关键词：{'、'.join(hits[:3])}）。"
    else:
        core = f"建议使用系统中的 **{tutorial.jump_label}** 功能。"
    if goal and len(goal) <= 40:
        return f"您想「{goal}」，{core}"
    return f"根据您的描述，{core}"


def build_semantic_catalog_for_llm() -> str:
    """供千问分类的紧凑功能语义表。"""
    lines = [
        "nav_id | 功能名 | 用户意图说法示例",
        "------|--------|----------------",
    ]
    examples = {
        "ai-targeted": "个人分析报告、学情诊断、提升方案、补弱",
        "ai-review": "课堂讲评、讲错题、巩固练习、试卷评讲",
        "ai-layered": "分层作业、分层推送、按水平推送",
        "class-students": "学生画像、单个学生学情、全景画像",
        "analytics-portrait": "班级整体报告、成绩分布、班级学情",
        "analytics-grade": "年级对比、各班横向比较",
        "class-dashboard": "班级看板、班级总览",
        "settings-class": "建班、导入学生、花名册",
        "grading-start": "批改作业、扫描试卷、作文批改",
        "grading-errors": "查分数、批改结果、错题统计",
        "prep-lesson": "写教案、教学设计",
        "prep-exam": "组卷、出题、生成试卷",
        "prep-bank": "备课计划、教学日历",
        "prep-video": "课件资源、上传素材",
        "settings-subject": "知识点配置、评分标准",
        "settings-hardware": "打印机扫描仪",
        "settings-personal": "改密码、个人资料",
        "settings-preferences": "API配置、系统设置",
        "home": "首页工作台、新手入门",
    }
    from app.services.ai_chat_tutorials import FEATURE_TUTORIALS

    for t in FEATURE_TUTORIALS:
        ex = examples.get(t.nav_id, "")
        lines.append(f"{t.nav_id} | {t.jump_label} | {ex}")
    return "\n".join(lines)
