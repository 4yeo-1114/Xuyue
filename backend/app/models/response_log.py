# -*- coding: utf-8 -*-
"""逐题响应日志表（R1 · 数据底座）。

记录每张试卷每个题 / 作答区的批改结果，供学情预警 / bandit 错题推荐使用。
纯追加表（只 INSERT，不做 DELETE/UPDATE），旁路写入不阻断批改主流程。
school_id 预留给 R2 回填（当前可空）。
"""
from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base
from app.models.user import gen_uuid


class ResponseLog(Base):
    __tablename__ = "response_logs"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    school_id = Column(String(36), nullable=True, comment="学校 id（R2 回填）")
    student_id = Column(String(36), nullable=True, index=True)
    class_id = Column(String(36), nullable=True)
    subject = Column(String(64), nullable=True)
    grade = Column(String(32), nullable=True, comment="年级（R2 作业采集）")
    homework_type = Column(String(64), nullable=True, comment="作业类型（R2 作业采集）")
    folder_safe = Column(String(255), nullable=True, index=True)
    paper_name = Column(String(255), nullable=True)
    engine = Column(String(32), nullable=True)
    question_id = Column(String(64), nullable=True, index=True, comment="题号 / slot_id")
    question_content = Column(Text, nullable=True)
    correct_answer = Column(Text, nullable=True)
    student_answer = Column(Text, nullable=True)
    status = Column(String(16), nullable=True, comment="correct|wrong|partial|unanswered")
    is_correct = Column(Boolean, nullable=True)
    score = Column(Float, nullable=True)
    max_score = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    raw_json = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True, comment="原始批改块快照")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_rl_user_created", "user_id", "created_at"),
        Index("idx_rl_subject_created", "subject", "created_at"),
        Index("idx_rl_student", "student_id"),
    )
