"""
五育成长画像评分口径引擎（纯函数，无 DB 依赖）。

分层：Repository 只负责取原始行，本模块负责算。单生 / 班级 / 学期报告三处共用同一套口径。

P0 评分口径（A0 §4）：
  1. 双轨制：
       - 成就轨（真实成长分）S_dim = Σ growth_records + 该维自动事件分（智育按时间衰减加权）
       - 活跃轨（参与度）      独立于成就轨，反映该维事件参与次数
       - data_status          has_data / insufficient（无数据即灰态，不充数）
  2. 智育 7 事件目录（event_catalog）+ 学期 cap + 时间衰减
  3. 班级百分位 P = 1 - (class_rank-1)/n；五档 A+/A/B/C/D；学校级 z-score；综合分 T-score。
"""
from __future__ import annotations

import datetime
import math
from typing import Optional

from app.services.portfolio.event_catalog import (
    DIMENSIONS,
    as_dt,
    current_term_bounds,
    decay_weight,
    event_config,
    is_event_enabled,
)

# 输出维度集合（五育 + 综合 total）
OUT_DIMS = DIMENSIONS + ("total",)

# 五档阈值（班级百分位 P ∈ [0,100]），顺序从高到低
TIER_RULES = (
    ("A+", 90.0),
    ("A", 75.0),
    ("B", 40.0),
    ("C", 20.0),
    ("D", 0.0),
)

# 综合分 T-score 参数：composite = SCALE_MEAN + SCALE_SD * z
SCALE_MEAN = 50.0
SCALE_SD = 10.0


# ── 基础口径 ──────────────────────────────────────

def tier_for_percentile(p: Optional[float]) -> Optional[str]:
    """百分位 → 五档（A+/A/B/C/D）；无数据返回 None。"""
    if p is None:
        return None
    for tier, threshold in TIER_RULES:
        if p >= threshold:
            return tier
    return "D"


def percentile_from_rank(rank: int, n: int) -> Optional[float]:
    """班级百分位 P = 1 - (class_rank-1)/n（n = 该班有数据学生数）。"""
    if n is None or n <= 0:
        return None
    rank = max(1, min(int(rank), n))
    return round((1 - (rank - 1) / n) * 100, 2)


def composite_from_z(z: Optional[float]) -> Optional[float]:
    """归一化标准分（综合分）：T-score 映射 50+10z，截断 [0,100]。"""
    if z is None or not math.isfinite(z):
        return None
    return round(max(0.0, min(100.0, SCALE_MEAN + SCALE_SD * z)), 2)


# ── 智育自动事件聚合（时间衰减 + 学期 cap）────────────

def _rank_up_events(exam_rows: list) -> list[dict]:
    """rank 提升事件：同 subject 相比上次 class_rank 更小（数字变小 = 进步）。"""
    by_subject: dict = {}
    for r in exam_rows or []:
        subject = r.get("subject")
        rank = r.get("class_rank")
        if not subject or rank is None:
            continue
        by_subject.setdefault(subject, []).append((as_dt(r.get("exam_date") or r.get("created_at")), int(rank)))
    events: list[dict] = []
    epoch = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
    for entries in by_subject.values():
        entries.sort(key=lambda x: x[0] or epoch)
        prev_rank = None
        for ts, rank in entries:
            if prev_rank is not None and rank < prev_rank:
                events.append({"event_type": "exam_rank_up", "occurred_at": ts})
            prev_rank = rank
    return events


def _above_avg_events(exam_rows: list) -> list[dict]:
    """超均分事件：exam_score.score > class_avg，每科次 +weight。"""
    events: list[dict] = []
    for r in exam_rows or []:
        score, avg = r.get("score"), r.get("class_avg")
        if score is None or avg is None:
            continue
        try:
            if float(score) > float(avg):
                events.append({"event_type": "above_class_avg",
                               "occurred_at": as_dt(r.get("exam_date") or r.get("created_at"))})
        except (TypeError, ValueError):
            continue
    return events


