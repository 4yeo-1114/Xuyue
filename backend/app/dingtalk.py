# -*- coding: utf-8 -*-
"""钉钉免登：authCode 换 userid → 匹配叙阅账号 → 发自己的 JWT"""
import time
import threading
import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.utils.security import create_access_token
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/auth", tags=["dingtalk"])

_DING_BASE = "https://oapi.dingtalk.com"
_lock = threading.Lock()
_cache = {"token": None, "expire_at": 0.0}


def _ding_token() -> str:
    """拿钉钉的通行证（access_token），自动缓存、提前 5 分钟刷新。"""
    app_key = (settings.DINGTALK_APP_KEY or "").strip()
    app_secret = (settings.DINGTALK_APP_SECRET or "").strip()
    if not app_key or not app_secret:
        raise RuntimeError("未配置 DINGTALK_APP_KEY / DINGTALK_APP_SECRET")

    with _lock:
        now = time.time()
        if _cache["token"] and now < _cache["expire_at"] - 300:
            return _cache["token"]
        r = requests.get(
            f"{_DING_BASE}/gettoken",
            params={"appkey": app_key, "appsecret": app_secret},
            timeout=10,
        ).json()
        if r.get("errcode") != 0:
            raise RuntimeError(f"拿钉钉通行证失败：{r.get('errcode')} {r.get('errmsg')}")
        _cache["token"] = r["access_token"]
        _cache["expire_at"] = now + int(r.get("expires_in") or 7200)
        return _cache["token"]


class DingLoginBody(BaseModel):
    code: str


@router.post("/dingtalk-login", response_model=ApiResponse[dict])
def dingtalk_login(body: DingLoginBody, db: Session = Depends(get_db)):
    """前端在钉钉里拿到 code → 这里换身份 → 发叙阅自己的令牌。"""
    code = (body.code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="缺少免登授权码")

    # 1) 用 code 换「这个人是谁」
    try:
        r = requests.post(
            f"{_DING_BASE}/topapi/v2/user/getuserinfo",
            params={"access_token": _ding_token()},
            json={"code": code},
            timeout=10,
        ).json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"调用钉钉失败：{e}")

    if r.get("errcode") != 0:
        # 40078 = code 过期或已用过
        raise HTTPException(
            status_code=401,
            detail=f"钉钉免登失败 {r.get('errcode')}: {r.get('errmsg')}",
        )
    info = r.get("result") or {}
    ding_userid = info.get("userid") or ""
    ding_name = info.get("name") or ""
    ding_mobile = info.get("mobile") or ""

    # 2) 在叙阅里找这个人：优先 userid 绑定，再手机号，最后姓名兜底
    user = None
    if ding_userid:
        user = db.query(User).filter(User.dingtalk_userid == ding_userid).first()
    if not user and ding_mobile:
        user = db.query(User).filter(User.phone == ding_mobile).first()
    if not user and ding_name:
        hits = db.query(User).filter(User.display_name == ding_name).all()
        if len(hits) == 1:      # 只有唯一匹配才认，避免重名串号
            user = hits[0]

    if not user:
        raise HTTPException(
            status_code=403,
            detail=(
                f"钉钉免登未匹配：钉钉返回 姓名={ding_name!r}、手机号={ding_mobile!r}、"
                f"userid={ding_userid!r}。"
                f"请在叙阅后台把对应账号绑定该钉钉 userid（dingtalk_userid 字段）"
            ),
        )

    # 3) 发叙阅自己的令牌（后面所有请求都只认它，不再用钉钉信息）
    token = create_access_token(user.id)
    return ApiResponse(data={
        "access_token": token,
        "user": {"id": user.id, "email": user.email, "display_name": user.display_name},
    })
