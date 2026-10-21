# -*- coding: utf-8 -*-
"""答案表手改覆盖层按框对位（2026-10-16 第1题错位事故的机制锁）。

事故链：手改 6 键按 sub_index 存 → 切题框变更 7 槽重排 → 重建把旧键按新
sub_index 硬盖 → 整题答案串位+漏「神圣」+「(轰然)」带印刷括号。锁三件事：
1. 覆盖层带 slot_bboxes，重建后按框回填（槽序重排/补槽不串位）；
2. 存了框但对不上的一律不落（宁缺勿串，不按号硬盖）；
3. 旧覆盖层（无 slot_bboxes）保持 sub_index 行为不回归；
另锁抽取侧印刷括号剥离（「(轰然)」→「轰然」）。
"""
from __future__ import annotations

from PIL import Image

from app.grading import reference_vlm_grading
from app.grading.reference_vlm_grading import (
    _strip_wrapping_parens,
    load_or_build_reference_answer_table,
    save_reference_answer_table_edits,
    VlmQuestion,
)

BOX_A = [10, 10, 50, 50]
BOX_B = [60, 10, 100, 50]
BOX_C = [10, 60, 50, 100]
BOX_NEW = [110, 10, 150, 50]


def _make_question(*, display_index=1, answer_bboxes=None, printed_no="1"):
    boxes = answer_bboxes or []
    return VlmQuestion(
        question_id=1,
        display_index=display_index,
        raw={},
        bbox=[0, 0, 160, 110],
        question_bbox=[0, 0, 160, 110],
        answer_bbox=boxes[0] if boxes else None,
        answer_bboxes=boxes,
        question_words="题干文本",
        answer_words=[],
        choices=[],
        question_type="填空题",
        printed_no=printed_no,
    )


def _entry(display_index, slots):
    return {
        "display_index": display_index,
        "printed_no": "1",
        "question_bbox": [0, 0, 160, 110],
        "slots": [
            {"sub_index": i + 1, "bbox": list(bbox), "answer_text": text}
            for i, (bbox, text) in enumerate(slots)
        ],
        "full_answer": "\n".join(t for _, t in slots if t),
    }


def _setup(monkeypatch, tmp_path, extract):
    monkeypatch.setattr(reference_vlm_grading, "correct_docs_dir", lambda: tmp_path)
    monkeypatch.setattr(reference_vlm_grading, "load_reference_layout", lambda folder: {"updated_at": "t1"})
    monkeypatch.setattr(reference_vlm_grading, "extract_reference_answer_table", extract)
    image_path = tmp_path / "std.png"
    Image.new("RGB", (50, 50), "white").save(image_path)
    return {
        "raw": {},
        "image_path": str(image_path),
        "source_path": str(image_path),
        "questions": [_make_question(answer_bboxes=[list(BOX_A), list(BOX_B), list(BOX_C)])],
    }


def _texts_by_bbox(entry):
    return {tuple(slot["bbox"]): slot["answer_text"] for slot in entry["slots"]}


def test_manual_edits_land_by_bbox_after_slot_reorder_and_new_slot(monkeypatch, tmp_path):
    """槽序重排+补新槽：手改按框回填到原槽，新槽留识别值（邓雨彤 Q1 事故形状）。"""
    calls = []

    def extract_v1(questions, image_path, *, skip_printed_numbers=None, stop_event=None):
        calls.append("v1")
        return [_entry(1, [(BOX_A, "旧1"), (BOX_B, "旧2"), (BOX_C, "旧3")])]

    doc = _setup(monkeypatch, tmp_path, extract_v1)
    first = load_or_build_reference_answer_table("edit-key-test", 1, doc)
    assert first["questions"][0]["full_answer"] == "旧1\n旧2\n旧3"

    save_reference_answer_table_edits(
        "edit-key-test",
        1,
        [
            {
                "display_index": 1,
                "printed_no": "1",
                "slots": [
                    {"sub_index": 1, "answer_text": "甲"},
                    {"sub_index": 2, "answer_text": "乙"},
                    {"sub_index": 3, "answer_text": "丙"},
                ],
            }
        ],
    )

    # 切题重排：原三框换了 sub_index，中间还多了一个新框
    def extract_v2(questions, image_path, *, skip_printed_numbers=None, stop_event=None):
        calls.append("v2")
        return [
            _entry(
                1,
                [(BOX_B, "新1"), (BOX_NEW, "新2"), (BOX_A, "新3"), (BOX_C, "新4")],
            )
        ]

    monkeypatch.setattr(reference_vlm_grading, "extract_reference_answer_table", extract_v2)
    monkeypatch.setattr(reference_vlm_grading, "load_reference_layout", lambda folder: {"updated_at": "t2"})
    second = load_or_build_reference_answer_table("edit-key-test", 1, doc)
    assert calls == ["v1", "v2"]

    by_bbox = _texts_by_bbox(second["questions"][0])
    # 手改按框落回原槽（不是按新 sub_index 硬盖）
    assert by_bbox[tuple(BOX_A)] == "甲"
    assert by_bbox[tuple(BOX_B)] == "乙"
    assert by_bbox[tuple(BOX_C)] == "丙"
    # 新框没手改：留识别值
    assert by_bbox[tuple(BOX_NEW)] == "新2"
    # full_answer 跟着槽序走
    assert second["questions"][0]["full_answer"] == "乙\n新2\n甲\n丙"


