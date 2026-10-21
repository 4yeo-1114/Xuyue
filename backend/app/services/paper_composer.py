# -*- coding: utf-8 -*-
"""R6c 薄弱点闭环组卷 service。

从家长端 PG 资产库（只读）按薄弱知识点 + 难度抽题组卷，融合 P2-2 智能组卷。

- 薄弱点来源：调用方传入 weak_kps（kp id / kp 名列表，可带 count 权重）；
  路由层负责从 R6a 桥表 wrong_question_kp_bridge 按 class/全校聚合出 top N。
- 抽题：QuestionKp 关联优先（kp_id），fallback questions.knowledge_point 名匹配
  （先取该学科全部去重 knowledge_point 串在 Python 侧匹配，规避 LIKE 全表扫）。
- 难度：DifficultyGold 金标优先（question_id → gold_difficulty），
  fallback questions.difficulty；每道题标注 difficulty_source=gold/question。
- 质量：quality_flag IN ('ok','filled') OR NULL 才可入池。
- 组卷结构：按薄弱点 count 权重分配题量（薄弱点题多）+ 难度梯度（易→中→难）+
  同知识点变式题去重（unique_key + 题面相似度）。
- 降级链：无薄弱点 / 抽不到题 → 学科+年级随机抽题（不报错）；
  PG 不可用由路由层统一转 503（本 service 不 catch，异常向上抛）。
"""
from __future__ import annotations

import logging
import random
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

import app.assets.models as am
from app.assets.repo import _coerce_limit, _quality_ok

logger = logging.getLogger(__name__)

# 单知识点候选池上限（一次最多拉这么多题再在内存里做难度/去重）
_CANDIDATE_LIMIT = 200
# 同知识点题面相似度去重阈值：> 0.95 视为变式重复题，跳过
_DUP_RATIO = 0.95
# 随机兜底时一次多拉的比例（供去重挑选用）
_RANDOM_FETCH_FACTOR = 3

# 难度带 → (下界, 上界)
_BAND_RANGES = {
    "easy": (1, 2),
    "medium": (3, 3),
    "hard": (4, 5),
}

# ── 分层组卷（A/B/C）：难度权重 + 知识点粒度策略 ──────────────────────
# A=提高/综合/压轴权重高；B=标准难度；C=基础巩固。
# 权重为显式参数传给选题逻辑（_band_plan_with_weights），不走 LLM。
TIER_BAND_WEIGHTS: dict = {
    "A": {"easy": 0.10, "medium": 0.35, "hard": 0.55},
    "B": {"easy": 0.25, "medium": 0.50, "hard": 0.25},
    "C": {"easy": 0.55, "medium": 0.35, "hard": 0.10},
}
# 知识点粒度：C 层只取单一知识点题，A 层优先跨知识点综合题，B 层不限
# （knowledge_point 含 "/" 视为跨知识点复合串）
TIER_KP_MODE: dict = {"A": "multi", "B": None, "C": "single"}
TIER_ZH: dict = {"A": "A层", "B": "B层", "C": "C层"}


def tier_strategy(tier: str) -> dict:
    """返回该层的选题策略 {band_weights, kp_mode, difficulty_pref}（未知层回落 B）。"""
    t = (tier or "B").strip().upper()
    if t not in TIER_BAND_WEIGHTS:
        t = "B"
    weights = dict(TIER_BAND_WEIGHTS[t])
    kp_mode = TIER_KP_MODE.get(t)
    # 难度偏好仅作兼容展示：A→难 B→中 C→易
    pref = {"A": "hard", "B": "medium", "C": "easy"}.get(t, "medium")
    return {
        "tier": t,
        "band_weights": weights,
        "kp_mode": kp_mode,
        "difficulty_pref": pref,
    }


