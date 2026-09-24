# -*- coding: utf-8 -*-
"""批改额度 / 充值接口（0924 需求一）。

- GET  /quota/me              当前账号额度
- GET  /quota/tiers           充值档位
- GET  /admin/quota/list      管理端账号额度总览（平台管理员）
- POST /admin/quota/recharge  管理员手动加额（平台管理员）
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.grading_quota import GradingQuota, GradingQuotaRechargeLog
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services import quota_service as qs
from app.utils.school_access import is_platform_admin

router = APIRouter(tags=["quota"])


def _require_platform_admin(db: Session, user_id: str) -> User:
    u = db.query(User).filter(User.id == user_id).first()
    if not u or not is_platform_admin(u):
        raise HTTPException(status_code=403, detail="仅系统管理员/子系统管理员可操作")
    return u


@router.get("/quota/me", response_model=ApiResponse[dict])
def my_quota(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return ApiResponse(data=qs.to_usage(qs.get_quota(db, user_id)))


@router.get("/quota/tiers", response_model=ApiResponse[list])
def quota_tiers(_uid: str = Depends(get_current_user_id)):
    return ApiResponse(data=qs.QUOTA_TIERS)


@router.get("/admin/quota/list", response_model=ApiResponse[list])
def admin_quota_list(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _require_platform_admin(db, user_id)
    users = db.query(User).order_by(User.display_name, User.email).all()
    quotas = {q.user_id: q for q in db.query(GradingQuota).all()}
    result = []
    for u in users:
        q = quotas.get(u.id)
        total = int(q.total_pages or 0) if q else 0
        used = int(q.used_pages or 0) if q else 0
        roles_list = [r.strip() for r in (u.roles or "").split(",") if r.strip()]
        result.append(
            {
                "user_id": str(u.id),
                "display_name": u.display_name,
                "email": u.email,
                "roles": roles_list or None,
                "total_pages": total,
                "used_pages": used,
                "today_pages": qs.today_pages_of(q),
                "locked": qs.is_locked(total, used),
            }
        )
    return ApiResponse(data=result)


class RechargeRequest(BaseModel):
    user_id: str
    amount_yuan: int


@router.post("/admin/quota/recharge", response_model=ApiResponse[dict])
def admin_quota_recharge(
    body: RechargeRequest,
    operator_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _require_platform_admin(db, operator_id)
    target = db.query(User).filter(User.id == body.user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="目标账号不存在")
    result = qs.recharge(db, body.user_id, body.amount_yuan, operator_id=operator_id)
    db.commit()
    return ApiResponse(data=result)


def _display_name(u: Optional[User]) -> Optional[str]:
    if u is None:
        return None
    return u.display_name or u.email or str(u.id)


@router.get("/admin/quota/recharge-logs", response_model=ApiResponse[dict])
def admin_quota_recharge_logs(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    filter_user_id: Optional[str] = Query(None),
):
    """管理员查看全平台充值流水（0924 需求三：所有账号的充值记录）。

    · 平台管理员专属；按时间倒序分页，可按目标账号过滤。
    · 目标与操作员名称一起返回，便于审计「谁给谁充了多少面」。
    """
    _require_platform_admin(db, user_id)

    q = db.query(GradingQuotaRechargeLog)
    if filter_user_id:
        q = q.filter(GradingQuotaRechargeLog.user_id == filter_user_id)

    total = int(q.count())
    rows = (
        q.order_by(GradingQuotaRechargeLog.created_at.desc(), GradingQuotaRechargeLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    uids = {r.user_id for r in rows} | {r.operator_id for r in rows if r.operator_id}
    user_map: dict[str, User] = {}
    if uids:
        user_map = {u.id: u for u in db.query(User).filter(User.id.in_(uids)).all()}

    items = []
    for r in rows:
        target = user_map.get(r.user_id)
        operator = user_map.get(r.operator_id) if r.operator_id else None
        items.append(
            {
                "id": str(r.id),
                "user_id": str(r.user_id),
                "user_name": _display_name(target),
                "amount_yuan": int(r.amount_yuan or 0),
                "base_pages": int(r.base_pages or 0),
                "bonus_pages": int(r.bonus_pages or 0),
                "total_pages": int(r.total_pages or 0),
                "operator_name": _display_name(operator),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )

    return ApiResponse(data={"total": total, "page": page, "page_size": page_size, "items": items})
