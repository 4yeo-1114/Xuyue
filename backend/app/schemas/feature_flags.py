"""E08 · 学校级 AI 管控：feature_flags 接口契约 schema。"""
from typing import Optional

from pydantic import BaseModel


class FeatureFlagOut(BaseModel):
    key: str
    label: Optional[str] = None
    enabled: bool
    scope: str = "global"
    scope_id: Optional[str] = None


class UpdateFeatureFlagRequest(BaseModel):
    enabled: bool
