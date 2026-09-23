from sqlalchemy import Boolean, Column, DateTime, String, Text, ForeignKey
from sqlalchemy.sql import func

from app.database import Base
from app.models.user import gen_uuid


class PrepPlan(Base):
    __tablename__ = "prep_plans"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    subject = Column(String(64), nullable=False)
    content = Column(Text, nullable=False)
    completed = Column(Boolean, nullable=False, default=False, server_default="0")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
