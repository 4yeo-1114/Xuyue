# -*- coding: utf-8 -*-
"""print_jobs 落库留痕（2026-10-23）触碰面测试。

内存队列 → 表：行↔dataclass 往返 / PATCH 改题重建 PDF / done 重打（reprint）/
printing 不可改不可删。SQLite monkeypatch 范本：tests/test_correction_ledger.py。
"""
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.print_job import PrintJobRow, PrintUploadRow
from app.routers import print_jobs as pj


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    PrintJobRow.__table__.create(bind=engine)
    PrintUploadRow.__table__.create(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    # PDF 重建不走真实排版（另有 worksheet_pdf 自己的测试），只数调用
    monkeypatch.setattr(
        pj, "_build_pdf", lambda payload, uploads: b"%PDF-fake-" + str(len(payload.get("questions") or payload.get("question_items") or [])).encode()
    )
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_job(**over):
    now = 1761000000.0
    job = pj.PrintJob(
        id="pj_test00000001",
        status="draft",
        title="七年级数学作业",
        subject="math",
        grade="junior1",
        class_name="3班",
        teacher="王老师",
        question_count=2,
        copies=1,
        created_by="u1",
        created_at=now,
        pdf=b"%PDF-fake",
        source="text",
        page_size="a4",
        layout="auto",
        payload={
            "questions": ["1+1=?", "2+2=?"],
            "question_count": 2,
            "answer_lines": 2,
            "note": "请认真作答",
            "title": "七年级数学作业",
            "subject": "math",
            "grade": "junior1",
            "class_name": "3班",
            "teacher": "王老师",
        },
        updated_at=now,
    )
    for k, v in over.items():
        setattr(job, k, v)
    return job


# ── 行 ↔ dataclass 往返 ──────────────────────────────────────────────────


def test_row_roundtrip_keeps_payload_and_pdf(db):
    job = _make_job()
    pj._save_job(db, job)

    loaded = pj._load_job(db, job.id)
    assert loaded is not None
    assert loaded.title == "七年级数学作业"
    assert loaded.payload["questions"] == ["1+1=?", "2+2=?"]
    assert loaded.pdf == b"%PDF-fake"
    assert loaded.status == "draft"


def test_to_full_exposes_edit_fields(db):
    job = _make_job()
    full = job.to_full()
    assert full["questions"] == ["1+1=?", "2+2=?"]
    assert full["note"] == "请认真作答"
    assert full["answer_lines"] == 2
    assert "question_items" in full and "uploads" in full
    assert full["job_id"] == job.id


# ── PATCH ────────────────────────────────────────────────────────────────


def test_patch_meta_only_does_not_rebuild_pdf(db):
    job = _make_job()
    pj._save_job(db, job)
    before_pdf = job.pdf

    res = pj.update_print_job(
        job.id,
        pj.UpdatePrintJobRequest(title="改了标题"),
        user_id="u1",
        db=db,
    )
    assert res["title"] == "改了标题"
    loaded = pj._load_job(db, job.id)
    assert loaded.pdf == before_pdf  # 没动出卷内容就不重建
    assert loaded.payload["title"] == "改了标题"  # 卷头参数同步进 payload


def test_patch_questions_rebuilds_pdf_and_recounts(db):
    job = _make_job()
    pj._save_job(db, job)

    res = pj.update_print_job(
        job.id,
        pj.UpdatePrintJobRequest(questions=["3+3=?", "4+4=?", "5+5=?"]),
        user_id="u1",
        db=db,
    )
    assert res["questions"] == ["3+3=?", "4+4=?", "5+5=?"]
    loaded = pj._load_job(db, job.id)
    assert loaded.question_count == 3
    assert loaded.pdf == b"%PDF-fake-3"  # _build_pdf 已按新题重建


def test_patch_printing_rejected(db):
    job = _make_job(status="printing")
    pj._save_job(db, job)
    with pytest.raises(Exception) as ei:
        pj.update_print_job(
            job.id,
            pj.UpdatePrintJobRequest(title="x"),
            user_id="u1",
            db=db,
        )
    assert "409" in str(ei.value) or "正在打印" in str(ei.value)


def test_patch_other_user_404(db):
    job = _make_job()
    pj._save_job(db, job)
    with pytest.raises(Exception) as ei:
        pj.update_print_job(
            job.id,
            pj.UpdatePrintJobRequest(title="x"),
            user_id="u2",
            db=db,
        )
    assert "404" in str(ei.value) or "不存在" in str(ei.value)


# ── 打印 / 重打 ──────────────────────────────────────────────────────────


def test_done_reprint_requires_flag(db):
    job = _make_job(status="done")
    pj._save_job(db, job)
    with pytest.raises(Exception) as ei:
        pj.enqueue_print_job(job.id, None, user_id="u1", db=db)
    assert "409" in str(ei.value) or "已经打印过" in str(ei.value)

    res = pj.enqueue_print_job(
        job.id,
        pj.PrintNowRequest(reprint=True),
        user_id="u1",
        db=db,
    )
    assert res["status"] == "pending"


def test_printing_enqueue_rejected(db):
    job = _make_job(status="printing")
    pj._save_job(db, job)
    with pytest.raises(Exception) as ei:
        pj.enqueue_print_job(job.id, None, user_id="u1", db=db)
    assert "409" in str(ei.value) or "正在打印" in str(ei.value)


def test_enqueue_sets_pending_and_resets_attempts(db):
    job = _make_job(status="failed", attempts=3, error="打印机脱机")
    pj._save_job(db, job)
    res = pj.enqueue_print_job(job.id, None, user_id="u1", db=db)
    assert res["status"] == "pending"
    loaded = pj._load_job(db, job.id)
    assert loaded.attempts == 0
    assert loaded.error is None


# ── 删除 ─────────────────────────────────────────────────────────────────


def test_delete_done_ok_printing_rejected(db):
    job = _make_job(status="done")
    pj._save_job(db, job)
    res = pj.cancel_print_job(job.id, user_id="u1", db=db)
    assert res["ok"] is True
    assert pj._load_job(db, job.id) is None

    job2 = _make_job(id="pj_test00000002", status="printing")
    pj._save_job(db, job2)
    with pytest.raises(Exception) as ei:
        pj.cancel_print_job(job2.id, user_id="u1", db=db)
    assert "409" in str(ei.value) or "正在打印" in str(ei.value)


# ── 列表归属隔离 ─────────────────────────────────────────────────────────


def test_list_only_own_jobs(db):
    pj._save_job(db, _make_job(id="pj_mine00000001", created_by="u1"))
    pj._save_job(db, _make_job(id="pj_other000001", created_by="u2"))
    res = pj.list_print_jobs(limit=20, user_id="u1", db=db)
    ids = [j["job_id"] for j in res["jobs"]]
    assert ids == ["pj_mine00000001"]


# ── 建表幂等（init_db 无条件段调用的函数）─────────────────────────────────


def test_ensure_print_jobs_tables_idempotent(monkeypatch):
    from app import database

    engine = create_engine("sqlite:///:memory:")
    monkeypatch.setattr(database, "engine", engine)
    database._ensure_print_jobs_tables()
    database._ensure_print_jobs_tables()  # 幂等再跑一遍不炸
    assert "print_jobs" in engine.table_names() if hasattr(engine, "table_names") else True
    from sqlalchemy import inspect

    insp = inspect(engine)
    assert "print_jobs" in insp.get_table_names()
    assert "print_uploads" in insp.get_table_names()
    engine.dispose()
