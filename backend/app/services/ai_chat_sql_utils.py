# -*- coding: utf-8 -*-
"""AI 助教：只读 SELECT 语句校验与简易解析。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|GRANT|REVOKE|"
    r"INTO\s+OUTFILE|LOAD_FILE|SLEEP|BENCHMARK|EXEC|EXECUTE|CALL|SET\s+@)\b",
    re.IGNORECASE,
)

# PG 专属危险关键字：_FORBIDDEN 是 MySQL 关键词集，\bSLEEP\b 不匹配 pg_sleep，
# 必须补充 PG 函数/运算符（审核硬要求）。
PG_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|GRANT|REVOKE|"
    r"INTO\s+OUTFILE|LOAD_FILE|SLEEP|BENCHMARK|EXEC|EXECUTE|CALL|SET\s+@|"
    r"PG_SLEEP|COPY|LO_IMPORT|LO_EXPORT|DBLINK|PG_READ_FILE|PG_READ_BINARY_FILE|"
    r"PG_STAT_FILE)\b",
    re.IGNORECASE,
)

_FROM_JOIN = re.compile(r"\b(?:FROM|JOIN)\s+`?([a-zA-Z_][a-zA-Z0-9_]*)`?", re.IGNORECASE)


@dataclass
class ParsedSelect:
    raw_sql: str
    columns: list[str]
    table: str
    where_sql: Optional[str] = None
    order_by: Optional[str] = None
    limit: int = 100
    distinct: bool = False
    where_conditions: list[tuple[str, str, str]] = field(default_factory=list)


def _strip_comments(sql: str) -> str:
    s = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    s = re.sub(r"--[^\n]*", " ", s)
    return s


def extract_sql_tables(sql: str) -> set[str]:
    text = _strip_comments((sql or "").strip())
    return {t.lower() for t in _FROM_JOIN.findall(text)}


def inject_scope_conditions(sql: str, conditions: list[str]) -> str:
    """在 SELECT 中注入 AND 条件（用于教师数据隔离）。"""
    if not conditions:
        return sql
    combined = " AND ".join(f"({c})" for c in conditions)
    text = (sql or "").strip().rstrip(";")
    if re.search(r"\bWHERE\b", text, re.IGNORECASE):
        m = re.search(r"\b(GROUP BY|ORDER BY|LIMIT)\b", text, re.IGNORECASE)
        if m:
            return text[: m.start()] + f" AND {combined} " + text[m.start() :]
        return f"{text} AND {combined}"
    m = re.search(r"\b(GROUP BY|ORDER BY|LIMIT)\b", text, re.IGNORECASE)
    if m:
        return text[: m.start()] + f" WHERE {combined} " + text[m.start() :]
    return f"{text} WHERE {combined}"


def validate_mysql_select(sql: str, allowed_tables: frozenset[str]) -> str:
    text = _strip_comments((sql or "").strip()).strip().rstrip(";")
    if not text:
        raise ValueError("SQL 不能为空")
    if not re.match(r"^SELECT\b", text, re.IGNORECASE):
        raise ValueError("只允许 SELECT 查询")
    if _FORBIDDEN.search(text):
        raise ValueError("SQL 含有禁止的操作或关键字")
    if ";" in text:
        raise ValueError("不允许多语句")
    tables = {t.lower() for t in _FROM_JOIN.findall(text)}
    if not tables:
        raise ValueError("未能识别 FROM/JOIN 表名")
    unknown = tables - {t.lower() for t in allowed_tables}
    if unknown:
        raise ValueError(f"不允许查询的表: {', '.join(sorted(unknown))}")
    if not re.search(r"\bLIMIT\b", text, re.IGNORECASE):
        text = f"{text} LIMIT 100"
    return text


def validate_local_select(sql: str, allowed_tables: frozenset[str]) -> str:
    text = validate_mysql_select(sql, allowed_tables)
    tables = {t.lower() for t in _FROM_JOIN.findall(text)}
    if not tables.issubset({t.lower() for t in allowed_tables}):
        raise ValueError("本地查询只能使用 local_ 开头的虚拟表")
    if any(not t.startswith("local_") for t in tables):
        raise ValueError("本地查询只能使用 local_ 开头的虚拟表")
    return text


def normalize_pg_sql(sql: str) -> str:
    """PG 方言预处理：剥反引号、IFNULL→COALESCE、LIMIT 兜底。

    - 反引号成对剥除（r"`([^`]+)`" → \\1），禁止全局 replace，防破坏题干字符串内 markdown 代码块。
    - IFNULL( → COALESCE(，大小写不敏感。
    - 无 LIMIT 时追加 LIMIT 100（参照 validate_mysql_select 逻辑）。
    """
    text = _strip_comments((sql or "").strip()).strip().rstrip(";")
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\bIFNULL\s*\(", "COALESCE(", text, flags=re.IGNORECASE)
    if not re.search(r"\bLIMIT\b", text, re.IGNORECASE):
        text = f"{text} LIMIT 100"
    return text


def validate_pg_select(sql: str, allowed_tables: frozenset[str]) -> str:
    """PG 资产库只读 SELECT 校验：与 validate_mysql_select 平行，互不影响。

    normalize_pg_sql 预处理后：仅 SELECT + 禁止 PG_FORBIDDEN + 防多语句(;) +
    表名白名单（复用 extract_sql_tables，表名 ⊆ allowed_tables）+ LIMIT 兜底。
    """
    text = normalize_pg_sql(sql)
    if not text:
        raise ValueError("SQL 不能为空")
    if not re.match(r"^SELECT\b", text, re.IGNORECASE):
        raise ValueError("只允许 SELECT 查询")
    if PG_FORBIDDEN.search(text):
        raise ValueError("SQL 含有禁止的操作或关键字")
    if ";" in text:
        raise ValueError("不允许多语句")
    tables = extract_sql_tables(text)
    if not tables:
        raise ValueError("未能识别 FROM/JOIN 表名")
    unknown = tables - {t.lower() for t in allowed_tables}
    if unknown:
        raise ValueError(f"不允许查询的表: {', '.join(sorted(unknown))}")
    return text


def parse_simple_select(sql: str) -> ParsedSelect:
    """解析单表 SELECT，供本地虚拟表执行器使用。"""
    text = _strip_comments(sql.strip()).rstrip(";")
    distinct = bool(re.match(r"^SELECT\s+DISTINCT\b", text, re.IGNORECASE))
    m = re.search(
        r"^SELECT\s+(?:DISTINCT\s+)?(.+?)\s+FROM\s+`?([a-zA-Z_][a-zA-Z0-9_]*)`?\s*(.*)$",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        raise ValueError("无法解析 SELECT 语句，请使用单表标准写法")

    cols_raw = m.group(1).strip()
    table = m.group(2).strip()
    tail = (m.group(3) or "").strip()

    if cols_raw == "*":
        columns = ["*"]
    else:
        columns = [c.strip().strip("`") for c in cols_raw.split(",")]

    where_sql: Optional[str] = None
    order_by: Optional[str] = None
    limit = 100

    wm = re.search(r"\bWHERE\b(.+?)(?:\bORDER\s+BY\b|\bLIMIT\b|$)", tail, re.IGNORECASE | re.DOTALL)
    if wm:
        where_sql = wm.group(1).strip()
        if re.search(r"\bORDER\s+BY\b", where_sql, re.IGNORECASE):
            where_sql = re.split(r"\bORDER\s+BY\b", where_sql, maxsplit=1, flags=re.IGNORECASE)[0].strip()

    om = re.search(r"\bORDER\s+BY\b(.+?)(?:\bLIMIT\b|$)", tail, re.IGNORECASE | re.DOTALL)
    if om:
        order_by = om.group(1).strip()
        if re.search(r"\bLIMIT\b", order_by, re.IGNORECASE):
            order_by = re.split(r"\bLIMIT\b", order_by, maxsplit=1, flags=re.IGNORECASE)[0].strip()

    lm = re.search(r"\bLIMIT\s+(\d+)\b", tail, re.IGNORECASE)
    if lm:
        limit = min(int(lm.group(1)), 500)

    conditions: list[tuple[str, str, str]] = []
    if where_sql:
        for part in re.split(r"\s+AND\s+", where_sql, flags=re.IGNORECASE):
            part = part.strip()
            eq = re.match(r"`?(\w+)`?\s*=\s*'([^']*)'", part, re.IGNORECASE)
            if eq:
                conditions.append((eq.group(1), "=", eq.group(2)))
                continue
            like = re.match(r"`?(\w+)`?\s+LIKE\s+'([^']*)'", part, re.IGNORECASE)
            if like:
                conditions.append((like.group(1), "LIKE", like.group(2)))

    return ParsedSelect(
        raw_sql=text,
        columns=columns,
        table=table,
        where_sql=where_sql,
        order_by=order_by,
        limit=limit,
        distinct=distinct,
        where_conditions=conditions,
    )
