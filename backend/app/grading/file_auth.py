# -*- coding: utf-8 -*-
"""从请求中解析当前用户（Authorization Header 或短时下载票，供图片等资源访问）。

H2：不再支持 URL 携带长期 JWT access_token（会泄漏到日志/Referer）。
文件直链统一使用 create_download_ticket 生成的短时下载票（绑定 user+resource，默认 10 分钟过期）。
"""
from __future__ import annotations

from fastapi import HTTPException, Request

from app.utils.security import decode_access_token, verify_download_ticket


def user_id_from_request(request: Request, resource: str = "") -> str:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        user_id = decode_access_token(auth[7:].strip())
        if user_id:
            return user_id
    # 短时下载票：必须绑定当前请求的 resource 路径
    ticket = request.query_params.get("ticket")
    if ticket:
        user_id = verify_download_ticket(ticket, resource)
        if user_id:
            return user_id
    raise HTTPException(status_code=401, detail="未登录")
