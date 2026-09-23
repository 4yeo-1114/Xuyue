"""考试表"""
from sqlalchemy import Column, String, Integer, Date, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class Exam(Base):
    __tablename__ = "exams"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    subject = Column(String(64), nullable=False)
    title = Column(String(256), nullable=False)
    total_score = Column(Integer, default=100, nullable=False)
    exam_date = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class SmartExamPaper(Base):
    """智能组卷-用户试卷库"""
    __tablename__ = "smart_exam_papers"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(256), nullable=False)
    subject = Column(String(64), nullable=False)
    questions = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
