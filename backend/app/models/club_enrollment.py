"""社团报名表（校园生活·社团成员）"""
from sqlalchemy import Column, String, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class ClubEnrollment(Base):
    __tablename__ = "club_enrollments"
    __table_args__ = (
        UniqueConstraint("student_id", "club_id", name="uk_student_club"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    student_id = Column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    club_id = Column(String(36), ForeignKey("campus_clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(16), nullable=False, default="enrolled", index=True)
    enrolled_at = Column(Date, nullable=False)
    left_at = Column(Date, nullable=True)
    recorded_by = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
