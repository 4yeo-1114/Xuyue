"""颁章记录表（争章·颁章）"""
from sqlalchemy import Column, String, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class BadgeAward(Base):
    __tablename__ = "badge_awards"
    __table_args__ = (
        UniqueConstraint("student_id", "badge_definition_id", "award_date", name="uk_student_badge_date"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    student_id = Column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    badge_definition_id = Column(String(36), ForeignKey("badge_definitions.id", ondelete="RESTRICT"), nullable=False, index=True)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    awarded_by = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    award_date = Column(Date, nullable=False, index=True)
    reason = Column(String(512), nullable=True)
    credit_transaction_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
