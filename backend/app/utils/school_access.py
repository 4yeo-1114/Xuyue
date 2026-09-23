"""校级视野与学校数据隔离辅助（D9 · 校级管理员角色 + school scope）。

角色判定以 users.roles（中文逗号分隔字符串）为准：
  - is_platform_admin(user)：系统管理员 / 子系统管理员 —— 平台级管理员
    （保留现有 _check_admin_permission 语义）。
  - is_school_admin(user)：系统管理员 / 子系统管理员 / 校级管理者 / 年级组长 ——
    校级视野，学校版全局功能（admin_dashboard / admin/users）的访问主体。

school scope（school 级数据隔离，兼容单校现状）：
  - get_user_school_id()：当前用户归属学校 ID。users 表当前没有 school_id 列
    （User 模型与库均未定义该列），数据源回退到已存在的 user_roles.school_id
    （表已存在、可空）。school_id 为 None/空 → 全局接口行为与现状完全一致（全量放行）。
  - get_school_user_ids()：学校内全部用户 ID（经 user_roles.school_id 归属）。
  - school_scope_class_ids()：把班级 id 集合按学校过滤；school_id 空 → 原集合不变。

原则：只加不减；school_id 空则与改前逐字节一致，绝不影响单校/demo 现状。
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User

# 平台级管理员（现有 _check_admin_permission 语义）
PLATFORM_ADMIN_ROLES = frozenset({"系统管理员", "子系统管理员"})
# 校级视野角色（学校版全局功能访问主体；"校级管理者" 为代码/seed/前端实际角色名）
SCHOOL_ADMIN_ROLES = frozenset({"系统管理员", "子系统管理员", "校级管理者", "年级组长"})


def get_user_roles(user: Optional[User]) -> set[str]:
    """将 users.roles 逗号分隔字符串解析为角色集合。"""
    if user is None or not user.roles:
        return set()
    return {r.strip() for r in user.roles.split(",") if r.strip()}


def is_platform_admin(user: Optional[User]) -> bool:
    """平台级管理员：系统管理员 / 子系统管理员（保留现有语义）。"""
    return bool(get_user_roles(user) & PLATFORM_ADMIN_ROLES)


def is_school_admin(user: Optional[User]) -> bool:
    """校级视野：系统管理员 / 子系统管理员 / 校级管理者 / 年级组长。"""
    return bool(get_user_roles(user) & SCHOOL_ADMIN_ROLES)


def get_user_school_id(db: Session, user: Optional[User]) -> Optional[str]:
    """当前用户归属学校 ID；无归属返回 None（全量放行）。

    users 表当前没有 school_id 列（User 模型与库均未定义），先 getattr 探测以兼容未来列；
    回退到已存在的 user_roles.school_id 作为数据源。查询失败时回退 None，不阻断全局接口。
    """
    if user is not None:
        sid = getattr(user, "school_id", None)
        if sid:
            return str(sid)
    try:
        from app.models.user_role import UserRole

        row = (
            db.query(UserRole.school_id)
            .filter(UserRole.user_id == user.id)
            .filter(UserRole.school_id.isnot(None))
            .limit(1)
            .first()
        )
        if row and row[0]:
            return str(row[0])
    except Exception:
        return None
    return None


def get_school_user_ids(db: Session, school_id: str) -> set[str]:
    """学校内全部用户 ID（经 user_roles.school_id 归属）；查询失败返回空集。"""
    try:
        from app.models.user_role import UserRole

        rows = (
            db.query(UserRole.user_id)
            .filter(UserRole.school_id == school_id)
            .all()
        )
        return {str(r[0]) for r in rows}
    except Exception:
        return set()


def school_scope_class_ids(
    db: Session, user: Optional[User], class_ids: Optional[set]
) -> Optional[set]:
    """按学校过滤班级 id 集合。

    - school_id 为空/None → 返回原 class_ids（None=全校，行为与现状完全一致）。
    - 非空 → 只保留 school_id 归属该校的班级（与既有 grade/class_id 过滤求交）。
    """
    school_id = get_user_school_id(db, user)
    if not school_id:
        return class_ids
    from app.models.class_model import Class

    q = db.query(Class.id).filter(Class.school_id == school_id)
    if class_ids is not None:
        q = q.filter(Class.id.in_(class_ids))
    return {str(r[0]) for r in q.all()}
