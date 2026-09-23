"""学科单元表（章节）"""
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class SubjectUnit(Base):
    __tablename__ = "subject_units"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject = Column(String(64), nullable=False, index=True)
    semester = Column(String(32), nullable=False, index=True)
    unit_index = Column(Integer, nullable=False)
    name = Column(String(256), nullable=False)
    subtitle = Column(String(256), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
