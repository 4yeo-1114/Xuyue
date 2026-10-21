# -*- coding: utf-8 -*-
"""轻成绩表（grading_score_summaries，对齐批改君 exam_scores）。

钉住四件事：
1. 总分口径与 extract_scores_from_completed / 前端 box_totals 一致
   （智能多页求和、作文取最大且整箱权威、同名文件人工覆盖）；
2. 未统分条目不落行；满分/逐题分跨页合并、引擎归属（default 戳/manual/essay）；
3. delete-then-insert 整文件夹重建：人少了旧行必须消失（重批自愈）；
4. 班级文件夹按姓名 best-effort 匹配 students（匹配不上 student_id 留空保成绩）。
"""
from __future__ import annotations

import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.database as database
from app.grading import score_summary_db


def _item(score=None, question_scores=None, max_score_total=None, engine=None, blocks=None):
    info = {"name": "x", "result": ""}
    if score is not None:
        info["score_total"] = score
    if question_scores is not None:
        info["question_scores"] = question_scores
    if max_score_total is not None:
        info["result"] = json.dumps({"max_score_total": max_score_total}, ensure_ascii=False)
    if engine is not None:
        info["engine"] = engine
    if blocks is not None:
        info["blocks"] = blocks
    return info


def _fake_histories(monkeypatch, default=None, manual=None, essay=None, meta=None):
    import app.grading.router as grading_router
    import app.services.auto_class_sync as acs

    monkeypatch.setattr(
        grading_router, "_read_grading_history",
        lambda safe, engine="default": (default if engine != "manual" else manual) or {},
    )
    monkeypatch.setattr(grading_router, "_read_essay_history", lambda safe: essay or {})
    monkeypatch.setattr(acs, "read_folder_meta", lambda safe: meta or {})


# ── 1. 聚合口径 ──────────────────────────────────────────────


def test_multi_page_sum_and_unscored_skip(monkeypatch):
    _fake_histories(
        monkeypatch,
        default={
            "engine": "aliyun",
            "completed": {
                "甲_1.jpg": _item(6, {"第1题": 6}, max_score_total=10),
                "甲_2.jpg": _item(4, {"第2题": 4}, max_score_total=10),
                "丁_1.jpg": _item(),  # 未统分：不落行
            },
        },
    )
    rows = score_summary_db.build_folder_summary_rows("普通文件夹")
    assert len(rows) == 1
    row = rows[0]
    assert row["student_name"] == "甲"
    assert row["score_total"] == 10.0
    assert row["max_score"] == 20.0  # 两页满分求和
    assert row["question_scores"] == {"第1题": 6, "第2题": 4}
    assert row["engine"] == "aliyun"  # 条目无 engine → 默认历史的引擎戳
    assert row["class_id"] is None
    assert row["exam_name"] == "普通文件夹"


def test_essay_total_is_authoritative_and_multi_page_takes_max(monkeypatch):
    _fake_histories(
        monkeypatch,
        default={"completed": {"乙_1.jpg": _item(6), "丙_1.jpg": _item(1)}},
        essay={
            "completed": {
                "乙_1.jpg": _item(25),        # 与普通通道同箱 → 整箱权威
                "丙_1.jpg": _item(20),
                "丙_2.jpg": _item(23),        # 作文多页 → 取最大
            }
        },
    )
    rows = {r["student_name"]: r for r in score_summary_db.build_folder_summary_rows("f")}
    assert rows["乙"]["score_total"] == 25.0
    assert rows["乙"]["engine"] == "essay"
    assert rows["丙"]["score_total"] == 23.0
    assert rows["丙"]["engine"] == "essay"


def test_manual_overrides_default_same_filename(monkeypatch):
    _fake_histories(
        monkeypatch,
        default={"completed": {"甲_1.jpg": _item(6)}},
        manual={"completed": {"甲_1.jpg": _item(5, engine=None)}},
    )
    rows = score_summary_db.build_folder_summary_rows("f")
    assert rows[0]["score_total"] == 5.0
    assert rows[0]["engine"] == "manual"  # 来自 manual 历史文件


