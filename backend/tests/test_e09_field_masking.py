# -*- coding: utf-8 -*-
"""E09 数据分类分级 · 字段掩码 + AI 出站 PII 补漏验收测试。

覆盖：
  1. field_masking 纯函数边界：mask_phone / mask_student_number / mask_address / mask_name
     （空值 / 短值 / 正常值）
  2. ai_chat_student_roster._student_profile_dict 生成的 AI profile 不含
     phone / parent_phone / parent_name / birthday / address / enroll_date / notes
  3. ai_chat_student_roster.infer_profile_fields_from_text 不再把家长/电话列为可请求字段
  4. wrong_question_db 的 AI 分析 prompt 不含 student_number；_student_match 输出不含
     student_number（学籍号不再出参）
  5. ai_chat_mysql_executor._strip_sensitive_columns 覆盖学生 PII 列（防御纵深）

环境：本批无迁移、无 DDL，全部为纯函数/模块级断言，不依赖 MySQL（仅需 env 变量注入，
避免 app.config fail-fast）。TestClient 非必需。
"""
import os

# 注入最小配置，避免 app.config fail-fast（本批不连库，DB_HOST 等仅用于占位）
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "13307")
os.environ.setdefault("DB_USER", "root")
os.environ.setdefault("DB_PASSWORD", "root_pw_2026")
os.environ.setdefault("DB_NAME", "grade_e09_test")
os.environ.setdefault("JWT_SECRET_KEY", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("AUTO_DDL", "false")
os.environ.setdefault("DASHSCOPE_API_KEY", "sk-e09-test-not-real")

from types import SimpleNamespace

from app.services.field_masking import (
    mask_address,
    mask_name,
    mask_phone,
    mask_student_number,
)
from app.services.ai_chat_student_roster import (
    _student_profile_dict,
    infer_profile_fields_from_text,
)
from app.grading.wrong_question_db import _analysis_prompt, _student_match
from app.services.ai_chat_mysql_executor import _strip_sensitive_columns


# ── 1. mask_phone 边界 ──────────────────────────────────


def test_mask_phone_empty_and_none():
    assert mask_phone(None) == ""
    assert mask_phone("") == ""
    assert mask_phone("   ") == ""


def test_mask_phone_short_values():
    assert mask_phone("1") == "*"
    assert mask_phone("1234") == "****"
    assert mask_phone("12345") == "12*45"
    assert mask_phone("1234567") == "12***67"


def test_mask_phone_normal():
    assert mask_phone("13800138000") == "138****8000"
    # 前3后4：138 + **** + 8000
    assert mask_phone("13800138000")[:3] == "138"
    assert mask_phone("13800138000")[-4:] == "8000"


# ── 2. mask_student_number 边界 ─────────────────────────


def test_mask_student_number_empty_and_short():
    assert mask_student_number(None) == ""
    assert mask_student_number("") == ""
    assert mask_student_number("2") == "*"
    assert mask_student_number("23") == "**"
    assert mask_student_number("234") == "*34"


def test_mask_student_number_normal():
    assert mask_student_number("23001189") == "23****89"
    assert mask_student_number("2024010123") == "20******23"
    # 保留前2后2
    assert mask_student_number("23001189")[:2] == "23"
    assert mask_student_number("23001189")[-2:] == "89"


# ── 3. mask_address 边界 ────────────────────────────────


def test_mask_address_empty():
    assert mask_address(None) == ""
    assert mask_address("") == ""


def test_mask_address_keeps_region_prefix():
    assert mask_address("广东省深圳市南山区科技园路1号") == "广东省深圳市南山区**"
    assert mask_address("江苏省南京市") == "江苏省南京市"
    assert mask_address("北京市朝阳区某某路1号") == "北京市朝阳区**"
    assert mask_address("南京市鼓楼区中山北路") == "南京市鼓楼区**"


def test_mask_address_no_region_fallback():
    # 无法识别行政区划 → 整体掩码（保守）
    out = mask_address("幸福小区3号楼")
    assert "*" in out
    assert "幸福" not in out


# ── 4. mask_name 边界 ───────────────────────────────────


def test_mask_name_boundaries():
    assert mask_name(None) == ""
    assert mask_name("") == ""
    assert mask_name("张") == "*"
    assert mask_name("王芳") == "王*"
    assert mask_name("张小明") == "张**"
    assert mask_name("欧阳锋") == "欧**"


# ── 5. AI 花名册 profile 不再携带 PII ──────────────────


def _fake_student(**overrides):
    base = dict(
        id="S1",
        name="张三",
        student_number="23001189",
        class_id="C1",
        gender="男",
        tier="A",
        status="active",
        cadre_role="班长",
        seat_row=1,
        seat_col=2,
        phone="13800138000",
        parent_name="张父",
        parent_phone="13900139000",
        birthday="2015-01-01",
        enroll_date="2023-09-01",
        address="广东省深圳市南山区科技园路1号",
        notes="注意：中午需服药",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _fake_class(**overrides):
    base = dict(id="C1", grade="五年级", name="五(1)班")
    base.update(overrides)
    return SimpleNamespace(**base)


def test_student_profile_dict_strips_pii():
    prof = _student_profile_dict(_fake_student(), _fake_class())
    for key in (
        "phone",
        "parent_name",
        "parent_phone",
        "birthday",
        "enroll_date",
        "address",
        "notes",
    ):
        assert key not in prof, f"AI profile 不应包含 {key}"
    # 保留 AI 需要的字段
    assert prof["name"] == "张三"
    assert prof["student_number"] == "23001189"
    assert "五(1)班" in prof["class_name"]
    assert prof["cadre_role"] == "班长"
    assert prof["is_cadre"] is True


def test_infer_profile_fields_from_text_excludes_parent_phone():
    # 问家长/电话 → 不再把 parent_name / parent_phone 作为可请求字段暴露给模型
    fields = infer_profile_fields_from_text("张某某的家长电话是多少")
    assert "parent_name" not in fields
    assert "parent_phone" not in fields
    # 问班干部/学号 → 仍然支持
    assert "cadre_role" in infer_profile_fields_from_text("他是班干部吗")
    assert "student_number" in infer_profile_fields_from_text("他的学号是多少")


# ── 6. wrong_question_db 学籍号不再出参/入 prompt ───────


def test_wrong_question_analysis_prompt_no_student_number():
    record = {
        "display_title": "某题",
        "paper_subject": "数学",
        "question_type": 1,
        "status": "wrong",
        "reason": "粗心",
    }
    prompt = _analysis_prompt(record)
    assert "student_number" not in prompt
    assert "学籍号" not in prompt


def test_wrong_question_student_match_strips_student_number():
    student = {"id": "S1", "name": "张三", "student_number": "23001189"}
    out = _student_match(student, "student_number_exact")
    assert out["id"] == "S1"
    assert out["name"] == "张三"
    assert out["matched_by"] == "student_number_exact"
    assert out["matched"] is True
    assert "student_number" not in out


# ── 7. MySQL 执行器结果集剥离学生 PII 列 ────────────────


def test_executor_strips_student_pii_columns():
    rows = [
        {
            "id": "S1",
            "name": "张三",
            "phone": "13800138000",
            "parent_name": "张父",
            "parent_phone": "13900139000",
            "address": "广东省深圳市南山区",
            "birthday": "2015-01-01",
            "password_hash": "x",
        }
    ]
    out = _strip_sensitive_columns(rows)
    row = out[0]
    for key in ("phone", "parent_name", "parent_phone", "address", "birthday", "password_hash"):
        assert key not in row, f"SQL 结果不应含 {key}"
    # 非敏感列保留
    assert row["id"] == "S1"
    assert row["name"] == "张三"
