"""R6b bandit 推荐框架单测（纯函数，不连 DB）。

覆盖：
- LinUCB 状态更新：有 reward 后 arm 权重/UCB 分数变化正确
- 推荐函数对空输入返回安全值（fallback）
- 无 reward → explore 确定性排序；有 reward → exploit 含 ucb_score
- context 特征向量形状与边界
"""
from __future__ import annotations

import random
from collections import Counter

import numpy as np

from app.services import bandit_recommender as br


def _mk_arm(kp_key: str, kp_name: str, wrong_count: int, conf: float = 0.8,
            methods: Counter | None = None, questions: list | None = None,
            difficulty: float = 3.0) -> br.BanditArm:
    methods = methods or Counter({"kp_includes": 1})
    questions = questions or [{
        "id": f"{kp_key}-q1",
        "question": f"{kp_name} 题目1",
        "answer": "A",
        "analysis": "略",
        "difficulty": difficulty,
    }]
    return br.BanditArm(
        kp_key=kp_key,
        kp_name=kp_name,
        subject="数学",
        wrong_count=wrong_count,
        avg_confidence=conf,
        match_signal=br._match_signal_from_methods(methods),
        error_labels=br._error_labels_from_methods(methods),
        questions=questions,
    )


def test_linucb_score_no_reward_positive():
    """无 reward（A=I, b=0）→ theta=0，score 仅探索项，为正且不报错。"""
    x = np.array([0.5, 0.7, 0.6, 1.0])
    A, b = np.eye(4), np.zeros(4)
    score = br._linucb_score(x, A, b, alpha=1.0)
    assert score > 0
    theta = np.linalg.solve(A, b)
    assert np.allclose(theta, 0)


def test_linucb_update_changes_theta_and_score():
    """有 reward=1 → theta 朝 x 方向倾斜，exploit 项分数提升，多次 update 单调上升。"""
    x = np.array([0.5, 0.7, 0.6, 1.0])
    A0, b0 = np.eye(4), np.zeros(4)
    s0 = br._linucb_score(x, A0, b0, alpha=0.0)  # 关闭探索，纯 exploit 项

    A, b = A0.copy(), b0.copy()
    scores = []
    for _ in range(5):
        A, b = br._linucb_update(A, b, x, 1.0)
        scores.append(br._linucb_score(x, A, b, alpha=0.0))
    assert scores[0] > s0
    assert scores[-1] > scores[0]
    theta = np.linalg.solve(A, b)
    assert float(theta @ x) > 0


def test_linucb_reward_ranks_high_reward_arm_first():
    """两 arm 特征相似，历史 reward 高的 arm UCB score 更高 → exploit 排序靠前。"""
    arm_a = _mk_arm("kpA", "kpA", wrong_count=3)
    arm_b = _mk_arm("kpB", "kpB", wrong_count=3)
    total = 6
    reward = 1.0

    x = br._context_vector(arm_a, total)
    # arm_a: 20 次 reward=1 历史；arm_b: 20 次 reward=0 历史（同曝光、不同回报）
    A_a, b_a = np.eye(4), np.zeros(4)
    for _ in range(20):
        A_a, b_a = br._linucb_update(A_a, b_a, x, 1.0)
    A_b, b_b = np.eye(4), np.zeros(4)
    for _ in range(20):
        A_b, b_b = br._linucb_update(A_b, b_b, x, 0.0)

    def load_state(key: str):
        return (A_a, b_a) if key == "kpA" else (A_b, b_b)

    # exploit 项（theta^T x）：高 reward 历史 arm 显著更高
    theta_a = np.linalg.solve(A_a + np.outer(x, x), b_a + reward * x)
    theta_b = np.linalg.solve(A_b + np.outer(x, x), b_b + reward * x)
    assert float(theta_a @ x) > float(theta_b @ x)

    ranked = br._linucb_rank(arms=[arm_a, arm_b], reward=reward, total_wrong=total,
                             alpha=1.0, load_state=load_state)
    assert ranked[0][1].kp_key == "kpA"
    assert ranked[0][0] > ranked[1][0]


