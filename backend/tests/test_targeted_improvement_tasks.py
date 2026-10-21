# -*- coding: utf-8 -*-
"""个性化学习任务清单（客户功能 #15）后端测试。

覆盖：
  1. plan_json → 任务行纯函数（phases.student_tasks / stages.dailyTasks / daily_routine）
  2. sync 幂等：同一 report 重复 sync 不重复建行
  3. PATCH 勾/取消：is_done / done_at
  4. 列表筛选：include_done=false 只回未完成
  5. 进度计数：total / done 不受 include_done 影响
  6. 权限：无班级访问 403

环境：内存 SQLite（monkeypatch engine/SessionLocal），不连真库。
"""
from __future__ import annotations

import os

os.environ.setdefault("AUTO_DDL", "false")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import app.database as database  # noqa: E402
from app.database import Base  # noqa: E402
from app.models.class_model import Class  # noqa: E402
from app.models.class_teacher import ClassTeacher  # noqa: E402
from app.models.student import Student  # noqa: E402
from app.models.targeted_improvement import (  # noqa: E402
    TargetedImprovementReport,
    TargetedImprovementTask,
)
from app.models.user import User  # noqa: E402
from app.routers.targeted_improvement import (  # noqa: E402
    TaskSyncRequest,
    TaskUpdateRequest,
    _extract_tasks_from_plan,
    list_improvement_tasks,
    sync_improvement_tasks,
    update_improvement_task,
)


# ── 纯函数：plan → 任务行 ─────────────────────────────────────────────


def test_extract_tasks_from_ai_phases_student_tasks():
    plan = {
        "phases": [
            {
                "title": "基础重建",
                "student_tasks": ["完成填空练习2题", "  观看微课  ", ""],
            },
            {
                "title": "应用提升",
                "student_tasks": ["完整综合题1套"],
            },
        ],
    }
    rows = _extract_tasks_from_plan(plan)
    assert [r["task_text"] for r in rows] == [
        "完成填空练习2题",
        "观看微课",
        "完整综合题1套",
    ]
    assert rows[0]["stage_label"] == "基础重建"
    assert rows[2]["stage_label"] == "应用提升"
    assert rows[0]["sort_order"] == 0 and rows[2]["sort_order"] == 2


def test_extract_tasks_from_demo_stages_daily_tasks():
    plan = {
        "stages": [
            {"name": "基础重建", "dailyTasks": ["观看微课《方法论》（15分钟）"]},
        ],
        "daily_routine": ["每日整理错题", "观看微课《方法论》（15分钟）"],
    }
    rows = _extract_tasks_from_plan(plan)
    texts = [r["task_text"] for r in rows]
    assert texts[0] == "观看微课《方法论》（15分钟）"
    assert "每日整理错题" in texts
    # daily_routine 与 stages 同文去重
    assert texts.count("观看微课《方法论》（15分钟）") == 1
    assert rows[-1]["stage_label"] == "日常"


def test_extract_tasks_empty_or_bad_plan():
    assert _extract_tasks_from_plan(None) == []
    assert _extract_tasks_from_plan({}) == []
    assert _extract_tasks_from_plan({"phases": "oops"}) == []


# ── SQLite 夹具 ───────────────────────────────────────────────────────


PLAN_JSON = """{
  "goal": "4周提升",
  "phases": [
    {"title": "基础重建", "student_tasks": ["任务A", "任务B"]},
    {"title": "巩固迁移", "student_tasks": ["任务C"]}
  ],
  "daily_routine": ["每日复习"]
}"""


