# -*- coding: utf-8 -*-
"""R6b contextual bandit 错题推荐框架（LinUCB 纯 numpy + 降级链）。

数据流（双库共存融合）：
  学生(MySQL student_wrong_questions) → R6a 桥表 wrong_question_kp_bridge(MySQL)
    → 薄弱知识点（confidence>=0.8 过滤，剔除 kp_keyword 弱信号）
    → PG 资产库 questions 同 kp 变式题（knowledge_point 文本匹配 + quality_flag 过滤）
    → LinUCB 排序（context 特征 = 错因分布 + 错误次数 + 难度层级）
    → 推荐列表 + 每题推荐理由

降级链（核心契约，任何一环都不裸 500）：
  1. 有 reward（response_logs 该生该科答对率非空）→ mode=exploit，LinUCB 按 UCB score 排序
  2. 无 reward（当前 response_logs=0 行）→ mode=explore，
     确定性薄弱点推荐（按错题频次排同 kp 变式题，seeded rng 轻微扰动可复现）
  3. 学生无错题 / 无薄弱知识点 / PG 无匹配变式题 → mode=fallback，返回空 items + reason（200，不报错）
  4. PG 资产库不可用 → 抛 AssetDBUnavailable，由路由层转 503（契约同 school_assets）

算法：LinUCB（contextual bandit）。arm = 该生薄弱知识点；context 特征向量 x = [错误次数占比,
匹配信号强度, 归一化难度, 1.0]。每 arm 学习 theta_a = A_a^{-1} b_a，
UCB score = theta_a^T x + alpha * sqrt(x^T A_a^{-1} x)。
无 reward 时 A=I、b=0 → theta=0，score 仅由探索项决定 → 自然降级为探索。
有 reward 后（response_logs 有数据）每 arm 状态随 reward 更新，score 向高回报 arm 倾斜。
arm 状态持久化到 bandit_arm_stats（MySQL），跨请求收敛。
"""
from __future__ import annotations

import logging
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── 配置常量 ─────────────────────────────────────────────────────
MIN_CONFIDENCE = 0.8          # 桥表 confidence 下限（剔除 kp_keyword 弱信号，该档 conf=0.6）
ALPHA = 1.0                   # LinUCB 探索系数
CONTEXT_DIM = 4               # context 特征维度
MAX_ARMS = 12                 # 最多纳入排序的薄弱知识点数
DEFAULT_DIFFICULTY = 3.0      # 难度缺失兜底（PG difficulty 1-5）
BATCH_SIZE = 500              # 错题 id IN 查询分块大小
_DIFF_NORM_DENOM = 4.0        # difficulty 归一化分母（1-5 → 0-1）

# match_method → 错因（匹配信号强度 + 错因文案），用于 context 特征与推荐理由
_MATCH_SIGNAL: Dict[str, float] = {
    "question_exact": 1.0,
    "kp_exact": 0.9,
    "question_includes": 0.8,
    "kp_includes": 0.7,
    "kp_keyword": 0.4,
}
_MATCH_ERROR_LABEL: Dict[str, str] = {
    "question_exact": "题干精确匹配",
    "question_includes": "题干包含匹配",
    "kp_exact": "知识点精确匹配",
    "kp_includes": "知识点包含匹配",
    "kp_keyword": "知识点关键词匹配",
}
_FALLBACK_SIGNAL = 0.5


class AssetDBUnavailable(RuntimeError):
    """PG 资产库不可用（未配置/不可达/查询异常）。路由层捕获转 503。"""


@dataclass
class BanditArm:
    """一个薄弱知识点 arm：聚合统计 + PG 候选变式题。"""
    kp_key: str              # 聚合键（kp_id 或 kp_name）
    kp_name: str
    subject: str
    wrong_count: int         # 该 kp 对应错题条数
    avg_confidence: float    # 桥表 confidence 均值
    match_signal: float      # 匹配信号强度 0-1
    error_labels: List[str]  # 错因文案（由 match_method 分布映射）
    questions: List[dict]    # PG 候选变式题（id/question/answer/analysis/difficulty/...）
    difficulty: float = DEFAULT_DIFFICULTY  # 候选变式题平均难度（context 特征用）
    A: Optional[np.ndarray] = field(default=None, repr=False)
    b: Optional[np.ndarray] = field(default=None, repr=False)


