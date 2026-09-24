# -*- coding: utf-8 -*-
"""口径 B · 请求/响应模型（§7.3）。

⚠️ 响应一律包 `ApiResponse{code,message,data}`（`app/schemas/common.py:8-11`），
错误走 FastAPI 的 `HTTPException(detail=...)` → `{"detail": "..."}`，⛔ 不引入 `{error,message}` 风格。
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


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


class OrderCreateIn(BaseModel):
    """`POST /payment/orders` 请求体（P2-1）。

    ⛔ **没有 `user_id` 字段** —— 收款对象只来自 JWT（§7.3 越权纪律，照 `routers/payment.py` 顶部）。
    """

    amount_fen: int = Field(..., ge=1, description="订单金额（**分**，正整数）")
    channel: str = Field(..., min_length=1, max_length=32, description="支付通道：wechat_pay / alipay")


class OrderCreateOut(BaseModel):
    """下单响应：我方订单号 ＋ **交给客户端的通道支付参数**（§7.3）。"""

    order_id: str
    channel: str
    amount_fen: int
    status: str
    payee_entity_id: Optional[str] = None
    pay_params: dict[str, Any] = Field(default_factory=dict)
