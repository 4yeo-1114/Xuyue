# -*- coding: utf-8 -*-
"""轻成绩表（对齐批改君 exam_scores）：批改文件夹的每生成绩汇总行。

一行 = 一个卷盒（学生）在一场批改文件夹里的成绩快照：
- 智能/参照/自主多页求和、作文多页取最大（与 extract_scores_from_completed / 前端 box_totals 同口径）；
- 批改历史 JSON 是唯一事实源，每次批改落盘后 delete-then-insert 重建本文件夹的行；
- 只收已统分条目（无 score_total 的不落行），重批/清空后重建即自愈。
"""
from sqlalchemy import Column, DateTime, Float, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base
from app.models.user import gen_uuid


class GradingScoreSummary(Base):
    __tablename__ = "grading_score_summaries"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), nullable=False, index=True)
    folder_safe = Column(String(255), nullable=False, index=True)
    # 班级文件夹（cls_{class_id}__{exam_name}）才有；普通文件夹留空
    class_id = Column(String(36), ForeignKey("classes.id", ondelete="SET NULL"), nullable=True, index=True)
    # 按姓名 best-effort 匹配 students 表；匹配不上/学生已删除 → 留空（成绩保留）
    student_id = Column(String(36), ForeignKey("students.id", ondelete="SET NULL"), nullable=True, index=True)
    student_name = Column(String(128), nullable=False)
    exam_name = Column(String(255), nullable=True)
    subject = Column(String(64), nullable=True)
    score_total = Column(Float, nullable=True, comment="整卷总分（多页求和/作文取最大后）")
    max_score = Column(Float, nullable=True, comment="整卷满分（无从取得则为空）")
    question_scores = Column(JSON, nullable=True, comment="逐题得分 {标题: 分}（跨页合并）")
    engine = Column(String(32), nullable=True, comment="default|baidu|smart_ref|aliyun|manual|essay")
    graded_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "folder_safe", "student_name", name="uq_gss_user_folder_student"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"},
    )
