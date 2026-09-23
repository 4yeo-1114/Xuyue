"""
智育事件目录（event_catalog）—— 评分口径的唯一事实来源（A0 §3 映射）。

7 个事件：
  1. wrong_question_corrected  错题订正     +1（cap 30）
  2. exam_rank_up              成绩排名提升 +2（cap 15）
  3. targeted_report           靶向提升报告 +1（cap 8）
  4. manual_growth             手动成长记录  ±N（无 cap，原样计分）
  5. above_class_avg           超班级均分   +2（无 cap）
  6. correction_rate_high      订正率达标   +3（cap 1）
  7. weak_point_conquered      薄弱点攻克   +2（cap 10）

时间衰减：w = e^(-Δt/τ)，τ 默认 90 天（ASSESSMENT_DECAY_TAU_DAYS 环境变量可配）。
本模块同时提供学期边界推导（cap_per_term 需要按当前学期切分）。
"""
from __future__ import annotations

import datetime
import math
import os
from typing import Optional

# 默认时间衰减半衰期（天）：事件越久权重越低。w = e^(-Δt/τ)
DEFAULT_DECAY_TAU_DAYS = 90.0

# 画像输出维度（五育 + AI 素养，对齐教基〔2021〕3号五方面 + 2024 教基厅函 32 号 AI 素养）。
# 这是全链路维度枚举的唯一事实来源：assessment_engine / repository / 班级·学期报告共用。
# ai_literacy 为增量维度：旧数据缺省按 0 处理，聚合/返回不报错。
DIMENSIONS = ("moral", "intellectual", "physical", "aesthetic", "labor", "ai_literacy")

# AI 课程成果成长记录 source_type（E02，走现有 growth 写入链路，复用幂等逻辑）
AI_SOURCE_TYPES = ("ai_course", "ai_project")

# ── 智育事件目录（口径唯一事实来源）──────────────────
EVENT_CATALOG: dict[str, dict] = {
    "wrong_question_corrected": {
        "event_type": "wrong_question_corrected",
        "name": "错题订正",
        "dimension": "intellectual",
        "weight": 1,
        "cap_per_term": 30,
        "enabled": True,
        "source": "wrong_question",
        "description": "错题订正（status='corrected'），每条 +1",
    },
    "exam_rank_up": {
        "event_type": "exam_rank_up",
        "name": "成绩排名提升",
        "dimension": "intellectual",
        "weight": 2,
        "cap_per_term": 15,
        "enabled": True,
        "source": "exam_score",
        "description": "同科成绩 class_rank 相比上次提升，每次 +2",
    },
    "targeted_report": {
        "event_type": "targeted_report",
        "name": "靶向提升报告",
        "dimension": "intellectual",
        "weight": 1,
        "cap_per_term": 8,
        "enabled": True,
        "source": "targeted_improvement_report",
        "description": "AI 靶向提升报告生成，每份 +1",
    },
    "manual_growth": {
        "event_type": "manual_growth",
        "name": "手动成长记录",
        "dimension": "any",
        "weight": None,  # 原样计分（growth_points 字段决定，可为负）
        "cap_per_term": None,
        "enabled": True,
        "source": "student_growth_record",
        "description": "成长流水（五育通用），按 growth_points 计分",
    },
    "above_class_avg": {
        "event_type": "above_class_avg",
        "name": "超班级均分",
        "dimension": "intellectual",
        "weight": 2,
        "cap_per_term": None,  # 用户拍板：不设 cap
        "enabled": True,
        "source": "exam_score",
        "description": "单科成绩高于该班均分，每科次 +2",
    },
    "correction_rate_high": {
        "event_type": "correction_rate_high",
        "name": "订正率达标",
        "dimension": "intellectual",
        "weight": 3,
        "cap_per_term": 1,  # 达标即一次性，每学期最多 1 次
        "enabled": True,
        "source": "wrong_question",
        "description": "该生订正率（已订正/总错题）≥80%，+3/学期",
    },
    "weak_point_conquered": {
        "event_type": "weak_point_conquered",
        "name": "薄弱点攻克",
        "dimension": "intellectual",
        "weight": 2,
        "cap_per_term": 10,
        "enabled": True,
        "source": "wrong_question",
        "description": "某 knowledge_point 从错到订正（被攻克），按知识点去重，每个 +2",
    },
}