# ── LinUCB 纯函数（可单测，不依赖 DB） ───────────────────────────
def _linucb_update(A: np.ndarray, b: np.ndarray, x: np.ndarray, reward: float):
    """LinUCB 增量更新：A <- A + x x^T；b <- b + reward * x。"""
    A2 = A + np.outer(x, x)
    b2 = b + reward * x
    return A2, b2


def _linucb_score(x: np.ndarray, A: np.ndarray, b: np.ndarray, alpha: float = ALPHA) -> float:
    """UCB score = theta^T x + alpha * sqrt(x^T A^-1 x)。数值稳定化（clamp 非负）。"""
    theta = np.linalg.solve(A, b)
    try:
        A_inv = np.linalg.inv(A)
        explore = max(0.0, float(x @ A_inv @ x))
    except np.linalg.LinAlgError:
        explore = 0.0
    return float(theta @ x) + alpha * float(np.sqrt(explore))


def _context_vector(arm: BanditArm, total_wrong: int) -> np.ndarray:
    """context 特征向量：[错误次数占比, 匹配信号强度, 归一化难度, 1.0]。"""
    err_rate = arm.wrong_count / total_wrong if total_wrong else 0.0
    diff_norm = max(0.0, min(1.0, (arm.difficulty - 1.0) / _DIFF_NORM_DENOM))
    return np.array([err_rate, arm.match_signal, diff_norm, 1.0], dtype=float)


def _match_signal_from_methods(methods: Counter) -> float:
    """按 match_method 频次加权平均信号强度。"""
    if not methods:
        return _FALLBACK_SIGNAL
    total = sum(methods.values())
    score = 0.0
    for method, cnt in methods.items():
        score += _MATCH_SIGNAL.get(method or "", _FALLBACK_SIGNAL) * cnt
    return score / total if total else _FALLBACK_SIGNAL


def _error_labels_from_methods(methods: Counter) -> List[str]:
    """match_method 分布 → 去重保序错因文案（按频次降序）。"""
    ordered = methods.most_common()
    labels = []
    for method, _cnt in ordered:
        label = _MATCH_ERROR_LABEL.get(method or "")
        if label and label not in labels:
            labels.append(label)
    return labels or ["未知匹配方式"]


# ── 纯排序逻辑（可单测） ────────────────────────────────────────
def _explore_rank(arms: List[BanditArm], total_wrong: int, rng: Optional[random.Random] = None):
    """确定性薄弱点推荐：按错误频次降序，同频次 seeded 扰动保可复现。"""
    rng = rng or random.Random()
    scored = [(arm.wrong_count + rng.uniform(0, 0.05), arm) for arm in arms]
    scored.sort(key=lambda t: -t[0])
    return [arm for _score, arm in scored]


def _linucb_rank(
    arms: List[BanditArm],
    reward: float,
    total_wrong: int,
    alpha: float = ALPHA,
    load_state: Optional[Callable[[str], Optional[tuple]]] = None,
):
    """exploit：按 UCB score 降序。load_state(kp_key) -> (A, b) | None。"""
    dim = CONTEXT_DIM
    scored: List[tuple] = []
    for arm in arms:
        x = _context_vector(arm, total_wrong)
        state = load_state(arm.kp_key) if load_state else None
        A = state[0] if state else np.eye(dim)
        b = state[1] if state else np.zeros(dim)
        # 用本次 reward 更新（reward 为已观察到的该生同科答对率）
        A2, b2 = _linucb_update(A, b, x, reward)
        score = _linucb_score(x, A2, b2, alpha)
        scored.append((score, arm, x, A2, b2))
    scored.sort(key=lambda t: -t[0])
    return scored  # [(score, arm, x, A, b)] 按 score 降序


