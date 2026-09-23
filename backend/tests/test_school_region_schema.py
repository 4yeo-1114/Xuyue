"""DL2 · 学校/区域 schema 契约测试（不依赖真实 MySQL 也能全绿）。

覆盖：
  1. models 层（纯 SQLAlchemy metadata，无需 DB 连接）：
     - Base.metadata.tables 含 regions / schools
     - regions.parent_id 自引用外键 → regions.id
     - schools.region_id 外键 → regions.id
     - classes.school_id 列存在、VARCHAR(36)、可空
     - Region/School 已注册到 app/models/__init__.py
  2. 迁移 SQL 文本层幂等守卫断言：
     - DL1 docs/migrations/2026-08-20-school-region.sql：
       CREATE TABLE IF NOT EXISTS / information_schema 检查 / fk_classes_school / fk_regions_parent / fk_schools_region
     - DL2 docs/migrations/2026-08-20-school-backfill.sql：
       INSERT INTO schools / WHERE NOT EXISTS（seed 幂等）/ WHERE school_id IS NULL（回填幂等）/ PREPARE 守卫
  3. 可选（本地 Docker MySQL 127.0.0.1:13307 可用时）：
     - scratch 库链式双跑 DL1 + DL2，验证 seed 幂等 + classes/students/exam_scores/wrong_questions 级联回填；
     - DB 不可用时自动 skip，不影响套件全绿。

环境：与 tests/conftest.py 一致，DB_* 为占位；测试自身不连 localhost:3306。
"""
import os
from pathlib import Path

import pytest
from sqlalchemy import String

from app.database import Base
from app.models.class_model import Class
from app.models.school import Region, School
from app.models.school_question_bank import SchoolQuestionBank

# DL2 回填脚本约定的固定默认学校 ID（docs/migrations/2026-08-20-school-backfill.sql）
_DEFAULT_SCHOOL_ID = "11111111-1111-4111-8111-111111111111"
# scratch 测试用的 profile id（替换脚本占位）
_PROFILE_ID = "11111111-2222-4333-8444-555555555555"

_REPO_ROOT = Path(__file__).resolve().parent.parent
_MIGRATION_REGION = _REPO_ROOT / "docs" / "migrations" / "2026-08-20-school-region.sql"
_MIGRATION_BACKFILL = _REPO_ROOT / "docs" / "migrations" / "2026-08-20-school-backfill.sql"
_MIGRATION_QB = _REPO_ROOT / "docs" / "migrations" / "2026-08-20-school-question-bank.sql"


# ── 1. models 层 schema 断言（无 DB 依赖） ─────────────────────────

def test_metadata_has_regions_and_schools():
    tables = Base.metadata.tables
    assert "regions" in tables, "Base.metadata 应含 regions 表（app/models/school.py:16-31）"
    assert "schools" in tables, "Base.metadata 应含 schools 表（app/models/school.py:34-50）"


def test_region_columns_and_parent_self_fk():
    regions = Base.metadata.tables["regions"]
    for col in ("id", "name", "level", "parent_id", "code", "created_at", "updated_at", "deleted_at"):
        assert col in regions.c, f"regions 缺列: {col}"
    fks = list(regions.c["parent_id"].foreign_keys)
    assert len(fks) == 1, "regions.parent_id 应为自引用外键"
    assert fks[0].column.table.name == "regions"
    assert fks[0].column.name == "id"


def test_school_columns_and_region_fk():
    schools = Base.metadata.tables["schools"]
    for col in ("id", "name", "region_id", "db_profile_id", "db_name", "created_at", "updated_at", "deleted_at"):
        assert col in schools.c, f"schools 缺列: {col}"
    fks = list(schools.c["region_id"].foreign_keys)
    assert len(fks) == 1, "schools.region_id 应为外键 → regions.id"
    assert fks[0].column.table.name == "regions"
    assert fks[0].column.name == "id"


def test_class_model_school_id_column():
    col = Class.__table__.c["school_id"]
    assert isinstance(col.type, String), f"school_id 类型应为 VARCHAR(36)，实际 {col.type}"
    assert col.type.length == 36
    assert col.nullable is True


