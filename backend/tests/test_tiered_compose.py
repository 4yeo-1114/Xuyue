# -*- coding: utf-8 -*-
"""分层组卷（A/B/C 各一份）· 测试。

覆盖：
  1. 纯函数：tier_strategy / _band_plan_with_weights / kp_is_single / filter_pool_by_kp_mode
  2. 层间差异策略生效：假题库断言 A 层偏难+跨知识点、C 层偏易+单一知识点
  3. compose_tiered_papers：每层一份、标题含 A层/B层/C层、meta 记 tier/班级/轮次
  4. 无分层时 ValueError 明确报错
  5. pack/unpack 元数据哨兵 + 结果列表读取（unpack_paper_questions）

组卷服务依赖 PG 资产库 —— 用假 Question 对象 + monkeypatch 挡掉 DB，测确定性部分。
"""
from __future__ import annotations

import types

import pytest

from app.services.paper_composer import (
    TIER_BAND_WEIGHTS,
    TIER_KP_MODE,
    TIER_ZH,
    _band_plan_with_weights,
    compose_paper,
    compose_q_to_exam_q,
    compose_tiered_papers,
    difficulty_summary,
    filter_pool_by_kp_mode,
    kp_is_single,
    pack_paper_questions,
    tier_strategy,
    unpack_paper_questions,
)


# ── 假题库对象（duck-typing，够 compose_paper 用） ─────────────────


class FakeQ:
    def __init__(self, id, difficulty=3, knowledge_point="单知识点", question=None,
                 unique_key=None, question_type="选择题", options=None,
                 answer="A", analysis="", subject="数学", grade="小学",
                 quality_flag="ok"):
        self.id = id
        self.difficulty = difficulty
        self.knowledge_point = knowledge_point
        self.question = question if question is not None else f"题目{id}题面内容足够长避免相似去重误伤_{id}"
        self.unique_key = unique_key or f"uk-{id}"
        self.question_type = question_type
        self.options = options if options is not None else ["A", "B", "C", "D"]
        self.answer = answer
        self.analysis = analysis
        self.subject = subject
        self.grade = grade
        self.quality_flag = quality_flag


def make_pool():
    """混合池：易/中/难 × 单一/跨知识点，各若干（单一足够填满 C 层 10 题）。"""
    pool = []
    # 单一知识点（12 道，覆盖易/中/难）
    for i, d in enumerate([1, 1, 2, 2, 2, 3, 3, 3, 3, 4, 4, 5]):
        pool.append(FakeQ(f"s{i}", difficulty=d, knowledge_point="一次函数"))
    # 跨知识点综合（8 道）
    for i, d in enumerate([2, 3, 3, 4, 4, 5, 5, 5]):
        pool.append(FakeQ(f"m{i}", difficulty=d, knowledge_point="一次函数/二次函数"))
    return pool


# ── 纯函数 ───────────────────────────────────────────────────────


def test_tier_strategy_profiles():
    """A/B/C 策略：难度权重递减 hard、知识点粒度 multi/None/single。"""
    a = tier_strategy("A")
    b = tier_strategy("B")
    c = tier_strategy("C")
    assert a["band_weights"]["hard"] > b["band_weights"]["hard"] > c["band_weights"]["hard"]
    assert c["band_weights"]["easy"] > b["band_weights"]["easy"] > a["band_weights"]["easy"]
    assert a["kp_mode"] == "multi"
    assert b["kp_mode"] is None
    assert c["kp_mode"] == "single"
    assert a["difficulty_pref"] == "hard"
    assert c["difficulty_pref"] == "easy"
    # 未知层回落 B
    assert tier_strategy("Z")["tier"] == "B"
    assert tier_strategy(None)["tier"] == "B"


def test_band_plan_with_weights_distribution():
    """权重 → 难度带序列：A 层 hard 占多数，C 层 easy 占多数。"""
    a_plan = _band_plan_with_weights(10, TIER_BAND_WEIGHTS["A"])
    c_plan = _band_plan_with_weights(10, TIER_BAND_WEIGHTS["C"])
    assert len(a_plan) == 10 and len(c_plan) == 10
    assert a_plan.count("hard") >= 5
    assert c_plan.count("easy") >= 5
    assert a_plan.count("hard") > a_plan.count("easy")
    assert c_plan.count("easy") > c_plan.count("hard")
    # 空/零
    assert _band_plan_with_weights(0, {"easy": 1, "medium": 0, "hard": 0}) == []


