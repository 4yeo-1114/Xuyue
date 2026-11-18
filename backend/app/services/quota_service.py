# -*- coding: utf-8 -*-
"""批改额度服务：计面、105% 硬停（口径：1 张上传图/页 = 1 面）。

- 计数：每上传一张学生试卷图 = 1 面；标准答案/原始试卷不占额度。
- 硬停：total_pages > 0 且 used_pages >= total_pages * 105% 时锁定。
（充值/档位/支付桥 20261111 随「余额/充值/支付整体移除」删掉。）
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.grading_quota import GradingQuota

logger = logging.getLogger(__name__)


def is_locked(total_pages: int, used_pages: int) -> bool:
    """是否触发 105% 硬停。total_pages<=0 视为无限额，不锁定。"""
    if total_pages <= 0:
        return False
    return used_pages * 100 >= total_pages * 105


def get_quota(db: Session, user_id: str) -> Optional[GradingQuota]:
    return db.query(GradingQuota).filter(GradingQuota.user_id == user_id).first()


def get_or_create_quota(db: Session, user_id: str) -> GradingQuota:
    q = get_quota(db, user_id)
    if q is None:
        q = GradingQuota(user_id=user_id, total_pages=0, used_pages=0, used_today_pages=0)
        db.add(q)
        db.flush()
    return q


def today_pages_of(q: Optional[GradingQuota]) -> int:
    if q is None:
        return 0
    if q.usage_date != date.today():
        return 0
    return int(q.used_today_pages or 0)


def to_usage(q: Optional[GradingQuota]) -> dict:
    total = int(q.total_pages or 0) if q else 0
    used = int(q.used_pages or 0) if q else 0
    available = total - used
    used_pct = round(used / total * 100, 2) if total > 0 else 0.0
    return {
        "total_pages": total,
        "used_pages": used,
        "available": available,
        "used_pct": used_pct,
        "locked": is_locked(total, used),
        "today_pages": today_pages_of(q),
    }


def _is_reference_filename(filename: str) -> bool:
    """标准答案 / 原始试卷不占额度。"""
    stem = Path(str(filename or "")).stem
    return (
        stem == "标准答案"
        or stem.startswith("标准答案_")
        or stem == "原始试卷"
        or stem.startswith("原始试卷_")
    )


def add_usage(user_id: str, pages: int = 1) -> None:
    """扣减额度：+pages 面。使用独立会话，可在批改旁路安全调用。"""
    uid = str(user_id or "").strip()
    if not uid:
        return
    pages = max(1, int(pages or 1))
    db = SessionLocal()
    try:
        q = get_or_create_quota(db, uid)
        today = date.today()
        if q.usage_date != today:
            q.used_today_pages = 0
            q.usage_date = today
        q.used_today_pages = int(q.used_today_pages or 0) + pages
        q.used_pages = int(q.used_pages or 0) + pages
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def record_page(user_id: str, filename: str, pages: int = 1) -> None:
    """按文件名扣额度：标准答案/原始试卷跳过。"""
    if _is_reference_filename(filename):
        return
    add_usage(user_id, pages)


def refund_page(user_id: str, filename: str, pages: int = 1) -> None:
    """退还额度：按文件名退（标准答案/原始试卷跳过），下限 0。

    11.9-4 取消扫描清残留：取消的批次不该扣老师的面数，删掉的文件把已扣的退回。
    """
    if _is_reference_filename(filename):
        return
    uid = str(user_id or "").strip()
    if not uid:
        return
    pages = max(1, int(pages or 1))
    db = SessionLocal()
    try:
        q = get_or_create_quota(db, uid)
        q.used_today_pages = max(0, int(q.used_today_pages or 0) - pages)
        q.used_pages = max(0, int(q.used_pages or 0) - pages)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def is_user_locked(user_id: str) -> bool:
    uid = str(user_id or "").strip()
    if not uid:
        return False
    db = SessionLocal()
    try:
        q = get_quota(db, uid)
        if q is None:
            return False
        return is_locked(int(q.total_pages or 0), int(q.used_pages or 0))
    except Exception:
        return False
    finally:
        db.close()


def ensure_user_available(user_id: str) -> None:
    """105% 硬停：超限抛 403。"""
    if is_user_locked(user_id):
        raise HTTPException(
            status_code=403,
            detail="批改额度已用尽（已超总量 105%），请联系管理员",
        )

