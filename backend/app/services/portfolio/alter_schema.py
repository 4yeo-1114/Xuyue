"""
种春风 · 五育画像域 幂等建表 + 增量列（99 §4.1 DDL 的 Python 版）。

集成接入（integration-agent 挂到 AUTO_DDL=true 启动路径，sync_database_schema() 之后）：
    from app.services.portfolio.alter_schema import apply_schema
    apply_schema(db)

本地验收可单独跑：
    python -m app.services.portfolio.alter_schema   # 读环境变量连库执行

幂等性：CREATE TABLE IF NOT EXISTS + information_schema 检查跳过已存在列/索引，
重复执行不报错、无副作用。MySQL 8 新增列走 INSTANT 算法。

@MySQL-only：含 ENGINE=InnoDB / ON UPDATE CURRENT_TIMESTAMP / mysql+pymysql 方言 DDL，P3 PG 统一后不适用，归档保留。
"""
from __future__ import annotations

import logging
import os

from sqlalchemy import text
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── 1. 新表 CREATE TABLE IF NOT EXISTS（与 app/models/*.py 严格一致）──────────

_CREATE_TABLES: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS indicator_definitions (
        id          VARCHAR(36)  NOT NULL,
        dimension   VARCHAR(32)  NOT NULL,
        code        VARCHAR(64)  NOT NULL,
        name        VARCHAR(128) NOT NULL,
        description VARCHAR(512) NULL,
        level       INT          NOT NULL DEFAULT 2,
        parent_id   VARCHAR(36)  NULL,
        sort_order  INT          NOT NULL DEFAULT 0,
        is_active   INT          NOT NULL DEFAULT 1,
        school_id   VARCHAR(36)  NULL,
        created_at  DATETIME     NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at  DATETIME     NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uq_id_code_school (code, school_id),
        KEY idx_id_dim_active (dimension, is_active),
        KEY idx_id_parent (parent_id),
        KEY ix_indicator_definitions_dimension (dimension),
        KEY ix_indicator_definitions_is_active (is_active),
        CONSTRAINT fk_id_parent FOREIGN KEY (parent_id) REFERENCES indicator_definitions (id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS student_portfolios (
        id                   VARCHAR(36)  NOT NULL,
        student_id           VARCHAR(36)  NOT NULL,
        class_id             VARCHAR(36)  NOT NULL,
        school_id            VARCHAR(36)  NULL,
        base_points          INT          NOT NULL DEFAULT 100,
        dimensions           JSON         NOT NULL,
        detail               JSON         NULL,
        auto_detail          JSON         NULL,
        total_growth_point   DECIMAL(10,2) NOT NULL DEFAULT 0.00,
        last_calculated_at   DATETIME     NULL,
        created_at           DATETIME     NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at           DATETIME     NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uq_sp_student_id (student_id),
        KEY idx_sp_class_id (class_id),
        CONSTRAINT fk_sp_student FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE,
        CONSTRAINT fk_sp_class   FOREIGN KEY (class_id)   REFERENCES classes  (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS student_growth_records (
        id            VARCHAR(36)  NOT NULL,
        student_id    VARCHAR(36)  NOT NULL,
        class_id      VARCHAR(36)  NOT NULL,
        school_id     VARCHAR(36)  NULL,
        dimension     VARCHAR(32)  NOT NULL,
        source_type   VARCHAR(32)  NOT NULL DEFAULT 'manual',
        source_id     VARCHAR(36)  NULL,
        growth_points INT          NOT NULL DEFAULT 0,
        evidence      JSON         NULL,
        note          VARCHAR(512) NULL,
        created_by    VARCHAR(36)  NULL,
        occurred_at   DATETIME     NULL,
        created_at    DATETIME     NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at    DATETIME     NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        KEY idx_sgr_student_id (student_id),
        KEY idx_sgr_student_dim (student_id, dimension),
        KEY idx_sgr_student_time (student_id, occurred_at),
        KEY idx_sgr_source (source_type, source_id),
        CONSTRAINT fk_sgr_student  FOREIGN KEY (student_id)  REFERENCES students (id) ON DELETE CASCADE,
        CONSTRAINT fk_sgr_class    FOREIGN KEY (class_id)    REFERENCES classes  (id) ON DELETE CASCADE,
        CONSTRAINT fk_sgr_creator  FOREIGN KEY (created_by)  REFERENCES users     (id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS report_snapshots (
        id            VARCHAR(36) NOT NULL,
        student_id    VARCHAR(36) NOT NULL,
        class_id      VARCHAR(36) NOT NULL,
        school_id     VARCHAR(36) NULL,
        term          VARCHAR(32) NOT NULL,
        version       INT         NOT NULL DEFAULT 1,
        parent_id     VARCHAR(36) NULL,
        payload       JSON        NOT NULL,
        generated_by  VARCHAR(36) NOT NULL,
        created_at    DATETIME    NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uq_rs_student_term_version (student_id, term, version),
        KEY idx_rs_class_term (class_id, term),
        CONSTRAINT fk_rs_student    FOREIGN KEY (student_id)   REFERENCES students (id) ON DELETE CASCADE,
        CONSTRAINT fk_rs_parent     FOREIGN KEY (parent_id)    REFERENCES report_snapshots (id) ON DELETE SET NULL,
        CONSTRAINT fk_rs_generator  FOREIGN KEY (generated_by) REFERENCES users (id) ON DELETE CASCADE,
        CONSTRAINT fk_rs_class      FOREIGN KEY (class_id)     REFERENCES classes (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS assessment_comments (
        id                 VARCHAR(36) NOT NULL,
        student_id         VARCHAR(36) NOT NULL,
        class_id           VARCHAR(36) NOT NULL,
        school_id          VARCHAR(36) NULL,
        term               VARCHAR(32) NOT NULL,
        status             VARCHAR(16) NOT NULL DEFAULT 'ai_generated',
        ai_content         TEXT        NULL,
        confirmed_content  TEXT        NULL,
        ai_model           VARCHAR(64) NULL,
        tokens_used        INT         NULL,
        cost_cent          INT         NULL,
        gate_flagged       TINYINT(1)  NOT NULL DEFAULT 0,
        created_by         VARCHAR(36) NOT NULL,
        confirmed_by       VARCHAR(36) NULL,
        confirmed_at       DATETIME    NULL,
        created_at         DATETIME    NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at         DATETIME    NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uq_ac_student_term (student_id, term),
        KEY idx_ac_class_term (class_id, term),
        CONSTRAINT fk_ac_student      FOREIGN KEY (student_id)   REFERENCES students (id) ON DELETE CASCADE,
        CONSTRAINT fk_ac_class        FOREIGN KEY (class_id)     REFERENCES classes  (id) ON DELETE CASCADE,
        CONSTRAINT fk_ac_creator      FOREIGN KEY (created_by)   REFERENCES users (id) ON DELETE CASCADE,
        CONSTRAINT fk_ac_confirmer    FOREIGN KEY (confirmed_by) REFERENCES users (id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS mentors (
        id            VARCHAR(36) NOT NULL,
        student_id    VARCHAR(36) NOT NULL,
        user_id       VARCHAR(36) NOT NULL,
        role          VARCHAR(16) NOT NULL DEFAULT 'tutor',
        assigned_by   VARCHAR(36) NULL,
        status        VARCHAR(16) NOT NULL DEFAULT 'active',
        created_at    DATETIME    NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at    DATETIME    NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uq_mtr_student_user (student_id, user_id),
        KEY idx_mtr_user_id (user_id),
        CONSTRAINT fk_mtr_student FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE,
        CONSTRAINT fk_mtr_user    FOREIGN KEY (user_id)    REFERENCES users    (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]

# ── 2. 既有表增量列（(table, column, ddl)）────────────

_COLUMN_ALTERS: list[tuple[str, str, str]] = [
    ("indicator_definitions", "level",
     "ALTER TABLE indicator_definitions ADD COLUMN level INT NOT NULL DEFAULT 2"),
    ("indicator_definitions", "parent_id",
     "ALTER TABLE indicator_definitions ADD COLUMN parent_id VARCHAR(36) NULL"),
    ("student_growth_records", "indicator_id",
     "ALTER TABLE student_growth_records ADD COLUMN indicator_id VARCHAR(36) NULL"),
    ("exam_scores", "class_avg",
     "ALTER TABLE exam_scores ADD COLUMN class_avg DECIMAL(10,2) NULL"),
    ("exam_scores", "class_rank",
     "ALTER TABLE exam_scores ADD COLUMN class_rank INT NULL"),
    ("exam_scores", "class_id",
     "ALTER TABLE exam_scores ADD COLUMN class_id VARCHAR(36) NULL"),
    ("exam_scores", "school_id",
     "ALTER TABLE exam_scores ADD COLUMN school_id VARCHAR(36) NULL"),
    ("exam_scores", "grade",
     "ALTER TABLE exam_scores ADD COLUMN grade VARCHAR(16) NULL"),
    ("wrong_questions", "status",
     "ALTER TABLE wrong_questions ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'open'"),
    ("wrong_questions", "corrected_at",
     "ALTER TABLE wrong_questions ADD COLUMN corrected_at DATETIME NULL"),
    ("wrong_questions", "knowledge_point_id",
     "ALTER TABLE wrong_questions ADD COLUMN knowledge_point_id VARCHAR(36) NULL"),
    ("wrong_questions", "school_id",
     "ALTER TABLE wrong_questions ADD COLUMN school_id VARCHAR(36) NULL"),
    ("students", "school_id",
     "ALTER TABLE students ADD COLUMN school_id VARCHAR(36) NULL"),
]

# ── 3. 既有表增量索引（(table, index, ddl)）───────────

_INDEX_ALTERS: list[tuple[str, str, str]] = [
    ("indicator_definitions", "idx_id_parent",
     "ALTER TABLE indicator_definitions ADD INDEX idx_id_parent (parent_id)"),
    ("student_growth_records", "ix_student_growth_records_indicator_id",
     "ALTER TABLE student_growth_records ADD INDEX ix_student_growth_records_indicator_id (indicator_id)"),
    ("wrong_questions", "idx_wq_status",
     "ALTER TABLE wrong_questions ADD INDEX idx_wq_status (student_id, status)"),
    ("wrong_questions", "idx_wq_kp",
     "ALTER TABLE wrong_questions ADD INDEX idx_wq_kp (student_id, knowledge_point_id, status)"),
    ("wrong_questions", "idx_wq_corrected",
     "ALTER TABLE wrong_questions ADD INDEX idx_wq_corrected (student_id, corrected_at)"),
]

# ── 4. 既有表增量外键（(table, constraint, ddl)）──────────

_FK_ALTERS: list[tuple[str, str, str]] = [
    ("indicator_definitions", "fk_id_parent",
     "ALTER TABLE indicator_definitions ADD CONSTRAINT fk_id_parent "
     "FOREIGN KEY (parent_id) REFERENCES indicator_definitions (id) ON DELETE SET NULL"),
    ("student_growth_records", "fk_sgr_indicator",
     "ALTER TABLE student_growth_records ADD CONSTRAINT fk_sgr_indicator "
     "FOREIGN KEY (indicator_id) REFERENCES indicator_definitions (id) ON DELETE SET NULL"),
]


def _column_exists(conn: Connection, table: str, column: str) -> bool:
    row = conn.execute(text(
        "SELECT COUNT(*) AS c FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
    ), {"t": table, "c": column}).mappings().first()
    return bool(row and int(row["c"]) > 0)


def _index_exists(conn: Connection, table: str, index: str) -> bool:
    row = conn.execute(text(
        "SELECT COUNT(*) AS c FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND INDEX_NAME = :i"
    ), {"t": table, "i": index}).mappings().first()
    return bool(row and int(row["c"]) > 0)


def _fk_exists(conn: Connection, table: str, constraint: str) -> bool:
    row = conn.execute(text(
        "SELECT COUNT(*) AS c FROM information_schema.REFERENTIAL_CONSTRAINTS "
        "WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = :t AND CONSTRAINT_NAME = :n"
    ), {"t": table, "n": constraint}).mappings().first()
    return bool(row and int(row["c"]) > 0)


def apply_schema(db: Session | Engine | Connection) -> dict:
    """执行幂等建表 + 增量列/索引/外键。返回 {created_tables, added_columns, added_indexes, added_fks}。

    兼容三种入参：
      - Session        （集成路径：sync_database_schema() 之后传 db）
      - Engine         （自动 connect + 最后 commit + close）
      - Connection     （由调用方管理事务，函数不 commit 不 close）
    """
    own_conn: Connection | None = None
    if isinstance(db, Session):
        conn = db.connection()
        commit = lambda: db.commit()  # noqa: E731
    elif isinstance(db, Connection):
        conn = db
        commit = lambda: None  # noqa: E731 —— 由调用方事务管理
    else:  # Engine
        conn = db.connect()
        own_conn = conn
        commit = lambda: conn.commit()  # noqa: E731
    try:
        for ddl in _CREATE_TABLES:
            conn.execute(text(ddl))
        added_cols: list[str] = []
        for table, column, ddl in _COLUMN_ALTERS:
            if not _column_exists(conn, table, column):
                conn.execute(text(ddl))
                added_cols.append(f"{table}.{column}")
        added_idx: list[str] = []
        for table, index, ddl in _INDEX_ALTERS:
            if not _index_exists(conn, table, index):
                conn.execute(text(ddl))
                added_idx.append(f"{table}.{index}")
        added_fk: list[str] = []
        for table, constraint, ddl in _FK_ALTERS:
            if not _fk_exists(conn, table, constraint):
                conn.execute(text(ddl))
                added_fk.append(f"{table}.{constraint}")
        commit()
        summary = {
            "created_tables": [
                "indicator_definitions", "student_portfolios", "student_growth_records",
                "report_snapshots", "assessment_comments", "mentors",
            ],
            "added_columns": added_cols,
            "added_indexes": added_idx,
            "added_fks": added_fk,
        }
        logger.info("[portfolio.alter_schema] 完成: %s", summary)
        return summary
    finally:
        if own_conn is not None:
            own_conn.close()


# ── 独立执行入口：python -m app.services.portfolio.alter_schema ──────────
def _standalone() -> None:
    import time

    from sqlalchemy import create_engine

    host = os.environ.get("DB_HOST", "127.0.0.1")
    port = os.environ.get("DB_PORT", "3307")
    user = os.environ.get("DB_USER", "root")
    pwd = os.environ.get("DB_PASSWORD", "root_pw_2026")
    name = os.environ.get("DB_NAME", "grade")
    engine = create_engine(
        f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{name}?charset=utf8mb4",
        pool_pre_ping=True,
    )
    t0 = time.time()
    with engine.begin() as conn:
        summary = apply_schema(conn)
    print(f"[ok] 幂等建表/ALTER 完成，耗时 {(time.time() - t0) * 1000:.0f}ms")
    print(summary)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _standalone()
