"""分层推送（nav/ai-layered）请求/响应模型"""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

TierName = Literal["A", "B", "C"]


class TierMove(BaseModel):
    student_id: str
    tier: TierName


class TiersBatchRequest(BaseModel):
    class_id: str
    moves: List[TierMove]


class TiersBatchResult(BaseModel):
    updated: int


class TiersAutoRequest(BaseModel):
    class_id: str
    subject: Optional[str] = None
    # 分层阈值：score >= a → A，>= b → B，其余 C
    thresholds: Optional[Dict[str, float]] = None


class TiersAutoResult(BaseModel):
    updated: int
    no_score: int
    tiers: Dict[str, List[str]]


class RosterStudent(BaseModel):
    id: str
    name: str
    student_number: Optional[str] = None
    tier: Optional[str] = None
    score: Optional[float] = None
    dingtalk_synced: bool = False
    # 家长联系方式：仅 can_view_student_pii 时回填，否则为 None（电话家长弹窗用）
    parent_name: Optional[str] = None
    parent_phone: Optional[str] = None


class TierAssignment(BaseModel):
    title: str
    desc: Optional[str] = None
    exam_id: Optional[str] = None


class TierMaterial(BaseModel):
    name: str
    url: str


class TierContent(BaseModel):
    assignments: List[TierAssignment] = Field(default_factory=list)
    materials: List[TierMaterial] = Field(default_factory=list)
    estimated_minutes: int = 40
    deadline_weekday: int = 5  # 1=周一 … 7=周日
    deadline_time: str = "22:00"
    require_parent_sign: bool = False
    require_photo: bool = False
    require_voice: bool = False


class PushTiming(BaseModel):
    mode: Literal["now", "scheduled"] = "now"
    scheduled_at: Optional[str] = None  # datetime-local 字符串，mode=scheduled 时用
    fired_at: Optional[str] = None


class NotifyStrategy(BaseModel):
    student: bool = True
    parent: bool = True
    reminder24h: bool = True
    late: bool = True


class SettingsSnapshot(BaseModel):
    name: str
    saved_at: Optional[str] = None
    snapshot: Dict[str, Any] = Field(default_factory=dict)


class LayeredPushSettings(BaseModel):
    thresholds: Dict[str, float] = Field(default_factory=lambda: {"a": 80, "b": 60})
    timing: PushTiming = Field(default_factory=PushTiming)
    notify: NotifyStrategy = Field(default_factory=NotifyStrategy)
    form_type: Literal["dingtalk", "h5"] = "h5"
    tiers: Dict[str, TierContent] = Field(default_factory=dict)
    templates: List[SettingsSnapshot] = Field(default_factory=list)


class SettingsPutRequest(BaseModel):
    class_id: str
    subject: Optional[str] = None
    settings: Dict[str, Any]


class PushRequest(BaseModel):
    class_id: str
    subject: str = ""
    notice_only: bool = False
    notice_text: Optional[str] = None


class PushStartResult(BaseModel):
    round_id: str
    total: int
    created_tasks: int
    notice_only: bool = False


class TestPushRequest(BaseModel):
    class_id: str
    subject: str = ""


class UrgeRequest(BaseModel):
    class_id: str
    subject: str = ""
    tier: Optional[TierName] = None


class ReportRequest(BaseModel):
    class_id: str
    subject: str = ""
    kind: Literal["weekly", "round"] = "weekly"
    recipient: Literal["self", "head"] = "self"


class TaskStatusPatch(BaseModel):
    status: Literal["pending", "completed"]


class SyncRosterRequest(BaseModel):
    class_id: str