def test_manual_edits_stale_bbox_do_not_scatter(monkeypatch, tmp_path):
    """存的框全对不上新槽：一个都不落（宁缺勿串），不许按号硬盖。"""

    def extract_v1(questions, image_path, *, skip_printed_numbers=None, stop_event=None):
        return [_entry(1, [(BOX_A, "旧1"), (BOX_B, "旧2")])]

    doc = _setup(monkeypatch, tmp_path, extract_v1)
    doc["questions"] = [_make_question(answer_bboxes=[list(BOX_A), list(BOX_B)])]
    load_or_build_reference_answer_table("edit-stale-test", 1, doc)
    save_reference_answer_table_edits(
        "edit-stale-test",
        1,
        [
            {
                "display_index": 1,
                "printed_no": "1",
                "slots": [{"sub_index": 1, "answer_text": "甲"}, {"sub_index": 2, "answer_text": "乙"}],
            }
        ],
    )

    # 框全重画（坐标离得远）：手改框一个都对不上
    far1, far2 = [200, 200, 260, 250], [300, 200, 360, 250]

    def extract_v2(questions, image_path, *, skip_printed_numbers=None, stop_event=None):
        return [_entry(1, [(far1, "新1"), (far2, "新2")])]

    monkeypatch.setattr(reference_vlm_grading, "extract_reference_answer_table", extract_v2)
    monkeypatch.setattr(reference_vlm_grading, "load_reference_layout", lambda folder: {"updated_at": "t2"})
    doc["questions"] = [_make_question(answer_bboxes=[list(far1), list(far2)])]
    second = load_or_build_reference_answer_table("edit-stale-test", 1, doc)

    by_bbox = _texts_by_bbox(second["questions"][0])
    assert by_bbox[tuple(far1)] == "新1"
    assert by_bbox[tuple(far2)] == "新2"
    assert "甲" not in second["questions"][0]["full_answer"]
    assert "乙" not in second["questions"][0]["full_answer"]


def test_manual_edits_legacy_without_bbox_keep_sub_index(monkeypatch, tmp_path):
    """旧覆盖层（无 slot_bboxes）仍按 sub_index 覆盖，不回归。"""

    def extract_v1(questions, image_path, *, skip_printed_numbers=None, stop_event=None):
        return [_entry(1, [(BOX_A, "旧1"), (BOX_B, "旧2")])]

    doc = _setup(monkeypatch, tmp_path, extract_v1)
    doc["questions"] = [_make_question(answer_bboxes=[list(BOX_A), list(BOX_B)])]
    page = load_or_build_reference_answer_table("edit-legacy-test", 1, doc)
    # 直接写旧格式覆盖层（历史数据形状：slots 纯文本、无 slot_bboxes）
    path = reference_vlm_grading._answer_table_path("edit-legacy-test")
    data = reference_vlm_grading._read_json(path)
    data["pages"]["1"]["manual_edits"] = {
        "updated_at": "2026-10-16T05:14:00+00:00",
        "by_display_index": {"1": {"printed_no": "1", "slots": {"1": "甲", "2": "乙"}}},
    }
    reference_vlm_grading._write_json(path, data)
    # 带旧覆盖层重新落盘缓存
    monkeypatch.setattr(reference_vlm_grading, "load_reference_layout", lambda folder: {"updated_at": "t2"})
    second = load_or_build_reference_answer_table("edit-legacy-test", 1, doc)
    by_bbox = _texts_by_bbox(second["questions"][0])
    assert by_bbox[tuple(BOX_A)] == "甲"
    assert by_bbox[tuple(BOX_B)] == "乙"


def test_save_records_slot_bboxes(monkeypatch, tmp_path):
    """保存手改时把槽框一并存档（重建按框回填的前提）。"""

    def extract_v1(questions, image_path, *, skip_printed_numbers=None, stop_event=None):
        return [_entry(1, [(BOX_A, "旧1"), (BOX_B, "旧2")])]

    doc = _setup(monkeypatch, tmp_path, extract_v1)
    doc["questions"] = [_make_question(answer_bboxes=[list(BOX_A), list(BOX_B)])]
    load_or_build_reference_answer_table("edit-bbox-test", 1, doc)
    save_reference_answer_table_edits(
        "edit-bbox-test",
        1,
        [
            {
                "display_index": 1,
                "printed_no": "1",
                "slots": [{"sub_index": 1, "answer_text": "甲"}, {"sub_index": 2, "answer_text": "乙"}],
            }
        ],
    )
    saved = reference_vlm_grading.read_reference_answer_table_page("edit-bbox-test", 1)
    overlay = saved["manual_edits"]["by_display_index"]["1"]
    assert overlay["slots"] == {"1": "甲", "2": "乙"}
    assert overlay["slot_bboxes"] == {"1": list(BOX_A), "2": list(BOX_B)}


def test_strip_wrapping_parens():
    """抽取侧印刷括号剥离：「(轰然)」→「轰然」；带内层括号/正文不动。"""
    assert _strip_wrapping_parens("(轰然)") == "轰然"
    assert _strip_wrapping_parens("（轰然）") == "轰然"
    assert _strip_wrapping_parens("轰然") == "轰然"
    assert _strip_wrapping_parens("(或：四世同堂)") == "或：四世同堂"
    assert _strip_wrapping_parens("骆驼祥子 (或：四世同堂)") == "骆驼祥子 (或：四世同堂)"
    assert _strip_wrapping_parens("(a(b))") == "(a(b))"  # 带内层括号不剥
    assert _strip_wrapping_parens("") == ""
