"""测评域权限辅助 —— 映射叙阅现有角色到 B0 契约角色（附录 B 权限矩阵）。

叙阅现有 users.roles 为中文逗号分隔（如"系统管理员,班主任"），无 B0 的 parent 角色。
本模块做应用层角色判定（契约 §7 注明中间件升级不在本契约范围）：
  - super_admin ≈ 系统管理员
  - org_admin   ≈ 子系统管理员
  - school_admin≈ 校级管理者 / 年级组长
  - teacher     ≈ 任课教师 / 班主任 / 教师 / 协作教师
  - student     ≈ users.id 关联 students.user_id
  - parent      ≈ users.id 出现在 parent_students.parent_id（绑定表即身份凭据）
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.student import Student
from app.models.parent_student import ParentStudent

# 中文角色名 → B0 角色 token
_ADMIN_ROLE_NAMES = {"系统管理员", "子系统管理员", "校级管理者", "年级组长"}
_SUPER_ADMIN_NAMES = {"系统管理员"}
_ORG_ADMIN_NAMES = {"子系统管理员"}
_SCHOOL_ADMIN_NAMES = {"校级管理者", "年级组长"}
_TEACHER_ROLE_NAMES = {"任课教师", "班主任", "教师", "协作教师", "科任教师"}


def _role_tokens(user: Optional[User]) -> set[str]:
    if not user or not user.roles:
        return set()
    return {r.strip() for r in user.roles.split(",") if r.strip()}


def get_role_tokens(db: Session, user_id: str) -> set[str]:
    u = db.query(User).filter(User.id == user_id).first()
    return _role_tokens(u)


def is_super_admin(db: Session, user_id: str) -> bool:
    return bool(get_role_tokens(db, user_id) & _SUPER_ADMIN_NAMES)


def is_org_admin(db: Session, user_id: str) -> bool:
    return bool(get_role_tokens(db, user_id) & _ORG_ADMIN_NAMES)


def is_school_admin(db: Session, user_id: str) -> bool:
    return bool(get_role_tokens(db, user_id) & _SCHOOL_ADMIN_NAMES)


def is_admin(db: Session, user_id: str) -> bool:
    """super_admin / org_admin / school_admin 任一即管理角色。"""
    return bool(get_role_tokens(db, user_id) & _ADMIN_ROLE_NAMES)


def is_teacher(db: Session, user_id: str) -> bool:
    if is_admin(db, user_id):
        return True
    return bool(get_role_tokens(db, user_id) & _TEACHER_ROLE_NAMES)


def can_manage_definitions(db: Session, user_id: str) -> bool:
    """B0 §7.1 / 附录 B：创建/编辑题组定义仅 super_admin / org_admin。"""
    return is_super_admin(db, user_id) or is_org_admin(db, user_id)


def get_student_for_user(db: Session, user_id: str) -> Optional[Student]:
    """user_id 关联的学生记录（student 账号本人）。"""
    return db.query(Student).filter(Student.user_id == user_id).first()


def is_student_user(db: Session, user_id: str) -> bool:
    return get_student_for_user(db, user_id) is not None


def is_parent_user(db: Session, user_id: str) -> bool:
    """user_id 作为 parent_students.parent_id 存在即视为家长账号（绑定表即身份凭据）。"""
    return (
        db.query(ParentStudent.id)
        .filter(ParentStudent.parent_id == user_id)
        .first()
        is not None
    )


def get_parent_bound_student_ids(db: Session, user_id: str, *, active_only: bool = True) -> list[str]:
    """家长绑定学生 ID 列表（契约：parent_students.parent_id 即身份凭据）。

    默认仅返回 status=active 的绑定，与测评 _result_view_allowed 的 active 判定一致。
    """
    q = db.query(ParentStudent.student_id).filter(ParentStudent.parent_id == user_id)
    if active_only:
        q = q.filter(ParentStudent.status == "active")
    return [row[0] for row in q.all()]


def can_manage_class_batch(db: Session, user_id: str, class_id: str) -> bool:
    """teacher/school_admin 建 class_batch 会话：复用班级访问控制。

    说明：现有 can_view_class 对管理角色放行，对教师要求班级有协作/属主关系。
    这里用 is_admin 快速放行 + can_view_class 兜底，避免新建依赖。
    """
    from app.utils.class_access import can_view_class

    if is_admin(db, user_id):
        return True
    return can_view_class(db, user_id, class_id)


def can_consent_operate(db: Session, user_id: str, student: Optional[Student]) -> bool:
    """B0 §6.2 权限：撤回/恢复 = super_admin、school_admin（本校）、该生被指派的 mentor 教师。

    叙阅无 mentors 表实现（Wave 1 归 A 域），此处以"该生班级管理者/创建者"作为 mentor 代理，
    管理角色直接放行。
    """
    if is_super_admin(db, user_id) or is_school_admin(db, user_id):
        return True
    if not student:
        return False
    # 班级属主 / 班级协作教师视作该生 mentor
    from app.utils.class_access import can_view_class

    return can_view_class(db, user_id, student.class_id)
