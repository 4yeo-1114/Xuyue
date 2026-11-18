# -*- coding: utf-8 -*-
"""答案集合无序比对（20261112 用户定规则，「地图的三要素」三空不按顺序填也算对）：
同题 ≥2 空逐位比对没全对时，整题答案多重集一致（只是顺序不同）→ 整题各空判对。
覆盖 A链（reference_vlm_grading._apply_answer_set_rule）与 B链（answer_key_grading）。
"""
import pytest

import app.grading.answer_key_grading as ak
import app.grading.reference_vlm_grading as rvg


# ── 共用比较器 ─────────────────────────────────────────────────────────


def test_set_rule_normalize_trims_edge_punct_only():
    assert ak._set_rule_normalize("城市。") == ak._set_rule_normalize("「城市」") == "城市"
    # 负号不许剥：-5 剥成 5 会和 5 假相等
    assert ak._set_rule_normalize("-5") == "-5"
    assert ak._set_rule_normalize("-5") != ak._set_rule_normalize("5")


def test_answer_set_is_objective_letters_and_tf():
    assert ak._answer_set_is_objective("A")
    assert ak._answer_set_is_objective("A、B")
    assert ak._answer_set_is_objective("ABD")
    assert ak._answer_set_is_objective("√")   # normalize → 对
    assert ak._answer_set_is_objective("错")
    assert not ak._answer_set_is_objective("河流")
    assert not ak._answer_set_is_objective("B超")
    assert not ak._answer_set_is_objective("A.北京")


def test_answer_set_matches_multiset_with_duplicates():
    assert ak._answer_set_matches(["城市", "气候", "河流"], ["河流", "城市", "气候"])
    assert ak._answer_set_matches(["360W", "360W"], ["360W", "360W"])
    assert not ak._answer_set_matches(["城市", "气候", "压力"], ["河流", "城市", "气候"])
    assert not ak._answer_set_matches(["360W"], ["360W", "360W"])


# ── A链：reference_vlm_grading._apply_answer_set_rule ─────────────────


def _sub(sub_index, code, stu, std, *, read_uncertain=False, partial_ratio=None):
    return {
        "question_id": sub_index,
        "sub_index": sub_index,
        "correctResult": code,
        "result": rvg.RESULT_TEXT.get(code, "错"),
        "reason": "",
        "analysis": "",
        "confidence": 0.9,
        "partial_ratio": partial_ratio,
        "transcription": stu,
        "read_uncertain": read_uncertain,
        "correct_answer": std,
    }


def _mkq(subs, display_index=5):
    return rvg.VlmQuestion(
        question_id=1,
        display_index=display_index,
        raw={"sub_grading_results": subs},
        bbox=[0, 0, 10, 10],
        question_bbox=[0, 0, 10, 10],
        answer_bbox=None,
        answer_bboxes=[],
        question_words="",
        answer_words=[],
        choices=[],
        question_type="填空题",
    )


def test_rvg_swapped_blanks_forced_correct():
    """地图的三要素：三空填反序 → 整题各空判对，整题聚合跟着变对。"""
    q = _mkq(
        [
            _sub(1, rvg.WRONG, "城市", "河流"),
            _sub(2, rvg.WRONG, "气候", "城市"),
            _sub(3, rvg.WRONG, "河流", "气候"),
        ]
    )
    rvg._apply_answer_set_rule([q])
    subs = q.raw["sub_grading_results"]
    assert all(item["correctResult"] == rvg.CORRECT for item in subs)
    assert all(item["result"] == "对" for item in subs)
    assert all("顺序不同" in item["reason"] for item in subs)
    assert q.raw["correctResult"] == rvg.CORRECT


def test_rvg_order_ok_leaves_reasons_untouched():
    q = _mkq(
        [
            _sub(1, rvg.CORRECT, "河流", "河流"),
            _sub(2, rvg.CORRECT, "城市", "城市"),
        ]
    )
    rvg._apply_answer_set_rule([q])
    assert all(item["reason"] == "" for item in q.raw["sub_grading_results"])


def test_rvg_missing_text_no_fire():
    q = _mkq(
        [
            _sub(1, rvg.WRONG, "", "河流"),      # 转写缺失
            _sub(2, rvg.WRONG, "河流", "城市"),
        ]
    )
    rvg._apply_answer_set_rule([q])
    assert all(
        item["correctResult"] == rvg.WRONG for item in q.raw["sub_grading_results"]
    )


def test_rvg_pending_no_fire():
    """任一空待确认 → 整题不碰（人工拍板优先）。"""
    q = _mkq(
        [
            _sub(1, rvg.PENDING, "城市", "河流"),
            _sub(2, rvg.WRONG, "河流", "城市"),
        ]
    )
    rvg._apply_answer_set_rule([q])
    assert q.raw["sub_grading_results"][0]["correctResult"] == rvg.PENDING
    assert q.raw["sub_grading_results"][1]["correctResult"] == rvg.WRONG


