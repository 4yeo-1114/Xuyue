"""C 域请求模型。

字段命名：C0 契约 API 使用 camelCase；同时兼容 snake_case（codebase 惯例）。
通过 pydantic alias + populate_by_name 实现双写兼容。
"""
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


def _conf():
    return ConfigDict(populate_by_name=True)


# ---------- 争章 ----------
class BadgeDefinitionCreate(BaseModel):
    model_config = _conf()
    name: str
    description: Optional[str] = None
    badge_type: str = Field("school_based", alias="badgeType")
    category: str = "moral"
    icon_url: Optional[str] = Field(None, alias="iconUrl")
    points_awarded: int = Field(10, alias="pointsAwarded")
    min_grade: Optional[str] = Field(None, alias="minGrade")
    max_grade: Optional[str] = Field(None, alias="maxGrade")
    is_active: bool = Field(True, alias="isActive")
    sort_order: int = Field(0, alias="sortOrder")


class BadgeDefinitionUpdate(BaseModel):
    model_config = _conf()
    name: Optional[str] = None
    description: Optional[str] = None
    badge_type: Optional[str] = Field(None, alias="badgeType")
    category: Optional[str] = None
    icon_url: Optional[str] = Field(None, alias="iconUrl")
    points_awarded: Optional[int] = Field(None, alias="pointsAwarded")
    min_grade: Optional[str] = Field(None, alias="minGrade")
    max_grade: Optional[str] = Field(None, alias="maxGrade")
    is_active: Optional[bool] = Field(None, alias="isActive")
    sort_order: Optional[int] = Field(None, alias="sortOrder")


class BadgeAwardRequest(BaseModel):
    model_config = _conf()
    student_ids: List[str] = Field(..., alias="studentIds")
    badge_definition_id: str = Field(..., alias="badgeDefinitionId")
    award_date: str = Field(..., alias="awardDate")
    reason: Optional[str] = None


# ---------- 学分银行 ----------
class ManualCreditRequest(BaseModel):
    model_config = _conf()
    student_id: str = Field(..., alias="studentId")
    amount: int
    description: str


# ---------- 兑换 ----------
class RewardProductCreate(BaseModel):
    model_config = _conf()
    name: str
    description: Optional[str] = None
    image_url: Optional[str] = Field(None, alias="imageUrl")
    product_type: str = Field("physical", alias="productType")
    points_required: int = Field(..., alias="pointsRequired")
    stock: int = 0
    stock_warning: int = Field(5, alias="stockWarning")
    is_active: bool = Field(True, alias="isActive")
    exchange_limit_per_student: int = Field(0, alias="exchangeLimitPerStudent")
    sort_order: int = Field(0, alias="sortOrder")


class RewardProductUpdate(BaseModel):
    model_config = _conf()
    name: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = Field(None, alias="imageUrl")
    product_type: Optional[str] = Field(None, alias="productType")
    points_required: Optional[int] = Field(None, alias="pointsRequired")
    stock: Optional[int] = None
    stock_warning: Optional[int] = Field(None, alias="stockWarning")
    is_active: Optional[bool] = Field(None, alias="isActive")
    exchange_limit_per_student: Optional[int] = Field(None, alias="exchangeLimitPerStudent")
    sort_order: Optional[int] = Field(None, alias="sortOrder")


class RedemptionCreate(BaseModel):
    model_config = _conf()
    student_id: str = Field(..., alias="studentId")
    product_id: str = Field(..., alias="productId")


class RedemptionStatusUpdate(BaseModel):
    model_config = _conf()
    status: str
    notes: Optional[str] = None


# ---------- 校外实践 ----------
class PracticeCreate(BaseModel):
    model_config = _conf()
    student_id: str = Field(..., alias="studentId")
    practice_type: str = Field(..., alias="practiceType")
    title: str
    description: Optional[str] = None
    practice_date: str = Field(..., alias="practiceDate")
    duration_hours: Optional[float] = Field(None, alias="durationHours")
    location: Optional[str] = None
    evidence_images: Optional[List[dict]] = Field(None, alias="evidenceImages")


class PracticeUpdate(BaseModel):
    model_config = _conf()
    student_id: Optional[str] = Field(None, alias="studentId")
    practice_type: Optional[str] = Field(None, alias="practiceType")
    title: Optional[str] = None
    description: Optional[str] = None
    practice_date: Optional[str] = Field(None, alias="practiceDate")
    duration_hours: Optional[float] = Field(None, alias="durationHours")
    location: Optional[str] = None
    evidence_images: Optional[List[dict]] = Field(None, alias="evidenceImages")


class PracticeReview(BaseModel):
    model_config = _conf()
    status: str
    review_comment: Optional[str] = Field(None, alias="reviewComment")


# ---------- 晨午检请假/出勤 ----------
class AttendanceRecordItem(BaseModel):
    model_config = _conf()
    student_id: str = Field(..., alias="studentId")
    status: str = Field("present")
    reason: Optional[str] = None


class AttendanceBatchCreate(BaseModel):
    model_config = _conf()
    class_id: str = Field(..., alias="classId")
    date: str
    check_type: str = Field("morning", alias="checkType")
    records: List[AttendanceRecordItem]