def test_class_folder_parses_class_and_exam(monkeypatch):
    _fake_histories(
        monkeypatch,
        default={"completed": {"张三_1.jpg": _item(9)}},
        meta={"subject": "数学"},
    )
    rows = score_summary_db.build_folder_summary_rows("cls_c1__期中考试")
    assert rows[0]["class_id"] == "c1"
    assert rows[0]["exam_name"] == "期中考试"
    assert rows[0]["subject"] == "数学"


def test_result_json_score_total_fallback(monkeypatch):
    # 条目级没有 score_total，但结果 JSON 里有（与 router._item_score_total 同口径）
    info = {"name": "甲_1.jpg", "result": json.dumps({"score_total": 8.5}, ensure_ascii=False)}
    _fake_histories(monkeypatch, default={"completed": {"甲_1.jpg": info}})
    rows = score_summary_db.build_folder_summary_rows("f")
    assert rows[0]["score_total"] == 8.5


# ── 2. 落库重建（sqlite）────────────────────────────────────────


def _sqlite(monkeypatch, tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'gss.db'}")
    from app.models.grading_score_summary import GradingScoreSummary
    from app.models.student import Student

    GradingScoreSummary.__table__.create(bind=eng)
    Student.__table__.create(bind=eng)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=eng))
    return eng


def _seed_student(eng, class_id: str, name: str):
    from app.models.student import Student

    db = sessionmaker(bind=eng)()
    db.add(
        Student(
            id=f"stu-{name}",
            class_id=class_id,
            user_id="u1",
            name=name,
            student_number="1",
        )
    )
    db.commit()
    db.close()


def test_sync_rebuilds_rows_and_matches_students(monkeypatch, tmp_path):
    eng = _sqlite(monkeypatch, tmp_path)
    _seed_student(eng, "c1", "张三")
    _fake_histories(
        monkeypatch,
        default={"completed": {"张三_1.jpg": _item(9), "李四_1.jpg": _item(7)}},
        meta={"subject": "语文"},
    )
    out = score_summary_db.sync_folder_score_summaries("u1", "cls_c1__期末")
    assert out["rows"] == 2

    rows = {r["student_name"]: r for r in score_summary_db.get_folder_score_summaries("u1", "cls_c1__期末")}
    assert rows["张三"]["student_id"] == "stu-张三"  # 按名命中
    assert rows["李四"]["student_id"] is None         # 匹配不上留空保成绩
    assert rows["李四"]["score_total"] == 7.0
    assert rows["李四"]["subject"] == "语文"

    # 重批后只剩一人：旧的第二行必须消失（delete-then-insert，不残留）
    _fake_histories(
        monkeypatch,
        default={"completed": {"张三_1.jpg": _item(5)}},
        meta={"subject": "语文"},
    )
    score_summary_db.sync_folder_score_summaries("u1", "cls_c1__期末")
    rows2 = score_summary_db.get_folder_score_summaries("u1", "cls_c1__期末")
    assert [r["student_name"] for r in rows2] == ["张三"]
    assert rows2[0]["score_total"] == 5.0

    # 别的用户看不到
    assert score_summary_db.get_folder_score_summaries("u2", "cls_c1__期末") == []


def test_sync_with_empty_history_clears_rows(monkeypatch, tmp_path):
    _sqlite(monkeypatch, tmp_path)
    _fake_histories(monkeypatch, default={"completed": {"甲_1.jpg": _item(3)}})
    score_summary_db.sync_folder_score_summaries("u1", "f")
    assert len(score_summary_db.get_folder_score_summaries("u1", "f")) == 1
    _fake_histories(monkeypatch, default={"completed": {}})
    out = score_summary_db.sync_folder_score_summaries("u1", "f")
    assert out["rows"] == 0
    assert score_summary_db.get_folder_score_summaries("u1", "f") == []
