"""测评题组定义表（B0 契约 §2.1）

自研轻量题组定义：题面、选项、维度映射、计分规则。运营人员可动态增删改。
学术安全线：题面文案不得含人格归因词，只做行为观察 / 学习方式 / 兴趣倾向描述。
"""
from sqlalchemy import JSON, Column, String, Integer, Text, Boolean, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class AssessmentDefinition(Base):
    __tablename__ = "assessment_definitions"
    __table_args__ = (
        Index("idx_ad_domain", "domain"),
        Index("idx_ad_status", "status"),
        Index("idx_ad_domain_status", "domain", "status"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(128), nullable=False, comment="题组名称")
    domain = Column(String(64), nullable=False, comment="测评域: personality/interest/learning_style/self_built_survey")
    grade_range = Column(String(32), nullable=False, default="all", comment="适用学段: primary/junior/senior/all")
    version = Column(Integer, nullable=False, default=1, comment="版本号，从1开始递增")
    status = Column(String(16), nullable=False, default="draft", comment="状态: draft/active/retired")
    consent_required = Column(Boolean, nullable=False, default=True, comment="是否需要监护人同意")
    questions = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False, comment="题面数组（见 B0 §2.1 questions JSON 结构）")
    description = Column(Text, nullable=True, comment="题组说明/指导语")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
