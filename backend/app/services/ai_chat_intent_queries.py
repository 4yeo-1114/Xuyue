# -*- coding: utf-8 -*-
"""AI 助教：根据问句语义自动查库（全模块，无需用户指明前端界面）。"""

from __future__ import annotations

import re
from typing import Any, Callable, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.class_model import Class
from app.models.class_teacher import ClassTeacher
from app.models.student import Student
from app.models.user import User
from app.services.ai_chat_access import (
    can_use_mysql_in_ai_chat,
    extract_class_name_from_text,
    extract_exam_label_from_text,
    extract_grade_from_text,
    extract_score_query_context,
    extract_student_name_from_text,
    extract_student_number_from_text,
    get_accessible_classes,
    looks_like_class_count_question,
    looks_like_class_roster_question,
    looks_like_concrete_data_request,
    looks_like_data_question,
    looks_like_grading_exam_stats_question,
    looks_like_student_class_question,
    looks_like_student_exam_score_question,
    looks_like_student_profile_question,
    normalize_grade_label,
)
from app.services.ai_chat_student_roster import infer_profile_fields_from_text, lookup_students_in_roster
from app.services.ai_chat_class_review import lookup_class_review_sessions, looks_like_class_review_data_question
from app.services.ai_chat_grading_tools import execute_grading_data_tool
from app.services.ai_chat_intent_registry import (
    build_intent_hints_for_text,
    classify_intents,
    extract_subject_from_text,
    looks_like_count_question,
    looks_like_list_question,
)
from app.services.ai_chat_local_exam import query_student_exam_score
from app.services.ai_chat_mysql_executor import execute_mysql_query
from app.services.ai_chat_local_executor import execute_local_data_query
from app.services.ai_chat_privacy import looks_like_user_account_privacy_question


