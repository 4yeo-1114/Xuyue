"""班级表，与前端 Supabase types 对应"""
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class Class(Base):
    __tablename__ = "classes"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    school_id = Column(String(36), nullable=True, comment="学校 ID，锚点 schools.id")
    school_level = Column(String(32), nullable=False)
    grade = Column(String(32), nullable=False)
    name = Column(String(128), nullable=False)
    student_count = Column(Integer, default=0, nullable=False)
    dingtalk_dept_id = Column(String(64), nullable=True, index=True, comment="钉钉部门ID，通讯录同步锚点")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
