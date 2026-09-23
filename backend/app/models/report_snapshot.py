"""学期报告快照（99-reconciliation §4.1.3，冻结不可变，无 updated_at）"""
from sqlalchemy import JSON, Column, String, Integer, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class ReportSnapshot(Base):
    __tablename__ = "report_snapshots"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    student_id = Column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    school_id = Column(String(36), nullable=True)
    term = Column(String(32), nullable=False)  # 2025-2026-1
    version = Column(Integer, nullable=False, default=1)
    parent_id = Column(String(36), ForeignKey("report_snapshots.id", ondelete="SET NULL"), nullable=True)
    payload = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False)
    generated_by = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("student_id", "term", "version", name="uq_rs_student_term_version"),
        Index("idx_rs_class_term", "class_id", "term"),
    )
