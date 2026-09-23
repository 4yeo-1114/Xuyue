# -*- coding: utf-8 -*-
"""AI 助教：MySQL 查询按角色限定表与行范围。"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.services.ai_chat_access import get_accessible_class_ids, is_ai_chat_mysql_admin
from app.services.ai_chat_sql_utils import extract_sql_tables, inject_scope_conditions

MYSQL_ALLOWED_TABLES = frozenset(
    {
        "classes",
        "students",
        "exams",
        "exam_scores",
        "wrong_questions",
        "knowledge_points",
        "smart_exam_papers",
        "class_teachers",
        "subject_units",
        "exam_question_templates",
        "student_analysis",
        "student_score_history",
        "student_wrong_questions",
        "lesson_plans",
        "prep_plans",
        "teaching_resources",
        "essay_rubrics",
        "class_review_sessions",
        "targeted_improvement_reports",
        "targeted_recommendations",
        "grading_daily_stats",
        "todo_items",
        "system_config",
        "feature_flags",
    }
)

# 教案、智能组卷：与前端一致，严格按登录账号隔离（管理员也不能查他人试卷/教案）
ACCOUNT_ISOLATED_TABLES = frozenset(
    {
        "lesson_plans",
        "smart_exam_papers",
        "exam_question_templates",
    }
)

# 普通教师其他按 user_id 隔离的表
OTHER_USER_SCOPED_TABLES = frozenset(
    {
        "knowledge_points",
        "subject_units",
        "prep_plans",
        "teaching_resources",
        "essay_rubrics",
        "grading_daily_stats",
        "todo_items",
    }
)

USER_ID_SCOPED_TABLES = ACCOUNT_ISOLATED_TABLES | OTHER_USER_SCOPED_TABLES

CLASS_ID_SCOPED_TABLES = frozenset(
    {
        "class_review_sessions",
        "targeted_improvement_reports",
        "targeted_recommendations",
        "student_analysis",
        "student_score_history",
        "student_wrong_questions",
    }
)

TEACHER_MYSQL_TABLES = (
    USER_ID_SCOPED_TABLES
    | CLASS_ID_SCOPED_TABLES
    | frozenset({"classes", "students", "class_teachers"})
)

ADMIN_ONLY_MYSQL_TABLES = frozenset(
    {
        "exams",
        "exam_scores",
        "wrong_questions",
        "system_config",
        "feature_flags",
    }
)

_USER_ID_EQ_PATTERN = re.compile(r"\b(\w+\.)?user_id\s*=\s*'([^']*)'", re.IGNORECASE)


def get_mysql_allowed_tables(db: Session, user_id: str) -> frozenset[str]:
    if is_ai_chat_mysql_admin(db, user_id):
        return MYSQL_ALLOWED_TABLES
    return TEACHER_MYSQL_TABLES


def _sql_literal(value: str) -> str:
    return (value or "").replace("'", "''")


def _validate_account_isolated_sql(sql: str, user_id: str) -> None:
    """禁止在教案/组卷查询中指定其它账号的 user_id。"""
    tables = extract_sql_tables(sql)
    if not tables & ACCOUNT_ISOLATED_TABLES:
        return
    uid = (user_id or "").strip()
    for m in _USER_ID_EQ_PATTERN.finditer(sql):
        if m.group(2) != uid:
            raise ValueError(
                "教案与智能组卷按账号隔离，只能查询当前登录账号的数据，不可指定其他 user_id。"
            )


def apply_mysql_query_scope(db: Session, user_id: str, sql: str, *, admin: bool) -> str:
    """注入行级过滤：教案/组卷始终限定当前账号；普通教师另加班级等范围。"""
    _validate_account_isolated_sql(sql, user_id)
    tables = extract_sql_tables(sql)
    conditions: list[str] = []
    uid = _sql_literal(user_id)

    for table in sorted(tables & ACCOUNT_ISOLATED_TABLES):
        conditions.append(f"{table}.user_id = '{uid}'")

    if not admin:
        for table in sorted(tables & OTHER_USER_SCOPED_TABLES):
            conditions.append(f"{table}.user_id = '{uid}'")

        class_ids = get_accessible_class_ids(db, user_id, mysql_unrestricted=False)
        if tables & CLASS_ID_SCOPED_TABLES:
            if not class_ids:
                conditions.append("1=0")
            else:
                id_list = ",".join(f"'{_sql_literal(cid)}'" for cid in class_ids)
                for table in sorted(tables & CLASS_ID_SCOPED_TABLES):
                    conditions.append(f"{table}.class_id IN ({id_list})")

        if "classes" in tables:
            if not class_ids:
                conditions.append("1=0")
            else:
                id_list = ",".join(f"'{_sql_literal(cid)}'" for cid in class_ids)
                conditions.append(f"classes.id IN ({id_list})")

        if "students" in tables:
            if not class_ids:
                conditions.append("1=0")
            else:
                id_list = ",".join(f"'{_sql_literal(cid)}'" for cid in class_ids)
                conditions.append(f"students.class_id IN ({id_list})")

        if "class_teachers" in tables:
            conditions.append(f"class_teachers.user_id = '{uid}'")

    return inject_scope_conditions(sql, conditions)
