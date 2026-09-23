"""E10 学生 PII 角色分层脱敏 · 后端验收测试。

覆盖（契约：全局管理员 + 班主任(head) 看完整 PII；副班主任(deputy)/协作教师(teacher) 看掩码）：
  1. GET /students：全局管理员/班主任 看完整 PII
  2. GET /students：deputy/teacher 看掩码（phone 含 ****、学号 XX****XX、address 带 **、
     parent_name 带 **、birthday 为 None；非 PII 字段保持原样）
  3. POST /students 回显完整（仅 head 可达），deputy 建学生 403
  4. PATCH /students/{id} 回显完整（仅 head 可达）
  5. /admin/rights/data/export CSV 导出：head/全局管理员 完整；deputy/teacher 掩码

环境：需要本地 Docker MySQL（127.0.0.1:13307, root/root_pw_2026）。
测试自建 grade_e10_test scratch 库，跑完不清理以便复查，可手工 DROP。
"""
import os

# 用专用 E10_* 覆盖变量 + 本地 Docker 默认值，避免拾取 shell 中遗留的生产 DB_* 环境变量。
_DB_HOST = os.environ.get("E10_DB_HOST", "127.0.0.1")
_DB_PORT = int(os.environ.get("E10_DB_PORT", "13307"))
_DB_USER = os.environ.get("E10_DB_USER", "root")
_DB_PWD = os.environ.get("E10_DB_PASSWORD", "root_pw_2026")
_TEST_DB = os.environ.get("E10_TEST_DB", "grade_e10_test")

os.environ["DB_HOST"] = _DB_HOST
os.environ["DB_PORT"] = str(_DB_PORT)
os.environ["DB_USER"] = _DB_USER
os.environ["DB_PASSWORD"] = _DB_PWD
os.environ["DB_NAME"] = _TEST_DB
os.environ.setdefault("JWT_SECRET_KEY", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("AUTO_DDL", "false")
os.environ.setdefault("DASHSCOPE_API_KEY", "sk-e10-test-not-real")

# 必须先建好 scratch 库，再导入 app.database（engine 绑定 DB_NAME）。
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

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.dependencies import bind_grading_user_context, get_current_user_id
from app.routers import admin_rights, students

from app.models.user import User
from app.models.class_model import Class
from app.models.class_teacher import ClassTeacher
from app.models.student import Student
from app.models.exam import Exam
from app.models.exam_score import ExamScore
from app.models.indicator_definition import IndicatorDefinition
from app.models.student_growth_record import StudentGrowthRecord
from app.models.student_portfolio import StudentPortfolio
from app.models.evaluation_archive import EvaluationArchive
from app.models.assessment_definition import AssessmentDefinition
from app.models.assessment_session import AssessmentSession
from app.models.assessment_result import AssessmentResult

# admin_rights._csv_rows 会查询画像/成长/综评/测评/成绩等表，建全依赖表，避免 FK 缺失。
_E10_TABLES = [
    User.__table__,
    Class.__table__,
    ClassTeacher.__table__,
    Student.__table__,
    Exam.__table__,
    ExamScore.__table__,
    IndicatorDefinition.__table__,
    StudentGrowthRecord.__table__,
    StudentPortfolio.__table__,
    EvaluationArchive.__table__,
    AssessmentDefinition.__table__,
    AssessmentSession.__table__,
    AssessmentResult.__table__,
]

# 删除顺序：子表在前，父表在后（FK CASCADE）。
_TEAR_DOWN_TABLES = [
    ExamScore.__table__,
    AssessmentResult.__table__,
    AssessmentSession.__table__,
    AssessmentDefinition.__table__,
    StudentGrowthRecord.__table__,
    StudentPortfolio.__table__,
    EvaluationArchive.__table__,
    Exam.__table__,
    IndicatorDefinition.__table__,
    Student.__table__,
    ClassTeacher.__table__,
    Class.__table__,
    User.__table__,
]


# 专用引擎：绑定本模块 scratch 库（grade_e10_test），避免被共享 app.database.engine 的
# 首次导入绑定污染（其他测试模块可能带脏 DB_* 环境变量先导入 app.database，导致连不上库）。
_TEST_DB_URL = f"mysql+pymysql://{_DB_USER}:{_DB_PWD}@{_DB_HOST}:{_DB_PORT}/{_TEST_DB}"


@pytest.fixture(scope="module")
def test_db():
    if not _MYSQL_AVAILABLE:
        pytest.skip(f"本地 Docker MySQL 不可用，跳过 TestClient 冒烟：{_DB_ERR}")
    test_engine = create_engine(_TEST_DB_URL, pool_pre_ping=True)
    test_session_factory = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine, tables=_E10_TABLES)
    yield test_session_factory, test_engine

    # 清理本次测试数据（子表在前），避免污染下次运行
    with test_engine.begin() as conn:
        for table in _TEAR_DOWN_TABLES:
            conn.execute(table.delete())
    test_engine.dispose()


