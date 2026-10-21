# -*- coding: utf-8 -*-
"""修正/复核记账台账（B 项：修正回流 + 复核记账）。

一行 = 一次判分被推翻 / 复核留痕（was→new 对照）：
- human_ai_correct：老师 ai-correct 手动修正（原判 vs 修正后）；
- form_guard / vl_ink：形态校验强降级、VL 笔迹复核拦截（flagged 为只标不改判）。

re-grade 全量重跑后按文件夹置 voided=1（历史事实保留，当前态统计可排除）。
与 response_logs 不同：本表可 UPDATE voided；response_logs 保持纯追加不动。
"""
from sqlalchemy import Boolean, Column, DateTime, Float, Index, Integer, String
from sqlalchemy.sql import func

from app.database import Base
from app.models.user import gen_uuid


class CorrectionLedger(Base):
    __tablename__ = "correction_ledger"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), nullable=False, index=True)
    folder_safe = Column(String(255), nullable=False, index=True)
    paper_name = Column(String(255), nullable=True)
    engine = Column(String(32), nullable=True)
    # 题号/小题号：历史块里可能是 int/str/列表，存归一化字符串（见 correction_ledger._scalar_str）
    index = Column(String(64), nullable=True, comment="题号")
    sub_index = Column(String(64), nullable=True, comment="小题 / 作答区序号")
    source = Column(String(32), nullable=False, index=True, comment="human_ai_correct|form_guard|vl_ink")
    was_result = Column(String(16), nullable=True, comment="原判（对|错|半对|未作答）")
    new_result = Column(String(16), nullable=True, comment="修正后判定")
    was_comment = Column(String(500), nullable=True)
    new_comment = Column(String(500), nullable=True)
    was_score = Column(Float, nullable=True)
    new_score = Column(Float, nullable=True)
    subject_family = Column(String(32), nullable=True)
    voided = Column(Boolean, nullable=False, default=False, comment="re-grade 重跑后作废")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_cl_user_created", "user_id", "created_at"),
        Index("idx_cl_folder_paper", "folder_safe", "paper_name"),
    )
