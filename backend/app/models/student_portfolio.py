"""学生五育画像主表（99-reconciliation §4.1.1）"""
from sqlalchemy import JSON, Column, String, Integer, DateTime, ForeignKey, Numeric, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class StudentPortfolio(Base):
    __tablename__ = "student_portfolios"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    student_id = Column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    school_id = Column(String(36), nullable=True)
    base_points = Column(Integer, nullable=False, default=100, server_default="100")
    # {"moral":0,"intellectual":15.5,"physical":0,"aesthetic":0,"labor":0,"ai_literacy":0,"total":15.5}
    # E02：ai_literacy 为增量键（AI 素养），旧数据缺省按 0 处理；聚合/返回时老记录不报错。
    dimensions = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False)
    detail = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)
    auto_detail = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)
    total_growth_point = Column(Numeric(10, 2), nullable=False, default=0, server_default="0.00")
    last_calculated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("student_id", name="uq_sp_student_id"),
        Index("idx_sp_class_id", "class_id"),
    )
