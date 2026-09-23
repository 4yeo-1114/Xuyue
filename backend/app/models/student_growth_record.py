"""学生成长记录流水表（99-reconciliation §4.1.2）"""
from sqlalchemy import JSON, Column, String, Integer, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class StudentGrowthRecord(Base):
    __tablename__ = "student_growth_records"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    student_id = Column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    school_id = Column(String(36), nullable=True)
    # E02：dimension 扩展支持 ai_literacy（AI 素养）。列是 VARCHAR(32)，无 CHECK/枚举约束，
    # 老数据可读，无需迁移即可写入新维度。
    dimension = Column(String(32), nullable=False)  # moral|intellectual|physical|aesthetic|labor|ai_literacy
    # E02：source_type 支持 ai_course/ai_project（AI 课程过程性成果/作品/素养表现），
    # 走现有 growth 事件/写入链路，复用幂等逻辑。
    source_type = Column(String(32), nullable=False, default="manual")
    source_id = Column(String(36), nullable=True)   # 来源记录ID，幂等去重键之一
    indicator_id = Column(String(36), ForeignKey("indicator_definitions.id", ondelete="SET NULL", name="fk_sgr_indicator"), nullable=True, index=True)  # 二级指标字典ID，纯归类标签
    growth_points = Column(Integer, nullable=False, default=0)
    evidence = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)
    note = Column(String(512), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_sgr_student_id", "student_id"),
        Index("idx_sgr_student_dim", "student_id", "dimension"),
        Index("idx_sgr_student_time", "student_id", "occurred_at"),
        Index("idx_sgr_source", "source_type", "source_id"),
    )
