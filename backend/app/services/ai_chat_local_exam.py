# -*- coding: utf-8 -*-
"""AI 助教：读取个人批改档案中的考试与得分（grading_history / 错题档案）。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from app.grading.user_paths import get_user_grading_paths


def _display_exam_title(folder_key: str) -> str:
    s = str(folder_key or "")
    if s.startswith("cls_") and "__" in s:
        return s.split("__", 1)[1] or s
    return s


def _paper_stem(filename: str) -> str:
    stem = Path(str(filename or "")).stem.strip()
    m = re.match(r"^(?P<name>.+)_\d+$", stem)
    return (m.group("name") if m else stem).strip()


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _score_from_history_item(item: dict) -> Optional[float]:
    if not isinstance(item, dict):
        return None
    for key in ("score_total", "score", "total_score"):
        raw = item.get(key)
        try:
            if raw is not None and str(raw).strip() != "":
                return round(float(raw), 1)
        except Exception:
            pass
    result = str(item.get("result") or "")
    try:
        parsed = json.loads(result)
        scores = parsed.get("scores")
        if isinstance(scores, dict):
            total = 0.0
            seen = False
            for value in scores.values():
                try:
                    total += float(value or 0)
                    seen = True
                except Exception:
                    pass
            if seen:
                return round(total, 1)
    except Exception:
        pass
    m = re.search(r"<essay_score>\s*([\d.]+)\s*</essay_score>", result)
    if not m:
        m = re.search(r"作文得分[：:\s]*([\d.]+)", result)
    if m:
        try:
            return round(float(m.group(1)), 1)
        except Exception:
            return None
    return None


def _resolve_student_name(filename: str, item: Optional[dict]) -> str:
    if isinstance(item, dict):
        group = str(item.get("group_name") or "").strip()
        if group:
            return group
        student = item.get("student")
        if isinstance(student, dict):
            name = str(student.get("name") or "").strip()
            if name:
                return name
    return _paper_stem(filename)


def _class_id_from_exam_key(exam_key: str) -> str:
    safe = str(exam_key or "").strip()
    if safe.startswith("cls_") and "__" in safe:
        return safe.split("__", 1)[0][4:]
    return ""


def match_local_exam_key(
    user_id: str,
    search: str,
    *,
    class_id: Optional[str] = None,
    require_class: bool = False,
) -> Optional[str]:
    needle = (search or "").strip()
    correct = get_user_grading_paths(user_id).correct_docs
    if not correct.is_dir():
        return None
    folders = [d.name for d in correct.iterdir() if d.is_dir()]
    if class_id:
        prefix = f"cls_{class_id}__"
        scoped = [key for key in folders if key.startswith(prefix)]
        if not scoped:
            return None
        folders = scoped
    elif require_class:
        return None
    if not needle:
        return folders[0] if len(folders) == 1 else None

    matched: list[str] = []
    for key in folders:
        title = _display_exam_title(key)
        if needle in title or needle in key or title in needle:
            matched.append(key)
    if not matched:
        for key in folders:
            title = _display_exam_title(key)
            if any(part and part in title for part in re.split(r"[\s_\-]+", needle) if len(part) >= 2):
                matched.append(key)
    if len(matched) == 1:
        return matched[0]
    if len(matched) > 1:
        return None
    return None


def summarize_local_exam_scores(
    user_id: str,
    exam_key: str,
    *,
    class_label: str = "",
    class_id: Optional[str] = None,
) -> dict[str, Any]:
    paths = get_user_grading_paths(user_id)
    hist_dir = paths.grading_history
    exam_title = _display_exam_title(exam_key)

    history_files = [
        (hist_dir / f"{exam_key}.json", "智能批改"),
        (hist_dir / f"{exam_key}__manual.json", "答题卡（自主阅卷）"),
        (hist_dir / f"{exam_key}__essay.json", "作文批改"),
    ]

    per_student: dict[str, list[float]] = {}
    sources_used: set[str] = set()

    for path, label in history_files:
        data = _read_json_file(path)
        completed = data.get("completed")
        if not isinstance(completed, dict):
            continue
        for filename, item in completed.items():
            if not isinstance(item, dict):
                continue
            score = _score_from_history_item(item)
            if score is None:
                continue
            name = _resolve_student_name(str(filename), item)
            per_student.setdefault(name, []).append(score)
            sources_used.add(label)

    student_rows: list[dict[str, Any]] = []
    score_values: list[float] = []
    for name, vals in sorted(per_student.items()):
        total = round(sum(vals), 1)
        student_rows.append({"student_name": name, "score": total})
        score_values.append(total)

    if not score_values:
        return {
            "exam_title": exam_title,
            "exam_key": exam_key,
            "class_id": class_id or _class_id_from_exam_key(exam_key) or None,
            "class_label": class_label or None,
            "student_count": 0,
            "message": "该场考试暂无已归档的得分记录，可能尚未完成批改或尚未保存结果。",
        }

    max_score = max(score_values)
    min_score = min(score_values)
    avg_score = round(sum(score_values) / len(score_values), 1)
    top = [r for r in student_rows if r["score"] == max_score]

    student_rows.sort(key=lambda x: (-x["score"], x["student_name"]))

    for idx, row in enumerate(student_rows, 1):
        row["rank"] = idx

    return {
        "exam_title": exam_title,
        "exam_key": exam_key,
        "class_id": class_id or _class_id_from_exam_key(exam_key) or None,
        "class_label": class_label or None,
        "student_count": len(student_rows),
        "max_score": max_score,
        "min_score": min_score,
        "avg_score": avg_score,
        "top_students": top[:5],
        "rankings": student_rows[:30],
        "score_sources": sorted(sources_used),
        "source_type": "批改档案",
    }


def list_local_exams(user_id: str) -> list[dict[str, Any]]:
    correct = get_user_grading_paths(user_id).correct_docs
    if not correct.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for folder in sorted(correct.iterdir()):
        if not folder.is_dir():
            continue
        exam_key = folder.name
        stats = summarize_local_exam_scores(user_id, exam_key)
        out.append(
            {
                "exam_key": exam_key,
                "class_id": _class_id_from_exam_key(exam_key) or None,
                "exam_title": _display_exam_title(exam_key),
                "student_count": stats.get("student_count", 0),
                "has_scores": bool(stats.get("student_count")),
                "max_score": stats.get("max_score"),
                "avg_score": stats.get("avg_score"),
            }
        )
    return out


def query_local_exam_scores(
    user_id: str,
    *,
    exam_search: str = "",
    class_id: Optional[str] = None,
    class_label: str = "",
    limit: int = 1,
    require_class_match: bool = False,
) -> dict[str, Any]:
    """查询批改档案中的考试得分；必须按班级隔离，禁止跨班返回。"""
    search = (exam_search or "").strip()
    requested_class = (class_label or "").strip()
    require_class = require_class_match or bool(requested_class)

    if require_class and not class_id:
        return {
            "found": False,
            "requested_class_label": requested_class,
            "exam_search": search or None,
            "message": f"未找到「{requested_class}」在批改档案中的考试记录，请确认班级编号是否正确。",
            "source_type": "批改档案",
        }

    if search:
        key = match_local_exam_key(
            user_id,
            search,
            class_id=class_id,
            require_class=require_class,
        )
        if not key:
            available = list_local_exams(user_id)
            if class_id:
                available = [e for e in available if e.get("class_id") == class_id]
            return {
                "found": False,
                "requested_class_label": requested_class or None,
                "class_id": class_id,
                "exam_search": search,
                "available_exams": available[:15],
                "message": (
                    f"未在「{requested_class}」的批改档案中找到与「{search}」匹配的考试。"
                    if requested_class
                    else f"未找到与「{search}」匹配的考试。"
                ),
                "source_type": "批改档案",
            }
        summary = summarize_local_exam_scores(user_id, key, class_label=requested_class, class_id=class_id)
        return {
            "found": True,
            "requested_class_label": requested_class or summary.get("class_label"),
            "class_id": class_id or summary.get("class_id"),
            "exams": [summary],
            "source_type": "批改档案",
        }

    exams = list_local_exams(user_id)
    if not exams:
        return {
            "found": False,
            "message": "当前账号下暂无已批改的考试档案。",
            "source_type": "批改档案",
        }

    if class_id:
        exams = [e for e in exams if e.get("class_id") == class_id]

    if require_class and not exams:
        return {
            "found": False,
            "requested_class_label": requested_class,
            "class_id": class_id,
            "message": f"「{requested_class}」暂无已归档的批改考试。",
            "source_type": "批改档案",
        }

    if len(exams) == 1:
        key = exams[0].get("exam_key") or ""
        if key:
            summary = summarize_local_exam_scores(user_id, key, class_label=requested_class, class_id=class_id)
            return {
                "found": True,
                "requested_class_label": requested_class or summary.get("class_label"),
                "class_id": class_id or summary.get("class_id"),
                "exams": [summary],
                "source_type": "批改档案",
            }

    detailed: list[dict[str, Any]] = []
    for item in exams[:limit]:
        key = item.get("exam_key") or ""
        if key:
            detailed.append(
                summarize_local_exam_scores(user_id, key, class_label=requested_class, class_id=class_id)
            )
    return {
        "found": bool(detailed),
        "requested_class_label": requested_class or None,
        "class_id": class_id,
        "exams": detailed,
        "available_exams": exams[:15],
        "source_type": "批改档案",
    }


def _match_student_name(record_name: str, search: str) -> bool:
    if not search:
        return False
    record = (record_name or "").strip()
    needle = search.strip()
    if not record or not needle:
        return False
    if record == needle:
        return True
    return needle in record or record in needle


def query_student_exam_score(
    user_id: str,
    *,
    student_name: str,
    exam_search: str = "",
    class_id: Optional[str] = None,
    class_label: str = "",
    require_class_match: bool = False,
) -> dict[str, Any]:
    """查询某学生在某场考试（批改档案）中的得分；按班级隔离。"""
    student_name = (student_name or "").strip()
    exam_search = (exam_search or "").strip()
    requested_class = (class_label or "").strip()
    require_class = require_class_match or bool(requested_class)

    if not student_name:
        return {
            "found": False,
            "message": "未能从问句中识别学生姓名，请说明要查询哪位学生的分数。",
        }

    if require_class and not class_id:
        return {
            "found": False,
            "student_name": student_name,
            "requested_class_label": requested_class,
            "message": f"未找到「{requested_class}」班，无法查询该班学生成绩。",
            "source_type": "批改档案",
        }

    exams = list_local_exams(user_id)
    if class_id:
        exams = [e for e in exams if e.get("class_id") == class_id]
    if not exams:
        return {
            "found": False,
            "student_name": student_name,
            "requested_class_label": requested_class or None,
            "class_id": class_id,
            "message": (
                f"「{requested_class}」暂无已归档的批改考试。"
                if requested_class
                else "当前账号下暂无已批改的考试档案。"
            ),
            "source_type": "批改档案",
        }

    def _lookup_in_exam(exam_key: str, exam_title: str) -> Optional[dict[str, Any]]:
        summary = summarize_local_exam_scores(
            user_id,
            exam_key,
            class_label=requested_class,
            class_id=class_id,
        )
        for row in summary.get("rankings") or []:
            if _match_student_name(str(row.get("student_name") or ""), student_name):
                return {
                    "found": True,
                    "student_name": student_name,
                    "exam_title": summary.get("exam_title") or exam_title,
                    "class_id": summary.get("class_id"),
                    "class_label": summary.get("class_label") or requested_class or None,
                    "score": row.get("score"),
                    "rank": row.get("rank"),
                    "source_type": "批改档案",
                }
        return None

    if exam_search:
        key = match_local_exam_key(
            user_id,
            exam_search,
            class_id=class_id,
            require_class=require_class,
        )
        if not key:
            return {
                "found": False,
                "student_name": student_name,
                "exam_search": exam_search,
                "requested_class_label": requested_class or None,
                "class_id": class_id,
                "available_exams": [e["exam_title"] for e in exams[:15]],
                "message": (
                    f"未在「{requested_class}」的批改档案中找到与「{exam_search}」匹配的考试。"
                    if requested_class
                    else f"未找到与「{exam_search}」匹配的考试。"
                ),
                "source_type": "批改档案",
            }
        hit = _lookup_in_exam(key, _display_exam_title(key))
        if hit:
            return hit
        title = _display_exam_title(key)
        return {
            "found": False,
            "student_name": student_name,
            "exam_title": title,
            "requested_class_label": requested_class or None,
            "class_id": class_id,
            "message": f"在「{title}」的批改记录中未找到「{student_name}」的得分。",
            "source_type": "批改档案",
        }

    records: list[dict[str, Any]] = []
    for item in exams:
        key = item.get("exam_key") or match_local_exam_key(
            user_id,
            item["exam_title"],
            class_id=class_id,
            require_class=require_class,
        )
        if not key:
            continue
        hit = _lookup_in_exam(key, item["exam_title"])
        if hit:
            records.append(hit)

    if not records:
        return {
            "found": False,
            "student_name": student_name,
            "requested_class_label": requested_class or None,
            "class_id": class_id,
            "message": f"在批改档案中未查询到「{student_name}」的考试得分记录。",
            "source_type": "批改档案",
        }

    if len(records) == 1:
        return {**records[0], "records": records}

    return {
        "found": True,
        "student_name": student_name,
        "requested_class_label": requested_class or None,
        "class_id": class_id,
        "records": records,
        "source_type": "批改档案",
    }
