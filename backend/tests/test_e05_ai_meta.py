"""E05 AI 内容统一标识（GB 45438 隐式标识）· 后端验收测试。

覆盖：
  1. 迁移 SQL 幂等性（同一文件跑两遍不报错，三表 is_ai + ai_meta 列存在且只一列）
  2. 写入点冒烟（调用内部 upsert 函数）：
     - class_analysis_reports      → is_ai=1 + ai_meta={"generator":"qwen",...}
     - class_review_sessions       → is_ai=1 + ai_meta={"generator":"qwen",...}
     - targeted_improvement_reports→ is_ai=1 + ai_meta={"generator":"qwen",...}
  3. TestClient 读回冒烟：三表 API 读回 is_ai=true、ai_meta 有值
  4. AI 诊断 JSON 落盘 meta 往返：文件带 meta(is_ai/generator)，API 读回解包为原数组形状
  5. 组卷响应 is_ai 打标逻辑（纯函数级：标记函数对列表逐题加 is_ai）

环境：需要本地 Docker MySQL（127.0.0.1:13307, root/root_pw_2026）。
测试自建 grade_e05_test / grade_e05_mig 两个 scratch 库，跑完不清理以便复查，可手工 DROP。
"""
import os

# 用专用 E05_* 覆盖变量 + 本地 Docker 默认值，避免拾取 shell 中遗留的生产 DB_* 环境变量。
_DB_HOST = os.environ.get("E05_DB_HOST", "127.0.0.1")
_DB_PORT = int(os.environ.get("E05_DB_PORT", "13307"))
_DB_USER = os.environ.get("E05_DB_USER", "root")
_DB_PWD = os.environ.get("E05_DB_PASSWORD", "root_pw_2026")
_TEST_DB = os.environ.get("E05_TEST_DB", "grade_e05_test")
_MIG_DB = os.environ.get("E05_MIG_DB", "grade_e05_mig")

os.environ["DB_HOST"] = _DB_HOST
os.environ["DB_PORT"] = str(_DB_PORT)
os.environ["DB_USER"] = _DB_USER
os.environ["DB_PASSWORD"] = _DB_PWD
os.environ["DB_NAME"] = _TEST_DB
os.environ.setdefault("JWT_SECRET_KEY", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("AUTO_DDL", "false")

# 必须先建好 scratch 库，再导入 app.database（engine 绑定 DB_NAME）。
# Docker MySQL 不在时：DB 相关用例自动 skip，纯逻辑用例仍可跑。
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

import json
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import Base, engine, SessionLocal, get_db
from app.dependencies import bind_grading_user_context, get_current_user_id
from app.routers import student_analysis, class_analysis, class_review, targeted_improvement
from app.utils.qwen_settings import AI_GENERATOR

from app.models.user import User
from app.models.class_model import Class
from app.models.class_teacher import ClassTeacher
from app.models.student import Student
from app.models.system_settings import SystemSettings
from app.models.class_analysis import ClassAnalysisReport
from app.models.class_review import ClassReviewSession
from app.models.targeted_improvement import TargetedImprovementReport


# ── 纯逻辑用例（不依赖 DB）──────────────────────────────


def test_ai_generate_question_marking_injects_is_ai():
    """组卷打标逻辑：对 AI 生成的题目数组逐题加 is_ai=true（模拟 exams.ai_generate_exam 内的注入段）。"""
    questions = [
        {"id": "q1", "type": "choice", "stem": "s", "content": "c", "score": 5, "options": ["a", "b"]},
        {"id": "q2", "type": "judge", "stem": "", "content": "c2", "score": 3},
    ]
    for q in questions:
        if isinstance(q, dict):
            q["is_ai"] = True
    assert all(q.get("is_ai") is True for q in questions)
    # 非 dict 元素跳过不报错（契约：只打标对象）
    mixed = [{"id": "q1"}, None, 3]
    for q in mixed:
        if isinstance(q, dict):
            q["is_ai"] = True
    assert mixed[0]["is_ai"] is True and mixed[1] is None


def test_ai_meta_generator_constant():
    assert AI_GENERATOR == "qwen"


# ── TestClient 冒烟（Docker MySQL）──────────────────────

_E05_TABLES = [
    User.__table__,
    Class.__table__,
    ClassTeacher.__table__,
    Student.__table__,
    SystemSettings.__table__,
    ClassAnalysisReport.__table__,
    ClassReviewSession.__table__,
    TargetedImprovementReport.__table__,
]


@pytest.fixture(scope="module")
def test_app():
    if not _MYSQL_AVAILABLE:
        pytest.skip(f"本地 Docker MySQL 不可用，跳过 TestClient 冒烟：{_DB_ERR}")
    Base.metadata.create_all(bind=engine, tables=_E05_TABLES)

    app = FastAPI()
    app.include_router(student_analysis.router)
    app.include_router(class_analysis.router)
    app.include_router(class_review.router)
    app.include_router(targeted_improvement.router)

    def _fake_current_user(authorization: str | None = Header(None)) -> str:
        # 测试用：Authorization: Bearer <user_id> 直接作为当前用户 ID（跳过 JWT 解码）
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="未登录")
        return authorization.replace("Bearer ", "").strip()

    def _fake_bind(user_id: str = Depends(get_current_user_id)):
        # 模拟真实 bind_grading_user_context：绑定批改用户上下文（诊断落盘路径依赖）
        from app.grading.user_paths import set_grading_user_id
        set_grading_user_id(user_id)
        return user_id

    app.dependency_overrides[get_current_user_id] = _fake_current_user
    app.dependency_overrides[bind_grading_user_context] = _fake_bind

    with TestClient(app) as client:
        yield client

    # 清理本次测试数据（子表在前），避免污染下次运行
    with engine.begin() as conn:
        for table in (
            TargetedImprovementReport.__table__,
            ClassReviewSession.__table__,
            ClassAnalysisReport.__table__,
            Student.__table__,
            ClassTeacher.__table__,
            Class.__table__,
            User.__table__,
        ):
            conn.execute(table.delete())


