# -*- coding: utf-8 -*-
"""口径 B · 支付宝 adapter（开放平台 · RSA2 · **电脑网站支付** `alipay.trade.page.pay`）。

> 2026-09-30 由当面付 `precreate` 切换为 page.pay：开放平台只开通了「电脑网站支付」
> 产品，调 precreate 报 `40004 ACQ.ACCESS_FORBIDDEN`；page.pay 实测直接 302 进收银台。
> page.pay 成功响应 = **302 + Location**（无 JSON 信封），下单取 Location 作 `pay_url`。

设计依据：设计稿 §2.2（接口）、§2.3（窄依赖）、§10 Q1/Q2（通道与主体 = ① 类，本题**已拍**：
通道 = 微信支付 ＋ 支付宝；收款主体 = 公司主体 ⇒ `requires_payee_entity=True`）。

⛔ **本模块永不 import `ledger`**，也永不写 `ledger_entries` / `payment_accounts`（§2.3）。
⛔ 凭据全部从配置读，**允许缺失**；缺失 ⇒ `ChannelNotConfiguredError`（HTTP 501）。

协议要点（可复算）：
  · 签名串 = **去掉 `sign`（`sign_type` 保留！见 `_sign_message`）后**按 key 升序的 `k=v` 用 `&` 连接（值为**解码后**的原文）
  · 签名算法 = RSA2（RSASSA-PKCS1-v1_5 + SHA-256），base64
  · 回调 = `application/x-www-form-urlencoded`；只有 `TRADE_SUCCESS` / `TRADE_FINISHED` 视作收款
  · 应答必须是纯文本 `success`（否则支付宝**重推**）
  · 金额 `total_amount` 是**元**字符串（如 `"0.50"`）⇒ 换算成分一律走 `Decimal`，⛔ 不碰 float
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional
from urllib.parse import parse_qsl, urlencode

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

CHANNEL = "alipay"
METHOD_PAGE_PAY = "alipay.trade.page.pay"
PRODUCT_CODE_PAGE_PAY = "FAST_INSTANT_TRADE_PAY"   # 电脑网站支付产品码
SIGN_TYPE = "RSA2"
SUCCESS_TRADE_STATES = ("TRADE_SUCCESS", "TRADE_FINISHED")
DEFAULT_SUBJECT = "叙阅批改充值"
# 回调时间戳容差（秒）：支付宝用 `notify_time`（"YYYY-MM-DD HH:MM:SS"，**北京时间**）防重放。
TS_TOLERANCE_SEC = 300
# ⚠️ 支付宝所有时间字段（`notify_time` / `gmt_payment` …）都是**北京时间（UTC+8）且不带时区标记**。
#    直接 `.replace(tzinfo=utc)` 会把它当 UTC ⇒ 与真实时刻差 8 小时 ⇒ **每一条真实回调都会被
#    「超出容差」判掉**（且入账时间会整体偏 8 小时）。必须先按 +08:00 定位再换算。
BEIJING_TZ = timezone(timedelta(hours=8))


def _cfg(name: str) -> str:
    return str(getattr(settings, name, "") or "").strip()


def _fen_to_yuan(amount_fen: int) -> str:
    """分 → 元字符串（两位小数）。⛔ 不用 float（0.1 + 0.2 那类误差在钱上是不可接受的）。"""
    value = (Decimal(int(amount_fen)) / Decimal(100)).quantize(Decimal("0.01"))
    return f"{value:.2f}"


def _yuan_to_fen(text: str) -> int:
    """元字符串 → 分。非法/负数 ⇒ 抛 `ValueError`（由调用方按不可信处理）。"""
    value = Decimal(str(text).strip())
    if value < 0:
        raise ValueError("金额为负")
    return int((value * 100).to_integral_value())


def _sign_message(params: Mapping[str, str]) -> str:
    """**请求**签名串（我方出站签名）：剔除 `sign` 与空值，按 key 升序 `k=v` 以 `&` 连接。

    ⚠️ `sign_type` **参与**请求签名（与微信 v3 不同，微信剔 sign_type）。
       实测网关报 isv.invalid-signature 并回显其验签串含 `sign_type=RSA2`
       —— 剔掉它必然验签失败。⛔ 别照微信的习惯再改回去。
    """
    items = [(str(k), str(v)) for k, v in params.items()
             if k != "sign" and str(v) != ""]
    items.sort(key=lambda kv: kv[0])
    return "&".join(f"{k}={v}" for k, v in items)


def _verify_candidates(params: Mapping[str, str]) -> list[str]:
    """**回调验签**候选签名串。

    出站请求与入站 notify 的签名串规则不完全一致（官方文档/各 SDK 口径有出入：
    有的剔 `sign_type`、有的留；空值参数有的剔、有的留），2026-09-30 生产真实
    notify 按「留 sign_type」单一规则验签失败 ⇒ 改为按 4 种合法拼法依次尝试。

    ⚠️ 安全性不变：每个候选都要求**支付宝私钥签出的真实 RSA2 签名**才可能通过，
       这里只是放宽「规范串拼法」的容错，⛔ 不是放宽信任（伪造者没有私钥，一种都过不了）。
    """
    variants: list[list[tuple[str, str]]] = [
        [(k, v) for k, v in params.items() if k != "sign" and str(v) != ""],
        [(k, v) for k, v in params.items()
         if k not in ("sign", "sign_type") and str(v) != ""],
        [(k, v) for k, v in params.items() if k != "sign"],
        [(k, v) for k, v in params.items() if k not in ("sign", "sign_type")],
    ]
    out: list[str] = []
    for items in variants:
        items = sorted(((str(k), str(v)) for k, v in items), key=lambda kv: kv[0])
        msg = "&".join(f"{k}={v}" for k, v in items)
        if msg not in out:
            out.append(msg)
    return out


def _http_post_form(url: str, *, params: Mapping[str, str],
                    timeout: float = 15.0,
                    allow_redirects: bool = True) -> tuple[int, str, Mapping[str, str]]:
    """HTTP 传输层（**唯一**的 I/O 接缝；测试可替换它，从而在无凭据环境下也能验签参数）。

    返回 `(status_code, body_text, headers)`。
    page.pay 必须传 `allow_redirects=False`——成功是 302 + Location，跟随跳转会
    把收银台 HTML 当「下单响应」，丢掉 Location 就拿不到 `pay_url`。
    """
    import requests  # 局部 import：让本模块在无网络依赖的场景（如纯单测）也能被导入

    resp = requests.post(url, data=dict(params), timeout=timeout,
                         allow_redirects=allow_redirects)
    return resp.status_code, str(resp.text or ""), dict(resp.headers or {})


class AlipayChannelAdapter(PaymentChannelAdapter):
    channel = CHANNEL

    def capabilities(self) -> ChannelCapabilities:
        return {
            "channel": self.channel,
            "supports_callback": True,
            # 同微信：退款口径已拍「余额不可退；套餐未使用部分可退（待套餐上线后实现，
            # 见 §10 Q5 / §5.2）」⇒ 套餐后置、可退对象不存在 ⇒ 本批不做 P2-4，如实声明 False。
            "supports_refund": False,
            "requires_payee_entity": True,   # 已拍：收款主体 = 公司主体
            "fee_rate_bps": None,            # §10 Q1：手续费谁承担未拍 ⇒ None（⛔ 不猜）
        }

    # ────────────────────────── 配置检查（缺失 ⇒ 501，⛔ 不静默）──────────────────────────

    def _pay_config(self) -> dict[str, Any]:
        missing = []
        app_id = _cfg("PAYMENT_ALIPAY_APP_ID")
        private_key = _cfg("PAYMENT_ALIPAY_PRIVATE_KEY")
        for name, value in (("PAYMENT_ALIPAY_APP_ID", app_id),
                            ("PAYMENT_ALIPAY_PRIVATE_KEY", private_key)):
            if not value:
                missing.append(name)
        if missing:
            raise ChannelNotConfiguredError(
                "支付宝通道未配置：缺少 " + "、".join(missing)
                + "（收款主体资质尚未申请，本状态为预期；配置齐全后自动生效）"
            )
        pem = crypto.load_pem(private_key, what="支付宝应用私钥")
        crypto.load_private_key(pem)
        return {"app_id": app_id, "private_pem": pem}

    def _callback_config(self) -> dict[str, Any]:
        missing = []
        app_id = _cfg("PAYMENT_ALIPAY_APP_ID")
        public_key = _cfg("PAYMENT_ALIPAY_PUBLIC_KEY")
        for name, value in (("PAYMENT_ALIPAY_APP_ID", app_id),
                            ("PAYMENT_ALIPAY_PUBLIC_KEY", public_key)):
            if not value:
                missing.append(name)
        if missing:
            raise ChannelNotConfiguredError(
                "支付宝通道未配置（无法验签回调）：缺少 " + "、".join(missing)
            )
        pub_pem = crypto.load_pem(public_key, what="支付宝公钥")
        crypto.load_public_key(pub_pem)  # PEM 非法 ⇒ 503，不是把它归约成「验签失败」
        return {"app_id": app_id, "public_pem": pub_pem}

    # ────────────────────────── 下单 ──────────────────────────

    def create_payment(self, order: Any) -> ChannelIntent:
        cfg = self._pay_config()
        biz = {
            "out_trade_no": str(order.id),          # 我方订单号 = 通道的 out_trade_no
            "total_amount": _fen_to_yuan(int(order.amount_fen)),
            "subject": DEFAULT_SUBJECT,
            "product_code": PRODUCT_CODE_PAGE_PAY,  # 电脑网站支付必填
        }
        params: dict[str, str] = {
            "app_id": cfg["app_id"],
            "method": METHOD_PAGE_PAY,
            "format": "JSON",
            "charset": "utf-8",
            "sign_type": SIGN_TYPE,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "biz_content": json.dumps(biz, separators=(",", ":"), ensure_ascii=False),
        }
        base = _cfg("PAYMENT_CALLBACK_BASE_URL").rstrip("/")
        if base:
            params["notify_url"] = f"{base}/api/v1/payment/callback/{CHANNEL}"
        params["sign"] = crypto.rsa_sign_sha256(
            cfg["private_pem"], _sign_message(params).encode("utf-8")
        )

        # charset 必须放 URL 查询串：biz_content 里有中文（subject=「叙阅批改充值」）时，
        # 网关若不知 charset 会按错误编码重建验签串 ⇒ isv.invalid-signature。
        # 实测（2026-09-30 生产）：ascii 参数两种都过，中文参数只有 charset 在查询串才过。
        url = _cfg("PAYMENT_ALIPAY_GATEWAY")
        sep = "&" if "?" in url else "?"
        status, body_text, headers = _http_post_form(
            f"{url}{sep}charset=utf-8", params=params, allow_redirects=False
        )

        # ── 成功形态：302 + Location（收银台跳转链首跳），无 JSON 信封、无 sign ──
        location = str(headers.get("Location") or headers.get("location") or "").strip()
        if status in (301, 302) and location:
            return ChannelIntent(
                channel=self.channel,
                out_trade_no=str(order.id),
                pay_params={"pay_url": location, "out_trade_no": str(order.id)},
            )

        # ── 其余都是失败：page.pay 成功必 302，200 = 错误 JSON（尽力解析可读报错）──
        if status != 200:
            raise ChannelError(f"支付宝下单失败：HTTP {status} body={body_text[:300]}")
        ok_key = f"{METHOD_PAGE_PAY.replace('.', '_')}_response"
        last: ChannelError | None = None
        for key in (ok_key, "error_response"):
            try:
                node = self._extract_node(body_text, key)
            except ChannelError as exc:
                last = exc
                continue
            self._verify_response(node["raw"], body_text, cfg)
            obj = node["obj"]
            if str(obj.get("code") or "") == "10000":
                # 200 + 10000 却没给出 302：响应形态与预期不符，不静默吞单
                raise ChannelError(f"支付宝下单响应异常（200 成功但无跳转）：{body_text[:300]}")
            raise ChannelError(
                "支付宝下单失败：code=%s msg=%s sub_msg=%s"
                % (obj.get("code"), obj.get("msg"), obj.get("sub_msg"))
            )
        raise ChannelError(
            f"支付宝下单失败：HTTP 200 无法解析响应（{last}）：{body_text[:300]}"
        )

    @staticmethod
    def _extract_node(body_text: str, node_key: str) -> dict[str, Any]:
        """取出响应里 `<node_key>` 节点的**原始文本**与其解析结果。

        ⚠️ 必须取**原始文本**：支付宝的响应签名是对该节点**原样字节**签的，
           重新 `json.dumps` 会因空白/键序不同而必然验签失败。
        """
        key = f'"{node_key}"'
        i = body_text.find(key)
        if i < 0:
            raise ChannelError(f"支付宝响应缺少节点 {node_key}：{body_text[:300]}")
        j = body_text.index(":", i + len(key))
        tail = body_text[j + 1:].lstrip()
        try:
            obj, end = json.JSONDecoder().raw_decode(tail)
        except ValueError as exc:
            raise ChannelError(f"支付宝响应节点 {node_key} 不是合法 JSON：{exc}") from exc
        return {"obj": obj if isinstance(obj, dict) else {}, "raw": tail[:end]}

    def _verify_response(self, node_raw: str, body_text: str, cfg: dict[str, Any]) -> None:
        """校验支付宝**响应**签名（用支付宝公钥）。"""
        try:
            envelope = json.loads(body_text)
            sign = str(envelope.get("sign") or "")
        except Exception:
            sign = ""
        if not sign:
            logger.warning("支付宝响应无 sign 字段，跳过响应验签（下单仍以业务码判定）")
            return
        pub = _cfg("PAYMENT_ALIPAY_PUBLIC_KEY")
        if not pub:
            return
        if not crypto.rsa_verify_sha256(
            crypto.load_pem(pub, what="支付宝公钥"), node_raw.encode("utf-8"), sign
        ):
            raise ChannelError("支付宝下单响应验签失败（响应可能被篡改）")

    # ────────────────────────── 回调 ──────────────────────────

    def parse_callback(self, raw_body: bytes, headers: Mapping[str, str]) -> Optional[ChannelCallback]:
        cfg = self._callback_config()  # 未配置 / PEM 非法 ⇒ raise（501 / 503）
        try:
            return self._parse_verified(cfg, raw_body)
        except ChannelError:
            raise
        except Exception:
            logger.warning("支付宝回调解析失败，按验签失败处理（不入账）", exc_info=True)
            return None

    def _parse_verified(self, cfg: dict[str, Any], raw_body: bytes) -> Optional[ChannelCallback]:
        try:
            body_text = raw_body.decode("utf-8")
        except UnicodeDecodeError:
            return None
        # keep_blank_values：`sign` 之外的字段若为空也参与不了签名串（_sign_message 剔空值）
        pairs = parse_qsl(body_text, keep_blank_values=True)
        params = {str(k): str(v) for k, v in pairs}
        sign = str(params.get("sign") or "")
        if not sign:
            logger.warning("支付宝回调缺少 sign 字段，已拒绝")
            return None
        if str(params.get("sign_type") or SIGN_TYPE).upper() != SIGN_TYPE:
            logger.warning("支付宝回调 sign_type 非 RSA2：%s", params.get("sign_type"))
            return None
        # 4 种规范拼法 × 2 种签名形态（表单解码可能把 base64 的 `+` 还原成空格）
        sign_forms = [sign]
        if " " in sign:
            sign_forms.append(sign.replace(" ", "+"))
        verified = False
        for msg in _verify_candidates(params):
            for sg in sign_forms:
                if crypto.rsa_verify_sha256(cfg["public_pem"], msg.encode("utf-8"), sg):
                    verified = True
                    break
            if verified:
                break
        if not verified:
            logger.warning("支付宝回调验签失败（已拒绝，未入账）")
            return None

        # 重放防护：notify_time 新鲜度（支付宝给的是**北京时间**，见 BEIJING_TZ 注释）
        notify_time = str(params.get("notify_time") or "").strip()
        if notify_time:
            try:
                seen = datetime.strptime(notify_time, "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=BEIJING_TZ
                )
                skew = abs(time.time() - seen.timestamp())
                if skew > TS_TOLERANCE_SEC:
                    logger.warning("支付宝回调 notify_time 超出容差（%ss），已拒绝", int(skew))
                    return None
            except ValueError:
                logger.warning("支付宝回调 notify_time 无法解析：%s（已拒绝）", notify_time)
                return None

        # 纵深防御：app_id 不符 ⇒ 不是发给我们的
        got_app_id = str(params.get("app_id") or "")
        if cfg["app_id"] and got_app_id and got_app_id != cfg["app_id"]:
            logger.error("支付宝回调 app_id 不符：期望 %s 实得 %s（已拒绝）", cfg["app_id"], got_app_id)
            return None

        trade_status = str(params.get("trade_status") or "")
        if trade_status not in SUCCESS_TRADE_STATES:
            logger.info("支付宝回调 trade_status 非成功态：%s", trade_status)
            return None

        out_trade_no = str(params.get("out_trade_no") or "").strip()
        trade_no = str(params.get("trade_no") or "").strip()
        total_amount = str(params.get("total_amount") or "").strip()
        if not out_trade_no or not trade_no or not total_amount:
            logger.error("支付宝回调缺少 out_trade_no/trade_no/total_amount，已拒绝")
            return None
        try:
            paid_fen = _yuan_to_fen(total_amount)
        except (InvalidOperation, ValueError):
            logger.error("支付宝回调 total_amount 非法：%s（已拒绝）", total_amount)
            return None

        paid_at = datetime.now(timezone.utc)
        gmt_payment = str(params.get("gmt_payment") or "").strip()
        if gmt_payment:
            try:
                # 支付宝时间戳是北京时间（UTC+8）⇒ 先按 +08:00 定位，再统一转 UTC 存
                paid_at = datetime.strptime(gmt_payment, "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=BEIJING_TZ
                ).astimezone(timezone.utc)
            except ValueError:
                logger.warning("支付宝 gmt_payment 无法解析：%s", gmt_payment)

        return ChannelCallback(
            channel=self.channel,
            order_id=out_trade_no,            # ⛔ 只带订单号，不带任何身份字段
            channel_trade_no=trade_no,
            paid_amount_fen=paid_fen,
            paid_at=paid_at,
            raw={"trade_status": trade_status, "out_trade_no": out_trade_no, "trade_no": trade_no},
        )

    def callback_ack(self, ok: bool) -> tuple[str, str]:
        # 支付宝只认纯文本 `success`；其余（含 HTTP 非 200）一律按失败**重推**。
        if ok:
            return "success", "text/plain; charset=utf-8"
        return "failure", "text/plain; charset=utf-8"
