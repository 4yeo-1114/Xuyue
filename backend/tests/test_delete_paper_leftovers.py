# -*- coding: utf-8 -*-
"""删除试卷收尾清理回归测试。

背景 bug：历史记录里的留痕图 URL 固化过 ?ticket=<JWT> 下载票（见
test_history_image_resign.py），删除试卷时 _remove_grading_history_entry 用
url.split("/")[-1] 取“文件名”，把整段票也算进去 → Path.is_file() 抛
OSError: [Errno 36] File name too long（Linux 实测 ENAMETOOLONG）。

而试卷本体在收尾清理之前就已 unlink，于是：
  1) 第一次删除 → 文件删掉了但接口 500；
  2) 前端当删除失败，列表不刷新，用户重试 → 404「文件不存在」，永远删不掉。
表现为“我删除试卷为啥一直显示文件不存在”。

本测试锁定三点：
  - URL 到文件名必须剥掉 ?query/#fragment；
  - _remove_grading_history_entry 面对带票 URL 不抛错，且能按真名删掉 modify 图；
  - 删除接口幂等：文件已不在但历史残留时，清理后返回成功（幽灵条目自愈），
    且收尾清理失败不能让请求 5xx。
"""

import asyncio

from app.grading import user_paths
from app.grading import router as grading_router

UID = "user-test-del-0001"
SAFE = "cls_x__8"
PAPER = "王五_1.jpg"
STEM = "cls_x__8_王五_1"
# 足够长的票：拼进文件名必然超过 255 字节（复现 ENAMETOOLONG 的前提）
TICKET = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." + "A" * 400

_IMAGE_KEYS = (
    ("image_original", "original"),
    ("image_annotated", "annotated"),
    ("image_marks_only", "marks_only"),
)


# ---------------------------------------------------------------- 工具

def _patch_project_root(monkeypatch, tmp_path):
    monkeypatch.setattr(user_paths, "project_root", lambda: tmp_path)


def _set_user(user_id):
    return grading_router.set_grading_user_id(user_id)


def _run_as(user_id, fn, *args):
    token = _set_user(user_id)
    try:
        return fn(*args)
    finally:
        grading_router.reset_grading_user_id(token)


def _write_grading_history(user_id, safe, data, engine="default"):
    _run_as(user_id, grading_router._write_grading_history, safe, data, engine)


def _read_grading_history(user_id, safe, engine="default"):
    return _run_as(user_id, grading_router._read_grading_history, safe, engine)


def _ghost_history(stem=STEM):
    """一条带超长下载票的历史记录（三个图片字段都带上）。"""
    item = {
        "name": PAPER,
        "group_name": "王五",
        "result": "总题量：10；已批改：10；批改中：0",
    }
    for key, prefix in _IMAGE_KEYS:
        item[key] = f"/api/v1/grading/modify/{prefix}_{stem}.jpg?ticket={TICKET}"
    return {
        "version": 1,
        "completed": {PAPER: item},
        "failed": {},
        "scoring_config": None,
    }


def _prepare_modify_images(user_id):
    """按 URL 里的真名建出 modify 残留图，返回路径列表。"""
    def _mk():
        modify = grading_router.modify_dir()
        modify.mkdir(parents=True, exist_ok=True)
        paths = []
        for _, prefix in _IMAGE_KEYS:
            p = modify / f"{prefix}_{STEM}.jpg"
            p.write_bytes(b"img")
            paths.append(p)
        return paths

    return _run_as(user_id, _mk)


def _paper_path(user_id, safe, name):
    return _run_as(user_id, lambda: grading_router.correct_docs_dir() / safe / name)


# ---------------------------------------------------------------- URL → 文件名

def test_img_name_from_url_strips_ticket_query_and_fragment():
    name_from = grading_router._img_name_from_url
    assert name_from(f"/api/v1/grading/modify/original_{STEM}.jpg?ticket={TICKET}") == f"original_{STEM}.jpg"
    assert name_from("/api/v1/grading/modify/annotated_x.jpg?t=123") == "annotated_x.jpg"
    assert name_from("/api/v1/grading/modify/marks_only_x.jpg#frag") == "marks_only_x.jpg"
    assert name_from("/api/v1/grading/modify/plain.jpg") == "plain.jpg"
    # 空值 / 路径穿越都必须给出空串，拒绝当文件名用；多级路径只取末段（沿用
    # _delete_modify_file_by_url 既有约定，末段仍是 modify 目录内的扁平名）
    assert name_from("") == ""
    assert name_from(None) == ""
    assert name_from("/api/v1/grading/modify/a/b.jpg") == "b.jpg"
    assert name_from("/api/v1/grading/modify/..") == ""
    assert name_from("/api/v1/grading/modify/a\\b.jpg") == ""


