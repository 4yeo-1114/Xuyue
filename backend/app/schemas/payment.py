# -*- coding: utf-8 -*-
"""口径 B · 请求/响应模型（§7.3）。

⚠️ 响应一律包 `ApiResponse{code,message,data}`（`app/schemas/common.py:8-11`），
错误走 FastAPI 的 `HTTPException(detail=...)` → `{"detail": "..."}`，⛔ 不引入 `{error,message}` 风格。
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class PaymentAccountOut(BaseModel):
    user_id: str
    balance_fen: int
    total_recharged_fen: int
    total_consumed_fen: int
    status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class LedgerEntryOut(BaseModel):
    id: str
    entry_type: str
    amount_fen: int
    balance_after_fen: int
    description: Optional[str] = None
    created_at: Optional[str] = None


class LedgerPageOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[LedgerEntryOut]


class UsageItemOut(BaseModel):
    kind: str
    folder_safe: str
    subject_key: str
    net: int


class UsageOut(BaseModel):
    """口径 B 用量（⛔ **不是**口径 A 的成本核算 —— 数据源 = `usage_events`）。"""

    total_grade: int
    total_upload: int
    folders: list[dict[str, Any]]
    recent: list[UsageItemOut]
