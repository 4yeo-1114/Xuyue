# -*- coding: utf-8 -*-
"""E08 · 学校级 AI 管控统一层。

统一闸门：功能开关（feature_flags，后端 MySQL 为唯一事实源） + 角色白名单 + 敏感输入拦截。

管控聚焦：功能开关 + 角色 + 敏感输入 + PII。
「防直接复制 AI 作答」本批不做代码拦截（前端 CSS user-select 留后续批次），仅在头注释标注。

各 AI 端点关掉时返回 403，detail 提示「该 AI 功能已由学校/系统关闭」。
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.feature_flag import FeatureFlag
from app.services.ai_chat_access import parse_user_roles
from app.services.ai_chat_privacy import looks_like_user_account_privacy_question

# AI 可用角色白名单：学校/系统管理员 + 教学岗（班主任/副班主任/任课教师/协作教师）。
# 复用 ai_chat_access.parse_user_roles 的角色解析；角色集参考 app/utils/class_access.py。
AI_ALLOWED_ROLES: frozenset[str] = frozenset({
    "系统管理员",
    "子系统管理员",
    "校级管理者",
    "班主任",
    "副班主任",
    "任课教师",
    "协作教师",
})

FEATURE_DISABLED_DETAIL = "该 AI 功能已由学校/系统关闭"

# ── 敏感输入正则：中国大陆身份证号（15/18 位）+ 手机号（1 开头 11 位）────────
_ID_CARD_15 = re.compile(r"(?<!\d)\d{15}(?!\d)")
_ID_CARD_18 = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")


def is_feature_enabled(db: Session, key: str) -> bool:
    """feature_flags[key].enabled 是否开启。

    表不存在或行缺失 → 默认 True 放行，避免迁移前环境（AUTO_DDL=false 未建表）全 403。
    """
    try:
        row = db.query(FeatureFlag).filter(FeatureFlag.key == key).first()
    except Exception:  # noqa: BLE001 - 表缺失/连接异常时降级放行
        return True
    if row is None:
        return True
    return bool(row.enabled)


def require_ai_access(db: Session, user_id: str, key: str) -> None:
    """统一 AI 访问闸门：功能开关关闭或角色不在白名单 → 403。"""
    if not is_feature_enabled(db, key):
        raise HTTPException(status_code=403, detail=FEATURE_DISABLED_DETAIL)
    roles = parse_user_roles(db, user_id)
    if not (set(roles) & AI_ALLOWED_ROLES):
        raise HTTPException(status_code=403, detail="当前账号无权使用该 AI 功能")


def assert_no_sensitive_input(text: Optional[str]) -> bool:
    """输入是否命中敏感个人信息（身份证号 / 手机号 / 账号密码隐私问句）。

    复用 app/services/ai_chat_privacy.py 的问句正则/拦截思路，并补身份证/手机号正则。
    返回 True 表示命中敏感输入，调用方应拒答（403）。
    """
    s = (text or "").strip()
    if not s:
        return False
    if _ID_CARD_18.search(s) or _ID_CARD_15.search(s) or _PHONE.search(s):
        return True
    if looks_like_user_account_privacy_question(s):
        return True
    return False
