# -*- coding: utf-8 -*-
"""切题审查分值接入统分（参考答案批改能改分/统分）+ 识别答案回显合并。

锁四件事：
1. _reference_layout_slot_scores：已确认布局里老师填的分值按 (页号, 页内题号) 汇总；
   整题没填过 → 不出现（统分退回卷面读分）；填过但个别空没填 → 没填的空按 1 分
   （与切题弹窗占位、手动批改默认同口径）。
2. api_auto_scoring_config 快路径：每题分值都填满 → source=layout 直接返回、不进 VL。
3. 老师填的分值盖掉 VL 结果；VL 读不到分且有标准答题区 → 返回题清单（缺分给 0）
   不报错，让老师在统分设置里手动填（修「报错却无处可填」的死路）。
4. _answer_table_derived_answers + api_get_answer_key(include_table=)：识别答案按
   「全卷题号_空号」补缺回显；老师保存的优先（只补缺不覆盖）。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.grading import reference_vlm_grading, router as grading_router
from app.grading.router import (
    _answer_table_derived_answers,
    _reference_layout_slot_scores,
    _standard_scoring_questions,
    api_auto_scoring_config,
    api_get_answer_key,
)


def _write_answer_table(docs: Path, folder: str, pages: dict) -> None:
    folder_dir = docs / folder
    folder_dir.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "updated_at": "2026-11-08T00:00:00", "pages": pages}
    (folder_dir / ".reference_answer_table.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _write_layout(docs: Path, folder: str, page_questions: dict) -> None:
    """写已确认的切题审查布局（.reference_vlm_layout.json）。"""
    folder_dir = docs / folder
    folder_dir.mkdir(parents=True, exist_ok=True)
    pages = {
        str(page_no): {
            "page_no": int(page_no),
            "layout": {"page_no": int(page_no), "questions": questions},
        }
        for page_no, questions in page_questions.items()
    }
    payload = {"version": 1, "status": "confirmed", "updated_at": "2026-11-08T00:00:00", "pages": pages}
    (folder_dir / ".reference_vlm_layout.json").write_text(
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


def _q(display_no, slots):
    return {
        "display_no": display_no,
        "question_id": f"q-{display_no}",
        "regions": [{"region_id": f"r-{display_no}", "bbox": [0, 0, 10, 10]}],
        "answer_slots": [
            {"slot_id": f"s-{display_no}-{i}", **({"max_score": v} if v is not None else {})}
            for i, v in enumerate(slots, start=1)
        ],
    }


@pytest.fixture()
def fake_docs(tmp_path, monkeypatch):
    docs = tmp_path / "papers"
    monkeypatch.setattr(grading_router, "correct_docs_dir", lambda: docs)
    monkeypatch.setattr(reference_vlm_grading, "correct_docs_dir", lambda: docs)
    monkeypatch.setattr(
        grading_router,
        "_reference_standard_sources",
        lambda _safe: {
            1: (Path("标准答案.png"), Path("标准答案.png")),
            2: (Path("标准答案_2.png"), Path("标准答案_2.png")),
        },
    )
    return docs


def test_layout_slot_scores_sum_and_defaults(fake_docs):
    """已填 → Σ（没填的空按 1）；整题没填过 → 不出现。"""
    safe = "cls_slot"
    _write_layout(
        fake_docs,
        safe,
        {
            "1": [_q(1, [3, 3]), _q(2, [4])],
            "2": [_q(1, [5, None]), _q(2, [None, None])],
        },
    )
    scores = _reference_layout_slot_scores(safe)
    assert scores == {(1, 1): 6.0, (1, 2): 4.0, (2, 1): 6.0}
    # (2, 2) 整题没填过：不出现，统分退回卷面读分
    assert (2, 2) not in scores


def test_standard_scoring_questions_carries_max_score(fake_docs):
    """答题区题清单带上切题审查分值（跨页全局键）；没填过的题为 None。"""
    safe = "cls_std"
    _write_answer_table(
        fake_docs,
        safe,
        {
            "1": {"questions": [_entry(1, "1", [_slot(1, "A"), _slot(2, "B")]), _entry(2, "2", [_slot(1, "C")])]},
            "2": {"questions": [_entry(1, "", [_slot(1, "D")])]},
        },
    )
    _write_layout(fake_docs, safe, {"1": [_q(1, [3, 3]), _q(2, [4])], "2": [_q(1, [5])]})
    by_key = {q["key"]: q for q in _standard_scoring_questions(safe)}
    assert by_key["第1题"]["max_score"] == 6.0
    assert by_key["第2题"]["max_score"] == 4.0
    assert by_key["第3题"]["max_score"] == 5.0  # P2 display 1 → 全局第3题


def test_auto_scoring_fast_path_skips_vl(fake_docs, monkeypatch):
    """每题分值填满 → source=layout 直接返回，VL 不跑、不占重活闸。"""
    safe = "cls_fast"
    _write_answer_table(
        fake_docs,
        safe,
        {
            "1": {"questions": [_entry(1, "1", [_slot(1, "A")]), _entry(2, "2", [_slot(1, "B")])]},
        },
    )
    _write_layout(fake_docs, safe, {"1": [_q(1, [6]), _q(2, [4])]})

    def boom(*_a, **_k):
        raise AssertionError("快路径不该进 VL")

    monkeypatch.setattr(grading_router, "_vision_read_full_scores", boom)
    monkeypatch.setattr(grading_router, "_read_grading_history", lambda _safe: {})
    written = {}
    monkeypatch.setattr(
        grading_router, "_write_grading_history", lambda _safe, data: written.update(data)
    )

    res = api_auto_scoring_config(safe, db=None)

    assert res["ok"] is True
    assert res["source"] == "layout"
    assert res["scoring_config"] == {"第1题": 6.0, "第2题": 4.0}
    assert res["full_score"] == 10.0
    assert res["question_structure"]["第1题"]["printed_no"] == "1"
    assert written["paper_subs"] == {}


def test_auto_scoring_layout_overrides_vl(fake_docs, monkeypatch):
    """只填了部分题：VL 兜底其余题，老师填过的盖掉 VL。"""
    safe = "cls_mix"
    _write_answer_table(
        fake_docs,
        safe,
        {
            "1": {"questions": [_entry(1, "1", [_slot(1, "A")]), _entry(2, "2", [_slot(1, "B")])]},
        },
    )
    _write_layout(fake_docs, safe, {"1": [_q(1, [6])]})  # 第2题没填
    monkeypatch.setattr(
        grading_router,
        "_vision_read_full_scores",
        lambda _db, _imgs, keys, _desc: {"full_score": 12, "scores": {k: 5.0 for k in keys}},
    )
    monkeypatch.setattr(grading_router, "_read_grading_history", lambda _safe: {})
    monkeypatch.setattr(
        grading_router, "_write_grading_history", lambda _safe, data: None
    )

    res = api_auto_scoring_config(safe, db=None)

    assert res["scoring_config"] == {"第1题": 6.0, "第2题": 5.0}
    assert res.get("source") != "layout"


def test_auto_scoring_vl_unusable_returns_manual_list(fake_docs, monkeypatch):
    """卷面读不到分 + 有标准答题区：返回题清单（缺分 0）不报错，老师手动填。"""
    safe = "cls_manual_fill"
    _write_answer_table(
        fake_docs,
        safe,
        {
            "1": {"questions": [_entry(1, "1", [_slot(1, "A")]), _entry(2, "2", [_slot(1, "B")])]},
        },
    )
    _write_layout(fake_docs, safe, {"1": [_q(1, [6])]})
    monkeypatch.setattr(grading_router, "_vision_read_full_scores", lambda *_a, **_k: None)
    monkeypatch.setattr(grading_router, "_read_grading_history", lambda _safe: {})
    monkeypatch.setattr(
        grading_router, "_write_grading_history", lambda _safe, data: None
    )

    res = api_auto_scoring_config(safe, db=None)

    assert res["ok"] is True
    assert res["scoring_config"] == {"第1题": 6.0, "第2题": 0.0}
    assert res["question_titles"] == ["第1题", "第2题"]


def test_answer_key_include_table_merges_missing(fake_docs, monkeypatch):
    """识别答案按「全卷题号_空号」补缺回显；老师保存的优先。"""
    safe = "cls_merge"
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
        "_read_grading_history",
        lambda *_a, **_k: {"answer_key": {"raw": "1_1 老师写的", "answers": {"1_1": "老师写的"}}},
    )

    # 识别答案推导：P1 第1题 2 空 + P2 第1题（全局第2题）1 空
    derived = _answer_table_derived_answers(safe)
    assert derived == {"1_1": "肢", "1_2": "体", "2_1": "抖擞"}

    plain = asyncio.run(api_get_answer_key(safe))
    assert plain["answers"] == {"1_1": "老师写的"}

    merged = asyncio.run(api_get_answer_key(safe, include_table=True))
    # 老师保存的优先，识别答案只补缺
    assert merged["answers"] == {"1_1": "老师写的", "1_2": "体", "2_1": "抖擞"}
    assert merged["raw"] == "1_1 老师写的"
