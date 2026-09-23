# -*- coding: utf-8 -*-
"""P2-4 批 5：POST /recommend/wrong-questions/click 点击奖励上报端点单测。

覆盖：
- 成功路径：reward 透传 record_click_reward，返回 success/clicked/reward
- reward 非法值（0.5 / -1 / 2）→ 422（pydantic 强校验）
- 学生不存在 → 404；无班级访问权限 → 403（_assert_class_access 防 IDOR）
- PG 资产库未配置（ASSETS_DB_ENABLED=False）→ 503
- 端点到真实 record_click_reward 的完整调用链：clicks/reward_sum 被正确更新
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.bandit_arm_stats import BanditArmStats
from app.models.student import Student
from app.routers import bandit_recommend


def _make_student(student_id: str, class_id: str) -> SimpleNamespace:
    return SimpleNamespace(id=student_id, class_id=class_id)


class _FakeDB:
    """按查询模型分流返回的桩 db：Student → 学生行；BanditArmStats → arm 行。

    用于「真实 record_click_reward」链路测试，避免 MagicMock 的 query().first()
    把 Student 查找和 arm 行查找混成同一个返回值。
    """

    def __init__(self, student=None, arm_row=None):
        self.student = student
        self.arm_row = arm_row
        self._current = None
        self.added = []
        self.commits = 0

    def query(self, model):
        self._current = model
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        if self._current is Student:
            return self.student
        if self._current is BanditArmStats:
            return self.arm_row
        return None

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def _auth(token: str = "u1"):
    return {"Authorization": f"Bearer {token}"}


_VALID_PAYLOAD = {
    "student_id": "S1",
    "subject": "数学",
    "kp_name": "四则运算",
    "reward": 1.0,
}


def _build_client(fake_db, assets_enabled: bool = True, monkeypatch=None):
    """构造含 bandit_recommend 路由的测试 app，覆盖鉴权与 db 依赖。"""
    if monkeypatch is not None:
        monkeypatch.setattr(
            bandit_recommend.settings, "ASSETS_DB_ENABLED", assets_enabled
        )
    else:
        bandit_recommend.settings.ASSETS_DB_ENABLED = assets_enabled

    app = FastAPI()
    app.include_router(bandit_recommend.router)

    def _fake_current_user(authorization: str | None = Header(None)) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="未登录")
        return authorization.replace("Bearer ", "").strip()

    def _get_db_override():
        try:
            yield fake_db
        finally:
            pass

    app.dependency_overrides[get_current_user_id] = _fake_current_user
    app.dependency_overrides[get_db] = _get_db_override

    return TestClient(app)


@pytest.fixture()
def fake_db():
    db = MagicMock()
    # 默认学生查找 first() 返回 None（学生不存在），各用例按需覆写为具体学生
    db.query.return_value.filter.return_value.first.return_value = None
    return db


@pytest.fixture()
def make_client(monkeypatch):
    """返回 (fake_db, client) 工厂；ASSETS_DB_ENABLED 由 monkeypatch 管理自动还原。"""

    def _make(fdb, assets_enabled: bool = True):
        client = _build_client(fdb, assets_enabled=assets_enabled, monkeypatch=monkeypatch)
        return client

    return _make


# ── 成功路径 ───────────────────────────────────────────


def test_click_success_reward_one(make_client, fake_db):
    fake_db.query.return_value.filter.return_value.first.return_value = _make_student(
        "S1", "C1"
    )
    client = make_client(fake_db)
    with patch.object(bandit_recommend, "can_view_class", return_value=True) as mock_access, \
            patch.object(bandit_recommend, "record_click_reward") as mock_record:
        resp = client.post(
            "/recommend/wrong-questions/click", json=_VALID_PAYLOAD, headers=_auth("u1")
        )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"success": True, "clicked": True, "reward": 1.0}
    mock_access.assert_called_once_with(fake_db, "u1", "C1")
    mock_record.assert_called_once_with(
        db=fake_db,
        student_id="S1",
        subject="数学",
        kp_name="四则运算",
        reward=1.0,
    )


def test_click_success_reward_zero(make_client, fake_db):
    """答错（reward=0）同样透传成功。"""
    fake_db.query.return_value.filter.return_value.first.return_value = _make_student(
        "S1", "C1"
    )
    client = make_client(fake_db)
    payload = {**_VALID_PAYLOAD, "reward": 0}
    with patch.object(bandit_recommend, "can_view_class", return_value=True), \
            patch.object(bandit_recommend, "record_click_reward") as mock_record:
        resp = client.post(
            "/recommend/wrong-questions/click", json=payload, headers=_auth("u1")
        )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"success": True, "clicked": True, "reward": 0.0}
    mock_record.assert_called_once_with(
        db=fake_db,
        student_id="S1",
        subject="数学",
        kp_name="四则运算",
        reward=0.0,
    )


# ── reward 非法值 → 422 ──────────────────────────────


@pytest.mark.parametrize("bad_reward", [0.5, -1, 2])
def test_click_invalid_reward_422(make_client, fake_db, bad_reward):
    fake_db.query.return_value.filter.return_value.first.return_value = _make_student(
        "S1", "C1"
    )
    client = make_client(fake_db)
    payload = {**_VALID_PAYLOAD, "reward": bad_reward}
    resp = client.post(
        "/recommend/wrong-questions/click", json=payload, headers=_auth("u1")
    )
    assert resp.status_code == 422, resp.text


# ── 学生不存在 / 无班级访问权限 ───────────────────────


def test_click_student_not_found_404(make_client, fake_db):
    # fake_db 默认 first() 返回 None → 学生不存在
    client = make_client(fake_db)
    resp = client.post(
        "/recommend/wrong-questions/click", json=_VALID_PAYLOAD, headers=_auth("u1")
    )
    assert resp.status_code == 404, resp.text


def test_click_forbidden_no_class_access(make_client, fake_db):
    fake_db.query.return_value.filter.return_value.first.return_value = _make_student(
        "S1", "C1"
    )
    client = make_client(fake_db)
    with patch.object(bandit_recommend, "can_view_class", return_value=False):
        resp = client.post(
            "/recommend/wrong-questions/click", json=_VALID_PAYLOAD, headers=_auth("u1")
        )
    assert resp.status_code == 403, resp.text
    assert "forbidden" in resp.json()["detail"]


# ── PG 资产库未配置 → 503 ────────────────────────────


def test_click_assets_not_configured_503(make_client, fake_db):
    client = make_client(fake_db, assets_enabled=False)
    resp = client.post(
        "/recommend/wrong-questions/click", json=_VALID_PAYLOAD, headers=_auth("u1")
    )
    assert resp.status_code == 503, resp.text
    assert resp.json()["detail"]["reason"] == "assets db not configured"


# ── 端点到真实 record_click_reward 的完整调用链 ───────


def test_click_real_record_click_reward_updates_stats(make_client):
    """不 mock record_click_reward：走真实服务函数，验证 clicks/reward_sum 落库更新。

    用 _FakeDB 按模型分流：Student 查询返回学生行，BanditArmStats 查询返回 arm 行，
    确保链路（鉴权 → 学生校验 → 班级权限 → record_click_reward 更新）全通。
    """
    arm_row = SimpleNamespace(clicks=0, reward_sum=0.0, a_json=None)
    fdb = _FakeDB(student=_make_student("S1", "C1"), arm_row=arm_row)
    client = make_client(fdb)

    with patch.object(bandit_recommend, "can_view_class", return_value=True):
        resp = client.post(
            "/recommend/wrong-questions/click",
            json={**_VALID_PAYLOAD, "reward": 1.0},
            headers=_auth("u1"),
        )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"success": True, "clicked": True, "reward": 1.0}
    assert arm_row.clicks == 1
    assert arm_row.reward_sum == 1.0
    assert fdb.commits == 1


def test_click_real_record_click_reward_new_arm_row(make_client):
    """arm 行不存在时，record_click_reward 自动建行并回填 clicks/reward_sum。"""
    fdb = _FakeDB(student=_make_student("S1", "C1"), arm_row=None)
    client = make_client(fdb)

    with patch.object(bandit_recommend, "can_view_class", return_value=True):
        resp = client.post(
            "/recommend/wrong-questions/click",
            json={**_VALID_PAYLOAD, "reward": 0.0},
            headers=_auth("u1"),
        )

    assert resp.status_code == 200, resp.text
    assert len(fdb.added) == 1
    new_row = fdb.added[0]
    assert new_row.student_id == "S1"
    assert new_row.subject == "数学"
    assert new_row.kp_name == "四则运算"
    assert new_row.clicks == 1
    assert new_row.reward_sum == 0.0
