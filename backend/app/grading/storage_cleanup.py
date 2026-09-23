# -*- coding: utf-8 -*-
"""grading_data_{user_id} 垃圾清理：临时文件、孤儿留痕图、可再生的缓存等。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from app.grading.router import _batch_lock, _batch_results, _scan_watchers
from app.grading.user_paths import (
    get_user_grading_paths,
    project_root,
    reset_grading_user_id,
    set_grading_user_id,
)


def _human_bytes(num: int) -> str:
    size = float(max(0, int(num)))
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{int(num)} B"


def _safe_unlink(path: Path) -> int:
    try:
        if path.is_file():
            size = path.stat().st_size
            path.unlink()
            return size
    except Exception:
        pass
    return 0


def _extract_modify_filename(url: Any) -> str:
    if not isinstance(url, str) or "/grading/modify/" not in url:
        return ""
    name = url.split("/grading/modify/")[-1]
    return name.split("?")[0].split("#")[0].strip()


def _extract_home_img_filename(url: Any) -> str:
    if not isinstance(url, str) or "/grading/home_img/" not in url:
        return ""
    name = url.split("/grading/home_img/")[-1]
    return name.split("?")[0].split("#")[0].strip()


def _walk_modify_refs(obj: Any, refs: set[str]) -> None:
    if isinstance(obj, dict):
        for key in ("image_original", "image_annotated", "image_marks_only"):
            fn = _extract_modify_filename(obj.get(key))
            if fn:
                refs.add(fn)
        for value in obj.values():
            _walk_modify_refs(value, refs)
    elif isinstance(obj, list):
        for item in obj:
            _walk_modify_refs(item, refs)
    elif isinstance(obj, str):
        fn = _extract_modify_filename(obj)
        if fn:
            refs.add(fn)


def _collect_modify_references(paths) -> set[str]:
    refs: set[str] = set()
    history_dir = paths.grading_history
    home_dir = paths.home_img

    if history_dir.is_dir():
        for path in history_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict):
                _walk_modify_refs(data, refs)

    if home_dir.is_dir():
        for path in home_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict):
                _walk_modify_refs(data, refs)

    with _batch_lock:
        for data in _batch_results.values():
            if not isinstance(data, dict):
                continue
            for item in data.get("completed") or []:
                if isinstance(item, dict):
                    _walk_modify_refs(item, refs)

    return refs


def _collect_home_img_references(paths) -> set[str]:
    refs: set[str] = set()
    home_dir = paths.home_img
    if not home_dir.is_dir():
        return refs
    for path in home_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        rid = str(data.get("id") or path.stem).strip()
        if rid:
            refs.add(f"{rid}.json")
        for key in ("image_original", "image_annotated", "image_marks_only", "upload_filename"):
            url = data.get(key)
            if isinstance(url, str):
                if url.startswith("/"):
                    fn = _extract_home_img_filename(url)
                else:
                    fn = url.split("?")[0].split("#")[0].strip()
                if fn:
                    refs.add(fn)
        files = data.get("files")
        if isinstance(files, dict):
            for value in files.values():
                if isinstance(value, str) and value:
                    refs.add(value.split("?")[0].split("#")[0].strip())
    return refs


def _cleanup_all_files(
    directory: Path,
    *,
    exclude_names: Optional[set[str]] = None,
    recursive: bool = False,
) -> dict[str, int]:
    deleted_files = 0
    freed_bytes = 0
    if not directory.is_dir():
        return {"files": 0, "bytes": 0}
    exclude = exclude_names or set()
    iterator = directory.rglob("*") if recursive else directory.iterdir()
    for path in iterator:
        if not path.is_file():
            continue
        if path.name in exclude:
            continue
        try:
            freed_bytes += _safe_unlink(path)
            deleted_files += 1
        except Exception:
            continue
    return {"files": deleted_files, "bytes": freed_bytes}


def _cleanup_orphan_files(directory: Path, referenced: set[str]) -> dict[str, int]:
    deleted_files = 0
    freed_bytes = 0
    if not directory.is_dir():
        return {"files": 0, "bytes": 0}
    for path in directory.iterdir():
        if not path.is_file():
            continue
        if path.name in referenced:
            continue
        freed_bytes += _safe_unlink(path)
        deleted_files += 1
    return {"files": deleted_files, "bytes": freed_bytes}


def _scan_import_running_for_user(user_id: str) -> bool:
    state = _scan_watchers.get(user_id) or {}
    return bool(state.get("running"))


def run_grading_data_cleanup(user_id: str) -> dict[str, Any]:
    """清理当前用户 grading_data_{user_id} 中可安全删除的文件。"""
    token = set_grading_user_id(user_id)
    try:
        paths = get_user_grading_paths(user_id)
        details: dict[str, dict[str, int]] = {}
        skipped: list[str] = []
        total_files = 0
        total_bytes = 0

        def _add(category: str, stat: dict[str, int]) -> None:
            nonlocal total_files, total_bytes
            details[category] = stat
            total_files += int(stat.get("files") or 0)
            total_bytes += int(stat.get("bytes") or 0)

        _add("temp", _cleanup_all_files(paths.temp))

        _add("project_temp", _cleanup_all_files(project_root() / "temp"))

        if _scan_import_running_for_user(user_id):
            details["scan"] = {"files": 0, "bytes": 0}
            skipped.append("scan")
        else:
            _add("scan", _cleanup_all_files(paths.scan))

        modify_refs = _collect_modify_references(paths)
        _add("modify_orphans", _cleanup_orphan_files(paths.modify, modify_refs))

        home_refs = _collect_home_img_references(paths)
        _add("home_img_orphans", _cleanup_orphan_files(paths.home_img, home_refs))

        _add("ai_diagnosis", _cleanup_all_files(paths.ai_diagnosis))

        _add("history_legacy", _cleanup_all_files(paths.history_legacy))

        result: dict[str, Any] = {
            "ok": True,
            "freed_bytes": total_bytes,
            "freed_bytes_human": _human_bytes(total_bytes),
            "deleted_files": total_files,
            "details": details,
        }
        if skipped:
            result["skipped"] = skipped
        return result
    finally:
        reset_grading_user_id(token)
