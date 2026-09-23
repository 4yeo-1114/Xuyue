"""施测会话表（B0 契约 §2.2）

记录每次施测的会话，支持 class_batch（教师集中批次）和 self（学生自主重测）两种模式。

状态机：
    pending ─→ in_progress ─→ submitted ─→ graded
      │                                      │
      └────────────── canceled ←─────────────┘（仅 pending/in_progress 可取消）
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class AssessmentSession(Base):
    __tablename__ = "assessment_sessions"
    __table_args__ = (
        Index("idx_as_student", "student_id"),
        Index("idx_as_definition", "definition_id"),
        Index("idx_as_status", "status"),
        Index("idx_as_batch", "batch_id"),
        Index("idx_as_student_def", "student_id", "definition_id"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    student_id = Column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, comment="学生ID → students.id")
    definition_id = Column(String(36), ForeignKey("assessment_definitions.id", ondelete="CASCADE"), nullable=False, comment="题组定义ID → assessment_definitions.id")
    test_mode = Column(String(16), nullable=False, default="class_batch", comment="施测模式: class_batch/self")
    batch_id = Column(String(36), nullable=True, comment="批次ID（class_batch模式下关联同一批次）")
    status = Column(String(16), nullable=False, default="pending", comment="状态: pending/in_progress/submitted/graded/canceled")
    proctored_by = Column(String(36), nullable=True, comment="监考/施测教师ID → users.id")
    created_by = Column(String(36), nullable=True, comment="会话创建者ID → users.id")
    taken_at = Column(DateTime(timezone=True), nullable=True, comment="学生开始作答时间")
    submitted_at = Column(DateTime(timezone=True), nullable=True, comment="提交时间")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
