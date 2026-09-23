# -*- coding: utf-8 -*-
"""下载票重签回归测试：读历史接口返回的图片直链必须带「当场新签」的票。

背景：留痕图直链里的 ?ticket= 只有 10 分钟有效期（DOWNLOAD_TICKET_EXPIRE_MINUTES），
而批改时已把票固化进 URL。读取历史时必须重签，否则用户过一会儿回看，
<img> 请求返回 401，表现为原试卷/留痕图空白。

曾经的 bug：grading-history 做了重签，essay-grading-history 漏了（复制粘贴漏改）。
本测试同时覆盖两条路径，任何一条漏掉重签都会失败。
"""

import asyncio

from app.grading import user_paths
from app.grading import router as grading_router
from app.utils.security import verify_download_ticket

UID = "user-test-0001"
SAFE = "cls_x__语文作文"

# 模拟历史记录里固化的「10 分钟前签发、现已过期」的票
STALE = "STALE_TICKET_FROM_10_MIN_AGO"

_IMAGE_KEYS = (
    ("image_original", "original"),
    ("image_annotated", "annotated"),
    ("image_marks_only", "marks_only"),
)


# ---------------------------------------------------------------- 工具

def _patch_project_root(monkeypatch, tmp_path):
    """把 grading_data_all 根目录重定向到 tmp_path，做 per-user 文件系统隔离。"""
    monkeypatch.setattr(user_paths, "project_root", lambda: tmp_path)


def _set_user(user_id):
    return grading_router.set_grading_user_id(user_id)


def _write_essay_history(user_id, safe, data):
    token = _set_user(user_id)
    try:
        grading_router._write_essay_history(safe, data)
    finally:
        grading_router.reset_grading_user_id(token)


def _write_grading_history(user_id, safe, data, engine="default"):
    token = _set_user(user_id)
    try:
        grading_router._write_grading_history(safe, data, engine)
    finally:
        grading_router.reset_grading_user_id(token)


def _stale_completed(name, stem):
    """一条带过期票的历史记录（三个图片字段都带上）。

    注意 result 不能为空：grading-history 会把没有 result 的条目当「占位记录」剔除。
    """
    item = {
        "name": name,
        "group_name": name.split("_")[0],
        "result": "总题量：10；已批改：10；批改中：0",
    }
    for key, prefix in _IMAGE_KEYS:
        item[key] = f"/api/v1/grading/modify/{prefix}_{stem}.jpg?ticket={STALE}"
    return item


def _assert_resigned(url, *, resource, uid):
    """断言：旧票被剥掉，且附上的新票能被 verify_download_ticket 校验通过。"""
    assert url, "图片 URL 为空"
    assert STALE not in url, f"过期票没被剥掉: {url}"
    assert "ticket=" in url, f"没有重新签发票: {url}"
    ticket = url.split("ticket=", 1)[1]
    assert verify_download_ticket(ticket, resource) == uid, (
        f"重签的票校验不通过（resource={resource}）: {url}"
    )


# ---------------------------------------------------------------- 作文批改历史

def test_essay_history_resigns_stale_ticket(monkeypatch, tmp_path):
    _patch_project_root(monkeypatch, tmp_path)
    stem = "essay_cls_x__语文作文_张三_1"
    _write_essay_history(UID, SAFE, {
        "version": 1,
        "completed": {"张三_1.jpg": _stale_completed("张三_1.jpg", stem)},
        "failed": {},
    })

    token = _set_user(UID)
    try:
        resp = asyncio.run(grading_router.api_get_essay_grading_history(SAFE))
    finally:
        grading_router.reset_grading_user_id(token)

    assert resp["ok"] is True
    assert len(resp["completed"]) == 1
    item = resp["completed"][0]
    for key, prefix in _IMAGE_KEYS:
        _assert_resigned(
            item[key], resource=f"grading/modify/{prefix}_{stem}.jpg", uid=UID
        )


def test_essay_history_drops_internal_fields_but_keeps_images(monkeypatch, tmp_path):
    """重签的同时仍要剔除内部字段（rubric_text/prompts/dimensions）。"""
    _patch_project_root(monkeypatch, tmp_path)
    stem = "essay_cls_x__语文作文_李四_1"
    item: dict = _stale_completed("李四_1.jpg", stem)
    item["rubric_text"] = "批改标准正文"
    item["prompts"] = {"dimensions_json": "{}"}
    item["dimensions"] = [{"key": "content"}]
    _write_essay_history(UID, SAFE, {
        "version": 1, "completed": {"李四_1.jpg": item}, "failed": {},
    })

    token = _set_user(UID)
    try:
        resp = asyncio.run(grading_router.api_get_essay_grading_history(SAFE))
    finally:
        grading_router.reset_grading_user_id(token)

    out = resp["completed"][0]
    for field in ("rubric_text", "prompts", "dimensions"):
        assert field not in out, f"内部字段 {field} 泄漏到接口返回"
    assert "ticket=" in out["image_annotated"]


# ---------------------------------------------------------------- 快速批改历史

def test_grading_history_resigns_stale_ticket(monkeypatch, tmp_path):
    _patch_project_root(monkeypatch, tmp_path)
    # grading 的历史文件名不是 essay_ 前缀，走另一条构造
    stem = "cls_x__语文试卷_王五_1"
    _write_grading_history(UID, SAFE, {
        "version": 1,
        "completed": {"王五_1.jpg": _stale_completed("王五_1.jpg", stem)},
        "failed": {},
        "scoring_config": None,
    })

    token = _set_user(UID)
    try:
        resp = asyncio.run(grading_router.api_get_grading_history(SAFE, engine="default"))
    finally:
        grading_router.reset_grading_user_id(token)

    assert resp["ok"] is True
    assert len(resp["completed"]) == 1
    item = resp["completed"][0]
    for key, prefix in _IMAGE_KEYS:
        _assert_resigned(
            item[key], resource=f"grading/modify/{prefix}_{stem}.jpg", uid=UID
        )


# ---------------------------------------------------------------- 共用函数本身

def test_resign_history_list_handles_edge_cases(monkeypatch, tmp_path):
    """空 URL / 非图片外链 / 非 dict 条目都不能把接口搞崩。"""
    _patch_project_root(monkeypatch, tmp_path)
    token = _set_user(UID)
    try:
        out = grading_router._resign_history_list([
            {"name": "b.jpg", "image_annotated": None},
            {"name": "a.jpg", "image_annotated": "https://cdn.example.com/x.jpg"},
            "不是字典",
            {"name": "c.jpg",
             "image_annotated": f"/api/v1/grading/modify/annotated_x.jpg?ticket={STALE}"},
        ])
    finally:
        grading_router.reset_grading_user_id(token)

    names = [i["name"] for i in out]
    assert names == ["a.jpg", "b.jpg", "c.jpg"], f"排序/过滤异常: {names}"
    # 外链原样保留
    assert out[0]["image_annotated"] == "https://cdn.example.com/x.jpg"
    # 站内链接换上新票
    _assert_resigned(
        out[2]["image_annotated"], resource="grading/modify/annotated_x.jpg", uid=UID
    )
