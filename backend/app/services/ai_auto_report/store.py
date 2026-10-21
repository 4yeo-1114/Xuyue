# -*- coding: utf-8 -*-
"""内存队列：待推送到 AI 助教界面的自动分析报告。"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Optional

from app.grading.user_paths import sanitize_user_id

_lock = threading.Lock()

# 正在流式生成中的 (user, folder) 集合：同账号同文件夹同时只允许一路生成
_streaming_keys: set[str] = set()


def _norm_user_id(user_id: str) -> str:
    return sanitize_user_id(str(user_id or "").strip())
_reports: dict[str, dict[str, Any]] = {}
_MAX_AGE_SEC = 3600 * 6


def _purge_expired() -> None:
    now = time.time()
    expired = [rid for rid, item in _reports.items() if now - float(item.get("created_at") or 0) > _MAX_AGE_SEC]
    for rid in expired:
        _reports.pop(rid, None)


def _has_pending_locked(uid: str, folder_safe: str, report_type: str) -> bool:
    return any(
        item.get("user_id") == uid
        and item.get("folder_safe") == folder_safe
        and item.get("report_type") == report_type
        and item.get("status") == "pending"
        for item in _reports.values()
    )


def has_pending_for_folder(user_id: str, folder_safe: str, report_type: str) -> bool:
    uid = _norm_user_id(user_id)
    with _lock:
        _purge_expired()
        return _has_pending_locked(uid, folder_safe, report_type)


def _stream_key(user_id: str, folder_safe: str) -> str:
    return f"{_norm_user_id(user_id)}::{folder_safe}"


def begin_stream(user_id: str, folder_safe: str) -> bool:
    """同账号同文件夹同时只允许一路报告生成；拿到生成权返回 True。"""
    key = _stream_key(user_id, folder_safe)
    with _lock:
        if key in _streaming_keys:
            return False
        _streaming_keys.add(key)
        return True


def end_stream(user_id: str, folder_safe: str) -> None:
    with _lock:
        _streaming_keys.discard(_stream_key(user_id, folder_safe))


def enqueue_report(
    *,
    user_id: str,
    folder_safe: str,
    folder_display: str,
    report_type: str,
    title: str,
    user_message: str,
    payload: dict[str, Any],
    fingerprint: str,
) -> Optional[str]:
    uid = _norm_user_id(user_id)
    if not uid or uid == "unknown":
        return None
    report_id = str(uuid.uuid4())
    item = {
        "id": report_id,
        "user_id": uid,
        "folder_safe": folder_safe,
        "folder_display": folder_display,
        "report_type": report_type,
        "title": title,
        "user_message": user_message,
        "payload": payload,
        "fingerprint": fingerprint,
        "status": "pending",
        "created_at": time.time(),
    }
    with _lock:
        _purge_expired()
        # 防同一账号同一文件夹同类报告重复入队（1013 事故：106 秒内连点两次触发两批 41 人报告）
        if _has_pending_locked(uid, folder_safe, report_type):
            return None
        _reports[report_id] = item
    return report_id


def list_pending(user_id: str) -> list[dict[str, Any]]:
    uid = _norm_user_id(user_id)
    if not uid or uid == "unknown":
        return []
    with _lock:
        _purge_expired()
        items = [
            {
                "id": item["id"],
                "folder_safe": item["folder_safe"],
                "folder_display": item["folder_display"],
                "report_type": item["report_type"],
                "title": item["title"],
                "user_message": item["user_message"],
                "created_at": item["created_at"],
            }
            for item in _reports.values()
            if item.get("user_id") == uid and item.get("status") == "pending"
        ]
    items.sort(key=lambda x: float(x.get("created_at") or 0))
    return items


def get_report(report_id: str, user_id: str) -> Optional[dict[str, Any]]:
    uid = _norm_user_id(user_id)
    with _lock:
        item = _reports.get(report_id)
        if not item or item.get("user_id") != uid:
            return None
        return dict(item)


def mark_consumed(report_id: str, user_id: str) -> bool:
    uid = _norm_user_id(user_id)
    with _lock:
        item = _reports.get(report_id)
        if not item or item.get("user_id") != uid:
            return False
        item["status"] = "consumed"
        return True