def test_region_school_registered_in_models_init():
    import app.models as models_pkg

    assert hasattr(models_pkg, "Region"), "app/models/__init__.py 应导出 Region"
    assert hasattr(models_pkg, "School"), "app/models/__init__.py 应导出 School"


def test_region_school_class_symbols_importable():
    # 防止模型改名/删除后仍可正常引用
    assert Region.__tablename__ == "regions"
    assert School.__tablename__ == "schools"
    assert Class.__tablename__ == "classes"


# ── DL4a C2 校本题库表 school_question_banks 契约 ──────────────

def test_metadata_has_school_question_banks():
    tables = Base.metadata.tables
    assert "school_question_banks" in tables, "Base.metadata 应含 school_question_banks 表"


def test_school_question_bank_fingerprint_column():
    tbl = Base.metadata.tables["school_question_banks"]
    for col in ("id", "school_id", "subject", "question_type", "question_text",
                "correct_answer", "knowledge_point_id", "fingerprint", "difficulty",
                "created_at", "updated_at", "deleted_at"):
        assert col in tbl.c, f"school_question_banks 缺列: {col}"
    col = tbl.c["fingerprint"]
    assert isinstance(col.type, String), f"fingerprint 类型应为 VARCHAR(67)，实际 {col.type}"
    assert col.type.length == 67, f"fingerprint 长度应为 67（fp_+64hex），实际 {col.type.length}"
    assert col.nullable is False, "fingerprint 应为 NOT NULL"
    # fingerprint 无 FK（纯索引列，长度 67 不指向任何表）
    assert len(col.foreign_keys) == 0, "fingerprint 不应有外键"


def test_school_question_bank_unique_and_school_fk():
    tbl = Base.metadata.tables["school_question_banks"]
    ucs = [c for c in tbl.constraints if getattr(c, "name", None) == "uq_sqb_school_fp"]
    assert len(ucs) == 1, "应存在唯一约束 uq_sqb_school_fp"
    cols = [col.name for col in ucs[0].columns]
    assert cols == ["school_id", "fingerprint"], \
        f"uq_sqb_school_fp 应定义在 (school_id, fingerprint)，实际 {cols}"
    fks = list(tbl.c["school_id"].foreign_keys)
    assert len(fks) == 1, "school_question_banks.school_id 应为外键 → schools.id"
    assert fks[0].column.table.name == "schools"
    assert fks[0].column.name == "id"
    # knowledge_point_id 预留位不加外键
    assert len(list(tbl.c["knowledge_point_id"].foreign_keys)) == 0, \
        "knowledge_point_id 不应有外键（知识点锚表未定）"


def test_school_question_bank_registered_in_models_init():
    import app.models as models_pkg

    assert hasattr(models_pkg, "SchoolQuestionBank"), "app/models/__init__.py 应导出 SchoolQuestionBank"
    assert "SchoolQuestionBank" in models_pkg.__all__, "SchoolQuestionBank 应在 __all__ 中"
    assert SchoolQuestionBank.__tablename__ == "school_question_banks"


# ── 2. 迁移 SQL 文本层幂等守卫断言 ───────────────────────────────

def _read_sql(path: Path) -> str:
    assert path.exists(), f"迁移文件缺失: {path}"
    return path.read_text(encoding="utf-8")


def test_dl1_region_sql_has_idempotent_guards():
    sql = _read_sql(_MIGRATION_REGION)
    # 锚表幂等建表
    assert "CREATE TABLE IF NOT EXISTS `regions`" in sql
    assert "CREATE TABLE IF NOT EXISTS `schools`" in sql
    # classes.school_id 幂等补列：information_schema 检查列不存在才 ALTER
    assert "information_schema.COLUMNS" in sql
    assert "ALTER TABLE classes ADD COLUMN school_id" in sql
    assert "PREPARE st FROM @s" in sql
    # 外键约束
    assert "fk_regions_parent" in sql
    assert "fk_schools_region" in sql
    assert "fk_classes_school" in sql
    # school_id 列定义类型
    assert "school_id VARCHAR(36) NULL" in sql


