"""学生表"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class Student(Base):
    __tablename__ = "students"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    school_id = Column(String(36), nullable=True, index=True, comment="所属学校,多校归属收敛 R2")
    name = Column(String(128), nullable=False)
    student_number = Column(String(64), nullable=False)
    dingtalk_userid = Column(String(64), nullable=True, index=True, comment="钉钉成员 userid，通讯录同步锚点")

    # 额外字段
    gender = Column(String(8), nullable=True)
    tier = Column(String(2), nullable=True)
    status = Column(String(16), nullable=True)
    birthday = Column(String(32), nullable=True)
    phone = Column(String(32), nullable=True)
    parent_name = Column(String(255), nullable=True)
    parent_phone = Column(String(32), nullable=True)
    address = Column(String(255), nullable=True)
    enroll_date = Column(String(32), nullable=True)
    seat_row = Column(Integer, nullable=True)
    seat_col = Column(Integer, nullable=True)
    cadre_role = Column(String(64), nullable=True)
    notes = Column(String(1024), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