def _assemble_recommendations(scored_arms: List[BanditArm], limit: int, mode: str, ucb_map: Optional[dict] = None) -> List[dict]:
    """arm 排序结果 → 推荐题列表（轮询去重填充），每题附推荐理由。

    轮询（round-robin）：每轮从每个 arm 取 1 道未用题，保证推荐覆盖多个薄弱知识点，
    而非单个 kp 霸榜。ucb_map: {kp_key: ucb_score}，仅 exploit 模式传入，落进每题 reason。
    """
    items: List[dict] = []
    used: set = set()
    if not scored_arms:
        return items

    per_arm_cursor = [0] * len(scored_arms)  # 每个 arm 已消费的题游标
    while len(items) < limit:
        any_taken = False
        for i, arm in enumerate(scored_arms):
            if len(items) >= limit:
                break
            idx = per_arm_cursor[i]
            while idx < len(arm.questions):
                q = arm.questions[idx]
                idx += 1
                per_arm_cursor[i] = idx
                qid = q.get("id")
                if qid in used:
                    continue
                used.add(qid)
                err_part = "、".join(arm.error_labels) if arm.error_labels else "知识点匹配"
                mode_explain = {
                    "explore": "当前处于探索阶段，优先巩固错误最多的薄弱知识点",
                    "exploit": "已结合历史作答反馈，优先推荐掌握度更低的同类题",
                    "fallback": "按薄弱知识点兜底推荐",
                }.get(mode, "")
                reason = {
                    "kp_name": arm.kp_name,
                    "error_types": arm.error_labels,
                    "error_count": arm.wrong_count,
                    "confidence": round(arm.avg_confidence, 2),
                    "mode": mode,
                    "reason_text": (
                        f"「{arm.kp_name}」累计错 {arm.wrong_count} 次"
                        f"（错因：{err_part}，匹配置信度 {round(arm.avg_confidence * 100)}%），"
                        f"判定为薄弱知识点。{mode_explain}，故推荐该知识点的变式题。"
                    ),
                }
                if ucb_map and arm.kp_key in ucb_map:
                    reason["ucb_score"] = round(ucb_map[arm.kp_key], 4)
                items.append({
                    "question": {
                        "id": qid,
                        "question": q.get("question", ""),
                        "answer": q.get("answer", ""),
                        "analysis": q.get("analysis", ""),
                        "difficulty": q.get("difficulty", DEFAULT_DIFFICULTY),
                    },
                    "reason": reason,
                })
                any_taken = True
                break
        if not any_taken:
            break
    return items


