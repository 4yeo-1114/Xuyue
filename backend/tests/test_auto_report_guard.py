# -*- coding: utf-8 -*-
"""自动报告防并发闸：同账号同文件夹重复入队去重 + 生成单飞（1013 磁盘事故防线）。"""

import pytest

from app.services.ai_auto_report import store


@pytest.fixture(autouse=True)
def _clean_store_state():
    with store._lock:
        store._reports.clear()
        store._streaming_keys.clear()
    yield
    with store._lock:
        store._reports.clear()
        store._streaming_keys.clear()


def _enqueue(uid: str = "u1", folder: str = "cls_a", rtype: str = "smart_scoring"):
    return store.enqueue_report(
        user_id=uid,
        folder_safe=folder,
        folder_display="第一单元测试",
        report_type=rtype,
        title="t",
        user_message="m",
        payload={},
        fingerprint="fp1",
    )


def _first_pending_id() -> str:
    items = store.list_pending("u1")
    assert items, "应有 pending 报告"
    return items[0]["id"]


def test_enqueue_dedupes_same_user_folder_type_while_pending():
    assert _enqueue() is not None
    # 同账号同文件夹同类型：pending 期间再入队应被拒绝
    assert _enqueue() is None
    assert len(store.list_pending("u1")) == 1


def test_enqueue_allowed_after_consumed():
    rid = _enqueue()
    assert rid is not None
    assert store.mark_consumed(rid, "u1")
    # 上一份已消费后，允许再次入队（例如统分配置变更后重新生成）
    assert _enqueue() is not None
    pending = store.list_pending("u1")
    assert len(pending) == 1  # 已消费的不计入 pending，新入队的在列
    assert pending[0]["id"] != rid


def test_enqueue_not_blocked_for_other_folder_or_user_or_type():
    assert _enqueue(folder="cls_a") is not None
    # 不同文件夹 / 不同账号 / 不同类型（作文）均不受影响
    assert _enqueue(folder="cls_b") is not None
    assert _enqueue(uid="u2", folder="cls_a") is not None
    assert _enqueue(folder="cls_a", rtype="essay") is not None
    assert len(store.list_pending("u1")) == 3


def test_has_pending_for_folder_reflects_status():
    assert not store.has_pending_for_folder("u1", "cls_a", "smart_scoring")
    rid = _enqueue()
    assert store.has_pending_for_folder("u1", "cls_a", "smart_scoring")
    assert not store.has_pending_for_folder("u1", "cls_a", "essay")
    assert not store.has_pending_for_folder("u2", "cls_a", "smart_scoring")
    store.mark_consumed(rid, "u1")
    assert not store.has_pending_for_folder("u1", "cls_a", "smart_scoring")


def test_begin_stream_single_flight_per_folder():
    assert store.begin_stream("u1", "cls_a")
    # 同账号同文件夹：第二路生成应被拒绝
    assert not store.begin_stream("u1", "cls_a")
    # 其他文件夹 / 其他账号不受影响
    assert store.begin_stream("u1", "cls_b")
    assert store.begin_stream("u2", "cls_a")
    store.end_stream("u1", "cls_a")
    # 结束后可再次开始
    assert store.begin_stream("u1", "cls_a")
    store.end_stream("u1", "cls_a")


def test_end_stream_unknown_key_is_safe():
    store.end_stream("u_nope", "cls_nope")  # 不应抛异常
