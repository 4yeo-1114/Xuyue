from typing import Literal, Optional
from pydantic import BaseModel


class LoginRequest(BaseModel):
    # 宽松校验：演示环境邮箱可能落在保留域（如 @grade.local），不做严格 EmailStr 校验；
    # 具体格式在路由层做"非空且含 @" 检查。
    email: str
    password: str


# 免审核自助注册只允许「任课教师」——这是唯一的注册闸门（Pydantic 校验阶段即拦非法值）。
# 收窄理由：系统管理员/子系统管理员/校级管理者/年级组长都能经 is_school_admin() 拿到后台权限，
# 自助注册若可选即等于公网自封管理员（提权）。
RegisterRole = Literal["任课教师"]


class RegisterRequest(BaseModel):
    # 宽松校验：同 LoginRequest，路由层做"非空且含 @" 检查
    email: str
    password: str
    display_name: Optional[str] = None
    role: RegisterRole
    teaching_subject: Optional[str] = None  # 可选、自由填写；长度上限见 routers/auth.py
    teaching_grade: Optional[str] = None  # 可选、自由填写；长度上限见 routers/auth.py


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    phone: Optional[str] = None
    teaching_subject: Optional[str] = None
    teaching_grade: Optional[str] = None
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
    teaching_grade: Optional[str] = None
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
