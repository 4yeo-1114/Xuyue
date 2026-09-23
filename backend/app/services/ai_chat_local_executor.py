# -*- coding: utf-8 -*-
"""AI 助教：执行大模型针对 local_* 虚拟表的只读 SELECT（限定当前用户目录）。"""

from __future__ import annotations

import re
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.grading.user_paths import get_user_grading_paths, user_grading_root
from app.models.class_model import Class
from app.services.ai_chat_local_exam import (
    _display_exam_title,
    _paper_stem,
    _read_json_file,
    _resolve_student_name,
    _score_from_history_item,
    list_local_exams,
    match_local_exam_key,
)
from app.services.ai_chat_sql_utils import ParsedSelect, parse_simple_select, validate_local_select

LOCAL_ALLOWED_TABLES = frozenset(
    {
        "local_exam_list",
        "local_grading_scores",
        "local_ct_students",
        "local_ct_wrong_questions",
    }
)


def _resolve_class_label(db: Optional[Session], class_id: str, cls_meta: dict[str, Any]) -> str:
    if db and class_id:
        cls = db.query(Class).filter(Class.id == class_id).first()
        if cls:
            grade = (cls.grade or "").replace("小学", "").strip()
            name = (cls.name or "").strip()
            if grade and name:
                return f"{grade}{name}班" if not name.endswith("班") else f"{grade}{name}"
            return name or class_id
    name = str(cls_meta.get("name") or cls_meta.get("label") or "").strip()
    grade = str(cls_meta.get("grade") or "").replace("小学", "").strip()
    if grade and name:
        return f"{grade}{name}班" if not name.endswith("班") else f"{grade}{name}"
    return name or class_id


def _iter_ct_json_files(user_id: str):
    ct_root = get_user_grading_paths(user_id).ct
    if not ct_root.is_dir():
        return
    for cls_dir in sorted(ct_root.iterdir()):
        if not cls_dir.is_dir() or not cls_dir.name.startswith("cls_"):
            continue
        class_id = cls_dir.name[4:]
        for kind in ("records", "analysis"):
            sub = cls_dir / kind
            if not sub.is_dir():
                continue
            for path in sorted(sub.glob("*.json")):
                yield class_id, kind, path.stem, path


def _paper_student_name(paper_name: str, paper: dict[str, Any]) -> str:
    student = paper.get("student")
    if isinstance(student, dict) and student.get("name"):
        return str(student["name"])
    return _paper_stem(paper_name)


def _match_condition(row: dict[str, Any], col: str, op: str, val: str) -> bool:
    cell = str(row.get(col, "") or "")
    if op == "=":
        return cell == val
    if op == "LIKE":
        pattern = val.replace("%", ".*").replace("_", ".")
        return bool(re.search(f"^{pattern}$", cell, re.IGNORECASE))
    return True


def _filter_rows(rows: list[dict[str, Any]], parsed: ParsedSelect) -> list[dict[str, Any]]:
    out = rows
    for col, op, val in parsed.where_conditions:
        out = [r for r in out if _match_condition(r, col, op, val)]
    return out