def _band_plan_with_weights(count: int, weights: dict) -> list:
    """按显式难度权重生成目标难度带序列（长度 count），带内打散。

    weights: {"easy": x, "medium": y, "hard": z}（不要求和为 1，内部归一）。
    与 _band_plan 同一输出形状，供 compose_paper 的 tier 路径使用。
    """
    if count <= 0:
        return []
    w = {"easy": 0.3, "medium": 0.5, "hard": 0.2}
    if isinstance(weights, dict):
        for k in w:
            try:
                v = float(weights.get(k))
            except (TypeError, ValueError):
                continue
            if v >= 0:
                w[k] = v
    total = sum(w.values()) or 1.0
    easy_n = max(0, round(count * w["easy"] / total))
    hard_n = max(0, round(count * w["hard"] / total))
    if easy_n + hard_n > count:
        hard_n = max(0, count - easy_n)
    medium_n = count - easy_n - hard_n
    if medium_n < 0:
        hard_n = max(0, count - easy_n)
        medium_n = count - easy_n - hard_n
    plan = ["easy"] * easy_n + ["medium"] * medium_n + ["hard"] * hard_n
    random.shuffle(plan)
    return plan


def kp_is_single(raw_kp: Any) -> bool:
    """knowledge_point 是否单一知识点（无 / 分隔或只有一个有效段）。"""
    if not raw_kp:
        return True
    segs = [s for s in str(raw_kp).split("/") if s.strip()]
    return len(segs) <= 1


def _kp_of(q: Any) -> Any:
    """取 knowledge_point：兼容 ORM 对象与 question dict。"""
    if isinstance(q, dict):
        return q.get("knowledge_point")
    return getattr(q, "knowledge_point", None)


def filter_pool_by_kp_mode(pool: list, kp_mode: Optional[str]) -> list:
    """按知识点粒度过滤候选池。

    - "single"：只保留单一知识点题（C 层基础巩固）；
    - "multi"：只保留跨知识点综合题（A 层提高/压轴），无命中时回退原池；
    - None/其他：原样返回。
    """
    if not kp_mode or not pool:
        return list(pool or [])
    mode = str(kp_mode).strip().lower()
    if mode == "single":
        filtered = [q for q in pool if kp_is_single(_kp_of(q))]
        return filtered or list(pool)
    if mode == "multi":
        filtered = [
            q for q in pool if not kp_is_single(_kp_of(q))
        ]
        return filtered or list(pool)
    return list(pool)


def difficulty_summary(questions: list) -> dict:
    """题目难度概况：{easy, medium, hard, avg, count}（difficulty 1-5，≤2 易 3 中 ≥4 难）。"""
    easy = medium = hard = 0
    total = 0
    n = 0
    for q in questions or []:
        raw = q.get("difficulty") if isinstance(q, dict) else getattr(q, "difficulty", None)
        try:
            d = int(raw) if raw is not None else 3
        except (TypeError, ValueError):
            d = 3
        total += d
        n += 1
        if d <= 2:
            easy += 1
        elif d >= 4:
            hard += 1
        else:
            medium += 1
    return {
        "easy": easy,
        "medium": medium,
        "hard": hard,
        "avg": round(total / n, 2) if n else 0,
        "count": n,
    }

# 清洗：去空白/标点/小写（与 R6a 回填脚本一致，保证 kp 名可比）
_PUNCT_RE = re.compile(r"[，。！？、；：,.!?;:\"'（）()\[\]【】《》〈〉<>「」『』~～·\-—_/\\|]")


def clean_text(s: Any) -> str:
    if not s:
        return ""
    s = str(s).replace(" ", "").replace("　", "")
    s = _PUNCT_RE.sub("", s)
    return s.lower()


def _kp_matches_name(raw_kp: Optional[str], weak_clean: str) -> bool:
    """questions.knowledge_point 复合串（a/b/c）是否命中薄弱点 clean 名。

    规则：切分后任一 segment 与弱名逐字相等，或双向包含（len>=2 防泛词）。
    """
    if not raw_kp or not weak_clean:
        return False
    segs = [s for s in (clean_text(x) for x in str(raw_kp).split("/")) if s]
    for s in segs:
        if s == weak_clean:
            return True
    for s in segs:
        if len(weak_clean) >= 2 and weak_clean in s:
            return True
        if len(s) >= 2 and s in weak_clean:
            return True
    return False


def _load_gold_difficulty(db: Session) -> dict:
    """把 difficulty_gold 全量载入 {question_id: gold_difficulty}（7483 行，量小）。"""
    gold: dict[str, int] = {}
    rows = db.query(am.DifficultyGold.question_id, am.DifficultyGold.gold_difficulty).all()
    for qid, gd in rows:
        if qid and gd:
            try:
                gold[qid] = int(gd)
            except (TypeError, ValueError):
                continue
    return gold