def _weak_point_events(corrected_rows: list) -> list[dict]:
    """薄弱点攻克：knowledge_point 从"错"到"订正"＝被攻克，按知识点去重。"""
    latest: dict = {}
    for r in corrected_rows or []:
        kp = r.get("knowledge_point")
        if not kp:
            continue
        ts = as_dt(r.get("corrected_at"))
        if ts is None:
            continue
        if kp not in latest or ts > latest[kp]:
            latest[kp] = ts
    return [
        {"event_type": "weak_point_conquered", "occurred_at": ts, "knowledge_point": kp}
        for kp, ts in latest.items()
    ]


def _apply_term_cap(events: list[dict], now: datetime.datetime,
                    term_from: datetime.datetime = None,
                    term_to: datetime.datetime = None) -> list[dict]:
    """cap_per_term：当前学期内同类型事件按时间倒序保留最近 cap 条。"""
    if term_from is None or term_to is None:
        term_from, term_to = current_term_bounds(now)
    grouped: dict[str, list] = {}
    for e in events:
        grouped.setdefault(e["event_type"], []).append(e)

    kept: list[dict] = []
    for etype, evs in grouped.items():
        cfg = event_config(etype)
        cap = cfg.get("cap_per_term")
        if cap:
            in_term = [e for e in evs
                       if e["occurred_at"] and term_from <= e["occurred_at"] <= term_to]
            if len(in_term) > cap:
                drop = {id(e) for e in
                        sorted(in_term, key=lambda e: e["occurred_at"], reverse=True)[cap:]}
                evs = [e for e in evs if id(e) not in drop]
        kept.extend(evs)
    return kept


