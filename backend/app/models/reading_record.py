"""阅读记录表（校园生活·阅读打卡，榜单实时聚合，无 updated_at）"""
from sqlalchemy import Column, String, Integer, Date, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class ReadingRecord(Base):
    __tablename__ = "reading_records"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    student_id = Column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    book_title = Column(String(255), nullable=False)
    pages_read = Column(Integer, nullable=False, default=0)
    reading_minutes = Column(Integer, nullable=False, default=0)
    reading_date = Column(Date, nullable=False, index=True)
    recorded_by = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
