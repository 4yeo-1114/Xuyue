# -*- coding: utf-8 -*-
"""看图直判兜底（对齐批改君「image 1 即标准答案」）。

答案表行转写带 [?] 等不可靠标记时：
1. 不给错文（错文会反判学生）→ 表文本/本槽标准列落〈文本缺失〉哨兵；
2. 不给空（空会漏进 answer_words 机配兜底）；
3. read_guard 不因哨兵打待确认（否则淹没老师）；
4. 两道文本闸（表引文回验/标准列冲突）对哨兵放行——表文本作废，
   该槽判分只认 image 1 红框，这是提示词既有兜底条款的生效通道。

20261108 照批改君整改：read_guard/表引文回验闸/字母矛盾闸从判分链废除
（函数保留但不再挂钩），判词三态定案；哨兵映射（1/2）仍是进提示词前的
错文防线，文本闸函数（5/6）保留自身行为供未来复用。
"""
from __future__ import annotations

from types import SimpleNamespace

from app.grading.reference_vlm_grading import (
    CORRECT,
    PENDING,
    WRONG,
    _TEXT_MISSING,
    _answer_table_slot_text,
    _answer_table_summary_text,
    _apply_read_guard,
    _apply_standard_text_conflict_guard,
    _normalize_decision,
    _standard_answer_text,
    _table_quote_mismatch,
    _transcription_flagged,
    _unreliable_as_text_missing,
    VlmQuestion,
)

BBOX = [20, 20, 120, 60]


def _q(**kwargs) -> VlmQuestion:
    defaults = dict(
        question_id=1,
        display_index=1,
        raw={},
        bbox=[0, 0, 180, 90],
        question_bbox=[0, 0, 180, 90],
        answer_bbox=list(BBOX),
        answer_bboxes=[list(BBOX)],
        question_words="题干",
        answer_words=["机配兜底文本"],
        choices=[],
        question_type="填空",
        printed_no="3",
    )
    defaults.update(kwargs)
    return VlmQuestion(**defaults)


# ── 1. 哨兵映射 ──────────────────────────────────────────────


def test_unreliable_as_text_missing_maps_flagged_text():
    assert _unreliable_as_text_missing("参见[?]图") == _TEXT_MISSING
    assert _unreliable_as_text_missing("肢[体|休]") == _TEXT_MISSING
    assert _unreliable_as_text_missing("  遏[?]制  ") == _TEXT_MISSING


def test_unreliable_as_text_missing_passes_clean_and_empty():
    assert _unreliable_as_text_missing("扼制 柳暗花明") == "扼制 柳暗花明"
    assert _unreliable_as_text_missing("  空格  ") == "空格"
    assert _unreliable_as_text_missing("") == ""
    assert _unreliable_as_text_missing(None) is None


# ── 2. 完整表：不可靠行标〈文本缺失〉，不给错文 ─────────────────


def test_answer_table_summary_marks_flagged_rows():
    table = {
        "questions": [
            {"display_index": 1, "printed_no": "2", "full_answer": "B"},
            {"display_index": 2, "printed_no": "3", "full_answer": "参见[?]图"},
            {"display_index": 3, "printed_no": "4", "full_answer": "扼制 柳暗花明"},
            {"display_index": 4, "printed_no": "5", "full_answer": "肢[体|休]"},
        ]
    }
    text = _answer_table_summary_text(table)
    assert "第2题：B" in text
    assert "第4题：扼制 柳暗花明" in text
    assert "第3题：〈文本缺失〉" in text
    assert "第5题：〈文本缺失〉" in text
    # 错文绝不进表（[?] 片段/候选字都不能漏给模型当文本权威）
    assert "[?]" not in text
    assert "参见" not in text
    assert "肢[体|休]" not in text


# ── 3. 本槽标准列：哨兵不漏 answer_words 兜底 ───────────────────


def test_slot_text_flagged_maps_to_sentinel():
    table = {
        "questions": [
            {
                "display_index": 1,
                "printed_no": "3",
                "full_answer": "参见[?]图",
                "slots": [{"bbox": list(BBOX), "answer_text": "参见[?]图"}],
            }
        ]
    }
    q = _q()
    raw = _answer_table_slot_text(table, q, BBOX, prefer_no="3")
    assert raw == "参见[?]图"
    assert _unreliable_as_text_missing(raw) == _TEXT_MISSING


