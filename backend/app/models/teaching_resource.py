"""教学资源表（含文件元数据）"""
from sqlalchemy import JSON, Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class TeachingResource(Base):
    __tablename__ = "teaching_resources"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    type = Column(String(64), nullable=False, default="其他")
    file_url = Column(String(1024), nullable=False)
    file_name = Column(String(256), nullable=False)
    file_size = Column(Integer, default=0, nullable=False)
    mime_type = Column(String(128), nullable=True)
    tags = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)  # list of strings
    is_shared = Column(Boolean, default=False, nullable=False)
    uses = Column(Integer, default=0, nullable=False)
    rating = Column(Integer, default=0, nullable=False)
    # AI 检测 / 来源
    detected_grade = Column(String(32), nullable=True)
    detected_class = Column(String(32), nullable=True)
    detected_subject = Column(String(64), nullable=True)
    detected_unit = Column(String(128), nullable=True)
    detected_chapter = Column(String(128), nullable=True)
    detected_school_level = Column(String(32), nullable=True)
    detection_confidence = Column(Float, nullable=True)
    uploaded_from_class = Column(String(64), nullable=True)
    uploaded_from_grade = Column(String(32), nullable=True)
    is_cross_class = Column(Boolean, nullable=True)
    question_count = Column(Integer, nullable=True)
    knowledge_point_count = Column(Integer, nullable=True)
    difficulty = Column(Integer, nullable=True)
    source_label = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
