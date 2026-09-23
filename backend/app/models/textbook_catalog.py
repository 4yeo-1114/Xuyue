"""教材目录表：学科 → 版本 → 单元/章节，供教案备课教材级联选择（R4 备课 MVP）。

简单两级即可：edition（教材/版本）→ unit（单元/章节）。
parent_id 自关联，NULL=顶层（edition 级节点）；不建 FK，保持插入顺序与 seed 幂等自由。
"""
from sqlalchemy import Column, Index, Integer, String, DateTime
from sqlalchemy.sql import func

from app.database import Base
from app.models.user import gen_uuid


class TextbookCatalog(Base):
    __tablename__ = "textbook_catalogs"
    __table_args__ = (
        Index("idx_tc_subject_edition", "subject", "edition"),
        Index("idx_tc_parent", "parent_id"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(128), nullable=False)  # 节点名，如「第一章 有理数」
    subject = Column(String(64), nullable=False)  # 学科：语文/数学/英语…
    edition = Column(String(64), nullable=True)  # 版本，如「人教版」
    grade = Column(String(64), nullable=True)  # 年级，如「七年级」
    level = Column(String(16), nullable=False, default="unit", server_default="unit")  # 层级：edition/unit/chapter
    unit_index = Column(Integer, nullable=True)  # 序号
    parent_id = Column(String(36), nullable=True)  # 自关联父节点，NULL=顶层（edition）
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
