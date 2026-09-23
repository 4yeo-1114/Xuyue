"""R6b contextual bandit 状态表（bandit_arm_stats）。

记录每学生每学科每 arm（薄弱知识点）的 LinUCB 状态与推荐/反馈统计：
- a_json / b_json：LinUCB 每 arm 的上下文协方差矩阵 A(4x4) 与奖励向量 b(4)，
  JSON 序列化跨请求持久化（无 reward 时保持初始化态，有 reward 后逐步收敛）。
- impressions / clicks / reward_sum：推荐曝光 / 点击 / 累计奖励（供后续点击率分析）。

写库非关键路径：表不存在（AUTO_DDL=false）或写失败仅告警，不影响推荐主流程。
幂等建表照抄 app/database.py `_ensure_*` 风格。
"""
from sqlalchemy import JSON, Column, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base
from app.models.user import gen_uuid


class BanditArmStats(Base):
    __tablename__ = "bandit_arm_stats"
    __table_args__ = (
        UniqueConstraint("student_id", "subject", "kp_key", name="uq_bandit_arm"),
        Index("ix_bandit_arm_student", "student_id"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    student_id = Column(String(36), nullable=False, index=True)
    subject = Column(String(64), nullable=False, index=True)
    kp_key = Column(String(128), nullable=False, comment="薄弱知识点键（kp_id 或 kp_name）")
    kp_name = Column(String(128), nullable=False)
    mode = Column(String(16), nullable=False, default="explore")
    impressions = Column(Integer, nullable=False, default=0)
    clicks = Column(Integer, nullable=False, default=0)
    reward_sum = Column(Float, nullable=False, default=0.0)
    ucb_score = Column(Float, nullable=False, default=0.0)
    a_json = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True, comment="LinUCB A 矩阵(4x4) JSON")
    b_json = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True, comment="LinUCB b 向量(4) JSON")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
