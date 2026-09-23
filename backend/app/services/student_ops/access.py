"""C 域细粒度权限检查（C0 §0.1 角色矩阵）"""
from sqlalchemy.orm import Session

from app.models.user import User
from app.utils.class_access import _is_global_admin, get_class_role

_SUPER_ADMIN_ROLES = {"系统管理员", "子系统管理员"}


def _roles(db: Session, user_id: str) -> set:
    u = db.query(User).filter(User.id == user_id).first()
    if not u or not u.roles:
        return set()
    return {r.strip() for r in u.roles.split(",") if r.strip()}


def is_super_admin(db: Session, user_id: str) -> bool:
    """系统管理员 / 子系统管理员：章定义管理、商品库管理、兑换审核。"""
    return bool(_roles(db, user_id) & _SUPER_ADMIN_ROLES)


def is_global_admin(db: Session, user_id: str) -> bool:
    """校级管理者 / 年级组长 / 系统管理员 等拥有全校视图。"""
    return _is_global_admin(db, user_id)


def can_manage_badge_definitions(db: Session, user_id: str) -> bool:
    """章定义管理：系统管理员 / 子系统管理员。"""
    return is_super_admin(db, user_id)


def can_manage_class_ops(db: Session, user_id: str, class_id: str) -> bool:
    """颁章 / 学分操作 / 实践录入 / 校园生活录入：班主任(head)/副班主任(deputy)/管理员。"""
    return get_class_role(db, user_id, class_id) in ("head", "deputy")


def can_view_class_data(db: Session, user_id: str, class_id: str) -> bool:
    """查看：所管班级或全校视图。"""
    return get_class_role(db, user_id, class_id) is not None


def can_review_practice(db: Session, user_id: str, class_id: str) -> bool:
    """实践审核：管理员 / 校级管理者 / 年级组长（global admin）或班主任。"""
    return get_class_role(db, user_id, class_id) == "head"


def can_manage_products(db: Session, user_id: str) -> bool:
    """商品库管理：系统管理员 / 子系统管理员。"""
    return is_super_admin(db, user_id)


def can_review_redemption(db: Session, user_id: str) -> bool:
    """兑换审核/发放/取消：系统管理员 / 子系统管理员。"""
    return is_super_admin(db, user_id)


def can_manage_clubs(db: Session, user_id: str) -> bool:
    """社团创建/编辑/删除：系统管理员 / 子系统管理员。"""
    return is_super_admin(db, user_id)
