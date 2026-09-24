"""批改额度账户与充值流水（0924 需求一：充值入口 + 积分体系）。

- grading_quota：每账号一行，累计充值总面数 total_pages / 已用面数 used_pages。
- grading_quota_recharge_logs：管理员手动加额流水（审计）。
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
    total_pages = Column(Integer, nullable=False, default=0)  # 累计充值总面数
    used_pages = Column(Integer, nullable=False, default=0)  # 已用面数（累计）
    used_today_pages = Column(Integer, nullable=False, default=0)  # 当天已用面数
    usage_date = Column(Date, nullable=True)  # used_today_pages 对应日期
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class GradingQuotaRechargeLog(Base):
    __tablename__ = "grading_quota_recharge_logs"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount_yuan = Column(Integer, nullable=False, default=0)
    base_pages = Column(Integer, nullable=False, default=0)
    bonus_pages = Column(Integer, nullable=False, default=0)
    total_pages = Column(Integer, nullable=False, default=0)
    operator_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
