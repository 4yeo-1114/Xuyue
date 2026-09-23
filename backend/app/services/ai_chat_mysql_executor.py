# -*- coding: utf-8 -*-
"""AI 助教：执行大模型生成的只读 SELECT（主库，双引擎）。

- 默认 mysql：行为与历史完全一致（MySQL 方言白名单校验）。
- settings.db_engine == "postgresql"：主库切 PG 后，LLM 生成的 MySQL 方言 SQL
  先经 PG 翻译层（剥反引号 / IFNULL→COALESCE / 布尔字面量）再走 PG 白名单校验。
"""

from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.services.ai_chat_access import is_ai_chat_mysql_admin
from app.services.ai_chat_datasource import (
    MYSQL_SENSITIVE_COLUMNS as _SENSITIVE_USER_COLUMNS,
    serialize_cell,
    strip_sensitive_columns,
)
from app.services.ai_chat_mysql_scope import (
    ACCOUNT_ISOLATED_TABLES,
    ADMIN_ONLY_MYSQL_TABLES,
    apply_mysql_query_scope,
    get_mysql_allowed_tables,
)
from app.services.ai_chat_privacy import validate_sql_privacy
from app.services.ai_chat_sql_utils import (
    extract_sql_tables,
    validate_mysql_select,
    validate_pg_select,
)

# E09：AI 助教 SQL 结果集统一剥离的敏感列 —— 登录凭据 + 学生 PII（L3-L5）。
# 即使大模型拼出 SELECT phone, parent_phone, address ...，返回值也不会带到模型上下文。
# P2-4 批 2：常量迁入 ai_chat_datasource.MYSQL_SENSITIVE_COLUMNS（消除循环依赖），本模块别名引用。


def _strip_sensitive_columns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """薄包装：收敛后的参数化实现 + MySQL 敏感列集合（保留签名兼容既有测试/调用方）。"""
    return strip_sensitive_columns(rows, _SENSITIVE_USER_COLUMNS)


# F1b：主库切 PG 后，LLM 生成的 MySQL 方言 SQL 需先经 PG 翻译层再执行。
# 翻译思路复用 ai_chat_asset_executor._pg_dialect_preprocess：
# - 成对剥 MySQL 反引号（不能全局 replace，防破坏题干字符串内 markdown 代码块）
# - IFNULL(a, b) → COALESCE(a, b)
# - 已知 PG 布尔列（knowledge_points.is_weak）的 =1/=0 → =true/=false，避免误伤整数/浮点列
_BACKTICK_PAIR = re.compile(r"`([^`]+)`")
_IFNULL = re.compile(r"\bIFNULL\s*\(", re.IGNORECASE)
_PG_BOOLEAN_COLUMNS = frozenset({"is_weak"})
_BOOL_LITERAL = re.compile(
    r"\b(%s)\s*=\s*([10])\b" % "|".join(sorted(_PG_BOOLEAN_COLUMNS)),
    re.IGNORECASE,
)


def _pg_dialect_preprocess(sql: str) -> str:
    """把 LLM 生成的 MySQL 方言痕迹转成 PG 可执行：剥反引号、IFNULL→COALESCE、布尔字面量。"""
    out = _BACKTICK_PAIR.sub(r"\1", sql)
    out = _IFNULL.sub("COALESCE(", out)

    def _bool_literal(m: re.Match) -> str:
        return f"{m.group(1)} = {'true' if m.group(2) == '1' else 'false'}"

    out = _BOOL_LITERAL.sub(_bool_literal, out)
    return out


def execute_mysql_query(
    db: Session, user_id: str, sql: str, params: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    if not (user_id or "").strip():
        return {"success": False, "error": "未登录，无法查询", "rows": [], "row_count": 0}

    # M8：只读防线——原始 SQL 必须是以 SELECT 开头，任何写操作直接拒绝。
    # 注意：生产库应使用只读 MySQL 账号，这是数据库层兜底。
    if not re.match(r"^\s*SELECT\b", (sql or "").strip(), re.IGNORECASE):
        return {"success": False, "error": "只允许 SELECT 只读查询", "rows": [], "row_count": 0}

    admin = is_ai_chat_mysql_admin(db, user_id)
    allowed = get_mysql_allowed_tables(db, user_id)

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
        if settings.db_engine == "postgresql":
            # F1b：PG 主库执行前先套 PG 翻译层（剥反引号/IFNULL→COALESCE/布尔字面量），
            # 再走 PG 白名单校验路径（validate_pg_select 含 PG_FORBIDDEN + LIMIT 兜底）。
            pg_sql = _pg_dialect_preprocess(sql)
            scoped_sql = apply_mysql_query_scope(db, user_id, pg_sql, admin=admin)
            safe_sql = validate_pg_select(scoped_sql, allowed)
        else:
            scoped_sql = apply_mysql_query_scope(db, user_id, sql, admin=admin)
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
        result = db.execute(text(safe_sql), params or {})
        rows_raw = result.mappings().all()
        rows = [{key: serialize_cell(val) for key, val in row.items()} for row in rows_raw]
        rows = _strip_sensitive_columns(rows)
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
