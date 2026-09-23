"""错题表

@deprecated：废弃空表（0 行），学校错题唯一权威为 StudentWrongQuestion，P3-B3 修正后不新增列
"""
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class WrongQuestion(Base):
    __tablename__ = "wrong_questions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    school_id = Column(String(36), nullable=True, index=True, comment="所属学校,多校归属收敛 R2")
    subject = Column(String(64), nullable=False)
    question_content = Column(Text, nullable=False)
    correct_answer = Column(Text, nullable=True)
    student_answer = Column(Text, nullable=True)
    error_type = Column(String(64), nullable=False, default="other")
    analysis = Column(Text, nullable=True)
    exam_id = Column(String(36), ForeignKey("exams.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
