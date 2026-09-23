# -*- coding: utf-8 -*-
"""免审核自助注册测试账号接口验收测试。

覆盖：
  1. 任课教师+数学 注册成功：users.roles / teaching_subject、class_teachers 新增 1 行
     role="teacher" subject="数学"、响应含 access_token
  2. 班主任注册成功：class_teachers role="head"
  3. 年级组长/校级管理者/系统管理员注册成功：不产生 class_teachers 行
  4. 重复邮箱 → 409；非法角色 → 422；任课教师缺科目/非法科目 → 400；
     其他角色带科目 → 400；演示池空 → 503；限流 → 429
  5. settings.ALLOW_PUBLIC_REGISTRATION=False → 403

测试方式：直接调用 auth.register（与 test_admin_batch_delete 同款 fake db 风格），
mock 掉密码哈希 / token 签发 / 批改目录初始化 / 注册限流外部副作用。
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.database import get_db
from app.models.class_model import Class
from app.models.class_teacher import ClassTeacher
from app.models.user import User
from app.routers import auth
from app.schemas.auth import RegisterRequest

# 供「限流真实逻辑」用例在 autouse fixture 打桩后还原原始实现
_ORIG_REGISTER_LOCKED = auth._register_locked
_ORIG_RECORD_REGISTER = auth._record_register


class _FakeQuery:
    """链式查询 stub：filter/outerjoin/group_by/order_by 全部透传，first/all 返回预设行。"""

    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_a, **_k):
        return self

    def outerjoin(self, *_a, **_k):
        return self

    def group_by(self, *_a):
        return self

    def order_by(self, *_a):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeDb:
    def __init__(self, existing_users=None, demo_classes=None):
        self.existing_users = existing_users or []
        self.demo_classes = demo_classes or []
        self.added = []
        self.flushed = False
        self.committed = False
        self.rolled_back = False

    def query(self, model):
        if model is User:
            return _FakeQuery(self.existing_users)
        if model is Class:
            return _FakeQuery(self.demo_classes)
        return _FakeQuery([])

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, User) and not getattr(obj, "id", None):
            obj.id = f"user-{len(self.added)}"
        if isinstance(obj, ClassTeacher) and not getattr(obj, "id", None):
            obj.id = f"ct-{len(self.added)}"

    def flush(self):
        self.flushed = True

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class _StatefulDb(_FakeDb):
    """注册→登录跨请求共享：注册写入 users，后续登录查询能查到。"""

    def __init__(self, demo_classes=None):
        super().__init__(existing_users=[], demo_classes=demo_classes or [])

    def add(self, obj):
        super().add(obj)
        if isinstance(obj, User) and not any(u.id == obj.id for u in self.existing_users):
            self.existing_users.append(obj)


def _request(host="127.0.0.1"):
    return SimpleNamespace(client=SimpleNamespace(host=host))


def _demo_class(cls_id="cls-demo-1"):
    return SimpleNamespace(id=cls_id, name="演示-三年级1班")


def _existing_user(email="used@example.com"):
    u = User(id="user-existing", email=email, roles="任课教师")
    return u


def _make_client(monkeypatch, db):
    """构造走真实 FastAPI 路由的 TestClient：覆盖 get_db 依赖 + mock 注册/登录外部副作用。

    注：本机 TestClient 的 with 上下文（portal 模式）会挂起，故直接 new 出来用（无 with）。
    """
    monkeypatch.setattr(auth, "_register_locked", lambda ip: False)
    monkeypatch.setattr(auth, "_record_register", lambda ip: None)
    monkeypatch.setattr(auth, "hash_password", lambda p: "hashed-pw")
    monkeypatch.setattr(auth, "verify_password", lambda p, h: True)
    monkeypatch.setattr(auth, "create_access_token", lambda subject: f"token-{subject}")
    monkeypatch.setattr(auth, "ensure_user_grading_layout", lambda user_id: None)
    monkeypatch.setattr(auth, "_is_login_locked", lambda email, ip: False)
    monkeypatch.setattr(auth, "_clear_login_failures", lambda email, ip: None)

    app = FastAPI()
    app.include_router(auth.router)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


@pytest.fixture(autouse=True)
def _default_mocks(monkeypatch):
    """统一 mock 注册路径的外部副作用，让各用例只关注注册逻辑本身。"""
    monkeypatch.setattr(auth, "_register_locked", lambda ip: False)
    monkeypatch.setattr(auth, "_record_register", lambda ip: None)
    monkeypatch.setattr(auth, "hash_password", lambda p: "hashed-pw")
    monkeypatch.setattr(auth, "create_access_token", lambda subject: f"token-{subject}")
    monkeypatch.setattr(auth, "ensure_user_grading_layout", lambda user_id: None)


# ── 角色注册成功 ──────────────────────────────────────────


def test_register_subject_teacher_success():
    db = _FakeDb(demo_classes=[_demo_class()])
    resp = auth.register(
        RegisterRequest(email="math@example.com", password="123456", role="任课教师", teaching_subject="数学"),
        _request(),
        db=db,
    )

    assert resp.access_token == "token-user-1"
    user = db.added[0]
    assert isinstance(user, User)
    assert user.email == "math@example.com"
    assert user.roles == "任课教师"
    assert user.teaching_subject == "数学"
    assert user.password_hash == "hashed-pw"

    ct = db.added[1]
    assert isinstance(ct, ClassTeacher)
    assert ct.class_id == "cls-demo-1"
    assert ct.user_id == user.id
    assert ct.role == "teacher"
    assert ct.subject == "数学"
    assert db.committed


def test_register_head_teacher_success():
    db = _FakeDb(demo_classes=[_demo_class()])
    resp = auth.register(
        RegisterRequest(email="head@example.com", password="123456", role="班主任"),
        _request(),
        db=db,
    )

    assert resp.access_token.startswith("token-")
    ct = db.added[1]
    assert isinstance(ct, ClassTeacher)
    assert ct.role == "head"
    assert ct.subject is None
    assert db.committed


@pytest.mark.parametrize(
    "role",
    ["年级组长", "校级管理者", "系统管理员"],
)
def test_register_global_roles_no_class_teacher(role):
    db = _FakeDb()
    resp = auth.register(
        RegisterRequest(email=f"{role}@example.com", password="123456", role=role),
        _request(),
        db=db,
    )

    assert resp.access_token.startswith("token-")
    user = db.added[0]
    assert user.roles == role
    # 全局角色不绑定演示班 → 只新增了 User，没有 ClassTeacher
    assert len([o for o in db.added if isinstance(o, ClassTeacher)]) == 0
    assert db.committed


# ── 校验分支 ─────────────────────────────────────────────


def test_register_duplicate_email_409():
    db = _FakeDb(existing_users=[_existing_user("dup@example.com")])
    with pytest.raises(HTTPException) as exc_info:
        auth.register(
            RegisterRequest(email="DUP@example.com", password="123456", role="任课教师", teaching_subject="数学"),
            _request(),
            db=db,
        )
    assert exc_info.value.status_code == 409
    assert not db.committed


def test_register_invalid_role_422():
    # RegisterRole 是 Literal，非法角色在 pydantic 校验阶段就 422
    with pytest.raises(ValidationError):
        RegisterRequest(email="boss@example.com", password="123456", role="校长")


def test_register_teacher_missing_subject_400():
    db = _FakeDb(demo_classes=[_demo_class()])
    with pytest.raises(HTTPException) as exc_info:
        auth.register(
            RegisterRequest(email="nosubj@example.com", password="123456", role="任课教师"),
            _request(),
            db=db,
        )
    assert exc_info.value.status_code == 400


def test_register_teacher_invalid_subject_400():
    db = _FakeDb(demo_classes=[_demo_class()])
    with pytest.raises(HTTPException) as exc_info:
        auth.register(
            RegisterRequest(email="phys@example.com", password="123456", role="任课教师", teaching_subject="物理"),
            _request(),
            db=db,
        )
    assert exc_info.value.status_code == 400


def test_register_non_teacher_with_subject_400():
    db = _FakeDb()
    with pytest.raises(HTTPException) as exc_info:
        auth.register(
            RegisterRequest(email="head@example.com", password="123456", role="班主任", teaching_subject="数学"),
            _request(),
            db=db,
        )
    assert exc_info.value.status_code == 400


def test_register_demo_pool_empty_503():
    db = _FakeDb(demo_classes=[])
    with pytest.raises(HTTPException) as exc_info:
        auth.register(
            RegisterRequest(email="teacher@example.com", password="123456", role="任课教师", teaching_subject="语文"),
            _request(),
            db=db,
        )
    assert exc_info.value.status_code == 503
    # flush 成功但 commit 前因池空中止 → 未提交
    assert not db.committed


def test_register_rate_limited_429(monkeypatch):
    monkeypatch.setattr(auth, "_register_locked", lambda ip: True)
    db = _FakeDb()
    with pytest.raises(HTTPException) as exc_info:
        auth.register(
            RegisterRequest(email="spam@example.com", password="123456", role="年级组长"),
            _request(),
            db=db,
        )
    assert exc_info.value.status_code == 429


def test_register_disabled_by_config_403(monkeypatch):
    monkeypatch.setattr(auth.settings, "ALLOW_PUBLIC_REGISTRATION", False)
    db = _FakeDb()
    with pytest.raises(HTTPException) as exc_info:
        auth.register(
            RegisterRequest(email="blocked@example.com", password="123456", role="年级组长"),
            _request(),
            db=db,
        )
    assert exc_info.value.status_code == 403


# ── 注册限流逻辑（真实实现，1 小时窗口 / 单 IP 5 次）──────


def test_register_rate_limit_window_real_logic(monkeypatch):
    # autouse fixture 打了桩，这里还原真实实现再测
    monkeypatch.setattr(auth, "_register_locked", _ORIG_REGISTER_LOCKED)
    monkeypatch.setattr(auth, "_record_register", _ORIG_RECORD_REGISTER)
    ip = "rate-limit-test-ip"
    auth._REGISTER_COUNTS.pop(ip, None)
    try:
        assert not auth._register_locked(ip)
        for _ in range(auth._REGISTER_MAX_PER_IP):
            auth._record_register(ip)
        assert auth._register_locked(ip)
    finally:
        auth._REGISTER_COUNTS.pop(ip, None)


# ── HTTP 层（TestClient 走真实路由，复现 EmailStr 拒绝 .local 的 bug）────────


def test_http_register_local_email_success(monkeypatch):
    db = _FakeDb(demo_classes=[_demo_class()])
    client = _make_client(monkeypatch, db)
    resp = client.post(
        "/auth/register",
        json={"email": "teacher@grade.local", "password": "123456", "role": "任课教师", "teaching_subject": "数学"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"].startswith("token-")
    assert body["user"]["email"] == "teacher@grade.local"
    # 落库校验
    user = db.added[0]
    assert user.roles == "任课教师"
    assert user.teaching_subject == "数学"
    ct = db.added[1]
    assert ct.role == "teacher"
    assert ct.subject == "数学"


def test_http_register_invalid_email_400(monkeypatch):
    db = _FakeDb()
    client = _make_client(monkeypatch, db)
    for bad_email in ("", "notanemail", "   "):
        resp = client.post(
            "/auth/register",
            json={"email": bad_email, "password": "123456", "role": "任课教师", "teaching_subject": "数学"},
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"] == "邮箱格式不正确"


def test_http_register_com_email_success(monkeypatch):
    db = _FakeDb(demo_classes=[_demo_class()])
    client = _make_client(monkeypatch, db)
    resp = client.post(
        "/auth/register",
        json={"email": "teacher@example.com", "password": "123456", "role": "任课教师", "teaching_subject": "数学"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"].startswith("token-")


def test_http_register_then_login_local_email(monkeypatch):
    # 闭环：.local 邮箱注册成功 → 自动登录 OK → 退出后走 /auth/login 也应能登录
    db = _StatefulDb(demo_classes=[_demo_class()])
    client = _make_client(monkeypatch, db)

    reg = client.post(
        "/auth/register",
        json={"email": "head@grade.local", "password": "123456", "role": "班主任"},
    )
    assert reg.status_code == 200, reg.text

    login = client.post(
        "/auth/login",
        json={"email": "head@grade.local", "password": "123456"},
    )
    assert login.status_code == 200, login.text
    body = login.json()
    assert body["access_token"].startswith("token-")
    assert body["user"]["email"] == "head@grade.local"


def test_http_login_com_email_success(monkeypatch):
    # 回归：正常 .com 邮箱登录不受宽松校验影响
    db = _FakeDb(existing_users=[_existing_user("login@example.com")])
    client = _make_client(monkeypatch, db)
    resp = client.post(
        "/auth/login",
        json={"email": "login@example.com", "password": "123456"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"].startswith("token-")
