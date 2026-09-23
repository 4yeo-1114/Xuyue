# -*- coding: utf-8 -*-
"""init_db() 「无条件补列/建表段」回归测试（D-1 同类漂移收口）。

⚠️ **本文件是 SQLite 单测，不算真证据** —— 它**不验 MySQL 语义**：
  不验 1054 `Unknown column` / 1146 `Table doesn't exist`、
  不验 ALTER 在 InnoDB 上对既有行的行为、不验索引名在 MySQL 里的作用域口径。
  真 MySQL 证据 = `F:\\claude-temp\\_drift_fix_verify.py`（跑在 scratch 库 `grade_d1_verify`）。

本文件钉住三件事：
  1. 补列/建表逻辑对「缺列缺表的既有库」确实生效（走成功路径，不是兜底路径）；
  2. 幂等：二次调用不抛、库状态不变；
  3. **【载重断言】`init_db()` 在 `AUTO_DDL=false`（生产默认）下仍会调用这些 ensure**
     —— 这正是 D-1 的病灶：它们曾被放在 `sync_database_schema()` 的
     `if not AUTO_DDL: return` **之后**，等于一次都不执行。
"""
import os

# ⚠️ 必须先于任何 `app.*` import：本仓 backend/.env 当前写着 AUTO_DDL=true，
# 而 app.database 在 **import 时**就会因 AUTO_DDL=true 调用 _ensure_database() 去连库。
# 本文件测的就是「生产默认 AUTO_DDL=false」这条路径，故在此把配置钉死为被测口径
# （pydantic-settings 优先级：os.environ > .env）。
os.environ["AUTO_DDL"] = "false"

import pytest  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import app.database as database  # noqa: E402
from app.database import Base
from app.models.ai_generation_history import AiGenerationHistory
from app.models.bandit_arm_stats import BanditArmStats
from app.models.lesson_plan import LessonPlan
from app.models.response_log import ResponseLog
from app.models.student_analysis import StudentWrongQuestion
from app.models.textbook_catalog import TextbookCatalog
from app.models.user import User
from app.models.wrong_question_kp_bridge import WrongQuestionKpBridge

# ── 真库漂移清单（2026-09-24 只读探针实测口径）────────────────────────────
DRIFT_COLUMNS = {
    "users": ("dingtalk_userid",),
    "lesson_plans": ("textbook_id", "unit_id", "catalog_id", "edition", "chapter"),
    "student_wrong_questions": (
        "school_id",
        "corrected_at",
        "knowledge_point_id",
        "status",
    ),
}
DRIFT_TABLES = (
    "bandit_arm_stats",
    "textbook_catalogs",
    "wrong_question_kp_bridge",
    "ai_generation_history",
    "response_logs",
)

# ── 「漂移态」旧库：只含漂移发生前的列，故意不含上面那些 ────────────────
_LEGACY_DDL = (
    """
    CREATE TABLE users (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        email VARCHAR(255) NOT NULL,
        password_hash VARCHAR(255) NOT NULL
    )
    """,
    """
    CREATE TABLE lesson_plans (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        user_id VARCHAR(36) NOT NULL,
        class_id VARCHAR(36) NOT NULL,
        subject VARCHAR(32) NOT NULL,
        title VARCHAR(255) NOT NULL
    )
    """,
    """
    CREATE TABLE student_wrong_questions (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        class_id VARCHAR(36) NOT NULL,
        student_name VARCHAR(64) NOT NULL,
        subject VARCHAR(64) NOT NULL,
        exam_name VARCHAR(128) NOT NULL,
        question_title VARCHAR(255) NOT NULL
    )
    """,
)


@pytest.fixture()
def drift_engine(monkeypatch):
    """把 app.database 的 engine/SessionLocal 换成 SQLite 的「漂移态旧库」。

    ⛔ 全程不连真 MySQL（连 app.database.engine 都被换掉）。
    """
    eng = create_engine("sqlite:///:memory:")
    with eng.connect() as conn:
        for ddl in _LEGACY_DDL:
            conn.execute(text(ddl))
        # 既有行：用来验证补出来的 NOT NULL DEFAULT 列对老数据成立
        conn.execute(
            text(
                "INSERT INTO student_wrong_questions "
                "(id, class_id, student_name, subject, exam_name, question_title) "
                "VALUES ('wq-1', 'c-1', '张三', '数学', '期中', '第1题')"
            )
        )
        conn.commit()

    monkeypatch.setattr(database, "engine", eng)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=eng))
    # 生产默认口径：AUTO_DDL=false（正是 D-1 发病的配置）
    monkeypatch.setattr(database.settings, "AUTO_DDL", False)
    return eng


def _cols(eng, table):
    return {c["name"] for c in inspect(eng).get_columns(table)}


def _tables(eng):
    return set(inspect(eng).get_table_names())


def _indexes(eng, table):
    return {ix["name"] for ix in inspect(eng).get_indexes(table)}


# ══ 1. 【载重断言】无条件段确实被 init_db() 调到（AUTO_DDL=false）══════