def _fetch_candidates_by_name(db: Session, subject: str, grade: Optional[str],
                              weak_clean: str, kp_raws: list, limit: int) -> list:
    """按 questions.knowledge_point 名匹配取候选题（kp_raws 为该学科去重 kp 串）。

    金标优先：先取命中 DifficultyGold 的题（上限 limit），余量再随机补齐，
    保证难度金标题始终在候选池内（金标仅占全库 ~0.6%，纯随机几乎抽不到）。
    """
    matched_raws = [kp for kp in kp_raws if _kp_matches_name(kp, weak_clean)]
    if not matched_raws:
        return []
    base = [
        am.Question.subject == subject,
        am.Question.knowledge_point.in_(matched_raws),
        _quality_ok(am.Question.quality_flag),
    ]
    if grade:
        base.append(am.Question.grade == grade)
    gold_rows = (
        db.query(am.Question)
        .join(am.DifficultyGold, am.DifficultyGold.question_id == am.Question.id)
        .filter(*base)
        .order_by(func.random())
        .limit(limit)
        .all()
    )
    if len(gold_rows) >= limit:
        return gold_rows
    gold_ids = {q.id for q in gold_rows}
    q = db.query(am.Question).filter(*base)
    if gold_ids:
        q = q.filter(~am.Question.id.in_(gold_ids))
    rest = q.order_by(func.random()).limit(limit - len(gold_rows)).all()
    return gold_rows + rest


def _fetch_candidates_by_kp_id(db: Session, subject: str, grade: Optional[str],
                               kp_id: str, limit: int) -> list:
    """经 QuestionKp 桥接表按 kp_id 取候选题（金标优先同名匹配）。"""
    base = [_quality_ok(am.Question.quality_flag)]
    if subject:
        base.append(am.Question.subject == subject)
    if grade:
        base.append(am.Question.grade == grade)
    gold_rows = (
        db.query(am.Question)
        .join(am.QuestionKp, am.QuestionKp.question_id == am.Question.id)
        .join(am.DifficultyGold, am.DifficultyGold.question_id == am.Question.id)
        .filter(am.QuestionKp.kp_id == kp_id, *base)
        .order_by(func.random())
        .limit(limit)
        .all()
    )
    if len(gold_rows) >= limit:
        return gold_rows
    gold_ids = {q.id for q in gold_rows}
    q = (
        db.query(am.Question)
        .join(am.QuestionKp, am.QuestionKp.question_id == am.Question.id)
        .filter(am.QuestionKp.kp_id == kp_id, *base)
    )
    if gold_ids:
        q = q.filter(~am.Question.id.in_(gold_ids))
    rest = q.order_by(func.random()).limit(limit - len(gold_rows)).all()
    return gold_rows + rest


def _fetch_candidates(db: Session, subject: str, grade: Optional[str],
                      wk: dict, kp_raws: list, limit: int = _CANDIDATE_LIMIT) -> list:
    """按薄弱点取候选题：kp_id 关联优先，fallback 名匹配。"""
    kp_id = wk.get("id") or ""
    kp_name = wk.get("name") or ""
    kp_clean = clean_text(kp_name)
    if kp_id:
        rows = _fetch_candidates_by_kp_id(db, subject, grade, kp_id, limit)
        if rows:
            return rows
    if kp_clean:
        rows = _fetch_candidates_by_name(db, subject, grade, kp_clean, kp_raws, limit)
        if not rows and grade:
            # grade 过滤抽空 → 去掉 grade 再试一次
            rows = _fetch_candidates_by_name(db, subject, None, kp_clean, kp_raws, limit)
        if rows:
            return rows
    return []


def _dedupe_pick(pool: list, used_keys: set, used_texts: list,
                 target_band: str, gold: dict, relax: bool = False):
    """从候选池挑一道满足目标难度带的题（unique_key + 题面相似度去重）。

    返回 (question, resolved_difficulty) 或 (None, None)。
    """
    if not pool:
        return None, None
    band_pool: list = []
    other_pool: list = []
    lo, hi = _BAND_RANGES[target_band]
    for q in pool:
        if q.unique_key in used_keys:
            continue
        diff = gold.get(q.id) or (q.difficulty or 3)
        item = (q, int(diff))
        if lo <= int(diff) <= hi:
            band_pool.append(item)
        else:
            other_pool.append(item)
    candidates = band_pool
    if relax and not band_pool:
        candidates = other_pool
    if not candidates:
        candidates = band_pool or other_pool
    random.shuffle(candidates)
    # 金标优先：难度金标题（DifficultyGold 有值）优先被抽取，无金标时兜底 questions.difficulty
    candidates.sort(key=lambda item: 0 if item[0].id in gold else 1)
    for q, diff in candidates:
        text = (q.question or "").strip()
        if text:
            dup = False
            for t in used_texts:
                if t and SequenceMatcher(None, text, t).ratio() > _DUP_RATIO:
                    dup = True
                    break
            if dup:
                continue
        return q, diff
    return None, None


