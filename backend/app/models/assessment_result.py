"""锚点结果表（B0 契约 §2.3）

存储学生作答后的锚点结果，物理隔离于五育评分体系。每份作答生成一条记录。

学术红线：purpose 字段有 CHECK 约束强制 'anchor'，防止评分用途误入。
guardian_consent 状态机：not_required ─→ granted ─→ withdrawn ─→ granted ─→ ...
                                  version 每次恢复 +1
"""
from sqlalchemy import JSON, Column, String, DateTime, ForeignKey, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class AssessmentResult(Base):
    __tablename__ = "assessment_results"
    __table_args__ = (
        Index("idx_ar_student", "student_id"),
        Index("idx_ar_domain", "domain"),
        Index("idx_ar_definition", "definition_id"),
        Index("idx_ar_session", "session_id"),
        # 学术红线：purpose 只允许 anchor，评分用途直接被数据库拒绝
        CheckConstraint("purpose = 'anchor'", name="chk_ar_purpose"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    student_id = Column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, comment="学生ID → students.id")
    definition_id = Column(String(36), ForeignKey("assessment_definitions.id", ondelete="SET NULL"), nullable=True, comment="题组定义ID → assessment_definitions.id")
    session_id = Column(String(36), ForeignKey("assessment_sessions.id", ondelete="SET NULL"), nullable=True, comment="关联会话ID → assessment_sessions.id")
    domain = Column(String(64), nullable=False, comment="测评域，继承自题组的domain")
    purpose = Column(String(16), nullable=False, default="anchor", comment="用途: 强制anchor（锚点），DB约束兜底")
    tag_schema = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False, comment="白名单标签结果 {labels, dimension_percents, generated_at}")
    raw_score = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True, comment="原始作答数据 {answers, dimension_points, total_answered}")
    guardian_consent = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False, comment="监护人同意状态 {status, version, granted_at, withdrawn_at}")
    created_by = Column(String(36), nullable=True, comment="创建者ID → users.id")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
