from sqlalchemy import JSON, Text, Column, DateTime, Index, String, UniqueConstraint, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.sql import func

from app.database import Base
from app.models.user import gen_uuid


class ClassAnalysisReport(Base):
    __tablename__ = "class_analysis_reports"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    report_uuid = Column(String(36), nullable=False, default=gen_uuid)
    class_id = Column(String(36), nullable=False, index=True)
    class_name = Column(String(128), nullable=False, index=True)
    subject = Column(String(64), nullable=False, index=True)

    exam_names_json = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    imported_folder_names_json = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    source_summary_json = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    analysis_json = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)

    # E05 · AI 内容统一标识（GB 45438 隐式标识）：本表全部 AI 生成，生成时显式写 is_ai=1 + ai_meta
    is_ai = Column(Boolean, nullable=False, default=1, server_default="1", comment="AI内容统一标识(GB45438):1=AI生成")
    ai_meta = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True, comment="AI生成元数据:{generator,model}")

    generated_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("class_id", "subject", name="uq_class_analysis_report_class_subject"),
        Index("ix_class_analysis_report_name_subject", "class_name", "subject"),
    )
