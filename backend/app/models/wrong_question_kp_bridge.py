"""R6a 错题→知识点桥表（wrong_question_kp_bridge）。

student_wrong_questions 历史错题 ↔ PG 资产库知识点的跨库匹配结果落表。
- 只写主 MySQL 库；PG 资产库只读，跨库匹配在 Python 侧完成（不做跨库 SQL）。
- PK = wrong_question_id（student_wrong_questions.id），回填幂等（ON DUPLICATE KEY）。
- kp_id：knowledge_points.id 收录的名称才有值；历史标题匹配多为题库标签（如
  「统计与概率」「单位换算」），未收录时 kp_id 为 NULL，仅保留 kp_name 文本。
"""
from sqlalchemy import Column, Float, Index, String, DateTime
from sqlalchemy.sql import func

from app.database import Base


class WrongQuestionKpBridge(Base):
    __tablename__ = "wrong_question_kp_bridge"
    __table_args__ = (
        Index("idx_wqkp_subject", "subject"),
        Index("idx_wqkp_kp_id", "kp_id"),
    )

    wrong_question_id = Column(String(36), primary_key=True)  # student_wrong_questions.id
    kp_id = Column(String(36), nullable=True)  # knowledge_points.id（未收录时 NULL）
    kp_name = Column(String(128), nullable=False)
    subject = Column(String(64), nullable=False)
    # 匹配方式：question_exact / question_includes / kp_exact / kp_includes / kp_keyword
    match_method = Column(String(32), nullable=False)
    confidence = Column(Float, nullable=True)
    matched_at = Column(DateTime, server_default=func.now())
