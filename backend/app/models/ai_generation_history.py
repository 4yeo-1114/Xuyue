"""AI 生成历史（智能生成课件/学案/多媒体资源，生成即落库）。"""
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class AiGenerationHistory(Base):
    __tablename__ = "ai_generation_history"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    gen_type = Column(String(32), nullable=False)
    subject = Column(String(64), default="", nullable=False)
    grade = Column(String(64), default="", nullable=False)
    title = Column(String(256), default="", nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
