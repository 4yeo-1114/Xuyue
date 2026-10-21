"""口径 B · 开票申请表（P3-1 结构）。

设计依据：docs/payment/payment-design.md §9-Phase3「P3-1 发票」、§10 Q3（「开普票/专票
⇒ 必须价税分离」，其中 `payment_invoices` 表**属本项**）。

⛔ **已拍口径（逐字落实，⛔ 不自创、⛔ 不扩项）**：
  · 票种 = **普票** ⇒ 只要「抬头 ＋ 纳税人识别号」两项。⛔ **无**专票那四项
    （地址 / 电话 / 开户行 / 账号）。
  · 载体 = **电子** ⇒ 交付 = 邮箱（`email`）。⛔ 无收件地址、⛔ 无任何邮寄字段。
  · 金额 = **含税**（`0.5 元/份` 是含税价）⇒ `amount_fen` 与订单 `amount_fen` 同口径，
    单位仍是**分**（整数，不用浮点）。
  · 手续费 = **平台承担** ⇒ 手续费**不进老师账本**，⛔ 本表**不出现**手续费分摊。
  · 红冲 = **本阶段不做** ⇒ ⛔ 不实现红字发票、⛔ 不留任何红冲字段。
  · ⚠️ **税率仍未拍** ⇒ ⛔ 本表**不出现** `tax_rate_bps` / `tax_amount_fen` /
    `amount_excl_tax_fen`：本批走「**老师申请 → 人工开票**」，**税额不由本系统计算**。
    （价税分离的 3 个**可空**列只立在 `payment_orders` 上，见 §10 Q3 / P3-2 与
    `app/database.py::_ensure_payment_order_tax_columns()`；⛔ 本表不重复、不预填。）
"""
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base
from app.models.user import gen_uuid


class PaymentInvoice(Base):
    __tablename__ = "payment_invoices"
    __table_args__ = (
        # 一单一票（brief 硬约束 5）：同一订单只能有 1 张发票申请。
        # ⚠️ 这是**DB 层**的真约束，⛔ 不只靠应用层的 if —— 有回归用例直接 INSERT 第二行判红。
        UniqueConstraint("order_id", name="uk_payment_invoice_order"),
        Index("idx_payment_invoice_user_time", "user_id", "created_at"),
        Index("idx_payment_invoice_status", "status"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    order_id = Column(
        String(36),
        # ⚠️ 指向 payment_orders_v2（口径 B 订单表；生产同名旧表是同事的家长订单表，
        #    详见 payment_order.py 表名注释）。生产存量表的旧 FK 由
        #    `app/database.py::_ensure_payment_invoices_order_fk()` 幂等迁移。
        ForeignKey("payment_orders_v2.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # requested | issued | void（状态机 = 严格线性，见 services/payment/invoices.py）
    status = Column(String(16), nullable=False, default="requested")
    # **含税**金额（分）—— 申请时从**订单**取值快照（⛔ 不从请求体取：老师不能自己填票面金额）
    amount_fen = Column(Integer, nullable=False)
    # ── 普票的两项开票信息（已拍：只要这两项）──
    title = Column(String(255), nullable=False)          # 发票抬头
    taxpayer_id = Column(String(64), nullable=False)     # 纳税人识别号
    # 电子发票交付邮箱（已拍载体 = 电子 ⇒ 交付只走邮箱，⛔ 无邮寄/收件地址字段）
    email = Column(String(255), nullable=False)
    # 人工开票后回填的发票号码（本批**无后台入口** ⇒ 列先立着给状态机数据层用，故可空）
    invoice_no = Column(String(64), nullable=True)
    issued_at = Column(DateTime(timezone=True), nullable=True)
    voided_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
