"""口径 B · 资金流水（**只增不改，无 updated_at** —— 与 `credit_transactions` 一致）。

设计依据：docs/payment/payment-design.md §3.2 表 3、§3.3 I1/I3/I4/I5。
⛔ 应用层禁止对本表做 UPDATE / DELETE。
"""
import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects import mysql

from app.database import Base
from app.models.user import gen_uuid

# ⚠️ 排序确定性 —— §3.3 I3 要求「最新一行 balance_after_fen 与余额一致」，可这要求
#    「最新一行」**可判定**。MySQL 的 `DATETIME` 默认 0 位小数秒 ⇒ 同一秒内落的多笔分录
#    时间戳**完全相同** ⇒ 排序退化为按随机 UUID 兜底 ⇒ I3 复算会**随机**判红，
#    账单分页（`ORDER BY created_at DESC`）也会重复/漏行。
#    ⇒ 仅对 MySQL 方言取微秒精度（SQLite 原生 `DateTime` 本身就以微秒存 ISO 文本）。
#    ⚠️ 代价（如实申报）：`DATETIME(6)` **不接受** `DEFAULT NOW()`（fsp 不匹配，MySQL 报
#       1067 Invalid default value）⇒ 本列改为**应用侧默认值**，不再带 server_default。
MICRO_DT = DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=6), "mysql")


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        Index("uk_ledger_idempotency", "idempotency_key", unique=True),
        Index("idx_ledger_account_time", "account_id", "created_at"),
        Index("idx_ledger_type_time", "entry_type", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    account_id = Column(
        String(36), ForeignKey("payment_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # recharge | consume | refund | grant | expire | adjust
    entry_type = Column(String(32), nullable=False)
    # 有符号：充值/授予 = 正，消费 = 负，冲正 = 正
    amount_fen = Column(Integer, nullable=False)
    # 记账后余额快照（可复算，§3.3 I3）
    balance_after_fen = Column(Integer, nullable=False)
    # 幂等键，唯一索引（§3.3 I1）
    idempotency_key = Column(String(191), nullable=False)
    usage_event_id = Column(
        String(36), ForeignKey("usage_events.id", ondelete="SET NULL"), nullable=True
    )
    order_id = Column(String(36), nullable=True)
    operator_id = Column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    description = Column(String(512), nullable=True)
    created_at = Column(MICRO_DT, default=_utcnow, index=True)
