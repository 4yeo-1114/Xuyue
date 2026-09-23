"""校外实践记录表"""
from sqlalchemy import JSON, Column, String, Integer, Text, Date, DateTime, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class PracticeRecord(Base):
    __tablename__ = "practice_records"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    student_id = Column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    practice_type = Column(String(32), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    practice_date = Column(Date, nullable=False, index=True)
    duration_hours = Column(Numeric(4, 1), nullable=True)
    location = Column(String(255), nullable=True)
    evidence_images = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)
    status = Column(String(16), nullable=False, default="pending", index=True)
    reviewer_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    review_comment = Column(String(512), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    credit_transaction_id = Column(String(36), nullable=True)
    recorded_by = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
