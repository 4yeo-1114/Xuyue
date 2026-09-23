# -*- coding: utf-8 -*-
"""AI 助教：执行资产库（家长端 PG 镜像）只读 SELECT。

参照 ai_chat_mysql_executor.execute_mysql_query 的只读执行模式：
SELECT-only 校验 → PG 方言预处理 → 表名白名单 → LIMIT 兜底 → 敏感列剥离 → 行序列化。

与 MySQL executor 的关键差异：
- 不接收 db 参数：内部用 get_asset_db() 自建资产 session，零污染主 MySQL session
  （审核硬要求：不改 execute_ai_chat_tool 签名）。
- 资产库未配置/连不上时返回 error dict，不抛 500。
- 仅执行 SELECT，资产查询只读，绝无 INSERT/UPDATE。
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text

from app.assets.database import get_asset_db
from app.services.ai_chat_asset_scope import (
    ASSET_ALLOWED_TABLES,
    ASSET_SENSITIVE_COLUMNS,
)
from app.services.ai_chat_datasource import serialize_cell, strip_sensitive_columns
from app.services.ai_chat_sql_utils import validate_mysql_select

# PG 方言预处理：成对剥 MySQL 反引号（不能全局 replace，防破坏题干字符串内 markdown 代码块）
_BACKTICK_PAIR = re.compile(r"`([^`]+)`")
_IFNULL = re.compile(r"\bIFNULL\s*\(", re.IGNORECASE)

# 已知 PG 布尔列（knowledge_points.is_weak），只转换布尔列的 =1/=0，避免误伤整数/浮点列
_PG_BOOLEAN_COLUMNS = frozenset({"is_weak"})
_BOOL_LITERAL = re.compile(
    r"\b(%s)\s*=\s*([10])\b" % "|".join(sorted(_PG_BOOLEAN_COLUMNS)),
    re.IGNORECASE,
)


def _pg_dialect_preprocess(sql: str) -> str:
    """把 MySQL 方言痕迹转成 PG 可执行：剥反引号、IFNULL→COALESCE、布尔字面量。"""
    out = _BACKTICK_PAIR.sub(r"\1", sql)
    out = _IFNULL.sub("COALESCE(", out)

    def _bool_literal(m: re.Match) -> str:
        return f"{m.group(1)} = {'true' if m.group(2) == '1' else 'false'}"

    out = _BOOL_LITERAL.sub(_bool_literal, out)
    return out


def _strip_sensitive_columns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """薄包装：收敛后的参数化实现 + 资产库敏感列集合（家长端学习状态 + 家长 PII）。"""
    return strip_sensitive_columns(rows, ASSET_SENSITIVE_COLUMNS)


def execute_asset_query(user_id: str, sql: str) -> dict[str, Any]:
    """只读执行资产库 SELECT，返回 {success, rows, row_count}。"""
    if not (user_id or "").strip():
        return {"success": False, "error": "未登录，无法查询", "rows": [], "row_count": 0}

    sql_raw = (sql or "").strip()
    if not sql_raw:
        return {"success": False, "error": "SQL 不能为空", "rows": [], "row_count": 0}

    # 只读防线：原始 SQL 必须以 SELECT 开头，任何写操作直接拒绝
    if not re.match(r"^\s*SELECT\b", sql_raw, re.IGNORECASE):
        return {"success": False, "error": "只允许 SELECT 只读查询", "rows": [], "row_count": 0}

    # PG 方言预处理 → 白名单/防多语句/禁止关键字/LIMIT 兜底（复用 validate_mysql_select）
    try:
        safe_sql = _pg_dialect_preprocess(sql_raw)
        safe_sql = validate_mysql_select(safe_sql, ASSET_ALLOWED_TABLES)
    except ValueError as e:
        return {"success": False, "error": str(e), "rows": [], "row_count": 0}

    # 审核硬要求：不接收 db 参数，内部自建资产 session（get_asset_db 未配置时抛 503）
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
        rows = _strip_sensitive_columns(rows)
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
