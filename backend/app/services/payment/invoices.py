# -*- coding: utf-8 -*-
"""口径 B · 开票申请的领域逻辑（P3-1 结构：状态机 / 一单一票 / 越权收敛）。

设计依据：docs/payment/payment-design.md §9-Phase3「P3-1 发票」、§10 Q3。

分工（照 `orders.py` 的范式：路由只做 HTTP 映射）：
    提交：`submit_invoice_request`  →  校验归属/状态 → 建申请（`requested`）
    查询：`list_invoices`           →  只查**自己**的（⛔ 无 `user_id` 入参）
    标记：`mark_issued` / `mark_void` →  **状态机的数据层**，本批⛔ 无路由调用

⛔ **本批不建任何后台/admin 端点**（`routers/payment.py:16` 已声明 admin 端点不在范围）
   ⇒ `mark_issued` / `mark_void` 只把状态机留好、有回归用例钉住跃迁表，**等口径拍完再接端点**。

状态机（**严格线性**）::

    requested ──▶ issued ──▶ void

⚠️ 依据（③ 类技术取值，写明理由）：brief 逐字给的链就是 `requested → issued → void`；
   `requested → void`（申请未开就作废）**不在这条链上** ⇒ 加它属**自创**，且本批没有任何
   端点会走到它（老师侧只有「提交」与「查询」两个端点）。
   ⛔ 本模块**不是**红冲：`void` = 作废，红字发票本阶段不做（brief 已拍「红冲：本阶段不做」）。

⛔ **金额口径**（§10 Q4 已拍「0.5 元/份 = 含税价」）：开票金额 = **订单**的 `amount_fen`
   （含税·分），⛔ **绝不从请求体取** —— 否则老师能自己开票面金额。
"""
from __future__ import annotations

import datetime
import logging

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.payment_invoice import PaymentInvoice
from app.models.payment_order import PaymentOrder
from app.services.payment import ledger as ledger_svc

logger = logging.getLogger(__name__)

INVOICE_REQUESTED = "requested"
INVOICE_ISSUED = "issued"
INVOICE_VOID = "void"

# 状态机的**唯一真值来源**（⛔ 别在别处再写一份 if —— 有回归用例逐条钉住这张表）
ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    INVOICE_REQUESTED: (INVOICE_ISSUED,),
    INVOICE_ISSUED: (INVOICE_VOID,),
    INVOICE_VOID: (),
}


class InvoiceNotFoundError(Exception):
    """订单/发票不存在**或不属于当前用户** ⇒ 路由映射为 404。

    ⚠️ 「不存在」与「不是你的」**回同一个 404**：回 403 等于告诉探测者「这个订单号是真的」。
    """

    http_status = 404


class InvoiceStateError(Exception):
    """状态不允许本次操作（重复申请 / 非法跃迁 / 订单未支付）⇒ 路由映射为 409。"""

    http_status = 409


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


# ────────────────────────── 提交开票申请 ──────────────────────────

