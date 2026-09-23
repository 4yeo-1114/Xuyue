"""锚点结果 / 监护人同意 API 请求响应模型（B0 §7.4-7.5）"""
from typing import Optional, List, Any, Dict
from pydantic import BaseModel


class ResultRecord(BaseModel):
    id: str
    student_id: str
    definition_id: Optional[str] = None
    definition_name: Optional[str] = None
    domain: str
    purpose: str
    tag_schema: Dict[str, Any] = {}
    raw_score: Optional[Dict[str, Any]] = None
    guardian_consent: Dict[str, Any] = {}
    session_id: Optional[str] = None
    created_by: Optional[str] = None
    created_at: str = ""


class ResultListData(BaseModel):
    rows: List[ResultRecord]
    total: int


class SubmitAnswerResult(BaseModel):
    result_id: str
    session_id: str
    labels: List[str]
    dimension_percents: Dict[str, float]
    total_answered: int
    consent_status: str
