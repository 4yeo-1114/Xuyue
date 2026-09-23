"""种春风·五育成长画像域 请求体 Schema（A0 §6.3 / §6.5 / §6.7 / §6.8）。"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# 画像维度枚举：五育 + AI 素养（E02，对齐教基〔2021〕3号五方面 + 2024 教基厅函 32 号）。
# 与 event_catalog.DIMENSIONS 保持一致；ai_literacy 为增量，旧请求不传仍兼容。
Dimension = Literal["moral", "intellectual", "physical", "aesthetic", "labor", "ai_literacy"]

# 成长记录来源类型：manual 手动；ai_course/ai_project 为 AI 课程成果（E02，复用幂等链路）
GrowthSourceType = Literal["manual", "ai_course", "ai_project"]

TERM_PATTERN = r"^\d{4}-\d{4}-[12]$"


class GrowthRecordCreate(BaseModel):
    """教师手动录入成长记录（A0 §6.3）。E02 扩展：可录入 AI 课程成果（source_type=ai_course/ai_project）。"""

    dimension: Dimension
    growth_point: int = Field(..., ge=-10, le=10, description="成长分值，可为负")
    source_id: Optional[str] = Field(None, max_length=36, description="关联源记录 ID")
    source_type: GrowthSourceType = Field("manual", description="来源类型：manual / ai_course / ai_project")
    indicator_id: Optional[str] = Field(None, max_length=36, description="二级指标字典ID，可空")
    evidence: Optional[dict] = Field(None, description="证据 JSON")
    note: Optional[str] = Field(None, max_length=500, description="备注")


class ReportFreezeRequest(BaseModel):
    """冻结学期报告（A0 §6.5）。"""

    term: str = Field(..., pattern=TERM_PATTERN, description="学年-学期，如 2025-2026-1")


class CommentGenerateRequest(BaseModel):
    """生成 AI 评语（A0 §6.7）。"""

    term: str = Field(..., pattern=TERM_PATTERN)


class CommentConfirmRequest(BaseModel):
    """确认评语（A0 §6.8），可修改文本后确认。"""

    term: str = Field(..., pattern=TERM_PATTERN)
    content: Optional[str] = Field(None, max_length=2000, description="确认后的评语文本")


class MemoryCreate(BaseModel):
    """学生成长印记上传（multipart/form-data：file + caption）。"""

    caption: Optional[str] = Field(None, max_length=200, description="照片说明（可选）")


class MemoryItem(BaseModel):
    """学生成长印记单条（GET /students/{id}/memories 列表项）。"""

    id: str
    student_id: str
    class_id: Optional[str] = None
    image_path: str
    download_url: Optional[str] = None
    thumb_url: Optional[str] = None
    caption: Optional[str] = None
    source_type: str
    created_by: Optional[str] = None
    created_at: Optional[str] = None
