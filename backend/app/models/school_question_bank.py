"""C2 校本题库表（SchoolQuestionBank）。

DL4a（C2 校本题库数据层落地）：
- 题库唯一键 = UNIQUE(school_id, fingerprint)：同一道题跨多张卷子收敛到同一条记录，
  从而叠加正答率等统计（见 DL3 app/utils/question_fingerprint.py）。
- 指纹来源 `app.utils.question_fingerprint.question_fingerprint()`，输出
  ``fp_`` 前缀 + 64 位小写 hex（总长 67 字符），故 fingerprint 列用 VARCHAR(67)。
- P0 语义：实质内容变化（改科目 / 改题型 / 改题干 / 改答案）⇒ 指纹变化 ⇒ 视为新题；
  仅排版级差异 ⇒ 指纹不变 ⇒ 同一题。
- knowledge_point_id 为知识点锚点扩展位（知识点锚表未定，本表不加外键）。
"""
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class SchoolQuestionBank(Base):
    """校本题库表。school_id → schools.id；UNIQUE(school_id, fingerprint) 为题库唯一键。"""
    __tablename__ = "school_question_banks"
    __table_args__ = (
        UniqueConstraint("school_id", "fingerprint", name="uq_sqb_school_fp"),
        Index("idx_sqb_school_id", "school_id"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    school_id = Column(String(36), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)  # 所属学校，锚点 schools.id
    subject = Column(String(64), nullable=True)  # 科目
    question_type = Column(String(32), nullable=True)  # 题型
    question_text = Column(Text, nullable=False)  # 题干（指纹来源）
    correct_answer = Column(Text, nullable=True)  # 参考答案
    knowledge_point_id = Column(String(36), nullable=True, comment="知识点锚点（预留，知识点锚表未定，不加外键）")
    fingerprint = Column(String(67), nullable=False, comment="题目稳定ID指纹，question_fingerprint 输出 fp_+64hex，总长 67")
    difficulty = Column(String(16), nullable=True)  # 难度
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
