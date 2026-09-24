# -*- coding: utf-8 -*-
"""口径 B · 微信支付 adapter（APIv3 · Native 扫码下单）。

设计依据：设计稿 §2.2（接口）、§2.3（窄依赖）、§10 Q1/Q2（通道与主体 = ① 类，本题**已拍**：
通道 = 微信支付 ＋ 支付宝；收款主体 = 公司主体 ⇒ `requires_payee_entity=True`）。

⛔ **本模块永不 import `ledger`**，也永不写 `ledger_entries` / `payment_accounts`（§2.3）。
   它只做两件事：把我们的话带给微信（`create_payment`）／把微信的话翻译成 `ChannelCallback`
   （`parse_callback`）。**记账是 `ledger.apply_payment_confirmed` 的事。**

⛔ 凭据全部从配置读（`app.config.settings`），**允许缺失**；缺失 ⇒
   `ChannelNotConfiguredError`（HTTP 501），⛔ **绝不由本模块伪造一个成功响应**。

协议要点（可复算，便于复核）：
  · 签名串 = `"{method}\\n{url_path}\\n{timestamp}\\n{nonce}\\n{body}\\n"`，RSASSA-PKCS1-v1_5 + SHA-256
  · 回调请求头 = `Wechatpay-Timestamp` / `Wechatpay-Nonce` / `Wechatpay-Signature` / `Wechatpay-Serial`
  · 回调 body 里的 `resource` 是 **AES-256-GCM** 密文，密钥 = APIv3 密钥（32 字节）
  · 应答必须是 `{"code":"SUCCESS"}`（否则微信按失败**无限重推**）
"""
from __future__ import annotations

import base64
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from app.config import settings
from app.services.payment.channels import crypto
from app.services.payment.channels.base import (
    ChannelCallback,
    ChannelCapabilities,
    ChannelError,
    ChannelIntent,
    ChannelNotConfiguredError,
    PaymentChannelAdapter,
)

logger = logging.getLogger(__name__)

CHANNEL = "wechat_pay"
NATIVE_URL_PATH = "/v3/pay/transactions/native"
# 回调时间戳容差（秒）：防重放。⚠️ 微信官方建议 5 分钟。
TS_TOLERANCE_SEC = 300
DEFAULT_DESCRIPTION = "叙阅批改充值"


def _cfg(name: str) -> str:
    return str(getattr(settings, name, "") or "").strip()


def _notify_url() -> Optional[str]:
    base = _cfg("PAYMENT_CALLBACK_BASE_URL").rstrip("/")
    return f"{base}/api/v1/payment/callback/{CHANNEL}" if base else None


def _http_post_json(url: str, *, headers: Mapping[str, str], body: bytes,
                    timeout: float = 15.0) -> tuple[int, dict[str, Any], Mapping[str, str]]:
    """HTTP 传输层（**唯一**的 I/O 接缝；测试可替换它，从而在无凭据环境下也能验签参数）。

    返回 `(status_code, json_or_empty, headers)`。
    """
    import requests  # 局部 import：让本模块在无网络依赖的场景（如纯单测）也能被导入

    resp = requests.post(url, data=body, headers=dict(headers), timeout=timeout)
    try:
        data = resp.json() if resp.content else {}
    except Exception:
        data = {}
    return resp.status_code, (data if isinstance(data, dict) else {}), dict(resp.headers or {})


