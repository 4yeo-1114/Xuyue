"""学生导师指派表（00 §5.12，归 A 画像 agent）"""
from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class Mentor(Base):
    __tablename__ = "mentors"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    student_id = Column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(16), nullable=False, default="tutor")  # tutor|guardian（guardian 留位）
    assigned_by = Column(String(36), nullable=True)  # 指派者用户 ID（00 §5.12 无外键约束）
    status = Column(String(16), nullable=False, default="active")  # active|revoked
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("student_id", "user_id", name="uq_mtr_student_user"),
        Index("idx_mtr_user_id", "user_id"),
    )
