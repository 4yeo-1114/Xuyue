# -*- coding: utf-8 -*-
"""口径 B · 请求/响应模型（§7.3）。

⚠️ 响应一律包 `ApiResponse{code,message,data}`（`app/schemas/common.py:8-11`），
错误走 FastAPI 的 `HTTPException(detail=...)` → `{"detail": "..."}`，⛔ 不引入 `{error,message}` 风格。
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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


# ────────────────────────── Phase 3：开票申请（P3-1）──────────────────────────

class InvoiceCreateIn(BaseModel):
    """`POST /payment/invoices` 请求体（P3-1 提开发票申请）。

    ⛔ **没有 `user_id`** —— 申请人只来自 JWT（§7.3 越权纪律）。
    ⛔ **没有 `amount_fen`** —— 开票金额（含税）**只从订单取**，否则老师能自己填票面金额
       （回归用例：请求体里塞 `amount_fen` ⇒ 落库值仍是订单金额）。
    ⛔ **没有**专票四字段（地址 / 电话 / 开户行 / 账号）—— 已拍票种 = **普票**。
    ⛔ **没有**收件地址 / 邮寄字段 —— 已拍载体 = **电子**，交付 = 邮箱。
    ⛔ **没有**任何税率/税额字段 —— 税率未拍，且本批走「老师申请 → 人工开票」，税额不由本系统算。

    ⚠️ `str_strip_whitespace`：`"   "` 必须先被 strip 再判 `min_length`，否则空白抬头能过闸。
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    order_id: str = Field(..., min_length=1, max_length=36, description="已支付订单号")
    title: str = Field(..., min_length=1, max_length=255, description="发票抬头（普票）")
    taxpayer_id: str = Field(..., min_length=1, max_length=64, description="纳税人识别号")
    # EmailStr 由 `email-validator` 提供（requirements.txt:15 已在依赖里）；⛔ 不禁用校验 ——
    # 交付渠道就是邮箱，写错一个字符 = 发票寄不到，属必须挡住的一类输入。
    email: EmailStr = Field(..., description="电子发票交付邮箱")


class InvoiceOut(BaseModel):
    """开票申请（⛔ 只回**已拍票种/载体**要用的字段，没有专票/邮寄/税额字段）。"""

    id: str
    order_id: str
    status: str
    amount_fen: int  # 含税（分）
    title: str
    taxpayer_id: str
    email: str
    invoice_no: Optional[str] = None
    issued_at: Optional[str] = None
    voided_at: Optional[str] = None
    created_at: Optional[str] = None


class InvoicePageOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[InvoiceOut]


# ────────────────────────── §6.2 对账巡检（只读，Phase 3 追加）──────────────────────────

class ReconcileE1Out(BaseModel):
    """E1（内部自洽，§6.2 L459）：逐账户 `SUM(ledger_entries.amount_fen) == balance_fen`。"""

    ok: bool
    accounts_checked: int
    unbalanced_count: int
    total_balance_fen: int
    total_sum_amount_fen: int
    discrepancies: list[dict[str, Any]] = Field(default_factory=list)


class ReconcileE2Out(BaseModel):
    """E2（收入一致，§6.2 L460）：`SUM(recharge 分录) == SUM(已支付订单)`。"""

    ok: bool
    recharge_fen: int
    paid_orders_fen: int
    diff_fen: int
    discrepancies: list[dict[str, Any]] = Field(default_factory=list)


class ReconciliationOut(BaseModel):
    """`GET /payment/admin/reconciliation` 响应体（**只读**）。

    ⚠️ 只出 E1/E2 两段 —— **E3（通道一致）本阶段不落地**，理由与将来落点的三个前提见
       `docs/payment/payment-design.md` §6.5（⛔ 本响应里**不出现** E3 字段：没落地的等式
       不许长成一个看着"已经在跑"的 JSON 字段）。
    """

    e1: ReconcileE1Out
    e2: ReconcileE2Out
    checked_at: str
