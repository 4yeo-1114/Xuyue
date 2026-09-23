"""学生成长印记（动态相册）记录（种春风 P0 合同缺口，A0 §6 学生五育画像扩展）。

教师上传的学生成长照片/影像索引，图片文件落盘 assets/memories/，
本表仅存元数据与相对路径。
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class StudentMemory(Base):
    __tablename__ = "student_memories"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    student_id = Column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    school_id = Column(String(36), nullable=True)
    # assets/memories 下的相对路径，如 2026-08/<uuid>.jpg
    image_path = Column(String(512), nullable=False)
    caption = Column(String(200), nullable=True)
    source_type = Column(String(32), nullable=False, default="memory", server_default="memory")
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_student_memory_student", "student_id"),
        Index("idx_student_memory_created", "created_at"),
    )
