# -*- coding: utf-8 -*-
"""P2-4 批4b：资产意图查询统一剥列兜底验收测试。

背景：intent_query_asset_* 三个资产意图直连 app.assets.repo（固定参数化查询），
rows 统一经过 _asset_query_rows 包装。本批在 _asset_query_rows 返回前加
strip_sensitive_columns 防御性兜底——repo 白名单列时零效果，未来 repo 新增
ASSET_SENSITIVE_COLUMNS 敏感列时自动剥离，防漂移泄敏。

覆盖：
  1. _asset_query_rows 返回前对含敏感列 rows 剥列（user_id/mastery/phone 被剔除）
  2. 正常白名单行（无敏感列）原样透传，不被误伤
  3. ASSETS_DB_ENABLED=False 优雅降级（不执行 fn，不动既有行为）
  4. repo 抛异常时优雅降级返回 error dict（不 500）
  5. intent_query_asset_question_bank 全链路：mock repo.get_questions 返回含
     敏感列 rows，最终行不含 user_id/mastery/phone

环境：除显式 monkeypatch 外不连库（conftest.py 已注入最小 env 配置）。
"""
from app.config import settings
from app.services import ai_chat_intent_queries as iq
from app.services.ai_chat_asset_scope import ASSET_SENSITIVE_COLUMNS


# ── 1. 敏感列剥除兜底 ───────────────────────────


def test_asset_query_rows_strips_sensitive_columns(monkeypatch):
    monkeypatch.setattr(settings, "ASSETS_DB_ENABLED", True)

    def fake_repo_fn():
        return [
            {
                "id": "Q1",
                "subject": "数学",
                "question": "1+1=?",
                "user_id": "u1",
                "mastery": 0.9,
                "phone": "13800138000",
            }
        ]

    out = iq._asset_query_rows(fake_repo_fn)
    assert out["success"] is True
    rows = out["rows"]
    assert len(rows) == 1
    assert rows[0]["id"] == "Q1"
    assert rows[0]["subject"] == "数学"
    assert rows[0]["question"] == "1+1=?"
    # 敏感列必须被剔除
    assert "user_id" not in rows[0]
    assert "mastery" not in rows[0]
    assert "phone" not in rows[0]
    # 且所有 ASSET_SENSITIVE_COLUMNS 均不应出现在行中
    for col in ASSET_SENSITIVE_COLUMNS:
        assert col not in rows[0]
    assert out["row_count"] == 1


# ── 2. 白名单行原样透传 ────────────────────────


def test_asset_query_rows_passes_whitelist_rows_through(monkeypatch):
    monkeypatch.setattr(settings, "ASSETS_DB_ENABLED", True)
    whitelist_row = {
        "id": "Q1",
        "subject": "数学",
        "grade": "初中",
        "question": "1+1=?",
        "options": ["1", "2", "3"],
    }

    out = iq._asset_query_rows(lambda: [dict(whitelist_row)])
    assert out["success"] is True
    assert out["rows"] == [whitelist_row]
    assert out["row_count"] == 1


# ── 3. ASSETS_DB_ENABLED=False 优雅降级 ────────


def test_asset_query_rows_disabled_degrades_gracefully(monkeypatch):
    monkeypatch.setattr(settings, "ASSETS_DB_ENABLED", False)
    called = []

    def fake_repo_fn():
        called.append(1)
        return [{"id": "Q1", "user_id": "u1"}]

    out = iq._asset_query_rows(fake_repo_fn)
    assert out == {"success": False, "error": "资产库未启用", "rows": [], "row_count": 0}
    assert called == []  # 未启用时不执行 fn（不动既有行为）


# ── 4. repo 抛异常优雅降级 ─────────────────────


def test_asset_query_rows_repo_error_degrades_gracefully(monkeypatch):
    monkeypatch.setattr(settings, "ASSETS_DB_ENABLED", True)

    def boom_fn():
        raise RuntimeError("assets db unreachable")

    out = iq._asset_query_rows(boom_fn)
    assert out["success"] is False
    assert out["rows"] == []
    assert out["row_count"] == 0
    assert "资产库查询失败" in out["error"]


# ── 5. intent_query_asset_question_bank 全链路 ──


def test_question_bank_intent_strips_sensitive_columns_end_to_end(monkeypatch):
    monkeypatch.setattr(settings, "ASSETS_DB_ENABLED", True)
    from app.assets import repo

    monkeypatch.setattr(
        repo,
        "get_questions",
        lambda subject, limit: [
            {
                "id": "Q1",
                "subject": subject,
                "grade": "初中",
                "question_type": "choice",
                "question": "1+1=?",
                "options": ["1", "2", "3"],
                "user_id": "u1",
                "mastery": 0.9,
                "phone": "13800138000",
            }
        ],
    )

    out = iq.intent_query_asset_question_bank("u1", subject="数学")
    assert out["success"] is True
    assert out["row_count"] == 1
    row = out["rows"][0]
    assert row["id"] == "Q1"
    assert row["subject"] == "数学"
    assert "user_id" not in row
    assert "mastery" not in row
    assert "phone" not in row
