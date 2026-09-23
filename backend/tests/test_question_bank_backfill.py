# -*- coding: utf-8 -*-
"""DL4b · 校本题库回填器单测（in-memory SQLite，无需 MySQL）。

模式参照 tests/test_ai_chat_history.py（SQLite in-memory + Base.metadata.create_all）。

覆盖回填器三态：
  1. created    —— 同 (school_id, fingerprint) 不存在 → 新建
  2. updated    —— 同指纹已存在且未删 → 更新内容，不新建不重复
  3. restored   —— 同指纹已存在且软删（deleted_at 非空）→ 恢复该行（清 deleted_at +
                  更新内容），绝不触发 DuplicateEntry（唯一键 uq_sqb_school_fp）
另覆盖：空题干校验、school_id 显式覆盖 + 默认学校兜底、同指纹收敛为单行。
"""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.school import School
from app.models.school_question_bank import SchoolQuestionBank
from app.utils.question_bank_backfill import DEFAULT_SCHOOL_ID, upsert_question_to_bank


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[School.__table__, SchoolQuestionBank.__table__])
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _record(**overrides) -> dict:
    base = {
        "paper_subject": "数学",
        "question_type": "解答题",
        "question_text": "求 2x+3=7 的解。",
        "estimated_correct_answer": "x=2",
    }
    base.update(overrides)
    return base


# ── 三态：新建 / 更新 / 软删恢复 ──────────────────────────────────────


def test_created_when_no_row(db):
    result = upsert_question_to_bank(db, _record())
    db.commit()

    assert result["action"] == "created"
    rows = db.query(SchoolQuestionBank).all()
    assert len(rows) == 1
    assert rows[0].school_id == DEFAULT_SCHOOL_ID
    assert rows[0].question_text == "求 2x+3=7 的解。"
    assert rows[0].fingerprint == result["fingerprint"]
    assert rows[0].deleted_at is None


def test_updated_when_already_active(db):
    first = upsert_question_to_bank(db, _record())
    db.commit()

    # 同指纹（排版级差异被 DL3 吸收，指纹不变）→ 更新既有行而非新建
    result = upsert_question_to_bank(db, _record(question_text="求 2x+3=7 的解"))
    db.commit()

    assert result["action"] == "updated"
    assert result["id"] == first["id"], "同指纹已存在时应更新既有行而非新建"
    rows = db.query(SchoolQuestionBank).all()
    assert len(rows) == 1
    assert rows[0].id == first["id"]
    assert rows[0].deleted_at is None


def test_restored_when_soft_deleted(db):
    first = upsert_question_to_bank(db, _record())
    db.commit()

    # 模拟业务软删：同指纹行 deleted_at 非空（仍占着 UNIQUE(school_id, fingerprint)）
    row = db.query(SchoolQuestionBank).one()
    row.deleted_at = datetime.datetime(2026, 8, 1, tzinfo=datetime.timezone.utc)
    db.commit()

    result = upsert_question_to_bank(db, _record())
    db.commit()

    assert result["action"] == "restored"
    assert result["id"] == first["id"], "软删行同指纹必须恢复原行，不得新建"
    rows = db.query(SchoolQuestionBank).all()
    assert len(rows) == 1, "软删行同指纹若新建会撞 UNIQUE 抛 DuplicateEntry，必须走恢复"
    assert rows[0].deleted_at is None, "恢复后 deleted_at 应清空"
    assert rows[0].id == first["id"]


# ── 边界：空题干 / 默认学校兜底 / school_id 覆盖 / 同指纹收敛 ────────


def test_empty_question_text_rejected(db):
    with pytest.raises(ValueError):
        upsert_question_to_bank(db, _record(question_text="   "))


def test_school_id_override_and_default_fallback(db):
    upsert_question_to_bank(db, _record(school_id="S_1"))
    db.commit()
    assert db.query(SchoolQuestionBank).one().school_id == "S_1"

    upsert_question_to_bank(db, _record(question_text="另一道题"))
    db.commit()
    school_ids = {r.school_id for r in db.query(SchoolQuestionBank).all()}
    assert DEFAULT_SCHOOL_ID in school_ids, "未给 school_id 时应兜底到 DL2 默认学校"


def test_same_fingerprint_collapses_to_single_row(db):
    # 仅排版级差异（空格）→ 指纹不变 → 收敛为同一条
    upsert_question_to_bank(db, _record(question_text="求 2x+3=7 的解。"))
    upsert_question_to_bank(db, _record(question_text="求 2x+3=7 的解"))
    db.commit()
    assert db.query(SchoolQuestionBank).count() == 1

    # 实质变化（改题干）→ 指纹变化 → 新题
    upsert_question_to_bank(db, _record(question_text="求 3x+5=11 的解。"))
    db.commit()
    assert db.query(SchoolQuestionBank).count() == 2
