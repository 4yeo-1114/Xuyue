# -*- coding: utf-8 -*-
"""AI 助教：数据访问范围与问句解析（AI 助教对所有登录用户能力一致）。"""

from __future__ import annotations

import re
from typing import Optional

from sqlalchemy import asc, or_
from sqlalchemy.orm import Session

from app.models.class_model import Class
from app.models.class_teacher import ClassTeacher
from app.models.user import User

AI_CHAT_MYSQL_ADMIN_ROLES = frozenset({"系统管理员", "子系统管理员", "校级管理者"})

_GRADE_SHORT = {
    "一年级": "小学一年级",
    "二年级": "小学二年级",
    "三年级": "小学三年级",
    "四年级": "小学四年级",
    "五年级": "小学五年级",
    "六年级": "小学六年级",
    "初一": "初一年级",
    "初二": "初二年级",
    "初三": "初三年级",
    "高一": "高一年级",
    "高二": "高二年级",
    "高三": "高三年级",
}


def parse_user_roles(db: Session, user_id: str) -> list[str]:
    u = db.query(User).filter(User.id == user_id).first()
    if not u or not u.roles:
        return []
    return [r.strip() for r in u.roles.split(",") if r.strip()]


def is_ai_chat_mysql_admin(db: Session, user_id: str) -> bool:
    """M2：只有系统管理员/子系统管理员/校级管理者才具备 AI 助教 MySQL 全库（含教务表）查询权限。

    之前对任何登录用户都返回 True，等于绕过 ADMIN_ONLY_MYSQL_TABLES 限制。
    普通教师只能查 TEACHER_MYSQL_TABLES（自己的教案/组卷/班级数据）。
    """
    roles = parse_user_roles(db, user_id)
    return bool(set(roles) & AI_CHAT_MYSQL_ADMIN_ROLES)


def can_use_mysql_in_ai_chat(db: Session, user_id: str) -> bool:
    """AI 助教 MySQL 预查与工具查询对所有角色一致开放。"""
    return bool((user_id or "").strip())


def normalize_grade_label(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    if text in _GRADE_SHORT:
        return _GRADE_SHORT[text]
    if text.startswith("小学") or text.startswith("初") or text.startswith("高"):
        return text
    m = re.fullmatch(r"([一二三四五六])年级", text)
    if m:
        return f"小学{m.group(1)}年级"
    return text


def extract_grade_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    patterns = [
        r"小学[一二三四五六]年级",
        r"[初高][一二三]年级?",
        r"[一二三四五六]年级",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return normalize_grade_label(m.group(0))
    return None


_SKIP_NAME_WORDS = {
    "系统",
    "学生",
    "班级",
    "有没有",
    "多少",
    "几个",
    "年级",
    "小学",
    "中学",
    "哪位",
    "名字",
    "叫什么",
    "是否存在",
    "查询",
    "帮我",
    "请问",
    "批改详细",
    "详细界面",
    "批改界面",
    "批改",
}


def _normalize_extracted_name(name: str) -> Optional[str]:
    text = (name or "").strip()
    for prefix in ("查询", "查一下", "帮我查", "请问", "告诉我"):
        if text.startswith(prefix) and len(text) > len(prefix):
            text = text[len(prefix) :].strip()
    for suffix in (
        "是不是",
        "是否是",
        "期中考试",
        "期末考试",
        "单元测验",
        "期中",
        "期末",
        "月考",
        "周测",
        "单元",
        "考试",
        "测验",
        "期",
        "同学",
        "学生",
        "的",
        "是",
        "在",
    ):
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)].strip()
    if len(text) >= 2 and text not in _SKIP_NAME_WORDS:
        return text
    return None


