# -*- coding: utf-8 -*-
"""AI 助教 Tool 执行：大模型生成 SQL，后端安全执行。

P2-4 批 2：execute_ai_chat_tool 改为查 DataSourceRegistration 注册表 dispatch。
- 命中 DATA_SOURCES → 走注册项执行（local 走自定义 execute 钩子；mysql/asset 走统一 SQL 管线）。
- 未命中 → 回退原 if-branch（过渡，批 2.5 清理）。
- 最终未知工具返回 error dict，不抛 500。
对外行为不变：已有工具返回 payload 结构一字不变。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.assets.database import get_asset_db
from app.services.ai_chat_access import is_ai_chat_mysql_admin
from app.services.ai_chat_datasource import (
    DATA_SOURCES,
    DataSourceRegistration,
    serialize_cell,
    strip_sensitive_columns,
)
from app.services.ai_chat_local_executor import execute_local_data_query
from app.services.ai_chat_mysql_executor import execute_mysql_query
from app.services.ai_chat_mysql_scope import ACCOUNT_ISOLATED_TABLES, ADMIN_ONLY_MYSQL_TABLES
from app.services.ai_chat_privacy import validate_sql_privacy
from app.services.ai_chat_sql_utils import extract_sql_tables, validate_mysql_select

# 注册表 key 即 execute_ai_chat_tool 支持的工具名全集（完整性不变量，tests/test_ai_chat_dispatch.py 守护）。
QUERY_TOOL_NAMES = frozenset(DATA_SOURCES)

# 各工具的「SQL 为空」错误文案（注册表驱动路径与过渡 if-branch 共用，保持行为一致）。
_EMPTY_SQL_ERROR = {
    "execute_mysql_query": "请提供 sql 参数（只读 SELECT）",
    "execute_local_data_query": "请提供 sql 参数（local_* 虚拟表 SELECT）",
    "execute_asset_query": "请提供 sql 参数（只读 SELECT，资产库）",
}


def execute_ai_chat_tool(db: Session, tool_name: str, args: dict[str, Any], user_id: str) -> Any:
    args = args or {}
    sql = (args.get("sql") or args.get("query") or "").strip()

    registration = DATA_SOURCES.get(tool_name)
    if registration is not None:
        if not sql:
            result = {
                "success": False,
                "error": _EMPTY_SQL_ERROR.get(tool_name, "请提供 sql 参数"),
                "rows": [],
                "row_count": 0,
            }
        elif registration.execute is not None:
            # 非 SQL 自定义执行器（local 走 JSON 虚拟表管线）
            result = registration.execute(user_id, sql, db=db)
        else:
            # 统一 SQL 管线（mysql / asset）
            result = execute_registered_sql(
                db,
                user_id,
                sql,
                registration,
                empty_sql_error=_EMPTY_SQL_ERROR.get(tool_name, "请提供 sql 参数"),
            )
    elif tool_name == "execute_mysql_query":
        if not sql:
            result = {"success": False, "error": "请提供 sql 参数（只读 SELECT）", "rows": [], "row_count": 0}
        else:
            result = execute_mysql_query(db, user_id, sql)
    elif tool_name == "execute_local_data_query":
        if not sql:
            result = {"success": False, "error": "请提供 sql 参数（local_* 虚拟表 SELECT）", "rows": [], "row_count": 0}
        else:
            result = execute_local_data_query(user_id, sql, db=db)
    elif tool_name == "execute_asset_query":
        if not sql:
            result = {"success": False, "error": "请提供 sql 参数（只读 SELECT，资产库）", "rows": [], "row_count": 0}
        else:
            from app.services.ai_chat_asset_executor import execute_asset_query

            result = execute_asset_query(user_id, sql)
    else:
        result = {"success": False, "error": f"未知工具: {tool_name}"}

    # P2-4 批4a：AI 工具调用全程留痕（best-effort 旁路，失败不阻断主链路）。
    _audit_tool_call(db, user_id, tool_name, args, result)
    return result


# ── P2-4 批4a：AI 工具调用审计（AiAuditLog，best-effort 旁路）──────────────
_SENSITIVE_KEY_PATTERN = re.compile(r"(password|token|secret|credential)", re.IGNORECASE)
_SQL_KEY_MAX_LEN = 500
_SUMMARY_MAX_LEN = 300


def _sanitize_audit_value(key: str, value: Any) -> Any:
    """单值脱敏：敏感 key 的值一律替换为 "***"；sql/query 字符串截断到 500；
    嵌套结构递归处理；其余非 JSON 可序列化值 str() 兜底。"""
    if _SENSITIVE_KEY_PATTERN.search(key):
        return "***"
    if isinstance(value, dict):
        return {str(k): _sanitize_audit_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_audit_value(key, v) for v in value]
    if isinstance(value, str):
        if key.lower() in ("sql", "query"):
            return value[:_SQL_KEY_MAX_LEN]
        return value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _sanitize_audit_args(args: dict[str, Any]) -> dict[str, Any]:
    """审计入参脱敏：返回 JSON 可序列化子集（敏感值替换、sql 截断、其余 str() 兜底）。"""
    return {str(k): _sanitize_audit_value(str(k), v) for k, v in (args or {}).items()}


def _tool_result_summary(result: Any) -> str:
    """结果摘要：成功 → 截断的首行 JSON（前 300 字符）或 row_count=N；失败 → error 前 300 字符。"""
    if not isinstance(result, dict):
        return str(result)[:_SUMMARY_MAX_LEN]
    if result.get("success"):
        rows = result.get("rows")
        if isinstance(rows, list) and rows:
            return json.dumps(rows[0], ensure_ascii=False, default=str)[:_SUMMARY_MAX_LEN]
        return f"row_count={result.get('row_count', 0)}"
    error = result.get("error")
    return str(error if error is not None else result)[:_SUMMARY_MAX_LEN]


def _audit_tool_call(
    db: Session,
    user_id: str,
    tool_name: str,
    args: dict[str, Any],
    result: Any,
) -> None:
    """写一条 tool_call 审计（AiAuditLog，agent_audit_logs）。

    best-effort 旁路：任何失败仅 logger.warning，绝不影响工具执行结果返回。
    conversation_id 当前调用链无对话上下文，固定 None。
    """
    try:
        from app.models.ai_conversation import AiAuditLog

        log = AiAuditLog(
            user_id=user_id,
            conversation_id=None,
            event_type="tool_call",
            event_subtype=tool_name,
            tool_name=tool_name,
            tool_args_json=_sanitize_audit_args(args),
            tool_result_summary=_tool_result_summary(result),
            tool_success=bool(result.get("success")) if isinstance(result, dict) else False,
        )
        db.add(log)
        db.commit()
    except Exception as e:
        logger.warning("AI 工具调用审计写入失败(不阻断): %s", e)
        try:
            db.rollback()  # 恢复会话，避免脏状态影响主链路后续查询
        except Exception:
            pass


def execute_registered_sql(
    db: Session,
    user_id: str,
    sql: str,
    registration: DataSourceRegistration,
    *,
    empty_sql_error: str,
) -> dict[str, Any]:
    """统一 SQL 管线：SELECT 校验 → 白名单/禁词 → 可选行级 scope → 执行 → 敏感列剥离 → 序列化。

    由 DataSourceRegistration 驱动；mysql/asset 的源级差异（会话获取、PG 方言预处理、
    角色校验、返回结构附加字段）按 registration.name 分派。行为与
    ai_chat_mysql_executor.execute_mysql_query / ai_chat_asset_executor.execute_asset_query 一致。
    """
    if not (user_id or "").strip():
        return {"success": False, "error": "未登录，无法查询", "rows": [], "row_count": 0}

    sql_raw = (sql or "").strip()
    if not sql_raw:
        return {"success": False, "error": empty_sql_error, "rows": [], "row_count": 0}

    if not re.match(r"^\s*SELECT\b", sql_raw, re.IGNORECASE):
        return {"success": False, "error": "只允许 SELECT 只读查询", "rows": [], "row_count": 0}

    if registration.name == "mysql":
        return _execute_mysql_sql(db, user_id, sql_raw, registration)
    if registration.name == "asset":
        return _execute_asset_sql(user_id, sql_raw, registration)
    return {
        "success": False,
        "error": f"数据源 {registration.name} 不支持统一 SQL 管线",
        "rows": [],
        "row_count": 0,
    }


def _execute_mysql_sql(
    db: Session,
    user_id: str,
    sql: str,
    registration: DataSourceRegistration,
) -> dict[str, Any]:
    """MySQL 只读执行（对应 ai_chat_mysql_executor.execute_mysql_query 的行为）。"""
    admin = is_ai_chat_mysql_admin(db, user_id)
    allowed = registration.allowed_tables(db, user_id)  # Callable(db, user_id) -> frozenset

    privacy_err = validate_sql_privacy(sql)
    if privacy_err:
        return {"success": False, "error": privacy_err, "rows": [], "row_count": 0}

    try:
        tables = extract_sql_tables(sql)
        if not admin and tables & ADMIN_ONLY_MYSQL_TABLES:
            return {
                "success": False,
                "error": (
                    "无权查询该教务表，请改用 lesson_plans、smart_exam_papers、"
                    "targeted_improvement_reports、class_review_sessions 或 local_* 虚拟表。"
                ),
                "rows": [],
                "row_count": 0,
            }
        scoped_sql = registration.scope(db, user_id, sql, admin=admin)
        safe_sql = validate_mysql_select(scoped_sql, allowed)
        account_scoped = bool(extract_sql_tables(sql) & ACCOUNT_ISOLATED_TABLES)
    except ValueError as e:
        return {"success": False, "error": str(e), "rows": [], "row_count": 0}

    if re.search(r"\bpassword_hash\b|\bplain_password\b", safe_sql, re.IGNORECASE):
        return {
            "success": False,
            "error": "禁止查询 password_hash、plain_password 等敏感字段",
            "rows": [],
            "row_count": 0,
        }

    try:
        result = db.execute(text(safe_sql), {})
        rows_raw = result.mappings().all()
        rows = [{key: serialize_cell(val) for key, val in row.items()} for row in rows_raw]
        rows = strip_sensitive_columns(rows, registration.sensitive_columns)
        payload: dict[str, Any] = {
            "success": True,
            "sql_executed": safe_sql,
            "row_count": len(rows),
            "rows": rows,
            "scoped": True,
            "account_isolated": account_scoped,
        }
        if account_scoped:
            payload["scope_note"] = "教案/组卷结果已限定为当前登录账号，不含其他教师数据。"
        if not rows:
            payload["message"] = "查询成功但无匹配记录，回答用户时必须说明「未查询到」，禁止编造。"
        return payload
    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "error": f"SQL 执行失败: {e}",
            "sql_executed": safe_sql,
            "rows": [],
            "row_count": 0,
        }


def _execute_asset_sql(
    user_id: str,
    sql: str,
    registration: DataSourceRegistration,
) -> dict[str, Any]:
    """资产库（家长端 PG 镜像）只读执行（对应 ai_chat_asset_executor.execute_asset_query）。"""
    from app.services.ai_chat_asset_executor import _pg_dialect_preprocess

    safe_sql = _pg_dialect_preprocess(sql)
    try:
        safe_sql = validate_mysql_select(safe_sql, registration.allowed_tables)
    except ValueError as e:
        return {"success": False, "error": str(e), "rows": [], "row_count": 0}

    # 审核硬要求：资产查询不接收 db 参数，内部自建资产 session（未配置时抛 503）
    try:
        gen = get_asset_db()
        db = next(gen)
    except HTTPException:
        return {
            "success": False,
            "error": "资产库不可用",
            "rows": [],
            "row_count": 0,
        }

    try:
        result = db.execute(text(safe_sql))
        rows_raw = result.mappings().all()
        rows = [{key: serialize_cell(val) for key, val in row.items()} for row in rows_raw]
        rows = strip_sensitive_columns(rows, registration.sensitive_columns)
        payload: dict[str, Any] = {
            "success": True,
            "sql_executed": safe_sql,
            "row_count": len(rows),
            "rows": rows,
        }
        if not rows:
            payload["message"] = "查询成功但无匹配记录，回答用户时必须说明「未查询到」，禁止编造。"
        return payload
    except Exception as e:  # 含 OperationalError：资产库不可用/查询失败，不抛 500
        return {
            "success": False,
            "error": f"资产库查询失败: {e}",
            "sql_executed": safe_sql,
            "rows": [],
            "row_count": 0,
        }
    finally:
        # 关闭 get_asset_db 生成的 session（触发其 finally → db.close()）
        next(gen, None)


def parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}
