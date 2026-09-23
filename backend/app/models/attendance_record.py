"""晨午检请假/出勤记录表（校园生活·请假出勤）

status 取值：present(出勤) / leave(请假) / late(迟到) / absent(缺勤)。
同一学生同一检查类型同一天只允许一条记录（uk_student_attendance）。
"""
from sqlalchemy import Column, String, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("student_id", "check_type", "date", name="uk_student_attendance"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    student_id = Column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    check_type = Column(String(16), nullable=False, default="morning", index=True)
    status = Column(String(16), nullable=False, default="present", index=True)
    reason = Column(String(512), nullable=True)
    recorded_by = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