def extract_student_name_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    patterns = [
        # 分数/考试类问句（优先）
        r"批改(?:详细)?(?:界面)?的([\u4e00-\u9fa5·]{2,3}?)(?:的)?(?:期中|期末|月考|周测|单元)?(?:考试|测验)?",
        r"^([\u4e00-\u9fa5·]{2,3})(?:的)?(?:期中|期末|月考|周测|单元|模拟|联考)",
        r"^([\u4e00-\u9fa5·]{2,3})(?:期中|期末|月考|周测|单元)(?:考试|测验|考)?",
        r"的([\u4e00-\u9fa5·]{2,3})的(?:期中|期末|月考|周测|单元)?(?:考试|测验)",
        r"^([\u4e00-\u9fa5·]{2,3})的.{0,12}(?:考试|测验|月考|期中|期末)",
        r"^([\u4e00-\u9fa5·]{2,3})(?:是|在|属于|读)?(?:哪|什么|哪个|哪一个)(?:个)?(?:班|班级|年级)",
        r"^([\u4e00-\u9fa5·]{2,4})(?:是|在|属于|读)?(?:哪|什么|哪个|哪一个)(?:个)?(?:班|班级|年级)",
        r"^([\u4e00-\u9fa5·]{2,4})(?:的)?(?:班|班级|年级)(?:是|在)?(?:哪|什么|哪个)",
        r"^([\u4e00-\u9fa5·]{2,4})(?:的)?(?:学籍号|学号|班干部|班干|职务|座位)",
        r"^([\u4e00-\u9fa5·]{2,4})(?:是不是|是否)(?:班)?班干部",
        r"查询([\u4e00-\u9fa5·]{2,4})(?:同学|学生)?(?:的)?(?:班级|学号|学籍号|班干部)?",
        r"([\u4e00-\u9fa5·]{2,4})(?:同学|学生)?(?:的)?(?:学籍号|学号|班干部|班干)(?:是|为|多少|什么)?",
        r"叫[「\"']?([\u4e00-\u9fa5·]{2,4})(?:这个|这名|那位|的|学生|同学|名字)?",
        r"有没有([\u4e00-\u9fa5·]{2,4})(?:这个|这名|那位)?(?:学生|同学)?",
        r"是否存在([\u4e00-\u9fa5·]{2,4})(?:这个|这名|那位)?(?:学生|同学)?",
        r"([\u4e00-\u9fa5·]{2,4})(?:这)?(?:名|位)(?:学生|同学)",
        r"学生(?:名叫|名字是|叫)[「\"']?([\u4e00-\u9fa5·]{2,4})",
        r"^([\u4e00-\u9fa5·]{2,4})(?:同学|学生)?[，,。?？\s]",
        r"^([\u4e00-\u9fa5·]{2,4})的",
    ]
    for pat in patterns:
        m = re.search(pat, text.strip())
        if not m:
            continue
        name = (m.group(1) or "").strip()
        cleaned = _normalize_extracted_name(name)
        if cleaned:
            return cleaned
    return None


def looks_like_student_class_question(text: str) -> bool:
    if not text:
        return False
    if looks_like_student_exam_score_question(text):
        return False
    return bool(re.search(r"(哪个|哪一个|什么|哪一).{0,6}(班|班级|年级)", text)) or bool(
        re.search(r"(班|班级|年级).{0,6}(哪个|哪一个|什么)", text)
    )


def extract_student_number_from_text(text: str) -> Optional[str]:
    """从问句提取学号/学籍号。"""
    if not text:
        return None
    patterns = [
        r"学号[是为：:\s]*([A-Za-z0-9\-]{3,32})",
        r"学籍号[是为：:\s]*([A-Za-z0-9\-]{3,32})",
        r"([0-9]{6,20})(?:号)?(?:学号|学籍)",
    ]
    for pat in patterns:
        m = re.search(pat, text.strip())
        if m:
            num = (m.group(1) or "").strip()
            if num:
                return num
    return None


def looks_like_student_profile_question(text: str) -> bool:
    """是否在问花名册中的学生个人信息（班级、学号、班干部等）。"""
    if not text:
        return False
    if looks_like_student_exam_score_question(text):
        return False
    if looks_like_grading_exam_stats_question(text):
        return False
    if looks_like_student_class_question(text):
        return True
    if extract_student_number_from_text(text):
        return True
    if re.search(r"学籍号|学号|班干部|班干|什么职务|担任什么|座位号|座号", text):
        return bool(extract_student_name_from_text(text) or extract_student_number_from_text(text))
    if extract_student_name_from_text(text) and re.search(
        r"学籍|学号|班干部|班干|职务|座位|性别|家长",
        text,
    ):
        return True
    return False


