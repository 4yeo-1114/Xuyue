# -*- coding: utf-8 -*-
"""独立老师支付系统 Phase 0（P0-1..P0-6）· 仓内回归测试。

判据逐条取自 docs/payment/payment-design.md §9「Phase 0」表的「验收（可判定）」列。

覆盖：
  P0-1  6 张表 + models/__init__ 注册 + database._ensure_payment_tables 存在且挂在无条件段
  P0-2  账本核心：I1 幂等（同键只落 1 行）/ I2 扣穿被拒 / I3 SUM(amount)==balance
  P0-3  计量：1 学生 3 图 ⇒ 恰 1 条 delta=+1；删除 ⇒ 恰 1 条 delta=-1；重复投递 ⇒ 无新行
  P0-4  net-diff：批改→删除→再批改 ⇒ 2 条负额 + 1 条冲正，SUM 对应 1 份净额
  P0-5  批改入口闸门 402（走真实 FastAPI 路由）+ 已在跑的批改不被中断
  P0-6  只读账单投影 /payment/account|ledger|usage（分页、code/message/data、错误走 detail）

测试方式：**真 SQLite 内存库**（真执行 SQL，唯一索引/WHERE 真实生效 —— 不用「假 db」，
否则「同键只落 1 行」这类断言会被假 db 蒙混过关）+ 真实 FastAPI TestClient 走路由。

⚠️ 必须在 import 任何 `app.*` 之前 `AUTO_DDL=false`（本机 backend/.env 里是 AUTO_DDL=true，
   import 期就会去连库 ⇒ collection 挂）。照 test_e09_field_masking 等既有 5 个文件的约定，
   ⛔ 不依赖 conftest。
"""
import os