def build_recommendations(
    kp_rows: Dict[str, dict],
    subject: str,
    limit: int = 5,
    reward: Optional[float] = None,
    rng: Optional[random.Random] = None,
    question_fetcher: Optional[Callable[[str, str, int], List[dict]]] = None,
    load_state: Optional[Callable[[str], Optional[tuple]]] = None,
) -> dict:
    """纯逻辑推荐（无 DB 副作用）：从 kp 聚合 → 取变式题 → 打分排序 → 组装推荐。

    kp_rows: {kp_key: {wrong_count, conf_sum, methods: Counter, kp_id}}
    question_fetcher(kp_name, subject, limit) -> 变式题 dict 列表（PG 查询由调用方注入）
    load_state(kp_key) -> (A, b) | None（持久化状态，exploit 时用）
    返回统一响应 shape（mode/items/reason），任何空输入返回安全 fallback。
    """
    if not kp_rows:
        return {"mode": "fallback", "reason": "无薄弱知识点", "items": []}

    # 组装 arms
    arms: List[BanditArm] = []
    for kp_key, agg in kp_rows.items():
        kp_name = agg.get("kp_name") or kp_key
        questions = question_fetcher(kp_name, subject, limit) if question_fetcher else []
        if not questions:
            continue
        methods: Counter = agg.get("methods") or Counter()
        difficulty = float(np.mean([float(q.get("difficulty") or DEFAULT_DIFFICULTY) for q in questions]))
        arms.append(BanditArm(
            kp_key=kp_key,
            kp_name=kp_name,
            subject=subject,
            wrong_count=int(agg.get("wrong_count", 0)),
            avg_confidence=(agg.get("conf_sum", 0.0) / max(1, agg.get("wrong_count", 0))),
            match_signal=_match_signal_from_methods(methods),
            error_labels=_error_labels_from_methods(methods),
            questions=questions,
            difficulty=difficulty,
            A=None,
            b=None,
        ))
    if not arms:
        return {"mode": "fallback", "reason": "PG 无匹配变式题", "items": []}

    total_wrong = sum(a.wrong_count for a in arms)
    arm_states: Dict[str, dict] = {}
    if reward is not None:
        mode = "exploit"
        ranked = _linucb_rank(arms, reward, total_wrong, ALPHA, load_state=load_state)
        # ranked 元素含 (score, arm, x, A, b)，组装需要 arm 顺序
        sorted_arms = [arm for _s, arm, _x, _A, _b in ranked]
        ucb_map = {arm.kp_key: float(_s) for _s, arm, _x, _A, _b in ranked}
        # 更新后的 LinUCB 状态（A/b）返回给调用方落 bandit_arm_stats，跨请求收敛
        arm_states = {arm.kp_key: {"A": _A.tolist(), "b": _b.tolist()} for _s, arm, _x, _A, _b in ranked}
    else:
        mode = "explore"
        sorted_arms = _explore_rank(arms, total_wrong, rng)
        ucb_map = {}

    items = _assemble_recommendations(sorted_arms, limit, mode, ucb_map=ucb_map)
    return {
        "mode": mode,
        "reason": "",
        "items": items,
        "arm_count": len(sorted_arms),
        "arm_states": arm_states,
    }


# ── DB 数据层（MySQL 主库 + PG 资产库） ─────────────────────────
def aggregate_kp_from_bridge(db, student_id: str, subject: str, min_conf: float = MIN_CONFIDENCE) -> Dict[str, dict]:
    """学生错题 → R6a 桥表 → 薄弱知识点聚合。

    返回 {kp_key: {kp_name, wrong_count, conf_sum, methods: Counter, kp_id}}。
    学生不存在 / 无错题 / 无桥接命中 → 空 dict（安全）。
    """
    from app.models.student import Student
    from app.models.student_analysis import StudentWrongQuestion
    from app.models.wrong_question_kp_bridge import WrongQuestionKpBridge

    if db is None:
        return {}
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        return {}

    wq_ids = [
        r[0] for r in db.query(StudentWrongQuestion.id).filter(
            StudentWrongQuestion.student_name == student.name,
            StudentWrongQuestion.class_id == student.class_id,
            StudentWrongQuestion.subject == subject,
        ).all()
    ]
    if not wq_ids:
        return {}

    bridges = []
    for i in range(0, len(wq_ids), BATCH_SIZE):
        chunk = wq_ids[i:i + BATCH_SIZE]
        bridges += db.query(WrongQuestionKpBridge).filter(
            WrongQuestionKpBridge.wrong_question_id.in_(chunk),
            WrongQuestionKpBridge.confidence >= min_conf,
        ).all()
    if not bridges:
        return {}

    agg: Dict[str, dict] = {}
    for b in bridges:
        key = b.kp_id or (b.kp_name or "未知")
        a = agg.setdefault(key, {
            "kp_name": b.kp_name or key,
            "kp_id": b.kp_id,
            "wrong_count": 0,
            "conf_sum": 0.0,
            "methods": Counter(),
        })
        a["wrong_count"] += 1
        a["conf_sum"] += float(b.confidence or 0.0)
        a["methods"][b.match_method or ""] += 1
    return agg