def compute_intellectual_events(corrected_rows: list, report_rows: list,
                                exam_rows: list, wrong_total: int = 0,
                                now: datetime.datetime = None,
                                tau_days: float = None,
                                apply_decay: bool = True,
                                term_from: datetime.datetime = None,
                                term_to: datetime.datetime = None) -> dict:
    """聚合智育自动事件（7 事件目录 + 时间衰减 + 学期 cap）。

    corrected_rows: 该生已订正错题行（含 corrected_at / knowledge_point）
    report_rows:    该生靶向报告行（含 created_at/generated_at）
    exam_rows:      该生成绩行（含 subject / score / class_avg / class_rank / exam_date）
    wrong_total:    该生错题总数（含未订正，用于订正率）
    apply_decay:    False 时关闭时间衰减（学期报告快照用）
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    events: list[dict] = []

    def _push(etype: str, occurred_at) -> None:
        if not is_event_enabled(etype):
            return
        cfg = event_config(etype)
        events.append({"event_type": etype, "points": cfg["weight"], "occurred_at": occurred_at})

    # 1) 错题订正
    for r in corrected_rows or []:
        _push("wrong_question_corrected", as_dt(r.get("corrected_at") or r.get("created_at")))
    # 2) rank 提升
    for ev in _rank_up_events(exam_rows):
        _push("exam_rank_up", ev["occurred_at"])
    # 3) 靶向提升报告
    for r in report_rows or []:
        _push("targeted_report", as_dt(r.get("created_at") or r.get("generated_at")))
    # 4) 超班级均分
    for ev in _above_avg_events(exam_rows):
        _push("above_class_avg", ev["occurred_at"])
    # 5) 订正率达标（≥80%）
    if wrong_total and int(wrong_total) > 0:
        corrected_cnt = len(corrected_rows or [])
        if corrected_cnt / int(wrong_total) >= 0.8:
            latest = max((as_dt(r.get("corrected_at")) for r in (corrected_rows or [])
                          if as_dt(r.get("corrected_at")) is not None),
                         default=None)
            _push("correction_rate_high", latest)
    # 6) 薄弱点攻克
    for ev in _weak_point_events(corrected_rows):
        _push("weak_point_conquered", ev["occurred_at"])

    activity_count = len(events)          # 参与次数（cap 前）
    kept = _apply_term_cap(events, now, term_from, term_to)   # cap 后

    total = 0.0
    raw_total = 0
    by_event: dict = {}
    raw_by_event: dict = {}
    for e in events:
        r = raw_by_event.setdefault(e["event_type"], {"count": 0, "weight": e["points"]})
        r["count"] += 1
    for e in kept:
        w = decay_weight(e["occurred_at"], now, tau_days) if apply_decay else 1.0
        e["decay_weight"] = round(w, 4)
        total += e["points"] * w
        raw_total += e["points"]
        b = by_event.setdefault(e["event_type"], {
            "count": 0, "points": 0.0, "weight": e["points"]})
        b["count"] += 1
        b["points"] = round(b["points"] + e["points"] * w, 4)

    return {
        "events": kept,
        "total": round(total, 2),
        "raw_total": raw_total,
        "activity_count": activity_count,
        "by_event": by_event,
        "raw_by_event": raw_by_event,
    }


# ── 双轨制组装 ────────────────────────────────────

def assemble_dual_track(growth_by_dim: dict, intel_auto: dict) -> dict:
    """组装双轨制：成就轨 / 活跃轨 / data_status。

    growth_by_dim: {dim: {"points": int, "count": int}}（成长流水聚合）
    intel_auto:    compute_intellectual_events 的返回（智育自动事件）
    """
    dims: dict = {}
    activity: dict = {}
    status: dict = {}
    for dim in DIMENSIONS:
        growth = growth_by_dim.get(dim) or {}
        growth_pts = int(growth.get("points") or 0)
        growth_cnt = int(growth.get("count") or 0)
        if dim == "intellectual":
            score = growth_pts + intel_auto["total"]
            has_data = growth_cnt > 0 or intel_auto["activity_count"] > 0
            activity_cnt = growth_cnt + intel_auto["activity_count"]
        else:
            score = growth_pts
            has_data = growth_cnt > 0
            activity_cnt = growth_cnt
        dims[dim] = round(score, 2)
        activity[dim] = {"count": activity_cnt}
        status[dim] = "has_data" if has_data else "insufficient"
    return {
        "dimensions": dims,
        "activity_track": activity,
        "data_status": status,
        "total": round(sum(dims.values()), 2),
    }


# ── 班级/年级自适应基准线（输出口径）────────────────

def _scores_by_dim(student_scores: dict) -> dict:
    """{student_id: {dim: score, total}} → {dim: {student_id: score}}。"""
    out = {d: {} for d in OUT_DIMS}
    for sid, scores in (student_scores or {}).items():
        for d in DIMENSIONS:
            out[d][sid] = float(scores.get(d) or 0)
        out["total"][sid] = float(scores.get("total") or 0)
    return out


def _is_eligible(student_status: dict, dim: str) -> bool:
    """该生该维是否参与排名/标准化。total 维 = 五育任一维 has_data。"""
    if dim == "total":
        return any(v == "has_data" for v in (student_status or {}).values())
    return (student_status or {}).get(dim) == "has_data"


def class_rank_metrics(student_scores: dict, student_status: dict) -> dict:
    """班级内排名口径（仅统计 has_data 学生）→ {dim: {student_id: metrics}}。"""
    by_dim = _scores_by_dim(student_scores)
    out: dict = {}
    for dim in OUT_DIMS:
        eligible = {
            sid: s for sid, s in by_dim[dim].items()
            if _is_eligible((student_status.get(sid) or {}), dim)
        }
        ranked = sorted(eligible.items(), key=lambda kv: kv[1], reverse=True)
        n = len(ranked)
        dim_out: dict = {}
        for rank, (sid, score) in enumerate(ranked, start=1):
            p = percentile_from_rank(rank, n)
            dim_out[sid] = {
                "rank": rank,
                "n": n,
                "percentile": p,
                "tier": tier_for_percentile(p),
                "score": round(score, 2),
            }
        out[dim] = dim_out
    return out


def _mean_std(vals: list[float]) -> tuple[Optional[float], Optional[float]]:
    """均值 / 总体标准差；样本不足或无方差返回 None（避免除零）。"""
    if not vals:
        return None, None
    avg = sum(vals) / len(vals)
    var = sum((v - avg) ** 2 for v in vals) / len(vals)
    std = math.sqrt(var)
    return avg, std


def school_z_metrics(student_scores: dict, student_status: dict) -> dict:
    """学校级标准化 z-score → {dim: {student_id: {z_score, school_avg, school_std, n}}}。"""
    by_dim = _scores_by_dim(student_scores)
    out: dict = {}
    for dim in OUT_DIMS:
        eligible = {
            sid: s for sid, s in by_dim[dim].items()
            if _is_eligible((student_status.get(sid) or {}), dim)
        }
        vals = list(eligible.values())
        avg, std = _mean_std(vals)
        dim_out: dict = {}
        n = len(vals)
        for sid, s in eligible.items():
            z = (s - avg) / std if avg is not None and std else 0.0
            dim_out[sid] = {
                "z_score": round(z, 3),
                "school_avg": round(avg, 2) if avg is not None else None,
                "school_std": round(std, 2) if std is not None else None,
                "n": n,
            }
        out[dim] = dim_out
    return out


def composite_metrics(z_metrics: dict) -> dict:
    """z-score → 综合分（归一化标准分 0-100）→ {dim: {student_id: composite}}。"""
    out: dict = {}
    for dim, m in z_metrics.items():
        out[dim] = {
            sid: composite_from_z(meta.get("z_score"))
            for sid, meta in m.items()
        }
    return out


def merge_student_metrics(student_id: str, rank_metrics: dict, z_metrics: dict,
                          composite: dict) -> dict:
    """把班级排名 / 学校 z / 综合分合并到单个学生（输出 {dim: {percentile, tier, z_score, composite}}）。"""
    merged: dict = {}
    for dim in OUT_DIMS:
        r = (rank_metrics.get(dim) or {}).get(student_id)
        z = (z_metrics.get(dim) or {}).get(student_id)
        c = (composite.get(dim) or {}).get(student_id)
        if r is None:
            merged[dim] = {
                "percentile": None, "tier": None,
                "rank": None, "n": None, "z_score": None, "composite": None,
            }
        else:
            merged[dim] = {
                "percentile": r["percentile"], "tier": r["tier"],
                "rank": r["rank"], "n": r["n"],
                "z_score": (z or {}).get("z_score"),
                "composite": c,
            }
    return merged


def flatten_baseline(baseline: dict) -> dict:
    """merge_student_metrics 的嵌套形态 → 扁平化各输出字段。"""
    out: dict = {
        "percentile": {}, "tier": {}, "z_score": {}, "composite": {}, "rank": {}, "n": {},
    }
    for dim, m in (baseline or {}).items():
        out["percentile"][dim] = m.get("percentile")
        out["tier"][dim] = m.get("tier")
        out["z_score"][dim] = m.get("z_score")
        out["composite"][dim] = m.get("composite")
        out["rank"][dim] = m.get("rank")
        out["n"][dim] = m.get("n")
    return out


def group_raw_by_student(raw: dict) -> dict:
    """班级/学校原始行 → {student_id: {corrected, reports, exam_scores, wrong_total}}。"""
    out: dict = {}

    def bucket(sid: str) -> dict:
        return out.setdefault(sid, {"corrected": [], "reports": [], "exam_scores": [], "wrong_total": 0})

    for r in raw.get("corrected") or []:
        sid = str(r.get("student_id") or "")
        if sid:
            bucket(sid)["corrected"].append(r)
    for r in raw.get("reports") or []:
        sid = str(r.get("student_id") or "")
        if sid:
            bucket(sid)["reports"].append(r)
    for r in raw.get("exam_scores") or []:
        sid = str(r.get("student_id") or "")
        if sid:
            bucket(sid)["exam_scores"].append(r)
    for sid, cnt in (raw.get("wrong_total") or {}).items():
        if sid:
            bucket(sid)["wrong_total"] = int(cnt or 0)
    return out
