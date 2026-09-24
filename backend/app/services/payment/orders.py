# -*- coding: utf-8 -*-
"""口径 B · 下单与回调编排（P2-1 / P2-3 的业务逻辑；路由只做 HTTP 映射）。

设计依据：设计稿 §2.3（窄依赖）、§7.3（路由）、§6.3（D1/D2/D3 差异处置）。

分工（⛔ 这是本模块存在的主要理由：把「验签」与「记账」物理隔开）：
    下单：`create_order`  →  建订单 ＋ 让 adapter 去通道要支付参数
    回调：`handle_callback` →  adapter **验签**并翻译出 `ChannelCallback`
                              →  `ledger.apply_payment_confirmed` **记账**
    ⛔ adapter 拿不到账本、账本拿不到 adapter（两个方向都不 import）。
    ⛔ **不信任请求体里的 user_id**：收款对象一律由订单号反查（§7.3 越权纪律）。
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

from sqlalchemy.orm import Session

from app.config import settings
from app.models.payment_order import PaymentOrder
from app.models.user import gen_uuid
from app.services.payment import ledger as ledger_svc
from app.services.payment.channels import (
    CallbackVerificationError,
    ChannelCallback,
    get_adapter,
)

logger = logging.getLogger(__name__)


def resolve_payee_entity_id() -> Optional[str]:
    """收款主体标识（§10 Q1 已拍「公司主体」，但**具体执照/主体标识主导者没给**）。

    ⇒ ⛔ **不编值**：从配置读；配置缺失 ⇒ 留空 ＋ 记日志（照 brief 的口径）。
    """
    value = str(getattr(settings, "PAYMENT_PAYEE_ENTITY_ID", "") or "").strip()
    if value:
        return value
    logger.warning(
        "收款主体标识未配置（PAYMENT_PAYEE_ENTITY_ID 为空）：订单将以空主体落库。"
        "收款主体已拍为「公司主体」，但具体主体标识待补 —— 通道侧资质到位前属预期状态。"
    )
    return None


def create_order(
    db: Session,
    *,
    user_id: str,
    amount_fen: int,
    channel: str,
    subject_type: str = "recharge",
) -> Tuple[PaymentOrder, Any]:
    """下单（P2-1）。返回 `(订单, ChannelIntent)`。

    ⚠️ **先向通道要支付参数，成功后才落库**（`PaymentOrder(id=...)` 用显式 id，
       尚未 flush）。理由：通道未配置/被拒时**不留一条幽灵 pending 订单**
       —— brief 的验收是「下单**明确失败**」，不是「留下半截记录」。
       通道失败 ⇒ `ChannelNotConfiguredError`(501) / `ChannelError`(500)，**库里零新增**。

    ⛔ `user_id` 只来自 JWT（由路由注入），⛔ 不是请求参数。
    """
    amount = int(amount_fen)
    if amount <= 0:
        raise ValueError("订单金额必须为正（单位：分）")

    adapter = get_adapter(channel)  # 未知通道 ⇒ UnknownChannelError(404)
    order = PaymentOrder(
        id=gen_uuid(),                      # 显式 id：通道要拿它当 out_trade_no
        user_id=str(user_id).strip(),
        channel=adapter.channel,
        status=ledger_svc.ORDER_PENDING,
        amount_fen=amount,
        subject_type=str(subject_type or "recharge").strip() or "recharge",
        payee_entity_id=resolve_payee_entity_id(),
    )
    intent = adapter.create_payment(order)  # 凭据缺失 ⇒ 501（⛔ 不落库、⛔ 不假成功）

    db.add(order)
    db.commit()
    db.refresh(order)
    return order, intent


def handle_callback(
    db: Session,
    *,
    channel: str,
    raw_body: bytes,
    headers: Any,
) -> Tuple[ChannelCallback, Any, bool]:
    """回调编排（P2-3）。返回 `(通道事实, 分录, 是否新建分录)`。

    顺序**不可换**：先验签拿事实，再记账。验签不过（`parse_callback` 返回 None）⇒
    `CallbackVerificationError`(400)，**一行账都不记**（§6.3 D2：不自动冲销，
    防被伪造回调打成负账 —— 这里更进一步：伪造回调**根本不产生任何分录**）。

    ⛔ 本函数**不读也不信**请求体里的任何身份字段；收款对象由订单号反查。
    """
    adapter = get_adapter(channel)  # 未知通道 ⇒ UnknownChannelError(404)
    fact = adapter.parse_callback(raw_body, headers)
    if fact is None:
        raise CallbackVerificationError(f"{channel} 回调验签失败或事件不受理（未入账）")
    entry, created = ledger_svc.apply_payment_confirmed(
        db,
        order_id=fact.order_id,
        channel_trade_no=fact.channel_trade_no,
        paid_amount_fen=fact.paid_amount_fen,
        paid_at=fact.paid_at,
    )
    return fact, entry, created