def test_dl2_backfill_sql_has_idempotent_guards():
    sql = _read_sql(_MIGRATION_BACKFILL)
    # seed：幂等插入默认学校
    assert "INSERT INTO schools" in sql
    assert "WHERE NOT EXISTS" in sql
    assert "db_profile_id" in sql
    assert "DATABASE()" in sql
    # 回填：UPDATE 全部带 WHERE school_id IS NULL
    assert "UPDATE classes SET school_id" in sql
    assert "UPDATE students" in sql
    assert "UPDATE wrong_questions" in sql
    assert "UPDATE exam_scores" in sql
    assert "school_id IS NULL" in sql
    # 守卫写法（与 DL1 一致）
    assert "information_schema.TABLES" in sql
    assert "PREPARE st FROM @s" in sql


def test_dl4a_qb_sql_has_idempotent_guards():
    sql = _read_sql(_MIGRATION_QB)
    # 幂等建表
    assert "CREATE TABLE IF NOT EXISTS `school_question_banks`" in sql
    # 指纹列必须是 VARCHAR(67)（fp_+64hex，总长 67；不是立项稿笔误的 64）
    assert "fingerprint` VARCHAR(67) NOT NULL" in sql
    # 唯一键 + 索引 + 外键
    assert "uq_sqb_school_fp" in sql
    assert "idx_sqb_school_id" in sql
    assert "fk_sqb_school" in sql
    assert "REFERENCES `schools` (`id`) ON DELETE CASCADE" in sql


# ── 3. 可选：本地 Docker MySQL 链式双跑（默认跳过） ──────────────

_DB_HOST = os.environ.get("DL2_DB_HOST", "127.0.0.1")
_DB_PORT = int(os.environ.get("DL2_DB_PORT", "13307"))
_DB_USER = os.environ.get("DL2_DB_USER", "root")
_DB_PWD = os.environ.get("DL2_DB_PASSWORD", "root_pw_2026")
_SCRATCH_DB = os.environ.get("DL2_SCRATCH_DB", "grade_school_dl2_mig")

_MYSQL_AVAILABLE = False
_MYSQL_ERR = ""
try:
    import pymysql

    _conn = pymysql.connect(
        host=_DB_HOST, port=_DB_PORT, user=_DB_USER, password=_DB_PWD,
        autocommit=True, connect_timeout=5,
    )
    _conn.close()
    _MYSQL_AVAILABLE = True
except Exception as _exc:  # noqa: BLE001 - 环境不可用则跳过 DB 用例
    _MYSQL_AVAILABLE = False
    _MYSQL_ERR = repr(_exc)


