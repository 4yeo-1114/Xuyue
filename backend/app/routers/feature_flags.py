# -*- coding: utf-8 -*-
"""E08 · 学校级 AI 管控：AI 功能开关接口（后端 MySQL feature_flags 为唯一事实源）。

契约（前后端锁定，勿改字段名）：
  - GET   /feature-flags           → ApiResponse(data=[{key,label,enabled,scope,scope_id}])，登录用户可读，按 key 排序
  - PATCH /feature-flags/{key}     body {enabled: bool} → ApiResponse(data={key,enabled})，仅系统管理员/子系统管理员/校级管理者
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.feature_flag import FeatureFlag
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.feature_flags import FeatureFlagOut, UpdateFeatureFlagRequest

router = APIRouter(prefix="/feature-flags", tags=["feature-flags"])

# 管理员角色：与 system_settings._is_admin 保持一致，并额外纳入「校级管理者」
#（学校级 AI 管控主体是校级管理者，给权更稳）。
_ADMIN_ROLES = frozenset({"系统管理员", "子系统管理员", "校级管理者"})


def _user_roles(user: User) -> List[str]:
    roles_str = getattr(user, "roles", None) or ""
    return [r.strip() for r in roles_str.split(",") if r.strip()]


def _is_admin(roles: List[str]) -> bool:
    return bool(set(roles) & _ADMIN_ROLES)


def _flag_out(row: FeatureFlag) -> FeatureFlagOut:
    return FeatureFlagOut(
        key=row.key,
        label=row.label,
        enabled=bool(row.enabled),
        scope=row.scope,
        scope_id=row.scope_id,
    )


@router.get("", response_model=ApiResponse[List[FeatureFlagOut]])
def list_feature_flags(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    rows = db.query(FeatureFlag).order_by(FeatureFlag.key.asc()).all()
    return ApiResponse(data=[_flag_out(row) for row in rows])


@router.patch("/{key}", response_model=ApiResponse[dict])
def update_feature_flag(
    key: str,
    body: UpdateFeatureFlagRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    roles = _user_roles(user)
    if not _is_admin(roles):
        raise HTTPException(status_code=403, detail="无权限修改 AI 功能开关")
    row = db.query(FeatureFlag).filter(FeatureFlag.key == key).first()
    if not row:
        raise HTTPException(status_code=404, detail="功能开关不存在")
    row.enabled = body.enabled
    row.updated_by = user_id
    db.commit()
    db.refresh(row)
    return ApiResponse(data={"key": row.key, "enabled": bool(row.enabled)})
