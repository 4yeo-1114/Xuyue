# -*- coding: utf-8 -*-
"""口径 B · 通道适配层（设计稿 §2）。

注册表是**唯一的通道发现入口**：路由不 import 任何具体 adapter，
只 `get_adapter(channel)`。⇒ 通道定了（§10 Q2）/ 换主体了（§10 Q1），
只需新增一个 adapter ＋ 改这里的注册项，**账本与路由一行都不用改**（§2.1 的设计目标）。

依赖方向（§2.3，本包最重要的一条）：
    `routers/payment.py` → `channels/*`（只解析出「订单已被确认收款」这个事实）
                         → `ledger.apply_payment_confirmed`（只记账）
    ⛔ 本包**永不** import `app.services.payment.ledger`，**永不**写账本两表。
"""
from __future__ import annotations

from typing import Dict, Tuple

from app.services.payment.channels.alipay import AlipayChannelAdapter
from app.services.payment.channels.base import (  # noqa: F401  （对外转出数据契约）
    CallbackVerificationError,
    ChannelCallback,
    ChannelCapabilities,
    ChannelCryptoUnavailableError,
    ChannelError,
    ChannelIntent,
    ChannelNotConfiguredError,
    ChannelPaymentStatus,
    ChannelRefundResult,
    PaymentChannelAdapter,
    RefundRequest,
    UnknownChannelError,
)
from app.services.payment.channels.unset import UnsetChannelAdapter
from app.services.payment.channels.wechat import WechatPayChannelAdapter

CHANNEL_UNSET = "unset"
CHANNEL_WECHAT = "wechat_pay"
CHANNEL_ALIPAY = "alipay"

# 通道选型 = ① 类已拍（主导者 2026-09-24）：微信支付 ＋ 支付宝；收款主体 = 公司主体。
_ADAPTERS: Dict[str, PaymentChannelAdapter] = {
    CHANNEL_UNSET: UnsetChannelAdapter(),
    CHANNEL_WECHAT: WechatPayChannelAdapter(),
    CHANNEL_ALIPAY: AlipayChannelAdapter(),
}


def register(adapter: PaymentChannelAdapter) -> PaymentChannelAdapter:
    """注册/覆盖一个通道实现（新增通道、或测试注入替身）。"""
    name = str(getattr(adapter, "channel", "") or "").strip()
    if not name:
        raise ValueError("adapter.channel 不能为空")
    _ADAPTERS[name] = adapter
    return adapter


def get_adapter(channel: str) -> PaymentChannelAdapter:
    """按通道名取 adapter。未知通道 ⇒ `UnknownChannelError`（路由映射为 404）。

    ⚠️ 空/未知**不回落 `unset`**：回落会把「打错通道名」伪装成「通道未配置」，
       把客户端的错报成服务端的错（两者排查路径不同）。
    """
    name = str(channel or "").strip()
    adapter = _ADAPTERS.get(name)
    if adapter is None:
        raise UnknownChannelError(f"未知支付通道：{name or '(空)'}")
    return adapter


def registered_channels() -> Tuple[str, ...]:
    return tuple(sorted(_ADAPTERS.keys()))
