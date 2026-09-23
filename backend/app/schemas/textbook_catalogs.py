"""教材目录响应 schema（R4 备课 MVP，供前端教材级联选择器复用）"""
from typing import List, Optional

from pydantic import BaseModel


class TextbookCatalogNode(BaseModel):
    id: str
    name: str
    subject: str
    edition: Optional[str] = None
    grade: Optional[str] = None
    level: str  # edition / unit / chapter
    unit_index: Optional[int] = None
    parent_id: Optional[str] = None

    class Config:
        from_attributes = True


class TextbookCatalogPair(BaseModel):
    """一条「学科 × 年级 × 版本」的可用目录组合（含节点数），供四维定位矩阵同步数据。"""

    subject: str
    grade: Optional[str] = None
    edition: Optional[str] = None
    node_count: int = 0


class TextbookCatalogOptions(BaseModel):
    """教材目录可用维度汇总：版本/学科/年级去重列表 + 组合明细。"""

    editions: List[str] = []
    subjects: List[str] = []
    grades: List[str] = []
    pairs: List[TextbookCatalogPair] = []
