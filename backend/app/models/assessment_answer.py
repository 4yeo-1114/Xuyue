"""作答明细表（B0 契约 §2.4，只读快照表，无 updated_at）

存储每题作答明细（可选）：v1 推荐直接写 assessment_results.raw_score.answers（JSON 内嵌），
本表在需要逐题分析 / 跨学生聚合某题作答分布 / 审计时启用。
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class AssessmentAnswer(Base):
    __tablename__ = "assessment_answers"
    __table_args__ = (
        Index("idx_aa_result", "result_id"),
        Index("idx_aa_result_question", "result_id", "question_id"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    result_id = Column(String(36), ForeignKey("assessment_results.id", ondelete="CASCADE"), nullable=False, comment="锚点结果ID → assessment_results.id")
    question_id = Column(String(32), nullable=False, comment="题号，如 ls_q1")
    option_key = Column(String(8), nullable=False, comment="选择的选项键")
    dim = Column(String(64), nullable=False, comment="顶层维度键")
    option_dim = Column(String(64), nullable=True, comment="子维度键")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
