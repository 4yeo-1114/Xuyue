# -*- coding: utf-8 -*-
"""聚合已统分试卷数据（参考靶向提升），供自动分析报告使用。"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.database import SessionLocal
from app.grading import wrong_question_db
from app.grading.grading_stats import is_paper_shows_graded_badge
from app.grading.router import (
    _paper_box_display_name,
    _parse_ai_result_to_counts,
    _preview_url_for_file,
    _read_grading_history,
)
from app.grading.user_paths import correct_docs_dir
from app.models.class_model import Class
from app.routers.targeted_improvement import (
    _analysis_items_for_paper,
    _compact_question_record,
    _is_wrong_record,
    _lookup_ct_paper,
    _read_wrong_jsons,
    _records_for_paper,
    _safe_excerpt,
    _wrong_titles_from_grading_result,
)


def _display_folder_name(name: str) -> str:
    s = str(name or "").strip()
    if s.startswith("cls_") and "__" in s:
        return s.split("__", 1)[1] or s
    m = re.match(r"^cls_[^_]+_(.+)$", s)
    return m.group(1) if m else s


def _parse_class_id(folder_safe: str) -> str:
    class_id, _ = wrong_question_db._split_class_exam(folder_safe)
    return class_id


def _load_class_meta(class_id: str) -> dict[str, Any]:
    if not class_id:
        return {}
    db = SessionLocal()
    try:
        row = db.query(Class).filter(Class.id == class_id).first()
        if not row:
            return {"class_id": class_id}
        return {
            "class_id": class_id,
            "class_name": row.name or "",
            "grade": row.grade or "",
            "school_level": row.school_level or "",
        }
    finally:
        db.close()


def _unique_sorted(items) -> list[str]:
    return sorted({str(x) for x in items if str(x).strip()}, key=lambda x: str(x))


def _iter_scored_ref_items(folder_safe: str) -> list[tuple[str, dict]]:
    """仅返回已完成统分（有 score_total）的有效智能批改记录。"""
    history = _read_grading_history(folder_safe, "default")
    completed = history.get("completed") if isinstance(history.get("completed"), dict) else {}
    scored: list[tuple[str, dict]] = []
    for filename, info in completed.items():
        if not isinstance(info, dict):
            continue
        if not is_paper_shows_graded_badge(info, source="ref"):
            continue
        result_text = str(info.get("result") or "").strip()
        if not result_text or result_text.startswith("{"):
            continue
        if info.get("score_total") is None:
            continue
        scored.append((str(filename), info))
    return scored


def _compact_analysis_item(item: dict) -> dict:
    if not isinstance(item, dict):
        return {}
    analysis = item.get("analysis") if isinstance(item.get("analysis"), dict) else {}
    assets = item.get("assets") if isinstance(item.get("assets"), dict) else {}
    q_img = assets.get("question_image") if isinstance(assets.get("question_image"), dict) else {}
    a_img = assets.get("answer_image") if isinstance(assets.get("answer_image"), dict) else {}
    q_rel = q_img.get("relative_to_grading_data") or q_img.get("path")
    a_rel = a_img.get("relative_to_grading_data") or a_img.get("path")
    return {
        "display_title": item.get("display_title") or item.get("question_key"),
        "question_key": item.get("question_key"),
        "summary": analysis.get("summary") or analysis.get("diagnosis") or analysis.get("message"),
        "advice": analysis.get("advice"),
        "question_image_url": wrong_question_db.ct_image_api_url_for_rel(q_rel),
        "answer_image_url": wrong_question_db.ct_image_api_url_for_rel(a_rel),
    }


def _wrong_images_for_boxes(folder_safe: str, box_names: set[str]) -> list[dict]:
    images = wrong_question_db.collect_wrong_question_images([folder_safe])
    if not box_names:
        return images[:40]
    filtered = [img for img in images if str(img.get("student_name") or "") in box_names]
    return (filtered or images)[:40]


def collect_smart_scoring_payload(folder_safe: str) -> dict[str, Any]:
    """智能批改：仅汇总已统分试卷（与批改详细界面显示分数的试卷一致）。"""
    history = _read_grading_history(folder_safe, "default")
    scoring_config = history.get("scoring_config") if isinstance(history.get("scoring_config"), dict) else {}
    full_score = history.get("full_score")
    scored_items = _iter_scored_ref_items(folder_safe)

    records_json, analysis_json = _read_wrong_jsons(folder_safe)
    record_papers = records_json.get("papers") if isinstance(records_json.get("papers"), dict) else {}
    analysis_papers = analysis_json.get("papers") if isinstance(analysis_json.get("papers"), dict) else {}

    questions_stat: dict[str, dict] = {}
    students_by_box: dict[str, dict] = {}
    box_names: set[str] = set()

    def ensure_question_stat(title: str) -> dict:
        if title not in questions_stat:
            questions_stat[title] = {
                "title": title,
                "correct": 0,
                "wrong": 0,
                "blank": 0,
                "wrong_students": [],
            }
        return questions_stat[title]

    for filename, info in scored_items:
        box_name = _paper_box_display_name(filename)
        box_names.add(box_name)
        result_text = str(info.get("result") or "").strip()
        counts, blocks = _parse_ai_result_to_counts(result_text)
        wrong_titles = _wrong_titles_from_grading_result(result_text)

        for b in blocks:
            title = b["title"]
            st = b["status"]
            q_stat = ensure_question_stat(title)
            if st == "correct":
                q_stat["correct"] += 1
            elif st == "wrong":
                q_stat["wrong"] += 1
                q_stat["wrong_students"].append(box_name)
            elif st == "blank":
                q_stat["blank"] += 1
                q_stat["wrong_students"].append(box_name)

        record_paper = _lookup_ct_paper(record_papers, box_name, filename)
        analysis_paper = _lookup_ct_paper(analysis_papers, box_name, filename)
        page_records = _records_for_paper(record_paper) if isinstance(record_paper, dict) else []
        wrong_records = [item for item in page_records if _is_wrong_record(item)]
        analysis_items = _analysis_items_for_paper(analysis_paper) if isinstance(analysis_paper, dict) else []

        preview_url = ""
        file_path = correct_docs_dir() / folder_safe / filename
        if file_path.is_file():
            preview_url = _preview_url_for_file(folder_safe, filename)

        try:
            score_num = float(info.get("score_total"))
        except Exception:
            score_num = None

        stat = students_by_box.setdefault(
            box_name,
            {
                "student_box": box_name,
                "source_filenames": [],
                "score_total": 0.0,
                "question_scores": {},
                "correct_count": 0,
                "wrong_count": 0,
                "wrong_questions": set(),
                "grading_result_excerpt": "",
                "image_original": "",
                "image_annotated": "",
                "paper_preview_url": "",
                "paper_records": [],
                "wrong_records": [],
                "wrong_analysis": [],
            },
        )
        stat["source_filenames"].append(filename)
        stat["correct_count"] += counts["correct"]
        stat["wrong_count"] += counts["wrong"] + counts["blank"]
        stat["wrong_questions"].update(wrong_titles)
        if score_num is not None:
            stat["score_total"] = (stat["score_total"] or 0) + score_num
        stat["grading_result_excerpt"] = _safe_excerpt(
            (stat.get("grading_result_excerpt") or "") + "\n" + result_text,
            limit=1500,
        )
        if info.get("image_original"):
            stat["image_original"] = str(info.get("image_original"))
        if info.get("image_annotated"):
            stat["image_annotated"] = str(info.get("image_annotated"))
        if preview_url:
            stat["paper_preview_url"] = preview_url

        q_scores = info.get("question_scores") if isinstance(info.get("question_scores"), dict) else {}
        for key, value in q_scores.items():
            try:
                num = float(value)
            except Exception:
                continue
            stat["question_scores"][str(key)] = stat["question_scores"].get(str(key), 0) + num

        existing_keys = {str(x.get("question_key")) for x in stat["paper_records"] if isinstance(x, dict)}
        for item in page_records[:80]:
            compact = _compact_question_record(item)
            key = str(compact.get("question_key") or "")
            if key and key in existing_keys:
                continue
            stat["paper_records"].append(compact)
            if key:
                existing_keys.add(key)
        for item in wrong_records[:40]:
            compact = _compact_question_record(item)
            stat["wrong_records"].append(compact)
        for item in analysis_items[:30]:
            stat["wrong_analysis"].append(_compact_analysis_item(item))

    questions_list = []
    for q in questions_stat.values():
        q["wrong_students"] = _unique_sorted(q.get("wrong_students", []))
        questions_list.append(q)
    questions_list.sort(key=lambda x: (x["wrong"] + x["blank"]), reverse=True)

    students_list: list[dict[str, Any]] = []
    scores: list[float] = []
    for stat in students_by_box.values():
        score = stat.get("score_total")
        if score is not None:
            try:
                scores.append(float(score))
            except Exception:
                pass
        students_list.append(
            {
                "student_box": stat["student_box"],
                "source_filenames": _unique_sorted(stat.get("source_filenames", [])),
                "score_total": stat.get("score_total"),
                "question_scores": stat.get("question_scores") or {},
                "correct_count": stat["correct_count"],
                "wrong_count": stat["wrong_count"],
                "wrong_questions": _unique_sorted(stat.get("wrong_questions", [])),
                "grading_result_excerpt": stat.get("grading_result_excerpt") or "",
                "image_original": stat.get("image_original") or "",
                "image_annotated": stat.get("image_annotated") or "",
                "paper_preview_url": stat.get("paper_preview_url") or "",
                "paper_records": stat.get("paper_records") or [],
                "wrong_records": stat.get("wrong_records") or [],
                "wrong_analysis": stat.get("wrong_analysis") or [],
            }
        )

    students_list.sort(
        key=lambda x: (
            -(float(x.get("score_total")) if x.get("score_total") is not None else -1.0),
            x["wrong_count"],
            str(x["student_box"]),
        )
    )

    avg_score = round(sum(scores) / len(scores), 1) if scores else None
    class_meta = _load_class_meta(_parse_class_id(folder_safe))
    wrong_images = _wrong_images_for_boxes(folder_safe, box_names)
    student_count = len(students_list)

    return {
        "exam_name": _display_folder_name(folder_safe),
        "folder_safe": folder_safe,
        "report_kind": "smart_scoring",
        "scope_note": (
            f"本报告仅分析已完成统分的 {student_count} 名学生；"
            f"文件夹内未批改或未统分的试卷框未纳入。"
        ),
        "class": class_meta,
        "student_count": student_count,
        "paper_count": student_count,
        "scored_file_count": len(scored_items),
        "score_summary": {
            "count": len(scores),
            "average": avg_score,
            "max": max(scores) if scores else None,
            "min": min(scores) if scores else None,
            "full_score": full_score,
        },
        "scoring_config": scoring_config,
        "score_ranking": [
            {
                "rank": idx + 1,
                "student_box": s["student_box"],
                "score_total": s.get("score_total"),
                "wrong_count": s.get("wrong_count"),
            }
            for idx, s in enumerate(students_list)
        ],
        "top_wrong_questions": questions_list[:20],
        "students": students_list,
        "wrong_question_images": wrong_images,
        "ct_records_meta": {
            "has_records_json": bool(record_papers),
            "has_analysis_json": bool(analysis_papers),
        },
    }


def count_scored_ref_papers(folder_safe: str) -> int:
    return len(_iter_scored_ref_items(folder_safe))


def count_scored_student_boxes(folder_safe: str) -> int:
    """已统分学生数：按试卷框去重，1 个试卷框 = 1 名学生。"""
    boxes = {_paper_box_display_name(filename) for filename, _ in _iter_scored_ref_items(folder_safe)}
    return len(boxes)


def collect_essay_payload(folder_safe: str) -> dict[str, Any]:
    """作文批改：文件夹内全部已批改试卷（作文模式保持原逻辑）。"""
    from app.grading.router import _read_essay_history

    history = _read_essay_history(folder_safe)
    completed = history.get("completed") if isinstance(history.get("completed"), dict) else {}
    full_score = history.get("full_score")
    students: list[dict[str, Any]] = []
    scores: list[float] = []
    for filename, info in completed.items():
        if not isinstance(info, dict):
            continue
        if not is_paper_shows_graded_badge(info, source="essay"):
            continue
        box_name = _paper_box_display_name(filename)
        score_val: Optional[float] = None
        if info.get("score_total") is not None:
            try:
                score_val = float(info.get("score_total"))
                scores.append(score_val)
            except Exception:
                pass
        result_text = str(info.get("result") or "")
        students.append(
            {
                "student_box": box_name,
                "filename": filename,
                "score_total": score_val,
                "result_excerpt": _safe_excerpt(result_text, limit=800),
                "image_annotated": str(info.get("image_annotated") or ""),
            }
        )
    students.sort(
        key=lambda x: (
            float(x.get("score_total")) if x.get("score_total") is not None else -1.0,
            str(x.get("student_box") or ""),
        ),
        reverse=True,
    )
    class_meta = _load_class_meta(_parse_class_id(folder_safe))
    return {
        "exam_name": _display_folder_name(folder_safe),
        "folder_safe": folder_safe,
        "report_kind": "essay",
        "class": class_meta,
        "paper_count": len(students),
        "score_summary": {
            "count": len(scores),
            "average": round(sum(scores) / len(scores), 1) if scores else None,
            "max": max(scores) if scores else None,
            "min": min(scores) if scores else None,
            "full_score": full_score,
        },
        "students": students,
    }


def collect_manual_payload(folder_safe: str) -> dict[str, Any]:
    """答题卡（自主阅卷）：文件夹内全部已阅完（有总分）的试卷成绩单。"""
    history = _read_grading_history(folder_safe, "manual")
    completed = history.get("completed") if isinstance(history.get("completed"), dict) else {}
    full_score = history.get("full_score")
    students: list[dict[str, Any]] = []
    scores: list[float] = []
    for filename, info in completed.items():
        if not isinstance(info, dict):
            continue
        # manual 的 result 是 JSON 字符串、无 ref 的「badge」概念，直接以 score_total 判已阅完
        score_val = info.get("score_total")
        if score_val is None:
            continue
        try:
            fscore = float(score_val)
        except (TypeError, ValueError):
            continue
        scores.append(fscore)
        students.append(
            {
                "student_box": _paper_box_display_name(str(filename)),
                "score_total": fscore,
            }
        )
    students.sort(key=lambda x: float(x["score_total"]), reverse=True)
    class_meta = _load_class_meta(_parse_class_id(folder_safe))
    return {
        "exam_name": _display_folder_name(folder_safe),
        "folder_safe": folder_safe,
        "report_kind": "manual",
        "class": class_meta,
        "student_count": len(students),
        "paper_count": len(students),
        "score_summary": {
            "count": len(scores),
            "average": round(sum(scores) / len(scores), 1) if scores else None,
            "max": max(scores) if scores else None,
            "min": min(scores) if scores else None,
            "full_score": full_score,
        },
        "score_ranking": [
            {
                "rank": idx + 1,
                "student_box": s["student_box"],
                "score_total": s["score_total"],
                "wrong_count": None,
            }
            for idx, s in enumerate(students)
        ],
    }
