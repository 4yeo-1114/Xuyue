from sqlalchemy import JSON, Text, Column, DateTime, ForeignKey, String, UniqueConstraint, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.sql import func

from app.database import Base
from app.models.user import gen_uuid


class TargetedImprovementReport(Base):
    __tablename__ = "targeted_improvement_reports"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(String(36), ForeignKey("students.id", ondelete="SET NULL"), nullable=True, index=True)
    student_name = Column(String(128), nullable=False, index=True)
    student_number = Column(String(64), nullable=True)
    subject = Column(String(64), nullable=False, index=True)

    diagnosis_text = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    plan_text = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    diagnosis_json = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    plan_json = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    source_summary_json = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    exam_names_json = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    imported_folder_names_json = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    ai_raw_json = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)

    # E05 · AI 内容统一标识（GB 45438 隐式标识）：本表全部 AI 生成，生成时显式写 is_ai=1 + ai_meta
    is_ai = Column(Boolean, nullable=False, default=1, server_default="1", comment="AI内容统一标识(GB45438):1=AI生成")
    ai_meta = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True, comment="AI生成元数据:{generator,model}")

    generated_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("class_id", "student_name", "subject", name="uq_targeted_report_class_student_subject"),
    )


class TargetedRecommendation(Base):
    __tablename__ = "targeted_recommendations"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    subject = Column(String(64), nullable=False, index=True)
    student_names_json = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=False)  # 对齐库侧 LONGTEXT(P3-C1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("class_id", "subject", name="uq_targeted_recommendation_class_subject"),
    )
