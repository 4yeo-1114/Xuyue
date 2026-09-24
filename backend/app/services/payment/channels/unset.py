# -*- coding: utf-8 -*-
"""口径 B · `UnsetChannelAdapter`（**默认注册项**，§2.2 末段逐字行为）。

设计意图：**未定 = 一个可运行、可测试、明确报错的实现**，而不是「到处 if 判断」或「留白」。
⇒ 账本侧代码**一条都不用改**，通道定了只需新增一个 adapter 并改注册项。

⚠️ 「明确报错」是硬要求：⛔ 不许静默返回一个假的下单成功（那等于**假收钱**）。
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from app.services.payment.channels.base import (
    ChannelCallback,
    ChannelCapabilities,
    ChannelIntent,
    ChannelNotConfiguredError,
    PaymentChannelAdapter,
)

NOT_CONFIGURED_MESSAGE = "收款通道尚未配置"


class UnsetChannelAdapter(PaymentChannelAdapter):
    """未配置通道的占位实现（§2.2）。"""

    channel = "unset"

    def capabilities(self) -> ChannelCapabilities:
        return {
            "channel": self.channel,
            "supports_callback": False,
            "supports_refund": False,   # 未配置通道 ⇒ 退款同样无从谈起（退款口径见 base.py）
            "requires_payee_entity": False,
            "fee_rate_bps": None,
        }

    def create_payment(self, order: Any) -> ChannelIntent:
        # §2.2 逐字：抛 HTTPException(501, detail="收款通道尚未配置")
        # ⚠️ 本层不 import fastapi —— 异常→HTTP 的映射统一在 routers/payment.py 做，
        #    这样通道层保持「纯业务、可单测、不依赖 Web 框架」。
        raise ChannelNotConfiguredError(NOT_CONFIGURED_MESSAGE)

    def parse_callback(self, raw_body: bytes, headers: Mapping[str, str]) -> Optional[ChannelCallback]:
        # §2.2 逐字：恒返回 None（⇒ 调用方一律不得入账）
        return None

    def callback_ack(self, ok: bool) -> tuple[str, str]:
        # 未配置通道本就不该收到回调；失败态让对端重推并暴露问题，⛔ 不伪装成功。
        if ok:
            return '{"code":0,"message":"ok","data":null}', "application/json"
        return (
            '{"code":1,"message":"' + NOT_CONFIGURED_MESSAGE + '","data":null}',
            "application/json",
        )
