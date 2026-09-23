from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.system_settings import SystemSettings
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.system_settings import (
    SystemSettingsOut,
    UpdateBaiduAccessTokenRequest,
    UpdateBaiduCredentialsRequest,
    UpdateQwenSettingsRequest,
)
from app.utils.qwen_settings import DEFAULT_QWEN_MODEL, get_qwen_config, mask_secret


router = APIRouter(prefix="/system-settings", tags=["system-settings"])


def _get_or_create_settings(db: Session) -> SystemSettings:
    row = db.query(SystemSettings).first()
    if row:
        return row
    row = SystemSettings(system_email=None, baidu_access_token=None, qwen_model=DEFAULT_QWEN_MODEL)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _user_roles(user: User) -> List[str]:
    roles_str = getattr(user, "roles", None) or ""
    return [r.strip() for r in roles_str.split(",") if r.strip()]


def _is_admin(roles: List[str]) -> bool:
    return ("系统管理员" in roles) or ("子系统管理员" in roles)


def _mask_token(tok: str) -> str:
    return mask_secret(tok)


def _settings_out(row: SystemSettings, admin: bool, db: Session) -> SystemSettingsOut:
    masked = _mask_token(row.baidu_access_token or "") if admin and (row.baidu_access_token or "").strip() else None
    baidu_api_key = (getattr(row, "baidu_api_key", None) or "").strip()
    baidu_secret_key = (getattr(row, "baidu_secret_key", None) or "").strip()
    qwen_key, qwen_model = get_qwen_config(db)
    qwen_masked = mask_secret(qwen_key) if admin and qwen_key else None
    return SystemSettingsOut(
        can_edit_access_token=admin,
        access_token_masked=masked,
        baidu_api_key_masked=_mask_token(baidu_api_key) if admin and baidu_api_key else None,
        baidu_secret_key_masked=_mask_token(baidu_secret_key) if admin and baidu_secret_key else None,
        baidu_auto_refresh_configured=bool(baidu_api_key and baidu_secret_key),
        qwen_api_key_masked=qwen_masked,
        qwen_model=qwen_model or DEFAULT_QWEN_MODEL,
    )


@router.get("", response_model=ApiResponse[SystemSettingsOut])
def get_system_settings(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    roles = _user_roles(user)
    admin = _is_admin(roles)
    row = _get_or_create_settings(db)
    return ApiResponse(data=_settings_out(row, admin, db))


@router.patch("/baidu-access-token", response_model=ApiResponse[SystemSettingsOut])
def update_baidu_access_token(
    body: UpdateBaiduAccessTokenRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    roles = _user_roles(user)
    if not _is_admin(roles):
        raise HTTPException(status_code=403, detail="无权限修改 access_token")
    token = (body.access_token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="access_token 不能为空")
    row = _get_or_create_settings(db)
    row.baidu_access_token = token
    row.updated_by = user_id
    db.commit()
    db.refresh(row)
    from app.grading.baidu_grading import invalidate_baidu_auth_cache

    invalidate_baidu_auth_cache()
    return ApiResponse(data=_settings_out(row, True, db))


@router.patch("/baidu-credentials", response_model=ApiResponse[SystemSettingsOut])
def update_baidu_credentials(
    body: UpdateBaiduCredentialsRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    roles = _user_roles(user)
    if not _is_admin(roles):
        raise HTTPException(status_code=403, detail="无权限修改百度鉴权配置")

    row = _get_or_create_settings(db)
    api_key = (body.api_key or "").strip() or (getattr(row, "baidu_api_key", None) or "").strip()
    secret_key = (body.secret_key or "").strip() or (getattr(row, "baidu_secret_key", None) or "").strip()
    if not api_key or not secret_key:
        raise HTTPException(status_code=400, detail="百度 API Key 和 Secret Key 必须同时配置")

    from app.grading.baidu_grading import (
        invalidate_baidu_auth_cache,
        request_baidu_access_token,
    )

    try:
        access_token, _expires_in = request_baidu_access_token(api_key, secret_key)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row.baidu_api_key = api_key
    row.baidu_secret_key = secret_key
    row.baidu_access_token = access_token
    row.updated_by = user_id
    db.commit()
    db.refresh(row)
    invalidate_baidu_auth_cache()
    return ApiResponse(data=_settings_out(row, True, db))


@router.patch("/qwen", response_model=ApiResponse[SystemSettingsOut])
def update_qwen_settings(
    body: UpdateQwenSettingsRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    roles = _user_roles(user)
    if not _is_admin(roles):
        raise HTTPException(status_code=403, detail="无权限修改千问配置")

    row = _get_or_create_settings(db)
    api_key = (body.api_key or "").strip()
    model = (body.model or DEFAULT_QWEN_MODEL).strip() or DEFAULT_QWEN_MODEL
    if api_key:
        row.dashscope_api_key = api_key
    elif not (row.dashscope_api_key or "").strip():
        raise HTTPException(status_code=400, detail="千问 API Key 不能为空")

    row.qwen_model = model[:64]
    row.updated_by = user_id
    db.commit()
    db.refresh(row)
    return ApiResponse(data=_settings_out(row, True, db))