def get_catalog() -> dict[str, dict]:
    """返回完整事件目录（防御性拷贝，防调用方误改全局）。"""
    return {k: dict(v) for k, v in EVENT_CATALOG.items()}


def event_config(event_type: str) -> dict:
    """取单个事件配置；不存在返回空 dict（调用方按禁用处理）。"""
    return EVENT_CATALOG.get(event_type) or {}


def enabled_events(dimension: str = None) -> list[dict]:
    """返回启用的事件列表；dimension 给定时只返回该维事件（'any' 视为全部维度）。"""
    out = []
    for cfg in EVENT_CATALOG.values():
        if not cfg.get("enabled"):
            continue
        if dimension and cfg.get("dimension") not in (dimension, "any"):
            continue
        out.append(dict(cfg))
    return out


def is_event_enabled(event_type: str) -> bool:
    """事件是否启用（不存在或 enabled=false → 不计分）。"""
    return bool(EVENT_CATALOG.get(event_type, {}).get("enabled"))


def get_tau_days() -> float:
    """时间衰减 τ（天），可经环境变量 ASSESSMENT_DECAY_TAU_DAYS 覆盖。"""
    raw = os.environ.get("ASSESSMENT_DECAY_TAU_DAYS", "").strip()
    try:
        return float(raw) if raw else DEFAULT_DECAY_TAU_DAYS
    except (TypeError, ValueError):
        return DEFAULT_DECAY_TAU_DAYS


def as_dt(value) -> Optional[datetime.datetime]:
    """把 DB 返回的 datetime / date / 字符串统一成 timezone-aware UTC datetime。

    注：exams.exam_date 是 DATE 列，pymysql 返回 datetime.date（无 tzinfo 且不支持
    replace(tzinfo=...)），需先转成 datetime 再补 UTC。
    """
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=datetime.timezone.utc)
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime(value.year, value.month, value.day,
                                 tzinfo=datetime.timezone.utc)
    try:
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def decay_weight(occurred_at, now: datetime.datetime = None, tau_days: float = None) -> float:
    """时间衰减权重 w = e^(-Δt/τ)。空时间按 Δt=0（权重 1）。"""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    tau_days = tau_days if tau_days is not None else get_tau_days()
    ts = as_dt(occurred_at)
    if ts is None:
        return 1.0
    dt_days = (now - ts).total_seconds() / 86400.0
    if dt_days < 0:
        return 1.0
    if tau_days <= 0:
        return 1.0
    return math.exp(-dt_days / tau_days)


def current_term_bounds(now: datetime.datetime = None) -> tuple[datetime.datetime, datetime.datetime]:
    """推导"当前学年-学期"的起止边界（cap_per_term 切分用）。

    约定：
      - 上学期：9/1 ~ 次年 1/31
      - 下学期：2/1 ~ 当年 7/31
      - 8 月为暑假，归入新学年上学期（2026-08 → 2026-2027-1）。
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    tz = datetime.timezone.utc
    y, m = now.year, now.month
    if m == 8:
        return (
            datetime.datetime(y, 9, 1, tzinfo=tz),
            datetime.datetime(y + 1, 1, 31, 23, 59, 59, tzinfo=tz),
        )
    if 9 <= m <= 12 or m == 1:
        y1 = y if m >= 9 else y - 1
        return (
            datetime.datetime(y1, 9, 1, tzinfo=tz),
            datetime.datetime(y1 + 1, 1, 31, 23, 59, 59, tzinfo=tz),
        )
    y1 = y if m >= 2 else y - 1
    return (
        datetime.datetime(y1, 2, 1, tzinfo=tz),
        datetime.datetime(y1, 7, 31, 23, 59, 59, tzinfo=tz),
    )