@pytest.fixture()
def db_env(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(
        bind=engine,
        tables=[
            User.__table__,
            Class.__table__,
            ClassTeacher.__table__,
            Student.__table__,
            TargetedImprovementReport.__table__,
            TargetedImprovementTask.__table__,
        ],
    )
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", TestingSession)
    try:
        yield TestingSession
    finally:
        engine.dispose()


@pytest.fixture()
def seed(db_env):
    db = db_env()
    try:
        db.add(User(id="T1", email="t1@test.local", password_hash="x", roles="班主任"))
        db.add(Class(id="C1", user_id="T1", school_level="小学", grade="五年级", name="五(1)班"))
        db.add(Student(id="S1", class_id="C1", user_id="T1", name="甲", student_number="001"))
        db.add(
            TargetedImprovementReport(
                id="R1",
                class_id="C1",
                student_id="S1",
                student_name="甲",
                subject="数学",
                plan_json=PLAN_JSON,
            )
        )
        db.add(User(id="U1", email="u1@test.local", password_hash="x", roles="任课教师"))
        db.commit()
        return {"class_id": "C1", "student_id": "S1", "report_id": "R1"}
    finally:
        db.close()


def _session(db_env):
    return db_env()


# ── sync 幂等 ─────────────────────────────────────────────────────────


def test_sync_creates_tasks_from_plan(db_env, seed):
    db = _session(db_env)
    try:
        result = sync_improvement_tasks(
            TaskSyncRequest(report_id=seed["report_id"]),
            user_id="T1",
            db=db,
        )
        data = result.data
        assert data["created_count"] == 4  # 任务A/B/C + 每日复习
        assert data["total"] == 4
        assert data["done"] == 0
        texts = [t["task_text"] for t in data["tasks"]]
        assert "任务A" in texts and "每日复习" in texts
    finally:
        db.close()


def test_sync_is_idempotent(db_env, seed):
    db = _session(db_env)
    try:
        first = sync_improvement_tasks(
            TaskSyncRequest(report_id=seed["report_id"]), user_id="T1", db=db
        )
        second = sync_improvement_tasks(
            TaskSyncRequest(report_id=seed["report_id"]), user_id="T1", db=db
        )
        assert first.data["created_count"] == 4
        assert second.data["created_count"] == 0
        assert second.data["skipped_count"] == 4
        assert second.data["total"] == 4
    finally:
        db.close()


# ── PATCH 勾选 ────────────────────────────────────────────────────────


def test_patch_task_toggle_done_and_undone(db_env, seed):
    db = _session(db_env)
    try:
        synced = sync_improvement_tasks(
            TaskSyncRequest(report_id=seed["report_id"]), user_id="T1", db=db
        )
        task_id = synced.data["tasks"][0]["id"]
        done = update_improvement_task(
            task_id, TaskUpdateRequest(is_done=True), user_id="T1", db=db
        )
        assert done.data["is_done"] is True
        assert done.data["done_at"] is not None

        undone = update_improvement_task(
            task_id, TaskUpdateRequest(is_done=False), user_id="T1", db=db
        )
        assert undone.data["is_done"] is False
        assert undone.data["done_at"] is None
    finally:
        db.close()


def test_patch_missing_task_404(db_env, seed):
    db = _session(db_env)
    try:
        with pytest.raises(HTTPException) as exc:
            update_improvement_task(
                "no-such-id", TaskUpdateRequest(is_done=True), user_id="T1", db=db
            )
        assert exc.value.status_code == 404
    finally:
        db.close()


# ── 列表筛选 + 进度计数 ──────────────────────────────────────────────


def test_list_filter_and_progress_counts(db_env, seed):
    db = _session(db_env)
    try:
        synced = sync_improvement_tasks(
            TaskSyncRequest(report_id=seed["report_id"]), user_id="T1", db=db
        )
        for item in synced.data["tasks"][:2]:
            update_improvement_task(
                item["id"], TaskUpdateRequest(is_done=True), user_id="T1", db=db
            )

        all_res = list_improvement_tasks(
            class_id="C1", subject="数学", include_done=True, user_id="T1", db=db
        )
        assert all_res.data["total"] == 4
        assert all_res.data["done"] == 2
        assert len(all_res.data["tasks"]) == 4

        pending = list_improvement_tasks(
            class_id="C1", subject="数学", include_done=False, user_id="T1", db=db
        )
        assert len(pending.data["tasks"]) == 2
        assert all(not t["is_done"] for t in pending.data["tasks"])
        # 进度计数是全量口径，不受 include_done 影响
        assert pending.data["total"] == 4
        assert pending.data["done"] == 2
    finally:
        db.close()


def test_list_requires_class_access(db_env, seed):
    db = _session(db_env)
    try:
        with pytest.raises(HTTPException) as exc:
            list_improvement_tasks(
                class_id="C1", subject="数学", include_done=True, user_id="U1", db=db
            )
        assert exc.value.status_code == 403
    finally:
        db.close()