def test_standard_answer_text_sentinel_blocks_word_fallback():
    # explicit 是哨兵（非空）→ 不许退回 answer_words 机配文本
    task = SimpleNamespace(
        standard_answer_text=_TEXT_MISSING,
        standard_question=_q(),
        standard_answer_bbox=list(BBOX),
    )
    assert _standard_answer_text(task) == _TEXT_MISSING
    # explicit 为空才走 answer_words 兜底（既有行为不变）
    task_empty = SimpleNamespace(
        standard_answer_text=None,
        standard_question=_q(),
        standard_answer_bbox=list(BBOX),
    )
    assert _standard_answer_text(task_empty) == "机配兜底文本"


# ── 4. read_guard：哨兵不打待确认，错文照旧打 ────────────────────


def _decision(**overrides) -> dict:
    data = {
        "question_id": 5,
        "correctResult": CORRECT,
        "result": "对",
        "transcription": "答",
        "read_confidence": 0.95,
        "reason": "与标准一致",
        "analysis": "与标准一致",
        "confidence": 0.9,
    }
    data.update(overrides)
    return data


def test_read_guard_ignores_text_missing_sentinel():
    decision = _normalize_decision(_decision(), 5, standard_answer_text=_TEXT_MISSING)
    assert decision["correctResult"] == CORRECT
    assert decision["read_uncertain"] is False
    assert "待人工确认" not in decision["reason"]


def test_flagged_standard_text_no_longer_forces_pending():
    # 20261108 照批改君：read_guard 整链废除——旁路直塞的 [?] 错文不再强制待确认，
    # image 1 是权威，模型照图判的判词定案
    decision = _normalize_decision(_decision(), 5, standard_answer_text="参见[?]图")
    assert decision["correctResult"] == CORRECT
    assert decision["read_uncertain"] is False
    assert "待人工确认" not in decision["reason"]


# ── 5. 表引文回验：哨兵行无从校验放行，错行/抄错字照旧拦 ──────────


def test_quote_mismatch_passes_on_text_missing_row():
    table = "第2题：B\n第3题：〈文本缺失〉\n第4题：扼制 柳暗花明\n"
    # 模型照抄表里的哨兵行
    assert _table_quote_mismatch("第3题：〈文本缺失〉", 3, table) is None
    assert _table_quote_mismatch("〈文本缺失〉", 3, table) is None
    # 模型对缺文行改抄 image 1 答案（看图直判的正常行为）→ 不算「引文找不到」
    assert _table_quote_mismatch("第3题：空间", 3, table) is None
    # 无 located_no 也放行（引文本身就是哨兵）
    assert _table_quote_mismatch("第3题：〈文本缺失〉", None, table) is None
    # 非缺文行的查错行/抄错字照旧拦（回归）
    assert _table_quote_mismatch("第4题：遏制 柳暗花明", 4, table) is not None
    assert _table_quote_mismatch("第4题：空间", 4, table) is not None


def test_quote_mismatch_via_normalize_decision_image1_fallback():
    """headline：缺文行 + 模型引 image 1 答案 → 判分落得下去，不进待确认。"""
    table_text = "第2题：B\n第3题：〈文本缺失〉\n"
    decision = _normalize_decision(
        _decision(
            correctResult=WRONG,
            result="错",
            standard_quote="第3题：空间",
            located_no=3,
        ),
        5,
        standard_answer_text=_TEXT_MISSING,
        answer_table_text=table_text,
    )
    assert decision["correctResult"] == WRONG
    assert "待人工确认" not in decision["reason"]


# ── 6. 标准列冲突闸：哨兵列无文本权威可对质 → 放行 ───────────────


def test_conflict_guard_skips_text_missing_column():
    decision = _decision(standard_quote="第3题：空间")
    assert _apply_standard_text_conflict_guard(decision, _TEXT_MISSING) is False
    assert decision["correctResult"] == CORRECT
    # 哨兵带第N题前缀的引文同样放行
    decision2 = _decision(standard_quote="第3题：〈文本缺失〉")
    assert _apply_standard_text_conflict_guard(decision2, _TEXT_MISSING) is False
    # 回归：真实文本对不上照旧拦
    decision3 = _decision(standard_quote="第3题：空间")
    assert _apply_standard_text_conflict_guard(decision3, "不矛盾。因为济南四周有一圈小山") is True
    assert decision3["correctResult"] == PENDING


def test_transcription_flagged_does_not_match_sentinel():
    # 哨兵本身绝不能再被当成「识别不清」标记（否则守卫自噬回待确认）
    assert not _transcription_flagged(_TEXT_MISSING)
    assert _transcription_flagged("参见[?]图")
