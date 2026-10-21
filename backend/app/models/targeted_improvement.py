from sqlalchemy import JSON, Text, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, Boolean
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


class TargetedImprovementTask(Base):
    """个性化学习任务清单（客户功能 #15 闭环）。

    从靶向报告 plan_json 的 phases[].student_tasks / stages[].dailyTasks 等抽成可勾选任务行；
    同一 report 重复 sync 按 (class_id, student_name, subject, report_id, task_text) 应用层去重。
    """
    __tablename__ = "targeted_improvement_tasks"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(String(36), ForeignKey("students.id", ondelete="SET NULL"), nullable=True, index=True)
    student_name = Column(String(128), nullable=False, index=True)
    subject = Column(String(64), nullable=False, index=True)
    report_id = Column(String(36), ForeignKey("targeted_improvement_reports.id", ondelete="SET NULL"), nullable=True, index=True)
    task_text = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=False)
    stage_label = Column(String(128), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    is_done = Column(Boolean, nullable=False, default=False, server_default="0")
    done_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_tit_class_student_subject", "class_id", "student_name", "subject"),
        # 生产 DDL 口径：字符串列 COLLATE 用 0900_ai_ci（memory/xuyue-ddl-drift）
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"},
    )