def read_reward_from_logs(db, student_id: str, subject: str) -> Optional[float]:
    """reward = response_logs 该生该科答对率；无记录返回 None（→ explore）。

    当前 response_logs 0 行 → 恒为 None，走探索/降级；有数据后自动切 exploit。
    """
    from app.models.response_log import ResponseLog
    from sqlalchemy import func

    if db is None:
        return None
    total = db.query(func.count(ResponseLog.id)).filter(
        ResponseLog.student_id == student_id,
        ResponseLog.subject == subject,
        ResponseLog.is_correct.isnot(None),
    ).scalar()
    if not total:
        return None
    correct = db.query(func.count(ResponseLog.id)).filter(
        ResponseLog.student_id == student_id,
        ResponseLog.subject == subject,
        ResponseLog.is_correct.is_(True),
    ).scalar()
    return float(correct) / float(total)


def fetch_variant_questions(asset_db, subject: str, kp_name: str, limit: int) -> List[dict]:
    """PG 资产库取同 kp 变式题：subject + knowledge_point 文本匹配 + quality 过滤。

    前缀匹配优先（走索引），无结果 contains 兜底（'语文阅读理解' 等复合标签）。
    PG 不可达/未配置 → 抛 AssetDBUnavailable（路由层转 503）。
    """
    if asset_db is None:
        raise AssetDBUnavailable("assets db not configured")
    import app.assets.models as am
    try:
        rows = (
            asset_db.query(am.Question)
            .filter(
                am.Question.subject == subject,
                am.Question.knowledge_point.like(f"{kp_name}%"),
                (am.Question.quality_flag.in_(["ok", "filled"])) | am.Question.quality_flag.is_(None),
            )
            .limit(limit)
            .all()
        )
        if not rows:
            rows = (
                asset_db.query(am.Question)
                .filter(
                    am.Question.subject == subject,
                    am.Question.knowledge_point.like(f"%{kp_name}%"),
                    (am.Question.quality_flag.in_(["ok", "filled"])) | am.Question.quality_flag.is_(None),
                )
                .limit(limit)
                .all()
            )
    except AssetDBUnavailable:
        raise
    except Exception as exc:
        logger.warning("bandit: assets db query failed: %s", exc)
        raise AssetDBUnavailable("assets db unreachable") from exc
    return [_question_to_dict(q) for q in rows]


def _question_to_dict(q) -> dict:
    return {
        "id": q.id,
        "subject": q.subject,
        "grade": q.grade,
        "question": q.question,
        "options": q.options,
        "answer": q.answer,
        "analysis": q.analysis,
        "knowledge_point": q.knowledge_point,
        "difficulty": q.difficulty,
        "quality_flag": q.quality_flag,
    }


# ── 状态持久化（bandit_arm_stats，非关键路径） ──────────────────
def _load_arm_state(db, student_id: str, subject: str):
    """返回 loader(kp_key) -> (A, b) | None。写库异常静默降级为 None。"""
    if db is None:
        return None

    def loader(kp_key: str):
        try:
            from app.models.bandit_arm_stats import BanditArmStats
            row = db.query(BanditArmStats).filter(
                BanditArmStats.student_id == student_id,
                BanditArmStats.subject == subject,
                BanditArmStats.kp_key == kp_key,
            ).first()
            if row and row.a_json:
                A = np.array(row.a_json, dtype=float)
                b = np.array(row.b_json or [0.0] * CONTEXT_DIM, dtype=float)
                if A.shape == (CONTEXT_DIM, CONTEXT_DIM):
                    return A, b
        except Exception:
            logger.warning("bandit: load arm state failed", exc_info=True)
        return None
    return loader