def _question_to_dict(q: Any, kp_id: str, kp_name: str,
                      difficulty: int, difficulty_source: str) -> dict:
    return {
        "id": q.id,
        "subject": q.subject,
        "grade": q.grade,
        "question_type": q.question_type,
        "question": q.question,
        "options": q.options,
        "answer": q.answer,
        "analysis": q.analysis,
        "knowledge_point": q.knowledge_point,
        "difficulty": int(difficulty),
        "difficulty_source": difficulty_source,
        "kp_id": kp_id,
        "kp_name": kp_name,
        "unique_key": q.unique_key,
        "quality_flag": q.quality_flag,
    }


def _normalize_pref(pref: Any) -> Optional[str]:
    if pref is None:
        return None
    p = str(pref).strip().lower()
    if p in ("易", "easy", "偏易", "1", "2"):
        return "easy"
    if p in ("难", "hard", "偏难", "4", "5"):
        return "hard"
    if p in ("中", "medium", "适中", "3"):
        return "medium"
    return None


def _band_plan(count: int, pref: Optional[str]) -> list:
    """生成易→中→难目标难度带序列（长度 count），带内打散便于跨 kp 均摊。"""
    if count <= 0:
        return []
    easy_n = max(0, round(count * 0.3))
    hard_n = max(0, round(count * 0.2))
    if pref == "easy":
        easy_n = min(count, easy_n + 1)
    elif pref == "hard":
        hard_n = min(max(0, count - 1), hard_n + 1)
    elif pref == "medium":
        easy_n = max(0, easy_n - 1)
    medium_n = count - easy_n - hard_n
    if medium_n < 0:
        hard_n = max(0, count - easy_n)
        medium_n = count - easy_n - hard_n
    plan = ["easy"] * easy_n + ["medium"] * medium_n + ["hard"] * hard_n
    random.shuffle(plan)
    return plan


def _allocate_slots(weak_kps: list, count: int) -> list:
    """按薄弱点 count 权重分配题量（权重越大题越多），余数按小数部分最大者摊。"""
    n = len(weak_kps)
    if n == 0:
        return []
    weights: list[int] = []
    for wk in weak_kps:
        w = 1
        c = wk.get("count") or wk.get("weight") or 0
        try:
            c = int(c)
        except (TypeError, ValueError):
            c = 0
        if c > 0:
            w = c
        weights.append(w)
    total = sum(weights) or 1
    slots = []
    fracs = []
    assigned = 0
    for i, w in enumerate(weights):
        raw = count * w / total
        s = int(raw)
        slots.append(s)
        assigned += s
        fracs.append((raw - s, i))
    remain = count - assigned
    fracs.sort(key=lambda x: -x[0])
    for _, i in fracs[:remain]:
        slots[i] += 1
    return slots


def _random_fallback(db: Session, subject: str, grade: Optional[str],
                     count: int, gold: dict, used_keys: set, used_texts: list) -> list:
    """降级：无薄弱点/抽不到 → 学科+年级随机抽题（quality 放行，去重）。"""
    q = db.query(am.Question).filter(
        am.Question.subject == subject,
        _quality_ok(am.Question.quality_flag),
    )
    if grade:
        q = q.filter(am.Question.grade == grade)
    rows = q.order_by(func.random()).limit(count * _RANDOM_FETCH_FACTOR).all()
    # 金标优先：随机兜底同样优先抽取有 DifficultyGold 的题
    rows.sort(key=lambda qobj: 0 if qobj.id in gold else 1)
    picked: list = []
    for qobj in rows:
        if len(picked) >= count:
            break
        if qobj.unique_key in used_keys:
            continue
        diff = gold.get(qobj.id) or (qobj.difficulty or 3)
        source = "gold" if qobj.id in gold else "question"
        text = (qobj.question or "").strip()
        if text:
            dup = False
            for t in used_texts:
                if t and SequenceMatcher(None, text, t).ratio() > _DUP_RATIO:
                    dup = True
                    break
            if dup:
                continue
        picked.append(_question_to_dict(qobj, None, None, int(diff), source))
        used_keys.add(qobj.unique_key)
        if text:
            used_texts.append(text)
    return picked


