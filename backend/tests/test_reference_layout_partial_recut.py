# -*- coding: utf-8 -*-
"""11.11-10 替换一张标准答案只失效本页，另一张切好的题保留。

台账原话：「老师会出现错传，替换其中一张，然后另一张切好的题会被取消，
两张全部要重新切分」。病根：load_reference_layout_for_editing 任何页签名不匹配
就整体报错（409），把老师逼进「重新切题」整卷重切，另一面手切的题跟着丢。
修法：签名不匹配的页交给 fallback_builder 现场重切，其余页沿用已保存切题。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.grading import reference_vlm_grading, router as grading_router
from app.grading.reference_vlm_grading import (
    confirm_reference_layout,
    delete_reference_layout,
    load_reference_layout_for_editing,
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


def _confirm_both(folder: str, p1: Path, p2: Path) -> None:
    prepare_id = save_reference_layout_prepare(
        folder,
        [_record(1, p1, "saved-p1"), _record(2, p2, "saved-p2")],
    )
    confirm_reference_layout(
        folder,
        prepare_id,
        [_edited(1, "saved-p1"), _edited(2, "saved-p2")],
    )


def test_replace_one_page_recuts_only_that_page(docs):
    p1 = _mk_source(docs / "标准答案.jpg", "p1")
    p2 = _mk_source(docs / "标准答案_2.jpg", "p2")
    _confirm_both(str(docs), p1, p2)

    # 老师替换 P2：文件内容变了 → 签名不匹配
    _mk_source(p2, "p2-replaced")
    calls: list[int] = []

    def builder(page_no: int, source_path: Path, grading_path: Path):
        calls.append(page_no)
        return _record(page_no, source_path, "fresh-p2")

    result = load_reference_layout_for_editing(
        str(docs),
        {1: (p1, p1), 2: (p2, p2)},
        fallback_builder=builder,
    )
    assert calls == [2]  # 只重切 P2
    assert result["recut_pages"] == [2]
    pages = result["pages"]
    assert [p["page_no"] for p in pages] == [1, 2]
    # P1 沿用已保存切题，P2 是现场重切的新题
    assert pages[0]["questions"][0]["question_id"] == "saved-p1"
    assert pages[1]["questions"][0]["question_id"] == "fresh-p2"
    assert result["prepare_id"]


def test_deleted_page_recuts_only_that_page(docs):
    """错传后先删掉那张：delete_reference_layout 只删本页，其余页照常复用。"""
    p1 = _mk_source(docs / "标准答案.jpg", "p1")
    p2 = _mk_source(docs / "标准答案_2.jpg", "p2")
    _confirm_both(str(docs), p1, p2)

    delete_reference_layout(str(docs), 2)  # 上传替换时后端就是这个动作
    calls: list[int] = []

    def builder(page_no: int, source_path: Path, grading_path: Path):
        calls.append(page_no)
        return _record(page_no, source_path, "fresh-p2")

    result = load_reference_layout_for_editing(
        str(docs),
        {1: (p1, p1), 2: (p2, p2)},
        fallback_builder=builder,
    )
    assert calls == [2]
    assert result["recut_pages"] == [2]
    assert result["pages"][0]["questions"][0]["question_id"] == "saved-p1"


def test_all_fresh_no_fallback_call(docs):
    p1 = _mk_source(docs / "标准答案.jpg", "p1")
    p2 = _mk_source(docs / "标准答案_2.jpg", "p2")
    _confirm_both(str(docs), p1, p2)

    def boom(page_no, source_path, grading_path):
        raise AssertionError("不该重切")

    result = load_reference_layout_for_editing(
        str(docs),
        {1: (p1, p1), 2: (p2, p2)},
        fallback_builder=boom,
    )
    assert result["recut_pages"] == []
    assert [p["questions"][0]["question_id"] for p in result["pages"]] == [
        "saved-p1",
        "saved-p2",
    ]


def test_old_contract_without_builder_still_raises(docs):
    p1 = _mk_source(docs / "标准答案.jpg", "p1")
    p2 = _mk_source(docs / "标准答案_2.jpg", "p2")
    _confirm_both(str(docs), p1, p2)
    _mk_source(p2, "p2-replaced")
    with pytest.raises(RuntimeError, match="已变更"):
        load_reference_layout_for_editing(str(docs), {1: (p1, p1), 2: (p2, p2)})


def test_confirm_after_partial_recut_roundtrip(docs):
    """重切后的混合审查会话照常整卷确认；确认完两页都新鲜。"""
    p1 = _mk_source(docs / "标准答案.jpg", "p1")
    p2 = _mk_source(docs / "标准答案_2.jpg", "p2")
    _confirm_both(str(docs), p1, p2)
    _mk_source(p2, "p2-replaced")

    def builder(page_no: int, source_path: Path, grading_path: Path):
        return _record(page_no, source_path, "fresh-p2")

    result = load_reference_layout_for_editing(
        str(docs),
        {1: (p1, p1), 2: (p2, p2)},
        fallback_builder=builder,
    )
    confirm_reference_layout(
        str(docs),
        result["prepare_id"],
        [
            _edited(1, "saved-p1"),
            _edited(2, "fresh-p2"),
        ],
    )
    again = load_reference_layout_for_editing(
        str(docs),
        {1: (p1, p1), 2: (p2, p2)},
        fallback_builder=lambda *_a: (_ for _ in ()).throw(AssertionError("不该重切")),
    )
    assert again["recut_pages"] == []
    assert [p["questions"][0]["question_id"] for p in again["pages"]] == [
        "saved-p1",
        "fresh-p2",
    ]
