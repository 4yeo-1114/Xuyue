# -*- coding: utf-8 -*-
"""多选题字母集合判定规则（20261021 用户定）：
选错任意一个 → 错 0 分；只少选没多选 → 半对（按选对比例）；集合全同 → 对。
覆盖 answer_key 选择题支路 / match_answers 兜底 / 参考卷 _multi_select_letter_rule。
"""
import pytest

import app.grading.answer_key_grading as ak
import app.grading.reference_vlm_grading as rvg


# ── answer_key 选择题支路（grade_paper_by_answer_key 字母集合比对） ──────


def _grade_choice(student: str, expected: str, max_score: float = 4.0, monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setattr(ak, "_ocr_choice_answers", lambda *a, **k: {})
        monkeypatch.setattr(ak, "_omr_choice_answer", lambda *a, **k: student)
        monkeypatch.setattr(ak, "_vl_read_choice_answer", lambda *a, **k: None)
    block = {
        "slot_id": "slot-1",
        "label": "1_1",
        "kind": "choice",
        "index": 1,
        "max_score": max_score,
        "choice_options": ["A", "B", "C", "D"],
        "bbox": [0, 0, 20, 20],
    }
    decisions = ak.grade_paper_by_answer_key("ignored.png", [block], {"1_1": expected})
    return decisions["slot-1"]


def test_multi_select_exact_match_correct(monkeypatch):
    # AD vs DA：顺序无关，全同=对
    dec = _grade_choice("DA", "AD", monkeypatch=monkeypatch)
    assert dec["status"] == "correct"


def test_multi_select_any_wrong_pick_is_wrong(monkeypatch):
    # AD vs BD：选错 B → 错，不给分（哪怕选对了 D）
    dec = _grade_choice("BD", "AD", monkeypatch=monkeypatch)
    assert dec["status"] == "wrong"
    assert dec.get("score") in (None, 0)


def test_multi_select_wrong_plus_missing_is_wrong(monkeypatch):
    # AD vs BC：选错 B、C → 错
    dec = _grade_choice("BC", "AD", monkeypatch=monkeypatch)
    assert dec["status"] == "wrong"


def test_multi_select_extra_wrong_pick_is_wrong(monkeypatch):
    # AD vs ABD：多选了 B → 错（不算全对）
    dec = _grade_choice("ABD", "AD", monkeypatch=monkeypatch)
    assert dec["status"] == "wrong"


def test_multi_select_missing_only_is_partial(monkeypatch):
    # AD vs D：只少选 A、没多选 → 半对，score = 1/2 × 4 = 2
    dec = _grade_choice("D", "AD", monkeypatch=monkeypatch)
    assert dec["status"] == "partial"
    assert dec["score"] == 2
    assert dec["partial_ratio"] == pytest.approx(0.5)


def test_multi_select_missing_multiple_is_partial(monkeypatch):
    # ABD vs A：少选两个 → 仍是半对，score = 1/3 × 3 = 1
    dec = _grade_choice("A", "ABD", max_score=3.0, monkeypatch=monkeypatch)
    assert dec["status"] == "partial"
    assert dec["score"] == 1


def test_multi_select_separator_letters_still_compared(monkeypatch):
    # OCR 读出「A、D」：剥分隔符后集合比对 = 全同 → 对
    dec = _grade_choice("A、D", "AD", monkeypatch=monkeypatch)
    assert dec["status"] == "correct"


def test_single_select_unaffected(monkeypatch):
    # 单选 B vs B → 对；A vs B → 错（不走多选分支）
    assert _grade_choice("B", "B", monkeypatch=monkeypatch)["status"] == "correct"
    assert _grade_choice("A", "B", monkeypatch=monkeypatch)["status"] == "wrong"


# ── match_answers 兜底：多选字母不走「包含即对」 ─────────────────────────


def test_match_answers_multi_letter_order_free():
    assert ak.match_answers("DAB", "ABD") == "对"


def test_match_answers_multi_letter_no_containment():
    # ABD ⊃ AB：旧「包含即对」会误判对，新规则=错（多选了 D）
    assert ak.match_answers("ABD", "AB") == "错"
    assert ak.match_answers("D", "AD") == "错"  # 少选兜底只判对/错，半对在选择题支路


def test_match_answers_filling_containment_kept():
    # 填空包含关系宽容不受影响（非 A-D 多字母）
    assert ak.match_answers("等于3牛顿", "等于3") == "对"


# ── 参考卷 _multi_select_letter_rule（VL 判定后确定性覆盖） ──────────────


def test_rvg_rule_all_cases():
    assert rvg._multi_select_letter_rule("AD", "AD") == (rvg.CORRECT, None)
    assert rvg._multi_select_letter_rule("DA", "AD") == (rvg.CORRECT, None)
    assert rvg._multi_select_letter_rule("BD", "AD") == (rvg.WRONG, None)   # 选错 B
    assert rvg._multi_select_letter_rule("ABD", "AD") == (rvg.WRONG, None)  # 多选 B
    assert rvg._multi_select_letter_rule("D", "AD") == (rvg.PARTIAL, 0.5)   # 少选
    assert rvg._multi_select_letter_rule("A", "ABD") == (rvg.PARTIAL, round(1 / 3, 3))


def test_rvg_rule_fail_open_on_non_letter():
    assert rvg._multi_select_letter_rule("见图", "AD") is None
    assert rvg._multi_select_letter_rule("BD", "参考答案：不固定") is None
    assert rvg._multi_select_letter_rule("B", "A") is None  # 单选不归它管


def test_rvg_rule_separators_and_prefix():
    assert rvg._multi_select_letter_rule("A、D", "第5题：AD") == (rvg.CORRECT, None)


def test_normalize_decision_override_wrong_pick(monkeypatch):
    # VL 宽容判了对，但转写 BD ≠ 标准 AD → 确定性覆盖为错
    d = rvg._normalize_decision(
        {
            "correctResult": rvg.CORRECT,
            "result": "对",
            "transcription": "BD",
            "standard_answer_text": "AD",
        },
        3,
        standard_answer_text="AD",
    )
    assert d["correctResult"] == rvg.WRONG
    assert d["result"] == "错"
    assert "错误选项" in d["reason"]


def test_normalize_decision_override_missing_is_partial(monkeypatch):
    # VL 一棍子判错，但只少选 → 覆盖为半对
    d = rvg._normalize_decision(
        {
            "correctResult": rvg.WRONG,
            "result": "错",
            "transcription": "D",
            "standard_answer_text": "AD",
        },
        3,
        standard_answer_text="AD",
    )
    assert d["correctResult"] == rvg.PARTIAL
    assert d["result"] == "半对"
    assert d["partial_ratio"] == 0.5


def test_normalize_decision_does_not_override_pending(monkeypatch):
    # 表引文对不上转人工后，多选覆盖不许抢跑
    d = rvg._normalize_decision(
        {
            "correctResult": rvg.PENDING,
            "result": "待确认",
            "transcription": "BD",
            "standard_answer_text": "AD",
        },
        3,
        standard_answer_text="AD",
    )
    assert d["correctResult"] == rvg.PENDING