def compose_paper(db: Session, subject: str, grade: Optional[str],
                  weak_kps: Optional[list], count: int,
                  difficulty_pref: Any = None,
                  band_weights: Optional[dict] = None,
                  kp_mode: Optional[str] = None) -> dict:
    """按薄弱知识点 + 难度组卷。

    参数：
      db             assets 只读 session（PG）
      subject        学科（如 数学/语文）
      grade          学段（小学/初中/高中，可选）
      weak_kps       [{id?, name?, count?}, ...] 或 [str(id 或 name), ...]，可选
      count          题量（1-50）
      difficulty_pref  难度偏好（易/中/难 或 1-5，可选）
      band_weights   显式难度带权重 {"easy","medium","hard"}，分层组卷用（优先于 difficulty_pref）
      kp_mode        知识点粒度："single"=只取单一知识点 / "multi"=优先跨知识点综合 / None 不限
    返回：
      {"questions": [...], "meta": {...}}
    """
    count = _coerce_limit(count, default=10)
    gold = _load_gold_difficulty(db)

    # 该学科去重 knowledge_point 串（名匹配候选池，一次加载复用）
    kp_raws: list = []
    if subject:
        kp_raws = [
            r[0] for r in db.query(am.Question.knowledge_point)
            .filter(am.Question.subject == subject)
            .filter(am.Question.knowledge_point.isnot(None))
            .filter(am.Question.knowledge_point != "")
            .distinct()
            .all()
        ]

    questions: list = []
    used_keys: set = set()
    used_texts: list = []
    weak_picked = 0
    pref = _normalize_pref(difficulty_pref)

    # 规范化 weak_kps → [{id?, name?, count?}]
    wk_list: list = []
    for wk in weak_kps or []:
        if isinstance(wk, dict):
            if wk.get("name") or wk.get("id"):
                wk_list.append(wk)
        else:
            s = str(wk).strip()
            if s:
                wk_list.append({"name": s})

    if wk_list:
        slots = _allocate_slots(wk_list, count)
        # 分层组卷：显式难度权重优先；否则走原 easy/medium/hard 偏好
        if band_weights:
            plan = _band_plan_with_weights(count, band_weights)
        else:
            plan = _band_plan(count, pref)
        plan_idx = 0
        for wk, slot_n in zip(wk_list, slots):
            if slot_n <= 0:
                continue
            pool = _fetch_candidates(db, subject, grade, wk, kp_raws)
            pool = filter_pool_by_kp_mode(pool, kp_mode)
            if not pool:
                continue
            for _ in range(slot_n):
                if plan_idx >= len(plan):
                    break
                band = plan[plan_idx]
                plan_idx += 1
                qobj, diff = _dedupe_pick(pool, used_keys, used_texts, band, gold)
                if qobj is None:
                    qobj, diff = _dedupe_pick(pool, used_keys, used_texts, band, gold, relax=True)
                if qobj is None:
                    continue
                source = "gold" if qobj.id in gold else "question"
                questions.append(
                    _question_to_dict(qobj, wk.get("id") or "", wk.get("name") or "",
                                      diff, source)
                )
                weak_picked += 1
                used_keys.add(qobj.unique_key)
                text = (qobj.question or "").strip()
                if text:
                    used_texts.append(text)

    # 不足 count：随机兜底补足（有薄弱点时也补，凑满题量）
    if len(questions) < count:
        leftover = count - len(questions)
        fill = _random_fallback(db, subject, grade, leftover, gold, used_keys, used_texts)
        fill = filter_pool_by_kp_mode(fill, kp_mode)
        questions.extend(fill)

    composition = "weak-kp" if weak_picked else "random-fallback"

    # 难度梯度：易→中→难
    questions.sort(key=lambda x: x["difficulty"])

    meta = {
        "subject": subject,
        "grade": grade,
        "count": len(questions),
        "requested_count": count,
        "difficulty_pref": pref,
        "weak_kp_count": len(wk_list),
        "composition": composition,
    }
    if band_weights:
        meta["band_weights"] = dict(band_weights)
    if kp_mode:
        meta["kp_mode"] = kp_mode
    return {"questions": questions, "meta": meta}


