"""考试成绩表"""
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, UniqueConstraint, Numeric, Integer
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class ExamScore(Base):
    __tablename__ = "exam_scores"
    __table_args__ = (UniqueConstraint("exam_id", "student_id", name="uq_exam_student"),)

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    exam_id = Column(String(36), ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    school_id = Column(String(36), nullable=True, index=True, comment="所属学校,多校归属收敛 R2")
    score = Column(Float, nullable=True)
    # E04《未成年人学校保护规定》：成绩等级制，等级呈现、不公开不排名。
    # 取值契约：excellent | good | pass | needs_work；score 为空 → grade 为空。
    grade = Column(String(16), nullable=True, comment="成绩等级:excellent|good|pass|needs_work")
    class_avg = Column(Numeric(10, 2), nullable=True, comment="班级平均分(库补列, P3-B3 回写)")
    class_id = Column(String(36), nullable=True, comment="班级 id(库补列, P3-B3 回写)")
    class_rank = Column(Integer, nullable=True, comment="班级排名(库补列, P3-B3 回写)")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
