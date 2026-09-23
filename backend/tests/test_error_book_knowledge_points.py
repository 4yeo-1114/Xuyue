from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.grading import router as grading_router
from app.grading import wrong_question_db


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _write_history(history_dir: Path, safe: str, *, engine: str, result_text: str) -> None:
    path = history_dir / f"{safe}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "engine": engine,
                "updated_at": "2026-01-02T00:00:00+00:00",
                "completed": {"小明_1.jpg": {"name": "小明_1.jpg", "result": result_text}},
                "failed": {},
                "scoring_config": None,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _sample_analysis() -> dict:
    return {
        "papers": {
            "小明_1.jpg": {
                "wrong_question_analysis": [
                    {
                        "display_title": "第1题-作答区1",
                        "analysis": {"knowledge_points": ["分数加减", "通分"]},
                    },
                    {
                        "display_title": "第1题-作答区2",
                        "analysis": {"knowledge_points": ["通分", "约分"]},
                    },
                    {
                        "display_title": "第2题",
                        "analysis": {"knowledge_points": ["一元一次方程"]},
                    },
                ]
            }
        }
    }


def test_collect_wrong_question_knowledge_points_merges_by_title(tmp_path, monkeypatch):
    ct_root = tmp_path / "ct"
    monkeypatch.setattr(wrong_question_db, "_ct_root", lambda: ct_root)
    _write_json(
        ct_root / "cls_test" / "analysis" / "期中.json",
        _sample_analysis(),
    )

    result = wrong_question_db.collect_wrong_question_knowledge_points("cls_test__期中")

    assert result == {
        "第1题-作答区1": ["分数加减", "通分"],
        "第1题-作答区2": ["通分", "约分"],
        "第2题": ["一元一次方程"],
    }


def test_collect_wrong_question_knowledge_points_missing_analysis(tmp_path, monkeypatch):
    ct_root = tmp_path / "ct"
    monkeypatch.setattr(wrong_question_db, "_ct_root", lambda: ct_root)

    assert wrong_question_db.collect_wrong_question_knowledge_points("cls_test__期中") == {}


def test_detail_attaches_knowledge_points_to_questions(tmp_path, monkeypatch):
    history_dir = tmp_path / "history"
    ct_root = tmp_path / "ct"
    monkeypatch.setattr(grading_router, "grading_history_dir", lambda: history_dir)
    monkeypatch.setattr(grading_router, "correct_docs_dir", lambda: tmp_path / "papers")
    monkeypatch.setattr(wrong_question_db, "_ct_root", lambda: ct_root)

    _write_history(
        history_dir,
        "cls_test__期中",
        engine="baidu",
        result_text="第1题: 正确\n第1题: 错误\n第2题: 未作答\n",
    )
    _write_json(
        ct_root / "cls_test" / "analysis" / "期中.json",
        _sample_analysis(),
    )

    result = asyncio.run(
        grading_router.api_get_error_book_folder_detail("cls_test__期中")
    )

    questions = {q["title"]: q for q in result["questions"]}

    # 主题：各作答区知识点并集、去重保序
    assert questions["第1题"]["knowledge_points"] == ["分数加减", "通分", "约分"]
    # 单作答区：直接用该题自己的知识点
    assert questions["第2题"]["knowledge_points"] == ["一元一次方程"]

    sub_items = questions["第1题"]["subItems"]
    assert len(sub_items) == 2
    assert sub_items[0]["knowledge_points"] == ["分数加减", "通分"]
    assert sub_items[1]["knowledge_points"] == ["通分", "约分"]
    assert "knowledge_points" not in sub_items[0].get("subItems", {})


def test_detail_attaches_empty_knowledge_points_when_analysis_missing(tmp_path, monkeypatch):
    history_dir = tmp_path / "history"
    monkeypatch.setattr(grading_router, "grading_history_dir", lambda: history_dir)
    monkeypatch.setattr(grading_router, "correct_docs_dir", lambda: tmp_path / "papers")
    # 不写 analysis 文件
    _write_history(
        history_dir,
        "exam",
        engine="baidu",
        result_text="第1题: 错误\n",
    )

    result = asyncio.run(grading_router.api_get_error_book_folder_detail("exam"))

    assert result["questions"][0]["knowledge_points"] == []
