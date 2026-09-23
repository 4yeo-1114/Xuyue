# -*- coding: utf-8 -*-
"""AI 助教：学生花名册精确查询（班级、学号、班干部等）。"""

from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.class_model import Class
from app.models.student import Student
from app.services.ai_chat_access import can_use_mysql_in_ai_chat, get_accessible_classes


def _class_display(cls: Class) -> str:
    grade = (cls.grade or "").replace("小学", "").strip()
    name = (cls.name or "").strip()
    if grade and name:
        return f"{grade}{name}班" if not name.endswith("班") else f"{grade}{name}"
    return name or str(cls.id)


def _name_variants(name: str) -> list[str]:
    raw = (name or "").strip()
    if not raw:
        return []
    variants = [raw]
    if "·" in raw:
        variants.append(raw.replace("·", ""))
    elif len(raw) >= 3:
        # 欧阳锋 → 不自动拆；仅处理显式间隔号
        pass
    return list(dict.fromkeys(variants))


def _student_profile_dict(student: Student, cls: Class) -> dict[str, Any]:
    """构造发往大模型的学生花名册档案。

    E09 分级（JY/T 0661-2025 近似）：只发 AI 对话需要的字段。
    - 姓名/性别/班级/年级/学号/班干部/座位等 → 保留（姓名出站由 Anonymizer 匿名化）。
    - phone/parent_name/parent_phone/birthday/address/notes（L3-L5 敏感）→ 一律不下发大模型，
      即使老师提问「家长电话/住址」也不得带出（详见 docs/contracts/13-data-classification.md）。
    """
    cadre = (student.cadre_role or "").strip() or None
    return {
        "student_id": student.id,
        "name": student.name,
        "student_number": (student.student_number or "").strip() or None,
        "class_id": student.class_id,
        "class_name": _class_display(cls),
        "grade": cls.grade,
        "class_no": cls.name,
        "gender": student.gender,
        "tier": student.tier,
        "status": student.status,
        "cadre_role": cadre,
        "is_cadre": bool(cadre),
        "seat_row": student.seat_row,
        "seat_col": student.seat_col,
    }


def lookup_students_in_roster(
    db: Session,
    user_id: str,
    *,
    student_name: Optional[str] = None,
    student_number: Optional[str] = None,
    class_id: Optional[str] = None,
    class_name: Optional[str] = None,
    exact_only: bool = True,
) -> dict[str, Any]:
    """从 MySQL 花名册精确查询学生；禁止模糊匹配以免串人。"""
    admin = can_use_mysql_in_ai_chat(db, user_id)
    accessible = get_accessible_classes(db, user_id, mysql_unrestricted=admin)
    if not accessible:
        return {
            "success": True,
            "found": False,
            "students": [],
            "source_type": "系统花名册",
            "message": "未查询到可访问班级下的学生花名册。",
        }

    accessible_ids = {c.id for c in accessible}
    target_ids = list(accessible_ids)

    if class_id:
        if class_id not in accessible_ids:
            return {
                "success": True,
                "found": False,
                "requested_class_id": class_id,
                "students": [],
                "source_type": "系统花名册",
                "message": "指定班级不在可访问范围内。",
            }
        target_ids = [class_id]
    elif class_name:
        from app.services.ai_chat_intent_queries import _match_class_token, _resolve_class_id_from_label

        cid, _ = _resolve_class_id_from_label(db, user_id, class_name)
        if cid and cid in accessible_ids:
            target_ids = [cid]
        else:
            token = (class_name or "").strip().rstrip("班")
            matched = [c for c in accessible if _match_class_token(c, token)]
            if len(matched) == 1:
                target_ids = [matched[0].id]
            elif len(matched) > 1:
                target_ids = [c.id for c in matched]

    q = (
        db.query(Student, Class)
        .join(Class, Student.class_id == Class.id)
        .filter(Student.class_id.in_(target_ids))
    )

    number = (student_number or "").strip()
    name = (student_name or "").strip()

    if number:
        rows = q.filter(Student.student_number == number).order_by(Class.grade, Class.name).all()
        match_type = "student_number"
    elif name:
        variants = _name_variants(name)
        rows = q.filter(Student.name.in_(variants)).order_by(Class.grade, Class.name).all()
        match_type = "exact_name"
        if not rows and not exact_only:
            rows = q.filter(Student.name.like(f"%{name}%")).order_by(Class.grade, Class.name).limit(20).all()
            match_type = "fuzzy_name"
    else:
        return {
            "success": True,
            "found": False,
            "students": [],
            "source_type": "系统花名册",
            "message": "未能识别要查询的学生姓名或学号。",
        }

    students = [_student_profile_dict(s, c) for s, c in rows]

    if not students:
        return {
            "success": True,
            "found": False,
            "search_name": name or None,
            "search_number": number or None,
            "requested_class_name": class_name,
            "class_id": class_id,
            "students": [],
            "match_type": match_type,
            "source_type": "系统花名册",
            "message": (
                f"未在花名册中找到学号为「{number}」的学生。"
                if number
                else f"未在花名册中找到姓名为「{name}」的学生（已按精确姓名匹配）。"
            ),
        }

    payload: dict[str, Any] = {
        "success": True,
        "found": True,
        "search_name": name or None,
        "search_number": number or None,
        "requested_class_name": class_name,
        "class_id": class_id,
        "students": students,
        "match_type": match_type,
        "ambiguous": len(students) > 1,
        "source_type": "系统花名册",
    }
    if len(students) == 1:
        payload["student"] = students[0]
    elif len(students) > 1:
        payload["message"] = (
            f"系统中有 {len(students)} 名同名学生「{name}」，已分别列出各班记录，"
            "回答时必须逐条引用下方 JSON 中的 class_name、student_number，禁止合并或猜测。"
        )
    return payload


def infer_profile_fields_from_text(text: str) -> list[str]:
    """从问句推断用户关心的花名册字段。"""
    s = (text or "").strip()
    if not s:
        return []
    fields: list[str] = []
    if re.search(r"(哪个|哪一个|什么|哪一).{0,8}(班|班级|年级)", s) or re.search(
        r"(班|班级|年级).{0,8}(哪个|哪一个|什么)", s
    ):
        fields.append("class_name")
    if re.search(r"学籍号|学号", s):
        fields.append("student_number")
    if re.search(r"班干部|班干|职务|担任", s):
        fields.append("cadre_role")
    if re.search(r"座位|座号", s):
        fields.extend(["seat_row", "seat_col"])
    if re.search(r"性别", s):
        fields.append("gender")
    # E09：家长姓名/家长电话/手机/住址/生日属 L3-L5 敏感字段，不下发大模型，
    # 因此不再把它们作为「可请求字段」暴露给模型（避免模型尝试从花名册带出）。
    return fields
