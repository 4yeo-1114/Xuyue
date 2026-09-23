# -*- coding: utf-8 -*-
"""P2-4 批1：ai_chat_datasource 工具函数验收测试。

覆盖收敛后的统一实现：
  1. strip_sensitive_columns：敏感列掩码行为（含嵌套 dict 值 / None 值 / 空列表 / 默认空集合）
  2. serialize_cell：Decimal/date/datetime/str/int/其他 的序列化转换

本批只测工具函数，不碰 AI 意图链路（批 2/批 3 再覆盖）。
环境：纯函数测试，不依赖数据库（conftest.py 已注入最小 env 配置）。
"""
from datetime import date, datetime
from decimal import Decimal

from app.services.ai_chat_datasource import (
    _DEFAULT_SENSITIVE_COLUMNS,
    serialize_cell,
    strip_sensitive_columns,
)


# ── 1. strip_sensitive_columns ───────────────────────────


def test_strip_sensitive_columns_removes_masked_columns():
    rows = [
        {
            "id": "S1",
            "name": "张三",
            "phone": "13800138000",
            "parent_phone": "13900139000",
            "password_hash": "x",
        }
    ]
    out = strip_sensitive_columns(
        rows, frozenset({"phone", "parent_phone", "password_hash"})
    )
    row = out[0]
    for key in ("phone", "parent_phone", "password_hash"):
        assert key not in row, f"结果不应含 {key}"
    # 非敏感列原样保留
    assert row["id"] == "S1"
    assert row["name"] == "张三"


def test_strip_sensitive_columns_keeps_non_sensitive():
    rows = [{"id": "S1", "name": "张三", "mastery": 0.9}]
    out = strip_sensitive_columns(rows, frozenset({"user_id", "mastery"}))
    assert out == [{"id": "S1", "name": "张三"}]


def test_strip_sensitive_columns_preserves_nested_values():
    # 敏感列剥离只作用于顶层 key；嵌套 dict/列表值原样保留（不递归进嵌套结构）
    rows = [{"id": "S1", "profile": {"phone": "13800138000"}, "tags": ["a", "b"]}]
    out = strip_sensitive_columns(rows, frozenset({"id"}))
    assert out[0]["profile"] == {"phone": "13800138000"}
    assert out[0]["tags"] == ["a", "b"]


def test_strip_sensitive_columns_none_values_preserved():
    # 敏感列被剥离，但非敏感列的 None 值原样保留
    rows = [{"id": "S1", "phone": None, "note": None}]
    out = strip_sensitive_columns(rows, frozenset({"phone"}))
    assert out == [{"id": "S1", "note": None}]


def test_strip_sensitive_columns_empty_rows():
    assert strip_sensitive_columns([], frozenset({"phone"})) == []


def test_strip_sensitive_columns_default_empty_set():
    # 默认敏感列集合为空集：不剥离任何列，原样返回
    rows = [{"id": "S1", "phone": "13800138000"}]
    out = strip_sensitive_columns(rows)
    assert out == rows
    assert _DEFAULT_SENSITIVE_COLUMNS == frozenset()


# ── 2. serialize_cell ────────────────────────────────────


def test_serialize_cell_decimal_to_float():
    val = serialize_cell(Decimal("3.14"))
    assert val == 3.14
    assert isinstance(val, float)


def test_serialize_cell_datetime_to_isoformat():
    assert serialize_cell(datetime(2026, 8, 30, 12, 30, 0)) == "2026-08-30T12:30:00"


def test_serialize_cell_date_to_isoformat():
    assert serialize_cell(date(2026, 8, 30)) == "2026-08-30"


def test_serialize_cell_passthrough_primitives():
    assert serialize_cell("abc") == "abc"
    assert serialize_cell(42) == 42
    assert serialize_cell(3.5) == 3.5
    assert serialize_cell(True) is True
    assert serialize_cell(None) is None
    assert serialize_cell([1, 2]) == [1, 2]
    assert serialize_cell({"k": "v"}) == {"k": "v"}
