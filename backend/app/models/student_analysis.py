from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid

class StudentAnalysis(Base):
    __tablename__ = "student_analysis"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    student_name = Column(String(64), nullable=False, index=True)
    subject = Column(String(64), nullable=False, index=True)
    
    target_score = Column(Integer, nullable=True)
    current_score = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class StudentScoreHistory(Base):
    __tablename__ = "student_score_history"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    student_name = Column(String(64), nullable=False, index=True)
    subject = Column(String(64), nullable=False, index=True)
    
    exam_name = Column(String(128), nullable=False)
    score = Column(Integer, nullable=False)
    class_avg = Column(Integer, nullable=True) # New column for class average

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

class StudentWrongQuestion(Base):
    __tablename__ = "student_wrong_questions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    student_name = Column(String(64), nullable=False, index=True)
    subject = Column(String(64), nullable=False, index=True)
    
    exam_name = Column(String(128), nullable=False)
    question_title = Column(String(255), nullable=False)
    
    image_url = Column(String(512), nullable=True)
    answer_url = Column(String(512), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # P3-B3 错题实体统一：多校归属与订正状态列（学校错题唯一权威，库补列幂等 ensure）
    school_id = Column(String(36), nullable=True, index=True, comment="所属学校,多校归属收敛 R2")
    corrected_at = Column(DateTime(timezone=True), nullable=True, comment="订正时间")
    knowledge_point_id = Column(String(36), nullable=True, index=True, comment="知识点 id")
    status = Column(String(16), nullable=False, server_default="open", comment="错题状态:open|closed")