@pytest.fixture(scope="module")
def test_app(test_db):
    test_session_factory, _ = test_db

    app = FastAPI()
    app.include_router(students.router)
    app.include_router(admin_rights.router)

    def _fake_current_user(authorization: str | None = Header(None)) -> str:
        # 测试用：Authorization: Bearer <user_id> 直接作为当前用户 ID（跳过 JWT 解码）
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="未登录")
        return authorization.replace("Bearer ", "").strip()

    def _fake_bind(user_id: str = Depends(get_current_user_id)):
        return user_id

    def _get_test_db():
        db = test_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_current_user_id] = _fake_current_user
    app.dependency_overrides[bind_grading_user_context] = _fake_bind
    app.dependency_overrides[get_db] = _get_test_db

    with TestClient(app) as client:
        yield client


@pytest.fixture()
def seed(test_app, test_db):
    """标准种子：A1 全局管理员 / H1 班主任(类属主) / D1 副班主任 / T1 协作教师。"""
    test_session_factory, _ = test_db
    with test_session_factory() as db:
        for model in (ExamScore, AssessmentResult, AssessmentSession, AssessmentDefinition,
                      StudentGrowthRecord, StudentPortfolio, EvaluationArchive,
                      Exam, IndicatorDefinition, Student, ClassTeacher, Class, User):
            db.query(model).delete()
        db.commit()

        a1 = User(id="A1", email="a1@test.local", password_hash="x", roles="系统管理员")
        h1 = User(id="H1", email="h1@test.local", password_hash="x", roles="班主任")
        d1 = User(id="D1", email="d1@test.local", password_hash="x", roles="协作教师")
        t1 = User(id="T1", email="t1@test.local", password_hash="x", roles="任课教师")
        db.add_all([a1, h1, d1, t1])
        db.flush()

        c1 = Class(id="C1", user_id="H1", school_level="小学", grade="五年级", name="五(1)班")
        db.add(c1)
        db.flush()

        db.add_all([
            ClassTeacher(id="CT1", class_id="C1", user_id="D1", role="deputy"),
            ClassTeacher(id="CT2", class_id="C1", user_id="T1", role="teacher"),
        ])
        db.flush()

        s1 = Student(
            id="S1", class_id="C1", user_id="H1", name="张三",
            student_number="23001189", gender="男", tier="B", status="正常",
            birthday="2015-01-01", phone="13800138000", parent_name="张小明",
            parent_phone="13900139000", address="广东省深圳市南山区科技园路1号",
        )
        db.add(s1)
        db.commit()
        return {"A1": "A1", "H1": "H1", "D1": "D1", "T1": "T1", "S1": s1.id}


def _auth(token: str):
    return {"Authorization": f"Bearer {token}"}


def _first_row(client, token: str):
    resp = client.get("/students", headers=_auth(token), params={"class_id": "C1"})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"][0]


# ── 1. GET /students：管理员/班主任 看完整 ────────────────


def test_global_admin_sees_full_pii(test_app, seed):
    row = _first_row(test_app, seed["A1"])
    assert row["student_number"] == "23001189"
    assert row["phone"] == "13800138000"
    assert row["parent_phone"] == "13900139000"
    assert row["parent_name"] == "张小明"
    assert row["address"] == "广东省深圳市南山区科技园路1号"
    assert row["birthday"] == "2015-01-01"


def test_head_sees_full_pii(test_app, seed):
    row = _first_row(test_app, seed["H1"])
    assert row["student_number"] == "23001189"
    assert row["phone"] == "13800138000"
    assert row["parent_phone"] == "13900139000"
    assert row["parent_name"] == "张小明"
    assert row["address"] == "广东省深圳市南山区科技园路1号"
    assert row["birthday"] == "2015-01-01"


# ── 2. GET /students：副班主任/协作教师 看掩码 ───────────


def test_deputy_sees_masked_pii(test_app, seed):
    row = _first_row(test_app, seed["D1"])
    assert row["student_number"] == "23****89"
    assert row["phone"] == "138****8000"
    assert "****" in row["phone"]
    assert row["parent_phone"] == "139****9000"
    assert row["parent_name"] == "张**"
    assert "**" in row["address"]
    assert row["address"] == "广东省深圳市南山区**"
    assert row["birthday"] is None
    # 非 PII 字段保持原样
    assert row["name"] == "张三"
    assert row["gender"] == "男"
    assert row["status"] == "正常"
    assert row["tier"] == "B"


