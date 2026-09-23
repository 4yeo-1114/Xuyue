"""错题遗忘曲线复习表（简易 SM-2 调度）

每行代表「某个学生的一道错题」的复习状态：复习次数、上次/下次复习时间、
当前间隔天数。复习打卡时按 again/good/easy 推进间隔（1/2/4/7/15/30... 天）。
独立建表，不改动既有表，避免 migration。

@deprecated：死模型（库无表），P3 迁移不参与，勿注册 create_all
"""
from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class WrongQuestionReview(Base):
    __tablename__ = "wrong_question_review"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    class_id = Column(String(36), nullable=False, index=True)
    # 优先存 students.id；学生档案里查不到时可为空（错题来源是 student_name 反查）
    student_id = Column(String(36), nullable=True, index=True)
    # 冗余学生姓名，展示用（StudentWrongQuestion 里只有姓名没有 id）
    student_name = Column(String(64), nullable=False, index=True)
    subject = Column(String(64), nullable=False, index=True)
    # 源错题引用：StudentWrongQuestion.id（方便溯源）
    question_ref = Column(String(255), nullable=False)
    # 展示用题号/题目
    question_title = Column(String(255), nullable=True)
    image_url = Column(String(512), nullable=True)
    # 错因分类（default=other；变式题推荐按 subject + error_type 匹配）
    error_type = Column(String(64), nullable=False, default="other")
    # 当前处于间隔序列中的位置（成功复习次数）
    review_count = Column(Integer, nullable=False, default=0)
    last_reviewed_at = Column(DateTime(timezone=True), nullable=True)
    next_review_at = Column(DateTime(timezone=True), nullable=False, index=True)
    interval_days = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
