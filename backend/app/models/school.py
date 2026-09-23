"""学校/区域锚表（Region + School）。

DL1（D1/F1 区域多校视图数据层前置）：
- 只建锚表结构，不碰业务；跨库聚合 / 回填由后续 DL 处理。
- 多租户现状 = 每客户一库（multi_project_settings.json 的 db_profiles），本模块不改变该架构。
- 各业务表的 school_id 为可空 VARCHAR(36)，锚点 schools.id；本 DL 只补 classes.school_id 列，
  其余孤儿列（exam_scores/wrong_questions/students 等）维持现状，由后续 DL 统一收敛。
"""
from sqlalchemy import SmallInteger, Column, String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class Region(Base):
    """区域层级锚表（省/市/区县），parent_id 自引用，NULL=顶层。"""
    __tablename__ = "regions"
    __table_args__ = (
        Index("idx_regions_parent_id", "parent_id"),
        Index("idx_regions_code", "code"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(128), nullable=False)
    level = Column(SmallInteger().with_variant(TINYINT(), "mysql"), nullable=False, default=1, comment="区域层级:1=省 2=市 3=区县")
    parent_id = Column(String(36), ForeignKey("regions.id", ondelete="SET NULL"), nullable=True)  # 自引用父节点
    code = Column(String(32), nullable=True)  # 区域编码（如行政区划码）
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class School(Base):
    """学校锚表。region_id 指向 regions.id；db_profile_id 为跨库注册锚点。"""
    __tablename__ = "schools"
    __table_args__ = (
        Index("idx_schools_name", "name"),
        Index("idx_schools_db_profile_id", "db_profile_id"),
        Index("idx_schools_region_id", "region_id"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(128), nullable=False)
    region_id = Column(String(36), ForeignKey("regions.id", ondelete="SET NULL"), nullable=True)  # 所属区域
    db_profile_id = Column(String(36), nullable=True, comment="跨库注册锚点，对应 multi_project_settings 的 profile")
    db_name = Column(String(128), nullable=True)  # 对应库名（多租户每客户一库）
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