def test_teacher_sees_masked_pii(test_app, seed):
    row = _first_row(test_app, seed["T1"])
    assert row["student_number"] == "23****89"
    assert "****" in row["phone"]
    assert "**" in row["address"]
    assert row["parent_name"] == "张**"
    assert row["birthday"] is None
    assert row["name"] == "张三"


# ── 3. POST /students 回显完整（仅 head）─────────────────


def test_post_echo_full_pii_for_head(test_app, seed):
    resp = test_app.post(
        "/students",
        headers=_auth(seed["H1"]),
        json={"class_id": "C1", "name": "李四", "student_number": "2024010123", "gender": "男"},
    )
    assert resp.status_code == 200, resp.text
    row = resp.json()["data"]
    assert row["name"] == "李四"
    assert row["student_number"] == "2024010123"  # 回显完整，不掩码


def test_deputy_cannot_create_student(test_app, seed):
    resp = test_app.post(
        "/students",
        headers=_auth(seed["D1"]),
        json={"class_id": "C1", "name": "王五", "student_number": "2024010124"},
    )
    assert resp.status_code == 403, resp.text


# ── 4. PATCH /students/{id} 回显完整（仅 head）────────────


def test_patch_echo_full_pii_for_head(test_app, seed):
    resp = test_app.patch(
        f"/students/{seed['S1']}",
        headers=_auth(seed["H1"]),
        json={"phone": "13711112222", "parent_name": "张新父"},
    )
    assert resp.status_code == 200, resp.text
    row = resp.json()["data"]
    assert row["phone"] == "13711112222"
    assert row["parent_name"] == "张新父"
    assert row["student_number"] == "23001189"  # 回显完整，不掩码


def test_teacher_cannot_update_student(test_app, seed):
    resp = test_app.patch(
        f"/students/{seed['S1']}",
        headers=_auth(seed["T1"]),
        json={"phone": "13711113333"},
    )
    assert resp.status_code == 403, resp.text


# ── 5. CSV 导出 /admin/rights/data/export ────────────────


def _csv_text(resp) -> list[list[str]]:
    import csv
    import io

    content = resp.content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(content)))


def _csv_info(rows: list[list[str]]) -> dict:
    return {r[1]: r[2] for r in rows if len(r) >= 3 and r[0] == "学生信息"}


def test_rights_export_admin_full_pii(test_app, seed):
    resp = test_app.get(
        "/admin/rights/data/export",
        headers=_auth(seed["A1"]),
        params={"student_id": seed["S1"]},
    )
    assert resp.status_code == 200, resp.text
    info = _csv_info(_csv_text(resp))
    assert info["学号"] == "23001189"
    assert info["生日"] == "2015-01-01"
    assert info["联系电话"] == "13800138000"
    assert info["家长姓名"] == "张小明"
    assert info["家长电话"] == "13900139000"
    assert info["家庭住址"] == "广东省深圳市南山区科技园路1号"


def test_rights_export_head_full_pii(test_app, seed):
    resp = test_app.get(
        "/admin/rights/data/export",
        headers=_auth(seed["H1"]),
        params={"student_id": seed["S1"]},
    )
    assert resp.status_code == 200, resp.text
    info = _csv_info(_csv_text(resp))
    assert info["姓名"] == "张三"
    assert info["学号"] == "23001189"
    assert info["生日"] == "2015-01-01"
    assert info["联系电话"] == "13800138000"
    assert info["家长姓名"] == "张小明"
    assert info["家长电话"] == "13900139000"
    assert info["家庭住址"] == "广东省深圳市南山区科技园路1号"
    assert info["状态"] == "正常"


def test_rights_export_deputy_masked_pii(test_app, seed):
    resp = test_app.get(
        "/admin/rights/data/export",
        headers=_auth(seed["D1"]),
        params={"student_id": seed["S1"]},
    )
    assert resp.status_code == 200, resp.text
    info = _csv_info(_csv_text(resp))
    assert info["姓名"] == "张三"  # 非 PII 保持原样
    assert info["学号"] == "23****89"
    assert info["生日"] == ""
    assert info["联系电话"] == "138****8000"
    assert info["家长姓名"] == "张**"
    assert info["家长电话"] == "139****9000"
    assert info["家庭住址"] == "广东省深圳市南山区**"


def test_rights_export_teacher_masked_pii(test_app, seed):
    resp = test_app.get(
        "/admin/rights/data/export",
        headers=_auth(seed["T1"]),
        params={"student_id": seed["S1"]},
    )
    assert resp.status_code == 200, resp.text
    info = _csv_info(_csv_text(resp))
    assert info["学号"] == "23****89"
    assert info["生日"] == ""
    assert info["联系电话"] == "138****8000"
    assert info["家长电话"] == "139****9000"
    assert info["家庭住址"] == "广东省深圳市南山区**"
