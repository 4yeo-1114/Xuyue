# -*- coding: utf-8 -*-
"""AI 题源（不接题库时的替代出题链路）· 测试。

覆盖：
  1. compose_tiered_papers_ai：A/B/C 三份、meta.source=tiered-compose + engine=ai、
     层难度差异、payload 哨兵可落库（LLM 打桩，不发真请求）
  2. compose_tiered_papers_ai 参数校验（学科空 / 无分层 → ValueError）
  3. recommend_for_student_ai：指定知识点 / 薄弱 kp 两路，items 同 question/reason 形状
  4. default_requirements 配比：总数守恒
"""
from __future__ import annotations

import pytest

import app.services.ai_question_gen as ai_gen
import app.services.auto_variant as av_mod
from app.services.ai_question_gen import default_requirements
from app.services.bandit_recommender import recommend_for_student_ai
from app.services.paper_composer import (
    compose_tiered_papers_ai,
    unpack_paper_questions,
)


def _fake_questions(n=4, prefix="q"):
    """构造 n 道 ExamQuestion 形状的假 AI 题（无 difficulty，由层权重赋值）。"""
    out = []
    for i in range(n):
        out.append({
            "id": f"{prefix}_{i}",
            "type": "choice" if i % 2 == 0 else "short_answer",
            "stem": "",
            "content": f"第{i+1}题：1+1=?（{prefix}）",
            "options": ["1", "2", "3", "4"] if i % 2 == 0 else [],
            "score": 5,
            "answer": "2",
            "analysis": "加法",
            "knowledge_point": "加法",
            "is_ai": True,
        })
    return out


@pytest.fixture()
def stub_llm(monkeypatch):
    """打桩 LLM 出题 + LLM 配置；返回调用记录供断言。"""
    calls = []

    def fake_llm_generate_questions(db, **kwargs):
        calls.append(kwargs)
        n = sum(int(r.get("count") or 0) for r in (kwargs.get("requirements") or []))
        return _fake_questions(max(1, n) if n else 4)

    monkeypatch.setattr(
        ai_gen, "llm_generate_questions", fake_llm_generate_questions
    )
    monkeypatch.setattr(
        "app.utils.qwen_settings.get_llm_config",
        lambda db: ("http://llm.test", "key", "model"),
    )
    return calls


TIERS = {"A": ["s1", "s2"], "B": ["s3"], "C": ["s4"], "unassigned": 1}


def test_compose_tiered_papers_ai_three_papers(stub_llm):
    result = compose_tiered_papers_ai(
        None,
        class_id="C1",
        subject="数学",
        grade=None,
        topics=["加法", "减法"],
        requirements=[{"type": "choice", "count": 4, "score": 3}],
        count=4,
        round_id="r1",
        exam_folder="f1",
        tiers=TIERS,
    )
    papers = result["papers"]
    assert [p["tier"] for p in papers] == ["A", "B", "C"]
    assert result["tiers"] == {"A": 2, "B": 1, "C": 1, "unassigned": 1}
    assert len({p["meta"]["batch_id"] for p in papers}) == 1

    for p in papers:
        meta = p["meta"]
        assert meta["source"] == "tiered-compose"   # 结果清单过滤口径不变
        assert meta["engine"] == "ai"
        assert meta["class_id"] == "C1"
        assert meta["round_id"] == "r1"
        assert p["title"].startswith("数学")
        assert "分层卷" in p["title"]
        assert len(p["questions"]) == 4
        # payload = meta 哨兵 + 题目，可直接落 smart_exam_papers
        got_meta, got_qs = unpack_paper_questions(p["payload"])
        assert got_meta["tier"] == meta["tier"]
        assert len(got_qs) == 4
        for q in p["questions"]:
            assert q["type"] in ("choice", "short_answer")
            assert "stem" in q and "score" in q
            assert q["is_ai"] is True
            assert q["difficulty"] in (2, 3, 4)

    # 层间差异：A 难题不少于 C（权重 A hard=0.55 vs C hard=0.10）
    a_sum = papers[0]["difficulty"]
    c_sum = papers[2]["difficulty"]
    assert a_sum["hard"] >= c_sum["hard"] or a_sum["avg"] >= c_sum["avg"]

    # 三份卷各调一次 LLM，且都带上了指定知识点
    assert len(stub_llm) == 3
    for kw in stub_llm:
        assert kw["topics"] == ["加法", "减法"]
        assert kw["llm_cfg"] == ("http://llm.test", "key", "model")


def test_compose_tiered_papers_ai_validation():
    with pytest.raises(ValueError, match="学科"):
        compose_tiered_papers_ai(None, "C1", "", None, None, None, 5, None, None, TIERS)
    with pytest.raises(ValueError, match="tiers"):
        compose_tiered_papers_ai(None, "C1", "数学", None, None, None, 5, None, None, None)
    with pytest.raises(ValueError, match="分层"):
        compose_tiered_papers_ai(
            None, "C1", "数学", None, None, None, 5, None, None,
            {"A": [], "B": [], "C": [], "unassigned": 3},
        )


def test_recommend_for_student_ai_manual_topics(monkeypatch):
    """显式知识点：不查桥表，LLM 变式题 → mode=ai + reason 形状完整。"""
    def fake_variants(db, subject, kp_name, titles, limit, types=None, extra_topics=None):
        assert kp_name == "一次函数"
        return [
            {
                "id": f"llm-{kp_name}-0",
                "question": "一次函数变式1",
                "answer": "y=2x+1",
                "analysis": "待定系数法",
                "difficulty": None,
                "source": "llm",
            }
        ]

    monkeypatch.setattr(av_mod, "_llm_generate_variants", fake_variants)
    result = recommend_for_student_ai(
        None, "stu-1", "数学", limit=5, types=["choice"], topics=["一次函数"]
    )
    assert result["mode"] == "ai"
    assert result["student_id"] == "stu-1"
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["question"]["question"] == "一次函数变式1"
    assert item["question"]["answer"] == "y=2x+1"
    assert item["reason"]["kp_name"] == "一次函数"
    assert item["reason"]["mode"] == "ai"
    assert item["reason"]["error_count"] == 0  # 手动指定，无错题统计
    assert "指定的考点" in item["reason"]["reason_text"]


def test_recommend_for_student_ai_no_kp(monkeypatch):
    """无薄弱点（桥表空）→ 诚实空 items，不报错。"""
    monkeypatch.setattr(
        "app.services.bandit_recommender.aggregate_kp_from_bridge",
        lambda *a, **k: {},
    )
    result = recommend_for_student_ai(None, "stu-1", "数学", limit=5)
    assert result["mode"] == "ai"
    assert result["items"] == []
    assert "无薄弱" in result["reason"]


def test_default_requirements_total():
    for n in (1, 5, 10, 20):
        reqs = default_requirements(n)
        assert sum(int(r["count"]) for r in reqs) == n
        for r in reqs:
            assert r["type"] in ai_gen.VALID_TYPES
            assert r["count"] > 0
            assert r["score"] > 0
