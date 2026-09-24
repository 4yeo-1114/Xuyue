"""口径 B · 老师钱包账户表（一师一行）。

设计依据：docs/payment/payment-design.md §3.2 表 1。
结构照抄 `credit_accounts`（`models/credit_account.py`）的仓库习惯，
⛔ 不复用该表（它是学生积分，subject 是 students.id）。
"""
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base
from app.models.user import gen_uuid


class PaymentAccount(Base):
    __tablename__ = "payment_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", name="uk_payment_account_user"),
        Index("idx_payment_account_status", "status"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 余额单位一律「分」（整数，不用浮点）—— §3.2
    balance_fen = Column(Integer, nullable=False, default=0)
    total_recharged_fen = Column(Integer, nullable=False, default=0)
    total_consumed_fen = Column(Integer, nullable=False, default=0)
    status = Column(String(16), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
