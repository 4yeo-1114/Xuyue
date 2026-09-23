# -*- coding: utf-8 -*-
"""AI 助教：数据源注册表 + 结果集敏感列剥离 + 单元格序列化（统一实现）。

P2-4 批 1：把 ai_chat_mysql_executor / ai_chat_asset_executor 各自维护的一份
「敏感列剥离 + 行序列化」逻辑参数化收敛到这里，行为与原两份实现完全一致：

- strip_sensitive_columns：从结果行中剔除 sensitive_columns 命中的列，
  具体集合由各 executor 的常量传入（mysql 7 列 / asset 11 列不同）。
- serialize_cell：统一两种序列化——Decimal→float、datetime/date→isoformat、
  其余原样（防 json.dumps 崩溃）。mysql 原只 isoformat 但 Decimal 也可能出现，
  asset 已处理 Decimal，收敛后两者都安全。

P2-4 批 2：新增 DataSourceRegistration 数据源注册表 + DATA_SOURCES 常量，
把「每个 LLM 可见工具 → 数据源执行所需的元数据」集中到一处，execute_ai_chat_tool
改为查表 dispatch（见 ai_chat_tools.execute_ai_chat_tool）。MySQL 敏感列集合
MYSQL_SENSITIVE_COLUMNS 从 ai_chat_mysql_executor 迁入（消除 executor → 本模块的
循环依赖），executor 侧改为 import 本常量，对外行为不变。

本模块只提供注册表 + 纯工具函数，不涉及 AI 意图链路，供各 executor / dispatch 复用。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Optional

from app.services.ai_chat_asset_scope import ASSET_ALLOWED_TABLES, ASSET_SENSITIVE_COLUMNS
from app.services.ai_chat_local_executor import LOCAL_ALLOWED_TABLES, execute_local_data_query
from app.services.ai_chat_mysql_scope import apply_mysql_query_scope, get_mysql_allowed_tables
from app.services.ai_chat_sql_utils import _FORBIDDEN, PG_FORBIDDEN

# 占位默认敏感列（空集）：具体集合仍由各 executor 传入，避免隐式默认值泄敏。
_DEFAULT_SENSITIVE_COLUMNS: frozenset[str] = frozenset()

# E09：AI 助教 SQL 结果集统一剥离的 MySQL 敏感列 —— 登录凭据 + 学生 PII（L3-L5）。
# 从 ai_chat_mysql_executor 迁入，作为注册表与 executor 共享的唯一来源（防漂移泄敏）。
MYSQL_SENSITIVE_COLUMNS: frozenset[str] = frozenset(
    {
        "password_hash",
        "plain_password",
        "phone",
        "parent_name",
        "parent_phone",
        "address",
        "birthday",
    }
)


@dataclass(frozen=True)
class DataSourceRegistration:
    """数据源注册项：LLM 可见工具 → 数据源执行所需的全部元数据。

    - name：数据源名（"mysql" | "asset" | "local"）。
    - tool_name：LLM 可见工具名（execute_ai_chat_tool 的入参）。
    - allowed_tables：表名白名单。frozenset 固定白名单（asset/local），
      或 Callable(db, user_id) -> frozenset（mysql 按角色动态取）。
    - sensitive_columns：结果集强制剥离的敏感列（返回结构必不含这些列）。
    - forbidden_keywords：SQL 禁止关键字正则（mysql=_FORBIDDEN，asset=PG_FORBIDDEN）。
    - scope：行级 scope 注入函数（mysql 有 apply_mysql_query_scope；asset/local 暂无 → None）。
    - execute：非 SQL 自定义执行器钩子（local 用 execute_local_data_query）；
      None 表示走统一 SQL 管线（mysql/asset）。
    """

    name: str
    tool_name: str
    allowed_tables: Any
    sensitive_columns: frozenset[str]
    forbidden_keywords: Any
    scope: Optional[Callable[..., Any]] = None
    execute: Optional[Callable[..., Any]] = None


# 注册表：key 与 execute_ai_chat_tool 支持的 tool_name 一一对应（完整性不变量，测试守护）。
DATA_SOURCES: dict[str, DataSourceRegistration] = {
    "execute_mysql_query": DataSourceRegistration(
        name="mysql",
        tool_name="execute_mysql_query",
        allowed_tables=get_mysql_allowed_tables,  # Callable(db, user_id) -> frozenset，按角色
        sensitive_columns=MYSQL_SENSITIVE_COLUMNS,
        forbidden_keywords=_FORBIDDEN,
        scope=apply_mysql_query_scope,
    ),
    "execute_asset_query": DataSourceRegistration(
        name="asset",
        tool_name="execute_asset_query",
        allowed_tables=ASSET_ALLOWED_TABLES,
        sensitive_columns=ASSET_SENSITIVE_COLUMNS,
        forbidden_keywords=PG_FORBIDDEN,
    ),
    "execute_local_data_query": DataSourceRegistration(
        name="local",
        tool_name="execute_local_data_query",
        allowed_tables=LOCAL_ALLOWED_TABLES,
        sensitive_columns=frozenset(),  # 本地 grading_data 为用户本人数据，无额外剥离
        forbidden_keywords=_FORBIDDEN,
        execute=execute_local_data_query,
    ),
}


def strip_sensitive_columns(
    rows: list[dict[str, Any]],
    sensitive_columns: frozenset[str] = _DEFAULT_SENSITIVE_COLUMNS,
) -> list[dict[str, Any]]:
    """剔除结果集中属于 sensitive_columns 的列，返回新 dict 列表（不改原行）。

    行为与原 mysql/asset 两份 _strip_sensitive_columns 完全一致：
    保留未命中的列，原样透传；rows 可为空或含 None 值（None 值列不受影响）。
    """
    return [
        {k: v for k, v in row.items() if k not in sensitive_columns}
        for row in rows
    ]


def serialize_cell(value: Any) -> Any:
    """Decimal → float，datetime/date → isoformat，其余原样（防 json.dumps 崩溃）。"""
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
