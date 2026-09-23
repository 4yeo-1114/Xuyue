"""兑换商品表（兑换管理）"""
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class RewardProduct(Base):
    __tablename__ = "reward_products"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    description = Column(String(1024), nullable=True)
    image_url = Column(String(512), nullable=True)
    product_type = Column(String(16), nullable=False, default="physical", index=True)
    points_required = Column(Integer, nullable=False)
    stock = Column(Integer, nullable=False, default=0)
    stock_warning = Column(Integer, nullable=False, default=5)
    is_active = Column(Integer, nullable=False, default=1, index=True)
    exchange_limit_per_student = Column(Integer, nullable=False, default=0)
    sort_order = Column(Integer, nullable=False, default=0)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
