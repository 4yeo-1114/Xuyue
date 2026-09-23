# -*- coding: utf-8 -*-
"""批改完成后自动分析报告：触发条件判断与入队。"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from typing import Optional

from app.grading.router import (
    _grading_history_lock,
    _read_essay_history,
    _read_grading_history,
    _write_essay_history,
    _write_grading_history,
)
from app.grading.grading_stats import _list_folder_upload_filenames, is_paper_shows_graded_badge
from app.grading.user_paths import run_with_grading_user, sanitize_user_id
from app.services.ai_auto_report.collector import (
    _display_folder_name,
    collect_essay_payload,
    collect_smart_scoring_payload,
    count_scored_ref_papers,
)
from app.services.ai_auto_report.store import enqueue_report

_DEBUG = os.environ.get("AI_AUTO_REPORT_DEBUG", "").strip().lower() in ("1", "true", "yes")


def _log_skip(reason: str, folder_safe: str, **extra) -> None:
    if _DEBUG:
        parts = [f"[ai_auto_report] skip folder={folder_safe!r} reason={reason}"]
        if extra:
            parts.append(f"extra={extra}")
        print(" ".join(parts))


def _fingerprint(data: dict) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _all_upload_files_graded_essay(folder_safe: str) -> bool:
    files = _list_folder_upload_filenames(folder_safe)
    if not files:
        _log_skip("no_upload_files", folder_safe)
        return False
    completed = _read_essay_history(folder_safe).get("completed") or {}
    if not isinstance(completed, dict):
        return False
    for fname in files:
        entry = completed.get(fname)
        if not is_paper_shows_graded_badge(entry, source="essay"):
            return False
    return True


def _read_trigger_fingerprint(history: dict, key: str) -> Optional[str]:
    triggers = history.get("auto_report_triggers")
    if not isinstance(triggers, dict):
        return None
    token = triggers.get(key)
    return str(token) if token else None


def _save_trigger_fingerprint(folder_safe: str, key: str, fp: str, *, engine: str) -> None:
    with _grading_history_lock:
        if engine == "essay":
            data = _read_essay_history(folder_safe)
            triggers = data.setdefault("auto_report_triggers", {})
            if not isinstance(triggers, dict):
                triggers = {}
                data["auto_report_triggers"] = triggers
            triggers[key] = fp
            _write_essay_history(folder_safe, data)
        else:
            data = _read_grading_history(folder_safe, "default")
            triggers = data.setdefault("auto_report_triggers", {})
            if not isinstance(triggers, dict):
                triggers = {}
                data["auto_report_triggers"] = triggers
            triggers[key] = fp
            _write_grading_history(folder_safe, data, "default")


def _smart_scoring_fingerprint(folder_safe: str) -> str:
    history = _read_grading_history(folder_safe, "default")
    payload = collect_smart_scoring_payload(folder_safe)
    return _fingerprint(
        {
            "type": "smart_scoring",
            "history_updated_at": history.get("updated_at"),
            "student_count": payload.get("student_count"),
            "score_ranking": payload.get("score_ranking"),
            "scoring_config": payload.get("scoring_config"),
        }
    )


def _try_enqueue_smart_report(user_id: str, folder_safe: str) -> None:
    scored_count = count_scored_ref_papers(folder_safe)
    if scored_count <= 0:
        _log_skip("no_scored_papers", folder_safe)
        return

    fp = _smart_scoring_fingerprint(folder_safe)
    history = _read_grading_history(folder_safe, "default")
    if _read_trigger_fingerprint(history, "smart_scoring") == fp:
        _log_skip("duplicate_fingerprint", folder_safe, fp=fp)
        return

    payload = collect_smart_scoring_payload(folder_safe)
    display = _display_folder_name(folder_safe)
    student_count = int(payload.get("student_count") or payload.get("paper_count") or 0)
    title = f"{display} · 智能批改分析报告"
    user_message = (
        f"【自动分析】「{display}」已完成统分（共 {student_count} 名学生），"
        f"请根据已纳入分析的试卷数据生成简要考试报告。"
    )
    report_id = enqueue_report(
        user_id=user_id,
        folder_safe=folder_safe,
        folder_display=display,
        report_type="smart_scoring",
        title=title,
        user_message=user_message,
        payload=payload,
        fingerprint=fp,
    )
    if report_id:
        _save_trigger_fingerprint(folder_safe, "smart_scoring", fp, engine="default")
        print(f"[ai_auto_report] enqueued smart report id={report_id} folder={folder_safe!r} students={student_count} user={user_id!r}")
    else:
        print(f"[ai_auto_report] enqueue failed folder={folder_safe!r} user={user_id!r}")


def _try_enqueue_essay_report(user_id: str, folder_safe: str) -> None:
    if not _all_upload_files_graded_essay(folder_safe):
        return

    payload = collect_essay_payload(folder_safe)
    history = _read_essay_history(folder_safe)
    fp = _fingerprint(
        {
            "type": "essay",
            "history_updated_at": history.get("updated_at"),
            "files": _list_folder_upload_filenames(folder_safe),
            "paper_count": payload.get("paper_count"),
        }
    )
    if _read_trigger_fingerprint(history, "essay") == fp:
        _log_skip("duplicate_fingerprint", folder_safe, fp=fp)
        return

    display = _display_folder_name(folder_safe)
    title = f"{display} · 作文批改分析报告"
    user_message = f"【自动分析】已完成「{display}」全部作文批改，请生成班级作文分析报告。"
    report_id = enqueue_report(
        user_id=user_id,
        folder_safe=folder_safe,
        folder_display=display,
        report_type="essay",
        title=title,
        user_message=user_message,
        payload=payload,
        fingerprint=fp,
    )
    if report_id:
        _save_trigger_fingerprint(folder_safe, "essay", fp, engine="essay")
        print(f"[ai_auto_report] enqueued essay report id={report_id} folder={folder_safe!r} user={user_id!r}")


def schedule_smart_scoring_auto_report(user_id: str, folder_safe: str) -> None:
    """统分设置后尝试入队（只要有至少一份已统分试卷即可）。"""
    uid = sanitize_user_id(str(user_id or "").strip())
    safe = str(folder_safe or "").strip()
    if not uid or uid == "unknown" or not safe:
        print(f"[ai_auto_report] smart scoring skipped: invalid user/folder user={user_id!r} folder={folder_safe!r}")
        return
    try:
        _try_enqueue_smart_report(uid, safe)
    except Exception as e:
        print(f"[ai_auto_report] smart scoring trigger failed folder={safe!r}: {e}")


def schedule_essay_auto_report(user_id: str, folder_safe: str) -> None:
    uid = sanitize_user_id(str(user_id or "").strip())
    safe = str(folder_safe or "").strip()
    if not uid or uid == "unknown" or not safe:
        return
    try:
        _try_enqueue_essay_report(uid, safe)
    except Exception as e:
        print(f"[ai_auto_report] essay trigger failed folder={safe!r}: {e}")


def run_smart_scoring_auto_report_async(user_id: str, folder_safe: str) -> None:
    uid = str(user_id or "").strip()
    safe = str(folder_safe or "").strip()
    if not uid or not safe:
        return
    threading.Thread(
        target=lambda: run_with_grading_user(uid, schedule_smart_scoring_auto_report, uid, safe),
        daemon=True,
    ).start()


def run_essay_auto_report_async(user_id: str, folder_safe: str) -> None:
    uid = str(user_id or "").strip()
    safe = str(folder_safe or "").strip()
    if not uid or not safe:
        return
    threading.Thread(
        target=lambda: run_with_grading_user(uid, schedule_essay_auto_report, uid, safe),
        daemon=True,
    ).start()
