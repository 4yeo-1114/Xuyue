# -*- coding: utf-8 -*-
"""11.9-4 取消扫描（软件半）回归：终止待传队列 + 清残留 + 重新绑定。

背景 bug：老师点取消后监测线程在「等文件写入完成」的一秒窗口里仍把文件搬进
目标文件夹；自动绑定又按到达序把导入文件改名占槽，取消清理按旧名找不到改过
名的文件 → 残留占着槽位 → 下一批按到达序绑定整体错位（张三的卷绑到李四框）。

锁定四点：
  1) 清残留逐个「删文件 → 冲统计 → 退面数」交错记账：多页学生（张三_1/2/3）
     的统计账只冲一次——全部先删完再记账会把多页学生的上传账多扣，
     测试用每次记账时的文件夹快照锁住这个顺序；
  2) 中途手动删过的文件（unlink FileNotFoundError）统计不重复冲、面数仍退；
  3) 自动绑定的重命名同步进扫描会话记录（rename 钩子）：取消清理按新名字
     还能删到文件，不漏删；
  4) 扫描目录里的卡纸尾页/半截残留（不在 baseline 里）一并清掉。
"""

import asyncio
import threading

from app.grading import grading_stats
from app.grading import router as grading_router
from app.grading import user_paths
from app.services import quota_service

SAFE = "cls_scan_cancel"


# ---------------------------------------------------------------- 工具

def _patch_project_root(monkeypatch, tmp_path):
    monkeypatch.setattr(user_paths, "project_root", lambda: tmp_path)


def _run_as(user_id, fn, *args):
    token = grading_router.set_grading_user_id(user_id)
    try:
        return fn(*args)
    finally:
        grading_router.reset_grading_user_id(token)


class _FakeReq:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


def _mk_folder(uid, safe, files):
    """在用户上下文里建目标文件夹并放好文件，返回文件夹 Path。"""

    def _mk():
        folder = user_paths.correct_docs_dir() / safe
        folder.mkdir(parents=True, exist_ok=True)
        for name in files:
            (folder / name).write_bytes(b"img")
        return folder

    return _run_as(uid, _mk)


def _seed_scan_state(uid, safe, folder, names, baseline=()):
    state = grading_router._scan_state(uid)
    state["running"] = True
    state["target_folder"] = safe
    state["stop_event"] = threading.Event()
    state["thread"] = None
    state["imported_files"] = [
        {"name": n, "path": str(folder / n)} for n in names
    ]
    state["baseline"] = set(baseline)
    return state


def _patch_accounting(monkeypatch, folder):
    """统计走真函数（只把落库的增减拦下来），面数退订拦下来，逐调用留痕。"""
    calls = {
        "records": [],        # 每次 record_paper_deleted_for_file：当时文件夹还剩什么
        "decrement": [],      # 上传统计冲减（记录学生 key）
        "grade_decrement": [],  # 批改统计冲减（本场景应为空）
        "refund": [],         # 面数退还
    }
    real_record = grading_stats.record_paper_deleted_for_file

    def spy_record(user_id, folder_safe, filename):
        remaining = sorted(p.name for p in folder.iterdir() if p.is_file())
        calls["records"].append({"name": filename, "remaining": remaining})
        return real_record(user_id, folder_safe, filename)

    def fake_decrement(user_id, folder_safe, n, subject_key=None):
        calls["decrement"].append({"key": subject_key, "n": n})

    def fake_grade_decrement(user_id, folder_safe, n, subject_key=None):
        calls["grade_decrement"].append({"key": subject_key, "n": n})

    def fake_refund(user_id, filename, pages=1):
        calls["refund"].append({"name": filename, "pages": pages})

    monkeypatch.setattr(
        grading_stats, "record_paper_deleted_for_file", spy_record
    )
    monkeypatch.setattr(grading_stats, "record_upload_decrement", fake_decrement)
    monkeypatch.setattr(
        grading_stats, "record_grade_decrement", fake_grade_decrement
    )
    monkeypatch.setattr(quota_service, "refund_page", fake_refund)
    return calls


def _stop_clean(uid):
    return _run_as(
        uid,
        asyncio.run,
        grading_router.api_scan_import_stop(
            None, {"delete_imported": True}, None
        ),
    )


# ---------------------------------------------------------------- 测试

