# -*- coding: utf-8 -*-
"""本地安装包不设免费额度（20261110 用户拍板）：QUOTA_GATES_DISABLED=1 时
面数闸（403）全关、不计面——客户想用多少用多少，
模型钱花在用户自己的百度/阿里云账户上。生产不配置 ⇒ 闸门照旧。
（钱包闸 20261111 随「余额/充值/支付整体移除」删掉，只剩面数闸。）
"""
from __future__ import annotations

from types import SimpleNamespace

from app.grading.quota_gate import _gates_disabled, quota_gate


def test_gates_disabled_parsing(monkeypatch):
    for raw, want in (
        ("1", True),
        ("true", True),
        ("YES", True),
        ("on", True),
        ("0", False),
        ("off", False),
        ("junk", False),
        ("", False),
    ):
        monkeypatch.setenv("QUOTA_GATES_DISABLED", raw)
        assert _gates_disabled() is want, raw


def test_settings_fallback_and_env_priority(monkeypatch):
    monkeypatch.delenv("QUOTA_GATES_DISABLED", raising=False)
    monkeypatch.setattr(
        "app.config.settings", SimpleNamespace(QUOTA_GATES_DISABLED="1")
    )
    assert _gates_disabled() is True
    monkeypatch.setenv("QUOTA_GATES_DISABLED", "0")
    assert _gates_disabled() is False  # 环境变量优先（排障可临时覆盖）


def test_disabled_gates_pass_without_user_context(monkeypatch):
    """闸关了就彻底不拦不查库：连用户上下文没有都直接放行。"""
    monkeypatch.setenv("QUOTA_GATES_DISABLED", "1")
    assert quota_gate() is None
    assert quota_gate(charge_pages=3) is None


def test_gates_unchanged_when_switch_off(monkeypatch):
    """开关不配 = 闸门照旧语义：无用户上下文按故障放行（不 500），行为不回归。"""
    monkeypatch.delenv("QUOTA_GATES_DISABLED", raising=False)
    monkeypatch.setattr(
        "app.config.settings", SimpleNamespace(QUOTA_GATES_DISABLED="")
    )
    assert _gates_disabled() is False
    assert quota_gate() is None  # 无 uid ⇒ 留痕放行（既有语义）
