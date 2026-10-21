# -*- coding: utf-8 -*-
"""C 项判分缓存测试：键稳定性 / human 最高优先 / guard 痕迹拒写 / hit_count /
选择题预查命中（命中以缓存为准，跳过比对）。

sqlite monkeypatch 范本：tests/test_users_dingtalk_userid_upgrade.py:84-96。
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.grading.answer_key_grading as ak
from app.grading import verdict_cache as vc
from app.grading.verdict_cache import (
    block_cache_key,
    cache_key,
    decision_status_from_result,
    lookup_block,
    lookup_many,
    store_blocks,
)
from app.models.verdict_cache import VerdictCache


def _blk(result="对", comment="评语", **extra):
    block = {
        "question_content": "1+1=?",
        "question_type": "选择题",
        "correct_answer": "2",
        "student_answer": "B",
        "result": result,
        "comment": comment,
    }
    block.update(extra)
    return block


# ── 键稳定性 / 红线（纯函数，无 DB）───────────────────────────────────


def test_cache_key_stable_and_sensitive():
    k1 = cache_key("数学", "选择题", "1+1=?", "2", "B")
    assert k1 == cache_key("数学", "选择题", "1+1=?", "2", "B")
    assert k1 != cache_key("数学", "选择题", "1+1=?", "2", "C")  # 异答异键
    assert k1 != cache_key("数学", "选择题", "2+2=?", "4", "B")  # 异题异键
    assert k1.startswith("fp_") and ":" in k1


def test_cache_key_empty_identity_returns_none():
    # 红线：question_content / correct_answer / student_answer 三缺一 → 不缓存不命中
    assert cache_key("数学", "选择题", "1+1=?", "2", "") is None
    assert cache_key("数学", "选择题", "1+1=?", "2", None) is None
    assert cache_key("数学", "选择题", "1+1=?", "2", "   ") is None
    assert cache_key("数学", "选择题", "1+1=?", "", "B") is None
    assert cache_key("数学", "选择题", "", "2", "B") is None
    assert cache_key(None, None, None, None, None) is None


def test_cache_key_list_student_answer_joins():
    # list 先 join：⛔ str(list) 会把 "['x=2']" 污染进键
    assert cache_key("数学", None, "q", "a", ["x=2"]) == cache_key("数学", None, "q", "a", "x=2")


def test_block_cache_key_field_fallbacks():
    blk = {"question": "题干", "expected_answer": "5", "student_answer": "5"}
    assert block_cache_key(blk, "数学") == cache_key("数学", None, "题干", "5", "5")
    assert block_cache_key({"question_content": "q"}, "数学") is None
    assert block_cache_key("not-a-dict", "数学") is None


def test_decision_status_mapping():
    assert decision_status_from_result("对") == "correct"
    assert decision_status_from_result("半对（0.6）") == "partial"
    assert decision_status_from_result("未作答") == "unanswered"
    assert decision_status_from_result("瞎写") is None


def test_cache_disabled_by_default(monkeypatch):
    monkeypatch.delenv("VERDICT_CACHE", raising=False)
    assert store_blocks([_blk()], "数学", "aliyun", "ai") == 0
    assert lookup_many(["fp_x:y"]) == {}
    assert lookup_block(_blk(), "数学") is None


# ── 读写（sqlite monkeypatch，VERDICT_CACHE=1）────────────────────────


@pytest.fixture()
def cache_env(monkeypatch):
    monkeypatch.setenv("VERDICT_CACHE", "1")
    engine = create_engine("sqlite:///:memory:")
    VerdictCache.__table__.create(bind=engine)
    monkeypatch.setattr(vc, "SessionLocal", sessionmaker(bind=engine))
    try:
        yield engine
    finally:
        engine.dispose()


def _rows(engine):
    session = sessionmaker(bind=engine)()
    try:
        return session.query(VerdictCache).all()
    finally:
        session.close()


def test_store_and_lookup_roundtrip(cache_env):
    assert store_blocks([_blk(result="对", comment="历史判定")], "数学", "aliyun", "ai") == 1
    hit = lookup_block(_blk(student_answer="B"), "数学")
    assert hit["result"] == "对" and hit["comment"] == "历史判定"
    assert lookup_block(_blk(student_answer="C"), "数学") is None


def test_human_overwrites_ai_and_ai_never_overwrites_human(cache_env):
    store_blocks([_blk(result="错", comment="ai判错")], "数学", "aliyun", "ai")
    assert _rows(cache_env)[0].source == "ai"

    assert store_blocks([_blk(result="对", comment="老师改判")], "数学", "aliyun", "human") == 1
    row = _rows(cache_env)[0]
    assert row.source == "human" and row.result == "对"

    # ai 永不覆盖 human 行
    assert store_blocks([_blk(result="错", comment="ai又判错")], "数学", "aliyun", "ai") == 0
    row = _rows(cache_env)[0]
    assert row.source == "human" and row.result == "对"

    # lookup 返回的就是人工终态（human 优先）
    assert lookup_block(_blk(), "数学")["result"] == "对"


def test_hit_count_increments(cache_env):
    store_blocks([_blk()], "数学", "aliyun", "ai")
    key = block_cache_key(_blk(), "数学")
    lookup_many([key])
    lookup_many([key])
    assert _rows(cache_env)[0].hit_count == 2


def test_guard_traced_ai_blocks_refused_human_allowed(cache_env):
    # 幻觉不入缓存（防全班放大）；人工推翻后是终态，正应进缓存飞轮
    suspicious = _blk(result="错", form_guard={"suspicious": True, "reason": "判错无理由"})
    downgraded = _blk(result="未作答", form_guard={"action": "downgraded", "was_result": "错"})
    ink = _blk(index=3, result="对", ink_evidence={"action": "flagged", "suspicious": True})

    assert store_blocks([suspicious, downgraded, ink], "数学", "aliyun", "ai") == 0
    assert _rows(cache_env) == []

    assert store_blocks([suspicious], "数学", "aliyun", "human") == 1
    assert _rows(cache_env)[0].source == "human"


# ── answer_key 选择题预查命中：命中以缓存为准，跳过比对 ────────────────


def test_answer_key_choice_cache_hit_skips_compare(cache_env, monkeypatch):
    monkeypatch.setattr(ak, "_ocr_choice_answers", lambda *a, **k: {})
    monkeypatch.setattr(ak, "_omr_choice_answer", lambda *a, **k: "A")

    # 预置缓存：历史人工判定「A 对」（与本卷标准答案 B 矛盾——命中必须以缓存为准）
    store_blocks(
        [
            {
                "question_content": "1+1=?",
                "question_type": "选择题",
                "correct_answer": "B",
                "student_answer": "A",
                "result": "对",
                "comment": "历史人工判定",
            }
        ],
        "数学",
        "answer_key",
        "human",
    )

    block = {
        "slot_id": "slot-1",
        "label": "1_1",
        "kind": "choice",
        "index": 1,
        "max_score": 1,
        "question_content": "1+1=?",
        "question_type": "选择题",
        "choice_options": ["A", "B", "C", "D"],
        "bbox": [0, 0, 20, 20],
    }
    decisions = ak.grade_paper_by_answer_key("ignored.png", [block], {"1_1": "B"}, subject="数学")

    # 比对被跳过：若跑 match_answers("A","B") 只会得 wrong；缓存命中 → correct
    assert decisions["slot-1"]["status"] == "correct"
    # human 行不被本次 ai 回写覆盖
    assert _rows(cache_env)[0].source == "human"


def test_answer_key_choice_cache_miss_runs_compare(cache_env, monkeypatch):
    monkeypatch.setattr(ak, "_ocr_choice_answers", lambda *a, **k: {})
    monkeypatch.setattr(ak, "_omr_choice_answer", lambda *a, **k: "A")

    block = {
        "slot_id": "slot-1",
        "label": "1_1",
        "kind": "choice",
        "index": 1,
        "max_score": 1,
        "question_content": "1+1=?",
        "question_type": "选择题",
        "choice_options": ["A", "B", "C", "D"],
        "bbox": [0, 0, 20, 20],
    }
    decisions = ak.grade_paper_by_answer_key("ignored.png", [block], {"1_1": "B"}, subject="数学")

    assert decisions["slot-1"]["status"] == "wrong"  # A vs B 比对判错
    # 新判分回写缓存（只写不查路径的同款出口）
    rows = _rows(cache_env)
    assert len(rows) == 1 and rows[0].source == "ai" and rows[0].result == "错"