def persist_recommendation(
    db,
    student_id: str,
    subject: str,
    result: dict,
    arm_states: Optional[dict] = None,
) -> None:
    """推荐后落 bandit_arm_stats（曝光 +1；exploit 时同步 ucb_score 与 LinUCB A/b 状态）。

    arm_states: {kp_key: {"A": [[...]], "b": [...]}}，exploit 时由 build_recommendations 返回，
    写回 a_json/b_json 实现跨请求学习收敛。写库失败仅告警，绝不阻断推荐返回。
    """
    if db is None:
        return
    try:
        from app.models.bandit_arm_stats import BanditArmStats
        mode = result.get("mode") or "fallback"
        arm_states = arm_states or {}
        seen: set = set()
        for item in result.get("items", []):
            reason = item.get("reason", {}) or {}
            kp_name = reason.get("kp_name", "")
            key = kp_name or "unknown"
            if key in seen:
                continue  # 同一 kp 的多道题只记一次统计，避免唯一键冲突
            seen.add(key)
            row = db.query(BanditArmStats).filter(
                BanditArmStats.student_id == student_id,
                BanditArmStats.subject == subject,
                BanditArmStats.kp_key == key,
            ).first()
            if row is None:
                row = BanditArmStats(
                    student_id=student_id,
                    subject=subject,
                    kp_key=key,
                    kp_name=kp_name,
                    mode=mode,
                )
                db.add(row)
            row.mode = mode
            row.impressions = (row.impressions or 0) + 1
            if reason.get("ucb_score") is not None:
                row.ucb_score = float(reason["ucb_score"])
            if key in arm_states:
                row.a_json = arm_states[key]["A"]
                row.b_json = arm_states[key]["b"]
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("bandit: persist_recommendation failed (ignored)", exc_info=True)


def record_click_reward(db, student_id: str, subject: str, kp_name: str, reward: float) -> None:
    """点击/答题反馈回填：clicks +1, reward_sum += reward, 更新 LinUCB b 向量。

    供外部（如前端答题回调 / response_logs 落库钩子）调用；当前为预留接口。
    写失败仅告警。
    """
    if db is None:
        return
    try:
        from app.models.bandit_arm_stats import BanditArmStats
        row = db.query(BanditArmStats).filter(
            BanditArmStats.student_id == student_id,
            BanditArmStats.subject == subject,
            BanditArmStats.kp_key == kp_name,
        ).first()
        if row is None:
            row = BanditArmStats(
                student_id=student_id,
                subject=subject,
                kp_key=kp_name,
                kp_name=kp_name,
                mode="exploit",
            )
            db.add(row)
        row.clicks = (row.clicks or 0) + 1
        row.reward_sum = (row.reward_sum or 0.0) + float(reward)
        if row.a_json:
            b = np.array(row.b_json or [0.0] * CONTEXT_DIM, dtype=float)
            x = np.array([1.0, 1.0, 0.5, 1.0], dtype=float)  # 简版反馈向量
            b2 = b + float(reward) * x
            row.b_json = b2.tolist()
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("bandit: record_click_reward failed (ignored)", exc_info=True)


# ── 主入口（路由调用） ───────────────────────────────────────────
def recommend_for_student(
    db,
    asset_db,
    student_id: str,
    subject: str,
    limit: int = 5,
    min_conf: float = MIN_CONFIDENCE,
    rng: Optional[random.Random] = None,
) -> dict:
    """R6b 主流程：学生错题 → 桥表薄弱 kp → PG 变式题 → 排序推荐 → 落统计。

    - PG 不可用 → 抛 AssetDBUnavailable（路由层 503）
    - 学生无错题/无 kp/无匹配 → fallback 空 items（200）
    - response_logs 无 reward → explore（确定性薄弱点推荐）
    """
    kp_rows = aggregate_kp_from_bridge(db, student_id, subject, min_conf=min_conf)
    if not kp_rows:
        return {"mode": "fallback", "reason": "无薄弱知识点（无错题或桥接未命中）", "items": []}

    # 截断 arm 数量，控制 PG 查询次数
    kp_rows = dict(list(kp_rows.items())[:MAX_ARMS])

    reward = read_reward_from_logs(db, student_id, subject)

    load_state = _load_arm_state(db, student_id, subject) if reward is not None else None

    result = build_recommendations(
        kp_rows=kp_rows,
        subject=subject,
        limit=limit,
        reward=reward,
        rng=rng,
        question_fetcher=lambda kp_name, subj, lim: fetch_variant_questions(asset_db, subj, kp_name, lim),
        load_state=load_state,
    )
    result["student_id"] = student_id
    result["subject"] = subject

    # 落统计（非关键路径）：exploit 时把更新后的 A/b 状态写回，跨请求收敛
    persist_recommendation(db, student_id, subject, result, arm_states=result.get("arm_states"))
    return result