# ---------------------------------------------------------------- 历史条目清理

def test_remove_grading_history_entry_with_ticketed_urls(monkeypatch, tmp_path):
    """带票 URL 不许抛错（旧代码 ENAMETOOLONG 直接炸），且按真名删掉残留图。"""
    _patch_project_root(monkeypatch, tmp_path)
    _write_grading_history(UID, SAFE, _ghost_history())
    img_paths = _prepare_modify_images(UID)
    for p in img_paths:
        assert p.is_file()

    # 旧代码在这里抛 OSError（文件名里带整段票），正是删除接口 500 的源头
    _run_as(UID, grading_router._remove_grading_history_entry, SAFE, PAPER, "default")

    data = _read_grading_history(UID, SAFE)
    assert PAPER not in data["completed"], "历史条目没被清掉"
    for p in img_paths:
        assert not p.is_file(), f"残留图没按真名删掉: {p.name}"


# ---------------------------------------------------------------- 删除接口

def test_delete_folder_file_idempotent_heals_ghost(monkeypatch, tmp_path):
    """文件已不在、只剩历史残留（旧 bug 的现场）：再点删除要自愈返回成功。

    旧代码这里 404「文件不存在」——正是“一直显示文件不存在”的来源。
    """
    _patch_project_root(monkeypatch, tmp_path)
    _write_grading_history(UID, SAFE, _ghost_history())
    img_paths = _prepare_modify_images(UID)
    paper = _paper_path(UID, SAFE, PAPER)
    paper.parent.mkdir(parents=True, exist_ok=True)
    assert not paper.is_file()

    resp = _run_as(UID, asyncio.run, grading_router.api_delete_folder_file(SAFE, PAPER))

    assert resp == {"ok": True}, f"幽灵条目没自愈: {resp}"
    data = _read_grading_history(UID, SAFE)
    assert PAPER not in data["completed"], "历史残留没被清掉"
    for p in img_paths:
        assert not p.is_file(), f"残留图没清掉: {p.name}"


def test_delete_folder_file_cleans_history_when_paper_exists(monkeypatch, tmp_path):
    _patch_project_root(monkeypatch, tmp_path)
    _write_grading_history(UID, SAFE, _ghost_history())
    img_paths = _prepare_modify_images(UID)
    paper = _paper_path(UID, SAFE, PAPER)
    paper.parent.mkdir(parents=True, exist_ok=True)
    paper.write_bytes(b"paper")
    sidecar = paper.with_suffix(".json")
    sidecar.write_text("{}", encoding="utf-8")

    resp = _run_as(UID, asyncio.run, grading_router.api_delete_folder_file(SAFE, PAPER))

    assert resp == {"ok": True}
    assert not paper.is_file()
    assert not sidecar.is_file()
    data = _read_grading_history(UID, SAFE)
    assert PAPER not in data["completed"]
    for p in img_paths:
        assert not p.is_file()


def test_delete_folder_file_survives_cleanup_failure(monkeypatch, tmp_path):
    """收尾清理炸了也不能 5xx——文件已删，报错会让前端反复重试出「文件不存在」。"""
    _patch_project_root(monkeypatch, tmp_path)
    paper = _paper_path(UID, SAFE, PAPER)
    paper.parent.mkdir(parents=True, exist_ok=True)
    paper.write_bytes(b"paper")

    def _boom(*args, **kwargs):
        raise OSError("cleanup exploded")

    monkeypatch.setattr(grading_router, "_remove_grading_history_entry", _boom)

    resp = _run_as(UID, asyncio.run, grading_router.api_delete_folder_file(SAFE, PAPER))

    assert resp == {"ok": True}, "清理失败不该把已成功的删除打成错误"
    assert not paper.is_file()
