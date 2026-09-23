from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.sql import func

from app.database import Base
from app.models.user import gen_uuid


class SystemSettings(Base):
    __tablename__ = "system_settings"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    system_email = Column(String(255), nullable=True)
    baidu_access_token = Column(Text, nullable=True)
    baidu_api_key = Column(Text, nullable=True)
    baidu_secret_key = Column(Text, nullable=True)
    dashscope_api_key = Column(Text, nullable=True)
    qwen_model = Column(String(64), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(String(36), nullable=True)
