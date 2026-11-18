"""批改额度账户（0924 需求一；充值流水表随充值功能 20261111 移除）。

- grading_quota：每账号一行，额度总面数 total_pages / 已用面数 used_pages。
"""
import uuid
from datetime import date

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class GradingQuota(Base):
    __tablename__ = "grading_quota"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    total_pages = Column(Integer, nullable=False, default=0)  # 额度总面数（0 = 无限额）
    used_pages = Column(Integer, nullable=False, default=0)  # 已用面数（累计）
    used_today_pages = Column(Integer, nullable=False, default=0)  # 当天已用面数
    usage_date = Column(Date, nullable=True)  # used_today_pages 对应日期
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
