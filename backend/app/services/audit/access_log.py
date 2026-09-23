"""访问留痕写服务（E03 监护人同意闭环 + E14 合规后台）。

对外唯一入口 log_access(db, *, user_id, user_role, action, target_type, target_id, detail=None)：
  - 内部 try/except，写失败仅 log 不抛错（不阻断主流程）
  - user_role 为中文角色标签（如 "管理员"/"班主任"），调用方可传 resolve_user_role 推导

写入点控制在「敏感读取 + 高危动作」：portfolio 学期/月报读取、综评档案读取、
成长记录列表读取、学生画像读取、AI auto-report 拉取、导出/下载、consent 变更、
行权 correct/delete。不给所有读接口加。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.access_log import AccessLog

logger = logging.getLogger(__name__)

# action 白名单（与契约一致）
VALID_ACTIONS = {
    "view_report",
    "view_portfolio",
    "view_growth",
    "view_archive",
    "ai_report",
    "export",
    "delete",
    "correct",
    "consent_change",
}


def resolve_user_role(db: Session, user_id: str) -> str:
    """由 users.roles（中文逗号分隔）推导单一中文角色标签（按最高权限取一）。"""
    try:
        from app.services.assessment import access as access_svc

        tokens = access_svc.get_role_tokens(db, user_id)
    except Exception:  # noqa: BLE001 - 角色解析失败不阻断留痕
        tokens = set()
    for admin_role in ("系统管理员", "子系统管理员", "校级管理者", "年级组长"):
        if admin_role in tokens:
            return admin_role
    for teacher_role in ("班主任", "任课教师", "教师", "协作教师", "科任教师"):
        if teacher_role in tokens:
            return teacher_role
    return (sorted(tokens)[0] if tokens else "未知")


def log_access(
    db: Session,
    *,
    user_id: str,
    user_role: str,
    action: str,
    target_type: str,
    target_id: str,
    detail: Optional[dict] = None,
) -> None:
    """写一条 access_log；任何失败仅记录日志，绝不向上抛（不阻断主流程）。"""
    if action not in VALID_ACTIONS:
        action = "export"  # 兜底：未知 action 降级为导出类留痕
    row = AccessLog(
        user_id=str(user_id or "")[:36],
        user_role=str(user_role or "")[:32],
        action=action[:32],
        target_type=str(target_type or "")[:32],
        target_id=str(target_id or "")[:36],
        detail=detail if isinstance(detail, dict) else None,
    )
    try:
        db.add(row)
        db.commit()
    except Exception:  # noqa: BLE001 - 留痕失败不阻断主流程
        db.rollback()
        logger.warning(
            "[access_log] 写入访问留痕失败（已忽略）：action=%s target_type=%s target_id=%s",
            action,
            target_type,
            target_id,
            exc_info=True,
        )
