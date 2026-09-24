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
    # ── 价税分离（设计稿 §10 Q3「开普票/专票 ⇒ 必须价税分离」；P3-2 提前到 Phase 2）──
    # ⚠️ 单位口径与 `amount_fen` 一致：**分**（整数），`tax_rate_bps` 是**整数基点**（1% = 100bps）。
    # ⚠️ **可空**：存量订单没有这些值；且**税率尚未拍**（主导者 2026-09-24 只拍了「要开票 ⇒
    #    需价税分离」，没给税率、也没说 `amount_fen` 是含税价还是不含税价）
    #    ⇒ ⛔ 本批**不编税率、不臆定取整口径**，列先立着，等口径到位再填。
    # ⚠️ **账本不动**（§10 Q3 逐字：「建议**含税记账**，税额只在订单层拆，避免账本多一套
    #    一致性约束」）⇒ `ledger_entries` 继续是纯「分」整数，⛔ 不加税字段。
    # ⚠️ 加列靠 `app/database.py::_ensure_payment_order_tax_columns()`（幂等 ALTER + 挂无条件段）：
    #    Phase 0 已把本表建出来了，`create_all` **不会**给已存在的表补列。
    amount_excl_tax_fen = Column(Integer, nullable=True)
    tax_amount_fen = Column(Integer, nullable=True)
    tax_rate_bps = Column(Integer, nullable=True)
    plan_id = Column(String(36), nullable=True)
    subject_type = Column(String(32), nullable=False, default="recharge")
    payee_entity_id = Column(String(64), nullable=True)
    channel_detail_json = Column(Text, nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
