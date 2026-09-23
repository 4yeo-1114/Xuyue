"""E08 学校级 AI 管控 · 后端验收测试。

覆盖：
  1. assert_no_sensitive_input 命中身份证号 / 手机号（纯函数）
  2. build_comment_messages 评语 messages 无学生真名（匿名化断言，纯函数）
  3. feature_flags 接口：GET 全量（按 key 排序，字段集锁定）/ PATCH 管理员可改 / 非管理员 403 / key 不存在 404
  4. AI 端点接线：flag enabled 时端点 200（组卷 mock LLM）；PATCH 关掉某 flag 后对应端点 403（detail=「该 AI 功能已由学校/系统关闭」）
  5. 角色白名单：无角色用户即使 flag 开启也被 require_ai_access 403；班主任放行
  6. 迁移 SQL 幂等性（同一文件跑两遍不报错，9 行数据不变）

环境：需要本地 Docker MySQL（127.0.0.1:13307, root/root_pw_2026）。
测试自建 grade_e08_test / grade_e08_mig 两个 scratch 库，跑完不清理以便复查，可手工 DROP。
"""
import os

# 用专用 E08_* 覆盖变量 + 本地 Docker 默认值，避免拾取 shell 中遗留的生产 DB_* 环境变量。
_DB_HOST = os.environ.get("E08_DB_HOST", "127.0.0.1")
_DB_PORT = int(os.environ.get("E08_DB_PORT", "13307"))
_DB_USER = os.environ.get("E08_DB_USER", "root")
_DB_PWD = os.environ.get("E08_DB_PASSWORD", "root_pw_2026")
_TEST_DB = os.environ.get("E08_TEST_DB", "grade_e08_test")
_MIG_DB = os.environ.get("E08_MIG_DB", "grade_e08_mig")

