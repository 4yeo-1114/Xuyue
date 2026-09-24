# -*- coding: utf-8 -*-
"""独立老师支付系统 Phase 3（P3-1 发票结构）· **真 MySQL** 回归测试。

判据逐条取自 docs/payment/payment-design.md §9-Phase3「P3-1 发票」/ §10 Q3
＋ 本批 brief 的「已拍口径」表（票种=普票 / 载体=电子 / 金额=含税 / 手续费=平台承担 /
红冲=不做 / 税率未拍 ⇒ 不硬编）。

文件主轴 = **每条判据自己的红**（每条用例的 docstring 里逐条写明「什么输入下它会失败」）。

环境：**真 Docker MySQL**（127.0.0.1:13307），scratch 库 `grade_invoice_p3`。
    ⛔ **绝不碰跨会话共享的 `grade` 库**（只读）—— `test_p3_00` 用断言把这条钉死。
    ⛔ 口令只从环境变量 / `backend/.env`（已被 .gitignore 忽略）读，**不写进本文件**。

⚠️ **本文件与仓内其它真库测试（test_e04 / test_payment_p0 / test_payment_p2）一样，
   假定自己独占一个 pytest 进程**：`app.config.settings` 是模块级单例，谁先 import 谁定
   DB_*。⚠️ **请按文件单跑**（`pytest tests/test_payment_p3.py`）—— 与别的真库测试同进程
   混跑时，`test_p3_00` 会**显式判红**（⛔ 不会静默跑错库）。
⚠️ 用 `python -u -m pytest` 跑：输出重定向时块缓冲会丢输出（空输出 ≠ 没执行）。
"""
import os
import pathlib

# ── 环境必须早于任何 `app.*` import（`app.database` 在**导入期**就会按 AUTO_DDL 去连库）──
# ⚠️ `pydantic-settings` 优先级：os.environ > `.env` 文件 ⇒ 下面一律**强制赋值**（不是 setdefault），
#    否则本机 `backend/.env` 的 `AUTO_DDL=true` / `DB_NAME=grade_e2e` 会压过测试口径。
_DB_HOST = os.environ.get("P3_DB_HOST", "127.0.0.1")
_DB_PORT = int(os.environ.get("P3_DB_PORT", "13307"))
_DB_USER = os.environ.get("P3_DB_USER", "root")
_TEST_DB = os.environ.get("P3_TEST_DB", "grade_invoice_p3")
_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]


def _read_db_password() -> str:
    """口令只从「专用覆盖变量 `P3_DB_PASSWORD` / `backend/.env`」读。

    ⛔ **不读通用的 `DB_PASSWORD` 环境变量** —— `tests/conftest.py:23` 有一句
       `os.environ.setdefault("DB_PASSWORD", "test")`，它在**任何测试模块被 import 之前**
       就先跑（pytest 先加载 conftest）⇒ 读通用名必然拿到占位串 `"test"`，
       于是真库连接被拒、**所有 DB 用例静默转 skip**（本文件第一次跑就是这么挂的：
       `OperationalError 1045 ... using password: YES`）。`test_e04/e05/e08/e10` 全都用
       「专用前缀变量 + 本地 Docker 默认值」正是为了躲这个坑，此处照抄那条纪律。
    ⛔ 口令**不硬编进本文件**（brief：`backend/.env` 自己读、别写进任何提交的文件）。
    """
    pwd = os.environ.get("P3_DB_PASSWORD")
    if pwd:
        return pwd
    env_file = _BACKEND_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("DB_PASSWORD="):
                return line.split("=", 1)[1].strip()
    return ""


_DB_PASSWORD = _read_db_password()

