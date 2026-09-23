from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, field_validator


class LessonPlanRecord(BaseModel):
    id: str
    user_id: str
    class_id: str
    school_year: str = ""
    term: str = ""
    grade: Optional[str] = None
    subject: str
    title: str = ""
    teaching_content: str = ""
    teaching_objectives: str = ""
    key_points: str = ""
    difficult_points: str = ""
    teaching_preparation: str = ""
    teaching_process: str = ""
    collective_preparation_advice: str = ""
    blackboard_design: str = ""
    teaching_reflection: str = ""
    main_author: str = ""
    deputy_author: str = ""
    lesson_sequence: str = ""
    # R4 备课 MVP：教材级联字段（均可空，旧数据兼容）
    textbook_id: Optional[str] = None
    unit_id: Optional[str] = None
    catalog_id: Optional[str] = None
    edition: Optional[str] = None
    chapter: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    class Config:
        from_attributes = True


class CreateLessonPlanRequest(BaseModel):
    class_id: str
    school_year: Optional[str] = None
    term: Optional[str] = None
    grade: Optional[str] = None
    subject: str
    title: Optional[str] = None
    teaching_content: Optional[str] = None
    teaching_objectives: Optional[str] = None
    key_points: Optional[str] = None
    difficult_points: Optional[str] = None
    teaching_preparation: Optional[str] = None
    teaching_process: Optional[str] = None
    collective_preparation_advice: Optional[str] = None
    blackboard_design: Optional[str] = None
    teaching_reflection: Optional[str] = None
    main_author: Optional[str] = None
    deputy_author: Optional[str] = None
    lesson_sequence: Optional[str] = None
    # R4 备课 MVP：教材级联字段（均可空）
    textbook_id: Optional[str] = None
    unit_id: Optional[str] = None
    catalog_id: Optional[str] = None
    edition: Optional[str] = None
    chapter: Optional[str] = None
    completed_at: Optional[datetime] = None

    @field_validator("completed_at", mode="before")
    @classmethod
    def _empty_completed_at_to_none(cls, value):
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value


class UpdateLessonPlanRequest(BaseModel):
    school_year: Optional[str] = None
    term: Optional[str] = None
    grade: Optional[str] = None
    subject: Optional[str] = None
    title: Optional[str] = None
    teaching_content: Optional[str] = None
    teaching_objectives: Optional[str] = None
    key_points: Optional[str] = None
    difficult_points: Optional[str] = None
    teaching_preparation: Optional[str] = None
    teaching_process: Optional[str] = None
    collective_preparation_advice: Optional[str] = None
    blackboard_design: Optional[str] = None
    teaching_reflection: Optional[str] = None
    main_author: Optional[str] = None
    deputy_author: Optional[str] = None
    lesson_sequence: Optional[str] = None
    # R4 备课 MVP：教材级联字段（均可空）
    textbook_id: Optional[str] = None
    unit_id: Optional[str] = None
    catalog_id: Optional[str] = None
    edition: Optional[str] = None
    chapter: Optional[str] = None
    completed_at: Optional[datetime] = None

    @field_validator("completed_at", mode="before")
    @classmethod
    def _empty_completed_at_to_none(cls, value):
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value


class SendLessonPlanEmailRequest(BaseModel):
    pdf_base64: str
    filename: Optional[str] = None
    to_email: Optional[str] = None


# ── AI 备课（分步确认式生成，见 LessonPlanPage.tsx）────────

class AiGenerateOutlineRequest(BaseModel):
    subject: str
    grade: Optional[str] = None
    edition: Optional[str] = None
    unit_name: Optional[str] = None
    lesson_title: str
    lesson_sequence: Optional[str] = None


class AiGenerateOutlineStep(BaseModel):
    step: Optional[str] = None
    point: Optional[str] = None


class AiGenerateOutlineResult(BaseModel):
    title: Optional[str] = None
    objectives: Optional[str] = None
    key_points: Optional[str] = None
    difficult_points: Optional[str] = None
    process_summary: Optional[List[AiGenerateOutlineStep]] = None


class AiGenerateFullRequest(BaseModel):
    class_id: str
    outline: str
    subject: str
    grade: Optional[str] = None
    edition: Optional[str] = None
    unit_name: Optional[str] = None
    lesson_title: str
    lesson_sequence: Optional[str] = None
