"""系统配置表"""
from sqlalchemy import JSON, Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class SystemConfig(Base):
    __tablename__ = "system_config"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    key = Column(String(128), unique=True, nullable=False, index=True)
    value = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)
    label = Column(String(256), nullable=True)
    category = Column(String(64), nullable=True)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(String(36), nullable=True)
