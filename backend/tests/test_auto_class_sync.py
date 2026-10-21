"""批改完成后自动导入学情+自动分层（客户清单 #1）· 测试。

覆盖：
  1. 纯函数：班级文件夹解析 / 卷盒名 / 双历史合并 / 总分提取 / 平均分取整 / 阈值合并
  2. apply_auto_tiers：设置阈值生效、无成绩者保持原层并计数、返回实际阈值
  3. 阈值读写：显式覆盖 > 设置 > 默认；回写不拆散整份设置（不建遮蔽行）
  4. auto_sync_folder_after_grading 端到端（历史打桩）：
     成绩历史/当前分/错题/分层 一次跑齐，重复跑幂等；非班级文件夹/无分/无班级/无权限 跳过

环境：优先本地 Docker MySQL（127.0.0.1:13307, root/root_pw_2026，scratch 库 grade_auto_sync_test）；
没有 Docker MySQL 时自动退到内存 SQLite 跑同一条 ORM 链路（纯函数单测始终可跑）。
"""
import os

# 用专用 AUTOSYNC_* 覆盖变量 + 本地 Docker 默认值，避免拾取 shell 中遗留的生产 DB_* 环境变量。
_DB_HOST = os.environ.get("AUTOSYNC_DB_HOST", "127.0.0.1")
_DB_PORT = int(os.environ.get("AUTOSYNC_DB_PORT", "13307"))
_DB_USER = os.environ.get("AUTOSYNC_DB_USER", "root")
_DB_PWD = os.environ.get("AUTOSYNC_DB_PASSWORD", "root_pw_2026")
_TEST_DB = os.environ.get("AUTOSYNC_TEST_DB", "grade_auto_sync_test")

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

import json

import pytest

from app.database import Base, engine, SessionLocal
from app.models.user import User
from app.models.class_model import Class
from app.models.class_teacher import ClassTeacher
from app.models.student import Student
from app.models.exam import Exam
from app.models.exam_score import ExamScore
from app.models.student_analysis import StudentAnalysis, StudentScoreHistory, StudentWrongQuestion
from app.models.system_config import SystemConfig
from app.services import auto_class_sync as acs
from app.services import layered_push_service as svc

# ── 纯函数单测（不依赖 DB）──────────────────────────────


def test_parse_class_folder():
    assert acs.parse_class_folder("cls_1144d487-9e68-480f-adac-b19fbba65bb6__语文") == (
        "1144d487-9e68-480f-adac-b19fbba65bb6",
        "语文",
    )
    assert acs.parse_class_folder("cls_abc_def__期中考试") == ("abc_def", "期中考试")
    # 显示名里的 __ 归考试名（与前端 displayFolderName 同口径）
    assert acs.parse_class_folder("cls_C1__名__字") == ("C1", "名__字")
    assert acs.parse_class_folder("普通文件夹") is None
    assert acs.parse_class_folder("cls_abc") is None  # 无 __
    assert acs.parse_class_folder("cls_abc__") is None  # 考试名为空
    assert acs.parse_class_folder("cls___语文") is None  # class_id 为空
    assert acs.parse_class_folder("") is None


def test_paper_box_display_name():
    assert acs.paper_box_display_name("张三_1.jpg") == "张三"
    assert acs.paper_box_display_name("张三_2.png") == "张三"
    assert acs.paper_box_display_name("李四_1_2.jpg") == "李四_1"  # 贪婪：只去最后一页号
    assert acs.paper_box_display_name("王五.jpg") == "王五"
    assert acs.paper_box_display_name("王五") == "王五"
    assert acs.paper_box_display_name("") == ""


def test_merge_completed_manual_overrides_same_filename():
    default_completed = {"张三_1.jpg": {"score_total": 40}, "张三_2.jpg": {"score_total": 60}}
    manual_completed = {"张三_1.jpg": {"score_total": 35}}
    merged = acs.merge_completed(default_completed, manual_completed)
    assert merged["张三_1.jpg"]["score_total"] == 35  # 同名文件人工覆盖
    assert merged["张三_2.jpg"]["score_total"] == 60  # 智能独有页保留


def test_extract_scores_from_completed():
    completed = {
        "张三_1.jpg": {"score_total": 40},
        "张三_2.jpg": {"score_total": 60},  # 同卷多页求和
        "李四_1.jpg": {"score_total": None},  # 无分跳过
        "王五_1.jpg": {"score_total": "abc"},  # 坏值跳过
        "赵六.jpg": {"score_total": 88},  # 单文件无页号
        "孙七_1.jpg": "not-a-dict",  # 非 dict 跳过
    }
    scores = acs.extract_scores_from_completed(completed)
    assert scores == {"张三": 100.0, "赵六": 88.0}
    assert acs.extract_scores_from_completed({}) == {}


