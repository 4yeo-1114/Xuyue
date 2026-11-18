from __future__ import annotations

import json

from app.grading import router as grading_router


def _completed_names(safe: str, engine: str) -> set[str]:
    data = grading_router._read_grading_history(safe, engine)
    return set((data.get("completed") or {}).keys())


def _stamp(safe: str, engine: str = "default") -> str:
    data = grading_router._read_grading_history(safe, engine)
    return str(data.get("engine") or "")


def _item(name: str) -> dict:
    return {"name": name, "result": json.dumps({"ok": True}, ensure_ascii=False)}


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(grading_router, "grading_history_dir", lambda: tmp_path)
    monkeypatch.setattr(grading_router, "modify_dir", lambda: tmp_path / "modify")
    monkeypatch.setattr(grading_router, "_schedule_auto_sync_class", lambda *a, **k: None)
    calls = {"wq_removed": [], "ledger_voided": []}

    import app.grading.correction_ledger as cl
    import app.grading.wrong_question_db as wq

    monkeypatch.setattr(
        wq,
        "remove_paper_from_exam_wrong_questions",
        lambda f, p: calls["wq_removed"].append((f, p)),
    )
    monkeypatch.setattr(
        cl,
        "void_paper_corrections",
        lambda f, p: calls["ledger_voided"].append((f, p)),
    )
    return calls


def test_selected_regrade_preserves_other_students(tmp_path, monkeypatch):
    """11.9-5：勾选/单张重批只动选中卷子，其余学生保持已批改。"""
    _setup(tmp_path, monkeypatch)
    grading_router._replace_folder_grading_run("exam", "aliyun")
    for name in ("甲_1.jpg", "乙_1.jpg", "丙_1.jpg"):
        grading_router._persist_grading_success("exam", _item(name), "aliyun")

    grading_router._reset_selected_grading_run("exam", "aliyun", "乙_1.jpg", None)

    assert _completed_names("exam", "default") == {"甲_1.jpg", "丙_1.jpg"}
    # 引擎戳保留 → 本次重批的落盘照常写回
    assert _stamp("exam") == "aliyun"
    grading_router._persist_grading_success("exam", _item("乙_1.jpg"), "aliyun")
    assert _completed_names("exam", "default") == {"甲_1.jpg", "乙_1.jpg", "丙_1.jpg"}


def test_selected_regrade_touches_only_selected_side_data(tmp_path, monkeypatch):
    """错题记录/台账作废按卷处理，不整文件夹清。"""
    calls = _setup(tmp_path, monkeypatch)
    grading_router._replace_folder_grading_run("exam", "aliyun")
    for name in ("甲_1.jpg", "乙_1.jpg"):
        grading_router._persist_grading_success("exam", _item(name), "aliyun")

    grading_router._reset_selected_grading_run(
        "exam", "aliyun", None, {"乙_1.jpg"}
    )

    assert calls["wq_removed"] == [("exam", "乙_1.jpg")]
    assert calls["ledger_voided"] == [("exam", "乙_1.jpg")]


def test_multi_select_regrade_removes_each_selected(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    grading_router._replace_folder_grading_run("exam", "aliyun")
    for name in ("甲_1.jpg", "乙_1.jpg", "丙_1.jpg", "丁_1.jpg"):
        grading_router._persist_grading_success("exam", _item(name), "aliyun")

    grading_router._reset_selected_grading_run(
        "exam", "aliyun", "甲_1.jpg", {"丙_1.jpg", "丁_1.jpg"}
    )

    assert _completed_names("exam", "default") == {"乙_1.jpg"}


def test_engine_switch_selected_regrade_restamps_and_blocks_late_writes(
    tmp_path, monkeypatch
):
    """换引擎后勾选重批：保留他人条目、补本次引擎戳，旧引擎迟到写入丢弃。"""
    _setup(tmp_path, monkeypatch)
    grading_router._replace_folder_grading_run("exam", "baidu")
    for name in ("甲_1.jpg", "乙_1.jpg"):
        grading_router._persist_grading_success("exam", _item(name), "baidu")

    grading_router._reset_selected_grading_run("exam", "aliyun", "乙_1.jpg", None)

    assert _completed_names("exam", "default") == {"甲_1.jpg"}
    assert _stamp("exam") == "aliyun"
    # 旧 run（baidu）迟到写入被守卫拦下；本次引擎（aliyun）落盘照常
    grading_router._persist_grading_success("exam", _item("旧_1.jpg"), "baidu")
    grading_router._persist_grading_success("exam", _item("乙_1.jpg"), "aliyun")
    assert _completed_names("exam", "default") == {"甲_1.jpg", "乙_1.jpg"}


def test_selected_regrade_manual_history_also_cleared(tmp_path, monkeypatch):
    """同名条目在 manual 历史里的也一并清（对齐全量清档口径，只限选中卷）。"""
    _setup(tmp_path, monkeypatch)
    grading_router._replace_folder_grading_run("exam", "manual")
    for name in ("甲_1.jpg", "乙_1.jpg"):
        grading_router._persist_grading_success("exam", _item(name), "manual")

    grading_router._reset_selected_grading_run("exam", "manual", "乙_1.jpg", None)

    assert _completed_names("exam", "manual") == {"甲_1.jpg"}
    assert _stamp("exam", "manual") == "manual"
    grading_router._persist_grading_success("exam", _item("乙_1.jpg"), "manual")
    assert _completed_names("exam", "manual") == {"甲_1.jpg", "乙_1.jpg"}
