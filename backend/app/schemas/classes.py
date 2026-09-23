"""班级相关请求/响应模型，与前端 ClassRecord 一致"""
from typing import Optional
from pydantic import BaseModel, EmailStr


class ClassRecord(BaseModel):
    id: str
    user_id: str
    school_level: str
    grade: str
    name: str
    student_count: int
    created_at: str
    updated_at: str
    my_role: Optional[str] = None  # head | deputy | teacher，列表接口填充
    is_owner: bool = False

    class Config:
        from_attributes = True


class ClassTeacherRecord(BaseModel):
    id: str
    user_id: str
    email: str
    display_name: Optional[str] = None
    role: str
    subject: Optional[str] = None


class AddClassTeacherRequest(BaseModel):
    email: EmailStr
    role: str  # deputy | teacher


class PatchClassTeacherRequest(BaseModel):
    role: str


class CreateClassRequest(BaseModel):
    school_level: str
    grade: str
    name: str


class UpdateClassRequest(BaseModel):
    name: str
