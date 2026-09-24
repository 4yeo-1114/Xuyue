# -*- coding: utf-8 -*-
"""升级库补列验收：users.dingtalk_userid 必须在**默认配置**下被补上。

真库实测的缺陷：任何早于 User.dingtalk_userid 这个 ORM 字段的库，升级后
`SELECT users.id, ..., users.dingtalk_userid, ... FROM users WHERE users.email = %s`
报 (1054, "Unknown column 'users.dingtalk_userid' in 'field list'")
⇒ 自助注册、登录全线 HTTP 500。

修复落点是 _ensure_dingtalk_sync_columns()（database.py），由 init_db() **无条件**
调用（main.py:65-66 lifespan → init_db()，每次启动都跑）；
而 _ensure_user_extra_columns() 挂在 sync_database_schema() 里，位于
`if not AUTO_DDL: return`（database.py:85-86）之后 ⇒ **默认 AUTO_DDL=false 时一次都不执行**。
所以本测试的区分度 = 「默认配置下 init_db() 这条启动路径有没有覆盖它」，
光断言「某个 helper 的语句集合里含这一列」判不出这个差别。

测试做法（复现默认部署配置下的真实启动路径，不调 helper、直接调 init_db）：
  1. in-memory SQLite 造一张**旧库形态**的 users 表（无 dingtalk_userid、无该索引）
  2. 把 database.engine / SessionLocal 指到该 SQLite
  3. 调 init_db()
  4. 断言列 / 索引被补上，且那条曾经报 1054 的 ORM 查询能跑通

⚠ 诚实声明（本测试**不**验证的部分，别当它验过）：
  - **不是真 MySQL**。验证的是「默认配置下这条 ALTER / CREATE INDEX 会不会被真的
    发出」+「语句本身能被 SQL 引擎接受」；⛔ 不验证 MySQL 专有语义（重复执行的报错
    文案、utf8mb4、ADD INDEX 语法差异等）。真库行为的证据是真库实测，不是本文件。
  - type="sqlite" 的 engine 是**替换**（monkeypatch）进去的，不是产品 engine。
  - SessionLocal 一并替换，是为了让 _backfill_class_teacher_heads 不连真库——
    否则这会变成一条**会写真实数据库**的测试。
"""
from __future__ import annotations

import os

# 必须在 `from app import database` 之前：本 worktree 的 backend/.env（gitignore 的
# 本地文件）里 AUTO_DDL=true，会让 app/database.py:33-34 在**导入期**就 _ensure_database()
# 连真库；本机 3306 无 MySQL ⇒ 收集阶段直接 OperationalError，测试根本跑不起来。
# false 同时是 app/config.py:63 的默认值，也正是本缺陷所要求的「默认部署配置」。
os.environ.setdefault("AUTO_DDL", "false")

from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import database  # noqa: E402
from app.database import init_db  # noqa: E402
from app.models.user import User  # noqa: E402

# 旧库形态的 users：除 dingtalk_userid 外与 User 模型逐列对齐
_LEGACY_USERS_DDL = """
CREATE TABLE users (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(255) NULL,
    phone VARCHAR(32) NULL,
    teaching_subject VARCHAR(32) NULL,
    roles VARCHAR(255) NULL,
    job_title VARCHAR(255) NULL,
    personal_email VARCHAR(255) NULL,
    ui_locale VARCHAR(8) NULL DEFAULT 'zh',
    created_at DATETIME NULL,
    updated_at DATETIME NULL
)
"""

_INDEX_NAME = "ix_users_dingtalk_userid"


def _columns(engine, table: str) -> set:
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {r[1] for r in rows}


def _index_names(engine, table: str) -> list:
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA index_list({table})")).fetchall()
    return [r[1] for r in rows]


@pytest.fixture()
def legacy_db(monkeypatch):
    """默认配置（AUTO_DDL=false）+ 一张旧库形态的 users 表。"""
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text(_LEGACY_USERS_DDL))
        conn.commit()

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
    # 这一句是「默认配置」的显式化：AUTO_DDL 默认 False（config.py:63），
    # 本 worktree 的本地 .env 把它开成了 true。断言而非静默，防止有人改了默认值后
    # 这条测试变成在验证另一条路径还不自知。
    monkeypatch.setattr(database, "settings", SimpleNamespace(AUTO_DDL=False))
    try:
        yield engine
    finally:
        engine.dispose()


# ── 判据 1：默认配置下，启动路径必须补上列 ──────────────────────────────
# 红：把 ALTER 放进 _ensure_user_extra_columns()（AUTO_DDL 提前返回之后）⇒ 缺列 ⇒ FAIL
def test_init_db_adds_users_dingtalk_userid_without_auto_ddl(legacy_db):
    assert "dingtalk_userid" not in _columns(legacy_db, "users"), "夹具没造出旧库形态"

    init_db()

    assert "dingtalk_userid" in _columns(legacy_db, "users")


# ── 判据 2：补列后，那条报 1054 的 ORM 查询必须能跑通 ────────────────────
# 红：同判据 1（缺列时 SQLAlchemy 渲染出的 SELECT 会命中不存在的列）
def test_orm_user_query_works_after_init_db(legacy_db):
    init_db()

    session = sessionmaker(bind=legacy_db)()
    try:
        # SQLAlchemy 把 users.dingtalk_userid 一并渲染进 SELECT 列表 —— 即 500 那条语句
        assert session.query(User).filter(User.email == "nobody@example.com").first() is None
    finally:
        session.close()


# ── 判据 3：ORM 声明了 index=True，升级库必须补上同名索引 ────────────────
# 红：去掉 CREATE INDEX 那段 ⇒ 索引不存在 ⇒ FAIL（与判据 1 相互独立）
def test_init_db_adds_users_dingtalk_userid_index(legacy_db):
    assert _INDEX_NAME not in _index_names(legacy_db, "users"), "夹具没造出旧库形态"

    init_db()

    assert _INDEX_NAME in _index_names(legacy_db, "users")


# ── 判据 4：幂等 —— init_db 每次启动都跑，补列语句必须可重复执行 ──────────
# 红：把逐语句 try/except 兜底去掉 ⇒ 第二次 init_db() 抛「已存在」⇒ ERROR
def test_init_db_dingtalk_backfill_is_idempotent(legacy_db):
    init_db()
    init_db()

    assert "dingtalk_userid" in _columns(legacy_db, "users")
    assert _index_names(legacy_db, "users").count(_INDEX_NAME) == 1
