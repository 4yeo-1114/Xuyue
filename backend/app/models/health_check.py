"""晨午检记录表（校园生活·晨午检）"""
from sqlalchemy import Column, String, Integer, Numeric, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class HealthCheck(Base):
    __tablename__ = "health_checks"
    __table_args__ = (
        UniqueConstraint("student_id", "check_type", "check_date", name="uk_student_check"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    student_id = Column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    check_type = Column(String(16), nullable=False)
    check_date = Column(Date, nullable=False, index=True)
    temperature = Column(Numeric(3, 1), nullable=True)
    health_status = Column(String(16), nullable=False, default="normal")
    symptoms = Column(String(512), nullable=True)
    is_alert = Column(Integer, nullable=False, default=0, index=True)
    handled_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    handle_notes = Column(String(512), nullable=True)
    recorded_by = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