class WechatPayChannelAdapter(PaymentChannelAdapter):
    channel = CHANNEL

    def capabilities(self) -> ChannelCapabilities:
        return {
            "channel": self.channel,
            "supports_callback": True,
            # 原路退回能力微信是有的，但退款口径已拍「**余额不可退；套餐未使用部分可退**
            # （待套餐上线后实现，见 §10 Q5 / §5.2）」⇒ 套餐后置、**可退对象不存在** ⇒ 本批
            # 不做 P2-4（⛔ 不是「退款被禁」）。故此处如实声明 False：能力声明必须**反映我方
            # 是否真的支持**，不是通道理论上能不能。
            "supports_refund": False,
            "requires_payee_entity": True,   # 已拍：收款主体 = 公司主体
            "fee_rate_bps": None,            # §10 Q1：手续费谁承担未拍 ⇒ None（⛔ 不猜）
        }

    # ────────────────────────── 配置检查（缺失 ⇒ 501，⛔ 不静默）──────────────────────────

    def _pay_config(self) -> dict[str, Any]:
        """下单所需凭据。返回已解析的私钥 bytes（PEM 校验在此就地做掉）。"""
        missing = []
        app_id = _cfg("PAYMENT_WECHAT_APP_ID")
        mch_id = _cfg("PAYMENT_WECHAT_MCH_ID")
        serial_no = _cfg("PAYMENT_WECHAT_CERT_SERIAL_NO")
        private_key = _cfg("PAYMENT_WECHAT_PRIVATE_KEY")
        for name, value in (
            ("PAYMENT_WECHAT_APP_ID", app_id),
            ("PAYMENT_WECHAT_MCH_ID", mch_id),
            ("PAYMENT_WECHAT_CERT_SERIAL_NO", serial_no),
            ("PAYMENT_WECHAT_PRIVATE_KEY", private_key),
        ):
            if not value:
                missing.append(name)
        if missing:
            raise ChannelNotConfiguredError(
                "微信支付通道未配置：缺少 " + "、".join(missing)
                + "（收款主体资质尚未申请，本状态为预期；配置齐全后自动生效）"
            )
        pem = crypto.load_pem(private_key, what="微信支付商户私钥")
        crypto.load_private_key(pem)  # PEM 非法 ⇒ ChannelCryptoUnavailableError(503)，不是 501
        return {"app_id": app_id, "mch_id": mch_id, "serial_no": serial_no, "private_pem": pem}

    def _callback_config(self) -> dict[str, Any]:
        """回调验签/解密所需凭据。⚠️ 公钥**先就地 load 一次**校验 PEM：
        否则「公钥配错了」会被 `rsa_verify_sha256` 归约成「验签失败(400)」，
        把服务端配置错误误诊成「有人在伪造回调」。"""
        missing = []
        api_v3_key = _cfg("PAYMENT_WECHAT_API_V3_KEY")
        public_key = _cfg("PAYMENT_WECHAT_PUBLIC_KEY")
        for name, value in (("PAYMENT_WECHAT_API_V3_KEY", api_v3_key),
                            ("PAYMENT_WECHAT_PUBLIC_KEY", public_key)):
            if not value:
                missing.append(name)
        if missing:
            raise ChannelNotConfiguredError(
                "微信支付通道未配置（无法验签回调）：缺少 " + "、".join(missing)
            )
        key_bytes = api_v3_key.encode("utf-8")
        if len(key_bytes) != 32:
            raise ChannelCryptoUnavailableError(
                f"PAYMENT_WECHAT_API_V3_KEY 必须是 32 字节（当前 {len(key_bytes)}）"
            )
        pub_pem = crypto.load_pem(public_key, what="微信支付公钥")
        crypto.load_public_key(pub_pem)
        return {"api_v3_key": key_bytes, "public_pem": pub_pem,
                "mch_id": _cfg("PAYMENT_WECHAT_MCH_ID"), "app_id": _cfg("PAYMENT_WECHAT_APP_ID")}

    # ────────────────────────── 下单 ──────────────────────────

    def create_payment(self, order: Any) -> ChannelIntent:
        cfg = self._pay_config()
        body: dict[str, Any] = {
            "appid": cfg["app_id"],
            "mchid": cfg["mch_id"],
            "description": DEFAULT_DESCRIPTION,
            "out_trade_no": str(order.id),          # 我方订单号就是通道的 out_trade_no
            "amount": {"total": int(order.amount_fen), "currency": "CNY"},
        }
        notify = _notify_url()
        if notify:
            body["notify_url"] = notify
        body_bytes = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(16)
        message = f"POST\n{NATIVE_URL_PATH}\n{timestamp}\n{nonce}\n{body_bytes.decode('utf-8')}\n"
        signature = crypto.rsa_sign_sha256(cfg["private_pem"], message.encode("utf-8"))

        headers = {
            "Authorization": (
                'WECHATPAY2-SHA256-RSA2048 '
                f'mchid="{cfg["mch_id"]}",nonce_str="{nonce}",'
                f'timestamp="{timestamp}",serial_no="{cfg["serial_no"]}",'
                f'signature="{signature}"'
            ),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "xuyue-payment/1.0",
        }
        url = _cfg("PAYMENT_WECHAT_API_BASE").rstrip("/") + NATIVE_URL_PATH
        status, data, resp_headers = _http_post_json(url, headers=headers, body=body_bytes)

        if status != 200:
            raise ChannelError(
                "微信支付下单失败：HTTP %s code=%s message=%s"
                % (status, data.get("code"), data.get("message"))
            )
        # 响应验签（微信要求；公钥已在本方法开头校验过，故这里不必再取 _callback_config）
        self._verify_response(resp_headers, json.dumps(data, separators=(",", ":"), ensure_ascii=False))

        code_url = str(data.get("code_url") or "").strip()
        if not code_url:
            raise ChannelError("微信支付下单响应缺少 code_url，无法继续")
        return ChannelIntent(
            channel=self.channel,
            out_trade_no=str(order.id),
            pay_params={"code_url": code_url, "out_trade_no": str(order.id)},
        )

    def _verify_response(self, resp_headers: Mapping[str, str], body_text: str) -> None:
        """校验微信**响应**签名。⚠️ 微信对响应也签名，跳过等于放行中间人改包。"""
        h = {str(k).lower(): v for k, v in (resp_headers or {}).items()}
        pub = _cfg("PAYMENT_WECHAT_PUBLIC_KEY")
        if not pub or not h.get("wechatpay-signature"):
            return  # 未配置公钥 ⇒ 无法验（回调侧会因缺少公钥而 501，此处不额外报错）
        message = "{}\n{}\n{}\n".format(
            h.get("wechatpay-timestamp", ""), h.get("wechatpay-nonce", ""), body_text
        )
        if not crypto.rsa_verify_sha256(
            crypto.load_pem(pub, what="微信支付公钥"), message.encode("utf-8"),
            h.get("wechatpay-signature", ""),
        ):
            raise ChannelError("微信支付下单响应验签失败（响应可能被篡改）")

    # ────────────────────────── 回调 ──────────────────────────

    def parse_callback(self, raw_body: bytes, headers: Mapping[str, str]) -> Optional[ChannelCallback]:
        cfg = self._callback_config()  # 未配置 / PEM 非法 ⇒ raise（501 / 503），⛔ 不返回 None 蒙混
        try:
            return self._parse_verified(cfg, raw_body, headers)
        except ChannelError:
            raise
        except Exception:
            # 任何解析失败（密文损坏、JSON 破损、字段缺失）一律按**不可信**处理 ⇒ None
            logger.warning("微信支付回调解析失败，按验签失败处理（不入账）", exc_info=True)
            return None

    def _parse_verified(self, cfg: dict[str, Any], raw_body: bytes,
                        headers: Mapping[str, str]) -> Optional[ChannelCallback]:
        h = {str(k).lower(): ("" if v is None else str(v)) for k, v in (headers or {}).items()}
        ts = h.get("wechatpay-timestamp", "")
        nonce = h.get("wechatpay-nonce", "")
        sig = h.get("wechatpay-signature", "")
        if not (ts and nonce and sig):
            logger.warning("微信支付回调缺少 Wechatpay-Timestamp/Nonce/Signature 头")
            return None
        # 重放防护：时间戳必须新鲜（否则昨天抓到的合法回调今天还能再投一次）
        try:
            skew = abs(int(time.time()) - int(ts))
        except (TypeError, ValueError):
            return None
        if skew > TS_TOLERANCE_SEC:
            logger.warning("微信支付回调时间戳超出容差（%ss > %ss），已拒绝", skew, TS_TOLERANCE_SEC)
            return None

        try:
            body_text = raw_body.decode("utf-8")
        except UnicodeDecodeError:
            return None
        message = f"{ts}\n{nonce}\n{body_text}\n"
        if not crypto.rsa_verify_sha256(cfg["public_pem"], message.encode("utf-8"), sig):
            logger.warning("微信支付回调验签失败（已拒绝，未入账）")
            return None

        envelope = json.loads(body_text)
        if str(envelope.get("event_type") or "") != "TRANSACTION.SUCCESS":
            logger.info("微信支付回调事件类型不受理：event_type=%s", envelope.get("event_type"))
            return None

        resource = envelope.get("resource") or {}
        if str(resource.get("algorithm") or "") != "AEAD_AES_256_GCM":
            logger.error("微信支付回调 resource.algorithm 非 AEAD_AES_256_GCM：%s", resource.get("algorithm"))
            return None
        plaintext = crypto.aes256_gcm_decrypt(
            key=cfg["api_v3_key"],
            nonce=str(resource.get("nonce") or "").encode("utf-8"),
            ciphertext=base64.b64decode(str(resource.get("ciphertext") or "")),
            associated_data=str(resource.get("associated_data") or "").encode("utf-8"),
        )
        payload = json.loads(plaintext.decode("utf-8"))

        # 纵深防御：签名有效但商户号/应用号对不上 ⇒ 不是发给我们的（或密钥串了）
        for field, expected, what in (("mchid", cfg["mch_id"], "商户号"),
                                      ("appid", cfg["app_id"], "应用号")):
            got = str(payload.get(field) or "")
            if expected and got and got != expected:
                logger.error("微信支付回调 %s 不符：期望 %s 实得 %s（已拒绝）", what, expected, got)
                return None
        if str(payload.get("trade_state") or "") != "SUCCESS":
            logger.info("微信支付回调 trade_state 非 SUCCESS：%s", payload.get("trade_state"))
            return None

        out_trade_no = str(payload.get("out_trade_no") or "").strip()
        transaction_id = str(payload.get("transaction_id") or "").strip()
        amount = payload.get("amount") if isinstance(payload.get("amount"), dict) else {}
        # §6.3 D3「以通道实收入账」⇒ 取用户**实付**（payer_total）；缺失时退订单金额（total）
        paid = amount.get("payer_total", amount.get("total"))
        if not out_trade_no or not transaction_id or paid is None:
            logger.error("微信支付回调缺少 out_trade_no/transaction_id/amount，已拒绝")
            return None

        paid_at = datetime.now(timezone.utc)
        raw_success_time = str(payload.get("success_time") or "").strip()
        if raw_success_time:
            try:
                paid_at = datetime.fromisoformat(raw_success_time)
            except ValueError:
                logger.warning("微信支付 success_time 无法解析：%s", raw_success_time)

        return ChannelCallback(
            channel=self.channel,
            order_id=out_trade_no,            # ⛔ 只带订单号，不带任何身份字段
            channel_trade_no=transaction_id,
            paid_amount_fen=int(paid),
            paid_at=paid_at,
            raw={"trade_state": payload.get("trade_state"),
                 "out_trade_no": out_trade_no, "transaction_id": transaction_id},
        )

    def callback_ack(self, ok: bool) -> tuple[str, str]:
        # 微信把**非** `{"code":"SUCCESS"}` 一律当失败并重推 ⇒ 成功态必须用它的字面格式
        if ok:
            return '{"code":"SUCCESS","message":"成功"}', "application/json"
        return '{"code":"FAIL","message":"处理失败"}', "application/json"
