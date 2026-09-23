"""章定义表（争章·章定义）"""
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class BadgeDefinition(Base):
    __tablename__ = "badge_definitions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(128), nullable=False)
    description = Column(String(512), nullable=True)
    badge_type = Column(String(32), nullable=False, default="school_based", index=True)
    category = Column(String(32), nullable=False, default="moral", index=True)
    icon_url = Column(String(512), nullable=True)
    points_awarded = Column(Integer, nullable=False, default=10)
    min_grade = Column(String(16), nullable=True)
    max_grade = Column(String(16), nullable=True)
    is_active = Column(Integer, nullable=False, default=1, index=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