def test_init_db_calls_all_drift_ensures_even_when_auto_ddl_false(drift_engine, monkeypatch):
    """D-1 病灶回归：这 7 个 ensure 必须在 AUTO_DDL=false 下仍被 init_db() 调用。

    若有人把它们挪回 sync_database_schema() 的提前 return 之后，本用例判红。
    """
    called = []

    def spy(name):
        def _f(*a, **kw):
            called.append(name)
        return _f

    for fn in (
        "_ensure_lesson_plan_extra_columns",
        "_ensure_student_wrong_questions_extra_columns",
        "_ensure_textbook_catalogs_table",
        "_ensure_wrong_question_kp_bridge_table",
        "_ensure_bandit_arm_stats_table",
        "_ensure_response_logs_table",
        "_ensure_ai_generation_history_table",
    ):
        monkeypatch.setattr(database, fn, spy(fn))

    assert database.settings.AUTO_DDL is False  # 前置：确实是发病配置
    database.init_db()

    assert set(called) == {
        "_ensure_lesson_plan_extra_columns",
        "_ensure_student_wrong_questions_extra_columns",
        "_ensure_textbook_catalogs_table",
        "_ensure_wrong_question_kp_bridge_table",
        "_ensure_bandit_arm_stats_table",
        "_ensure_response_logs_table",
        "_ensure_ai_generation_history_table",
    }


# ══ 2. 补列：10 列全部落地（走成功路径）══════════════════════════════

def test_drift_columns_backfilled(drift_engine):
    before = {t: _cols(drift_engine, t) for t in DRIFT_COLUMNS}
    for t, cols in DRIFT_COLUMNS.items():
        for c in cols:
            assert c not in before[t], "前置失败：旧库不该有 %s.%s" % (t, c)

    database._ensure_dingtalk_sync_columns()
    database._ensure_lesson_plan_extra_columns()
    database._ensure_student_wrong_questions_extra_columns()

    for t, cols in DRIFT_COLUMNS.items():
        got = _cols(drift_engine, t)
        for c in cols:
            assert c in got, "%s.%s 未被补齐（无条件段漏了这一列）" % (t, c)


def test_backfilled_columns_match_orm(drift_engine):
    """补出来的列名/类型必须与 ORM 一致（照 ORM 补，不自创）。

    范围界定：无条件段承诺的只有**漂移列**，不承诺把旧表补成完整 ORM 表
    （非漂移列如 lesson_plans.teaching_content 归 AUTO_DDL 路径 / 人工迁移）。
    """
    database._ensure_dingtalk_sync_columns()
    database._ensure_lesson_plan_extra_columns()
    database._ensure_student_wrong_questions_extra_columns()

    # 漂移列必须真的是 ORM 成员（防止本文件测了一个 ORM 里不存在的列名）
    assert set(DRIFT_COLUMNS["lesson_plans"]) <= set(LessonPlan.__table__.columns.keys())
    assert set(DRIFT_COLUMNS["student_wrong_questions"]) <= set(
        StudentWrongQuestion.__table__.columns.keys()
    )
    # 且其 DDL 类型与 ORM 编译结果逐字相同（旧库补出来的列 = create_all 会建的列）
    from sqlalchemy.dialects import mysql as _mysql
    from sqlalchemy.schema import CreateColumn as _CreateColumn

    pairs = [
        (LessonPlan.__table__, "lesson_plans"),
        (StudentWrongQuestion.__table__, "student_wrong_questions"),
    ]
    d = _mysql.dialect()
    for table, tname in pairs:
        for col in DRIFT_COLUMNS[tname]:
            expected = str(_CreateColumn(table.c[col]).compile(dialect=d)).split(
                " COMMENT "
            )[0].strip()
            exp_type = expected.split()[1]
            exp_notnull = "NOT NULL" in expected
            exp_default = (
                expected.split("DEFAULT", 1)[1].strip() if "DEFAULT" in expected else None
            )
            with drift_engine.connect() as conn:
                got_type, got_notnull, got_default = conn.execute(
                    text(
                        "SELECT type, \"notnull\", dflt_value FROM pragma_table_info(:t)"
                        " WHERE name = :c"
                    ),
                    {"t": tname, "c": col},
                ).fetchone()
            assert got_type.upper() == exp_type.upper(), (col, got_type, exp_type)
            assert bool(got_notnull) is exp_notnull, (col, got_notnull, exp_notnull)
            if exp_default is not None:
                assert (got_default or "").strip() == exp_default, (
                    col,
                    got_default,
                    exp_default,
                )


def test_status_default_applies_to_existing_rows(drift_engine):
    """status 是真库那 4 列里唯一 NOT NULL 的：老行必须被填成 'open'（成功路径）。"""
    database._ensure_student_wrong_questions_extra_columns()
    with drift_engine.connect() as conn:
        (val,) = conn.execute(
            text("SELECT status FROM student_wrong_questions WHERE id='wq-1'")
        ).fetchone()
    assert val == "open"


