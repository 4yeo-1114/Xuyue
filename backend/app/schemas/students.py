"""学生相关请求/响应模型"""
from pydantic import BaseModel
from typing import Optional, Literal


class StudentRecord(BaseModel):
    id: str
    class_id: str
    user_id: str
    name: str
    student_number: str
    gender: Optional[str] = None
    tier: Optional[str] = None
    status: Optional[str] = None
    birthday: Optional[str] = None
    phone: Optional[str] = None
    parent_name: Optional[str] = None
    parent_phone: Optional[str] = None
    address: Optional[str] = None
    enroll_date: Optional[str] = None
    seat_row: Optional[int] = None
    seat_col: Optional[int] = None
    cadre_role: Optional[str] = None
    notes: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    class Config:
        from_attributes = True


class CreateStudentRequest(BaseModel):
    class_id: str
    name: str
    student_number: Optional[str] = None
    gender: Optional[str] = None


class UpdateStudentRequest(BaseModel):
    name: Optional[str] = None
    student_number: Optional[str] = None
    gender: Optional[str] = None
    tier: Optional[str] = None
    status: Optional[str] = None
    birthday: Optional[str] = None
    phone: Optional[str] = None
    parent_name: Optional[str] = None
    parent_phone: Optional[str] = None
    address: Optional[str] = None
    enroll_date: Optional[str] = None
    seat_row: Optional[int] = None
    seat_col: Optional[int] = None
    cadre_role: Optional[str] = None
    notes: Optional[str] = None
