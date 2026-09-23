"""AI 学期评语表（99-reconciliation §4.1.4）"""
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, Boolean, UniqueConstraint, Index
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class AssessmentComment(Base):
    __tablename__ = "assessment_comments"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    student_id = Column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    school_id = Column(String(36), nullable=True)
    term = Column(String(32), nullable=False)
    status = Column(String(16), nullable=False, default="ai_generated")  # ai_generated|confirmed|ai_failed
    ai_content = Column(Text, nullable=True)
    confirmed_content = Column(Text, nullable=True)
    ai_model = Column(String(64), nullable=True)
    tokens_used = Column(Integer, nullable=True)
    cost_cent = Column(Integer, nullable=True)
    gate_flagged = Column(Boolean, nullable=False, default=False, server_default="0")
    created_by = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    confirmed_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("student_id", "term", name="uq_ac_student_term"),
        Index("idx_ac_class_term", "class_id", "term"),
    )