def looks_like_student_exam_score_question(text: str) -> bool:
    """是否在问某学生某次考试的得分（数据来源：批改档案 / 批改详细）。"""
    if not text:
        return False
    if looks_like_grading_exam_stats_question(text):
        return False
    if not re.search(
        r"多少分|几分|得多少|考了.{0,4}分|分数是多少|得分是多少|考了多少|得了多少|得分|分数",
        text,
    ):
        return False
    if re.search(r"考试|月考|期中|期末|测验|统考|周测|模拟|联考|单元", text):
        return True
    if extract_student_name_from_text(text):
        return True
    if re.search(r"^[\u4e00-\u9fa5·]{2,4}的", text.strip()):
        return True
    return False


def looks_like_grading_exam_stats_question(text: str) -> bool:
    """是否在问某班/某次考试的成绩概况、排名等（批改档案，无需说「批改详细」）。"""
    if not text:
        return False
    if re.search(r"怎么用|如何使用|怎么操作|如何操作|功能|教程|步骤|在哪看|在哪里看", text):
        return False
    has_stats = bool(
        re.search(
            r"排名|名次|排行|第几名|前几名|排第|谁最高|谁最低|谁考得最好|"
            r"最高|最低|平均|均分|及格|满分|分数段|分布|概况|情况怎么样|怎么样|"
            r"成绩情况|分数情况|考情|成绩单",
            text,
        )
    )
    has_score_word = bool(re.search(r"成绩|分数|得分", text))
    has_exam_ctx = bool(
        re.search(
            r"考试|测验|月考|期中|期末|周测|模拟|联考|单元|试卷|整场|这次|那场|某次|考",
            text,
        )
    )
    has_class_ctx = bool(
        extract_class_name_from_text(text)
        or extract_grade_from_text(text)
        or re.search(r"[0-9]{3,4}班|[一二三四五六七八九十]+年级", text)
        or re.search(r"(班级|个班)", text)
    )
    if has_stats and (has_exam_ctx or (has_class_ctx and has_score_word)):
        return True
    if re.search(r"(班级|个班).{0,16}(考试|期中|期末|月考).{0,16}(排名|成绩|分数|情况)", text):
        return True
    if re.search(r"(排名|名次|排行).{0,16}(考试|期中|期末|月考|测验)", text):
        return True
    if has_class_ctx and has_exam_ctx and has_score_word and re.search(r"哪些|谁|情况|统计", text):
        return True
    return False