def test_build_recommendations_empty_kp_returns_fallback():
    """空 kp 聚合 → fallback 空 items（安全值）。"""
    result = br.build_recommendations({}, "数学", limit=5, reward=None)
    assert result["mode"] == "fallback"
    assert result["items"] == []
    assert result["reason"]


def test_build_recommendations_no_reward_explore_deterministic():
    """无 reward → explore 确定性薄弱点推荐：同 seed 两次结果一致，错误最多 kp 排最前。"""
    kp_rows = {
        "四则运算": {"kp_name": "四则运算", "wrong_count": 5, "conf_sum": 4.0,
                     "methods": Counter({"question_includes": 5})},
        "单位换算": {"kp_name": "单位换算", "wrong_count": 3, "conf_sum": 2.4,
                     "methods": Counter({"kp_includes": 3})},
        "统计与概率": {"kp_name": "统计与概率", "wrong_count": 1, "conf_sum": 1.0,
                       "methods": Counter({"kp_exact": 1})},
    }

    def fetcher(kp_name, subj, lim):
        return [{
            "id": f"{kp_name}-1", "question": f"{kp_name} 变式题",
            "answer": "B", "analysis": "解析", "difficulty": 3,
        }]

    r1 = br.build_recommendations(kp_rows, "数学", limit=5, reward=None,
                                  rng=random.Random(42), question_fetcher=fetcher)
    r2 = br.build_recommendations(kp_rows, "数学", limit=5, reward=None,
                                  rng=random.Random(42), question_fetcher=fetcher)
    assert r1["mode"] == "explore"
    assert [i["question"]["id"] for i in r1["items"]] == [i["question"]["id"] for i in r2["items"]]
    assert r1["items"][0]["question"]["id"] == "四则运算-1"
    # 轮询填充：推荐覆盖全部 3 个薄弱 kp（而非单一 kp 霸榜）
    assert {i["reason"]["kp_name"] for i in r1["items"]} == {"四则运算", "单位换算", "统计与概率"}
    assert len(r1["items"]) == 3
    reason = r1["items"][0]["reason"]
    assert reason["mode"] == "explore"
    assert reason["kp_name"] == "四则运算"
    assert reason["error_count"] == 5
    assert reason["confidence"] == 0.8
    assert reason["error_types"]


def test_build_recommendations_exploit_includes_ucb():
    """有 reward → exploit 模式，每题 reason 含 ucb_score。"""
    kp_rows = {
        "四则运算": {"kp_name": "四则运算", "wrong_count": 5, "conf_sum": 4.0,
                     "methods": Counter({"question_includes": 5})},
        "单位换算": {"kp_name": "单位换算", "wrong_count": 3, "conf_sum": 2.4,
                     "methods": Counter({"kp_includes": 3})},
    }

    def fetcher(kp_name, subj, lim):
        return [{
            "id": f"{kp_name}-1", "question": "题", "answer": "A", "analysis": "析",
            "difficulty": 3,
        }]

    r = br.build_recommendations(kp_rows, "数学", limit=5, reward=0.8,
                                 rng=random.Random(1), question_fetcher=fetcher)
    assert r["mode"] == "exploit"
    for item in r["items"]:
        assert item["reason"]["mode"] == "exploit"
        assert "ucb_score" in item["reason"]
        assert isinstance(item["reason"]["ucb_score"], float)
    # exploit 返回更新后的 LinUCB A/b 状态（供落库跨请求收敛）
    assert r["arm_states"]
    for state in r["arm_states"].values():
        assert len(state["A"]) == 4 and len(state["b"]) == 4


def test_aggregate_kp_from_bridge_none_db_safe():
    """空输入（db=None）返回安全空值。"""
    assert br.aggregate_kp_from_bridge(None, "student_x", "数学") == {}
    assert br.read_reward_from_logs(None, "student_x", "数学") is None


def test_context_vector_shapes_and_bounds():
    arm = _mk_arm("k", "k", wrong_count=3, difficulty=5.0)
    x = br._context_vector(arm, total_wrong=10)
    assert x.shape == (4,)
    assert 0.0 <= x[0] <= 1.0
    assert 0.0 <= x[2] <= 1.0
    assert x[3] == 1.0
