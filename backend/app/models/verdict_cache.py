# -*- coding: utf-8 -*-
"""判分缓存表（C 项：同（题, 作答）二次出现直接复用判分）。

cache_key = question_fingerprint(subject, question_type, question_content,
correct_answer) + ":" + text_fingerprint(student_answer)。
人工修正（source=human）为最高优先级判据：human 可覆盖 ai 行，ai 永不覆盖 human 行。

红线（见 app/grading/verdict_cache.py cache_key）：question_content /
correct_answer / student_answer 任一为空不进缓存——空键同值必串判。
"""
from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class VerdictCache(Base):
    __tablename__ = "verdict_cache"

    # fp_(67) + ":" + hex(64) = 132 字符；定长 String(140) 留量
    cache_key = Column(String(140), primary_key=True)
    question_fingerprint = Column(String(67), nullable=False, index=True, comment="题目稳定 ID（fp_ 前缀）")
    student_answer_hash = Column(String(64), nullable=False, comment="作答文本指纹（64 hex）")
    result = Column(String(16), nullable=False, comment="对|错|半对|未作答")
    comment = Column(Text, nullable=True)
    partial_ratio = Column(Float, nullable=True)
    source = Column(String(8), nullable=False, comment="human|ai")
    subject_family = Column(String(32), nullable=True)
    engine = Column(String(32), nullable=True, comment="首个写入该行的引擎")
    hit_count = Column(Integer, nullable=False, default=0, comment="命中次数（观察用）")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_vc_fp_source", "question_fingerprint", "source"),
    )