def extract_exam_hint_from_text(text: str) -> str:
    if not text:
        return ""
    patterns = [
        r"[「\"']([^「」\"']{2,30})[」\"'].*?(?:考试|测验|统考|月考|期中|期末)",
        r"(.{2,24}?)(?:这次|本场|此次|那场|哪次)?(?:的)?(?:考试|测验|月考|统考)(?:中|里|的)?",
        r"(期中|期末|单元|月考|模拟|联考)[^\s，,。?？]{0,12}",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        hint = (m.group(1) or "").strip()
        hint = re.sub(r"(最高|最低|平均|分数|得分|成绩|多少|是谁|哪一位).*$", "", hint).strip()
        if len(hint) >= 2 and hint not in {"这次", "那场", "哪次", "某次"}:
            return hint
    return ""


def looks_like_score_question(text: str) -> bool:
    if not text:
        return False
    from app.services.ai_chat_access import looks_like_grading_exam_stats_question

    if looks_like_grading_exam_stats_question(text):
        return True
    return bool(
        re.search(
            r"最高|最低|平均|均分|满分|多少分|得分|分数|考了多少|排第|前几名|谁最高|谁考得最好|"
            r"排名|名次|排行|成绩怎么样|成绩情况|分数情况",
            text,
        )
    )


def _class_display(cls: Class) -> str:
    grade = (cls.grade or "").replace("小学", "").strip()
    name = (cls.name or "").strip()
    if grade and name:
        return f"{grade}{name}班" if not name.endswith("班") else f"{grade}{name}"
    return name or str(cls.id)


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not payload.get("success"):
        return []
    rows = payload.get("rows")
    return rows if isinstance(rows, list) else []


def _format_count_list_reply(
    label: str,
    payload: dict[str, Any],
    *,
    title_key: str = "title",
    count_key: str = "cnt",
    direct: bool = True,
) -> dict[str, Any]:
    """为简单统计/列表查询附加 mandatory_reply。"""
    rows = _rows(payload)
    if not payload.get("success"):
        return payload
    if len(rows) == 1 and count_key in (rows[0] or {}):
        cnt = rows[0].get(count_key) or rows[0].get("COUNT(*)") or 0
        payload = {
            **payload,
            "mandatory_reply": f"您共有 {int(cnt)} 条{label}记录。",
            "direct_answer": direct,
        }
        return payload
    if not rows:
        payload = {
            **payload,
            "mandatory_reply": f"未查询到相关{label}记录。",
            "direct_answer": direct,
        }
        return payload
    titles = [str(r.get(title_key) or r.get("name") or "") for r in rows if r.get(title_key) or r.get("name")]
    titles = [t for t in titles if t][:15]
    if titles:
        payload = {
            **payload,
            "mandatory_reply": f"查询到 {len(rows)} 条{label}：" + "、".join(titles) + "。",
            "direct_answer": direct and len(titles) <= 10,
        }
    return payload


def intent_query_class_count(db: Session, user_id: str, grade: Optional[str] = None) -> dict[str, Any]:
    admin = can_use_mysql_in_ai_chat(db, user_id)
    grade_norm = normalize_grade_label(grade) if grade else None
    classes = get_accessible_classes(
        db,
        user_id,
        grade=grade_norm,
        mysql_unrestricted=admin,
    )
    items = [
        {
            "class_id": c.id,
            "grade": c.grade,
            "name": c.name,
            "student_count": c.student_count or 0,
            "label": _class_display(c),
        }
        for c in classes
    ]
    count = len(classes)
    if grade_norm:
        if count == 0:
            reply = f"未查询到「{grade_norm}」的班级记录。"
        else:
            labels = "、".join(it["label"] for it in items[:30])
            suffix = f"（{labels}）" if labels else ""
            reply = f"「{grade_norm}」共有 {count} 个班级{suffix}。"
    else:
        reply = f"您可访问的班级共有 {count} 个。" if count else "未查询到可访问的班级记录。"
    return {
        "success": True,
        "class_count": count,
        "grade": grade_norm,
        "classes": items,
        "mandatory_reply": reply,
        "direct_answer": True,
    }


def _match_class_token(cls: Class, token: str) -> bool:
    if not token:
        return True
    token = token.strip().rstrip("班")
    name = (cls.name or "").strip().rstrip("班")
    label = _class_display(cls).replace("班", "").strip()
    if token == name or token == label:
        return True
    if token.isdigit():
        for field in (name, label):
            if not field:
                continue
            digit_groups = re.findall(r"\d+", field)
            if token in digit_groups:
                return True
        return False
    return token in name or name.endswith(token) or token in label or label.endswith(token)


def _resolve_class_id_from_label(db: Session, user_id: str, class_label: str) -> tuple[Optional[str], str]:
    """将问句中的班号/班级名解析为 class_id 与展示名。"""
    token = (class_label or "").strip().rstrip("班")
    if not token:
        return None, ""
    admin = can_use_mysql_in_ai_chat(db, user_id)
    accessible = get_accessible_classes(db, user_id, mysql_unrestricted=admin)
    matched = [c for c in accessible if _match_class_token(c, token)]
    if not matched:
        return None, class_label
    if len(matched) > 1 and token.isdigit():
        exact = [
            c
            for c in matched
            if token in re.findall(r"\d+", _class_display(c).replace("班", ""))
            or token in re.findall(r"\d+", (c.name or "").replace("班", ""))
        ]
        if len(exact) == 1:
            matched = exact
    cls = matched[0]
    return cls.id, _class_display(cls)


def intent_query_student_profile(
    db: Session,
    user_id: str,
    *,
    student_name: Optional[str] = None,
    student_number: Optional[str] = None,
    class_id: Optional[str] = None,
    class_name: Optional[str] = None,
    user_text: str = "",
) -> dict[str, Any]:
    """精确查询学生花名册：班级、学号、班干部等。"""
    name = (student_name or "").strip()
    number = (student_number or "").strip()
    if not name and not number and user_text:
        name = (extract_student_name_from_text(user_text) or "").strip()
        number = (extract_student_number_from_text(user_text) or "").strip()

    result = lookup_students_in_roster(
        db,
        user_id,
        student_name=name or None,
        student_number=number or None,
        class_id=class_id,
        class_name=class_name,
        exact_only=True,
    )
    fields = infer_profile_fields_from_text(user_text)
    if fields:
        result["requested_fields"] = fields
    return result


def intent_query_students_mysql(
    db: Session,
    user_id: str,
    *,
    search: Optional[str] = None,
    class_name: Optional[str] = None,
    list_roster: bool = False,
) -> dict[str, Any]:
    admin = can_use_mysql_in_ai_chat(db, user_id)
    accessible = get_accessible_classes(db, user_id, mysql_unrestricted=admin)
    if not accessible:
        return {
            "success": True,
            "found": False,
            "students": [],
            "student_names": [],
            "mandatory_reply": "未查询到可访问班级下的学生记录。",
            "direct_answer": True,
        }

    class_ids = [c.id for c in accessible]
    token = (class_name or "").rstrip("班") if class_name else ""

    if search and not list_roster:
        profile = lookup_students_in_roster(
            db,
            user_id,
            student_name=search,
            class_name=class_name,
            exact_only=True,
        )
        profile["query"] = "student_search"
        return profile

    if list_roster and token:
        matched = [c for c in accessible if _match_class_token(c, token)]
        if not matched:
            return {
                "success": True,
                "found": False,
                "class_name": class_name,
                "students": [],
                "student_names": [],
                "mandatory_reply": f"未找到「{class_name}」班或未登记学生。",
                "direct_answer": True,
            }
        target_ids = [c.id for c in matched]
        class_label = _class_display(matched[0])
    else:
        target_ids = class_ids
        class_label = ""

    q = db.query(Student, Class).join(Class, Student.class_id == Class.id).filter(
        Student.class_id.in_(target_ids)
    )

    rows = q.order_by(Class.grade, Class.name, Student.name).limit(200).all()
    students = [
        {
            "name": s.name,
            "class_name": _class_display(c),
            "student_number": s.student_number,
            "cadre_role": s.cadre_role,
            "gender": s.gender,
        }
        for s, c in rows
    ]
    names = [s["name"] for s in students if s.get("name")]

    if list_roster and token:
        if names:
            cls_name = class_label or class_name or token
            return {
                "success": True,
                "found": True,
                "class_name": cls_name,
                "students": students,
                "student_names": names,
                "total": len(names),
                "mandatory_reply": f"「{cls_name}」共有 {len(names)} 名学生：{'、'.join(names)}。",
                "direct_answer": True,
            }
        return {
            "success": True,
            "found": False,
            "class_name": class_name,
            "students": [],
            "student_names": [],
            "mandatory_reply": f"未找到「{class_name}」班或未登记学生。",
            "direct_answer": True,
        }

    return {
        "success": True,
        "found": bool(students),
        "students": students,
    }


def _mysql_list_or_count(
    db: Session,
    user_id: str,
    *,
    table: str,
    label: str,
    subject: Optional[str] = None,
    student_name: Optional[str] = None,
    extra_where: str = "",
    title_key: str = "title",
    mode: str = "list",
    order_by: str = "updated_at DESC",
    direct_on_empty: bool = True,
) -> dict[str, Any]:
    where_parts: list[str] = []
    params: dict[str, Any] = {}
    if subject:
        where_parts.append("subject LIKE :subject")
        params["subject"] = f"%{subject}%"
    if student_name:
        where_parts.append("student_name LIKE :student_name")
        params["student_name"] = f"%{student_name}%"
    if extra_where:
        where_parts.append(extra_where)
    where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

    if mode == "count":
        sql = f"SELECT COUNT(*) AS cnt FROM {table}{where_sql}"
    else:
        sql = f"SELECT * FROM {table}{where_sql} ORDER BY {order_by} LIMIT 20"

    payload = execute_mysql_query(db, user_id, sql, params=params)
    return _format_count_list_reply(
        label,
        payload,
        title_key=title_key,
        direct=direct_on_empty or mode == "count",
    )


def intent_query_lesson_plans(
    db: Session, user_id: str, *, subject: Optional[str] = None, mode: str = "list"
) -> dict[str, Any]:
    return _mysql_list_or_count(
        db,
        user_id,
        table="lesson_plans",
        label="教案",
        subject=subject,
        mode=mode,
        title_key="title",
    )


def intent_query_smart_exams(
    db: Session, user_id: str, *, subject: Optional[str] = None, mode: str = "list"
) -> dict[str, Any]:
    return _mysql_list_or_count(
        db,
        user_id,
        table="smart_exam_papers",
        label="试卷",
        subject=subject,
        mode=mode,
        title_key="title",
    )


def intent_query_targeted_reports(
    db: Session,
    user_id: str,
    *,
    subject: Optional[str] = None,
    student_name: Optional[str] = None,
    mode: str = "list",
) -> dict[str, Any]:
    return _mysql_list_or_count(
        db,
        user_id,
        table="targeted_improvement_reports",
        label="靶向提升报告",
        subject=subject,
        student_name=student_name,
        mode=mode,
        title_key="student_name",
        order_by="generated_at DESC",
        direct_on_empty=True,
    )


def intent_query_targeted_recommendations(
    db: Session, user_id: str, *, subject: Optional[str] = None, mode: str = "list"
) -> dict[str, Any]:
    return _mysql_list_or_count(
        db,
        user_id,
        table="targeted_recommendations",
        label="靶向推荐名单",
        subject=subject,
        mode=mode,
        title_key="subject",
        order_by="updated_at DESC",
    )


def intent_query_class_review(
    db: Session,
    user_id: str,
    *,
    subject: Optional[str] = None,
    class_id: Optional[str] = None,
    class_name: Optional[str] = None,
    mode: str = "list",
    user_text: str = "",
) -> dict[str, Any]:
    """查询某班某学科的课堂讲评完整内容（ORM，含 consolidation 等）。"""
    if mode == "count":
        return _mysql_list_or_count(
            db,
            user_id,
            table="class_review_sessions",
            label="课堂讲评",
            subject=subject,
            mode="count",
            title_key="title",
            order_by="generated_at DESC",
        )
    return lookup_class_review_sessions(
        db,
        user_id,
        subject=subject,
        class_id=class_id,
        class_name=class_name,
        user_text=user_text,
    )


def intent_query_student_analysis(
    db: Session,
    user_id: str,
    *,
    subject: Optional[str] = None,
    student_name: Optional[str] = None,
    mode: str = "list",
    use_history: bool = False,
) -> dict[str, Any]:
    table = "student_score_history" if use_history else "student_analysis"
    order = "created_at DESC" if use_history else "updated_at DESC"
    return _mysql_list_or_count(
        db,
        user_id,
        table=table,
        label="学情",
        subject=subject,
        student_name=student_name,
        mode=mode,
        title_key="student_name",
        order_by=order,
    )


def intent_query_knowledge_weak(db: Session, user_id: str, *, subject: Optional[str] = None) -> dict[str, Any]:
    from app.config import settings

    # 双引擎兼容（P3 业务库迁移 F1b）：MySQL 布尔用 1，PG 用 true
    where = "is_weak = true" if settings.db_engine == "postgresql" else "is_weak = 1"
    params: dict[str, Any] = {}
    if subject:
        where += " AND subject LIKE :subject"
        params["subject"] = f"%{subject}%"
    sql = (
        f"SELECT subject, code, name, mastery, is_weak "
        f"FROM knowledge_points WHERE {where} ORDER BY mastery ASC LIMIT 50"
    )
    payload = execute_mysql_query(db, user_id, sql, params=params)
    rows = _rows(payload)
    if payload.get("success") and not rows:
        payload["mandatory_reply"] = "未查询到薄弱知识点记录。"
        payload["direct_answer"] = True
    elif rows:
        names = [str(r.get("name") or "") for r in rows[:10] if r.get("name")]
        if names:
            payload["mandatory_reply"] = f"薄弱知识点包括：{'、'.join(names)}等，共 {len(rows)} 条。"
            payload["direct_answer"] = len(names) <= 8
    return payload


def _asset_query_rows(fn, *args, **kwargs) -> dict[str, Any]:
    """执行资产库只读查询，未启用/异常时优雅降级（绝不抛 500）。"""
    from app.config import settings

    if not settings.ASSETS_DB_ENABLED:
        return {"success": False, "error": "资产库未启用", "rows": [], "row_count": 0}
    try:
        rows = fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001 - 资产库不可达时降级，不抛 500
        return {"success": False, "error": f"资产库查询失败: {e}", "rows": [], "row_count": 0}
    rows = rows or []
    # 防御性兜底：统一剥列管线（repo 白名单列时零效果；未来 repo 新增
    # ASSET_SENSITIVE_COLUMNS 敏感列时自动剥离，防漂移泄敏）
    from app.services.ai_chat_asset_scope import ASSET_SENSITIVE_COLUMNS
    from app.services.ai_chat_datasource import strip_sensitive_columns

    rows = strip_sensitive_columns(rows, ASSET_SENSITIVE_COLUMNS)
    return {"success": True, "rows": rows, "row_count": len(rows)}


def intent_query_asset_question_bank(
    user_id: str, *, subject: Optional[str] = None, grade: Optional[str] = None
) -> dict[str, Any]:
    """题库检索/出题（家长端 PG 资产 questions 表，只读）。grade 为中文学段（小学/初中/高中/大学）。"""
    from app.assets import repo

    if not subject:
        return {
            "success": False,
            "error": "缺少学科参数",
            "rows": [],
            "row_count": 0,
            "mandatory_reply": "请补充学科（如数学/物理）后再出题。",
            "direct_answer": True,
        }
    limit = 5
    if grade:
        payload = _asset_query_rows(repo.get_random_questions, subject, grade, limit)
    else:
        payload = _asset_query_rows(repo.get_questions, subject, limit)
    rows = payload.get("rows") or []
    if payload.get("success"):
        brief = [
            {
                "id": r.get("id"),
                "subject": r.get("subject"),
                "grade": r.get("grade"),
                "question_type": r.get("question_type"),
                "question": r.get("question"),
                "options": r.get("options"),
            }
            for r in rows
        ]
        payload["rows"] = brief
        payload["row_count"] = len(brief)
        if brief:
            payload["mandatory_reply"] = f"已从资产题库检索到 {len(brief)} 道{subject or ''}题。"
            payload["direct_answer"] = True
        else:
            payload["mandatory_reply"] = "未查询到符合条件的题目记录。"
            payload["direct_answer"] = True
    return payload


def intent_query_asset_knowledge_tree(
    user_id: str, *, subject: Optional[str] = None
) -> dict[str, Any]:
    """知识树/知识点结构（家长端 PG knowledge_points JOIN subject_units，只读）。"""
    from app.assets import repo

    if not subject:
        return {
            "success": False,
            "error": "缺少学科参数",
            "rows": [],
            "row_count": 0,
            "mandatory_reply": "请补充学科后再查知识点树。",
            "direct_answer": True,
        }
    payload = _asset_query_rows(repo.get_kp_tree, subject)
    rows = payload.get("rows") or []
    if payload.get("success"):
        if rows:
            names = [str(r.get("name") or "") for r in rows[:20] if r.get("name")]
            suffix = "等。" if len(names) > 15 else "。"
            payload["mandatory_reply"] = (
                f"「{subject}」知识点树共 {len(rows)} 个节点：{'、'.join(names[:15])}{suffix}"
            )
            payload["direct_answer"] = True
        else:
            payload["mandatory_reply"] = f"未查询到「{subject}」的知识点树。"
            payload["direct_answer"] = True
    return payload


def intent_query_asset_similar_questions(
    user_id: str, *, text: str, subject: Optional[str] = None
) -> dict[str, Any]:
    """相似题（MVP 简版：候选集内 difflib 文本相似度 top N，家长端 PG 资产题库，只读）。"""
    import difflib

    from app.assets import repo

    query_text = (text or "").strip()
    if not subject:
        return {
            "success": False,
            "error": "缺少学科参数",
            "rows": [],
            "row_count": 0,
            "mandatory_reply": "请补充学科后再找相似题。",
            "direct_answer": True,
        }
    if not query_text:
        return {
            "success": False,
            "error": "缺少题目文本",
            "rows": [],
            "row_count": 0,
            "mandatory_reply": "请提供题目文本后再找相似题。",
            "direct_answer": True,
        }
    payload = _asset_query_rows(repo.get_questions, subject, 50)
    rows = payload.get("rows") or []
    if not payload.get("success"):
        return payload
    if not rows:
        payload["mandatory_reply"] = "未查询到可用于相似题比对的题目。"
        payload["direct_answer"] = True
        return payload
    scored: list[dict[str, Any]] = []
    for q in rows:
        q_text = str(q.get("question") or "").strip()
        if not q_text:
            continue
        ratio = difflib.SequenceMatcher(None, query_text, q_text).ratio()
        if ratio > 0:
            scored.append(
                {"id": q.get("id"), "question": q_text, "similarity": round(ratio, 4)}
            )
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    top = scored[:5]
    payload["rows"] = top
    payload["row_count"] = len(top)
    payload["source"] = "similarity-mvp"
    if top:
        payload["mandatory_reply"] = f"检索到 {len(top)} 道相似题（按文本相似度）。"
        payload["direct_answer"] = True
    else:
        payload["mandatory_reply"] = "未检索到相似度足够的题目。"
        payload["direct_answer"] = True
    return payload


def intent_query_class_teachers(
    db: Session, user_id: str, *, class_name: Optional[str] = None
) -> dict[str, Any]:
    """查班级任课/班主任；服务端 ORM 读取，不向 AI 开放 users 表 SQL。"""
    token = (class_name or "").strip().rstrip("班")
    admin = can_use_mysql_in_ai_chat(db, user_id)
    accessible = get_accessible_classes(db, user_id, mysql_unrestricted=admin)
    if not accessible:
        return {
            "success": True,
            "row_count": 0,
            "rows": [],
            "message": "未查询到可访问班级下的任课教师记录。",
        }

    class_ids = [c.id for c in accessible]
    q = (
        db.query(ClassTeacher, Class, User)
        .join(Class, ClassTeacher.class_id == Class.id)
        .join(User, ClassTeacher.user_id == User.id)
        .filter(ClassTeacher.class_id.in_(class_ids))
    )
    if token:
        q = q.filter(or_(Class.name == token, Class.name.like(f"%{token}%")))
    else:
        q = q.filter(ClassTeacher.role == "head")

    rows_out: list[dict[str, Any]] = []
    for ct, cls, user in q.order_by(Class.grade, Class.name).limit(30).all():
        teacher_name = (user.display_name or "").strip() or "未知"
        rows_out.append(
            {
                "grade": cls.grade,
                "class_no": cls.name,
                "role": ct.role,
                "subject": ct.subject,
                "teacher_name": teacher_name,
            }
        )
    return {
        "success": True,
        "row_count": len(rows_out),
        "rows": rows_out,
        "message": "未查询到匹配记录。" if not rows_out else None,
    }


def intent_query_todo(db: Session, user_id: str, *, mode: str = "list") -> dict[str, Any]:
    return _mysql_list_or_count(
        db,
        user_id,
        table="todo_items",
        label="待办",
        mode=mode,
        title_key="title",
        order_by="created_at DESC",
    )


def intent_query_prep_resources(
    db: Session, user_id: str, *, subject: Optional[str] = None, mode: str = "list"
) -> dict[str, Any]:
    return _mysql_list_or_count(
        db,
        user_id,
        table="teaching_resources",
        label="教学资源",
        subject=subject,
        mode=mode,
        title_key="title",
    )


def intent_query_exam_registry(
    db: Session, user_id: str, *, subject: Optional[str] = None, mode: str = "list"
) -> dict[str, Any]:
    where_parts: list[str] = []
    params: dict[str, Any] = {}
    if subject:
        where_parts.append("e.subject LIKE :subject")
        params["subject"] = f"%{subject}%"
    where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
    if mode == "count":
        sql = f"SELECT COUNT(*) AS cnt FROM exams e{where_sql}"
    else:
        sql = (
            f"SELECT e.title, e.subject, e.exam_date, e.total_score, c.grade, c.name AS class_no "
            f"FROM exams e JOIN classes c ON e.class_id = c.id{where_sql} "
            f"ORDER BY e.exam_date DESC LIMIT 20"
        )
    payload = execute_mysql_query(db, user_id, sql, params=params)
    return _format_count_list_reply(label="登记考试", payload=payload, title_key="title")


def intent_query_local_exams(db: Session, user_id: str, *, mode: str = "list") -> dict[str, Any]:
    if mode == "count":
        sql = "SELECT COUNT(*) AS cnt FROM local_exam_list"
    else:
        sql = "SELECT exam_title, student_count, max_score, min_score, avg_score FROM local_exam_list LIMIT 20"
    payload = execute_local_data_query(user_id, sql, db=db)
    return _format_count_list_reply(
        "批改考试",
        payload,
        title_key="exam_title",
        direct=True,
    )


def intent_query_student_exam_score(
    user_id: str,
    *,
    student_name: Optional[str] = None,
    exam_name: Optional[str] = None,
    user_text: str = "",
    class_id: Optional[str] = None,
    class_name: Optional[str] = None,
    require_class_match: bool = False,
) -> dict[str, Any]:
    name = (student_name or "").strip()
    exam = (exam_name or "").strip()
    if not name and user_text:
        name, exam_parsed = extract_score_query_context(user_text)
        if not exam:
            exam = (exam_parsed or "").strip()
    return query_student_exam_score(
        user_id,
        student_name=name or "",
        exam_search=exam,
        class_id=class_id,
        class_label=(class_name or "").strip(),
        require_class_match=require_class_match,
    )


def _query_mode(text: str) -> str:
    if looks_like_count_question(text):
        return "count"
    if looks_like_list_question(text):
        return "list"
    return "detail"


_STAGE_RE = re.compile(r"(小学|初中|高中|大学)")


def _extract_stage(text: str) -> Optional[str]:
    """提取中文学段（小学/初中/高中/大学），用于资产题库按学段过滤。"""
    m = _STAGE_RE.search(text or "")
    return m.group(1) if m else None


def detect_intent_calls(db: Session, user_id: str, user_text: str) -> list[tuple[str, dict[str, Any]]]:
    text = (user_text or "").strip()
    if not text or not looks_like_data_question(text):
        return []
    if looks_like_user_account_privacy_question(text):
        return []

    classified = classify_intents(text)
    if not classified:
        return []

    mode = _query_mode(text)
    subject = extract_subject_from_text(text)
    score_name, score_exam = extract_score_query_context(text)
    name = score_name or extract_student_name_from_text(text)
    class_label = extract_class_name_from_text(text)
    grade = extract_grade_from_text(text)
    exam_hint = extract_exam_label_from_text(text) or extract_exam_hint_from_text(text)
    is_score_query = looks_like_student_exam_score_question(text)

    calls: list[tuple[str, dict[str, Any]]] = []
    intent_ids = {iid for iid, _ in classified}

    def add(intent: str, args: Optional[dict[str, Any]] = None) -> None:
        calls.append((intent, args or {}))

    # 某学生某次考试得分（批改档案，最高优先级）
    if is_score_query or "intent_student_exam_score" in intent_ids:
        score_args: dict[str, Any] = {
            "student_name": name,
            "exam_name": score_exam or exam_hint,
            "user_text": text,
        }
        if class_label:
            class_id, class_display = _resolve_class_id_from_label(db, user_id, class_label)
            score_args["require_class_match"] = True
            score_args["class_name"] = class_display or class_label
            if class_id:
                score_args["class_id"] = class_id
        add("intent_student_exam_score", score_args)

    # 班级 / 学生
    if "intent_class_count" in intent_ids or looks_like_class_count_question(text):
        args: dict[str, Any] = {}
        if grade:
            args["grade"] = grade
        add("intent_class_count", args)

    if "intent_students_roster" in intent_ids or looks_like_class_roster_question(text):
        if class_label:
            add("intent_students", {"class_name": class_label, "list_roster": True})

    student_number = extract_student_number_from_text(text)
    profile_q = (
        "intent_student_profile" in intent_ids
        or "intent_student_class" in intent_ids
        or (name and looks_like_student_profile_question(text))
        or (name and looks_like_student_class_question(text))
        or bool(student_number)
    )
    if profile_q:
        profile_args: dict[str, Any] = {"user_text": text}
        if name:
            profile_args["student_name"] = name
        if student_number:
            profile_args["student_number"] = student_number
        if class_label:
            class_id, class_display = _resolve_class_id_from_label(db, user_id, class_label)
            if class_id:
                profile_args["class_id"] = class_id
            profile_args["class_name"] = class_display or class_label
        add("intent_student_profile", profile_args)

    # 教案 / 组卷 / 靶向 / 讲评 / 学情
    if "intent_lesson_plans" in intent_ids:
        add("intent_lesson_plans", {"subject": subject, "mode": mode})

    if "intent_smart_exams" in intent_ids:
        add("intent_smart_exams", {"subject": subject, "mode": mode})

    if "intent_targeted_reports" in intent_ids:
        report_mode = "list" if (name or subject or looks_like_concrete_data_request(text)) else mode
        add(
            "intent_targeted_reports",
            {"subject": subject, "student_name": name, "mode": report_mode},
        )

    if "intent_targeted_recommendations" in intent_ids:
        add("intent_targeted_recommendations", {"subject": subject, "mode": mode})

    if "intent_class_review" in intent_ids or looks_like_class_review_data_question(text):
        review_mode = (
            "list"
            if mode == "count"
            else "detail"
            if (looks_like_concrete_data_request(text) or looks_like_class_review_data_question(text))
            else mode
        )
        review_args: dict[str, Any] = {
            "subject": subject,
            "mode": review_mode,
            "user_text": text,
        }
        if class_label:
            cid, cdisp = _resolve_class_id_from_label(db, user_id, class_label)
            if cid:
                review_args["class_id"] = cid
            review_args["class_name"] = cdisp or class_label
        add("intent_class_review", review_args)

    if "intent_student_analysis" in intent_ids:
        add(
            "intent_student_analysis",
            {
                "subject": subject,
                "student_name": name,
                "mode": mode,
                "use_history": bool(re.search(r"趋势|历史|历次", text)),
            },
        )

    if "intent_knowledge_weak" in intent_ids:
        add("intent_knowledge_weak", {"subject": subject})

    if "intent_class_teachers" in intent_ids:
        add("intent_class_teachers", {"class_name": class_label})

    if "intent_todo" in intent_ids:
        add("intent_todo", {"mode": mode})

    if "intent_prep_resources" in intent_ids:
        add("intent_prep_resources", {"subject": subject, "mode": mode})

    if "intent_exam_registry" in intent_ids:
        add("intent_exam_registry", {"subject": subject, "mode": mode})

    # 资产库（家长端 PG 只读）：题库检索 / 知识树 / 相似题
    if "intent_question_bank" in intent_ids:
        stage = _extract_stage(text) or grade
        add("intent_question_bank", {"subject": subject, "grade": stage})

    if "intent_knowledge_tree" in intent_ids:
        add("intent_knowledge_tree", {"subject": subject})

    if "intent_similar_question" in intent_ids:
        add("intent_similar_question", {"subject": subject, "text": text})

    # 批改档案（本地）：排名/均分/成绩概况
    wants_exam_stats = looks_like_grading_exam_stats_question(text) or (
        (not is_score_query) and ("intent_grading_scores" in intent_ids or looks_like_score_question(text))
    )
    if wants_exam_stats:
        args: dict[str, Any] = {}
        exam = exam_hint or score_exam
        if exam:
            args["exam_name"] = exam
        if class_label:
            class_id, class_display = _resolve_class_id_from_label(db, user_id, class_label)
            args["require_class_match"] = True
            args["class_name"] = class_display or class_label
            if class_id:
                args["class_id"] = class_id
        add("query_exam_scores", args)

    if "intent_grading_exams" in intent_ids:
        add("intent_local_exams", {"mode": mode})

    if "intent_grading_wrong" in intent_ids or re.search(r"错题", text):
        args = {}
        if name:
            args["student_name"] = name
        add("query_grading_wrong_questions", args)

    # 限制单次最多 4 个意图，保留先匹配的（已按 priority 排序）
    seen: set[tuple[str, str]] = set()
    deduped: list[tuple[str, dict[str, Any]]] = []
    for intent, args in calls:
        key = (intent, str(sorted((args or {}).items())))
        if key in seen:
            continue
        seen.add(key)
        deduped.append((intent, args))
        if len(deduped) >= 4:
            break
    return deduped


# ---------------------------------------------------------------------------
# P2-4 批 3：意图执行器注册表。每个执行器把 execute_intent_call 原 if 分支的
# 函数调用 + args.get 解包原样搬入（行为契约：对同一 (intent, args) 返回与原逻辑一致）。
# 动态意图（query_* / list_grading_exams）无法静态注册，仍走 execute_intent_call 原分派。
# ---------------------------------------------------------------------------


def _exec_student_exam_score(db: Session, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    return intent_query_student_exam_score(
        user_id,
        student_name=args.get("student_name"),
        exam_name=args.get("exam_name"),
        user_text=str(args.get("user_text") or ""),
        class_id=args.get("class_id"),
        class_name=args.get("class_name"),
        require_class_match=bool(args.get("require_class_match")),
    )


def _exec_class_count(db: Session, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    return intent_query_class_count(db, user_id, grade=args.get("grade"))


def _exec_student_profile(db: Session, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    return intent_query_student_profile(
        db,
        user_id,
        student_name=args.get("student_name"),
        student_number=args.get("student_number"),
        class_id=args.get("class_id"),
        class_name=args.get("class_name"),
        user_text=str(args.get("user_text") or ""),
    )


def _exec_students(db: Session, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    return intent_query_students_mysql(
        db,
        user_id,
        search=args.get("search"),
        class_name=args.get("class_name"),
        list_roster=bool(args.get("list_roster")),
    )


def _exec_lesson_plans(db: Session, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    return intent_query_lesson_plans(db, user_id, subject=args.get("subject"), mode=args.get("mode") or "list")


def _exec_smart_exams(db: Session, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    return intent_query_smart_exams(db, user_id, subject=args.get("subject"), mode=args.get("mode") or "list")


def _exec_targeted_reports(db: Session, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    return intent_query_targeted_reports(
        db,
        user_id,
        subject=args.get("subject"),
        student_name=args.get("student_name"),
        mode=args.get("mode") or "list",
    )


def _exec_targeted_recommendations(db: Session, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    return intent_query_targeted_recommendations(
        db, user_id, subject=args.get("subject"), mode=args.get("mode") or "list"
    )


def _exec_class_review(db: Session, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    return intent_query_class_review(
        db,
        user_id,
        subject=args.get("subject"),
        class_id=args.get("class_id"),
        class_name=args.get("class_name"),
        mode=args.get("mode") or "list",
        user_text=str(args.get("user_text") or ""),
    )


def _exec_student_analysis(db: Session, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    return intent_query_student_analysis(
        db,
        user_id,
        subject=args.get("subject"),
        student_name=args.get("student_name"),
        mode=args.get("mode") or "list",
        use_history=bool(args.get("use_history")),
    )


def _exec_knowledge_weak(db: Session, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    return intent_query_knowledge_weak(db, user_id, subject=args.get("subject"))


def _exec_question_bank(db: Session, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    return intent_query_asset_question_bank(user_id, subject=args.get("subject"), grade=args.get("grade"))


def _exec_knowledge_tree(db: Session, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    return intent_query_asset_knowledge_tree(user_id, subject=args.get("subject"))


def _exec_similar_question(db: Session, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    return intent_query_asset_similar_questions(
        user_id, text=str(args.get("text") or ""), subject=args.get("subject")
    )


def _exec_class_teachers(db: Session, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    return intent_query_class_teachers(db, user_id, class_name=args.get("class_name"))


def _exec_todo(db: Session, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    return intent_query_todo(db, user_id, mode=args.get("mode") or "list")


def _exec_prep_resources(db: Session, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    return intent_query_prep_resources(db, user_id, subject=args.get("subject"), mode=args.get("mode") or "list")


def _exec_exam_registry(db: Session, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    return intent_query_exam_registry(db, user_id, subject=args.get("subject"), mode=args.get("mode") or "list")


def _exec_local_exams(db: Session, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    return intent_query_local_exams(db, user_id, mode=args.get("mode") or "list")


# 静态意图执行器注册表：key 与 detect_intent_calls 能产出的静态 intent 一一对应
# （完整性不变量由 tests/test_intent_executors.py 守护）。
INTENT_EXECUTORS: dict[str, Callable[[Session, str, dict[str, Any]], dict[str, Any]]] = {
    "intent_student_exam_score": _exec_student_exam_score,
    "intent_class_count": _exec_class_count,
    "intent_student_profile": _exec_student_profile,
    "intent_students": _exec_students,
    "intent_lesson_plans": _exec_lesson_plans,
    "intent_smart_exams": _exec_smart_exams,
    "intent_targeted_reports": _exec_targeted_reports,
    "intent_targeted_recommendations": _exec_targeted_recommendations,
    "intent_class_review": _exec_class_review,
    "intent_student_analysis": _exec_student_analysis,
    "intent_knowledge_weak": _exec_knowledge_weak,
    "intent_question_bank": _exec_question_bank,
    "intent_knowledge_tree": _exec_knowledge_tree,
    "intent_similar_question": _exec_similar_question,
    "intent_class_teachers": _exec_class_teachers,
    "intent_todo": _exec_todo,
    "intent_prep_resources": _exec_prep_resources,
    "intent_exam_registry": _exec_exam_registry,
    "intent_local_exams": _exec_local_exams,
}


def execute_intent_call(db: Session, user_id: str, intent: str, args: dict[str, Any]) -> dict[str, Any]:
    args = args or {}
    executor = INTENT_EXECUTORS.get(intent)
    if executor is not None:
        return executor(db, user_id, args)
    if intent.startswith("query_") or intent == "list_grading_exams":
        return execute_grading_data_tool(user_id, intent, args, db=db)
    return {"success": False, "error": f"未知意图: {intent}"}


def run_intent_queries(db: Session, user_id: str, user_text: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for intent, args in detect_intent_calls(db, user_id, user_text):
        key = (intent, str(sorted(args.items())))
        if key in seen:
            continue
        seen.add(key)
        payload = execute_intent_call(db, user_id, intent, args)
        results.append({"tool": intent, "args": args, "result": payload})
    return results


def build_intent_sql_hint(db: Session, user_id: str, user_text: str) -> str:
    """为大模型补充语义→表映射提示（全模块）。"""
    text = (user_text or "").strip()
    if not text or not looks_like_data_question(text):
        return ""

    hints = build_intent_hints_for_text(text)
    lines = [
        "【语义查数提示】用户未指明前端模块时，请根据问题含义选表，禁止要求用户说明去哪个界面：",
        *hints,
        "请立即调用 execute_mysql_query 或 execute_local_data_query，禁止不查库直接回答。",
    ]
    return "\n".join(lines)