def submit_invoice_request(
    db: Session,
    *,
    user_id: str,
    order_id: str,
    title: str,
    taxpayer_id: str,
    email: str,
) -> PaymentInvoice:
    """提交开票申请（P3-1）。成功返回 `status='requested'` 的申请行。

    ⛔ `user_id` 只来自 JWT（由路由注入），⛔ 不是请求参数。
    raise `InvoiceNotFoundError`(404) / `InvoiceStateError`(409)。
    """
    uid = str(user_id or "").strip()
    if not uid:
        raise ValueError("user_id 不能为空")
    oid = str(order_id or "").strip()
    if not oid:
        raise ValueError("order_id 不能为空")

    order = db.query(PaymentOrder).filter(PaymentOrder.id == oid).first()
    # ⛔ 归属校验与「订单不存在」合并成同一个 404（见 InvoiceNotFoundError docstring）
    if order is None or str(order.user_id or "").strip() != uid:
        raise InvoiceNotFoundError(f"订单不存在：{oid}")

    # 只有**已支付**订单能开票（pending/failed/cancelled/refunded 一律拒）
    if order.status != ledger_svc.ORDER_PAID:
        raise InvoiceStateError(
            f"订单 {oid} 当前状态为 {order.status}，只有已支付订单可申请开票"
        )

    existing = db.query(PaymentInvoice).filter(PaymentInvoice.order_id == oid).first()
    if existing is not None:
        raise InvoiceStateError(
            f"订单 {oid} 已提交过开票申请（当前状态 {existing.status}），一单一票"
        )

    invoice = PaymentInvoice(
        order_id=oid,
        user_id=uid,
        status=INVOICE_REQUESTED,
        # ⚠️ 含税金额**只从订单取**（见模块 docstring 的金额口径）；⛔ 请求体里的金额一律不采信
        amount_fen=int(order.amount_fen or 0),
        title=str(title or "").strip(),
        taxpayer_id=str(taxpayer_id or "").strip(),
        email=str(email or "").strip(),
    )
    db.add(invoice)
    try:
        db.commit()
    except IntegrityError:
        # 并发兜底：`uk_payment_invoice_order` 冲突 ⇒ 另一个请求已经建了 ⇒ 判重复（409）
        db.rollback()
        raise InvoiceStateError(f"订单 {oid} 已提交过开票申请，一单一票")
    db.refresh(invoice)
    return invoice


# ────────────────────────── 查询（只能查自己）──────────────────────────

def list_invoices(
    db: Session, *, user_id: str, page: int, page_size: int
) -> tuple[int, list[PaymentInvoice]]:
    """我的开票申请（分页，倒序）。⛔ **不收 `user_id` 入参** —— 只能用 JWT 身份。

    返回 `(总数, 本页行)`。
    """
    q = db.query(PaymentInvoice).filter(PaymentInvoice.user_id == str(user_id or "").strip())
    total = int(q.with_entities(func.count(PaymentInvoice.id)).scalar() or 0)
    rows = (
        q.order_by(PaymentInvoice.created_at.desc(), PaymentInvoice.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return total, rows


# ────────────────────────── 状态机（本批无路由，只留数据层）──────────────────────────

def _load(db: Session, invoice_id: str) -> PaymentInvoice:
    inv = (
        db.query(PaymentInvoice)
        .filter(PaymentInvoice.id == str(invoice_id or "").strip())
        .first()
    )
    if inv is None:
        raise InvoiceNotFoundError(f"发票申请不存在：{invoice_id}")
    return inv


def _transition(
    db: Session, invoice: PaymentInvoice, target: str, *, invoice_no: str | None = None
) -> PaymentInvoice:
    allowed = ALLOWED_TRANSITIONS.get(invoice.status, ())
    if target not in allowed:
        raise InvoiceStateError(
            f"发票申请 {invoice.id} 当前状态 {invoice.status} 不能跃迁到 {target}"
        )
    invoice.status = target
    now = _now()
    if target == INVOICE_ISSUED:
        invoice.issued_at = now
        if invoice_no is not None and str(invoice_no).strip():
            invoice.invoice_no = str(invoice_no).strip()
    else:  # INVOICE_VOID
        invoice.voided_at = now
    db.commit()
    db.refresh(invoice)
    return invoice


def mark_issued(db: Session, *, invoice_id: str, invoice_no: str | None = None) -> PaymentInvoice:
    """人工开票完成：`requested` → `issued`（**本批无路由**）。

    ⚠️ `invoice_no` 可空（③ 类取值，取可逆侧）：真实流程里发票号在税局系统出票后才有，
       允许「先标记已开票、号码后补」比强制必填更容易退回；列本身可空（`requested` 行没有它）。
    """
    return _transition(db, _load(db, invoice_id), INVOICE_ISSUED, invoice_no=invoice_no)


def mark_void(db: Session, *, invoice_id: str) -> PaymentInvoice:
    """作废：`issued` → `void`（**本批无路由**）。

    ⛔ **不是红冲**：红字发票本阶段不做（brief 已拍）；本函数只改状态与时间戳，⛔ 不动账本、
    ⛔ 不产生任何 `ledger_entries`（余额不可退 = §10 Q5，开票作废与钱无关）。
    """
    return _transition(db, _load(db, invoice_id), INVOICE_VOID)
