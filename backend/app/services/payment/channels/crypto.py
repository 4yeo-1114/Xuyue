# -*- coding: utf-8 -*-
"""口径 B · 通道密码学原语（RSA2 签名/验签 + AES-256-GCM 解密）。

微信支付 APIv3 与支付宝开放平台用的**都是** RSASSA-PKCS1-v1_5 + SHA-256（支付宝叫 RSA2），
差别只在**被签的字符串怎么拼**（微信是 `timestamp\nnonce\nbody\n`，支付宝是排序后的
`k=v&k=v`）。⇒ 拼串逻辑留在各自 adapter，本模块只放**与协议无关**的原语，⛔ 不重复实现两份 RSA。

⚠️ 依赖声明：本模块需要 `cryptography`（已进 `backend/requirements.txt`）。
   ⛔ 不手写 AES / PKCS#1 —— 手搓密码学的失败模式是「静默验签通过」，这是本系统最不能出的事。
   依赖缺失时抛 `ChannelCryptoUnavailableError`（503，服务端缺件），
   ⛔ **不**降级成「跳过验签」（那等于给伪造回调开门）。
"""
from __future__ import annotations

import base64
import logging
from typing import Optional

from app.services.payment.channels.base import ChannelCryptoUnavailableError

logger = logging.getLogger(__name__)

try:  # pragma: no cover - 由「依赖缺失」这条分支覆盖，CI 上恒为已安装
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    _CRYPTO_OK = True
except Exception:  # pragma: no cover
    _CRYPTO_OK = False
    InvalidSignature = Exception  # type: ignore[assignment,misc]


def crypto_available() -> bool:
    return _CRYPTO_OK


def _require_crypto() -> None:
    if not _CRYPTO_OK:
        raise ChannelCryptoUnavailableError(
            "服务端缺少密码学依赖 cryptography，无法验签/解密 —— 已拒绝本次请求"
            "（⛔ 不会降级为跳过验签）"
        )


# ────────────────────────── PEM 装载 ──────────────────────────

def load_pem(value: str, *, what: str) -> bytes:
    """把配置里的 PEM 值读成 bytes。支持「PEM 全文」与「`@路径`」两种写法。

    ⛔ 内容为空 ⇒ 抛 `ChannelCryptoUnavailableError`（调用方应在此之前就按「未配置」拦掉）。
    """
    raw = str(value or "").strip()
    if not raw:
        raise ChannelCryptoUnavailableError(f"{what} 未配置")
    if raw.startswith("@"):
        path = raw[1:].strip()
        try:
            with open(path, "rb") as f:
                return f.read()
        except OSError as exc:
            raise ChannelCryptoUnavailableError(f"{what} 读取失败：{path}（{exc}）") from exc
    return raw.encode("utf-8")


def load_private_key(pem: bytes):
    """装载 RSA 私钥（PKCS#8 / PKCS#1 PEM 均支持 —— 微信与支付宝发的都是 PKCS#8）。"""
    _require_crypto()
    try:
        key = serialization.load_pem_private_key(pem, password=None)
    except Exception as exc:
        raise ChannelCryptoUnavailableError(f"私钥无法解析（PEM 格式错误）：{exc}") from exc
    if not hasattr(key, "sign"):
        raise ChannelCryptoUnavailableError("配置的私钥不是 RSA 私钥（通道要求 RSA）")
    return key


def load_public_key(pem: bytes):
    """装载 RSA 公钥（SPKI PEM，即通道下发的「公钥」文件）。"""
    _require_crypto()
    try:
        key = serialization.load_pem_public_key(pem)
    except Exception as exc:
        raise ChannelCryptoUnavailableError(f"公钥无法解析（PEM 格式错误）：{exc}") from exc
    if not hasattr(key, "verify"):
        raise ChannelCryptoUnavailableError("配置的公钥不是 RSA 公钥（通道要求 RSA）")
    return key


# ────────────────────────── 签名 / 验签（RSASSA-PKCS1-v1_5 + SHA-256）──────────────────────────

def rsa_sign_sha256(private_key_pem: bytes, message: bytes) -> str:
    """签名并 base64 编码（微信的 `signature`、支付宝的 `sign` 都是 base64）。"""
    key = load_private_key(private_key_pem)
    sig = key.sign(message, padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode("ascii")


def rsa_verify_sha256(public_key_pem: bytes, message: bytes, signature_b64: str) -> bool:
    """验签。**任何异常一律返回 False**（⛔ 不抛给调用方）—— 调用方只需判真/假。"""
    if not str(signature_b64 or "").strip():
        return False
    try:
        pub = load_public_key(public_key_pem)
        sig = base64.b64decode(str(signature_b64).strip(), validate=True)
    except Exception:
        return False
    try:
        pub.verify(sig, message, padding.PKCS1v15(), hashes.SHA256())
        return True
    except InvalidSignature:
        return False
    except Exception:
        return False


# ────────────────────────── AES-256-GCM（微信回调 resource 解密）──────────────────────────

def aes256_gcm_decrypt(*, key: bytes, nonce: bytes, ciphertext: bytes,
                       associated_data: Optional[bytes] = None) -> bytes:
    """AES-256-GCM 解密。密钥/密文/认证数据任一不符 ⇒ **抛原异常**（⛔ 不返回半截明文）。

    ⚠️ 解密失败（`InvalidTag`）**不**包装成 `ChannelCryptoUnavailableError`：
       它多半意味着「密文/密钥不对」= 回调不可信 ⇒ 调用方按**验签失败（400）**处理；
       包装成 503 会把「有人在伪造」误诊成「服务端缺件」。
       ⛔ 但**依赖缺失**仍然走 503（下面 `_require_crypto` 抛的就是它）。
    """
    _require_crypto()
    return AESGCM(key).decrypt(nonce, ciphertext, associated_data or b"")
