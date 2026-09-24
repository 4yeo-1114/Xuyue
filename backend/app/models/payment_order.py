"""口径 B · 支付订单表。

设计依据：docs/payment/payment-design.md §3.2 / §6.1 / §8。
⚠️ 本批（Phase 0）**只建表**，⛔ 不写任何下单 / 回调 / 验签 / 通道接线（那是 Phase 2）。
⚠️ `payee_*` 字段留白：收款主体 = ① 类未拍项（§10 Q1），本批不猜、不填默认值。
"""
from sqlalchemy import Column, DateTime, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base
from app.models.user import gen_uuid


class PaymentOrder(Base):
    __tablename__ = "payment_orders"
    __table_args__ = (
        Index("idx_payment_order_user_time", "user_id", "created_at"),
        Index("idx_payment_order_status", "status"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), nullable=False, index=True)
    # manual | unset | wechat_pay | alipay | bank_transfer | aggregator（通道选型 = §10 Q2）
    channel = Column(String(32), nullable=False, default="unset")
    channel_trade_no = Column(String(128), nullable=True, index=True)
    # pending | paid | failed | cancelled | refunded
    status = Column(String(16), nullable=False, default="pending")
    amount_fen = Column(Integer, nullable=False)
    paid_amount_fen = Column(Integer, nullable=True)
    plan_id = Column(String(36), nullable=True)
    subject_type = Column(String(32), nullable=False, default="recharge")
    payee_entity_id = Column(String(64), nullable=True)
    channel_detail_json = Column(Text, nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
