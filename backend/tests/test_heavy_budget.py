# -*- coding: utf-8 -*-
"""全局重活预算（排队等着）单测——1015 根治。

验证：①槽位满了新任务排队而不是超卖 ②异常/结束必放槽 ③排队状态可观测
④批改/报告/打印四个重活入口都已挂上 heavy_slot。
"""
import inspect
import threading
import time

import pytest

from app.services import heavy_budget


@pytest.fixture(autouse=True)
def _reset_slots():
    heavy_budget.set_slots_for_test(2)
    yield
    heavy_budget.set_slots_for_test()


def test_third_task_waits_for_slot():
    """N=2：两个进，第三个排队；释放一个后第三个才进。"""
    heavy_budget.set_slots_for_test(2)
    inside = threading.Semaphore(0)
    release = threading.Semaphore(0)

    def worker(tag):
        with heavy_budget.heavy_slot(f"t-{tag}"):
            inside.release()
            release.acquire()

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(3)]
    for t in threads:
        t.start()

    assert inside.acquire(timeout=2), "第 1 个应立即进"
    assert inside.acquire(timeout=2), "第 2 个应立即进"
    assert not inside.acquire(timeout=0.3), "第 3 个必须排队，不得超卖"

    release.release()
    assert inside.acquire(timeout=2), "释放一个槽位后第 3 个应进"
    release.release()
    release.release()
    for t in threads:
        t.join(timeout=3)

    st = heavy_budget.budget_status()
    assert st["running"] == {} and st["waiting"] == 0


def test_exception_releases_slot():
    heavy_budget.set_slots_for_test(1)
    with pytest.raises(ValueError):
        with heavy_budget.heavy_slot("boom"):
            raise ValueError("炸了")

    entered = threading.Event()

    def worker():
        with heavy_budget.heavy_slot("after"):
            entered.set()

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    assert entered.wait(2), "异常后槽位必须已释放"
    t.join(timeout=2)


def test_budget_status_counts_waiting():
    heavy_budget.set_slots_for_test(1)
    hold = threading.Event()
    started = threading.Event()

    def holder():
        with heavy_budget.heavy_slot("h1"):
            started.set()
            hold.wait(5)

    t1 = threading.Thread(target=holder, daemon=True)
    t1.start()
    assert started.wait(2)

    st = heavy_budget.budget_status()
    assert st["running"] == {"h1": 1} and st["waiting"] == 0

    q_started = threading.Event()

    def queued():
        q_started.set()
        with heavy_budget.heavy_slot("h2"):
            pass

    t2 = threading.Thread(target=queued, daemon=True)
    t2.start()
    assert q_started.wait(2)
    time.sleep(0.1)  # 让 t2 真正进入排队计数
    st = heavy_budget.budget_status()
    assert st["waiting"] == 1 and st["running"] == {"h1": 1}

    hold.set()
    t1.join(timeout=3)
    t2.join(timeout=3)
    st = heavy_budget.budget_status()
    assert st["running"] == {} and st["waiting"] == 0


def test_default_slots_from_env(monkeypatch):
    monkeypatch.setenv("HEAVY_TASK_SLOTS", "3")
    heavy_budget.set_slots_for_test()
    assert heavy_budget.budget_status()["slots"] == 3
    monkeypatch.delenv("HEAVY_TASK_SLOTS")
    heavy_budget.set_slots_for_test()
    assert heavy_budget.budget_status()["slots"] == 2


def test_heavy_paths_are_wired():
    """四个重活入口都必须挂 heavy_slot（防回归拆掉总闸）。"""
    from app.grading import router
    from app.routers import ai_auto_report

    assert "heavy_slot" in inspect.getsource(router._run_ref_grade)
    assert "heavy_slot" in inspect.getsource(router.api_print_marks_pdf)
    assert "heavy_slot" in inspect.getsource(router.api_print_marks_batch_start)
    assert "heavy_slot" in inspect.getsource(ai_auto_report.api_stream_auto_report)


def test_run_ref_grade_queues_then_runs(monkeypatch):
    """批改线程拿不到槽位时 job 显示排队中，跑起来后清除标志。"""
    heavy_budget.set_slots_for_test(1)
    from app.grading import router as r

    got_in = threading.Event()
    release = threading.Event()

    def holder():
        with heavy_budget.heavy_slot("holder"):
            got_in.set()
            release.wait(5)

    h = threading.Thread(target=holder, daemon=True)
    h.start()
    assert got_in.wait(2)

    seen = {}
    started = threading.Event()

    def fake_impl(job_id, folder_name, engine, only_filename=None, only_filenames=None):
        with r._ref_grade_lock:
            seen["queued"] = r._ref_grade_results[job_id].get("queued")
            seen["waited"] = r._ref_grade_results[job_id].get("queue_waited_s")
        started.set()

    monkeypatch.setattr(r, "_run_ref_grade_impl", fake_impl)
    monkeypatch.setattr(r, "_sync_ref_job_from_history", lambda *a, **k: None)

    with r._ref_grade_lock:
        r._ref_grade_results["jobQ"] = {
            "completed": [], "failed": [], "in_progress": [], "done": False,
            "total": 1, "engine": "aliyun", "user_id": "U1", "folder": "cls_Q",
            "push_dingtalk": False,
        }

    t = threading.Thread(
        target=r._run_ref_grade,
        args=("jobQ", "cls_Q", "aliyun", None, None, "U1"),
        daemon=True,
    )
    t.start()
    time.sleep(0.3)
    with r._ref_grade_lock:
        assert r._ref_grade_results["jobQ"].get("queued") is True, "槽位被占时应排队中"

    release.set()
    assert started.wait(3), "释放槽位后应开跑"
    t.join(timeout=3)
    h.join(timeout=3)
    assert seen["queued"] is False, "开跑后应清除排队标志"
    assert isinstance(seen["waited"], (int, float)) and seen["waited"] >= 0
