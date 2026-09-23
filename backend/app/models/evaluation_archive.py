"""综评档案（EvaluationArchive）——补齐合同「写实记录→遴选→公示→成档」。

状态流：draft(待遴选) → selected(已遴选) → publicity(公示中) → archived(已存档)。
公示中可撤回(→draft)，公示期默认 7 天（由路由写入 publicity_end_at）。
与 ReportSnapshot（学期报告冻结版本链）配合：报告快照即「成档」出口，本条记录驱动公示流程。

@deprecated：死模型（库无表），P3 迁移不参与，勿注册 create_all
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class EvaluationArchive(Base):
    __tablename__ = "evaluation_archives"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    term = Column(String(32), nullable=False)  # 2025-2026-1
    status = Column(String(16), nullable=False, default="draft", server_default="draft")
    selected_at = Column(DateTime(timezone=True), nullable=True)
    publicity_at = Column(DateTime(timezone=True), nullable=True)
    publicity_end_at = Column(DateTime(timezone=True), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    operator_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("class_id", "student_id", "term", name="uq_ea_class_student_term"),
        Index("idx_ea_class_term_status", "class_id", "term", "status"),
    )