# ── 分层组卷：A/B/C 各一份（复用 compose_paper 选题，不走 LLM） ─────────

# assets question_type（中/英）→ ExamGenPage ExamQuestion.type
_TYPE_NAME_TO_EXAM_TYPE = {
    "选择题": "choice",
    "填空题": "fill",
    "判断题": "judge",
    "简答题": "short_answer",
    "作文": "essay",
    "写作": "essay",
    "连线题": "matching",
    "排序题": "ordering",
    "阅读理解": "reading",
    "完形填空": "cloze",
    "计算题": "calculation",
    "应用题": "application",
    "choice": "choice",
    "fill": "fill",
    "judge": "judge",
    "short_answer": "short_answer",
    "essay": "essay",
    "matching": "matching",
    "ordering": "ordering",
    "reading": "reading",
    "cloze": "cloze",
    "calculation": "calculation",
    "application": "application",
}

# 元数据哨兵 key：塞进 questions 列表首项（isExamQuestion 不会当成题目）
TIERED_META_KEY = "__tiered_meta__"


def compose_q_to_exam_q(q: dict) -> dict:
    """组卷题 dict → ExamGenPage ExamQuestion 形状（可直接进试卷库展示/打印）。"""
    raw_type = (q.get("question_type") or "").strip()
    qtype = _TYPE_NAME_TO_EXAM_TYPE.get(raw_type) or _TYPE_NAME_TO_EXAM_TYPE.get(
        raw_type.lower()
    ) or "short_answer"
    options = q.get("options")
    if not isinstance(options, list):
        options = []
    score = 30 if qtype == "essay" else 5
    out = {
        "id": str(q.get("id") or q.get("unique_key") or ""),
        "type": qtype,
        "stem": (q.get("question") or "").strip(),
        "content": "",
        "options": [str(o) for o in options],
        "score": score,
    }
    if q.get("answer"):
        out["answer"] = str(q["answer"])
    if q.get("analysis"):
        out["analysis"] = str(q["analysis"])
    if q.get("knowledge_point"):
        out["knowledge_point"] = str(q["knowledge_point"])
    if q.get("difficulty") is not None:
        try:
            out["difficulty"] = int(q["difficulty"])
        except (TypeError, ValueError):
            pass
    return out


def pack_paper_questions(exam_questions: list, meta: dict) -> list:
    """把元数据哨兵 + 题目列表写进 smart_exam_papers.questions。

    首项 {__tiered_meta__: {...}} 不会被 ExamGenPage isExamQuestion 识别为题目，
    故不污染展示；GET tiered-compose/result 读它拿 tier/班级/轮次。
    """
    return [{TIERED_META_KEY: dict(meta or {})}] + list(exam_questions or [])


def unpack_paper_questions(raw: Any) -> tuple:
    """拆 questions 列表 → (meta, exam_questions)。无哨兵时 meta={}。"""
    if not isinstance(raw, list):
        return {}, []
    meta: dict = {}
    items: list = []
    for item in raw:
        if isinstance(item, dict) and TIERED_META_KEY in item and len(item) == 1:
            val = item.get(TIERED_META_KEY)
            if isinstance(val, dict):
                meta = val
            continue
        items.append(item)
    return meta, items


def read_class_tiers(db: Session, class_id: str) -> dict:
    """读当前分层：{A: [student_id,...], B: [...], C: [...], unassigned: n}。"""
    from app.models.student import Student

    buckets: dict = {"A": [], "B": [], "C": [], "unassigned": 0}
    rows = db.query(Student.id, Student.tier).filter(Student.class_id == class_id).all()
    for sid, tier in rows:
        t = (tier or "").strip().upper()
        if t in ("A", "B", "C"):
            buckets[t].append(sid)
        else:
            buckets["unassigned"] += 1
    return buckets


