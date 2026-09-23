from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.sql import func

from app.database import Base
from app.models.user import gen_uuid


class TodoItem(Base):
    __tablename__ = "todo_items"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=True)

    remind_at = Column(DateTime(timezone=True), nullable=True, index=True)
    notified_at = Column(DateTime(timezone=True), nullable=True, index=True)

    is_done = Column(Boolean, nullable=False, server_default="0", index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
