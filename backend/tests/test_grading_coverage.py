# -*- coding: utf-8 -*-
"""批改覆盖率 / 判定原子性 · 纯函数测试（客户反馈：第14题全员无判定标记）。

覆盖：
  1. 对象 / dict 两种输入形态取应有题号（printed_no 优先，空则退回 display_index）
  2. 标准卷 1..30、blocks 缺 14 → missing == [14]、coverage < 1
  3. 块在但无任何判定 → unjudged，ensure_atomicity 后显式「待确认 + needs_review」
  4. 「待确认」题进 pending，不算 missing
  5. 全部判定完整 → missing/unjudged 空、coverage == 1.0
  6. ensure_atomicity 的 actions 含 missing 题号说明
另补：一题多槽部分未判仍要标、重复调用幂等、码兜底与碎片块不进统计。
"""
from dataclasses import dataclass

from app.grading import grading_coverage as gc


@dataclass
class FakeQuestion:
    """模拟 VlmQuestion 的题号字段（测试不 import 重量级判分模块）。"""

    display_index: int
    printed_no: object = None


def _block(index, result="对", status=None, sub_index=1, **extra):
    block = {"index": index, "sub_index": sub_index, "result": result}
    if status is not None:
        block["status"] = status
    block.update(extra)
    return block


def _paper_1_to_30():
    """标准卷 1..30（对象形态，printed_no 与 display_index 同号）。"""
    return [FakeQuestion(display_index=n, printed_no=str(n)) for n in range(1, 31)]


def _blocks_1_to_13_and_15_to_30():
    """blocks 覆盖 1..13 与 15..30，恰好缺 14。"""
    return [_block(n) for n in list(range(1, 14)) + list(range(15, 31))]


# ── 1. 两种输入形态取题号 ─────────────────────────────────────────────────


def test_expected_numbers_for_object_and_dict_inputs():
    objects = [
        FakeQuestion(display_index=1, printed_no="1"),
        FakeQuestion(display_index=2, printed_no=""),   # 空字符串 → 退回 display_index
        FakeQuestion(display_index=3, printed_no=None),  # None → 退回 display_index
    ]
    dicts = [
        {"display_index": 1, "printed_no": "1"},
        {"display_index": 2, "printed_no": ""},
        {"display_index": 3},  # 无 printed_no 键
    ]
    expected = [1, 2, 3]
    assert gc.expected_question_numbers(objects) == expected
    assert gc.expected_question_numbers(dicts) == expected


def test_expected_numbers_dedup_sorted_and_ignore_unnumbered():
    items = [
        FakeQuestion(display_index=5, printed_no="5"),
        FakeQuestion(display_index=5, printed_no="5"),  # 重复 → 去重
        FakeQuestion(display_index=2, printed_no="2"),
        {"display_index": None, "printed_no": ""},  # 碎片：无题号 → 不进表
        FakeQuestion(display_index=0, printed_no=""),  # 0 号无效 → 不进表
    ]
    assert gc.expected_question_numbers(items) == [2, 5]


def test_expected_numbers_printed_no_wins_over_display_index():
    # 老师重编号后 display_index 变了，printed_no 是卷面真实题号
    items = [FakeQuestion(display_index=7, printed_no="第14题")]
    assert gc.expected_question_numbers(items) == [14]


# ── 2. 缺第 14 题 ────────────────────────────────────────────────────────


def test_missing_question_14_and_coverage_below_one():
    report = gc.coverage_report(_paper_1_to_30(), _blocks_1_to_13_and_15_to_30())
    assert report["missing"] == [14]
    assert 14 not in report["appeared"]
    assert report["stats"]["expected"] == 30
    assert 0.0 < report["stats"]["coverage"] < 1.0
    assert report["stats"]["coverage"] == round(29 / 30, 4)
    assert report["stats"]["missing"] == 1


# ── 3. 块在、判定全空 → unjudged + 原子化 ────────────────────────────────


def test_unjudged_question_is_reported_and_marked():
    standard = _paper_1_to_30()
    blocks = _blocks_1_to_13_and_15_to_30()
    blocks.append(_block(14, result=""))  # 第 14 题块在，但没有任何判定
    report = gc.coverage_report(standard, blocks)

    assert report["unjudged"] == [14]
    assert report["missing"] == []  # 出现了，不算缺题
    assert 14 not in report["judged"]

    target = next(b for b in blocks if b["index"] == 14)
    actions = gc.ensure_atomicity(blocks, report)

    assert target["result"] == "待确认"
    assert target["needs_review"] is True
    assert target["read_uncertain"] is True
    assert "未产出判定" in target["reason"]
    assert any(
        a["action"] == "mark_unjudged" and a["index"] == 14 for a in actions
    )
    # 已判定块不被误标
    judged_block = next(b for b in blocks if b["index"] == 3)
    assert "needs_review" not in judged_block
    assert judged_block["result"] == "对"


def test_unjudged_by_ungraded_status_and_by_missing_fields():
    # status="ungraded"（前端手动批改口径）与 status/result 全缺，都必须算未判定
    blocks = [
        _block(1, result="对", status="correct"),
        {"index": 2, "sub_index": 1, "status": "ungraded"},
        {"index": 3, "sub_index": 1},  # 什么都空
    ]
    report = gc.coverage_report(
        [{"display_index": 1}, {"display_index": 2}, {"display_index": 3}], blocks
    )
    assert report["expected"] == [1, 2, 3]
    assert report["unjudged"] == [2, 3]
    gc.ensure_atomicity(blocks, report)
    for block in blocks[1:]:
        assert block["result"] == "待确认"
        assert block["needs_review"] is True