def compose_tiered_papers(
    asset_db: Session,
    class_id: str,
    subject: str,
    grade: Optional[str] = None,
    weak_kps: Optional[list] = None,
    count: int = 10,
    round_id: Optional[str] = None,
    exam_folder: Optional[str] = None,
    tiers: Optional[dict] = None,
) -> dict:
    """按 A/B/C 层各组一份卷（题源复用 compose_paper，层间差异走难度权重+知识点粒度）。

    tiers 必须由调用方从主库读出后传入（read_class_tiers）；asset_db 是 PG 资产库。
    返回：
      {
        "tiers": {"A": n, "B": n, "C": n, "unassigned": n},
        "papers": [
          {
            "tier": "A",
            "title": "...A层...",
            "questions": [exam_q...],   # ExamQuestion 形状（不含 meta 哨兵）
            "payload": [meta哨兵, ...],  # 直接落库 smart_exam_papers.questions
            "meta": {...},
            "difficulty": {...},
          }, ...  # 固定 A/B/C 三份
        ],
      }
    无任何分层时 raise ValueError（路由层转 400）。
    """
    if not subject or not str(subject).strip():
        raise ValueError("学科不能为空")
    if not isinstance(tiers, dict):
        raise ValueError("tiers 缺失：请先从主库读取班级分层")
    tier_buckets = tiers
    assigned = sum(len(tier_buckets.get(t) or []) for t in ("A", "B", "C"))
    if assigned == 0:
        raise ValueError("该班尚未完成分层，请先在分层推送中自动/手动分层")

    papers: list = []
    now_tag = datetime.now().strftime("%Y%m%d-%H%M%S")
    batch_id = f"tc-{now_tag}"
    for tier in ("A", "B", "C"):
        strategy = tier_strategy(tier)
        result = compose_paper(
            asset_db,
            subject,
            grade,
            weak_kps,
            count,
            strategy["difficulty_pref"],
            band_weights=strategy["band_weights"],
            kp_mode=strategy["kp_mode"],
        )
        exam_qs = [compose_q_to_exam_q(q) for q in result.get("questions") or []]
        summary = difficulty_summary(result.get("questions") or [])
        tier_label = TIER_ZH.get(tier, tier)
        title = f"{subject}{tier_label}分层卷-{now_tag}"
        meta = {
            "source": "tiered-compose",
            "batch_id": batch_id,
            "tier": tier,
            "tier_label": tier_label,
            "class_id": class_id,
            "subject": subject,
            "grade": grade,
            "round_id": round_id,
            "exam_folder": exam_folder,
            "band_weights": strategy["band_weights"],
            "kp_mode": strategy["kp_mode"],
            "difficulty_pref": strategy["difficulty_pref"],
            "student_count": len(tier_buckets.get(tier) or []),
            "compose_meta": result.get("meta") or {},
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        papers.append(
            {
                "tier": tier,
                "title": title,
                "questions": exam_qs,
                "payload": pack_paper_questions(exam_qs, meta),
                "meta": meta,
                "difficulty": summary,
            }
        )
    return {
        "tiers": {
            "A": len(tier_buckets.get("A") or []),
            "B": len(tier_buckets.get("B") or []),
            "C": len(tier_buckets.get("C") or []),
            "unassigned": int(tier_buckets.get("unassigned") or 0),
        },
        "papers": papers,
    }


# 难度带 → difficulty 数值（≤2 易 / 3 中 / ≥4 难，与 difficulty_summary 同口径）
_BAND_TO_DIFFICULTY = {"easy": 2, "medium": 3, "hard": 4}


def compose_tiered_papers_ai(
    db: Session,
    class_id: str,
    subject: str,
    grade: Optional[str] = None,
    topics: Optional[list] = None,
    requirements: Optional[list] = None,
    count: int = 10,
    round_id: Optional[str] = None,
    exam_folder: Optional[str] = None,
    tiers: Optional[dict] = None,
) -> dict:
    """按 A/B/C 层各组一份卷（题源=AI 生成，不依赖 PG 题库）。

    与 compose_tiered_papers 同返回形状、同 meta 结构（source 恒为 "tiered-compose"，
    额外 engine="ai"），保证 GET /papers/tiered-compose/result 清单兼容；
    三份卷并发出题（LLM 配置只读一次），层间差异体现在难度权重 + 出题备注。
    无任何分层 raise ValueError；AI 失败 raise AIGenerationError（路由层转 500）。
    """
    from app.services.ai_question_gen import (
        AIGenerationError,
        default_requirements,
        llm_generate_questions,
        tier_difficulty_text,
    )

    if not subject or not str(subject).strip():
        raise ValueError("学科不能为空")
    if not isinstance(tiers, dict):
        raise ValueError("tiers 缺失：请先从主库读取班级分层")
    tier_buckets = tiers
    assigned = sum(len(tier_buckets.get(t) or []) for t in ("A", "B", "C"))
    if assigned == 0:
        raise ValueError("该班尚未完成分层，请先在分层推送中自动/手动分层")

    topic_list = [str(t).strip() for t in (topics or []) if str(t).strip()]
    reqs = [dict(r) for r in (requirements or []) if isinstance(r, dict)]
    reqs = [r for r in reqs if int(r.get("count") or 0) > 0]
    if not reqs:
        reqs = default_requirements(count)

    # LLM 配置只读一次（key 在 SystemSettings；worker 线程不再碰 db）
    from app.utils.qwen_settings import get_llm_config

    llm_cfg = get_llm_config(db)

    def _gen_tier(tier: str) -> list:
        strategy = tier_strategy(tier)
        tier_label = TIER_ZH.get(tier, tier)
        kp_note = {
            "multi": "优先命制跨知识点的综合题。",
            "single": "每题聚焦单一知识点，突出基础巩固。",
        }.get(strategy.get("kp_mode") or "", "")
        extra_note = (
            f"本卷为{tier_label}（{tier}层）分层卷，难度{tier_difficulty_text(strategy['difficulty_pref'])}。{kp_note}"
        )
        qs = llm_generate_questions(
            db,
            subject=subject,
            grade=grade,
            difficulty=tier_difficulty_text(strategy["difficulty_pref"]),
            topics=topic_list,
            requirements=reqs,
            extra_note=extra_note,
            llm_cfg=llm_cfg,
        )
        # 层难度权重落到 difficulty 数字（difficulty_summary 口径），层间差异可量化
        plan = _band_plan_with_weights(len(qs), strategy["band_weights"])
        for q, band in zip(qs, plan):
            q["difficulty"] = _BAND_TO_DIFFICULTY.get(band, 3)
        return qs

    from concurrent.futures import ThreadPoolExecutor

    tier_list = ("A", "B", "C")
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {t: pool.submit(_gen_tier, t) for t in tier_list}
        tier_questions = {}
        for t in tier_list:
            try:
                tier_questions[t] = futures[t].result()
            except Exception as e:
                for other in futures.values():
                    other.cancel()
                if isinstance(e, AIGenerationError):
                    raise
                raise AIGenerationError("AI 解析失败，请重试或修改提示词") from e

    papers: list = []
    now_tag = datetime.now().strftime("%Y%m%d-%H%M%S")
    batch_id = f"tc-{now_tag}"
    for tier in tier_list:
        strategy = tier_strategy(tier)
        exam_qs = tier_questions.get(tier) or []
        summary = difficulty_summary(exam_qs)
        tier_label = TIER_ZH.get(tier, tier)
        title = f"{subject}{tier_label}分层卷-{now_tag}"
        meta = {
            "source": "tiered-compose",
            "engine": "ai",
            "batch_id": batch_id,
            "tier": tier,
            "tier_label": tier_label,
            "class_id": class_id,
            "subject": subject,
            "grade": grade,
            "round_id": round_id,
            "exam_folder": exam_folder,
            "band_weights": strategy["band_weights"],
            "kp_mode": strategy["kp_mode"],
            "difficulty_pref": strategy["difficulty_pref"],
            "student_count": len(tier_buckets.get(tier) or []),
            "compose_meta": {
                "engine": "ai",
                "topics": topic_list,
                "requirements": reqs,
            },
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        papers.append(
            {
                "tier": tier,
                "title": title,
                "questions": exam_qs,
                "payload": pack_paper_questions(exam_qs, meta),
                "meta": meta,
                "difficulty": summary,
            }
        )
    return {
        "tiers": {
            "A": len(tier_buckets.get("A") or []),
            "B": len(tier_buckets.get("B") or []),
            "C": len(tier_buckets.get("C") or []),
            "unassigned": int(tier_buckets.get("unassigned") or 0),
        },
        "papers": papers,
    }
