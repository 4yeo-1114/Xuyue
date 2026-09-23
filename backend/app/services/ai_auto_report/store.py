# -*- coding: utf-8 -*-
"""内存队列：待推送到 AI 助教界面的自动分析报告。"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Optional

from app.grading.user_paths import sanitize_user_id

_lock = threading.Lock()


def _norm_user_id(user_id: str) -> str:
    return sanitize_user_id(str(user_id or "").strip())
_reports: dict[str, dict[str, Any]] = {}
_MAX_AGE_SEC = 3600 * 6


def _purge_expired() -> None:
    now = time.time()
    expired = [rid for rid, item in _reports.items() if now - float(item.get("created_at") or 0) > _MAX_AGE_SEC]
    for rid in expired:
        _reports.pop(rid, None)


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