def test_orm_indexes_backfilled(drift_engine):
    """ORM 声明 index=True 的单列，索引名取自 ORM，必须一并补上。"""
    database._ensure_dingtalk_sync_columns()
    database._ensure_lesson_plan_extra_columns()
    database._ensure_student_wrong_questions_extra_columns()

    assert "ix_users_dingtalk_userid" in _indexes(drift_engine, "users")
    for ix in LessonPlan.__table__.indexes:
        if len(list(ix.columns)) == 1 and list(ix.columns)[0].name in (
            "textbook_id", "unit_id", "catalog_id"
        ):
            assert ix.name in _indexes(drift_engine, "lesson_plans"), ix.name
    for ix in StudentWrongQuestion.__table__.indexes:
        if len(list(ix.columns)) == 1 and list(ix.columns)[0].name in (
            "school_id", "knowledge_point_id"
        ):
            assert ix.name in _indexes(drift_engine, "student_wrong_questions"), ix.name


def test_single_column_index_helper_skips_composite(drift_engine):
    """负例：复合索引不许被 `_ensure_single_column_indexes` 误建（多列索引不归它管）。"""
    database._ensure_response_logs_table()
    before = _indexes(drift_engine, "response_logs")
    # idx_rl_user_created 是 (user_id, created_at) 复合索引，传 user_id 不该建它
    database._ensure_single_column_indexes(ResponseLog.__table__, ["user_id"])
    after = _indexes(drift_engine, "response_logs")
    assert "idx_rl_user_created" not in after - before


# ══ 3. 建表：5 张缺表全部落地 ═══════════════════════════════════════

def test_drift_tables_created(drift_engine):
    for t in DRIFT_TABLES:
        assert t not in _tables(drift_engine), "前置失败：旧库不该有表 %s" % t

    database._ensure_textbook_catalogs_table()
    database._ensure_wrong_question_kp_bridge_table()
    database._ensure_bandit_arm_stats_table()
    database._ensure_response_logs_table()
    database._ensure_ai_generation_history_table()

    got = _tables(drift_engine)
    for t in DRIFT_TABLES:
        assert t in got, "缺表 %s 未被建出（无条件段漏了这一张）" % t


def test_created_tables_match_orm_columns(drift_engine):
    database._ensure_textbook_catalogs_table()
    database._ensure_wrong_question_kp_bridge_table()
    database._ensure_bandit_arm_stats_table()
    database._ensure_response_logs_table()
    database._ensure_ai_generation_history_table()

    for model in (
        TextbookCatalog,
        WrongQuestionKpBridge,
        BanditArmStats,
        ResponseLog,
        AiGenerationHistory,
    ):
        assert set(model.__table__.columns.keys()) <= _cols(
            drift_engine, model.__tablename__
        ), model.__tablename__


# ══ 4. 端到端：init_db() 在 AUTO_DDL=false 下把漂移态旧库补成完整态 ═══

def _snapshot(eng):
    return (
        {t: _cols(eng, t) for t in DRIFT_COLUMNS},
        _tables(eng),
    )


def test_init_db_repairs_drift_state(drift_engine):
    database.init_db()  # 必须不抛

    for t, cols in DRIFT_COLUMNS.items():
        got = _cols(drift_engine, t)
        for c in cols:
            assert c in got, "%s.%s 仍缺" % (t, c)
    assert set(DRIFT_TABLES) <= _tables(drift_engine)


def test_init_db_is_idempotent(drift_engine):
    database.init_db()
    first = _snapshot(drift_engine)

    database.init_db()  # 二次：不许抛、不许把库改坏
    second = _snapshot(drift_engine)

    assert first == second
    for t, cols in DRIFT_COLUMNS.items():
        for c in cols:
            assert c in _cols(drift_engine, t)
    assert set(DRIFT_TABLES) <= _tables(drift_engine)


def test_init_db_second_call_does_not_raise_on_existing_columns(drift_engine):
    """幂等的最直接断言：列/表已存在时，ALTER/CREATE 的报错必须被就地吞掉。"""
    database._ensure_lesson_plan_extra_columns()
    database._ensure_student_wrong_questions_extra_columns()
    database._ensure_dingtalk_sync_columns()
    database._ensure_lesson_plan_extra_columns()
    database._ensure_student_wrong_questions_extra_columns()
    database._ensure_dingtalk_sync_columns()
    database._ensure_response_logs_table()
    database._ensure_response_logs_table()

    assert "response_logs" in _tables(drift_engine)
    assert "catalog_id" in _cols(drift_engine, "lesson_plans")


# ══ 5. 反空跑哨兵：漂移清单必须与 ORM 对得上 ═══════════════════════

def test_drift_lists_are_real_orm_members():
    """若哪天 ORM 改了列名，本文件必须判红，而不是悄悄测了个不存在的列。"""
    assert set(DRIFT_COLUMNS["users"]) <= set(User.__table__.columns.keys())
    assert set(DRIFT_COLUMNS["lesson_plans"]) <= set(LessonPlan.__table__.columns.keys())
    assert set(DRIFT_COLUMNS["student_wrong_questions"]) <= set(
        StudentWrongQuestion.__table__.columns.keys()
    )
    for t in DRIFT_TABLES:
        assert t in Base.metadata.tables, t
