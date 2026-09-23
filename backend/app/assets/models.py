"""P0 资产引擎只读模型（家长端 PG 资产库镜像映射，字段以家长端为权威）。

- 统一挂 assets_base（独立 declarative_base），与主平台 Base 完全隔离：
  绝不 from app.database import Base，否则资产表会被 Base.metadata.create_all
  误建进主 MySQL 库造成启动 DDL 报错。
- 全部只读映射既有 PG 表，不建表不迁移。
- 表名与家长端实际表名一致（questions / knowledge_points / question_kp /
  subject_units / difficulty_gold）。
"""
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON, JSONB
from sqlalchemy.sql import func

from app.assets.database import assets_base


class Question(assets_base):
    """统一题库入库表（家长端 questions）— 资产抽题主数据源。"""

    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("source", "raw_id", name="uq_questions_source_raw_id"),
    )

    id = Column(String(36), primary_key=True)
    subject = Column(String(32), nullable=False, index=True)
    grade = Column(String(16), nullable=True, index=True)
    question_type = Column(String(16), nullable=False, index=True)
    question = Column(Text, nullable=False)
    options = Column(JSON, nullable=True)
    answer = Column(Text, nullable=False)
    analysis = Column(Text, nullable=True)
    knowledge_point = Column(String(128), nullable=True, index=True)
    difficulty = Column(Integer, nullable=False, default=3)
    source = Column(String(32), nullable=False, index=True)
    raw_id = Column(String(128), nullable=False)
    unique_key = Column(String(64), unique=True, index=True, nullable=False)
    curriculum = Column(String(16), default="k12")
    difficulty_source = Column(String(16), nullable=True, index=True)
    difficulty_updated_at = Column(DateTime(timezone=True), nullable=True)
    esl_level = Column(Integer, nullable=True, index=True)
    esl_level_source = Column(String(16), nullable=True, index=True)
    # 抽题质量过滤关键列（必须映射）：ok/filled=可入池, bad/dup/...=禁入, NULL=放行
    quality_flag = Column(String(16), nullable=True, index=True)
    # AI 出题验收判级：pass/reject/review，NULL=存量真实题（放行）
    ai_verdict = Column(String(16), nullable=True, index=True)
    ai_confidence = Column(String(16), nullable=True, index=True)
    ai_judge_source = Column(String(16), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class KnowledgePoint(assets_base):
    """知识点表（家长端 knowledge_points）。"""

    __tablename__ = "knowledge_points"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    unit_id = Column(String(36), ForeignKey("subject_units.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    name = Column(String(256), nullable=False)
    level = Column(String(32), nullable=True)
    mastery = Column(Float, default=0, nullable=False)
    is_weak = Column(Boolean, default=False, nullable=False)
    prerequisite = Column(JSON, nullable=True)
    postrequisite = Column(JSON, nullable=True)
    related = Column(JSON, nullable=True)
    is_a = Column(JSON, nullable=True)
    hours = Column(Integer, default=0, nullable=False)
    key_point = Column(String(512), nullable=True)
    difficulty = Column(String(32), nullable=True)
    common_errors = Column(Text, nullable=True)
    resources = Column(JSON, nullable=True)
    standard_code = Column(String(64), nullable=True, index=True)
    standard_id = Column(String(36), ForeignKey("curriculum_standards.id"), nullable=True)
    curriculum = Column(String(16), default="k12", nullable=False, index=True)
    # C0 知识本质四分类：fact/rule/procedure/symbol
    knowledge_nature = Column(String(16), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class QuestionKp(assets_base):
    """题→知识点多对多桥接表（家长端 question_kp）。"""

    __tablename__ = "question_kp"
    __table_args__ = (
        PrimaryKeyConstraint("question_id", "kp_id", name="question_kp_pkey"),
        Index("idx_question_kp_kp_id", "kp_id"),
        Index("idx_question_kp_question_id", "question_id"),
    )

    question_id = Column(String(36), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    kp_id = Column(String(36), ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False)
    matched_via = Column(String(16), nullable=False, default="exact")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SubjectUnit(assets_base):
    """学科单元表（家长端 subject_units）。"""

    __tablename__ = "subject_units"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject = Column(String(64), nullable=False, index=True)
    semester = Column(String(32), nullable=False, index=True)
    grade = Column(String(16), nullable=True, index=True)
    unit_index = Column(Integer, nullable=False)
    name = Column(String(256), nullable=False)
    subtitle = Column(String(256), nullable=True)
    curriculum = Column(String(16), default="k12", nullable=False, index=True)
    standard_id = Column(String(36), ForeignKey("curriculum_standards.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DifficultyGold(assets_base):
    """题目难度评测集 DB 镜像（家长端 difficulty_gold）。"""

    __tablename__ = "difficulty_gold"
    __table_args__ = (
        Index("idx_difficulty_gold_subject", "subject"),
        Index("idx_difficulty_gold_gold_diff", "gold_difficulty"),
    )

    question_id = Column(String(36), primary_key=True)
    subject = Column(String(32), nullable=True)
    grade = Column(String(16), nullable=True)
    question_type = Column(String(16), nullable=True)
    question = Column(Text, nullable=True)
    options = Column(JSON, nullable=True)
    answer = Column(Text, nullable=True)
    analysis = Column(Text, nullable=True)
    knowledge_point = Column(String(128), nullable=True)
    sys_difficulty = Column(Integer, nullable=True)
    sys_difficulty_source = Column(String(16), nullable=True)
    seed_difficulty = Column(Integer, nullable=True)
    gold_difficulty = Column(Integer, nullable=True)
    gold_verdict = Column(String(16), nullable=True)
    source = Column(String(32), nullable=True)
    source_seed = Column(String(128), nullable=True)
    confidence = Column(String(8), nullable=True)
    model = Column(String(32), nullable=True)
    reason = Column(Text, nullable=True)
    annotated_by = Column(String(64), nullable=True)
    annotated_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(16), nullable=False, default="confirmed")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class IdentityLink(assets_base):
    """R3 身份统一桥表（家长端 PG identity_link）— 学校端学生(MySQL) ↔ 家长端学生(PG)。

    只读映射既有 PG 表（docs/migrations/2026-08-29-identity-link.sql 建表）。
    写入红线：主平台绝不写家长端 PG，identity_link 写入只走 SQL 脚本 / 人工，
    本模型不提供任何写路径（无 add/flush 调用）。
    school_db_profile_id 支持多租户，默认 'local'；匹配依据存 matched_by jsonb 快照。
    """

    __tablename__ = "identity_link"
    __table_args__ = (
        UniqueConstraint(
            "school_db_profile_id", "school_student_id", "parent_student_id",
            name="uq_identity_link_school",
        ),
        UniqueConstraint("parent_student_id", name="uq_identity_link_parent_s"),
        UniqueConstraint(
            "parent_user_id", "school_db_profile_id", "school_student_id",
            name="uq_identity_link_parent_u",
        ),
        Index("idx_identity_link_school", "school_db_profile_id", "school_student_id"),
        Index("idx_identity_link_parent_s", "parent_student_id"),
        Index("idx_identity_link_parent_u", "parent_user_id"),
    )

    id = Column(String(36), primary_key=True)
    school_db_profile_id = Column(String(36), nullable=False, default="local")
    school_student_id = Column(String(36), nullable=False)
    parent_student_id = Column(String(36), ForeignKey("students.id"), nullable=False)
    parent_user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    link_method = Column(String(16), nullable=False, default="manual")
    confidence = Column(Numeric(4, 3), nullable=False, default=0)
    source = Column(String(32), nullable=True)
    matched_by = Column(JSONB, nullable=True)
    status = Column(String(16), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
