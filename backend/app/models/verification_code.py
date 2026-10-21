"""验证码表（登录/注册合规改造）。

- 邮箱注册验证码（channel=email）、手机号短信登录/绑定（channel=sms）。
- 只存 code_hash（sha256），不存明文验证码；一次性消费（consumed），过期失效（expires_at）。
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    # target：收件地址的规范化形态（邮箱 lowercase / 手机号规范化）
    target = Column(String(255), nullable=False, index=True)
    channel = Column(String(16), nullable=False)  # 'email' | 'sms'
    purpose = Column(String(32), nullable=False)  # 'register' | 'login' | 'bind'
    code_hash = Column(String(64), nullable=False)  # sha256(code) 十六进制
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 复合索引：按 (target, channel, purpose) 查最近一条用于限频/校验
    __table_args__ = None  # 幂等建表走 database._ensure_verification_codes_table，索引在 raw SQL 里建
