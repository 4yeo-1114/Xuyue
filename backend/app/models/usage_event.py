"""口径 B · 用量事件流（**只增不改**）。

设计依据：docs/payment/payment-design.md §3.2 表 2、§7.1。
1 份 = （用户, 文件夹, 学生）三元组的「已批改」状态发生 0→1 跃迁（同 §3.1）。
"""
import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, SmallInteger, String
from sqlalchemy.dialects import mysql

from app.database import Base
from app.models.user import gen_uuid

# 同 `ledger_entry.MICRO_DT`：MySQL 侧取微秒精度，否则同一秒内的事件无法排序
# ⇒ `GET /payment/usage` 的 recent 顺序不稳定、P0-3/§3.5 的「先 +1 后 -1」顺序判据会随机翻车。
MICRO_DT = DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=6), "mysql")


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class UsageEvent(Base):
    __tablename__ = "usage_events"
    __table_args__ = (
        Index("uk_usage_event_uid", "event_uid", unique=True),
        Index("idx_usage_event_user_kind_time", "user_id", "kind", "occurred_at"),
        Index("idx_usage_event_business", "user_id", "kind", "folder_safe", "subject_key"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind = Column(String(32), nullable=False)
    folder_safe = Column(String(255), nullable=False, default="")
    subject_key = Column(String(255), nullable=False, default="")
    # +1（产生）/ -1（冲正）
    delta = Column(SmallInteger, nullable=False)
    # 上游事件的稳定标识 ⇒ uk_usage_event_uid 兜底「同一跃迁重复投递只落一行」
    event_uid = Column(String(64), nullable=False)
    occurred_at = Column(MICRO_DT, nullable=False)
    created_at = Column(MICRO_DT, default=_utcnow)
