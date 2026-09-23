"""访问留痕表（E03 监护人同意闭环 + E14 合规后台）。

记录对 6-15 岁学生个人信息（PIPL 敏感信息）的敏感读取与高危行权动作，
供教师/管理员代办行权与年度审计导出使用。
写失败不阻断主流程（见 app/services/audit/access_log.py，内部 try/except）。
"""
from sqlalchemy import JSON, Column, String, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class AccessLog(Base):
    __tablename__ = "access_logs"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), nullable=False, comment="操作用户 → users.id")
    user_role = Column(String(32), nullable=False, comment="中文角色，如 管理员/班主任")
    action = Column(String(32), nullable=False, comment="view_report|view_portfolio|view_growth|view_archive|ai_report|export|delete|correct|consent_change")
    target_type = Column(String(32), nullable=False, comment="student|class")
    target_id = Column(String(36), nullable=False, comment="student_id 或 class_id")
    detail = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True, comment="补充：report_type/term/字段名等")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_al_target_time", "target_id", "created_at"),
        Index("idx_al_user_time", "user_id", "created_at"),
        Index("idx_al_action", "action"),
    )
