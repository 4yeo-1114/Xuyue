# -*- coding: utf-8 -*-
"""P2-4 批4a：AiAuditLog 工具调用审计接线验收测试。

覆盖：
  1. 成功路径：execute_ai_chat_tool 写一条 event_type=tool_call 审计，tool_success/tool_name 正确
  2. 脱敏：入参 password 值替换为 "***"，sql 截断到 ≤500
  3. 失败不阻断：审计写入抛异常时，execute_ai_chat_tool 返回值不受影响
  4. 未知工具：仍返回 error dict 且写审计（tool_success=False）

审计为 best-effort 旁路：通过假 Session 捕获 db.add 的对象，不连库。
"""
import re
from types import SimpleNamespace

from app.models.ai_conversation import AiAuditLog
from app.services.ai_chat_datasource import DATA_SOURCES, DataSourceRegistration
from app.services.ai_chat_tools import _sanitize_audit_args, execute_ai_chat_tool


def _fake_local_reg(rows: list[dict]) -> DataSourceRegistration:
    """fake 注册项：execute 钩子直接返回固定成功 payload（避免依赖真实用户目录/DB）。"""
    return DataSourceRegistration(
        name="local",
        tool_name="execute_local_data_query",
        allowed_tables=frozenset({"local_exam_list"}),
        sensitive_columns=frozenset(),
        forbidden_keywords=re.compile(r"\bDROP\b"),
        execute=lambda uid, sql, db=None: {
            "success": True,
            "sql_executed": sql,
            "row_count": len(rows),
            "rows": rows,
        },
    )


def _capture_db():
    """假 Session：捕获 add 的对象；commit/rollback 为 no-op。"""
    calls = []
    db = SimpleNamespace(
        add=lambda obj: calls.append(obj),
        commit=lambda: None,
        rollback=lambda: None,
    )
    return db, calls


# ── 1. 成功路径 ───────────────────────────────────


def test_success_path_writes_tool_call_audit(monkeypatch):
    rows = [{"exam_title": "期中考试"}]
    monkeypatch.setitem(DATA_SOURCES, "execute_local_data_query", _fake_local_reg(rows))
    db, calls = _capture_db()

    out = execute_ai_chat_tool(
        db, "execute_local_data_query", {"sql": "SELECT * FROM local_exam_list"}, "u1"
    )
    assert out["success"] is True
    assert len(calls) == 1  # 一次调用最多写 1 条 tool_call 记录

    log = calls[0]
    assert isinstance(log, AiAuditLog)
    assert log.event_type == "tool_call"
    assert log.event_subtype == "execute_local_data_query"
    assert log.tool_name == "execute_local_data_query"
    assert log.user_id == "u1"
    assert log.tool_success is True
    assert log.conversation_id is None  # 当前调用链无对话上下文
    assert log.tool_args_json == {"sql": "SELECT * FROM local_exam_list"}
    assert "期中考试" in log.tool_result_summary  # 截断首行 JSON
    assert len(log.tool_result_summary) <= 300


# ── 2. 脱敏：password → "***"，sql 截断 ≤500 ──────


def test_audit_args_sanitized_and_sql_truncated(monkeypatch):
    monkeypatch.setitem(DATA_SOURCES, "execute_local_data_query", _fake_local_reg([]))
    db, calls = _capture_db()

    long_sql = "SELECT " + "a" * 600
    execute_ai_chat_tool(
        db,
        "execute_local_data_query",
        {
            "sql": long_sql,
            "password": "P@ssw0rd",
            "api_token": "tok123",
            "normal_key": "v",
        },
        "u1",
    )
    stored = calls[0].tool_args_json
    assert stored["password"] == "***"
    assert stored["api_token"] == "***"
    assert stored["normal_key"] == "v"
    assert len(stored["sql"]) <= 500
    assert stored["sql"] == long_sql[:500]


def test_sanitize_audit_args_recurses_nested_sensitive():
    out = _sanitize_audit_args(
        {"nested": {"password": "pw", "keep": "yes"}, "sql": "S" * 600}
    )
    assert out["nested"]["password"] == "***"
    assert out["nested"]["keep"] == "yes"
    assert len(out["sql"]) == 500


# ── 3. 失败不阻断 ─────────────────────────────────


def test_audit_failure_does_not_block_tool_result(monkeypatch):
    rows = [{"exam_title": "期中"}]
    monkeypatch.setitem(DATA_SOURCES, "execute_local_data_query", _fake_local_reg(rows))

    def boom(obj):
        raise RuntimeError("db down")

    db = SimpleNamespace(add=boom, commit=lambda: None, rollback=lambda: None)

    out = execute_ai_chat_tool(
        db, "execute_local_data_query", {"sql": "SELECT * FROM local_exam_list"}, "u1"
    )
    # 审计写入失败不阻断：返回值与无审计时（fake execute 直接返回）一致
    assert out == {
        "success": True,
        "sql_executed": "SELECT * FROM local_exam_list",
        "row_count": 1,
        "rows": rows,
    }


# ── 4. 未知工具 → error dict + 审计 tool_success=False ──


def test_unknown_tool_returns_error_and_writes_audit():
    db, calls = _capture_db()

    out = execute_ai_chat_tool(db, "definitely_not_a_tool", {"sql": "SELECT 1"}, "u1")
    assert out["success"] is False
    assert "未知工具" in out["error"]
    assert len(calls) == 1

    log = calls[0]
    assert log.event_type == "tool_call"
    assert log.tool_name == "definitely_not_a_tool"
    assert log.tool_success is False
    assert log.tool_result_summary == "未知工具: definitely_not_a_tool"


def test_registered_empty_sql_writes_audit_failure():
    # 命中注册表但空 SQL：返回错误 + 审计 tool_success=False（不连库）
    db, calls = _capture_db()

    out = execute_ai_chat_tool(db, "execute_mysql_query", {}, "u1")
    assert out["success"] is False
    assert len(calls) == 1

    log = calls[0]
    assert log.event_type == "tool_call"
    assert log.tool_success is False
    assert log.tool_result_summary == "请提供 sql 参数（只读 SELECT）"
