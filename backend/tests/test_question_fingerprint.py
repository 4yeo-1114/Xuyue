# -*- coding: utf-8 -*-
"""DL3 · 题目稳定 ID 指纹纯函数单测（无 DB 依赖，只用 stdlib）。

覆盖：同题幂等 / 空白差异吸收 / 全半角吸收 / 标点吸收 / 实质变化产生新指纹 /
空输入边界 / 输出格式 / 字段边界。
"""
import re

from app.utils.question_fingerprint import question_fingerprint

_FP_RE = re.compile(r"^fp_[0-9a-f]{64}$")


def _fp(subject=None, question_type=None, question_text=None, correct_answer=None):
    return question_fingerprint(subject, question_type, question_text, correct_answer)


# ── 同题两次 → 指纹一致（含 None 字段组合） ─────────────────────────

def test_same_question_twice_same_fingerprint():
    a = _fp("数学", "解答题", "求 2x+3=7 的解。", "x=2")
    b = _fp("数学", "解答题", "求 2x+3=7 的解。", "x=2")
    assert a == b


def test_same_question_with_none_fields_deterministic():
    a = _fp(None, "选择题", "1+1=?", "2")
    b = _fp(None, "选择题", "1+1=?", "2")
    assert a == b
    assert _FP_RE.fullmatch(a)


# ── 空白差异吸收 ───────────────────────────────────────────────────

def test_whitespace_differences_absorbed():
    base = _fp("数学", "解答题", "分数加减", "略")
    assert _fp("数学", "解答题", "分数 加减", "略") == base
    assert _fp("数学", "解答题", "分数\n加减", "略") == base
    assert _fp("数学", "解答题", "分数\t加减", "略") == base
    assert _fp("数学", "解答题", "分数  \t 加减", "略") == base


# ── 全半角差异吸收 ─────────────────────────────────────────────────

def test_fullwidth_halfwidth_absorbed():
    base = _fp("数学", "计算题", "1+2", "3")
    assert _fp("数学", "计算题", "１＋２", "３") == base


# ── 标点差异吸收 ───────────────────────────────────────────────────

def test_trailing_period_absorbed():
    base = _fp("数学", "解答题", "第1题 求x的值", "5")
    assert _fp("数学", "解答题", "第1题 求x的值。", "5") == base


def test_trailing_semicolon_absorbed():
    base = _fp("数学", "解答题", "2x+3=7", "x=2")
    assert _fp("数学", "解答题", "2x+3=7;", "x=2") == base


# ── 实质变化 → 不同指纹 ────────────────────────────────────────────

def test_substantive_change_gives_different_fingerprint():
    assert _fp("数学", "解答题", "2x+3=7", "x=2") != _fp("数学", "解答题", "2x+3=8", "x=2")
    assert _fp("数学", "解答题", "分数加减", "略") != _fp("数学", "解答题", "分数乘除", "略")


# ── 空输入边界：不抛错、确定性、且各不相同 ─────────────────────────

def test_empty_inputs_no_crash_deterministic_and_distinct():
    fp_none = _fp(None, None, None, None)
    fp_empty = _fp("", "", "", "")
    fp_punct = _fp("。", "。", "。", "。")

    # 确定性
    assert fp_none == _fp(None, None, None, None)
    assert fp_empty == _fp("", "", "", "")
    assert fp_punct == _fp("。", "。", "。", "。")

    # 两两不同（缺席 None / 显式空串 / 全标点，语义各不相同）
    assert len({fp_none, fp_empty, fp_punct}) == 3

    # 均符合 fp_ + 64 hex 格式
    for fp in (fp_none, fp_empty, fp_punct):
        assert _FP_RE.fullmatch(fp)


# ── 输出格式：fp_ 前缀 + 恰好 64 位 hex ────────────────────────────

def test_output_format_fp_prefix_and_64_hex():
    fp = _fp("语文", "阅读理解", "文章的主旨是什么？", "热爱生活")
    assert fp.startswith("fp_")
    assert len(fp) == 3 + 64
    assert _FP_RE.fullmatch(fp)


# ── 字段边界：| 分隔不歧义 ─────────────────────────────────────────

def test_field_boundary_not_ambiguous():
    a = _fp("a", None, "b|c", None)
    b = _fp("a|b", None, "c", None)
    assert a != b
