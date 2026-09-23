"""学校二级评价指标字典（indicator_definitions）。

E01（对齐教基〔2021〕3号五方面）扩展为三层级：维度(level=1) → 方面(level=2) → 观测点(level=3)。
  - dimension 列存五育维度标签（moral/intellectual/physical/aesthetic/labor/ai_literacy），各层级继承父维度；
  - level=2 即原「二级评价指标」：手动成长记录按指标归类、C 域自动加分映射到对应指标，
    indicator_id 纯归类标签，画像评分口径零改动；
  - parent_id 自引用：方面挂到维度、观测点挂到方面，NULL=顶层；
  - 老 19 条系统默认指标（school_id=NULL）ALTER 补列后 level 默认 2、parent_id 默认 NULL，老数据可读。
school_id 可空：NULL = 系统默认指标（全校通用）；学校可下挂自己的指标。
"""
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid

# 指标层级：1=维度 / 2=方面 / 3=观测点
INDICATOR_LEVEL_DIMENSION = 1
INDICATOR_LEVEL_ASPECT = 2
INDICATOR_LEVEL_POINT = 3


class IndicatorDefinition(Base):
    __tablename__ = "indicator_definitions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    dimension = Column(String(32), nullable=False, index=True)  # moral|intellectual|physical|aesthetic|labor|ai_literacy
    code = Column(String(64), nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(String(512), nullable=True)
    level = Column(Integer, nullable=False, default=2)  # 1=维度 / 2=方面 / 3=观测点（E01）
    parent_id = Column(String(36), ForeignKey("indicator_definitions.id", ondelete="SET NULL",
                                              name="fk_id_parent"), nullable=True, index=True)  # 自引用父节点
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Integer, nullable=False, default=1, index=True)
    school_id = Column(String(36), nullable=True)  # NULL = 系统默认
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("code", "school_id", name="uq_id_code_school"),
        Index("idx_id_dim_active", "dimension", "is_active"),
        Index("idx_id_parent", "parent_id"),
    )
