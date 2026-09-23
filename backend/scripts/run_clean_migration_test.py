# -*- coding: utf-8 -*-
"""干净库迁移验证：重建 grade_mig_clean → 建最小基础表 → 跑迁移(pass1) → 校验 → 幂等重跑(pass2)。

退出码 0 = 全部通过；非 0 = 有失败。
"""
import pymysql
from pymysql.constants import CLIENT

CONN = dict(host="127.0.0.1", port=3307, user="root", password="root_pw_2026", charset="utf8mb4")
DB = "grade_mig_clean"
MIG = "docs/migrations/2026-08-11-chunfeng-v1.sql"

BASE_TABLES = [
    "CREATE TABLE users (id VARCHAR(36) NOT NULL PRIMARY KEY, email VARCHAR(255) NULL, password_hash VARCHAR(255) NULL, roles VARCHAR(255) NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
    "CREATE TABLE classes (id VARCHAR(36) NOT NULL PRIMARY KEY, name VARCHAR(255) NULL, user_id VARCHAR(36) NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
    "CREATE TABLE students (id VARCHAR(36) NOT NULL PRIMARY KEY, name VARCHAR(255) NULL, class_id VARCHAR(36) NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
    "CREATE TABLE exam_scores (id VARCHAR(36) NOT NULL PRIMARY KEY, student_id VARCHAR(36) NULL, exam_id VARCHAR(36) NULL, score DECIMAL(10,2) NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
    "CREATE TABLE wrong_questions (id VARCHAR(36) NOT NULL PRIMARY KEY, student_id VARCHAR(36) NULL, question_id VARCHAR(36) NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
]

NEW_TABLES = [
    "student_portfolios", "student_growth_records", "report_snapshots", "assessment_comments", "mentors",
    "assessment_definitions", "assessment_sessions", "assessment_results", "assessment_answers", "parent_students",
    "badge_definitions", "badge_awards", "credit_accounts", "credit_transactions", "reward_products", "redemption_records",
    "practice_records", "campus_clubs", "club_enrollments", "club_attendance", "book_borrows", "reading_records",
    "health_checks", "student_tasks",
]
ALTER_COLS = [
    ("exam_scores", "class_avg"), ("exam_scores", "class_rank"), ("exam_scores", "class_id"), ("exam_scores", "school_id"),
    ("wrong_questions", "status"), ("wrong_questions", "corrected_at"), ("wrong_questions", "knowledge_point_id"), ("wrong_questions", "school_id"),
    ("students", "school_id"),
]
ALTER_IDX = [("wrong_questions", "idx_wq_status"), ("wrong_questions", "idx_wq_kp"), ("wrong_questions", "idx_wq_corrected")]


def conn(db=None):
    kw = dict(CONN)
    if db:
        kw["database"] = db
    return pymysql.connect(client_flag=CLIENT.MULTI_STATEMENTS, **kw)


def run_migration():
    with conn(DB) as c:
        cur = c.cursor()
        with open(MIG, encoding="utf-8") as f:
            sql = f.read()
        cur.execute(sql)
        while cur.nextset():
            pass
        c.commit()


def show_tables():
    with conn(DB) as c:
        cur = c.cursor()
        cur.execute("SHOW TABLES")
        return {r[0] for r in cur.fetchall()}


def col_exists(t, col):
    with conn(DB) as c:
        cur = c.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s",
            (DB, t, col))
        return cur.fetchone()[0] > 0


def idx_exists(t, ix):
    with conn(DB) as c:
        cur = c.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME=%s",
            (DB, t, ix))
        return cur.fetchone()[0] > 0


def verify(tag):
    tables = show_tables()
    missing = [t for t in NEW_TABLES if t not in tables]
    bad_cols = [(t, c) for t, c in ALTER_COLS if not col_exists(t, c)]
    bad_idx = [(t, i) for t, i in ALTER_IDX if not idx_exists(t, i)]
    print(f"[{tag}] new tables: {len(NEW_TABLES) - len(missing)}/{len(NEW_TABLES)}",
          "MISSING=" + ",".join(missing) if missing else "ALL OK")
    print(f"[{tag}] alter cols:", "ALL OK" if not bad_cols else "MISSING=" + ",".join(f"{t}.{c}" for t, c in bad_cols))
    print(f"[{tag}] alter idxs:", "ALL OK" if not bad_idx else "MISSING=" + ",".join(f"{t}.{i}" for t, i in bad_idx))
    return not missing and not bad_cols and not bad_idx


# 0. rebuild clean db + base tables
with conn() as c:
    cur = c.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS `{DB}`")
    cur.execute(f"CREATE DATABASE `{DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    c.commit()
with conn(DB) as c:
    cur = c.cursor()
    for stmt in BASE_TABLES:
        cur.execute(stmt)
    c.commit()
print("[setup] clean db + base tables created")

# 1. pass-1
run_migration()
print("[pass1] migration applied")
ok1 = verify("pass1")

# 2. pass-2 (idempotent re-run)
run_migration()
print("[pass2] migration re-applied (idempotent)")
ok2 = verify("pass2")

print("RESULT:", "PASS" if (ok1 and ok2) else "FAIL")
raise SystemExit(0 if (ok1 and ok2) else 1)
