# -*- coding: utf-8 -*-
"""轻成绩表读写（对齐批改君 exam_scores）：批改历史 → grading_score_summaries。

写入口 sync_folder_score_summaries：从 default+manual+essay 三份批改历史聚合
每生一行（智能/参照/自主多页求和、作文多页取最大且命中即整卷权威，
与 auto_class_sync.extract_scores_from_completed / 前端 box_totals 同口径），
delete-then-insert 重建本文件夹的行。

批改历史 JSON 是唯一事实源：重批清史后重建即自愈，不维护增量状态；
未统分条目（无 score_total）不落行。班级/普通文件夹都写（class_id 可空）。

调用方需在 grading 用户上下文中（读历史依赖 user_paths）。
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional


def _num(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _result_json(info: dict) -> dict:
    raw = info.get("result")
    if not isinstance(raw, str) or not raw.strip().startswith("{"):
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _score_total_of(info: dict) -> Optional[float]:
    """与 router._item_score_total 同口径：条目级 score_total 优先，结果 JSON 兜底。"""
    num = _num(info.get("score_total"))
    if num is not None:
        return num
    return _num(_result_json(info).get("score_total"))


def _max_score_of(info: dict) -> Optional[float]:
    """整页满分：结果 JSON 的 max_score_total 优先，块 max_score 求和兜底。"""
    num = _num(_result_json(info).get("max_score_total"))
    if num is not None:
        return num
    blocks = info.get("blocks")
    if isinstance(blocks, list) and blocks:
        total = 0.0
        seen = False
        for block in blocks:
            if isinstance(block, dict) and block.get("max_score") is not None:
                total += _num(block.get("max_score")) or 0.0
                seen = True
        return total if seen else None
    return None


def _question_scores_of(info: dict) -> Dict[str, float]:
    """逐题分：条目级 question_scores（统分/手动修正写入）优先，结果 JSON 的 scores 兜底。"""
    raw = info.get("question_scores")
    if not isinstance(raw, dict):
        raw = _result_json(info).get("scores")
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, float] = {}
    for key, value in raw.items():
        num = _num(value)
        if num is not None:
            out[str(key)] = num
    return out


def _new_slot() -> dict:
    return {
        "max_score": 0.0,
        "has_max": False,
        "question_scores": {},
        "engine": "",
    }


def build_folder_summary_rows(folder_safe: str) -> list[dict]:
    """聚合批改历史 → 每生一行的纯数据行（不含 user_id/学生匹配，便于单测）。"""
    from app.services.auto_class_sync import (
        extract_scores_from_completed,
        merge_completed,
        paper_box_display_name,
        parse_class_folder,
        read_folder_meta,
    )
    from app.grading.router import _read_essay_history, _read_grading_history

    default_data = _read_grading_history(folder_safe, "default") or {}
    manual_data = _read_grading_history(folder_safe, "manual") or {}
    essay_data = _read_essay_history(folder_safe) or {}
    default_completed = default_data.get("completed") or {}
    manual_completed = manual_data.get("completed") or {}
    essay_completed = essay_data.get("completed") or {}

    def _normalized(completed: Any) -> Dict[str, Any]:
        # 条目级缺 score_total 时从结果 JSON 兜底（与 router._item_score_total 同口径），
        # 再交给现成聚合器——聚合规则（多页求和/作文整箱权威）只有它一份
        out: Dict[str, Any] = {}
        for filename, info in (completed or {}).items():
            if not isinstance(info, dict):
                continue
            num = _score_total_of(info)
            if num is not None and info.get("score_total") is None:
                info = dict(info)
                info["score_total"] = num
            out[filename] = info
        return out

    # 总分口径交给现成聚合器（多页求和 / 作文取最大且整箱权威）
    completed = merge_completed(_normalized(default_completed), _normalized(manual_completed))
    totals = extract_scores_from_completed(completed, _normalized(essay_completed))
    if not totals:
        return []

    default_stamp = str(default_data.get("engine") or "").strip() or "default"
    meta: Dict[str, dict] = {}

    def _meta_feed(filename: Any, info: Any, fallback_engine: str) -> None:
        if not isinstance(info, dict):
            return
        box = paper_box_display_name(str(filename or ""))
        if not box:
            return
        slot = meta.setdefault(box, _new_slot())
        maxs = _max_score_of(info)
        if maxs is not None:
            slot["max_score"] += maxs
            slot["has_max"] = True
        slot["question_scores"].update(_question_scores_of(info))
        engine = str(info.get("engine") or fallback_engine or "").strip()
        if engine:
            slot["engine"] = engine

    for filename, info in default_completed.items():
        _meta_feed(filename, info, default_stamp)
    # manual 后喂：同名文件人工结果覆盖智能结果（与 merge_completed 同序）
    for filename, info in manual_completed.items():
        _meta_feed(filename, info, "manual")
    # 作文：总分口径里作文整卷权威 → 引擎跟着标 essay
    for filename, info in essay_completed.items():
        box = paper_box_display_name(str(filename or ""))
        if box and box in totals:
            meta.setdefault(box, _new_slot())["engine"] = "essay"

    parsed = parse_class_folder(folder_safe)
    class_id, exam_name = parsed if parsed else (None, folder_safe)
    subject = str((read_folder_meta(folder_safe) or {}).get("subject") or "").strip()

    rows: list[dict] = []
    for box, score in totals.items():
        slot = meta.get(box) or _new_slot()
        rows.append(
            {
                "student_name": box,
                "class_id": class_id,
                "exam_name": exam_name,
                "subject": subject or None,
                "score_total": float(score),
                "max_score": round(slot["max_score"], 2) if slot["has_max"] else None,
                "question_scores": slot["question_scores"] or None,
                "engine": slot["engine"] or None,
            }
        )
    rows.sort(key=lambda r: r["student_name"])
    return rows


def sync_folder_score_summaries(user_id: str, folder_safe: str) -> dict:
    """重建该文件夹的成绩汇总行（delete-then-insert）。

    幂等：以批改历史为唯一事实源整文件夹重建，两次调用结果一致；
    历史被清空 → 行清空。失败向上抛（调用方旁路 try/except，不阻断批改主链路）。
    """
    if not user_id or not folder_safe:
        return {"skipped": "no_identity"}
    rows = build_folder_summary_rows(folder_safe)

    from app.database import SessionLocal
    from app.models.grading_score_summary import GradingScoreSummary

    db = SessionLocal()
    try:
        # 姓名 best-effort 匹配学生（与学情导入同为按名对齐；匹配不上留空）
        student_ids: Dict[str, str] = {}
        if rows and rows[0].get("class_id"):
            from app.models.student import Student

            names = [r["student_name"] for r in rows]
            for stu in (
                db.query(Student)
                .filter(Student.class_id == rows[0]["class_id"], Student.name.in_(names))
                .all()
            ):
                student_ids.setdefault(str(stu.name), str(stu.id))

        db.query(GradingScoreSummary).filter(
            GradingScoreSummary.user_id == user_id,
            GradingScoreSummary.folder_safe == folder_safe,
        ).delete()
        for row in rows:
            db.add(
                GradingScoreSummary(
                    user_id=user_id,
                    folder_safe=folder_safe,
                    class_id=row.get("class_id"),
                    student_id=student_ids.get(row["student_name"]),
                    student_name=row["student_name"],
                    exam_name=row.get("exam_name"),
                    subject=row.get("subject"),
                    score_total=row.get("score_total"),
                    max_score=row.get("max_score"),
                    question_scores=row.get("question_scores"),
                    engine=row.get("engine"),
                )
            )
        db.commit()
        return {"rows": len(rows), "folder": folder_safe, "class_id": rows[0].get("class_id") if rows else None}
    finally:
        db.close()


def get_folder_score_summaries(user_id: str, folder_safe: str) -> list[dict]:
    """读该文件夹的汇总行（按学生名升序）。"""
    from app.database import SessionLocal
    from app.models.grading_score_summary import GradingScoreSummary

    db = SessionLocal()
    try:
        rows = (
            db.query(GradingScoreSummary)
            .filter(
                GradingScoreSummary.user_id == user_id,
                GradingScoreSummary.folder_safe == folder_safe,
            )
            .order_by(GradingScoreSummary.student_name.asc())
            .all()
        )
        return [
            {
                "student_name": r.student_name,
                "student_id": r.student_id,
                "class_id": r.class_id,
                "exam_name": r.exam_name,
                "subject": r.subject,
                "score_total": r.score_total,
                "max_score": r.max_score,
                "question_scores": r.question_scores,
                "engine": r.engine,
                "graded_at": r.graded_at.isoformat() if r.graded_at else None,
            }
            for r in rows
        ]
    finally:
        db.close()
