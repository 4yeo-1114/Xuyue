"""E04 隐私优先成绩单 · 后端验收测试。

覆盖：
  1. grade_for_score 分数→等级纯函数边界（85/84/70/69/60/59/None）
  2. filter_rankings_for_parent / ensure_ranking_grade 纯函数
  3. TestClient 冒烟（本地 Docker MySQL 127.0.0.1:13307，scratch 库 grade_e04_test）：
     - 教师/管理员能读全班成绩（含 grade）、批量写成绩（grade 自动算）
     - 无班级权限用户读写 403
     - 家长视图：rankings 只留绑定学生记录且去掉 rank；教师/管理员视图保持完整
  4. 迁移 SQL 幂等性（同一文件跑两遍不报错，列存在）

环境：需要本地 Docker MySQL（127.0.0.1:13307, root/root_pw_2026）。
测试自建 grade_e04_test / grade_e04_mig 两个 scratch 库，跑完不清理以便复查，可手工 DROP。
"""
import os

# 用专用 E04_* 覆盖变量 + 本地 Docker 默认值，避免拾取 shell 中遗留的生产 DB_* 环境变量。
_DB_HOST = os.environ.get("E04_DB_HOST", "127.0.0.1")
_DB_PORT = int(os.environ.get("E04_DB_PORT", "13307"))
_DB_USER = os.environ.get("E04_DB_USER", "root")
_DB_PWD = os.environ.get("E04_DB_PASSWORD", "root_pw_2026")
_TEST_DB = os.environ.get("E04_TEST_DB", "grade_e04_test")
_MIG_DB = os.environ.get("E04_MIG_DB", "grade_e04_mig")