os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "13307")
os.environ.setdefault("DB_USER", "root")
os.environ.setdefault("DB_PASSWORD", "root_pw_2026")
os.environ.setdefault("DB_NAME", "grade_payment_p0_test")
os.environ.setdefault("JWT_SECRET_KEY", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("AUTO_DDL", "false")
os.environ.setdefault("DASHSCOPE_API_KEY", "sk-p0-test-not-real")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, func  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.dependencies import get_current_user_id  # noqa: E402
from app.models.ledger_entry import LedgerEntry  # noqa: E402
from app.models.payment_account import PaymentAccount  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.usage_event import UsageEvent  # noqa: E402
from app.services.payment import ledger as L  # noqa: E402
from app.services.payment import metering as M  # noqa: E402
from app.services.payment import pricing as P  # noqa: E402

TEACHER = "u-p0-teacher"     # 仅任课教师（独立老师）
TEACHER0 = "u-p0-zero"       # 仅任课教师，余额 0
COMBO = "u-p0-combo"         # 任课教师 + 班主任（非「仅任课教师」）
FOLDER = "f_p0"
UNIT = P.unit_price_fen("grade")


@pytest.fixture()
def sqlite_env(monkeypatch):
    """真 SQLite 内存库 + 把 grading_stats / metering 的 SessionLocal 指向它。

    ⛔ 不 mock 任何断言对象：唯一索引、SUM、行锁语句都是真跑的。
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    import app.grading.grading_stats as GS

    monkeypatch.setattr(GS, "SessionLocal", TestSession)
    monkeypatch.setattr(M, "SessionLocal", TestSession)
    # 批改计费闸门（`grading/router.py::_payment_gate_or_402`）在函数体内
    # `from app.database import SessionLocal` 取会话 ⇒ 必须连它一起指向测试库，
    # 否则闸门会去打真 MySQL（本机 3306 无库）⇒ 撞上「闸门故障放行」而**测不到 402**。
    import app.database as _DB

    monkeypatch.setattr(_DB, "SessionLocal", TestSession)

    db = TestSession()
    for uid, roles in ((TEACHER, "任课教师"), (TEACHER0, "任课教师"),
                       (COMBO, "任课教师,班主任")):
        db.add(User(id=uid, email=f"{uid}@p0.test", display_name=uid,
                    password_hash="x", roles=roles))
    db.commit()
    try:
        yield TestSession, db
    finally:
        db.close()
        engine.dispose()


def _count(db, model, *crit):
    return int(db.query(func.count()).select_from(model).filter(*crit).scalar() or 0)


# ─────────────────────────── P0-1 ───────────────────────────

def test_p0_1_six_payment_models_registered():
    """6 张支付表模型已注册进 Base.metadata，且 models.__all__ 收口。"""
    import app.models as models_pkg

    expected = {
        "payment_accounts", "usage_events", "ledger_entries",
        "payment_plans", "subscriptions", "payment_orders",
    }
    assert expected <= set(Base.metadata.tables.keys()), (
        f"未注册的表: {sorted(expected - set(Base.metadata.tables.keys()))}"
    )
    for cls in ("PaymentAccount", "UsageEvent", "LedgerEntry",
                "PaymentPlan", "Subscription", "PaymentOrder"):
        assert cls in models_pkg.__all__, f"{cls} 未进 __all__"
        assert hasattr(models_pkg, cls)


def test_p0_1_ensure_payment_tables_hooked_into_unconditional_section():
    """`_ensure_payment_tables` 必须挂在 `init_db()` 的**无条件段**。

    判据（照 D-1 事故）：它的调用行必须出现在 `init_db()` 函数体内、
    ⛔ 不得出现在 `sync_database_schema()` 的 `if not AUTO_DDL: return` 之后。
    """
    import ast
    import inspect

    import app.database as dbmod

    def _code_only(fn) -> str:
        """剥掉 docstring / 注释，只留**可执行代码**（否则文档里提到的 AUTO_DDL 会误判）。"""
        tree = ast.parse(inspect.getsource(fn))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
                body = list(getattr(node, "body", []))
                if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)                         and isinstance(body[0].value.value, str):
                    node.body = body[1:] or [ast.Pass()]
        return ast.unparse(tree)

    src = inspect.getsource(dbmod)
    init_code = _code_only(dbmod.init_db)
    sync_code = _code_only(dbmod.sync_database_schema)
    ensure_code = _code_only(dbmod._ensure_payment_tables)

    assert "_ensure_payment_tables()" in init_code, "init_db() 未调用 _ensure_payment_tables()"
    assert init_code.index("_ensure_payment_tables()") > init_code.index("_ensure_flow_tables()"), (
        "必须与 _ensure_flow_tables 并列在无条件段尾部"
    )
    # sync_database_schema() 的可执行代码第 1 条就是 `if not AUTO_DDL: return`
    assert "AUTO_DDL" in sync_code
    assert sync_code.index("AUTO_DDL") < sync_code.index("_ensure_payment_tables()")         if "_ensure_payment_tables()" in sync_code else True
    # 生产默认 AUTO_DDL=false 时无条件段仍要执行 ⇒ 该函数自身不得依赖 AUTO_DDL
    assert "AUTO_DDL" not in ensure_code, "_ensure_payment_tables 不得依赖 AUTO_DDL"
    assert src.count("def _ensure_payment_tables") == 1


# ─────────────────────────── P0-2 ───────────────────────────

def test_p0_2_i1_idempotent_same_key_single_row(sqlite_env):
    """I1：同一幂等键重复记账**只落 1 行**（DB 层唯一索引，不靠应用层 if）。"""
    TestSession, db = sqlite_env
    e1, created1 = L.post_entry(db, user_id=TEACHER, entry_type=L.ENTRY_GRANT,
                                amount_fen=1000, idempotency_key="k-dup",
                                description="首次")
    e2, created2 = L.post_entry(db, user_id=TEACHER, entry_type=L.ENTRY_GRANT,
                                amount_fen=1000, idempotency_key="k-dup",
                                description="重复")
    assert created1 is True and created2 is False
    assert e1.id == e2.id
    assert _count(db, LedgerEntry, LedgerEntry.idempotency_key == "k-dup") == 1
    acct = db.query(PaymentAccount).filter(PaymentAccount.user_id == TEACHER).one()
    assert int(acct.balance_fen) == 1000, "重复记账不得把余额加两次"


def test_p0_2_i1_idempotent_through_unique_index_not_app_layer(sqlite_env):
    """I1 的强制手段必须是**数据库唯一索引**：绕过应用层前置查询仍只落 1 行。

    直接发两条同键 INSERT（跳过 post_entry 的快路径），断言 DB 层抛 IntegrityError。
    ⚠️ 两条必须**分属两个事务**：同一事务里连插两条，失败后 `rollback()` 会把第一条也一起回滚
    （实测 count==0），那样测到的是「事务回滚」而不是「唯一索引」。
    """
    from sqlalchemy.exc import IntegrityError

    TestSession, db = sqlite_env
    acct = L.get_or_create_account(db, TEACHER)
    db.add(LedgerEntry(account_id=acct.id, entry_type=L.ENTRY_ADJUST, amount_fen=1,
                       balance_after_fen=1, idempotency_key="k-index"))
    db.commit()          # 第一条独立事务落库
    db.add(LedgerEntry(account_id=acct.id, entry_type=L.ENTRY_ADJUST, amount_fen=1,
                       balance_after_fen=1, idempotency_key="k-index"))
    with pytest.raises(IntegrityError):
        db.commit()      # 第二条同键 ⇒ 被 DB 唯一索引拒绝
    db.rollback()
    assert _count(db, LedgerEntry, LedgerEntry.idempotency_key == "k-index") == 1


def test_p0_2_i2_overdraft_rejected(sqlite_env):
    """I2：余额不足**必须被拒**，而不是扣成负数。"""
    TestSession, db = sqlite_env
    L.post_entry(db, user_id=TEACHER, entry_type=L.ENTRY_GRANT, amount_fen=100,
                 idempotency_key="k-bal")
    with pytest.raises(L.InsufficientBalanceError):
        L.post_entry(db, user_id=TEACHER, entry_type=L.ENTRY_CONSUME, amount_fen=-101,
                     idempotency_key="k-over")
    acct = db.query(PaymentAccount).filter(PaymentAccount.user_id == TEACHER).one()
    assert int(acct.balance_fen) == 100
    assert int(acct.balance_fen) >= 0
    assert _count(db, LedgerEntry, LedgerEntry.idempotency_key == "k-over") == 0


def test_p0_2_i3_sum_amount_equals_balance(sqlite_env):
    """I3：`SUM(amount_fen) == balance_fen`，且最新一行 `balance_after_fen` == 余额。"""
    TestSession, db = sqlite_env
    L.post_entry(db, user_id=TEACHER, entry_type=L.ENTRY_GRANT, amount_fen=500,
                 idempotency_key="k-1")
    L.post_entry(db, user_id=TEACHER, entry_type=L.ENTRY_CONSUME, amount_fen=-120,
                 idempotency_key="k-2")
    L.post_entry(db, user_id=TEACHER, entry_type=L.ENTRY_CONSUME, amount_fen=-80,
                 idempotency_key="k-3")
    result = L.verify_invariant_e1(db, TEACHER)
    assert result["ok"] is True, result
    assert result["balance_fen"] == 300
    assert result["sum_amount_fen"] == 300
    assert result["latest_balance_after_fen"] == 300


# ─────────────────────────── P0-3 ───────────────────────────

class _TransitionStub:
    """可控的「学生是否已批改」判定桩。

    ⚠️ `record_graded_state_change` 对同一学生**连续两次**调用该判定（先「旧态」再「新态」），
    故桩必须按序吐出两个不同的值；固定返回同一个值会让 `was == now` 恒成立、
    跃迁永远判不出（本批真踩过这个坑，P0-3/P0-4 因此全红）。
    """

    def __init__(self):
        self.seq = []

    def set(self, was: bool, now: bool):
        self.seq = [was, now]

    def __call__(self, folder_safe, student_key, **kw):
        return self.seq.pop(0) if self.seq else False


@pytest.fixture()
def grade_ctx(sqlite_env, monkeypatch):
    """把「学生是否已批改」的判定换成可控桩，其余（写库/计量）全走真路径。"""
    import app.grading.grading_stats as GS

    stub = _TransitionStub()
    monkeypatch.setattr(GS, "_student_group_shows_graded", stub)
    return stub


ENTRY_A = {"name": "张三_1.jpg", "result": "总题量：2；已批改：2；批改中：0", "score": 88}
ENTRY_B = {"name": "张三_2.jpg", "result": "总题量：2；已批改：2；批改中：0", "score": 88}
ENTRY_C = {"name": "张三_1.jpg", "result": "总题量：3；已批改：3；批改中：0", "score": 92}


def _grade_events(db):
    return db.query(UsageEvent).filter(UsageEvent.user_id == TEACHER,
                                       UsageEvent.kind == "grade").all()


def test_p0_3_batch_three_images_yields_one_event(sqlite_env, grade_ctx):
    """批量批改 1 个学生 3 张图 ⇒ **恰 1 条** usage_events(delta=+1)。"""
    import app.grading.grading_stats as GS

    TestSession, db = sqlite_env
    grade_ctx.set(False, True)
    grade_ctx.set(False, True)   # 第 1 张：0→1 跃迁 ⇒ 计 1 份
    GS.record_graded_state_change(TEACHER, FOLDER, None, ENTRY_A, source="ref", filename="张三_1.jpg")
    grade_ctx.set(True, True)    # 第 2 张：已是已批改 ⇒ 不计
    GS.record_graded_state_change(TEACHER, FOLDER, ENTRY_A, ENTRY_B, source="ref", filename="张三_2.jpg")
    grade_ctx.set(True, True)    # 第 3 张：已是已批改 ⇒ 不计
    GS.record_graded_state_change(TEACHER, FOLDER, ENTRY_B, ENTRY_B, source="ref", filename="张三_3.jpg")
    evs = _grade_events(db)
    assert len(evs) == 1, f"期望恰 1 条事件，实得 {[int(e.delta) for e in evs]}"
    assert int(evs[0].delta) == 1
    assert evs[0].subject_key == "张三"
    assert evs[0].folder_safe == FOLDER


def test_p0_3_l1_same_event_uid_swallowed_by_unique_index(sqlite_env):
    """L1 的真判据：**同一 event_uid 二次投递**必须被 `uk_usage_event_uid` 吞掉。

    ⚠️ 为什么单独写一条（红实验发现）：走 `record_graded_state_change` 的「重复投递」
    （下一条用例）测的是**跃迁判定** —— was==now 时它**根本不调用** `emit_usage_event`，
    重复从没送到 L1 ⇒ 把唯一索引摘掉它照样绿。故此处**直投** `emit_usage_event`，
    并用 `kind="upload"`（默认不计费、也不受 grade 净额上界约束）⇒ 这条变红只能由 L1 造成。
    """
    TestSession, db = sqlite_env
    kw = dict(user_id=TEACHER0, kind="upload", folder_safe="f_l1", subject_key="s1",
              delta=1, occurrence="dup", run_ledger=False)
    assert M.emit_usage_event(**kw) is True, "首次投递应落行"
    assert M.emit_usage_event(**kw) is False, "同一 event_uid 二次投递应被唯一索引吞掉"
    rows = db.query(UsageEvent).filter(UsageEvent.user_id == TEACHER0,
                                       UsageEvent.kind == "upload").all()
    assert len(rows) == 1, f"期望只落 1 行，实得 {len(rows)}"


def test_p0_3_repeat_delivery_no_new_row(sqlite_env, grade_ctx):
    """重复投递**同一跃迁** ⇒ 无新行（⚠️ 实际测的是**跃迁判定**，不是 L1 —— 见上一条）。"""
    import app.grading.grading_stats as GS

    TestSession, db = sqlite_env
    grade_ctx.set(False, True)
    GS.record_graded_state_change(TEACHER, FOLDER, None, ENTRY_A, source="ref", filename="张三_1.jpg")
    n1 = len(_grade_events(db))
    GS.record_graded_state_change(TEACHER, FOLDER, None, ENTRY_A, source="ref", filename="张三_1.jpg")
    GS.record_graded_state_change(TEACHER, FOLDER, None, ENTRY_A, source="ref", filename="张三_1.jpg")
    n2 = len(_grade_events(db))
    assert (n1, n2) == (1, 1), f"期望 (1,1)，实得 ({n1},{n2})"


def test_p0_3_delete_yields_one_negative_event(sqlite_env, grade_ctx):
    """删除该学生 ⇒ **恰 1 条** delta=-1，且净额回到 0。"""
    import app.grading.grading_stats as GS

    TestSession, db = sqlite_env
    grade_ctx.set(False, True)
    GS.record_graded_state_change(TEACHER, FOLDER, None, ENTRY_A, source="ref", filename="张三_1.jpg")
    grade_ctx.set(True, False)
    GS.record_graded_state_change(TEACHER, FOLDER, ENTRY_A, None, source="ref", filename="张三_1.jpg")
    evs = _grade_events(db)
    assert sorted(int(e.delta) for e in evs) == [-1, 1]
    assert L.current_net(db, TEACHER, "grade", FOLDER, "张三") == 0


def test_p0_3_upload_events_not_billed(sqlite_env):
    """§3.1：upload 是次项，**默认不收** ⇒ 写事件但不产生任何分录。"""
    import app.grading.grading_stats as GS

    TestSession, db = sqlite_env
    GS.record_upload(TEACHER, FOLDER, 1, subject_key="张三")
    ups = db.query(UsageEvent).filter(UsageEvent.user_id == TEACHER,
                                      UsageEvent.kind == "upload").all()
    assert len(ups) == 1 and int(ups[0].delta) == 1
    assert P.is_billable("upload") is False
    assert _count(db, LedgerEntry, LedgerEntry.entry_type == L.ENTRY_CONSUME) == 0


# ─────────────────────────── P0-4 ───────────────────────────

def test_p0_4_grade_delete_regrade_two_consumes_plus_one_reversal(sqlite_env, grade_ctx):
    """批改→删除→再批改 ⇒ 2 条负额分录 + 1 条冲正；SUM(amount) 对应 **1 份净额**。"""
    import app.grading.grading_stats as GS

    TestSession, db = sqlite_env
    L.post_entry(db, user_id=TEACHER, entry_type=L.ENTRY_GRANT, amount_fen=100000,
                 idempotency_key="k-grant")

    # 批改
    grade_ctx.set(False, True)
    GS.record_graded_state_change(TEACHER, FOLDER, None, ENTRY_A, source="ref", filename="张三_1.jpg")
    # 删除（冲正）
    grade_ctx.set(True, False)
    GS.record_graded_state_change(TEACHER, FOLDER, ENTRY_A, None, source="ref", filename="张三_1.jpg")
    # 再批改（载荷不同 ⇒ 新 event_uid ⇒ 新事件 ⇒ 二次扣费）
    grade_ctx.set(False, True)
    GS.record_graded_state_change(TEACHER, FOLDER, None, ENTRY_C, source="ref", filename="张三_1.jpg")

    digest = L.business_digest(TEACHER, "grade", FOLDER, "张三")
    rows = db.query(LedgerEntry).filter(LedgerEntry.idempotency_key.like(f"{digest}|net=%")).all()
    neg = [r for r in rows if int(r.amount_fen) < 0]
    pos = [r for r in rows if int(r.amount_fen) > 0]
    assert len(neg) == 2, f"期望 2 条 consume 分录（负额），实得 {len(neg)}：{[(r.idempotency_key, r.amount_fen) for r in rows]}"
    assert len(pos) == 1, f"期望 1 条冲正分录，实得 {len(pos)}"
    assert sum(int(r.amount_fen) for r in rows) == -UNIT, "SUM(amount) 应恰对应 1 份净额"
    assert L.current_net(db, TEACHER, "grade", FOLDER, "张三") == 1
    # I5：冲正必须是**反向分录**，不是就地改数（原分录仍在、金额未变）
    assert all(int(r.amount_fen) != 0 for r in rows)
    assert len({r.idempotency_key for r in rows}) == len(rows), "幂等键必须互不相同"
    # 冲正分录 description 必须点名（§3.2：冲正必填）
    assert "冲正" in (pos[0].description or "")


def test_p0_4_repeat_delivery_adds_no_entry(sqlite_env, grade_ctx):
    """重复投递最后一个跃迁 ⇒ 不新增分录（净额不变 ⇒ 差额 0）。"""
    import app.grading.grading_stats as GS

    TestSession, db = sqlite_env
    L.post_entry(db, user_id=TEACHER, entry_type=L.ENTRY_GRANT, amount_fen=100000,
                 idempotency_key="k-grant")
    grade_ctx.set(False, True)
    GS.record_graded_state_change(TEACHER, FOLDER, None, ENTRY_A, source="ref", filename="张三_1.jpg")
    n1 = _count(db, LedgerEntry, LedgerEntry.entry_type == L.ENTRY_CONSUME)
    GS.record_graded_state_change(TEACHER, FOLDER, None, ENTRY_A, source="ref", filename="张三_1.jpg")
    n2 = _count(db, LedgerEntry, LedgerEntry.entry_type == L.ENTRY_CONSUME)
    assert (n1, n2) == (1, 1), f"期望 (1,1)，实得 ({n1},{n2})"


def test_p0_4_i6_remove_folder_stats_does_not_wipe_ledger(sqlite_env, grade_ctx):
    """I6：口径 A 的 `remove_folder_stats` 抹掉统计行，但**账本一行不动**（只补冲正）。"""
    import app.grading.grading_stats as GS

    TestSession, db = sqlite_env
    L.post_entry(db, user_id=TEACHER, entry_type=L.ENTRY_GRANT, amount_fen=100000,
                 idempotency_key="k-grant")
    grade_ctx.set(False, True)
    GS.record_graded_state_change(TEACHER, FOLDER, None, ENTRY_A, source="ref", filename="张三_1.jpg")
    before = db.query(LedgerEntry).count()
    GS.remove_folder_stats(TEACHER, FOLDER)
    after = db.query(LedgerEntry).count()
    assert after == before + 1, f"应只补 1 条冲正，实得 {before} → {after}"
    assert L.current_net(db, TEACHER, "grade", FOLDER, "张三") == 0


def test_p0_4_ledger_is_append_only_no_update_path(sqlite_env):
    """I4：账本**只增不改** —— 模块内不得出现对 LedgerEntry 的 UPDATE/DELETE。"""
    import inspect

    import app.services.payment.ledger as mod

    src = inspect.getsource(mod)
    assert "query(LedgerEntry).delete" not in src
    assert "query(LedgerEntry).update" not in src
    assert "LedgerEntry.__table__.update" not in src


# ─────────────────────────── P0-5 ───────────────────────────

@pytest.fixture()
def api_client(sqlite_env):
    from app.database import get_db as _get_db
    from app.dependencies import bind_grading_user_context
    from app.grading.user_paths import set_grading_user_id
    from app.routers import payment as payment_router

    TestSession, _db = sqlite_env
    app = FastAPI()
    app.include_router(payment_router.router, prefix="/api/v1")

    def _override_db():
        d = TestSession()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[_get_db] = _override_db
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user_id] = lambda: TEACHER

    async def _no_dir_bind():
        # ⚠️ 必须 `async`：contextvar 的写在 sync `Depends` 里**传不到** async 端点
        #（本仓生产用 `main.py::grading_user_context_middleware` 这个 async 中间件来做同一件事）。
        # 本 fixture 建的裸 `FastAPI()` 没有那个中间件 ⇒ 在此以同等语义补上（实测：sync 版会让
        # 端点抛 `RuntimeError: grading user context 未设置`）。
        set_grading_user_id(TEACHER)
        return TEACHER

    try:
        from app.grading.router import router as grading_router

        app.include_router(grading_router, prefix="/api/v1")
        app.dependency_overrides[bind_grading_user_context] = _no_dir_bind
    except Exception:
        pass
    return app, TestClient(app), TestSession


def test_p0_5_zero_balance_blocked_with_402(api_client):
    """余额 0 + 无套餐 ⇒ 发起批改被拒 **402**（走真实路由，不是直接调函数）。"""
    _app, client, TestSession = api_client
    db = TestSession()
    L.get_or_create_account(db, TEACHER)      # 余额 0
    db.close()

    r = client.post(f"/api/v1/grading/folders/{FOLDER}/grade-by-reference",
                    json={"engine": "manual"})
    assert r.status_code == 402, f"HTTP={r.status_code} body={r.text[:300]}"
    assert "detail" in r.json()
    assert "余额" in r.json()["detail"] or "额度" in r.json()["detail"]


def test_p0_5_after_topup_passes_gate(api_client):
    """充值后同一账号放行（说明 402 是闸门造成的，不是别的错误）。"""
    _app, client, TestSession = api_client
    db = TestSession()
    L.grant_manual(db, user_id=TEACHER, amount_fen=500, operator_id=TEACHER, description="充值")
    db.close()
    r = client.post(f"/api/v1/grading/folders/{FOLDER}/grade-by-reference",
                    json={"engine": "manual"})
    assert r.status_code != 402, f"充值后不应再 402，实得 {r.status_code} {r.text[:200]}"


def test_p0_5_non_teacher_only_account_not_gated(api_client):
    """§8.2：**非**「仅任课教师」账号不受闸门约束（行为与改动前逐字一致）。"""
    _app, client, TestSession = api_client
    db = TestSession()
    L.get_or_create_account(db, COMBO)        # 余额 0
    assert L.grading_gate_denied(db, COMBO) is None
    assert L.grading_gate_denied(db, TEACHER) is not None
    db.close()


def test_p0_5_running_grading_not_interrupted(api_client):
    """⛔ 闸门只挡「发起新批改」：**状态/进度端点**对余额 0 的老师不得返回 402。"""
    _app, client, TestSession = api_client
    db = TestSession()
    L.get_or_create_account(db, TEACHER)      # 余额 0
    db.close()
    r = client.get(f"/api/v1/grading/folders/{FOLDER}/grade-by-reference/status/nonexistent-job")
    assert r.status_code != 402, (
        f"已在跑/已发起的批改进度查询不得被闸门打断，实得 {r.status_code}"
    )


def test_p0_5_gate_only_wired_to_start_endpoints():
    """闸门调用点必须**只**出现在「发起批改」端点上（源码级判据，防误挂进进度端点）。"""
    import re

    from app.grading import router as grading_router_mod

    src = open(grading_router_mod.__file__, encoding="utf-8").read()
    lines = src.splitlines()
    calls = [i for i, ln in enumerate(lines) if ln.strip().startswith("_payment_gate_or_402(")]
    assert calls, "闸门没有任何调用点（P0-5 未接线）"
    paths = []
    for i in calls:
        for prev in reversed(lines[:i]):
            m = re.match(r'@router\.(get|post|put|delete)\("([^"]+)"', prev.strip())
            if m:
                paths.append(m.group(2))
                break
    allowed = ("/grade-by-reference", "/grade-by-answer-key", "/essay-grade/start")
    assert all(p.endswith(allowed) for p in paths), f"闸门挂错端点: {paths}"
    assert len(calls) == 3, f"期望 3 个发起端点，实得 {paths}"


# ─────────────────────────── P0-6 ───────────────────────────

def test_p0_6_account_endpoint_format(api_client):
    """`GET /payment/account`：`{code,message,data}` 与全仓一致。"""
    _app, client, TestSession = api_client
    db = TestSession()
    L.grant_manual(db, user_id=TEACHER, amount_fen=1234, operator_id=TEACHER, description="入账")
    db.close()
    r = client.get("/api/v1/payment/account")
    assert r.status_code == 200
    b = r.json()
    assert set(b.keys()) >= {"code", "message", "data"}
    assert b["code"] == 0
    assert b["data"]["user_id"] == TEACHER
    assert b["data"]["balance_fen"] == 1234


def test_p0_6_account_endpoint_ignores_other_user_id(api_client):
    """越权防护：传 `?user_id=<别人>` 仍只返回自己的账户（§12 第 6 条）。"""
    _app, client, TestSession = api_client
    r = client.get(f"/api/v1/payment/account?user_id={COMBO}")
    assert r.status_code == 200
    assert r.json()["data"]["user_id"] == TEACHER


def test_p0_6_ledger_pagination_and_isolation(api_client):
    """`GET /payment/ledger`：分页 + 只含自己的流水。"""
    _app, client, TestSession = api_client
    db = TestSession()
    for i in range(5):
        L.post_entry(db, user_id=TEACHER, entry_type=L.ENTRY_GRANT, amount_fen=100 + i,
                     idempotency_key=f"lg-{i}")
    L.post_entry(db, user_id=COMBO, entry_type=L.ENTRY_GRANT, amount_fen=9999,
                 idempotency_key="lg-other")
    db.close()

    r = client.get("/api/v1/payment/ledger?page=1&page_size=2")
    d = r.json()["data"]
    assert (d["total"], d["page"], d["page_size"], len(d["items"])) == (5, 1, 2, 2)
    ids1 = [x["id"] for x in d["items"]]
    d2 = client.get("/api/v1/payment/ledger?page=2&page_size=2").json()["data"]
    ids2 = [x["id"] for x in d2["items"]]
    assert not set(ids1) & set(ids2), "分页不得重复"
    assert 9999 not in [x["amount_fen"] for x in d["items"] + d2["items"]], "不得含他人流水"


def test_p0_6_usage_endpoint_reads_usage_events(api_client):
    """`GET /payment/usage`：口径 B（`usage_events` 净额），⛔ 不读口径 A 的统计表。"""
    _app, client, TestSession = api_client
    db = TestSession()
    db.add(UsageEvent(user_id=TEACHER, kind="grade", folder_safe=FOLDER, subject_key="张三",
                      delta=1, occurred_at=__import__("datetime").datetime.utcnow(),
                      event_uid="u1"))
    db.add(UsageEvent(user_id=TEACHER, kind="grade", folder_safe=FOLDER, subject_key="李四",
                      delta=1, occurred_at=__import__("datetime").datetime.utcnow(),
                      event_uid="u2"))
    db.commit()
    db.close()
    r = client.get("/api/v1/payment/usage")
    assert r.status_code == 200
    u = r.json()["data"]
    assert u["total_grade"] == 2
    assert u["total_upload"] == 0
    assert set(u.keys()) >= {"total_grade", "total_upload", "folders", "recent"}


def test_p0_6_401_error_body_uses_detail(api_client):
    """未登录 ⇒ 401，错误体是 `{"detail": ...}`（本仓统一风格，⛔ 非 `{error,message}`）。"""
    from app.routers import payment as payment_router

    app = FastAPI()
    app.include_router(payment_router.router, prefix="/api/v1")
    r = TestClient(app).get("/api/v1/payment/account")
    assert r.status_code == 401
    body = r.json()
    assert "detail" in body and "error" not in body


def test_p0_6_scan_billing_untouched():
    """⛔ `scan_billing.py` 9 个只读端点零改动（口径 A 的权威投影）。"""
    from app.routers import scan_billing

    src = open(scan_billing.__file__, encoding="utf-8").read()
    assert src.count("@router.get(") == 9
    assert src.count("@router.post(") == 0
    assert src.count("@router.put(") == 0
    assert src.count("@router.delete(") == 0


def test_p0_6_payment_router_has_no_phase2_endpoints():
    """本批不写 Phase 2：⛔ 无 /orders、无 /callback、无 /admin/grant。"""
    from app.routers import payment as payment_router

    paths = {r.path for r in payment_router.router.routes}
    assert paths == {"/payment/account", "/payment/ledger", "/payment/usage"}, sorted(paths)