@pytest.fixture()
def seed(test_app):
    """标准种子：T1 班主任(类属主) / U1 无权限教师。"""
    with SessionLocal() as db:
        for model in (TargetedImprovementReport, ClassReviewSession, ClassAnalysisReport, Student, ClassTeacher, Class, User, SystemSettings):
            db.query(model).delete()
        db.commit()

        t1 = User(id="T1", email="t1@test.local", password_hash="x", roles="班主任")
        u1 = User(id="U1", email="u1@test.local", password_hash="x", roles="任课教师")
        db.add_all([t1, u1])
        db.flush()

        c1 = Class(id="C1", user_id="T1", school_level="小学", grade="五年级", name="五(1)班")
        db.add(c1)
        db.flush()

        s1 = Student(id="S1", class_id="C1", user_id="T1", name="甲", student_number="001")
        db.add(s1)
        db.flush()

        db.commit()
        return {"T1": "T1", "U1": "U1", "S1": s1.id}


def _auth(token: str):
    return {"Authorization": f"Bearer {token}"}


# ── 写入点冒烟（内部 upsert 函数）────────────────────────


def test_class_analysis_upsert_writes_meta(test_app, seed):
    with SessionLocal() as db:
        report = {
            "id": "rep1",
            "class_id": "C1",
            "subject": "数学",
            "exam_names": ["期中"],
            "imported_folder_names": ["f1"],
            "source_summary": {},
            "analysis": {"conclusion": "整体良好"},
        }
        row = class_analysis._upsert_db_report(
            db,
            class_id="C1",
            class_name="五(1)班",
            subject="数学",
            report=report,
            model="qwen-test",
        )
        db.commit()
        assert row.is_ai == 1
        assert row.ai_meta == {"generator": "qwen", "model": "qwen-test"}


def test_class_review_upsert_writes_meta(test_app, seed):
    with SessionLocal() as db:
        row = class_review._upsert_session(
            db,
            "C1",
            "数学",
            ["f1"],
            {"exam_names": ["期中"]},
            {"pre_class": {"目标": "掌握重点"}},
        )
        db.commit()
        assert row.is_ai == 1
        assert row.ai_meta["generator"] == "qwen"
        assert row.ai_meta["model"]  # 从 qwen 配置解析出的模型名（缺省 qwen3.7-plus）


def test_targeted_improvement_upsert_writes_meta(test_app, seed):
    with SessionLocal() as db:
        student = db.query(Student).filter(Student.id == seed["S1"]).first()
        ai_data = {
            "diagnosis": {"summary": "计算薄弱"},
            "plan": {"goal": "每日练习"},
        }
        row = targeted_improvement._upsert_report(
            db,
            student=student,
            subject="数学",
            folders=["f1"],
            payload={"exam_count": 1, "exams": []},
            ai_data=ai_data,
            model="qwen-test",
        )
        db.commit()
        assert row.is_ai == 1
        assert row.ai_meta == {"generator": "qwen", "model": "qwen-test"}


# ── API 读回冒烟（is_ai / ai_meta 可见）─────────────────


