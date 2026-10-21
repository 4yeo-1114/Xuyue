# -*- coding: utf-8 -*-
"""统分按标准答题区来（2026-10-16）：题清单=老师手改过的答题区，分值=标准试卷卷面。

锁三件事：
1. _standard_scoring_questions：跨页全局重编号（第1页第N题→第N题，第2页第N题→第(M+N)题），
   印刷题号/空数/答案摘要带齐；
2. _score_ai_result_by_config(title_offset=…)：批改结果文本的页内题号折算到全局键查分，
   details 仍存页内题号（前端按 blocks 对照展示）；
3. api_auto_scoring_config 优先走标准答题区（不依赖批改历史），返回/落库结构完整。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.grading import reference_vlm_grading, router as grading_router
from app.grading.router import (
    _score_ai_result_by_config,
    _scoring_title_offsets,
    _standard_scoring_questions,
    api_auto_scoring_config,
)


def _write_answer_table(docs: Path, folder: str, pages: dict) -> None:
    """写 .reference_answer_table.json（与 save_reference_answer_table_edits 同构）。"""
    folder_dir = docs / folder
    folder_dir.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "updated_at": "2026-10-16T00:00:00", "pages": pages}
    (folder_dir / ".reference_answer_table.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _entry(display_index, printed_no, slots):
    return {
        "display_index": display_index,
        "printed_no": printed_no,
        "question_bbox": [0, 0, 10, 10],
        "slots": slots,
        "full_answer": "\n".join(s["answer_text"] for s in slots),
    }


def _slot(sub_index, text):
    return {"sub_index": sub_index, "bbox": [0, 0, 5, 5], "answer_text": text}


@pytest.fixture()
def fake_docs(tmp_path, monkeypatch):
    docs = tmp_path / "papers"
    monkeypatch.setattr(grading_router, "correct_docs_dir", lambda: docs)
    monkeypatch.setattr(reference_vlm_grading, "correct_docs_dir", lambda: docs)
    return docs


def test_standard_scoring_questions_numbers_across_pages(fake_docs, monkeypatch):
    """P1 13 题（display 1..13）→ 第1..13题；P2 3 题（display 1..3）→ 第14..16题。"""
    safe = "cls_test"
    _write_answer_table(
        fake_docs,
        safe,
        {
            "1": {
                "questions": [
                    _entry(1, "1", [_slot(1, "肢"), _slot(2, "体")]),
                    _entry(2, "2", [_slot(1, "A")]),
                    _entry(13, "13", [_slot(1, "站")]),
                    _entry(6, "", [_slot(1, "C")]),
                ]
            },
            "2": {
                "questions": [
                    _entry(2, "2", [_slot(1, "放弃"), _slot(2, "冷静")]),
                    _entry(1, "", [_slot(1, "抖擞")]),
                    _entry(3, "", [_slot(1, "死心眼")]),
                ]
            },
        },
    )
    monkeypatch.setattr(
        grading_router,
        "_reference_standard_sources",
        lambda _safe: {1: (Path("标准答案.png"), Path("标准答案.png")),
                       2: (Path("标准答案_2.png"), Path("标准答案_2.png"))},
    )

    questions = _standard_scoring_questions(safe)
    keys = [q["key"] for q in questions]
    # 第1页 display 1,2,13,6 → 1,2,13,6；第2页偏移13：display 2,1,3 → 15,14,16
    assert keys == ["第1题", "第2题", "第13题", "第6题", "第15题", "第14题", "第16题"]
    by_key = {q["key"]: q for q in questions}
    assert by_key["第1题"]["printed_no"] == "1"
    assert by_key["第1题"]["slot_count"] == 2
    assert by_key["第1题"]["answer_preview"] == "肢、体"
    assert by_key["第6题"]["printed_no"] == ""
    assert by_key["第14题"]["page_no"] == 2
    assert by_key["第14题"]["display_no"] == 1
    # 偏移：第1页 0，第2页 13
    offsets = {q["page_no"]: int(q["key"][1:-1]) - q["display_no"] for q in questions}
    assert offsets == {1: 0, 2: 13}


def test_standard_scoring_questions_empty_without_answer_table(fake_docs):
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(
            grading_router, "_reference_standard_sources", lambda _safe: {1: (Path("a.png"), Path("a.png"))}
        )
        assert _standard_scoring_questions("cls_none") == []
    finally:
        monkeypatch.undo()


def test_score_by_config_maps_page_local_title_via_offset():
    """第2页结果文本的「第1题」→ 全局键「第14题」查分；details 仍存「第1题」。"""
    text = (
        "总题量：2；正确：1；错误：1；半对：0；未作答：0；待确认：0\n逐题讲解：\n"
        "第1题-作答区1：对 - 答案正确\n第1题-作答区2：错 - 写错了\n"
        "第2题：对 - 完全正确"
    )
    config = {"第1题": 7.0, "第14题": 6.0, "第15题": 4.0}
    total, details = _score_ai_result_by_config(text, config, None, title_offset=13)
    # 第1题（=第14题，6分）：2空对1空 → 3.0；第2题（=第15题，4分）：全对 → 4.0
    assert details == {"第1题": 3.0, "第2题": 4.0}
    assert total == 7.0

    # offset=0（第1页）：直接按页内题号查
    total1, details1 = _score_ai_result_by_config(text, {"第1题": 7.0, "第2题": 4.0})
    assert details1 == {"第1题": 3.5, "第2题": 4.0}
    assert total1 == 7.5


def test_scoring_title_offsets_from_standard_table(fake_docs):
    safe = "cls_off"
    _write_answer_table(
        fake_docs,
        safe,
        {
            "1": {"questions": [_entry(1, "1", [_slot(1, "A")]), _entry(3, "3", [_slot(1, "B")])]},
            "2": {"questions": [_entry(1, "", [_slot(1, "C")])]},
        },
    )
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(
            grading_router,
            "_reference_standard_sources",
            lambda _safe: {1: (Path("标准答案.png"), Path("标准答案.png")),
                           2: (Path("标准答案_2.png"), Path("标准答案_2.png"))},
        )
        assert _scoring_title_offsets(safe, {}) == {1: 0, 2: 3}
    finally:
        monkeypatch.undo()


def test_auto_scoring_config_prefers_standard_questions(fake_docs, monkeypatch):
    """标准答题区存在 → 不查批改历史；题清单/读卷图都用标准答案链，paper_subs 返回空。"""
    safe = "cls_auto"
    _write_answer_table(
        fake_docs,
        safe,
        {
            "1": {"questions": [_entry(1, "1", [_slot(1, "肢"), _slot(2, "体")])]},
            "2": {"questions": [_entry(1, "", [_slot(1, "抖擞")])]},
        },
    )
    monkeypatch.setattr(
        grading_router,
        "_reference_standard_sources",
        lambda _safe: {1: (Path("标准答案.png"), Path("标准答案.png")),
                       2: (Path("标准答案_2.png"), Path("标准答案_2.png"))},
    )
    # 批改历史不存在也不该走它；写库记下来就好
    written = {}
    monkeypatch.setattr(grading_router, "_read_grading_history", lambda _safe: {})
    monkeypatch.setattr(
        grading_router, "_write_grading_history", lambda _safe, data: written.update(data)
    )
    captured = {}

    def fake_vision(db, image_paths, question_keys, descriptions):
        captured["image_paths"] = list(image_paths)
        captured["question_keys"] = list(question_keys)
        captured["descriptions"] = list(descriptions)
        return {
            "full_score": 10,
            "scores": {k: 5.0 for k in question_keys},
            "major_scores": {"一": 10},
            "structure": [
                {"index": 1, "major": "一", "sub": "1", "title": "读拼音", "display": "一、1", "score": 5, "question_text": "读拼音"},
                {"index": 2, "major": "一", "sub": "2", "title": "写词语", "display": "一、2", "score": 5, "question_text": "写词语"},
            ],
            "question_texts": {},
            "gaps": [],
            "items": [{"major": "一", "sub": "", "title": "积累与运用", "score": 10}],
            "order": ["一"],
            "paper_subs": {"一": [{"num": "1", "score": 5}, {"num": "2", "score": 5}]},
            "blank_count_map": {"第2题": {"blanks": 1, "kind": "blank"}},
        }

    monkeypatch.setattr(grading_router, "_vision_read_full_scores", fake_vision)
    monkeypatch.setattr(
        grading_router,
        "get_grading_user_id",
        lambda: "test-user",
    )

    res = api_auto_scoring_config(safe, db=None)

    assert res["ok"] is True
    # 题清单来自答题区（跨页全局键），不是批改结果
    assert captured["question_keys"] == ["第1题", "第2题"]
    assert captured["image_paths"] == [Path("标准答案.png"), Path("标准答案_2.png")]
    assert "印刷题号「1」" in captured["descriptions"][0]
    assert res["scoring_config"] == {"第1题": 5.0, "第2题": 5.0}
    assert res["question_titles"] == ["第1题", "第2题"]
    # 标准答题区路径：逐题行直接绑 scoring_config，不用卷面折叠小题清单
    assert res["paper_subs"] == {}
    # 结构带上印刷题号（界面行标签）
    assert res["question_structure"]["第1题"]["printed_no"] == "1"
    assert written["question_structure"]["第1题"]["printed_no"] == "1"
    assert written["paper_subs"] == {}
    assert written["blank_count_map"] == {"第2题": {"blanks": 1, "kind": "blank"}}
