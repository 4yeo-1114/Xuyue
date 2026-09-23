"""施测会话 API 请求/响应模型（B0 §7.2）"""
from typing import Optional, List, Any
from pydantic import BaseModel, Field

ALLOWED_TEST_MODES = {"class_batch", "self"}


class CreateSessionRequest(BaseModel):
    definition_id: str
    test_mode: str = "class_batch"
    student_ids: Optional[List[str]] = None
    student_id: Optional[str] = None
    batch_id: Optional[str] = None


class AnswerSubmit(BaseModel):
    question_id: str
    option_key: str


class SubmitAnswersRequest(BaseModel):
    answers: List[AnswerSubmit] = Field(..., min_length=1)


class SessionRecord(BaseModel):
    id: str
    student_id: str
    student_name: Optional[str] = None
    definition_id: str
    definition_name: Optional[str] = None
    test_mode: str
    batch_id: Optional[str] = None
    status: str
    proctored_by: Optional[str] = None
    created_by: Optional[str] = None
    taken_at: Optional[str] = None
    submitted_at: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    questions: Optional[List[Any]] = None


class SessionListData(BaseModel):
    rows: List[SessionRecord]
    total: int
