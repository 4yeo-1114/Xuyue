"""口径 B · 套餐定义表（配置型数据）。

设计依据：docs/payment/payment-design.md §5.1 表 4。
⚠️ 本批（Phase 0）**只建表**，套餐服务逻辑（抵扣顺序 / overage_policy / 惰性过期）留 Phase 1。
"""
from sqlalchemy import Column, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base
from app.models.user import gen_uuid


class PaymentPlan(Base):
    __tablename__ = "payment_plans"
    __table_args__ = (UniqueConstraint("code", name="uk_plan_code"),)

    id = Column(String(36), primary_key=True, default=gen_uuid)
    code = Column(String(64), nullable=False)
    name = Column(String(128), nullable=False)
    price_fen = Column(Integer, nullable=False)
    period_unit = Column(String(16), nullable=False)
    period_count = Column(Integer, nullable=False, default=1)
    included_grade_quota = Column(Integer, nullable=False, default=0)
    overage_policy = Column(String(16), nullable=False, default="wallet")
    is_active = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