def test_rvg_read_uncertain_no_fire():
    q = _mkq(
        [
            _sub(1, rvg.WRONG, "城市", "河流"),
            _sub(2, rvg.WRONG, "河流", "城市", read_uncertain=True),
        ]
    )
    rvg._apply_answer_set_rule([q])
    assert all(
        item["correctResult"] == rvg.WRONG for item in q.raw["sub_grading_results"]
    )


def test_rvg_letter_answers_no_fire():
    """选项字母按小问对位，跨空对调不算对。"""
    q = _mkq(
        [
            _sub(1, rvg.WRONG, "B", "A"),
            _sub(2, rvg.WRONG, "A", "B"),
        ]
    )
    rvg._apply_answer_set_rule([q])
    assert all(
        item["correctResult"] == rvg.WRONG for item in q.raw["sub_grading_results"]
    )


def test_rvg_tf_answers_no_fire():
    """判断对错同理，不进无序集合。"""
    q = _mkq(
        [
            _sub(1, rvg.WRONG, "错", "对"),
            _sub(2, rvg.WRONG, "对", "错"),
        ]
    )
    rvg._apply_answer_set_rule([q])
    assert all(
        item["correctResult"] == rvg.WRONG for item in q.raw["sub_grading_results"]
    )


def test_rvg_multiset_mismatch_no_fire():
    q = _mkq(
        [
            _sub(1, rvg.WRONG, "城市", "河流"),
            _sub(2, rvg.WRONG, "气候", "城市"),
            _sub(3, rvg.WRONG, "压力", "气候"),  # 压力 ∉ 标准集合
        ]
    )
    rvg._apply_answer_set_rule([q])
    assert all(
        item["correctResult"] == rvg.WRONG for item in q.raw["sub_grading_results"]
    )


def test_rvg_partial_and_wrong_swapped_become_correct():
    q = _mkq(
        [
            _sub(1, rvg.WRONG, "城市", "河流"),
            _sub(2, rvg.PARTIAL, "河流", "城市", partial_ratio=0.5),
        ]
    )
    rvg._apply_answer_set_rule([q])
    subs = q.raw["sub_grading_results"]
    assert all(item["correctResult"] == rvg.CORRECT for item in subs)
    assert all(item["partial_ratio"] is None for item in subs)


def test_rvg_punct_tolerant_and_negative_number_strict():
    # 句读容差：「城市。」==「城市」
    q1 = _mkq(
        [
            _sub(1, rvg.WRONG, "城市。", "河流"),
            _sub(2, rvg.WRONG, "河流", "城市"),
        ]
    )
    rvg._apply_answer_set_rule([q1])
    assert all(
        item["correctResult"] == rvg.CORRECT for item in q1.raw["sub_grading_results"]
    )
    # 负号严判：-5 和 5 不是同一个答案，集合不一致不放行
    q2 = _mkq(
        [
            _sub(1, rvg.WRONG, "3", "-5"),
            _sub(2, rvg.WRONG, "5", "3"),
        ]
    )
    rvg._apply_answer_set_rule([q2])
    assert all(
        item["correctResult"] == rvg.WRONG for item in q2.raw["sub_grading_results"]
    )
    # 真·换序（-5/3 对调）→ 判对
    q3 = _mkq(
        [
            _sub(1, rvg.WRONG, "3", "-5"),
            _sub(2, rvg.WRONG, "-5", "3"),
        ]
    )
    rvg._apply_answer_set_rule([q3])
    assert all(
        item["correctResult"] == rvg.CORRECT for item in q3.raw["sub_grading_results"]
    )


def test_rvg_single_slot_untouched():
    q = _mkq([_sub(1, rvg.WRONG, "城市", "河流")])
    rvg._apply_answer_set_rule([q])
    assert q.raw["sub_grading_results"][0]["correctResult"] == rvg.WRONG


# ── B链：answer_key_grading._apply_answer_set_rule ────────────────────


def _blk(slot_id, sub_index, expected, student, *, kind=None, read_uncertain=False):
    block = {
        "slot_id": slot_id,
        "label": f"5_{sub_index}",
        "index": 5,
        "sub_index": sub_index,
        "expected_answer": expected,
        "student_answer": student,
        "read_uncertain": read_uncertain,
    }
    if kind:
        block["kind"] = kind
    return block


def test_ak_swapped_blanks_forced_correct():
    blocks = [
        _blk("s1", 1, "河流", "城市"),
        _blk("s2", 2, "城市", "气候"),
        _blk("s3", 3, "气候", "河流"),
    ]
    decisions = {"s1": {"status": "wrong"}, "s2": {"status": "wrong"}, "s3": {"status": "wrong"}}
    ak._apply_answer_set_rule(blocks, decisions)
    assert all(decisions[s]["status"] == "correct" for s in ("s1", "s2", "s3"))
    assert all("顺序不同" in b["reason"] for b in blocks)


