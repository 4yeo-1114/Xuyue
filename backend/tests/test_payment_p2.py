# -*- coding: utf-8 -*-
"""独立老师支付系统 Phase 2（P2-1 下单 / P2-2 通道适配层 / P2-3 回调入账）· 仓内回归测试。

判据逐条取自 docs/payment/payment-design.md §2.2/§2.3/§3.5/§6.3/§7.3/§9-Phase2 表。

覆盖与「每条判据必须有自己的红」的对应关系（**这是本文件的结构主轴**）：
  P2-1 下单        : 401（真 JWT）/ `?user_id=` 被忽略 / 凭据缺失 ⇒ **501 且零新增行** /
                     unset ⇒ 501 / 未知通道 ⇒ 404 / 假通道 happy path / 主体缺失只留空 + 记日志
  P2-2 通道适配层  : 注册表与 capabilities / **源码级钉住「通道层不碰账本」**(§2.3) /
                     unset 明确报错 / 退款与查单如实声明未实现（P2-4：**可退对象不存在**
                       —— 已拍「余额不可退；套餐未使用部分可退（待套餐上线后实现）」，
                       而套餐后置 ⇒ 无对象可退；⛔ 不是「退款被禁」，见 §10 Q5 / §5.2）
  P2-3 回调        : 闭环（下单→回调→apply_payment_confirmed→余额+流水）/
                     重复投递只落 1 条（I1）＋**两条独立的红**：
                       (a) 把幂等键换成非确定版本 ⇒ 同一断言立刻变红（应用层判据的承重墙）
                       (b) 摘掉 `uk_ledger_idempotency` 唯一索引 ⇒ 裸重放插得进去（DB 判据的承重墙）
                     伪造签名 ⇒ 400 且**未入账**（假通道 + 微信/支付宝**两个真实 adapter**，
                       且用**自签测试密钥对**走真 RSA / 真 AES-256-GCM，⛔ 不 mock 掉验签）/
                     回调不带 JWT 也认（身份只来自验签）/ 订单不存在 404 / 已退款 409 /
                     金额不符按实收入账并留 error 痕（§6.3 D3）/ 请求体里的 user_id 不被采信
  AUTO_DDL=false   : 旧库自愈（照 `_ensure_payment_tables` 挂无条件段的口径）

测试方式：**真 SQLite 内存库**（真执行 SQL ⇒ 唯一索引/行锁语句真实生效，⛔ 不用假 db）
        ＋ 真实 FastAPI TestClient。⛔ 不 mock 掉任何断言对象。

⚠️ 必须在 import 任何 `app.*` 之前 `AUTO_DDL=false`（本机 backend/.env 里是 AUTO_DDL=true，
   import 期就会去连库 ⇒ collection 挂）。照 `test_payment_p0.py` 与既有两个文件的约定，
   ⛔ 不依赖 conftest。
"""
import os

os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "13307")
os.environ.setdefault("DB_USER", "root")
os.environ.setdefault("DB_PASSWORD", "root_pw_2026")
os.environ.setdefault("DB_NAME", "grade_payment_p2_test")
os.environ.setdefault("JWT_SECRET_KEY", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("AUTO_DDL", "false")
os.environ.setdefault("DASHSCOPE_API_KEY", "sk-p2-test-not-real")

import ast  # noqa: E402
import base64  # noqa: E402
import hashlib  # noqa: E402
import hmac  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import pathlib  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.database as database  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.models.ledger_entry import LedgerEntry  # noqa: E402
from app.models.payment_account import PaymentAccount  # noqa: E402
from app.models.payment_order import PaymentOrder  # noqa: E402
from app.routers import payment as payment_router  # noqa: E402
from app.services.payment import channels  # noqa: E402
from app.services.payment import ledger as L  # noqa: E402
from app.services.payment import pricing as P  # noqa: E402
from app.services.payment.channels import (  # noqa: E402
    CallbackVerificationError,
    ChannelCallback,
    ChannelIntent,
    ChannelNotConfiguredError,
    PaymentChannelAdapter,
)
from app.utils.security import create_access_token  # noqa: E402

TEACHER = "u-p2-teacher"
OTHER = "u-p2-other"
UNIT = P.unit_price_fen("grade")
BEIJING = timezone(timedelta(hours=8))


# ═══════════════════════════ 夹具 ═══════════════════════════

@pytest.fixture()
def sqlite_env(monkeypatch):
    """真 SQLite 内存库（StaticPool ⇒ 多会话共享同一连接，唯一索引真实生效）。

    ⚠️ **必须打开 `PRAGMA foreign_keys=ON`**：SQLite 默认**不校验外键**，而真 MySQL 上
       `payment_accounts.user_id` 是指向 `users.id` 的真外键（ON DELETE CASCADE）。
       关着外键做测试 = 用假约束验真语义（本批在真库上就被这条绊过一次）⇒ 显式打开，
       并给测试用户建真 `users` 行。
    """
    from sqlalchemy import event

    from app.models.user import User

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _rec):  # pragma: no cover - 由 SQLite 回调触发
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(database, "SessionLocal", TestSession)
    db = TestSession()
    for uid in (TEACHER, OTHER):
        db.add(User(id=uid, email=uid + "@p2.test", display_name=uid,
                    password_hash="x", roles="任课教师"))
    db.commit()
    try:
        yield TestSession, db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture()
def p2_app(sqlite_env):
    """只挂 payment 路由的裸 FastAPI。

    ⚠️ **只**覆盖 `get_db`，⛔ **不**覆盖 `get_current_user_id` —— 下单的「收款对象 = JWT 身份」
       这条判据必须走**真 JWT 解析**才算验到（覆盖掉它等于自证）。
    """
    TestSession, _db = sqlite_env
    app = FastAPI()
    app.include_router(payment_router.router, prefix="/api/v1")

    def _override_db():
        d = TestSession()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = _override_db
    return app, TestClient(app), TestSession


def _auth(user_id: str) -> dict:
    """真 JWT（走 `app.utils.security.create_access_token`，与生产同一条路）。"""
    return {"Authorization": "Bearer " + create_access_token(user_id)}


class FakeChannelAdapter(PaymentChannelAdapter):
    """测试替身：「假 adapter」，但**验签是真的**（HMAC-SHA256），⛔ 不是「永远返回成功」。"""

    channel = "fake"

    def __init__(self):
        self.secret = b"fake-channel-secret-0123456789"
        self.configured = True
        self.create_calls = 0

    def capabilities(self):
        return {
            "channel": self.channel,
            "supports_callback": True,
            "supports_refund": False,
            "requires_payee_entity": True,
            "fee_rate_bps": None,
        }

    def create_payment(self, order):
        self.create_calls += 1
        if not self.configured:
            raise ChannelNotConfiguredError("fake 通道未配置")
        return ChannelIntent(
            channel=self.channel,
            out_trade_no=str(order.id),
            pay_params={"qr_code": "fake://pay/" + str(order.id)},
        )

    def sign(self, body: bytes) -> str:
        return hmac.new(self.secret, body, hashlib.sha256).hexdigest()

    def parse_callback(self, raw_body, headers):
        if not self.configured:
            raise ChannelNotConfiguredError("fake 通道未配置（无法验签回调）")
        h = {str(k).lower(): v for k, v in (headers or {}).items()}
        got = str(h.get("x-fake-signature") or "")
        if not got or not hmac.compare_digest(got, self.sign(raw_body)):
            return None
        payload = json.loads(raw_body.decode("utf-8"))
        return ChannelCallback(
            channel=self.channel,
            order_id=str(payload["out_trade_no"]),
            channel_trade_no=str(payload.get("channel_trade_no") or ""),
            paid_amount_fen=int(payload["paid_amount_fen"]),
            paid_at=datetime.now(timezone.utc),
            raw=payload,
        )

    def callback_ack(self, ok):
        if ok:
            return '{"code":0,"message":"ok","data":null}', "application/json"
        return '{"code":1,"message":"fake rejected","data":null}', "application/json"


@pytest.fixture()
def fake_channel(monkeypatch):
    """把假 adapter 注册进通道表。

    ⚠️ 用 `monkeypatch.setitem` 而非公开的 `channels.register()`：前者的撤销是**自动**的，
       注册表在用例结束后必然回到干净态（`register()` 会留下一个跨用例的常驻 "fake" 通道）。
    """
    adapter = FakeChannelAdapter()
    monkeypatch.setitem(channels._ADAPTERS, adapter.channel, adapter)
    return adapter