def test_class_average_rounds_like_js():
    # 与 ImportScoresDialog Math.round 一致：.5 向上（Python round 是银行家舍入，不能用）
    assert acs.class_average({"张三": 100.0, "李四": 55.0}) == 78  # 77.5 → 78
    assert acs.class_average({"张三": 100.0, "李四": 54.0}) == 77  # 77.0 → 77
    assert acs.class_average({"张三": 0.0}) == 0
    assert acs.class_average({}) is None


def test_merge_thresholds():
    assert acs.__dict__ is not None  # 模块加载健全
    # 默认
    assert svc.merge_thresholds(None, None) == {"a": 80.0, "b": 60.0}
    # 设置生效
    assert svc.merge_thresholds({"a": 90, "b": 50}, None) == {"a": 90.0, "b": 50.0}
    # 显式覆盖压过设置
    assert svc.merge_thresholds({"a": 90, "b": 50}, {"a": 85}) == {"a": 85.0, "b": 50.0}
    # 设置里的坏值忽略，回退默认；无关键忽略
    assert svc.merge_thresholds({"a": "x", "z": 1}, None) == {"a": 80.0, "b": 60.0}
    # 显式覆盖的坏值报错（端点 400 语义）
    with pytest.raises(ValueError):
        svc.merge_thresholds(None, {"a": "x"})
    with pytest.raises(ValueError):
        svc.merge_thresholds(None, "not-a-dict")


# ── DB 用例（Docker MySQL）──────────────────────────────

_AUTO_SYNC_TABLES = [
    User.__table__,
    Class.__table__,
    ClassTeacher.__table__,
    Student.__table__,
    Exam.__table__,
    ExamScore.__table__,
    StudentAnalysis.__table__,
    StudentScoreHistory.__table__,
    StudentWrongQuestion.__table__,
    SystemConfig.__table__,
]


# DB 用例的会话工厂：优先 Docker MySQL scratch 库；没有则内存 SQLite（ORM 链路照跑）。
_session_factory = None
_app_db_module = None
_orig_session_local = None


@pytest.fixture(scope="module")
def db_ready():
    global _session_factory, _app_db_module, _orig_session_local
    if _MYSQL_AVAILABLE:
        Base.metadata.create_all(bind=engine, tables=_AUTO_SYNC_TABLES)
        _session_factory = SessionLocal
    else:
        from sqlalchemy import create_engine as _create_engine
        from sqlalchemy.orm import sessionmaker as _sessionmaker
        from sqlalchemy.pool import StaticPool

        import app.database as app_db

        sqlite_engine = _create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=sqlite_engine, tables=_AUTO_SYNC_TABLES)
        _session_factory = _sessionmaker(bind=sqlite_engine, autoflush=False, autocommit=False)
        # auto_sync_folder_after_grading 函数内懒加载 SessionLocal —— 换成 SQLite 工厂
        _app_db_module = app_db
        _orig_session_local = app_db.SessionLocal
        app_db.SessionLocal = _session_factory
    yield
    if _MYSQL_AVAILABLE:
        with engine.begin() as conn:
            for table in reversed(_AUTO_SYNC_TABLES):
                conn.execute(table.delete())
    elif _app_db_module is not None:
        _app_db_module.SessionLocal = _orig_session_local


@pytest.fixture()
def seed(db_ready):
    """T1 班主任 / C1 班 / 张三(无层) 李四(A) 王五(C)；分层阈值 a:90 b:50 存在学科设置行。"""
    with _session_factory() as db:
        for model in (
            StudentWrongQuestion,
            StudentScoreHistory,
            StudentAnalysis,
            SystemConfig,
            ExamScore,
            Exam,
            Student,
            ClassTeacher,
            Class,
            User,
        ):
            db.query(model).delete()
        db.commit()

        db.add(User(id="T1", email="t1@test.local", password_hash="x", roles="班主任"))
        db.add(User(id="U1", email="u1@test.local", password_hash="x", roles="任课教师"))
        db.flush()
        db.add(Class(id="C1", user_id="T1", school_level="小学", grade="五年级", name="五(1)班"))
        db.flush()
        db.add(Student(id="S1", class_id="C1", user_id="T1", name="张三", student_number="001", tier=None))
        db.add(Student(id="S2", class_id="C1", user_id="T1", name="李四", student_number="002", tier="A"))
        db.add(Student(id="S3", class_id="C1", user_id="T1", name="王五", student_number="003", tier="C"))
        db.add(
            SystemConfig(
                key="layered_push:C1:语文",
                value={"thresholds": {"a": 90, "b": 50}, "tiers": {"A": {"require_parent_sign": True}}},
                label="分层推送设置",
                category="layered_push",
                updated_by="T1",
            )
        )
        db.add(
            SystemConfig(
                key="layered_push:C1",
                value={"thresholds": {"a": 88, "b": 44}},
                label="分层推送设置",
                category="layered_push",
                updated_by="T1",
            )
        )
        db.commit()
        return {"T1": "T1", "U1": "U1", "C1": "C1"}