@pytest.mark.skipif(not _MYSQL_AVAILABLE, reason=f"本地 Docker MySQL 不可用: {_MYSQL_ERR}")
def test_backfill_sql_idempotent_on_scratch_db():
    import pymysql

    conn = pymysql.connect(
        host=_DB_HOST, port=_DB_PORT, user=_DB_USER, password=_DB_PWD,
        autocommit=True, client_flag=pymysql.constants.CLIENT.MULTI_STATEMENTS,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{_SCRATCH_DB}`")
            cur.execute(f"CREATE DATABASE `{_SCRATCH_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cur.execute(f"USE `{_SCRATCH_DB}`")

            # 建最小基础表，模拟"DL1 执行前"形态：
            #   classes 无 school_id（由 DL1 幂等补列）；孤儿表已有 school_id 列（alter_schema 已补）。
            #   表 collation 用 utf8mb4_unicode_ci，与 app 经 SQLAlchemy 建表的实际 collation 一致
            #   （SQLAlchemy 对 utf8mb4 默认映射 utf8mb4_unicode_ci；否则 MySQL 8 默认
            #    utf8mb4_0900_ai_ci 会让 DL1 的 fk_classes_school 报 3780 不兼容）。
            cur.execute(
                "CREATE TABLE classes ("
                " id VARCHAR(36) NOT NULL PRIMARY KEY,"
                " user_id VARCHAR(36) NOT NULL,"
                " name VARCHAR(128) NOT NULL"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
            )
            cur.execute(
                "CREATE TABLE students ("
                " id VARCHAR(36) NOT NULL PRIMARY KEY,"
                " class_id VARCHAR(36) NOT NULL,"
                " school_id VARCHAR(36) NULL,"
                " name VARCHAR(128) NOT NULL"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
            )
            cur.execute(
                "CREATE TABLE exam_scores ("
                " id VARCHAR(36) NOT NULL PRIMARY KEY,"
                " student_id VARCHAR(36) NOT NULL,"
                " class_id VARCHAR(36) NULL,"
                " school_id VARCHAR(36) NULL"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
            )
            cur.execute(
                "CREATE TABLE wrong_questions ("
                " id VARCHAR(36) NOT NULL PRIMARY KEY,"
                " student_id VARCHAR(36) NOT NULL,"
                " class_id VARCHAR(36) NOT NULL,"
                " school_id VARCHAR(36) NULL"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
            )
            # 业务行：2 班 2 生；e1 class_id 空（走 student 兜底）、e2 class_id 有值（走 class_id join）
            cur.execute(
                "INSERT INTO classes (id, user_id, name) VALUES ('c1','u1','一班'),('c2','u1','二班')"
            )
            cur.execute(
                "INSERT INTO students (id, class_id, school_id, name) VALUES "
                "('s1','c1',NULL,'甲'),('s2','c2',NULL,'乙')"
            )
            cur.execute(
                "INSERT INTO exam_scores (id, student_id, class_id, school_id) VALUES "
                "('e1','s1',NULL,NULL),('e2','s1','c1',NULL)"
            )
            cur.execute(
                "INSERT INTO wrong_questions (id, student_id, class_id, school_id) VALUES ('w1','s1','c1',NULL)"
            )

        sql_region = _read_sql(_MIGRATION_REGION)
        sql_backfill = _read_sql(_MIGRATION_BACKFILL).replace("REPLACE_WITH_PROFILE_ID", _PROFILE_ID)

        # 第一遍：DL1 建表 + DL2 回填
        with conn.cursor() as cur:
            cur.execute(sql_region)
            cur.execute(sql_backfill)
        with conn.cursor() as cur:
            _assert_backfill_state(cur)

        # 第二遍：重复执行，无副作用（幂等）
        with conn.cursor() as cur:
            cur.execute(sql_region)
            cur.execute(sql_backfill)
        with conn.cursor() as cur:
            _assert_backfill_state(cur)
    finally:
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{_SCRATCH_DB}`")
        conn.close()


def _assert_backfill_state(cur):
    """DB 用例状态断言：schools 1 行、四张表 school_id 全部回填到默认学校。"""
    cur.execute("SELECT COUNT(*) FROM schools")
    assert cur.fetchone()[0] == 1, "seed 后 schools 应恰好 1 行（幂等）"
    cur.execute("SELECT COUNT(*) FROM schools WHERE id = %s", (_DEFAULT_SCHOOL_ID,))
    assert cur.fetchone()[0] == 1, "默认学校 id 应为固定占位"
    cur.execute("SELECT COUNT(*) FROM classes WHERE school_id IS NULL")
    assert cur.fetchone()[0] == 0, "classes.school_id 应全部回填"
    cur.execute("SELECT COUNT(*) FROM students WHERE school_id IS NULL")
    assert cur.fetchone()[0] == 0, "students.school_id 应全部回填"
    cur.execute("SELECT COUNT(*) FROM exam_scores WHERE school_id IS NULL")
    assert cur.fetchone()[0] == 0, "exam_scores.school_id 应全部回填（含 student 兜底）"
    cur.execute("SELECT COUNT(*) FROM wrong_questions WHERE school_id IS NULL")
    assert cur.fetchone()[0] == 0, "wrong_questions.school_id 应全部回填"
    cur.execute("SELECT DISTINCT school_id FROM classes")
    assert {row[0] for row in cur.fetchall()} == {_DEFAULT_SCHOOL_ID}
