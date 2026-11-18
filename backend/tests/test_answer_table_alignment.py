# -*- coding: utf-8 -*-
"""答案表「答案↔题号」对齐与判对确定性校验（2026-11-17 P0 回归）。

用户反馈：初一英语训练七第 16–25 题答案序列与题号整体错开一行，
学生写 be / have / 2s 也被判 ✓。
"""
from __future__ import annotations

import pytest

import app.grading.reference_vlm_grading as rvg


def _entry(printed, text):
    return {
        "printed_no": str(printed),
        "display_index": printed,
        "slots": [{"sub_index": 1, "bbox": [0, 0, 1, 1], "answer_text": text}],
        "full_answer": text,
    }


# ── 错行检测与矫正 ─────────────────────────────────────────────────────


def test_no_offset_when_numbers_aligned():
    entries = [_entry(16, "16. having"), _entry(17, "17. is"), _entry(18, "18. are")]
    assert rvg._answer_entry_number_offset(entries) is None
    rvg._align_answer_entry_numbers(entries)
    # 只剥内联题号，不改号
    # 题号与内联题号一致时保留原样（「16. having」里的 16 是合法题号）
    assert [(e["printed_no"], e["slots"][0]["answer_text"]) for e in entries] == [
        ("16", "16. having"),
        ("17", "17. is"),
        ("18", "18. are"),
    ]


def test_offset_detected_and_renumbered():
    """整表错行一行：第 15 条里装的是「16. having」。"""
    entries = [
        _entry(15, "16. having"),
        _entry(16, "17. is"),
        _entry(17, "18. are"),
        _entry(18, "19. our"),
    ]
    assert rvg._answer_entry_number_offset(entries) == 1
    rvg._align_answer_entry_numbers(entries)
    mapping = {e["printed_no"]: e["slots"][0]["answer_text"] for e in entries}
    assert mapping["16"].endswith("having")
    assert mapping["17"].endswith("is")
    assert mapping["18"].endswith("are")
    assert mapping["19"].endswith("our")


def test_entries_without_inline_numbers_untouched():
    entries = [_entry(16, "having"), _entry(17, "is")]
    assert rvg._answer_entry_number_offset(entries) is None
    rvg._align_answer_entry_numbers(entries)
    assert [(e["printed_no"], e["slots"][0]["answer_text"]) for e in entries] == [
        ("16", "having"),
        ("17", "is"),
    ]


# ── 判对确定性校验（P0） ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "student,standard,should_block",
    [
        # 用户实测的错误情形：必须拦截
        ("be", "study", True),
        ("have", "study", True),
        ("2s", "study", True),
        ("is", "having", True),
        ("are", "having", True),
        ("B", "A", True),
        ("0.6", "0.5", True),
        # 正确答案不得误伤
        ("study", "study", True and False),
        ("Study", "study", False),
        ("STUDY.", "study", False),
        ("havin", "having", False),
        ("0.5", "0.5", False),
        ("A", "A", False),
        ("做功", "做功", False),
    ],
)
def test_verify_answer_against_standard(student, standard, should_block):
    conflict = rvg._verify_answer_against_standard(student, standard, rvg.CORRECT)
    assert bool(conflict) is should_block, f"{student!r} vs {standard!r}"


def test_verify_only_applies_to_correct_verdict():
    # 判错/未作答不受这层校验影响
    assert rvg._verify_answer_against_standard("be", "study", rvg.WRONG) is None
    assert rvg._verify_answer_against_standard("be", "study", rvg.UNANSWERED) is None


def test_verify_skips_unreliable_standard():
    assert rvg._verify_answer_against_standard("study", rvg._TEXT_MISSING, rvg.CORRECT) is None
    assert rvg._verify_answer_against_standard("study", "", rvg.CORRECT) is None


def test_verify_skips_long_essay_answers():
    """简答题（标准答案 > 20 字符）不做逐字校验，交回语义判断。"""
    std = "因为学校很大而且有很多学生"
    assert rvg._verify_answer_against_standard("因为学校很大", std, rvg.CORRECT) is None


def test_verify_rejects_negation_substitution():
    """「不做功」不能因为包含「做功」被判对（反义风险）。"""
    assert rvg._verify_answer_against_standard("不做功", "做功", rvg.CORRECT) is not None


def test_verify_accepts_explicit_multiple_variants():
    # 标准答案用 | 显式声明多解：命中任一即放行
    assert rvg._verify_answer_against_standard("变红", "变红|褪色", rvg.CORRECT) is None
    assert rvg._verify_answer_against_standard("变蓝", "变红|褪色", rvg.CORRECT) is not None
