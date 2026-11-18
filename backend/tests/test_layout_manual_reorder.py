# -*- coding: utf-8 -*-
"""11.11-1 题目框手动排序（上移/下移+重编号）后端回归。

台账原话（龙欣 26.11.11）：「题目框不能手动编辑排序，不能识别试卷题号顺序排序，
生成课堂讲评的时候，课堂讲评是按照切题的题目框顺序生成的报告，与试卷实际的
题号不符，初中题目存在一个题干里面包含了2-3个小题」。
本批只做手动排序（上移/下移+整卷连续重编号），自动题号排序不在本批。

锁定六点：
  1) 重编号后按 question_id（q-{原号}）认领原题：换过号的两题各拿各的框，
     不按 display_no 硬认（否则 2↔1 对调后互相认错框）；
  2) raw 身份戳仍是原号（layout_display_index=原号），重编号不动它；
  3) 合成分身（synthetic_from_layout）不回流提取：分身戳号与重编号后原题
     身份撞号时不得偷走原题的认领；新增题每轮由 layout 重新合成；
  4) 无 question_id 的旧数据仍按 display_no 认领（老口径不断）；
  5) 手改答案覆盖层的 by_display_index 键在保存时跟着换号（手改不丢），
     撞号宁缺勿串；save_reference_layout_page 与 confirm_reference_layout
     两条保存路都换；
  6) 矫正后 questions 按老师定的题号排（报告「第N题」跟排法走）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from app.grading import reference_vlm_grading, router as grading_router
from app.grading.reference_vlm_grading import (
    _display_no_remap,
    apply_reference_layout_to_document,
    confirm_reference_layout,
    extract_vlm_questions,
    load_reference_layout,
    save_reference_layout_page,
    save_reference_layout_prepare,
)

# 图内坐标（200×400 的小图，框都离边远点）
Q1_BOX = [10, 10, 190, 60]
A1_BOX = [10, 70, 190, 110]
Q2_BOX = [10, 150, 190, 200]
A2_BOX = [10, 210, 190, 250]
QX_BOX = [10, 300, 190, 340]
AX_BOX = [10, 350, 190, 390]


@pytest.fixture()
def img(tmp_path):
    path = tmp_path / "standard.png"
    Image.new("RGB", (200, 400), "white").save(path)
    return path


@pytest.fixture()
def docs(tmp_path, monkeypatch):
    root = tmp_path / "docs"
    monkeypatch.setattr(grading_router, "correct_docs_dir", lambda: root)
    monkeypatch.setattr(reference_vlm_grading, "correct_docs_dir", lambda: root)
    folder = root / "班1"
    folder.mkdir(parents=True)
    return folder


def _raw_question(qus_id, qbox, abox, **extra):
    item = {
        "qus_id": qus_id,
        "location": {"qus_location": list(qbox), "ans_location": [list(abox)]},
        "qus_elements": {
            "question_words": f"题{qus_id}",
            "answer_words": [f"答{qus_id}"],
        },
    }
    item.update(extra)
    return item


def _edit(qid, display_no, qbox, abox):
    return {
        "question_id": qid,
        "display_no": display_no,
        "regions": [{"bbox": list(qbox)}],
        "answer_slots": [{"bbox": list(abox)}],
    }


def _apply(raw, edits, img_path):
    document = {"raw": raw, "image_path": str(img_path), "image_size": [200, 400]}
    layout_page = {"page_no": 1, "image_size": [200, 400], "questions": edits}
    return apply_reference_layout_to_document(document, layout_page)


# ---------------------------------------------------------------- 1/2/6

def test_renumbered_swap_binds_by_identity_not_number(img):
    """q-1↔q-2 对调题号后各拿各的框；身份戳仍是原号；按老师题号排。"""
    raw = {
        "qus_results": [
            _raw_question(1, Q1_BOX, A1_BOX),
            _raw_question(2, Q2_BOX, A2_BOX),
        ]
    }
    edits = [
        _edit("q-1", 2, Q1_BOX, A1_BOX),  # 原 1 号题被老师排到第 2
        _edit("q-2", 1, Q2_BOX, A2_BOX),  # 原 2 号题被老师排到第 1
    ]
    corrected = _apply(raw, edits, img)
    questions = corrected["questions"]

    assert [q.display_index for q in questions] == [1, 2]
    first, second = questions
    # 老师排第 1 的是原 2 号题：拿的必须是原 2 号题的框
    assert first.raw.get("qus_id") == 2
    assert first.question_bbox == Q2_BOX
    assert first.answer_bboxes == [A2_BOX]
    assert second.raw.get("qus_id") == 1
    assert second.question_bbox == Q1_BOX
    assert second.answer_bboxes == [A1_BOX]
    # 身份戳 = 原号，不跟老师题号走（重建提取按戳认原号）
    container = corrected["raw"]["qus_results"]
    assert container[0]["layout_display_index"] == 1
    assert container[1]["layout_display_index"] == 2


# ---------------------------------------------------------------- 3

def test_synthetic_twin_does_not_steal_binding(img):
    """上轮合成的分身带着撞号戳回流时：提取直接跳过，不偷原题的认领；
    新增题（uuid 编辑）每轮重新合成进 questions。"""
    twin = _raw_question(
        2, Q2_BOX, A2_BOX, synthetic_from_layout=True, layout_display_index=2
    )
    raw = {
        "qus_results": [
            _raw_question(1, Q1_BOX, A1_BOX),
            twin,
            _raw_question(2, Q2_BOX, A2_BOX),
        ]
    }
    # 提取层面：分身直接跳过
    questions = extract_vlm_questions(raw, image_path=str(img))
    assert len(questions) == 2
    assert all(not q.raw.get("synthetic_from_layout") for q in questions)

    edits = [
        _edit("q-1", 1, Q1_BOX, A1_BOX),
        _edit("q-2", 3, Q2_BOX, A2_BOX),  # 原 2 号被老师排到第 3
        _edit("question-uuid-aaa", 2, QX_BOX, AX_BOX),  # 新增题占第 2
    ]
    corrected = _apply(raw, edits, img)
    questions = corrected["questions"]

    assert [q.display_index for q in questions] == [1, 2, 3]
    first, added, moved = questions
    assert first.raw.get("qus_id") == 1
    # 第 2 = 新增题的合成分身，框是老师画的新增题框
    assert added.raw.get("synthetic_from_layout") is True
    assert added.question_bbox == QX_BOX
    assert added.answer_bboxes == [AX_BOX]
    # 第 3 = 原 2 号题，框没被分身偷走
    assert moved.raw.get("qus_id") == 2
    assert moved.question_bbox == Q2_BOX
    assert moved.answer_bboxes == [A2_BOX]


# ---------------------------------------------------------------- 4

def test_legacy_qidless_edit_binds_by_display_no(img):
    """无 question_id 的旧数据：还按 display_no 认领（老口径不断）。"""
    raw = {"qus_results": [_raw_question(1, Q1_BOX, A1_BOX)]}
    edits = [_edit("", 1, Q1_BOX, A1_BOX)]
    corrected = _apply(raw, edits, img)
    questions = corrected["questions"]
    assert len(questions) == 1
    assert questions[0].raw.get("qus_id") == 1
    assert not questions[0].raw.get("layout_deleted")


# ---------------------------------------------------------------- 5

def _seed_answer_table(folder: Path, page_no: str, by_display_index: dict):
    path = folder / reference_vlm_grading._ANSWER_TABLE_FILENAME
    payload = {
        "version": 1,
        "updated_at": "2026-01-01T00:00:00",
        "pages": {
            page_no: {
                "page_no": int(page_no),
                "cache_token": {"source_signature": {"size": 1}},
                "questions": [],
                "manual_edits": {"by_display_index": by_display_index},
            }
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _read_by_display_index(path: Path, page_no: str):
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["pages"][page_no]["manual_edits"]["by_display_index"]


def _record(page_no, source_path, edits):
    return {
        "page_no": page_no,
        "filename": source_path.name,
        "image_url": f"/img/{source_path.name}",
        "image_size": [200, 400],
        "questions": edits,
        "source_path": str(source_path),
        "image_path": str(source_path),
        "raw": {"stub": True},
    }


def test_manual_overlay_keys_remap_on_save_page_renumber(docs):
    """每面单独保存路：重编号后手改覆盖层的题号键跟着换，内容不丢不串。"""
    p1 = docs / "standard.jpg"
    p1.write_bytes(b"standard-bytes")
    source_edits = [
        _edit("q-1", 1, Q1_BOX, A1_BOX),
        _edit("q-2", 2, Q2_BOX, A2_BOX),
    ]
    prepare_id = save_reference_layout_prepare(
        str(docs), [_record(1, p1, source_edits)]
    )
    table_path = _seed_answer_table(
        docs,
        "1",
        {"1": {"answer": "orig-1"}, "2": {"answer": "orig-2"}},
    )

    edited_page = {
        "page_no": 1,
        "questions": [
            _edit("q-1", 2, Q1_BOX, A1_BOX),  # 对调
            _edit("q-2", 1, Q2_BOX, A2_BOX),
        ],
    }
    save_reference_layout_page(str(docs), prepare_id, edited_page)

    by_index = _read_by_display_index(table_path, "1")
    # 原 1 号的老师手改跟着题走到新号 2，原 2 号的走到新号 1
    assert by_index == {
        "2": {"answer": "orig-1"},
        "1": {"answer": "orig-2"},
    }
    saved = load_reference_layout(str(docs))
    saved_questions = saved["pages"]["1"]["layout"]["questions"]
    assert [q["display_no"] for q in saved_questions] == [2, 1]


def test_manual_overlay_keys_remap_on_confirm_renumber(docs):
    """整卷确认路：同样换键；被删题的死键撞不过挪过来的活键。"""
    p1 = docs / "standard.jpg"
    p1.write_bytes(b"standard-bytes")
    source_edits = [
        _edit("q-1", 1, Q1_BOX, A1_BOX),
        _edit("q-2", 2, Q2_BOX, A2_BOX),
    ]
    prepare_id = save_reference_layout_prepare(
        str(docs), [_record(1, p1, source_edits)]
    )
    table_path = _seed_answer_table(
        docs,
        "1",
        {
            "1": {"answer": "orig-1"},
            "2": {"answer": "dead-q2"},  # q-2 被删，这是死键
        },
    )

    # 老师删掉 q-2，把 q-1 排到第 2（腾出的号）：活键 1→2 优先于死键 2
    edited_page = {
        "page_no": 1,
        "questions": [_edit("q-1", 2, Q1_BOX, A1_BOX)],
    }
    confirm_reference_layout(str(docs), prepare_id, [edited_page])

    by_index = _read_by_display_index(table_path, "1")
    assert by_index == {"2": {"answer": "orig-1"}}


def test_display_no_remap_minted_qid_fallback():
    """旧数据铸号回认：源题无 id、编辑侧 q-{原号}，也能得出换号对照。"""
    source = {
        "questions": [
            {"question_id": "", "display_no": 1},
            {"question_id": "q-2", "display_no": 2},
        ]
    }
    edited = {
        "questions": [
            {"question_id": "q-1", "display_no": 3},  # 铸号 + 重编号
            {"question_id": "q-2", "display_no": 2},  # 没换号：不进对照
        ]
    }
    assert _display_no_remap(source, edited) == {1: 3}

    # 没动号的普通编辑：对照为空（保存时不碰答案表）
    same = {"questions": [{"question_id": "q-1", "display_no": 1}]}
    assert _display_no_remap({"questions": [{"question_id": "q-1", "display_no": 1}]}, same) == {}
