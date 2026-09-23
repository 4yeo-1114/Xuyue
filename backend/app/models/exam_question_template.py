"""考试题型模板表（组卷用）"""
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class ExamQuestionTemplate(Base):
    __tablename__ = "exam_question_templates"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject = Column(String(64), nullable=False, index=True)
    type_name = Column(String(128), nullable=False)
    default_count = Column(Integer, default=1, nullable=False)
    default_score_each = Column(Integer, default=0, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