def test_apply_auto_tiers_uses_settings_thresholds(seed):
    with _session_factory() as db:
        db.add(StudentAnalysis(class_id="C1", student_name="张三", subject="语文", current_score=95))
        db.add(StudentAnalysis(class_id="C1", student_name="李四", subject="语文", current_score=55))
        db.commit()

        result = svc.apply_auto_tiers(db, "C1", "语文")

        assert result["thresholds"] == {"a": 90.0, "b": 50.0}  # 学科设置行生效（非默认 80/60）
        assert result["no_score"] == 1  # 王五无成绩
        assert result["updated"] == 2  # 张三 None→A；李四 A→B（55<90）
        by_name = {s.name: s.tier for s in db.query(Student).filter(Student.class_id == "C1").all()}
        assert by_name == {"张三": "A", "李四": "B", "王五": "C"}  # 王五保持原层

        # 显式覆盖阈值压过设置：55 < 60 → 李四掉 C
        result2 = svc.apply_auto_tiers(db, "C1", "语文", {"a": 80, "b": 60})
        assert result2["thresholds"] == {"a": 80.0, "b": 60.0}
        by_name = {s.name: s.tier for s in db.query(Student).filter(Student.class_id == "C1").all()}
        assert by_name == {"张三": "A", "李四": "C", "王五": "C"}


def test_thresholds_read_write_precedence(seed):
    with _session_factory() as db:
        # 读：学科行 > 班级行
        assert svc.resolve_thresholds(db, "C1", "语文") == {"a": 90.0, "b": 50.0}
        # 无学科行的学科 → 落到班级行
        assert svc.resolve_thresholds(db, "C1", "数学") == {"a": 88.0, "b": 44.0}
        # 显式覆盖 > 设置
        assert svc.resolve_thresholds(db, "C1", "语文", {"a": 70}) == {"a": 70.0, "b": 50.0}

        # 回写进 load_settings 命中的那行：不拆散整份设置、不建遮蔽行
        svc.update_stored_thresholds(db, "C1", "语文", {"a": 70.0, "b": 40.0}, "T1")
        row = db.query(SystemConfig).filter(SystemConfig.key == "layered_push:C1:语文").first()
        assert row.value["thresholds"] == {"a": 70.0, "b": 40.0}
        assert row.value["tiers"] == {"A": {"require_parent_sign": True}}  # 原有设置保留

        # 无学科行的学科：写进班级行，不新建 layered_push:C1:数学
        svc.update_stored_thresholds(db, "C1", "数学", {"a": 66.0, "b": 33.0}, "T1")
        keys = [r.key for r in db.query(SystemConfig).all()]
        assert "layered_push:C1:数学" not in keys
        row = db.query(SystemConfig).filter(SystemConfig.key == "layered_push:C1").first()
        assert row.value["thresholds"] == {"a": 66.0, "b": 33.0}

        # 无任何设置行：建行 + 默认阈值可读
        svc.update_stored_thresholds(db, "C2", "英语", {"a": 99.0, "b": 11.0}, "T1")
        assert svc.resolve_thresholds(db, "C2", "英语") == {"a": 99.0, "b": 11.0}


def _patch_histories(monkeypatch, completed, default_completed=None, manual_completed=None, essay_completed=None):
    """打桩批改历史读取：auto 同步的 load_folder_completed 与 import_scores_core 的错题提取。"""
    monkeypatch.setattr(acs, "load_folder_completed", lambda safe: acs.merge_completed(completed, {}))
    monkeypatch.setattr(acs, "load_folder_essay_completed", lambda safe: dict(essay_completed or {}))
    monkeypatch.setattr(acs, "read_folder_meta", lambda safe: {"subject": "语文", "class_id": "C1"})

    def fake_read(safe, engine):
        if engine == "manual":
            return {"completed": dict(manual_completed or {})}
        return {"completed": dict(default_completed or {})}

    import app.routers.student_analysis as sa

    monkeypatch.setattr(sa, "_read_grading_history", fake_read)


