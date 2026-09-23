"""功能开关表"""
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    key = Column(String(128), unique=True, nullable=False, index=True)
    label = Column(String(256), nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)
    scope = Column(String(64), nullable=False, default="global")
    scope_id = Column(String(36), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(String(36), nullable=True)
