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
                  difficulty_pref: Any = None) -> dict:
    """按薄弱知识点 + 难度组卷。

    参数：
      db             assets 只读 session（PG）
      subject        学科（如 数学/语文）
      grade          学段（小学/初中/高中，可选）
      weak_kps       [{id?, name?, count?}, ...] 或 [str(id 或 name), ...]，可选
      count          题量（1-50）
      difficulty_pref  难度偏好（易/中/难 或 1-5，可选）
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
        plan = _band_plan(count, pref)
        plan_idx = 0
        for wk, slot_n in zip(wk_list, slots):
            if slot_n <= 0:
                continue
            pool = _fetch_candidates(db, subject, grade, wk, kp_raws)
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
    return {"questions": questions, "meta": meta}
