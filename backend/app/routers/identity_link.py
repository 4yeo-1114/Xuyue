# -*- coding: utf-8 -*-
"""R3 身份统一：identity_link 桥表只读 REST 层（主平台侧）。

家长端 PG（app/assets/ 只读通道）的 identity_link 桥表暴露：

- GET /api/v1/identity-links?school_student_id=<id>    → 按学校端学生 id 查桥记录
- GET /api/v1/identity-links?parent_student_id=<id>    → 按家长端学生 id 查桥记录
- 两者可组合；均不传时返回最近记录（limit 兜底）。

设计约束（红线）：
- 主平台绝不写家长端 PG —— 本模块只读，无 POST/DELETE。
- identity_link 的写入只走 SQL 脚本 / 人工（建表见
  docs/migrations/2026-08-29-identity-link.sql）。
- join 不出库：本桥表只存 id 锚点，不 join students/users 拉字段，
  直接返回桥记录（两库身份本就割裂，取字段会引入跨库 join 复杂度）。
- 降级守卫对齐 school_assets：ASSETS_DB_ENABLED=False → 503；
  PG 不可达/查询异常 → 503，绝不裸 500。
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.assets.database import get_asset_db
from app.config import settings
import app.assets.models as am

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/identity-links", tags=["identity_link"])

# 单次查询最大行数硬上限
_MAX_LIMIT = 100


def _guard_enabled() -> None:
    """503 守卫一：未配置资产库（enabled=False）直接拒绝。"""
    if not settings.ASSETS_DB_ENABLED:
        raise HTTPException(
            status_code=503,
            detail={"enabled": False, "reason": "assets db not configured"},
        )


def _safe_query(fn, *args, **kwargs) -> Any:
    """503 守卫二：PG 不可达 / 查询异常 → 503，绝不裸 500。"""
    try:
        return fn(*args, **kwargs)
    except Exception:
        logger.warning("identity_link db query failed", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={"enabled": False, "reason": "assets db unreachable"},
        )


def _coerce_limit(limit, default: int = 20) -> int:
    """把 limit 收敛到 [1, _MAX_LIMIT]，防御负数/0/超限。"""
    try:
        v = int(limit)
    except (TypeError, ValueError):
        v = default
    return max(1, min(v, _MAX_LIMIT))


def _row_to_dict(r) -> dict:
    """桥记录 → dict（confidence 为 Decimal，转为 float 便于 JSON 序列化）。"""
    confidence = r.confidence
    try:
        confidence = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        pass
    return {
        "id": r.id,
        "school_db_profile_id": r.school_db_profile_id,
        "school_student_id": r.school_student_id,
        "parent_student_id": r.parent_student_id,
        "parent_user_id": r.parent_user_id,
        "link_method": r.link_method,
        "confidence": confidence,
        "source": r.source,
        "matched_by": r.matched_by,
        "status": r.status,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


@router.get("")
def list_identity_links(
    school_student_id: str | None = Query(None, description="学校端学生 id（主平台 MySQL students.id）"),
    parent_student_id: str | None = Query(None, description="家长端学生 id（家长端 PG students.id）"),
    limit: int = Query(20, ge=1, le=_MAX_LIMIT, description="返回条数上限"),
    _db: Session = Depends(get_asset_db),
):
    """只读查询 identity_link 桥记录：按学校学生 / 家长学生查，可组合。

    均不传时返回最近记录（按 created_at 倒序，limit 兜底）。
    只读：无 POST/DELETE，写入走 SQL 脚本 / 人工。
    """
    _guard_enabled()
    limit = _coerce_limit(limit)

    def _query():
        # _db 为 get_asset_db 注入的只读 session，请求结束由依赖关闭
        q = _db.query(am.IdentityLink)
        if school_student_id:
            q = q.filter(am.IdentityLink.school_student_id == school_student_id)
        if parent_student_id:
            q = q.filter(am.IdentityLink.parent_student_id == parent_student_id)
        rows = q.order_by(am.IdentityLink.created_at.desc()).limit(limit).all()
        return [_row_to_dict(r) for r in rows]

    items = _safe_query(_query)
    return {"items": items, "count": len(items)}
