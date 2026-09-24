# -*- coding: utf-8 -*-
"""批改额度服务：档位、扣减、105% 硬停（口径：1 张上传图/页 = 1 面）。

- 计数：每上传一张学生试卷图 = 1 面；标准答案/原始试卷不占额度。
- 硬停：total_pages > 0 且 used_pages >= total_pages * 105% 时锁定。
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.grading_quota import GradingQuota, GradingQuotaRechargeLog

logger = logging.getLogger(__name__)

# 充值档位：100→300、500→1600、1000→3300、2000→7500、5000→20000
QUOTA_TIERS: list[dict] = [
    {"amount_yuan": 100, "base_pages": 300, "bonus_pages": 0, "total_pages": 300},
    {"amount_yuan": 500, "base_pages": 1500, "bonus_pages": 100, "total_pages": 1600},
    {"amount_yuan": 1000, "base_pages": 3000, "bonus_pages": 300, "total_pages": 3300},
    {"amount_yuan": 2000, "base_pages": 6000, "bonus_pages": 1500, "total_pages": 7500},
    {"amount_yuan": 5000, "base_pages": 15000, "bonus_pages": 5000, "total_pages": 20000},
]


def tier_by_amount(amount_yuan: int) -> Optional[dict]:
    return next((t for t in QUOTA_TIERS if t["amount_yuan"] == amount_yuan), None)


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
            detail="批改额度已用尽（已超总量 105%），请联系管理员充值",
        )


def recharge(
    db: Session,
    user_id: str,
    amount_yuan: int,
    operator_id: Optional[str] = None,
) -> dict:
    """管理员手动加额，返回充值结果。档位无效时抛 400。"""
    tier = tier_by_amount(amount_yuan)
    if tier is None:
        raise HTTPException(status_code=400, detail="无效的充值档位")
    q = get_or_create_quota(db, user_id)
    q.total_pages = int(q.total_pages or 0) + tier["total_pages"]
    db.add(
        GradingQuotaRechargeLog(
            user_id=user_id,
            amount_yuan=tier["amount_yuan"],
            base_pages=tier["base_pages"],
            bonus_pages=tier["bonus_pages"],
            total_pages=tier["total_pages"],
            operator_id=operator_id,
        )
    )
    db.flush()
    return {
        "ok": True,
        "base_pages": tier["base_pages"],
        "bonus_pages": tier["bonus_pages"],
        "total_pages": tier["total_pages"],
        "new_total": int(q.total_pages or 0),
    }


def credit_from_payment(
    db: Session,
    *,
    user_id: str,
    order_id: str,
    amount_yuan: int,
) -> Optional[dict]:
    """支付桥：通道确认收款后按档位加面（同事支付系统 → 我的额度体系）。

    幂等：`GradingQuotaRechargeLog.source_order_id` 唯一约束兜底 —— 同一订单重复回调
    只加一次面（与账本侧 `pay-confirm|{order_id}` 的幂等语义对齐，两层各自独立兜底）。
    非档位金额：记 error 不加面（需人工核查），分账本那边仍按实收入账、不受影响。
    """
    oid = str(order_id or "").strip()
    if not oid:
        return None
    tier = tier_by_amount(int(amount_yuan or 0))
    if tier is None:
        logger.error(
            "支付确认金额非充值档位，不加面（需人工核查）：order_id=%s amount_yuan=%s",
            oid,
            amount_yuan,
        )
        return None
    # 幂等快路径：同订单已加过面 ⇒ 直接返回
    already = (
        db.query(GradingQuotaRechargeLog)
        .filter(GradingQuotaRechargeLog.source_order_id == oid)
        .first()
    )
    if already is not None:
        return None
    q = get_or_create_quota(db, user_id)
    q.total_pages = int(q.total_pages or 0) + tier["total_pages"]
    db.add(
        GradingQuotaRechargeLog(
            user_id=str(user_id).strip(),
            amount_yuan=tier["amount_yuan"],
            base_pages=tier["base_pages"],
            bonus_pages=tier["bonus_pages"],
            total_pages=tier["total_pages"],
            operator_id=None,
            source_order_id=oid,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # 并发/重复投递：唯一约束冲突 ⇒ 已加过面，回滚（不重复加）
        db.rollback()
        return None
    return {
        "ok": True,
        "total_pages": tier["total_pages"],
        "new_total": int(q.total_pages or 0),
    }
