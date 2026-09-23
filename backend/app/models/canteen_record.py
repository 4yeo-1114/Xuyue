"""食堂电子台账表（canteen_records）：P0-4 纯软件 MVP，防篡改设计 = 只增不改。

按 type 分类：health_check（晨检）/ sample（留样）/ accompany（陪餐）/
disinfection（消毒）/ menu（菜单）。宽松 schema：公共字段 type + date 必填，
各类型专属字段统一放一张宽表（可空），按 type 白名单写入。
"""
from sqlalchemy import Column, Index, Integer, String, Boolean, Float, DateTime
from sqlalchemy.sql import func

from app.database import Base
from app.models.user import gen_uuid


class CanteenRecord(Base):
    __tablename__ = "canteen_records"
    __table_args__ = (
        Index("idx_canteen_type_created", "type", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    type = Column(String(32), nullable=False)  # health_check/sample/accompany/disinfection/menu
    date = Column(String(16), nullable=False)  # 台账日期 YYYY-MM-DD
    occurred_at = Column(DateTime(timezone=True), server_default=func.now())  # 记录时间
    created_by = Column(String(36), nullable=True)  # 记录人 user_id

    # 晨检 health_check
    staff_name = Column(String(128), nullable=True)
    temperature = Column(Float, nullable=True)
    health_status = Column(String(64), nullable=True)
    pass_ = Column("pass", Boolean, nullable=True)

    # 留样 sample
    meal_type = Column(String(64), nullable=True)
    dish_name = Column(String(128), nullable=True)
    sample_qty = Column(Integer, nullable=True)
    sampler_name = Column(String(128), nullable=True)
    storage_temp = Column(Float, nullable=True)
    review_result = Column(String(64), nullable=True)

    # 陪餐 accompany
    person_name = Column(String(128), nullable=True)
    person_role = Column(String(64), nullable=True)
    comments = Column(String(1024), nullable=True)

    # 消毒 disinfection
    area = Column(String(128), nullable=True)
    method = Column(String(128), nullable=True)
    operator_name = Column(String(128), nullable=True)
    result = Column(String(64), nullable=True)

    # 菜谱 menu
    dishes = Column(String(2048), nullable=True)
    nutrition_note = Column(String(2048), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