def test_kp_is_single_and_filter():
    assert kp_is_single("一次函数") is True
    assert kp_is_single("一次函数/二次函数") is False
    assert kp_is_single(None) is True
    assert kp_is_single("") is True

    pool = make_pool()
    single = filter_pool_by_kp_mode(pool, "single")
    multi = filter_pool_by_kp_mode(pool, "multi")
    assert all(kp_is_single(q.knowledge_point) for q in single)
    assert all(not kp_is_single(q.knowledge_point) for q in multi)
    assert len(single) < len(pool) and len(multi) < len(pool)
    # None 不过滤
    assert filter_pool_by_kp_mode(pool, None) == pool
    # 过滤空时回退原池（保底可出卷）
    only_multi = [q for q in pool if not kp_is_single(q.knowledge_point)]
    assert filter_pool_by_kp_mode(only_multi, "single") == only_multi


def test_difficulty_summary():
    qs = [
        {"difficulty": 1},
        {"difficulty": 2},
        {"difficulty": 3},
        {"difficulty": 5},
        {"difficulty": None},  # 视为 3
    ]
    s = difficulty_summary(qs)
    assert s["easy"] == 2
    assert s["medium"] == 2
    assert s["hard"] == 1
    assert s["count"] == 5
    assert difficulty_summary([])["count"] == 0


# ── compose_paper 层间差异（假题库 + monkeypatch） ─────────────────


@pytest.fixture()
def fake_asset_db(monkeypatch):
    """挡掉 DB：_load_gold_difficulty / _fetch_candidates / _random_fallback / kp_raws。"""
    pool = make_pool()

    monkeypatch.setattr(
        "app.services.paper_composer._load_gold_difficulty", lambda db: {}
    )
    monkeypatch.setattr(
        "app.services.paper_composer._fetch_candidates",
        lambda db, subject, grade, wk, kp_raws, limit=200: list(pool),
    )

    def _fake_random(db, subject, grade, count, gold, used_keys, used_texts):
        """随机兜底也从假池取（跳过已用），避免真实 DB 查询。"""
        from app.services.paper_composer import (
            _question_to_dict,
            filter_pool_by_kp_mode,
        )
        picked = []
        for q in pool:
            if len(picked) >= count:
                break
            if q.unique_key in used_keys:
                continue
            picked.append(
                _question_to_dict(q, "", "", int(q.difficulty or 3), "question")
            )
            used_keys.add(q.unique_key)
        return picked

    monkeypatch.setattr(
        "app.services.paper_composer._random_fallback", _fake_random
    )

    class _Q:
        def filter(self, *a, **k):
            return self

        def distinct(self):
            return self

        def all(self):
            return []

    class _DB:
        def query(self, *a, **k):
            return _Q()

    return _DB()


def test_compose_paper_tier_difficulty_differs(fake_asset_db):
    """A 层 hard 多、C 层 easy 多；C 层全单一知识点、A 层含跨知识点。"""
    a = compose_paper(
        fake_asset_db, "数学", None, [{"name": "一次函数", "count": 10}], 10,
        "hard", band_weights=TIER_BAND_WEIGHTS["A"], kp_mode=TIER_KP_MODE["A"],
    )
    c = compose_paper(
        fake_asset_db, "数学", None, [{"name": "一次函数", "count": 10}], 10,
        "easy", band_weights=TIER_BAND_WEIGHTS["C"], kp_mode=TIER_KP_MODE["C"],
    )
    a_q, c_q = a["questions"], c["questions"]
    assert len(a_q) == 10 and len(c_q) == 10

    a_hard = sum(1 for q in a_q if (q.get("difficulty") or 3) >= 4)
    c_easy = sum(1 for q in c_q if (q.get("difficulty") or 3) <= 2)
    a_avg = sum(q.get("difficulty") or 3 for q in a_q) / len(a_q)
    c_avg = sum(q.get("difficulty") or 3 for q in c_q) / len(c_q)
    assert a_hard >= 4, f"A 层应偏难，实际 hard={a_hard}"
    assert c_easy >= 4, f"C 层应偏易，实际 easy={c_easy}"
    # 均值口径更稳：A 层平均难度显著高于 C 层
    assert a_avg > c_avg, f"A avg={a_avg} 应 > C avg={c_avg}"

    # C 层单一知识点
    assert all(kp_is_single(q.get("knowledge_point")) for q in c_q)
    # A 层有跨知识点（池子里 multi 有 8 道，权重 hard 为主会抽到）
    assert any(not kp_is_single(q.get("knowledge_point")) for q in a_q)

    # meta 记录策略
    assert a["meta"]["band_weights"]["hard"] > c["meta"]["band_weights"]["hard"]
    assert c["meta"]["kp_mode"] == "single"


