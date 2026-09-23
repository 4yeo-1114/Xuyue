# -*- coding: utf-8 -*-
"""P2-4 批2：DataSourceRegistration 注册表 + execute_ai_chat_tool 查表 dispatch 验收测试。

覆盖：
  1. 完整性不变量：DATA_SOURCES 的 key 完整覆盖 execute_ai_chat_tool 支持的工具名
  2. execute_ai_chat_tool 对未知工具返回 error dict（不 500）
  3. 配置不变量：每项注册的 sensitive_columns / scope / allowed_tables 有值且类型正确
  4. 统一 SQL 管线纯函数级用例：mysql / asset 各一个（注入 mock 避免 DB 依赖）

环境：除显式 monkeypatch 的 DB 依赖外不连库（conftest.py 已注入最小 env 配置）。
"""
import re
from types import SimpleNamespace

from app.services.ai_chat_datasource import DATA_SOURCES, DataSourceRegistration
from app.services.ai_chat_tools import QUERY_TOOL_NAMES, execute_ai_chat_tool, execute_registered_sql


# ── 1. 完整性不变量 ───────────────────────────


def test_data_sources_cover_all_execute_tool_names():
    # DATA_SOURCES 的 key 必须与 execute_ai_chat_tool 支持的 tool_name 全集一一对应
    assert set(DATA_SOURCES) == set(QUERY_TOOL_NAMES)
    assert set(DATA_SOURCES) == {
        "execute_mysql_query",
        "execute_local_data_query",
        "execute_asset_query",
    }


# ── 2. 未知工具 → error dict ──────────────────


def test_unknown_tool_returns_error_dict():
    result = execute_ai_chat_tool(None, "definitely_not_a_tool", {"sql": "SELECT 1"}, "u1")
    assert result["success"] is False
    assert "未知工具" in result["error"]


# ── 3. 配置不变量 ────────────────────────────


def test_registration_config_invariants():
    assert len(DATA_SOURCES) == 3
    for tool_name, reg in DATA_SOURCES.items():
        assert isinstance(reg, DataSourceRegistration)
        assert reg.name in {"mysql", "asset", "local"}
        assert reg.tool_name == tool_name
        # sensitive_columns：非空 frozenset
        assert isinstance(reg.sensitive_columns, frozenset)
        # allowed_tables：frozenset 固定白名单，或 Callable 取白名单
        assert isinstance(reg.allowed_tables, frozenset) or callable(reg.allowed_tables)
        # forbidden_keywords：正则模式（带 .search）
        assert reg.forbidden_keywords is not None and hasattr(reg.forbidden_keywords, "search")
        # scope：None（无行级注入）或 Callable
        assert reg.scope is None or callable(reg.scope)
        # execute：None（走统一 SQL 管线）或 Callable（非 SQL 自定义执行器）
        assert reg.execute is None or callable(reg.execute)
        # 注册表 key 与 tool_name 双向一致
        assert DATA_SOURCES[reg.tool_name] is reg

    # mysql：动态白名单（Callable）+ 行级 scope + 学生 PII 敏感列
    mysql = DATA_SOURCES["execute_mysql_query"]
    assert mysql.name == "mysql"
    assert callable(mysql.allowed_tables)
    assert mysql.scope is not None and callable(mysql.scope)
    assert {"phone", "password_hash", "parent_phone", "address", "birthday"} <= mysql.sensitive_columns

    # asset：固定白名单 + 无 scope + 家长 PII/学习状态敏感列
    asset = DATA_SOURCES["execute_asset_query"]
    assert asset.name == "asset"
    assert isinstance(asset.allowed_tables, frozenset)
    assert asset.scope is None
    assert {"user_id", "mastery", "is_weak", "phone", "email"} <= asset.sensitive_columns

    # local：自定义 execute 钩子 + 仅 local_* 虚拟表
    local = DATA_SOURCES["execute_local_data_query"]
    assert local.name == "local"
    assert local.execute is not None and callable(local.execute)
    assert isinstance(local.allowed_tables, frozenset)
    assert local.allowed_tables and all(t.startswith("local_") for t in local.allowed_tables)


# ── 4. 统一 SQL 管线纯函数级用例（mock 避免 DB 依赖）────


def test_registered_sql_pipeline_mysql_strips_sensitive_columns(monkeypatch):
    from app.services import ai_chat_tools as tools

    monkeypatch.setattr(tools, "is_ai_chat_mysql_admin", lambda db, uid: False)
    monkeypatch.setattr(tools, "validate_sql_privacy", lambda sql: None)

    reg = DataSourceRegistration(
        name="mysql",
        tool_name="execute_mysql_query",
        allowed_tables=lambda db, uid: frozenset({"classes"}),
        sensitive_columns=frozenset({"phone", "parent_phone"}),
        forbidden_keywords=re.compile(r"\bDROP\b"),
        scope=lambda db, uid, sql, admin: sql,  # 本用例无实际 scope 注入
    )

    class FakeResult:
        def mappings(self):
            return SimpleNamespace(
                all=lambda: [{"id": "S1", "name": "张三", "phone": "13800138000"}]
            )

    db = SimpleNamespace(execute=lambda *a, **k: FakeResult(), rollback=lambda: None)

    out = execute_registered_sql(
        db, "u1", "SELECT id, name, phone FROM classes LIMIT 1", reg, empty_sql_error="请提供 sql"
    )
    assert out["success"] is True
    assert out["rows"] == [{"id": "S1", "name": "张三"}]
    assert "phone" not in out["rows"][0]
    assert out["scoped"] is True
    assert out["account_isolated"] is False


def test_registered_sql_pipeline_asset_uses_asset_db_and_strips(monkeypatch):
    from app.services import ai_chat_tools as tools

    reg = DataSourceRegistration(
        name="asset",
        tool_name="execute_asset_query",
        allowed_tables=frozenset({"questions"}),
        sensitive_columns=frozenset({"user_id", "mastery", "is_weak"}),
        forbidden_keywords=re.compile(r"\bDROP\b"),
    )

    class FakeResult:
        def mappings(self):
            return SimpleNamespace(
                all=lambda: [{"id": "Q1", "user_id": "u1", "mastery": 0.9, "is_weak": False}]
            )

    def fake_get_asset_db():
        yield SimpleNamespace(execute=lambda *a, **k: FakeResult())

    monkeypatch.setattr(tools, "get_asset_db", fake_get_asset_db)

    out = execute_registered_sql(
        None,
        "u1",
        "SELECT id, user_id, mastery, is_weak FROM questions LIMIT 1",
        reg,
        empty_sql_error="请提供 sql",
    )
    assert out["success"] is True
    assert out["rows"] == [{"id": "Q1"}]
    assert "user_id" not in out["rows"][0]
    assert "mastery" not in out["rows"][0]


# ── 5. execute_ai_chat_tool 注册表路径冒烟（不连 DB）────


def test_execute_ai_chat_tool_registered_empty_sql_error():
    # 命中注册表：空 SQL 返回各工具专属错误文案（不 500）
    out = execute_ai_chat_tool(None, "execute_mysql_query", {}, "u1")
    assert out == {
        "success": False,
        "error": "请提供 sql 参数（只读 SELECT）",
        "rows": [],
        "row_count": 0,
    }


def test_execute_ai_chat_tool_local_dispatch_via_registry():
    # local 走注册表 execute 钩子：目录不存在返回 error dict（不连 DB）
    out = execute_ai_chat_tool(
        None, "execute_local_data_query", {"sql": "SELECT * FROM local_exam_list"}, "__no_such_user__"
    )
    assert out["success"] is False
    assert out["rows"] == []
