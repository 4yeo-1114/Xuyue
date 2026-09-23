from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, Text, UniqueConstraint, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.sql import func

from app.database import Base
from app.models.user import gen_uuid


class ClassReviewSession(Base):
    __tablename__ = "class_review_sessions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    subject = Column(String(64), nullable=False, index=True)
    # 按账号隔离：课堂讲评只对创建它的老师可见，避免不同老师导入同一班级科目时互相覆盖
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    title = Column(String(255), nullable=True)

    exam_names_json = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    imported_folder_names_json = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    source_summary_json = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    pre_class_json = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    tracking_json = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    consolidation_json = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    post_feedback_json = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    ai_raw_json = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)

    # E05 · AI 内容统一标识（GB 45438 隐式标识）：本表全部 AI 生成，生成时显式写 is_ai=1 + ai_meta
    is_ai = Column(Boolean, nullable=False, default=1, server_default="1", comment="AI内容统一标识(GB45438):1=AI生成")
    ai_meta = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True, comment="AI生成元数据:{generator,model}")

    generated_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("class_id", "subject", "user_id", name="uq_class_review_session_class_subject"),
    )
