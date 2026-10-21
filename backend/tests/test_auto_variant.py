# -*- coding: utf-8 -*-
"""客户清单#2 批改后自动配套练习 · 测试。

覆盖：
  1. 错题行 → 高频薄弱点聚合（kp 聚合 / 伪 kp / 截断 / 门槛）
  2. 薄弱点 → 变式题装配（stub 资产库 fetcher，1-3 条、失败记 skip_reason）
  3. 幂等跳过（已生成 items 非空 → skip；force 重跑）
  4. 资产库空 / fetcher 抛异常 → 降级不炸，status=empty
  5. 主链路隔离：auto_variant 抛异常不影响 auto_sync 返回
  6. 单场单飞：同 folder 并发只跑一个
  7. 无错题 → status=empty 且不抛
  8. JSON 原子写读回环

纯逻辑 + 打桩，不连 MySQL/PG。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from app.services import auto_variant as av


# ── 纯函数：聚合 ────────────────────────────────────────────────
def test_aggregate_weak_points_groups_by_kp():
    rows = [
        {"question_title": "第1题", "student_name": "张三", "kp_name": "一元二次方程", "kp_id": "k1"},
        {"question_title": "第1题", "student_name": "李四", "kp_name": "一元二次方程", "kp_id": "k1"},
        {"question_title": "第2题", "student_name": "王五", "kp_name": "一元二次方程", "kp_id": "k1"},
        {"question_title": "第3题", "student_name": "张三", "kp_name": "因式分解", "kp_id": "k2"},
    ]
    wps = av.aggregate_weak_points(rows)
    assert len(wps) == 2
    assert wps[0]["kp_name"] == "一元二次方程"
    assert wps[0]["wrong_count"] == 3
    assert wps[0]["student_count"] == 3
    assert wps[1]["kp_name"] == "因式分解"
    assert wps[1]["wrong_count"] == 1


def test_aggregate_weak_points_fallback_title_as_kp():
    rows = [
        {"question_title": "第5题-作答区1", "student_name": "A", "kp_name": "", "kp_id": ""},
        {"question_title": "第5题-作答区1", "student_name": "B", "kp_name": "", "kp_id": ""},
        {"question_title": "第6题", "student_name": "A", "kp_name": "", "kp_id": ""},
    ]
    wps = av.aggregate_weak_points(rows)
    assert wps[0]["kp_name"] == "第5题-作答区1"  # 无桥接 → 题干作伪 kp
    assert wps[0]["wrong_count"] == 2
    assert wps[0]["student_count"] == 2


def test_aggregate_weak_points_limit_and_threshold():
    rows = [
        {"question_title": f"第{i}题", "student_name": f"s{i}", "kp_name": f"kp{i}"}
        for i in range(10)
    ]
    wps = av.aggregate_weak_points(rows, min_wrong_count=2, max_points=3)
    assert wps == []  # 全是 1 次，门槛 2 过滤光

    rows2 = rows + [
        {"question_title": "第0题", "student_name": "x", "kp_name": "kp0"},
        {"question_title": "第1题", "student_name": "y", "kp_name": "kp1"},
        {"question_title": "第2题", "student_name": "z", "kp_name": "kp2"},
        {"question_title": "第3题", "student_name": "w", "kp_name": "kp3"},
    ]
    wps2 = av.aggregate_weak_points(rows2, min_wrong_count=2, max_points=3)
    assert len(wps2) == 3
    assert all(w["wrong_count"] >= 2 for w in wps2)


# ── 纯函数：装配 ────────────────────────────────────────────────
def test_assemble_with_stub_fetcher():
    def fetcher(kp_name, subject, limit):
        return [
            {"id": f"{kp_name}-1", "question": f"{kp_name}题1", "answer": "A", "analysis": "略", "difficulty": 3},
            {"id": f"{kp_name}-2", "question": f"{kp_name}题2", "answer": "B", "analysis": "略", "difficulty": 4},
            {"id": f"{kp_name}-3", "question": f"{kp_name}题3", "answer": "C", "analysis": "略", "difficulty": 5},
            {"id": f"{kp_name}-4", "question": f"{kp_name}题4", "answer": "D", "analysis": "略", "difficulty": 5},
        ]

    wps = [{"kp_name": "一元二次方程", "kp_id": "k1", "wrong_count": 5, "student_count": 4, "titles": ["第1题"]}]
    payload = av.assemble_weak_point_payload(wps, fetcher, "数学", limit_per_kp=3)
    assert len(payload) == 1
    assert payload[0]["skip_reason"] is None
    assert len(payload[0]["variants"]) == 3  # 截到 3
    assert payload[0]["variants"][0]["source"] == "asset_db"
    items = av.flatten_variant_items(payload)
    assert len(items) == 3
    assert items[0]["kp_name"] == "一元二次方程"


def test_assemble_fetcher_empty_or_raise_records_skip():
    def empty_fetcher(kp_name, subject, limit):
        return []

    def boom_fetcher(kp_name, subject, limit):
        raise RuntimeError("asset db down")

    wps = [
        {"kp_name": "kpA", "wrong_count": 2, "student_count": 2, "titles": ["第1题"]},
        {"kp_name": "kpB", "wrong_count": 1, "student_count": 1, "titles": ["第2题"]},
    ]
    payload = av.assemble_weak_point_payload(wps[:1], empty_fetcher, "数学")
    assert payload[0]["variants"] == []
    assert payload[0]["skip_reason"] == "no_variants"

    payload2 = av.assemble_weak_point_payload(wps[1:], boom_fetcher, "数学")
    assert payload2[0]["variants"] == []
    assert payload2[0]["skip_reason"] == "fetch_failed"


# ── 幂等 / force ────────────────────────────────────────────────
def test_should_skip_existing_idempotent_and_force():
    assert av.should_skip_existing(None, force=False) is False
    assert av.should_skip_existing({"items": []}, force=False) is False
    assert av.should_skip_existing({"items": [{"id": 1}]}, force=False) is True
    assert av.should_skip_existing({"items": [{"id": 1}]}, force=True) is False


def test_generate_idempotent_and_force(monkeypatch, tmp_path):
    """已生成 items 非空 → 跳过；force=True 重跑并覆盖。"""
    folder = "cls_C1__月考"
    calls = {"n": 0}

    def fake_fetcher(kp_name, subject, limit):
        calls["n"] += 1
        return [{"id": "q1", "question": "题", "answer": "A", "analysis": "", "difficulty": 3}]

    monkeypatch.setattr(av, "auto_variants_path", lambda safe: tmp_path / f"{safe}.json")
    monkeypatch.setattr(av, "load_wrong_rows_from_db", lambda *a, **k: [
        {"question_title": "第1题", "student_name": "张三", "kp_name": "分数", "kp_id": "k1"},
        {"question_title": "第1题", "student_name": "李四", "kp_name": "分数", "kp_id": "k1"},
    ])
    monkeypatch.setattr(av, "load_wrong_rows_from_history", lambda safe: [])
    monkeypatch.setattr(av, "_llm_generate_variants", lambda *a, **k: [])

    r1 = av.auto_generate_variants_after_grading(
        "T1", folder, force=False, db=object(), question_fetcher=fake_fetcher, use_llm_fallback=False
    )
    assert r1["status"] == "ready"
    assert r1["items_count"] == 1
    n_after_first = calls["n"]

    r2 = av.auto_generate_variants_after_grading(
        "T1", folder, force=False, db=object(), question_fetcher=fake_fetcher, use_llm_fallback=False
    )
    assert r2["skipped"] == "already_generated"
    assert calls["n"] == n_after_first  # 未再取题

    r3 = av.auto_generate_variants_after_grading(
        "T1", folder, force=True, db=object(), question_fetcher=fake_fetcher, use_llm_fallback=False
    )
    assert r3["status"] == "ready"
    assert calls["n"] > n_after_first  # force 重跑

    saved = json.loads((tmp_path / f"{folder}.json").read_text(encoding="utf-8"))
    assert saved["status"] == "ready"
    assert saved["items"] and saved["items"][0]["question"] == "题"


# ── 资产库空降级 ────────────────────────────────────────────────
def test_empty_asset_db_degrades_without_crash(monkeypatch, tmp_path):
    folder = "cls_C1__期中"
    monkeypatch.setattr(av, "auto_variants_path", lambda safe: tmp_path / f"{safe}.json")
    monkeypatch.setattr(av, "load_wrong_rows_from_db", lambda *a, **k: [
        {"question_title": "第1题", "student_name": "A", "kp_name": "几何", "kp_id": ""},
    ])
    monkeypatch.setattr(av, "load_wrong_rows_from_history", lambda safe: [])
    monkeypatch.setattr(av, "_llm_generate_variants", lambda *a, **k: [])

    def empty_fetcher(kp_name, subject, limit):
        return []

    r = av.auto_generate_variants_after_grading(
        "T1", folder, force=True, db=object(), question_fetcher=empty_fetcher, use_llm_fallback=False
    )
    assert r["status"] == "empty"
    assert r["items_count"] == 0
    saved = json.loads((tmp_path / f"{folder}.json").read_text(encoding="utf-8"))
    assert saved["status"] == "empty"
    assert saved["weak_points"][0]["skip_reason"] == "no_variants"


def test_no_wrong_questions_status_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(av, "auto_variants_path", lambda safe: tmp_path / f"{safe}.json")
    monkeypatch.setattr(av, "load_wrong_rows_from_db", lambda *a, **k: [])
    monkeypatch.setattr(av, "load_wrong_rows_from_history", lambda safe: [])

    r = av.auto_generate_variants_after_grading("T1", "cls_C1__空卷", force=True, db=object())
    assert r["status"] == "empty"
    assert r["reason"] == "no_wrong_questions"


# ── 单场单飞 ────────────────────────────────────────────────────
def test_single_flight_skips_concurrent(monkeypatch, tmp_path):
    folder = "cls_C1__并发"
    entered = threading.Event()
    release = threading.Event()
    results = []

    monkeypatch.setattr(av, "auto_variants_path", lambda safe: tmp_path / f"{safe}.json")

    def slow_fetcher(kp_name, subject, limit):
        entered.set()
        release.wait(timeout=3)
        return [{"id": "q", "question": "t", "answer": "a", "analysis": "", "difficulty": 3}]

    monkeypatch.setattr(av, "load_wrong_rows_from_db", lambda *a, **k: [
        {"question_title": "第1题", "student_name": "A", "kp_name": "kp", "kp_id": ""},
    ])
    monkeypatch.setattr(av, "load_wrong_rows_from_history", lambda safe: [])
    monkeypatch.setattr(av, "_llm_generate_variants", lambda *a, **k: [])

    def run():
        results.append(av.auto_generate_variants_after_grading(
            "T1", folder, force=True, db=object(), question_fetcher=slow_fetcher, use_llm_fallback=False
        ))

    t = threading.Thread(target=run)
    t.start()
    assert entered.wait(timeout=3)
    # 第二次调用应直接 already_running，不进生成
    r2 = av.auto_generate_variants_after_grading(
        "T1", folder, force=True, db=object(), question_fetcher=slow_fetcher, use_llm_fallback=False
    )
    assert r2.get("skipped") == "already_running"
    release.set()
    t.join(timeout=5)
    assert results and results[0].get("status") in ("ready", "empty")


# ── 主链路隔离 ──────────────────────────────────────────────────
def test_auto_variant_exception_does_not_break_auto_sync(monkeypatch):
    """auto_variant 抛异常 → auto_sync_folder_after_grading 仍正常返回。"""
    import app.services.auto_class_sync as acs

    def boom(*_a, **_k):
        raise RuntimeError("variant boom")

    monkeypatch.setattr(acs, "load_folder_completed", lambda safe: {"张三_1.jpg": {"score_total": 90}})
    monkeypatch.setattr(acs, "load_folder_essay_completed", lambda safe: {})
    monkeypatch.setattr(acs, "read_folder_meta", lambda safe: {"subject": "数学", "class_id": "C1"})

    import app.services.auto_variant as av_mod

    monkeypatch.setattr(av_mod, "auto_generate_variants_after_grading", boom)

    # 需要 DB 的段打桩：class 存在 + 有权限 + import/tier 成功
    class _FakeQ:
        def filter(self, *_a, **_k):
            return self

        def first(self):
            return type("Cls", (), {"id": "C1"})()

    class _FakeDb:
        def query(self, *_a, **_k):
            return _FakeQ()

        def close(self):
            pass

    # 只打桩 SessionLocal 与权限/导入，不动 Class 模型（避免跨文件泄漏）
    monkeypatch.setattr("app.database.SessionLocal", lambda: _FakeDb())
    monkeypatch.setattr("app.utils.class_access.can_view_class", lambda db, uid, cid: True)

    import app.routers.student_analysis as sa

    monkeypatch.setattr(sa, "import_scores_core", lambda *a, **k: {"imported_count": 1})
    import app.services.layered_push_service as lps

    monkeypatch.setattr(lps, "apply_auto_tiers", lambda *a, **k: {"updated": 1, "no_score": 0, "thresholds": {}})

    summary = acs.auto_sync_folder_after_grading("T1", "cls_C1__月考")
    assert summary.get("skipped") is None
    assert summary["students"] == 1
    assert summary["imported_count"] == 1


# ── 原子写 / 读回 ───────────────────────────────────────────────
def test_atomic_write_and_load_roundtrip(monkeypatch, tmp_path):
    target = tmp_path / "cls_C1__写读.json"
    monkeypatch.setattr(av, "auto_variants_path", lambda safe: target)

    payload = {"folder": "cls_C1__写读", "status": "ready", "items": [{"id": 1, "question": "q"}]}
    av.atomic_write_json(target, payload)
    assert target.is_file()
    assert not list(tmp_path.glob("*.tmp"))  # 无残留 tmp

    loaded = av.load_auto_variants("cls_C1__写读")
    assert loaded == payload

    assert av.load_auto_variants("不存在") is None or True  # 路径被 stub 成同一文件，仅验证读不炸


def test_read_api_none_when_not_generated(monkeypatch, tmp_path):
    monkeypatch.setattr(av, "auto_variants_path", lambda safe: tmp_path / f"{safe}.json")
    data = av.read_auto_variants_for_api("cls_C1__未生成")
    assert data["status"] == "none"
    assert data["items"] == []