def test_partially_judged_question_still_marks_empty_slot():
    # 一题两槽：槽1判对、槽2未判 → 题目级算已判定，但空槽必须被显式标出
    blocks = [
        _block(1, result="对", sub_index=1),
        _block(1, result="", sub_index=2),
    ]
    report = gc.coverage_report([1], blocks)
    assert report["judged"] == [1]
    assert report["unjudged"] == []

    gc.ensure_atomicity(blocks, report)
    assert blocks[0]["result"] == "对"
    assert "needs_review" not in blocks[0]
    assert blocks[1]["result"] == "待确认"
    assert blocks[1]["needs_review"] is True


# ── 4. 待确认不算 missing ────────────────────────────────────────────────


def test_pending_question_listed_as_pending_not_missing():
    standard = _paper_1_to_30()
    blocks = _blocks_1_to_13_and_15_to_30()
    blocks.append(_block(14, result="待确认"))
    report = gc.coverage_report(standard, blocks)

    assert report["pending"] == [14]
    assert report["missing"] == []
    assert 14 not in report["judged"]
    assert report["stats"]["coverage"] == round(29 / 30, 4)

    # 待确认块本身已有可见判定，ensure_atomicity 不再改写它
    target = next(b for b in blocks if b["index"] == 14)
    gc.ensure_atomicity(blocks, report)
    assert target["result"] == "待确认"
    assert "needs_review" not in target


def test_pending_via_status_and_code_fallback():
    blocks = [
        _block(1, status="pending"),                       # 英文状态
        {"index": 2, "sub_index": 1, "baidu_correct_result": 5},  # 只有码
    ]
    report = gc.coverage_report(
        [{"display_index": 1}, {"display_index": 2}], blocks
    )
    assert report["pending"] == [1, 2]
    assert report["unjudged"] == []


# ── 5. 全部判定完整 ──────────────────────────────────────────────────────


def test_full_coverage():
    standard = _paper_1_to_30()
    blocks = [_block(n) for n in range(1, 31)]
    report = gc.coverage_report(standard, blocks)

    assert report["missing"] == []
    assert report["unjudged"] == []
    assert report["pending"] == []
    assert report["unexpected"] == []
    assert report["stats"]["coverage"] == 1.0
    assert report["stats"]["judged"] == 30

    actions = gc.ensure_atomicity(blocks, report)
    assert actions == []
    # 完整卷块不被污染
    assert all("needs_review" not in b for b in blocks)


# ── 6. actions 含 missing 题号说明 ───────────────────────────────────────


def test_actions_include_missing_question_entry():
    standard = _paper_1_to_30()
    blocks = _blocks_1_to_13_and_15_to_30()
    report = gc.coverage_report(standard, blocks)
    actions = gc.ensure_atomicity(blocks, report)

    missing_actions = [a for a in actions if a["action"] == "missing_question"]
    assert [a["index"] for a in missing_actions] == [14]
    assert "人工确认" in missing_actions[0]["reason"]


def test_actions_cover_both_unjudged_and_missing():
    standard = _paper_1_to_30()
    blocks = [b for b in _blocks_1_to_13_and_15_to_30() if b["index"] != 15]
    blocks.append(_block(14, result=""))
    report = gc.coverage_report(standard, blocks)
    actions = gc.ensure_atomicity(blocks, report)

    by_action = {(a["action"], a["index"]) for a in actions}
    assert ("missing_question", 15) in by_action
    assert ("mark_unjudged", 14) in by_action


# ── 附加：幂等 / 碎片块 / 异常题号口径 ───────────────────────────────────


def test_ensure_atomicity_is_idempotent():
    blocks = [{"index": 7, "sub_index": 1, "reason": "原说明"}]
    report = gc.coverage_report([7], blocks)
    gc.ensure_atomicity(blocks, report)
    first = dict(blocks[0])
    gc.ensure_atomicity(blocks, report)
    assert blocks[0]["reason"] == first["reason"]
    assert blocks[0]["reason"].count("未产出判定") == 1
    assert blocks[0]["reason"].startswith("原说明")


def test_blocks_without_question_no_are_ignored():
    # 没有题号的切题碎片块不进统计、不被标记（也不会被当成缺题去标）
    blocks = [_block(None), {"sub_index": 1, "result": ""}]
    report = gc.coverage_report([{"display_index": 1}], blocks)
    assert report["expected"] == [1]
    assert report["appeared"] == []
    assert report["missing"] == [1]  # 唯一「应有」题确实一块都没有
    gc.ensure_atomicity(blocks, report)
    assert "needs_review" not in blocks[0]
    assert "needs_review" not in blocks[1]


def test_unexpected_number_surfaces_numbering_mismatch():
    report = gc.coverage_report(
        [{"display_index": 1}, {"display_index": 2}],
        [_block(1), _block(2), _block(99)],
    )
    assert report["unexpected"] == [99]
    assert report["stats"]["coverage"] == 1.0  # 多出的块不虚增覆盖率
