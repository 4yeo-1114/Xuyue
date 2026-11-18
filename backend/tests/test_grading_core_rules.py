# -*- coding: utf-8 -*-
"""判分核心纯逻辑单元测试（固化第 3 步修复的关键比对规则）。

覆盖：标准答案解析（各种格式）、归一化、选择题字母集合比对（单/多/少/错选）、
多空题空号拆分与 key 对齐、多空命中比例、待人工确认留痕。
不依赖网络与数据库。
"""
from __future__ import annotations

import pytest

import app.grading.answer_key_grading as ak


# ── 标准答案解析 ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        # 单空：一行多题
        ("1.A 2.C 3.D 4.B 5.A", {"1_1": "A", "2_1": "C", "3_1": "D", "4_1": "B", "5_1": "A"}),
        # 小数答案不得被截断（旧版 bug：0.5 → 0）
        ("1. 0.5 2. 1.08×10^5 3. 2", {"1_1": "0.5", "2_1": "1.08×10^5", "3_1": "2"}),
        # 多空题
        ("5.1 B 5.2 D", {"5_1": "B", "5_2": "D"}),
        # 负号答案
        ("9.0.5 10.36W 11.-3", {"9_1": "0.5", "10_1": "36W", "11_1": "-3"}),
        # 含空格的答案不被切成两题
        ("1. 做功 2. 不做功", {"1_1": "做功", "2_1": "不做功"}),
        ("1. 0.5 m/s 2. 3", {"1_1": "0.5 m/s", "2_1": "3"}),
        # 多空 + 科学计数法
        ("5.1 1.08×10^5 5.2 3", {"5_1": "1.08×10^5", "5_2": "3"}),
        # 连续题号
        ("1-5 ABCDA", {"1_1": "A", "2_1": "B", "3_1": "C", "4_1": "D", "5_1": "A"}),
        # 数值范围答案行不是题号范围（不应被解成题号）
        ("2-3 m", {}),
        # 每行一题：整行保留，括号小问不被拆
        ("1.不做功\n2.变大\n3.弹性势能", {"1_1": "不做功", "2_1": "变大", "3_1": "弹性势能"}),
        ("15.(1)18 km/h (2)1.08×10^5 J", {"15_1": "(1)18 km/h (2)1.08×10^5 J"}),
        # 空输入
        ("", {}),
        ("   ", {}),
    ],
)
def test_parse_answer_key_text(text, expected):
    assert ak.parse_answer_key_text(text) == expected


def test_parse_entry_first_wins_for_duplicate_question():
    # 重复题号保留第一次出现（setdefault），避免后面的杂音覆盖
    got = ak.parse_answer_key_text("1.A 2.C\n1.B")
    assert got["1_1"] == "A"


