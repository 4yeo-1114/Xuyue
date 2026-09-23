from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.grading import reference_vlm_grading, router as grading_router, wrong_question_db


def _write_history(path: Path, *, engine: str, updated_at: str, completed: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "engine": engine,
                "updated_at": updated_at,
                "completed": completed or {},
                "failed": {},
                "scoring_config": None,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _manual_item(name: str, blocks: list[dict], score_total: float) -> dict:
    question_scores = {
        str(block["title"]): float(block.get("score") or 0)
        for block in blocks
        if block.get("status") != "ungraded"
    }
    return {
        "name": name,
        "result": json.dumps(
            {
                "type": "manual_analyze",
                "version": 2,
                "manual_status": "graded",
                "blocks": blocks,
                "scores": question_scores,
                "score_total": score_total,
            },
            ensure_ascii=False,
        ),
        "score_total": score_total,
        "question_scores": question_scores,
    }


def test_latest_grading_history_uses_updated_at(tmp_path, monkeypatch):
    monkeypatch.setattr(grading_router, "grading_history_dir", lambda: tmp_path)
    _write_history(
        tmp_path / "exam.json",
        engine="baidu",
        updated_at="2026-01-01T00:00:00+00:00",
        completed={"old.jpg": {"name": "old.jpg", "result": "旧结果"}},
    )
    _write_history(
        tmp_path / "exam__manual.json",
        engine="manual",
        updated_at="2026-01-02T00:00:00+00:00",
        completed={"new.jpg": {"name": "new.jpg", "result": "新结果"}},
    )

    history, storage_engine = grading_router._latest_grading_history("exam")

    assert storage_engine == "manual"
    assert history["engine"] == "manual"
    assert set(history["completed"]) == {"new.jpg"}


def test_replace_folder_run_deletes_all_old_result_artifacts(tmp_path, monkeypatch):
    history_dir = tmp_path / "history"
    modify_dir = tmp_path / "modify"
    modify_dir.mkdir()
    smart_mark = modify_dir / "annotated_ref_exam_甲_1.jpg"
    manual_mark = modify_dir / "marks_only_manual_exam_乙_1.jpg"
    smart_mark.write_bytes(b"old-smart")
    manual_mark.write_bytes(b"old-manual")
    _write_history(
        history_dir / "exam.json",
        engine="baidu",
        updated_at="2026-01-01T00:00:00+00:00",
        completed={
            "甲_1.jpg": {
                "name": "甲_1.jpg",
                "result": "旧结果",
                "image_annotated": "/api/v1/grading/modify/annotated_ref_exam_甲_1.jpg?t=1",
            }
        },
    )
    _write_history(
        history_dir / "exam__manual.json",
        engine="manual",
        updated_at="2026-01-02T00:00:00+00:00",
        completed={
            "乙_1.jpg": {
                "name": "乙_1.jpg",
                "result": "旧结果",
                "image_marks_only": "/api/v1/grading/modify/marks_only_manual_exam_乙_1.jpg?t=2",
            }
        },
    )
    cleanup_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(grading_router, "grading_history_dir", lambda: history_dir)
    monkeypatch.setattr(grading_router, "modify_dir", lambda: modify_dir)
    monkeypatch.setattr(
        wrong_question_db,
        "delete_exam_wrong_question_file",
        lambda safe: cleanup_calls.append(("wrong", safe)),
    )
    monkeypatch.setattr(
        reference_vlm_grading,
        "delete_reference_vlm_folder_artifacts",
        lambda safe: cleanup_calls.append(("reference", safe)),
    )

    grading_router._replace_folder_grading_run("exam", "aliyun")

    assert not smart_mark.exists()
    assert not manual_mark.exists()
    assert not (history_dir / "exam__manual.json").exists()
    new_history = json.loads((history_dir / "exam.json").read_text(encoding="utf-8"))
    assert new_history["engine"] == "aliyun"
    assert new_history["completed"] == {}
    assert new_history["failed"] == {}
    assert cleanup_calls == [("wrong", "exam"), ("reference", "exam")]


def test_manual_history_is_normalized_to_smart_detail_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(grading_router, "grading_history_dir", lambda: tmp_path)
    monkeypatch.setattr(grading_router, "correct_docs_dir", lambda: tmp_path / "papers")
    student_a = _manual_item(
        "甲_1.jpg",
        [
            {"index": 1, "title": "第1题-作答区1", "status": "correct", "score": 2},
            {"index": 1, "title": "第1题-作答区2", "status": "wrong", "score": 0},
            {"index": 2, "title": "第2题-作答区1", "status": "unanswered", "score": 0},
        ],
        2,
    )
    student_b = _manual_item(
        "乙_1.jpg",
        [
            {"index": 1, "title": "第1题-作答区1", "status": "correct", "score": 2},
            {"index": 1, "title": "第1题-作答区2", "status": "correct", "score": 2},
            {"index": 2, "title": "第2题-作答区1", "status": "partial", "score": 1},
        ],
        5,
    )
    _write_history(
        tmp_path / "exam__manual.json",
        engine="manual",
        updated_at="2026-01-02T00:00:00+00:00",
        completed={"甲_1.jpg": student_a, "乙_1.jpg": student_b},
    )

    result = asyncio.run(grading_router.api_get_error_book_folder_detail("exam"))
    stats = asyncio.run(grading_router.api_get_error_book_folder_stats("exam"))

    assert result["source_engine"] == "manual"
    assert stats == {
        "ok": True,
        "student_count": 2,
        "question_count": 2,
        "error_rate": 75.0,
    }
    questions = {question["title"]: question for question in result["questions"]}
    assert (questions["第1题"]["correct"], questions["第1题"]["wrong"]) == (1, 1)
    assert len(questions["第1题"]["subItems"]) == 2
    assert (questions["第2题"]["wrong"], questions["第2题"]["blank"]) == (1, 1)
    students = {student["filename"]: student for student in result["students"]}
    assert students["甲"]["score_total"] == 2
    assert students["乙"]["score_total"] == 5
    assert "第1题-作答区 2" in students["甲"]["wrong_questions"]