def test_multi_page_student_accounted_once_and_interleaved(monkeypatch, tmp_path):
    """多页学生统计账只冲一次；删一个记一次账（快照锁住交错顺序）；面数逐个退。"""
    _patch_project_root(monkeypatch, tmp_path)
    uid = "user-scan-cancel-0001"
    files = ["张三_1.jpg", "张三_2.jpg", "张三_3.jpg", "李四_1.jpg"]
    folder = _mk_folder(uid, SAFE, files)
    _seed_scan_state(uid, SAFE, folder, files)
    calls = _patch_accounting(monkeypatch, folder)

    result = _stop_clean(uid)

    assert result["ok"] is True
    assert result["deleted_imported"] == 4
    assert result["refunded_pages"] == 4
    # 文件全部清掉
    assert sorted(p.name for p in folder.iterdir()) == []
    # 记账顺序 = 导入顺序，且每次记账时文件夹只剩「该文件之后还没删的」
    assert [r["name"] for r in calls["records"]] == files
    assert [r["remaining"] for r in calls["records"]] == [
        ["张三_2.jpg", "张三_3.jpg", "李四_1.jpg"],
        ["张三_3.jpg", "李四_1.jpg"],
        ["李四_1.jpg"],
        [],
    ]
    # 张三 3 页只冲一次上传账、李四 1 页冲一次：共 2 次（全删完再记账会变 4 次）
    assert [d["key"] for d in calls["decrement"]] == ["张三", "李四"]
    # 从未批改过的卷不动批改统计
    assert calls["grade_decrement"] == []
    # 面数按文件逐个退（导入时 record_page 就是逐个扣的）
    assert [r["name"] for r in calls["refund"]] == files
    assert all(r["pages"] == 1 for r in calls["refund"])
    # 会话记录清空，槽位腾出来给下一批重新绑定
    assert grading_router._scan_state(uid)["imported_files"] == []


def test_manually_deleted_file_refunds_without_double_stats(monkeypatch, tmp_path):
    """中途手动删过的文件：统计不重复冲（删除接口当时已冲过），面数仍退给老师。"""
    _patch_project_root(monkeypatch, tmp_path)
    uid = "user-scan-cancel-0002"
    folder = _mk_folder(uid, SAFE, ["李四_1.jpg"])
    # 王五_1.jpg 记录在案但文件已被手动删掉
    _seed_scan_state(uid, SAFE, folder, ["王五_1.jpg", "李四_1.jpg"])
    calls = _patch_accounting(monkeypatch, folder)

    result = _stop_clean(uid)

    assert result["deleted_imported"] == 1
    assert result["refunded_pages"] == 2
    # 统计只按还在的文件冲一次
    assert [r["name"] for r in calls["records"]] == ["李四_1.jpg"]
    assert [d["key"] for d in calls["decrement"]] == ["李四"]
    # 两个文件的面数都要退（导入时各扣过 1 面）
    assert sorted(r["name"] for r in calls["refund"]) == ["李四_1.jpg", "王五_1.jpg"]


def test_rename_hook_syncs_session_records_and_cleanup_follows_new_name(
    monkeypatch, tmp_path
):
    """自动绑定改名后同步进会话记录：取消清理按新名字删得到，不漏删占槽。"""
    _patch_project_root(monkeypatch, tmp_path)
    uid = "user-scan-cancel-0003"
    old_name = "张三_1.jpg"
    new_name = "张三_答题卡1.jpg"
    folder = _mk_folder(uid, SAFE, [old_name])
    state = _seed_scan_state(uid, SAFE, folder, [old_name])

    result = _run_as(
        uid,
        asyncio.run,
        grading_router.api_rename_folder_file(
            SAFE, _FakeReq({"old_name": old_name, "new_name": new_name})
        ),
    )
    assert result["ok"] is True

    recs = state["imported_files"]
    assert len(recs) == 1
    assert recs[0]["name"] == new_name
    assert recs[0]["path"] == str(folder / new_name)

    calls = _patch_accounting(monkeypatch, folder)
    stop_result = _stop_clean(uid)

    # 改过名的文件被删掉（旧实现按旧名 unlink 失败 → 漏删 → 下一批绑定错位）
    assert not (folder / new_name).exists()
    assert stop_result["deleted_imported"] == 1
    assert [r["name"] for r in calls["refund"]] == [new_name]
    # 新名字不再以 _数字 结尾，学生 key = 整个主名（张三_答题卡1）
    assert [d["key"] for d in calls["decrement"]] == ["张三_答题卡1"]


def test_cancel_sweeps_scan_dir_leftovers(monkeypatch, tmp_path):
    """扫描目录里本会话出现过的卡纸尾页/半截残留（不在 baseline）一并清掉。"""
    _patch_project_root(monkeypatch, tmp_path)
    uid = "user-scan-cancel-0004"
    folder = _mk_folder(uid, SAFE, ["李四_1.jpg"])
    _seed_scan_state(uid, SAFE, folder, ["李四_1.jpg"])
    calls = _patch_accounting(monkeypatch, folder)

    def _add_leftover():
        scan = user_paths.scan_dir()
        scan.mkdir(parents=True, exist_ok=True)
        (scan / "卡纸尾页.pdf").write_bytes(b"pdf")
        (scan / "会话前就在的旧文件.pdf").write_bytes(b"pdf")
        return None

    _run_as(uid, _add_leftover)
    # 会话启动前就在的旧文件属于 baseline，不能动
    grading_router._scan_state(uid)["baseline"] = {"会话前就在的旧文件.pdf"}

    result = _stop_clean(uid)

    def _scan_names():
        return sorted(p.name for p in user_paths.scan_dir().iterdir())

    assert _run_as(uid, _scan_names) == ["会话前就在的旧文件.pdf"]
    assert result["deleted_pending"] == 1
    assert result["deleted_imported"] == 1
    assert len(calls["refund"]) == 1
