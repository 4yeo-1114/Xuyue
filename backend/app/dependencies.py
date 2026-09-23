"""公共依赖：从 JWT 解析当前用户 ID；当前用户归属学校 ID（租户上下文，宽松模式）"""
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.grading.user_paths import ensure_user_grading_layout, set_grading_user_id
from app.utils.security import decode_access_token


def get_current_user_id(
    authorization: Optional[str] = Header(None),
) -> str:
    """H2：仅接受 Authorization Header，不再支持 URL query 传 JWT（避免令牌泄漏到日志/Referer）。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="登录已过期或无效")
    return user_id


def get_current_school_id(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> Optional[str]:
    """当前用户归属学校 ID（R2 租户上下文，宽松模式）。

    复用 app/utils/school_access.get_user_school_id 的解析逻辑
    （users.school_id 探测 → 回退 user_roles.school_id）。
    无归属 / 查询失败一律返回 None，绝不 raise、绝不 403 —— 保持单校/demo 现状放行。
    """
    try:
        from app.models.user import User
        from app.utils.school_access import get_user_school_id

        user = db.query(User).filter(User.id == user_id).first()
        return get_user_school_id(db, user)
    except Exception:
        return None


def bind_grading_user_context(
    user_id: str = Depends(get_current_user_id),
) -> str:
    """为批改相关 API 绑定当前用户的 grading_data_{user_id} 上下文，并确保目录存在。

    注意：不使用 yield/finally 清理 contextvar——FastAPI 在线程池里执行 teardown 时会
    与 set 时的 Context 不一致，导致 Token reset 抛出 ValueError。
    每次请求开始时会覆盖写入，后台任务自行 run_with_grading_user 管理上下文。
    """
    ensure_user_grading_layout(user_id)
    set_grading_user_id(user_id)
    return user_id
