"""教案表：按账户 + 班级 + 学科隔离"""
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.database import Base
from app.models.user import gen_uuid


class LessonPlan(Base):
    __tablename__ = "lesson_plans"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    school_year = Column(String(32), nullable=True)
    term = Column(String(32), nullable=True)
    grade = Column(String(32), nullable=True)
    subject = Column(String(32), nullable=False, index=True)
    title = Column(String(255), nullable=False, default="")
    teaching_content = Column(Text, nullable=True)
    teaching_objectives = Column(Text, nullable=True)
    key_points = Column(Text, nullable=True)
    difficult_points = Column(Text, nullable=True)
    teaching_preparation = Column(Text, nullable=True)
    teaching_process = Column(Text, nullable=True)
    collective_preparation_advice = Column(Text, nullable=True)
    blackboard_design = Column(Text, nullable=True)
    teaching_reflection = Column(Text, nullable=True)
    main_author = Column(String(255), nullable=True)
    deputy_author = Column(String(255), nullable=True)
    lesson_sequence = Column(String(64), nullable=True)
    # R4 备课 MVP：教材级联字段（textbook_catalogs 目录节点，均可空，旧数据不受影响）
    textbook_id = Column(String(36), nullable=True, index=True)  # 教材 id（edition 级节点）
    unit_id = Column(String(36), nullable=True, index=True)      # 单元 id（unit 级节点）
    catalog_id = Column(String(36), nullable=True, index=True)   # 目录节点 id（任意层级）
    edition = Column(String(64), nullable=True)                  # 教材版本（如「人教版」）
    chapter = Column(String(128), nullable=True)                 # 章/节名
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
