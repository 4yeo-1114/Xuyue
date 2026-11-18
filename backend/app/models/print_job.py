# -*- coding: utf-8 -*-
"""打印任务（布置作业）持久化表：小程序/网页共享的作业记录。

原 print_jobs 是纯内存队列（重启即清空、不留痕），网页端无法留痕/修改。
2026-10-23 起落库：print_jobs 存作业记录（含出卷参数与 PDF 字节），print_uploads
存老师上传的题目材料（一小时内没被作业引用才清，被引用的随作业走）。
"""
from sqlalchemy import Column, String, Integer, Float, Text, LargeBinary
from sqlalchemy.dialects.mysql import MEDIUMBLOB, MEDIUMTEXT

from app.database import Base


class PrintJobRow(Base):
    __tablename__ = "print_jobs"
    __table_args__ = {"mysql_collate": "utf8mb4_0900_ai_ci"}

    id = Column(String(24), primary_key=True)
    created_by = Column(String(36), nullable=False, index=True)
    # draft=已生成待预览 / pending=排队等打印 / printing=代理取走打印中 / done / failed
    status = Column(String(16), nullable=False, default="draft")
    title = Column(String(256), nullable=False, default="")
    subject = Column(String(32), nullable=False, default="")
    grade = Column(String(32), nullable=False, default="")
    class_name = Column(String(64), nullable=False, default="")
    teacher = Column(String(64), nullable=False, default="")
    question_count = Column(Integer, nullable=False, default=0)
    copies = Column(Integer, nullable=False, default=1)
    # text = 老师手写题目；upload = 上传图片/文档；ai = AI 生成
    source = Column(String(16), nullable=False, default="text")
    page_size = Column(String(8), nullable=False, default="a4")
    layout = Column(String(8), nullable=False, default="auto")
    # 出卷全量参数 JSON（questions / question_items / note / answer_lines / upload_ids …），
    # 网页端据此展示与修改，改完按它重建 PDF。
    payload = Column(Text().with_variant(MEDIUMTEXT, "mysql"), nullable=False, default="{}")
    # 作业纸 PDF 字节；PATCH 改内容时重建
    pdf = Column(LargeBinary().with_variant(MEDIUMBLOB, "mysql"), nullable=True)
    created_at = Column(Float, nullable=False, default=0)
    updated_at = Column(Float, nullable=False, default=0)
    attempts = Column(Integer, nullable=False, default=0)
    claimed_at = Column(Float, nullable=True)
    claimed_by = Column(String(64), nullable=True)
    printed_at = Column(Float, nullable=True)
    printer = Column(String(128), nullable=True)
    error = Column(String(256), nullable=True)


class PrintUploadRow(Base):
    __tablename__ = "print_uploads"
    __table_args__ = {"mysql_collate": "utf8mb4_0900_ai_ci"}

    id = Column(String(24), primary_key=True)
    created_by = Column(String(36), nullable=False, index=True)
    kind = Column(String(16), nullable=False, default="image")
    name = Column(String(255), nullable=False, default="")
    size = Column(Integer, nullable=False, default=0)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    pages = Column(Integer, nullable=True)
    data = Column(LargeBinary().with_variant(MEDIUMBLOB, "mysql"), nullable=False)
    # 被哪个作业引用；NULL=还没被引用（超过 1 小时清掉）
    job_id = Column(String(24), nullable=True, index=True)
    created_at = Column(Float, nullable=False, default=0)
