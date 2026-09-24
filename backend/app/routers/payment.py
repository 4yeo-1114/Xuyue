# -*- coding: utf-8 -*-
"""口径 B · 支付路由（**只读账单投影**，Phase 0 = P0-6）。

设计依据：docs/payment/payment-design.md §7.3。

物理分离（§7.3 逐字）：⛔ `routers/scan_billing.py` 的 9 个只读端点一个都不改 ——
它们**不是**本模块的数据源；两套端点、两套数据源并存。
本模块的数据源：`payment_accounts` + `ledger_entries` + `usage_events`（口径 B 自己的表）。

本批只实现 P0-6 的 3 个端点：
  GET /api/v1/payment/account   我的余额（分）+ 状态
  GET /api/v1/payment/ledger    我的资金流水（分页）
  GET /api/v1/payment/usage     我的用量（口径 B）
⛔ `POST /payment/orders`、`POST /payment/callback/{channel}`、`POST /payment/admin/grant`
   属 Phase 2（依赖 §2 通道），本批不写。

⚠️ 越权（§12 第 6 条）：本模块**不接 `user_id` query 参数**，一律用 JWT 里的身份 ——
「余额/流水/账单天生强隐私」，必须自己收一道「只能查自己」，⛔ 不照抄 `scan_billing` 的
`user_id: Optional[str] = Query(None)` 范式。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.ledger_entry import LedgerEntry
from app.models.usage_event import UsageEvent
from app.schemas.common import ApiResponse
from app.schemas.payment import LedgerEntryOut, LedgerPageOut, PaymentAccountOut, UsageOut
from app.services.payment import ledger as ledger_svc

router = APIRouter(prefix="/payment", tags=["payment"])

_MAX_PAGE_SIZE = 200


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


@router.get("/account", response_model=ApiResponse[PaymentAccountOut])
def api_get_my_account(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """我的余额（分）+ 状态。账户惰性创建（§8.1）。"""
    acct = ledger_svc.get_or_create_account(db, user_id)
    return ApiResponse(
        data=PaymentAccountOut(
            user_id=acct.user_id,
            balance_fen=int(acct.balance_fen or 0),
            total_recharged_fen=int(acct.total_recharged_fen or 0),
            total_consumed_fen=int(acct.total_consumed_fen or 0),
            status=acct.status,
            created_at=_iso(acct.created_at),
            updated_at=_iso(acct.updated_at),
        )
    )


@router.get("/ledger", response_model=ApiResponse[LedgerPageOut])
def api_list_my_ledger(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=_MAX_PAGE_SIZE),
    entry_type: Optional[str] = Query(None),
):
    """我的资金流水（分页，倒序）。⛔ 只能查自己（无 user_id 入参）。"""
    acct = ledger_svc.get_or_create_account(db, user_id)
    q = db.query(LedgerEntry).filter(LedgerEntry.account_id == acct.id)
    if entry_type:
        q = q.filter(LedgerEntry.entry_type == str(entry_type).strip())
    total = int(q.with_entities(func.count(LedgerEntry.id)).scalar() or 0)
    rows = (
        q.order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ApiResponse(
        data=LedgerPageOut(
            total=total,
            page=page,
            page_size=page_size,
            items=[
                LedgerEntryOut(
                    id=r.id,
                    entry_type=r.entry_type,
                    amount_fen=int(r.amount_fen or 0),
                    balance_after_fen=int(r.balance_after_fen or 0),
                    description=r.description,
                    created_at=_iso(r.created_at),
                )
                for r in rows
            ],
        )
    )


@router.get("/usage", response_model=ApiResponse[UsageOut])
def api_get_my_usage(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
    limit: int = Query(50, ge=1, le=_MAX_PAGE_SIZE),
):
    """我的用量（**口径 B**：`usage_events` 净额，⛔ 非口径 A 的 `grading_daily_stats`）。"""
    per_kind = (
        db.query(UsageEvent.kind, func.coalesce(func.sum(UsageEvent.delta), 0))
        .filter(UsageEvent.user_id == user_id)
        .group_by(UsageEvent.kind)
        .all()
    )
    totals: dict[str, int] = {str(k): int(v or 0) for k, v in per_kind}

    per_folder = (
        db.query(
            UsageEvent.kind,
            UsageEvent.folder_safe,
            func.coalesce(func.sum(UsageEvent.delta), 0),
        )
        .filter(UsageEvent.user_id == user_id)
        .group_by(UsageEvent.kind, UsageEvent.folder_safe)
        .all()
    )
    folders = [
        {"kind": str(k), "folder_safe": str(f), "net": int(v or 0)}
        for k, f, v in per_folder
        if int(v or 0) != 0
    ]

    recent_rows = (
        db.query(UsageEvent)
        .filter(UsageEvent.user_id == user_id)
        .order_by(UsageEvent.occurred_at.desc(), UsageEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    recent = [
        {
            "kind": r.kind,
            "folder_safe": r.folder_safe,
            "subject_key": r.subject_key,
            "net": int(r.delta or 0),
        }
        for r in recent_rows
    ]

    return ApiResponse(
        data=UsageOut(
            total_grade=int(totals.get("grade", 0)),
            total_upload=int(totals.get("upload", 0)),
            folders=folders,
            recent=recent,
        )
    )


# ⛔ `POST /payment/orders`、`POST /payment/callback/{channel}`、`POST /payment/admin/grant`
#    属 Phase 2（依赖 §2 通道适配层）—— 本批**一个都不写**，连 501 桩都不留（越界）。