def extract_exam_label_from_text(text: str) -> Optional[str]:
    """从问句提取考试名称关键词，如 期中、月考、第一单元测验。"""
    if not text:
        return None
    patterns = [
        r"[「\"']([^「」\"']{2,30})[」\"']",
        r"(?:的|在|参加)(期中|期末|月考|模拟|联考|单元(?:测|测试)?|周测|测验)",
        r"(期中|期末|月考|模拟|联考|单元(?:测|测试)?|周测)(?:考试|测验|统考)?",
        r"的([^的，,。?？\s]{2,24}?)(?:考试|测验|统考)(?:多少分|几分|得分|考了|多少)",
        r"(.{2,24}?)(?:这次|本场|此次|那场)?(?:的)?(?:考试|测验|月考|统考)(?:中|里|的)?",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        hint = (m.group(1) or "").strip()
        hint = re.sub(
            r"^(?:的|在|参加)|(?:多少分|几分|得分|分数|考了多少|是多少).*$",
            "",
            hint,
        ).strip()
        hint = re.sub(r"^[\u4e00-\u9fa5·]{2,4}的", "", hint).strip()
        hint = re.sub(r"^[0-9]{3,4}班?", "", hint).strip()
        hint = re.sub(r"^[一二三四五六七八九十]+年级?", "", hint).strip()
        if len(hint) >= 2 and hint not in {"这次", "那场", "哪次", "某次", "考试", "测验"}:
            return hint
    return None


def extract_score_query_context(text: str) -> tuple[Optional[str], Optional[str]]:
    """解析「某某的某次考试多少分」→ (学生姓名, 考试关键词)。"""
    text = (text or "").strip()
    if not text:
        return None, None
    name = extract_student_name_from_text(text)
    exam = extract_exam_label_from_text(text)
    return name, exam


def looks_like_class_count_question(text: str) -> bool:
    if not text:
        return False
    return bool(
        re.search(
            r"(多少|几个|有几|共有|一共).{0,12}(班级|个班|个班?)|"
            r"(班级|个班).{0,8}(多少|几个|有几)|"
            r"有几个班",
            text,
        )
    )


def extract_class_name_from_text(text: str) -> Optional[str]:
    """从问句中提取班级编号，如 2101班、2103。"""
    if not text:
        return None
    patterns = [
        r"([0-9]{3,4})班?",
        r"([一二三四五六七八九十百]+)[\(\（][0-9一二三四五六七八九十]+[\)\）]班?",
        r"([一二三四五六七八九十]+)班",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        label = (m.group(1) or "").strip()
        if label and label not in {"班", "班级"}:
            return label
    return None


def looks_like_class_roster_question(text: str) -> bool:
    """是否在问某班有哪些/列出学生名单。"""
    if not text:
        return False
    if not re.search(r"学生|名单|花名册|同学|有哪些|列出|列举|全部|所有", text):
        return False
    return bool(extract_class_name_from_text(text)) or bool(re.search(r"(班|班级).{0,8}(学生|名单|同学)", text))


_PURE_HOWTO_PATTERN = re.compile(
    r"怎么用|如何使用|怎么使用|怎么操作|如何操作|教程|使用说明|功能介绍|"
    r"在哪里|在哪(?!个)|如何去|怎么进入|怎么打开|步骤|操作流程|"
    r"有什么功能|能做什么|有哪些功能|新手|入门|"
    r"如何批改|怎么批改|如何组卷|怎么组卷|如何备课|怎么备课|用哪个功能|什么功能|哪个模块",
    re.I,
)

_DATA_SEEKING_PATTERN = re.compile(
    r"查(询)?|看看|告诉我|总结|汇总|列出|列举|有哪些|是什么|什么情况|怎么样|"
    r"内容(是什么|有哪些)?|结果|记录|数据|报告|方案|诊断|分析",
    re.I,
)

_CONCRETE_ARTIFACT_KEYWORDS = (
    "分析报告",
    "个人分析报告",
    "个人分析",
    "学情分析",
    "诊断报告",
    "提升方案",
    "提升计划",
    "诊断结果",
    "靶向",
    "讲评方案",
    "巩固方案",
    "课堂讲评",
    "讲评方案",
    "讲评内容",
    "巩固方案",
    "教案",
    "试卷",
    "组卷",
    "推荐名单",
    "学情",
    "成绩趋势",
    "错题",
    "批改结果",
    "薄弱点",
    "学籍号",
    "学号",
    "班干部",
)


def looks_like_concrete_data_request(text: str) -> bool:
    """用户是否在要**具体业务数据**（查库/查档案），而非功能怎么用。"""
    s = (text or "").strip()
    if not s:
        return False

    if looks_like_student_exam_score_question(s) or looks_like_grading_exam_stats_question(s):
        return True

    from app.services.ai_chat_intent_registry import classify_intents, extract_subject_from_text

    name = extract_student_name_from_text(s)
    class_label = extract_class_name_from_text(s)

    # 「XX是什么」且无具体学生/班级 → 功能介绍，非查数
    if re.search(r"是什么|什么意思|啥意思|干什么|做什么", s) and not name and not class_label:
        if not re.search(r"查|查询|告诉我|总结|汇总|列出|内容", s):
            return False

    subject = extract_subject_from_text(s)
    has_artifact = any(k in s for k in _CONCRETE_ARTIFACT_KEYWORDS)
    seeks_data = bool(_DATA_SEEKING_PATTERN.search(s))
    pure_howto = bool(_PURE_HOWTO_PATTERN.search(s))
    intents = classify_intents(s)

    # 某学生 + 学科/报告/查数语义 → 要该生的具体记录
    if name and (has_artifact or seeks_data or subject):
        return True

    # 明确要某类业务记录（报告、方案、讲评等）
    if has_artifact and (seeks_data or name or class_label):
        return True

    if intents:
        # 仅问「怎么用 / 是什么」且无具体查询对象 → 教程
        if pure_howto and not seeks_data and not name and not class_label:
            return False
        if re.search(r"是什么|什么意思|啥意思|干什么|做什么", s) and not name and not seeks_data and not class_label:
            return False
        return True

    if looks_like_class_count_question(s) or looks_like_class_roster_question(s):
        return True
    if name and looks_like_student_class_question(s):
        return True
    if looks_like_student_profile_question(s):
        return True
    from app.services.ai_chat_class_review import looks_like_class_review_data_question

    if looks_like_class_review_data_question(s):
        return True

    return False


def looks_like_data_question(text: str) -> bool:
    if not text:
        return False
    if looks_like_concrete_data_request(text):
        return True
    from app.services.ai_chat_intent_registry import classify_intents

    if classify_intents(text):
        return True
    if looks_like_student_exam_score_question(text):
        return True
    if looks_like_grading_exam_stats_question(text):
        return True
    if looks_like_class_count_question(text):
        return True
    if looks_like_class_roster_question(text):
        return True
    if extract_student_name_from_text(text):
        return True
    if looks_like_student_class_question(text):
        return True
    keywords = (
        "学生", "班级", "年级", "错题", "知识点", "成绩", "考试", "组卷", "题目", "批改",
        "分数", "得分", "最高", "最低", "平均", "排名", "教案", "备课", "靶向", "讲评",
        "巩固", "学情", "试卷", "待办", "班主任", "任课", "诊断", "提升", "薄弱",
    )
    return any(k in text for k in keywords)


def get_accessible_classes(
    db: Session,
    user_id: str,
    *,
    grade: Optional[str] = None,
    school_level: Optional[str] = None,
    class_id: Optional[str] = None,
    mysql_unrestricted: bool = False,
) -> list[Class]:
    """mysql_unrestricted=True 时返回全库班级；AI 助教预查默认对全部用户开放。"""
    grade_norm = normalize_grade_label(grade) if grade else None

    if mysql_unrestricted:
        q = db.query(Class)
    else:
        owned_ids = {c.id for c in db.query(Class.id).filter(Class.user_id == user_id).all()}
        invited_ids = {
            r.class_id
            for r in db.query(ClassTeacher.class_id).filter(ClassTeacher.user_id == user_id).all()
        }
        class_ids = list(owned_ids | invited_ids)
        if not class_ids:
            return []
        q = db.query(Class).filter(Class.id.in_(class_ids))

    if school_level:
        q = q.filter(Class.school_level == school_level)
    if grade_norm:
        short = grade_norm.replace("小学", "")
        q = q.filter(
            or_(
                Class.grade == grade_norm,
                Class.grade == short,
                Class.grade.like(f"%{short}%"),
            )
        )
    if class_id:
        q = q.filter(Class.id == class_id)

    return q.order_by(asc(Class.grade), asc(Class.name)).all()


def get_accessible_class_ids(
    db: Session,
    user_id: str,
    *,
    grade: Optional[str] = None,
    school_level: Optional[str] = None,
    class_id: Optional[str] = None,
    mysql_unrestricted: bool = False,
) -> list[str]:
    return [
        c.id
        for c in get_accessible_classes(
            db,
            user_id,
            grade=grade,
            school_level=school_level,
            class_id=class_id,
            mysql_unrestricted=mysql_unrestricted,
        )
    ]