def _sort_rows(rows: list[dict[str, Any]], order_by: Optional[str]) -> list[dict[str, Any]]:
    if not order_by:
        return rows
    parts = order_by.strip().split()
    if not parts:
        return rows
    col = parts[0].strip("`")
    desc = len(parts) > 1 and parts[1].upper() == "DESC"
    try:
        return sorted(rows, key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
    except TypeError:
        return sorted(rows, key=lambda r: str(r.get(col, "")), reverse=desc)


def _project_columns(rows: list[dict[str, Any]], columns: list[str], distinct: bool) -> list[dict[str, Any]]:
    if columns == ["*"]:
        return rows
    projected: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        item = {c: row.get(c) for c in columns}
        if distinct:
            key = tuple(item.get(c) for c in columns)
            if key in seen:
                continue
            seen.add(key)
        projected.append(item)
    return projected


def _build_local_exam_list(user_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in list_local_exams(user_id):
        rows.append(
            {
                "exam_key": match_local_exam_key(user_id, item["exam_title"]) or "",
                "exam_title": item.get("exam_title"),
                "student_count": item.get("student_count", 0),
                "max_score": item.get("max_score"),
                "avg_score": item.get("avg_score"),
            }
        )
    return rows


def _build_local_grading_scores(user_id: str) -> list[dict[str, Any]]:
    paths = get_user_grading_paths(user_id)
    hist_dir = paths.grading_history
    correct = paths.correct_docs
    rows: list[dict[str, Any]] = []

    if not correct.is_dir():
        return rows

    for folder in sorted(correct.iterdir()):
        if not folder.is_dir():
            continue
        exam_key = folder.name
        exam_title = _display_exam_title(exam_key)
        for suffix, grading_type in (
            ("", "智能批改"),
            ("__manual", "答题卡（自主阅卷）"),
            ("__essay", "作文批改"),
        ):
            data = _read_json_file(hist_dir / f"{exam_key}{suffix}.json")
            completed = data.get("completed")
            if not isinstance(completed, dict):
                continue
            for filename, item in completed.items():
                if not isinstance(item, dict):
                    continue
                score = _score_from_history_item(item)
                if score is None:
                    continue
                rows.append(
                    {
                        "exam_key": exam_key,
                        "exam_title": exam_title,
                        "student_name": _resolve_student_name(str(filename), item),
                        "score": score,
                        "grading_type": grading_type,
                    }
                )
    return rows


def _build_local_ct_students(user_id: str, db: Optional[Session]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for class_id, _kind, exam_name, path in _iter_ct_json_files(user_id):
        data = _read_json_file(path)
        cls_meta = data.get("class") if isinstance(data.get("class"), dict) else {}
        class_label = _resolve_class_label(db, class_id, cls_meta)
        papers = data.get("papers") if isinstance(data.get("papers"), dict) else {}
        for paper_name, paper in papers.items():
            if not isinstance(paper, dict):
                continue
            name = _paper_student_name(str(paper_name), paper)
            key = (class_id, name, exam_name)
            if key in seen:
                continue
            seen.add(key)
            summary = paper.get("summary") if isinstance(paper.get("summary"), dict) else {}
            rows.append(
                {
                    "class_id": class_id,
                    "class_name": class_label,
                    "student_name": name,
                    "exam_name": exam_name,
                    "wrong_question_count": summary.get("wrong_question_count")
                    or len(paper.get("wrong_questions") or []),
                }
            )
    return rows


def _build_local_ct_wrong_questions(user_id: str, db: Optional[Session]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for class_id, _kind, exam_name, path in _iter_ct_json_files(user_id):
        data = _read_json_file(path)
        cls_meta = data.get("class") if isinstance(data.get("class"), dict) else {}
        class_label = _resolve_class_label(db, class_id, cls_meta)
        papers = data.get("papers") if isinstance(data.get("papers"), dict) else {}
        for paper_name, paper in papers.items():
            if not isinstance(paper, dict):
                continue
            name = _paper_student_name(str(paper_name), paper)
            for wq in paper.get("wrong_questions") or []:
                if not isinstance(wq, dict):
                    continue
                rows.append(
                    {
                        "class_name": class_label,
                        "student_name": name,
                        "exam_name": exam_name,
                        "subject": str(wq.get("paper_subject") or paper.get("subject") or ""),
                        "content": str(wq.get("display_title") or wq.get("question_key") or "")[:120],
                        "error_type": str(wq.get("status") or wq.get("baidu_reason") or ""),
                    }
                )
    return rows


_TABLE_BUILDERS: dict[str, Callable[..., list[dict[str, Any]]]] = {
    "local_exam_list": lambda uid, db: _build_local_exam_list(uid),
    "local_grading_scores": lambda uid, db: _build_local_grading_scores(uid),
    "local_ct_students": lambda uid, db: _build_local_ct_students(uid, db),
    "local_ct_wrong_questions": lambda uid, db: _build_local_ct_wrong_questions(uid, db),
}


def execute_local_data_query(
    user_id: str,
    sql: str,
    db: Optional[Session] = None,
) -> dict[str, Any]:
    """仅允许查询当前 user_id 对应 grading_data 目录下的虚拟表。"""
    root = user_grading_root(user_id).resolve()
    if not root.is_dir():
        return {
            "success": False,
            "error": "当前用户批改目录不存在",
            "rows": [],
            "row_count": 0,
            "user_data_root": str(root),
        }

    try:
        safe_sql = validate_local_select(sql, LOCAL_ALLOWED_TABLES)
        parsed = parse_simple_select(safe_sql)
    except ValueError as e:
        return {"success": False, "error": str(e), "rows": [], "row_count": 0}

    table = parsed.table.lower()
    builder = _TABLE_BUILDERS.get(table)
    if not builder:
        return {"success": False, "error": f"未知虚拟表: {parsed.table}", "rows": [], "row_count": 0}

    all_rows = builder(user_id, db)
    filtered = _filter_rows(all_rows, parsed)
    sorted_rows = _sort_rows(filtered, parsed.order_by)
    limited = sorted_rows[: parsed.limit]
    projected = _project_columns(limited, parsed.columns, parsed.distinct)

    payload: dict[str, Any] = {
        "success": True,
        "sql_executed": safe_sql,
        "virtual_table": parsed.table,
        "user_data_root": str(root),
        "row_count": len(projected),
        "rows": projected,
    }
    if not projected:
        payload["message"] = "查询成功但无匹配记录，回答时必须说明「未查询到」，禁止编造姓名或分数。"
    return payload
