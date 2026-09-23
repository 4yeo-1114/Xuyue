# -*- coding: utf-8 -*-
"""AI 助教：登录账号与个人隐私查询拦截。"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.services.ai_chat_sql_utils import extract_sql_tables
from app.services.multi_project_settings import get_project_name

# AI 助教禁止通过 SQL 工具访问的 MySQL 表（登录账号 / 个人资料）
PRIVACY_BLOCKED_MYSQL_TABLES = frozenset({"users", "profiles", "user_roles"})

PRIVACY_BLOCKED_SQL_COLUMNS = re.compile(
    r"\b(password_hash|plain_password)\b",
    re.IGNORECASE,
)

_PRIVACY_QUESTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"密码", re.I),
    re.compile(r"\bpassword\b", re.I),
    re.compile(r"plain_password|password_hash", re.I),
    re.compile(r"账号密码|登录密码|帐户密码|账户密码|重置密码|找回密码", re.I),
    re.compile(r"(查|查询|看看|告诉我|输出|列出|导出|读取).{0,16}(账号|帐户|账户)", re.I),
    re.compile(r"(账号|帐户|账户).{0,10}(密码|信息|资料|详情|隐私|数据)", re.I),
    re.compile(r"\busers\b|\buser_roles\b|\bprofiles\b", re.I),
    re.compile(r"users?\s*表|user\s*表|profiles?\s*表|user_roles?\s*表", re.I),
    re.compile(r"用户表|账号表|登录表", re.I),
    re.compile(r"登录用户.{0,16}(信息|资料|隐私|数据|详情|邮箱|手机|电话)", re.I),
    re.compile(r"(系统|登录|平台|教师|老师|管理员|职工).{0,8}(账号|帐户|账户)", re.I),
    re.compile(r"MySQL.{0,24}(用户|账号|帐户|密码|users|profiles)", re.I),
    re.compile(r"(数据库|库里|表中).{0,12}(用户账号|登录账号|用户信息|账号密码)", re.I),
    re.compile(r"(邮箱|手机|电话|个人信息).{0,12}(登录|系统|教师|老师|管理员).{0,8}(账号|用户)?", re.I),
    re.compile(r"SELECT.{0,40}\bFROM\s+users\b", re.I),
    re.compile(r"JOIN\s+users\b", re.I),
)

PRIVACY_REFUSAL_TEMPLATE = """你是"{project_name} AI 助教"。

用户正在询问系统**登录账号、密码或其它登录用户个人隐私**，这类请求必须拒绝。

**硬性规则**：
1. 礼貌说明：为保护全体用户的隐私与安全，AI 助教不能查询或透露任何登录账号、密码、手机号、邮箱、个人资料等信息。
2. 禁止调用任何数据查询工具；禁止编造账号或密码；禁止给出「可以尝试查 users 表」之类的提示。
3. 用自然中文简短回答（2~4 句），可建议用户联系系统管理员或使用「个人设置」自行查看本人信息。
4. 回复中勿出现 MySQL、users 表、SQL、数据库等技术词。"""


def looks_like_user_account_privacy_question(text: str) -> bool:
    """问句是否涉及登录账号/密码/用户表等隐私数据。"""
    s = (text or "").strip()
    if not s:
        return False
    return any(p.search(s) for p in _PRIVACY_QUESTION_PATTERNS)


def validate_sql_privacy(sql: str) -> Optional[str]:
    """校验 SQL 是否触碰隐私表或敏感字段；返回错误说明或 None。"""
    text = (sql or "").strip()
    if not text:
        return None
    tables = extract_sql_tables(text)
    blocked = tables & PRIVACY_BLOCKED_MYSQL_TABLES
    if blocked:
        names = "、".join(sorted(blocked))
        return (
            f"为保护用户隐私，禁止查询登录账号相关表（{names}）。"
            "AI 助教不可查询或返回系统登录用户的账号、密码、邮箱、手机号等个人信息。"
        )
    if PRIVACY_BLOCKED_SQL_COLUMNS.search(text):
        return "为保护用户隐私，禁止查询 password_hash、plain_password 等敏感字段。"
    return None


def build_privacy_refusal_messages(user_messages: list[Any]) -> list[dict[str, Any]]:
    """构建隐私拒答的流式对话消息。"""
    system = PRIVACY_REFUSAL_TEMPLATE.format(project_name=get_project_name())
    msgs: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for m in user_messages:
        if hasattr(m, "model_dump"):
            msgs.append(m.model_dump())
        elif isinstance(m, dict):
            msgs.append(m)
    return msgs
