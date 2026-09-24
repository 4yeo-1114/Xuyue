import uuid
from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from app.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    phone = Column(String(32), nullable=True)
    dingtalk_userid = Column(String(64), nullable=True, index=True)  # 钉钉免登 userid 绑定
    teaching_subject = Column(String(32), nullable=True)
    teaching_grade = Column(String(32), nullable=True)  # 任教年级（如 三年级/七年级/高一）
    roles = Column(String(255), nullable=True)  # 逗号分隔的多个角色，例如 "任课教师,班主任"
    job_title = Column(String(255), nullable=True)  # 岗位职责/岗位信息
    # C4：已删除 plain_password 明文密码列；历史库中存量明文密码需要人工迁移清理
    personal_email = Column(String(255), nullable=True)  # 预先设置好的个人邮箱，用于接收邮件
    ui_locale = Column(String(8), nullable=True, default="zh")  # 界面语言：zh | en
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
