# -*- coding: utf-8 -*-
"""11.11-11 切分界面每面切完单独保存：单页并进已保存布局，其余页不动。

台账原话：「切题审查页面：P1、P2页面切完题后，只需要点一次保存，但是识别答案功能：
P1、P2页面需要每一张单独保存，容易弄错.切分界面能不能每一面试卷切分之后单独保存」。
修法：save_reference_layout_page 单页合并落盘（切完一面就存），整卷 confirm 仍然可用。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.grading import reference_vlm_grading, router as grading_router
from app.grading.reference_vlm_grading import (
    confirm_reference_layout,
    load_reference_layout,
    load_reference_layout_for_editing,
    reference_layout_status,
    save_reference_layout_page,
    save_reference_layout_prepare,
)


@pytest.fixture()
def docs(tmp_path, monkeypatch):
    root = tmp_path / "docs"
    monkeypatch.setattr(grading_router, "correct_docs_dir", lambda: root)
    monkeypatch.setattr(reference_vlm_grading, "correct_docs_dir", lambda: root)
    folder = root / "班1"
    folder.mkdir(parents=True)
    return folder


def _mk_source(path: Path, tag: str) -> Path:
    path.write_bytes(f"standard-{tag}".encode("utf-8"))
    return path


def _record(page_no: int, source_path: Path, question_id: str) -> dict:
    return {
        "page_no": page_no,
        "filename": source_path.name,
        "image_url": f"/img/{source_path.name}",
        "image_size": [100, 200],
        "questions": [
            {
                "question_id": question_id,
                "display_no": 1,
                "regions": [],
                "answer_slots": [],
            }
        ],
        "source_path": str(source_path),
        "image_path": str(source_path),
        "raw": {"stub": True},
    }


def _edited(page_no: int, question_id: str) -> dict:
    return {
        "page_no": page_no,
        "questions": [
            {
                "question_id": question_id,
                "display_no": 1,
                "regions": [],
                "answer_slots": [],
            }
        ],
    }


def _prepare_both(docs: Path, p1: Path, p2: Path) -> str:
    return save_reference_layout_prepare(
        str(docs),
        [_record(1, p1, "saved-p1"), _record(2, p2, "saved-p2")],
    )


def test_save_single_page_merges_others_untouched(docs):
    p1 = _mk_source(docs / "标准答案.jpg", "p1")
    p2 = _mk_source(docs / "标准答案_2.jpg", "p2")
    prepare_id = _prepare_both(docs, p1, p2)

    result = save_reference_layout_page(str(docs), prepare_id, _edited(1, "cut-p1"))
    pages = result["pages"]
    assert set(pages) == {"1"}  # 只落 P1，P2 不跟着动
    assert pages["1"]["layout"]["questions"][0]["question_id"] == "cut-p1"
    assert pages["1"]["source_signature"]["size"] > 0

    # 再单独存 P2：P1 保留
    result = save_reference_layout_page(str(docs), prepare_id, _edited(2, "cut-p2"))
    pages = result["pages"]
    assert set(pages) == {"1", "2"}
    assert pages["1"]["layout"]["questions"][0]["question_id"] == "cut-p1"
    assert pages["2"]["layout"]["questions"][0]["question_id"] == "cut-p2"


def test_partial_save_keeps_pending_for_final_confirm(docs):
    p1 = _mk_source(docs / "标准答案.jpg", "p1")
    p2 = _mk_source(docs / "标准答案_2.jpg", "p2")
    prepare_id = _prepare_both(docs, p1, p2)

    save_reference_layout_page(str(docs), prepare_id, _edited(1, "cut-p1"))
    # 会话还在：最后点「确认保存」照常整卷覆盖（含完整页校验）
    result = confirm_reference_layout(
        str(docs),
        prepare_id,
        [_edited(1, "cut-p1"), _edited(2, "cut-p2")],
    )
    assert set(result["pages"]) == {"1", "2"}
    # 确认完 = 两页都有签名匹配的已存条目 → 状态全确认
    status = reference_layout_status(
        str(docs),
        {1: p1, 2: p2},
    )
    assert status["confirmed"] is True
    assert status["stale_pages"] == []


def test_partial_save_updates_status_per_page(docs):
    """只存 P1 时：P1 reviewed、P2 stale，confirmed 仍是 False（别提前放行批改）。"""
    p1 = _mk_source(docs / "标准答案.jpg", "p1")
    p2 = _mk_source(docs / "标准答案_2.jpg", "p2")
    prepare_id = _prepare_both(docs, p1, p2)

    save_reference_layout_page(str(docs), prepare_id, _edited(1, "cut-p1"))
    status = reference_layout_status(str(docs), {1: p1, 2: p2})
    assert status["confirmed"] is False
    assert status["reviewed_pages"] == [1]
    assert status["stale_pages"] == [2]


def test_partial_save_bumps_layout_updated_at(docs):
    """答案表 cache_token 带 layout_updated_at：每面落盘自动让答案表按新框重建。"""
    p1 = _mk_source(docs / "标准答案.jpg", "p1")
    p2 = _mk_source(docs / "标准答案_2.jpg", "p2")
    prepare_id = _prepare_both(docs, p1, p2)

    save_reference_layout_page(str(docs), prepare_id, _edited(1, "cut-p1"))
    first = load_reference_layout(str(docs)).get("updated_at")
    save_reference_layout_page(str(docs), prepare_id, _edited(2, "cut-p2"))
    second = load_reference_layout(str(docs)).get("updated_at")
    assert first and second and second != first


def test_invalid_prepare_id_rejected(docs):
    p1 = _mk_source(docs / "标准答案.jpg", "p1")
    _prepare_both(docs, p1, p1)
    with pytest.raises(RuntimeError, match="已失效"):
        save_reference_layout_page(str(docs), "bad-id", _edited(1, "cut-p1"))


def test_unknown_page_rejected(docs):
    p1 = _mk_source(docs / "标准答案.jpg", "p1")
    p2 = _mk_source(docs / "标准答案_2.jpg", "p2")
    prepare_id = _prepare_both(docs, p1, p2)
    with pytest.raises(RuntimeError, match="缺少 P3"):
        save_reference_layout_page(str(docs), prepare_id, _edited(3, "cut-p3"))


def test_empty_questions_rejected(docs):
    p1 = _mk_source(docs / "标准答案.jpg", "p1")
    p2 = _mk_source(docs / "标准答案_2.jpg", "p2")
    prepare_id = _prepare_both(docs, p1, p2)
    bad = {"page_no": 1, "questions": []}
    with pytest.raises(RuntimeError, match="至少需要一个题目框"):
        save_reference_layout_page(str(docs), prepare_id, bad)


def test_per_face_save_then_reedit_load_roundtrip(docs):
    """单面落盘后重新打开编辑：已存页原样复用，签名照旧匹配。"""
    p1 = _mk_source(docs / "标准答案.jpg", "p1")
    p2 = _mk_source(docs / "标准答案_2.jpg", "p2")
    prepare_id = _prepare_both(docs, p1, p2)
    save_reference_layout_page(str(docs), prepare_id, _edited(1, "cut-p1"))
    save_reference_layout_page(str(docs), prepare_id, _edited(2, "cut-p2"))

    def boom(*_a):
        raise AssertionError("不该重切")

    result = load_reference_layout_for_editing(
        str(docs),
        {1: (p1, p1), 2: (p2, p2)},
        fallback_builder=boom,
    )
    assert result["recut_pages"] == []
    assert [p["questions"][0]["question_id"] for p in result["pages"]] == [
        "cut-p1",
        "cut-p2",
    ]