def test_auto_sync_end_to_end(seed, monkeypatch):
    completed = {
        "张三_1.jpg": {"score_total": 40},
        "张三_2.jpg": {"score_total": 60},
        "李四_1.jpg": {"score_total": 55, "result": json.dumps({"scores": {"第1题": 0, "第2题": 10}})},
        "王五_1.jpg": {"score_total": None},
    }
    _patch_histories(
        monkeypatch,
        completed,
        manual_completed={"李四_1.jpg": completed["李四_1.jpg"]},
    )

    summary = acs.auto_sync_folder_after_grading("T1", "cls_C1__月考")
    assert summary.get("skipped") is None, summary
    assert summary["class_id"] == "C1"
    assert summary["exam_name"] == "月考"
    assert summary["subject"] == "语文"
    assert summary["students"] == 2
    assert summary["class_avg"] == 78
    assert summary["imported_count"] == 2

    with _session_factory() as db:
        rows = (
            db.query(StudentScoreHistory)
            .filter(StudentScoreHistory.class_id == "C1", StudentScoreHistory.exam_name == "月考")
            .all()
        )
        by_name = {r.student_name: r for r in rows}
        assert set(by_name) == {"张三", "李四"}  # 王五无分不导入
        assert by_name["张三"].score == 100  # 双页求和
        assert by_name["李四"].score == 55
        assert by_name["张三"].class_avg == 78
        assert by_name["张三"].subject == "语文"

        current = {
            r.student_name: r.current_score
            for r in db.query(StudentAnalysis).filter(StudentAnalysis.class_id == "C1").all()
        }
        assert current == {"张三": 100, "李四": 55}

        wq = (
            db.query(StudentWrongQuestion)
            .filter(StudentWrongQuestion.class_id == "C1", StudentWrongQuestion.exam_name == "月考")
            .all()
        )
        assert [(w.student_name, w.question_title) for w in wq] == [("李四", "第1题")]  # score==0 才算错题

        tiers = {s.name: s.tier for s in db.query(Student).filter(Student.class_id == "C1").all()}
        # 阈值 a:90 b:50：张三 100→A；李四 55→B；王五无成绩保持 C
        assert tiers == {"张三": "A", "李四": "B", "王五": "C"}

    # 幂等：重复跑不产生重复行
    summary2 = acs.auto_sync_folder_after_grading("T1", "cls_C1__月考")
    assert summary2.get("skipped") is None
    with _session_factory() as db:
        n = (
            db.query(StudentScoreHistory)
            .filter(StudentScoreHistory.class_id == "C1", StudentScoreHistory.exam_name == "月考")
            .count()
        )
        assert n == 2
        n_wq = (
            db.query(StudentWrongQuestion)
            .filter(StudentWrongQuestion.class_id == "C1", StudentWrongQuestion.exam_name == "月考")
            .count()
        )
        assert n_wq == 1


def test_auto_sync_essay_whole_paper_scores(seed, monkeypatch):
    """作文通道：多页重复同一整卷总分 → 学情导入取最大不乘页数；智能照旧逐页累加。"""
    completed = {"张三_1.jpg": {"score_total": 40}, "张三_2.jpg": {"score_total": 60}}
    essay = {"李四_1.jpg": {"score_total": 82}, "李四_2.jpg": {"score_total": 82}}
    _patch_histories(monkeypatch, completed, essay_completed=essay)

    summary = acs.auto_sync_folder_after_grading("T1", "cls_C1__月考")
    assert summary.get("skipped") is None, summary
    assert summary["students"] == 2

    with _session_factory() as db:
        rows = {
            r.student_name: float(r.score)
            for r in db.query(StudentScoreHistory)
            .filter(StudentScoreHistory.class_id == "C1", StudentScoreHistory.exam_name == "月考")
            .all()
        }
        assert rows == {"张三": 100.0, "李四": 82.0}  # 李四两页作文 82+82 不求和


def test_auto_sync_skips(seed, monkeypatch):
    # 非班级文件夹
    assert acs.auto_sync_folder_after_grading("T1", "普通文件夹")["skipped"] == "not_class_folder"
    # 无带分结果：空成绩绝不进 _sync_exam_scores（防止清掉已有成绩）
    monkeypatch.setattr(acs, "load_folder_completed", lambda safe: {"张三_1.jpg": {"score_total": None}})
    monkeypatch.setattr(acs, "load_folder_essay_completed", lambda safe: {})
    monkeypatch.setattr(acs, "read_folder_meta", lambda safe: {"subject": "语文"})
    assert acs.auto_sync_folder_after_grading("T1", "cls_C1__月考")["skipped"] == "no_scores"
    # 班级不存在
    monkeypatch.setattr(
        acs, "load_folder_completed", lambda safe: {"张三_1.jpg": {"score_total": 90}}
    )
    assert acs.auto_sync_folder_after_grading("T1", "cls_NOPE__月考")["skipped"] == "class_not_found"
    # 无班级权限
    assert acs.auto_sync_folder_after_grading("U1", "cls_C1__月考")["skipped"] == "no_permission"
    # 上述跳过不应写入任何成绩
    with _session_factory() as db:
        assert db.query(StudentScoreHistory).count() == 0
