"""家长-学生绑定 API 请求/响应模型（B0 §7.6）"""
from typing import Optional, List
from pydantic import BaseModel, Field

ALLOWED_RELATIONS = {"guardian", "father", "mother", "other"}


class CreateParentStudentRequest(BaseModel):
    parent_id: str
    student_id: str
    relation: str = "guardian"


class ParentStudentRecord(BaseModel):
    id: str
    parent_id: str
    parent_name: Optional[str] = None
    student_id: str
    student_name: Optional[str] = None
    relation: str
    status: str
    created_by: Optional[str] = None
    created_at: str = ""


class ParentStudentListData(BaseModel):
    rows: List[ParentStudentRecord]
    total: int
