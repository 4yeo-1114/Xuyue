# -*- coding: utf-8 -*-
"""口径 B · 通道适配层基类与数据契约（设计稿 §2.2 / §2.3）。

**本模块最重要的一条边界（§2.3「账本侧对通道的唯一依赖」）：**
    账本只认识**一个事实** —— 「订单 X 已被通道确认收款」，入口是
    `ledger.apply_payment_confirmed(...)`。
    ⇒ ⛔ 本包（含 `wechat.py` / `alipay.py`）**永不 import** `app.services.payment.ledger`、
       **永不**直接写 `ledger_entries` / `payment_accounts`。
    ⇒ 依赖方向单向：`routers/payment.py` → channels（**只解析出事实**）→ ledger（**只记账**）。
       有回归用例在源码级钉住这条（`tests/test_payment_p2.py::test_p2_2_channels_never_touch_ledger`）。

**未定项隔离**：通道/主体是 ① 类未拍项（§10 Q1/Q2）。未配置 ⇒ 挂 `UnsetChannelAdapter`
（可运行、可测试、**明确报错**），而不是「到处 if 判断」或「留白」。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Mapping, Optional, TypedDict


class ChannelCapabilities(TypedDict):
    """§2.2 的能力声明（**纯声明**，不参与记账）。"""

    channel: str
    supports_callback: bool      # 是否有异步回调（对公转账 = False，需人工核销）
    supports_refund: bool        # 是否支持原路退回
    requires_payee_entity: bool  # 是否绑定收款主体（已拍：两个真实通道都 = True）
    fee_rate_bps: Optional[int]  # 通道手续费（bps）；None = 未定（§10 Q1，⛔ 本批不猜）


@dataclass(frozen=True)
class ChannelIntent:
    """下单结果：交给前端/客户端的**支付参数**（§7.3「下单（返回通道支付参数）」）。

    ⚠️ 通道交易号在**下单时通常还没有**（微信要等用户支付、支付宝要等回调），
       故 `channel_trade_no` 默认 None；它由 `parse_callback` 带回来。
    """

    channel: str
    out_trade_no: str
    pay_params: dict[str, Any] = field(default_factory=dict)
    channel_trade_no: Optional[str] = None


@dataclass(frozen=True)
class ChannelCallback:
    """回调解析出的**事实**（§2.3：账本只认这一件事）。

    ⚠️ `order_id` 是**我方订单号**（= `payment_orders.id`，即通道侧的 `out_trade_no`），
       ⛔ **不是**通道交易号；后者在 `channel_trade_no`。
    ⚠️ ⛔ **不携带 user_id** —— 收款主体由订单号反查，⛔ 绝不信任请求体里的身份字段（越权）。
    """

    channel: str
    order_id: str
    channel_trade_no: str
    paid_amount_fen: int
    paid_at: datetime
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChannelPaymentStatus:
    """主动查单结果（§2.2 `query_payment`）。"""

    channel: str
    order_id: str
    channel_trade_no: Optional[str]
    paid: bool
    paid_amount_fen: int = 0
    paid_at: Optional[datetime] = None


@dataclass(frozen=True)
class RefundRequest:
    """退款请求（§2.2 `create_refund`；⛔ 本批不做 P2-4）。

    ⚠️ 不做的理由**不是「退款被禁」**，而是**可退对象不存在**：退款口径已拍 =
    「**余额不可退；套餐未使用部分可退**（待套餐上线后实现，见 §10 Q5 / §5.2）」，
    而套餐已后置（Phase 1 缩减为只做预充值按量扣）⇒ 当前没有套餐可退。
    """

    order_id: str
    channel_trade_no: Optional[str]
    refund_amount_fen: int
    reason: str = ""


@dataclass(frozen=True)
class ChannelRefundResult:
    channel: str
    ok: bool
    channel_refund_no: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)


# ────────────────────────── 异常（由路由映射为 HTTP 状态码）──────────────────────────

class ChannelError(Exception):
    """通道层异常基类。`http_status` 由 `routers/payment.py` 直接采用。"""

    http_status: ClassVar[int] = 500


class UnknownChannelError(ChannelError):
    """通道名未注册 ⇒ 404。"""

    http_status = 404


class ChannelNotConfiguredError(ChannelError):
    """通道未配置/凭据缺失 ⇒ **501**（§7.3 明文：501 = 通道未配置）。

    ⚠️ 这是 §2.2 `UnsetChannelAdapter` 的默认行为，也是凭据缺失时的行为 ——
       ⛔ **必须明确失败，不许静默走假成功**。
    """

    http_status = 501


class ChannelCryptoUnavailableError(ChannelError):
    """服务端缺少密码学依赖（`cryptography`）⇒ 503。

    ⚠️ 独立出来是为了**不要**把它伪装成「验签失败」—— 后者是 400（客户端问题），
       本类是服务端缺件，必须一眼可辨（否则故障会被当成「有人在伪造回调」排查）。
    """

    http_status = 503


class CallbackVerificationError(ChannelError):
    """回调验签失败 / 事件类型不受理 ⇒ **400**，且**绝不入账**。"""

    http_status = 400


# ────────────────────────── 接口（照 §2.2）──────────────────────────

class PaymentChannelAdapter(ABC):
    """§2.2 的 `PaymentChannelAdapter`。

    ⛔ 实现类**只做两件事**：① 把我们的话带给通道（`create_payment`）；
    ② 把通道的话翻译成 `ChannelCallback`（`parse_callback`）。
    记账、余额、幂等**一律不在这里**。
    """

    channel: ClassVar[str] = "unset"

    @abstractmethod
    def capabilities(self) -> ChannelCapabilities:
        """能力声明。"""

    @abstractmethod
    def create_payment(self, order: Any) -> ChannelIntent:
        """下单。入参是 `PaymentOrder`（⚠️ 可能是**尚未落库**的实例，只用其 `id`/`amount_fen`）。

        raise `ChannelNotConfiguredError`（凭据缺失）/ `ChannelError`（通道拒绝）。
        """

    @abstractmethod
    def parse_callback(self, raw_body: bytes, headers: Mapping[str, str]) -> Optional[ChannelCallback]:
        """解析并**验签**回调。

        返回 `None` = 验签失败 / 事件不受理 ⇒ 调用方**不得入账**（§2.2：
        `UnsetChannelAdapter.parse_callback` 恒返回 None）。
        raise `ChannelNotConfiguredError`（无法验签，因为没配置）。
        """

    def query_payment(self, channel_trade_no: str) -> ChannelPaymentStatus:
        """主动查单。⛔ 本批未实现（不在 P2-1/P2-2/P2-3 范围，且无法在无凭据环境下验证）。"""
        raise NotImplementedError(f"{self.channel}: query_payment 未实现（Phase 2 未纳入本批）")

    def create_refund(self, req: RefundRequest) -> ChannelRefundResult:
        """退款。⛔ 本批未实现 —— 理由 = **可退对象不存在**（⛔ 不是「退款被禁」）。

        已拍口径：「**余额不可退；套餐未使用部分可退**（待套餐上线后实现，见 §10 Q5 / §5.2）」。
        套餐已后置 ⇒ 当前没有套餐、也就没有「未使用部分」可退 ⇒ P2-4 无实现对象。
        """
        raise NotImplementedError(
            f"{self.channel}: 退款（P2-4）未实现：可退对象不存在 —— 余额不可退，"
            "套餐未使用部分可退但套餐尚未上线（§10 Q5 / §5.2）"
        )

    def callback_ack(self, ok: bool) -> tuple[str, str]:
        """回调应答体 `(body, media_type)`。

        ⚠️ **只给 body / media_type，HTTP 状态码由路由决定**（成功 = 200；
        失败 = 按异常映射出的 4xx/5xx）—— 两者都要让通道**判定为失败并重推**，
        但状态码保持可诊断，⛔ 不把「验签失败」伪装成 200。

        默认 = 本仓统一风格 `ApiResponse{code,message,data}`；**通道有自己格式时必须覆写**
        （微信要 `{"code":"SUCCESS"}`、支付宝要纯文本 `success`），
        否则通道会把应答判为失败而**无限重推**。
        """
        if ok:
            return '{"code":0,"message":"ok","data":null}', "application/json"
        return '{"code":1,"message":"invalid callback","data":null}', "application/json"
