"""班级访问与角色：创建者为班主任，协作教师见 class_teachers 表"""
from typing import Literal, Optional

from sqlalchemy.orm import Session

from app.models.class_model import Class
from app.models.class_teacher import ClassTeacher
from app.models.user import User

ClassRole = Literal["head", "deputy", "teacher"]


def _is_global_admin(db: Session, user_id: str) -> bool:
    """判断用户是否为拥有全局管理权限的角色"""
    u = db.query(User).filter(User.id == user_id).first()
    if not u or not u.roles:
        return False
    roles = [r.strip() for r in u.roles.split(",") if r.strip()]
    # 任课老师/教师/测试账号等无全局权限角色，只能看到自己加入的班级
    return any(r in ["系统管理员", "子系统管理员", "校级管理者", "年级组长"] for r in roles)


def get_class_role(db: Session, user_id: str, class_id: str) -> Optional[ClassRole]:
    """当前用户在班级中的角色；无权限返回 None。"""
    c = db.query(Class).filter(Class.id == class_id).first()
    if not c:
        return None
    
    # 如果是全局管理员，直接返回 "head" 赋予最高权限
    if _is_global_admin(db, user_id):
        return "head"

    if c.user_id == user_id:
        return "head"
    row = db.query(ClassTeacher).filter(ClassTeacher.class_id == class_id, ClassTeacher.user_id == user_id).first()
    if not row:
        return None
    r = (row.role or "").lower()
    if r in ("head", "deputy", "teacher"):
        return r  # type: ignore[return-value]
    return "teacher"


def can_view_class(db: Session, user_id: str, class_id: str) -> bool:
    if _is_global_admin(db, user_id):
        return True
    return get_class_role(db, user_id, class_id) is not None


def can_manage_teachers(db: Session, user_id: str, class_id: str) -> bool:
    if _is_global_admin(db, user_id):
        return True
    # 只有班主任（head）可以管理教师
    return get_class_role(db, user_id, class_id) == "head"


def can_manage_students(db: Session, user_id: str, class_id: str) -> bool:
    if _is_global_admin(db, user_id):
        return True
    r = get_class_role(db, user_id, class_id)
    # 只有班主任（head）可以增删改查学生
    return r == "head"


def can_view_student_pii(db: Session, user_id: str, class_id: str) -> bool:
    """是否可查看学生完整 PII：全局管理员/班主任(head)看完整；副班主任/协作教师看脱敏。

    与 E09 数据分类分级决策一致：看完整 PII = 全局管理员 + 班主任(head)；
    deputy/teacher 仅能看掩码（读接口脱敏，写仍被 can_manage_students 限制为 head）。
    """
    if _is_global_admin(db, user_id):
        return True
    return get_class_role(db, user_id, class_id) == "head"


def is_class_owner(db: Session, user_id: str, class_id: str) -> bool:
    if _is_global_admin(db, user_id):
        return True
    c = db.query(Class).filter(Class.id == class_id).first()
    return bool(c and c.user_id == user_id)
