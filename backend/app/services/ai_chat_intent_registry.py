# -*- coding: utf-8 -*-
"""AI 助教：全模块语义意图注册表（用户不必说前端模块名）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# 常见学科，用于从问句提取过滤条件
SUBJECT_KEYWORDS = (
    "语文",
    "数学",
    "英语",
    "物理",
    "化学",
    "生物",
    "历史",
    "地理",
    "政治",
    "科学",
    "道德与法治",
    "信息技术",
    "音乐",
    "美术",
    "体育",
)


@dataclass(frozen=True)
class IntentRule:
    """一条意图规则：关键词/正则命中即认为用户在问该类数据。"""

    intent_id: str
    description: str
    keywords: tuple[str, ...] = ()
    patterns: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ()
    priority: int = 0
    data_source: str = "mysql"  # mysql | local | orm


INTENT_RULES: tuple[IntentRule, ...] = (
    # —— 班级 / 学生 ——
    IntentRule(
        "intent_class_count",
        "班级数量、某年级有几个班",
        patterns=(
            r"(多少|几个|有几|共有|一共).{0,12}(班级|个班)",
            r"(班级|个班).{0,8}(多少|几个|有几)",
            r"有几个班",
            r"(班级|年级).{0,6}(情况|概况|整体)",
        ),
        priority=20,
        data_source="orm",
    ),
    IntentRule(
        "intent_students_roster",
        "某班学生名单/花名册",
        keywords=("花名册", "名单"),
        patterns=(
            r"(班|班级).{0,8}(学生|名单|同学|花名册)",
            r"(学生|名单|同学).{0,8}(班|班级)",
            r"(有哪些|列出|列举).{0,8}(学生|同学)",
        ),
        exclude_patterns=(r"哪个班", r"在哪", r"哪个年级"),
        priority=18,
        data_source="orm",
    ),
    IntentRule(
        "intent_student_class",
        "某学生在哪个班",
        patterns=(
            r"(哪个|哪一个|什么|哪一).{0,6}(班|班级|年级)",
            r"(班|班级|年级).{0,6}(哪个|哪一个|什么)",
        ),
        priority=19,
        data_source="orm",
    ),
    IntentRule(
        "intent_student_profile",
        "学生学号、学籍号、班干部、座位等花名册信息",
        keywords=("学籍号", "学号", "班干部", "班干", "职务", "座位", "座号"),
        patterns=(
            r"学籍号",
            r"学号",
            r"班干部",
            r"班干",
            r"什么职务",
            r"担任.{0,6}(什么|啥|哪个)",
            r"座位",
            r"[\u4e00-\u9fa5·]{2,4}.{0,10}(学籍号|学号|班干部|班干)",
        ),
        priority=20,
        data_source="orm",
    ),
    # —— 教案 ——
    IntentRule(
        "intent_lesson_plans",
        "教案、备课、教学目标",
        keywords=("教案", "备课", "教学目标", "教学过程", "教学重点", "教学难点"),
        patterns=(
            r"写了.{0,6}教案",
            r"有哪些教案",
            r"教案.{0,6}(多少|几个|列表|清单)",
        ),
        priority=12,
    ),
    # —— 智能组卷 ——
    IntentRule(
        "intent_smart_exams",
        "组卷、试卷库、我的试卷",
        keywords=("组卷", "试卷库", "智能组卷", "我的试卷", "试卷列表"),
        patterns=(
            r"出了.{0,6}卷",
            r"有哪些试卷",
            r"试卷.{0,6}(多少|几个|列表)",
            r"保存了.{0,8}试卷",
        ),
        priority=12,
    ),
    # —— 靶向提升 ——
    IntentRule(
        "intent_targeted_reports",
        "靶向诊断、个人分析报告、提升方案",
        keywords=(
            "靶向",
            "诊断报告",
            "提升方案",
            "提升计划",
            "诊断结果",
            "个人分析",
            "个人分析报告",
            "分析报告",
            "学情分析",
        ),
        patterns=(
            r"靶向.{0,8}(报告|方案|诊断)",
            r"(诊断|提升).{0,6}方案",
            r"(个人|学情)分析报告",
            r"个人分析",
            r"[\u4e00-\u9fa5·]{2,4}.{0,16}(个人)?分析(报告)?",
            r"[\u4e00-\u9fa5·]{2,4}.{0,12}(数学|语文|英语|物理|化学|生物|历史|地理|政治).{0,12}(报告|分析|诊断|方案)",
        ),
        priority=17,
    ),
    IntentRule(
        "intent_targeted_recommendations",
        "靶向推荐关注学生",
        keywords=("推荐名单", "关注学生", "推荐学生"),
        patterns=(r"推荐.{0,6}(学生|名单)", r"需要关注.{0,6}学生"),
        priority=13,
    ),
    # —— 课堂讲评 ——
    IntentRule(
        "intent_class_review",
        "课堂讲评、巩固方案、课后反馈",
        keywords=(
            "课堂讲评",
            "讲评",
            "二次巩固",
            "巩固方案",
            "课前讲评",
            "课后反馈",
            "智能复习",
            "讲评内容",
            "讲评记录",
        ),
        patterns=(
            r"[0-9]{3,4}班?.{0,12}(数学|语文|英语|物理|化学|生物|历史|地理|政治).{0,12}(课堂)?讲评",
            r"(数学|语文|英语|物理|化学|生物|历史|地理|政治).{0,12}(课堂)?讲评",
            r"讲评.{0,8}(方案|记录|内容|报告)",
            r"巩固.{0,6}方案",
            r"[\u4e00-\u9fa5·]{0,4}(班|班级)?.{0,8}讲评",
        ),
        priority=17,
    ),
    # —— 学情 ——
    IntentRule(
        "intent_student_analysis",
        "学情、成绩趋势、目标分",
        keywords=("学情", "成绩趋势", "目标分", "历次成绩", "成绩历史", "学情报告"),
        patterns=(
            r"成绩.{0,6}(趋势|变化|历史)",
            r"目标.{0,4}分",
            r"[\u4e00-\u9fa5·]{2,4}.{0,12}学情",
        ),
        priority=14,
    ),
    # —— 知识点 ——
    IntentRule(
        "intent_knowledge_weak",
        "薄弱知识点、掌握度",
        keywords=("薄弱点", "薄弱知识点", "掌握度", "知识点"),
        patterns=(r"薄弱", r"掌握.{0,4}不好", r"哪些知识点"),
        # P0-B4c 消歧：knowledge_weak 的 keyword「知识点」会被「数学的知识树有哪些知识点」双命中，
        # 追加排除「知识树/知识图谱/知识点结构/考纲」，让该类问句干净地落 intent_knowledge_tree（改动最小方案）。
        exclude_patterns=(r"错题", r"知识树", r"知识图谱", r"知识点结构", r"考纲"),
        priority=10,
    ),
    # —— 批改档案（本地） ——
    IntentRule(
        "intent_student_exam_score",
        "某学生某次考试得多少分（批改详细/批改档案）",
        patterns=(
            r"[\u4e00-\u9fa5·]{2,4}的.{0,28}(考试|月考|期中|期末|测验|统考).{0,16}(多少分|几分|得分|考了多少)",
            r"(多少分|几分|考了多少|得分是多少).{0,28}(考试|月考|期中|期末|测验)",
            r"[\u4e00-\u9fa5·]{2,4}.{0,12}(考试|月考|期中|期末).{0,12}(多少分|几分|分数)",
        ),
        priority=17,
        data_source="local",
    ),
    IntentRule(
        "intent_grading_scores",
        "批改得分、排名、最高最低分（批改档案/批改详细，无需用户说界面名）",
        keywords=("批改详细", "批改档案", "批改结果"),
        patterns=(
            r"最高|最低|平均|均分|满分|多少分|得分|分数|考了多少|成绩",
            r"排第|前几名|谁最高|谁考得最好|排名|名次|排行|第几名",
            r"成绩怎么样|成绩情况|分数情况|考情",
            r"(班级|个班).{0,12}(考试|期中|期末).{0,12}(排名|成绩|分数|情况)",
            r"(排名|名次).{0,12}(考试|期中|期末|月考)",
        ),
        priority=18,
        data_source="local",
    ),
    IntentRule(
        "intent_grading_exams",
        "已批改考试列表",
        keywords=("批改",),
        patterns=(
            r"有哪些考试",
            r"哪些考试",
            r"批改了.{0,8}考试",
            r"考试.{0,6}(列表|清单)",
        ),
        exclude_patterns=(r"多少分", r"最高", r"最低", r"排名"),
        priority=9,
        data_source="local",
    ),
    IntentRule(
        "intent_grading_wrong",
        "批改档案中的错题",
        keywords=("错题", "错题本", "错因"),
        patterns=(r"错了哪些", r"哪些题错"),
        priority=15,
        data_source="local",
    ),
    IntentRule(
        "intent_grading_students",
        "批改档案中的学生",
        keywords=("批改",),
        patterns=(r"批改.{0,8}学生",),
        priority=8,
        data_source="local",
    ),
    # —— 教务登记（管理员） ——
    IntentRule(
        "intent_exam_registry",
        "系统登记的考试与成绩",
        keywords=("登记", "统考", "月考", "期中", "期末"),
        patterns=(
            r"系统.{0,6}考试",
            r"登记.{0,6}成绩",
        ),
        exclude_patterns=(r"批改", r"档案", r"多少分", r"几分", r"考了多少", r"得分", r"排名", r"名次", r"最高", r"最低", r"平均|均分"),
        priority=7,
    ),
    IntentRule(
        "intent_class_teachers",
        "班主任、任课教师",
        keywords=("班主任", "任课教师", "副班主任"),
        patterns=(r"谁.{0,4}班主任", r"教.{0,4}班"),
        priority=11,
    ),
    IntentRule(
        "intent_todo",
        "待办事项",
        keywords=("待办", "todo", "任务清单"),
        priority=5,
    ),
    IntentRule(
        "intent_prep_resources",
        "备课资源、教学资源",
        keywords=("备课资源", "教学资源", "课件"),
        priority=6,
    ),
    # —— 资产库（家长端 PG 只读）：题库检索 / 知识树 / 相似题（P0-B4c） ——
    IntentRule(
        "intent_question_bank",
        "题库检索、出题、例题/真题（家长端 PG 资产题库）",
        patterns=(
            r"(给我出|来几道|出几道|出\d+道|帮我出|出题|推荐.{0,4}题)",
            r"题库",
            r"(例题|真题)",
            r"(题目|题).{0,10}(有哪些|给我|找|列出|来|查|看看|看一下)",
            r"(有哪些|列出|列举).{0,6}(题目|例题|真题)",
        ),
        exclude_patterns=(
            r"错题", r"错因", r"错了哪些",
            r"排名|名次|排行",
            r"多少分|得分|成绩|考了多少",
            r"相似|变式",  # 相似题/变式题归 intent_similar_question
        ),
        priority=16,
        data_source="asset",
    ),
    IntentRule(
        "intent_knowledge_tree",
        "知识树、知识图谱、知识点结构、考纲（家长端 PG 资产知识点）",
        patterns=(
            r"(知识树|知识图谱|知识点结构|考纲)",
            r"有哪些知识点",
            r"知识点.{0,6}(有哪些|列表|目录|结构|框架|一览)",
            r"知识(树|图谱).{0,12}(有哪些|查|看)",
        ),
        exclude_patterns=(
            r"薄弱", r"掌握.{0,4}(不好|差|低)", r"不会", r"错题",
            r"排名|成绩|分数|得分",
        ),
        priority=11,
        data_source="asset",
    ),
    IntentRule(
        "intent_similar_question",
        "相似题、变式题、同类型题（家长端 PG 资产题库）",
        patterns=(
            r"(相似题|类似题|同类型题|变式题)",
            r"(相似|类似|变式).{0,4}(题|题目)",
            r"(出|找|来|推荐).{0,4}(相似|类似|变式).{0,3}(题|题目)",
        ),
        priority=14,
        data_source="asset",
    ),
)


def extract_subject_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    for subj in SUBJECT_KEYWORDS:
        if subj in text:
            return subj
    return None


def looks_like_count_question(text: str) -> bool:
    return bool(re.search(r"多少|几个|有几|共有|一共|数量|统计", text))


def looks_like_list_question(text: str) -> bool:
    return bool(re.search(r"有哪些|列出|列举|清单|列表|都有什么|有什么", text))


def _rule_matches(rule: IntentRule, text: str) -> bool:
    for pat in rule.exclude_patterns:
        if re.search(pat, text):
            return False
    if any(kw in text for kw in rule.keywords):
        return True
    return any(re.search(pat, text) for pat in rule.patterns)


def classify_intents(text: str, *, min_priority: int = 0) -> list[tuple[str, int]]:
    """返回命中的 intent_id 列表，按 priority 降序。"""
    text = (text or "").strip()
    if not text:
        return []
    hits: list[tuple[str, int]] = []
    seen: set[str] = set()
    for rule in sorted(INTENT_RULES, key=lambda r: r.priority, reverse=True):
        if rule.priority < min_priority:
            continue
        if rule.intent_id in seen:
            continue
        if _rule_matches(rule, text):
            hits.append((rule.intent_id, rule.priority))
            seen.add(rule.intent_id)
    return hits


def get_intent_rule(intent_id: str) -> Optional[IntentRule]:
    for rule in INTENT_RULES:
        if rule.intent_id == intent_id:
            return rule
    return None


def build_intent_hints_for_text(text: str) -> list[str]:
    """根据命中意图生成给大模型的 SQL/查数提示。"""
    text = (text or "").strip()
    if not text:
        return []

    hints: list[str] = []
    subject = extract_subject_from_text(text)
    subj_filter = f" AND subject LIKE '%{subject}%'" if subject else ""
    intents = [iid for iid, _ in classify_intents(text)]

    mapping = {
        "intent_class_count": (
            "- 问班级/年级数量 → `classes` 表，"
            "示例：SELECT grade, name, student_count FROM classes WHERE grade LIKE '%年级%' LIMIT 100"
        ),
        "intent_students_roster": (
            "- 问某班学生名单 → `students` JOIN `classes`，按班号 name 过滤"
        ),
        "intent_student_class": (
            "- 问学生在哪个班 → 使用预查花名册结果中的 class_name；"
            "或 `students` JOIN `classes`，**姓名必须精确匹配**"
        ),
        "intent_student_profile": (
            "- 问学号/学籍号/班干部/座位等 → 使用预查花名册 JSON 中的 student_number、"
            "cadre_role、class_name 等字段，**禁止猜测**；姓名须精确匹配 students.name"
        ),
        "intent_lesson_plans": (
            f"- 问教案/备课 → `lesson_plans`（当前账号，勿写 user_id）"
            f"{subj_filter or '，可按 subject 过滤'}"
        ),
        "intent_smart_exams": (
            f"- 问组卷/试卷 → `smart_exam_papers`（当前账号）"
            f"{subj_filter or ''}"
        ),
        "intent_targeted_reports": (
            f"- 问某学生靶向诊断/个人分析报告/提升方案 → `targeted_improvement_reports`"
            f"（SELECT student_name, subject, diagnosis_text, plan_text 等；数据在靶向提升模块生成）"
            f"{subj_filter or '，按 student_name、subject 过滤'}"
        ),
        "intent_targeted_recommendations": (
            f"- 问靶向推荐名单 → `targeted_recommendations`{subj_filter}"
        ),
        "intent_class_review": (
            f"- 问某班某学科课堂讲评 → 使用预查 JSON 中 session 的 consolidation、pre_class、"
            f"source_summary、post_feedback 等字段总结；"
            f"found 为 false 时必须说明未生成讲评，禁止编造"
            f"{subj_filter or '；按 class_id + subject 精确匹配'}"
        ),
        "intent_student_analysis": (
            "- 问学情/成绩趋势 → `student_score_history` 或 `student_analysis`"
        ),
        "intent_knowledge_weak": (
            "- 问薄弱知识点 → `knowledge_points` WHERE is_weak = 1"
        ),
        "intent_student_exam_score": (
            "- 问某学生某次考试多少分 → **必须**用 `execute_local_data_query` 查 `local_grading_scores`"
            "（数据来自批改详细/批改档案，不是 MySQL 教务成绩表）；"
            "示例：SELECT student_name, score, exam_title FROM local_grading_scores "
            "WHERE student_name LIKE '%姓名%' AND exam_title LIKE '%考试关键词%'"
        ),
        "intent_grading_scores": (
            "- 问某班/某次考试的**排名、均分、最高最低分、成绩概况** → **必须**用 `execute_local_data_query` "
            "查 `local_grading_scores`（数据来自**批改详细/批改档案**，用户不必说界面名；"
            "**不是** MySQL 教务表 exam_scores）；"
            "示例：SELECT student_name, score, exam_title, class_label FROM local_grading_scores "
            "WHERE exam_title LIKE '%期中%' ORDER BY score DESC LIMIT 30"
        ),
        "intent_grading_exams": (
            "- 问已批改考试 → `execute_local_data_query` 查 `local_exam_list`"
        ),
        "intent_grading_wrong": (
            "- 问错题 → `execute_local_data_query` 查 `local_ct_wrong_questions`"
        ),
        "intent_exam_registry": (
            "- 问系统登记考试/成绩 → `exams` JOIN `exam_scores`（管理员）"
        ),
        "intent_class_teachers": (
            "- 问班主任/任课 → 查 `class_teachers` + `classes`（禁止查 users 表）"
        ),
        "intent_todo": (
            "- 问待办 → `todo_items`"
        ),
        "intent_prep_resources": (
            "- 问教学资源 → `teaching_resources` 或 `prep_plans`"
        ),
        "intent_question_bank": (
            "- 问题目/出题/例题/真题 → 用 `execute_asset_query` 查家长端 PG 资产题库 "
            "`questions` 表（只读 SELECT，按 subject/grade 过滤，如 WHERE subject LIKE '%数学%'）"
        ),
        "intent_knowledge_tree": (
            "- 问知识树/知识图谱/考纲/知识点结构 → 用 `execute_asset_query` 查 "
            "`knowledge_points` JOIN `subject_units` 按学科返回知识点结构（只读 SELECT）"
        ),
        "intent_similar_question": (
            "- 问相似题/变式/同类型题 → 用 `execute_asset_query` 查 `questions` "
            "同知识点题（经 `question_kp` 桥接，只读 SELECT）"
        ),
    }

    for iid in intents:
        hint = mapping.get(iid)
        if hint and hint not in hints:
            hints.append(hint)

    if not hints:
        hints.append(
            "- 根据问句含义选表：班级→classes/students；教案→lesson_plans；"
            "组卷→smart_exam_papers；靶向→targeted_*；讲评→class_review_sessions；"
            "批改得分/错题→execute_local_data_query。"
        )
    return hints