def test_ak_ungraded_slot_no_fire():
    blocks = [_blk("s1", 1, "河流", "城市"), _blk("s2", 2, "城市", "河流")]
    decisions = {"s1": {"status": "wrong"}}  # s2 未判（ungraded）
    ak._apply_answer_set_rule(blocks, decisions)
    assert decisions["s1"]["status"] == "wrong"
    assert "s2" not in decisions


def test_ak_choice_block_no_fire():
    blocks = [
        _blk("s1", 1, "河流", "城市", kind="choice"),
        _blk("s2", 2, "城市", "河流"),
    ]
    decisions = {"s1": {"status": "wrong"}, "s2": {"status": "wrong"}}
    ak._apply_answer_set_rule(blocks, decisions)
    assert decisions["s1"]["status"] == "wrong"


def test_ak_letter_standards_no_fire():
    blocks = [_blk("s1", 1, "A", "B"), _blk("s2", 2, "B", "A")]
    decisions = {"s1": {"status": "wrong"}, "s2": {"status": "wrong"}}
    ak._apply_answer_set_rule(blocks, decisions)
    assert decisions["s1"]["status"] == "wrong"


def test_ak_all_correct_early_out_keeps_reason():
    blocks = [_blk("s1", 1, "河流", "河流"), _blk("s2", 2, "城市", "城市")]
    decisions = {"s1": {"status": "correct"}, "s2": {"status": "correct"}}
    blocks[0]["reason"] = "原有说明"
    ak._apply_answer_set_rule(blocks, decisions)
    assert blocks[0]["reason"] == "原有说明"


def test_ak_different_questions_not_pooled():
    """不同题的答案不许跨题凑集合（5 题的空对调只在 5 题内找）。"""
    b1 = _blk("s1", 1, "河流", "城市")
    b2 = _blk("s2", 2, "城市", "河流")
    b2["index"] = 6  # 另一道题
    blocks = [b1, b2]
    decisions = {"s1": {"status": "wrong"}, "s2": {"status": "wrong"}}
    ak._apply_answer_set_rule(blocks, decisions)
    assert decisions["s1"]["status"] == "wrong"


def test_ak_integration_grade_paper_swapped_order(monkeypatch):
    """B链整链：三空填反序 → 逐位判错后被集合规则整体翻对。"""
    blocks = [
        {"slot_id": f"slot-{i}", "label": f"5_{i}", "index": 5, "sub_index": i,
         "max_score": 2.0, "bbox": [0, 0, 10, 10]}
        for i in (1, 2, 3)
    ]
    answers = {"5_1": "河流", "5_2": "城市", "5_3": "气候"}
    trans = ["城市", "气候", "河流"]  # 学生填反序
    calls = {"n": 0}

    def _fake_ai(image_path, bbox, prompt, q, prompt_template=None, **kw):
        stu = trans[calls["n"]]
        calls["n"] += 1
        return {
            "status": "wrong",
            "student_answer": stu,
            "reason": "与标准不一致",
            "analysis": "与标准不一致",
            "confidence": 0.9,
            "read_uncertain": False,
        }

    monkeypatch.setattr(ak, "_ai_grade_subjective", _fake_ai)
    monkeypatch.setattr(ak, "_store_answer_key_cache", lambda *a, **k: None)
    decisions = ak.grade_paper_by_answer_key("ignored.png", blocks, answers)
    assert calls["n"] == 3
    assert all(decisions[b["slot_id"]]["status"] == "correct" for b in blocks)
    assert all("顺序不同" in b["reason"] for b in blocks)


def test_ak_integration_unchanged_when_order_correct(monkeypatch):
    blocks = [
        {"slot_id": f"slot-{i}", "label": f"5_{i}", "index": 5, "sub_index": i,
         "max_score": 2.0, "bbox": [0, 0, 10, 10]}
        for i in (1, 2, 3)
    ]
    answers = {"5_1": "河流", "5_2": "城市", "5_3": "气候"}
    trans = ["河流", "城市", "气候"]
    calls = {"n": 0}

    def _fake_ai(image_path, bbox, prompt, q, prompt_template=None, **kw):
        stu = trans[calls["n"]]
        calls["n"] += 1
        return {
            "status": "correct",
            "student_answer": stu,
            "reason": "一致",
            "analysis": "一致",
            "confidence": 0.9,
            "read_uncertain": False,
        }

    monkeypatch.setattr(ak, "_ai_grade_subjective", _fake_ai)
    monkeypatch.setattr(ak, "_store_answer_key_cache", lambda *a, **k: None)
    decisions = ak.grade_paper_by_answer_key("ignored.png", blocks, answers)
    assert all(decisions[b["slot_id"]]["status"] == "correct" for b in blocks)
    # 逐位本来就全对 → 不盖集合规则的说明
    assert all("顺序不同" not in str(b.get("reason") or "") for b in blocks)
