# -*- coding: utf-8 -*-
"""首页快速批改「举一反三」错题变式题 · 测试。

覆盖：
  1. question_type_of 题型推断（choice/judge/fill/short_answer）
  2. split_merged_options 剥选项还原 content（精确后缀 / 对不上原样 / 无选项）
  3. build_variant_items 装配（多题排序、内容/答案/解析/考点、跳过空题干）
  4. generate happy path（打桩 analyze/generate，items 齐全）
  5. VL 分析失败 → 文本兜底仍出题
  6. 生成失败 → 用错因上下文兜底再试一次
  7. 全失败 → items 空 + failed_keys 记账
  8. 无错题 → 空 items 不调 LLM
  9. 超上限截断（MAX_WRONG_QUESTIONS）

纯逻辑 + 打桩，不连 LLM/VL。
"""
from __future__ import annotations

from app.grading import home_variants as hv


def _blk(idx, result="错", comment="", score=None, transcription=""):
    b = {"index": idx, "sub_index": 1, "result": result, "comment": comment}
    if score is not None:
        b["score"] = score
    if transcription:
        b["transcription"] = transcription
    return b


# ── 纯函数 ──────────────────────────────────────────────────────
def test_question_type_of():
    assert hv.question_type_of("题干", ["a", "b"], "B") == "choice"
    assert hv.question_type_of("题干", [], "正确") == "judge"
    assert hv.question_type_of("填 ___ 空", [], "3") == "fill"
    assert hv.question_type_of("简答题", [], "略") == "short_answer"


def test_split_merged_options_exact_suffix():
    opts = ["A. 1", "B. 2"]
    q = "1+1=?" + "\n" + "\n".join(opts)
    assert hv.split_merged_options(q, opts) == "1+1=?"


def test_split_merged_options_mismatch_unchanged():
    q = "题干保留 A. 1"
    assert hv.split_merged_options(q, ["B. 9"]) == "题干保留 A. 1"


def test_split_merged_options_no_options():
    assert hv.split_merged_options("纯题干", []) == "纯题干"


def test_build_variant_items_assemble():
    groups = {
        "2": {"result": "错", "comment": "算错"},
        "10": {"result": "半对", "comment": ""},
    }
    analyses = {"2": {"knowledge_points": ["计算"]}}
    variants = {
        "2": [
            {"question": "新题\nA. 1", "options": ["A. 1"], "answer": "A", "analysis": "看个位", "kp_name": "计算", "source": "llm"},
            {"question": "第二变式", "options": [], "answer": "5", "analysis": ""},
        ],
        "10": [],
    }
    items = hv.build_variant_items(groups, analyses, variants)
    assert [it["from_key"] for it in items] == ["2", "2"]  # 题号序在前
    assert items[0]["content"] == "新题"
    assert items[0]["type"] == "choice"
    assert items[0]["answer"] == "A"
    assert items[0]["kp_name"] == "计算"
    assert items[0]["orig_result"] == "错"
    assert items[1]["type"] == "short_answer"


def test_build_variant_items_skips_blank_question():
    groups = {"1": {"result": "错"}}
    variants = {"1": [{"question": "", "answer": "x"}, {"question": "有效", "answer": "y"}]}
    items = hv.build_variant_items(groups, {}, variants)
    assert len(items) == 1
    assert items[0]["question"] == "有效"


# ── 主链路（打桩 analyze/generate）────────────────────────────────
def test_generate_happy_path():
    blocks = [_blk(1, "错", "漏进位"), _blk(2, "对"), _blk(3, "半对", "不完整")]
    seen = {}

    def fake_analyze(group, path):
        seen["analyzed"] = seen.get("analyzed", 0) + 1
        return {"question_text": "原题文本", "knowledge_points": ["考点A"]}

    def fake_generate(db, subject, kp_name, titles, limit, extra_topics=None):
        seen["kp"] = kp_name
        return [{"question": f"{kp_name}变式\nA. x", "options": ["A. x"], "answer": "A", "analysis": "解析", "source": "llm"}]

    out = hv.generate_home_variants(
        blocks, analyze_fn=fake_analyze, generate_fn=fake_generate
    )
    assert out["wrong_count"] == 2  # 对的题不进
    assert len(out["items"]) == 2
    assert out["failed_keys"] == []
    assert seen["analyzed"] == 2
    assert seen["kp"] in ("考点A",)
    assert out["items"][0]["from_key"] == "1"


def test_generate_analyze_fail_text_fallback():
    blocks = [_blk(1, "错", "题干没读到")]

    def fake_analyze(group, path):
        return {}

    def fake_generate(db, subject, kp_name, titles, limit, extra_topics=None):
        # 兜底路径：kp 用题干/评语片段，titles 有内容
        assert titles, "应有文本兜底的原题"
        return [{"question": "变式", "options": [], "answer": "42", "analysis": ""}]

    out = hv.generate_home_variants(
        blocks, analyze_fn=fake_analyze, generate_fn=fake_generate
    )
    assert len(out["items"]) == 1


def test_generate_fallback_with_error_context():
    # VL 读出了窄考点但出题为空 → 用错因上下文当考点兜底再试一次
    blocks = [_blk(1, "错", "")]
    calls = {"n": 0, "kps": []}

    def fake_analyze(group, path):
        return {"question_text": "原题X", "knowledge_points": ["窄考点"]}

    def fake_generate(db, subject, kp_name, titles, limit, extra_topics=None):
        calls["n"] += 1
        calls["kps"].append(kp_name)
        if calls["n"] == 1:
            return []  # 第一次空 → 换错因上下文兜底
        return [{"question": "兜底变式", "options": [], "answer": "1", "analysis": ""}]

    out = hv.generate_home_variants(
        blocks,
        analyze_fn=fake_analyze,
        generate_fn=fake_generate,
        annotations={"1": {"text": "错因：忘记进位"}},
    )
    assert len(out["items"]) == 1
    assert calls["n"] == 2
    assert calls["kps"][0] == "窄考点"
    assert calls["kps"][1] == "错因：忘记进位"


def test_generate_all_failed_reports_keys():
    blocks = [_blk(1, "错"), _blk(2, "半对")]

    def fake_analyze(group, path):
        return {}

    def fake_generate(db, subject, kp_name, titles, limit, extra_topics=None):
        return []

    out = hv.generate_home_variants(
        blocks, analyze_fn=fake_analyze, generate_fn=fake_generate
    )
    assert out["items"] == []
    assert sorted(out["failed_keys"]) == ["1", "2"]


def test_generate_no_wrong_questions_no_llm():
    blocks = [_blk(1, "对"), _blk(2, "未作答")]
    calls = {"n": 0}

    def fake_generate(*a, **k):
        calls["n"] += 1
        return []

    out = hv.generate_home_variants(blocks, generate_fn=fake_generate)
    assert out["items"] == []
    assert out["wrong_count"] == 0
    assert calls["n"] == 0


def test_generate_caps_wrong_questions():
    blocks = [_blk(i, "错") for i in range(1, 11)]

    def fake_analyze(group, path):
        return {}

    def fake_generate(db, subject, kp_name, titles, limit, extra_topics=None):
        return [{"question": f"变式{kp_name}", "options": [], "answer": "1", "analysis": ""}]

    out = hv.generate_home_variants(
        blocks, analyze_fn=fake_analyze, generate_fn=fake_generate
    )
    assert out["wrong_count"] == hv.MAX_WRONG_QUESTIONS
    assert len(out["items"]) == hv.MAX_WRONG_QUESTIONS