# ── compose_tiered_papers ─────────────────────────────────────────


def test_compose_tiered_three_papers(fake_asset_db):
    """每层一份、标题标注、meta 记 tier/班级/轮次、payload 可落库。"""
    tiers = {"A": ["s1", "s2"], "B": ["s3"], "C": ["s4"], "unassigned": 1}
    result = compose_tiered_papers(
        fake_asset_db,
        class_id="C1",
        subject="数学",
        grade=None,
        weak_kps=[{"name": "一次函数", "count": 6}],
        count=6,
        round_id="round-9",
        exam_folder="folder-x",
        tiers=tiers,
    )
    papers = result["papers"]
    assert [p["tier"] for p in papers] == ["A", "B", "C"]
    assert result["tiers"] == {"A": 2, "B": 1, "C": 1, "unassigned": 1}

    for p in papers:
        t = p["tier"]
        assert TIER_ZH[t] in p["title"]
        assert p["title"].startswith("数学")
        assert len(p["questions"]) == 6
        meta = p["meta"]
        assert meta["tier"] == t
        assert meta["class_id"] == "C1"
        assert meta["round_id"] == "round-9"
        assert meta["exam_folder"] == "folder-x"
        assert meta["source"] == "tiered-compose"
        assert meta["batch_id"]
        # payload 含 meta 哨兵 + 题目
        assert len(p["payload"]) == 7
        assert "__tiered_meta__" in p["payload"][0]
        # ExamQuestion 形状可进试卷库
        for q in p["questions"]:
            assert "type" in q and "stem" in q and "score" in q

    # 同一 batch_id
    assert len({p["meta"]["batch_id"] for p in papers}) == 1

    # 层间难度差异仍生效
    a_sum = papers[0]["difficulty"]
    c_sum = papers[2]["difficulty"]
    assert a_sum["hard"] >= c_sum["hard"] or a_sum["avg"] >= c_sum["avg"]


def test_compose_tiered_no_tiers_raises():
    with pytest.raises(ValueError, match="分层"):
        compose_tiered_papers(
            None, "C1", "数学", None, None, 5, None, None,
            {"A": [], "B": [], "C": [], "unassigned": 3},
        )
    with pytest.raises(ValueError, match="tiers"):
        compose_tiered_papers(None, "C1", "数学", None, None, 5, None, None, None)
    with pytest.raises(ValueError, match="学科"):
        compose_tiered_papers(None, "C1", "", None, None, 5, None, None, {"A": ["x"]})


def test_pack_unpack_meta_sentinel():
    exam_qs = [{"id": "q1", "type": "choice", "stem": "s", "content": "", "options": [], "score": 5}]
    meta = {"tier": "A", "class_id": "C1", "source": "tiered-compose"}
    payload = pack_paper_questions(exam_qs, meta)
    assert len(payload) == 2
    got_meta, got_qs = unpack_paper_questions(payload)
    assert got_meta["tier"] == "A"
    assert got_qs == exam_qs
    # 无哨兵 / 非 list
    assert unpack_paper_questions(exam_qs) == ({}, exam_qs)
    assert unpack_paper_questions(None) == ({}, [])
    assert unpack_paper_questions({"nope": 1}) == ({}, [])


def test_compose_q_to_exam_q_mapping():
    q = {
        "id": "x1",
        "question_type": "选择题",
        "question": "1+1=?",
        "options": ["1", "2"],
        "answer": "2",
        "analysis": "简单加法",
        "knowledge_point": "加法",
        "difficulty": 1,
    }
    eq = compose_q_to_exam_q(q)
    assert eq["type"] == "choice"
    assert eq["stem"] == "1+1=?"
    assert eq["score"] == 5
    assert eq["answer"] == "2"
    assert eq["difficulty"] == 1
    # 作文 30 分
    eq2 = compose_q_to_exam_q({"question_type": "作文", "question": "写一篇"})
    assert eq2["type"] == "essay" and eq2["score"] == 30
    # 未知题型回落 short_answer
    eq3 = compose_q_to_exam_q({"question_type": "神秘题", "question": "x"})
    assert eq3["type"] == "short_answer"
