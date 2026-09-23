"""家长-学生绑定表（B0 契约 §7.6 前置依赖）

叙阅当前无 parent 角色 / parent_students 表，本表为测评模块监护人同意通道新增。
UNIQUE(parent_id, student_id) 防重复绑定。
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class ParentStudent(Base):
    __tablename__ = "parent_students"
    __table_args__ = (
        UniqueConstraint("parent_id", "student_id", name="uq_ps_pair"),
        Index("idx_ps_parent", "parent_id"),
        Index("idx_ps_student", "student_id"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    parent_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="家长 user ID → users.id（role 应含 parent）")
    student_id = Column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, comment="学生ID → students.id")
    relation = Column(String(16), nullable=False, default="guardian", comment="关系: guardian/father/mother/other")
    status = Column(String(16), nullable=False, default="active", comment="状态: active/inactive")
    created_by = Column(String(36), nullable=True, comment="创建者ID → users.id")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