os.environ["DB_HOST"] = _DB_HOST
os.environ["DB_PORT"] = str(_DB_PORT)
os.environ["DB_USER"] = _DB_USER
os.environ["DB_PASSWORD"] = _DB_PWD
os.environ["DB_NAME"] = _TEST_DB
os.environ.setdefault("JWT_SECRET_KEY", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("AUTO_DDL", "false")

# 必须先建好 scratch 库，再导入 app.database（engine 绑定 DB_NAME）。
# Docker MySQL 不在时：DB 相关用例自动 skip，纯函数单测仍可跑。
_MYSQL_AVAILABLE = False
import pymysql

try:
    _conn = pymysql.connect(host=_DB_HOST, port=_DB_PORT, user=_DB_USER, password=_DB_PWD, autocommit=True, connect_timeout=5)
    with _conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS `{_TEST_DB}`")
        cur.execute(f"CREATE DATABASE `{_TEST_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    _conn.close()
    _MYSQL_AVAILABLE = True
except Exception as _db_err:  # noqa: BLE001 - 环境不可用则降级跳过 DB 用例
    _MYSQL_AVAILABLE = False
    _DB_ERR = str(_db_err)

from pathlib import Path

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import Base, engine, SessionLocal, get_db
from app.dependencies import bind_grading_user_context, get_current_user_id
from app.routers import student_analysis, class_analysis
from app.services.grade_scores import (
    ensure_ranking_grade,
    filter_rankings_for_parent,
    grade_for_score,
)
from app.models.user import User
from app.models.class_model import Class
from app.models.student import Student
from app.models.exam import Exam
from app.models.exam_score import ExamScore
from app.models.class_analysis import ClassAnalysisReport
from app.models.parent_student import ParentStudent
from app.models.class_teacher import ClassTeacher

# ── 纯函数单测（不依赖 DB）──────────────────────────────


def test_grade_for_score_boundaries():
    cases = [
        (85, "excellent"),
        (84, "good"),
        (70, "good"),
        (69, "pass"),
        (60, "pass"),
        (59, "needs_work"),
        (0, "needs_work"),
        (100, "excellent"),
    ]
    for score, expected in cases:
        assert grade_for_score(score) == expected, f"score={score}"
    assert grade_for_score(None) is None
    assert grade_for_score("abc") is None
    assert grade_for_score(84.9) == "good"  # float 边界 >=70


def test_ensure_ranking_grade_backfills_missing():
    rows = [
        {"student_id": "s1", "score": 92},
        {"student_id": "s2", "score": 55, "grade": "needs_work"},  # 已有合法 grade 保留
        {"student_id": "s3", "score": None},
    ]
    ensure_ranking_grade(rows)
    assert rows[0]["grade"] == "excellent"
    assert rows[1]["grade"] == "needs_work"
    assert rows[2]["grade"] is None


def test_filter_rankings_for_parent_keeps_only_bound_and_strips_rank():
    rankings = [
        {"student_id": "s1", "student_name": "甲", "score": 92, "grade": "excellent", "rank": 1},
        {"student_id": "s2", "student_name": "乙", "score": 55, "grade": "needs_work", "rank": 2},
    ]
    out = filter_rankings_for_parent(rankings, ["s1"])
    assert len(out) == 1
    assert out[0]["student_id"] == "s1"
    assert out[0]["grade"] == "excellent"
    assert "rank" not in out[0]
    assert "score" in out[0]  # 本人成绩保留


# ── TestClient 冒烟（Docker MySQL）──────────────────────

_E04_TABLES = [
    User.__table__,
    Class.__table__,
    ClassTeacher.__table__,
    Student.__table__,
    Exam.__table__,
    ExamScore.__table__,
    ClassAnalysisReport.__table__,
    ParentStudent.__table__,
]


@pytest.fixture(scope="module")
def test_app():
    if not _MYSQL_AVAILABLE:
        pytest.skip(f"本地 Docker MySQL 不可用，跳过 TestClient 冒烟：{_DB_ERR}")
    # 只建 E04 冒烟需要的 8 张表（全量 58 表 DDL 在本机 Docker 上过慢，非必须不建）
    Base.metadata.create_all(bind=engine, tables=_E04_TABLES)

    app = FastAPI()
    app.include_router(student_analysis.router)
    app.include_router(class_analysis.router)

    def _fake_current_user(authorization: str | None = Header(None)) -> str:
        # 测试用：Authorization: Bearer <user_id> 直接作为当前用户 ID（跳过 JWT 解码）
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="未登录")
        return authorization.replace("Bearer ", "").strip()

    def _fake_bind(user_id: str = Depends(get_current_user_id)):
        return user_id

    app.dependency_overrides[get_current_user_id] = _fake_current_user
    app.dependency_overrides[bind_grading_user_context] = _fake_bind

    with TestClient(app) as client:
        yield client

    # 清理本次测试数据（子表在前），避免污染下次运行
    with engine.begin() as conn:
        for table in (
            ParentStudent.__table__,
            ExamScore.__table__,
            ClassAnalysisReport.__table__,
            Exam.__table__,
            Student.__table__,
            ClassTeacher.__table__,
            Class.__table__,
            User.__table__,
        ):
            conn.execute(table.delete())


@pytest.fixture()
def seed(test_app):
    """标准种子：T1 班主任(类属主) / A1 系统管理员 / P1 家长(绑定 S1) / U1 无权限教师。

    每个用例前先清空相关表，保证幂等、互不污染。
    """
    with SessionLocal() as db:
        for model in (ParentStudent, ExamScore, ClassAnalysisReport, Exam, Student, ClassTeacher, Class, User):
            db.query(model).delete()
        db.commit()

        t1 = User(id="T1", email="t1@test.local", password_hash="x", roles="班主任")
        a1 = User(id="A1", email="a1@test.local", password_hash="x", roles="系统管理员")
        p1 = User(id="P1", email="p1@test.local", password_hash="x", roles="")
        u1 = User(id="U1", email="u1@test.local", password_hash="x", roles="任课教师")
        db.add_all([t1, a1, p1, u1])
        db.flush()

        c1 = Class(id="C1", user_id="T1", school_level="小学", grade="五年级", name="五(1)班")
        db.add(c1)
        db.flush()

        s1 = Student(id="S1", class_id="C1", user_id="T1", name="甲", student_number="001")
        s2 = Student(id="S2", class_id="C1", user_id="T1", name="乙", student_number="002")
        db.add_all([s1, s2])
        db.flush()

        e1 = Exam(id="E1", user_id="T1", class_id="C1", subject="数学", title="期中", total_score=100, exam_date="2026-08-15")
        db.add(e1)
        db.flush()

        ps = ParentStudent(id="PS1", parent_id="P1", student_id="S1", relation="guardian", status="active")
        db.add(ps)
        db.flush()

        db.commit()
        db.refresh(s1)
        db.refresh(s2)
        return {"T1": "T1", "A1": "A1", "P1": "P1", "U1": "U1", "S1": s1.id, "S2": s2.id, "E1": e1.id}


def _auth(token: str):
    return {"Authorization": f"Bearer {token}"}


def test_teacher_read_write_exam_scores(test_app, seed):
    # 写：批量保存两次考试分数，grade 由后端自动算
    resp = test_app.post(
        "/student-analysis/exam-scores",
        headers=_auth(seed["T1"]),
        json=[
            {"exam_id": seed["E1"], "student_id": seed["S1"], "score": 92},
            {"exam_id": seed["E1"], "student_id": seed["S2"], "score": 55},
        ],
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    by_student = {item["student_id"]: item for item in data}
    assert by_student[seed["S1"]]["grade"] == "excellent"
    assert by_student[seed["S2"]]["grade"] == "needs_work"
    assert by_student[seed["S1"]]["score"] == 92

    # 读：按 exam 读全班成绩，grade 落库
    resp = test_app.get("/student-analysis/exam-scores", headers=_auth(seed["T1"]), params={"exam_id": seed["E1"]})
    assert resp.status_code == 200, resp.text
    rows = resp.json()["data"]
    assert len(rows) == 2
    by_student = {item["student_id"]: item for item in rows}
    assert by_student[seed["S1"]]["grade"] == "excellent"
    assert by_student[seed["S2"]]["grade"] == "needs_work"

    # 更新：同 exam+student 改分数，grade 跟着重算
    resp = test_app.post(
        "/student-analysis/exam-scores",
        headers=_auth(seed["T1"]),
        json=[{"exam_id": seed["E1"], "student_id": seed["S1"], "score": 65}],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"][0]["grade"] == "pass"

    # 未评分：score 空 → grade 空
    resp = test_app.post(
        "/student-analysis/exam-scores",
        headers=_auth(seed["T1"]),
        json=[{"exam_id": seed["E1"], "student_id": seed["S1"], "score": None}],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"][0]["grade"] is None


def test_admin_can_read_write_exam_scores(test_app, seed):
    resp = test_app.post(
        "/student-analysis/exam-scores",
        headers=_auth(seed["A1"]),
        json=[{"exam_id": seed["E1"], "student_id": seed["S1"], "score": 88}],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"][0]["grade"] == "excellent"
    resp = test_app.get("/student-analysis/exam-scores", headers=_auth(seed["A1"]), params={"exam_id": seed["E1"]})
    assert resp.status_code == 200, resp.text


def test_unauthorized_user_cannot_access_exam_scores(test_app, seed):
    # 无权限教师 U1：读/写均 403
    resp = test_app.get("/student-analysis/exam-scores", headers=_auth(seed["U1"]), params={"exam_id": seed["E1"]})
    assert resp.status_code == 403, resp.text
    resp = test_app.post(
        "/student-analysis/exam-scores",
        headers=_auth(seed["U1"]),
        json=[{"exam_id": seed["E1"], "student_id": seed["S1"], "score": 90}],
    )
    assert resp.status_code == 403, resp.text


def _seed_report(db: Session, rankings: list[dict]) -> None:
    report = {
        "id": "rep1",
        "class_id": "C1",
        "subject": "数学",
        "exam_names": ["期中"],
        "source_summary": {
            "overall_metrics": {},
            "exam_summaries": [
                {"exam_name": "期中", "rankings": rankings},
            ],
        },
        "analysis": {},
    }
    import json
    db.add(ClassAnalysisReport(
        id="CR1",
        report_uuid="CRU1",
        class_id="C1",
        class_name="五(1)班",
        subject="数学",
        exam_names_json=json.dumps(["期中"]),
        imported_folder_names_json="[]",
        source_summary_json=json.dumps(report["source_summary"], ensure_ascii=False),
        analysis_json="{}",
    ))
    db.commit()


def test_report_teacher_full_view_with_grade(test_app, seed):
    # 旧报告 rankings 不带 grade（验证 _ensure_report_grades 派生）
    with SessionLocal() as db:
        _seed_report(db, [
            {"student_id": seed["S1"], "student_name": "甲", "score": 92, "rank": 1},
            {"student_id": seed["S2"], "student_name": "乙", "score": 55, "rank": 2},
        ])
    resp = test_app.get("/class-analysis/report", headers=_auth(seed["T1"]), params={"class_id": "C1", "subject": "数学"})
    assert resp.status_code == 200, resp.text
    report = resp.json()["data"]["report"]
    rankings = report["source_summary"]["exam_summaries"][0]["rankings"]
    assert len(rankings) == 2
    by_name = {r["student_name"]: r for r in rankings}
    assert by_name["甲"]["grade"] == "excellent"
    assert by_name["乙"]["grade"] == "needs_work"
    assert "rank" in by_name["甲"]  # 教师视图保留 rank


def test_report_parent_view_trimmed(test_app, seed):
    with SessionLocal() as db:
        _seed_report(db, [
            {"student_id": seed["S1"], "student_name": "甲", "score": 92, "rank": 1},
            {"student_id": seed["S2"], "student_name": "乙", "score": 55, "rank": 2},
        ])
    resp = test_app.get("/class-analysis/report", headers=_auth(seed["P1"]), params={"class_id": "C1", "subject": "数学"})
    assert resp.status_code == 200, resp.text
    report = resp.json()["data"]["report"]
    rankings = report["source_summary"]["exam_summaries"][0]["rankings"]
    # 只保留绑定学生 S1 的记录
    assert [r["student_id"] for r in rankings] == [seed["S1"]]
    assert rankings[0]["grade"] == "excellent"
    assert "rank" not in rankings[0]
    assert "score" in rankings[0]

    # 未绑定该班学生的家长访问本班报告 → 403
    resp = test_app.get("/class-analysis/report", headers=_auth(seed["U1"]), params={"class_id": "C1", "subject": "数学"})
    assert resp.status_code == 403, resp.text


# ── 迁移 SQL 幂等性 ─────────────────────────────────────

def test_migration_sql_idempotent():
    if not _MYSQL_AVAILABLE:
        pytest.skip(f"本地 Docker MySQL 不可用，跳过迁移幂等性用例：{_DB_ERR}")
    mig_conn = pymysql.connect(
        host=_DB_HOST, port=_DB_PORT, user=_DB_USER, password=_DB_PWD,
        autocommit=True, client_flag=pymysql.constants.CLIENT.MULTI_STATEMENTS,
    )
    try:
        with mig_conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{_MIG_DB}`")
            cur.execute(f"CREATE DATABASE `{_MIG_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cur.execute(f"USE `{_MIG_DB}`")
            # 先建一张最小 exam_scores 表（模拟既有表），再跑迁移
            cur.execute(
                "CREATE TABLE exam_scores ("
                " id VARCHAR(36) NOT NULL PRIMARY KEY,"
                " user_id VARCHAR(36) NOT NULL,"
                " exam_id VARCHAR(36) NOT NULL,"
                " student_id VARCHAR(36) NOT NULL,"
                " score FLOAT NULL"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )
        sql_path = Path(__file__).resolve().parent.parent / "docs" / "migrations" / "2026-08-15-exam-score-grade.sql"
        sql_text = sql_path.read_text(encoding="utf-8")

        # 第一遍：应执行 ALTER 成功
        with mig_conn.cursor() as cur:
            cur.execute(sql_text)
        with mig_conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME='exam_scores' AND COLUMN_NAME='grade'")
            assert cur.fetchone()[0] == 1, "grade 列应已存在"

        # 第二遍：幂等，不报错（命中 SELECT 1 空跑）
        with mig_conn.cursor() as cur:
            cur.execute(sql_text)
        with mig_conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME='exam_scores' AND COLUMN_NAME='grade'")
            assert cur.fetchone()[0] == 1, "第二遍后 grade 列仍应只有一列"
    finally:
        with mig_conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{_MIG_DB}`")
        mig_conn.close()
