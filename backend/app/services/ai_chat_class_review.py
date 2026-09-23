# -*- coding: utf-8 -*-
"""AI 助教：课堂讲评（class_review_sessions）精确查询。"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.class_model import Class
from app.models.class_review import ClassReviewSession
from app.services.ai_chat_access import can_use_mysql_in_ai_chat, get_accessible_classes
from app.services.ai_chat_intent_registry import extract_subject_from_text


def _class_display(cls: Class) -> str:
    grade = (cls.grade or "").replace("小学", "").strip()
    name = (cls.name or "").strip()
    if grade and name:
        return f"{grade}{name}班" if not name.endswith("班") else f"{grade}{name}"
    return name or str(cls.id)


def _json_loads(raw: Any, default: Any = None) -> Any:
    if raw is None or raw == "":
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(str(raw))
    except Exception:
        return default if default is not None else str(raw)[:2000]


def _truncate_value(value: Any, max_len: int = 8000) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
        if len(text) <= max_len:
            return value
        return text[:max_len] + "…[内容已截断]"
    text = str(value)
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…[内容已截断]"


def _session_payload(session: ClassReviewSession, cls: Class) -> dict[str, Any]:
    generated = session.generated_at.isoformat() if session.generated_at else None
    return {
        "session_id": session.id,
        "class_id": session.class_id,
        "class_name": _class_display(cls),
        "class_no": cls.name,
        "grade": cls.grade,
        "subject": session.subject,
        "title": session.title or "",
        "generated_at": generated,
        "exam_names": _json_loads(session.exam_names_json, []),
        "imported_folder_names": _json_loads(session.imported_folder_names_json, []),
        "source_summary": _truncate_value(_json_loads(session.source_summary_json, {})),
        "pre_class": _truncate_value(_json_loads(session.pre_class_json, {})),
        "tracking": _truncate_value(_json_loads(session.tracking_json, {})),
        "consolidation": _truncate_value(_json_loads(session.consolidation_json, {})),
        "post_feedback": _truncate_value(_json_loads(session.post_feedback_json, {})),
    }


def lookup_class_review_sessions(
    db: Session,
    user_id: str,
    *,
    subject: Optional[str] = None,
    class_id: Optional[str] = None,
    class_name: Optional[str] = None,
    user_text: str = "",
) -> dict[str, Any]:
    """按班级 + 学科查询课堂讲评完整内容；无记录时 found=false。"""
    admin = can_use_mysql_in_ai_chat(db, user_id)
    accessible = get_accessible_classes(db, user_id, mysql_unrestricted=admin)
    if not accessible:
        return {
            "success": True,
            "found": False,
            "sessions": [],
            "source_type": "课堂讲评",
            "message": "未查询到可访问班级，无法读取课堂讲评。",
        }

    accessible_map = {c.id: c for c in accessible}
    subj = (subject or extract_subject_from_text(user_text) or "").strip()
    requested_class = (class_name or "").strip()
    require_class = bool(requested_class or class_id)

    if class_name and not class_id:
        from app.services.ai_chat_intent_queries import _resolve_class_id_from_label

        class_id, class_display = _resolve_class_id_from_label(db, user_id, class_name)
        if class_display:
            requested_class = class_display

    if require_class and not class_id:
        return {
            "success": True,
            "found": False,
            "requested_class_label": requested_class,
            "requested_subject": subj or None,
            "sessions": [],
            "source_type": "课堂讲评",
            "message": f"未找到「{requested_class}」班级，无法查询课堂讲评。",
        }

    if not subj and not class_id:
        return {
            "success": True,
            "found": False,
            "sessions": [],
            "source_type": "课堂讲评",
            "message": "请说明要查询的班级与学科，例如「2103班的数学课堂讲评」。",
        }

    target_class_ids = list(accessible_map.keys())
    if class_id:
        if class_id not in accessible_map:
            return {
                "success": True,
                "found": False,
                "class_id": class_id,
                "requested_subject": subj or None,
                "sessions": [],
                "source_type": "课堂讲评",
                "message": "指定班级不在可访问范围内。",
            }
        target_class_ids = [class_id]

    q = (
        db.query(ClassReviewSession, Class)
        .join(Class, ClassReviewSession.class_id == Class.id)
        .filter(ClassReviewSession.class_id.in_(target_class_ids))
    )

    if subj:
        q = q.filter(
            or_(
                ClassReviewSession.subject == subj,
                ClassReviewSession.subject.like(f"%{subj}%"),
            )
        )

    rows = q.order_by(ClassReviewSession.generated_at.desc()).limit(10).all()

    if not rows:
        parts = []
        if requested_class:
            parts.append(f"「{requested_class}」")
        if subj:
            parts.append(f"「{subj}」")
        label = "".join(parts) or "指定条件"
        return {
            "success": True,
            "found": False,
            "requested_class_label": requested_class or None,
            "requested_subject": subj or None,
            "class_id": class_id,
            "sessions": [],
            "source_type": "课堂讲评",
            "message": (
                f"未在课堂讲评记录中找到{label}的讲评数据，"
                "请确认该班该学科是否已在「课堂讲评」模块生成。"
            ),
        }

    sessions = [_session_payload(s, c) for s, c in rows]

    if class_id and subj and len(sessions) == 1:
        return {
            "success": True,
            "found": True,
            "requested_class_label": requested_class or sessions[0].get("class_name"),
            "requested_subject": subj,
            "class_id": class_id,
            "session": sessions[0],
            "sessions": sessions,
            "source_type": "课堂讲评",
        }

    payload: dict[str, Any] = {
        "success": True,
        "found": True,
        "requested_class_label": requested_class or None,
        "requested_subject": subj or None,
        "class_id": class_id,
        "sessions": sessions,
        "ambiguous": len(sessions) > 1,
        "source_type": "课堂讲评",
    }
    if len(sessions) == 1:
        payload["session"] = sessions[0]
    elif len(sessions) > 1:
        payload["message"] = (
            f"查询到 {len(sessions)} 条课堂讲评记录，请仅使用 JSON 中各条 session 的 "
            "class_name、subject、consolidation、pre_class 等字段回答，禁止合并或编造。"
        )
    return payload


def looks_like_class_review_data_question(text: str) -> bool:
    """是否在问课堂讲评的具体数据（非纯操作教程）。"""
    s = (text or "").strip()
    if not s:
        return False
    if re.search(r"怎么用|如何使用|怎么操作|如何操作|教程|步骤", s):
        if not re.search(r"查|查询|告诉我|总结|内容|方案|记录", s):
            return False
    if re.search(r"是什么|什么意思", s) and not re.search(
        r"查|查询|告诉我|总结|内容|方案|记录|讲评", s
    ):
        return False
    return bool(
        re.search(
            r"课堂讲评|讲评方案|讲评内容|讲评记录|二次巩固|巩固方案|课后反馈|智能复习|课前讲评",
            s,
        )
    )
