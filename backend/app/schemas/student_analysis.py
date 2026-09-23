from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class StudentAnalysisUpsert(BaseModel):
    class_id: str
    student_name: str
    subject: str
    target_score: Optional[int] = None
    current_score: Optional[int] = None

class StudentAnalysisResponse(BaseModel):
    id: str
    class_id: str
    student_name: str
    subject: str
    target_score: Optional[int]
    current_score: Optional[int]

    class Config:
        from_attributes = True

class StudentScoreItem(BaseModel):
    student_name: str
    score: int

class ImportScoresRequest(BaseModel):
    class_id: str
    subject: str
    exam_name: str
    record_id: Optional[str] = None
    class_avg: Optional[int] = None
    scores: List[StudentScoreItem]

class ScoreHistoryResponse(BaseModel):
    id: str
    exam_name: str
    score: int
    class_avg: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True

class AIDiagnosisRequest(BaseModel):
    class_id: str
    student_name: str
    subject: str

class WrongQuestionItem(BaseModel):
    title: str
    image_url: Optional[str] = None
    answer_url: Optional[str] = None
    # P3-B3 错题实体统一：student_wrong_questions 已加 knowledge_point_id 列，序列化透出（回填前多为 NULL）
    knowledge_point_id: Optional[str] = None
    # R6a 知识点锚点：wrong_question_kp_bridge.kp_name 文本锚点（name 锚点，未收录时 NULL）
    knowledge_point_name: Optional[str] = None

class WrongQuestionResponse(BaseModel):
    exam_name: str
    questions: List[WrongQuestionItem]
    created_at: Optional[datetime] = None


# ── E04 成绩等级制：exam_scores 读写契约（前后端锁定，勿改字段名）────────────────
# 契约:
#   读: GET  /student-analysis/exam-scores?exam_id=... → [{ student_id, score, grade }]
#   写: POST /student-analysis/exam-scores             → 请求 [{ exam_id, student_id, score }]
#       → 返回 [{ student_id, score, grade }]（grade 由后端 grade_for_score 计算落库）

class ExamScoreWriteItem(BaseModel):
    """写成绩请求项：{ exam_id, student_id, score }。score 为空表示该生该次考试无成绩。"""
    exam_id: str
    student_id: str
    score: Optional[float] = None


class ExamScoreItem(BaseModel):
    """成绩读写返回项：{ student_id, score, grade }。grade 为等级代码或 null。"""
    student_id: str
    score: Optional[float] = None
    grade: Optional[str] = None
