# -*- coding: utf-8 -*-
"""口径 B · 支付路由（Phase 0 只读账单投影 = P0-6；Phase 2 下单/回调 = P2-1 / P2-3）。

设计依据：docs/payment/payment-design.md §7.3。

物理分离（§7.3 逐字）：⛔ `routers/scan_billing.py` 的 9 个只读端点一个都不改 ——
它们**不是**本模块的数据源；两套端点、两套数据源并存。
本模块的数据源：`payment_accounts` + `ledger_entries` + `usage_events` + `payment_orders`（口径 B 自己的表）。

端点清单：
  GET  /api/v1/payment/account            我的余额（分）+ 状态          （登录，P0-6）
  GET  /api/v1/payment/ledger             我的资金流水（分页）           （登录，P0-6）
  GET  /api/v1/payment/usage              我的用量（口径 B）             （登录，P0-6）
  POST /api/v1/payment/orders             下单（返回通道支付参数）       （登录，P2-1）
  POST /api/v1/payment/callback/{channel} 通道回调（**按通道验签识别身份**）（P2-3）
  POST /api/v1/payment/invoices           提交开票申请（一单一票）       （登录，P3-1）
  GET  /api/v1/payment/invoices           我的开票申请（分页）           （登录，P3-1）
  GET  /api/v1/payment/admin/reconciliation  E1/E2 只读对账巡检（**只读**）  （**管理员**，§6.2/§6.4）
⛔ `POST /payment/admin/grant`（后台人工开通，**写**）不在本批范围。

⚠️ **P3-1 的「标记已开票 / 作废」本批⛔ 不做后台入口**：状态机只在
   `services/payment/invoices.py`（`mark_issued` / `mark_void`）留了数据层，本模块不挂它
   —— 上文那条「admin 端点不在本批范围」对新加的**写**路径同样成立。
⚠️ 唯一的 admin 路由是 `GET /admin/reconciliation`，它**零写路径**（只读巡检）：
   上面那条逐字排除的是 `POST /payment/admin/grant` 这个**写**端点，⛔ 不是「admin 一律不许」。

⚠️ 越权（§12 第 6 条）：本模块**不接 `user_id` query 参数**，一律用 JWT 里的身份 ——
「余额/流水/账单天生强隐私」，必须自己收一道「只能查自己」，⛔ 不照抄 `scan_billing` 的
`user_id: Optional[str] = Query(None)` 范式。
⚠️ 回调路由**没有也不可能有 JWT**（通道不会带我们的令牌）⇒ 它的身份来自**验签**：
   验签不过 ⇒ 400 且**一行账都不记**；收款对象由订单号反查，
   ⛔ **绝不信任请求体里的 user_id / 金额**之外的任何身份字段。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.ledger_entry import LedgerEntry
from app.models.payment_order import PaymentOrder
from app.models.usage_event import UsageEvent
from app.schemas.common import ApiResponse
from app.schemas.payment import (
    InvoiceCreateIn,
    InvoiceOut,
    InvoicePageOut,
    LedgerEntryOut,
    LedgerPageOut,
    OrderCreateIn,
    OrderCreateOut,
    OrderStatusOut,
    PaymentAccountOut,
    ReconciliationOut,
    ReconcileE1Out,
    ReconcileE2Out,
    UsageOut,
)
from app.services.payment import channels
from app.services.payment import invoices as invoices_svc
from app.services.payment import ledger as ledger_svc
from app.services.payment import orders as orders_svc

# 管理员闸**复用**仓内既有的那一套（⛔ 不新造一套）
# —— 照 `routers/admin_academic.py:26` / `routers/admin_dashboard.py:37` 的既有复用方式。
from app.routers.admin import _check_admin_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payment", tags=["payment"])

_MAX_PAGE_SIZE = 200

# 通道层 / 账本层异常 → HTTP 状态码（§7.3：409 = 订单已处理，501 = 通道未配置）。
# ⚠️ 状态码**定义在异常类自己身上**（`ChannelError.http_status` 等），此处只取用 ——
#    ⛔ 不做宽泛的 `except Exception` 兜底（那会把 500 级真实缺陷伪装成 4xx 客户端错误）。
#    ⇒ 只有下面 `_PAYMENT_ERRORS` 这几种**业务性拒绝**才转成 4xx/5xx 并写日志，
#      其余异常照常抛出（500 + 堆栈），⛔ 不被吞成「静默拒绝」。
_PAYMENT_ERRORS: tuple[type, ...] = (
    channels.ChannelError,          # 404 未知通道 / 400 验签失败 / 501 未配置 / 503 缺密码学依赖
    ledger_svc.OrderNotFoundError,  # 404
    ledger_svc.OrderStateError,     # 409
    invoices_svc.InvoiceNotFoundError,  # 404（订单/发票不存在，或不属于当前用户 —— 同一个 404）
    invoices_svc.InvoiceStateError,     # 409（重复申请 / 订单未支付 / 非法状态跃迁）
)


def _http_status_for(exc: BaseException) -> Optional[int]:
    """异常 → HTTP 状态码；返回 None 表示「不是业务性拒绝，别接」。"""
    if not isinstance(exc, _PAYMENT_ERRORS):
        return None
    status = getattr(exc, "http_status", None)
    return status if isinstance(status, int) else None


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


@router.get("/account", response_model=ApiResponse[PaymentAccountOut])
def api_get_my_account(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """我的余额（分）+ 状态。账户惰性创建（§8.1）。"""
    acct = ledger_svc.get_or_create_account(db, user_id)
    return ApiResponse(
        data=PaymentAccountOut(
            user_id=acct.user_id,
            balance_fen=int(acct.balance_fen or 0),
            total_recharged_fen=int(acct.total_recharged_fen or 0),
            total_consumed_fen=int(acct.total_consumed_fen or 0),
            status=acct.status,
            created_at=_iso(acct.created_at),
            updated_at=_iso(acct.updated_at),
        )
    )


@router.get("/ledger", response_model=ApiResponse[LedgerPageOut])
def api_list_my_ledger(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=_MAX_PAGE_SIZE),
    entry_type: Optional[str] = Query(None),
):
    """我的资金流水（分页，倒序）。⛔ 只能查自己（无 user_id 入参）。"""
    acct = ledger_svc.get_or_create_account(db, user_id)
    q = db.query(LedgerEntry).filter(LedgerEntry.account_id == acct.id)
    if entry_type:
        q = q.filter(LedgerEntry.entry_type == str(entry_type).strip())
    total = int(q.with_entities(func.count(LedgerEntry.id)).scalar() or 0)
    rows = (
        q.order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ApiResponse(
        data=LedgerPageOut(
            total=total,
            page=page,
            page_size=page_size,
            items=[
                LedgerEntryOut(
                    id=r.id,
                    entry_type=r.entry_type,
                    amount_fen=int(r.amount_fen or 0),
                    balance_after_fen=int(r.balance_after_fen or 0),
                    description=r.description,
                    created_at=_iso(r.created_at),
                )
                for r in rows
            ],
        )
    )


@router.get("/usage", response_model=ApiResponse[UsageOut])
def api_get_my_usage(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
    limit: int = Query(50, ge=1, le=_MAX_PAGE_SIZE),
):
    """我的用量（**口径 B**：`usage_events` 净额，⛔ 非口径 A 的 `grading_daily_stats`）。"""
    per_kind = (
        db.query(UsageEvent.kind, func.coalesce(func.sum(UsageEvent.delta), 0))
        .filter(UsageEvent.user_id == user_id)
        .group_by(UsageEvent.kind)
        .all()
    )
    totals: dict[str, int] = {str(k): int(v or 0) for k, v in per_kind}

    per_folder = (
        db.query(
            UsageEvent.kind,
            UsageEvent.folder_safe,
            func.coalesce(func.sum(UsageEvent.delta), 0),
        )
        .filter(UsageEvent.user_id == user_id)
        .group_by(UsageEvent.kind, UsageEvent.folder_safe)
        .all()
    )
    folders = [
        {"kind": str(k), "folder_safe": str(f), "net": int(v or 0)}
        for k, f, v in per_folder
        if int(v or 0) != 0
    ]

    recent_rows = (
        db.query(UsageEvent)
        .filter(UsageEvent.user_id == user_id)
        .order_by(UsageEvent.occurred_at.desc(), UsageEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    recent = [
        {
            "kind": r.kind,
            "folder_safe": r.folder_safe,
            "subject_key": r.subject_key,
            "net": int(r.delta or 0),
        }
        for r in recent_rows
    ]

    return ApiResponse(
        data=UsageOut(
            total_grade=int(totals.get("grade", 0)),
            total_upload=int(totals.get("upload", 0)),
            folders=folders,
            recent=recent,
        )
    )


# ────────────────────────── Phase 2：下单（P2-1）──────────────────────────

@router.post("/orders", response_model=ApiResponse[OrderCreateOut])
def api_create_order(
    payload: OrderCreateIn,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """下单：建订单 → 让通道 adapter 去要支付参数 → 返回给客户端（§7.3）。

    ⛔ 收款对象 = JWT 身份（**不收 `user_id` 入参**）。
    ⛔ 通道凭据缺失 ⇒ **501**，库里**零新增**（⛔ 不静默成功、⛔ 不留幽灵 pending 订单）。
    """
    try:
        order, intent = orders_svc.create_order(
            db, user_id=user_id, amount_fen=payload.amount_fen, channel=payload.channel
        )
    except _PAYMENT_ERRORS as exc:
        status = _http_status_for(exc) or 500
        logger.warning("下单失败：channel=%s user_id=%s HTTP=%s %s",
                       payload.channel, user_id, status, exc)
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    return ApiResponse(
        data=OrderCreateOut(
            order_id=order.id,
            channel=order.channel,
            amount_fen=int(order.amount_fen or 0),
            status=order.status,
            payee_entity_id=order.payee_entity_id,
            pay_params=dict(intent.pay_params or {}),
        )
    )


@router.get("/orders/{order_id}", response_model=ApiResponse[OrderStatusOut])
def api_get_order_status(
    order_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """订单状态轮询（前端二维码弹窗 2s 一次）。⛔ 只能查自己的订单（无 user_id 入参）。

    不存在 **或不属于当前用户** ⇒ 同一个 404（照 `/invoices` 的越权口径：
    不区分「没有这条」和「不是你的」，避免订单号被枚举探测）。
    """
    order = (
        db.query(PaymentOrder)
        .filter(PaymentOrder.id == str(order_id).strip(), PaymentOrder.user_id == user_id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=404, detail=f"订单不存在：{order_id}")
    return ApiResponse(
        data=OrderStatusOut(
            order_id=order.id,
            channel=order.channel,
            status=order.status,
            amount_fen=int(order.amount_fen or 0),
            paid_amount_fen=int(order.paid_amount_fen) if order.paid_amount_fen is not None else None,
            created_at=_iso(order.created_at),
            paid_at=_iso(order.paid_at),
        )
    )


# ────────────────────────── Phase 2：通道回调（P2-3）──────────────────────────

@router.post("/callback/{channel}")
async def api_channel_callback(
    channel: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """通道异步回调：**验签 → `apply_payment_confirmed`**（§2.3 §7.3）。

    · ⛔ **无 JWT**（通道不会带我们的令牌）—— 身份来自`{channel}` 的**验签**；
      验签不过 ⇒ 4xx，且**一行账都不记**（§6.3 D2：不自动冲销，防伪造回调打成负账）。
    · ⛔ 拿**原始 body** 验签（不是重序列化后的 JSON —— 那样必然验签失败）。
    · 应答体用**通道自己的格式**（微信 `{"code":"SUCCESS"}` / 支付宝 `success`），
      否则通道会把应答判为失败而无限重推。

    ⚠️ 这是本模块**唯一**的写路径端点；写动作全部经 `ledger.apply_payment_confirmed`。
    """
    raw_body = await request.body()
    try:
        adapter = channels.get_adapter(channel)
    except channels.UnknownChannelError as exc:
        logger.warning("收到未知通道回调：%s", channel)
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc

    try:
        fact, _entry, created = orders_svc.handle_callback(
            db, channel=channel, raw_body=raw_body, headers=request.headers
        )
    except _PAYMENT_ERRORS as exc:
        status = _http_status_for(exc) or 500
        body, media_type = adapter.callback_ack(False)
        logger.warning("通道回调被拒：channel=%s HTTP=%s %s", channel, status, exc)
        return Response(content=body, status_code=status, media_type=media_type)

    logger.info(
        "通道回调入账：channel=%s order_id=%s trade_no=%s amount_fen=%s 新建分录=%s",
        channel, fact.order_id, fact.channel_trade_no, fact.paid_amount_fen, created,
    )
    body, media_type = adapter.callback_ack(True)
    return Response(content=body, status_code=200, media_type=media_type)


# ────────────────────────── Phase 3：开票申请（P3-1）──────────────────────────

def _invoice_out(inv: Any) -> InvoiceOut:
    """ORM 行 → 响应体（⛔ 只回已拍票种/载体要用的字段）。"""
    return InvoiceOut(
        id=inv.id,
        order_id=inv.order_id,
        status=inv.status,
        amount_fen=int(inv.amount_fen or 0),
        title=inv.title,
        taxpayer_id=inv.taxpayer_id,
        email=inv.email,
        invoice_no=inv.invoice_no,
        issued_at=_iso(inv.issued_at),
        voided_at=_iso(inv.voided_at),
        created_at=_iso(inv.created_at),
    )


@router.post("/invoices", response_model=ApiResponse[InvoiceOut])
def api_submit_invoice(
    payload: InvoiceCreateIn,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """提交开票申请（P3-1）。**一单一票**，且只能给自己的**已支付**订单申请。

    已拍口径（逐字落实）：
      · 票种 = **普票** ⇒ 只收「抬头 ＋ 纳税人识别号」，⛔ 无专票四字段；
      · 载体 = **电子** ⇒ 交付 = **邮箱**，⛔ 无收件地址/邮寄字段；
      · 金额 = **含税**（分）⇒ 开票金额**从订单取**，⛔ 不采信请求体里的任何金额；
      · ⛔ 不出现税率/税额：本批走「老师申请 → 人工开票」，税额不由本系统计算。
    """
    try:
        invoice = invoices_svc.submit_invoice_request(
            db,
            user_id=user_id,
            order_id=payload.order_id,
            title=payload.title,
            taxpayer_id=payload.taxpayer_id,
            email=payload.email,
        )
    except _PAYMENT_ERRORS as exc:
        status = _http_status_for(exc) or 500
        logger.warning(
            "开票申请被拒：order_id=%s user_id=%s HTTP=%s %s",
            payload.order_id, user_id, status, exc,
        )
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    return ApiResponse(data=_invoice_out(invoice))


@router.get("/invoices", response_model=ApiResponse[InvoicePageOut])
def api_list_my_invoices(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=_MAX_PAGE_SIZE),
):
    """我的开票申请（分页，倒序）。⛔ 只能查自己（无 `user_id` 入参，照 /ledger）。"""
    total, rows = invoices_svc.list_invoices(
        db, user_id=user_id, page=page, page_size=page_size
    )
    return ApiResponse(
        data=InvoicePageOut(
            total=total,
            page=page,
            page_size=page_size,
            items=[_invoice_out(r) for r in rows],
        )
    )


# ──────────────── Phase 3 追加：E1/E2 只读对账巡检（§6.2 / §6.4）────────────────

@router.get("/admin/reconciliation", response_model=ApiResponse[ReconciliationOut])
def api_admin_reconciliation(
    db: Session = Depends(get_db),
    admin_id: str = Depends(get_current_user_id),
):
    """§6.2 的 E1/E2 只读巡检（**人工触发、低频**，⛔ 无常驻脚本、无调度框架 —— §6.4 L478/§13 L806）。

    **本端点为什么只读、并因此不违 `routers/payment.py:16`**：那条逐字只把
    `POST /payment/admin/grant`（后台**人工开通**这个**写**端点）排除在本批范围外，
    ⛔ 不是「所有 admin 端点都不许有」。本端点**零写路径**（不建表、不落差异行、不改任何状态）。

    E1/E2 的口径 = §6.2 L459/L460；判据本身**只有 `services/payment/ledger.py` 一处**
    （E1 复用既有的 `verify_invariant_e1()`，本端点不重写它）。

    ⚠️ **E3（通道一致）本阶段不落地**：三条硬阻塞与将来落点的三个前提逐条写在
       `docs/payment/payment-design.md` §6.5。本响应里**不出现** E3 字段。

    鉴权：沿用仓内既有的管理员闸 `_check_admin_permission`（`routers/admin.py:60`；
    照 `routers/admin_academic.py:26` 的既有复用方式），**任课教师 403**。
    """
    _check_admin_permission(db, admin_id)

    summary = ledger_svc.verify_invariants(db)
    e1 = summary["e1"]
    e2 = summary["e2"]
    logger.info(
        "对账巡检：E1 %s（%s/%s 账户不平）E2 %s（recharge=%s paid_orders=%s）",
        "平" if e1["ok"] else "不平", e1["unbalanced_count"], e1["accounts_checked"],
        "平" if e2["ok"] else "不平", e2["recharge_fen"], e2["paid_orders_fen"],
    )
    return ApiResponse(
        data=ReconciliationOut(
            e1=ReconcileE1Out(**e1),
            e2=ReconcileE2Out(**e2),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
    )