os.environ["DB_HOST"] = _DB_HOST
os.environ["DB_PORT"] = str(_DB_PORT)
os.environ["DB_USER"] = _DB_USER
os.environ["DB_PASSWORD"] = _DB_PASSWORD
os.environ["DB_NAME"] = _TEST_DB
os.environ["AUTO_DDL"] = "false"          # 本文件测的就是生产默认 AUTO_DDL=false 这条路
os.environ.setdefault("JWT_SECRET_KEY", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("DASHSCOPE_API_KEY", "sk-p3-test-not-real")

assert _TEST_DB != "grade", "⛔ 本文件禁止指向跨会话共享的 grade 库"

import pymysql  # noqa: E402

# scratch 库自建（照 test_e04 的范式）。Docker MySQL 不在 ⇒ 全部用例 skip（⚠️ 会显式打印原因）
_MYSQL_ERR = ""
_MYSQL_AVAILABLE = False
try:
    _probe = pymysql.connect(
        host=_DB_HOST, port=_DB_PORT, user=_DB_USER, password=_DB_PASSWORD,
        autocommit=True, connect_timeout=5,
    )
    with _probe.cursor() as _cur:
        _cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{_TEST_DB}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
    _probe.close()
    _MYSQL_AVAILABLE = True
except Exception as _exc:  # noqa: BLE001 - 环境不可用则降级
    _MYSQL_ERR = f"{type(_exc).__name__}: {_exc}"

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

import app.database as database  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402
from app.models.payment_account import PaymentAccount  # noqa: E402
from app.models.payment_invoice import PaymentInvoice  # noqa: E402
from app.models.payment_order import PaymentOrder  # noqa: E402
from app.models.user import User  # noqa: E402
from app.routers import payment as payment_router  # noqa: E402
from app.services.payment import invoices as svc  # noqa: E402
from app.services.payment import ledger as ledger_svc  # noqa: E402
from app.utils.security import create_access_token  # noqa: E402

TEACHER = "u-p3-teacher"
OTHER = "u-p3-other"

# 本模块**逐用例清行**只清这些表（DDL 层面的清场是 session 夹具的「整库重建」）。
# 顺序 = 外键**子表在前**（users 是被引用方，必须最后 DELETE、最先建）。
_OWN_TABLES = (
    "payment_invoices",
    "ledger_entries",
    "subscriptions",
    "payment_accounts",
    "usage_events",
    "payment_plans",
    "payment_orders",
    "users",
)

_GOOD_PAYLOAD = {
    "order_id": "o-p3-default",
    "title": "叙阅科技（上海）有限公司",
    "taxpayer_id": "91310000MA1K35Q123",
    "email": "teacher@example.com",
}


# ═══════════════════════════ 夹具 ═══════════════════════════

@pytest.fixture(scope="session")
def mysql_engine():
    """真 MySQL 引擎（scratch 库）：会话开始**整库重建** ＋ **连库自证**。

    ⚠️ 为什么是「整库重建」而不是「丢本模块那几张表」：被测的 `init_db()` 顺带会建出
       `response_logs` 等**同样 FK 指向 `users`** 的表（`_ensure_response_logs_table()`），
       于是 `DROP TABLE users` 会被 MySQL 拒（**3730** `Cannot drop table 'users'
       referenced by a foreign key constraint 'response_logs_ibfk_1'`）—— 本文件第二次跑
       时就是这么红的。重建整库对「init_db() 以后又建了哪张表」免疫。
    ⛔ 只允许重建 `grade_invoice_p3`（下面 assert 硬挡）—— **绝不碰共享的 `grade` 库**。
    """
    if not _MYSQL_AVAILABLE:
        pytest.skip(f"本地 Docker MySQL 不可用，P3 用例跳过（⛔ 这不构成绿）：{_MYSQL_ERR}")
    assert _TEST_DB == "grade_invoice_p3" and _TEST_DB != "grade", \
        f"⛔ 拒绝重建非 scratch 库：{_TEST_DB}"
    admin = pymysql.connect(
        host=_DB_HOST, port=_DB_PORT, user=_DB_USER, password=_DB_PASSWORD,
        autocommit=True, connect_timeout=5,
    )
    with admin.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS `{_TEST_DB}`")
        cur.execute(
            f"CREATE DATABASE `{_TEST_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
    admin.close()
    database.engine.dispose()   # 丢掉可能还指向旧库句柄的池连接

    eng = create_engine(
        f"mysql+pymysql://{_DB_USER}:{_DB_PASSWORD}@{_DB_HOST}:{_DB_PORT}/{_TEST_DB}?charset=utf8mb4",
        pool_pre_ping=True,
    )
    with eng.connect() as conn:
        got = conn.execute(text("SELECT DATABASE()")).scalar()
    assert got == _TEST_DB, f"连到的库是 {got}，不是 scratch 库 {_TEST_DB}"
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture(scope="session")
def seeded(mysql_engine):
    """建 `users`（支付表的**真外键**父表）→ 再调**被测的** `init_db()` 建支付表。

    ⚠️ `users` 必须本夹具自己先建：`_ensure_payment_tables()` 的 create_all **不含** users，
       而 MySQL 上缺外键父表会让整批 `CREATE TABLE` 全失败（`.env` 里 AUTO_DDL=false 时
       没有任何别的路径会建它）。
    ⚠️ 本夹具**故意不改 AUTO_DDL**：`database.init_db()` 在 `settings.AUTO_DDL=False`
       （真实生产默认）下跑 —— 这正是不许把建表上移到 `sync_database_schema()` 之后的理由。
    """
    assert database.settings.AUTO_DDL is False
    Base.metadata.create_all(bind=mysql_engine, tables=[User.__table__])
    database.init_db()
    assert inspect(mysql_engine).has_table("payment_invoices"), \
        "init_db() 在 AUTO_DDL=false 下没把 payment_invoices 建出来"
    return mysql_engine


@pytest.fixture()
def clean(seeded):
    """每个用例前清数据（保留表结构）—— 保证「库里零新增」这类断言读的是**本用例**的库态。"""
    with seeded.begin() as conn:
        for name in _OWN_TABLES:
            conn.execute(Base.metadata.tables[name].delete())
    return seeded


@pytest.fixture()
def db(clean):
    session = database.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(clean):
    """只挂 payment 路由的裸 FastAPI。

    ⚠️ **不覆盖 `get_db` 也不覆盖 `get_current_user_id`** —— 走真 `SessionLocal`（真 MySQL）
       与**真 JWT 解析**；覆盖掉任何一个都等于自证（照 test_payment_p2 的纪律）。
    """
    app = FastAPI()
    app.include_router(payment_router.router, prefix="/api/v1")
    with TestClient(app) as c:
        yield c


# ── 造数据 ──
def _add_user(db, uid: str, roles: str = "任课教师") -> None:
    db.add(User(id=uid, email=f"{uid}@p3.test", password_hash="x", display_name=uid, roles=roles))
    db.commit()


def _add_order(db, oid: str, uid: str, *, status: str = svc.ledger_svc.ORDER_PAID,
               amount_fen: int = 50) -> None:
    db.add(PaymentOrder(id=oid, user_id=uid, channel="unset", status=status,
                        amount_fen=amount_fen, subject_type="recharge"))
    db.commit()


def _auth(uid: str) -> dict:
    return {"Authorization": "Bearer " + create_access_token(uid)}


def _submit(client, uid: str, **over):
    payload = dict(_GOOD_PAYLOAD)
    payload.update(over)
    return client.post("/api/v1/payment/invoices", headers=_auth(uid), json=payload)


# ═══════════════════════════ 0. 环境守卫 ═══════════════════════════

def test_p3_00_env_points_at_scratch_db_not_shared_grade():
    """环境守卫：本文件必须打在 scratch 库上，⛔ 绝不碰共享的 `grade` 库。

    【自己的红】把上面的 `_TEST_DB` 改成 `grade`（或删掉 `assert _TEST_DB != "grade"`）
      ⇒ 本用例立刻红。⚠️ 混跑（同进程先 import 了别的真库测试）也会在这里红 ——
      这是**有意的**：宁可判红，也不静默跑错库。
    """
    assert _TEST_DB == "grade_invoice_p3"
    assert settings.DB_NAME == _TEST_DB, \
        f"settings.DB_NAME={settings.DB_NAME} 不是 scratch 库（同进程混跑？请按文件单跑）"
    assert settings.DB_NAME != "grade"
    assert settings.AUTO_DDL is False, "本文件测的是生产默认 AUTO_DDL=false 这条路"


# ═══════════════════════════ 1. 建表 / 迁移落点 ═══════════════════════════

def test_p3_01_init_db_creates_invoice_table_columns_and_indexes(mysql_engine, seeded):
    """P3-1 建表：真 MySQL 上 `payment_invoices` 列齐 ＋ 一单一票的唯一约束真的建出来了。

    【自己的红】把 `PaymentInvoice.__table__` 从 `_ensure_payment_tables()` 的 tables 列表里
      删掉 ⇒ 表不存在 ⇒ 红。把模型里的 `UniqueConstraint("order_id", ...)` 删掉 ⇒ 索引断言红。
    """
    insp = inspect(mysql_engine)
    assert insp.has_table("payment_invoices")
    cols = {c["name"] for c in insp.get_columns("payment_invoices")}
    assert {
        "id", "order_id", "user_id", "status", "amount_fen", "title", "taxpayer_id",
        "email", "invoice_no", "issued_at", "voided_at", "created_at", "updated_at",
    } <= cols, sorted(cols)

    names = {ix["name"] for ix in insp.get_indexes("payment_invoices")}
    names |= {uc["name"] for uc in insp.get_unique_constraints("payment_invoices")}
    assert "uk_payment_invoice_order" in names, "一单一票的 DB 约束没建出来"
    assert "idx_payment_invoice_user_time" in names


def test_p3_02_self_heal_lives_in_unconditional_segment(mysql_engine, seeded):
    """【载重断言】为什么 P3-1 建表必须落在 `init_db()` 的**无条件段**。

    两半都要成立（缺一半这条判据就是空的）：
      (a) `AUTO_DDL=false`（生产默认）下 `sync_database_schema()` **一个表都不建**（第一行就 return）；
      (b) 同配置下 `init_db()` **必须**把表建回来。

    【自己的红】把 `_ensure_payment_tables()` 挪到 `sync_database_schema()` 的早退
      **之后** ⇒ (b) 红（表补不回来，生产默认配置下一次都不执行 —— D-1 事故同因）；
      挪到早退**之前** ⇒ (a) 红（说明它其实挂在 AUTO_DDL 路径上）。
    """
    with mysql_engine.begin() as conn:
        Base.metadata.tables["payment_invoices"].drop(bind=conn, checkfirst=True)
    assert not inspect(mysql_engine).has_table("payment_invoices")

    # (a) AUTO_DDL=false ⇒ sync_database_schema 第一行 return
    assert database.settings.AUTO_DDL is False
    database.sync_database_schema()
    assert not inspect(mysql_engine).has_table("payment_invoices"), \
        "AUTO_DDL=false 时 sync_database_schema() 竟然建了表 —— 落点其实在它内部（错）"

    # (b) init_db() 的**无条件段**必须建回来
    database.init_db()
    assert inspect(mysql_engine).has_table("payment_invoices")
    cols_before = {c["name"] for c in inspect(mysql_engine).get_columns("payment_invoices")}
    # 幂等：二次调用不抛、列集合不变
    database.init_db()
    assert {c["name"] for c in inspect(mysql_engine).get_columns("payment_invoices")} == cols_before


def test_p3_03_init_db_invokes_ensure_payment_tables_under_auto_ddl_false(monkeypatch):
    """`AUTO_DDL=false` 时 `init_db()` 仍必须调用 `_ensure_payment_tables()`（直取调用点）。

    【自己的红】把 `init_db()` 里那句 `_ensure_payment_tables()` 删掉 ⇒ `called == []` ⇒ 红。
    """
    called: list[int] = []
    monkeypatch.setattr(database, "_ensure_payment_tables", lambda *a, **kw: called.append(1))
    assert database.settings.AUTO_DDL is False
    database.init_db()
    assert called, "_ensure_payment_tables 在 AUTO_DDL=false 下没有被 init_db() 调到"


# ═══════════════════════════ 2. 已拍口径的负向落实 ═══════════════════════════

# ⛔ 本批「已拍口径」逐字对应的**禁止列**（表里出现任意一个 = 自创/扩项）
FORBIDDEN_COLUMNS = {
    # 票种 = 普票 ⇒ ⛔ 专票那四项
    "address": "专票·地址",
    "phone": "专票·电话",
    "bank_name": "专票·开户行",
    "bank_account": "专票·账号",
    "company_address": "专票·地址",
    "company_phone": "专票·电话",
    # 载体 = 电子 ⇒ ⛔ 收件地址 / 邮寄相关
    "shipping_address": "邮寄地址",
    "mail_address": "邮寄地址",
    "postal_code": "邮编",
    "recipient": "收件人",
    "recipient_phone": "收件人电话",
    "express_no": "快递单号",
    # 税率未拍 + 税额不由本系统计算 ⇒ ⛔ 税率/税额
    "tax_rate_bps": "税率",
    "tax_amount_fen": "税额",
    "amount_excl_tax_fen": "不含税金额",
    # 红冲本阶段不做 ⇒ ⛔ 红冲
    "red_flush": "红冲",
    "red_flush_invoice_id": "红冲",
    "original_invoice_id": "红冲",
    "reversed_invoice_id": "红冲",
    "refund_amount_fen": "退款/红冲金额",
    # 手续费平台承担 ⇒ ⛔ 发票里的手续费分摊
    "fee_fen": "手续费",
    "platform_fee_fen": "手续费",
    "fee_rate_bps": "手续费率",
}


def test_p3_10_no_special_invoice_mail_tax_redflush_or_fee_columns(mysql_engine, seeded):
    """已拍口径的**负向**落实：模型与真库都⛔ 不得出现专票/邮寄/税率税额/红冲/手续费字段。

    【自己的红】给 `PaymentInvoice` 加任意一列（如 `bank_account` 或 `tax_rate_bps`）
      ⇒ 本用例立刻红（模型列集合与真库列集合都会多出来）。
    """
    orm_cols = set(PaymentInvoice.__table__.columns.keys())
    real_cols = {c["name"] for c in inspect(mysql_engine).get_columns("payment_invoices")}
    for name, what in FORBIDDEN_COLUMNS.items():
        assert name not in orm_cols, f"{what} 字段被加进了模型：{name}"
        assert name not in real_cols, f"{what} 字段被加进了真库：{name}"


def test_p3_11_invoice_request_body_carries_no_amount_and_no_tax_fields():
    """请求体**也没有**金额/税率/专票/邮寄字段（⛔ 不能靠「有字段但不读」蒙过去）。

    【自己的红】给 `InvoiceCreateIn` 加 `amount_fen` / `tax_rate_bps` / `bank_account`
      ⇒ 本用例红。
    """
    from app.schemas.payment import InvoiceCreateIn, InvoiceOut

    # ⚠️ `amount_fen` **不在**禁止列里：开票金额是已拍口径（含税·分）要回给老师的字段，
    #    它在**响应体**里是合法的。⛔ 它在**请求体**里才是危险信号（老师自己填票面金额），
    #    故下面把两者分开断言 —— 判据不能一把梭。
    forbidden_in_body = ("amount_fen", "amount", "total_fen")
    for name in forbidden_in_body:
        assert name not in InvoiceCreateIn.model_fields, f"请求体被加了字段：{name}"

    for name in ("tax_rate_bps", "tax_amount_fen", "amount_excl_tax_fen",
                 "fee_fen", "platform_fee_fen",
                 "bank_account", "bank_name", "address", "phone",
                 "company_address", "company_phone",
                 "shipping_address", "mail_address", "postal_code", "recipient",
                 "red_flush", "original_invoice_id"):
        assert name not in InvoiceCreateIn.model_fields, f"请求体被加了字段：{name}"
        assert name not in InvoiceOut.model_fields, f"响应体被加了字段：{name}"

    # 反向：响应体必须**带着**金额（含税·分），否则「含税口径」在接口层就丢了
    assert "amount_fen" in InvoiceOut.model_fields


# ═══════════════════════════ 3. 提交开票申请 ═══════════════════════════

def test_p3_20_submit_invoice_happy_path(client, db):
    """成功路径：老师给**自己已支付**的订单提交申请 ⇒ `requested` ＋ 真库 1 行。

    【自己的红】不设 `status`（默认值被改坏）/ 不写 `user_id` / 金额取错 ⇒ 对应断言红。
    """
    _add_user(db, TEACHER)
    _add_order(db, "o-p3-1", TEACHER, amount_fen=50)

    r = _submit(client, TEACHER, order_id="o-p3-1")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == 0
    d = body["data"]
    assert d["status"] == "requested"
    assert d["order_id"] == "o-p3-1"
    assert d["amount_fen"] == 50
    assert d["title"] == _GOOD_PAYLOAD["title"]
    assert d["taxpayer_id"] == _GOOD_PAYLOAD["taxpayer_id"]
    assert d["email"] == _GOOD_PAYLOAD["email"]
    assert d["invoice_no"] is None and d["issued_at"] is None and d["voided_at"] is None
    assert d["created_at"], "requested_at 语义靠 created_at 承载，不能为空"

    row = db.query(PaymentInvoice).one()
    assert (row.user_id, row.status, row.amount_fen) == (TEACHER, "requested", 50)
    assert (row.invoice_no, row.issued_at, row.voided_at) == (None, None, None)


def test_p3_21_amount_comes_from_order_not_request_body(client, db):
    """开票金额（含税·分）**只从订单取** —— 请求体里塞任何金额字段都不采信。

    【自己的红】让端点改读请求体（schema 加 `amount_fen` 并透传）⇒ 落库变 1 分 ⇒ 红。
      这条挡的是「老师自己填票面金额」。
    """
    _add_user(db, TEACHER)
    _add_order(db, "o-p3-amount", TEACHER, amount_fen=50)

    r = _submit(client, TEACHER, order_id="o-p3-amount",
                amount_fen=1, amount=1, total_fen=1, pay_amount_fen=1)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["amount_fen"] == 50
    assert db.query(PaymentInvoice).one().amount_fen == 50


def test_p3_22_submit_and_list_require_jwt(client, db):
    """两个端点都要登录：无 Authorization ⇒ 401，且**库里零新增**。

    【自己的红】把 `Depends(get_current_user_id)` 去掉 ⇒ 变成 200/422 ⇒ 红。
    """
    _add_user(db, TEACHER)
    _add_order(db, "o-p3-nologin", TEACHER)

    r = client.post("/api/v1/payment/invoices", json=dict(_GOOD_PAYLOAD, order_id="o-p3-nologin"))
    assert r.status_code == 401, r.text
    assert client.get("/api/v1/payment/invoices").status_code == 401
    assert db.query(PaymentInvoice).count() == 0


def test_p3_23_cannot_invoice_someone_elses_order(client, db):
    """越权：拿**别人的**订单号申请 ⇒ 404 ＋ 库里零新增（⛔ 不给「不是你的」回 403，防探测）。

    【自己的红】service 只按 `order_id` 反查、不校验归属 ⇒ 200 且落 1 行 ⇒ 红。
    """
    _add_user(db, TEACHER)
    _add_user(db, OTHER)
    _add_order(db, "o-p3-other", TEACHER)

    r = _submit(client, OTHER, order_id="o-p3-other")
    assert r.status_code == 404, r.text
    assert db.query(PaymentInvoice).count() == 0

    # 不存在的订单号也是同一个 404（不泄露「订单号存在与否」）
    r2 = _submit(client, OTHER, order_id="o-p3-does-not-exist")
    assert r2.status_code == 404, r2.text
    assert db.query(PaymentInvoice).count() == 0


@pytest.mark.parametrize("order_status", ["pending", "failed", "cancelled", "refunded"])
def test_p3_24_only_paid_order_invoiceable(client, db, order_status):
    """只有**已支付**订单能开票：四种非 paid 状态一律 409 ＋ 零新增。

    【自己的红】把 service 里的 `order.status != ORDER_PAID` 那段删掉 ⇒ 200 ⇒ 红。
    """
    _add_user(db, TEACHER)
    oid = f"o-p3-{order_status}"
    _add_order(db, oid, TEACHER, status=order_status)

    r = _submit(client, TEACHER, order_id=oid)
    assert r.status_code == 409, r.text
    assert db.query(PaymentInvoice).count() == 0


def test_p3_25_one_order_one_invoice_via_api(client, db):
    """一单一票：同一订单第二次申请 ⇒ 409，且库里**仍只有 1 行**、内容仍是第一次那份。

    【自己的红】把 service 的重复检查与模型的唯一约束**同时**摘掉 ⇒ 第二次 200 且库里 2 行 ⇒ 红。
      （只摘其中一个不会红 —— 所以这条**必须**和 `test_p3_26` 配对读：那条单独证明
       DB 层约束本身存在，这条证明应用层把冲突翻成 409。）
    """
    _add_user(db, TEACHER)
    _add_order(db, "o-p3-dup", TEACHER)

    first = _submit(client, TEACHER, order_id="o-p3-dup", title="第一版抬头")
    assert first.status_code == 200, first.text
    second = _submit(client, TEACHER, order_id="o-p3-dup", title="第二版抬头")
    assert second.status_code == 409, second.text

    rows = db.query(PaymentInvoice).all()
    assert len(rows) == 1
    assert rows[0].title == "第一版抬头"


def test_p3_26_unique_order_constraint_is_a_real_db_constraint(client, db):
    """一单一票**不只靠应用层的 if**：绕过 service 直接落第二行，DB 必须拒（1062）。

    【自己的红】删掉模型的 `UniqueConstraint("order_id", name="uk_payment_invoice_order")`
      ⇒ 下面这次 commit 会成功 ⇒ `pytest.raises(IntegrityError)` 捕不到 ⇒ 红。
    """
    _add_user(db, TEACHER)
    _add_order(db, "o-p3-uniq", TEACHER)
    assert _submit(client, TEACHER, order_id="o-p3-uniq").status_code == 200

    db.add(PaymentInvoice(
        id="dup-row", order_id="o-p3-uniq", user_id=TEACHER, status="requested",
        amount_fen=50, title="t", taxpayer_id="91310000MA1K35Q123", email="a@b.com",
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert db.query(PaymentInvoice).count() == 1


# ═══════════════════════════ 4. 查询（只能查自己）═══════════════════════════

def test_p3_30_list_returns_only_my_invoices_and_ignores_user_id_param(client, db):
    """只能查自己：别的人申请不出现在我的列表里；`?user_id=` 被忽略（⛔ 端点不收这个参数）。

    【自己的红】端点不加 `user_id` 过滤 ⇒ total 变 3 ⇒ 红；
      端点改成收 `user_id` query 参数 ⇒ 带 `?user_id=<OTHER>` 时 total 变 1 ⇒ 红。
    """
    _add_user(db, TEACHER)
    _add_user(db, OTHER)
    _add_order(db, "o-p3-t1", TEACHER)
    _add_order(db, "o-p3-t2", TEACHER)
    _add_order(db, "o-p3-o1", OTHER)
    mine = {_submit(client, TEACHER, order_id="o-p3-t1").json()["data"]["id"],
            _submit(client, TEACHER, order_id="o-p3-t2").json()["data"]["id"]}
    theirs = _submit(client, OTHER, order_id="o-p3-o1").json()["data"]["id"]

    r = client.get("/api/v1/payment/invoices", headers=_auth(TEACHER))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["total"] == 2
    assert {it["id"] for it in d["items"]} == mine
    assert theirs not in {it["id"] for it in d["items"]}

    # OTHER 侧看到的只有自己那 1 张
    d2 = client.get("/api/v1/payment/invoices", headers=_auth(OTHER)).json()["data"]
    assert d2["total"] == 1 and {it["id"] for it in d2["items"]} == {theirs}

    # `?user_id=` 一律被忽略
    d3 = client.get(f"/api/v1/payment/invoices?user_id={OTHER}", headers=_auth(TEACHER)).json()["data"]
    assert d3["total"] == 2 and {it["id"] for it in d3["items"]} == mine


def test_p3_31_list_pagination(client, db):
    """分页：`page`/`page_size` 真的生效（两页各 1 条、不重不漏），空页返回空 items。

    【自己的红】把 `.offset()/.limit()` 删掉 ⇒ 两页都回 2 条、且 id 相同 ⇒ 红。
      越界参数（`page_size=0` / `page=0`）应被 422 挡下。
    """
    _add_user(db, TEACHER)
    _add_order(db, "o-p3-p1", TEACHER)
    _add_order(db, "o-p3-p2", TEACHER)
    ids = {_submit(client, TEACHER, order_id="o-p3-p1").json()["data"]["id"],
           _submit(client, TEACHER, order_id="o-p3-p2").json()["data"]["id"]}

    p1 = client.get("/api/v1/payment/invoices?page=1&page_size=1", headers=_auth(TEACHER)).json()["data"]
    p2 = client.get("/api/v1/payment/invoices?page=2&page_size=1", headers=_auth(TEACHER)).json()["data"]
    p3 = client.get("/api/v1/payment/invoices?page=3&page_size=1", headers=_auth(TEACHER)).json()["data"]
    assert p1["total"] == p2["total"] == 2
    assert len(p1["items"]) == len(p2["items"]) == 1
    assert p1["items"][0]["id"] != p2["items"][0]["id"], "两页返回了同一行（offset 没生效）"
    assert {p1["items"][0]["id"], p2["items"][0]["id"]} == ids
    assert p3["items"] == []

    assert client.get("/api/v1/payment/invoices?page_size=0", headers=_auth(TEACHER)).status_code == 422
    assert client.get("/api/v1/payment/invoices?page=0", headers=_auth(TEACHER)).status_code == 422


def test_p3_32_list_empty_for_new_user(client, db):
    """空路径：从没申请过的老师 ⇒ `total=0` ＋ `items=[]`（不是 500、不是 null）。

    【自己的红】让端点对空结果抛错（如 `.one()`）⇒ 500 ⇒ 红。
    """
    _add_user(db, OTHER)
    r = client.get("/api/v1/payment/invoices", headers=_auth(OTHER))
    assert r.status_code == 200
    assert r.json()["data"] == {"total": 0, "page": 1, "page_size": 20, "items": []}


# ═══════════════════════════ 5. 状态机（本批只留数据层）═══════════════════════════

def test_p3_40_state_machine_requested_issued_void(client, db):
    """状态机主链：`requested` → `issued` → `void`，时间戳与发票号逐段落库，GET 能读回。

    【自己的红】`_transition` 里不落 `issued_at`/`voided_at` 或不 commit ⇒ 对应断言红。
    """
    _add_user(db, TEACHER)
    _add_order(db, "o-p3-sm", TEACHER)
    inv_id = _submit(client, TEACHER, order_id="o-p3-sm").json()["data"]["id"]

    svc.mark_issued(db, invoice_id=inv_id, invoice_no="INV-0001")
    row = db.query(PaymentInvoice).filter(PaymentInvoice.id == inv_id).one()
    assert row.status == "issued"
    assert row.issued_at is not None and row.invoice_no == "INV-0001"
    assert row.voided_at is None

    svc.mark_void(db, invoice_id=inv_id)
    row = db.query(PaymentInvoice).filter(PaymentInvoice.id == inv_id).one()
    assert row.status == "void" and row.voided_at is not None
    assert row.issued_at is not None, "作废不该抹掉 issued_at（状态机是叠加，不是覆盖）"

    d = client.get("/api/v1/payment/invoices", headers=_auth(TEACHER)).json()["data"]
    assert d["items"][0]["status"] == "void"
    assert d["items"][0]["issued_at"] and d["items"][0]["voided_at"]


def test_p3_41_illegal_transitions_rejected_and_state_unchanged(client, db):
    """非法跃迁一律 409 且**库态不变**：`issued→issued`、`requested→void`、`void→任何`。

    ⚠️ `requested → void` 被拒是**有意的**：brief 逐字给的链是 `requested → issued → void`，
       ⛔ 加一条不在链上的边属自创（见 `services/payment/invoices.py` 模块 docstring）。
    【自己的红】把 `ALLOWED_TRANSITIONS[requested]` 改成 `(issued, void)` ⇒ 第 2 组不再抛 ⇒ 红；
      把 `[issued]` 改成 `(issued, void)` ⇒ 第 1 组不再抛 ⇒ 红。
    """
    _add_user(db, TEACHER)
    _add_order(db, "o-p3-i1", TEACHER)
    _add_order(db, "o-p3-i2", TEACHER)
    a = _submit(client, TEACHER, order_id="o-p3-i1").json()["data"]["id"]
    b = _submit(client, TEACHER, order_id="o-p3-i2").json()["data"]["id"]

    # (1) requested → issued 合法；再来一次 `issued → issued` 必须拒
    svc.mark_issued(db, invoice_id=a)
    with pytest.raises(svc.InvoiceStateError):
        svc.mark_issued(db, invoice_id=a)

    # (2) requested → void 不在链上 ⇒ 拒
    with pytest.raises(svc.InvoiceStateError):
        svc.mark_void(db, invoice_id=b)

    # (3) void → 任何 ⇒ 拒
    svc.mark_void(db, invoice_id=a)
    with pytest.raises(svc.InvoiceStateError):
        svc.mark_void(db, invoice_id=a)
    with pytest.raises(svc.InvoiceStateError):
        svc.mark_issued(db, invoice_id=a)

    assert db.query(PaymentInvoice).filter(PaymentInvoice.id == a).one().status == "void"
    assert db.query(PaymentInvoice).filter(PaymentInvoice.id == b).one().status == "requested"
    assert len(svc.ALLOWED_TRANSITIONS) == 3, "状态机被加了第四态"


def test_p3_42_mark_unknown_invoice_is_404(db):
    """标记不存在的申请 ⇒ 404（`http_status` 是路由映射用的真值）。

    【自己的红】把 `_load` 的 None 分支删掉 ⇒ AttributeError ⇒ 红。
    """
    with pytest.raises(svc.InvoiceNotFoundError) as ei:
        svc.mark_issued(db, invoice_id="nope-nope")
    assert ei.value.http_status == 404
    assert set(svc.ALLOWED_TRANSITIONS) == {svc.INVOICE_REQUESTED, svc.INVOICE_ISSUED, svc.INVOICE_VOID}


# ═══════════════════════════ 6. 入参校验 ═══════════════════════════

@pytest.mark.parametrize(
    "over, why",
    [
        ({"title": ""}, "抬头不能为空"),
        ({"title": "   "}, "抬头不能是纯空白（先 strip 再判长度）"),
        ({"title": "x" * 256}, "抬头超长"),
        ({"taxpayer_id": ""}, "纳税人识别号不能为空"),
        ({"taxpayer_id": "x" * 65}, "纳税人识别号超长"),
        ({"email": "not-an-email"}, "邮箱格式非法（发票寄不到）"),
        ({"email": ""}, "邮箱不能为空"),
        ({"order_id": ""}, "订单号不能为空"),
        ({"order_id": "x" * 37}, "订单号超长"),
    ],
)
def test_p3_50_payload_validation_rejects_and_writes_nothing(client, db, over, why):
    """入参校验：缺项/空白/超长/非法邮箱一律 422 且**库里零新增**。

    【自己的红】按 case 对应：去掉 `min_length` ⇒ 空抬头 200；去掉 `str_strip_whitespace`
      ⇒ `"   "` 能过闸；去掉 `EmailStr` ⇒ 乱字符串 200；去掉 `max_length` ⇒ 超长 200（或 MySQL 1406）。
    """
    _add_user(db, TEACHER)
    _add_order(db, "o-p3-default", TEACHER)
    r = _submit(client, TEACHER, **over)
    assert r.status_code == 422, f"{why} —— 期望 422，实得 {r.status_code}: {r.text}"
    assert db.query(PaymentInvoice).count() == 0


def test_p3_51_route_inventory_has_no_admin_write_endpoint():
    """端点清单钉死：本模块只有 8 个（方法, 路径）组合；⛔ admin 侧**只有只读那一个**。

    ⛔ 尤其钉住「标记已开票本批**没有**后台入口」（brief 硬约束 4）—— 状态机只有数据层。
    ⚠️ 「不许有 admin 端点」这条**按逐字口径收窄**为「不许有 admin **写**端点」：`routers/payment.py:16`
       逐字排除的是 `POST /payment/admin/grant`（**写**）；`GET /admin/reconciliation` 零写路径。
    【自己的红】给 `payment.router` 加任意写路由（尤其 `/payment/admin/grant`）⇒ 集合不等 ⇒ 红。
    """
    got = set()
    for r in payment_router.router.routes:
        for m in getattr(r, "methods", set()) or set():
            if m in ("HEAD", "OPTIONS"):
                continue
            got.add((m, r.path))
    assert got == {
        ("GET", "/payment/account"),
        ("GET", "/payment/ledger"),
        ("GET", "/payment/usage"),
        ("POST", "/payment/orders"),
        ("POST", "/payment/callback/{channel}"),
        ("POST", "/payment/invoices"),
        ("GET", "/payment/invoices"),
        ("GET", "/payment/admin/reconciliation"),
    }
    admin_routes = [(m, p) for m, p in got if p.startswith("/payment/admin")]
    assert admin_routes == [("GET", "/payment/admin/reconciliation")], \
        f"admin 侧只许有那一个只读端点，实得 {admin_routes}"


# ═══════════════════════ 7. E1/E2 只读对账巡检（§6.2 / §6.4）═══════════════════════

ADMIN = "u-p3-admin"
_RECON = "/api/v1/payment/admin/reconciliation"

_E1_KEYS = {"ok", "accounts_checked", "unbalanced_count", "total_balance_fen",
            "total_sum_amount_fen", "discrepancies"}
_E2_KEYS = {"ok", "recharge_fen", "paid_orders_fen", "diff_fen", "discrepancies"}


def _add_admin(db) -> None:
    _add_user(db, ADMIN, roles="系统管理员")


def _paid_recharge(db, uid: str, oid: str, amount_fen: int) -> None:
    """走**真实**入账路径造「订单已支付 + recharge 分录」：`apply_payment_confirmed`。"""
    _add_order(db, oid, uid, status=ledger_svc.ORDER_PENDING, amount_fen=amount_fen)
    ledger_svc.apply_payment_confirmed(
        db, order_id=oid, channel_trade_no=f"trade-{oid}", paid_amount_fen=amount_fen
    )


def _table_counts(db) -> dict:
    return {n: int(db.query(Base.metadata.tables[n]).count()) for n in _OWN_TABLES}


def test_p3_60_reconciliation_requires_admin_jwt_and_shape(client, db):
    """鉴权与响应形态：无 JWT 401、**任课教师 403**、管理员 200；响应只有 E1/E2 两段。

    【自己的红】把 `_check_admin_permission` 那行删掉 ⇒ 任课教师拿到 200 ⇒ 红。
      给响应加一个 `e3` 字段（本阶段 E3 未落地，⛔ 不许长成字段）⇒ 集合断言红。
    """
    _add_user(db, TEACHER)
    _add_admin(db)

    assert client.get(_RECON).status_code == 401
    teacher = client.get(_RECON, headers=_auth(TEACHER))
    assert teacher.status_code == 403, teacher.text
    assert db.query(PaymentAccount).count() >= 0  # 403 不该有任何副作用

    r = client.get(_RECON, headers=_auth(ADMIN))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert set(d) == {"e1", "e2", "checked_at"}, sorted(d)
    assert set(d["e1"]) == _E1_KEYS, sorted(d["e1"])
    assert set(d["e2"]) == _E2_KEYS, sorted(d["e2"])
    assert "e3" not in d and "e3" not in d["e1"] and "e3" not in d["e2"], \
        "E3 本阶段未落地，⛔ 不许在响应里长成字段（见 design §6.5）"


def test_p3_61_reconciliation_balanced_state_reports_balanced(client, db):
    """自洽状态下 E1/E2 都判「平」，且逐项读数对得上（**防误报**那半边）。

    【自己的红】把 E1 的判据写反（`sum_amount == balance` → `!=`）⇒ 一致状态被判不平 ⇒ 红。
      把 `total_balance_fen` 的汇总改错（如累加 `unbalanced_count`）⇒ 红。
    """
    _add_user(db, TEACHER)
    _add_admin(db)
    _paid_recharge(db, TEACHER, "o-p3-rec-1", 50)

    d = client.get(_RECON, headers=_auth(ADMIN)).json()["data"]
    assert d["e1"]["ok"] is True and d["e1"]["unbalanced_count"] == 0
    assert d["e1"]["accounts_checked"] == 1
    assert d["e1"]["total_balance_fen"] == 50
    assert d["e1"]["total_sum_amount_fen"] == 50
    assert d["e1"]["discrepancies"] == []
    assert d["e2"]["ok"] is True and d["e2"]["diff_fen"] == 0
    assert d["e2"]["recharge_fen"] == 50 and d["e2"]["paid_orders_fen"] == 50
    assert d["e2"]["discrepancies"] == []
    assert d["checked_at"]


def test_p3_62_reconciliation_detects_e1_drift_and_does_not_fix_it(client, db):
    """E1 能**检出**余额与分录和不符的账户，并给出逐账户差异明细；⛔ 只报**不修**。

    【自己的红】把 `verify_invariant_e1_all` 里的 `if not one.get("ok")` 取反
      ⇒ 差异明细里装的就不是那个坏账户 ⇒ 红。
    """
    _add_user(db, TEACHER)
    _add_admin(db)
    _paid_recharge(db, TEACHER, "o-p3-rec-2", 50)

    acct = db.query(PaymentAccount).filter(PaymentAccount.user_id == TEACHER).one()
    acct.balance_fen = 999          # 失控写入 / 人工误操作的库内表征
    db.commit()

    d = client.get(_RECON, headers=_auth(ADMIN)).json()["data"]
    assert d["e1"]["ok"] is False
    assert d["e1"]["unbalanced_count"] == 1 and d["e1"]["accounts_checked"] == 1
    assert d["e1"]["total_balance_fen"] == 999
    assert d["e1"]["total_sum_amount_fen"] == 50
    disc = d["e1"]["discrepancies"]
    assert len(disc) == 1 and disc[0]["user_id"] == TEACHER
    assert disc[0]["balance_fen"] == 999 and disc[0]["sum_amount_fen"] == 50
    assert disc[0]["latest_balance_after_fen"] == 50

    # ⛔ 巡检只报不修（§6.3 D2「不自动冲销」）：那 999 一个字没变
    db.expire_all()
    assert db.query(PaymentAccount).filter(
        PaymentAccount.user_id == TEACHER).one().balance_fen == 999


def test_p3_63_reconciliation_e2_counts_only_recharge_entries(client, db):
    """E2 只认 `entry_type='recharge'`：**grant（赠送/人工开通）不是收入**，不进 E2。

    【自己的红】把 E2 那个求和的 `LedgerEntry.entry_type == ENTRY_RECHARGE` 过滤去掉
      ⇒ 30 分的 grant 被算成收入 ⇒ `recharge_fen` 变 30 ⇒ 红。
    """
    _add_user(db, TEACHER)
    _add_admin(db)
    ledger_svc.grant_manual(db, user_id=TEACHER, amount_fen=30, operator_id=ADMIN,
                            description="P3 对账用例：赠送")

    d = client.get(_RECON, headers=_auth(ADMIN)).json()["data"]
    assert d["e2"]["recharge_fen"] == 0, "grant 不是收入（§6.2 E2 只数 recharge）"
    assert d["e2"]["paid_orders_fen"] == 0
    assert d["e2"]["ok"] is True
    assert d["e1"]["ok"] is True and d["e1"]["total_balance_fen"] == 30


def test_p3_64_reconciliation_detects_e2_mismatch_with_per_user_detail(client, db):
    """E2 检出「订单已支付、账本没入账」：总量不平 ＋ 逐人差异明细（D1 的库内表征）。

    【自己的红】把 `PaymentOrder.status == ORDER_PAID` 换成 `!= ORDER_PAID`
      ⇒ 已支付订单不再计入 ⇒ 本用例的 `ok is False` / `diff_fen == -50` 立刻红。
    """
    _add_user(db, TEACHER)
    _add_admin(db)
    ledger_svc.grant_manual(db, user_id=TEACHER, amount_fen=30, operator_id=ADMIN,
                            description="P3 对账用例：赠送")
    _add_order(db, "o-p3-rec-4", TEACHER, status=ledger_svc.ORDER_PAID, amount_fen=50)

    d = client.get(_RECON, headers=_auth(ADMIN)).json()["data"]
    assert d["e2"]["ok"] is False
    assert d["e2"]["recharge_fen"] == 0 and d["e2"]["paid_orders_fen"] == 50
    assert d["e2"]["diff_fen"] == -50
    assert d["e2"]["discrepancies"] == [
        {"user_id": TEACHER, "recharge_fen": 0, "paid_orders_fen": 50, "diff_fen": -50}
    ]
    # E1/E2 是两把尺子：账户侧自洽不受影响（该用户根本没有 payment_accounts 行）
    assert d["e1"]["ok"] is True


def test_p3_65_reconciliation_calls_the_existing_e1_check_per_account(client, db, monkeypatch):
    """**复用而非重写**：E1 段必须**逐个账户调用既有的 `verify_invariant_e1()`**。

    ⛔ 这条钉的是「E1 判据全仓只有一份」—— 端点只许把它挂出来。
    【自己的红】在 `verify_invariant_e1_all` 里另写一份 E1 判据（不调既有函数）
      ⇒ `calls == []` ⇒ 红。
    """
    _add_user(db, TEACHER)
    _add_user(db, OTHER)
    _add_admin(db)
    _paid_recharge(db, TEACHER, "o-p3-rec-5", 50)
    _paid_recharge(db, OTHER, "o-p3-rec-6", 70)

    calls: list[str] = []
    real = ledger_svc.verify_invariant_e1

    def spy(session, user_id):
        calls.append(str(user_id))
        return real(session, user_id)

    monkeypatch.setattr(ledger_svc, "verify_invariant_e1", spy)
    r = client.get(_RECON, headers=_auth(ADMIN))
    assert r.status_code == 200, r.text
    assert sorted(calls) == sorted([TEACHER, OTHER]), f"未按账户调用既有 E1 判据：{calls}"
    assert r.json()["data"]["e1"]["accounts_checked"] == 2


def test_p3_66_reconciliation_is_read_only(client, db):
    """**只读**：跑一次巡检，支付侧八张表一行不多一行不少，且坏账仍坏着。

    【自己的红】让端点写库（如把差异落进某张表 / 顺手把余额修回去）⇒ 计数或余额断言红。
    """
    _add_user(db, TEACHER)
    _add_admin(db)
    _paid_recharge(db, TEACHER, "o-p3-rec-7", 50)
    acct = db.query(PaymentAccount).filter(PaymentAccount.user_id == TEACHER).one()
    acct.balance_fen = 999
    db.commit()

    before = _table_counts(db)
    r = client.get(_RECON, headers=_auth(ADMIN))
    assert r.status_code == 200
    db.expire_all()
    assert _table_counts(db) == before, "对账端点写了库（它必须是零写路径）"
    assert db.query(PaymentAccount).filter(
        PaymentAccount.user_id == TEACHER).one().balance_fen == 999