def _fake_callback(adapter: FakeChannelAdapter, order_id: str, paid_fen: int,
                   trade_no: str = "fake-trade-1", decoy_user_id: str = OTHER):
    """构造一份**签名有效**的假通道回调（含诱饵 user_id，用来验「不采信 body 身份」）。"""
    body = json.dumps(
        {
            "out_trade_no": order_id,
            "channel_trade_no": trade_no,
            "paid_amount_fen": paid_fen,
            # ⚠️ 诱饵：伪造回调里塞的 user_id。收款对象必须由**订单号反查**得出，
            #    若哪天实现改成读这个字段，本断言立刻判红。
            "user_id": decoy_user_id,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    return body, {"X-Fake-Signature": adapter.sign(body), "Content-Type": "application/json"}


def _post_callback(client, channel: str, body: bytes, headers: dict, auth: bool = False):
    h = dict(headers)
    if auth:
        h.update(_auth(TEACHER))
    return client.post(f"/api/v1/payment/callback/{channel}", content=body, headers=h)


def _count(db, model):
    return int(db.query(model).count())


# ── 自签测试密钥对（⛔ 不是真实商户凭据；只在测试进程内存在，用完即弃）──

@pytest.fixture(scope="module")
def rsa_keys():
    """模块级生成两对 RSA 密钥：`platform` = 通道方（用来签名），`attacker` = 伪造者。"""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    def _gen():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        priv = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode("utf-8")
        pub = key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        return priv, pub

    p_priv, p_pub = _gen()
    a_priv, a_pub = _gen()
    return {"platform_priv": p_priv, "platform_pub": p_pub,
            "attacker_priv": a_priv, "attacker_pub": a_pub}


def _rsa_sign(priv_pem: str, message: bytes) -> str:
    """独立复算签名（⛔ 不 import adapter 的私有 helper —— 那样两边一起错也测不出来）。"""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    key = serialization.load_pem_private_key(priv_pem.encode("utf-8"), password=None)
    return base64.b64encode(key.sign(message, padding.PKCS1v15(), hashes.SHA256())).decode("ascii")


WECHAT_CFG = {
    "PAYMENT_WECHAT_APP_ID": "wx-test-appid",
    "PAYMENT_WECHAT_MCH_ID": "1900000001",
    "PAYMENT_WECHAT_API_V3_KEY": "0123456789abcdef0123456789abcdef",  # 恰 32 字节
}


def _wechat_callback(priv_pem: str, *, order_id: str, trade_no: str, paid_fen: int,
                     api_v3_key: str = None, total_fen: int = None,
                     event_type: str = "TRANSACTION.SUCCESS", skew: int = 0,
                     key_override: bytes = None, nonce_override: bytes = None):
    """构造一份**微信 APIv3 格式**的回调（真 AES-256-GCM 加密 + 真 RSA 签名）。

    `key_override` = 用另一把 AES 密钥加密（密文合法、但解不开）⇒ 验签过而解密失败。
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = (api_v3_key or WECHAT_CFG["PAYMENT_WECHAT_API_V3_KEY"]).encode("utf-8")
    encrypt_key = key_override or key
    payload = {
        "mchid": WECHAT_CFG["PAYMENT_WECHAT_MCH_ID"],
        "appid": WECHAT_CFG["PAYMENT_WECHAT_APP_ID"],
        "out_trade_no": order_id,
        "transaction_id": trade_no,
        "trade_state": "SUCCESS",
        "amount": {"total": int(total_fen if total_fen is not None else paid_fen),
                   "payer_total": int(paid_fen)},
        "success_time": datetime.now(BEIJING).strftime("%Y-%m-%dT%H:%M:%S+08:00"),
    }
    nonce = nonce_override if nonce_override is not None else b"0123456789ab"
    aad = b"transaction"
    ct = AESGCM(encrypt_key).encrypt(nonce, json.dumps(payload).encode("utf-8"), aad)
    envelope = {
        "id": "evt-" + uuid.uuid4().hex,
        "create_time": datetime.now(BEIJING).strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "event_type": event_type,
        "resource_type": "encrypt-resource",
        "resource": {
            "algorithm": "AEAD_AES_256_GCM",
            "ciphertext": base64.b64encode(ct).decode("ascii"),
            "nonce": nonce.decode("utf-8"),
            "associated_data": aad.decode("utf-8"),
        },
    }
    body = json.dumps(envelope, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ts = str(int(time.time()) + skew)
    hnonce = "hdr-" + uuid.uuid4().hex[:16]
    # 微信签名串 = `timestamp\nnonce\nbody\n`（⛔ 不 import adapter 的拼串，独立复算）
    message = "{}\n{}\n{}\n".format(ts, hnonce, body.decode("utf-8")).encode("utf-8")
    return body, {
        "Wechatpay-Timestamp": ts,
        "Wechatpay-Nonce": hnonce,
        "Wechatpay-Signature": _rsa_sign(priv_pem, message),
        "Wechatpay-Serial": "TEST-SERIAL-0001",
        "Content-Type": "application/json",
    }


def _alipay_callback(priv_pem: str, *, order_id: str, trade_no: str, amount_yuan: str,
                     app_id: str, trade_status: str = "TRADE_SUCCESS", skew_sec: int = 0):
    """构造一份**支付宝格式**的回调（真 RSA2 签名，`application/x-www-form-urlencoded`）。"""
    now = datetime.now(BEIJING) + timedelta(seconds=skew_sec)
    params = {
        "app_id": app_id,
        "charset": "utf-8",
        "gmt_payment": now.strftime("%Y-%m-%d %H:%M:%S"),
        "notify_id": "nid-" + uuid.uuid4().hex,
        "notify_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "out_trade_no": order_id,
        "sign_type": "RSA2",
        "total_amount": amount_yuan,
        "trade_no": trade_no,
        "trade_status": trade_status,
    }
    # 支付宝签名串：剔除 sign/sign_type 与空值，按 key 升序 `k=v` 以 `&` 连接（独立复算）
    items = sorted((k, v) for k, v in params.items()
                   if k not in ("sign", "sign_type") and v != "")
    message = "&".join("{}={}".format(k, v) for k, v in items).encode("utf-8")
    params["sign"] = _rsa_sign(priv_pem, message)
    from urllib.parse import urlencode

    body = urlencode(params).encode("utf-8")
    return body, {"Content-Type": "application/x-www-form-urlencoded"}


@pytest.fixture()
def wechat_cfg(monkeypatch, rsa_keys):
    """把微信通道配成「测试密钥对 + 测试 APIv3 密钥」，并返回配置字典。"""
    for k, v in WECHAT_CFG.items():
        monkeypatch.setattr(settings, k, v)
    monkeypatch.setattr(settings, "PAYMENT_WECHAT_PUBLIC_KEY", rsa_keys["platform_pub"])
    monkeypatch.setattr(settings, "PAYMENT_WECHAT_PRIVATE_KEY", rsa_keys["platform_priv"])
    monkeypatch.setattr(settings, "PAYMENT_WECHAT_CERT_SERIAL_NO", "TEST-SERIAL-0001")
    return dict(WECHAT_CFG)


@pytest.fixture()
def alipay_cfg(monkeypatch, rsa_keys):
    monkeypatch.setattr(settings, "PAYMENT_ALIPAY_APP_ID", "2021000000000000")
    monkeypatch.setattr(settings, "PAYMENT_ALIPAY_PUBLIC_KEY", rsa_keys["platform_pub"])
    monkeypatch.setattr(settings, "PAYMENT_ALIPAY_PRIVATE_KEY", rsa_keys["platform_priv"])
    return {"app_id": "2021000000000000"}


# ═══════════════════════════ P2-2 通道适配层 ═══════════════════════════

def test_p2_2_registry_lists_exactly_three_channels():
    """注册表 = 已拍的两个真实通道 + `unset` 占位（⛔ 不多不少）。"""
    assert channels.registered_channels() == ("alipay", "unset", "wechat_pay")
    assert channels.CHANNEL_WECHAT == "wechat_pay"
    assert channels.CHANNEL_ALIPAY == "alipay"


def test_p2_2_unknown_channel_does_not_fall_back_to_unset():
    """未知通道 ⇒ 404，⛔ **不回落 unset**（回落会把「打错通道名」伪装成「未配置」）。"""
    with pytest.raises(channels.UnknownChannelError) as exc:
        channels.get_adapter("paypal")
    assert exc.value.http_status == 404
    with pytest.raises(channels.UnknownChannelError):
        channels.get_adapter("")


def test_p2_2_real_channels_require_payee_entity():
    """已拍口径：收款主体 = 公司主体 ⇒ 两个**真实**通道都 `requires_payee_entity=True`。

    ⛔ 若把这条改成 False（或改成由订单字段决定），本用例判红。
    """
    for name in ("wechat_pay", "alipay"):
        caps = channels.get_adapter(name).capabilities()
        assert caps["channel"] == name
        assert caps["requires_payee_entity"] is True, name
        assert caps["supports_callback"] is True, name
        # 退款口径已拍「余额不可退；套餐未使用部分可退（套餐未上线 ⇒ 可退对象不存在）」
        # ⇒ 本批不做 P2-4、如实声明 False（能力声明反映**我方是否真的支持**）
        assert caps["supports_refund"] is False, name
        # §10 Q1 手续费谁承担未拍 ⇒ None（⛔ 不猜一个数填上）
        assert caps["fee_rate_bps"] is None, name


def test_p2_2_unset_channel_is_explicit_not_silent():
    """`UnsetChannelAdapter`：下单**明确报错** 501，回调恒 None（⇒ 调用方不得入账）。"""
    a = channels.get_adapter("unset")
    caps = a.capabilities()
    assert caps["supports_callback"] is False
    assert caps["requires_payee_entity"] is False
    with pytest.raises(ChannelNotConfiguredError) as exc:
        a.create_payment(object())
    assert exc.value.http_status == 501
    assert "尚未配置" in str(exc.value)
    assert a.parse_callback(b"{}", {}) is None


def test_p2_2_refund_and_query_declare_not_implemented():
    """P2-4 未做、查单未做 ⇒ 抛 `NotImplementedError` 而非**静默假装成功**。

    ⚠️ 理由必须是「**可退对象不存在**」（余额不可退 + 套餐未上线），⛔ 措辞不许写成
    「退款被禁」—— 两者口径不同（主导者 2026-09-24 修正）。故连错误消息一起钉住。
    """
    from app.services.payment.channels import RefundRequest

    for name in ("unset", "wechat_pay", "alipay"):
        a = channels.get_adapter(name)
        with pytest.raises(NotImplementedError) as e1:
            a.create_refund(RefundRequest(order_id="o", channel_trade_no="t", refund_amount_fen=1))
        msg = str(e1.value)
        assert "P2-4" in msg and "Q5" in msg, name
        assert "可退对象不存在" in msg, name
        assert "套餐未使用部分可退" in msg, name
        assert "退款被禁" not in msg and "暂不支持退款" not in msg, name
        with pytest.raises(NotImplementedError):
            a.query_payment("t")


def test_p2_2_adapters_ack_in_channel_native_format():
    """应答体必须用**通道自己的格式**（否则通道判失败 ⇒ 无限重推）。"""
    w = channels.get_adapter("wechat_pay").callback_ack(True)
    assert w[0] == '{"code":"SUCCESS","message":"成功"}'
    a = channels.get_adapter("alipay").callback_ack(True)
    assert a[0] == "success" and a[1].startswith("text/plain")
    # 失败态也必须是对端认得的格式（微信 `{"code":"FAIL"}` / 支付宝 `failure`）
    assert json.loads(channels.get_adapter("wechat_pay").callback_ack(False)[0])["code"] == "FAIL"
    assert channels.get_adapter("alipay").callback_ack(False)[0] == "failure"


# ── §2.3 窄依赖：通道层**永不**碰账本（源码级）──

_FORBIDDEN_IMPORT_MODULES = {"app.services.payment.ledger"}
_FORBIDDEN_NAMES = {
    "LedgerEntry", "PaymentAccount", "ledger",
    "post_entry", "grant_manual", "apply_net_diff", "apply_payment_confirmed",
    "get_or_create_account", "lock_account", "business_key",
}
_FORBIDDEN_TABLE_TEXT = ("ledger_entries", "payment_accounts")


def _ledger_leak_hits(src: str) -> list:
    """扫一份 Python 源码里「通道层碰了账本」的痕迹。

    ⚠️ 走 AST 而不是裸字符串匹配：注释与 docstring（本包的 docstring **大量**提到
       `ledger.apply_payment_confirmed` 与 `ledger_entries` 作为**边界说明**）不该被判红，
       真的 import / 名字引用 / 裸 SQL 表名才该。
    """
    hits = []
    tree = ast.parse(src)

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _FORBIDDEN_IMPORT_MODULES or \
                        alias.name.startswith("app.services.payment.ledger"):
                    hits.append("import " + alias.name)
                if alias.name.split(".")[-1] == "ledger":
                    hits.append("import " + alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod in _FORBIDDEN_IMPORT_MODULES or mod.startswith("app.services.payment.ledger"):
                hits.append("from " + mod)
            for alias in node.names:
                if alias.name in ("ledger",) or alias.name in _FORBIDDEN_NAMES:
                    hits.append("from {} import {}".format(mod, alias.name))
        elif isinstance(node, ast.Name):
            if node.id in _FORBIDDEN_NAMES:
                hits.append("name:" + node.id)
        elif isinstance(node, ast.Attribute):
            if node.attr in _FORBIDDEN_NAMES:
                hits.append("attr:" + node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            for t in _FORBIDDEN_TABLE_TEXT:
                if t in node.value:
                    hits.append("sql:" + t)
    return sorted(set(hits))


def test_p2_2_channels_never_touch_ledger():
    """§2.3：`channels/*.py` ⛔ 不许 import 账本、⛔ 不许直接写 `ledger_entries`/`payment_accounts`。"""
    pkg = pathlib.Path(channels.__file__).parent
    files = sorted(pkg.glob("*.py"))
    assert {f.name for f in files} >= {"base.py", "unset.py", "wechat.py", "alipay.py", "__init__.py"}
    for f in files:
        hits = _ledger_leak_hits(f.read_text(encoding="utf-8"))
        assert hits == [], "{} 越界碰了账本：{}".format(f.name, hits)


def test_p2_2_ledger_leak_detector_is_not_vacuous():
    """**本用例是上面那条判据自己的红**：检测器必须能真的抓到越界写法。

    ⛔ 没有这一条，`test_p2_2_channels_never_touch_ledger` 可能是「检测器恒返回空」的假绿。
    """
    assert _ledger_leak_hits(
        "from app.services.payment.ledger import post_entry\n")
    assert _ledger_leak_hits("import app.services.payment.ledger as lg\n")
    assert _ledger_leak_hits("from app.models.ledger_entry import LedgerEntry\n")
    assert _ledger_leak_hits("x = LedgerEntry\n")
    assert _ledger_leak_hits("db.execute('INSERT INTO ledger_entries (id) VALUES (1)')\n")
    # 反向：纯说明性 docstring 不该判红（否则检测器只会逼人去删注释）
    assert _ledger_leak_hits('"""本模块永不 import ledger，也不写 ledger_entries。"""\n') == []
    assert _ledger_leak_hits("# 说明：账本入口是 ledger.apply_payment_confirmed\nx = 1\n") == []


# ═══════════════════════════ P2-1 下单 ═══════════════════════════

def test_p2_1_unit_price_unchanged_50_fen():
    """⛔ 本批不许动 `pricing.py` 的数值/单位（0.5 元/份 = 50 分，兜底默认）。"""
    assert UNIT == 50, UNIT
    assert P.unit_price_fen("grade") == 50


def test_p2_1_orders_how_much_and_which_channel():
    """下单入参只认「金额 + 通道」，⛔ 不收 user_id（越权 §7.3）。"""
    from app.schemas.payment import OrderCreateIn

    assert set(OrderCreateIn.model_fields.keys()) == {"amount_fen", "channel"}
    assert "user_id" not in OrderCreateIn.model_fields


def test_p2_1_orders_requires_jwt(p2_app):
    """⛔ 无 JWT ⇒ 401（真 `get_current_user_id`，未被覆盖）**且零新增订单**。"""
    app, client, TestSession = p2_app
    r = client.post("/api/v1/payment/orders", json={"amount_fen": UNIT, "channel": "fake"})
    assert r.status_code == 401, r.text
    assert "detail" in r.json()
    db = TestSession()
    try:
        assert _count(db, PaymentOrder) == 0
    finally:
        db.close()


def test_p2_1_orders_ignores_user_id_query_param_and_body_field(p2_app, fake_channel):
    """⛔ 越权：`?user_id=` 与请求体里的 `user_id` **都不被采信** —— 收款对象只能是 JWT 身份。"""
    app, client, TestSession = p2_app
    r = client.post(
        "/api/v1/payment/orders?user_id=" + OTHER,
        json={"amount_fen": UNIT, "channel": "fake", "user_id": OTHER},
        headers=_auth(TEACHER),
    )
    assert r.status_code == 200, r.text
    order_id = r.json()["data"]["order_id"]
    db = TestSession()
    try:
        order = db.query(PaymentOrder).filter(PaymentOrder.id == order_id).one()
        assert order.user_id == TEACHER, "收款对象被 query/body 里的 user_id 带偏了"
        assert order.status == "pending" and order.amount_fen == UNIT
        assert order.channel == "fake"
    finally:
        db.close()


def test_p2_1_missing_channel_credentials_fails_loudly_with_zero_rows(p2_app, monkeypatch):
    """**配置缺失的红**（验收 5）：不给微信凭据 ⇒ 下单 **501 明确失败**，库里**零新增**。

    ⛔ 不许静默走假成功；⛔ 也不许留一条幽灵 pending 订单。
    同时钉住「连出网都没试过」—— 传输层被换成炸弹，一碰即炸。
    """
    import app.services.payment.channels.wechat as wechat_mod

    for k in ("PAYMENT_WECHAT_APP_ID", "PAYMENT_WECHAT_MCH_ID",
              "PAYMENT_WECHAT_CERT_SERIAL_NO", "PAYMENT_WECHAT_PRIVATE_KEY",
              "PAYMENT_WECHAT_API_V3_KEY", "PAYMENT_WECHAT_PUBLIC_KEY"):
        monkeypatch.setattr(settings, k, "")

    def _boom(*a, **kw):
        raise AssertionError("凭据缺失却向微信发起了请求（应先报错，不出网）")

    monkeypatch.setattr(wechat_mod, "_http_post_json", _boom)

    app, client, TestSession = p2_app
    r = client.post("/api/v1/payment/orders",
                    json={"amount_fen": UNIT, "channel": "wechat_pay"},
                    headers=_auth(TEACHER))
    assert r.status_code == 501, r.text
    detail = r.json()["detail"]
    assert "未配置" in detail and "PAYMENT_WECHAT" in detail, detail

    db = TestSession()
    try:
        assert _count(db, PaymentOrder) == 0, "下单失败却留下了订单行（幽灵 pending 订单）"
    finally:
        db.close()


def test_p2_1_missing_alipay_credentials_fails_loudly(p2_app, monkeypatch):
    """同上，支付宝侧。两个真实通道**各自**都要有这条红。"""
    for k in ("PAYMENT_ALIPAY_APP_ID", "PAYMENT_ALIPAY_PRIVATE_KEY",
              "PAYMENT_ALIPAY_PUBLIC_KEY"):
        monkeypatch.setattr(settings, k, "")
    app, client, TestSession = p2_app
    r = client.post("/api/v1/payment/orders",
                    json={"amount_fen": UNIT, "channel": "alipay"},
                    headers=_auth(TEACHER))
    assert r.status_code == 501, r.text
    assert "PAYMENT_ALIPAY" in r.json()["detail"]
    db = TestSession()
    try:
        assert _count(db, PaymentOrder) == 0
    finally:
        db.close()


def test_p2_1_broken_pem_is_503_not_501(p2_app, monkeypatch):
    """凭据**填了但填错**（PEM 非法）⇒ 503（服务端缺件），⛔ 不伪装成 501「未配置」。

    两者排查路径不同：「没配」= 资质问题，「配错」= 运维问题。
    """
    for k, v in WECHAT_CFG.items():
        monkeypatch.setattr(settings, k, v)
    monkeypatch.setattr(settings, "PAYMENT_WECHAT_CERT_SERIAL_NO", "TEST-SERIAL-0001")
    monkeypatch.setattr(
        settings, "PAYMENT_WECHAT_PRIVATE_KEY",
        "-----BEGIN PRIVATE KEY-----\n不是base64\n-----END PRIVATE KEY-----\n",
    )
    app, client, TestSession = p2_app
    r = client.post("/api/v1/payment/orders",
                    json={"amount_fen": UNIT, "channel": "wechat_pay"},
                    headers=_auth(TEACHER))
    assert r.status_code == 503, r.text
    assert "私钥" in r.json()["detail"]
    db = TestSession()
    try:
        assert _count(db, PaymentOrder) == 0
    finally:
        db.close()


def test_p2_1_unset_channel_returns_501(p2_app):
    """通道 = `unset` ⇒ 501「收款通道尚未配置」（§2.2 末段的字面行为）。"""
    app, client, TestSession = p2_app
    r = client.post("/api/v1/payment/orders",
                    json={"amount_fen": UNIT, "channel": "unset"},
                    headers=_auth(TEACHER))
    assert r.status_code == 501, r.text
    assert r.json()["detail"] == "收款通道尚未配置"


def test_p2_1_unknown_channel_returns_404(p2_app):
    app, client, TestSession = p2_app
    r = client.post("/api/v1/payment/orders",
                    json={"amount_fen": UNIT, "channel": "paypal"},
                    headers=_auth(TEACHER))
    assert r.status_code == 404, r.text


@pytest.mark.parametrize("bad", [0, -1])
def test_p2_1_amount_must_be_positive(p2_app, fake_channel, bad):
    app, client, TestSession = p2_app
    r = client.post("/api/v1/payment/orders",
                    json={"amount_fen": bad, "channel": "fake"},
                    headers=_auth(TEACHER))
    assert r.status_code == 422, r.text


def test_p2_1_happy_path_returns_pay_params(p2_app, fake_channel):
    """成功路径：订单落库 pending + 支付参数回给客户端（⛔ 不是只测兜底路径）。"""
    app, client, TestSession = p2_app
    r = client.post("/api/v1/payment/orders",
                    json={"amount_fen": UNIT, "channel": "fake"},
                    headers=_auth(TEACHER))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == 0 and "message" in body
    data = body["data"]
    assert data["order_id"] and data["channel"] == "fake"
    assert data["amount_fen"] == UNIT and data["status"] == "pending"
    assert data["pay_params"] == {"qr_code": "fake://pay/" + data["order_id"]}
    assert fake_channel.create_calls == 1

    db = TestSession()
    try:
        assert db.query(PaymentOrder).filter(PaymentOrder.id == data["order_id"]).count() == 1
    finally:
        db.close()


def test_p2_1_payee_entity_id_from_config_never_invented(p2_app, fake_channel, monkeypatch, caplog):
    """收款主体：配置有 ⇒ 带进订单；配置空 ⇒ **留空 + 记日志**（⛔ 不编一个值）。"""
    app, client, TestSession = p2_app

    monkeypatch.setattr(settings, "PAYMENT_PAYEE_ENTITY_ID", "")
    with caplog.at_level(logging.WARNING, logger="app.services.payment.orders"):
        r1 = client.post("/api/v1/payment/orders",
                         json={"amount_fen": UNIT, "channel": "fake"},
                         headers=_auth(TEACHER))
    assert r1.status_code == 200 and r1.json()["data"]["payee_entity_id"] is None
    assert any("收款主体标识未配置" in rec.getMessage() for rec in caplog.records), \
        [rec.getMessage() for rec in caplog.records]

    caplog.clear()
    monkeypatch.setattr(settings, "PAYMENT_PAYEE_ENTITY_ID", "ENT-0001")
    r2 = client.post("/api/v1/payment/orders",
                     json={"amount_fen": UNIT, "channel": "fake"},
                     headers=_auth(TEACHER))
    assert r2.json()["data"]["payee_entity_id"] == "ENT-0001"
    assert not [rec for rec in caplog.records if "收款主体标识未配置" in rec.getMessage()]


# ═══════════════════════════ P2-3 回调入账 ═══════════════════════════

def _place_order(client, channel="fake", amount=None):
    r = client.post("/api/v1/payment/orders",
                    json={"amount_fen": amount or UNIT, "channel": channel},
                    headers=_auth(TEACHER))
    assert r.status_code == 200, r.text
    return r.json()["data"]["order_id"]


def test_p2_3_closed_loop_order_callback_ledger_balance(p2_app, fake_channel):
    """**闭环**（验收 2）：下单 → 回调 → `apply_payment_confirmed` → 余额变化 → 落 1 条分录。"""
    app, client, TestSession = p2_app
    order_id = _place_order(client)

    db = TestSession()
    try:
        assert L.get_or_create_account(db, TEACHER).balance_fen == 0
    finally:
        db.close()

    body, headers = _fake_callback(fake_channel, order_id, UNIT, trade_no="fake-trade-closed")
    r = _post_callback(client, "fake", body, headers)
    assert r.status_code == 200, r.text
    assert json.loads(r.text)["code"] == 0

    db = TestSession()
    try:
        acct = db.query(PaymentAccount).filter(PaymentAccount.user_id == TEACHER).one()
        assert int(acct.balance_fen) == UNIT, "余额没动"
        entries = db.query(LedgerEntry).filter(LedgerEntry.order_id == order_id).all()
        assert len(entries) == 1
        e = entries[0]
        assert e.entry_type == L.ENTRY_RECHARGE and e.amount_fen == UNIT
        assert e.balance_after_fen == UNIT
        # 幂等键 = §3.5 由**订单 id** 决定（可复算）
        assert e.idempotency_key == L.payment_confirm_key(order_id)
        assert e.idempotency_key == "pay-confirm|" + order_id
        # I3：分录快照 == 账户余额
        assert e.balance_after_fen == acct.balance_fen
        order = db.query(PaymentOrder).filter(PaymentOrder.id == order_id).one()
        assert order.status == "paid" and order.paid_amount_fen == UNIT
        assert order.channel_trade_no == "fake-trade-closed" and order.paid_at is not None
    finally:
        db.close()


def test_p2_3_callback_does_not_need_jwt(p2_app, fake_channel):
    """⚠️ 回调**没有也不可能有 JWT**（通道不会带我们的令牌）—— 身份只来自验签。"""
    app, client, TestSession = p2_app
    order_id = _place_order(client)
    body, headers = _fake_callback(fake_channel, order_id, UNIT)
    r = _post_callback(client, "fake", body, headers, auth=False)  # 不带 Authorization
    assert r.status_code == 200, r.text
    db = TestSession()
    try:
        assert db.query(LedgerEntry).filter(LedgerEntry.order_id == order_id).count() == 1
    finally:
        db.close()


def test_p2_3_duplicate_callback_records_exactly_one_entry(p2_app, fake_channel):
    """**I1（验收 3）**：同一回调投两次 ⇒ **只有 1 条分录**，余额只加一次。"""
    app, client, TestSession = p2_app
    order_id = _place_order(client)
    body, headers = _fake_callback(fake_channel, order_id, UNIT, trade_no="fake-dup")

    r1 = _post_callback(client, "fake", body, headers)
    r2 = _post_callback(client, "fake", body, headers)   # 同一条回调再投一次
    assert (r1.status_code, r2.status_code) == (200, 200), (r1.text, r2.text)

    db = TestSession()
    try:
        assert db.query(LedgerEntry).filter(LedgerEntry.order_id == order_id).count() == 1
        acct = db.query(PaymentAccount).filter(PaymentAccount.user_id == TEACHER).one()
        assert int(acct.balance_fen) == UNIT, "重复投递把余额加了两次"
        # I3：账户余额 == 该账户全部分录之和
        total = sum(int(e.amount_fen) for e in
                    db.query(LedgerEntry).filter(LedgerEntry.account_id == acct.id).all())
        assert total == int(acct.balance_fen)
    finally:
        db.close()


def test_p2_3_idempotency_green_comes_from_key_determinism(p2_app, fake_channel, monkeypatch):
    """**I1 这条判据自己的红（应用层）**：把幂等键换成**非确定**版本 ⇒ 同一断言立刻变红。

    §3.5「本设计最容易做错的一处」：幂等键一旦掺入时间戳/随机数/通道号，重复投递就会
    重复扣账。本条与 `test_p2_3_duplicate_callback_records_exactly_one_entry` 是**同一断言的两面**
    —— 那一面的绿若不依赖 `payment_confirm_key` 的确定性，本用例就不会红。
    """
    app, client, TestSession = p2_app

    # (a) 正常键：2 条回调 ⇒ 1 条分录
    ok_order = _place_order(client)
    body, headers = _fake_callback(fake_channel, ok_order, UNIT)
    _post_callback(client, "fake", body, headers)
    _post_callback(client, "fake", body, headers)
    db = TestSession()
    try:
        assert db.query(LedgerEntry).filter(LedgerEntry.order_id == ok_order).count() == 1
    finally:
        db.close()

    # (b) 变异：键掺入随机数 ⇒ 同一条回调投两次 = 两条分录（证明 (a) 的绿是键给的）
    monkeypatch.setattr(
        L, "payment_confirm_key",
        lambda order_id: "pay-confirm|{}|{}".format(order_id, uuid.uuid4().hex),
    )
    bad_order = _place_order(client)
    body2, headers2 = _fake_callback(fake_channel, bad_order, UNIT)
    _post_callback(client, "fake", body2, headers2)
    _post_callback(client, "fake", body2, headers2)
    db = TestSession()
    try:
        assert db.query(LedgerEntry).filter(LedgerEntry.order_id == bad_order).count() == 2, \
            "键非确定时竟然仍是 1 条 ⇒ 说明那条断言不是被幂等键判住的（超定绿）"
        acct = db.query(PaymentAccount).filter(PaymentAccount.user_id == TEACHER).one()
        # 余额 = (a) 的 1 份 + (b) 的 2 份 = 3 份：**(b) 重复扣了两次**
        assert int(acct.balance_fen) == 3 * UNIT, int(acct.balance_fen)
    finally:
        db.close()


def test_p2_3_unique_index_is_the_last_line_of_defense(sqlite_env):
    """**I1 这条判据自己的红（DB 层）**：`uk_ledger_idempotency` 是承重墙，不是装饰。

    应用层的 `if existing` 是快路径，**并发下两个请求会同时落空** ⇒ 唯一索引才是最后防线。
    故这里直接模拟「两个并发请求」的形状：绕过应用层判据，**裸插**同键两行。

      (a) 有唯一索引 ⇒ 第二行 `IntegrityError`（I1 真成立）
      (b) 摘掉唯一索引（另起一个库）⇒ 同一次裸插**插得进去** ⇒ 证明 (a) 的红确由该索引判出
    """
    from sqlalchemy.exc import IntegrityError

    TestSession, _db = sqlite_env
    key = "pay-confirm|concurrent-demo"

    def _raw_insert(session_factory):
        s = session_factory()
        try:
            acct = L.get_or_create_account(s, TEACHER)
            s.add(LedgerEntry(account_id=acct.id, entry_type=L.ENTRY_RECHARGE,
                              amount_fen=UNIT, balance_after_fen=UNIT,
                              idempotency_key=key, description="裸插（模拟并发第二请求）"))
            s.commit()
        finally:
            s.close()

    # (a) 索引在
    _raw_insert(TestSession)
    with pytest.raises(IntegrityError):
        _raw_insert(TestSession)

    # (b) 摘掉唯一索引 —— 另起一个库，隔离掉上面那次插入
    eng2 = create_engine("sqlite://", connect_args={"check_same_thread": False},
                         poolclass=StaticPool)
    Base.metadata.create_all(bind=eng2)
    S2 = sessionmaker(autocommit=False, autoflush=False, bind=eng2)
    assert "uk_ledger_idempotency" in {ix["name"] for ix in inspect(eng2).get_indexes("ledger_entries")}
    with eng2.begin() as conn:
        conn.execute(text("DROP INDEX uk_ledger_idempotency"))
    assert "uk_ledger_idempotency" not in {ix["name"] for ix in inspect(eng2).get_indexes("ledger_entries")}

    _raw_insert(S2)
    _raw_insert(S2)          # 摘掉索引后**不再报错** ⇒ 索引确实是那条判据的承重墙
    s = S2()
    try:
        assert s.query(LedgerEntry).filter(LedgerEntry.idempotency_key == key).count() == 2
    finally:
        s.close()
    eng2.dispose()


# ── 验签（验收 4）：伪造签名 ⇒ 拒绝，且拒绝时不入账 ──

def test_p2_3_fake_channel_forged_signature_rejected_and_not_recorded(p2_app, fake_channel):
    """伪造签名（用**别的密钥**签）⇒ 400，且**一行账都不记**。"""
    app, client, TestSession = p2_app
    order_id = _place_order(client)

    good_body, good_headers = _fake_callback(fake_channel, order_id, UNIT)
    forged = dict(good_headers)
    forged["X-Fake-Signature"] = hmac.new(b"attacker-secret", good_body, hashlib.sha256).hexdigest()

    r = _post_callback(client, "fake", good_body, forged)
    assert r.status_code == 400, r.text
    assert json.loads(r.text)["code"] == 1

    db = TestSession()
    try:
        assert db.query(LedgerEntry).filter(LedgerEntry.order_id == order_id).count() == 0
        acct = db.query(PaymentAccount).filter(PaymentAccount.user_id == TEACHER).one_or_none()
        assert acct is None or int(acct.balance_fen) == 0
        order = db.query(PaymentOrder).filter(PaymentOrder.id == order_id).one()
        assert order.status == "pending" and order.paid_amount_fen is None
    finally:
        db.close()

    # 缺签名头同样拒绝（不是「没签名就放行」）
    r2 = _post_callback(client, "fake", good_body, {"Content-Type": "application/json"})
    assert r2.status_code == 400, r2.text


def test_p2_3_wechat_forged_signature_rejected_and_not_recorded(p2_app, fake_channel, wechat_cfg, rsa_keys):
    """**微信**：回调体是**完全合法**的（真 AES-256-GCM 密文、event/trade_state 全对），
    唯独签名由**攻击者私钥**签发 ⇒ 必须 400 且不入账。

    ⚠️ 这条是「验签有红」的载重版本：若把验签摘掉，这份回调**会被正常解密并入账**
       ⇒ 本用例立刻判红。⛔ 不是「body 破损所以被拒」那种超定红。
    """
    app, client, TestSession = p2_app
    # 订单经 fake 通道下单（微信**下单**要出网，不是本用例的对象），
    # **回调**走真实微信 adapter（验签/解密才是本用例的对象）。订单号是两条路径的公共锚点。
    order_id = _place_order(client)
    body, headers = _wechat_callback(rsa_keys["attacker_priv"], order_id=order_id,
                                     trade_no="wx-attacker-1", paid_fen=UNIT)
    r = _post_callback(client, "wechat_pay", body, headers)
    assert r.status_code == 400, r.text
    assert json.loads(r.text)["code"] == "FAIL"
    db = TestSession()
    try:
        assert db.query(LedgerEntry).filter(LedgerEntry.order_id == order_id).count() == 0
        assert db.query(PaymentOrder).filter(PaymentOrder.id == order_id).one().status == "pending"
    finally:
        db.close()


def test_p2_3_wechat_valid_signature_records_ledger(p2_app, fake_channel, wechat_cfg, rsa_keys):
    """**微信成功路径**：真 RSA 签名 + 真 AES-256-GCM 解密 ⇒ 200 `{"code":"SUCCESS"}` + 入账。"""
    app, client, TestSession = p2_app
    order_id = _place_order(client)
    body, headers = _wechat_callback(rsa_keys["platform_priv"], order_id=order_id,
                                     trade_no="wx-trade-ok", paid_fen=UNIT)
    r = _post_callback(client, "wechat_pay", body, headers)
    assert r.status_code == 200, r.text
    assert json.loads(r.text)["code"] == "SUCCESS"
    db = TestSession()
    try:
        e = db.query(LedgerEntry).filter(LedgerEntry.order_id == order_id).one()
        assert e.amount_fen == UNIT and e.entry_type == L.ENTRY_RECHARGE
        order = db.query(PaymentOrder).filter(PaymentOrder.id == order_id).one()
        assert order.status == "paid" and order.channel_trade_no == "wx-trade-ok"
    finally:
        db.close()


def test_p2_3_wechat_decrypt_failure_is_rejected_not_500(p2_app, fake_channel, wechat_cfg, rsa_keys):
    """签名合法但**密文解不开**（AES 密钥不符）⇒ 按不可信拒绝 400，⛔ 不是 500 崩掉。

    （这也是「解密失败 ⛔ 不许被包装成 503 服务端缺件」那条设计的回归。）
    """
    app, client, TestSession = p2_app
    order_id = _place_order(client)
    body, headers = _wechat_callback(
        rsa_keys["platform_priv"], order_id=order_id, trade_no="wx-badkey", paid_fen=UNIT,
        key_override=b"ffffffffffffffffffffffffffffffff",
    )
    r = _post_callback(client, "wechat_pay", body, headers)
    assert r.status_code == 400, r.text
    db = TestSession()
    try:
        assert db.query(LedgerEntry).filter(LedgerEntry.order_id == order_id).count() == 0
    finally:
        db.close()


def test_p2_3_wechat_stale_timestamp_rejected(p2_app, fake_channel, wechat_cfg, rsa_keys):
    """重放防护：签名**完全合法**但时间戳过期 ⇒ 拒绝（否则昨天的回调今天还能再投一次）。"""
    app, client, TestSession = p2_app
    order_id = _place_order(client)
    body, headers = _wechat_callback(rsa_keys["platform_priv"], order_id=order_id,
                                     trade_no="wx-stale", paid_fen=UNIT, skew=-3600)
    r = _post_callback(client, "wechat_pay", body, headers)
    assert r.status_code == 400, r.text
    db = TestSession()
    try:
        assert db.query(LedgerEntry).filter(LedgerEntry.order_id == order_id).count() == 0
    finally:
        db.close()


def test_p2_3_wechat_unconfigured_callback_is_501(p2_app, monkeypatch, caplog):
    """凭据缺失 ⇒ **501**（⛔ 不是「验签失败 400」、更不是静默放行）—— 两者排查路径不同。"""
    for k in ("PAYMENT_WECHAT_API_V3_KEY", "PAYMENT_WECHAT_PUBLIC_KEY"):
        monkeypatch.setattr(settings, k, "")
    app, client, TestSession = p2_app
    with caplog.at_level(logging.WARNING, logger="app.routers.payment"):
        r = _post_callback(client, "wechat_pay", b"{}", {"Content-Type": "application/json"})
    assert r.status_code == 501, r.text
    # 应答体仍须是**微信认得的失败格式**（否则微信不重推，这笔就永远丢了）
    assert json.loads(r.text)["code"] == "FAIL"
    # 拒绝原因进日志（缺哪两个配置项必须一眼可见）
    assert any("PAYMENT_WECHAT_API_V3_KEY" in rec.getMessage() for rec in caplog.records), \
        [rec.getMessage() for rec in caplog.records]


def test_p2_3_alipay_forged_signature_rejected_and_not_recorded(p2_app, fake_channel, alipay_cfg, rsa_keys):
    """**支付宝**：参数全合法，签名由攻击者私钥签发 ⇒ 400 且不入账。"""
    app, client, TestSession = p2_app
    order_id = _place_order(client)
    body, headers = _alipay_callback(rsa_keys["attacker_priv"], order_id=order_id,
                                     trade_no="ali-attacker", amount_yuan="0.50",
                                     app_id=alipay_cfg["app_id"])
    r = _post_callback(client, "alipay", body, headers)
    assert r.status_code == 400, r.text
    assert r.text == "failure"
    db = TestSession()
    try:
        assert db.query(LedgerEntry).filter(LedgerEntry.order_id == order_id).count() == 0
    finally:
        db.close()


def test_p2_3_alipay_valid_signature_records_ledger(p2_app, fake_channel, alipay_cfg, rsa_keys):
    """**支付宝成功路径**：真 RSA2 签名 + `total_amount` 元→分换算 ⇒ 200 `success` + 入账。"""
    app, client, TestSession = p2_app
    order_id = _place_order(client)
    body, headers = _alipay_callback(rsa_keys["platform_priv"], order_id=order_id,
                                     trade_no="ali-trade-ok", amount_yuan="0.50",
                                     app_id=alipay_cfg["app_id"])
    r = _post_callback(client, "alipay", body, headers)
    assert r.status_code == 200, r.text
    assert r.text == "success"
    db = TestSession()
    try:
        e = db.query(LedgerEntry).filter(LedgerEntry.order_id == order_id).one()
        assert e.amount_fen == UNIT, "元→分换算错了（0.50 元应 = 50 分）"
        order = db.query(PaymentOrder).filter(PaymentOrder.id == order_id).one()
        assert order.status == "paid" and order.channel_trade_no == "ali-trade-ok"
    finally:
        db.close()


def test_p2_3_alipay_notify_time_is_beijing_time(p2_app, fake_channel, alipay_cfg, rsa_keys):
    """**时区回归**：`notify_time` 是**北京时间**（`+08:00`）。

    若把它当 UTC 解析，真实回调会因 8 小时偏差被「超出容差」判掉 —— 即**每一条真实回调
    都进不来**。故：北京时间「此刻」必须收进来（正例），且入库的 `paid_at` 必须是**真 UTC**。
    """
    app, client, TestSession = p2_app
    order_id = _place_order(client)
    body, headers = _alipay_callback(rsa_keys["platform_priv"], order_id=order_id,
                                     trade_no="ali-tz", amount_yuan="0.50",
                                     app_id=alipay_cfg["app_id"])
    # 回调体里的 notify_time 就是北京时间；只有当 adapter 按 +08:00 解析，才可能通过容差
    r = _post_callback(client, "alipay", body, headers)
    assert r.status_code == 200, "北京时间的 notify_time 被当成 UTC ⇒ 真实回调全被拒：" + r.text
    db = TestSession()
    try:
        order = db.query(PaymentOrder).filter(PaymentOrder.id == order_id).one()
        paid_at = order.paid_at
        if paid_at.tzinfo is None:
            paid_at = paid_at.replace(tzinfo=timezone.utc)
        assert abs(paid_at.timestamp() - time.time()) < 600, "paid_at 不是真 UTC（差了时区偏移）"
    finally:
        db.close()


def test_p2_3_alipay_wrong_app_id_rejected(p2_app, fake_channel, alipay_cfg, rsa_keys):
    """纵深防御：签名合法但 `app_id` 不是我们的 ⇒ 拒绝（密钥串了/别人家的回调）。"""
    app, client, TestSession = p2_app
    order_id = _place_order(client)
    body, headers = _alipay_callback(rsa_keys["platform_priv"], order_id=order_id,
                                     trade_no="ali-otherapp", amount_yuan="0.50",
                                     app_id="2021999999999999")
    r = _post_callback(client, "alipay", body, headers)
    assert r.status_code == 400, r.text
    db = TestSession()
    try:
        assert db.query(LedgerEntry).filter(LedgerEntry.order_id == order_id).count() == 0
    finally:
        db.close()


def test_p2_3_alipay_non_success_trade_status_is_not_recorded(p2_app, fake_channel, alipay_cfg, rsa_keys):
    """只有 `TRADE_SUCCESS`/`TRADE_FINISHED` 算收款；其余状态**签名有效也不入账**。"""
    app, client, TestSession = p2_app
    order_id = _place_order(client)
    body, headers = _alipay_callback(rsa_keys["platform_priv"], order_id=order_id,
                                     trade_no="ali-wait", amount_yuan="0.50",
                                     app_id=alipay_cfg["app_id"],
                                     trade_status="WAIT_BUYER_PAY")
    r = _post_callback(client, "alipay", body, headers)
    assert r.status_code == 400, r.text
    db = TestSession()
    try:
        assert db.query(LedgerEntry).filter(LedgerEntry.order_id == order_id).count() == 0
    finally:
        db.close()


def test_p2_3_unknown_channel_callback_404(p2_app):
    app, client, TestSession = p2_app
    r = _post_callback(client, "paypal", b"{}", {"Content-Type": "application/json"})
    assert r.status_code == 404, r.text


def test_p2_3_unset_channel_callback_never_records(p2_app, sqlite_env):
    """`unset` 通道的回调 ⇒ 恒不入账（§2.2 逐字：`parse_callback` 恒返回 None）。"""
    app, client, TestSession = p2_app
    r = _post_callback(client, "unset", b'{"out_trade_no":"whatever"}',
                       {"Content-Type": "application/json"})
    assert r.status_code == 400, r.text
    db = TestSession()
    try:
        assert _count(db, LedgerEntry) == 0
    finally:
        db.close()


def test_p2_3_callback_for_unknown_order_is_404_and_not_recorded(p2_app, fake_channel):
    """签名合法但订单号不存在 ⇒ 404（⛔ 不凭签名就凭空造账）。"""
    app, client, TestSession = p2_app
    body, headers = _fake_callback(fake_channel, "no-such-order", UNIT)
    r = _post_callback(client, "fake", body, headers)
    assert r.status_code == 404, r.text
    # ⚠️ 回调的**错误应答体也必须是对端认得的通道格式**（这里是 fake 的 code=1），
    #    否则通道收不到「失败」判定；拒绝原因走日志，⛔ 不指望对端读 detail。
    assert json.loads(r.text)["code"] == 1
    db = TestSession()
    try:
        assert _count(db, LedgerEntry) == 0
    finally:
        db.close()


def test_p2_3_callback_for_refunded_order_is_409(p2_app, fake_channel):
    """已退款订单再收到收款确认 ⇒ 409（`OrderStateError`），⛔ 不重复入账。"""
    app, client, TestSession = p2_app
    order_id = _place_order(client)
    db = TestSession()
    try:
        order = db.query(PaymentOrder).filter(PaymentOrder.id == order_id).one()
        order.status = L.ORDER_REFUNDED
        db.commit()
    finally:
        db.close()

    body, headers = _fake_callback(fake_channel, order_id, UNIT)
    r = _post_callback(client, "fake", body, headers)
    assert r.status_code == 409, r.text
    assert json.loads(r.text)["code"] == 1   # 应答体仍是通道格式（见上一条注释）
    db = TestSession()
    try:
        assert _count(db, LedgerEntry) == 0
    finally:
        db.close()


def test_p2_3_paid_order_reconfirm_is_idempotent_not_409(p2_app, fake_channel):
    """已 `paid` 的订单再收到确认 ⇒ **幂等返回**（200，仍 1 条分录），⛔ 不判 409。

    理由：通道会重推，把「重推」判成冲突会让对端永远收不到 ACK ⇒ 无限重推。
    """
    app, client, TestSession = p2_app
    order_id = _place_order(client)
    body, headers = _fake_callback(fake_channel, order_id, UNIT)
    assert _post_callback(client, "fake", body, headers).status_code == 200
    r = _post_callback(client, "fake", body, headers)
    assert r.status_code == 200, r.text
    db = TestSession()
    try:
        assert db.query(LedgerEntry).filter(LedgerEntry.order_id == order_id).count() == 1
    finally:
        db.close()


def test_p2_3_amount_mismatch_records_actual_and_logs_error(p2_app, fake_channel, caplog):
    """§6.3 D3「以**通道实收**入账」：实收 ≠ 订单金额 ⇒ 按实收入账 ＋ 留 error 痕。

    ⛔ 必须留痕不静默：金额不符是「收错钱 / 伪造 / 优惠」三类问题的共同表征。
    """
    app, client, TestSession = p2_app
    order_id = _place_order(client, amount=UNIT)
    body, headers = _fake_callback(fake_channel, order_id, 30, trade_no="fake-under")

    with caplog.at_level(logging.ERROR, logger="app.services.payment.ledger"):
        r = _post_callback(client, "fake", body, headers)
    assert r.status_code == 200, r.text
    assert any("金额与订单不符" in rec.getMessage() for rec in caplog.records), \
        [rec.getMessage() for rec in caplog.records]

    db = TestSession()
    try:
        e = db.query(LedgerEntry).filter(LedgerEntry.order_id == order_id).one()
        assert e.amount_fen == 30, "没有按通道实收入账"
        order = db.query(PaymentOrder).filter(PaymentOrder.id == order_id).one()
        assert order.amount_fen == UNIT and order.paid_amount_fen == 30
    finally:
        db.close()


def test_p2_3_callback_never_trusts_body_identity(p2_app, fake_channel):
    """⛔ 越权：回调体里塞 `user_id` **不改变**收款对象 —— 收款账户只能由订单号反查。

    （诱饵见 `_fake_callback`；若实现改成读 body 身份，本用例立刻判红。）
    """
    app, client, TestSession = p2_app
    order_id = _place_order(client)   # 订单属于 TEACHER
    body, headers = _fake_callback(fake_channel, order_id, UNIT, decoy_user_id=OTHER)
    assert _post_callback(client, "fake", body, headers).status_code == 200

    db = TestSession()
    try:
        e = db.query(LedgerEntry).filter(LedgerEntry.order_id == order_id).one()
        acct = db.query(PaymentAccount).filter(PaymentAccount.id == e.account_id).one()
        assert acct.user_id == TEACHER, "收款账户被回调体里的 user_id 带偏了"
        other = db.query(PaymentAccount).filter(PaymentAccount.user_id == OTHER).one_or_none()
        assert other is None or int(other.balance_fen) == 0
    finally:
        db.close()


def test_p2_3_only_one_write_path_into_ledger():
    """§2.3 窄依赖：路由层**不直接记账** —— 唯一的写路径是 `orders.handle_callback`。

    ⚠️ 走 AST 取**被调用的名字**，而不是裸字符串匹配：本模块 docstring 里**故意**写了
       「写动作全部经 `ledger.apply_payment_confirmed`」这句边界说明，字符串匹配会误判它。
    （读路径不受限：P0-6 的只读投影本来就要 import `LedgerEntry` 来查。）
    """
    import inspect
    from collections import Counter

    tree = ast.parse(inspect.getsource(payment_router))
    calls = Counter()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                calls[f.id] += 1
            elif isinstance(f, ast.Attribute):
                calls[f.attr] += 1

    for forbidden in ("post_entry", "apply_payment_confirmed", "grant_manual", "apply_net_diff"):
        assert calls[forbidden] == 0, "路由层直接调了 {} —— 记账必须经通道适配层编排".format(forbidden)
    assert calls["handle_callback"] == 1, "写路径不唯一：{}".format(calls["handle_callback"])


# ═══════════════════════════ AUTO_DDL=false 旧库自愈 ═══════════════════════════

TAX_COLUMNS = ("amount_excl_tax_fen", "tax_amount_fen", "tax_rate_bps")


def test_p2_tax_columns_declared_in_model_and_nullable():
    """§10 Q3 的 3 个价税分离列：**整数「分」口径 + 可空**（存量订单无值）。

    ⛔ 账本**不**跟着加税字段（§10 Q3 逐字：含税记账，税额只在订单层拆）。
    """
    from sqlalchemy import Integer

    cols = PaymentOrder.__table__.columns
    for name in TAX_COLUMNS:
        assert name in cols, "{} 不在 payment_orders 模型里".format(name)
        assert cols[name].nullable is True, name
        assert isinstance(cols[name].type, Integer), name
    # 账本表⛔不许出现税字段
    for name in TAX_COLUMNS:
        assert name not in LedgerEntry.__table__.columns, "账本被加了税字段：{}".format(name)


def test_p2_tax_columns_self_heal_when_auto_ddl_false(monkeypatch, caplog):
    """**价税分离补列自己的红**：真·旧库（缺这 3 列）＋ `AUTO_DDL=false` ⇒ `init_db()` 必须补齐。

    ⚠️ 为什么不能只靠 `create_all`：Phase 0 已把 `payment_orders` 建出来了，`create_all` 对
       **已存在的表**是空操作 ⇒ 缺的列永远补不上（首次开票才 1054）。
    ⚠️ 判据两条：(a) 3 列回来；(b) **二次调用幂等**且**表集合不变**（⛔ 不能靠重建表来补列）。
    """
    eng = create_engine("sqlite:///:memory:")
    monkeypatch.setattr(database, "engine", eng)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=eng))
    monkeypatch.setattr(database.settings, "AUTO_DDL", False)

    Base.metadata.create_all(bind=eng)
    with eng.begin() as conn:
        for name in TAX_COLUMNS:
            conn.execute(text("ALTER TABLE payment_orders DROP COLUMN {}".format(name)))
    cols = {c["name"] for c in inspect(eng).get_columns("payment_orders")}
    assert not (set(TAX_COLUMNS) & cols), cols
    # 既有订单行：补列不能把老数据搞没（可空列 ⇒ 老行取 NULL）
    with eng.begin() as conn:
        conn.execute(text(
            "INSERT INTO payment_orders (id, user_id, channel, status, amount_fen, subject_type) "
            "VALUES ('o-legacy', 'u-legacy', 'unset', 'pending', 50, 'recharge')"
        ))
    tables_before = set(inspect(eng).get_table_names())
    indexes_before = {ix["name"] for ix in inspect(eng).get_indexes("payment_orders")}

    database.init_db()

    cols = {c["name"] for c in inspect(eng).get_columns("payment_orders")}
    assert set(TAX_COLUMNS) <= cols, sorted(set(TAX_COLUMNS) - cols)
    assert set(inspect(eng).get_table_names()) == tables_before, "表集合变了（不是补列而是重建）"
    assert {ix["name"] for ix in inspect(eng).get_indexes("payment_orders")} == indexes_before, \
        "索引集合变了"
    with eng.begin() as conn:
        row = conn.execute(text(
            "SELECT amount_fen, amount_excl_tax_fen, tax_amount_fen, tax_rate_bps "
            "FROM payment_orders WHERE id='o-legacy'")).fetchone()
    assert row[0] == 50 and row[1] is None and row[2] is None and row[3] is None, row

    # 幂等：二次调用不抛、列与表态一字不变，**且不能靠吞异常混过去**
    # ⚠️ 这一条钉的是「真的**跳过**了已存在的列」：若去掉 `if name in existing: continue` 的比对，
    #    第二次 ALTER 会因列已存在而报错 —— 被外层 except 吞掉 ⇒ 光是「不抛」看不出来，
    #    于是要求「补列这条路**一条 error 日志都不打**」。
    cols_first = {c["name"] for c in inspect(eng).get_columns("payment_orders")}
    with caplog.at_level(logging.ERROR, logger="app.database"):
        database.init_db()
    noisy = [r.getMessage() for r in caplog.records if "价税分离补列" in r.getMessage()]
    assert not noisy, "二次调用仍在试图补列（幂等是靠吞异常混过去的）：{}".format(noisy)
    assert {c["name"] for c in inspect(eng).get_columns("payment_orders")} == cols_first
    assert set(inspect(eng).get_table_names()) == tables_before
    eng.dispose()


def test_p2_init_db_self_heals_payment_tables_when_auto_ddl_false(monkeypatch):
    """验收 7：`AUTO_DDL=false`（生产默认）下，缺表库能被 `init_db()` 补回来。

    ⛔ 这正是不许把 `_ensure_payment_tables()` 上移到 `sync_database_schema()` 的
    `if not AUTO_DDL: return` 之后的原因 —— 那样生产默认配置下一次都不执行。
    """
    eng = create_engine("sqlite:///:memory:")
    monkeypatch.setattr(database, "engine", eng)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=eng))
    monkeypatch.setattr(database.settings, "AUTO_DDL", False)

    # 先建全量（其它 `_ensure_*` 也要摸 users 等表），再刻意把两张支付表砸掉
    Base.metadata.create_all(bind=eng)
    with eng.begin() as conn:
        conn.execute(text("DROP TABLE payment_orders"))
        conn.execute(text("DROP TABLE ledger_entries"))
    tables = set(inspect(eng).get_table_names())
    assert "payment_orders" not in tables and "ledger_entries" not in tables

    database.init_db()

    tables = set(inspect(eng).get_table_names())
    assert {"payment_orders", "ledger_entries", "payment_accounts"} <= tables, sorted(tables)
    # 幂等：二次调用不抛、库状态不变
    database.init_db()
    assert set(inspect(eng).get_table_names()) == tables
    assert "uk_ledger_idempotency" in {
        ix["name"] for ix in inspect(eng).get_indexes("ledger_entries")
    }, "自愈出来的 ledger_entries 少了唯一索引 —— 幂等最后防线没建上"
    assert set(TAX_COLUMNS) <= {c["name"] for c in inspect(eng).get_columns("payment_orders")}
    eng.dispose()
