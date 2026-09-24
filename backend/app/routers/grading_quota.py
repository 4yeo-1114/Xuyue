# -*- coding: utf-8 -*-
"""批改额度 / 充值接口（0924 需求一）。

- GET  /quota/me              当前账号额度
- GET  /quota/tiers           充值档位
- GET  /admin/quota/list      管理端账号额度总览（平台管理员）
- POST /admin/quota/recharge  管理员手动加额（平台管理员）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.grading_quota import GradingQuota
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
