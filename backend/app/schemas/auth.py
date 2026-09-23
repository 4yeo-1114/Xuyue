from typing import Literal, Optional
from pydantic import BaseModel


class LoginRequest(BaseModel):
    # 宽松校验：演示环境邮箱可能落在保留域（如 @grade.local），不做严格 EmailStr 校验；
    # 具体格式在路由层做"非空且含 @" 检查。
    email: str
    password: str


# 前端注册选项 → 落库 roles 的映射（"校长"前端选项落库为"校级管理者"）
RegisterRole = Literal["任课教师", "班主任", "年级组长", "校级管理者", "系统管理员"]


class RegisterRequest(BaseModel):
    # 宽松校验：同 LoginRequest，路由层做"非空且含 @" 检查
    email: str
    password: str
    display_name: Optional[str] = None
    role: RegisterRole
    teaching_subject: Optional[str] = None  # 仅 role=="任课教师" 时必填


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    phone: Optional[str] = None
    teaching_subject: Optional[str] = None
    roles: Optional[list[str]] = []
    job_title: Optional[str] = None
    personal_email: Optional[str] = None
    multi_project_admin: bool = False
    ui_locale: str = "zh"

    class Config:
        from_attributes = True

class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = None
    phone: Optional[str] = None
    teaching_subject: Optional[str] = None
    job_title: Optional[str] = None
    personal_email: Optional[str] = None


class LocaleUpdateRequest(BaseModel):
    locale: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
