# -*- coding: utf-8 -*-
"""台账#7 题目漏批哨兵：标准侧有正式题号、却没排进任何判分任务的题。

切题/投影失配 → 该题零任务 → _build_blocks/_summarize「没判过不进结果」静默丢掉，
老师看到「题目漏批」。哨兵把这些题挑出来，结果文本亮成
「⚠️第X题：待确认 - 未定位到作答区，本题未批改，请手动批改」，绝不静默消失。
豁免：切题审查删掉的题（layout_deleted）、清空答题区的题（layout_slots_cleared）、
无印刷题号的切题碎片。
"""
from __future__ import annotations

from app.grading.reference_vlm_grading import (
    CORRECT,
    VlmGradingTask,
    VlmQuestion,
    _find_ungraded_standard_questions,
    _summarize_result_text,
)


def _q(qid: int, *, printed_no="3", raw=None, display_index: int = 3) -> VlmQuestion:
    return VlmQuestion(
        question_id=qid,
        display_index=display_index,
        raw=(raw if raw is not None else {}),
        bbox=[0, 0, 180, 90],
        question_bbox=[0, 0, 180, 90],
        answer_bbox=[0, 40, 180, 90],
        answer_bboxes=[[0, 40, 180, 90]],
        question_words="3、他是谁",
        answer_words=["鲁迅"],
        choices=[],
        question_type="填空",
        printed_no=printed_no,
    )


def _task(std: VlmQuestion, stu: VlmQuestion) -> VlmGradingTask:
    return VlmGradingTask(
        task_id=1,
        student_question=stu,
        standard_question=std,
        student_answer_bbox=[0, 40, 180, 90],
        standard_answer_bbox=[0, 40, 180, 90],
        student_context_bbox=[0, 0, 180, 90],
        standard_context_bbox=[0, 0, 180, 90],
        sub_index=1,
        has_mark_anchor=True,
        has_handwriting_location=True,
        is_answer_slot=True,
        anchor_source="template",
        template_slot_id=None,
    )


def test_missed_question_found_when_no_task():
    std = _q(101, printed_no="3")
    got = _find_ungraded_standard_questions([std], [])
    assert got == [std]


def test_covered_question_not_flagged():
    std = _q(101, printed_no="3")
    stu = _q(201, printed_no="3", display_index=3)
    got = _find_ungraded_standard_questions([std], [_task(std, stu)])
    assert got == []


def test_partial_coverage_counted_as_graded():
    """一个题只要有任意一个判分任务（哪怕只有 1 个空），就不算整题漏批。"""
    std = _q(101, printed_no="3")
    stu = _q(201, printed_no="3")
    covered = _q(102, printed_no="4", display_index=4)
    tasks = [_task(std, stu), _task(covered, _q(202, printed_no="4", display_index=4))]
    got = _find_ungraded_standard_questions([std, covered], tasks)
    assert got == []


def test_exempts_no_number_and_deliberate_exclusions():
    no_no = _q(110, printed_no=None)
    zero_no = _q(111, printed_no="", display_index=5)
    deleted = _q(112, printed_no="6", raw={"layout_deleted": True}, display_index=6)
    cleared = _q(113, printed_no="7", raw={"layout_slots_cleared": True}, display_index=7)
    got = _find_ungraded_standard_questions([no_no, zero_no, deleted, cleared], [])
    assert got == []


def test_summary_appends_warning_line_and_counts():
    std = _q(101, printed_no="3")
    text = _summarize_result_text([], ungraded_questions=[std])
    assert "⚠️第3题：待确认 - 未定位到作答区，本题未批改，请手动批改" in text
    assert "总题量：1" in text
    assert "待确认：1" in text


def test_summary_mixed_graded_and_ungraded():
    graded = _q(
        201,
        printed_no="2",
        display_index=2,
        raw={"grading_result": {"correctResult": CORRECT, "analysis": "与标准答案一致"}},
    )
    missed = _q(101, printed_no="3", display_index=3)
    text = _summarize_result_text([graded], ungraded_questions=[missed])
    assert "第2题：对" in text
    assert "⚠️第3题：待确认" in text
    assert "总题量：2" in text
    assert "正确：1" in text
    assert "待确认：1" in text


def test_summary_without_ungraded_is_unchanged():
    graded = _q(
        201,
        printed_no="2",
        display_index=2,
        raw={"grading_result": {"correctResult": CORRECT, "analysis": "对"}},
    )
    text = _summarize_result_text([graded])
    assert "⚠️" not in text
    assert "总题量：1" in text
