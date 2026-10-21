from __future__ import annotations

import json

from app.grading import router as grading_router


def _completed_names(safe: str, engine: str) -> set[str]:
    data = grading_router._read_grading_history(safe, engine)
    return set((data.get("completed") or {}).keys())


def _failed_names(safe: str, engine: str) -> set[str]:
    data = grading_router._read_grading_history(safe, engine)
    return set((data.get("failed") or {}).keys())


def _item(name: str) -> dict:
    return {"name": name, "result": json.dumps({"ok": True}, ensure_ascii=False)}


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(grading_router, "grading_history_dir", lambda: tmp_path)
    monkeypatch.setattr(grading_router, "_schedule_auto_sync_class", lambda *a, **k: None)


def test_legacy_history_without_engine_stamp_writes_freely(tmp_path, monkeypatch):
    """旧历史没有引擎戳（放行区）：落盘照常，不能丢结果。"""
    _setup(tmp_path, monkeypatch)
    (tmp_path / "exam.json").write_text(
        json.dumps({"version": 1, "completed": {}, "failed": {}}, ensure_ascii=False),
        encoding="utf-8",
    )
    grading_router._persist_grading_success("exam", _item("甲_1.jpg"), "aliyun")
    assert _completed_names("exam", "default") == {"甲_1.jpg"}


def test_missing_history_file_blocks_stray_writes(tmp_path, monkeypatch):
    """文件不存在 = 已被权威 run 清掉：迟到写入丢弃，不许凭空复活历史。"""
    _setup(tmp_path, monkeypatch)
    grading_router._persist_grading_success("exam", _item("甲_1.jpg"), "aliyun")
    grading_router._persist_grading_failure("exam", "乙_1.jpg", "已停止批改", "aliyun")
    assert not (tmp_path / "exam.json").exists()


def test_same_run_engine_persists(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    grading_router._replace_folder_grading_run("exam", "aliyun")
    grading_router._persist_grading_success("exam", _item("甲_1.jpg"), "aliyun")
    grading_router._persist_grading_failure("exam", "乙_1.jpg", "失败", "aliyun")
    assert _completed_names("exam", "default") == {"甲_1.jpg"}
    assert _failed_names("exam", "default") == {"乙_1.jpg"}


def test_superseded_engine_writes_are_dropped(tmp_path, monkeypatch):
    """模式切换后旧 run 的迟到 worker 不能把旧模式结果复活进新历史。"""
    _setup(tmp_path, monkeypatch)
    grading_router._replace_folder_grading_run("exam", "aliyun")
    grading_router._replace_folder_grading_run("exam", "smart_ref")
    # aliyun 旧 run 的迟到成功/失败一律丢弃
    grading_router._persist_grading_success("exam", _item("旧_1.jpg"), "aliyun")
    grading_router._persist_grading_failure("exam", "旧_2.jpg", "已停止批改", "aliyun")
    # manual 迟到写入同样丢弃（_replace 已清空 manual 历史，不允许复活）
    grading_router._persist_grading_success("exam", _item("旧_3.jpg"), "manual")
    assert _completed_names("exam", "default") == set()
    assert _failed_names("exam", "default") == set()
    assert not (tmp_path / "exam__manual.json").exists()
    # 新 run 自己的落盘不受影响
    grading_router._persist_grading_success("exam", _item("新_1.jpg"), "smart_ref")
    assert _completed_names("exam", "default") == {"新_1.jpg"}


def test_unknown_engine_writes_are_fail_open(tmp_path, monkeypatch):
    """engine=default（旧调用/未传）视为无法判定，放行不丢。"""
    _setup(tmp_path, monkeypatch)
    grading_router._replace_folder_grading_run("exam", "aliyun")
    grading_router._persist_grading_success("exam", _item("甲_1.jpg"), "default")
    grading_router._persist_grading_failure("exam", "乙_1.jpg", "已停止批改")
    assert _completed_names("exam", "default") == {"甲_1.jpg"}
    assert _failed_names("exam", "default") == {"乙_1.jpg"}


def test_manual_run_after_replace_accepts_manual_writes(tmp_path, monkeypatch):
    """自主阅卷权威 run（manual）建立后，manual 落盘放行、ref 落盘丢弃。"""
    _setup(tmp_path, monkeypatch)
    grading_router._replace_folder_grading_run("exam", "manual")
    grading_router._persist_grading_success("exam", _item("甲_1.jpg"), "manual")
    grading_router._persist_grading_success("exam", _item("乙_1.jpg"), "baidu")
    assert _completed_names("exam", "manual") == {"甲_1.jpg"}
    assert _completed_names("exam", "default") == set()


def test_write_grading_history_guard_blocks_resurrect_side_paths(tmp_path, monkeypatch):
    """旁路直写（满分同步/批注等）走同一道闸，不能绕过 _persist_* 复活历史。"""
    _setup(tmp_path, monkeypatch)
    grading_router._replace_folder_grading_run("exam", "aliyun")
    # smart_ref 迟到旁路直写 → 丢弃
    grading_router._write_grading_history(
        "exam", {"completed": {"旧.jpg": _item("旧.jpg")}, "failed": {}}, "smart_ref"
    )
    assert not (tmp_path / "exam.json").exists() or _completed_names("exam", "default") == set()
    # 同引擎直写放行
    grading_router._write_grading_history(
        "exam", {"completed": {"甲.jpg": _item("甲.jpg")}, "failed": {}}, "aliyun"
    )
    assert _completed_names("exam", "default") == {"甲.jpg"}
