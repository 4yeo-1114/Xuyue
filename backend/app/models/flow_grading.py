# -*- coding: utf-8 -*-
"""流水阅卷 / 集体阅卷 数据模型（flow_* 前缀）。

权威存储 = 数据库表（多老师并发、原子领取、进度/速度/历史需实时 SQL 聚合），
文件层只存图片（裁图 / 完整卷归档 / 留痕图），沿用现有「图片文件 + 短时下载票」模式。
每次 review 提交旁路写一条 response_logs（engine="flow"）与现有学情/错题底座打通。
"""
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base
from app.models.user import gen_uuid


class FlowBatch(Base):
    __tablename__ = "flow_batches"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False, comment="批次名，如「七年级数学期中」")
    subject = Column(String(64), nullable=False, comment="科目（与教师同科目过滤对齐）")
    grade = Column(String(32), nullable=True, comment="年级（原始写法）")
    grade_norm = Column(String(32), nullable=True, comment="年级规范值")
    school_id = Column(String(36), nullable=True)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    source_folder_safe = Column(String(255), nullable=True, comment="扫描入夹的源文件夹 safe 名")
    class_ids_json = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True, comment="全年级班级 id 列表")
    review_mode = Column(String(16), nullable=False, default="single", comment="single|double（批次默认，题目可覆盖）")
    resolver = Column(String(32), nullable=False, default="roster", comment="roster|barcode（学号解析器）")
    auto_objective = Column(Boolean, nullable=False, default=False, comment="是否用答案比对预判客观题")
    total_papers = Column(Integer, nullable=False, default=0, comment="学生卷总数（切割后回填）")
    status = Column(String(16), nullable=False, default="created", index=True,
                   comment="created/cutting/assigning/grading/arbitration/completed/canceled")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_flow_batch_subject_grade", "subject", "grade"),
    )


class FlowQuestion(Base):
    __tablename__ = "flow_questions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    batch_id = Column(String(36), ForeignKey("flow_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    question_no = Column(Integer, nullable=False, comment="题号")
    display_label = Column(String(64), nullable=True, comment="「第3题」或卷面题号")
    slot_ids_json = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True, comment="该题合并的作答区 slot_id 列表")
    max_score = Column(Float, nullable=False, default=0, comment="该题满分")
    review_mode = Column(String(16), nullable=True, comment="single|double，空则继承批次")
    standard_answer = Column(Text, nullable=True, comment="顶部标准答案框内容")
    crop_dir = Column(String(64), nullable=True, comment="相对 q{question_no}")
    total_items = Column(Integer, nullable=False, default=0, comment="该题学生卷总数")
    status = Column(String(16), nullable=False, default="pending",
                    comment="pending/assigned/grading/arbitration/completed")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("batch_id", "question_no", name="uq_flow_question_batch_no"),
    )


class FlowItem(Base):
    __tablename__ = "flow_items"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    batch_id = Column(String(36), ForeignKey("flow_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(String(36), ForeignKey("flow_questions.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(String(36), nullable=True)
    student_name = Column(String(128), nullable=True, comment="无学号时的回退名")
    student_number = Column(String(64), nullable=True, comment="命名用（L4 敏感，访问受文件端点鉴权限制）")
    paper_name = Column(String(255), nullable=False, comment="源文件名")
    source_page_no = Column(Integer, nullable=True, comment="页码")
    crop_path = Column(String(512), nullable=True, comment="crops/q{no}/{学号--题号}.jpg")
    full_paper_path = Column(String(512), nullable=True, comment="papers/{学号}[_p{page}].jpg")
    bbox_json = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True, comment="裁切 bbox")
    max_score = Column(Float, nullable=False, default=0)
    status = Column(String(24), nullable=False, default="pending", index=True,
                    comment="pending/claimed/graded/arbitration_pending/arbitrated")
    claimed_by_user_id = Column(String(36), nullable=True)
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    claim_expires_at = Column(DateTime(timezone=True), nullable=True, comment="过期可回收")
    final_score = Column(Float, nullable=True)
    final_status = Column(String(16), nullable=True, comment="correct/wrong/partial/unanswered")
    final_review_id = Column(String(36), nullable=True, comment="生效 review")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("question_id", "paper_name", name="uq_flow_item_question_paper"),
        Index("idx_flow_item_question_status", "question_id", "status"),
        Index("idx_flow_item_claimer_status", "claimed_by_user_id", "status"),
    )


class FlowAssignment(Base):
    __tablename__ = "flow_assignments"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    batch_id = Column(String(36), ForeignKey("flow_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(String(36), ForeignKey("flow_questions.id", ondelete="CASCADE"), nullable=False, index=True)
    assignee_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(16), nullable=False, default="single", comment="single|first|second|arbiter")
    assigned_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="分配人")
    status = Column(String(16), nullable=False, default="active", comment="active/revoked")
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("question_id", "assignee_user_id", "role", name="uq_flow_assignment_question_user_role"),
    )


class FlowReview(Base):
    __tablename__ = "flow_reviews"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    batch_id = Column(String(36), ForeignKey("flow_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(String(36), ForeignKey("flow_questions.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(String(36), ForeignKey("flow_items.id", ondelete="CASCADE"), nullable=False, index=True)
    assignment_id = Column(String(36), ForeignKey("flow_assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    reviewer_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    round = Column(Integer, nullable=False, default=1, comment="1=首评/单评，2=二评")
    score = Column(Float, nullable=False, default=0)
    status = Column(String(16), nullable=False, comment="correct|wrong|partial|unanswered")
    marks_json = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True, comment="自由布点 [{x,y,type}]（归一化 0~1）")
    comment = Column(Text, nullable=True, comment="批注输入框")
    is_current = Column(Boolean, nullable=False, default=True, comment="是否当前生效（改分时旧记录翻 False）")
    revised_from = Column(String(36), nullable=True, comment="改分指向旧 review")
    submitted_at = Column(DateTime(timezone=True), nullable=True, comment="用于速度统计")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_flow_review_reviewer_submitted", "reviewer_user_id", "submitted_at"),
        Index("idx_flow_review_assignment_current", "assignment_id", "is_current"),
    )


class FlowArbitration(Base):
    __tablename__ = "flow_arbitrations"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    batch_id = Column(String(36), ForeignKey("flow_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(String(36), ForeignKey("flow_questions.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(String(36), ForeignKey("flow_items.id", ondelete="CASCADE"), nullable=False, index=True)
    arbiter_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    first_review_id = Column(String(36), nullable=True)
    second_review_id = Column(String(36), nullable=True)
    first_score = Column(Float, nullable=True)
    second_score = Column(Float, nullable=True)
    final_score = Column(Float, nullable=False)
    final_status = Column(String(16), nullable=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