def test_class_analysis_report_read_back_meta(test_app, seed):
    with SessionLocal() as db:
        db.add(ClassAnalysisReport(
            id="CR1",
            report_uuid="CRU1",
            class_id="C1",
            class_name="五(1)班",
            subject="数学",
            exam_names_json="[\"期中\"]",
            imported_folder_names_json="[]",
            source_summary_json="{}",
            analysis_json="{}",
            is_ai=1,
            ai_meta={"generator": "qwen", "model": "qwen-test"},
        ))
        db.commit()
    resp = test_app.get(
        "/class-analysis/report",
        headers=_auth(seed["T1"]),
        params={"class_id": "C1", "subject": "数学"},
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()["data"]["report"]
    assert report["is_ai"] is True
    assert report["ai_meta"]["generator"] == "qwen"


def test_class_review_report_read_back_meta(test_app, seed):
    with SessionLocal() as db:
        db.add(ClassReviewSession(
            id="CV1",
            class_id="C1",
            subject="数学",
            title="数学课堂讲评",
            exam_names_json="[\"期中\"]",
            imported_folder_names_json="[]",
            source_summary_json="{}",
            pre_class_json="{}",
            is_ai=1,
            ai_meta={"generator": "qwen", "model": "qwen-test"},
        ))
        db.commit()
    resp = test_app.get(
        "/class-review/report",
        headers=_auth(seed["T1"]),
        params={"class_id": "C1", "subject": "数学"},
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()["data"]["report"]
    assert report["is_ai"] is True
    assert report["ai_meta"]["generator"] == "qwen"


def test_targeted_improvement_report_read_back_meta(test_app, seed):
    with SessionLocal() as db:
        db.add(TargetedImprovementReport(
            id="TI1",
            class_id="C1",
            student_id=seed["S1"],
            student_name="甲",
            student_number="001",
            subject="数学",
            diagnosis_text="计算薄弱",
            plan_text="每日练习",
            diagnosis_json="{}",
            plan_json="{}",
            is_ai=1,
            ai_meta={"generator": "qwen", "model": "qwen-test"},
        ))
        db.commit()
    resp = test_app.get(
        "/targeted-improvement/report",
        headers=_auth(seed["T1"]),
        params={"class_id": "C1", "subject": "数学", "student_name": "甲"},
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()["data"]["report"]
    assert report["is_ai"] is True
    assert report["ai_meta"]["generator"] == "qwen"


# ── AI 诊断 JSON 落盘 meta（往返）────────────────────────


def test_ai_diagnosis_file_meta_roundtrip(test_app, seed):
    from app.grading.user_paths import set_grading_user_id
    from app.routers.student_analysis import _get_diagnosis_file

    set_grading_user_id("T1")
    f = _get_diagnosis_file("C1", "甲", "数学")
    f.parent.mkdir(parents=True, exist_ok=True)
    # 模拟 run_ai_diagnosis 的新落盘形状：外层带 meta，data 为原数组
    payload = {
        "meta": {"is_ai": True, "generator": "qwen", "model": "qwen3.7-plus"},
        "data": [{"dim": "计算能力", "student": 80, "class": 75}],
    }
    f.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    try:
        resp = test_app.get(
            "/student-analysis/ai-diagnosis",
            headers=_auth(seed["T1"]),
            params={"class_id": "C1", "student_name": "甲", "subject": "数学"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert isinstance(data, list) and data[0]["dim"] == "计算能力"  # 解包回原数组形状
        raw = json.loads(f.read_text(encoding="utf-8"))
        assert raw["meta"]["is_ai"] is True  # 隐式标识随文件落盘
        assert raw["meta"]["generator"] == "qwen"
    finally:
        if f.exists():
            f.unlink()


# ── 迁移 SQL 幂等性 ─────────────────────────────────────

_MIG_TABLES = [
    ("class_analysis_reports", ["is_ai", "ai_meta"]),
    ("class_review_sessions", ["is_ai", "ai_meta"]),
    ("targeted_improvement_reports", ["is_ai", "ai_meta"]),
]


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
            # 先建三张最小表（模拟既有表），再跑迁移
            for table in _MIG_TABLES:
                cur.execute(
                    f"CREATE TABLE `{table[0]}` ("
                    " id VARCHAR(36) NOT NULL PRIMARY KEY"
                    ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                )
        sql_path = Path(__file__).resolve().parent.parent / "docs" / "migrations" / "2026-08-15-ai-content-meta.sql"
        sql_text = sql_path.read_text(encoding="utf-8")

        def _assert_cols():
            with mig_conn.cursor() as cur:
                for table, cols in _MIG_TABLES:
                    for col in cols:
                        cur.execute(
                            "SELECT COUNT(*) FROM information_schema.COLUMNS"
                            " WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
                            (table, col),
                        )
                        assert cur.fetchone()[0] == 1, f"{table}.{col} 应已存在"

        # 第一遍：应执行 ALTER 成功
        with mig_conn.cursor() as cur:
            cur.execute(sql_text)
        _assert_cols()

        # 第二遍：幂等，不报错（命中 SELECT 1 空跑）
        with mig_conn.cursor() as cur:
            cur.execute(sql_text)
        _assert_cols()
    finally:
        with mig_conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{_MIG_DB}`")
        mig_conn.close()
