"""题组定义 API 请求/响应模型（B0 §7.1）"""
from typing import Optional, List, Any
from pydantic import BaseModel, Field

ALLOWED_DOMAINS = {"personality", "interest", "learning_style", "self_built_survey"}
ALLOWED_GRADE_RANGES = {"primary", "junior", "senior", "all"}
ALLOWED_STATUSES = {"draft", "active", "retired"}


class OptionItem(BaseModel):
    key: str
    text: str
    dim: str
    score: Optional[int] = 1


class QuestionItem(BaseModel):
    id: str
    dim: str
    text: str
    reverse_scored: Optional[bool] = False
    options: List[OptionItem] = Field(..., min_length=2, max_length=4)


class CreateDefinitionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    domain: str
    grade_range: str = "all"
    version: int = 1
    status: str = "draft"
    consent_required: bool = True
    description: Optional[str] = None
    questions: List[QuestionItem]


class UpdateDefinitionRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    domain: Optional[str] = None
    grade_range: Optional[str] = None
    version: Optional[int] = None
    status: Optional[str] = None
    consent_required: Optional[bool] = None
    description: Optional[str] = None
    questions: Optional[List[QuestionItem]] = None


class DefinitionRecord(BaseModel):
    id: str
    name: str
    domain: str
    grade_range: str
    version: int
    status: str
    consent_required: bool
    description: Optional[str] = None
    question_count: int = 0
    questions: Optional[List[Any]] = None
    created_at: str = ""


class DefinitionListData(BaseModel):
    rows: List[DefinitionRecord]
    total: int
