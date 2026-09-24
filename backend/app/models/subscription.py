"""口径 B · 订阅表（一师同时最多 1 个 active）。

设计依据：docs/payment/payment-design.md §5.1 表 5。
⚠️ 本批（Phase 0）**只建表**；生命周期/抵扣顺序留 Phase 1。
⚠️ `period_end` 是**独占**边界：有效期 = `[period_start, period_end)`。
"""
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.sql import func

from app.database import Base
from app.models.user import gen_uuid


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("idx_subscription_user_status", "user_id", "status"),
        Index("idx_subscription_period_end", "period_end"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id = Column(
        String(36), ForeignKey("payment_plans.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # active | expired | cancelled | refunded
    status = Column(String(16), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    # 下单时快照套餐额度（套餐改价/改额度不影响已购订阅）
    included_grade_quota = Column(Integer, nullable=False, default=0)
    cancel_at = Column(DateTime(timezone=True), nullable=True)
    source_order_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
