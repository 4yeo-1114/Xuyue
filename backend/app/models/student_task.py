"""学生任务/打卡表（00 §5.8，归 C 运营 agent）"""
from sqlalchemy import JSON, Column, String, Integer, Text, Date, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class StudentTask(Base):
    __tablename__ = "student_tasks"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    student_id = Column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    task_type = Column(String(32), nullable=False, default="daily")
    dimension = Column(String(16), nullable=True)
    reward_points = Column(Integer, nullable=False, default=0)
    due_date = Column(Date, nullable=True, index=True)
    status = Column(String(16), nullable=False, default="pending", index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    evidence_json = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
