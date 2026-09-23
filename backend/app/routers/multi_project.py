# -*- coding: utf-8 -*-
"""多项目设置 API（仅 MULTI_PROJECT_ADMIN_EMAILS 注入的管理员邮箱可写；项目名称对所有登录用户可读）。"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.multi_project_settings import (
    apply_db_profile,
    delete_db_profile,
    get_active_db_profile_summary,
    get_project_name,
    is_multi_project_admin_email,
    list_db_profiles,
    load_settings,
    set_project_name,
    test_db_connection,
    upsert_db_profile,
)

router = APIRouter(tags=["multi_project"])


class ProjectNameBody(BaseModel):
    project_name: str = Field(..., min_length=1, max_length=32)


class DbProfileBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(default=3306, ge=1, le=65535)
    user: str = Field(..., min_length=1, max_length=128)
    password: str = Field(default="")
    database: str = Field(..., min_length=1, max_length=128)


def _user_email(db: Session, user_id: str) -> str:
    email = db.query(User.email).filter(User.id == user_id).scalar()
    return (email or "").strip().lower()


def require_multi_project_admin(db: Session, user_id: str) -> str:
    email = _user_email(db, user_id)
    if not email:
        raise HTTPException(status_code=401, detail="用户不存在")
    if not is_multi_project_admin_email(email):
        raise HTTPException(status_code=403, detail="无权访问多项目设置")
    return email


@router.get("/branding")
def api_public_branding():
    """登录页/全站品牌名（无需登录）。"""
    return {
        "project_name": get_project_name(),
    }


@router.get("/multi-project/access")
def api_multi_project_access(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    email = _user_email(db, user_id)
    return {"allowed": is_multi_project_admin_email(email)}


@router.get("/multi-project/settings", response_model=ApiResponse[dict])
def api_get_multi_project_settings(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_multi_project_admin(db, user_id)
    data = load_settings()
    return ApiResponse(
        data={
            "project_name": get_project_name(),
            "active_db_profile_id": data.get("active_db_profile_id"),
            "active_db_profile": get_active_db_profile_summary(),
            "db_profiles": list_db_profiles(mask_secret=True),
            "updated_at": data.get("updated_at"),
        }
    )


@router.put("/multi-project/project-name", response_model=ApiResponse[dict])
def api_update_project_name(
    body: ProjectNameBody,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_multi_project_admin(db, user_id)
    try:
        name = set_project_name(body.project_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ApiResponse(data={"project_name": name})


@router.post("/multi-project/db-profiles", response_model=ApiResponse[dict])
def api_create_db_profile(
    body: DbProfileBody,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_multi_project_admin(db, user_id)
    try:
        ok, msg = test_db_connection(body.host, body.port, body.user, body.password, body.database)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        profile = upsert_db_profile(
            profile_id=None,
            name=body.name,
            host=body.host,
            port=body.port,
            user=body.user,
            password=body.password,
            database=body.database,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ApiResponse(data=profile)


@router.put("/multi-project/db-profiles/{profile_id}", response_model=ApiResponse[dict])
def api_update_db_profile(
    profile_id: str,
    body: DbProfileBody,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_multi_project_admin(db, user_id)
    data = load_settings()
    existing = next((p for p in data.get("db_profiles") or [] if str(p.get("id")) == profile_id), None)
    if not existing:
        raise HTTPException(status_code=404, detail="配置项不存在")
    password = body.password.strip() or str(existing.get("password") or "")
    try:
        ok, msg = test_db_connection(body.host, body.port, body.user, password, body.database)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        profile = upsert_db_profile(
            profile_id=profile_id,
            name=body.name,
            host=body.host,
            port=body.port,
            user=body.user,
            password=password,
            database=body.database,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ApiResponse(data=profile)


@router.delete("/multi-project/db-profiles/{profile_id}", response_model=ApiResponse[dict])
def api_delete_db_profile(
    profile_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_multi_project_admin(db, user_id)
    try:
        delete_db_profile(profile_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ApiResponse(data={"deleted": profile_id})


@router.post("/multi-project/db-profiles/{profile_id}/apply", response_model=ApiResponse[dict])
def api_apply_db_profile(
    profile_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_multi_project_admin(db, user_id)
    try:
        result = apply_db_profile(profile_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ApiResponse(data=result)
