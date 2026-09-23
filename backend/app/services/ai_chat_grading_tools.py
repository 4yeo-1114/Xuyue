# -*- coding: utf-8 -*-
"""AI 助教：查询个人批改档案（考试得分、学生、错题）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator, Optional

from sqlalchemy.orm import Session

from app.grading.user_paths import get_user_grading_paths
from app.models.class_model import Class
from app.services.ai_chat_local_exam import list_local_exams, query_local_exam_scores


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _iter_ct_json_files(user_id: str) -> Iterator[tuple[str, str, str, Path]]:
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
    stem = Path(str(paper_name or "")).stem
    return stem.split("_")[0] if stem else str(paper_name or "")


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


def _match_text(value: str, needle: str) -> bool:
    if not needle:
        return True
    if value == needle:
        return True
    return needle in (value or "")


def execute_grading_data_tool(
    user_id: str,
    tool_name: str,
    args: dict[str, Any],
    db: Optional[Session] = None,
) -> Any:
    args = args or {}

    if tool_name == "query_exam_scores":
        exam_search = (args.get("exam_name") or args.get("search") or args.get("exam_search") or "").strip()
        class_id = (args.get("class_id") or "").strip() or None
        class_label = (args.get("class_name") or args.get("class_label") or "").strip()
        require_class = bool(args.get("require_class_match")) or bool(class_label)
        return query_local_exam_scores(
            user_id,
            exam_search=exam_search,
            class_id=class_id,
            class_label=class_label,
            limit=int(args.get("limit") or 3),
            require_class_match=require_class,
        )

    if tool_name == "list_grading_exams":
        exams = list_local_exams(user_id)
        return {
            "total": len(exams),
            "exams": exams,
            "message": "以下为当前账号已批改或已归档的考试列表。",
        }

    if tool_name == "query_grading_overview":
        exams = list_local_exams(user_id)
        class_ids: set[str] = set()
        wrong_total = 0

        for class_id, _kind, exam_name, path in _iter_ct_json_files(user_id):
            class_ids.add(class_id)
            data = _read_json(path)
            papers = data.get("papers") if isinstance(data.get("papers"), dict) else {}
            for paper in papers.values():
                if isinstance(paper, dict):
                    wqs = paper.get("wrong_questions") or []
                    if isinstance(wqs, list):
                        wrong_total += len(wqs)

        paths = get_user_grading_paths(user_id)
        exam_titles = [e["exam_title"] for e in exams[:20]]

        return {
            "archived_exam_count": len(exams),
            "exam_titles": exam_titles,
            "wrong_question_count": wrong_total,
            "class_count_in_records": len(class_ids),
            "message": "概况来自批改档案：含考试场次、错题统计等。",
        }

    if tool_name == "query_grading_students":
        search = (args.get("search") or "").strip()
        class_name = (args.get("class_name") or "").strip()
        list_roster = bool(args.get("list_roster")) or (class_name and not search)
        limit = int(args.get("limit") or 200)

        if list_roster and class_name:
            token = class_name.rstrip("班")
            found: list[dict[str, Any]] = []
            seen_names: set[str] = set()
            matched_class_label = ""

            for class_id, kind, exam_name, path in _iter_ct_json_files(user_id):
                data = _read_json(path)
                cls_meta = data.get("class") if isinstance(data.get("class"), dict) else {}
                class_label = _resolve_class_label(db, class_id, cls_meta)
                label_core = class_label.replace("班", "")
                if token not in label_core and not label_core.endswith(token):
                    meta_name = str(cls_meta.get("name") or "").rstrip("班")
                    if token != meta_name and not meta_name.endswith(token):
                        continue
                matched_class_label = class_label or token
                papers = data.get("papers") if isinstance(data.get("papers"), dict) else {}
                for paper_name, paper in papers.items():
                    if not isinstance(paper, dict):
                        continue
                    name = _paper_student_name(str(paper_name), paper)
                    if not name or name in seen_names:
                        continue
                    seen_names.add(name)
                    found.append({"name": name, "class_label": matched_class_label})
                    if len(found) >= limit:
                        break
                if len(found) >= limit:
                    break

            names = [s["name"] for s in found]
            if names:
                return {
                    "students": found,
                    "student_names": names,
                    "total": len(names),
                    "class_name": matched_class_label or class_name,
                    "found": True,
                    "mandatory_reply": (
                        f"批改档案中「{matched_class_label or class_name}」共有 {len(names)} 名学生："
                        f"{'、'.join(names)}。"
                    ),
                }
            return {
                "students": [],
                "student_names": [],
                "total": 0,
                "found": False,
                "class_name": class_name,
                "mandatory_reply": f"在批改档案中未找到「{class_name}」班的学生记录。",
            }

        found: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        for class_id, kind, exam_name, path in _iter_ct_json_files(user_id):
            data = _read_json(path)
            papers = data.get("papers") if isinstance(data.get("papers"), dict) else {}
            cls_meta = data.get("class") if isinstance(data.get("class"), dict) else {}
            for paper_name, paper in papers.items():
                if not isinstance(paper, dict):
                    continue
                name = _paper_student_name(str(paper_name), paper)
                if search and name != search and search not in name:
                    continue
                key = (class_id, name)
                if key in seen:
                    continue
                seen.add(key)
                summary = paper.get("summary") if isinstance(paper.get("summary"), dict) else {}
                class_label = _resolve_class_label(db, class_id, cls_meta)
                found.append(
                    {
                        "name": name,
                        "class_label": class_label,
                        "exam_name": exam_name,
                        "wrong_question_count": summary.get("wrong_question_count")
                        or len(paper.get("wrong_questions") or []),
                    }
                )
                if len(found) >= limit:
                    break
            if len(found) >= limit:
                break

        return {
            "students": found,
            "total": len(found),
            "search": search or None,
            "found": bool(found),
            "mandatory_reply": (
                f"未在批改档案中查询到「{search}」。" if search and not found else None
            ),
        }

    if tool_name == "query_grading_wrong_questions":
        student_name = (args.get("student_name") or args.get("search") or "").strip()
        subject = (args.get("subject") or "").strip()
        limit = int(args.get("limit") or 10)
        rows: list[dict[str, Any]] = []

        for class_id, _kind, exam_name, path in _iter_ct_json_files(user_id):
            if len(rows) >= limit:
                break
            data = _read_json(path)
            papers = data.get("papers") if isinstance(data.get("papers"), dict) else {}
            for paper_name, paper in papers.items():
                if not isinstance(paper, dict):
                    continue
                name = _paper_student_name(str(paper_name), paper)
                if student_name and not _match_text(name, student_name):
                    continue
                for wq in paper.get("wrong_questions") or []:
                    if not isinstance(wq, dict):
                        continue
                    paper_subject = str(wq.get("paper_subject") or paper.get("subject") or "")
                    if subject and subject not in paper_subject:
                        continue
                    rows.append(
                        {
                            "student_name": name,
                            "exam_name": exam_name,
                            "subject": paper_subject,
                            "content": str(wq.get("display_title") or wq.get("question_key") or "")[:100],
                            "error_type": wq.get("status") or wq.get("baidu_reason") or "",
                        }
                    )
                    if len(rows) >= limit:
                        break

        return {"wrong_questions": rows, "total": len(rows)}

    return {"error": f"Unknown grading tool: {tool_name}"}
