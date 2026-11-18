# -*- coding: utf-8 -*-
"""划掉重写 + 云端打印页序（2026-11-18 客户反馈）。

1. 云端打印留痕 P1 出现在第二页、P2 在第一页 → PDF 路径绝不能做「反顺序对调」。
2. 学生划掉旧答案再写新答案时，留痕上 ? 与 ✓/× 混乱 → 多候选答案一律转人工确认。
"""
from __future__ import annotations

import pytest

import app.grading.answer_key_grading as ak
import app.grading.print_marks as pm
import app.grading.reference_vlm_grading as rvg

CLS = "b9000000-0000-4000-8000-000000000018"


def _marks(name: str, page: int) -> str:
    return f"marks_only_ref_cls_{CLS}__18班英语训练七_{name}_{page}_wa.jpg"


# ── 1. 云端打印页序：PDF 必须严格 P1→P2 ───────────────────────────────


def test_pdf_path_keeps_p1_before_p2(monkeypatch):
    paths = [_marks("刘依璇", 1), _marks("刘依璇", 2)]
    for swap in ("1", "0"):
        monkeypatch.setenv("GRADING_DUPLEX_SWAP_SIDES", swap)
        out = pm.duplex_submission_paths(paths)
        assert [pm._page_no_from_marks_filename(p) for p in out] == [1, 2], (
            "PDF/云端打印按页序双面出纸，第1页必须是正面（P1）"
        )


def test_pdf_path_keeps_students_contiguous(monkeypatch):
    monkeypatch.setenv("GRADING_DUPLEX_SWAP_SIDES", "1")
    paths = [
        _marks("刘依璇", 1), _marks("刘依璇", 2),
        _marks("刘立航", 1), _marks("刘立航", 2),
    ]
    out = pm.duplex_submission_paths(paths)
    assert [pm._page_no_from_marks_filename(p) for p in out] == [1, 2, 1, 2]
    bases = [pm._student_base_from_marks_filename(p) for p in out]
    assert bases[0] == bases[1] and bases[2] == bases[3] and bases[0] != bases[2]


def test_pdf_path_interleaved_input_regroups(monkeypatch):
    monkeypatch.setenv("GRADING_DUPLEX_SWAP_SIDES", "1")
    paths = [_marks("A", 1), _marks("B", 1), _marks("A", 2), _marks("B", 2)]
    out = pm.duplex_submission_paths(paths)
    assert [pm._page_no_from_marks_filename(p) for p in out] == [1, 2, 1, 2]


def test_gdi_path_still_swaps_within_student(monkeypatch):
    """GDI 直打路径保留历史补偿：学生块内对调（这是打印机的需要，不是 bug）。"""
    monkeypatch.setenv("GRADING_DUPLEX_SWAP_SIDES", "1")
    paths = [_marks("A", 1), _marks("A", 2)]
    job = pm._duplex_job_paths(paths)
    assert [pm._page_no_from_marks_filename(p) for p in job] == [2, 1]


def test_gdi_path_swap_disabled(monkeypatch):
    monkeypatch.setenv("GRADING_DUPLEX_SWAP_SIDES", "0")
    paths = [_marks("A", 1), _marks("A", 2)]
    job = pm._duplex_job_paths(paths)
    assert [pm._page_no_from_marks_filename(p) for p in job] == [1, 2]


# ── 2. 划掉重写：多候选答案不许自动判 ──────────────────────────────────


@pytest.mark.parametrize(
    "text,ambiguous",
    [
        ("A", False),
        ("study", False),
        ("0.5", False),
        ("做功", False),
        ("having", False),
        # 划线后重写：旧答案和新答案被一起读出来
        ("A B", True),
        ("A/B", True),
        ("having be", True),
        ("做功、不做功", True),
        ("is are", True),
        ("study 或 be", True),
        # 正常的多词答案不能误伤
        ("because it is big", False),
        ("on the floor of the classroom", False),
    ],
)
def test_reference_chain_detects_multiple_candidates(text, ambiguous):
    assert bool(rvg._ambiguous_multi_candidate(text)) is ambiguous


@pytest.mark.parametrize(
    "text,ambiguous",
    [
        ("A", False),
        ("study", False),
        ("0.5", False),
        ("做功", False),
        ("A B", True),
        ("A/B", True),
        ("having be", True),
        ("做功、不做功", True),
        ("because it is big", False),
        ("on the floor of the classroom", False),
    ],
)
def test_answer_key_chain_detects_multiple_candidates(text, ambiguous):
    assert ak._looks_like_multiple_candidates(text) is ambiguous


def test_ambiguous_decision_becomes_pending():
    """转写多候选 → 判定必须转待确认，且原因写明是划掉重写。"""
    decision = {
        "question_id": 5,
        "correctResult": rvg.CORRECT,
        "result": "对",
        "transcription": "having be",
        "reason": "与标准一致",
        "analysis": "与标准一致",
        "confidence": 0.9,
        "read_confidence": 0.9,
        "standard_answer_text": "having",
    }
    out = rvg._normalize_decision(decision, 5, standard_answer_text="having")
    assert out["correctResult"] == rvg.PENDING
    assert out["result"] == "待确认"
    assert "划掉" in out["reason"] or "多个" in out["reason"]


def test_single_answer_still_grades_correct():
    decision = {
        "question_id": 5,
        "correctResult": rvg.CORRECT,
        "result": "对",
        "transcription": "having",
        "reason": "与标准一致",
        "analysis": "与标准一致",
        "confidence": 0.9,
        "read_confidence": 0.9,
    }
    out = rvg._normalize_decision(decision, 5, standard_answer_text="having")
    assert out["correctResult"] == rvg.CORRECT


def test_prompts_carry_strikethrough_rule():
    """按答案比对链的三条提示词都必须写明「只看未被划掉的最终答案」。"""
    assert "划掉" in ak._STUDENT_ANSWER_PROMPT
    assert "划掉" in ak._FILLIN_GRADE_PROMPT
    assert "划掉" in ak._SUBJECTIVE_GRADE_PROMPT


def test_reference_prompt_has_strikethrough_section():
    from app.grading.reference_vlm_grading import VlmGradingTask, VlmQuestionBatchTask, VlmQuestion

    std = VlmQuestion(
        question_id=1, display_index=1, raw={},
        bbox=[0, 0, 10, 10], question_bbox=[0, 0, 100, 100],
        answer_bbox=[10, 10, 50, 50], answer_bboxes=[[10, 10, 50, 50]],
        question_words="", answer_words=[], choices=[], question_type="",
        question_regions=[[0, 0, 100, 100]], printed_no="1",
    )
    task = VlmGradingTask(
        task_id=1, student_question=std, standard_question=std,
        student_answer_bbox=[10, 10, 50, 50], standard_answer_bbox=[10, 10, 50, 50],
        student_context_bbox=[0, 0, 100, 100], standard_context_bbox=[0, 0, 100, 100],
        sub_index=1, has_mark_anchor=True, has_handwriting_location=True,
        is_answer_slot=True, anchor_source="baidu_direct", template_slot_id=None,
    )
    batch = VlmQuestionBatchTask(batch_id=1, student_question=std, standard_question=std, slots=[task])
    prompt = rvg._build_batch_qwen_prompt(batch, "测试学生")
    assert "STRIKETHROUGH" in prompt
    assert "crossed-out" in prompt or "cross it out" in prompt
