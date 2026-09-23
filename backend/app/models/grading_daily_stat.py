import uuid
from datetime import date

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class GradingDailyStat(Base):
    """按用户、文件夹、自然日聚合的上传/批改份数。"""

    __tablename__ = "grading_daily_stats"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    folder_safe = Column(String(255), nullable=False, default="", index=True)
    stat_date = Column(Date, nullable=False, index=True)
    upload_count = Column(Integer, nullable=False, default=0)
    grade_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "folder_safe", "stat_date", name="uq_grading_daily_stat"),
    )