# ── 归一化 ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        (" a ", "A"),
        ("Ａ", "A"),          # 全角字母转半角
        ("√", "对"),
        ("✓", "对"),
        ("×", "错"),
        ("✗", "错"),
        ("0.5", "0.5"),
        ("1.08×10⁵", "1.08×10⁵"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_answer(raw, expected):
    assert ak.normalize_answer(raw) == expected


# ── 选择题字母集合比对（match_answers 的多选分支） ─────────────────────


@pytest.mark.parametrize(
    "student,expected,verdict",
    [
        ("A", "A", "对"),
        ("C", "A", "错"),
        ("ABD", "ABD", "对"),
        ("DAB", "ABD", "对"),   # 顺序无关
        ("A、B、D", "ABD", "对"),  # 分隔符无关
        ("AB", "ABD", "错"),     # 少选：match_answers 层面判错（比例分走选择题支路）
        ("ABDC", "ABD", "错"),   # 多选
        ("", "A", "未作答"),
        ("C", "", "错"),
    ],
)
def test_match_answers_choice(student, expected, verdict):
    assert ak.match_answers(student, expected) == verdict


def test_match_answers_fillin_containment():
    # 非纯数字且互相包含 → 对
    assert ak.match_answers("每秒做功60J", "做功60J") == "对"
    # 纯数字不走包含（避免 12 误判含 2）
    assert ak.match_answers("12", "2") == "错"


# ── 多空题空号拆分与 key 对齐 ──────────────────────────────────────────


def test_split_expected_blanks_legacy_format():
    assert ak._split_expected_blanks("1 做功 1.2 不做功 1.3 功率", 1) == ["做功", "不做功", "功率"]


def test_split_expected_blanks_single():
    assert ak._split_expected_blanks("做功", 1) == ["做功"]
    assert ak._split_expected_blanks("", 1) == []


def test_expected_blanks_for_block_collects_all_subs():
    key = {"5_1": "做功", "5_2": "不做功", "5_3": "功率"}
    assert ak._expected_blanks_for_block(key, {"index": 5}, "做功") == ["做功", "不做功", "功率"]
    # 只有一个空
    assert ak._expected_blanks_for_block({"7_1": "变大"}, {"index": 7}, "变大") == ["变大"]
    # 一个都没有
    assert ak._expected_blanks_for_block({}, {"index": 9}, None) == []


def test_fillin_hit_ratio_multi_blank():
    blanks = ["做功", "不做功"]
    assert ak._fillin_hit_ratio("做功 不做功", "x", 5, blanks=blanks) == 1.0
    assert ak._fillin_hit_ratio("做功", "x", 5, blanks=blanks) == 0.5
    assert ak._fillin_hit_ratio("完全无关", "x", 5, blanks=blanks) == 0.0
    assert ak._fillin_hit_ratio("", "x", 5, blanks=blanks) == 0.0


# ── 静默漏批必须留痕（无标准答案路径） ──────────────────────────────────


def test_missing_answer_key_marks_review_instead_of_silent_skip(tmp_path):
    """没有标准答案时，块必须显式「待确认」+ 原因，不许无声消失。"""
    from PIL import Image

    img = tmp_path / "p.png"
    Image.new("RGB", (200, 120), "white").save(img)
    blocks = [
        {"slot_id": "s1", "index": 3, "bbox": [10, 10, 190, 100], "max_score": 1},
    ]
    decisions = ak.grade_paper_by_answer_key(str(img), blocks, {})
    assert "s1" not in decisions, "无标准答案不应产出判定"
    b = blocks[0]
    assert b.get("needs_review") is True
    assert "标准答案缺失" in str(b.get("reason") or "")
    assert b.get("result") == "待确认"


def test_choice_read_uncertain_marked_when_no_letter(monkeypatch, tmp_path):
    """选择题读出不含 A-D 的内容（如连笔 B 被读成 13）→ 待人工确认，不硬判错。"""
    from PIL import Image

    img = tmp_path / "p.png"
    Image.new("RGB", (200, 120), "white").save(img)
    monkeypatch.setattr(ak, "_omr_choice_answer", lambda *a, **k: None)
    monkeypatch.setattr(ak, "_ocr_choice_answers", lambda *a, **k: {})
    monkeypatch.setattr(ak, "_vl_read_choice_answer", lambda *a, **k: "13")
    blocks = [{"slot_id": "c1", "index": 6, "bbox": [10, 10, 60, 50], "max_score": 1, "kind": "choice"}]
    decisions = ak.grade_paper_by_answer_key(str(img), blocks, {"6_1": "B"})
    assert "c1" not in decisions
    b = blocks[0]
    assert b.get("read_uncertain") is True
    assert "无法可靠比对" in str(b.get("reason") or "")


# ── 待确认放行：认不准的字不影响判分 ───────────────────────────────────


def test_uncertain_free_text_strips_markers():
    assert ak._uncertain_free_text("做功[?]") == "做功"
    assert ak._uncertain_free_text("[做功|不做功]") == ""
    assert ak._uncertain_free_text("海拔[甲|乙]500米") == "海拔500米"
    assert ak._uncertain_free_text("正常") == "正常"


def test_uncertain_region_irrelevant_when_key_answer_intact():
    # 只有一个边角字认不准，标准答案完整出现 → 可以放行判对
    assert ak._uncertain_region_is_irrelevant("做功[?]", "第1空：做功") is True
    assert ak._uncertain_region_is_irrelevant("0.5[?]", "0.5") is True
    # 认不准的恰是标准答案本身 → 不能放行
    assert ak._uncertain_region_is_irrelevant("[做功|不做功]", "第1空：做功") is False
    # 多空题：少一个空 → 不能放行
    assert ak._uncertain_region_is_irrelevant("做功[?]", "第1空：做功；第2空：不做功") is False
    # 多空题：两个空都确定 → 放行
    assert ak._uncertain_region_is_irrelevant("做功[?]不做功", "第1空：做功；第2空：不做功") is True


def test_text_markers_still_flagged_after_cleanup_fails():
    # 清理后什么都没剩（整题都认不准）→ 仍走待确认
    assert ak._uncertain_region_is_irrelevant("[?][?]", "第1空：做功") is False
    assert ak._uncertain_region_is_irrelevant("", "第1空：做功") is False