os.environ["DB_HOST"] = _DB_HOST
os.environ["DB_PORT"] = str(_DB_PORT)
os.environ["DB_USER"] = _DB_USER
os.environ["DB_PASSWORD"] = _DB_PWD
os.environ["DB_NAME"] = _TEST_DB
os.environ.setdefault("JWT_SECRET_KEY", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("AUTO_DDL", "false")
os.environ.setdefault("DASHSCOPE_API_KEY", "sk-e08-test-not-real")

# 必须先建好 scratch 库，再导入 app.database（engine 绑定 DB_NAME）。
_MYSQL_AVAILABLE = False
import pymysql

try:
    _conn = pymysql.connect(host=_DB_HOST, port=_DB_PORT, user=_DB_USER, password=_DB_PWD, autocommit=True, connect_timeout=5)
    with _conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS `{_TEST_DB}`")
        cur.execute(f"CREATE DATABASE `{_TEST_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    _conn.close()
    _MYSQL_AVAILABLE = True
except Exception as _db_err:  # noqa: BLE001 - 环境不可用则降级跳过 DB 用例
    _MYSQL_AVAILABLE = False
    _DB_ERR = str(_db_err)

from pathlib import Path

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import Base, engine, SessionLocal
from app.dependencies import bind_grading_user_context, get_current_user_id
from app.routers import feature_flags, exams, ai_chat, student_analysis
from app.services.ai_policy import (
    AI_ALLOWED_ROLES,
    FEATURE_DISABLED_DETAIL,
    assert_no_sensitive_input,
    require_ai_access,
)
from app.services.portfolio.comment import build_comment_messages

from app.models.user import User
from app.models.feature_flag import FeatureFlag
from app.models.system_settings import SystemSettings

# 9 个 flag keys（契约对齐前端 Supabase seed）
EXPECTED_KEYS = [
    "ai_review",
    "ai_targeted",
    "ai_layered",
    "smart_exam",
    "smart_gen",
    "ai_diagnosis",
    "ai_grading",
    "ai_chat",
    "ai_comment",
]
EXPECTED_FIELDS = {"key", "label", "enabled", "scope", "scope_id"}


def _exec_sql_script(dbname: str, sql_text: str) -> None:
    """在指定库执行多语句 SQL 脚本（MULTI_STATEMENTS，跑完 drain result set）。"""
    conn = pymysql.connect(
        host=_DB_HOST, port=_DB_PORT, user=_DB_USER, password=_DB_PWD,
        database=dbname, autocommit=True,
        client_flag=pymysql.constants.CLIENT.MULTI_STATEMENTS,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(sql_text)
            while cur.nextset():
                pass
    finally:
        conn.close()


_MIGRATION_SQL = Path(__file__).resolve().parent.parent / "docs" / "migrations" / "2026-08-15-ai-feature-flags.sql"


# ── 纯逻辑用例（不依赖 DB）──────────────────────────────


def test_assert_no_sensitive_input_hits_id_card():
    assert assert_no_sensitive_input("身份证号 110101199001011234") is True
    # 18 位身份证（末位 X）：17 位数字 + X
    assert assert_no_sensitive_input("证件号：11010119900101123X") is True


def test_assert_no_sensitive_input_hits_phone():
    assert assert_no_sensitive_input("联系电话 13800138000") is True


def test_assert_no_sensitive_input_clean_text_false():
    assert assert_no_sensitive_input("学生错题分析") is False
    assert assert_no_sensitive_input("") is False
    assert assert_no_sensitive_input(None) is False


def test_comment_messages_anonymize_student_name():
    """评语 messages 中不得出现学生真名；应出现稳定匿名标识（学生01）。"""
    report = {
        "name": "王小明",
        "grade": "五年级",
        "term": "2025-2026-1",
        "dimensions": {},
        "data_status": {},
        "baseline": {},
        "assessment_profile": {},
        "milestones": [],
    }
    msgs = build_comment_messages(report)
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert "王小明" not in msgs[1]["content"]
    assert "学生01" in msgs[1]["content"]


# ── TestClient 冒烟（Docker MySQL）──────────────────────

_E08_TABLES = [
    User.__table__,
    FeatureFlag.__table__,
    SystemSettings.__table__,
]

# 种子（对齐契约 key + 迁移 SQL label）
_SEED_FLAGS = [
    ("ai_review", "AI 课堂讲评与班级分析"),
    ("ai_targeted", "AI 靶向提升方案"),
    ("ai_layered", "AI 分层教学建议"),
    ("smart_exam", "AI 智能组卷"),
    ("smart_gen", "AI 智能生成教案/资源"),
    ("ai_diagnosis", "AI 学情诊断"),
    ("ai_grading", "AI 智能批改"),
    ("ai_chat", "AI 助教对话"),
    ("ai_comment", "AI 学业评语"),
]


@pytest.fixture(scope="module")
def test_app():
    if not _MYSQL_AVAILABLE:
        pytest.skip(f"本地 Docker MySQL 不可用，跳过 TestClient 冒烟：{_DB_ERR}")
    # 用 SQLAlchemy create_all + model 灌种子，避免跨测试模块 DB_NAME 环境变量互相污染
    #（全量跑时 engine 可能绑定到前序模块的库，不能假设指向 grade_e08_test）。
    Base.metadata.create_all(bind=engine, tables=_E08_TABLES)
    with SessionLocal() as db:
        db.query(FeatureFlag).delete()
        for key, label in _SEED_FLAGS:
            db.add(FeatureFlag(key=key, label=label, enabled=True, scope="global", scope_id=None, updated_by="system"))
        db.commit()

    app = FastAPI()
    app.include_router(feature_flags.router)
    app.include_router(exams.router)
    app.include_router(ai_chat.router)
    app.include_router(student_analysis.router)

    def _fake_current_user(authorization: str | None = Header(None)) -> str:
        # 测试用：Authorization: Bearer <user_id> 直接作为当前用户 ID（跳过 JWT 解码）
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="未登录")
        return authorization.replace("Bearer ", "").strip()

    def _fake_bind(user_id: str = Depends(get_current_user_id)):
        return user_id

    app.dependency_overrides[get_current_user_id] = _fake_current_user
    app.dependency_overrides[bind_grading_user_context] = _fake_bind

    with TestClient(app) as client:
        yield client

    # 清理本次测试数据，避免污染下次运行
    with engine.begin() as conn:
        for table in (SystemSettings.__table__, FeatureFlag.__table__, User.__table__):
            conn.execute(table.delete())


@pytest.fixture()
def seed(test_app):
    """标准种子：T1 班主任 / A1 系统管理员 / U1 任课教师 / P1 无角色（家长）。"""
    with SessionLocal() as db:
        db.query(User).delete()
        db.commit()
        t1 = User(id="T1", email="t1@test.local", password_hash="x", roles="班主任")
        a1 = User(id="A1", email="a1@test.local", password_hash="x", roles="系统管理员")
        u1 = User(id="U1", email="u1@test.local", password_hash="x", roles="任课教师")
        p1 = User(id="P1", email="p1@test.local", password_hash="x", roles="")
        db.add_all([t1, a1, u1, p1])
        db.commit()
        return {"T1": "T1", "A1": "A1", "U1": "U1", "P1": "P1"}


def _auth(token: str):
    return {"Authorization": f"Bearer {token}"}


def test_get_feature_flags_returns_all_sorted(test_app, seed):
    resp = test_app.get("/feature-flags", headers=_auth(seed["T1"]))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    keys = [d["key"] for d in data]
    assert keys == sorted(EXPECTED_KEYS)
    for d in data:
        assert set(d.keys()) == EXPECTED_FIELDS, d
        assert d["enabled"] is True
        assert d["scope"] == "global"


def test_patch_feature_flag_admin_only(test_app, seed):
    # 非管理员（任课教师）→ 403
    resp = test_app.patch("/feature-flags/ai_chat", headers=_auth(seed["U1"]), json={"enabled": False})
    assert resp.status_code == 403, resp.text
    # 管理员 → 200，返回 {key, enabled}
    resp = test_app.patch("/feature-flags/ai_chat", headers=_auth(seed["A1"]), json={"enabled": False})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {"key": "ai_chat", "enabled": False}
    # 读回确认
    resp = test_app.get("/feature-flags", headers=_auth(seed["A1"]))
    by_key = {d["key"]: d for d in resp.json()["data"]}
    assert by_key["ai_chat"]["enabled"] is False
    # 还原
    resp = test_app.patch("/feature-flags/ai_chat", headers=_auth(seed["A1"]), json={"enabled": True})
    assert resp.status_code == 200, resp.text


def test_patch_feature_flag_not_found(test_app, seed):
    resp = test_app.patch("/feature-flags/no_such_key", headers=_auth(seed["A1"]), json={"enabled": True})
    assert resp.status_code == 404, resp.text


def test_ai_chat_disabled_endpoint_403(test_app, seed):
    resp = test_app.patch("/feature-flags/ai_chat", headers=_auth(seed["A1"]), json={"enabled": False})
    assert resp.status_code == 200, resp.text
    resp = test_app.post(
        "/ai-chat",
        headers=_auth(seed["T1"]),
        json={"messages": [{"role": "user", "content": "你好"}]},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == FEATURE_DISABLED_DETAIL
    # 还原
    test_app.patch("/feature-flags/ai_chat", headers=_auth(seed["A1"]), json={"enabled": True})


def test_ai_generate_enabled_200_and_disabled_403(test_app, seed, monkeypatch):
    """组卷端点：smart_exam 开启时 200（mock LLM），关掉后 403。"""
    import app.routers.exams as exams_router

    def _fake_post(url, json=None, headers=None, timeout=None):
        class _FakeResp:
            status_code = 200

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": '[{"id":"q1","type":"choice","stem":"","content":"1+1=？","score":5,'
                                           '"options":["1","2","3","4"],"subQuestions":[]}]'
                            }
                        }
                    ]
                }

        return _FakeResp()

    monkeypatch.setattr(exams_router.requests, "post", _fake_post)
    body = {
        "topic": "分数乘法",
        "grade": "五年级",
        "term": "2025-2026-1",
        "difficulty": "中等",
        "subject": "语文",
        "requirements": [{"type": "choice", "count": 1, "score": 5}],
    }
    # 默认 smart_exam 开启 → 200
    resp = test_app.post("/exams/ai-generate", headers=_auth(seed["T1"]), json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"][0]["is_ai"] is True

    # 关掉 smart_exam → 403
    resp = test_app.patch("/feature-flags/smart_exam", headers=_auth(seed["A1"]), json={"enabled": False})
    assert resp.status_code == 200, resp.text
    resp = test_app.post("/exams/ai-generate", headers=_auth(seed["T1"]), json=body)
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == FEATURE_DISABLED_DETAIL
    # 还原
    test_app.patch("/feature-flags/smart_exam", headers=_auth(seed["A1"]), json={"enabled": True})


def test_ai_diagnosis_disabled_endpoint_403(test_app, seed):
    """AI 诊断：关掉 ai_diagnosis 后对应端点 403（guard 先于 LLM，无需 mock）。"""
    resp = test_app.patch("/feature-flags/ai_diagnosis", headers=_auth(seed["A1"]), json={"enabled": False})
    assert resp.status_code == 200, resp.text
    resp = test_app.post(
        "/student-analysis/ai-diagnosis",
        headers=_auth(seed["T1"]),
        json={"class_id": "C1", "student_name": "甲", "subject": "数学"},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == FEATURE_DISABLED_DETAIL
    # 还原
    test_app.patch("/feature-flags/ai_diagnosis", headers=_auth(seed["A1"]), json={"enabled": True})


def test_require_ai_access_role_whitelist(test_app, seed):
    """角色白名单：无角色用户（家长）即使 flag 开启也被 403；班主任放行。"""
    with SessionLocal() as db:
        require_ai_access(db, seed["T1"], "ai_chat")  # 班主任放行
        with pytest.raises(HTTPException) as exc:
            require_ai_access(db, seed["P1"], "ai_chat")
        assert exc.value.status_code == 403
        assert "班主任" in AI_ALLOWED_ROLES
        assert "系统管理员" in AI_ALLOWED_ROLES


# ── 迁移 SQL 幂等性 ─────────────────────────────────────


def test_migration_sql_idempotent():
    if not _MYSQL_AVAILABLE:
        pytest.skip(f"本地 Docker MySQL 不可用，跳过迁移幂等性用例：{_DB_ERR}")
    sql_text = _MIGRATION_SQL.read_text(encoding="utf-8")
    mig_conn = pymysql.connect(
        host=_DB_HOST, port=_DB_PORT, user=_DB_USER, password=_DB_PWD,
        autocommit=True, client_flag=pymysql.constants.CLIENT.MULTI_STATEMENTS,
    )
    try:
        with mig_conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{_MIG_DB}`")
            cur.execute(f"CREATE DATABASE `{_MIG_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cur.execute(f"USE `{_MIG_DB}`")
            cur.execute(
                "CREATE TABLE feature_flags ("
                " id VARCHAR(36) NOT NULL PRIMARY KEY,"
                " `key` VARCHAR(128) NOT NULL,"
                " label VARCHAR(256) NULL,"
                " enabled TINYINT(1) NOT NULL DEFAULT 1,"
                " scope VARCHAR(64) NOT NULL DEFAULT 'global',"
                " scope_id VARCHAR(36) NULL,"
                " updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                " updated_by VARCHAR(36) NULL,"
                " UNIQUE KEY uq_feature_flag_key (`key`)"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )

        def _count():
            with mig_conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM feature_flags")
                return cur.fetchone()[0]

        # 第一遍：插入 9 行
        _exec_sql_script(_MIG_DB, sql_text)
        assert _count() == 9
        # 第二遍：幂等，不报错，行数不变
        _exec_sql_script(_MIG_DB, sql_text)
        assert _count() == 9
    finally:
        with mig_conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{_MIG_DB}`")
        mig_conn.close()
