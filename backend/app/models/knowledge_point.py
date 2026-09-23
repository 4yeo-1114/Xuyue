"""知识点表"""
from sqlalchemy import JSON, Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    unit_id = Column(String(36), ForeignKey("subject_units.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    name = Column(String(256), nullable=False)
    level = Column(String(32), nullable=True)
    mastery = Column(Float, default=0, nullable=False)
    is_weak = Column(Boolean, default=False, nullable=False)
    prerequisite = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)  # list of codes/ids
    postrequisite = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)
    related = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)
    hours = Column(Integer, default=0, nullable=False)
    key_point = Column(String(512), nullable=True)
    difficulty = Column(String(32), nullable=True)
    common_errors = Column(Text, nullable=True)
    resources = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)  # [{type, name}, ...]
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
