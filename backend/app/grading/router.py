# -*- coding: utf-8 -*-
"""批改 API：快速批改、批量批改、参照批改（文件夹 + 标准答案）、扫描导入。"""
import os
import sys
import json
import uuid
import threading
import shutil
import time
import re
import copy
import traceback
from urllib.parse import quote
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

import requests
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request, Body, Depends, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.response_log import ResponseLog
from app.models.user import User
from app.schemas.common import ApiResponse
from app.utils.security import verify_password, build_download_url, create_download_ticket
from app.utils.qwen_settings import get_llm_config, get_llm_thinking_extra, get_qwen_config, get_vl_model
from app.dependencies import get_current_user_id, bind_grading_user_context
from app.grading.file_auth import user_id_from_request
from app.grading.pipeline import (
    real_grade_pipeline,
    real_grade_pipeline_by_reference,
    prepare_standard_answer_for_reference,
    draw_real_marks_and_save,
    draw_marks_only_and_save,
)
from app.grading.baidu_grading import (
    baidu_grade_single,
    baidu_grade_batch,
    draw_baidu_marks_and_save,
    extract_baidu_image_direction,
)
from app.grading.doc_convert import normalize_uploaded_image_orientation
from app.grading.essay_text_layout import fix_punctuation_line_starts
from app.grading.reference_vlm_grading import (
    build_reference_vlm_slot_template,
    crop_reference_answer_table_region,
    load_or_build_reference_answer_table,
    build_reference_layout_page,
    confirm_reference_layout,
    delete_reference_layout,
    draw_reference_vlm_marks_and_save,
    get_confirmed_reference_document,
    grade_reference_vlm_paper,
    invalidate_reference_answer_table,
    clear_answer_sheet_cache,
    load_or_build_answer_sheet_texts,
    load_reference_layout,
    load_reference_layout_for_editing,
    read_answer_sheet_texts,
    read_reference_answer_table_page,
    recognize_reference_vlm_batch,
    reference_layout_status,
    save_answer_sheet_texts,
    save_reference_answer_table_edits,
    save_reference_layout_prepare,
)
from app.grading.manual_grading import (
    _baidu_ocr_text,
    aggregate_manual_layout_pages,
    apply_paper_scores_to_page,
    baidu_paper_cut,
    build_manual_layout_page,
    build_manual_layout_page_from_boxes,
    build_manual_layout_page_from_reference_layout,
    confirm_manual_layout,
    delete_manual_layout,
    load_manual_layout_for_editing,
    load_paper_scores,
    manual_layout_blocks_for_image,
    manual_layout_status,
    save_manual_layout_prepare,
    save_paper_scores,
)
from app.grading.answer_card_boxes import detect_answer_card_boxes
from app.grading.answer_key_grading import (
    extract_answer_key_text_from_document,
    extract_answer_key_text_from_image,
    grade_paper_by_answer_key,
    parse_answer_key_text,
)
from app.grading.quota_gate import quota_gate
from app.grading.user_paths import (
    correct_docs_dir,
    correct_docs_img_dir,
    get_grading_user_id,
    get_user_grading_paths,
    grading_history_dir,
    home_img_dir,
    modify_dir,
    reset_grading_user_id,
    run_with_grading_user,
    scan_dir,
    set_grading_user_id,
    test_dir,
)

_home_img_lock = threading.Lock()
_home_quick_lock = threading.Lock()
_home_quick_jobs: dict[str, dict] = {}
_home_quick_stop_events: dict[str, threading.Event] = {}

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
_PDF_EXTS = {".pdf"}
_WORD_EXTS = {".doc", ".docx"}
_ALL_UPLOAD_EXTS = _IMAGE_EXTS | _PDF_EXTS | _WORD_EXTS
_batch_results = {}
_batch_lock = threading.Lock()
_ref_grade_results = {}
_ref_grade_lock = threading.Lock()
# 一键批改停止：job_id -> Event，set 后未开始的任务跳过，百度轮询中会中断
_ref_grade_stop_events: dict[str, threading.Event] = {}
_grading_history_lock = threading.Lock()


# ---- M1/M5：内存任务归属校验 + 打印/扫描权限 ----
def _assert_job_owner(job: dict) -> None:
    """M1：内存任务按用户隔离——非本人创建的 job 一律视为不存在（防 IDOR 越权）。"""
    owner = job.get("user_id")
    if owner and owner != get_grading_user_id():
        raise HTTPException(status_code=404, detail="任务不存在或已过期")


def _require_local_admin(request: Optional[Request], db: Session) -> str:
    """M5：打印/扫描仅允许本机来源（127.0.0.1/::1）；不再按角色限制（本机登录的教师均可打印）。"""
    if request is not None:
        host = (request.client.host if request.client else "") or ""
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise HTTPException(status_code=403, detail="仅允许从本机执行打印/扫描操作")
    return get_grading_user_id()

# 错题库写入（含可选 AI 分析）放到后台，避免阻塞智能模型批改主流程
_wrong_question_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="wq-upsert")

# 批改后自动导入学情+自动分层（客户清单 #1）：独立线程池，避免被错题库/LLM 任务堵住
_auto_sync_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="auto-class-sync")
# 同文件夹合并触发：跑的期间又有落盘则跑完再补一轮（保证最后一次落盘不丢）
_auto_sync_state: dict[str, dict] = {}
_auto_sync_state_lock = threading.Lock()


def _baidu_ref_grade_workers() -> int:
    return max(1, min(32, int(os.environ.get("BAIDU_GRADE_WORKERS", "16"))))


def _find_active_ref_job_locked(
    safe: str,
    *,
    engine: str,
    only_filename: Optional[str],
    only_filenames: Optional[set],
    user_id: Optional[str],
) -> Optional[tuple[str, bool]]:
    """1015 冻死防线：同文件夹参照批改单飞闸。返回 (job_id, same_scope)。

    【调用方必须持有 _ref_grade_lock】——闸门检查和任务注册必须在同一临界区
    内完成，否则「检查→清历史→注册」之间可挤进第二个请求（TOCTOU）。

    同文件夹已有未完成任务时：参数完全一致 → same_scope=True（前端连点可幂等
    返回在跑的 job_id）；参数/用户不一致 → 调用方应 409，绝不允许双批次并行
    （2026-10-15 两次连点各 8 线程整页 base64 把 8G 内存顶穿致整机僵死）。
    """
    target_names = sorted(only_filenames) if only_filenames else None
    for job_id, res in _ref_grade_results.items():
        if res.get("done") or res.get("folder") != safe:
            continue
        job_names = res.get("only_filenames")
        same_scope = (
            res.get("user_id") == user_id
            and str(res.get("engine") or "") == engine
            and (res.get("only_filename") or None) == (only_filename or None)
            and (sorted(job_names) if job_names else None) == target_names
        )
        return job_id, same_scope
    return None


def _paper_result_key(name: str) -> str:
    return str(name or "").strip()


def _fail_ref_paper_item(
    job_id: str,
    index: int,
    original_name: str,
    folder_safe: str,
    engine: str,
    msg: str,
) -> None:
    """将单张试卷标记为失败，并从 in_progress 移除（避免任务永远卡住）。"""
    with _ref_grade_lock:
        if job_id not in _ref_grade_results:
            return
        res = _ref_grade_results[job_id]
        done_names = {x.get("name") for x in res.get("completed", [])} | {x.get("name") for x in res.get("failed", [])}
        if original_name not in done_names:
            res["failed"].append({"index": index, "name": original_name, "msg": msg})
        in_progress = res.setdefault("in_progress", [])
        if original_name in in_progress:
            in_progress.remove(original_name)
    _persist_grading_failure(folder_safe, original_name, msg, engine)


def _sweep_ref_in_progress(
    job_id: str,
    folder_safe: str,
    engine: str,
    student_orig_list: list,
    msg: str = "批改未完成，请重试",
) -> None:
    """收尾：仍在 in_progress 的试卷一律记为失败，防止前端一直转圈。"""
    with _ref_grade_lock:
        if job_id not in _ref_grade_results:
            return
        stuck = list(_ref_grade_results[job_id].get("in_progress", []))
    if not stuck:
        return
    idx_by_key = {_paper_result_key(o.name): (i, o) for i, o in enumerate(student_orig_list)}
    for name in stuck:
        pair = idx_by_key.get(_paper_result_key(name))
        if pair:
            i, orig = pair
            _fail_ref_paper_item(job_id, i, orig.name, folder_safe, engine, msg)
        else:
            with _ref_grade_lock:
                if job_id not in _ref_grade_results:
                    continue
                res = _ref_grade_results[job_id]
                if name not in {x.get("name") for x in res.get("completed", [])} | {x.get("name") for x in res.get("failed", [])}:
                    res["failed"].append({"name": name, "msg": msg})
                in_progress = res.setdefault("in_progress", [])
                if name in in_progress:
                    in_progress.remove(name)
            _persist_grading_failure(folder_safe, name, msg, engine)


def _baidu_batch_item_key(index: int, filename: str) -> str:
    return f"{index}:{_paper_result_key(filename)}"


def _reconcile_missing_baidu_papers(
    job_id: str,
    folder_safe: str,
    engine: str,
    student_files: list,
    student_orig_list: list,
    ctx_uid: str,
    process_one_fn,
) -> None:
    """补批：凡未进入 completed/failed 的试卷，同步走 process_one（单张百度+留痕）。"""
    def _done_names() -> set:
        with _ref_grade_lock:
            if job_id not in _ref_grade_results:
                return set()
            res = _ref_grade_results[job_id]
            return {x.get("name") for x in res.get("completed", [])} | {
                x.get("name") for x in res.get("failed", [])
            }

    missing = [
        (i, sf, orig)
        for i, (sf, orig) in enumerate(zip(student_files, student_orig_list))
        if orig.name not in _done_names()
    ]
    if not missing:
        return
    for i, sf, orig in missing:
        print(f"补批遗漏试卷 [{orig.name}]（index={i}）")
        try:
            run_with_grading_user(ctx_uid, process_one_fn, (i, (sf, orig)))
        except Exception as e:
            print(f"补批失败 [{orig.name}]: {e}")
            _fail_ref_paper_item(job_id, i, orig.name, folder_safe, engine, str(e))
            continue
        if orig.name not in _done_names():
            _fail_ref_paper_item(
                job_id,
                i,
                orig.name,
                folder_safe,
                engine,
                "补批后仍未完成，请重试",
            )


def _schedule_baidu_wrong_question_upsert(
    user_id: str,
    folder_safe: str,
    paper_name: str,
    raw_result: dict,
    blocks_with_result: list,
    source_image_path: str,
) -> None:
    """异步写入错题库；批改线程立即返回，AI 分析在后台完成。"""
    raw_copy = copy.deepcopy(raw_result or {})
    blocks_copy = copy.deepcopy(blocks_with_result or [])
    img_path = str(source_image_path or "")

    def _run() -> None:
        try:
            from app.grading.wrong_question_db import upsert_baidu_wrong_questions

            upsert_baidu_wrong_questions(
                folder_safe=folder_safe,
                paper_name=paper_name,
                raw_result=raw_copy,
                blocks_with_result=blocks_copy,
                source_image_path=img_path,
            )
        except Exception as e:
            print(f"智能模型批改错题库生成失败: {folder_safe}/{paper_name}: {e}")

    _wrong_question_executor.submit(run_with_grading_user, user_id, _run)


def _schedule_response_log_write(
    user_id: str,
    folder_safe: str,
    paper_name: str,
    engine: str,
    blocks_with_result: list,
) -> None:
    """R1 逐题响应日志：异步旁路写入；批改线程立即返回，绝不阻断批改。"""
    if engine not in ("baidu", "smart_ref", "aliyun", "manual"):
        return

    def _run() -> None:
        try:
            from app.grading.response_log_db import write_response_logs

            write_response_logs(
                user_id,
                folder_safe,
                paper_name,
                engine,
                copy.deepcopy(blocks_with_result or []),
            )
        except Exception as e:
            print(f"逐题响应日志写入失败: {folder_safe}/{paper_name}: {e}")

    _wrong_question_executor.submit(run_with_grading_user, user_id, _run)


def _schedule_wrong_annotation_generation(
    user_id: str,
    folder_safe: str,
    paper_name: str,
    engine: str,
    blocks_with_result: list,
    source_image_path: str = "",
) -> None:
    """批改完成后异步为错/半对的题生成「为什么错」批注；绝不阻断批改主流程。

    生成结果写回 grading_history item 的 wrong_annotations（edited/manual 条目不覆盖）。
    """

    def _run() -> None:
        try:
            from app.grading.wrong_annotations import generate_wrong_annotations_for_blocks

            with _grading_history_lock:
                data = _read_grading_history(folder_safe, engine)
                item = (data.get("completed") or {}).get(paper_name)
            if not isinstance(item, dict):
                return
            generated = generate_wrong_annotations_for_blocks(
                blocks_with_result or item.get("blocks") or [],
                source_image_path=source_image_path,
                existing=item.get("wrong_annotations"),
            )
            if not generated:
                return
            with _grading_history_lock:
                data = _read_grading_history(folder_safe, engine)
                item = (data.get("completed") or {}).get(paper_name)
                if not isinstance(item, dict):
                    return
                merged = dict(item.get("wrong_annotations") or {})
                merged.update(generated)
                item["wrong_annotations"] = merged
                _regenerate_wrong_annotation_marks(
                    folder_safe,
                    item,
                    blocks_with_result or item.get("blocks") or [],
                    merged,
                )
                data["completed"][paper_name] = item
                _write_grading_history(folder_safe, data, engine)
        except Exception as e:
            print(f"判错批注生成失败: {folder_safe}/{paper_name}: {e}")

    _wrong_question_executor.submit(run_with_grading_user, user_id, _run)


def _schedule_auto_sync_class(user_id: str, folder_safe: str) -> None:
    """批改落盘后异步：成绩导入学情（成绩历史/当前分/错题）→ 按成绩自动分层。

    同文件夹合并触发（一批 N 张不跑 N 次）；跑的期间再有落盘则跑完补一轮。
    绝不阻断批改主流程；非班级文件夹在 worker 里静默跳过。
    """
    if not user_id or not folder_safe:
        return
    with _auto_sync_state_lock:
        st = _auto_sync_state.setdefault(folder_safe, {"running": False, "dirty": False})
        if st["running"]:
            st["dirty"] = True
            return
        st["running"] = True

    def _run() -> None:
        from app.services.auto_class_sync import auto_sync_folder_after_grading

        try:
            while True:
                with _auto_sync_state_lock:
                    st = _auto_sync_state[folder_safe]
                    st["dirty"] = False
                try:
                    summary = auto_sync_folder_after_grading(user_id, folder_safe)
                    if summary and not summary.get("skipped"):
                        print(
                            f"[auto_class_sync] {folder_safe}: 导入 {summary.get('students')} 人"
                            f"/分层更新 {summary.get('tier_updated')} 人"
                        )
                except Exception as e:
                    print(f"[auto_class_sync] 失败: {folder_safe}: {e}")
                with _auto_sync_state_lock:
                    st = _auto_sync_state[folder_safe]
                    if st["dirty"]:
                        continue
                    st["running"] = False
                    break
        except BaseException:
            with _auto_sync_state_lock:
                st = _auto_sync_state.get(folder_safe)
                if st is not None:
                    st["running"] = False
            raise

    _auto_sync_executor.submit(run_with_grading_user, user_id, _run)


_print_batch_lock = threading.Lock()
_print_batch_jobs: dict[str, dict] = {}
_print_batch_stop_events: dict[str, threading.Event] = {}
_PRINT_BATCH_GAP_SEC = 0.25

# 作文批改（独立逻辑）：job_id -> data
_essay_grade_lock = threading.Lock()
_essay_grade_results: dict[str, dict] = {}
_essay_grade_stop_events: dict[str, threading.Event] = {}
_essay_history_lock = threading.Lock()


def _paper_box_display_name(filename: str) -> str:
    stem = Path(str(filename or "")).stem
    match = re.match(r"^(?P<name>.+)_\d+$", stem)
    return (match.group("name") if match else stem) or stem


def _paper_box_page_no(filename: str) -> int:
    stem = Path(str(filename or "")).stem
    match = re.match(r"^.+_(?P<page>\d+)$", stem)
    if not match:
        return 1
    try:
        return max(1, int(match.group("page")))
    except Exception:
        return 1


_STANDARD_ANSWER_STEM_RE = re.compile(r"^标准答案(?:_(?P<page>\d+))?$")


def _standard_answer_page_no(filename: str) -> Optional[int]:
    stem = Path(str(filename or "")).stem
    match = _STANDARD_ANSWER_STEM_RE.fullmatch(stem)
    if not match:
        return None
    try:
        return max(1, int(match.group("page") or "1"))
    except Exception:
        return None


def _is_standard_answer_filename(filename: str) -> bool:
    return _standard_answer_page_no(filename) is not None


_ORIGINAL_PAPER_STEM_RE = re.compile(r"^(?:原始试卷|原卷|试卷)(?:_(?P<page>\d+))?$")


def _original_paper_page_no(filename: str) -> Optional[int]:
    stem = Path(str(filename or "")).stem
    match = _ORIGINAL_PAPER_STEM_RE.fullmatch(stem)
    if not match:
        return None
    try:
        return max(1, int(match.group("page") or "1"))
    except Exception:
        return None


def _is_original_paper_filename(filename: str) -> bool:
    return _original_paper_page_no(filename) is not None


# 答案纸（答案单独一张纸，空白卷模式第二上传）：只认「答案[_N]」，与
# 「标准答案[_N]」「原始试卷[_N]」三足鼎立，不抢后者职责。
_ANSWER_SHEET_STEM_RE = re.compile(r"^答案(?:_(?P<page>\d+))?$")


def _answer_sheet_page_no(filename: str) -> Optional[int]:
    stem = Path(str(filename or "")).stem
    match = _ANSWER_SHEET_STEM_RE.fullmatch(stem)
    if not match:
        return None
    try:
        return max(1, int(match.group("page") or "1"))
    except Exception:
        return None


def _is_answer_sheet_filename(filename: str) -> bool:
    return _answer_sheet_page_no(filename) is not None


def _original_paper_sources(folder_safe: str) -> dict[int, tuple[Path, Path]]:
    """收集已上传的原始试卷所有页（用于识别每题分值），按页号分组。PDF 全页转换。"""
    result: dict[int, tuple[Path, Path]] = {}
    directory = correct_docs_dir() / folder_safe
    if not directory.is_dir():
        return result
    for path in sorted(directory.iterdir(), key=lambda p: p.name):
        if not path.is_file() or path.suffix.lower() not in _ALL_UPLOAD_EXTS:
            continue
        base_page = _original_paper_page_no(path.name)
        if base_page is None:
            continue
        ext = path.suffix.lower()
        if ext == ".pdf":
            for i, img_path in enumerate(_pdf_all_pages_to_images(path, folder_safe), start=1):
                result.setdefault(base_page + i - 1, (path, Path(img_path)))
        elif ext in _IMAGE_EXTS:
            grading_path = _ensure_img_in_folder(path, folder_safe) or path
            result.setdefault(base_page, (path, Path(grading_path)))
        else:  # .doc / .docx：OCR 读分不支持，保留原文件（OCR 会失败并跳过）
            result.setdefault(base_page, (path, path))
    return result


def _reference_standard_document(
    page_no: int, confirmed_documents_by_page: dict[int, object]
) -> object:
    """Return the confirmed standard-answer layout used for one student page."""
    return confirmed_documents_by_page.get(page_no) or {}


def _home_record_path(job_id: str) -> Path:
    return home_img_dir() / f"{job_id}.json"


def _safe_unlink(p: Path) -> None:
    try:
        if p.is_file():
            p.unlink()
    except Exception:
        pass


def _img_name_from_url(url: Optional[str]) -> str:
    # Stored preview URLs carry cache-busting / download-ticket queries such as
    # ?t=123 or ?ticket=<JWT>. The filesystem name must be extracted before the
    # query, otherwise the "name" is hundreds of bytes and Path.is_file() raises
    # OSError: File name too long (ENAMETOOLONG).
    if not url:
        return ""
    name = str(url).split("?", 1)[0].split("#", 1)[0].rsplit("/", 1)[-1]
    # Path("..").name == ".."，点段要单独拦，不能只靠 Path(name).name != name；
    # 反斜杠在 Linux 上是合法文件名字符、Windows 上是分隔符，为跨平台一致直接拒。
    if not name or name in (".", "..") or "\\" in name or Path(name).name != name:
        return ""
    return name


def _home_delete_by_record(record: dict) -> None:
    files = []
    if isinstance(record.get("files"), dict):
        for v in record["files"].values():
            if isinstance(v, str) and v:
                files.append(v)
    for key in ["image_original", "image_annotated", "image_marks_only"]:
        url = record.get(key)
        if isinstance(url, str) and url.startswith("/api/v1/grading/home_img/"):
            img_name = _img_name_from_url(url)
            if img_name:
                files.append(img_name)
    if isinstance(record.get("upload_filename"), str):
        files.append(record["upload_filename"])
    files.append(f"{record.get('id')}.json")

    for name in set(files):
        _safe_unlink(home_img_dir() / name)

    rid = record.get("id")
    if isinstance(rid, str) and rid:
        try:
            ev = _home_quick_stop_events.get(rid)
            if ev:
                ev.set()
        except Exception:
            pass
        try:
            _home_quick_jobs.pop(rid, None)
        except Exception:
            pass


def _cleanup_home_img_records(keep: int = 10) -> None:
    try:
        json_files = sorted(
            [p for p in home_img_dir().glob("*.json") if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        return
    if len(json_files) <= keep:
        return
    for p in json_files[keep:]:
        try:
            record = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(record, dict):
                _home_delete_by_record(record)
            else:
                _safe_unlink(p)
        except Exception:
            _safe_unlink(p)


def _home_update_record(job_id: str, patch: dict) -> None:
    p = _home_record_path(job_id)
    try:
        rec = {}
        if p.is_file():
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
                if not isinstance(rec, dict):
                    rec = {}
            except Exception:
                rec = {}
        rec.update(patch or {})
        p.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _run_home_quick_job(job_id: str, img_path: Path, standard_path: Optional[Path], display_name: str, user_id: str) -> None:
    set_grading_user_id(user_id)
    stop_ev = _home_quick_stop_events.get(job_id)
    try:
        _home_update_record(job_id, {"status": "running", "progress": 15, "message": "开始批改…"})
        grade_path = img_path
        try:
            if stop_ev and stop_ev.is_set():
                _home_update_record(job_id, {"status": "cancelled", "progress": 100, "message": "已取消"})
                return
            if standard_path is not None and standard_path.is_file():
                # 参照批改：百度切题 + 千问对照标准答案逐题复核（与网页版同款引擎）
                from app.grading.pipeline import real_grade_pipeline_smart_ref
                result, blocks_with_result, baidu_raw, _ = real_grade_pipeline_smart_ref(
                    str(standard_path), str(grade_path), stop_event=stop_ev
                )
            else:
                # 无答案卷：百度盲批 + 补全漏切的主观题/作文
                result, blocks_with_result, baidu_raw = baidu_grade_single(str(grade_path), stop_event=stop_ev)
                try:
                    result, blocks_with_result = _supplement_baidu_grading(
                        None, grade_path, result, blocks_with_result
                    )
                except Exception:
                    pass
        except Exception as e:
            if stop_ev and stop_ev.is_set():
                _home_update_record(job_id, {"status": "cancelled", "progress": 100, "message": "已取消"})
                return
            raise e

        _home_update_record(job_id, {"status": "rendering", "progress": 85, "message": "生成留痕…"})
        image_original = image_annotated = image_marks_only = None
        orig_name = ann_name = marks_only_name = None
        if blocks_with_result:
            try:
                # 留痕前：视觉读整卷每题满分，逐题算得分（对=满分/错=0），让卷面在 √/× 旁标出分数
                try:
                    _attach_scores_to_blocks(None, img_path, result, blocks_with_result)
                except Exception:
                    pass
                orig_name, ann_name, marks_only_name = draw_baidu_marks_and_save(
                    str(img_path), blocks_with_result, baidu_raw, str(home_img_dir()), job_id
                )
                image_original = build_download_url(f"grading/home_img/{orig_name}", user_id)
                image_annotated = build_download_url(f"grading/home_img/{ann_name}", user_id)
                image_marks_only = build_download_url(f"grading/home_img/{marks_only_name}", user_id)
            except Exception:
                pass

        _home_update_record(
            job_id,
            {
                "ok": True,
                "status": "done",
                "progress": 100,
                "message": "完成",
                "result": result or "",
                "blocks": blocks_with_result or [],
                "image_original": image_original,
                "image_annotated": image_annotated,
                "image_marks_only": image_marks_only,
                "files": {
                    "upload": img_path.name,
                    "image_original": orig_name,
                    "image_annotated": ann_name,
                    "image_marks_only": marks_only_name,
                    "json": f"{job_id}.json",
                },
            },
        )

        # 判错批注：批完后异步补「为什么错」，写回作业记录（不阻塞快速批改）
        if blocks_with_result:
            def _gen_home_wrong(
                _blocks=list(blocks_with_result),
                _img=str(img_path),
                _uid=user_id,
                _job=job_id,
            ) -> None:
                try:
                    from app.grading.wrong_annotations import (
                        generate_wrong_annotations_for_blocks,
                        normalize_wrong_annotations,
                    )

                    generated = generate_wrong_annotations_for_blocks(
                        _blocks, source_image_path=_img
                    )
                    if not generated:
                        return
                    p = _home_record_path(_job)
                    rec = {}
                    if p.is_file():
                        try:
                            rec = json.loads(p.read_text(encoding="utf-8"))
                        except Exception:
                            rec = {}
                    merged = normalize_wrong_annotations(rec.get("wrong_annotations"))
                    merged.update(generated)
                    _home_update_record(_job, {"wrong_annotations": merged})
                except Exception as e:
                    print(f"首页判错批注生成失败: {job_id}: {e}")

            _wrong_question_executor.submit(
                run_with_grading_user, user_id, _gen_home_wrong
            )
    except Exception as e0:
        _home_update_record(
            job_id,
            {
                "ok": False,
                "status": "failed",
                "progress": 100,
                "message": str(e0) or "批改失败",
            },
        )
    finally:
        with _home_img_lock:
            _cleanup_home_img_records(keep=10)


# A2-B2 局部重批内部字段：仅用于改分端点复用配置，对外不暴露（避免 base64/长文本撑爆历史响应）。
_ESSAY_INTERNAL_FIELDS = ("rubric_text", "prompts", "dimensions")


def _essay_history_path(safe: str) -> Path:
    return grading_history_dir() / f"{safe}__essay.json"


def _read_essay_history(safe: str) -> dict:
    p = _essay_history_path(safe)
    if not p.is_file():
        return {"version": 1, "completed": {}, "failed": {}}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data.get("completed"), dict):
            data["completed"] = {}
        if not isinstance(data.get("failed"), dict):
            data["failed"] = {}
        return data
    except Exception:
        return {"version": 1, "completed": {}, "failed": {}}


def _write_essay_history(safe: str, data: dict) -> None:
    data["version"] = 1
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    # 整卷总分持久化（客户清单 #7）：作文整卷语义（多页重复总分取最大）一并落 box_totals
    try:
        data["box_totals"] = _compute_box_totals_snapshot(safe, "essay", data)
    except Exception:
        pass
    p = _essay_history_path(safe)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _persist_essay_success(safe: str, item: dict) -> None:
    name = item.get("name")
    if not name:
        return
    store = {k: v for k, v in item.items() if k != "index"}
    old_entry: Optional[dict] = None
    with _essay_history_lock:
        data = _read_essay_history(safe)
        prev = (data.get("completed") or {}).get(name)
        if isinstance(prev, dict):
            old_entry = dict(prev)
        data["completed"][name] = store
        data["failed"].pop(name, None)
        _write_essay_history(safe, data)
    try:
        from app.grading.grading_stats import record_graded_state_change

        record_graded_state_change(
            get_grading_user_id(), safe, old_entry, store, source="essay", filename=name
        )
    except Exception:
        pass
    # 作文批改落盘 → 同样自动导入学情+自动分层（客户清单 #1/#7；整卷总分语义见 box_totals）
    try:
        _schedule_auto_sync_class(get_grading_user_id(), safe)
    except Exception:
        pass


def _persist_essay_failure(safe: str, name: str, msg: str) -> None:
    if not name:
        return
    with _essay_history_lock:
        data = _read_essay_history(safe)
        data["failed"][name] = {"name": name, "msg": msg or "批改失败"}
        _write_essay_history(safe, data)


def _get_completed_names_from_essay_history(safe: str) -> set[str]:
    with _essay_history_lock:
        data = _read_essay_history(safe)
    completed = data.get("completed", {})
    if isinstance(completed, dict):
        return set(str(k) for k in completed.keys())
    return set()


def _remove_essay_history_entry(safe: str, filename: str) -> None:
    with _essay_history_lock:
        data = _read_essay_history(safe)
        
        # 尝试删除 modify 文件夹中残留的图片
        entry = data["completed"].get(filename)
        if entry and isinstance(entry, dict):
            for key in ["image_original", "image_annotated", "image_marks_only"]:
                _delete_modify_file_by_url(entry.get(key))

        data["completed"].pop(filename, None)
        data["failed"].pop(filename, None)
        _write_essay_history(safe, data)


def _rename_essay_history_entry(safe: str, old_filename: str, new_filename: str) -> None:
    if not old_filename or not new_filename or old_filename == new_filename:
        return
    with _essay_history_lock:
        data = _read_essay_history(safe)
        changed = False
        completed = data.get("completed", {})
        if isinstance(completed, dict) and old_filename in completed:
            item = completed.pop(old_filename)
            if isinstance(item, dict):
                item["name"] = new_filename
            completed[new_filename] = item
            changed = True
        failed = data.get("failed", {})
        if isinstance(failed, dict) and old_filename in failed:
            item = failed.pop(old_filename)
            if isinstance(item, dict):
                item["name"] = new_filename
            failed[new_filename] = item
            changed = True
        if changed:
            _write_essay_history(safe, data)


def _essay_preview_image_path(folder_safe: str, filename: str) -> Optional[Path]:
    """作文预览图：优先用 test_paper_img 的图片（PDF/Word 已转成 jpg），否则返回 None。"""
    try:
        orig_path = (correct_docs_dir() / folder_safe / filename)
        if not orig_path.is_file():
            return None
        gp = _ensure_img_in_folder(orig_path, folder_safe) or orig_path
        img_path = _get_grading_path(folder_safe, orig_path) or gp
        if img_path and Path(img_path).is_file():
            return Path(img_path)
    except Exception:
        return None
    return None

_ALLOWED_PAPER_SIZES = frozenset({"default", "a3", "a4", "a5", "b4", "b5", "letter", "legal", "tabloid", "custom"})


def _parse_paper_size(body: dict) -> str:
    """请求体中的 paper_size；缺省为 a4，非法值返回 400。"""
    raw = body.get("paper_size")
    if raw is None:
        return "a4"
    s = str(raw).strip().lower()
    if not s:
        return "a4"
    if s not in _ALLOWED_PAPER_SIZES:
        raise HTTPException(
            status_code=400,
            detail="paper_size 无效，请使用 default、a3、a4、a5、b4、b5、letter、legal、tabloid、custom",
        )
    return s


def _parse_custom_paper_mm(body: dict, paper_size: str) -> Optional[tuple[float, float]]:
    """paper_size=custom 时解析并校验用户自定义纸张尺寸（mm）。"""
    if paper_size != "custom":
        return None
    raw_w = body.get("custom_paper_width_mm")
    raw_h = body.get("custom_paper_height_mm")
    try:
        w = float(raw_w)
        h = float(raw_h)
    except Exception:
        raise HTTPException(status_code=400, detail="自定义纸张尺寸无效，请填写数字（单位 mm）")
    # 给出较宽的安全区间，避免驱动拒绝极端值
    if not (50.0 <= w <= 1200.0 and 50.0 <= h <= 1200.0):
        raise HTTPException(status_code=400, detail="自定义纸张尺寸范围应在 50~1200 mm")
    return (w, h)


def _parse_paper_source(body: dict) -> Optional[int]:
    raw = body.get("paper_source")
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw > 0 else None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            v = int(s)
        except Exception:
            raise HTTPException(status_code=400, detail="paper_source 无效，请传入纸盒 id（整数）")
        return v if v > 0 else None
    raise HTTPException(status_code=400, detail="paper_source 无效，请传入纸盒 id（整数）")


# 扫描导入：监测 scan 目录并复制新 PDF 到目标文件夹（按用户隔离）
_scan_watchers: dict[str, dict] = {}
_scan_watcher_lock = threading.Lock()
_SCAN_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".bmp")


def _scan_state(user_id: str) -> dict:
    if user_id not in _scan_watchers:
        _scan_watchers[user_id] = {
            "running": False,
            "target_folder": None,
            "thread": None,
            "stop_event": None,
            "imported_count": 0,
            "error": False,
            "error_message": None,
            "last_error_at": None,
            # 内部字段：连续失败计数（不对外暴露，用于卡纸/文件占用提示）
            "consecutive_failures": 0,
        }
    return _scan_watchers[user_id]


router = APIRouter(prefix="/grading", tags=["grading"], dependencies=[Depends(bind_grading_user_context)])


def _quota_gate() -> None:
    """0924 需求：批改额度 105% 硬停前置闸门（1 面 = 1 张上传图）。

    实现已抽到 `app/grading/quota_gate.py`（供流水/首页/批量等入口复用），
    本函数保留为薄别名，既有 5 处调用点零改动。语义：
    ⛔ 只挡「发起新批改」不挡进度/结果/取消；身份缺失/查库故障放行留痕。
    （替代同事的「分余额 402 闸门」—— 计费口径统一为「按面 + 105% 硬停」。）
    """
    from app.grading.quota_gate import quota_gate

    quota_gate()

# C6：图片/文件直链独立于 Bearer-only 主 router（<img> 标签无法带 Authorization Header），
# 走 user_id_from_request（Bearer 或 ?ticket= 短时下载票），并按 user_id 定位本人目录。
file_router = APIRouter(prefix="/grading", tags=["grading-files"])

@router.post("/scan-import/start")
async def api_scan_import_start(request: Request, body: dict = Body(...), db: Session = Depends(get_db)):
    """启动扫描仪监测线程。"""
    _require_local_admin(request, db)  # M5：仅本机来源 + 管理员/校级角色
    folder_name = body.get("folder_name")
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")

    uid = get_grading_user_id()
    # 105% 硬停：额度用尽时拒绝启动扫描导入
    try:
        from app.services import quota_service
        quota_service.ensure_user_available(uid)
    except HTTPException:
        raise
    except Exception:
        pass
    state = _scan_state(uid)
    with _scan_watcher_lock:
        if state["running"]:
            if state["target_folder"] == safe:
                return {"ok": True, "msg": "已在运行", "folder_name": safe}
            else:
                raise HTTPException(status_code=400, detail=f"有另一个扫描任务正在运行（目标: {state['target_folder']}）")
                
        stop_event = threading.Event()
        state["running"] = True
        state["target_folder"] = safe
        state["stop_event"] = stop_event
        # 新会话：清空上次的错误与计数（错误只在本次会话内可见）
        state["imported_count"] = 0
        state["error"] = False
        state["error_message"] = None
        state["last_error_at"] = None
        state["consecutive_failures"] = 0

        # 真实扫描线程逻辑：任何异常都写入共享状态，不崩溃、不终止线程。
        def watch_scan():
            set_grading_user_id(uid)
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutTimeoutError

            POLL_TIMEOUT = 30.0   # 单轮扫描+移动超时保护，防止线程卡死
            FAIL_LIMIT = 5        # 连续失败阈值：触发卡纸/占用/目录异常提示

            def _record_failure(msg: str) -> None:
                state["consecutive_failures"] += 1
                if state["consecutive_failures"] >= FAIL_LIMIT:
                    msg = f"{msg}；连续失败 {state['consecutive_failures']} 次，可能是卡纸/文件占用/目录异常"
                state["error"] = True
                state["error_message"] = msg
                state["last_error_at"] = datetime.now().isoformat()

            def _record_success() -> None:
                state["consecutive_failures"] = 0
                state["error"] = False
                state["error_message"] = None
                state["last_error_at"] = None
                state["imported_count"] += 1

            def _poll_once() -> None:
                """单轮扫描+移动；逐文件容错，异常置 error 后继续，不抛给调用方。"""
                set_grading_user_id(uid)  # 子线程恢复用户上下文
                try:
                    target_dir = correct_docs_dir() / safe
                    target_dir.mkdir(parents=True, exist_ok=True)
                except Exception as dir_e:
                    _record_failure(f"目标目录不可用：{dir_e}")
                    return
                try:
                    items = list(scan_dir().iterdir())
                except Exception as scan_e:
                    _record_failure(f"扫描目录读取失败：{scan_e}")
                    return
                for item in items:
                    if stop_event.is_set():
                        return
                    try:
                        if not item.is_file() or item.suffix.lower() not in _SCAN_EXTENSIONS:
                            continue
                    except Exception:
                        continue
                    # 等待文件写入完成
                    time.sleep(1)
                    try:
                        target_file = target_dir / item.name
                        if target_file.exists():
                            target_file = target_dir / f"{item.stem}_{int(time.time())}{item.suffix}"
                        shutil.move(str(item), str(target_file))
                    except Exception as move_e:
                        _record_failure(f"移动扫描文件失败：{move_e}")
                        continue
                    # 成功移动一个文件：计数 +1，并清除错误（错误恢复）
                    _record_success()
                    try:
                        from app.grading.grading_stats import record_upload_for_file
                        record_upload_for_file(uid, safe, target_file.name)
                    except Exception:
                        pass
                    try:
                        from app.services import quota_service
                        quota_service.record_page(uid, target_file.name, 1)
                    except Exception:
                        pass

            executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scan-watch")
            pending_future = None
            try:
                while not stop_event.is_set():
                    if pending_future is not None and not pending_future.done():
                        # 上一轮卡死未结束：不叠加任务，报错并进入下一轮
                        _record_failure("扫描轮询超时未完成，可能是卡纸/文件占用/目录异常")
                        time.sleep(2)
                        continue
                    try:
                        pending_future = executor.submit(_poll_once)
                        try:
                            pending_future.result(timeout=POLL_TIMEOUT)
                        except _FutTimeoutError:
                            _record_failure("扫描轮询超时，已跳过本轮，可能是卡纸/文件占用/目录异常")
                        except Exception as poll_e:
                            _record_failure(f"扫描轮询异常：{poll_e}")
                    except Exception as outer_e:
                        _record_failure(f"扫描监测异常：{outer_e}")
                    time.sleep(2)
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

        t = threading.Thread(target=watch_scan, daemon=True)
        t.start()
        state["thread"] = t
        
    return {"ok": True, "msg": "扫描监测已启动", "folder_name": safe}

@router.post("/scan-import/stop")
async def api_scan_import_stop(request: Request, db: Session = Depends(get_db)):
    """停止扫描仪监测线程。"""
    _require_local_admin(request, db)  # M5
    uid = get_grading_user_id()
    state = _scan_state(uid)
    with _scan_watcher_lock:
        if state["running"] and state["stop_event"]:
            state["stop_event"].set()
        state["running"] = False
        state["target_folder"] = None
        state["thread"] = None
        state["stop_event"] = None
    return {"ok": True, "msg": "扫描监测已停止"}

@router.get("/scan-import/status")
async def api_scan_import_status(request: Request, db: Session = Depends(get_db)):
    """获取扫描仪监测状态。"""
    _require_local_admin(request, db)  # M5
    uid = get_grading_user_id()
    state = _scan_state(uid)
    with _scan_watcher_lock:
        return {
            "ok": True,
            "running": state["running"],
            "folder_name": state["target_folder"],
            # 前端硬契约：字段名与类型必须保持一致
            "imported_count": state["imported_count"],
            "error": state["error"],
            "error_message": state["error_message"],
            "last_error_at": state["last_error_at"],
        }

def _safe_folder_name(name: str) -> str:
    if not name or not name.strip():
        return ""
    raw = name.strip()
    # P0-3：拦截目录穿越。原实现只剔除 / \ : * ? " < > |，但放行 "." 与 ".."，
    # 攻击者可用 %2E%2E（解码为 ".."）作为文件夹名拼进 correct_docs_dir()/safe
    # 等路径，实现对 test_paper 命名空间之外文件的写/读/删/改；多级穿越还会触发 500。
    # 现新增三道拦截（均返回空串，沿用既有错误处理路径，不影响各调用点行为）：
    #  1) 值恰好为 "." 或 ".."；
    #  2) 任何被 "/" 或 "\" 分隔出的路径段恰好为 "." 或 ".."（防御拼路径时的分段穿越）；
    #  3) 名称以 "." 开头或以 "." 结尾（Windows 隐藏/歧义名，如 ".hidden"、"foo."、"..."）。
    # 合法含点文件夹名（如「数学期中.卷」）内嵌点在中间，不受影响，予以保留。
    if raw in (".", "..") or raw.startswith(".") or raw.endswith("."):
        return ""
    if any(seg in (".", "..") for seg in re.split(r"[/\\]+", raw)):
        return ""
    s = "".join(c for c in raw if c not in "/\\:*?\"<>|")
    return s.strip() or ""


def _natural_sort_key(s: str):
    """自然排序 key，例如 10 会排在 2 后面"""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s))]


def _safe_class_token(class_id: Optional[str]) -> str:
    s = str(class_id or "").strip()
    if not s:
        return ""
    token = "".join(c for c in s if c.isalnum() or c in ("-", "_"))
    return token[:64]


def _class_folder_prefix(class_id: Optional[str]) -> str:
    token = _safe_class_token(class_id)
    if not token:
        return ""
    return f"cls_{token}__"


def cleanup_grading_data_for_class(class_id: str, user_id: str) -> dict:
    token = set_grading_user_id(user_id)
    try:
        prefix = _class_folder_prefix(class_id)
        if not prefix:
            return {"deleted_folders": 0, "deleted_histories": 0, "deleted_essay_histories": 0}

        deleted_folders = 0
        deleted_histories = 0
        deleted_essay_histories = 0

        try:
            folder_names = [d.name for d in correct_docs_dir().iterdir() if d.is_dir() and d.name.startswith(prefix)]
        except Exception:
            folder_names = []

        for safe in folder_names:
            for engine in ["default", "manual"]:
                try:
                    with _grading_history_lock:
                        data = _read_grading_history(safe, engine)
                    completed = data.get("completed", {})
                    if isinstance(completed, dict):
                        for entry in completed.values():
                            if not isinstance(entry, dict):
                                continue
                            for key in ["image_original", "image_annotated", "image_marks_only"]:
                                url = entry.get(key)
                                if url and isinstance(url, str) and url.startswith("/api/v1/grading/modify/"):
                                    img_name = _img_name_from_url(url)
                                    if img_name:
                                        _safe_unlink(modify_dir() / img_name)
                    hist = _grading_history_path(safe, engine)
                    if hist.is_file():
                        _safe_unlink(hist)
                        deleted_histories += 1
                except Exception:
                    pass

            try:
                with _essay_history_lock:
                    data = _read_essay_history(safe)
                completed = data.get("completed", {})
                if isinstance(completed, dict):
                    for entry in completed.values():
                        if not isinstance(entry, dict):
                            continue
                        for key in ["image_original", "image_annotated", "image_marks_only"]:
                            url = entry.get(key)
                            if url and isinstance(url, str) and url.startswith("/api/v1/grading/modify/"):
                                img_name = _img_name_from_url(url)
                                if img_name:
                                    _safe_unlink(modify_dir() / img_name)
                hist = _essay_history_path(safe)
                if hist.is_file():
                    _safe_unlink(hist)
                    deleted_essay_histories += 1
            except Exception:
                pass

            try:
                path = correct_docs_dir() / safe
                if path.is_dir():
                    shutil.rmtree(path)
            except Exception:
                pass
            try:
                img_path = correct_docs_img_dir() / safe
                if img_path.is_dir():
                    shutil.rmtree(img_path)
            except Exception:
                pass
            deleted_folders += 1
            try:
                scan_root = Path(scan_dir())
                for scan_sub in [scan_root / "_imported" / safe, scan_root / safe]:
                    if scan_sub.is_dir():
                        shutil.rmtree(scan_sub)
            except Exception:
                pass
            _sync_stats_on_folder_delete(user_id, safe)

        return {
            "deleted_folders": deleted_folders,
            "deleted_histories": deleted_histories,
            "deleted_essay_histories": deleted_essay_histories,
        }
    finally:
        reset_grading_user_id(token)


def _safe_image_filename(name: str) -> bool:
    return bool(name and ".." not in name and "/" not in name and "\\" not in name)


def _safe_file_filename(name: str) -> bool:
    """允许图片、PDF、Word 文件名。"""
    if not name or ".." in name or "/" in name or "\\" in name:
        return False
    ext = Path(name).suffix.lower()
    return ext in _ALL_UPLOAD_EXTS


def _file_type(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _PDF_EXTS:
        return "pdf"
    if ext in _WORD_EXTS:
        return "word"
    return "file"


def _safe_marks_only_filename(name: str) -> bool:
    """只允许 marks_only_ 开头的文件名，且无路径成分。"""
    if not name or ".." in name or "/" in name or "\\" in name:
        return False
    return name.startswith("marks_only_") and (
        name.lower().endswith(".jpg")
        or name.lower().endswith(".jpeg")
        or name.lower().endswith(".png")
    )


def _safe_annotated_filename(name: str) -> bool:
    """只允许 annotated_ 开头的图片文件名，且无路径成分。"""
    if not name or ".." in name or "/" in name or "\\" in name:
        return False
    return name.startswith("annotated_") and (
        name.lower().endswith(".jpg")
        or name.lower().endswith(".jpeg")
        or name.lower().endswith(".png")
    )


def _essay_report_name_from_filename(name: str) -> str:
    stem = Path(str(name or "").strip()).stem.strip() or "未命名"
    return f"{stem}作文批改报告"


def _normalize_essay_trace_sentence(text: str, fallback: str) -> str:
    sentence = re.sub(r"【[^】]+】", " ", str(text or ""))
    sentence = re.sub(r"^[\s\-—:：]*(开头|中间一|中间二|中间1|中间2|结尾)[\s:：、.-]*", "", sentence)
    sentence = re.sub(r"[\r\n\t]+", " ", sentence)
    sentence = re.sub(r"\s+", " ", sentence).strip(" ：:，,。；;、")
    if not sentence:
        return fallback
    return sentence


def _extract_essay_segment_comments(result_text: str) -> dict:
    """从作文报告中提取开头、中间两段、结尾四条旁批。"""
    text = re.sub(r"<essay_score>\s*[\d.]+\s*</essay_score>", "", str(result_text or ""))
    text = re.sub(r"^#+\s*作文得分[：:].*$", "", text, flags=re.M)
    defaults = {
        "opening": "开头入题较清楚，能引出中心。",
        "middle1": "中段材料展开较完整，注意细节支撑。",
        "middle2": "中段表达有层次，还可加强过渡。",
        "ending": "结尾能收束全文，升华还可更有力。",
    }
    labels = [
        ("opening", r"开头"),
        ("middle1", r"中间一|中间1|中段一|中段1"),
        ("middle2", r"中间二|中间2|中段二|中段2"),
        ("ending", r"结尾"),
    ]
    comments = {}
    section_match = re.search(r"【作文分段概述】\s*(.*?)(?=\n\s*【|$)", text, flags=re.S)
    section = section_match.group(1).strip() if section_match else ""
    for key, label_re in labels:
        m = re.search(rf"(?:^|\n)\s*(?:{label_re})\s*[：:、.-]\s*(.*?)(?=\n\s*(?:开头|中间一|中间1|中段一|中段1|中间二|中间2|中段二|中段2|结尾)\s*[：:、.-]|\Z)", section, flags=re.S)
        if m:
            comments[key] = _normalize_essay_trace_sentence(m.group(1), defaults[key])

    if len(comments) < 4:
        compact_lines = [
            ln.strip(" -—\t")
            for ln in re.split(r"[\r\n]+", section)
            if ln.strip(" -—\t")
        ]
        for (key, _), line in zip(labels, compact_lines):
            comments.setdefault(key, _normalize_essay_trace_sentence(line, defaults[key]))

    if len(comments) < 4:
        m = re.search(r"【老师总评】\s*(.*?)(?=\n\s*【|$)", text, flags=re.S)
        source = m.group(1) if m else text
        sentences = [p.strip() for p in re.split(r"(?<=[。！？!?])", re.sub(r"\s+", " ", source)) if p.strip()]
        for idx, (key, _) in enumerate(labels):
            if key not in comments:
                comments[key] = _normalize_essay_trace_sentence(sentences[idx] if idx < len(sentences) else "", defaults[key])

    return {key: comments.get(key) or defaults[key] for key, _ in labels}


def _extract_essay_trace_comment(result_text: str) -> str:
    """兼容旧调用：返回结尾旁批。"""
    comments = _extract_essay_segment_comments(result_text)
    return comments.get("ending") or "结尾能收束全文，升华还可更有力。"


def _extract_essay_teacher_summary(result_text: str) -> str:
    """提取【老师总评】全文，用于试卷底部尾批。"""
    text = re.sub(r"<essay_score>\s*[\d.]+\s*</essay_score>", "", str(result_text or ""))
    m = re.search(r"【老师总评】\s*(.*?)(?=\n\s*【|$)", text, flags=re.S)
    if not m:
        return ""
    summary = re.sub(r"[\r\n\t]+", " ", m.group(1))
    return re.sub(r"\s+", " ", summary).strip()


# 作文留痕字号/行距（旁批、分数、尾批）
_ESSAY_COMMENT_FONT_SCALE = 0.35
_ESSAY_COMMENT_FONT_MIN = 20
_ESSAY_COMMENT_FONT_MAX = 34
_ESSAY_SCORE_FONT_SCALE = 1.12
_ESSAY_SCORE_FONT_MIN = 32
_ESSAY_SCORE_FONT_MAX = 62
_ESSAY_TRACE_LINE_GAP = 4
# 留痕红色（略深，叠印更清晰）
_ESSAY_MARK_FILL_COLOR = "#C41E1E"
_ESSAY_MARK_OUTLINE_COLOR = "#8B1212"
# 旁批不描边，笔画更细；分数沿用 _adaptive_mark_params 的空 offsets
_ESSAY_COMMENT_TEXT_OFFSETS: list[tuple[int, int]] = []


def _trim_scan_borders(
    img,
    *,
    darkness: int = 100,
    row_dark_ratio: float = 0.9,
    max_frac: float = 0.25,
):
    """裁掉扫描件四周的纯黑边（扫描仪/拍照带入的边框）。

    只在「整行/整列几乎全黑」时才裁，且单边最多裁 max_frac，避免把正文误裁；
    裁剪后若剩余区域过小则放弃裁剪（多半是误判）。
    """
    try:
        import numpy as np
    except Exception:
        return img
    try:
        gray = np.asarray(img.convert("L"))
    except Exception:
        return img

    h, w = gray.shape[:2]
    if h < 50 or w < 50:
        return img
    dark = gray < darkness

    def _count(rows, dim: int) -> int:
        limit = max(1, int(dim * max_frac))
        n = 0
        for r in rows:
            if r.sum() / max(1, r.size) > row_dark_ratio:
                n += 1
                if n >= limit:
                    break
            else:
                break
        return n

    top = _count(dark, h)
    bottom = _count(dark[::-1], h)
    left = _count(dark.T, w)
    right = _count(dark.T[::-1], w)
    if not any((top, bottom, left, right)):
        return img

    right_x, bottom_y = w - right, h - bottom
    if right_x - left < w * 0.3 or bottom_y - top < h * 0.3:
        return img
    return img.crop((left, top, right_x, bottom_y))


def _trim_uploaded_scan_borders(path: Path) -> None:
    """上传的扫描图片若四周带黑边，就地裁掉，让预览与批改都干净。

    只处理图片（PDF/Word 跳过）；裁剪失败不影响上传本身。
    """
    try:
        if path.suffix.lower() not in _IMAGE_EXTS:
            return
        from PIL import Image, ImageOps

        with Image.open(path) as im:
            fixed = ImageOps.exif_transpose(im).convert("RGB")
        trimmed = _trim_scan_borders(fixed)
        if trimmed.size == fixed.size:
            return  # 没裁到东西，不重写文件
        trimmed.save(path, quality=95)
    except Exception as e:
        print(f"裁剪扫描黑边失败（不影响上传）: {path.name}: {e}")


def _essay_mark_fonts(w: int, h: int):
    """作文留痕字体：旁批偏小、分数适中。"""
    from app.grading.pipeline import _adaptive_mark_params, _load_cjk_font, _load_ascii_font

    base, offsets, margin_x, margin_y = _adaptive_mark_params(w, h)
    comment_px = max(
        _ESSAY_COMMENT_FONT_MIN,
        min(_ESSAY_COMMENT_FONT_MAX, int(base * _ESSAY_COMMENT_FONT_SCALE)),
    )
    score_px = max(
        _ESSAY_SCORE_FONT_MIN,
        min(_ESSAY_SCORE_FONT_MAX, int(base * _ESSAY_SCORE_FONT_SCALE)),
    )
    comment_font = _load_cjk_font(comment_px) or _load_ascii_font(comment_px)
    score_font = _load_cjk_font(score_px) or _load_ascii_font(score_px)
    return comment_font, score_font, base, offsets, margin_x, margin_y


def _essay_trace_line_step(draw, font, line_gap: int = _ESSAY_TRACE_LINE_GAP) -> int:
    """旁批/尾批单行占用高度（含行距），用于按行数微调纵向位置。"""
    try:
        bbox = draw.textbbox((0, 0), "中", font=font)
        return max(18, (bbox[3] - bbox[1]) + line_gap)
    except Exception:
        return 30


def _essay_cjk_char_width(draw, font) -> int:
    try:
        bbox = draw.textbbox((0, 0), "中", font=font)
        return max(12, bbox[2] - bbox[0])
    except Exception:
        return 28


def _essay_trace_even_ratios(count: int, *, top: float = 0.10, bottom: float = 0.90) -> list[float]:
    """将可用纵向区间均分为 count 段，返回每段中心位置比例（用于单页多句平分）。"""
    count = max(1, int(count))
    span = max(0.05, float(bottom) - float(top))
    return [top + span * (i + 0.5) / count for i in range(count)]


def _essay_trace_page_comments(segment_comments: dict, page_index: int, page_count: int) -> list:
    """
    按页固定分配四条旁批，避免按全文长度比例切分导致一句被拆到两页。
    - 单页：四句在页内纵向平分
    - 多页：第一页前两句略下移；末句略上移
    """
    page_count = max(1, int(page_count or 1))
    page_index = max(0, int(page_index or 0))

    def item(
        key: str,
        anchor: str = "center_right",
        slot: int = 0,
        ratio: Optional[float] = None,
        lines_up: int = 0,
        lines_down: int = 0,
    ) -> dict:
        return {
            "key": key,
            "text": segment_comments.get(key) or "",
            "anchor": anchor,
            "slot": slot,
            "ratio": ratio,
            "lines_up": lines_up,
            "lines_down": lines_down,
        }

    # 多页：第一页前两句、末句纵向微调
    multi_p1_opening = 0.24   # 原约 0.17，略下移
    multi_p1_middle1 = 0.56   # 原约 0.50，略下移
    multi_ending = 0.74       # 第四句旁批（结尾）略上移
    single_ending = 0.72      # 单页时第四句旁批位置

    if page_count == 1:
        if page_index != 0:
            return []
        r0, r1, r2, _r3 = _essay_trace_even_ratios(4)
        return [
            item("opening", ratio=r0),
            item("middle1", ratio=r1),
            item("middle2", ratio=r2, lines_down=3),
            item("ending", ratio=single_ending, lines_up=4),
        ]

    if page_index == 0:
        return [
            item("opening", ratio=multi_p1_opening),
            item("middle1", ratio=multi_p1_middle1),
        ]

    if page_count == 2 and page_index == 1:
        return [
            item("middle2", "upper_right", 0, lines_down=3),
            item("ending", ratio=multi_ending, lines_up=4),
        ]

    if page_count >= 3 and page_index == 1:
        return [item("middle2", "center_right", 0, lines_down=3)]

    if page_index == page_count - 1:
        return [item("ending", ratio=multi_ending, lines_up=4)]

    return []


# 旁批锚点 → 页面内纵向比例（相对单页高度，不再按全文长度切分）
_ESSAY_TRACE_ANCHOR_RATIO = {
    ("upper_right", 0): 0.17,
    ("upper_right", 1): 0.24,
    ("top_right", 0): 0.10,
    ("center_right", 0): 0.50,
    ("center_right", 1): 0.62,
    ("bottom_right", 0): 0.88,
}


def _essay_trace_layout(
    draw,
    text: str,
    font,
    page_w: int,
    page_h: int,
    margin_x: int,
    margin_y: int,
    anchor: str = "center_right",
    slot: int = 0,
    ratio: Optional[float] = None,
    lines_up: int = 0,
    lines_down: int = 0,
) -> dict:
    line_gap = _ESSAY_TRACE_LINE_GAP
    char_w = _essay_cjk_char_width(draw, font)
    max_width = max(80, int(page_w * 0.2) - char_w * 2)
    max_width = min(max_width, max(80, page_w - margin_x * 3))
    right_edge = max(margin_x + max_width, page_w - margin_x * 2) - char_w
    lines = _wrap_trace_text(draw, text, font, max_width, max_lines=0)
    line_heights = []
    line_widths = []
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_widths.append(bbox[2] - bbox[0])
            line_heights.append(bbox[3] - bbox[1])
        except Exception:
            line_widths.append(len(line) * 20)
            line_heights.append(36)
    total_h = sum(line_heights) + line_gap * max(0, len(lines) - 1)
    anchor_key = (str(anchor or "center_right").lower(), int(slot or 0))
    pos_ratio = ratio if ratio is not None else _ESSAY_TRACE_ANCHOR_RATIO.get(anchor_key, 0.5)
    y = int(page_h * pos_ratio) - total_h // 2
    if lines_up > 0:
        y -= lines_up * _essay_trace_line_step(draw, font, line_gap)
    if lines_down > 0:
        y += lines_down * _essay_trace_line_step(draw, font, line_gap)
    y = max(margin_y + 8, min(y, page_h - margin_y - total_h - 8))
    x_left = max(margin_x, right_edge - max_width) + char_w
    return {
        "lines": lines,
        "line_heights": line_heights,
        "line_widths": line_widths,
        "line_gap": line_gap,
        "right_edge": right_edge,
        "x_left": x_left,
        "max_width": max_width,
        "y": y,
    }


def _detect_essay_summary_box(
    image, page_w: int, page_h: int
) -> Optional[tuple]:
    """定位试卷下部的「总评」框，返回 (top, bottom, left, right, content_bottom)。

    依据：「总评」框内部基本空白，只有框的上下边线横贯整栏，因此页面下部最靠下的
    两条横线就是框的上下边（实测框高稳定在页面高度的 9%~10%）。扫描件的线常断成
    两行、颜色偏淡，所以先把相邻行并起来再判定。再用框内印刷内容（「总评：」字样）
    推算正文该从哪一行往下写。识别不到返回 None（调用方退回旧逻辑）。
    """
    if image is None:
        return None
    try:
        import numpy as np
    except Exception:
        return None
    try:
        gray = np.asarray(image.convert("L"))
    except Exception:
        return None

    h, w = gray.shape[:2]
    if h < 80 or w < 80:
        return None

    dark = gray < 128
    # 扫描件常有断线：把上下相邻行的暗像素并起来，避免一条线被拆成两行而漏检
    merged = dark.copy()
    if h > 2:
        merged[1:-1] = dark[:-2] | dark[1:-1] | dark[2:]
    ratios = merged.sum(axis=1) / float(w)

    # 收集下半部分的「横线」（连续若干行占比够高，视为同一条线）
    bands: list = []
    y = int(h * 0.55)
    while y < h:
        if ratios[y] < 0.55:
            y += 1
            continue
        start = y
        while y < h and ratios[y] >= 0.55:
            y += 1
        peak = max(range(start, y), key=lambda k: ratios[k])
        xs = np.flatnonzero(merged[peak])
        if xs.size:
            bands.append((peak, float(ratios[peak]), int(xs[0]), int(xs[-1])))

    if len(bands) < 2:
        return None

    # 「总评」框内部是空白的，所以框底边之下、框上边之上才会有别的横线。
    # 取最靠下的两条线即为框的上下边，其间距应落在常见框高范围内。
    bottom = bands[-1]
    top = bands[-2]
    gap = bottom[0] - top[0]
    if not (int(h * 0.04) <= gap <= int(h * 0.20)):
        return None

    left = min(top[2], bottom[2])
    right = max(top[3], bottom[3])
    if right - left < int(w * 0.3):
        return None

    # 框内印刷内容（「总评：」）的底边；只在前半框内探测，避免把格子线算进来
    content_bottom = top[0]
    probe_end = min(bottom[0], top[0] + max(20, int((bottom[0] - top[0]) * 0.5)))
    for y in range(top[0] + 2, probe_end):
        if int(dark[y, left:right].sum()) > 3:
            content_bottom = y

    return (top[0], bottom[0], left, right, content_bottom)


def _essay_footer_trace_layout(
    draw,
    text: str,
    font,
    page_w: int,
    page_h: int,
    margin_x: int,
    margin_y: int,
    *,
    image=None,
) -> Optional[dict]:
    """尾批：优先写进试卷上印刷的「总评」框；识别不到框时退回页面底部排布。"""
    content = str(text or "").strip()
    if not content:
        return None

    line_gap = _ESSAY_TRACE_LINE_GAP
    line_step = _essay_trace_line_step(draw, font, line_gap)

    def _measure(lines: list) -> list:
        heights = []
        for line in lines:
            try:
                bbox = draw.textbbox((0, 0), line, font=font)
                heights.append(bbox[3] - bbox[1])
            except Exception:
                heights.append(32)
        return heights

    box = _detect_essay_summary_box(image, page_w, page_h)
    if box:
        box_top, box_bottom, box_left, box_right, content_bottom = box
        char_w = _essay_cjk_char_width(draw, font)
        pad_x = max(6, int(char_w * 0.5))
        x_left = box_left + pad_x
        max_width = max(120, box_right - pad_x - x_left)

        lines = _wrap_trace_text(draw, content, font, max_width, max_lines=0)
        line_heights = _measure(lines)

        # 正文从「总评：」下方起排，底部留出一点内边距
        top_y = content_bottom + max(4, line_step // 4)
        bottom_limit = box_bottom - max(4, line_step // 5)
        avail_h = max(0, bottom_limit - top_y)
        total_h = sum(line_heights) + line_gap * max(0, len(lines) - 1)

        if total_h > avail_h and len(lines) > 1:
            # 框里放不下：先压行距（最多收到字高本身，避免行与行叠字）
            gap_floor = -max(0, min(line_heights) - 4)
            shrink = int((total_h - avail_h) / (len(lines) - 1))
            line_gap = max(gap_floor, line_gap - shrink)

        return {
            "lines": lines,
            "line_heights": line_heights,
            "line_gap": line_gap,
            "x_left": x_left,
            "y": top_y,
        }

    # ── 兜底：未识别到「总评」框时，沿用页面底部排布 ──
    char_w = _essay_cjk_char_width(draw, font)
    footer_inset_right = max(margin_x * 2, int(margin_x * 2.2))
    footer_inset_left = footer_inset_right + char_w * 2
    max_width = max(120, page_w - footer_inset_left - footer_inset_right)
    lines = _wrap_trace_text(draw, content, font, max_width, max_lines=0)
    line_heights = _measure(lines)
    total_h = sum(line_heights) + line_gap * max(0, len(lines) - 1)
    y = page_h - margin_y - total_h - 10
    y -= 4 * line_step
    # 尾批过长时向上收缩，避免盖住正文中部
    y = max(int(page_h * 0.52), min(y, page_h - margin_y - total_h - 8))
    return {
        "lines": lines,
        "line_heights": line_heights,
        "line_gap": line_gap,
        "x_left": footer_inset_left,
        "y": y,
    }


def _draw_essay_footer_trace(draw, layout: dict, font, fill: str, outline: str, offsets: list) -> None:
    y = layout["y"]
    for idx, line in enumerate(layout["lines"]):
        _draw_outlined_text(draw, (layout["x_left"], y), line, font, fill, outline, offsets)
        y += layout["line_heights"][idx] + layout["line_gap"]


def _wrap_trace_text(draw, text: str, font, max_width: int, max_lines: int = 0) -> list:
    """按像素宽度折行，适配中文短评留痕。max_lines=0 表示不限制行数。"""
    lines = []
    current = ""
    unlimited = max_lines <= 0
    for ch in str(text or ""):
        trial = current + ch
        try:
            bbox = draw.textbbox((0, 0), trial, font=font)
            width = bbox[2] - bbox[0]
        except Exception:
            width = len(trial) * 18
        if current and width > max_width:
            lines.append(current)
            current = ch
            if not unlimited and len(lines) >= max_lines:
                break
        else:
            current = trial
    if current and (unlimited or len(lines) < max_lines):
        lines.append(current)
    lines = fix_punctuation_line_starts(lines)
    return lines or [str(text or "").strip()]


def _draw_outlined_text(draw, xy, text: str, font, fill: str, outline: str, offsets: list) -> None:
    x, y = xy
    for ox, oy in offsets:
        draw.text((x + ox, y + oy), text, fill=outline, font=font)
    draw.text((x, y), text, fill=fill, font=font)


def _grading_history_path(safe: str, engine: str = "default") -> Path:
    # 为了避免和旧的逻辑冲突，如果 engine 没传或者是 default/aliyun/baidu/smart_ref，则依然使用原有的文件
    # essay 已经有 _essay_history_path 处理
    # 针对 manual 单独分出一个文件
    if engine == "manual":
        return grading_history_dir() / f"{safe}__manual.json"
    return grading_history_dir() / f"{safe}.json"


def _empty_grading_history(engine: str = "default") -> dict:
    return {
        "version": 1,
        "engine": "manual" if engine == "manual" else engine,
        "completed": {},
        "failed": {},
        "scoring_config": None,
    }


def _read_grading_history(safe: str, engine: str = "default") -> dict:
    p = _grading_history_path(safe, engine)
    if not p.is_file():
        return _empty_grading_history(engine)
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data.get("completed"), dict):
            data["completed"] = {}
        if not isinstance(data.get("failed"), dict):
            data["failed"] = {}
        if "scoring_config" not in data:
            data["scoring_config"] = None
        if not data.get("engine"):
            data["engine"] = "manual" if engine == "manual" else engine
        return data
    except Exception:
        return _empty_grading_history(engine)


def _item_score_total(item: dict) -> Optional[float]:
    """completed 条目的分数：优先 score_total，兜底 result JSON 里的 score_total。"""
    raw = item.get("score_total")
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    try:
        parsed = json.loads(item.get("result") or "{}")
        if isinstance(parsed, dict) and parsed.get("score_total") is not None:
            return float(parsed["score_total"])
    except Exception:
        pass
    return None


def _compute_box_totals_snapshot(safe: str, current_engine: str, current_data: dict) -> dict:
    """整卷总分持久化字段 box_totals：default+manual+essay 三份历史的合并视图。

    合并顺序 default → manual（同名覆盖）→ essay（同名覆盖，作文整卷语义）；
    作文条目整卷计分（取最大），普通条目逐页计分（累加）。只读不写，无递归风险。
    """
    from app.grading.box_totals import build_box_totals

    entries: dict[str, tuple] = {}  # filename -> (score, mode)；后写覆盖先写

    def _put(completed: Any, mode: str) -> None:
        if not isinstance(completed, dict):
            return
        for name, item in completed.items():
            if not isinstance(item, dict):
                continue
            entries[str(name)] = (_item_score_total(item), mode)

    is_manual_file = current_engine == "manual"
    is_essay_file = current_engine == "essay"

    if is_essay_file:
        _put(_read_grading_history(safe, "default").get("completed"), "sum")
        _put(_read_grading_history(safe, "manual").get("completed"), "sum")
        _put(current_data.get("completed"), "max")
    else:
        if is_manual_file:
            _put(_read_grading_history(safe, "default").get("completed"), "sum")
            _put(current_data.get("completed"), "sum")
        else:
            _put(current_data.get("completed"), "sum")
            _put(_read_grading_history(safe, "manual").get("completed"), "sum")
        _put(_read_essay_history(safe).get("completed"), "max")

    return build_box_totals((name, score, mode) for name, (score, mode) in entries.items())


def _write_grading_history(
    safe: str, data: dict, engine: str = "default", *, authoritative: bool = False
) -> None:
    # 引擎切换守卫统一收口：所有历史写（含统分/批注/满分同步等旁路）都过这道闸，
    # 迟到 worker 不经 _persist_* 也能被拦住。authoritative=True 只给
    # _replace_folder_grading_run 建立权威 run 的那一次空历史写用。
    if not authoritative and _persist_run_superseded(safe, engine):
        return
    data["version"] = 1
    if engine != "default" or not data.get("engine"):
        data["engine"] = "manual" if engine == "manual" else engine
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    # 整卷总分持久化（客户清单 #7）：每次写历史都刷新 box_totals 快照（正反面合并+作文语义）
    try:
        data["box_totals"] = _compute_box_totals_snapshot(safe, engine, data)
    except Exception:
        pass
    p = _grading_history_path(safe, engine)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _history_sort_timestamp(path: Path, data: dict) -> float:
    raw = str(data.get("updated_at") or "").strip()
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError):
            pass
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _latest_grading_history(safe: str) -> tuple[dict, str]:
    """Return the newest smart/reference or manual run for one folder."""
    candidates: list[tuple[float, int, dict, str]] = []
    for priority, engine in enumerate(("default", "manual")):
        path = _grading_history_path(safe, engine)
        if not path.is_file():
            continue
        data = _read_grading_history(safe, engine)
        candidates.append((_history_sort_timestamp(path, data), priority, data, engine))
    if not candidates:
        return _empty_grading_history(), "default"
    _timestamp, _priority, data, engine = max(candidates, key=lambda item: (item[0], item[1]))
    return data, engine


# 引擎切换守卫（对齐批改君）：_replace_folder_grading_run 是文件夹唯一「权威批改 run」
# 入口，会清空 default/manual 两份历史、再写一份盖着本次引擎戳的空历史。被顶替的旧 run
# 的迟到 worker 若再落盘，会把旧模式的结果/失败复活进新 run 的历史（例如取消 aliyun 后
# 立刻开 smart_ref，旧 worker 的「已停止批改」或最后一张卷会混进新历史）。
# 判据用「目标历史文件的引擎戳」而不是进程内标记：文件本身按用户隔离（user_paths），
# 同名文件夹多用户互不干扰；进程重启后也无状态可言（迟到 worker 必然是本进程线程）。
def _persist_run_superseded(safe: str, engine: str) -> bool:
    """True = 该落盘属于已被顶替的旧 run，应丢弃。调用方需在 _grading_history_lock 内。"""
    writer = str(engine or "").strip().lower()
    if writer in ("", "default"):
        # 引擎未知（兼容旧调用/测试桩、统分/配置等直写）→ 放行
        return False
    path = _grading_history_path(safe, engine)
    if not path.is_file():
        # 目标历史文件不在 = 已被更新的权威 run 清掉（正常写入方都经 replace 建好的
        # 空历史落盘，或要求历史里已有该条目）→ 这是迟到写入，丢弃，不许凭空复活历史。
        return True
    try:
        with open(path, "r", encoding="utf-8") as f:
            stamp = str((json.load(f) or {}).get("engine") or "").strip().lower()
    except Exception:
        return False  # 读不出引擎戳（损坏/竞态）→ 放行，宁可多写不丢结果
    if stamp in ("", "default"):
        return False  # 旧历史没盖引擎戳 → 放行
    return stamp != writer


def _persist_grading_success(safe: str, item: dict, engine: str = "default") -> None:
    """将成功批改结果写入本地 JSON，重启后仍可加载；同试卷名再次批改会覆盖本条。"""
    name = item.get("name")
    if not name:
        return
    store = {k: v for k, v in item.items() if k != "index"}
    source = "manual" if engine == "manual" else "ref"
    old_entry: Optional[dict] = None
    with _grading_history_lock:
        if _persist_run_superseded(safe, engine):
            return
        data = _read_grading_history(safe, engine)
        prev = (data.get("completed") or {}).get(name)
        if isinstance(prev, dict):
            old_entry = dict(prev)
        data["completed"][name] = store
        data["failed"].pop(name, None)
        _write_grading_history(safe, data, engine)
    try:
        from app.grading.grading_stats import record_graded_state_change

        record_graded_state_change(
            get_grading_user_id(), safe, old_entry, store, source=source, filename=name
        )
    except Exception:
        pass
    # 批改完成 → 自动导入学情+自动分层（客户清单 #1）；旁路异步，失败只打日志
    try:
        _schedule_auto_sync_class(get_grading_user_id(), safe)
    except Exception:
        pass


def _persist_grading_failure(safe: str, name: str, msg: str, engine: str = "default") -> None:
    """记录失败原因；不删除已有成功记录，避免单次失败抹掉此前已批改结果。"""
    if not name:
        return
    with _grading_history_lock:
        if _persist_run_superseded(safe, engine):
            return
        data = _read_grading_history(safe, engine)
        data["failed"][name] = {"name": name, "msg": msg or "批改失败"}
        _write_grading_history(safe, data, engine)


def _is_placeholder_completed_item(item: dict) -> bool:
    from app.grading.grading_stats import is_placeholder_completed_item

    return is_placeholder_completed_item(item)


def _sync_stats_on_paper_delete(user_id: str, safe: str, filename: str) -> None:
    try:
        from app.grading.grading_stats import record_paper_deleted_for_file

        record_paper_deleted_for_file(user_id, safe, filename)
    except Exception:
        pass


def _sync_stats_on_folder_delete(user_id: str, safe: str) -> None:
    try:
        from app.grading.grading_stats import remove_folder_stats

        remove_folder_stats(user_id, safe)
    except Exception:
        pass


def _remove_grading_history_entry(safe: str, filename: str, engine: str = "default") -> None:
    with _grading_history_lock:
        data = _read_grading_history(safe, engine)

        # 尝试删除 modify 文件夹中残留的图片（URL 带 ?ticket= 查询串，必须先剥掉，
        # 否则文件名撑爆 → OSError ENAMETOOLONG → 删除试卷在 unlink 之后 500）
        entry = data["completed"].get(filename)
        if entry and isinstance(entry, dict):
            for key in ["image_original", "image_annotated", "image_marks_only"]:
                _delete_modify_file_by_url(entry.get(key))

        data["completed"].pop(filename, None)
        data["failed"].pop(filename, None)
        _write_grading_history(safe, data, engine)
    _delete_reference_modify_artifacts(safe, filename)


def _rename_grading_history_entry(safe: str, old_filename: str, new_filename: str, engine: str = "default") -> None:
    if not old_filename or not new_filename or old_filename == new_filename:
        return
    with _grading_history_lock:
        data = _read_grading_history(safe, engine)
        changed = False
        completed = data.get("completed", {})
        if isinstance(completed, dict) and old_filename in completed:
            item = completed.pop(old_filename)
            if isinstance(item, dict):
                item["name"] = new_filename
            completed[new_filename] = item
            changed = True
        failed = data.get("failed", {})
        if isinstance(failed, dict) and old_filename in failed:
            item = failed.pop(old_filename)
            if isinstance(item, dict):
                item["name"] = new_filename
            failed[new_filename] = item
            changed = True
        if changed:
            _write_grading_history(safe, data, engine)


def _delete_modify_file_by_url(url: Optional[str]) -> None:
    if not url or not str(url).startswith("/api/v1/grading/modify/"):
        return
    # 见 _img_name_from_url：URL 里的 ?ticket=/?t= 查询串绝不能进文件名。
    img_name = _img_name_from_url(url)
    if not img_name:
        return
    try:
        img_path = modify_dir() / img_name
        if img_path.is_file():
            img_path.unlink()
    except Exception:
        pass


def _delete_reference_modify_artifacts(safe: str, filename: Optional[str] = None) -> None:
    """Delete generated grading images that may predate history cleanup."""
    folder_prefixes = (f"ref_{safe}_", f"manual_{safe}_")
    paper_stem = Path(filename).stem if filename else ""
    target_stems = {
        f"{folder_prefix}{paper_stem}"
        for folder_prefix in folder_prefixes
    } if paper_stem else set()
    prefixes = ("original_", "annotated_", "marks_only_")
    try:
        candidates = list(modify_dir().iterdir())
    except Exception:
        return
    for path in candidates:
        if not path.is_file():
            continue
        name = path.name
        generated_stem = ""
        for prefix in prefixes:
            if name.startswith(prefix):
                generated_stem = Path(name[len(prefix):]).stem
                break
        if not generated_stem or not generated_stem.startswith(folder_prefixes):
            continue
        # 批注打印变体 marks_only_{stem}_wa.jpg 与原图同生命周期
        stem_for_match = generated_stem[:-3] if generated_stem.endswith("_wa") else generated_stem
        if target_stems and stem_for_match not in target_stems:
            continue
        try:
            path.unlink()
        except Exception:
            pass


def _delete_modify_files_referenced_by_history(history_path: Path) -> None:
    if not history_path.is_file():
        return
    try:
        data = json.loads(history_path.read_text(encoding="utf-8"))
    except Exception:
        return
    for bucket in ("completed", "failed"):
        entries = data.get(bucket)
        if not isinstance(entries, dict):
            continue
        for entry in entries.values():
            if not isinstance(entry, dict):
                continue
            for key in ("image_original", "image_annotated", "image_marks_only", "image_marks_with_wrong_notes", "image_annotated_with_wrong_notes"):
                _delete_modify_file_by_url(entry.get(key))


def _replace_folder_grading_run(safe: str, engine: str) -> None:
    """Start one authoritative folder run and remove all previous result data."""
    target_engine = "manual" if engine == "manual" else engine
    history_paths = (
        _grading_history_path(safe, "default"),
        _grading_history_path(safe, "manual"),
    )
    with _grading_history_lock:
        for path in history_paths:
            _delete_modify_files_referenced_by_history(path)
        for path in history_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        # authoritative：本写入就是建立权威 run 的那一步（文件刚被删，引擎戳还没落地），
        # 引擎切换守卫必须放行它，否则 replace 自己会把自己拦掉。
        _write_grading_history(
            safe, _empty_grading_history(target_engine), target_engine, authoritative=True
        )

    _delete_reference_modify_artifacts(safe)
    try:
        from app.grading.wrong_question_db import delete_exam_wrong_question_file

        delete_exam_wrong_question_file(safe)
    except Exception:
        pass
    try:
        from app.grading.reference_vlm_grading import delete_reference_vlm_folder_artifacts

        delete_reference_vlm_folder_artifacts(safe)
    except Exception:
        pass
    # B 项：re-grade 全量重跑后旧台账行置 voided（历史事实保留，当前态统计排除）
    try:
        from app.grading.correction_ledger import void_folder_corrections

        void_folder_corrections(safe)
    except Exception:
        pass


def _get_completed_names_from_history(safe: str, engine: str = "default") -> set[str]:
    with _grading_history_lock:
        data = _read_grading_history(safe, engine)
    completed = data.get("completed", {})
    if isinstance(completed, dict):
        return set(
            str(k)
            for k, v in completed.items()
            if not _is_placeholder_completed_item(v if isinstance(v, dict) else {})
        )
    return set()


def _run_one_paper(save_path: Path, file_stem: str, original_name: str, modify_dir: Path, user_id: str) -> dict:
    try:
        result, blocks_with_result, _, _ = real_grade_pipeline(str(save_path))
        image_original = image_annotated = image_marks_only = None
        marks_only_filename = None
        if blocks_with_result:
            try:
                orig_name, ann_name = draw_real_marks_and_save(
                    str(save_path), blocks_with_result, str(modify_dir), file_stem
                )
                # H2：文件直链改为短时下载票（绑定当前用户+资源路径），不再把时间戳/长期令牌拼进 URL
                image_original = build_download_url(f"grading/modify/{orig_name}", user_id)
                image_annotated = build_download_url(f"grading/modify/{ann_name}", user_id)
                marks_only_filename = draw_marks_only_and_save(
                    str(save_path), blocks_with_result, str(modify_dir), file_stem
                )
                image_marks_only = build_download_url(f"grading/modify/{marks_only_filename}", user_id)
            except Exception:
                pass
        return {
            "index": -1,
            "name": original_name,
            "image_original": image_original,
            "image_annotated": image_annotated,
            "image_marks_only": image_marks_only,
            "result": result or "",
            "marks_only_filename": marks_only_filename,
        }
    except Exception as e:
        return {"index": -1, "name": original_name, "error": True, "msg": str(e)}


def _run_batch(batch_id: str, tasks: list, modify_dir_path: Path, user_id: str):
    set_grading_user_id(user_id)
    for i, (save_path, file_stem, original_name) in enumerate(tasks):
        item = _run_one_paper(save_path, file_stem, original_name, modify_dir_path, user_id)
        item["index"] = i
        with _batch_lock:
            if batch_id not in _batch_results:
                return
            if item.get("error"):
                _batch_results[batch_id]["failed"].append(
                    {"index": i, "name": original_name, "msg": item.get("msg", "批改失败")}
                )
            else:
                _batch_results[batch_id]["completed"].append(item)


@router.post("/quick")
async def api_grade_quick(file: UploadFile = File(...)):
    """快速批改：上传单张试卷图片，大模型自主批改，返回结果与图片 URL。"""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="请上传图片文件（如 jpg、png）")
    # 0924：大模型批改发起闸（本入口无独立上传侧计面 ⇒ 同步计 1 面）。
    # 放在 try/except Exception 之前，确保 403 不被下面的 500 包装吞掉。
    quota_gate(charge_pages=1)
    ext = ".jpg"
    if file.filename:
        for e in (".jpg", ".jpeg", ".png", ".webp"):
            if file.filename.lower().endswith(e):
                ext = e
                break
    name = f"{uuid.uuid4()}{ext}"
    save_path = test_dir() / name
    try:
        content = await file.read()
        save_path.write_bytes(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存图片失败: {e}")
    normalize_uploaded_image_orientation(save_path)
    file_stem = save_path.stem
    grade_path = save_path
    try:
        result, blocks_with_result, _, _ = real_grade_pipeline(str(grade_path))
        image_original = image_annotated = image_marks_only = None
        if blocks_with_result:
            try:
                orig_name, ann_name = draw_real_marks_and_save(
                    str(save_path), blocks_with_result, str(modify_dir()), file_stem
                )
                _uid = get_grading_user_id()
                image_original = build_download_url(f"grading/modify/{orig_name}", _uid)
                image_annotated = build_download_url(f"grading/modify/{ann_name}", _uid)
                marks_only_name = draw_marks_only_and_save(
                    str(save_path), blocks_with_result, str(modify_dir()), file_stem
                )
                image_marks_only = build_download_url(f"grading/modify/{marks_only_name}", _uid)
            except Exception:
                pass
        return {
            "ok": True,
            "result": result,
            "image_original": image_original,
            "image_annotated": image_annotated,
            "image_marks_only": image_marks_only,
        }
    except Exception as e0:
        raise HTTPException(
            status_code=500,
            detail=f"批改失败：请使用清晰的试卷图片。若仍失败，请检查 OCR 服务与网络。详情：{str(e0)}",
        )


@router.post("/home/standard")
async def api_home_upload_standard(file: UploadFile = File(...)):
    """上传标准答案卷，返回 standard_id（文件名），供 /home/quick 引用走千问对照批改。"""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="请上传图片文件（如 jpg、png）")
    ext = ".jpg"
    if file.filename:
        for e in (".jpg", ".jpeg", ".png", ".webp"):
            if file.filename.lower().endswith(e):
                ext = e
                break
    standard_id = f"std_{uuid.uuid4()}{ext}"
    save_path = home_img_dir() / standard_id
    try:
        content = await file.read()
        save_path.write_bytes(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存答案卷失败: {e}")
    return {"ok": True, "standard_id": standard_id}


@router.post("/home/quick")
async def api_home_grade_quick(
    file: UploadFile = File(...),
    standard_id: str = Form(""),
    anonymous: str = Form("false"),
):
    """首页图片批改：上传学生试卷（可选标准答案卷 id）。有答案卷走千问对照批改(smart_ref)，否则百度盲批。原图/留痕/空白留痕/json 保存到 grading_data/home_img。"""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="请上传图片文件（如 jpg、png）")
    # 0924：大模型批改发起闸（smart_ref/baidu，无独立上传侧计面 ⇒ 同步计 1 面）
    quota_gate(charge_pages=1)
    ext = ".jpg"
    if file.filename:
        for e in (".jpg", ".jpeg", ".png", ".webp"):
            if file.filename.lower().endswith(e):
                ext = e
                break
    job_id = str(uuid.uuid4())
    upload_name = f"{job_id}{ext}"
    save_path = home_img_dir() / upload_name
    try:
        content = await file.read()
        save_path.write_bytes(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存图片失败: {e}")
    normalize_uploaded_image_orientation(save_path)

    # 可选：标准答案卷（有则走千问对照批改），standard_id 由 /home/standard 预先上传
    standard_path: Optional[Path] = None
    standard_filename = None
    if standard_id:
        std_candidate = home_img_dir() / standard_id
        if std_candidate.is_file():
            standard_path = std_candidate
            standard_filename = standard_id

    created_at = datetime.now(timezone.utc).isoformat()
    display_name = (file.filename or upload_name).strip() or upload_name
    record = {
        "ok": True,
        "id": job_id,
        "name": display_name,
        "created_at": created_at,
        "engine": "smart_ref" if standard_path else "baidu",
        "anonymous": anonymous == "true",
        "user_id": get_grading_user_id(),
        "status": "queued",
        "progress": 5,
        "message": "已上传，等待开始…",
        "result": "",
        "image_original": None,
        "image_annotated": None,
        "image_marks_only": None,
        "upload_filename": upload_name,
        "files": {
            "upload": upload_name,
            "standard": standard_filename,
            "image_original": None,
            "image_annotated": None,
            "image_marks_only": None,
            "json": f"{job_id}.json",
        },
    }
    with _home_img_lock:
        _home_record_path(job_id).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        _cleanup_home_img_records(keep=10)

    with _home_quick_lock:
        if job_id not in _home_quick_stop_events:
            _home_quick_stop_events[job_id] = threading.Event()
        _home_quick_jobs[job_id] = {"id": job_id, "created_at": created_at, "status": "queued", "user_id": get_grading_user_id()}
        threading.Thread(
            target=_run_home_quick_job,
            args=(job_id, save_path, standard_path, display_name, get_grading_user_id()),
            daemon=True,
        ).start()
    return {"ok": True, "job_id": job_id, "item": record}


@router.get("/home/recent")
async def api_home_recent():
    """首页最近作业：返回最近批改的 10 条记录（来自 grading_data/home_img/*.json）。"""
    try:
        json_files = sorted(
            [p for p in home_img_dir().glob("*.json") if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:10]
    except Exception:
        json_files = []

    items = []
    for p in json_files:
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(rec, dict):
                continue
            items.append(
                {
                    "id": rec.get("id") or p.stem,
                    "name": rec.get("name") or p.stem,
                    "created_at": rec.get("created_at") or "",
                    "status": rec.get("status") or "",
                    "progress": rec.get("progress") if isinstance(rec.get("progress"), (int, float)) else None,
                    "message": rec.get("message") or "",
                    "ok": bool(rec.get("ok")) if "ok" in rec else True,
                }
            )
        except Exception:
            continue
    return {"ok": True, "items": items}


@router.get("/home/{job_id}")
async def api_home_detail(job_id: str):
    """首页作业详情：用于“查看”弹窗展示。"""
    p = _home_record_path(job_id)
    if not p.is_file():
        raise HTTPException(status_code=404, detail="作业不存在或已被清理")
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(rec, dict):
            raise ValueError("bad json")
    except Exception:
        raise HTTPException(status_code=500, detail="读取作业数据失败")
    _assert_job_owner(rec)
    for key in ("image_original", "image_annotated", "image_marks_only"):
        if rec.get(key):
            rec[key] = _re_sign_history_image_url(rec[key])
    return {"ok": True, "item": rec}


def _home_record_blocks(rec: dict) -> list:
    blocks = rec.get("blocks")
    if isinstance(blocks, list) and blocks:
        return blocks
    return []


@router.post("/home/{job_id}/wrong-annotation/save")
async def api_home_wrong_annotation_save(job_id: str, request: Request):
    """首页作业判错批注：整体覆盖保存（首页无留痕变体，只存文本）。"""
    p = _home_record_path(job_id)
    if not p.is_file():
        raise HTTPException(status_code=404, detail="作业不存在或已被清理")
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(rec, dict):
            raise ValueError("bad json")
    except Exception:
        raise HTTPException(status_code=500, detail="读取作业数据失败")
    _assert_job_owner(rec)
    try:
        body = await request.json()
    except Exception:
        body = {}
    from app.grading.wrong_annotations import normalize_wrong_annotations

    wrong_annotations = normalize_wrong_annotations(body.get("wrong_annotations"))
    _home_update_record(job_id, {"wrong_annotations": wrong_annotations})
    return {"ok": True, "wrong_annotations": wrong_annotations}


@router.post("/home/{job_id}/wrong-annotation/generate")
async def api_home_wrong_annotation_generate(job_id: str, request: Request):
    """首页作业判错批注：AI 生成/重生成（带 question_key 单题覆盖，不带整卷补齐）。"""
    p = _home_record_path(job_id)
    if not p.is_file():
        raise HTTPException(status_code=404, detail="作业不存在或已被清理")
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(rec, dict):
            raise ValueError("bad json")
    except Exception:
        raise HTTPException(status_code=500, detail="读取作业数据失败")
    _assert_job_owner(rec)
    try:
        body = await request.json()
    except Exception:
        body = {}
    question_key = str(body.get("question_key") or "").strip()
    blocks = _home_record_blocks(rec)
    if not blocks:
        raise HTTPException(status_code=409, detail="该作业缺少逐题数据，无法生成批注")

    from app.grading.wrong_annotations import (
        collect_wrong_question_groups,
        generate_wrong_annotations_for_blocks,
        normalize_wrong_annotations,
    )

    source_path = home_img_dir() / str(
        (rec.get("files") or {}).get("upload") or ""
    )
    source_image_path = str(source_path) if source_path.is_file() else ""
    existing = normalize_wrong_annotations(rec.get("wrong_annotations"))
    if question_key:
        groups = collect_wrong_question_groups(blocks)
        if question_key not in groups:
            raise HTTPException(status_code=404, detail="该题不是错/半对，无需生成错因批注")
        generated = generate_wrong_annotations_for_blocks(
            blocks,
            source_image_path=source_image_path,
            existing={},
            only_keys={question_key},
        )
    else:
        generated = generate_wrong_annotations_for_blocks(
            blocks,
            source_image_path=source_image_path,
            existing=existing,
        )
    if generated:
        existing.update(generated)
        _home_update_record(job_id, {"wrong_annotations": existing})
    return {"ok": True, "wrong_annotations": existing, "generated": generated}


@router.delete("/home/{job_id}")
async def api_home_delete(job_id: str):
    """删除首页最近作业：删除原图/留痕/仅留痕/json。"""
    p = _home_record_path(job_id)
    if not p.is_file():
        raise HTTPException(status_code=404, detail="作业不存在或已被清理")
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(rec, dict):
            rec = {"id": job_id, "files": {"json": f"{job_id}.json"}}
    except Exception:
        rec = {"id": job_id, "files": {"json": f"{job_id}.json"}}
    _assert_job_owner(rec)
    with _home_img_lock:
        _home_delete_by_record(rec)
    return {"ok": True}


@router.post("/batch")
async def api_grade_batch(files: List[UploadFile] = File(...)):
    """批量快速批改：上传多张图片，返回 batch_id，前端轮询 GET /grading/batch/{batch_id}。"""
    if not files:
        raise HTTPException(status_code=400, detail="请至少选择一张试卷图片")
    tasks = []
    for f in files:
        if not f.content_type or not f.content_type.startswith("image/"):
            continue
        ext = ".jpg"
        if f.filename:
            for e in (".jpg", ".jpeg", ".png", ".webp"):
                if f.filename.lower().endswith(e):
                    ext = e
                    break
        name = f"{uuid.uuid4()}{ext}"
        save_path = test_dir() / name
        try:
            content = await f.read()
            save_path.write_bytes(content)
        except Exception:
            continue
        normalize_uploaded_image_orientation(save_path)
        tasks.append((save_path, save_path.stem, f.filename or name))
    if not tasks:
        raise HTTPException(status_code=400, detail="没有有效的图片文件")
    # 0924：大模型批改发起闸（无独立上传侧计面 ⇒ 按本批张数计面）
    quota_gate(charge_pages=len(tasks))
    batch_id = str(uuid.uuid4())
    with _batch_lock:
        _batch_results[batch_id] = {"total": len(tasks), "completed": [], "failed": [], "user_id": get_grading_user_id()}
    threading.Thread(
        target=_run_batch,
        args=(batch_id, tasks, modify_dir(), get_grading_user_id()),
        daemon=True,
    ).start()
    return {"ok": True, "batch_id": batch_id, "total": len(tasks)}


@router.get("/batch/{batch_id}")
async def api_grade_batch_status(batch_id: str):
    with _batch_lock:
        data = _batch_results.get(batch_id)
    if not data:
        raise HTTPException(status_code=404, detail="批次不存在或已过期")
    _assert_job_owner(data)
    for c in data.get("completed", []):
        if c.get("image_original") and not c["image_original"].startswith("http"):
            base = os.environ.get("GRADING_BASE_URL", "").rstrip("/")
            if base:
                c["image_original"] = base + c["image_original"] if c["image_original"].startswith("/") else c["image_original"]
                c["image_annotated"] = base + c["image_annotated"] if c.get("image_annotated", "").startswith("/") else c.get("image_annotated")
                c["image_marks_only"] = base + c["image_marks_only"] if c.get("image_marks_only", "").startswith("/") else c.get("image_marks_only")
    return {"ok": True, "total": data["total"], "completed": data["completed"], "failed": data["failed"]}


# ---------- 参照批改：文件夹 + 标准答案 ----------
@router.get("/folders")
async def api_list_folders(class_id: Optional[str] = None):
    try:
        prefix = _class_folder_prefix(class_id)
        if not prefix:
            return {"ok": True, "folders": [], "meta": {}}
        dirs = [d.name for d in correct_docs_dir().iterdir() if d.is_dir()]
        dirs = [n for n in dirs if n.startswith(prefix)]
        dirs = sorted(dirs)
        # R1 任务列表展示：读 meta.json 取学科/年级/作业类型（R2 起新建文件夹写入；旧夹无 meta 则为空）
        try:
            from app.grading.response_log_db import _read_folder_meta
        except Exception:
            _read_folder_meta = lambda _safe: {}
        meta = {}
        for n in dirs:
            safe = _safe_folder_name(n)
            m = _read_folder_meta(safe) if safe else {}
            meta[n] = {
                "subject": str(m.get("subject") or "").strip(),
                "grade": str(m.get("grade") or "").strip(),
                "homework_type": str(m.get("homework_type") or "").strip(),
            }
        return {"ok": True, "folders": dirs, "meta": meta}
    except Exception as e:
        return {"ok": False, "folders": [], "meta": {}, "msg": str(e)}


# 年级「规范值 → 原始写法」映射：Class.grade 存规范值（小学五年级/初一），
# 而筛选下拉与 meta.json 用原始写法（五年级/七年级），这里统一转成原始写法。
_GRADE_DENORMALIZE_MAP = {
    "小学一年级": "一年级", "小学二年级": "二年级", "小学三年级": "三年级",
    "小学四年级": "四年级", "小学五年级": "五年级", "小学六年级": "六年级",
    "初一": "七年级", "初二": "八年级", "初三": "九年级",
}


def _denormalize_grade(grade) -> str:
    g = str(grade or "").strip()
    return _GRADE_DENORMALIZE_MAP.get(g, g)


@router.get("/history-recent")
async def api_recent_grading_history(limit: int = 100, db: Session = Depends(get_db)):
    """「批改历史」页：聚合所有班级最近批改过的文件夹及每卷结果（按更新时间倒序）。"""
    try:
        folder_dirs = [d for d in correct_docs_dir().iterdir() if d.is_dir()]
    except Exception:
        folder_dirs = []
    rows = []
    try:
        from app.grading.response_log_db import _read_folder_meta
    except Exception:  # 兜底：meta.json 读取失败时返回空，不影响历史列表
        _read_folder_meta = lambda _safe: {}
    for d in folder_dirs:
        folder_name = d.name
        safe = _safe_folder_name(folder_name)
        if not safe:
            continue
        with _grading_history_lock:
            default = _read_grading_history(safe, "default")
            manual = _read_grading_history(safe, "manual")
            essay = _read_essay_history(safe)
        sources = [("智能批改", default), ("自主阅卷", manual), ("作文批改", essay)]
        completed_by_name: dict = {}
        engines: list = []
        failed_count = 0
        for label, data in sources:
            comp = data.get("completed") or {}
            if isinstance(comp, dict):
                for item in comp.values():
                    if not isinstance(item, dict):
                        continue
                    if _is_placeholder_completed_item(item):
                        continue
                    nm = item.get("name")
                    if nm:
                        completed_by_name.setdefault(nm, item)
                        engines.append(label)
            fail = data.get("failed") or {}
            if isinstance(fail, dict):
                failed_count += len(fail)
        if not completed_by_name and failed_count == 0:
            continue
        # 先只剔除内部字段，图片票据留到最后再签（避免为被 limit 裁掉的文件夹白签票据）
        completed_list = [
            {k: v for k, v in it.items() if k != "baidu_raw"}
            for it in completed_by_name.values()
        ]
        latest_ts = 0.0
        for p in (
            _grading_history_path(safe, "default"),
            _grading_history_path(safe, "manual"),
            _essay_history_path(safe),
        ):
            try:
                latest_ts = max(latest_ts, p.stat().st_mtime)
            except OSError:
                pass
        display = folder_name
        class_id = ""
        if folder_name.startswith("cls_") and "__" in folder_name:
            class_id = folder_name.split("__", 1)[0][4:]  # 去掉前缀 cls_
            display = folder_name.split("__", 1)[1] or folder_name
        # R7 任务列表筛选：读 meta.json 取学科/年级/作业类型（R2 起新夹写入；年级稍后回退 Class.grade）
        meta = _read_folder_meta(safe)
        rows.append({
            "folder_name": folder_name,
            "display_name": display,
            "class_id": class_id,
            "grade": _denormalize_grade(meta.get("grade") or ""),
            "subject": str(meta.get("subject") or "").strip(),
            "homework_type": str(meta.get("homework_type") or "").strip(),
            "status": "failed" if failed_count > 0 else "completed",
            "updated_at": (
                datetime.fromtimestamp(latest_ts, tz=timezone.utc).isoformat()
                if latest_ts
                else None
            ),
            "engines": sorted(set(engines)),
            "completed": completed_list,
            "failed_count": failed_count,
        })
    rows.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
    rows = rows[: max(1, min(limit, 200))]
    for row in rows:
        row["completed"] = _resign_history_list(row["completed"], drop_fields=("baidu_raw",))
    # 解析班级名/年级（class_id → 班级名称+年级），查询失败则回退到 class_id
    unique_ids = {r.get("class_id") for r in rows if r.get("class_id")}
    class_names: dict = {}
    class_grades: dict = {}
    if unique_ids:
        try:
            from app.models.class_model import Class
            for c in db.query(Class).filter(Class.id.in_(unique_ids)).all():
                class_names[c.id] = c.name or ""
                class_grades[c.id] = c.grade or ""
        except Exception:
            class_names = {}
            class_grades = {}
    for row in rows:
        row["class_name"] = class_names.get(row.get("class_id"), "") or row.get("class_id", "")
        if not row.get("grade"):
            row["grade"] = _denormalize_grade(class_grades.get(row.get("class_id"), ""))
    return {"ok": True, "folders": rows}


def _pdf_all_pages_to_images(pdf_path: Path, folder_name: str) -> list[Path]:
    """将 PDF 每一页转 JPG 保存到 test_paper_img/<folder>/<stem>_img.jpg、<stem>_img_2.jpg…，返回全部页路径。"""
    try:
        from app.grading.doc_convert import pdf_to_images
    except ImportError:
        return []
    if not pdf_path.is_file() or pdf_path.suffix.lower() != ".pdf":
        return []
    try:
        images = pdf_to_images(str(pdf_path), dpi=150)
    except Exception:
        return []
    if not images:
        return []
    img_dir = correct_docs_img_dir() / folder_name
    img_dir.mkdir(parents=True, exist_ok=True)
    stem = pdf_path.stem
    out: list[Path] = []
    for i, img in enumerate(images, start=1):
        out_path = img_dir / (f"{stem}_img.jpg" if i == 1 else f"{stem}_img_{i}.jpg")
        try:
            img.convert("RGB").save(str(out_path), quality=90)
            out.append(out_path)
        except Exception:
            continue
    return out


def _pdf_to_img_in_folder(pdf_path: Path, folder_name: str) -> Optional[Path]:
    """将 PDF 转 JPG（全页）保存到 test_paper_img/<folder>/，返回第一页路径；失败返回 None。"""
    pages = _pdf_all_pages_to_images(pdf_path, folder_name)
    return pages[0] if pages else None


def _copy_image_to_img_folder(source_path: Path, folder_name: str) -> Optional[Path]:
    """将图片文件原样复制到 test_paper_img/<folder>/，保持同名。用于 jpg/png 等。"""
    if not source_path.is_file():
        return None
    ext = source_path.suffix.lower()
    if ext not in _IMAGE_EXTS:
        return None
    try:
        img_dir = correct_docs_img_dir() / folder_name
        img_dir.mkdir(parents=True, exist_ok=True)
        dest = img_dir / source_path.name
        shutil.copy2(str(source_path), str(dest))
        return dest
    except Exception:
        return None


def _ensure_img_in_folder(source_path: Path, folder_name: str) -> Optional[Path]:
    """确保 test_paper_img 中有该文件的预览/批改用图：PDF 转 JPG，图片原样复制。"""
    if not source_path.is_file():
        return None
    ext = source_path.suffix.lower()
    if ext == ".pdf":
        return _pdf_to_img_in_folder(source_path, folder_name)
    if ext in _IMAGE_EXTS:
        return _copy_image_to_img_folder(source_path, folder_name)
    return None


def _get_grading_path(folder_safe: str, orig_path: Path) -> Optional[Path]:
    """根据 test_paper 中的原始文件，返回 test_paper_img 中用于 OCR/批改的路径。PDF->xxx_img.jpg，图片->同名。"""
    if not orig_path.is_file():
        return None
    ext = orig_path.suffix.lower()
    if ext == ".pdf":
        img_name = f"{orig_path.stem}_img.jpg"
    elif ext in _IMAGE_EXTS:
        img_name = orig_path.name
    else:
        return None
    img_path = correct_docs_img_dir() / folder_safe / img_name
    return img_path if img_path.is_file() else None


@router.post("/folders")
async def api_create_folder(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    raw = (body.get("name") or "").strip()
    class_id = (body.get("class_id") or "").strip()
    subject = (body.get("subject") or "").strip()
    grade = (body.get("grade") or "").strip()
    homework_type = (body.get("homework_type") or "").strip()
    prefix = _class_folder_prefix(class_id or None)
    safe = _safe_folder_name(raw)
    if not safe:
        raise HTTPException(status_code=400, detail="文件夹名称无效")
    safe_name = f"{prefix}{safe}" if prefix else safe
    path = correct_docs_dir() / safe_name
    if path.exists():
        raise HTTPException(status_code=400, detail="该名称已存在，请使用其他名称")
    path.mkdir(parents=True, exist_ok=True)
    (correct_docs_img_dir() / safe_name).mkdir(parents=True, exist_ok=True)
    # R2 作业采集：落盘学科/年级/班级/作业类型元数据，供逐题响应日志回填
    try:
        (path / "meta.json").write_text(
            json.dumps(
                {"subject": subject, "grade": grade, "homework_type": homework_type, "class_id": class_id},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass
    return {"ok": True, "name": safe_name}


@router.post("/folders/rename")
async def api_rename_folder(request: Request):
    """
    修改文件夹名称，同步重命名相关的目录和历史记录文件。
    名称不变时可只改作业类型（仅更新 meta.json）。
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    old_name = body.get("old_name", "").strip()
    new_name = body.get("new_name", "").strip()
    homework_type = (body.get("homework_type") or "").strip()

    if not old_name or not new_name:
        raise HTTPException(status_code=400, detail="新旧文件夹名称均不能为空")

    old_safe = _safe_folder_name(old_name)
    new_safe_suffix = _safe_folder_name(new_name)

    if not old_safe or not new_safe_suffix:
        raise HTTPException(status_code=400, detail="文件夹名称包含非法字符")

    if old_safe.startswith("cls_") and "__" in old_safe:
        prefix = old_safe.split("__", 1)[0] + "__"
        new_safe = f"{prefix}{new_safe_suffix}"
    else:
        new_safe = new_safe_suffix

    old_dir = correct_docs_dir() / old_safe
    new_dir = correct_docs_dir() / new_safe

    if not old_dir.exists():
        raise HTTPException(status_code=404, detail="原文件夹不存在")

    name_changed = (new_safe != old_safe)
    if name_changed:
        if new_dir.exists():
            raise HTTPException(status_code=400, detail="新文件夹名称已存在，请换一个名称")

        # 重命名主文档目录
        try:
            old_dir.rename(new_dir)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"重命名文档目录失败: {str(e)}")

        # 重命名图片转换目录 (如果有)
        old_img_dir = correct_docs_img_dir() / old_safe
        new_img_dir = correct_docs_img_dir() / new_safe
        if old_img_dir.exists():
            try:
                old_img_dir.rename(new_img_dir)
            except Exception:
                pass # 允许失败

        # 重命名 history json 文件
        for suffix in [".json", "__manual.json", "__essay.json"]:
            old_hist = grading_history_dir() / f"{old_safe}{suffix}"
            new_hist = grading_history_dir() / f"{new_safe}{suffix}"
            if old_hist.exists():
                try:
                    old_hist.rename(new_hist)
                except Exception:
                    pass
        try:
            from app.grading.wrong_question_db import rename_exam_wrong_question_file
            rename_exam_wrong_question_file(old_safe, new_safe)
        except Exception:
            pass

    # R2 作业采集：同步更新 meta.json 的作业类型（保留原有学科/年级/班级；名称不变时也可只改类型）
    if homework_type:
        try:
            target_dir = new_dir if name_changed else old_dir
            meta_path = target_dir / "meta.json"
            meta = {}
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:
                    meta = {}
            if not isinstance(meta, dict):
                meta = {}
            meta["homework_type"] = homework_type
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    return {"ok": True, "msg": "修改名称成功"}


@router.post("/folders/delete")
async def api_delete_folders(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """批量删除文件夹，需传入登录密码确认。请求体 JSON: { "folder_names": ["a","b"], "password": "xxx" }。"""
    try:
        body = await request.json()
    except Exception:
        body = {}
    folder_names = body.get("folder_names") or []
    password = (body.get("password") or "").strip()
    if not isinstance(folder_names, list) or not folder_names:
        raise HTTPException(status_code=400, detail="请选择要删除的文件夹")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    if not verify_password(password, user.password_hash):
        raise HTTPException(status_code=400, detail="密码错误")
    uid = get_grading_user_id()
    state = _scan_state(uid)
    with _scan_watcher_lock:
        target = state.get("target_folder")
        if target and target in folder_names:
            state["running"] = False
            if state.get("stop_event"):
                state["stop_event"].set()
            state["target_folder"] = None
            state["thread"] = None
            state["stop_event"] = None
    deleted = []
    for raw_name in folder_names:
        safe = _safe_folder_name(str(raw_name).strip())
        if not safe:
            continue
        path = correct_docs_dir() / safe
        img_path = correct_docs_img_dir() / safe
        folder_gone = not path.is_dir()
        if path.is_dir():
            try:
                shutil.rmtree(path)
                deleted.append(safe)
                folder_gone = True
            except Exception:
                pass
        if img_path.is_dir():
            try:
                shutil.rmtree(img_path)
            except Exception:
                pass
        hist = _grading_history_path(safe)
        manual_hist = _grading_history_path(safe, "manual")
        essay_hist = _essay_history_path(safe)
        for history_path in (hist, manual_hist, essay_hist):
            _delete_modify_files_referenced_by_history(history_path)
        _delete_reference_modify_artifacts(safe)
        if hist.is_file():
            try:
                hist.unlink()
            except Exception:
                pass
        if manual_hist.is_file():
            try:
                manual_hist.unlink()
            except Exception:
                pass
        if essay_hist.is_file():
            try:
                essay_hist.unlink()
            except Exception:
                pass
        try:
            from app.grading.wrong_question_db import delete_exam_wrong_question_file
            delete_exam_wrong_question_file(safe)
        except Exception:
            pass
        try:
            from app.grading.reference_vlm_grading import delete_reference_vlm_folder_artifacts
            delete_reference_vlm_folder_artifacts(safe)
        except Exception:
            pass
        try:
            scan_root = Path(scan_dir())
            for scan_sub in [scan_root / "_imported" / safe, scan_root / safe]:
                if scan_sub.is_dir():
                    shutil.rmtree(scan_sub)
        except Exception:
            pass
        if folder_gone:
            _sync_stats_on_folder_delete(uid, safe)
    return {"ok": True, "msg": f"已删除 {len(deleted)} 个文件夹", "deleted": deleted}


def _url_with_mtime(base: str, path: Path) -> str:
    """在 url 后附加 ?v=mtime 防止浏览器缓存旧图。"""
    if path.is_file():
        try:
            t = int(path.stat().st_mtime)
            sep = "&" if "?" in base else "?"
            return f"{base}{sep}v={t}"
        except Exception:
            pass
    return base


def _with_download_ticket(url: str, resource: str) -> str:
    """C6/H2：为文件直链追加当前用户的短时下载票；无用户上下文时原样返回（降级为无票 URL）。"""
    try:
        uid = get_grading_user_id()
    except RuntimeError:
        return url
    ticket = create_download_ticket(uid, resource)
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}ticket={ticket}"


def _re_sign_history_image_url(url: Optional[str]) -> Optional[str]:
    """历史记录里的留痕图直链自带 ?ticket= 短时下载票（默认 10 分钟过期）。

    批改时 image_original / image_annotated / image_marks_only 已把下载票固化进 URL；
    用户稍后重新打开批改页会拿到过期票，<img> 请求返回 401，表现为原试卷/留痕图空白。
    这里在读取历史时剥掉旧票、按当前用户重签新票，避免返回过期票。
    """
    if not url or not isinstance(url, str):
        return url
    base = url.split("?", 1)[0]
    for prefix, resource in (
        ("/api/v1/grading/modify/", "grading/modify"),
        ("/api/v1/grading/home_img/", "grading/home_img"),
    ):
        if base.startswith(prefix):
            filename = base[len(prefix):]
            if filename and "/" not in filename:
                return _with_download_ticket(base, f"{resource}/{filename}")
            return url
    return url


# 历史记录里需要重签下载票的图片字段（快速批改与作文批改共用）
_HISTORY_IMAGE_KEYS = ("image_original", "image_annotated", "image_marks_only", "image_marks_with_wrong_notes", "image_annotated_with_wrong_notes")


def _resign_history_images(item: dict) -> dict:
    """把一条历史记录里的图片直链换成新签的下载票（就地修改并返回）。

    所有「返回历史记录」的接口都必须经过这里：票据默认 10 分钟过期，而批改时
    已把它固化进 URL，不重签的话用户稍后回看会拿到过期票、<img> 返回 401。
    """
    for key in _HISTORY_IMAGE_KEYS:
        if item.get(key):
            item[key] = _re_sign_history_image_url(item[key])
    return item


def _resign_history_list(items, *, drop_fields: tuple = ()) -> list:
    """批量整理历史记录：剔除内部字段 → 重签图片下载票 → 按名称自然排序。

    快速批改与作文批改两条路径共用，避免只改一份、漏掉另一份。
    """
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        clean = (
            {k: v for k, v in item.items() if k not in drop_fields}
            if drop_fields
            else item
        )
        out.append(_resign_history_images(clean))
    out.sort(key=lambda x: _natural_sort_key(x.get("name", "")))
    return out


def _preview_url_for_pdf(folder_safe: str, pdf_name: str) -> str:
    """PDF 的预览 url：若 test_paper_img 中有对应 _img.jpg 则返回；否则尝试即时转换，成功后返回预览路径。"""
    stem = Path(pdf_name).stem
    img_name = f"{stem}_img.jpg"
    img_path = correct_docs_img_dir() / folder_safe / img_name
    if img_path.is_file():
        base = f"/api/v1/grading/folders/{folder_safe}/preview/{img_name}"
        # C6：追加当前用户短时下载票（resource 与 serve 端点校验一致）
        return _with_download_ticket(_url_with_mtime(base, img_path), f"grading/folders/{folder_safe}/preview/{img_name}")
    pdf_path = correct_docs_dir() / folder_safe / pdf_name
    if pdf_path.is_file() and _pdf_to_img_in_folder(pdf_path, folder_safe):
        img_path = correct_docs_img_dir() / folder_safe / img_name
        base = f"/api/v1/grading/folders/{folder_safe}/preview/{img_name}"
        return _with_download_ticket(_url_with_mtime(base, img_path), f"grading/folders/{folder_safe}/preview/{img_name}")
    base = f"/api/v1/grading/folders/{folder_safe}/file/{pdf_name}"
    return _with_download_ticket(_url_with_mtime(base, pdf_path), f"grading/folders/{folder_safe}/file/{pdf_name}")


def _preview_url_for_file(folder_safe: str, filename: str) -> str:
    """统一预览 url：PDF 走 _preview_url_for_pdf；图片若在 test_paper_img 中则返回 preview，否则 file。附 v=mtime 防缓存。"""
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return _preview_url_for_pdf(folder_safe, filename)
    if ext in _IMAGE_EXTS:
        img_path = correct_docs_img_dir() / folder_safe / filename
        if img_path.is_file():
            base = f"/api/v1/grading/folders/{folder_safe}/preview/{filename}"
            return _with_download_ticket(_url_with_mtime(base, img_path), f"grading/folders/{folder_safe}/preview/{filename}")
    orig_path = correct_docs_dir() / folder_safe / filename
    base = f"/api/v1/grading/folders/{folder_safe}/file/{filename}"
    return _with_download_ticket(_url_with_mtime(base, orig_path), f"grading/folders/{folder_safe}/file/{filename}")


def _preview_image_name_for_file(filename: str) -> Optional[str]:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return f"{Path(filename).stem}_img.jpg"
    if ext in _IMAGE_EXTS:
        return filename
    return None


def _answer_table_region_url(folder_safe: str, page_no: int, bbox) -> str:
    """答案表作答区缩略图直链（带当前用户下载票），前端 <img> 直接用。"""
    try:
        x1, y1, x2, y2 = (int(v) for v in (bbox or [])[:4])
    except (TypeError, ValueError):
        return ""
    if x2 <= x1 or y2 <= y1:
        return ""
    base = (
        f"/api/v1/grading/folders/{folder_safe}/answer-table/region-image"
        f"?page_no={int(page_no)}&x1={x1}&y1={y1}&x2={x2}&y2={y2}"
    )
    return _with_download_ticket(base, f"grading/folders/{folder_safe}/answer-table/region-image")


def _attach_answer_table_region_urls(folder_safe: str, page_no: int, questions: list) -> list:
    """给每个作答区槽挂上缩略图直链（就地修改并返回同一列表）。"""
    for entry in questions or []:
        if not isinstance(entry, dict):
            continue
        for slot in entry.get("slots") or []:
            if isinstance(slot, dict):
                slot["region_url"] = _answer_table_region_url(folder_safe, page_no, slot.get("bbox"))
    return questions


def _reference_standard_sources(folder_safe: str) -> dict[int, tuple[Path, Path]]:
    """Return standard-answer source and OCR image paths grouped by page."""
    result: dict[int, tuple[Path, Path]] = {}
    directory = correct_docs_dir() / folder_safe
    if not directory.is_dir():
        return result
    for path in directory.iterdir():
        if not path.is_file() or path.suffix.lower() not in _ALL_UPLOAD_EXTS:
            continue
        page_no = _standard_answer_page_no(path.name)
        if page_no is None or page_no in result:
            continue
        grading_path = _get_grading_path(folder_safe, path)
        if grading_path is None:
            if path.suffix.lower() in (".doc", ".docx"):
                grading_path = path
            else:
                grading_path = _ensure_img_in_folder(path, folder_safe) or path
        result[page_no] = (path, Path(grading_path))
    return result


def _answer_sheet_sources(folder_safe: str) -> dict[int, tuple[Path, Path]]:
    """答案纸（答案单独一张纸）所有页：返回 {页号: (源文件, 批改图)}。"""
    result: dict[int, tuple[Path, Path]] = {}
    directory = correct_docs_dir() / folder_safe
    if not directory.is_dir():
        return result
    for path in directory.iterdir():
        if not path.is_file() or path.suffix.lower() not in _ALL_UPLOAD_EXTS:
            continue
        page_no = _answer_sheet_page_no(path.name)
        if page_no is None or page_no in result:
            continue
        grading_path = _get_grading_path(folder_safe, path)
        if grading_path is None:
            if path.suffix.lower() in (".doc", ".docx"):
                grading_path = path
            else:
                grading_path = _ensure_img_in_folder(path, folder_safe) or path
        result[page_no] = (path, Path(grading_path))
    return result


def _load_answer_sheet_texts_for_folder(folder_safe: str) -> dict:
    """答案纸答案 {印刷题号: 文本}（扫描缓存按文件签名自动失效）；无答案纸回 {}。"""
    sources = _answer_sheet_sources(folder_safe)
    if not sources:
        return {}
    try:
        return load_or_build_answer_sheet_texts(
            folder_safe,
            [(str(source), str(grading)) for _page, (source, grading) in sorted(sources.items())],
        )
    except Exception:
        traceback.print_exc()
        return {}


def _manual_template_sources(folder_safe: str) -> dict[int, tuple[Path, Path]]:
    """Use every page in the first natural paper box as the manual layout template."""
    directory = correct_docs_dir() / folder_safe
    if not directory.is_dir():
        return {}
    candidates = [
        path
        for path in directory.iterdir()
        if path.is_file()
        and path.suffix.lower() in _ALL_UPLOAD_EXTS
        and not _is_standard_answer_filename(path.name)
        and not _is_answer_sheet_filename(path.name)
    ]
    candidates.sort(key=lambda path: _natural_sort_key(path.name))
    if not candidates:
        return {}
    first_box = _paper_box_display_name(candidates[0].name)
    result: dict[int, tuple[Path, Path]] = {}
    for path in candidates:
        if _paper_box_display_name(path.name) != first_box:
            continue
        page_no = _paper_box_page_no(path.name)
        if page_no in result:
            continue
        grading_path = _get_grading_path(folder_safe, path)
        if grading_path is None:
            if path.suffix.lower() in (".doc", ".docx"):
                grading_path = path
            else:
                grading_path = _ensure_img_in_folder(path, folder_safe) or path
        result[page_no] = (path, Path(grading_path))
    return result


def _manual_template_sample_sources(
    folder_safe: str, ratio: float = 0.2, min_boxes: int = 1, max_boxes: int = 12
) -> dict[str, dict[int, tuple[Path, Path]]]:
    """按约 ratio（默认 20%）抽样学生试卷框作为切题模板来源。

    返回 {box_name: {page_no: (原图, grading_path)}}。自然排序后取前 N 个框
    （N = ceil(len*ratio)，夹在 [min_boxes, max_boxes]），第一个框始终在内并作为「代表卷」。
    确定性取前 N（不随机）：同一场考试所有答题卡版式一致，仅百度切题抖动不同，前 N 已足够。
    """
    import math

    files = _manual_student_files(folder_safe)
    if not files:
        return {}
    boxes: dict[str, list[Path]] = {}
    order: list[str] = []
    for path in files:
        box = _paper_box_display_name(path.name)
        if box not in boxes:
            boxes[box] = []
            order.append(box)
        boxes[box].append(path)
    n_sample = max(min_boxes, min(max_boxes, math.ceil(len(order) * ratio)))
    sampled = order[:n_sample]

    result: dict[str, dict[int, tuple[Path, Path]]] = {}
    for box in sampled:
        pages: dict[int, tuple[Path, Path]] = {}
        for path in boxes[box]:
            page_no = _paper_box_page_no(path.name)
            if page_no in pages:
                continue
            grading_path = _get_grading_path(folder_safe, path)
            if grading_path is None:
                if path.suffix.lower() in (".doc", ".docx"):
                    grading_path = path
                else:
                    grading_path = _ensure_img_in_folder(path, folder_safe) or path
            pages[page_no] = (path, Path(grading_path))
        result[box] = pages
    return result


def _manual_layout_response_status(folder_safe: str) -> dict:
    sources = _manual_template_sources(folder_safe)
    status = manual_layout_status(folder_safe, sources)
    all_pages = {_paper_box_page_no(path.name) for path in _manual_student_files(folder_safe)}
    missing_template_pages = sorted(all_pages - set(sources))
    if missing_template_pages:
        status["confirmed"] = False
        status["stale_pages"] = sorted(set(status.get("stale_pages") or []) | set(missing_template_pages))
    return status


def _rename_path_if_exists(old_path: Path, new_path: Path, *, replace_existing: bool = False) -> None:
    if not old_path.is_file() or old_path == new_path:
        return
    try:
        same_file_target = new_path.exists() and old_path.resolve() == new_path.resolve()
    except Exception:
        same_file_target = False
    new_path.parent.mkdir(parents=True, exist_ok=True)
    if same_file_target:
        tmp_path = old_path.with_name(f".rename_tmp_{uuid.uuid4().hex}{old_path.suffix}")
        try:
            old_path.rename(tmp_path)
            tmp_path.rename(new_path)
        except Exception:
            try:
                if tmp_path.is_file() and not old_path.is_file():
                    tmp_path.rename(old_path)
            except Exception:
                pass
        return
    if new_path.exists():
        if not replace_existing:
            return
        try:
            new_path.unlink()
        except Exception:
            return
    try:
        old_path.rename(new_path)
    except Exception:
        pass


@router.get("/folders/{folder_name:path}/files")
async def api_list_files(folder_name: str):
    safe = _safe_folder_name(folder_name)
    if not safe:
        return {"ok": False, "files": [], "msg": "无效文件夹名"}
    dir_path = correct_docs_dir() / safe
    if not dir_path.is_dir():
        return {
            "ok": True,
            "files": [],
            "standard_answer": None,
            "standard_answers": [],
            "answer_sheets": [],
            "reference_layout": {"confirmed": False, "reviewed_pages": [], "stale_pages": []},
            "manual_layout": {"confirmed": False, "reviewed_pages": [], "stale_pages": []},
        }
    files = []
    standard_answer_names: list[tuple[int, str]] = []
    answer_sheet_names: list[tuple[int, str]] = []
    for f in dir_path.iterdir():
        if not f.is_file() or f.suffix.lower() not in _ALL_UPLOAD_EXTS:
            continue
        standard_page_no = _standard_answer_page_no(f.name)
        if standard_page_no is not None:
            standard_answer_names.append((standard_page_no, f.name))
            continue
        sheet_page_no = _answer_sheet_page_no(f.name)
        if sheet_page_no is not None:
            answer_sheet_names.append((sheet_page_no, f.name))
            continue
        t = _file_type(f.name)
        url = _preview_url_for_file(safe, f.name)
        files.append({"name": f.name, "url": url, "type": t})
    files.sort(key=lambda x: _natural_sort_key(x["name"]))
    standard_answers = []
    for page_no, filename in sorted(standard_answer_names, key=lambda item: item[0]):
        standard_answers.append(
            {
                "name": f"标准答案 P{page_no}",
                "filename": filename,
                "url": _preview_url_for_file(safe, filename),
                "type": _file_type(filename),
                "page_no": page_no,
            }
        )
    answer_sheets = []
    for page_no, filename in sorted(answer_sheet_names, key=lambda item: item[0]):
        answer_sheets.append(
            {
                "name": f"答案纸 P{page_no}",
                "filename": filename,
                "url": _preview_url_for_file(safe, filename),
                "type": _file_type(filename),
                "page_no": page_no,
            }
        )
    standard_answer = next(
        (item for item in standard_answers if item["page_no"] == 1),
        standard_answers[0] if standard_answers else None,
    )
    return {
        "ok": True,
        "files": files,
        "standard_answer": standard_answer,
        "standard_answers": standard_answers,
        "answer_sheets": answer_sheets,
        "reference_layout": reference_layout_status(
            safe,
            {page_no: source for page_no, (source, _grading) in _reference_standard_sources(safe).items()},
        ),
        "manual_layout": _manual_layout_response_status(safe),
    }


@router.post("/folders/{folder_name:path}/reference-layout/prepare")
def api_prepare_reference_layout(folder_name: str):
    """OCR only the standard-answer pages for the interactive cut-question review."""
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    sources = _reference_standard_sources(safe)
    if not sources:
        raise HTTPException(status_code=400, detail="请先上传标准答案试卷")

    ocr_items = [
        (f"__layout_standard_p{page_no}__", f"标准答案 P{page_no}", str(source_path))
        for page_no, (source_path, _grading_path) in sorted(sources.items())
    ]
    # 同步重活（整页 VL OCR）：def 进线程池跑，别堵事件循环（堵死全站点不进去）
    from app.services.heavy_budget import heavy_slot

    with heavy_slot("layout-prepare"):
        cache, errors = recognize_reference_vlm_batch(ocr_items, allow_empty=True)
    if errors:
        details = "；".join(
            f"{key.replace('__layout_standard_', '').replace('__', '')}: {error}"
            for key, error in errors.items()
        )
        raise HTTPException(status_code=502, detail=f"标准答案 OCR 识别失败：{details}")

    pages = []
    response_pages = []
    for page_no, (source_path, _grading_path) in sorted(sources.items()):
        key = f"__layout_standard_p{page_no}__"
        document = cache.get(key)
        if not document:
            raise HTTPException(status_code=502, detail=f"标准答案 P{page_no} 未返回 OCR 结果")
        layout_page = build_reference_layout_page(
            document,
            page_no=page_no,
            filename=source_path.name,
            image_url=_preview_url_for_file(safe, source_path.name),
        )
        page_record = {
            **layout_page,
            "source_path": str(source_path),
            "image_path": document.get("image_path"),
            "raw": document.get("raw") or {},
        }
        pages.append(page_record)
        response_pages.append(layout_page)
    prepare_id = save_reference_layout_prepare(safe, pages)
    return {"ok": True, "prepare_id": prepare_id, "pages": response_pages}


@router.get("/folders/{folder_name:path}/reference-layout")
async def api_get_reference_layout(folder_name: str):
    """Load the saved cut layout for editing; this endpoint never calls OCR."""
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    sources = _reference_standard_sources(safe)
    if not sources:
        raise HTTPException(status_code=400, detail="请先上传标准答案试卷")
    try:
        result = load_reference_layout_for_editing(
            safe,
            sources,
            {
                page_no: _preview_url_for_file(safe, source_path.name)
                for page_no, (source_path, _grading_path) in sources.items()
            },
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, **result}


@router.post("/folders/{folder_name:path}/reference-layout/confirm")
async def api_confirm_reference_layout(folder_name: str, body: dict = Body(...)):
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    prepare_id = str(body.get("prepare_id") or "").strip()
    pages = body.get("pages")
    if not prepare_id or not isinstance(pages, list):
        raise HTTPException(status_code=400, detail="缺少切题审查数据")
    try:
        result = confirm_reference_layout(safe, prepare_id, pages)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    status = reference_layout_status(
        safe,
        {page_no: source for page_no, (source, _grading) in _reference_standard_sources(safe).items()},
    )
    return {"ok": True, "confirmed": status["confirmed"], "reference_layout": status, "updated_at": result.get("updated_at")}


def _answer_table_standard_document(safe: str, page_no: int, source_path: Path, grading_path: Path):
    """答案表识别用的标准页文档：优先已确认切题，未确认时现场 OCR 出题框。"""
    try:
        confirmed = get_confirmed_reference_document(safe, page_no, source_path, str(grading_path))
    except Exception:
        confirmed = None
    if confirmed is not None:
        return confirmed, None
    cache_key = f"__answer_table_p{page_no}__"
    try:
        cache, errors = recognize_reference_vlm_batch(
            [(cache_key, f"标准答案 P{page_no}", str(grading_path))],
            allow_empty=True,
        )
    except Exception as exc:
        return None, f"标准答案 OCR 识别失败：{exc}"
    document = cache.get(cache_key)
    if not document:
        err = errors.get(cache_key)
        return None, f"标准答案 OCR 识别失败：{err}" if err else "标准答案 OCR 未返回结果"
    return {
        "name": source_path.name,
        "source_path": str(source_path),
        "image_path": str(document.get("image_path") or grading_path),
        "raw": document.get("raw") or {},
        "image_size": document.get("image_size") or [0, 0],
    }, None


def _answer_table_pages_response(safe: str, *, build: bool) -> list[dict]:
    """逐标准页组装答案表：build=True 时自动识别（有缓存直接用），失败给缓存兜底。"""
    pages_out: list[dict] = []
    # 答案纸（答案单独一张纸）按印刷题号的答案，逐标准页合并进识别结果
    sheet_texts = _load_answer_sheet_texts_for_folder(safe)
    for page_no, (source_path, grading_path) in sorted(_reference_standard_sources(safe).items()):
        entry: dict = {
            "page_no": page_no,
            "filename": source_path.name,
            "questions": [],
            "error": "",
            # 答题区框总览底图（与切题审查同源预览图）+ 批改图坐标尺寸
            "image_url": _preview_url_for_file(safe, source_path.name),
            "image_size": None,
        }
        cached = read_reference_answer_table_page(safe, page_no)
        if not build:
            entry["questions"] = cached.get("questions") or []
            entry["updated_at"] = cached.get("updated_at")
            entry["image_size"] = cached.get("image_size") or None
            pages_out.append(entry)
            continue
        standard_doc, doc_error = _answer_table_standard_document(safe, page_no, source_path, grading_path)
        if standard_doc is None:
            entry["questions"] = cached.get("questions") or []
            entry["updated_at"] = cached.get("updated_at")
            entry["image_size"] = cached.get("image_size") or None
            entry["error"] = doc_error or "标准答案识别失败"
            pages_out.append(entry)
            continue
        try:
            table = load_or_build_reference_answer_table(
                safe, page_no, standard_doc, answer_sheet_texts=sheet_texts
            )
        except Exception as exc:
            traceback.print_exc()
            entry["questions"] = cached.get("questions") or []
            entry["updated_at"] = cached.get("updated_at")
            entry["image_size"] = cached.get("image_size") or None
            entry["error"] = f"标准答案识别失败：{exc}"
            pages_out.append(entry)
            continue
        entry["questions"] = table.get("questions") or cached.get("questions") or []
        entry["updated_at"] = table.get("updated_at") or cached.get("updated_at")
        entry["image_size"] = (
            table.get("image_size")
            or cached.get("image_size")
            or standard_doc.get("image_size")
            or None
        )
        pages_out.append(entry)
    for entry in pages_out:
        _attach_answer_table_region_urls(safe, entry.get("page_no") or 0, entry.get("questions") or [])
    return pages_out


@router.get("/folders/{folder_name:path}/answer-table")
def api_get_reference_answer_table(folder_name: str, build: int = 1):
    """上传完标准答案自动识别每道题答案；识别结果可手动修改（POST .../save）。"""
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    if not _reference_standard_sources(safe):
        raise HTTPException(status_code=400, detail="请先上传标准答案试卷")
    # 重建=逐槽 VL 转写+PIL 裁剪，分钟级重活：def 进线程池+总闸排队，别堵事件循环
    from app.services.heavy_budget import heavy_slot

    with heavy_slot("answer-table"):
        return {"ok": True, "pages": _answer_table_pages_response(safe, build=bool(build))}


@router.post("/folders/{folder_name:path}/answer-table/save")
async def api_save_reference_answer_table(folder_name: str, body: dict = Body(...)):
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    try:
        page_no = int(body.get("page_no") or 0)
    except (TypeError, ValueError):
        page_no = 0
    questions = body.get("questions")
    if page_no <= 0 or not isinstance(questions, list) or not questions:
        raise HTTPException(status_code=400, detail="缺少答案修改数据")
    try:
        saved = save_reference_answer_table_edits(safe, page_no, questions)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "ok": True,
        "page_no": page_no,
        "updated_at": saved.get("updated_at"),
        "questions": _attach_answer_table_region_urls(safe, page_no, saved.get("questions") or []),
    }


@router.post("/folders/{folder_name:path}/answer-table/rebuild")
def api_rebuild_reference_answer_table(folder_name: str, body: Optional[dict] = Body(default=None)):
    """强制重新识别答案表；reset_edits=True 连手动修改一起清掉。"""
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    body = body or {}
    try:
        page_no = int(body.get("page_no") or 0)
    except (TypeError, ValueError):
        page_no = 0
    invalidate_reference_answer_table(safe, page_no or None, reset_edits=bool(body.get("reset_edits")))
    if not _reference_standard_sources(safe):
        raise HTTPException(status_code=400, detail="请先上传标准答案试卷")
    from app.services.heavy_budget import heavy_slot

    with heavy_slot("answer-table"):
        return {"ok": True, "pages": _answer_table_pages_response(safe, build=True)}


def _answer_sheet_rows(texts: dict) -> list[dict]:
    """{题号: 答案} 排成专窗行（数字题号升序在前，其它在后）。"""

    def _key(item):
        no = str(item[0])
        try:
            return (0, int(no), no)
        except ValueError:
            return (1, 0, no)

    return [{"no": str(k), "answer": str(v)} for k, v in sorted(texts.items(), key=_key)]


@router.get("/folders/{folder_name:path}/answer-sheet")
def api_get_answer_sheet(folder_name: str, build: int = 1):
    """答案纸专窗：识别答案纸上每道题的答案（先看答案，再合并进答题区）。"""
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    sources = _answer_sheet_sources(safe)
    if not sources:
        raise HTTPException(status_code=400, detail="请先上传答案纸")
    pages = [
        (str(source), str(grading))
        for _page, (source, grading) in sorted(sources.items())
    ]
    error = ""
    if build:
        try:
            # 整版 VL 扫描是重活：def 进线程池+总闸，别堵事件循环
            from app.services.heavy_budget import heavy_slot

            with heavy_slot("answer-sheet"):
                texts = load_or_build_answer_sheet_texts(safe, pages)
        except Exception as exc:
            traceback.print_exc()
            texts = read_answer_sheet_texts(safe)
            error = f"答案纸识别失败：{exc}"
    else:
        texts = read_answer_sheet_texts(safe)
    return {
        "ok": True,
        "pages": [
            {"page_no": page_no, "filename": source.name}
            for page_no, (source, _grading) in sorted(sources.items())
        ],
        "rows": _answer_sheet_rows(texts),
        "error": error,
    }


@router.post("/folders/{folder_name:path}/answer-sheet/save")
def api_save_answer_sheet(folder_name: str, body: dict = Body(...)):
    """保存答案纸识别结果（专窗核对/改错后点「合并进答案表」）。

    rescan=true 丢弃缓存重新识别（扫错重试）；否则按老师确认过的答案落盘，
    后续答案表重建直接吃这份人工修正版。
    """
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    sources = _answer_sheet_sources(safe)
    if not sources:
        raise HTTPException(status_code=400, detail="请先上传答案纸")
    pages = [
        (str(source), str(grading))
        for _page, (source, grading) in sorted(sources.items())
    ]
    if bool(body.get("rescan")):
        clear_answer_sheet_cache(safe)
        from app.services.heavy_budget import heavy_slot

        with heavy_slot("answer-sheet"):
            texts = load_or_build_answer_sheet_texts(safe, pages)
    else:
        by_printed_no = body.get("by_printed_no")
        if not isinstance(by_printed_no, dict):
            raise HTTPException(status_code=400, detail="缺少答案数据")
        try:
            texts = save_answer_sheet_texts(safe, pages, by_printed_no)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "rows": _answer_sheet_rows(texts)}


def _manual_student_files(folder_safe: str) -> list[Path]:
    directory = correct_docs_dir() / folder_safe
    if not directory.is_dir():
        return []
    files = [
        path
        for path in directory.iterdir()
        if path.is_file()
        and path.suffix.lower() in _ALL_UPLOAD_EXTS
        and not _is_standard_answer_filename(path.name)
        and not _is_answer_sheet_filename(path.name)
        and not _is_original_paper_filename(path.name)
        and not path.stem.endswith("试卷")
    ]
    return sorted(files, key=lambda path: _natural_sort_key(path.name))


def _materialize_manual_layout_history(folder_safe: str, layout_data: dict) -> int:
    saved_pages = layout_data.get("pages") if isinstance(layout_data.get("pages"), dict) else {}
    files = _manual_student_files(folder_safe)
    completed: dict[str, dict] = {}
    scoring_config: dict[str, float] = {}
    for page_key, saved in saved_pages.items():
        layout = saved.get("layout") if isinstance(saved, dict) else None
        if not isinstance(layout, dict):
            continue
        for question in layout.get("questions") or []:
            if not isinstance(question, dict):
                continue
            for slot in question.get("answer_slots") or []:
                if not isinstance(slot, dict):
                    continue
                scoring_config[f"p{page_key}:{slot.get('slot_id')}"] = float(slot.get("max_score") or 1)

    for path in files:
        page_no = _paper_box_page_no(path.name)
        saved = saved_pages.get(str(page_no))
        layout_page = saved.get("layout") if isinstance(saved, dict) else None
        if not isinstance(layout_page, dict):
            raise RuntimeError(f"模板缺少 P{page_no}，无法切分 {path.name}")
        grading_path = _get_grading_path(folder_safe, path)
        if grading_path is None:
            grading_path = _ensure_img_in_folder(path, folder_safe) or path
        blocks, image_size = manual_layout_blocks_for_image(layout_page, str(grading_path))
        result = {
            "type": "manual_analyze",
            "version": 2,
            "manual_status": "ungraded",
            "template_page_no": page_no,
            "image_size": image_size,
            "blocks": blocks,
            "decisions": {},
            "scores": {},
            "score_total": 0,
            "max_score_total": round(sum(float(block.get("max_score") or 0) for block in blocks), 2),
        }
        completed[path.name] = {
            "name": path.name,
            "image_original": _preview_url_for_file(folder_safe, path.name),
            "image_annotated": "",
            "image_marks_only": "",
            "marks_only_filename": "",
            "score_total": None,
            "question_scores": {},
            "result": json.dumps(result, ensure_ascii=False),
        }

    # A confirmed manual layout starts a new authoritative grading run. Keep
    # the layout itself, but replace every result produced by an older mode.
    # 重新切题会整体重建历史，这里先保住已保存的标准答案（answer_key），
    # 否则“确认分值→重新切题”会把用户已录入的标准答案清掉。
    with _grading_history_lock:
        _pre = _read_grading_history(folder_safe, "manual")
    _answer_key = _pre.get("answer_key") if isinstance(_pre, dict) else None
    _replace_folder_grading_run(folder_safe, "manual")
    with _grading_history_lock:
        old_data = _read_grading_history(folder_safe, "manual")
        if isinstance(_answer_key, dict) and _answer_key:
            old_data["answer_key"] = _answer_key
        old_data["completed"] = completed
        old_data["failed"] = {}
        old_data["scoring_config"] = scoring_config
        old_data["manual_layout_updated_at"] = layout_data.get("updated_at")
        _write_grading_history(folder_safe, old_data, "manual")
    return len(completed)


@router.post("/folders/{folder_name:path}/manual-layout/prepare")
def api_prepare_manual_layout(folder_name: str, body: Optional[dict] = Body(default=None)):
    """生成可编辑的自主阅卷切题模板，source 决定框线来源（两种同构共用后续全链）。

    source=answer_card（默认，答题卡）：先识别视觉题号、再按答题卡框线切题。不再用
    百度「试卷切题」（paper_cut_edu，切得乱、漏题、把选择题切成手写小块），改用框线检测
    （detect_answer_card_boxes）切作答格 + 通用 OCR 识别印刷题号，把每个作答格挂到它
    上方/左侧的题号上。选择题整题跳过，display_no 用卷面原题号（1..8、15..21）。
    source=reference（试卷手动批改）：普通试卷没有答题卡印刷框线（框线检测会「未识别到
    题目」），改取标准答案识别列表已确认的标准答题区（reference layout）题目/作答区框，
    等比缩放到模板卷面坐标系。
    """
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    source = str((body or {}).get("source") or "answer_card").strip().lower()
    if source not in ("answer_card", "reference"):
        raise HTTPException(status_code=400, detail="无效切题来源")
    sources = _manual_template_sources(safe)
    if not sources:
        raise HTTPException(status_code=400, detail="请先上传至少一张学生试卷")

    ref_pages: dict = {}
    if source == "reference":
        ref = load_reference_layout(safe)
        if not isinstance(ref, dict) or ref.get("status") != "confirmed":
            raise HTTPException(status_code=400, detail="请先在「标准答案识别列表」确认标准答题区")
        ref_pages = ref.get("pages") if isinstance(ref.get("pages"), dict) else {}

    # 已确认的原始试卷分值（若有）注入每题 max_score，切题后即带真实分值。
    paper_scores = load_paper_scores(safe)
    pending_pages: list[dict] = []
    response_pages: list[dict] = []
    number_offset = 0  # 标准答题区页内题号 → 全卷题号（与 _scoring_title_offsets 同口径）
    for page_no, (source_path, grading_path) in sorted(sources.items()):
        if source == "reference":
            ref_page = ref_pages.get(str(page_no))
            if not isinstance(ref_page, dict):
                raise HTTPException(status_code=502, detail=f"标准答题区缺少 P{page_no}，无法切分试卷")
            try:
                page = build_manual_layout_page_from_reference_layout(
                    ref_page,
                    page_no=page_no,
                    filename=source_path.name,
                    image_url=_preview_url_for_file(safe, source_path.name),
                    image_path=str(grading_path),
                    number_offset=number_offset,
                )
            except RuntimeError as exc:
                raise HTTPException(status_code=502, detail=f"P{page_no} 切题失败：{exc}") from exc
            if page.get("questions"):
                number_offset = max(int(q.get("display_no") or 0) for q in page["questions"])
        else:
            try:
                page = build_manual_layout_page_from_boxes(
                    str(grading_path),
                    page_no=page_no,
                    filename=source_path.name,
                    image_url=_preview_url_for_file(safe, source_path.name),
                )
            except RuntimeError as exc:
                raise HTTPException(status_code=502, detail=f"P{page_no} 切题失败：{exc}") from exc
            if not page.get("questions"):
                raise HTTPException(status_code=502, detail=f"模板试卷 P{page_no} 未识别到题目")
        apply_paper_scores_to_page(page, paper_scores)
        pending_pages.append(
            {
                **copy.deepcopy(page),
                "source_path": str(source_path),
                "image_path": str(grading_path),
            }
        )
        response_pages.append(page)
    prepare_id = save_manual_layout_prepare(safe, pending_pages)
    return {"ok": True, "prepare_id": prepare_id, "pages": response_pages}


_CN_NUM = "一二三四五六七八九十"

# 只保留卷面「段标题/分值规则」词，丢弃题干/选项等噪声。
# 二栏排版下整卷按 (y,x) 排序会把题干文本插进段标题里，把「第13、14小题…每小题3分」隔断，
# 只留含分值标记的词再排序，即可还原出干净的段标题串。
_HEADER_TOKEN_RE = re.compile(
    r"[一二三四五六七八九十]+[、.．]"
    r"|共\s*\d+(?:\.\d+)?\s*分"
    r"|每[空小]题"
    r"|小题"
    r"|各\s*\d+(?:\.\d+)?\s*分"
)


def _explicit_in(sec: str) -> dict[int, float]:
    """在单段文本里解析显式题号分值（第N~M / 第N,M / 第N小题…X分），返回 {题号: 分值}。"""
    out: dict[int, float] = {}
    for m in re.finditer(
        r"第\s*(\d{1,3})\s*[~\-至]\s*(\d{1,3})\s*小题[^;；。]{0,40}?每小题\s*(\d+(?:\.\d+)?)\s*分",
        sec,
    ):
        a, b, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
        if a <= b:
            for q in range(a, b + 1):
                out[q] = s
    for m in re.finditer(
        r"第\s*(\d{1,3}(?:\s*[,，、]\s*\d{1,3})+)\s*小题[^;；。]{0,40}?每小题\s*(\d+(?:\.\d+)?)\s*分",
        sec,
    ):
        s = float(m.group(2))
        for q in re.findall(r"\d+", m.group(1)):
            out[int(q)] = s
    for m in re.finditer(
        r"第\s*(\d{1,3}(?:\s*[,，、]\s*\d{1,3})+)\s*小题各\s*(\d+(?:\.\d+)?)\s*分",
        sec,
    ):
        s = float(m.group(2))
        for q in re.findall(r"\d+", m.group(1)):
            out[int(q)] = s
    for m in re.finditer(r"第\s*(\d{1,3})\s*小题\s*(\d+(?:\.\d+)?)\s*分", sec):
        q, s = int(m.group(1)), float(m.group(2))
        if q not in out:
            out[q] = s
    return out


def _snap_score(v: float) -> float:
    """分值归到 0.5 粒度：卷面分值最小单位是 0.5 或 1，不允许两位小数（2.67→2.5、1.33→1.5）。"""
    if v <= 0:
        return 0.0
    return round(v * 2) / 2


def _parse_original_paper_scores(text: str) -> dict[int, float]:
    """从原始试卷 OCR 文本确定性解析每题分值。题号严格照抄卷面印刷，绝不自行编号。

    试卷各段标题印着分值规则，例如：
      一、填空题[共16分,每空1分]
      二、选择题(共14分,第9~12小题…每小题2分;第13,14小题…每小题3分)
      三、计算题(共22分,第15,16小题各7分,第17小题8分)
      四、实验与探究题(共28分,每小题7分)
    返回 {题号: 分值}。显式题号（第N~M/第N,M/第N小题）直接按印刷题号落分；
    无显式题号的段（每小题X分 / 每空X分）按段总分与显式题号边界推算。
    """
    scores: dict[int, float] = {}
    if not text:
        return scores
    t = text
    for a, b in (
        ("－", "-"), ("—", "-"), ("～", "~"), ("〜", "~"),
        ("﹒", "."), ("．", "."), ("·", "."),
    ):
        t = t.replace(a, b)

    def _set(q: int, s: float) -> None:
        if q >= 1 and s > 0:
            scores[int(q)] = _snap_score(s)

    # 1) 显式题号（第N~M / 第N,M / 第N小题…X分）：严格照抄卷面印刷题号。
    for q, s in _explicit_in(t).items():
        _set(q, s)
    lo = min(scores) if scores else None
    hi = max(scores) if scores else None

    # 2) 无显式题号的段（每小题X分 / 每空X分）：按段总分与显式题号边界推算。
    sections = [s for s in re.split(r"(?=[" + _CN_NUM + r"]+[、.．])", t) if s.strip()]
    cursor = (hi + 1) if hi is not None else 1
    for sec in sections:
        if _explicit_in(sec):
            continue  # 该段已有显式题号，跳过段级推断
        em = re.search(r"每小题\s*(\d+(?:\.\d+)?)\s*分", sec)
        if em:
            s = float(em.group(1))
            cm = re.search(r"共\s*(\d+(?:\.\d+)?)\s*分", sec)
            total = float(cm.group(1)) if cm else 0.0
            count = int(round(total / s)) if (cm and s > 0 and total > 0) else 0
            if 0 < count <= 30:
                for q in range(cursor, cursor + count):
                    _set(q, s)
                cursor += count
            continue
        pm = re.search(r"每空\s*(\d+(?:\.\d+)?)\s*分", sec)
        if pm:
            per_blank = float(pm.group(1))
            cm = re.search(r"共\s*(\d+(?:\.\d+)?)\s*分", sec)
            total = float(cm.group(1)) if cm else 0.0
            fill_hi = (lo - 1) if lo is not None else None
            if fill_hi and fill_hi >= 1 and per_blank > 0:
                blanks_per = _count_blanks_per_question(sec, fill_hi)
                if blanks_per is None and total > 0:
                    total_blanks = int(round(total / per_blank))
                    base, rem = divmod(total_blanks, fill_hi)
                    blanks_per = [base + (1 if i < rem else 0) for i in range(fill_hi)]
                if blanks_per:
                    for q, b in enumerate(blanks_per, start=1):
                        if b > 0:
                            _set(q, b * per_blank)
    return scores


def _count_blanks_per_question(text: str, n: int) -> Optional[list[int]]:
    """按题号 1..n 切分文本，数每题的作答空（括号/下划线/方格），返回每题空数列表。

    数不出（分段不齐 / 每段空数全 0）返回 None，由调用方均摊兜底。
    """
    # 题号行锚点：行首「数字+点/顿号」或独立「数字.」词。
    anchors: list[tuple[int, int]] = []
    for m in re.finditer(r"(?:^|\s)(\d{1,2})\s*[.、]", text):
        q = int(m.group(1))
        if 1 <= q <= n:
            anchors.append((q, m.start()))
    if len(anchors) < 2:
        return None
    blanks: list[int] = []
    for i, (q, pos) in enumerate(anchors):
        end = anchors[i + 1][1] if i + 1 < len(anchors) else len(text)
        seg = text[pos:end]
        b = _count_blanks(seg)
        blanks.append(b)
    if sum(blanks) <= 0:
        return None
    return blanks


def _count_blanks(seg: str) -> int:
    """数一段题干里的作答空：下划线串、空括号、方格。"""
    cnt = 0
    cnt += len(re.findall(r"[＿_﹏﹍─—]{2,}", seg))  # 下划线（成串算 1 空）
    cnt += len(re.findall(r"[（(]\s*[）)]", seg))  # 空括号
    cnt += len(re.findall(r"□", seg))  # 方格
    return cnt


@router.post("/folders/{folder_name:path}/original-paper/scores")
def api_recognize_original_paper_scores(folder_name: str, db: Session = Depends(get_db)):
    """识别原始试卷上每题的分值，返回逐题清单供确认页核对。

    定位已上传的「原始试卷」页 → 通用 OCR 读卷面印刷文字 → 正则确定性解析分值。
    题号严格照抄卷面印刷（第9~12小题 / 第13,14小题 / 第15,16小题 / 第17小题 / 每小题…），
    绝不自行编题号、绝不重排。识别结果仅作预填，最终以用户确认页逐题核对为准。
    """
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    sources = _original_paper_sources(safe)
    if not sources:
        raise HTTPException(status_code=400, detail="请先上传原始试卷（含每题分值的那份卷子）")

    texts: list[str] = []
    for _page_no, (_source, grading_path) in sorted(sources.items()):
        try:
            words = _baidu_ocr_text(str(grading_path))
        except Exception:
            continue
        if not words:
            continue
        header_words = [w for w in words if _HEADER_TOKEN_RE.search(w["words"])]
        if not header_words:
            header_words = words
        header_words = sorted(header_words, key=lambda w: (w["bbox"][1], w["bbox"][0]))
        texts.append(" ".join(w["words"] for w in header_words))

    # 全部页拼成一段再解析一次：显式题号（第9~12/第13,14/第15,16/第17）与
    # 无题号段（填空每空1分 / 实验每小题7分）要靠整卷的题号上下界推算，
    # 分页解析会让第 2 页的「实验与探究题」算不出 18~21。
    merged = _parse_original_paper_scores(" ".join(texts))
    if not merged:
        raise HTTPException(
            status_code=502,
            detail="未能识别出原始试卷上的题目分值，请确认上传的是含分值标注的原始试卷（段标题里要有「第X小题Y分 / 每小题Y分 / 每空Y分」）",
        )

    items = [
        {"no": q, "title": "", "score": merged[q]}
        for q in sorted(merged)
    ]
    total = round(sum(it["score"] for it in items), 2)
    return {"ok": True, "items": items, "total": total}


@router.post("/folders/{folder_name:path}/original-paper/scores/apply")
def api_apply_original_paper_scores(folder_name: str, body: dict = Body(...)):
    """确认页提交的逐题分值写回，后续切题时注入每题 max_score。"""
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    scores = body.get("scores") if isinstance(body, dict) else None
    if not isinstance(scores, dict) or not scores:
        raise HTTPException(status_code=400, detail="缺少逐题分值")
    save_paper_scores(safe, scores)
    return {"ok": True, "count": len(scores)}


@router.get("/folders/{folder_name:path}/manual-layout")
def api_get_manual_layout(folder_name: str):
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    sources = _manual_template_sources(safe)
    try:
        result = load_manual_layout_for_editing(
            safe,
            sources,
            {page_no: _preview_url_for_file(safe, source.name) for page_no, (source, _grading) in sources.items()},
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, **result}


@router.post("/folders/{folder_name:path}/manual-layout/confirm")
def api_confirm_manual_layout(folder_name: str, body: dict = Body(...)):
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    prepare_id = str(body.get("prepare_id") or "").strip()
    pages = body.get("pages")
    if not prepare_id or not isinstance(pages, list):
        raise HTTPException(status_code=400, detail="缺少切题审查数据")
    try:
        layout_data = confirm_manual_layout(safe, prepare_id, pages)
        paper_count = _materialize_manual_layout_history(safe, layout_data)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    status = _manual_layout_response_status(safe)
    return {
        "ok": True,
        "confirmed": status.get("confirmed", False),
        "manual_layout": status,
        "paper_count": paper_count,
        "updated_at": layout_data.get("updated_at"),
    }


@router.get("/folders/{folder_name:path}/grading-history")
async def api_get_grading_history(folder_name: str, engine: str = "default"):
    """读取本文件夹已持久化的批改记录（含 AI 解析与留痕图 URL），重启后端后仍可用。"""
    safe = _safe_folder_name(folder_name)
    if not safe:
        return {"ok": False, "completed": [], "failed": [], "scoring_config": None}
    with _grading_history_lock:
        data = _read_grading_history(safe, engine)
    failed = list(data.get("failed", {}).values())
    completed_raw = []
    for item in data.get("completed", {}).values():
        if _is_placeholder_completed_item(item if isinstance(item, dict) else {}):
            if isinstance(item, dict) and item.get("name"):
                failed.append({
                    "name": item.get("name"),
                    "msg": "未识别到可批改题目，未生成 AI 解析和留痕，请重新批改或检查试卷图片质量。",
                })
            continue
        completed_raw.append(item)
    missing_questions = _detect_missing_questions(data, engine)
    return {
        "ok": True,
        "completed": _resign_history_list(completed_raw, drop_fields=("baidu_raw",)),
        "failed": failed,
        "scoring_config": data.get("scoring_config"),
        "full_score": data.get("full_score"),
        "question_structure": data.get("question_structure"),
        "major_scores": data.get("major_scores"),
        "major_order": data.get("major_order"),
        "major_titles": data.get("major_titles"),
        "paper_subs": data.get("paper_subs"),
        "missing_questions": missing_questions,
        "inconsistent_count": len(missing_questions),
    }


@router.get("/folders/{folder_name:path}/score-summary")
def api_get_folder_score_summary(
    folder_name: str,
    user_id: str = Depends(get_current_user_id),
):
    """轻成绩表（对齐批改君 exam_scores）：本文件夹每生一行成绩汇总。

    读时按批改历史重建（幂等，旧文件夹自愈）再返回；未统分条目不落行。
    用 def 不用 async：写库+读历史放线程池，不占事件循环（防全站假死口径）。
    """
    safe = _safe_folder_name(folder_name)
    if not safe:
        return {"ok": False, "rows": [], "msg": "文件夹不存在"}
    try:
        from app.grading.score_summary_db import (
            get_folder_score_summaries,
            sync_folder_score_summaries,
        )

        summary = sync_folder_score_summaries(user_id, safe)
        rows = get_folder_score_summaries(user_id, safe)
    except Exception as e:
        return {"ok": False, "rows": [], "msg": str(e)}
    return {"ok": True, "rows": rows, "count": len(rows), "summary": summary}


@router.get("/folders/{folder_name:path}/essay-grading-history")
async def api_get_essay_grading_history(folder_name: str):
    """读取本文件夹已持久化的「作文批改」记录（仅作文批改使用），重启后端后仍可用。"""
    safe = _safe_folder_name(folder_name)
    if not safe:
        return {"ok": False, "completed": [], "failed": []}
    with _essay_history_lock:
        data = _read_essay_history(safe)
    failed = list(data.get("failed", {}).values())
    return {
        "ok": True,
        "completed": _resign_history_list(
            data.get("completed", {}).values(),
            drop_fields=_ESSAY_INTERNAL_FIELDS,
        ),
        "failed": failed,
    }


def _redraw_essay_trace_images(safe: str, filename: str, item: dict, paper_note: str) -> dict:
    """重绘作文留痕图：旁批不变，尾批用老师手写 paper_note 替换（仅最后一页）。

    绘制主体照抄 _run_essay_grade 的留痕段，复用 _essay_trace_* / _extract_essay_* 系列函数。
    返回更新后的 item（含新的 image_* URL 与 paper_note 字段）。
    """
    from PIL import Image, ImageDraw, ImageOps

    result_text = str(item.get("result") or "")
    # 分数字符串：优先 <essay_score> 标签，其次 score_total
    m_score = re.search(r"<essay_score>\s*(.*?)\s*</essay_score>", result_text, flags=re.S)
    score_text = (m_score.group(1).strip() if m_score else "").strip()
    if not score_text and item.get("score_total") is not None:
        try:
            st = float(item.get("score_total"))
            score_text = str(int(st)) if float(st).is_integer() else str(st)
        except (TypeError, ValueError):
            score_text = ""
    # R18/R16 等级制：优先用已存等级，缺省从总分 + 维度配置推导（兼容历史记录）
    essay_grade = str(item.get("essay_grade") or "").strip()
    if not essay_grade and item.get("score_total") is not None:
        try:
            from app.grading.essay_grading import derive_essay_grade
            essay_grade = derive_essay_grade(item.get("score_total"), _resolve_essay_item_dimensions(item))
        except Exception:
            essay_grade = ""
    segment_comments = _extract_essay_segment_comments(result_text)
    teacher_summary = paper_note.strip() if paper_note and paper_note.strip() else _extract_essay_teacher_summary(result_text)

    # 同组页（多页作文）：group_pages 记录同组所有页名，用于计算 page_index / page_count
    group_pages = item.get("group_pages") or []
    if not isinstance(group_pages, list) or not group_pages:
        group_pages = [filename]
    if filename not in group_pages:
        group_pages = [filename] + [p for p in group_pages if p != filename]
    page_index = group_pages.index(filename)
    page_count = len(group_pages)
    is_last_page = page_index == page_count - 1

    # 原图路径
    orig_path = correct_docs_dir() / safe / filename
    try:
        gp = _ensure_img_in_folder(orig_path, safe) or orig_path
        img_path = _get_grading_path(safe, orig_path) or gp
    except Exception:
        img_path = orig_path
    if not os.path.isfile(str(img_path)):
        raise HTTPException(status_code=404, detail=f"批改用原图不存在: {filename}")

    file_stem = f"essay_{safe}_{Path(filename).stem}"
    path = os.path.abspath(str(img_path))
    os.makedirs(str(modify_dir()), exist_ok=True)
    ext = os.path.splitext(path)[1].lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png"):
        ext = ".jpg"
    original_name = f"original_{file_stem}{ext}"
    annotated_name = f"annotated_{file_stem}{ext}"
    original_path = os.path.join(str(modify_dir()), original_name)
    annotated_path = os.path.join(str(modify_dir()), annotated_name)

    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    img = _trim_scan_borders(img)
    w, h = img.size
    dpi_save = img.info.get("dpi")
    img.save(original_path, quality=95, **(
        {"dpi": (round(dpi_save[0]), round(dpi_save[1] if dpi_save[1] else dpi_save[0]))}
        if dpi_save and isinstance(dpi_save, tuple) and len(dpi_save) >= 2 and dpi_save[0] > 0
        else {}
    ))
    draw = ImageDraw.Draw(img)
    comment_font, score_font, font_size, offsets, margin_x, margin_y = _essay_mark_fonts(w, h)
    outline_color, fill_color = _ESSAY_MARK_OUTLINE_COLOR, _ESSAY_MARK_FILL_COLOR

    if score_text and page_index == 0 and score_font:
        mark = f"{score_text}分" + (f" {essay_grade}" if essay_grade else "")
        check_x = w - int(font_size * 1.15 * len(mark)) - margin_x
        check_y = margin_y
        check_x = max(0, min(check_x, w - 10))
        check_y = max(0, min(check_y, h - 10))
        _draw_outlined_text(draw, (check_x, check_y), mark, score_font, fill_color, outline_color, offsets)

    comment_offsets = _ESSAY_COMMENT_TEXT_OFFSETS
    page_comments = _essay_trace_page_comments(segment_comments, page_index, page_count)
    trace_layouts = []
    footer_layout = None
    page_comment_bottom = 0
    if is_last_page and teacher_summary and comment_font:
        footer_layout = _essay_footer_trace_layout(
            draw,
            teacher_summary,
            comment_font,
            w,
            h,
            margin_x,
            margin_y,
            image=img,
        )
    if comment_font:
        for page_comment in page_comments:
            if not page_comment.get("text"):
                continue
            fixed_ratio = page_comment.get("ratio")
            layout = _essay_trace_layout(
                draw,
                page_comment["text"],
                comment_font,
                w,
                h,
                margin_x,
                margin_y,
                anchor=str(page_comment.get("anchor") or "center_right"),
                slot=int(page_comment.get("slot") or 0),
                ratio=float(fixed_ratio) if fixed_ratio is not None else None,
                lines_up=int(page_comment.get("lines_up") or 0),
                lines_down=int(page_comment.get("lines_down") or 0),
            )
            total_h = sum(layout["line_heights"]) + layout["line_gap"] * max(0, len(layout["lines"]) - 1)
            y = layout["y"]
            if fixed_ratio is None and page_comment_bottom > 0:
                y = max(y, page_comment_bottom + 10)
            y = max(margin_y + 8, min(y, h - margin_y - total_h - 8))
            layout["y"] = y
            if fixed_ratio is None:
                page_comment_bottom = y + total_h
            trace_layouts.append(layout)
            for idx, line in enumerate(layout["lines"]):
                x = layout["x_left"]
                _draw_outlined_text(draw, (x, y), line, comment_font, fill_color, outline_color, comment_offsets)
                y += layout["line_heights"][idx] + layout["line_gap"]

    if footer_layout and comment_font:
        _draw_essay_footer_trace(
            draw, footer_layout, comment_font, fill_color, outline_color, comment_offsets
        )

    img.save(annotated_path, quality=95)

    marks_only_name = f"marks_only_{file_stem}{ext}"
    marks_only_path = os.path.join(str(modify_dir()), marks_only_name)
    img_blank = Image.new("RGB", (w, h), color=(255, 255, 255))
    draw_blank = ImageDraw.Draw(img_blank)
    if score_text and page_index == 0 and score_font:
        mark = f"{score_text}分" + (f" {essay_grade}" if essay_grade else "")
        check_x = w - int(font_size * 1.15 * len(mark)) - margin_x * 2
        check_y = margin_y
        check_x = max(0, min(check_x, w - 10))
        check_y = max(0, min(check_y, h - 10))
        _draw_outlined_text(draw_blank, (check_x, check_y), mark, score_font, fill_color, outline_color, offsets)

    if comment_font:
        for layout in trace_layouts:
            y = layout["y"]
            for idx, line in enumerate(layout["lines"]):
                x = layout["x_left"]
                _draw_outlined_text(draw_blank, (x, y), line, comment_font, fill_color, outline_color, comment_offsets)
                y += layout["line_heights"][idx] + layout["line_gap"]
    if footer_layout and comment_font:
        _draw_essay_footer_trace(
            draw_blank, footer_layout, comment_font, fill_color, outline_color, comment_offsets
        )

    img_blank.save(
        marks_only_path,
        quality=95,
        **(
            {"dpi": (round(dpi_save[0]), round(dpi_save[1] if dpi_save[1] else dpi_save[0]))}
            if dpi_save and isinstance(dpi_save, tuple) and len(dpi_save) >= 2 and dpi_save[0] > 0
            else {}
        ),
    )

    uid = get_grading_user_id()
    item["image_original"] = build_download_url(f"grading/modify/{original_name}", uid)
    item["image_annotated"] = build_download_url(f"grading/modify/{annotated_name}", uid)
    item["image_marks_only"] = build_download_url(f"grading/modify/{marks_only_name}", uid)
    item["marks_only_filename"] = marks_only_name
    item["paper_note"] = str(paper_note or "").strip()
    return item


@router.post("/folders/{folder_name:path}/essay-note")
async def api_save_essay_note(folder_name: str, request: Request):
    """保存作文「老师总评」并重绘卷面（旁批不变，尾批用老师总评替换，仅最后一页显示）。"""
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    try:
        body = await request.json()
    except Exception:
        body = {}
    filename = str(body.get("filename") or "").strip()
    paper_note = str(body.get("paper_note") or "")
    if not filename:
        raise HTTPException(status_code=400, detail="缺少 filename")

    with _essay_history_lock:
        data = _read_essay_history(safe)
    item = (data.get("completed") or {}).get(filename)
    if not isinstance(item, dict):
        raise HTTPException(status_code=404, detail="未找到该作文的批改记录")

    # 同组所有页（多页作文）逐页重绘；尾批只在最后一页
    group_pages = item.get("group_pages") or []
    if not isinstance(group_pages, list) or not group_pages:
        group_pages = [filename]

    updated_items: dict[str, dict] = {}
    for page_name in group_pages:
        page_item = (data.get("completed") or {}).get(page_name)
        if not isinstance(page_item, dict):
            continue
        try:
            updated_items[page_name] = _redraw_essay_trace_images(safe, page_name, page_item, paper_note)
        except HTTPException:
            raise
        except Exception as e:
            print(f"作文总评重绘失败 [{page_name}]: {e}")

    if not updated_items:
        raise HTTPException(status_code=500, detail="总评重绘失败")

    with _essay_history_lock:
        data = _read_essay_history(safe)
        for page_name, redrawn in updated_items.items():
            data["completed"][page_name] = {k: v for k, v in redrawn.items() if k != "index"}
        _write_essay_history(safe, data)

    view_item = updated_items.get(filename) or item
    view = {k: v for k, v in view_item.items() if k not in _ESSAY_INTERNAL_FIELDS}
    return {"ok": True, "message": "老师总评已保存", "item": _resign_history_images(view)}


@file_router.get("/folders/{folder_name:path}/preview/{filename:path}")
async def api_serve_preview(folder_name: str, filename: str, request: Request):
    """预览图：从 test_paper_img 目录提供，支持 _img.jpg（PDF 转）及普通图片（jpg/png 等）。
    C6/H2：resource 绑定为 grading/folders/{folder}/preview/{file}，下载票须匹配。"""
    safe = _safe_folder_name(folder_name)
    base_name = Path(filename).name
    if not safe or not _safe_file_filename(base_name):
        raise HTTPException(status_code=404)
    if Path(base_name).suffix.lower() not in _IMAGE_EXTS:
        raise HTTPException(status_code=404)
    user_id = user_id_from_request(request, resource=f"grading/folders/{safe}/preview/{filename}")
    paths = get_user_grading_paths(user_id)
    path = paths.correct_docs_img / safe / base_name
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, filename=base_name)


@file_router.get("/folders/{folder_name:path}/file/{filename:path}")
async def api_serve_file(folder_name: str, filename: str, request: Request):
    """原文件直链：resource 绑定为 grading/folders/{folder}/file/{file}，下载票须匹配（C6）。"""
    safe = _safe_folder_name(folder_name)
    base_name = Path(filename).name
    if not safe or not _safe_file_filename(base_name):
        raise HTTPException(status_code=404)
    user_id = user_id_from_request(request, resource=f"grading/folders/{safe}/file/{filename}")
    paths = get_user_grading_paths(user_id)
    path = paths.correct_docs / safe / base_name
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, filename=base_name)


@file_router.get("/folders/{folder_name:path}/answer-table/region-image")
async def api_serve_answer_table_region_image(
    folder_name: str,
    request: Request,
    page_no: int = 0,
    x1: int = 0,
    y1: int = 0,
    x2: int = 0,
    y2: int = 0,
):
    """答案表作答区缩略图：按 bbox 裁标准答案页返回 JPEG。

    前端 6889 跨域画布裁剪会污染画布，缩略图必须服务端裁；<img> 带不了
    Authorization，鉴权走下载票（resource 绑定到本端点）。
    bbox 是答案表缓存 image_path 的坐标空间（与识别时同一张图）。
    """
    safe = _safe_folder_name(folder_name)
    if not safe or page_no <= 0:
        raise HTTPException(status_code=404)
    user_id = user_id_from_request(
        request, resource=f"grading/folders/{safe}/answer-table/region-image"
    )
    set_grading_user_id(user_id)
    # 答题区坐标按答案表缓存图（image_path）记；缓存缺失时回退标准答案识别图
    cached = read_reference_answer_table_page(safe, page_no)
    image_path = Path(str(cached.get("image_path") or "")) if cached.get("image_path") else None
    if not image_path or not image_path.is_file():
        sources = _reference_standard_sources(safe)
        pair = sources.get(int(page_no))
        if pair:
            image_path = pair[1]
    if not image_path or not image_path.is_file():
        raise HTTPException(status_code=404)
    try:
        jpeg = crop_reference_answer_table_region(str(image_path), [x1, y1, x2, y2])
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=jpeg, media_type="image/jpeg")


@router.post("/folders/{folder_name:path}/file/rename")
async def api_rename_folder_file(folder_name: str, request: Request):
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    try:
        body = await request.json()
    except Exception:
        body = {}

    old_name = Path(str(body.get("old_name") or "")).name.strip()
    raw_new_name = Path(str(body.get("new_name") or "")).name.strip()
    if not old_name or not raw_new_name:
        raise HTTPException(status_code=400, detail="试卷名称不能为空")
    if not _safe_file_filename(old_name):
        raise HTTPException(status_code=400, detail="原试卷名称无效")

    old_path = correct_docs_dir() / safe / old_name
    if not old_path.is_file():
        raise HTTPException(status_code=404, detail="试卷文件不存在")
    if _is_standard_answer_filename(old_path.name):
        raise HTTPException(status_code=400, detail="标准答案不支持重命名")
    if _is_answer_sheet_filename(old_path.name):
        raise HTTPException(status_code=400, detail="答案纸不支持重命名")

    old_ext = old_path.suffix
    new_path_obj = Path(raw_new_name)
    if not new_path_obj.suffix:
        raw_new_name = raw_new_name + old_ext
    elif new_path_obj.suffix.lower() != old_ext.lower():
        raise HTTPException(status_code=400, detail="重命名不能修改文件类型")

    new_name = Path(raw_new_name).name.strip()
    if not _safe_file_filename(new_name):
        raise HTTPException(status_code=400, detail="新试卷名称无效")
    if _is_standard_answer_filename(new_name):
        raise HTTPException(status_code=400, detail="学生试卷不能重命名为标准答案")
    if _is_answer_sheet_filename(new_name):
        raise HTTPException(status_code=400, detail="学生试卷不能重命名为答案纸")
    if old_name == new_name:
        return {
            "ok": True,
            "name": old_name,
            "filename": old_name,
            "url": _preview_url_for_file(safe, old_name),
            "type": _file_type(old_name),
        }

    new_path = correct_docs_dir() / safe / new_name
    try:
        same_file_target = new_path.exists() and old_path.resolve() == new_path.resolve()
    except Exception:
        same_file_target = False
    if new_path.exists() and not same_file_target:
        raise HTTPException(status_code=400, detail="同名试卷已存在，请换一个名称")

    try:
        if same_file_target:
            tmp_path = old_path.with_name(f".rename_tmp_{uuid.uuid4().hex}{old_ext}")
            old_path.rename(tmp_path)
            tmp_path.rename(new_path)
        else:
            old_path.rename(new_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重命名试卷失败: {e}")

    old_json_path = old_path.with_suffix(".json")
    new_json_path = new_path.with_suffix(".json")
    _rename_path_if_exists(old_json_path, new_json_path)

    old_preview_name = _preview_image_name_for_file(old_name)
    new_preview_name = _preview_image_name_for_file(new_name)
    if old_preview_name and new_preview_name:
        _rename_path_if_exists(
            correct_docs_img_dir() / safe / old_preview_name,
            correct_docs_img_dir() / safe / new_preview_name,
            replace_existing=True,
        )

    _rename_grading_history_entry(safe, old_name, new_name, "default")
    _rename_grading_history_entry(safe, old_name, new_name, "manual")
    _rename_essay_history_entry(safe, old_name, new_name)
    try:
        from app.grading.wrong_question_db import rename_paper_in_exam_wrong_questions
        rename_paper_in_exam_wrong_questions(safe, old_name, new_name)
    except Exception:
        pass

    return {
        "ok": True,
        "name": new_name,
        "filename": new_name,
        "url": _preview_url_for_file(safe, new_name),
        "type": _file_type(new_name),
    }


def _cleanup_paper_leftovers(safe: str, base_name: str) -> None:
    """删除试卷后的收尾清理：同名 json、批改/作文历史、错题本、参照批改产物、批注图。

    任何一步失败都只打日志、绝不向上传播——删除接口在 unlink 之后不能再 5xx，
    否则前端会当成删除失败反复重试，第二次起全部 404「文件不存在」。
    """
    path = correct_docs_dir() / safe / base_name
    try:
        # 尝试一并删除同名的 .json 文件（如果有）
        json_path = path.with_suffix(".json")
        if json_path.is_file():
            json_path.unlink()
    except Exception:
        print(traceback.format_exc())
    try:
        _remove_grading_history_entry(safe, base_name, "default")
        _remove_grading_history_entry(safe, base_name, "manual")
        _remove_essay_history_entry(safe, base_name)
    except Exception:
        print(traceback.format_exc())
    try:
        from app.grading.wrong_question_db import remove_paper_from_exam_wrong_questions
        remove_paper_from_exam_wrong_questions(safe, base_name)
    except Exception:
        pass
    try:
        from app.grading.reference_vlm_grading import remove_reference_vlm_paper_artifacts
        remove_reference_vlm_paper_artifacts(safe, base_name)
    except Exception:
        pass
    try:
        _delete_reference_modify_artifacts(safe, base_name)
    except Exception:
        print(traceback.format_exc())
    try:
        ext = Path(base_name).suffix.lower()
        if ext == ".pdf":
            img_path = correct_docs_img_dir() / safe / f"{Path(base_name).stem}_img.jpg"
        elif ext in _IMAGE_EXTS:
            img_path = correct_docs_img_dir() / safe / base_name
        else:
            img_path = None
        if img_path and img_path.is_file():
            img_path.unlink()
    except Exception:
        print(traceback.format_exc())


@router.delete("/folders/{folder_name:path}/file/{filename:path}")
async def api_delete_folder_file(folder_name: str, filename: str):
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    base_name = Path(filename).name
    if not base_name or not _safe_file_filename(base_name):
        raise HTTPException(status_code=400, detail="无效文件名")
    path = correct_docs_dir() / safe / base_name
    if not path.is_file():
        # 幂等删除：文件可能已在上一次请求里被 unlink、但收尾清理崩溃留下历史/批注
        # 残留。继续走清理并返回成功，让前端把幽灵条目从列表拿掉，否则每次重试都是
        # 404「文件不存在」。
        _cleanup_paper_leftovers(safe, base_name)
        return {"ok": True}
    standard_page_no = _standard_answer_page_no(base_name)
    if standard_page_no is not None:
        delete_reference_layout(safe, standard_page_no)
    _sync_stats_on_paper_delete(get_grading_user_id(), safe, base_name)
    path.unlink()
    _cleanup_paper_leftovers(safe, base_name)
    return {"ok": True}


@router.post("/folders/{folder_name:path}/files/clear")
async def api_clear_folder_files(
    folder_name: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """一键清空文件夹中的试卷文件（图片/PDF/Word），需用户名（邮箱）+密码二次验证。"""
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    try:
        body = await request.json()
    except Exception:
        body = {}
    username = (body.get("username") or "").strip()
    password = (body.get("password") or "").strip()
    if not username or not password:
        raise HTTPException(status_code=400, detail="请输入用户名和密码")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    # 当前系统登录名即邮箱，要求输入与当前账号一致
    if username.lower() != (user.email or "").lower():
        raise HTTPException(status_code=400, detail="用户名与当前登录账号不一致")
    if not verify_password(password, user.password_hash):
        raise HTTPException(status_code=400, detail="密码错误")

    dir_path = correct_docs_dir() / safe
    if not dir_path.is_dir():
        return {"ok": True, "deleted": 0}

    deleted = 0
    for f in list(dir_path.iterdir()):
        if not f.is_file() or f.suffix.lower() not in _ALL_UPLOAD_EXTS:
            continue
        try:
            f.unlink()
            # 一并删除对应的 json 文件（如果有）
            json_file = f.with_suffix(".json")
            if json_file.is_file():
                try:
                    json_file.unlink()
                except Exception:
                    pass
            deleted += 1
        except Exception:
            continue
        _remove_grading_history_entry(safe, f.name, "default")
        _remove_grading_history_entry(safe, f.name, "manual")
        _remove_essay_history_entry(safe, f.name)
        ext = f.suffix.lower()
        if ext == ".pdf":
            img_path = correct_docs_img_dir() / safe / f"{f.stem}_img.jpg"
        elif ext in _IMAGE_EXTS:
            img_path = correct_docs_img_dir() / safe / f.name
        else:
            img_path = None
        if img_path and img_path.is_file():
            try:
                img_path.unlink()
            except Exception:
                pass
    try:
        from app.grading.wrong_question_db import delete_exam_wrong_question_file
        delete_exam_wrong_question_file(safe)
    except Exception:
        pass
    try:
        from app.grading.reference_vlm_grading import delete_reference_vlm_folder_artifacts
        delete_reference_vlm_folder_artifacts(safe)
    except Exception:
        pass
    delete_reference_layout(safe)
    delete_manual_layout(safe)
    _delete_reference_modify_artifacts(safe)
    _sync_stats_on_folder_delete(get_grading_user_id(), safe)
    return {"ok": True, "deleted": deleted}


def _allowed_upload_type(content_type: str, filename: str) -> bool:
    if content_type and content_type.startswith("image/"):
        return True
    if content_type in ("application/pdf", "application/msword",
                       "application/vnd.openxmlformats-officedocument.wordprocessingml.document"):
        return True
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in _ALL_UPLOAD_EXTS:
            return True
    return False


def _ext_from_filename(filename: str) -> str:
    if not filename:
        return ".jpg"
    for e in (".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"):
        if filename.lower().endswith(e):
            return e
    return ".jpg"


@router.post("/folders/{folder_name:path}/upload")
async def api_upload_to_folder(
    folder_name: str,
    file: UploadFile = File(...),
    is_standard_answer: str = Form(""),
    standard_page_no: str = Form(""),
    is_original_paper: str = Form(""),
    original_page_no: str = Form(""),
    is_answer_sheet: str = Form(""),
    answer_sheet_page_no: str = Form(""),
):
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    dir_path = correct_docs_dir() / safe
    dir_path.mkdir(parents=True, exist_ok=True)
    (correct_docs_img_dir() / safe).mkdir(parents=True, exist_ok=True)
    if not file.filename:
        raise HTTPException(status_code=400, detail="请选择文件")
    if not _allowed_upload_type(file.content_type or "", file.filename):
        raise HTTPException(status_code=400, detail="仅支持图片、PDF、Word（.jpg/.png/.pdf/.doc/.docx）")
    ext = _ext_from_filename(file.filename)
    is_std = str(is_standard_answer).strip().lower() in ("true", "1", "yes")
    is_orig = str(is_original_paper).strip().lower() in ("true", "1", "yes")
    is_sheet = str(is_answer_sheet).strip().lower() in ("true", "1", "yes")
    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if is_orig:
        try:
            page_no = int(str(original_page_no or "1").strip() or "1")
        except Exception:
            raise HTTPException(status_code=400, detail="原始试卷页码必须是整数")
        if page_no < 1 or page_no > 20:
            raise HTTPException(status_code=400, detail="原始试卷页码必须在 1 到 20 之间")
        for old in dir_path.iterdir():
            if old.is_file() and _original_paper_page_no(old.name) == page_no:
                try:
                    old.unlink()
                except Exception:
                    pass
        img_dir = correct_docs_img_dir() / safe
        for old in img_dir.iterdir():
            if not old.is_file():
                continue
            original_stem = old.stem[:-4] if old.stem.endswith("_img") else old.stem
            if _original_paper_page_no(original_stem) == page_no:
                try:
                    old.unlink()
                except Exception:
                    pass
        save_stem = "原始试卷" if page_no == 1 else f"原始试卷_{page_no}"
        save_name = save_stem + ext
        save_path = dir_path / save_name
        save_path.write_bytes(content)
        normalize_uploaded_image_orientation(save_path)
        _trim_uploaded_scan_borders(save_path)
        _ensure_img_in_folder(save_path, safe)
        t = _file_type(save_name)
        url = _preview_url_for_file(safe, save_name)
        return {
            "ok": True,
            "name": f"原始试卷 P{page_no}",
            "filename": save_name,
            "url": url,
            "type": t,
            "page_no": page_no,
        }
    if is_std:
        try:
            page_no = int(str(standard_page_no or "1").strip() or "1")
        except Exception:
            raise HTTPException(status_code=400, detail="标准答案页码必须是整数")
        if page_no < 1 or page_no > 20:
            raise HTTPException(status_code=400, detail="标准答案页码必须在 1 到 20 之间")
        # A replaced standard page must be reviewed again; discard both the
        # confirmed page and any in-progress review for this page.
        delete_reference_layout(safe, page_no)
        for old in dir_path.iterdir():
            if old.is_file() and _standard_answer_page_no(old.name) == page_no:
                try:
                    old.unlink()
                except Exception:
                    pass
        img_dir = correct_docs_img_dir() / safe
        for old in img_dir.iterdir():
            if not old.is_file():
                continue
            original_stem = old.stem[:-4] if old.stem.endswith("_img") else old.stem
            if _standard_answer_page_no(original_stem) == page_no:
                try:
                    old.unlink()
                except Exception:
                    pass
        save_stem = "标准答案" if page_no == 1 else f"标准答案_{page_no}"
        save_name = save_stem + ext
        save_path = dir_path / save_name
        save_path.write_bytes(content)
        normalize_uploaded_image_orientation(save_path)
        _trim_uploaded_scan_borders(save_path)
        _ensure_img_in_folder(save_path, safe)
        t = _file_type(save_name)
        url = _preview_url_for_file(safe, save_name)
        return {
            "ok": True,
            "name": f"标准答案 P{page_no}",
            "filename": save_name,
            "url": url,
            "type": t,
            "page_no": page_no,
        }
    if is_sheet:
        try:
            page_no = int(str(answer_sheet_page_no or "1").strip() or "1")
        except Exception:
            raise HTTPException(status_code=400, detail="答案纸页码必须是整数")
        if page_no < 1 or page_no > 20:
            raise HTTPException(status_code=400, detail="答案纸页码必须在 1 到 20 之间")
        for old in dir_path.iterdir():
            if old.is_file() and _answer_sheet_page_no(old.name) == page_no:
                try:
                    old.unlink()
                except Exception:
                    pass
        img_dir = correct_docs_img_dir() / safe
        for old in img_dir.iterdir():
            if not old.is_file():
                continue
            original_stem = old.stem[:-4] if old.stem.endswith("_img") else old.stem
            if _answer_sheet_page_no(original_stem) == page_no:
                try:
                    old.unlink()
                except Exception:
                    pass
        save_stem = "答案" if page_no == 1 else f"答案_{page_no}"
        save_name = save_stem + ext
        save_path = dir_path / save_name
        save_path.write_bytes(content)
        normalize_uploaded_image_orientation(save_path)
        _trim_uploaded_scan_borders(save_path)
        _ensure_img_in_folder(save_path, safe)
        t = _file_type(save_name)
        url = _preview_url_for_file(safe, save_name)
        return {
            "ok": True,
            "name": f"答案纸 P{page_no}",
            "filename": save_name,
            "url": url,
            "type": t,
            "page_no": page_no,
        }
    # 105% 硬停：额度用尽时拒绝新增学生试卷
    try:
        from app.services import quota_service
        quota_service.ensure_user_available(get_grading_user_id())
    except HTTPException:
        raise
    except Exception:
        pass
    save_name = file.filename
    if not _safe_file_filename(save_name):
        save_name = str(uuid.uuid4()) + ext
    save_path = dir_path / save_name
    save_path.write_bytes(content)
    normalize_uploaded_image_orientation(save_path)
    _trim_uploaded_scan_borders(save_path)
    _ensure_img_in_folder(save_path, safe)
    t = _file_type(save_name)
    url = _preview_url_for_file(safe, save_name)
    try:
        from app.grading.grading_stats import record_upload_for_file
        record_upload_for_file(get_grading_user_id(), safe, save_name)
    except Exception:
        pass
    try:
        from app.services import quota_service
        quota_service.add_usage(get_grading_user_id(), 1)
    except Exception:
        pass
    return {
        "ok": True,
        "name": save_name,
        "filename": save_name,
        "url": url,
        "type": t,
    }


def _sync_ref_job_from_history(job_id: str, folder_safe: str) -> None:
    """Finalize only this job's in-memory results; never inject stale history."""
    with _ref_grade_lock:
        if job_id not in _ref_grade_results:
            return
        res = _ref_grade_results[job_id]
        known_completed = {x.get("name") for x in res.get("completed", []) if x.get("name")}
        known_failed = {x.get("name") for x in res.get("failed", []) if x.get("name")}
        done_names = known_completed | known_failed
        in_progress = res.setdefault("in_progress", [])
        res["in_progress"] = [n for n in in_progress if n not in done_names]


def _run_ref_grade(
    job_id: str,
    folder_name: str,
    engine: str = "aliyun",
    only_filename: Optional[str] = None,
    only_filenames: Optional[set[str]] = None,
    user_id: Optional[str] = None,
):
    if user_id:
        set_grading_user_id(user_id)
    # 1015 根治：全局重活预算——跨文件夹也排队限流。拿不到槽位就在这里等
    # （queued=True 供前端显示「排队中」），绝不两个批次并发硬扛内存。
    from app.services.heavy_budget import heavy_slot

    with _ref_grade_lock:
        if job_id in _ref_grade_results:
            _ref_grade_results[job_id]["queued"] = True
    try:
        with heavy_slot("ref-grade") as waited_s:
            with _ref_grade_lock:
                if job_id in _ref_grade_results:
                    _ref_grade_results[job_id]["queued"] = False
                    _ref_grade_results[job_id]["queue_waited_s"] = round(waited_s, 1)
            if engine == "manual":
                from app.grading.manual_grading import baidu_paper_cut, parse_paper_cut_result
                _run_manual_grade_analyze(job_id, folder_name, only_filename, only_filenames)
            else:
                _run_ref_grade_impl(
                    job_id,
                    folder_name,
                    engine,
                    only_filename=only_filename,
                    only_filenames=only_filenames,
                )
    except Exception as e:
        safe = _safe_folder_name(folder_name) or str(folder_name or "")
        msg = f"参照答案批改任务异常: {type(e).__name__}: {e}"
        print(msg)
        print(traceback.format_exc())
        with _ref_grade_lock:
            if job_id in _ref_grade_results:
                res = _ref_grade_results[job_id]
                if not res.get("failed") and not res.get("completed"):
                    res.setdefault("failed", []).append({"name": "", "msg": msg})
                res["in_progress"] = []
        if safe:
            try:
                _persist_grading_failure(safe, "", msg, engine)
            except Exception:
                print("参照答案批改任务异常落盘失败")
                print(traceback.format_exc())
    finally:
        _sync_ref_job_from_history(job_id, _safe_folder_name(folder_name) or "")
        stop_ev = _ref_grade_stop_events.pop(job_id, None)
        was_cancelled = bool(stop_ev and stop_ev.is_set())
        push_now = True
        with _ref_grade_lock:
            if job_id in _ref_grade_results:
                _ref_grade_results[job_id]["done"] = True
                push_now = bool(_ref_grade_results[job_id].get("push_dingtalk", True))
        # 批改一跑完就推钉钉（仅智能/参照引擎；手动批改有自己的 all-done 钩子；
        # 取消的任务不推，避免推空/半截成绩单）
        if push_now and not was_cancelled and engine in ("baidu", "aliyun") and user_id:
            try:
                from app.services.dingtalk_notify import notify_grading_done

                notify_grading_done(
                    user_id, _safe_folder_name(folder_name) or "", "grading_done"
                )
            except Exception as e:
                print(f"[dingtalk_notify] hook after ref grade failed: {e}")

def _run_manual_grade_analyze(job_id: str, folder_name: str, only_filename: Optional[str], only_filenames: Optional[set[str]]):
    safe = _safe_folder_name(folder_name)
    if not safe:
        return
    dir_path = correct_docs_dir() / safe
    if not dir_path.is_dir():
        with _ref_grade_lock:
            if job_id in _ref_grade_results:
                _ref_grade_results[job_id]["failed"].append({"name": "", "msg": "文件夹不存在"})
        return
        
    student_files = []
    student_orig = []
    for f in dir_path.iterdir():
        if not f.is_file() or f.suffix.lower() not in _ALL_UPLOAD_EXTS:
            continue
        if _is_standard_answer_filename(f.name) or _is_answer_sheet_filename(f.name):
            continue
        student_orig.append(f)
        gp = _get_grading_path(safe, f)
        if gp is None and f.suffix.lower() in (".doc", ".docx"):
            gp = f
        elif gp is None:
            gp = _ensure_img_in_folder(f, safe) or f
        student_files.append(gp)
        
    paired = list(zip(student_files, student_orig))
    if only_filename:
        nf = Path(only_filename).name
        paired = [(sf, so) for sf, so in paired if so.name == nf]
        if len(paired) != 1:
            with _ref_grade_lock:
                if job_id in _ref_grade_results:
                    _ref_grade_results[job_id]["failed"].append({"name": nf, "msg": "未找到该试卷或文件已变更"})
            return
    elif only_filenames is not None:
        paired = [(sf, so) for sf, so in paired if so.name in only_filenames]
        if not paired:
            return
            
    student_files = [p[0] for p in paired]
    student_orig = [p[1] for p in paired]

    def process_one(args):
        i, (student_grading_path, student_orig_path) = args
        original_name = student_orig_path.name
        with _ref_grade_lock:
            if job_id in _ref_grade_results:
                in_progress = _ref_grade_results[job_id].setdefault("in_progress", [])
                if original_name not in in_progress:
                    in_progress.append(original_name)
                    
        stop_ev = _ref_grade_stop_events.get(job_id)
        if stop_ev and stop_ev.is_set():
            with _ref_grade_lock:
                if job_id in _ref_grade_results:
                    _ref_grade_results[job_id]["failed"].append({"index": i, "name": original_name, "msg": "已停止批改"})
            return
            
        try:
            from app.grading.manual_grading import baidu_paper_cut, parse_paper_cut_result
            # 调用百度试卷切卷 API 获取原始切片坐标数据
            raw_data = baidu_paper_cut(str(student_grading_path))
            blocks = parse_paper_cut_result(raw_data)
            
            # 将原始坐标数据保存在 result 字段中，后续由前端读取并在左侧渲染高亮区域或提供切图
            result_json_str = json.dumps(
                {"type": "manual_analyze", "manual_status": "analyzed", "blocks": blocks},
                ensure_ascii=False,
            )
            
            # 生成一张原始的标注底图，方便留痕时使用
            # 在没有打分前，不画任何痕迹，只生成一份可以直接复制为 marks_only 的原图引用
            image_original = _preview_url_for_file(safe, original_name)
            # 我们将真实的留痕图片生成逻辑放在另一个独立的 API 中，当用户在前端点击“完成”时才去生成
            
            item = {
                "index": i,
                "name": original_name,
                "image_original": image_original,
                "image_annotated": "",
                "image_marks_only": "",
                "result": result_json_str,
                "marks_only_filename": "",
            }
            with _ref_grade_lock:
                if job_id not in _ref_grade_results:
                    return
                _ref_grade_results[job_id]["completed"].append(item)
            _persist_grading_success(safe, item, "manual")
            
        except Exception as e:
            with _ref_grade_lock:
                if job_id in _ref_grade_results:
                    _ref_grade_results[job_id]["failed"].append({"index": i, "name": original_name, "msg": str(e)})
            _persist_grading_failure(safe, original_name, str(e), "manual")
        finally:
            with _ref_grade_lock:
                if job_id in _ref_grade_results:
                    in_progress = _ref_grade_results[job_id].setdefault("in_progress", [])
                    if original_name in in_progress:
                        in_progress.remove(original_name)

    with ThreadPoolExecutor(max_workers=3) as executor:
        ctx_uid = get_grading_user_id()
        list(executor.map(lambda args: run_with_grading_user(ctx_uid, process_one, args), enumerate(zip(student_files, student_orig))))



def _run_ref_grade_impl(
    job_id: str,
    folder_name: str,
    engine: str = "aliyun",
    only_filename: Optional[str] = None,
    only_filenames: Optional[set[str]] = None,
):
    safe = _safe_folder_name(folder_name)
    if not safe:
        return
    dir_path = correct_docs_dir() / safe
    if not dir_path.is_dir():
        with _ref_grade_lock:
            if job_id in _ref_grade_results:
                _ref_grade_results[job_id]["failed"].append({"name": "", "msg": "文件夹不存在"})
        return
    standard_paths: dict[int, Path] = {}
    standard_source_paths: dict[int, Path] = {}
    duplicate_standard_pages: set[int] = set()
    student_files = []
    student_orig = []
    for f in dir_path.iterdir():
        if not f.is_file() or f.suffix.lower() not in _ALL_UPLOAD_EXTS:
            continue
        standard_page_no = _standard_answer_page_no(f.name)
        if standard_page_no is not None:
            if engine == "baidu":
                # 百度智能批改不使用标准答案
                continue
            gp = _get_grading_path(safe, f)
            if gp is None and f.suffix.lower() in (".doc", ".docx"):
                gp = f
            elif gp is None:
                gp = _ensure_img_in_folder(f, safe) or f
            if standard_page_no in standard_paths:
                duplicate_standard_pages.add(standard_page_no)
            else:
                standard_paths[standard_page_no] = Path(gp)
                standard_source_paths[standard_page_no] = f
            continue
        student_orig.append(f)
        gp = _get_grading_path(safe, f)
        if gp is None and f.suffix.lower() in (".doc", ".docx"):
            gp = f
        elif gp is None:
            gp = _ensure_img_in_folder(f, safe) or f
        student_files.append(gp)
    paired = list(zip(student_files, student_orig))
    if only_filename:
        nf = Path(only_filename).name
        paired = [(sf, so) for sf, so in paired if so.name == nf]
        if len(paired) != 1:
            with _ref_grade_lock:
                if job_id in _ref_grade_results:
                    _ref_grade_results[job_id]["failed"].append(
                        {"name": nf, "msg": "未找到该试卷或文件已变更"}
                    )
            return
    elif only_filenames is not None:
        paired = [(sf, so) for sf, so in paired if so.name in only_filenames]
        if not paired:
            return
    student_files = [p[0] for p in paired]
    student_orig = [p[1] for p in paired]
    with _ref_grade_lock:
        if job_id in _ref_grade_results:
            _ref_grade_results[job_id]["total"] = len(paired)
    # 科目族路由（方案 S3b 单一决策点）：文件夹 meta 优先，缺/无法映射才 VL 兜底，灰区强制 general
    subject_family = "general"
    family_hint = ""
    try:
        from app.grading.response_log_db import _read_folder_meta as _rfm
        from app.grading.subject_family import family_prompt_hint, resolve_family_with_fallback

        meta_subject = str((_rfm(safe) or {}).get("subject") or "").strip()
        first_img = str(student_files[0]) if student_files else None
        subject_family, _fam_src = resolve_family_with_fallback(meta_subject, first_img)
        family_hint = family_prompt_hint(subject_family)
    except Exception:
        subject_family = "general"
        family_hint = ""
    stop_ev = _ref_grade_stop_events.get(job_id)
    paper_vlm_cache: dict[str, dict] = {}
    paper_vlm_errors: dict[str, Exception] = {}
    paper_vlm_slot_templates: dict[int, list] = {}
    reference_answer_tables: dict[int, dict] = {}
    precomputed_std_by_page: dict[int, object] = {}
    precomputed_std_errors: dict[int, Exception] = {}
    student_page_by_name = {
        original.name: _paper_box_page_no(original.name) for original in student_orig
    }
    if engine in ("aliyun", "smart_ref"):
        if duplicate_standard_pages:
            duplicate_text = "、".join(f"P{page}" for page in sorted(duplicate_standard_pages))
            with _ref_grade_lock:
                if job_id in _ref_grade_results:
                    _ref_grade_results[job_id]["failed"].append(
                        {"name": "标准答案", "msg": f"标准答案页码重复：{duplicate_text}，请删除重复页面后重试"}
                    )
            return
        if not standard_paths or not student_files:
            with _ref_grade_lock:
                if job_id in _ref_grade_results:
                    _ref_grade_results[job_id]["failed"].append(
                        {"name": "", "msg": "需要至少一页标准答案与至少一页学生试卷"}
                    )
            return
        required_pages = sorted(set(student_page_by_name.values()))
        missing_pages = [page for page in required_pages if page not in standard_paths]
        for original in student_orig:
            page_no = student_page_by_name[original.name]
            if page_no in missing_pages:
                paper_vlm_errors[original.name] = RuntimeError(
                    f"缺少标准答案 P{page_no}，学生试卷 P{page_no} 不会回退使用其他页"
                )
        if engine == "smart_ref":
            for page_no in required_pages:
                standard_path = standard_paths.get(page_no)
                if standard_path is None:
                    continue
                try:
                    precomputed_std_by_page[page_no] = prepare_standard_answer_for_reference(
                        str(standard_path)
                    )
                except Exception as exc:
                    precomputed_std_errors[page_no] = exc
    else:
        if not student_files:
            with _ref_grade_lock:
                if job_id in _ref_grade_results:
                    _ref_grade_results[job_id]["failed"].append({"name": "", "msg": "请至少上传一张学生试卷（图片/PDF/Word）"})
            return
    if engine == "aliyun":
        required_pages = sorted(set(student_page_by_name.values()))
        layout_missing_pages: list[int] = []
        for page_no in required_pages:
            standard_path = standard_paths.get(page_no)
            source_path = standard_source_paths.get(page_no)
            if standard_path is None or source_path is None:
                layout_missing_pages.append(page_no)
                continue
            confirmed_doc = get_confirmed_reference_document(
                safe,
                page_no,
                source_path,
                str(standard_path),
            )
            if confirmed_doc is None:
                layout_missing_pages.append(page_no)
            else:
                precomputed_std_by_page[page_no] = confirmed_doc
        for original in student_orig:
            page_no = student_page_by_name[original.name]
            if page_no in layout_missing_pages:
                paper_vlm_errors[original.name] = RuntimeError(
                    f"请先完成标准答案 P{page_no} 的切题审查，再开始参照答案批改"
                )
        # The standard OCR JSON is cached by the review confirmation. Only
        # student papers need fresh OCR at grading time.
        ocr_items = [
            (orig.name, orig.name, str(sf))
            for sf, orig in zip(student_files, student_orig)
            if orig.name not in paper_vlm_errors
        ]
        batch_cache, batch_errors = recognize_reference_vlm_batch(
            ocr_items, stop_event=stop_ev
        )
        paper_vlm_cache.update(batch_cache)
        paper_vlm_errors.update(batch_errors)

        # 答案纸（答案单独一张纸）答案也进标准答案表：与识别列表同一份合并文本
        sheet_texts = _load_answer_sheet_texts_for_folder(safe)
        for page_no in required_pages:
            standard_doc = precomputed_std_by_page.get(page_no)
            if standard_doc is None:
                # The student-specific review error was created above. Never
                # rewrite it as a generic OCR failure or fall back to P1.
                continue
            # The confirmed standard layout is authoritative. Student OCR is
            # only used to locate handwriting and cannot redefine the slots.
            page_documents = {"__standard__": standard_doc}
            paper_vlm_slot_templates[page_no] = build_reference_vlm_slot_template(
                page_documents
            )
            # 用户要求第①步：批卷前先把每道题的标准答案完完整整识别成文本
            # （逐槽无上下文 VL 转写，按卷缓存）。判分提示词以该文本为唯一
            # 判分依据，再逐卷按题号对照作答区比对手写答案。
            try:
                reference_answer_tables[page_no] = load_or_build_reference_answer_table(
                    safe, page_no, standard_doc, answer_sheet_texts=sheet_texts, stop_event=stop_ev
                )
            except Exception:
                traceback.print_exc()
                reference_answer_tables[page_no] = {}
    # 百度：提交/查询各 2QPS，后台约 4 并发；流水线：百度完成一张即留痕并写入 completed
    if engine == "baidu":
        REF_WORKERS = _baidu_ref_grade_workers()
    elif engine == "aliyun":
        REF_WORKERS = max(1, min(10, int(os.environ.get("REFERENCE_VLM_PAPER_WORKERS", "6") or "6")))
    else:
        REF_WORKERS = 6
    stop_ev = _ref_grade_stop_events.get(job_id)
    baidu_handled_keys: set = set()
    baidu_post_executor = None

    def process_one(args):
        if len(args) == 4:
            i, (student_grading_path, student_orig_path), baidu_prefetch, baidu_error = args
        else:
            i, (student_grading_path, student_orig_path) = args
            baidu_prefetch = None
            baidu_error = None
        file_stem = f"ref_{safe}_{student_orig_path.stem}"
        original_name = student_orig_path.name
        student_page_no = student_page_by_name.get(
            original_name, _paper_box_page_no(original_name)
        )
        if engine != "baidu":
            with _ref_grade_lock:
                if job_id in _ref_grade_results:
                    in_progress = _ref_grade_results[job_id].setdefault("in_progress", [])
                    if original_name not in in_progress:
                        in_progress.append(original_name)
        if stop_ev and stop_ev.is_set():
            with _ref_grade_lock:
                if job_id in _ref_grade_results:
                    _ref_grade_results[job_id]["failed"].append(
                        {"index": i, "name": original_name, "msg": "已停止批改"}
                    )
            _persist_grading_failure(safe, original_name, "已停止批改", engine)
            return
        try:
            item = None
            for attempt in range(3): # 新增漏批重试机制：最多尝试3次
                try:
                    reference_vlm_mark_src = None
                    if engine == "baidu":
                        cache_key = original_name
                        if attempt == 0 and baidu_error is not None:
                            raise baidu_error
                        if attempt == 0 and baidu_prefetch is not None:
                            result, blocks_with_result, baidu_raw = baidu_prefetch
                        else:
                            result, blocks_with_result, baidu_raw = baidu_grade_single(
                                str(student_grading_path), stop_event=stop_ev
                            )
                        # 补全百度 correct_edu 漏切的主观题/作文（视觉模型识别整卷题目）
                        try:
                            result, blocks_with_result = _supplement_baidu_grading(
                                None, Path(student_grading_path), result, blocks_with_result
                            )
                        except Exception:
                            pass
                    elif engine == "smart_ref":
                        from app.grading.pipeline import real_grade_pipeline_smart_ref
                        standard_path = standard_paths.get(student_page_no)
                        if standard_path is None:
                            raise RuntimeError(
                                f"缺少标准答案 P{student_page_no}，学生试卷 P{student_page_no} 不会回退使用其他页"
                            )
                        if student_page_no in precomputed_std_errors:
                            raise precomputed_std_errors[student_page_no]
                        result, blocks_with_result, baidu_raw, _ = real_grade_pipeline_smart_ref(
                            str(standard_path),
                            str(student_grading_path),
                            precomputed_std=precomputed_std_by_page.get(student_page_no),
                            stop_event=stop_ev,
                            family_hint=family_hint,
                        )
                    else:
                        if original_name in paper_vlm_errors:
                            raise paper_vlm_errors[original_name]
                        std_vlm = _reference_standard_document(
                            student_page_no, precomputed_std_by_page
                        )
                        stu_vlm = paper_vlm_cache.get(original_name) or {}
                        if not std_vlm:
                            raise RuntimeError(
                                f"标准答案 P{student_page_no} 的已确认切题数据缺失，请重新进行切题审查"
                            )
                        if not stu_vlm:
                            fallback_cache, fallback_errors = recognize_reference_vlm_batch(
                                [(original_name, original_name, str(student_grading_path))],
                                stop_event=stop_ev,
                            )
                            if original_name in fallback_errors:
                                raise fallback_errors[original_name]
                            stu_vlm = fallback_cache.get(original_name) or {}
                            paper_vlm_cache[original_name] = stu_vlm
                        result, blocks_with_result, baidu_raw, reference_vlm_mark_src = grade_reference_vlm_paper(
                            f"标准答案 P{student_page_no}",
                            std_vlm,
                            original_name,
                            stu_vlm,
                            folder_safe=safe,
                            slot_template=paper_vlm_slot_templates.get(student_page_no, []),
                            stop_event=stop_ev,
                            family_hint=family_hint,
                            # C3 判分缓存身份：与回写侧（store_blocks）共用 meta 科目
                            cache_subject=meta_subject,
                            answer_table=reference_answer_tables.get(student_page_no),
                        )
                    # 形态校验兜底（方案 v1.0「一套兜底保险」）：强矛盾自动降级未作答，弱矛盾只标 suspicious；
                    # 同时统一补科目族标签，随 blocks 落 history/response_logs 供复核记账。
                    if blocks_with_result:
                        for _blk in blocks_with_result:
                            if isinstance(_blk, dict):
                                _blk["subject_family"] = subject_family
                        # 题干/作答区角色甄别（2026-10-12）：剔除百度切题把题干素材卡片
                        # 误框成的假作答区（「分一分」类题）。必须在 form_guard 之前，
                        # 否则假块还会触发「有笔迹判未作答」存疑噪音。
                        try:
                            from app.grading.slot_role import filter_stem_slots
                            _slot_changes = filter_stem_slots(str(student_grading_path), blocks_with_result)
                        except Exception:
                            _slot_changes = []
                        try:
                            from app.grading.form_guard import apply_form_guard
                            _fg_changes = apply_form_guard(str(student_grading_path), blocks_with_result)
                        except Exception:
                            _fg_changes = []
                        # VL 笔迹证据复核（A项）：印刷插图槽幻觉拦截——form_guard 的像素盲区
                        try:
                            from app.grading.ink_evidence import verify_handwriting_with_vl
                            _vl_changes = verify_handwriting_with_vl(str(student_grading_path), blocks_with_result)
                        except Exception:
                            _vl_changes = []
                        # B3 复核记账：兜底降级/复核存疑进 correction_ledger（旁路静默，绝不阻断批改）
                        if _fg_changes or _vl_changes:
                            try:
                                from app.grading.correction_ledger import (
                                    guard_changes_to_ledger_rows,
                                    record_corrections,
                                )
                                record_corrections(
                                    get_grading_user_id(),
                                    safe,
                                    original_name,
                                    engine,
                                    guard_changes_to_ledger_rows(_fg_changes, "form_guard", blocks_with_result, subject_family)
                                    + guard_changes_to_ledger_rows(_vl_changes, "vl_ink", blocks_with_result, subject_family),
                                    subject_family=subject_family,
                                )
                            except Exception:
                                pass
                        # C3 判分缓存回写：必须在 guard **之后**（guard 前写会把幻觉放大
                        # 到全班）；带 form_guard/ink_evidence 痕迹的块在 store_blocks 内
                        # 自拒不入缓存。baidu/smart_ref 块无文本身份，键红线自动跳过。
                        try:
                            from app.grading.verdict_cache import store_blocks

                            store_blocks(
                                blocks_with_result,
                                meta_subject,
                                engine,
                                "ai",
                                subject_family=subject_family,
                            )
                        except Exception:
                            pass
                        if any(
                            c.get("action") in ("downgraded", "removed_stem")
                            for c in _fg_changes + _vl_changes + _slot_changes
                        ):
                            if engine in ("baidu", "smart_ref"):
                                # 降级后摘要文本同步（与 ai-correct 同口径）
                                try:
                                    from app.grading.baidu_grading import _summarize_result
                                    result = _summarize_result(baidu_raw or {}, blocks_with_result)
                                except Exception:
                                    pass
                    image_original = image_annotated = image_marks_only = None
                    marks_only_filename = None
                    if blocks_with_result:
                        try:
                            mark_src = reference_vlm_mark_src or str(student_grading_path)
                            if not os.path.isfile(mark_src):
                                regen = _ensure_img_in_folder(student_orig_path, safe) or student_orig_path
                                mark_src = str(_get_grading_path(safe, student_orig_path) or regen)
                            if not os.path.isfile(mark_src):
                                raise FileNotFoundError(f"批改用原图不存在: {mark_src}")
                            if engine == "aliyun":
                                orig_name, ann_name, marks_only_filename = draw_reference_vlm_marks_and_save(
                                    mark_src,
                                    blocks_with_result,
                                    str(modify_dir()),
                                    file_stem,
                                    check_cross_scale=0.9,
                                )
                            elif engine in ("baidu", "smart_ref"):
                                mark_scale = 0.90 if engine == "baidu" else 1.0
                                # 留痕前：视觉读整卷每题满分，逐题算得分（对=满分/错=0），让卷面在 √/× 旁标出分数
                                try:
                                    _attach_scores_to_blocks(
                                        None, Path(mark_src), result, blocks_with_result
                                    )
                                except Exception:
                                    pass
                                orig_name, ann_name, marks_only_filename = draw_baidu_marks_and_save(
                                    mark_src,
                                    blocks_with_result,
                                    baidu_raw,
                                    str(modify_dir()),
                                    file_stem,
                                    check_cross_scale=mark_scale,
                                )
                                # 倒置扫描件（无 EXIF）自动摆正：按百度 detect_direction 朝向码
                                # 反向旋转整套图片，避免「卷子正、留痕反」。
                                _auto_rotate_baidu_output(baidu_raw, file_stem, safe, original_name)
                            else:
                                orig_name, ann_name = draw_real_marks_and_save(
                                    mark_src, blocks_with_result, str(modify_dir()), file_stem
                                )
                                marks_only_filename = draw_marks_only_and_save(
                                    mark_src, blocks_with_result, str(modify_dir()), file_stem
                                )
                            _rg_uid = get_grading_user_id()
                            image_original = build_download_url(f"grading/modify/{orig_name}", _rg_uid)
                            image_annotated = build_download_url(f"grading/modify/{ann_name}", _rg_uid)
                            image_marks_only = build_download_url(f"grading/modify/{marks_only_filename}", _rg_uid)
                        except Exception as mark_err:
                            print(f"留痕绘制失败 [{original_name}]: {mark_err}")
                    item = {
                        "index": i,
                        "name": original_name,
                        "image_original": image_original,
                        "image_annotated": image_annotated,
                        "image_marks_only": image_marks_only,
                        "result": result or "",
                        "marks_only_filename": marks_only_filename,
                    }
                    # 「编辑批改」入口依赖 blocks（逐题对错/bbox）才能展示；这里把逐题结果一并
                    # 放进内存 completed 列表，避免批改完成即点进详情却看不到「编辑批改」按钮。
                    if blocks_with_result:
                        item["blocks"] = copy.deepcopy(blocks_with_result)
                        item["engine"] = engine
                    if _is_placeholder_completed_item(item):
                        item = {
                            "index": i,
                            "name": original_name,
                            "error": True,
                            "msg": "未识别到可批改题目，未生成 AI 解析和留痕，请检查试卷图片质量后重试",
                        }
                    break # 成功则跳出重试循环
                except Exception as e:
                    msg = f"{type(e).__name__}: {e}"
                    print(f"参照答案批改失败 [{original_name}] attempt={attempt + 1}: {msg}")
                    print(traceback.format_exc())
                    item = {"index": i, "name": original_name, "error": True, "msg": msg}
                    if original_name in paper_vlm_errors:
                        break
                    if attempt < 2:
                        time.sleep(2)
                        continue
            
            with _ref_grade_lock:
                if job_id not in _ref_grade_results:
                    return
                res = _ref_grade_results[job_id]
                done_names = {x.get("name") for x in res.get("completed", [])} | {x.get("name") for x in res.get("failed", [])}
                if original_name in done_names:
                    in_progress = res.setdefault("in_progress", [])
                    if original_name in in_progress:
                        in_progress.remove(original_name)
                    return
                if item.get("error"):
                    _ref_grade_results[job_id]["failed"].append({"index": i, "name": original_name, "msg": item.get("msg", "批改失败")})
                else:
                    _ref_grade_results[job_id]["completed"].append(item)
            if item.get("error"):
                _persist_grading_failure(safe, original_name, str(item.get("msg", "批改失败")), engine)
            else:
                if engine in ("baidu", "smart_ref", "aliyun") and blocks_with_result:
                    # 落盘逐题结果供老师后续手动修正对错并重画留痕；仅智能批改存百度原始响应
                    persist_item = dict(item)
                    persist_item["blocks"] = copy.deepcopy(blocks_with_result)
                    persist_item["engine"] = engine
                    if engine in ("baidu", "smart_ref"):
                        persist_item["baidu_raw"] = copy.deepcopy(baidu_raw or {})
                    _persist_grading_success(safe, persist_item, engine)
                else:
                    _persist_grading_success(safe, item, engine)
                _schedule_response_log_write(
                    get_grading_user_id(),
                    safe,
                    original_name,
                    engine,
                    blocks_with_result or [],
                )
                if engine in ("baidu", "smart_ref"):
                    _schedule_baidu_wrong_question_upsert(
                        get_grading_user_id(),
                        safe,
                        original_name,
                        baidu_raw or {},
                        blocks_with_result or [],
                        str(student_grading_path),
                    )
                if engine in ("baidu", "smart_ref", "aliyun", "manual"):
                    _schedule_wrong_annotation_generation(
                        get_grading_user_id(),
                        safe,
                        original_name,
                        engine,
                        blocks_with_result or [],
                        str(student_grading_path),
                    )
        except Exception as outer_e:
            print(f"批改试卷发生未捕获异常 {original_name}: {outer_e}")
            with _ref_grade_lock:
                if job_id in _ref_grade_results:
                    _ref_grade_results[job_id]["failed"].append({"index": i, "name": original_name, "msg": f"系统内部错误: {outer_e}"})
            _persist_grading_failure(safe, original_name, f"系统内部错误: {outer_e}", engine)
        finally:
            with _ref_grade_lock:
                if job_id in _ref_grade_results:
                    in_progress = _ref_grade_results[job_id].setdefault("in_progress", [])
                    if original_name in in_progress:
                        in_progress.remove(original_name)

    if engine == "baidu":
        for _, orig in zip(student_files, student_orig):
            with _ref_grade_lock:
                if job_id in _ref_grade_results:
                    in_progress = _ref_grade_results[job_id].setdefault("in_progress", [])
                    if orig.name not in in_progress:
                        in_progress.append(orig.name)

        name_to_args = {
            _baidu_batch_item_key(i, orig.name): (i, sf, orig)
            for i, (sf, orig) in enumerate(zip(student_files, student_orig))
        }
        ctx_uid = get_grading_user_id()
        baidu_post_executor = ThreadPoolExecutor(max_workers=REF_WORKERS)
        mark_timeout = max(60, int(os.environ.get("BAIDU_MARK_TIMEOUT", "300")))
        baidu_post_futures: list[tuple[str, object]] = []

        def _ref_done_names() -> set:
            with _ref_grade_lock:
                if job_id not in _ref_grade_results:
                    return set()
                res = _ref_grade_results[job_id]
                return {x.get("name") for x in res.get("completed", [])} | {
                    x.get("name") for x in res.get("failed", [])
                }

        def _ref_completed_names() -> set:
            with _ref_grade_lock:
                if job_id not in _ref_grade_results:
                    return set()
                return {x.get("name") for x in _ref_grade_results[job_id].get("completed", [])}

        def _resolve_batch_args(batch_key: str):
            k = str(batch_key or "").strip()
            args_tuple = name_to_args.get(k)
            if args_tuple:
                return k, args_tuple
            if ":" in k:
                idx_str, tail = k.split(":", 1)
                try:
                    idx = int(idx_str)
                except ValueError:
                    idx = None
                if idx is not None:
                    for nk, av in name_to_args.items():
                        if av[0] == idx and _paper_result_key(av[2].name) == _paper_result_key(tail):
                            return nk, av
            print(f"百度批改结果键未匹配试卷 [{k!r}]，已知: {list(name_to_args.keys())}")
            return k, None

        baidu_callback_names: set[str] = set()

        def _on_baidu_result(key: str, parsed, err) -> None:
            k, args_tuple = _resolve_batch_args(key)
            if not args_tuple:
                print(f"百度批改结果键未匹配试卷 [{key!r}]，已知: {list(name_to_args.keys())}")
                return
            i, sf, orig = args_tuple
            paper_name = orig.name
            baidu_callback_names.add(paper_name)
            if paper_name in _ref_completed_names():
                return
            try:
                fut = baidu_post_executor.submit(
                    run_with_grading_user,
                    ctx_uid,
                    process_one,
                    (i, (sf, orig), parsed, err),
                )
            except Exception as e:
                print(f"百度留痕任务提交失败 [{paper_name}]: {e}")
                _fail_ref_paper_item(job_id, i, paper_name, safe, engine, f"留痕任务提交失败: {e}")
                return
            baidu_handled_keys.add(k)
            baidu_post_futures.append((paper_name, fut))

        try:
            baidu_grade_batch(
                [
                    (_baidu_batch_item_key(i, orig.name), str(sf))
                    for i, (sf, orig) in enumerate(zip(student_files, student_orig))
                ],
                stop_event=stop_ev,
                on_result=_on_baidu_result,
            )
        except Exception as e:
            print(f"百度批量批改异常，将回退单张批改: {e}")

        for orig_name, fut in baidu_post_futures:
            try:
                fut.result(timeout=mark_timeout)
            except FuturesTimeoutError:
                print(f"百度留痕处理超时 [{orig_name}]")
                idx_pair = next(
                    (v for v in name_to_args.values() if v[2].name == orig_name),
                    None,
                )
                if idx_pair:
                    _fail_ref_paper_item(
                        job_id,
                        idx_pair[0],
                        idx_pair[2].name,
                        safe,
                        engine,
                        "留痕处理超时，请重试",
                    )
            except Exception as e:
                print(f"百度留痕处理异常 [{orig_name}]: {e}")
                idx_pair = next(
                    (v for v in name_to_args.values() if v[2].name == orig_name),
                    None,
                )
                if idx_pair and orig_name not in _ref_done_names():
                    _fail_ref_paper_item(
                        job_id,
                        idx_pair[0],
                        idx_pair[2].name,
                        safe,
                        engine,
                        f"留痕处理失败: {e}",
                    )

        # 批量流水线未触发 on_result 的试卷（含同图重复卷）走单张补批
        for i, (sf, orig) in enumerate(zip(student_files, student_orig)):
            if orig.name in baidu_callback_names or orig.name in _ref_done_names():
                continue
            print(f"批量流水线未回调 [{orig.name}]（index={i}），单张补批")
            try:
                run_with_grading_user(ctx_uid, process_one, (i, (sf, orig)))
            except Exception as e:
                print(f"流水线漏批单张补批异常 [{orig.name}]: {e}")
                _fail_ref_paper_item(job_id, i, orig.name, safe, engine, str(e))
            else:
                if orig.name not in _ref_done_names():
                    _fail_ref_paper_item(job_id, i, orig.name, safe, engine, "流水线漏批后仍未完成，请重试")

        pending_done = _ref_done_names()
        unhandled = [
            (i, (sf, orig))
            for i, (sf, orig) in enumerate(zip(student_files, student_orig))
            if orig.name not in pending_done
        ]
        if unhandled:
            for args in unhandled:
                i, (sf, orig) = args
                try:
                    run_with_grading_user(ctx_uid, process_one, args)
                except Exception as e:
                    print(f"百度单张回退批改异常: {e}")
                    _fail_ref_paper_item(job_id, i, orig.name, safe, engine, str(e))
                else:
                    if orig.name not in _ref_done_names():
                        _fail_ref_paper_item(job_id, i, orig.name, safe, engine, "单张回退后仍未完成，请重试")

        _reconcile_missing_baidu_papers(
            job_id, safe, engine, student_files, student_orig, ctx_uid, process_one
        )
        baidu_post_executor.shutdown(wait=True)
        _sweep_ref_in_progress(job_id, safe, engine, student_orig)
    else:
        with ThreadPoolExecutor(max_workers=REF_WORKERS) as executor:
            ctx_uid = get_grading_user_id()
            list(executor.map(lambda args: run_with_grading_user(ctx_uid, process_one, args), enumerate(zip(student_files, student_orig))))

    # 跨卷一致性补批：主观题批改（smart_ref/aliyun）批完一轮后，检出比同文件夹
    # 其它卷少批题目的卷，重跑一次补齐缺口；仍缺的写回 history 供前端标红。
    if engine in ("smart_ref", "aliyun"):
        try:
            _retry_missing_question_papers(
                job_id,
                safe,
                engine,
                list(enumerate(zip(student_files, student_orig))),
                process_one,
            )
        except Exception as e:
            print(f"[漏批补批] 补批调度异常 safe={safe!r}: {e}")


def _retry_missing_question_papers(job_id, safe, engine, items, grade_fn) -> None:
    """对少批题目的卷补跑一次（跨卷比对 + 重跑 + 二次标记）。

    grade_fn 为批改单张卷的回调（process_one 闭包）；items 为
    [(index, (grading_path, orig_path))] 本批次全部试卷。只重跑仍在本次批次内的卷，
    且每卷只补跑一次，避免无限循环。
    """
    try:
        with _grading_history_lock:
            data = _read_grading_history(safe, engine)
        missing_map = _detect_missing_questions(data, engine)
    except Exception as e:
        print(f"[漏批补批] 读取历史失败 safe={safe!r}: {e}")
        return
    if not missing_map:
        return

    by_name = {}
    for i, pair in items:
        orig = pair[1]
        by_name[orig.name] = (i, pair)
    retry_names = [name for name in missing_map if name in by_name]
    if not retry_names:
        return

    print(f"[漏批补批] 检出 {len(retry_names)} 张卷少批题目，补跑一次: {retry_names}")
    ctx_uid = get_grading_user_id()
    for name in retry_names:
        args = by_name[name]
        # 补跑前快照原结果：补跑若失败被 process_one 标为 failed，则恢复原已批改结果，
        # 避免「已批改但少一题」的卷被误判成整卷批改失败。
        with _grading_history_lock:
            snapshot_data = _read_grading_history(safe, engine)
            snapshot = snapshot_data.get("completed", {}).get(name)
        try:
            run_with_grading_user(ctx_uid, grade_fn, args)
        except Exception as e:
            print(f"[漏批补批] 补跑失败 [{name}]: {e}")
        if snapshot is not None:
            with _grading_history_lock:
                data = _read_grading_history(safe, engine)
                if (
                    name not in data.get("completed", {})
                    and name in data.get("failed", {})
                ):
                    data["completed"][name] = snapshot
                    data["failed"].pop(name, None)
                    _write_grading_history(safe, data, engine)
                    print(f"[漏批补批] 补跑失败，已恢复原结果 [{name}]")

    # 补跑后再比对一次，仍缺的写回 history 供前端标红
    try:
        with _grading_history_lock:
            data = _read_grading_history(safe, engine)
        still_missing = _detect_missing_questions(data, engine)
        if still_missing:
            with _grading_history_lock:
                data = _read_grading_history(safe, engine)
                data["missing_questions"] = still_missing
                _write_grading_history(safe, data, engine)
            print(f"[漏批补批] 仍有 {len(still_missing)} 张卷缺题: {list(still_missing)}")
    except Exception as e:
        print(f"[漏批补批] 二次比对失败: {e}")


def _get_student_base_name(filename: str) -> str:
    stem = Path(filename).stem
    m = re.search(r'^(.*?)_\d+$', stem)
    if m:
        return m.group(1)
    return stem


def _page_no_from_student_filename(filename: str) -> int:
    stem = Path(filename).stem
    m = re.search(r"_(\d+)$", stem)
    if m:
        try:
            return max(1, int(m.group(1)))
        except ValueError:
            pass
    return 1


def _parse_essay_dimension_scores(result_text: str, dimensions=None):
    """从 LLM 输出解析 `<essay_dimensions>` 标签并校验。

    返回 (dimension_scores, dimension_total)：
    - dimension_scores: 校验通过的 {维度key: 得分} dict；解析/校验失败返回 None
    - dimension_total: 各维度得分之和（float）；失败返回 None

    校验规则：标签缺失 / JSON 非法 / 非 dict / 维度 key 不在配置维度内 /
    得分超出 [0, full_score] 任一失败，整体静默丢弃（返回 (None, None)），不阻断批改。
    """
    if not result_text:
        return None, None
    match = re.search(
        r"<essay_dimensions>([^<]+)</essay_dimensions>",
        result_text,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return None, None
    try:
        payload = json.loads(match.group(1).strip())
    except Exception:
        return None, None
    if not isinstance(payload, dict) or not payload:
        return None, None

    dim_map = {}
    for d in dimensions or []:
        key = (d or {}).get("key")
        if key:
            dim_map[str(key)] = d
    if not dim_map:
        return None, None

    scores = {}
    total = 0.0
    for key, val in payload.items():
        skey = str(key)
        if skey not in dim_map:
            return None, None
        try:
            num = float(val)
        except (TypeError, ValueError):
            return None, None
        full = dim_map[skey].get("full_score")
        try:
            full_score = float(full) if full is not None else float("inf")
        except (TypeError, ValueError):
            full_score = float("inf")
        if num < 0 or num > full_score:
            return None, None
        scores[skey] = val
        total += num

    return scores, total


def _extract_essay_grade_scores(result_text: str, dimensions=None) -> dict:
    """从 LLM 原始输出提取得分、解析维度分并清理隐藏标签。

    返回 dict:
      - score_text: Optional[str]     展示用得分字符串（维度分之和为准时同步）
      - score_total: Optional[float]  数值得分
      - dimension_scores: Optional[dict] 解析校验通过的维度分；否则 None
      - clean_text: str               去掉 <essay_score>/<essay_dimensions> 后的正文

    不一致处理策略：维度分之和为准——当 `<essay_dimensions>` 解析校验通过时，
    若与 `<essay_score>` 不一致（或 `<essay_score>` 缺失），以维度分之和同步
    score_total / score_text（模型对加法的算错远多于分维度打错，维度内自洽更可信）。
    """
    score_text = None
    score_match = re.search(
        r"<essay_score>.*?([\d]+(?:\.\d+)?).*?</essay_score>",
        result_text,
        re.DOTALL | re.IGNORECASE,
    )
    if score_match:
        try:
            score_val = float(score_match.group(1))
            score_text = str(score_val)
            if score_text.endswith(".0"):
                score_text = score_text[:-2]
        except ValueError:
            pass

    clean_text = re.sub(
        r"<essay_score>.*?</essay_score>", "", result_text, flags=re.DOTALL | re.IGNORECASE
    ).strip()
    clean_text = re.sub(
        r"<essay_dimensions>.*?</essay_dimensions>", "", clean_text, flags=re.DOTALL | re.IGNORECASE
    ).strip()

    score_total = float(score_text) if score_text else None
    dimension_scores, dim_total = _parse_essay_dimension_scores(result_text, dimensions)

    if dimension_scores is not None and dim_total is not None:
        score_total = dim_total
        score_text = str(int(dim_total)) if float(dim_total).is_integer() else str(dim_total)

    return {
        "score_text": score_text,
        "score_total": score_total,
        "dimension_scores": dimension_scores,
        "clean_text": clean_text,
    }


def _run_essay_grade(
    job_id: str,
    folder_name: str,
    rubric_text: str,
    only_filename: Optional[str] = None,
    only_filenames: Optional[set[str]] = None,
    prompts: Optional[dict] = None,
    user_id: Optional[str] = None,
) -> None:
    """作文批改：先创建百度OCR task → 轮询结果 → 通义千问批改。"""
    if user_id:
        set_grading_user_id(user_id)
    ctx_uid = user_id or get_grading_user_id()
    safe = _safe_folder_name(folder_name)
    if not safe:
        return
    dir_path = correct_docs_dir() / safe
    stop_ev = _essay_grade_stop_events.get(job_id)
    from app.grading.essay_grading import (
        DEFAULT_DIMENSIONS,
        baidu_essay_create_task,
        baidu_essay_get_result,
        baidu_essay_parse_status,
        derive_essay_grade,
        grade_essay_with_qwen,
    )

    # A2-B1 维度化：prompts["dimensions_json"] 传入自定义维度配置，缺省用默认五维
    dimensions = None
    dimensions_json = str((prompts or {}).get("dimensions_json") or "").strip()
    if dimensions_json:
        try:
            parsed_dims = json.loads(dimensions_json)
            if isinstance(parsed_dims, list) and parsed_dims:
                dimensions = parsed_dims
        except Exception:
            dimensions = None
    if not dimensions:
        dimensions = DEFAULT_DIMENSIONS

    # 目标：减少“真空期”。先并发创建 task_id（很快），再集中轮询（百度侧可并行处理），
    # 最后再调用通义批改（文本生成较慢）。
    OCR_CREATE_WORKERS = 3
    OCR_POLL_INTERVAL_SEC = 1.0
    OCR_TIMEOUT_SEC = 240.0
    QWEN_WORKERS = 2

    # 收集要处理的学生文件
    student_files: list[Path] = []
    for f in dir_path.iterdir():
        if not f.is_file() or f.suffix.lower() not in _ALL_UPLOAD_EXTS:
            continue
        if _is_standard_answer_filename(f.name) or _is_answer_sheet_filename(f.name):
            continue
        if only_filename and f.name != only_filename:
            continue
        if only_filenames is not None and f.name not in only_filenames:
            continue
        student_files.append(f)
        
    student_files.sort(key=lambda f: _natural_sort_key(f.name))
    student_names = [f.name for f in student_files]
    
    # 按照学生前缀分组，支持多页作文合并批改
    groups: dict[str, list[int]] = {}
    for i, name in enumerate(student_names):
        base = _get_student_base_name(name)
        groups.setdefault(base, []).append(i)
    for base in list(groups.keys()):
        groups[base] = sorted(
            groups[base],
            key=lambda idx: _page_no_from_student_filename(student_names[idx]),
        )

    # 初始化任务状态（便于前端看到“已提交/识别中”）
    with _essay_grade_lock:
        if job_id in _essay_grade_results:
            _essay_grade_results[job_id]["ocr_tasks"] = {
                name: {"name": name, "task_id": "", "status": "init", "created_at": time.time()}
                for name in student_names
            }

    def _grading_image_path(orig_path: Path) -> Path:
        # 确保有对应的预览/批改用图片（PDF->JPG，图片复制）
        try:
            gp = _ensure_img_in_folder(orig_path, safe) or orig_path
            return _get_grading_path(safe, orig_path) or gp
        except Exception:
            return orig_path

    def _build_group_ocr_image(base: str, indices: list[int]) -> Path:
        # 同一试卷框的多页先拼成一张长图，再统一送百度 OCR。
        if len(indices) == 1:
            return _grading_image_path(student_files[indices[0]])
        from PIL import Image

        source_paths = [_grading_image_path(student_files[i]) for i in indices]
        images = []
        try:
            for path in source_paths:
                images.append(Image.open(str(path)).convert("RGB"))
            max_width = max(img.width for img in images)
            gap = 24
            total_height = sum(int(img.height * max_width / max(1, img.width)) for img in images) + gap * (len(images) - 1)
            canvas = Image.new("RGB", (max_width, total_height), color=(255, 255, 255))
            y = 0
            for img in images:
                if img.width != max_width:
                    new_h = max(1, int(img.height * max_width / max(1, img.width)))
                    pasted = img.resize((max_width, new_h))
                else:
                    pasted = img
                canvas.paste(pasted, (0, y))
                y += pasted.height + gap
            os.makedirs(str(modify_dir()), exist_ok=True)
            merged_path = modify_dir() / f"essay_ocr_merge_{safe}_{base}.jpg"
            canvas.save(str(merged_path), quality=92)
            return merged_path
        finally:
            for img in images:
                try:
                    img.close()
                except Exception:
                    pass

    # 1) 并发创建百度 OCR task_id（按试卷框分组，一组只提交一次）
    def _create_group(args):
        base, indices = args
        group_names = [student_names[i] for i in indices]
        try:
            if stop_ev and stop_ev.is_set():
                return
            with _essay_grade_lock:
                if job_id in _essay_grade_results:
                    _essay_grade_results[job_id].setdefault("in_progress", [])
                    for name in group_names:
                        if name not in _essay_grade_results[job_id]["in_progress"]:
                            _essay_grade_results[job_id]["in_progress"].append(name)
                    if "ocr_tasks" in _essay_grade_results[job_id]:
                        for name in group_names:
                            _essay_grade_results[job_id]["ocr_tasks"][name]["status"] = "uploading"

            img_path = _build_group_ocr_image(base, indices)
            task_id = None
            for attempt in range(3): # 新增漏批重试机制
                try:
                    task_id = baidu_essay_create_task(str(img_path))
                    break
                except Exception as e:
                    if attempt < 2:
                        time.sleep(2)
                    else:
                        raise e
                        
            with _essay_grade_lock:
                if job_id in _essay_grade_results and "ocr_tasks" in _essay_grade_results[job_id]:
                    for name in group_names:
                        _essay_grade_results[job_id]["ocr_tasks"][name]["task_id"] = task_id
                        _essay_grade_results[job_id]["ocr_tasks"][name]["status"] = "pending"
                        _essay_grade_results[job_id]["ocr_tasks"][name]["created_at"] = time.time()
        except Exception as e:
            try:
                with _essay_grade_lock:
                    if job_id in _essay_grade_results:
                        for i in indices:
                            name = student_names[i]
                            _essay_grade_results[job_id]["failed"].append({"index": i, "name": name, "msg": f"OCR提交失败: {e}"})
                            if "ocr_tasks" in _essay_grade_results[job_id]:
                                _essay_grade_results[job_id]["ocr_tasks"][name]["status"] = "failed"
                            _persist_essay_failure(safe, name, f"OCR提交失败: {e}")
            except Exception:
                pass

    # 2) 轮询 OCR 直到 group 中的所有页 success，然后再送通义批改（按组并发）
    def _grade_group(base: str, indices: list[int], titles: list[str], contents: list[str]):
        if stop_ev and stop_ev.is_set():
            return [{"index": i, "name": student_names[i], "error": True, "msg": "已停止批改"} for i in indices]
        try:
            final_title = " ".join([t for t in titles if t])
            final_content = "\n\n".join([c for c in contents if c])
            
            if not final_content.strip():
                return [{"index": i, "name": student_names[i], "error": True, "msg": "所有页面均未识别到有效文字"} for i in indices]

            result_text = None
            for attempt in range(3): # 新增漏批重试机制
                try:
                    result_text = grade_essay_with_qwen(final_title, final_content, rubric_text or "", prompts, dimensions)
                    if not result_text:
                        raise ValueError("模型返回为空")
                    break
                except Exception as e:
                    print(f"作文大模型批改报错: {e}")
                    if attempt < 2:
                        time.sleep(2)
                    else:
                        raise e
            
            parsed_scores = _extract_essay_grade_scores(result_text, dimensions)
            score_text = parsed_scores["score_text"]
            score_total = parsed_scores["score_total"]
            dimension_scores = parsed_scores["dimension_scores"]
            clean_result_text = parsed_scores["clean_text"]
            # R18/R16 语文作文等级制：由总分 + 维度满分推导五级等级
            essay_grade = derive_essay_grade(score_total, dimensions) if score_total is not None else ""

            from app.grading.essay_grading import normalize_essay_result_text

            clean_result_text = normalize_essay_result_text(clean_result_text)
            
            segment_comments = _extract_essay_segment_comments(clean_result_text)
            teacher_summary = _extract_essay_teacher_summary(clean_result_text)

            # 同样去除掉AI生成的评分栏（如果有的话），因为Prompt可能依然会偶尔生成
            clean_result_text = re.sub(r"【评分】[\s\S]*?(?=\n【|$)", "", clean_result_text).strip()
            
            # 将评分移到最前面（含等级）
            if score_text:
                grade_line = f"等级：{essay_grade}\n" if essay_grade else ""
                result_text = f"【作文得分】\n{score_text} 分\n{grade_line}\n" + clean_result_text + f"\n<essay_score>{score_text}</essay_score>"
            else:
                result_text = clean_result_text
                
            result_text = normalize_essay_result_text(result_text)

            group_results = []
            
            for i in indices:
                name = student_names[i]
                orig_path = student_files[i]
                page_index = indices.index(i)
                image_original = image_annotated = image_marks_only = marks_only_filename = None
                try:
                    img_path = _grading_image_path(orig_path)
                    file_stem = f"essay_{safe}_{orig_path.stem}"
                    from PIL import Image, ImageDraw, ImageOps
                    
                    path = os.path.abspath(str(img_path))
                    os.makedirs(str(modify_dir()), exist_ok=True)
                    ext = os.path.splitext(path)[1].lower() or ".jpg"
                    if ext not in (".jpg", ".jpeg", ".png"):
                        ext = ".jpg"
                    original_name = f"original_{file_stem}{ext}"
                    annotated_name = f"annotated_{file_stem}{ext}"
                    original_path = os.path.join(str(modify_dir()), original_name)
                    annotated_path = os.path.join(str(modify_dir()), annotated_name)
                    
                    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
                    img = _trim_scan_borders(img)  # 去掉扫描仪带入的黑边，避免留痕图四周发黑
                    w, h = img.size
                    dpi_save = img.info.get("dpi")
                    img.save(original_path, quality=95, **(
                        {"dpi": (round(dpi_save[0]), round(dpi_save[1] if dpi_save[1] else dpi_save[0]))}
                        if dpi_save and isinstance(dpi_save, tuple) and len(dpi_save) >= 2 and dpi_save[0] > 0
                        else {}
                    ))
                    draw = ImageDraw.Draw(img)
                    comment_font, score_font, font_size, offsets, margin_x, margin_y = _essay_mark_fonts(w, h)
                    outline_color, fill_color = _ESSAY_MARK_OUTLINE_COLOR, _ESSAY_MARK_FILL_COLOR

                    if score_text and page_index == 0 and score_font:
                        mark = f"{score_text}分" + (f" {essay_grade}" if essay_grade else "")
                        check_x = w - int(font_size * 1.15 * len(mark)) - margin_x
                        check_y = margin_y
                        check_x = max(0, min(check_x, w - 10))
                        check_y = max(0, min(check_y, h - 10))
                        _draw_outlined_text(draw, (check_x, check_y), mark, score_font, fill_color, outline_color, offsets)

                    comment_offsets = _ESSAY_COMMENT_TEXT_OFFSETS
                    page_comments = _essay_trace_page_comments(segment_comments, page_index, len(indices))
                    trace_layouts = []
                    footer_layout = None
                    page_comment_bottom = 0
                    is_last_page = page_index == len(indices) - 1
                    if is_last_page and teacher_summary and comment_font:
                        footer_layout = _essay_footer_trace_layout(
                            draw,
                            teacher_summary,
                            comment_font,
                            w,
                            h,
                            margin_x,
                            margin_y,
                            image=img,
                        )
                    if comment_font:
                        for page_comment in page_comments:
                            if not page_comment.get("text"):
                                continue
                            fixed_ratio = page_comment.get("ratio")
                            layout = _essay_trace_layout(
                                draw,
                                page_comment["text"],
                                comment_font,
                                w,
                                h,
                                margin_x,
                                margin_y,
                                anchor=str(page_comment.get("anchor") or "center_right"),
                                slot=int(page_comment.get("slot") or 0),
                                ratio=float(fixed_ratio) if fixed_ratio is not None else None,
                                lines_up=int(page_comment.get("lines_up") or 0),
                                lines_down=int(page_comment.get("lines_down") or 0),
                            )
                            total_h = sum(layout["line_heights"]) + layout["line_gap"] * max(0, len(layout["lines"]) - 1)
                            y = layout["y"]
                            if fixed_ratio is None and page_comment_bottom > 0:
                                y = max(y, page_comment_bottom + 10)
                            y = max(margin_y + 8, min(y, h - margin_y - total_h - 8))
                            layout["y"] = y
                            if fixed_ratio is None:
                                page_comment_bottom = y + total_h
                            trace_layouts.append(layout)
                            for idx, line in enumerate(layout["lines"]):
                                x = layout["x_left"]
                                _draw_outlined_text(draw, (x, y), line, comment_font, fill_color, outline_color, comment_offsets)
                                y += layout["line_heights"][idx] + layout["line_gap"]
                    elif page_comments:
                        print(f"作文旁批跳过（未安装中文字体）: {orig_path.name}")

                    if footer_layout and comment_font:
                        _draw_essay_footer_trace(
                            draw, footer_layout, comment_font, fill_color, outline_color, comment_offsets
                        )
                    
                    img.save(annotated_path, quality=95)
                    
                    marks_only_name = f"marks_only_{file_stem}{ext}"
                    marks_only_path = os.path.join(str(modify_dir()), marks_only_name)
                    img_blank = Image.new("RGB", (w, h), color=(255, 255, 255))
                    draw_blank = ImageDraw.Draw(img_blank)
                    if score_text and page_index == 0 and score_font:
                        mark = f"{score_text}分" + (f" {essay_grade}" if essay_grade else "")
                        check_x = w - int(font_size * 1.15 * len(mark)) - margin_x * 2
                        check_y = margin_y
                        check_x = max(0, min(check_x, w - 10))
                        check_y = max(0, min(check_y, h - 10))
                        _draw_outlined_text(draw_blank, (check_x, check_y), mark, score_font, fill_color, outline_color, offsets)

                    if comment_font:
                        for layout in trace_layouts:
                            y = layout["y"]
                            for idx, line in enumerate(layout["lines"]):
                                x = layout["x_left"]
                                _draw_outlined_text(draw_blank, (x, y), line, comment_font, fill_color, outline_color, comment_offsets)
                                y += layout["line_heights"][idx] + layout["line_gap"]
                    if footer_layout and comment_font:
                        _draw_essay_footer_trace(
                            draw_blank, footer_layout, comment_font, fill_color, outline_color, comment_offsets
                        )

                    img_blank.save(
                        marks_only_path,
                        quality=95,
                        **(
                            {"dpi": (round(dpi_save[0]), round(dpi_save[1] if dpi_save[1] else dpi_save[0]))}
                            if dpi_save and isinstance(dpi_save, tuple) and len(dpi_save) >= 2 and dpi_save[0] > 0
                            else {}
                        ),
                    )
                    
                    _eg_uid = ctx_uid or get_grading_user_id()
                    image_original = build_download_url(f"grading/modify/{original_name}", _eg_uid)
                    image_annotated = build_download_url(f"grading/modify/{annotated_name}", _eg_uid)
                    image_marks_only = build_download_url(f"grading/modify/{marks_only_name}", _eg_uid)
                    marks_only_filename = marks_only_name
                    
                except Exception as e:
                    print(f"作文批改绘制留痕失败: {e}")

                item_res = {
                    "index": i,
                    "name": name,
                    "group_name": base,
                    "group_pages": [student_names[x] for x in indices],
                    "result": result_text,
                    "score_total": score_total,
                    "essay_grade": essay_grade,
                    "ocr_title": final_title,
                    "ocr_content": final_content,
                    "image_original": image_original,
                    "image_annotated": image_annotated,
                    "image_marks_only": image_marks_only,
                    "marks_only_filename": marks_only_filename,
                    # A2-B2 局部重批所需配置：改分端点据此复用已存 OCR 文本重新生成点评
                    "rubric_text": rubric_text or "",
                    "prompts": prompts or {},
                    "dimensions": dimensions,
                }
                if dimension_scores is not None:
                    item_res["dimension_scores"] = dimension_scores
                group_results.append(item_res)
            return group_results
        except Exception as e:
            return [{"index": i, "name": student_names[i], "error": True, "msg": f"通义批改失败: {e}"} for i in indices]

    try:
        with ThreadPoolExecutor(max_workers=OCR_CREATE_WORKERS) as ex:
            list(ex.map(lambda args: run_with_grading_user(ctx_uid, _create_group, args), list(groups.items())))

        start_ts = time.time()
        pending_set = set(student_names)
        ocr_results_cache = {name: {"title": "", "content": ""} for name in student_names}
        pending_groups = set(groups.keys())

        with _essay_grade_lock:
            if job_id in _essay_grade_results:
                failed_names = set([x.get("name") for x in _essay_grade_results[job_id].get("failed", [])])
                done_names = set([x.get("name") for x in _essay_grade_results[job_id].get("completed", [])])
                pending_set = pending_set - failed_names - done_names
        
        pending_groups = set([base for base, indices in groups.items() if any(student_names[i] in pending_set for i in indices)])

        grading_futures = {}
        ocr_error_counts = {base: 0 for base in groups.keys()}
        with ThreadPoolExecutor(max_workers=QWEN_WORKERS) as grade_ex:
            while pending_groups:
                if stop_ev and stop_ev.is_set():
                    break
                if time.time() - start_ts > OCR_TIMEOUT_SEC:
                    with _essay_grade_lock:
                        if job_id in _essay_grade_results:
                            for name in list(pending_set):
                                _essay_grade_results[job_id]["failed"].append({"index": -1, "name": name, "msg": "百度OCR超时"})
                                _persist_essay_failure(safe, name, "百度OCR超时")
                                if "ocr_tasks" in _essay_grade_results[job_id]:
                                    _essay_grade_results[job_id]["ocr_tasks"][name]["status"] = "timeout"
                    break

                progressed = False
                for base in list(pending_groups):
                    indices = groups[base]
                    rep_name = student_names[indices[0]]
                    with _essay_grade_lock:
                        task_id = (
                            (_essay_grade_results.get(job_id) or {})
                            .get("ocr_tasks", {})
                            .get(rep_name, {})
                            .get("task_id", "")
                        )
                    if not task_id:
                        continue
                    try:
                        data = baidu_essay_get_result(task_id)
                        ocr_error_counts[base] = 0
                        status, title, content = baidu_essay_parse_status(data)
                        with _essay_grade_lock:
                            if job_id in _essay_grade_results and "ocr_tasks" in _essay_grade_results[job_id]:
                                for i in indices:
                                    _essay_grade_results[job_id]["ocr_tasks"][student_names[i]]["status"] = status
                        if status == "success":
                            for i in indices:
                                name = student_names[i]
                                ocr_results_cache[name]["title"] = title
                                ocr_results_cache[name]["content"] = content
                                pending_set.discard(name)
                            progressed = True
                        elif status == "failed":
                            for i in indices:
                                name = student_names[i]
                                pending_set.discard(name)
                            progressed = True
                            with _essay_grade_lock:
                                if job_id in _essay_grade_results:
                                    for i in indices:
                                        name = student_names[i]
                                        _essay_grade_results[job_id]["failed"].append({"index": i, "name": name, "msg": f"百度OCR处理失败: {data}"})
                                        _persist_essay_failure(safe, name, f"百度OCR处理失败: {data}")
                    except Exception as e:
                        ocr_error_counts[base] = ocr_error_counts.get(base, 0) + 1
                        if ocr_error_counts[base] >= 3:
                            progressed = True
                            pending_groups.discard(base)
                            with _essay_grade_lock:
                                if job_id in _essay_grade_results:
                                    in_progress = _essay_grade_results[job_id].setdefault("in_progress", [])
                                    for i in indices:
                                        name = student_names[i]
                                        pending_set.discard(name)
                                        if name in in_progress:
                                            in_progress.remove(name)
                                        _essay_grade_results[job_id]["failed"].append(
                                            {"index": i, "name": name, "msg": f"百度OCR查询失败: {e}"}
                                        )
                                        _persist_essay_failure(safe, name, f"百度OCR查询失败: {e}")
                                        if "ocr_tasks" in _essay_grade_results[job_id]:
                                            _essay_grade_results[job_id]["ocr_tasks"][name]["status"] = "failed"

                for base in list(pending_groups):
                    indices = groups[base]
                    if all(student_names[i] not in pending_set for i in indices):
                        pending_groups.remove(base)
                        progressed = True
                        
                        valid_indices = []
                        for i in indices:
                            name = student_names[i]
                            with _essay_grade_lock:
                                is_failed = any(x.get("name") == name for x in _essay_grade_results.get(job_id, {}).get("failed", []))
                            if not is_failed:
                                valid_indices.append(i)
                                
                        if valid_indices:
                            # 既然整框合并成一张长图提交 OCR，同一组的结果是完全一样的，只需取第一页的文本即可，避免重复拼接
                            rep_name = student_names[valid_indices[0]]
                            group_titles = [ocr_results_cache[rep_name]["title"]]
                            group_contents = [ocr_results_cache[rep_name]["content"]]
                            future = grade_ex.submit(
                                run_with_grading_user,
                                ctx_uid,
                                _grade_group,
                                base,
                                valid_indices,
                                group_titles,
                                group_contents,
                            )
                            grading_futures[future] = list(valid_indices)

                done_futs = [f for f in grading_futures.keys() if f.done()]
                if done_futs:
                    progressed = True
                for f in done_futs:
                    future_indices = grading_futures.pop(f, [])
                    try:
                        items_res = f.result()
                    except Exception as e:
                        print(f"Future error: {e}")
                        items_res = [
                            {"index": i, "name": student_names[i], "error": True, "msg": f"通义批改线程失败: {e}"}
                            for i in future_indices
                        ]
                    if not items_res:
                        items_res = [
                            {"index": i, "name": student_names[i], "error": True, "msg": "通义批改未返回结果"}
                            for i in future_indices
                        ]
                    for item_res in items_res:
                        with _essay_grade_lock:
                            if job_id in _essay_grade_results:
                                in_progress = _essay_grade_results[job_id].setdefault("in_progress", [])
                                if item_res.get("name") in in_progress:
                                    in_progress.remove(item_res.get("name"))
                                if item_res.get("error"):
                                    _essay_grade_results[job_id]["failed"].append(
                                        {"index": item_res.get("index", -1), "name": item_res.get("name", ""), "msg": item_res.get("msg", "批改失败")}
                                    )
                                    _persist_essay_failure(safe, item_res.get("name", ""), str(item_res.get("msg", "批改失败")))
                                else:
                                    _essay_grade_results[job_id]["completed"].append(item_res)
                                    _persist_essay_success(safe, item_res)

                if not progressed:
                    time.sleep(OCR_POLL_INTERVAL_SEC)

            while grading_futures:
                if stop_ev and stop_ev.is_set():
                    with _essay_grade_lock:
                        if job_id in _essay_grade_results:
                            for f, future_indices in list(grading_futures.items()):
                                try:
                                    items_res = f.result(timeout=0.01)
                                except Exception:
                                    items_res = [
                                        {"index": i, "name": student_names[i], "error": True, "msg": "已停止批改"}
                                        for i in future_indices
                                    ]
                                for item_res in items_res:
                                    in_progress = _essay_grade_results[job_id].setdefault("in_progress", [])
                                    if item_res.get("name") in in_progress:
                                        in_progress.remove(item_res.get("name"))
                                    if item_res.get("error"):
                                        _essay_grade_results[job_id]["failed"].append(
                                            {
                                                "index": item_res.get("index", -1),
                                                "name": item_res.get("name", ""),
                                                "msg": item_res.get("msg", "已停止批改"),
                                            }
                                        )
                    break
                done_futs = [f for f in grading_futures.keys() if f.done()]
                if not done_futs:
                    time.sleep(0.2)
                    continue
                for f in done_futs:
                    future_indices = grading_futures.pop(f, [])
                    try:
                        items_res = f.result()
                    except Exception as e:
                        print(f"Future error: {e}")
                        items_res = [
                            {"index": i, "name": student_names[i], "error": True, "msg": f"通义批改线程失败: {e}"}
                            for i in future_indices
                        ]
                    if not items_res:
                        items_res = [
                            {"index": i, "name": student_names[i], "error": True, "msg": "通义批改未返回结果"}
                            for i in future_indices
                        ]
                    for item_res in items_res:
                        with _essay_grade_lock:
                            if job_id in _essay_grade_results:
                                in_progress = _essay_grade_results[job_id].setdefault("in_progress", [])
                                if item_res.get("name") in in_progress:
                                    in_progress.remove(item_res.get("name"))
                                if item_res.get("error"):
                                    _essay_grade_results[job_id]["failed"].append(
                                        {"index": item_res.get("index", -1), "name": item_res.get("name", ""), "msg": item_res.get("msg", "批改失败")}
                                    )
                                    _persist_essay_failure(safe, item_res.get("name", ""), str(item_res.get("msg", "批改失败")))
                                else:
                                    _essay_grade_results[job_id]["completed"].append(item_res)
                                    _persist_essay_success(safe, item_res)
                if grading_futures:
                    time.sleep(OCR_POLL_INTERVAL_SEC)
    except Exception as e:
        print(f"Essay grade loop failed: {e}")
        with _essay_grade_lock:
            if job_id in _essay_grade_results:
                done_names = set(x.get("name") for x in _essay_grade_results[job_id].get("completed", []))
                failed_names = set(x.get("name") for x in _essay_grade_results[job_id].get("failed", []))
                in_progress = _essay_grade_results[job_id].setdefault("in_progress", [])
                for idx, name in enumerate(student_names):
                    if name in done_names or name in failed_names:
                        continue
                    if name in in_progress:
                        in_progress.remove(name)
                    _essay_grade_results[job_id]["failed"].append(
                        {"index": idx, "name": name, "msg": f"批改内部错误: {e}"}
                    )
                    _persist_essay_failure(safe, name, f"批改内部错误: {e}")

    try:
        from app.services.ai_auto_report.triggers import run_essay_auto_report_async

        run_essay_auto_report_async(ctx_uid, safe)
    except Exception as e:
        print(f"[ai_auto_report] hook after essay grade failed: {e}")

    try:
        # 手动模式（push_dingtalk=false）不推；结果按 job 存在任务字典里
        with _essay_grade_lock:
            _essay_push = bool(
                _essay_grade_results.get(job_id, {}).get("push_dingtalk", True)
            )
        if _essay_push:
            from app.services.dingtalk_notify import notify_grading_done

            notify_grading_done(ctx_uid, safe, "essay")
    except Exception as e:
        print(f"[dingtalk_notify] hook after essay grade failed: {e}")

def _run_print_batch_job(job_id: str, filenames: list[str], printer_name: Optional[str], user_id: str) -> None:
    set_grading_user_id(user_id)
    from app.grading.print_marks import print_image, print_images, sort_marks_filenames_for_print
    printed = 0
    errors = []
    stop_ev = _print_batch_stop_events.get(job_id)
    with _print_batch_lock:
        job = _print_batch_jobs.get(job_id) or {}
        mode = str(job.get("print_mode") or "single")
        paper_size = str(job.get("paper_size") or "a4")
        custom_paper_mm = job.get("custom_paper_mm")
        paper_source = job.get("paper_source")
    filenames = sort_marks_filenames_for_print(list(filenames or []))
    pair_mode = mode == "double"
    try:
        if pair_mode:
            pairs = []
            i = 0
            while i < len(filenames):
                if i + 1 < len(filenames):
                    pairs.append([filenames[i], filenames[i + 1]])
                    i += 2
                else:
                    pairs.append([filenames[i]])
                    i += 1
            total = len(pairs)
            for idx, pair in enumerate(pairs):
                if stop_ev and stop_ev.is_set():
                    break
                paths = []
                bad = False
                for fn in pair:
                    path = modify_dir() / fn
                    if not path.is_file():
                        errors.append({"filename": fn, "msg": "文件不存在"})
                        bad = True
                        continue
                    paths.append(str(path))
                if bad or not paths:
                    with _print_batch_lock:
                        if job_id in _print_batch_jobs:
                            _print_batch_jobs[job_id]["errors"] = errors
                    continue
                ok, msg = print_images(
                    paths,
                    printer_name=printer_name,
                    copies=1,
                    duplex=True,
                    paper_size=paper_size,
                    custom_paper_mm=custom_paper_mm,
                    paper_source=paper_source if isinstance(paper_source, int) else None,
                )
                if ok:
                    printed += len(paths)
                else:
                    errors.append({"filename": ",".join(pair), "msg": msg})
                with _print_batch_lock:
                    if job_id in _print_batch_jobs:
                        _print_batch_jobs[job_id]["printed"] = printed
                        _print_batch_jobs[job_id]["errors"] = errors
                if idx < total - 1:
                    if stop_ev:
                        if stop_ev.wait(_PRINT_BATCH_GAP_SEC):
                            break
                    else:
                        time.sleep(_PRINT_BATCH_GAP_SEC)
        else:
            total = len(filenames)
            for idx, fn in enumerate(filenames):
                if stop_ev and stop_ev.is_set():
                    break
                path = modify_dir() / fn
                if not path.is_file():
                    errors.append({"filename": fn, "msg": "文件不存在"})
                    with _print_batch_lock:
                        if job_id in _print_batch_jobs:
                            _print_batch_jobs[job_id]["errors"] = errors
                    continue
                ok, msg = print_image(
                    str(path),
                    printer_name=printer_name,
                    copies=1,
                    paper_size=paper_size,
                    custom_paper_mm=custom_paper_mm,
                    paper_source=paper_source if isinstance(paper_source, int) else None,
                )
                if ok:
                    printed += 1
                else:
                    errors.append({"filename": fn, "msg": msg})
                with _print_batch_lock:
                    if job_id in _print_batch_jobs:
                        _print_batch_jobs[job_id]["printed"] = printed
                        _print_batch_jobs[job_id]["errors"] = errors
                if idx < total - 1:
                    if stop_ev:
                        if stop_ev.wait(_PRINT_BATCH_GAP_SEC):
                            break
                    else:
                        time.sleep(_PRINT_BATCH_GAP_SEC)
    except Exception as e:
        errors.append({"filename": "", "msg": f"打印任务异常: {e}"})
    finally:
        cancelled = bool(stop_ev and stop_ev.is_set())
        with _print_batch_lock:
            if job_id in _print_batch_jobs:
                _print_batch_jobs[job_id]["printed"] = printed
                _print_batch_jobs[job_id]["errors"] = errors
                _print_batch_jobs[job_id]["done"] = True
                _print_batch_jobs[job_id]["cancelled"] = cancelled
        _print_batch_stop_events.pop(job_id, None)


@router.post("/print-marks")
async def api_print_marks(request: Request, db: Session = Depends(get_db)):
    """打印单张留痕图"""
    _require_local_admin(request, db)  # M5
    from app.grading.print_marks import print_image
    try:
        body = await request.json()
    except Exception:
        body = {}
    filename = (body.get("filename") or "").strip()
    if not _safe_marks_only_filename(filename):
        raise HTTPException(status_code=400, detail="文件名无效")
    
    path = modify_dir() / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="留痕图片不存在")
        
    printer_name = (body.get("printer_name") or "").strip() or None
    paper_size = _parse_paper_size(body)
    custom_paper_mm = _parse_custom_paper_mm(body, paper_size)
    paper_source = _parse_paper_source(body)
    
    ok, msg = print_image(
        str(path), 
        printer_name=printer_name,
        copies=1,
        paper_size=paper_size,
        custom_paper_mm=custom_paper_mm,
        paper_source=paper_source
    )
    if not ok:
        raise HTTPException(status_code=500, detail=msg)
    return {"ok": True, "msg": msg}


@router.post("/print-test-marks/grade")
async def api_print_test_marks_grade(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """测试打印第一步：上传试卷（图片/PDF/Word）→ AI 批改 → 生成留痕，返回留痕文件名供第二步打印。"""
    _require_local_admin(request, db)  # M5
    # 0924：大模型批改发起闸（real_grade_pipeline，无独立上传侧计面 ⇒ 计 1 面）
    quota_gate(charge_pages=1)
    from app.grading.doc_convert import ensure_image_path

    allowed_exts = (".jpg", ".jpeg", ".png", ".webp", ".pdf", ".doc", ".docx")
    ext = ""
    if file.filename:
        lower = file.filename.lower()
        for e in allowed_exts:
            if lower.endswith(e):
                ext = e
                break
    if not ext:
        raise HTTPException(status_code=400, detail="仅支持图片(jpg/png/webp)、PDF 或 Word 文档")

    save_path = test_dir() / f"{uuid.uuid4()}{ext}"
    try:
        content = await file.read()
        save_path.write_bytes(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存文件失败: {e}")

    temp_img_path: Optional[str] = None
    try:
        normalize_uploaded_image_orientation(save_path)
        grade_path, is_temp = ensure_image_path(str(save_path))
        if is_temp:
            temp_img_path = grade_path
        result, blocks_with_result, _, _ = real_grade_pipeline(str(grade_path))
        if not blocks_with_result:
            raise HTTPException(status_code=500, detail="未识别到任何文字块，请换图或检查 OCR 配置。")
        marks_only_name = draw_marks_only_and_save(
            str(grade_path), blocks_with_result, str(modify_dir()), Path(grade_path).stem
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"测试批改失败：{str(e)}")
    finally:
        for p in (save_path, Path(temp_img_path) if temp_img_path else None):
            if p is None:
                continue
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass

    return {"ok": True, "result": result, "marks_only_filename": marks_only_name}


@router.post("/print-marks-batch")
async def api_print_marks_batch(request: Request, db: Session = Depends(get_db)):
    """阻塞式批量打印多张留痕图"""
    _require_local_admin(request, db)  # M5
    from app.grading.print_marks import print_images
    try:
        body = await request.json()
    except Exception:
        body = {}
    filenames = body.get("filenames") or []
    printer_name = (body.get("printer_name") or "").strip() or None
    paper_size = _parse_paper_size(body)
    custom_paper_mm = _parse_custom_paper_mm(body, paper_size)
    paper_source = _parse_paper_source(body)
    
    if not isinstance(filenames, list):
        raise HTTPException(status_code=400, detail="需要 filenames 数组")
    
    paths = []
    errors = []
    for fn in filenames:
        fn = (fn or "").strip()
        if not _safe_marks_only_filename(fn):
            errors.append({"filename": fn, "msg": "文件名无效"})
            continue
        path = modify_dir() / fn
        if not path.is_file():
            errors.append({"filename": fn, "msg": "文件不存在"})
            continue
        paths.append(str(path))
        
    if not paths:
        return {"ok": False, "printed": 0, "errors": errors}
        
    ok, msg = print_images(
        paths,
        printer_name=printer_name,
        copies=1,
        duplex=False,
        paper_size=paper_size,
        custom_paper_mm=custom_paper_mm,
        paper_source=paper_source
    )
    if not ok:
        raise HTTPException(status_code=500, detail=msg)
    return {"ok": True, "printed": len(paths), "errors": errors}


@router.post("/print-marks-pdf")
async def api_print_marks_pdf(request: Request, db: Session = Depends(get_db)):
    """把多张留痕图合成一个 PDF 返回（每图一页），替代物理打印。

    无物理副作用，仅要求登录（router 级 JWT），不要求本机来源（与 _require_local_admin 无关），
    因此局域网访问也可导出 PDF。
    """
    from app.grading.print_marks import images_to_pdf_bytes
    try:
        body = await request.json()
    except Exception:
        body = {}
    filenames = body.get("filenames") or []
    if not isinstance(filenames, list) or not filenames:
        raise HTTPException(status_code=400, detail="需要 filenames 数组")

    paths: list[str] = []
    for fn in filenames:
        fn = (fn or "").strip()
        if not _safe_marks_only_filename(fn):
            raise HTTPException(status_code=400, detail=f"文件名无效: {fn}")
        # 优先用「原卷+留痕」图（annotated_），没有才退回纯留痕（marks_only_）
        annotated_path = modify_dir() / ("annotated_" + fn[len("marks_only_"):])
        if annotated_path.is_file():
            path = annotated_path
        else:
            path = modify_dir() / fn
            if not path.is_file():
                raise HTTPException(status_code=404, detail=f"留痕图片不存在: {fn}")
        paths.append(str(path))

    import asyncio

    def _build_pdf():
        # 1015 根治：合成 PDF 也进全局重活预算排队；放到线程池里等槽位，
        # 排队再久也不堵事件循环（其他请求照常响应）。
        from app.services.heavy_budget import heavy_slot

        with heavy_slot("print-marks-pdf"):
            return images_to_pdf_bytes(paths)

    try:
        pdf_bytes = await asyncio.to_thread(_build_pdf)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成 PDF 失败: {e}")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="marks.pdf"'},
    )


def _rotate_paper_set(stem: str, method, folder: str, raw_name: str) -> list[str]:
    """把某张试卷的整套图片（原卷/留痕/纯留痕 + 预览 + 原始上传件）按 method 一并旋转。

    stem：modify_dir 下的文件名 stem（original_xxx.jpg 去掉前缀后的 xxx.jpg）；空串表示没有留痕输出。
    folder / raw_name：定位预览图与原始上传件（可空）。找不到任何可旋转图片时返回空列表。
    """
    from PIL import Image, ImageOps

    rotated: list[str] = []
    if stem:
        ext = Path(stem).suffix.lower()
        for prefix in ("original_", "annotated_", "marks_only_"):
            target = modify_dir() / f"{prefix}{stem}"
            if not target.is_file():
                continue
            im = Image.open(target)
            im = ImageOps.exif_transpose(im).transpose(method)
            save_kw: dict = {}
            if ext in (".jpg", ".jpeg"):
                im = im.convert("RGB")
                save_kw = {"quality": 95}
            im.save(target, **save_kw)
            im.close()
            rotated.append(f"{prefix}{stem}")

    raw_paths: list[Path] = []
    if folder and raw_name:
        safe_folder = _safe_folder_name(folder)
        if safe_folder and ".." not in raw_name and "/" not in raw_name and "\\" not in raw_name:
            # 预览图（前端「试卷」实际显示的就是它）；PDF 预览名带 _img 后缀
            preview_name = _preview_image_name_for_file(raw_name)
            if preview_name:
                candidate = correct_docs_img_dir() / safe_folder / preview_name
                if candidate.is_file() and candidate.suffix.lower() in _IMAGE_EXTS:
                    raw_paths.append(candidate)
            # 原图本身（仅图片上传存在；PDF 源文件不旋转）
            if Path(raw_name).suffix.lower() in _IMAGE_EXTS:
                candidate = correct_docs_dir() / safe_folder / raw_name
                if candidate.is_file():
                    raw_paths.append(candidate)

    for raw_path in raw_paths:
        raw_ext = raw_path.suffix.lower()
        im = Image.open(raw_path)
        im = ImageOps.exif_transpose(im).transpose(method)
        save_kw: dict = {}
        if raw_ext in (".jpg", ".jpeg"):
            im = im.convert("RGB")
            save_kw = {"quality": 95}
        im.save(raw_path, **save_kw)
        im.close()
        rotated.append(f"raw:{raw_name}")

    return rotated


def _auto_rotate_baidu_output(baidu_raw: dict, stem: str, folder: str, raw_name: str) -> int:
    """批改后依据百度 detect_direction 的朝向码自动摆正整套图片，返回朝向码（0/1/2/3，-1 未处理）。

    倒置扫描件（无 EXIF）上传后上下颠倒，百度 detect_direction=true 时会在结果里报方向；
    这里把原卷/留痕/预览一并反向旋转到正向，避免「卷子正、留痕反」。
    只按百度明确返回的朝向码动作，取不到方向时不动（-1），绝不误转已正的卷子。
    可用环境变量 GRADING_AUTO_ROTATE=off 关闭。
    """
    flag = os.environ.get("GRADING_AUTO_ROTATE", "").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return -1
    code = extract_baidu_image_direction(baidu_raw or {})
    if code not in (1, 2, 3):
        return code
    from PIL import Image

    # direction 表示输入图相对正向的旋转量：1=逆90 2=逆180 3=逆270，摆正需反向旋转。
    method = {1: Image.ROTATE_270, 2: Image.ROTATE_180, 3: Image.ROTATE_90}[code]
    try:
        rotated = _rotate_paper_set(stem or "", method, folder or "", raw_name or "")
        print(f"[auto-rotate] 百度朝向={code} 已自动摆正: {rotated}")
    except Exception as e:
        print(f"[auto-rotate] 自动摆正失败: {e}")
    return code


@router.post("/rotate-image")
async def api_rotate_image(request: Request, db: Session = Depends(get_db)):
    """把某张试卷的原卷/留痕图整体旋转 90°（left=逆时针 / right=顺时针），用于纠正倒置、侧倒的扫描件。

    传入任一图片文件名（original_/annotated_/marks_only_ 开头，或原始上传文件名），后端把
    原卷、留痕、纯留痕、预览、原始上传件一并旋转，保证预览与「输出 PDF」一致。
    """
    from PIL import Image

    try:
        body = await request.json()
    except Exception:
        body = {}
    filename = (body.get("filename") or "").strip()
    direction = str(body.get("direction") or "right").strip().lower()
    if direction not in ("left", "right"):
        raise HTTPException(status_code=400, detail="direction 仅支持 left 或 right")

    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="文件名无效")

    folder = (body.get("folder") or "").strip()
    raw_name = (body.get("raw_name") or "").strip()

    # 留痕输出文件名（original_/annotated_/marks_only_ 前缀）→ 取 stem；否则视为原始上传文件名（批改前旋转）
    stem = None
    for prefix in ("original_", "annotated_", "marks_only_"):
        if filename.startswith(prefix):
            stem = filename[len(prefix):]
            break
    if stem is None:
        if not raw_name:
            raw_name = filename
        # 批改前旋转：支持图片，也支持 PDF（PDF 源不转，只转其预览图 xxx_img.jpg）
        if Path(filename).suffix.lower() not in _IMAGE_EXTS | {".pdf"}:
            raise HTTPException(status_code=400, detail="仅支持图片或 PDF 文件")
    else:
        if Path(stem).suffix.lower() not in (".jpg", ".jpeg", ".png"):
            raise HTTPException(status_code=400, detail="仅支持 jpg/jpeg/png 图片")

    # ROTATE_90 = 逆时针 90°（左转）；ROTATE_270 = 顺时针 90°（右转）
    method = Image.ROTATE_270 if direction == "right" else Image.ROTATE_90
    try:
        rotated = _rotate_paper_set(stem or "", method, folder, raw_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"旋转失败: {e}")

    if not rotated:
        raise HTTPException(status_code=404, detail="未找到可旋转的图片")

    return {"ok": True, "direction": direction, "rotated": rotated}


@router.post("/print-marks-batch/start")
async def api_print_marks_batch_start(request: Request, db: Session = Depends(get_db)):
    """启动后台批量打印任务，立即返回 job_id，支持轮询与取消。"""
    _require_local_admin(request, db)  # M5
    try:
        body = await request.json()
    except Exception:
        body = {}
    filenames = body.get("filenames") or []
    printer_name = (body.get("printer_name") or "").strip() or None
    print_mode = str(body.get("print_mode") or "single").strip().lower()
    paper_size = _parse_paper_size(body)
    custom_paper_mm = _parse_custom_paper_mm(body, paper_size)
    paper_source = _parse_paper_source(body)
    if print_mode not in ("single", "double"):
        raise HTTPException(status_code=400, detail="print_mode 仅支持 single 或 double")
    if not isinstance(filenames, list):
        raise HTTPException(status_code=400, detail="需要 filenames 数组")
    validated = []
    for fn in filenames:
        fn = (fn or "").strip()
        if not _safe_marks_only_filename(fn):
            continue
        validated.append(fn)
    if not validated:
        raise HTTPException(status_code=400, detail="没有可打印的有效留痕文件")
    job_id = str(uuid.uuid4())
    with _print_batch_lock:
        _print_batch_jobs[job_id] = {
            "total": len(validated),
            "printed": 0,
            "errors": [],
            "done": False,
            "cancelled": False,
            "print_mode": print_mode,
            "paper_size": paper_size,
            "custom_paper_mm": custom_paper_mm,
            "paper_source": paper_source,
            "user_id": get_grading_user_id(),
        }
    _print_batch_stop_events[job_id] = threading.Event()

    def _run_print_batch_guarded():
        # 1015 根治：打印批次也进全局重活预算排队（与批改/报告共享槽位）
        from app.services.heavy_budget import heavy_slot

        with heavy_slot("print-batch"):
            _run_print_batch_job(job_id, validated, printer_name, get_grading_user_id())

    threading.Thread(
        target=_run_print_batch_guarded,
        daemon=True,
    ).start()
    return {"ok": True, "job_id": job_id, "total": len(validated)}


@router.get("/print-marks-batch/status/{job_id}")
async def api_print_marks_batch_status(job_id: str, request: Request, db: Session = Depends(get_db)):
    _require_local_admin(request, db)  # M5
    with _print_batch_lock:
        data = _print_batch_jobs.get(job_id)
    if not data:
        raise HTTPException(status_code=404, detail="打印任务不存在或已过期")
    _assert_job_owner(data)
    return {
        "ok": True,
        "total": data.get("total", 0),
        "printed": data.get("printed", 0),
        "errors": data.get("errors", []),
        "done": bool(data.get("done")),
        "cancelled": bool(data.get("cancelled")),
        "print_mode": data.get("print_mode", "single"),
    }


@router.post("/print-marks-batch/cancel")
async def api_print_marks_batch_cancel(request: Request, db: Session = Depends(get_db)):
    _require_local_admin(request, db)  # M5
    try:
        body = await request.json()
    except Exception:
        body = {}
    job_id = (body.get("job_id") or "").strip()
    if not job_id:
        raise HTTPException(status_code=400, detail="缺少 job_id")
    with _print_batch_lock:
        _pb_data = _print_batch_jobs.get(job_id)
    # 任务记录存在时校验归属（防 IDOR）；已清理则保持原“尽力取消”语义
    if _pb_data is not None:
        _assert_job_owner(_pb_data)
    ev = _print_batch_stop_events.get(job_id)
    if ev:
        ev.set()
    with _print_batch_lock:
        if job_id in _print_batch_jobs:
            _print_batch_jobs[job_id]["cancelled"] = True
    return {"ok": True, "msg": "已请求取消打印"}


@router.post("/folders/{folder_name:path}/essay-grade/start")
async def api_start_essay_grade(folder_name: str, request: Request):
    """启动作文批改任务（支持单张或多张选择）"""
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    _quota_gate()  # 0924 额度 105% 硬停前置闸门
    try:
        body = await request.json()
    except Exception:
        body = {}
    rubric_text = str(body.get("rubric_text") or "").strip()
    prompts = {
        "summary_prompt": str(body.get("summary_prompt") or "").strip(),
        "comment_prompt": str(body.get("comment_prompt") or "").strip(),
        "rewrite_prompt": str(body.get("rewrite_prompt") or "").strip(),
        "guidance_prompt": str(body.get("guidance_prompt") or "").strip(),
        "scoring_prompt": str(body.get("scoring_prompt") or "").strip(),
        "topic_text": str(body.get("topic_text") or "").strip(),
        "topic_image_base64": str(body.get("topic_image_base64") or "").strip(),
        "dimensions_json": str(body.get("dimensions_json") or "").strip(),
    }
    only_filename = body.get("filename")
    only_filenames_list = body.get("filenames")
    requested_specific_files = bool(only_filename or only_filenames_list)
    
    only_filenames = None
    if isinstance(only_filenames_list, list) and len(only_filenames_list) > 0:
        only_filenames = set(str(x).strip() for x in only_filenames_list if str(x).strip())
    
    if only_filename:
        only_filename = str(only_filename).strip()

    job_id = str(uuid.uuid4())
    with _essay_grade_lock:
        _essay_grade_results[job_id] = {
            "total": 0,
            "completed": [],
            "failed": [],
            "in_progress": [],
            "ocr_tasks": {},
            "user_id": get_grading_user_id(),
            # 批改完是否自动推钉钉（前端「自动推送钉钉/手动」开关）
            "push_dingtalk": bool(body.get("push_dingtalk", True)),
        }
        _essay_grade_stop_events[job_id] = threading.Event()

    dir_path = correct_docs_dir() / safe
    if not dir_path.is_dir():
        with _essay_grade_lock:
            _essay_grade_results[job_id]["failed"].append({"index": -1, "name": "ALL", "msg": "文件夹不存在"})
        return {"ok": True, "job_id": job_id, "total": 0}

    # 扩展 target 以包含同组的所有页面
    if only_filename or only_filenames:
        target_bases = set()
        for f in dir_path.iterdir():
            if not f.is_file() or f.suffix.lower() not in _ALL_UPLOAD_EXTS:
                continue
            if _is_standard_answer_filename(f.name):
                continue
            if only_filename and f.name == only_filename:
                target_bases.add(_get_student_base_name(f.name))
            if only_filenames and f.name in only_filenames:
                target_bases.add(_get_student_base_name(f.name))
        
        expanded_filenames = set()
        for f in dir_path.iterdir():
            if not f.is_file() or f.suffix.lower() not in _ALL_UPLOAD_EXTS:
                continue
            if _is_standard_answer_filename(f.name):
                continue
            if _get_student_base_name(f.name) in target_bases:
                expanded_filenames.add(f.name)
                
        only_filenames = expanded_filenames
        only_filename = None

    student_names = []
    for f in dir_path.iterdir():
        if not f.is_file() or f.suffix.lower() not in _ALL_UPLOAD_EXTS:
            continue
        if _is_standard_answer_filename(f.name) or _is_answer_sheet_filename(f.name):
            continue
        if only_filename and f.name != only_filename:
            continue
        if only_filenames is not None and f.name not in only_filenames:
            continue
        student_names.append(f.name)

    if not student_names:
        with _essay_grade_lock:
            _essay_grade_results.pop(job_id, None)
            _essay_grade_stop_events.pop(job_id, None)
        raise HTTPException(status_code=400, detail="未匹配到可重新批改的试卷，请刷新列表后重试")

    # 选择批改或单张重批时，先移除旧的作文历史，避免前端继续显示旧结果，
    # 也确保已批改学生可以被当作一次全新的作文任务重新批改。
    if requested_specific_files:
        for name in student_names:
            _remove_essay_history_entry(safe, name)
    
    # 支持多页合并批改：按照前缀分组统计真正的总批改份数
    groups = {}
    for name in student_names:
        base = _get_student_base_name(name)
        groups.setdefault(base, []).append(name)

    total = len(student_names)
    with _essay_grade_lock:
        _essay_grade_results[job_id]["total"] = total
        _essay_grade_results[job_id]["in_progress"] = student_names

    threading.Thread(
        target=_run_essay_grade,
        args=(job_id, safe, rubric_text, only_filename, only_filenames, prompts, get_grading_user_id()),
        daemon=True,
    ).start()
    return {"ok": True, "job_id": job_id, "total": total}

@router.get("/folders/{folder_name:path}/essay-grade/status/{job_id}")
async def api_essay_grade_status(folder_name: str, job_id: str):
    """查询作文批改状态"""
    safe = _safe_folder_name(folder_name)
    with _essay_grade_lock:
        data = _essay_grade_results.get(job_id)
    if not data:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    _assert_job_owner(data)

    total = data.get("total", 0)
    completed = data.get("completed", [])
    failed = data.get("failed", [])
    in_progress = data.get("in_progress", [])
    done = bool(total > 0 and (len(completed) + len(failed) >= total))
    if not in_progress:
        done = done or bool(total > 0 and (len(completed) + len(failed) >= total))

    current_name = None
    if in_progress:
        current_name = in_progress[0]
        ocr_task = data.get("ocr_tasks", {}).get(current_name)
        if ocr_task:
            st = ocr_task.get("status")
            if st == "uploading":
                current_name += " (正在上传OCR)"
            elif st == "pending":
                current_name += " (OCR识别中)"
            elif st == "success":
                current_name += " (AI批改中)"

    return {
        "ok": True,
        "total": total,
        "completed": completed,
        "failed": failed,
        "current_name": current_name,
        "done": done,
    }

@router.post("/folders/{folder_name:path}/essay-grade/cancel")
async def api_cancel_essay_grade(folder_name: str, request: Request):
    """取消作文批改任务"""
    safe = _safe_folder_name(folder_name)
    try:
        body = await request.json()
    except Exception:
        body = {}
    job_id = body.get("job_id")
    if not job_id:
        raise HTTPException(status_code=400, detail="缺少 job_id")
    with _essay_grade_lock:
        _eg_data = _essay_grade_results.get(job_id)
    if _eg_data is not None:
        _assert_job_owner(_eg_data)
    ev = _essay_grade_stop_events.get(job_id)
    if ev:
        ev.set()
    return {"ok": True, "msg": "已发送停止指令"}


# ---------- A2-B2 作文改分 + 局部重批 ----------

class EssayScoreUpdateBody(BaseModel):
    """作文改分请求体：仅服务 essay 引擎。"""

    filename: str
    dimension_scores: dict[str, float]
    total_score: Optional[float] = None
    regenerate_report: bool = False


def _format_essay_score(value) -> str:
    """将分数格式化为展示串：整数不带小数点（83 -> '83'），非整数保留（83.5 -> '83.5'）。"""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(num)) if num.is_integer() else str(num)


def _replace_essay_grade_line(text: str, grade: str) -> str:
    """把【作文得分】块后的「等级：X」行替换为新等级；无该行则在分数行后插入。"""
    if re.search(r"^等级：", text, flags=re.M):
        return re.sub(r"^等级：.*$", f"等级：{grade}", text, count=1, flags=re.M)
    return re.sub(
        r"(【作文得分】\n[^\n]*分\s*\n)",
        lambda m: f"{m.group(1)}等级：{grade}\n",
        text,
        count=1,
    )


def _replace_essay_score_first_line(result_text: str, new_total, grade: Optional[str] = None) -> str:
    """把 result 首行【作文得分】后的分数替换为新总分，其它【】板块原样保留。

    同时同步末尾遗留的 <essay_score> 隐藏标签（历史记录会持久化该标签），
    避免记录内新旧总分不一致；该标签非【】板块，不影响板块结构。
    grade 非空时同步「等级：X」行（R18/R16 等级制）。
    """
    new_score = _format_essay_score(new_total)
    text = str(result_text or "")
    if "【作文得分】" not in text:
        grade_line = f"等级：{grade}\n" if grade else ""
        text = f"【作文得分】\n{new_score} 分\n{grade_line}\n" + text.lstrip("\n")
    else:
        text = re.sub(
            r"(【作文得分】\n)[^\n]*",
            lambda m: f"{m.group(1)}{new_score} 分",
            text,
            count=1,
        )
        if grade:
            text = _replace_essay_grade_line(text, grade)
    text = re.sub(
        r"<essay_score>.*?</essay_score>",
        f"<essay_score>{new_score}</essay_score>",
        text,
        count=1,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return text


def _resolve_essay_item_dimensions(item: dict) -> list[dict]:
    """从 completed 项解析评分维度配置：已存 dimensions > prompts.dimensions_json > 默认五维。"""
    from app.grading.essay_grading import DEFAULT_DIMENSIONS

    dims = item.get("dimensions")
    if isinstance(dims, list) and dims:
        return dims
    dimensions_json = str(((item.get("prompts") or {}).get("dimensions_json")) or "").strip()
    if dimensions_json:
        try:
            parsed = json.loads(dimensions_json)
            if isinstance(parsed, list) and parsed:
                return parsed
        except Exception:
            pass
    return list(DEFAULT_DIMENSIONS)


def _validate_essay_score_dimensions(dimension_scores: dict, dimensions: list[dict]) -> None:
    """校验改分维度：key 必须都在维度配置内、每个值在 [0, full_score]，非法抛 422。"""
    if not isinstance(dimension_scores, dict) or not dimension_scores:
        raise HTTPException(status_code=422, detail="dimension_scores 不能为空")
    dim_map = {}
    for d in dimensions or []:
        key = (d or {}).get("key")
        if key:
            dim_map[str(key)] = d
    errors = []
    for raw_key, val in dimension_scores.items():
        key = str(raw_key)
        dim = dim_map.get(key)
        if dim is None:
            errors.append(f"未知维度: {key}")
            continue
        try:
            num = float(val)
        except (TypeError, ValueError):
            errors.append(f"维度 {key} 得分必须是数字")
            continue
        full = dim.get("full_score")
        try:
            full_score = float(full) if full is not None else float("inf")
        except (TypeError, ValueError):
            full_score = float("inf")
        if num < 0 or num > full_score:
            errors.append(f"维度 {key} 得分 {num} 超出范围 [0, {full_score}]")
    if errors:
        raise HTTPException(status_code=422, detail="；".join(errors))


@router.post("/folders/{folder_name:path}/essay-grade/score")
async def api_update_essay_score(
    folder_name: str,
    body: EssayScoreUpdateBody,
    user_id: str = Depends(get_current_user_id),
):
    """A2-B2 作文改分 + 局部重批（仅 essay 引擎）。

    默认模式（regenerate_report=False）：只写记录，不重新 OCR、不重新 LLM——
    更新 completed 项 dimension_scores / score_total，并把 result 首行
    【作文得分】分数替换为新总分，其它【】板块原样保留。

    局部重批模式（regenerate_report=True）：复用已存 ocr_title/ocr_content
    （不重新 OCR）+ 改后维度分，调 essay_grading.regrade_essay_with_qwen
    重新生成整篇点评，整体替换 result，并更新维度分与总分。
    """
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    set_grading_user_id(user_id)

    filename = str(body.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=422, detail="filename 不能为空")

    with _essay_history_lock:
        data = _read_essay_history(safe)
    completed = data.get("completed") or {}
    item = completed.get(filename)
    if not isinstance(item, dict):
        raise HTTPException(status_code=404, detail="未找到该作文批改记录")

    dimensions = _resolve_essay_item_dimensions(item)
    _validate_essay_score_dimensions(body.dimension_scores, dimensions)

    try:
        total_score = float(body.total_score) if body.total_score is not None else float(sum(body.dimension_scores.values()))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="total_score 必须是数字")
    new_score_text = _format_essay_score(total_score)
    from app.grading.essay_grading import derive_essay_grade
    new_grade = derive_essay_grade(total_score, dimensions)

    if body.regenerate_report:
        # 0924：局部重批走 regrade_essay_with_qwen（大模型）⇒ 接闸；不计面
        # （图片在上传/发起作文批改时已计，防双扣）。只写记录模式不调模型，不拦。
        quota_gate()
        title = str(item.get("ocr_title") or "").strip()
        content = str(item.get("ocr_content") or "").strip()
        if not content:
            raise HTTPException(status_code=422, detail="缺少已存 OCR 文本，无法局部重批")
        rubric_text = str(item.get("rubric_text") or "")
        prompts = item.get("prompts") or {}
        # 用改后维度分覆盖维度配置的 full_score，作为重评的评分配置
        new_dims = []
        for d in dimensions:
            nd = dict(d or {})
            key = str(nd.get("key"))
            if key in body.dimension_scores:
                nd["full_score"] = float(body.dimension_scores[key])
            new_dims.append(nd)

        from app.grading.essay_grading import normalize_essay_result_text, regrade_essay_with_qwen

        result_text = regrade_essay_with_qwen(title, content, rubric_text, prompts, new_dims)
        parsed = _extract_essay_grade_scores(result_text, new_dims)
        clean_text = (parsed.get("clean_text") or "").strip()
        # 去掉 AI 偶尔残留的【评分】栏
        clean_text = re.sub(r"【评分】[\s\S]*?(?=\n【|$)", "", clean_text).strip()
        grade_line = f"等级：{new_grade}\n" if new_grade else ""
        new_result = f"【作文得分】\n{new_score_text} 分\n{grade_line}\n" + clean_text
        item["result"] = normalize_essay_result_text(new_result)
    else:
        item["result"] = _replace_essay_score_first_line(item.get("result") or "", total_score, new_grade)

    item["score_total"] = total_score
    item["essay_grade"] = new_grade
    item["dimension_scores"] = {k: float(v) for k, v in body.dimension_scores.items()}

    with _essay_history_lock:
        data["completed"][filename] = item
        _write_essay_history(safe, data)

    # 作文改分/局部重批后总分变了 → 同步导入学情+自动分层（客户清单 #7）
    try:
        _schedule_auto_sync_class(get_grading_user_id(), safe)
    except Exception:
        pass

    return {
        "ok": True,
        "regenerate_report": body.regenerate_report,
        "completed": {
            "name": item.get("name") or filename,
            "filename": filename,
            "score_total": item.get("score_total"),
            "dimension_scores": item.get("dimension_scores"),
            "result": item.get("result"),
        },
    }


# ---------- A2-C 作文文案手动修改 ----------

class EssayResultUpdateBody(BaseModel):
    """作文文案修改请求体：老师直接改 AI 写的评语/总评/建议等正文，整体替换 result。"""

    filename: str
    result: str


_ESSAY_SCORE_LINE_RE = re.compile(r"【作文得分】\s*\n?\s*([\d]+(?:\.\d+)?)\s*分")


@router.post("/folders/{folder_name:path}/essay-grade/result")
async def api_update_essay_result(
    folder_name: str,
    body: EssayResultUpdateBody,
    user_id: str = Depends(get_current_user_id),
):
    """A2-C 作文文案手动修改（仅 essay 引擎）。

    老师对 AI 生成的【总评】【分项评语】【修改建议】【升格范文】等正文不满意时，
    直接改成自己认可的版本并保存。整体替换 result 文本，不重跑 OCR、不重跑 LLM；
    若老师顺手改了【作文得分】行，则同步 score_total（维度分不变，分数精修仍走改分入口）。
    """
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    set_grading_user_id(user_id)

    filename = str(body.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=422, detail="filename 不能为空")
    new_result = str(body.result or "").strip()
    if not new_result:
        raise HTTPException(status_code=422, detail="result 不能为空")

    with _essay_history_lock:
        data = _read_essay_history(safe)
    completed = data.get("completed") or {}
    item = completed.get(filename)
    if not isinstance(item, dict):
        raise HTTPException(status_code=404, detail="未找到该作文批改记录")

    from app.grading.essay_grading import derive_essay_grade, normalize_essay_result_text

    item["result"] = normalize_essay_result_text(new_result)

    # 顺带同步【作文得分】总分（可选）：改文案时若改了分数行，保持卡片总分一致。
    m = _ESSAY_SCORE_LINE_RE.search(item["result"])
    if m:
        try:
            item["score_total"] = float(m.group(1))
        except (TypeError, ValueError):
            pass
    # R18/R16 等级制：分数可能被老师顺手改动，重算等级保持一致
    try:
        if item.get("score_total") is not None:
            item["essay_grade"] = derive_essay_grade(item.get("score_total"), _resolve_essay_item_dimensions(item))
    except Exception:
        pass

    # 老师编辑文案时可能删掉末尾 <essay_score> 隐藏标签，这里写回并与同步后的总分保持一致
    try:
        if item.get("score_total") is not None:
            tag = f"<essay_score>{_format_essay_score(item['score_total'])}</essay_score>"
            if re.search(r"<essay_score>.*?</essay_score>", item["result"], flags=re.DOTALL | re.IGNORECASE):
                item["result"] = re.sub(
                    r"<essay_score>.*?</essay_score>",
                    tag,
                    item["result"],
                    count=1,
                    flags=re.DOTALL | re.IGNORECASE,
                )
            else:
                item["result"] = item["result"].rstrip() + "\n" + tag
    except Exception:
        pass

    with _essay_history_lock:
        data["completed"][filename] = item
        _write_essay_history(safe, data)

    # 作文改分/局部重批后总分变了 → 同步导入学情+自动分层（客户清单 #7）
    try:
        _schedule_auto_sync_class(get_grading_user_id(), safe)
    except Exception:
        pass

    return {
        "ok": True,
        "completed": {
            "name": item.get("name") or filename,
            "filename": filename,
            "score_total": item.get("score_total"),
            "dimension_scores": item.get("dimension_scores"),
            "result": item.get("result"),
        },
    }


# ---------- 作文批改标准 (Essay Rubric) ----------

@router.get("/rubrics")
async def api_get_rubrics(user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from app.models.essay_rubric import EssayRubric
    rubrics = db.query(EssayRubric).filter(EssayRubric.user_id == user_id).order_by(EssayRubric.created_at.desc()).all()
    return {
            "ok": True,
            "rubrics": [
                {
                    "id": r.id,
                    "name": r.name,
                    "content": r.content,
                    "summary_prompt": r.summary_prompt,
                    "comment_prompt": r.comment_prompt,
                    "rewrite_prompt": r.rewrite_prompt,
                    "guidance_prompt": r.guidance_prompt,
                    "scoring_prompt": r.scoring_prompt,
                    "topic_text": r.topic_text,
                    "topic_image_base64": r.topic_image_base64,
                    "dimensions_json": r.dimensions_json,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                } for r in rubrics
            ]
        }

@router.post("/rubrics")
async def api_create_rubric(request: Request, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from app.models.essay_rubric import EssayRubric
    import uuid
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = (body.get("name") or "").strip()
    content = (body.get("content") or "").strip()
    summary_prompt = (body.get("summary_prompt") or "").strip()
    comment_prompt = (body.get("comment_prompt") or "").strip()
    rewrite_prompt = (body.get("rewrite_prompt") or "").strip()
    guidance_prompt = (body.get("guidance_prompt") or "").strip()
    scoring_prompt = (body.get("scoring_prompt") or "").strip()
    topic_text = (body.get("topic_text") or "").strip()
    topic_image_base64 = (body.get("topic_image_base64") or "").strip()
    dimensions_json = (body.get("dimensions_json") or "").strip()

    if not name:
        raise HTTPException(status_code=400, detail="规则名称不能为空")

    new_rubric = EssayRubric(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name=name,
        content=content,
        summary_prompt=summary_prompt,
        comment_prompt=comment_prompt,
        rewrite_prompt=rewrite_prompt,
        guidance_prompt=guidance_prompt,
        scoring_prompt=scoring_prompt,
        topic_text=topic_text,
        topic_image_base64=topic_image_base64,
        dimensions_json=dimensions_json
    )
    db.add(new_rubric)
    db.commit()
    db.refresh(new_rubric)
    return {
        "ok": True,
        "rubric": {
            "id": new_rubric.id,
            "name": new_rubric.name,
            "content": new_rubric.content,
            "summary_prompt": new_rubric.summary_prompt,
            "comment_prompt": new_rubric.comment_prompt,
            "rewrite_prompt": new_rubric.rewrite_prompt,
            "guidance_prompt": new_rubric.guidance_prompt,
            "scoring_prompt": new_rubric.scoring_prompt,
            "topic_text": new_rubric.topic_text,
            "topic_image_base64": new_rubric.topic_image_base64,
            "dimensions_json": new_rubric.dimensions_json,
            "created_at": new_rubric.created_at,
            "updated_at": new_rubric.updated_at,
        }
    }

@router.put("/rubrics/{rubric_id}")
async def api_update_rubric(rubric_id: str, request: Request, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from app.models.essay_rubric import EssayRubric
    try:
        body = await request.json()
    except Exception:
        body = {}
    content = (body.get("content") or "").strip()
    name = (body.get("name") or "").strip()
    summary_prompt = (body.get("summary_prompt") or "").strip()
    comment_prompt = (body.get("comment_prompt") or "").strip()
    rewrite_prompt = (body.get("rewrite_prompt") or "").strip()
    guidance_prompt = (body.get("guidance_prompt") or "").strip()
    scoring_prompt = (body.get("scoring_prompt") or "").strip()
    topic_text = (body.get("topic_text") or "").strip()
    topic_image_base64 = (body.get("topic_image_base64") or "").strip()
    dimensions_json = (body.get("dimensions_json") or "").strip()

    rubric = db.query(EssayRubric).filter(EssayRubric.id == rubric_id, EssayRubric.user_id == user_id).first()
    if not rubric:
        raise HTTPException(status_code=404, detail="未找到该批改标准")
    
    if name:
        rubric.name = name
    rubric.content = content
    if "summary_prompt" in body:
        rubric.summary_prompt = summary_prompt
    if "comment_prompt" in body:
        rubric.comment_prompt = comment_prompt
    if "rewrite_prompt" in body:
        rubric.rewrite_prompt = rewrite_prompt
    if "guidance_prompt" in body:
        rubric.guidance_prompt = guidance_prompt
    if "scoring_prompt" in body:
        rubric.scoring_prompt = scoring_prompt
    if "topic_text" in body:
        rubric.topic_text = topic_text
    if "topic_image_base64" in body:
        rubric.topic_image_base64 = topic_image_base64
    if "dimensions_json" in body:
        rubric.dimensions_json = dimensions_json
    db.commit()
    db.refresh(rubric)
    return {
        "ok": True,
        "rubric": {
            "id": rubric.id,
            "name": rubric.name,
            "content": rubric.content,
            "summary_prompt": rubric.summary_prompt,
            "comment_prompt": rubric.comment_prompt,
            "rewrite_prompt": rubric.rewrite_prompt,
            "guidance_prompt": rubric.guidance_prompt,
            "scoring_prompt": rubric.scoring_prompt,
            "topic_text": rubric.topic_text,
            "topic_image_base64": rubric.topic_image_base64,
            "dimensions_json": rubric.dimensions_json,
            "created_at": rubric.created_at,
            "updated_at": rubric.updated_at,
        }
    }

@router.delete("/rubrics")
async def api_delete_rubrics(request: Request, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from app.models.essay_rubric import EssayRubric
    try:
        body = await request.json()
    except Exception:
        body = {}
    ids = body.get("ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="请选择要删除的规则")
    
    db.query(EssayRubric).filter(EssayRubric.id.in_(ids), EssayRubric.user_id == user_id).delete(synchronize_session=False)
    db.commit()
    return {"ok": True, "msg": f"已成功删除 {len(ids)} 个批改标准"}

# ---------- 错题本 (Error Book) ----------

def _infer_ai_block_status(content: str) -> str:
    """
    推断 AI 批改块的状态：correct, wrong, blank, partial, 或 unknown
    """
    t = (content or "").strip()
    if not t:
        return "unknown"

    # 1. 提取最前面的判定结果（最准确，匹配：第X题: 正确）
    status_match = re.search(
        r'^第[0-9A-Za-z\(\)（）一二三四五六七八九十百千两]+题(?:[-—]作答区[0-9]+)?[:：]\s*(对|错|正确|错误|半对|未答|未作答|空白)',
        t
    )
    if status_match:
        s = status_match.group(1)
        if s in ["对", "正确"]: return "correct"
        if s in ["错", "错误"]: return "wrong"
        if s in ["半对"]: return "partial"
        if s in ["未答", "未作答", "空白"]: return "blank"

    # 2. 兜底精确匹配冒号后的状态
    if any(x in t for x in ["：对", ": 对", "：正确", ": 正确"]): return "correct"
    if any(x in t for x in ["：错", ": 错", "：错误", ": 错误"]): return "wrong"
    if any(x in t for x in ["：半对", ": 半对"]): return "partial"
    if any(x in t for x in ["：未作答", ": 未作答", "：空白"]): return "blank"

    # 3. 最后的模糊关键字匹配
    t_lower = t.lower()
    if re.search(r'半对', t_lower):
        return "partial"
    if re.search(r'未作答|未答|空白|未填写|blank', t_lower):
        return "blank"
    if re.search(r'错误|不正确|有误|incorrect|wrong', t_lower):
        return "wrong"
    if re.search(r'正确|匹配|无明显错误|correct', t_lower):
        return "correct"

    return "unknown"


def _extract_partial_ratio(content: str):
    """从结果文本里提取半对比例（如 半对（0.6）→ 0.6）；没有则返回 None。"""
    m = re.search(r'半对[（(]\s*([0-9]+(?:\.[0-9]+)?)\s*[)）]', content or "")
    if not m:
        return None
    try:
        return min(1.0, max(0.0, float(m.group(1))))
    except (TypeError, ValueError):
        return None


def _snap_partial_ratio(ratio) -> float:
    """半对给分只落在 0 / 0.5 / 1 三档，杜绝 0.6/0.7 这种脏小数分。

    小学批改只认整分/半分；大模型给的「0.6」是「对六成」的粗略比例，直接乘会出
    0.6/1.2/1.4 这种卷面上不该出现的小数。这里就近归到最近的半档：
    0.75 及以上算全对(1.0)，0.25 以下算错(0.0)，中间算半对(0.5)。
    """
    try:
        r = float(ratio)
    except (TypeError, ValueError):
        return 0.5
    r = min(1.0, max(0.0, r))
    if r >= 0.75:
        return 1.0
    if r >= 0.25:
        return 0.5
    return 0.0

def _parse_ai_result_to_counts(text: str):
    """
    解析 AI 结果文本并统计对错数量，返回 counts 和 blocks
    """
    raw = (text or "").strip()
    if not raw:
        return {"correct": 0, "wrong": 0, "blank": 0, "unknown": 0, "partial": 0}, []

    lines = raw.splitlines()
    q_start_pattern = re.compile(r'^第([0-9A-Za-z\(\)（）一二三四五六七八九十百千两]+)题')
    
    blocks = []
    current_title = ""
    current_buffer = []
    
    def flush():
        if current_title:
            content = "\n".join(current_buffer).strip()
            item_status = _infer_ai_block_status(content)
            item_partial_ratio = _extract_partial_ratio(content)

            # Check if this main question already exists
            existing_block = next((b for b in blocks if b["title"] == current_title), None)
            if existing_block:
                if "subItems" not in existing_block:
                    existing_block["subItems"] = []
                existing_block["subItems"].append({
                    "content": content,
                    "status": item_status,
                    "partial_ratio": item_partial_ratio
                })
                existing_block["content"] += "\n\n" + content
                if item_status in ["wrong", "blank"]:
                    existing_block["status"] = "wrong"
                elif item_status == "partial" and existing_block.get("status") not in ("wrong",):
                    existing_block["status"] = "partial"
                    existing_block["partial_ratio"] = item_partial_ratio
            else:
                blocks.append({
                    "title": current_title,
                    "content": content,
                    "status": item_status,
                    "partial_ratio": item_partial_ratio,
                    "subItems": [{
                        "content": content,
                        "status": item_status,
                        "partial_ratio": item_partial_ratio
                    }]
                })
        current_buffer.clear()

    for ln in lines:
        line = ln.strip()
        if not line:
            continue
        match = q_start_pattern.match(line)
        if match:
            flush()
            current_title = f"第{match.group(1)}题"
            current_buffer.append(line)
        elif current_title:
            current_buffer.append(line)
            
    flush()

    counts = {"correct": 0, "wrong": 0, "blank": 0, "unknown": 0, "partial": 0}
    for b in blocks:
        counts[b["status"]] += 1

    return counts, blocks


def _manual_status_for_detail(status: object) -> str:
    value = str(status or "ungraded").strip().lower()
    if value == "correct":
        return "correct"
    if value in ("wrong", "partial"):
        return "wrong"
    if value == "unanswered":
        return "blank"
    return "unknown"


def _parse_manual_result_to_counts(text: str) -> tuple[dict, list[dict]]:
    """Normalize manual answer-slot decisions to the smart-detail block shape."""
    try:
        payload = json.loads(str(text or "{}"))
    except (TypeError, ValueError):
        payload = {}
    if not isinstance(payload, dict) or payload.get("type") != "manual_analyze":
        return {"correct": 0, "wrong": 0, "blank": 0, "unknown": 0}, []

    grouped: dict[str, list[dict]] = {}
    for position, block in enumerate(payload.get("blocks") or [], start=1):
        if not isinstance(block, dict):
            continue
        try:
            question_no = max(1, int(block.get("index") or position))
        except (TypeError, ValueError):
            question_no = position
        title = f"第{question_no}题"
        grouped.setdefault(title, []).append(
            {
                "content": str(block.get("title") or ""),
                "status": _manual_status_for_detail(block.get("status")),
            }
        )

    blocks: list[dict] = []
    counts = {"correct": 0, "wrong": 0, "blank": 0, "unknown": 0}
    for title, sub_items in grouped.items():
        statuses = [str(item.get("status") or "unknown") for item in sub_items]
        if not statuses or "unknown" in statuses:
            status = "unknown"
        elif "wrong" in statuses:
            status = "wrong"
        elif all(item == "blank" for item in statuses):
            status = "blank"
        elif "blank" in statuses:
            status = "wrong"
        else:
            status = "correct"
        counts[status] += 1
        blocks.append(
            {
                "title": title,
                "content": "\n".join(item["content"] for item in sub_items if item["content"]),
                "status": status,
                "subItems": sub_items,
            }
        )
    return counts, blocks


def _parse_history_result_to_counts(info: dict, history_engine: str) -> tuple[dict, list[dict]]:
    text = str(info.get("result") or "") if isinstance(info, dict) else ""
    if history_engine == "manual":
        return _parse_manual_result_to_counts(text)
    return _parse_ai_result_to_counts(text)


def _extract_ai_scoring_titles(text: str) -> list[str]:
    """从智能模型批改结果中提取可统分的题目键。"""
    _, blocks = _parse_ai_result_to_counts(text or "")
    titles: list[str] = []
    seen: set[str] = set()
    for b in blocks:
        title = str(b.get("title") or "").strip()
        if not title or title == "总览":
            continue
        sub_items = b.get("subItems") or []
        if isinstance(sub_items, list) and len(sub_items) > 1:
            for idx, _ in enumerate(sub_items, start=1):
                key = f"{title}-作答区{idx}"
                if key not in seen:
                    titles.append(key)
                    seen.add(key)
        else:
            if title not in seen:
                titles.append(title)
                seen.add(title)
    return titles


def _question_title_sort_key(title: str) -> tuple:
    """自然排序键：按题号里的数字排序，无数字时退回原字符串。"""
    m = re.search(r"(\d+)", str(title or ""))
    return (int(m.group(1)) if m else 0, str(title or ""))


def _detect_missing_questions(history: dict, history_engine: str) -> dict[str, dict]:
    """跨卷一致性检测：找出比同文件夹其它卷少批题目的试卷（按页比较）。

    同一页内，某题号出现在超过半数试卷中即视为「应批题目」；某卷缺了其中某题即漏批。
    仅智能批改（ref）有意义；manual 返回空；单张卷无从比较，跳过。

    返回 {filename: {"page_no": int, "missing": [题号...], "expected_count": int, "actual_count": int}}。
    """
    if history_engine == "manual":
        return {}
    completed = history.get("completed") if isinstance(history.get("completed"), dict) else {}
    if len(completed) < 2:
        return {}

    page_paper_sets: dict[int, dict[str, set[str]]] = {}
    page_paper_count: dict[int, int] = {}
    for filename, info in completed.items():
        if not isinstance(info, dict):
            continue
        result_text = str(info.get("result") or "").strip()
        if not result_text or result_text.startswith("{"):
            continue
        page_no = _paper_box_page_no(filename)
        _, blocks = _parse_history_result_to_counts(info, history_engine)
        titles: set[str] = set()
        for b in blocks:
            title = str(b.get("title") or "").strip()
            if title and title != "总览":
                titles.add(title)
        if not titles:
            continue
        page_paper_sets.setdefault(page_no, {})[str(filename)] = titles
        page_paper_count[page_no] = page_paper_count.get(page_no, 0) + 1

    result: dict[str, dict] = {}
    for page_no, paper_sets in page_paper_sets.items():
        n = page_paper_count.get(page_no, 0)
        if n < 2:
            continue
        freq: dict[str, int] = {}
        for titles in paper_sets.values():
            for t in titles:
                freq[t] = freq.get(t, 0) + 1
        # 严格过半数的卷都出现该题才视为「应批」；少数卷缺失即漏批（避免单卷异常题号误报）
        expected = {t for t, c in freq.items() if c * 2 > n}
        for filename, titles in paper_sets.items():
            missing = sorted(
                (t for t in expected if t not in titles),
                key=_question_title_sort_key,
            )
            if missing:
                result[filename] = {
                    "page_no": page_no,
                    "missing": missing,
                    "expected_count": len(expected),
                    "actual_count": len(titles),
                }
    return result


def _standard_scoring_questions(safe: str) -> list[dict]:
    """标准答题区（识别答案，老师手改过）→ 统分权威题清单（跨页全局重编号）。

    「有哪些题、多少道题」以答题区为准（2026-10-16 用户口径），不再从批改结果文本反推。
    题号口径与统分键一致：第1页第N题→第N题，第2页第N题→第(M+N)题（M=上一页最大题号）；
    批改结果文本的页内题号按 _scoring_title_offsets 同一偏移折算到本清单的键。
    """
    out: list[dict] = []
    offset = 0
    for page_no in sorted(_reference_standard_sources(safe).keys()):
        cached = read_reference_answer_table_page(safe, page_no)
        entries = [e for e in (cached.get("questions") or []) if isinstance(e, dict)]
        page_max = 0
        for entry in entries:
            try:
                display_no = int(entry.get("display_index") or 0)
            except (TypeError, ValueError):
                display_no = 0
            if display_no <= 0:
                continue
            key_no = offset + display_no
            page_max = max(page_max, key_no)
            slots = [s for s in (entry.get("slots") or []) if isinstance(s, dict)]
            answer = "\n".join(
                str(s.get("answer_text") or "").strip()
                for s in slots
                if str(s.get("answer_text") or "").strip()
            ) or str(entry.get("full_answer") or "").strip()
            out.append(
                {
                    "key": f"第{key_no}题",
                    "page_no": page_no,
                    "display_no": display_no,
                    "printed_no": str(entry.get("printed_no") or "").strip(),
                    "slot_count": len(slots),
                    "answer_preview": re.sub(r"\s+", "、", answer)[:60],
                }
            )
        if page_max:
            offset = page_max
    return out


def _scoring_title_offsets(safe: str, completed: dict) -> dict[int, int]:
    """页号 → 统分键题号偏移（跨页全局重编号：第k页第N题 → 第(offset+N)题）。

    有标准答题区时以答题区为准（与 _standard_scoring_questions 同源）；
    无则退回按批改结果文本各页最大题号累加（与老自动统分同口径）。
    """
    std = _standard_scoring_questions(safe)
    if std:
        out: dict[int, int] = {}
        for q in std:
            m = re.match(r"^第(\d+)题$", str(q.get("key") or ""))
            if m:
                out[int(q["page_no"])] = int(m.group(1)) - int(q["display_no"])
        return out
    page_texts: dict[int, str] = {}
    for item in (completed or {}).values():
        if not isinstance(item, dict):
            continue
        t = str(item.get("result") or "").strip()
        if not t or t.startswith("{"):
            continue
        p = _image_path_of_item(safe, item)
        pn = _page_no_of_filename(p.name) if (p and p.is_file()) else None
        if pn is None:
            continue
        page_texts.setdefault(pn, t)
    out: dict[int, int] = {}
    offset = 0
    for pn in sorted(page_texts):
        out[pn] = offset
        _c, blks = _parse_ai_result_to_counts(page_texts[pn])
        page_max = 0
        for b in blks:
            m = re.match(r"^第(\d+)题$", str(b.get("title") or "").strip())
            if not m:
                continue
            page_max = max(page_max, offset + int(m.group(1)))
        offset = page_max or offset
    return out


def _score_ai_result_by_config(text: str, scoring_config: dict, blank_count_map: dict = None, title_offset: int = 0) -> tuple[float, dict]:
    """按统分配置为智能模型批改结果计算每题得分和总分。

    blank_count_map（第N题 → {blanks, kind}）是视觉「重切作答区」数出的空数，优先用
    「整题满分 ÷ 空数」得干净每空分；缺失时才退回按作答区数均分。

    title_offset：统分键是跨页全局重编号（第2页第1题=第14题），批改结果文本的题号是页内号；
    查分按 offset 折算到全局键，details 仍存页内题号（前端按 blocks 对照展示）。
    """
    _, blocks = _parse_ai_result_to_counts(text or "")
    blank_count_map = blank_count_map if isinstance(blank_count_map, dict) else {}
    details: dict[str, float] = {}
    total = 0.0

    def _full_score_of(key: str) -> float:
        raw = _lookup_score(key, scoring_config)
        if raw is None:
            raw = 0
        try:
            return max(0.0, float(raw))
        except Exception:
            return 0.0

    def _score_for(status: str, full: float, ratio=None) -> float:
        if status == "correct":
            return full
        if status == "partial":
            return full * _snap_partial_ratio(ratio)
        return 0.0

    for b in blocks:
        title = str(b.get("title") or "").strip()
        if not title or title == "总览":
            continue
        # 页内题号 → 全局键（第2页第1题=第14题）；details 键保持页内题号
        lookup = title
        if title_offset:
            _m = re.match(r"^第(\d+)题$", title)
            if _m:
                lookup = f"第{title_offset + int(_m.group(1))}题"
        sub_items = b.get("subItems") or []
        full = _full_score_of(lookup)  # 题级满分（整数）
        if isinstance(sub_items, list) and len(sub_items) > 1:
            # 题级记分：整题一个满分，按各作答区正确率累计得分。
            # 优先用「重切作答区」数出的空数算出干净每空分；缺失才退回按作答区数均分。
            bcm = blank_count_map.get(lookup) or blank_count_map.get(title)
            if bcm and int(bcm.get("blanks") or 0) > 0:
                blanks = int(bcm["blanks"])
                kind = str(bcm.get("kind") or "blank")
                per = full if (kind == "choice" or blanks <= 1) else full / blanks
            else:
                per = full / len(sub_items)
            earned = 0.0
            for sub in sub_items:
                status = str((sub or {}).get("status") or "unknown")
                earned += _score_for(status, per, (sub or {}).get("partial_ratio"))
            score = round(earned, 1)
            details[title] = score
            total += score
        else:
            status = str(b.get("status") or "unknown")
            score = _score_for(status, full, b.get("partial_ratio"))
            score = round(score, 1)
            details[title] = score
            total += score

    return round(total, 1), details

@router.get("/error-book/folders/{folder_name:path}/stats")
async def api_get_error_book_folder_stats(folder_name: str):
    """
    获取某个文件夹的错题统计信息（用于错题本列表展示：参与人数、收录题目、平均错误率）
    """
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="文件夹名称不合法")
        
    # 旧数据可能同时存在两份；只统计更新时间更晚的一次批改。
    with _grading_history_lock:
        history, history_engine = _latest_grading_history(safe)
        
    completed = history.get("completed", {})

    if not completed:
        return {
            "ok": True,
            "student_count": 0,
            "question_count": 0,
            "error_rate": 0
        }

    # 读取文件夹内的文件数量，排除标准答案
    folder_dir = correct_docs_dir() / safe
    files_count = 0
    if folder_dir.is_dir():
        for entry in folder_dir.iterdir():
            if entry.is_file() and not entry.name.startswith("cls_"):
                if "标准答案" not in entry.name:
                    files_count += 1
    total_wrong_or_blank = 0
    total_parsed_questions_across_all_papers = 0
    paper_boxes = set()
    
    # 统计题目
    question_titles = set()
    for filename, info in completed.items():
        if not isinstance(info, dict):
            continue
        paper_boxes.add(_paper_box_display_name(filename))
        page_no = _paper_box_page_no(filename)
        result_text = info.get("result", "")
        if not result_text:
            continue
        counts, blocks = _parse_history_result_to_counts(info, history_engine)
        
        # 只统计大题
        # _parse_ai_result_to_counts 已经把 subItems 归拢到了主 block 下
        # 所以 blocks 的长度就是这套试卷的大题数量
        for b in blocks:
            question_titles.add((page_no, b["title"]))
            
        total_parsed_questions_across_all_papers += sum(
            1 for block in blocks if block.get("status") in ("correct", "wrong", "blank")
        )
        
        # 计算这套试卷有几道大题报错了
        # 大题为错误或未作答时都计入错误率。
        for b in blocks:
            if b["status"] in ("wrong", "blank"):
                total_wrong_or_blank += 1
        
    total_questions_collected = len(question_titles)
    
    error_rate = 0
    if total_parsed_questions_across_all_papers > 0:
        error_rate = round((total_wrong_or_blank / total_parsed_questions_across_all_papers) * 100, 1)

    student_count = len(paper_boxes) if paper_boxes else files_count

    return {
        "ok": True,
        "student_count": student_count,
        "question_count": total_questions_collected,
        "error_rate": error_rate
    }

@router.get("/error-book/folders/{folder_name:path}/detail")
async def api_get_error_book_folder_detail(folder_name: str):
    """
    获取某个文件夹详细的错题统计数据，包括题目排行和学生排行
    """
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="文件夹名称不合法")

    with _grading_history_lock:
        history, history_engine = _latest_grading_history(safe)

    # 错题本详情透出知识点：从同 class 目录 analysis JSON 读取每题知识点，缺失时降级为空映射
    try:
        from app.grading.wrong_question_db import collect_wrong_question_knowledge_points

        knowledge_map = collect_wrong_question_knowledge_points(safe)
    except Exception:
        knowledge_map = {}

    completed = history.get("completed", {})
    scoring_config = history.get("scoring_config") if isinstance(history.get("scoring_config"), dict) else {}

    # 跨卷一致性：某卷比同文件夹其它卷少批的题目（按页比较，卷框维度归并）
    missing_map = _detect_missing_questions(history, history_engine)
    box_missing: dict[str, list[str]] = {}
    for filename, m in missing_map.items():
        box = _paper_box_display_name(filename)
        bucket = box_missing.setdefault(box, [])
        for t in m.get("missing", []):
            if t not in bucket:
                bucket.append(t)
    for bucket in box_missing.values():
        bucket.sort(key=_question_title_sort_key)

    # 题目统计
    questions_stat = {}  # title -> {"correct": 0, "wrong": 0, "blank": 0}
    questions_by_page = {}
    # 学生统计
    students_by_box = {}

    def unique_sorted(items) -> list[str]:
        return sorted({str(x) for x in items if str(x).strip()}, key=lambda x: str(x))

    def ensure_question_stat(target: dict, title: str) -> dict:
        if title not in target:
            target[title] = {
                "title": title,
                "correct": 0,
                "wrong": 0,
                "blank": 0,
                "wrong_students": [],
                "subItems": {},
            }
        return target[title]
    
    for filename, info in completed.items():
        if not isinstance(info, dict):
            continue
        box_name = _paper_box_display_name(filename)
        page_no = _paper_box_page_no(filename)
        page_questions_stat = questions_by_page.setdefault(page_no, {})
        result_text = info.get("result", "")
        counts, blocks = _parse_history_result_to_counts(info, history_engine)
        
        student_wrong = counts["wrong"] + counts["blank"]
        student_correct = counts["correct"]
        wrong_titles = []
        correct_titles = []
        
        for b in blocks:
            title = b["title"]
            st = b["status"]
            q_stat = ensure_question_stat(questions_stat, title)
            page_q_stat = ensure_question_stat(page_questions_stat, title)
            
            if st == "correct":
                q_stat["correct"] += 1
                page_q_stat["correct"] += 1
                correct_titles.append(title)
            elif st == "wrong":
                q_stat["wrong"] += 1
                page_q_stat["wrong"] += 1
                wrong_titles.append(title)
                q_stat["wrong_students"].append(box_name)
                page_q_stat["wrong_students"].append(box_name)
            elif st == "blank":
                q_stat["blank"] += 1
                page_q_stat["blank"] += 1
                wrong_titles.append(title)
                q_stat["wrong_students"].append(box_name)
                page_q_stat["wrong_students"].append(box_name)

            # 统计子作答区
            sub_items = b.get("subItems", [])
            if len(sub_items) > 1: # 只有多个作答区才需要展示下拉
                for idx, sub in enumerate(sub_items):
                    sub_title = f"作答区 {idx + 1}"
                    sub_st = sub.get("status", "unknown")
                    if sub_title not in q_stat["subItems"]:
                        q_stat["subItems"][sub_title] = {
                            "title": sub_title, 
                            "correct": 0, 
                            "wrong": 0, 
                            "blank": 0,
                            "wrong_students": []
                        }
                    if sub_title not in page_q_stat["subItems"]:
                        page_q_stat["subItems"][sub_title] = {
                            "title": sub_title,
                            "correct": 0,
                            "wrong": 0,
                            "blank": 0,
                            "wrong_students": [],
                        }
                    if sub_st in ["correct", "wrong", "blank"]:
                        q_stat["subItems"][sub_title][sub_st] += 1
                        page_q_stat["subItems"][sub_title][sub_st] += 1
                    
                    # 记录学生在哪个作答区出错
                    if sub_st in ["wrong", "blank"]:
                        wrong_titles.append(f"{title}-{sub_title}")
                        q_stat["subItems"][sub_title]["wrong_students"].append(box_name)
                        page_q_stat["subItems"][sub_title]["wrong_students"].append(box_name)
                
        stat = students_by_box.setdefault(box_name, {
            "filename": box_name,
            "source_filenames": [],
            "correct_count": 0,
            "wrong_count": 0,
            "correct_questions": set(),
            "wrong_questions": set(),
            "score_total": None,
            "question_scores": {},
        })
        stat["source_filenames"].append(filename)
        stat["correct_count"] += student_correct
        stat["wrong_count"] += student_wrong
        stat["correct_questions"].update(correct_titles)
        stat["wrong_questions"].update(wrong_titles)

        score_total = info.get("score_total")
        if score_total is not None:
            try:
                score_num = float(score_total)
            except Exception:
                score_num = None
            if score_num is not None:
                stat["score_total"] = (stat["score_total"] or 0) + score_num

        question_scores = info.get("question_scores") if isinstance(info.get("question_scores"), dict) else {}
        for key, value in question_scores.items():
            try:
                num = float(value)
            except Exception:
                continue
            stat["question_scores"][str(key)] = stat["question_scores"].get(str(key), 0) + num
        
    def to_question_list(stat_map: dict) -> list[dict]:
        items = []
        for q in stat_map.values():
            q["wrong_students"] = unique_sorted(q.get("wrong_students", []))
            title = str(q.get("title") or "")
            # 知识点透出：主题取 analysis 中该题 + 各作答区的知识并集；子作答区取各自的知识点
            aggregated = list(knowledge_map.get(title, []))
            sub_items = q.get("subItems", {})
            if isinstance(sub_items, dict):
                for sub in sub_items.values():
                    sub["wrong_students"] = unique_sorted(sub.get("wrong_students", []))
                    slot_no = str(sub.get("title") or "").removeprefix("作答区 ").strip()
                    sub_points = list(knowledge_map.get(f"{title}-作答区{slot_no}", []))
                    sub["knowledge_points"] = sub_points
                    for point in sub_points:
                        if point not in aggregated:
                            aggregated.append(point)
                q["subItems"] = list(sub_items.values())
            q["knowledge_points"] = aggregated
            items.append(q)
        items.sort(key=lambda x: (x["wrong"] + x["blank"]), reverse=True)
        return items

    # 将题目统计转换为列表并排序（错的多的在前面）
    questions_list = to_question_list(questions_stat)
    question_pages = [
        {
            "page_no": page_no,
            "label": f"第 {page_no} 张",
            "questions": to_question_list(page_stat),
        }
        for page_no, page_stat in sorted(questions_by_page.items(), key=lambda x: x[0])
    ]

    students_stat = []
    for stat in students_by_box.values():
        students_stat.append({
            "filename": stat["filename"],
            "source_filenames": unique_sorted(stat.get("source_filenames", [])),
            "correct_count": stat["correct_count"],
            "wrong_count": stat["wrong_count"],
            "correct_questions": unique_sorted(stat["correct_questions"]),
            "wrong_questions": unique_sorted(stat["wrong_questions"]),
            "score_total": stat["score_total"],
            "question_scores": stat["question_scores"],
            "missing_questions": box_missing.get(stat["filename"], []),
        })
    
    # 如果已经做过统分，则按总分从高到低排序；否则按错题数从高到低排序
    if any(s.get("score_total") is not None for s in students_stat):
        students_stat.sort(
            key=lambda x: (
                -(float(x.get("score_total")) if x.get("score_total") is not None else -1.0),
                x["wrong_count"],
                str(x["filename"]),
            )
        )
    else:
        students_stat.sort(key=lambda x: x["wrong_count"], reverse=True)

    return {
        "ok": True,
        "source_engine": str(history.get("engine") or history_engine),
        "questions": questions_list,
        "question_pages": question_pages,
        "students": students_stat,
        "scoring_config": scoring_config,
        "full_score": history.get("full_score"),
        "missing_questions": missing_map,
        "inconsistent_count": len(missing_map),
    }


@router.post("/folders/{folder_name:path}/scoring-config/apply")
def api_apply_scoring_config(folder_name: str, body: Optional[dict] = Body(default=None)):
    """按统分配置为当前文件夹的智能模型批改结果批量计算分数。"""
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    body = body or {}

    with _grading_history_lock:
        data = _read_grading_history(safe)
        scoring_config = body.get("scoring_config")
        if scoring_config is not None:
            data["scoring_config"] = scoring_config
        scoring_config = data.get("scoring_config")
        if not isinstance(scoring_config, dict) or not scoring_config:
            raise HTTPException(status_code=400, detail="请先设置每个题目的分数")

        # 整卷满分：优先用前端回传的识别值；否则用各题分值之和兜底
        full_score = body.get("full_score")
        if full_score is None:
            try:
                full_score = round(sum(float(v) for v in scoring_config.values() if v is not None), 1)
            except (TypeError, ValueError):
                full_score = 0.0
        data["full_score"] = full_score
        question_structure = body.get("question_structure")
        if isinstance(question_structure, dict):
            data["question_structure"] = question_structure
        # 大题总分/题序/标题（供统分界面「大题+小题」分组展示）一并持久化
        major_scores = body.get("major_scores")
        if isinstance(major_scores, dict):
            data["major_scores"] = major_scores
        major_order = body.get("major_order")
        if isinstance(major_order, list):
            data["major_order"] = major_order
        major_titles = body.get("major_titles")
        if isinstance(major_titles, dict):
            data["major_titles"] = major_titles
        paper_subs = body.get("paper_subs")
        if isinstance(paper_subs, dict):
            data["paper_subs"] = paper_subs

        completed = data.get("completed", {})
        if not isinstance(completed, dict) or not completed:
            raise HTTPException(status_code=400, detail="当前文件夹暂无智能模型批改结果")

        # 统分键是跨页全局重编号（第2页第1题=第14题）；按页偏移折算后再查分
        title_offsets = _scoring_title_offsets(safe, completed)

        applied = 0
        question_titles: list[str] = []
        for filename, item in completed.items():
            if not isinstance(item, dict):
                continue
            result_text = str(item.get("result") or "").strip()
            if not result_text or result_text.startswith("{"):
                continue
            titles = _extract_ai_scoring_titles(result_text)
            if titles and not question_titles:
                question_titles = titles
            _p = _image_path_of_item(safe, item)
            _pn = _page_no_of_filename(_p.name) if (_p and _p.is_file()) else None
            title_offset = title_offsets.get(_pn, 0) if _pn is not None else 0
            score_total, question_scores = _score_ai_result_by_config(
                result_text, scoring_config, data.get("blank_count_map"), title_offset=title_offset
            )
            item["score_total"] = score_total
            item["question_scores"] = question_scores
            applied += 1

        _write_grading_history(safe, data)

    try:
        from app.services.ai_auto_report.triggers import schedule_smart_scoring_auto_report

        # 统分接口已在 grading 用户上下文中，同步入队更可靠（避免子线程丢失 contextvar）
        schedule_smart_scoring_auto_report(get_grading_user_id(), safe)
    except Exception as e:
        print(f"[ai_auto_report] hook after scoring apply failed: {e}")

    try:
        # 统分完成自动钉钉工作通知（user_id 在请求上下文先取值再传参，避免子线程 contextvar 丢失）
        # push_dingtalk=false（前端「手动推送」模式）时跳过
        if bool(body.get("push_dingtalk", True)):
            from app.services.dingtalk_notify import notify_grading_done

            notify_grading_done(get_grading_user_id(), safe)
    except Exception as e:
        print(f"[dingtalk_notify] hook after scoring apply failed: {e}")

    # 统分后 score_total 才齐：再触发一次自动导入学情+自动分层（客户清单 #1）
    try:
        _schedule_auto_sync_class(get_grading_user_id(), safe)
    except Exception as e:
        print(f"[auto_class_sync] hook after scoring apply failed: {e}")

    return {
        "ok": True,
        "message": f"已完成 {applied} 张试卷的一键打分",
        "applied_count": applied,
        "question_titles": question_titles,
    }


def _extract_json_from_llm(text: str) -> dict:
    """从大模型输出中提取首个 JSON 对象（容忍 markdown 代码块与前后缀说明）。"""
    s = (text or "").strip()
    s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
    s = re.sub(r"\s*```$", "", s).strip()
    start = s.find("{")
    if start == -1:
        raise ValueError("AI 返回内容不是 JSON 对象")
    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(s[start:])
    except json.JSONDecodeError:
        raise ValueError("AI 返回内容不是 JSON 对象")
    if not isinstance(obj, dict):
        raise ValueError("AI 返回内容不是 JSON 对象")
    return obj


_QUESTION_KEY_RE = re.compile(r'^第(.+?)题(?:[-_—－·\s]*作答区[-_—－·\s]*(\d+))?$')


def _question_key_identity(key: object) -> tuple[str, object] | None:
    """把题目键解析成 (题号, 作答区号) 标识，用于对 LLM 返回键做宽松匹配。"""
    m = _QUESTION_KEY_RE.match(str(key or "").strip())
    if not m:
        return None
    zone = m.group(2)
    return (m.group(1), int(zone) if zone else None)


def _fuzzy_score_lookup(key: str, score_map: dict) -> object:
    """优先精确匹配；否则按题号+作答区号宽松匹配（容忍分隔符/空格差异）。"""
    if key in score_map:
        return score_map[key]
    ident = _question_key_identity(key)
    if ident is None:
        return None
    for k, v in score_map.items():
        if _question_key_identity(k) == ident:
            return v
    return None


def _lookup_score(key: str, score_map: dict) -> object:
    """统分取值统一入口：兼容「题级映射」（{第N题: 分}）与「作答区级映射」（{第N题-作答区M: 分}）。

    视觉识别返回题级映射（同一题各作答区同分）；文本兜底返回作答区级映射。这里按
    精确 → 题号（把「第N题-作答区M」归到「第N题」）→ 宽松 依次匹配，两种格式都能命中。
    """
    if key in score_map:
        return score_map[key]
    ident = _question_key_identity(key)
    if ident is not None:
        title = f"第{ident[0]}题"
        if title in score_map:
            return score_map[title]
    return _fuzzy_score_lookup(key, score_map)


_DASHSCOPE_COMPAT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _image_path_to_data_url(path: Path) -> str:
    """试卷图片 → base64 data URL（供 qwen-vl-max 视觉调用）。"""
    try:
        from PIL import Image
    except Exception as exc:
        raise RuntimeError(f"缺少 Pillow，无法读取试卷图片: {exc}") from exc
    import base64
    import io as _io
    with Image.open(path) as source:
        image = source.convert("RGB")
        image.thumbnail((1800, 1800))
        stream = _io.BytesIO()
        image.save(stream, format="JPEG", quality=82, optimize=True)
    encoded = base64.b64encode(stream.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _image_path_of_item(safe: str, item: dict) -> Optional[Path]:
    """定位某批改项对应的试卷原图本地路径（image_original URL / 上传原图 / 目录兜底）。"""
    # 1) image_original 是下载 URL（grading/modify/{orig_name}）→ 取文件名 → modify_dir()
    img_url = str(item.get("image_original") or "")
    if img_url:
        base = img_url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
        if base:
            p = modify_dir() / base
            if p.is_file():
                return p
    # 2) 上传原图 → OCR 用图
    name = str(item.get("name") or "")
    if name:
        src = correct_docs_dir() / safe / name
        gp = _get_grading_path(safe, src)
        if gp is not None:
            return gp
        # 3) 目录内按同 stem 兜底扫描
        stem = Path(name).stem
        d = correct_docs_img_dir() / safe
        if d.is_dir():
            for f in sorted(d.iterdir()):
                if f.is_file() and f.suffix.lower() in _IMAGE_EXTS and f.stem == stem:
                    return f
    return None


def _resolve_paper_image(safe: str, completed: dict) -> Optional[Path]:
    """从批改历史里定位第一份可用于读印分的试卷原图本地路径。"""
    for item in completed.values():
        if not isinstance(item, dict):
            continue
        if not str(item.get("result") or "").strip():
            continue
        p = _image_path_of_item(safe, item)
        if p is not None:
            return p
    return None


def _page_no_of_filename(name: str) -> Optional[int]:
    """从文件名末尾提取页号（如 丁金花_2.jpg → 2）。"""
    m = re.search(r"_(\d+)\.(?:jpg|jpeg|png|webp|bmp)$", name, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except (TypeError, ValueError):
            return None
    return None


def _resolve_paper_images(safe: str, completed: dict) -> list[Path]:
    """定位试卷的所有页原图（按页号去重排序），供统分读完整卷结构。

    单页 _resolve_paper_image 只取第一张，多页卷会漏掉后面页的题目，导致统分匹配不全、
    错配。这里遍历所有已完成项，收集不同页号的原图，按页号升序返回（页号未知的排后）。
    """
    pages: dict[int, Path] = {}
    unnamed: list[Path] = []
    for item in completed.values():
        if not isinstance(item, dict):
            continue
        if not str(item.get("result") or "").strip():
            continue
        p = _image_path_of_item(safe, item)
        if p is None or not p.is_file():
            continue
        page_no = _page_no_of_filename(p.name)
        if page_no is None:
            if p not in unnamed:
                unnamed.append(p)
        else:
            pages.setdefault(page_no, p)
    ordered = [pages[k] for k in sorted(pages)]
    ordered.extend(unnamed)
    return ordered


def _vision_recognize_paper_questions(db: Session, image_path: Path) -> Optional[list]:
    """用 qwen-vl-max 识别整张试卷的所有题目（含主观题、作文），返回题目列表。

    用于补全百度 correct_edu 漏切的主观题/作文：识别卷面全部题目后，与百度已批的
    客观题对比，差额即漏切的题。返回 list[dict]，每项含 major/sub/sub_sub/title/type/score；
    失败返回 None（调用方跳过补全，不影响原批改结果）。
    """
    api_key, _model = get_qwen_config(db)
    if not api_key:
        return None
    try:
        data_url = _image_path_to_data_url(image_path)
    except Exception:
        return None

    prompt = (
        "这是一张学生试卷的扫描图。请识别卷面上的所有题目，包括大题、小题、"
        "括号数字标号（如（1）（2））、主观题和作文，不要漏掉任何一道。\n\n"
        "对每道题输出这些字段：\n"
        "- major：大题标号（严格照抄卷面印刷，如 一、二、三、四…；作文若单独占一个大题也单独列出）\n"
        "- sub：大题下的小题标号（严格照抄卷面印刷，如 1、2、3…；没有则留空字符串）\n"
        "- sub_sub：小题下的括号标号（严格照抄卷面印刷，如（1）（2）；没有则留空字符串）\n"
        "- title：该题的简短标题或内容关键词（用于定位）\n"
        "- type：题型（选择/填空/主观简答/作文/其他）\n"
        "- score：卷面括号里印的这道题分值（整数；小题若没有单独印分，把大题总分分摊到各小题，保证小题分值相加等于大题总分）\n\n"
        "注意：题号必须严格照抄卷面印刷的编号，禁止自行编造顺序号、禁止重新排序；"
        "主观题（补充句子、阅读简答）和作文最容易漏，务必识别出来；"
        "全卷所有题的 score 相加应等于卷面合计分。\n\n"
        "只输出一个 JSON 对象，不要任何解释。格式示例：\n"
        '{"questions":[{"major":"一","sub":"1","sub_sub":"","title":"读拼音写词语","type":"填空","score":7},'
        '{"major":"一","sub":"4","sub_sub":"（2）","title":"补充句子","type":"主观简答","score":4},'
        '{"major":"四","sub":"","sub_sub":"","title":"习作","type":"作文","score":30}]}'
    )
    payload = {
        "model": get_vl_model(),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": prompt},
                ],
            },
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
        "enable_thinking": False,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        response = requests.post(
            f"{_DASHSCOPE_COMPAT_URL}/chat/completions",
            json=payload,
            headers=headers,
            timeout=180,
        )
    except requests.RequestException:
        return None
    try:
        res_json = response.json()
    except ValueError:
        return None
    if response.status_code != 200 or "error" in res_json:
        return None
    content = (res_json.get("choices") or [{}])[0].get("message", {}).get("content", "")
    try:
        raw = _extract_json_from_llm(content)
    except ValueError:
        return None
    questions = raw.get("questions")
    if not isinstance(questions, list) or not questions:
        return None
    result: list[dict] = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        try:
            score = float(q.get("score"))
        except (TypeError, ValueError):
            continue
        result.append(
            {
                "major": str(q.get("major") or "").strip(),
                "sub": str(q.get("sub") or "").strip(),
                "sub_sub": str(q.get("sub_sub") or "").strip(),
                "title": str(q.get("title") or "").strip(),
                "type": str(q.get("type") or "").strip(),
                "score": max(0.0, score),
            }
        )
    if not result:
        return None
    return result


def _title_in_baidu(title: str, baidu_comments: str) -> bool:
    """题目标题与百度已批内容是否有实质重叠（用于避免重复补全主观题）。

    百度 correct_edu 常把多道阅读题揉进一个「第N题」块的多个作答区，导致同一道题
    既被百度批过、又被补全流程再补一次。用 2 字滑动窗口比对（命中 >= 2 个才判重），
    比只比前 3 字更鲁棒（如「找出像猴儿似的…」与百度批语「…猴儿似的…」能对上）。
    """
    t = re.sub(r"[^一-鿿]", "", title or "")
    if len(t) < 2:
        return False
    baidu = baidu_comments or ""
    bigrams = {t[i : i + 2] for i in range(len(t) - 1)}
    hits = sum(1 for bg in bigrams if bg in baidu)
    return hits >= 2


def _supplement_baidu_grading(
    db: Session, image_path: Path, result_text: str, blocks_with_result: list
) -> tuple[str, list]:
    """用视觉模型识别整卷题目，补全百度 correct_edu 漏切的主观题/作文（标记「未批」）。

    百度 correct_edu 对客观题（选择/填空）切分稳定，但主观题（补充句子、阅读简答）和
    作文经常漏切。这里用 qwen-vl 把整卷题目认出来，把百度没批到的主观题/作文补成
    「未批」题块，让满分识别能读全分、统分能覆盖整卷（补上的题暂记 0 分，等人工批）。
    识别失败或无漏切时原样返回。
    """
    try:
        from app.grading.paper_structure import _short_title
    except Exception:
        _short_title = None
    vision_questions = _vision_recognize_paper_questions(db, image_path)
    if not vision_questions:
        return result_text, blocks_with_result

    baidu_comments = " ".join(str(b.get("comment") or "") for b in blocks_with_result)

    supplements: list[dict] = []
    for q in vision_questions:
        qtype = str(q.get("type") or "")
        is_essay = any(k in qtype for k in ("作文", "习作", "写作"))
        is_subjective = any(k in qtype for k in ("主观", "简答", "赏析", "表达", "谈", "看法"))
        has_sub = bool(str(q.get("sub") or "").strip())
        # 只补「作文」或「有小题号的主观题」；跳过无小题号的大题头/阅读段头/指导语
        # （如「观察与梳理 11分」「阅读与鉴赏 26分」「小嘎子…阅读段」），否则会把它们当题补进统分。
        if not (is_essay or (is_subjective and has_sub)):
            continue
        title = str(q.get("title") or "")
        if title and _title_in_baidu(title, baidu_comments):
            continue
        supplements.append(q)

    if not supplements:
        return result_text, blocks_with_result

    # 现有最大题号（从 blocks 的 index，兜底从 result_text 解析）
    max_index = 0
    for b in blocks_with_result:
        try:
            max_index = max(max_index, int(b.get("index") or 0))
        except (TypeError, ValueError):
            continue
    if max_index <= 0:
        _, blocks = _parse_ai_result_to_counts(result_text)
        for b in blocks:
            ident = _question_key_identity(b.get("title"))
            if ident:
                try:
                    max_index = max(max_index, int(ident[0]))
                except (TypeError, ValueError):
                    pass

    text_lines = (result_text or "").rstrip().splitlines()
    next_index = max_index
    append_lines: list[str] = []
    for q in supplements:
        next_index += 1
        raw_title = str(q.get("title") or "").strip() or "主观题"
        title = _short_title(raw_title) if _short_title else raw_title
        score = q.get("score")
        score_text = f"{score:g}分" if isinstance(score, (int, float)) else ""
        append_lines.append(f"第{next_index}题-作答区1：未批；{title}（{score_text}）")
        blocks_with_result.append(
            {
                "baidu_original_index": next_index,
                "baidu_real_name": str(next_index),
                "index": next_index,
                "sub_index": 1,
                "is_question": True,
                "result": "未批",
                "comment": f"{title}（{score_text}）",
                "bbox": [0, 0, 0, 0],
                "baidu_correct_result": 0,
                "baidu_question_bbox": [0, 0, 0, 0],
                "baidu_is_slot": False,
                "supplemented": True,
            }
        )

    # 更新首行「总题量」计数（不影响 _parse_ai_result_to_counts，但前端会显示）
    for i, ln in enumerate(text_lines):
        if ln.startswith("总题量"):
            m = re.match(r"总题量[：:]\s*(\d+)", ln)
            if m:
                try:
                    total = int(m.group(1)) + len(supplements)
                    text_lines[i] = re.sub(r"总题量[：:]\s*\d+", f"总题量：{total}", ln)
                except (TypeError, ValueError):
                    pass
            break

    return "\n".join(text_lines + append_lines), blocks_with_result


def _vision_read_full_scores(
    db: Session, image_paths: list[Path], question_keys: list[str], descriptions: list[str]
) -> Optional[dict]:
    """识别卷面印的每题满分：整卷转录 → 正则解析 → 一致性推断 → 题目块匹配（文本）。

    多页卷会逐页识别再合并（majors 取并集、items/transcript 拼接），保证题目块能对号入座到
    整卷所有题——否则只读第一页会漏掉后面页的题目，导致匹配错配、漏分。

    失败返回 None（调用方回退文本猜分）。新流程解决三个老问题：
      - 分值印成「（X☆）」而非「（X分）」，且两栏排版 → 整页视觉吐 JSON 极易错乱；
      - 大题总分 > 小题分值之和（试卷截断/漏切）→ 用合计锚点推断缺失分值；
      - 视觉把「33☆」误读「35☆」等 → 用「大题总分 + 合计=100」交叉校正。
    """
    api_key, _model = get_qwen_config(db)
    if not api_key:
        print("[统分诊断] _vision_read_full_scores: 无 qwen api_key")
        return None
    try:
        from app.grading.paper_structure import (
            recognize_paper_structure,
            match_blocks_to_scores,
            infer_missing_sections,
            _leaf_items_for_matching,
            detect_blank_counts,
        )
    except Exception as exc:
        print(f"[统分诊断] 导入 paper_structure 失败 {exc!r}")
        return None

    paths = [p for p in (image_paths or []) if p]
    if not paths:
        print("[统分诊断] _vision_read_full_scores: 无试卷原图")
        return None

    # 逐页识别整卷结构，再合并成一份（多页卷只读第一页会漏题）。
    majors: dict = {}
    total = 0
    order: list[str] = []
    transcript_parts: list[str] = []
    items: list[dict] = []
    for image_path in paths:
        result = recognize_paper_structure(api_key, image_path)
        if not isinstance(result, dict):
            continue
        for m, s in (result.get("majors") if isinstance(result.get("majors"), dict) else {}).items():
            majors.setdefault(m, s)
        if not total:
            total = result.get("total") or 0
        if not order:
            order = result.get("order") if isinstance(result.get("order"), list) else []
        _items = result.get("items") if isinstance(result.get("items"), list) else []
        if _items:
            items.extend(_items)
        t = result.get("transcript") or ""
        if t.strip():
            transcript_parts.append(t)
    if not majors:
        print("[统分诊断] recognize_paper_structure 失败（所有页均未识别出大题）")
        return None
    transcript = "\n\n".join(transcript_parts)

    # 跨页大题归属修复：大题头在前一页、其小题在后一页时，后一页小题的 major 会被正则留空
    # （cur_major 只在同页内生效）。用「最近出现的大题」回填，保证三(二)这类跨页小题归属正确。
    _last_major = ""
    for it in items:
        m = str(it.get("major") or "").strip()
        if m:
            _last_major = m
        elif _last_major and (it.get("sub") or it.get("sub_sub")):
            it["major"] = _last_major

    # 推断整卷转录漏掉的阅读段头（（二）这类页中段头），把该段小题从上一段里拆出来。
    # 用确定性算术（大题总分 − 已知段分值 = 漏段分值），不靠视觉模型读段头（那会幻觉出「（二）26」）。
    for _ms in infer_missing_sections(majors, items):
        _mj = _ms["major"]
        _first = str(_ms["first_sub"])
        _insert_at = None
        for _i, _it in enumerate(items):
            if _it.get("major") == _mj and str(_it.get("sub") or "") == _first and not _it.get("sub_sub"):
                _insert_at = _i
                break
        if _insert_at is None:
            continue
        items.insert(_insert_at, {
            "major": _mj,
            "sub": _ms["section"],
            "sub_sub": "",
            "title": "",
            "score": _ms["score"],
        })

    # 大题 → 小题（题号 + 分值）清单，供统分界面「大题 + 小题分数框」展示（不放题干）。
    # 选择题分组（小题标题含「选择」且带 sub_sub 子项，子项是各自独立的题）要逐个列出，
    # 每个选择题一个分数框，不能塌成「选择题 16分」一坨；其余小问（如句子练习下的（1）（2））仍折叠进小题。
    # 注意：只靠「选择」关键词会误伤「在文中括号里选择恰当的汉字打√」这类无子项的题，故额外要求有 sub_sub 子项。
    _has_subsub: set[tuple] = set()
    for it in items:
        _m = str(it.get("major") or "").strip()
        _s = str(it.get("sub") or "").strip()
        if _m and _s and str(it.get("sub_sub") or "").strip():
            _has_subsub.add((_m, _s))
    choice_groups: set[tuple] = set()
    for it in items:
        _m = str(it.get("major") or "").strip()
        _s = str(it.get("sub") or "").strip()
        if (not it.get("sub_sub")) and (_m, _s) in _has_subsub and "选择" in str(it.get("title") or ""):
            choice_groups.add((_m, _s))

    paper_subs: dict[str, list[dict]] = {}
    for it in items:
        m = str(it.get("major") or "").strip()
        sub = str(it.get("sub") or "").strip()
        sub_sub = str(it.get("sub_sub") or "").strip()
        if not m or not sub:
            continue
        try:
            score = int(round(float(it.get("score") or 0)))
        except (TypeError, ValueError):
            score = 0
        if (m, sub) in choice_groups:
            # 选择题分组：只列 sub_sub（每个选择题独立一题），跳过「选择题 16分」分组头本身
            if not sub_sub:
                continue
            num = f"{sub}（{sub_sub}）"
        else:
            # 非选择题：小问仍折叠进小题
            if sub_sub:
                continue
            num = sub
            # 阅读段（（一）（二）…）的 sub 是汉字（一/二…），展示成「（一）」更贴近卷面
            if re.fullmatch(r"[一二三四五六七八九十]+", num):
                num = f"（{num}）"
        paper_subs.setdefault(m, []).append({"num": num, "score": score})

    # 合并后重算「缺失/截断」差值（大题总分 > 其下小题之和），只作展示用。
    sub_sum: dict[str, int] = {}
    for it in items:
        if it.get("sub") and not it.get("sub_sub"):
            try:
                s = int(it.get("score") or 0)
            except (TypeError, ValueError):
                s = 0
            sub_sum[it.get("major")] = sub_sum.get(it.get("major"), 0) + s
    gaps: list[dict] = []
    for m, s in majors.items():
        try:
            s_int = int(s)
        except (TypeError, ValueError):
            s_int = 0
        ss = sub_sum.get(m, 0)
        if s_int > 0 and ss > 0 and s_int > ss:
            gaps.append({"major": m, "total": s_int, "sum": ss, "gap": s_int - ss})

    # 题目块描述：question_keys 与 descriptions 一一对应。descriptions 已含「第N题：关键词」，
    # 直接复用，避免再包一层「第N题：」造成重复标题。
    block_descriptions: list[str] = []
    for i, key in enumerate(question_keys):
        snip = descriptions[i] if i < len(descriptions) else ""
        block_descriptions.append(snip if snip else key)

    # 题目块 → 卷面题：直接把识别出的题目结构（items，题号+分值）当权威清单喂给 LLM 对号入座，
    # 不再用「作答区数量」这类每张卷都不同的硬编码信号。
    matched = match_blocks_to_scores(
        api_key, transcript, majors, total, order, block_descriptions, items
    ) or {}
    if not matched:
        print("[统分诊断] match_blocks_to_scores 失败")
        return None

    # 逐题块归一化：index 与 question_keys 顺序一一对应；分值强制整数（杜绝均分小数）
    scores: dict[str, float] = {}
    structure: list[dict] = []
    question_texts: dict[str, str] = {}
    for i, key in enumerate(question_keys):
        blk = matched.get(i + 1)
        if not isinstance(blk, dict):
            continue
        score = float(int(round(max(0.0, float(blk.get("score") or 0)))))
        major = str(blk.get("major") or "").strip()
        # 前端用 sub 生成卷面题号标签：优先小问号（（1）（2）），其次小题号（1/2/3），都没有（整大题）用大题号（二）。
        # 关键：题号必须按原卷来——是 1 就是 1，是（1）就是（1），不要再用「第N题/第一大题」重排。
        sub = str(blk.get("sub_sub") or blk.get("sub") or blk.get("major") or "").strip()
        title = str(blk.get("title") or "").strip()
        display = f"{major}、{sub} {title}".strip() if (sub or title) else major
        scores[key] = score
        structure.append(
            {
                "index": i + 1,
                "major": major,
                "sub": sub,
                "title": title,
                "display": display,
                "score": score,
                "question_text": title,
            }
        )
        if title:
            question_texts[key] = title

    if not scores:
        print("[统分诊断] _vision_read_full_scores: 未匹配到任何题块")
        return None

    # 大题总分（整卷真实满分锚点）；full_score 用大题之和，保证即使百度只切到部分客观题，
    # 整卷满分仍等于卷面合计（如 100），不被切到的题漏算。
    major_scores: dict[str, float] = {m: float(s) for m, s in majors.items()}
    full_score = int(round(sum(major_scores.values()))) if major_scores else int(round(sum(scores.values())))
    print(
        f"[统分诊断] majors={major_scores} gaps={gaps} 匹配块数={len(scores)}/{len(question_keys)} full_score={full_score}"
    )

    # 重切作答区：视觉数空（填空每个括号/横线一空、选择 1 空、主观 1 空），
    # 供「整题满分 ÷ 空数 = 每空分」算出干净的 0.5/1 分值（替代百度 slot 少算导致的 0.4/0.6）。
    # blank_count_map 以「第N题」为键（与 scoring_config/_lookup_score 口径一致），值含 blanks + kind。
    blank_count_map: dict[str, dict] = {}
    try:
        leaves = _leaf_items_for_matching(items)
        blank_map = detect_blank_counts(api_key, paths, leaves, transcript)
        for _idx, _m in matched.items():
            if not isinstance(_m, dict):
                continue
            _bm = blank_map.get((_m.get("major"), _m.get("sub"), _m.get("sub_sub"), _m.get("score")))
            if _bm and isinstance(_bm, dict) and int(_bm.get("blanks") or 0) > 0:
                try:
                    _ki = int(_idx)
                except (TypeError, ValueError):
                    _ki = 0
                # 键必须与 question_keys 同名（答题区路径题号可能跳号，位置号≠题号）
                _bkey = question_keys[_ki - 1] if 1 <= _ki <= len(question_keys) else f"第{_idx}题"
                blank_count_map[_bkey] = {
                    "blanks": int(_bm["blanks"]),
                    "kind": str(_bm.get("kind") or "blank"),
                }
    except Exception as exc:
        print(f"[统分诊断] 作答区数空失败（回退均分） {exc!r}")

    return {
        "full_score": full_score,
        "scores": scores,
        "major_scores": major_scores,
        "structure": structure,
        "question_texts": question_texts,
        "gaps": gaps,
        "items": items,
        "order": order,
        "paper_subs": paper_subs,
        "blank_count_map": blank_count_map,
    }


def _attach_scores_to_blocks(
    db: Session, image_path: Path, result_text: str, blocks_with_result: list
) -> list:
    """批改留痕前视觉读整卷每题满分，给每个批改题块算出得分写入 block["score"]。

    得分规则（科大讯飞式卷面留痕）：对 = 满分；半对 = 满分 × 比例（默认一半）；
    错 / 未作答 / 未批 = 0。读分失败或读不到该题分值则不改动该题块（仍只打对错）。
    """
    if not blocks_with_result or image_path is None:
        return blocks_with_result

    _counts, parsed = _parse_ai_result_to_counts(result_text or "")
    question_keys: list[str] = []
    descriptions: list[str] = []
    for b in parsed:
        title = str(b.get("title") or "").strip()
        if not title or title == "总览":
            continue
        snippet = str(b.get("content") or "").strip()
        snippet = re.sub(r"第\d+题-作答区\d+[:：](?:对|错|半对|部分对|未作答)?[；;]?", "", snippet)
        snippet = re.sub(r"\s+", " ", snippet).strip()[:100]
        question_keys.append(title)
        descriptions.append(f"{title}：{snippet}")
    if not question_keys:
        return blocks_with_result

    vision_map = _vision_read_full_scores(db, [image_path], question_keys, descriptions)
    if not isinstance(vision_map, dict):
        return blocks_with_result
    scores = vision_map.get("scores")
    if not isinstance(scores, dict) or not scores:
        return blocks_with_result
    blank_count_map = vision_map.get("blank_count_map")
    if not isinstance(blank_count_map, dict):
        blank_count_map = {}

    # 大题总分均分到该题下的每个空/小问：先按题号分组。
    # 优先用「重切作答区」数出的空数（整题满分 ÷ 空数 = 每空分，干净 0.5/1）；
    # 数空失败才退回按「题下作答区块数」均分（旧逻辑，可能出 0.4/0.6 小数）。
    groups: dict[int, list] = {}
    for blk in blocks_with_result:
        try:
            idx = int(blk.get("index"))
        except (TypeError, ValueError):
            continue
        groups.setdefault(idx, []).append(blk)

    for idx, blks in groups.items():
        raw_full = _lookup_score(f"第{idx}题", scores)
        if raw_full is None:
            continue
        try:
            full = float(raw_full)
        except (TypeError, ValueError):
            continue
        bcm = blank_count_map.get(f"第{idx}题")
        if bcm and int(bcm.get("blanks") or 0) > 0:
            blanks = int(bcm["blanks"])
            kind = str(bcm.get("kind") or "blank")
            per = full if (kind == "choice" or blanks <= 1) else full / blanks
        else:
            n = len(blks)
            if n <= 0:
                continue
            per = full / n  # 卷面印的是整题总分，均分到每个空
        for blk in blks:
            result = str(blk.get("result") or "")
            if result == "对":
                score = per
            elif result == "半对":
                score = per * _snap_partial_ratio(blk.get("partial_ratio"))
            else:
                score = 0.0
            blk["score"] = round(score, 1)
            blk["full_score"] = round(per, 1)
    return blocks_with_result


@router.post("/folders/{folder_name:path}/scoring-config/auto")
def api_auto_scoring_config(
    folder_name: str, db: Session = Depends(get_db)
):
    """AI 识别试卷印的每题满分，返回给前端确认后应用。

    题清单优先取标准答题区（识别答案，老师手改过——「有哪些题、多少道题」以它为准），
    分值从标准试卷卷面读；没传标准答案的旧文件夹才退回从批改结果文本反推。
    VL 读分是分钟级重活：def 进线程池 + heavy_slot 排队，别堵事件循环（整站假死教训）。
    """
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")

    from app.services.heavy_budget import heavy_slot

    with heavy_slot("scoring-auto"):
        # ── 题清单：标准答题区优先（2026-10-16：统分按识别答案那套题来） ──
        std_questions = _standard_scoring_questions(safe)
        if std_questions:
            question_keys = [q["key"] for q in std_questions]
            title_keys = list(question_keys)
            descriptions = [
                (
                    f'{q["key"]}：印刷题号「{q["printed_no"] or "?"}」；'
                    f'{q["slot_count"]}个作答区；标准答案：{q["answer_preview"]}'
                )
                for q in std_questions
            ]
            paper_images = [
                grading_path
                for _page_no, (_src, grading_path) in sorted(_reference_standard_sources(safe).items())
            ]
        else:
            with _grading_history_lock:
                data = _read_grading_history(safe)
                completed = data.get("completed", {})
                if not isinstance(completed, dict) or not completed:
                    raise HTTPException(status_code=400, detail="当前文件夹暂无智能模型批改结果")

                # 多页卷：按页号收集整卷各页的批改结果文本（不再只取第一份，避免漏掉后面页的题），
                # 并按页累加题号全局重编号（第1页第N题→第N题，第2页第N题→第(M+N)题，M=上一页最大题号），
                # 保证跨页题号唯一，与统分界面/课堂讲评的全局题号口径一致。
                page_results: list[tuple[int, str]] = []
                for _filename, item in completed.items():
                    if not isinstance(item, dict):
                        continue
                    t = str(item.get("result") or "").strip()
                    if not t or t.startswith("{"):
                        continue
                    _p = _image_path_of_item(safe, item)
                    _pn = _page_no_of_filename(_p.name) if (_p and _p.is_file()) else None
                    if _pn is None:
                        continue
                    if any(pn == _pn for pn, _ in page_results):
                        continue
                    page_results.append((_pn, t))
                page_results.sort(key=lambda x: x[0])

                blocks: list[dict] = []
                offset = 0
                for _pn, t in page_results:
                    _c, _blks = _parse_ai_result_to_counts(t)
                    _page_max = 0
                    for _b in _blks:
                        _m = re.match(r"^第(\d+)题$", str(_b.get("title") or "").strip())
                        if not _m:
                            continue
                        _new_no = offset + int(_m.group(1))
                        _b["title"] = f"第{_new_no}题"
                        _page_max = max(_page_max, _new_no)
                    offset = _page_max or offset
                    blocks.extend(_blks)
                if not blocks:
                    raise HTTPException(status_code=400, detail="未识别到可统分的题目")
                # 过滤「空白答题区」块：百度会把作文格/方格等纯印刷空白区切成题，
                # 内容形如「仅见印刷…无任何新增笔迹」，不是题目，不应进入统分。
                blocks = [
                    b
                    for b in blocks
                    if not (
                        re.search(r"仅见印刷", str(b.get("content") or ""))
                        and re.search(r"无任何新增", str(b.get("content") or ""))
                    )
                ]
                question_keys = []
                descriptions = []
                for b in blocks:
                    title = str(b.get("title") or "").strip()
                    if not title or title == "总览":
                        continue
                    snippet = str(b.get("content") or "").strip()
                    # 去掉「第N题-作答区M：对/错；」前缀，只留作答理由关键词，避免题号/空数干扰读分
                    snippet = re.sub(r"第\d+题-作答区\d+[:：](?:对|错|半对|部分对|未作答)?[；;]?", "", snippet)
                    snippet = re.sub(r"\s+", " ", snippet).strip()[:100]
                    # 题级键：一道题一个分值，不再拆到作答区
                    question_keys.append(title)
                    descriptions.append(f"{title}：{snippet}")
                # 题级键（去重的「第N题」顺序），与视觉识别的 structure index 一一对应
                title_keys = []
                _seen_titles: set[str] = set()
                for b in blocks:
                    t = str(b.get("title") or "").strip()
                    if not t or t == "总览" or t in _seen_titles:
                        continue
                    _seen_titles.add(t)
                    title_keys.append(t)

                if not question_keys:
                    raise HTTPException(status_code=400, detail="未识别到可统分的题目")

            # ── 视觉识别优先：读卷面印的每题满分；失败则回退文本大模型按题型猜分 ──
            # 多页卷要读全部页（读全卷题目结构再匹配），否则只读第一页会漏题、错配。
            paper_images = _resolve_paper_images(safe, completed)

        print(f"[统分诊断] safe={safe!r} std={bool(std_questions)} paper_images={paper_images!r} question_keys={question_keys!r}")
        vision_map = (
            _vision_read_full_scores(db, paper_images, question_keys, descriptions)
            if paper_images
            else None
        )
        print(f"[统分诊断] vision_map={'None' if not isinstance(vision_map, dict) else ('ok, keys=' + str(list(vision_map.keys())))}")
    vision_full_score = None
    vision_scores = None
    vision_major_scores = None
    vision_structure = None
    vision_items = None
    vision_order = None
    if isinstance(vision_map, dict):
        vision_full_score = vision_map.get("full_score")
        vision_scores = vision_map.get("scores") if isinstance(vision_map.get("scores"), dict) else None
        vision_major_scores = (
            vision_map.get("major_scores")
            if isinstance(vision_map.get("major_scores"), dict)
            else None
        )
        vision_structure = vision_map.get("structure")
        vision_items = vision_map.get("items") if isinstance(vision_map.get("items"), list) else None
        vision_order = vision_map.get("order") if isinstance(vision_map.get("order"), list) else None
        vision_paper_subs = (
            vision_map.get("paper_subs")
            if isinstance(vision_map.get("paper_subs"), dict)
            else None
        )
        vision_blank_count_map = (
            vision_map.get("blank_count_map")
            if isinstance(vision_map.get("blank_count_map"), dict)
            else None
        )

    # 大题标题（一、积累与运用…）：从 items 里的大题头（sub 为空、带 title）提取，供前端「一、积累与运用 33」展示
    major_titles: dict[str, str] = {}
    if vision_items:
        for it in vision_items:
            if not isinstance(it, dict):
                continue
            m = str(it.get("major") or "").strip()
            sub = str(it.get("sub") or "").strip()
            title = str(it.get("title") or "").strip()
            if m and not sub and title and m not in major_titles:
                major_titles[m] = title
    vision_usable = bool(vision_scores) and any(
        _lookup_score(k, vision_scores) is not None for k in question_keys
    )

    # 卷面题号层级结构：视觉识别返回的 structure（index 与 title_keys 顺序对应）→ {第N题: {major, sub, display}}
    # 题干全文从 vision_items 按 (major, sub, sub_sub) 查回（items 的 title 是完整题干），
    # 让「课堂讲评」点开每题能直接展示原题，比 VLM 错题分析里的 question_text 更全、更稳。
    item_text_map: dict[tuple, str] = {}
    if vision_items:
        for _it in vision_items:
            if not isinstance(_it, dict):
                continue
            _tt = str(_it.get("title") or "").strip()
            if not _tt:
                continue
            _tk = (
                str(_it.get("major") or "").strip(),
                str(_it.get("sub") or "").strip(),
                str(_it.get("sub_sub") or "").strip(),
            )
            item_text_map.setdefault(_tk, _tt)
    question_structure: dict[str, dict] = {}
    if isinstance(vision_structure, list):
        for s in vision_structure:
            if not isinstance(s, dict):
                continue
            try:
                idx = int(s.get("index"))
            except (TypeError, ValueError):
                idx = 0
            if 1 <= idx <= len(title_keys):
                title = title_keys[idx - 1]
                _m = str(s.get("major") or "").strip()
                _sub = str(s.get("sub") or "").strip()
                _ss = str(s.get("sub_sub") or "").strip()
                _full = item_text_map.get((_m, _sub, _ss), "") or str(s.get("title") or "").strip()
                question_structure[title] = {
                    "major": _m,
                    "sub": _sub,
                    "sub_sub": _ss,
                    "display": str(s.get("display") or "").strip(),
                    "question_text": _full,
                }
    if not question_structure:
        question_structure = {}
    if std_questions:
        # 标准答题区路径：每道题（含未匹配上的）都补一条结构；印刷题号带上（界面行标签优先显示卷面题号）
        for q in std_questions:
            _s = question_structure.setdefault(
                q["key"],
                {"major": "", "sub": "", "sub_sub": "", "display": "", "question_text": ""},
            )
            if q["printed_no"]:
                _s["printed_no"] = q["printed_no"]

    # 逐题准确分值优先：新识别管线已把每个题目块映射到卷面小问并读准分值（整数），
    # 直接按题落分即可（不再均分大题总分，从根上避免「7分被均成3分」这类错误）。
    # 只有逐题分没覆盖全时才退回「大题总分均分」兜底。
    per_block_ready = bool(vision_scores) and all(
        _lookup_score(k, vision_scores) is not None for k in question_keys
    )
    major_usable = (not per_block_ready) and bool(vision_major_scores) and bool(question_structure)
    if per_block_ready:
        score_map = vision_scores
    elif major_usable:
        score_map = {}
    else:
        # 卷面读不到任何分值：不再用文本大模型按题型猜分（会「自作主张加分」），
        # 直接提示老师手动填写分值。
        raise HTTPException(
            status_code=400,
            detail="未能从卷面识别到分值，请手动为每道题填写分值",
        )

    # 只保留合法题目键，分值归一化为非负数（保留一位小数）。
    # 视觉识别返回「大题总分」（major_scores，键为「一」「二」…）+ 每个题目块所属大题（structure）。
    # 大题总分 = 该大题下所有小题分值之和，只能算一次。这里把大题总分均分到该大题下的每个作答区
    # （余数归最后一个），保证求和 == 大题总分，从根上避免「大题总分 + 小题分值」重复叠加。
    normalized: dict[str, float] = {}
    missing: list[str] = []

    # 大题总分模式：视觉读到大题总分且识别出题目块归属时优先走这条，不再按「第N题」读小题分。
    if major_usable:
        zones_by_major: dict[str, list[str]] = {}
        for key in question_keys:
            ident = _question_key_identity(key)
            title = f"第{ident[0]}题" if ident else key
            major = (question_structure.get(title) or {}).get("major") or title
            zones_by_major.setdefault(major, []).append(key)
        for major, zone_keys in zones_by_major.items():
            raw = vision_major_scores.get(major)
            if raw is None:
                # 宽松匹配：忽略首尾空格差异
                for mk, mv in vision_major_scores.items():
                    if str(mk).strip() == str(major).strip():
                        raw = mv
                        break
            if raw is None:
                missing.extend(zone_keys)
                for k in zone_keys:
                    normalized[k] = 0.0
                continue
            try:
                total = max(0.0, float(raw))
            except (TypeError, ValueError):
                total = 0.0
            n = len(zone_keys)
            total_int = int(round(total))
            if n <= 1:
                normalized[zone_keys[0]] = float(total_int)
            else:
                # 整数均分：余数分给末尾几题，保证每个分值都是整数且求和 == 大题总分（杜绝 0.5/7.5 小数）
                base = total_int // n
                rem = total_int - base * n
                for i, k in enumerate(zone_keys):
                    normalized[k] = float(base + (1 if i >= n - rem else 0))
    else:
        # 题级归一化：视觉/文本兜底都返回题级分值，直接按题级落分，不再均分到作答区
        # （避免「3 分 6 空 = 0.5 分/空」这类小数，满分按卷面印的整数题级分值走）
        for key in question_keys:
            raw = _lookup_score(key, score_map)
            if raw is None:
                missing.append(key)
                normalized[key] = 0.0
            else:
                try:
                    normalized[key] = float(int(round(max(0.0, float(raw)))))
                except (TypeError, ValueError):
                    normalized[key] = 0.0

    # 若 AI 返回的键完全对不上题目键，宁可报错提示重试，也不要静默地全给 0
    if missing and len(missing) == len(question_keys):
        raise HTTPException(
            status_code=500,
            detail=f"AI 返回的分值键与题目不一致（{len(missing)}/{len(question_keys)} 项未匹配），请重试",
        )

    # 整卷满分：vision_full_score 现为「各大题总分之和」（经合计锚点交叉校正，可靠），
    # 直接用；它是整卷真实满分，不受「百度只切到部分客观题」影响（如整卷 100，客观题块只切到 44，
    # full_score 仍是 100，缺的主观题/作文由补全流程或老师手动补齐）。
    computed_total = round(sum(normalized.values()), 1)
    if major_usable:
        full_score = computed_total
    else:
        try:
            _vf = float(vision_full_score) if vision_full_score is not None else None
        except (TypeError, ValueError):
            _vf = None
        if _vf is not None and _vf > 0:
            full_score = round(_vf, 1)
        else:
            full_score = computed_total

    print(
        f"[统分调试] safe={safe!r} vision_full_score={vision_full_score!r} "
        f"vision_major_scores={vision_major_scores!r} computed_total={computed_total} "
        f"final_full_score={full_score} major_usable={major_usable}"
    )

    # 统分结构持久化：空数（第N题→{blanks,kind}）、题号层级（第N题→major/sub/题干全文）、
    # 大题→小题清单等一并落库。供 apply/手动修正算「整题满分÷空数=干净每空分」，
    # 也供「课堂讲评」按统分题号排列、点开每题看原题。
    with _grading_history_lock:
        try:
            _d = _read_grading_history(safe)
            if vision_blank_count_map:
                _d["blank_count_map"] = vision_blank_count_map
            if question_structure:
                _d["question_structure"] = question_structure
            if std_questions:
                # 标准答题区路径：逐题行就是答题区题目本身，不再用卷面折叠小题清单
                # （折叠行的分摊对不上题，老师改了不生效）；清掉旧 paper_subs 防止界面串行。
                _d["paper_subs"] = {}
            elif vision_paper_subs:
                _d["paper_subs"] = vision_paper_subs
            if major_titles:
                _d["major_titles"] = major_titles
            if vision_major_scores:
                _d["major_scores"] = vision_major_scores
            if vision_order:
                _d["major_order"] = vision_order
            _write_grading_history(safe, _d)
        except Exception as _e:
            print(f"[统分诊断] 持久化统分结构失败 {_e!r}")

    return {
        "ok": True,
        "scoring_config": normalized,
        "question_titles": question_keys,
        "full_score": full_score,
        "question_structure": question_structure,
        # 大题总分（卷面印的权威值，一/二/三/四…）与题序，供前端按「大题+小题」分组展示。
        # 题序缺失时退回 major_scores 的键序（Python dict 保序），保证一/二/三/四大题全部显示。
        "major_scores": vision_major_scores or {},
        "major_order": vision_order or list((vision_major_scores or {}).keys()),
        "major_titles": major_titles,
        # 大题 → 小题清单：老路径给卷面折叠小题；标准答题区路径给空（逐题分数框直接绑 scoring_config）
        "paper_subs": {} if std_questions else (vision_paper_subs or {}),
        # 第N题 → {blanks, kind}（供前端透传回 save/apply，保障下次应用仍用干净每空分）
        "blank_count_map": vision_blank_count_map or {},
    }


_MANUAL_SLOT_STATUSES = {"ungraded", "correct", "wrong", "unanswered", "partial"}


def _normalize_deduction_items(raw) -> Optional[dict]:
    """结构化扣分项归一：{「第N题」/「第N题-作答区M」: [{label, points}, ...]}。

    - key 与统分键同规则（block.title / 第N题 / 第N题-作答区M），空 key 丢弃；
    - 每项强制 label:str、points:float>=0（扣分记正数）；垃圾条目丢弃；
    - 空列表保留（表示该题清空扣分项）；
    - raw=None → None（本次不改）；非 dict → {}（整体清空，防脏写）。
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    for key, items in raw.items():
        k = str(key or "").strip()
        if not k:
            continue
        if not isinstance(items, list):
            continue
        cleaned: list = []
        for it in items:
            if not isinstance(it, dict):
                continue
            label = str(it.get("label") or "").strip()
            try:
                points = float(it.get("points"))
            except (TypeError, ValueError):
                continue
            if points < 0:
                points = abs(points)
            if not label and points == 0:
                continue
            cleaned.append({"label": label, "points": round(points, 2)})
        out[k] = cleaned
    return out


def _apply_manual_annotations_to_trace(
    annotated_name: Optional[str],
    marks_only_filename: Optional[str],
    blocks: list,
    question_notes: Optional[dict],
    paper_note: Optional[str],
) -> None:
    """在 manual 留痕图（annotated_* / marks_only_*）上补画老师批注与整卷总评。"""
    question_notes = question_notes if isinstance(question_notes, dict) else {}
    paper_note = str(paper_note or "").strip()
    if not question_notes and not paper_note:
        return
    from app.grading.pipeline import draw_manual_annotations
    from PIL import Image, ImageDraw
    for fname in (annotated_name, marks_only_filename):
        if not fname:
            continue
        path = modify_dir() / str(fname)
        if not path.is_file():
            continue
        img = Image.open(str(path)).convert("RGB")
        draw = ImageDraw.Draw(img)
        w, h = img.size
        draw_manual_annotations(draw, w, h, blocks, question_notes, paper_note)
        img.save(str(path), quality=95)


def _variant_notes_from_item(item: dict) -> tuple:
    """取老师的逐题批注/整卷总评：智能卷在 item 顶层，手动卷在 result JSON 里。"""
    qn = item.get("question_notes")
    pn = str(item.get("paper_note") or "").strip()
    if isinstance(qn, dict) or pn:
        return qn if isinstance(qn, dict) else {}, pn
    try:
        res_json = json.loads(item.get("result") or "{}")
        if isinstance(res_json, dict):
            qn2 = res_json.get("question_notes")
            return (
                qn2 if isinstance(qn2, dict) else {},
                str(res_json.get("paper_note") or "").strip(),
            )
    except Exception:
        pass
    return {}, ""


def _annotated_name_from_item(item: dict) -> str:
    """解析 item 的卷面留痕文件名：image_annotated URL 取末段；退回按 marks 名换前缀。"""
    url = str(item.get("image_annotated") or "")
    name = url.split("?", 1)[0].rsplit("/", 1)[-1].strip()
    if name and _safe_annotated_filename(name):
        return name
    marks_name = str(item.get("marks_only_filename") or "").strip()
    if marks_name and _safe_marks_only_filename(marks_name):
        cand = "annotated_" + marks_name[len("marks_only_"):]
        if _safe_annotated_filename(cand):
            return cand
    return ""


def _wrong_annotation_variant_fields(item: dict) -> dict:
    """批注保存/生成响应里带给前端的变体图四个字段（URL 重签下载票）。"""
    return {
        "marks_with_wrong_notes_filename": item.get("marks_with_wrong_notes_filename"),
        "image_marks_with_wrong_notes": _re_sign_history_image_url(
            item.get("image_marks_with_wrong_notes")
        ),
        "annotated_with_wrong_notes_filename": item.get("annotated_with_wrong_notes_filename"),
        "image_annotated_with_wrong_notes": _re_sign_history_image_url(
            item.get("image_annotated_with_wrong_notes")
        ),
    }


def _regenerate_wrong_annotation_marks(
    safe: str,
    item: dict,
    blocks: list,
    wrong_annotations,
    question_notes: Optional[dict] = None,
    paper_note: Optional[str] = None,
) -> None:
    """按 wrong_annotations 生成/清除两个变体图，就地写 item 四个字段。

    - 打印变体 marks_only_{stem}_wa.jpg：从 marks_only 白底留痕派生（打印/导出用）。
    - 预览变体 annotated_{stem}_wa.jpg：从 annotated 卷面留痕派生（屏幕预览直接显示）。
    - 原图只烧老师批注，错因只进变体；wrong_annotations 为空 → 删变体文件并清字段。
    - 调用方负责随后持久化 item。
    """
    from app.grading.pipeline import draw_wrong_annotations_variant
    from app.grading.wrong_annotations import normalize_wrong_annotations

    wrong = normalize_wrong_annotations(wrong_annotations)
    marks_name = str(item.get("marks_only_filename") or "").strip()
    ann_name = _annotated_name_from_item(item)
    if question_notes is None or paper_note is None:
        qn_fallback, pn_fallback = _variant_notes_from_item(item)
        question_notes = question_notes if question_notes is not None else qn_fallback
        paper_note = paper_note if paper_note is not None else pn_fallback

    def _rebuild(src_name: str, name_key: str, url_key: str, validator, *, paper_mode: bool) -> None:
        old_variant = str(item.get(name_key) or "").strip()

        def _clear() -> None:
            if old_variant and validator(old_variant):
                try:
                    (modify_dir() / old_variant).unlink(missing_ok=True)
                except OSError:
                    pass
            item.pop(name_key, None)
            item.pop(url_key, None)

        if not wrong or not src_name or not validator(src_name):
            _clear()
            return
        src = modify_dir() / src_name
        if not src.is_file():
            _clear()
            return
        variant_name = f"{Path(src_name).stem}_wa.jpg"
        out_path = modify_dir() / variant_name
        ok = draw_wrong_annotations_variant(
            str(src),
            str(out_path),
            blocks or [],
            wrong,
            question_notes if isinstance(question_notes, dict) else {},
            str(paper_note or ""),
            paper_mode=paper_mode,
        )
        if not ok:
            _clear()
            return
        if old_variant and old_variant != variant_name and validator(old_variant):
            try:
                (modify_dir() / old_variant).unlink(missing_ok=True)
            except OSError:
                pass
        item[name_key] = variant_name
        item[url_key] = build_download_url(
            f"grading/modify/{variant_name}", get_grading_user_id()
        )

    _rebuild(
        marks_name,
        "marks_with_wrong_notes_filename",
        "image_marks_with_wrong_notes",
        _safe_marks_only_filename,
        paper_mode=False,
    )
    _rebuild(
        ann_name,
        "annotated_with_wrong_notes_filename",
        "image_annotated_with_wrong_notes",
        _safe_annotated_filename,
        paper_mode=True,
    )


def _save_manual_slot_decisions(
    safe: str,
    filename: str,
    item: dict,
    res_json: dict,
    decisions: dict,
    *,
    generate_marks: bool,
    question_notes: Optional[dict] = None,
    paper_note: Optional[str] = None,
    wrong_annotations: Optional[dict] = None,
    deduction_items: Optional[dict] = None,
) -> dict:
    blocks = res_json.get("blocks") if isinstance(res_json.get("blocks"), list) else []
    normalized_decisions: dict[str, dict] = {}
    scores: dict[str, float] = {}
    question_scores: dict[str, float] = {}
    marks: list[dict] = []
    completed_count = 0
    score_total = 0.0
    max_score_total = 0.0
    # 改分/改等第进台账：只记「已批过再改」；首次批改（prev=ungraded）不进
    _status_to_result = {
        "correct": "对",
        "wrong": "错",
        "unanswered": "未作答",
        "partial": "半对",
    }
    _regrade_ledger_rows: list = []

    def _as_float(v):
        try:
            return None if v is None or str(v).strip() == "" else float(v)
        except (TypeError, ValueError):
            return None

    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        slot_id = str(block.get("slot_id") or f"slot-{index + 1}")
        title = str(block.get("title") or f"作答区{index + 1}")
        try:
            max_score = round(float(block.get("max_score") or 0), 2)
        except (TypeError, ValueError):
            max_score = 0.0
        if max_score <= 0:
            raise HTTPException(status_code=400, detail=f"{title} 的分数上限无效，请重新保存切题规则")
        max_score_total += max_score

        _prev_status = str(block.get("status") or "ungraded").strip().lower()
        _prev_score = block.get("score")
        incoming = decisions.get(slot_id)
        if not isinstance(incoming, dict):
            incoming = {
                "status": block.get("status") or "ungraded",
                "score": block.get("score"),
            }
        status = str(incoming.get("status") or "ungraded").strip().lower()
        if status not in _MANUAL_SLOT_STATUSES:
            raise HTTPException(status_code=400, detail=f"{title} 的批改状态无效")
        score: Optional[float]
        if status == "correct":
            score = max_score
        elif status in ("wrong", "unanswered"):
            score = 0.0
        elif status == "partial":
            try:
                score = round(float(incoming.get("score")), 2)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"请填写 {title} 的半对得分")
            if score < 0 or score > max_score:
                raise HTTPException(status_code=400, detail=f"{title} 的得分必须在 0 到 {max_score:g} 之间")
        else:
            score = None

        # 已批过再改才进台账（状态/分数任一变）；同一路径只记这一处
        if _prev_status != "ungraded" and (
            _prev_status != status or _as_float(_prev_score) != _as_float(score)
        ):
            _regrade_ledger_rows.append(
                {
                    "index": block.get("index") if block.get("index") is not None else title,
                    "sub_index": block.get("sub_index"),
                    "source": "human_ai_correct",
                    "was_result": _status_to_result.get(_prev_status),
                    "new_result": _status_to_result.get(status),
                    "was_comment": None,
                    "new_comment": None,
                    "was_score": _as_float(_prev_score),
                    "new_score": _as_float(score),
                    "subject_family": block.get("subject_family"),
                }
            )

        block["slot_id"] = slot_id
        block["title"] = title
        block["max_score"] = max_score
        block["status"] = status
        block["score"] = score
        normalized_decisions[slot_id] = {"status": status, "score": score, "max_score": max_score}
        if status != "ungraded":
            completed_count += 1
            value = float(score or 0)
            score_total += value
            scores[title] = value
            question_scores[title] = value
            mark_result = {
                "correct": "对",
                "wrong": "错",
                "unanswered": "未作答",
                "partial": "半对",
            }[status]
            marks.append({"is_question": True, "bbox": block.get("bbox"), "result": mark_result})

    all_completed = bool(blocks) and completed_count == len(blocks)
    res_json["version"] = 2
    res_json["manual_status"] = "graded" if all_completed else "ungraded"
    res_json["blocks"] = blocks
    res_json["decisions"] = normalized_decisions
    res_json["scores"] = scores
    res_json["score_total"] = round(score_total, 2)
    res_json["max_score_total"] = round(max_score_total, 2)
    # 老师批注/整卷总评：与 wrong_annotations/deduction_items 同语义——
    # 带了才覆盖（空 map/空串=显式清空），None=本次不改（旧分数保存口不带这两个字段，
    # 不能顺手清掉已有批注）；正文对照前后值进台账（见下方 diff_note_rows）。
    _prev_qn = res_json.get("question_notes")
    _prev_pn = res_json.get("paper_note")
    _prev_wa = item.get("wrong_annotations")
    if isinstance(question_notes, dict):
        res_json["question_notes"] = question_notes
    else:
        res_json.setdefault("question_notes", {})
    if paper_note is not None:
        res_json["paper_note"] = str(paper_note or "").strip()
    else:
        res_json.setdefault("paper_note", "")
    _eff_qn = res_json.get("question_notes") if isinstance(res_json.get("question_notes"), dict) else {}
    _eff_pn = str(res_json.get("paper_note") or "").strip()
    item["result"] = json.dumps(res_json, ensure_ascii=False)
    item["score_total"] = round(score_total, 2) if all_completed else None
    item["question_scores"] = question_scores if all_completed else {}
    if wrong_annotations is not None:
        # 判错原因批注：item 级统一存（四引擎一致）；None 表示本次未带，保持原值
        item["wrong_annotations"] = wrong_annotations
    if deduction_items is not None:
        # 结构化扣分项：整体覆盖保存（res_json + item 双写，前端直读 item）；None 表示本次不改
        res_json["deduction_items"] = deduction_items
        item["deduction_items"] = deduction_items
        item["result"] = json.dumps(res_json, ensure_ascii=False)

    if generate_marks:
        _delete_modify_file_by_url(item.get("image_annotated"))
        _delete_modify_file_by_url(item.get("image_marks_only"))
        source_path = correct_docs_dir() / safe / filename
        grading_path = _get_grading_path(safe, source_path)
        if grading_path is None:
            grading_path = _ensure_img_in_folder(source_path, safe) or source_path
        file_stem = f"manual_{safe}_{Path(filename).stem}"
        _original_name, annotated_name = draw_real_marks_and_save(
            str(grading_path), marks, str(modify_dir()), file_stem,
            score_total=round(score_total, 2), manual_style=True,
        )
        marks_only_filename = draw_marks_only_and_save(
            str(grading_path), marks, str(modify_dir()), file_stem,
            score_total=round(score_total, 2), manual_style=True,
        )
        _apply_manual_annotations_to_trace(
            annotated_name, marks_only_filename, blocks, _eff_qn, _eff_pn
        )
        _m_uid = get_grading_user_id()
        item["image_annotated"] = build_download_url(f"grading/modify/{annotated_name}", _m_uid)
        item["image_marks_only"] = build_download_url(f"grading/modify/{marks_only_filename}", _m_uid)
        item["marks_only_filename"] = marks_only_filename

    # 判错批注打印变体：marks 重画或批注变更都需重建（wrong_annotations 为空会清掉变体）
    _regenerate_wrong_annotation_marks(
        safe, item, blocks, item.get("wrong_annotations"), _eff_qn, _eff_pn
    )

    _persist_grading_success(safe, item, "manual")
    with _grading_history_lock:
        data = _read_grading_history(safe, "manual")
        data["full_score"] = round(max_score_total, 2)
        _write_grading_history(safe, data, "manual")
    # 批注类增删改进台账（老师批注/整卷总评/判错批注，was→new 文本对照）；
    # 与改分/改等第共用下面这一次 record_corrections（同一保存路径只记一遍）
    try:
        from app.grading.correction_ledger import diff_note_rows

        _note_before = {"question_notes": _prev_qn, "paper_note": _prev_pn}
        _note_after = {"question_notes": _eff_qn, "paper_note": _eff_pn}
        if wrong_annotations is not None:
            _note_before["wrong_annotations"] = _prev_wa
            _note_after["wrong_annotations"] = wrong_annotations
        _regrade_ledger_rows += diff_note_rows(_note_before, _note_after)
    except Exception:
        pass
    # 改分/改等第台账（旁路静默；同一保存路径只记这一处，勿与 scores 分支重复）
    if _regrade_ledger_rows:
        try:
            from app.grading.correction_ledger import record_corrections

            record_corrections(
                get_grading_user_id(), safe, str(filename), "manual", _regrade_ledger_rows
            )
        except Exception:
            pass
    _schedule_response_log_write(
        get_grading_user_id(), safe, str(filename), "manual", blocks
    )
    _schedule_wrong_annotation_generation(
        get_grading_user_id(), safe, str(filename), "manual", blocks
    )
    return item


def _maybe_notify_manual_all_done(safe: str, allow: bool = True) -> None:
    """答题卡（自主阅卷）全部阅完后自动推一次钉钉（最后一张 graded 时触发，标志位去重）。

    allow=False（前端「手动推送」模式）：直接跳过且不消费去重标志，
    之后手动点「推送钉钉」或切回自动模式仍能正常触发。
    """
    if not allow:
        return
    try:
        with _grading_history_lock:
            data = _read_grading_history(safe, "manual")
            if data.get("dingtalk_notified"):
                return
            completed = data.get("completed") if isinstance(data.get("completed"), dict) else {}
            if not completed:
                return
            if not all(
                isinstance(info, dict) and info.get("score_total") is not None
                for info in completed.values()
            ):
                return
            data["dingtalk_notified"] = True
            _write_grading_history(safe, data, "manual")
        from app.services.dingtalk_notify import notify_grading_done

        notify_grading_done(get_grading_user_id(), safe, "manual")
    except Exception as e:
        print(f"[dingtalk_notify] manual all-done check failed safe={safe!r}: {e}")


@router.post("/folders/{folder_name:path}/manual-grade")
async def api_save_manual_grade(folder_name: str, request: Request):
    """保存答题卡（自主阅卷）的打分并生成留痕图"""
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    
    try:
        body = await request.json()
    except Exception:
        body = {}
        
    filename = body.get("filename")
    scores = body.get("scores")
    decisions = body.get("decisions")
    generate_marks = body.get("generate_marks", True) # 新增参数，指示是否需要生成图片
    # 老师批注/整卷总评：与 wrong_annotations 同语义——body 带了才覆盖（空=显式清空），
    # 缺省/None=本次不改（旧分数保存口不带这两个字段，不能顺手清掉已有批注）
    question_notes = body.get("question_notes")
    if question_notes is not None and not isinstance(question_notes, dict):
        question_notes = {}
    paper_note = body.get("paper_note")
    paper_note = str(paper_note or "").strip() if paper_note is not None else None
    # 判错原因批注（item 级，与 question_notes 平级）；缺省 None 表示本次不改
    from app.grading.wrong_annotations import normalize_wrong_annotations

    wrong_annotations = (
        normalize_wrong_annotations(body.get("wrong_annotations"))
        if "wrong_annotations" in body
        else None
    )
    # 结构化扣分项：key=统分键「第N题」「第N题-作答区M」；缺省 None 表示本次不改
    deduction_items = (
        _normalize_deduction_items(body.get("deduction_items"))
        if "deduction_items" in body
        else None
    )

    if not filename or (not isinstance(scores, dict) and not isinstance(decisions, dict)):
        raise HTTPException(status_code=400, detail="参数缺失")
        
    with _grading_history_lock:
        data = _read_grading_history(safe, "manual")
        
    completed = data.get("completed", {})
    item = completed.get(filename)
    
    if not item or "manual_analyze" not in str(item.get("result", "")):
        raise HTTPException(status_code=404, detail="未找到自主阅卷切题记录")

    if isinstance(decisions, dict):
        try:
            res_json = json.loads(item["result"])
            saved_item = _save_manual_slot_decisions(
                safe,
                str(filename),
                item,
                res_json,
                decisions,
                generate_marks=bool(generate_marks),
                question_notes=question_notes,
                paper_note=paper_note,
                wrong_annotations=wrong_annotations,
                deduction_items=deduction_items,
            )
            _maybe_notify_manual_all_done(
                safe, allow=bool(body.get("push_dingtalk", True))
            )
            return {"ok": True, "message": "批改结果已保存", "item": saved_item}
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        
    try:
        # 更新 JSON 中的分数记录
        res_json = json.loads(item["result"])
        # 纯调分进台账：只记「改分」不记首次打分（prev 空表 → diff 空行）
        from app.grading.correction_ledger import diff_note_rows, diff_score_map_rows

        _prev_scores = res_json.get("scores") if isinstance(res_json.get("scores"), dict) else {}
        _score_ledger_rows = diff_score_map_rows(_prev_scores, scores or {})
        # 批注类增删改也进台账（老师批注/总评）；body 缺省不改不记，与纯调分共用一次写入
        _prev_qn = res_json.get("question_notes")
        _prev_pn = res_json.get("paper_note")
        _eff_qn = question_notes if question_notes is not None else _prev_qn
        _eff_pn = paper_note if paper_note is not None else _prev_pn
        _score_ledger_rows += diff_note_rows(
            {"question_notes": _prev_qn, "paper_note": _prev_pn},
            {"question_notes": _eff_qn, "paper_note": _eff_pn},
        )
        if _score_ledger_rows:
            try:
                from app.grading.correction_ledger import record_corrections

                record_corrections(
                    get_grading_user_id(), safe, str(filename), "manual", _score_ledger_rows
                )
            except Exception:
                pass
        res_json["scores"] = scores
        res_json["manual_status"] = "graded" if generate_marks else res_json.get("manual_status", "analyzed")
        if question_notes is not None:
            res_json["question_notes"] = question_notes
        else:
            res_json.setdefault("question_notes", {})
        if paper_note is not None:
            res_json["paper_note"] = paper_note
        else:
            res_json.setdefault("paper_note", "")
        if deduction_items is not None:
            # 结构化扣分项：整体覆盖保存（与 decisions 路径同语义）；None 表示本次不改
            res_json["deduction_items"] = deduction_items
            item["deduction_items"] = deduction_items
        # 可选：如果需要在前端直接显示总分，可以把计算好的总分存进去
        item["result"] = json.dumps(res_json, ensure_ascii=False)
        
        # 如果不需要生成图片（仅静默保存分数），则直接持久化并返回
        if not generate_marks:
            _persist_grading_success(safe, item, "manual")
            return {"ok": True, "message": "分数已自动保存", "item": item}
        
        _delete_modify_file_by_url(item.get("image_annotated"))
        _delete_modify_file_by_url(item.get("image_marks_only"))
        item["image_annotated"] = ""
        item["image_marks_only"] = ""
        item["marks_only_filename"] = ""

        # 获取原始切片信息用于生成留痕图
        blocks = res_json.get("blocks", [])
        
        # 准备生成留痕图的数据结构
        blocks_with_result = []
        for b in blocks:
            title = f"第{b['index']}题" + (f"-作答区{b['sub_index']}" if b.get('is_sub') else "")
            score = scores.get(title)
            
            # 在这里判断对错（可以根据是否有分数，或者分数是否满分来判断，这里为了简单演示，只要有分且 > 0 就打钩，0 分打叉）
            # 注意：实际场景中答题卡（自主阅卷）主要是打分，打勾打叉取决于老师是否扣了分。这里仅作示例
            is_correct = False
            if score is not None:
                try:
                    s_val = float(score)
                    is_correct = s_val > 0 # 这里可以结合 scoring_config 判断是否满分
                except:
                    pass
                    
            if score is not None:
                blocks_with_result.append({
                    "is_question": True,
                    "bbox": b["bbox"],
                    "result": "对" if is_correct else "错",
                    "score": score, # 传递 score 给留痕渲染函数
                })
        
        # 调用画图逻辑
        from app.grading.pipeline import draw_real_marks_and_save, draw_marks_only_and_save
        file_stem = f"ref_{safe}_{Path(filename).stem}"
        orig_name, ann_name = draw_real_marks_and_save(
            str(correct_docs_dir() / safe / filename), blocks_with_result, str(modify_dir()), file_stem
        )
        marks_only_filename = draw_marks_only_and_save(
            str(correct_docs_dir() / safe / filename), blocks_with_result, str(modify_dir()), file_stem
        )
        _apply_manual_annotations_to_trace(
            ann_name, marks_only_filename, blocks, _eff_qn, _eff_pn
        )

        _m2_uid = get_grading_user_id()
        item["image_annotated"] = build_download_url(f"grading/modify/{ann_name}", _m2_uid)
        item["image_marks_only"] = build_download_url(f"grading/modify/{marks_only_filename}", _m2_uid)
        item["marks_only_filename"] = marks_only_filename
        _regenerate_wrong_annotation_marks(
            safe, item, blocks, item.get("wrong_annotations"), _eff_qn, _eff_pn
        )

        _persist_grading_success(safe, item, "manual")
        
        return {"ok": True, "message": "保存并生成留痕成功", "item": item}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _ai_block_score_key(blk: dict) -> str:
    """把智能批改 block 映射到统分键（与 _extract_ai_scoring_titles 口径一致）。"""
    idx = blk.get("index")
    sub = blk.get("sub_index")
    if blk.get("baidu_is_slot") and sub:
        return f"第{idx}题-作答区{sub}"
    return f"第{idx}题"


def _recompute_ai_correct_scores(stored_blocks: list, scoring_config: dict, prev_question_scores: dict, blank_count_map: dict = None) -> tuple[float, dict]:
    """按修正后的 blocks 重算每题得分与总分：手动 score 覆盖 > 统分配置按对错 > 沿用旧分。

    scoring_config 现为题级（{第N题: 分}）；作答区级 block（baidu_is_slot）把题级满分均分到该题各作答区。
    blank_count_map（第N题 → {blanks, kind}）是视觉「重切作答区」数出的空数，优先用「整题满分 ÷ 空数」
    得出干净每空分；缺失时才退回按该题作答区块数均分。
    """
    scoring_config = scoring_config if isinstance(scoring_config, dict) else {}
    prev = prev_question_scores if isinstance(prev_question_scores, dict) else {}
    blank_count_map = blank_count_map if isinstance(blank_count_map, dict) else {}

    # 统计每题作答区 block 数，用于把题级满分均分到作答区
    slot_count_by_index: dict = {}
    for blk in stored_blocks:
        if blk.get("baidu_is_slot") and blk.get("sub_index"):
            idx = blk.get("index")
            slot_count_by_index[idx] = slot_count_by_index.get(idx, 0) + 1

    question_scores: dict = {}
    total = 0.0
    for blk in stored_blocks:
        key = _ai_block_score_key(blk)
        manual = blk.get("score")
        if manual is not None and str(manual).strip() != "":
            try:
                val = round(float(manual), 1)
            except (TypeError, ValueError):
                val = 0.0
        else:
            # 题级满分：优先按题号查，兼容旧作答区级键
            full = _lookup_score(f"第{blk.get('index')}题", scoring_config)
            if full is None:
                full = _lookup_score(key, scoring_config)
            if full is None:
                try:
                    val = float(prev.get(key) or 0)
                except (TypeError, ValueError):
                    val = 0.0
            else:
                try:
                    full = max(0.0, float(full))
                except (TypeError, ValueError):
                    full = 0.0
                if blk.get("baidu_is_slot") and blk.get("sub_index"):
                    bcm = blank_count_map.get(f"第{blk.get('index')}题")
                    if bcm and int(bcm.get("blanks") or 0) > 0:
                        blanks = int(bcm["blanks"])
                        kind = str(bcm.get("kind") or "blank")
                        full = full if (kind == "choice" or blanks <= 1) else full / blanks
                    else:
                        n = slot_count_by_index.get(blk.get("index"), 1)
                        full = full / n if n else 0.0
                result = blk.get("result")
                if result == "对":
                    val = full
                elif result == "半对":
                    val = full * _snap_partial_ratio(blk.get("partial_ratio"))
                else:
                    val = 0.0
        question_scores[key] = round(val, 1)
        total += val
    return round(total, 1), question_scores


@router.post("/folders/{folder_name:path}/ai-correct")
async def api_ai_correct(folder_name: str, request: Request):
    """老师手动修正「智能批改」（baidu/smart_ref）逐题对错/得分/文案，重画留痕并更新摘要。

    body: { filename, engine, blocks }；blocks 为编辑后的完整逐题结果列表，
    每项含 index / sub_index / result（对|错|未作答），可选 comment（文案）与 score（得分）。
    """
    from app.grading.baidu_grading import _summarize_result

    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    try:
        body = await request.json()
    except Exception:
        body = {}
    filename = str(body.get("filename") or "").strip()
    engine = str(body.get("engine") or "").strip()
    new_blocks = body.get("blocks")
    if not filename or not _safe_file_filename(filename):
        raise HTTPException(status_code=400, detail="文件名无效")
    if engine not in ("baidu", "smart_ref", "aliyun"):
        raise HTTPException(status_code=400, detail="仅支持智能批改（baidu/smart_ref）与参照答案批改（aliyun）手动修正")
    if not isinstance(new_blocks, list):
        raise HTTPException(status_code=400, detail="缺少 blocks")

    with _grading_history_lock:
        data = _read_grading_history(safe, engine)
    item = (data.get("completed") or {}).get(filename)
    if not isinstance(item, dict):
        raise HTTPException(status_code=404, detail="未找到该试卷的智能批改记录")
    stored_blocks = item.get("blocks") or []
    baidu_raw = item.get("baidu_raw") or {}
    if not stored_blocks:
        raise HTTPException(status_code=409, detail="该试卷缺少可手动修正的逐题数据，请重新批改")
    if engine in ("baidu", "smart_ref") and (not isinstance(baidu_raw, dict) or not baidu_raw):
        raise HTTPException(status_code=409, detail="该试卷缺少可手动修正的逐题数据，请重新批改")

    # 前端回传的逐题变更：按 (index, sub_index) 对齐到存储 blocks
    result_map: dict = {}
    comment_map: dict = {}
    score_map: dict = {}
    partial_ratio_map: dict = {}
    for b in new_blocks:
        if not isinstance(b, dict):
            continue
        key = (b.get("index"), b.get("sub_index"))
        res = str(b.get("result") or "").strip()
        if res in ("对", "错", "未作答", "半对"):
            result_map[key] = res
        if "partial_ratio" in b:
            raw_ratio = b.get("partial_ratio")
            if raw_ratio is None or str(raw_ratio).strip() == "":
                partial_ratio_map[key] = None
            else:
                try:
                    partial_ratio_map[key] = min(1.0, max(0.0, float(raw_ratio)))
                except (TypeError, ValueError):
                    pass  # 非法比例忽略，保持原值
        if "comment" in b:
            comment_map[key] = str(b.get("comment") or "").strip()
        if "score" in b:
            raw_score = b.get("score")
            if raw_score is None or str(raw_score).strip() == "":
                score_map[key] = None
            else:
                try:
                    score_map[key] = round(float(raw_score), 1)
                except (TypeError, ValueError):
                    pass  # 非法分值忽略，保持原值
    # 老师手动批注：每道题一句（question_notes，key=题号）+ 整卷总评（paper_note）
    question_notes = body.get("question_notes")
    question_notes = question_notes if isinstance(question_notes, dict) else {}
    paper_note = str(body.get("paper_note") or "").strip()
    # 判错原因批注：整体覆盖保存（edited/manual 条目由前端带全量，重生成在各自端点内保护）
    from app.grading.wrong_annotations import normalize_wrong_annotations

    wrong_annotations_in = normalize_wrong_annotations(body.get("wrong_annotations"))
    # 结构化扣分项：与 wrong_annotations 同语义——body 带了就整体覆盖，没带则保留原值
    deduction_items_in = (
        _normalize_deduction_items(body.get("deduction_items"))
        if "deduction_items" in body
        else None
    )
    if not result_map:
        raise HTTPException(status_code=400, detail="未提供有效的对错修正")

    # B1 修正对照：先快照原判四字段，就地覆盖后 diff 出真实变更（全无变化不写任何东西）
    from app.grading.correction_ledger import _diff_ai_correct_blocks, snapshot_ai_correct_fields

    _before_result_snapshot = snapshot_ai_correct_fields(stored_blocks)

    for blk in stored_blocks:
        key = (blk.get("index"), blk.get("sub_index"))
        if key in result_map:
            res = result_map[key]
            blk["result"] = res
            blk["baidu_correct_result"] = {"对": 1, "错": 2, "未作答": 3, "半对": 4}[res]
            if res != "半对":
                blk["partial_ratio"] = None
        if key in partial_ratio_map and blk.get("result") == "半对":
            blk["partial_ratio"] = partial_ratio_map[key]
        if key in comment_map:
            blk["comment"] = comment_map[key]
        if blk.get("result") == "未作答":
            blk["comment"] = ""
        if key in score_map:
            if score_map[key] is None:
                blk.pop("score", None)
            else:
                blk["score"] = score_map[key]

    # B1 修正对照：diff → (ledger_rows, changed_blocks)；变更块盖 ai_original_result /
    # corrected_by / status 三键（人工终态随 blocks 进 history / response_logs）
    _ledger_rows, _changed_blocks = _diff_ai_correct_blocks(_before_result_snapshot, stored_blocks)
    # 批注类字段对照：老师批注/试卷总评/判错批注 的增删改也进台账（同一次保存只记这一处）。
    # wrong_annotations 仅 body 带了才覆盖（缺省不改），故只在带了时参与对照。
    from app.grading.correction_ledger import diff_note_rows

    _note_before = {
        "question_notes": item.get("question_notes"),
        "paper_note": item.get("paper_note"),
    }
    _note_after = {"question_notes": question_notes, "paper_note": paper_note}
    if "wrong_annotations" in body:
        _note_before["wrong_annotations"] = item.get("wrong_annotations")
        _note_after["wrong_annotations"] = wrong_annotations_in
    _ledger_rows += diff_note_rows(_note_before, _note_after)

    if engine in ("baidu", "smart_ref"):
        result_text = _summarize_result(baidu_raw, stored_blocks)
    else:
        result_text = item.get("result") or ""

    # 仅当有统分配置、已有历史分数或老师手动改了分时，才重算总分/每题得分；
    # 否则保持原样，避免「只改对错」时把 score_total 意外清零。
    scoring_config = data.get("scoring_config") or {}
    prev_question_scores = item.get("question_scores") or {}
    has_manual_score = any((blk.get("score") is not None and str(blk.get("score")).strip() != "") for blk in stored_blocks)
    score_total = None
    question_scores = None
    if scoring_config or prev_question_scores or has_manual_score:
        score_total, question_scores = _recompute_ai_correct_scores(
            stored_blocks, scoring_config, prev_question_scores, data.get("blank_count_map")
        )

    # 重新推导批改用原图并重画留痕（file_stem 与原批改一致，直接覆盖原图）
    student_orig_path = correct_docs_dir() / safe / filename
    mark_src = _get_grading_path(safe, student_orig_path)
    if mark_src is None:
        mark_src = _ensure_img_in_folder(student_orig_path, safe) or student_orig_path
    mark_src = str(mark_src)
    if not os.path.isfile(mark_src):
        raise HTTPException(status_code=404, detail=f"批改用原图不存在: {filename}")
    file_stem = f"ref_{safe}_{student_orig_path.stem}"
    mark_scale = 0.90 if engine == "baidu" else 1.0
    try:
        if engine == "aliyun":
            _orig_name, ann_name, marks_only_filename = draw_reference_vlm_marks_and_save(
                mark_src,
                stored_blocks,
                str(modify_dir()),
                file_stem,
                check_cross_scale=0.9,
                question_notes=question_notes,
                paper_note=paper_note,
            )
        else:
            _orig_name, ann_name, marks_only_filename = draw_baidu_marks_and_save(
                mark_src,
                stored_blocks,
                baidu_raw,
                str(modify_dir()),
                file_stem,
                check_cross_scale=mark_scale,
                question_notes=question_notes,
                paper_note=paper_note,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"留痕重绘失败: {e}")

    _uid = get_grading_user_id()
    # B3 修正回流 + 复核记账：台账记 was→new 对照；变更块以 engine="manual" 回流
    # response_logs（行归属人工动作）。只记真实变更，原样保存不写任何东西。
    if _ledger_rows:
        try:
            from app.grading.correction_ledger import record_corrections

            record_corrections(_uid, safe, filename, engine, _ledger_rows)
        except Exception:
            pass
    if _changed_blocks:
        _schedule_response_log_write(_uid, safe, filename, "manual", _changed_blocks)
        # C3 判分缓存：人工终态最高优先（可覆盖 ai 行；幻觉被老师推翻后正应进缓存飞轮）。
        # 无文本身份的块（baidu/smart_ref）由 cache_key 红线自动跳过。
        try:
            from app.grading.response_log_db import _read_folder_meta
            from app.grading.verdict_cache import store_blocks

            store_blocks(_changed_blocks, (_read_folder_meta(safe) or {}).get("subject"), engine, "human")
        except Exception:
            pass
    updated = dict(item)
    updated["blocks"] = stored_blocks
    if engine in ("baidu", "smart_ref"):
        updated["baidu_raw"] = baidu_raw
    updated["engine"] = engine
    updated["result"] = result_text
    updated["question_notes"] = question_notes
    updated["paper_note"] = paper_note
    if "wrong_annotations" in body:
        updated["wrong_annotations"] = wrong_annotations_in
    if deduction_items_in is not None:
        # 结构化扣分项：整体覆盖保存；None（body 未带）保持原值
        updated["deduction_items"] = deduction_items_in
    if score_total is not None:
        updated["score_total"] = score_total
    if question_scores is not None:
        updated["question_scores"] = question_scores
    updated["image_annotated"] = build_download_url(f"grading/modify/{ann_name}", _uid)
    updated["image_marks_only"] = build_download_url(f"grading/modify/{marks_only_filename}", _uid)
    updated["marks_only_filename"] = marks_only_filename
    # 判错批注打印变体随修正后的 wrong_annotations 重建（没带该字段则沿用旧批注）
    _regenerate_wrong_annotation_marks(
        safe, updated, stored_blocks, updated.get("wrong_annotations"), question_notes, paper_note
    )

    with _grading_history_lock:
        data = _read_grading_history(safe, engine)
        data["completed"][filename] = {k: v for k, v in updated.items() if k != "index"}
        _write_grading_history(safe, data, engine)

    # 改分落盘 → 自动导入学情+自动分层（成绩变了，分层跟着变；客户清单 #1）
    try:
        _schedule_auto_sync_class(get_grading_user_id(), safe)
    except Exception:
        pass

    view = {k: v for k, v in updated.items() if k != "baidu_raw"}
    return {"ok": True, "message": "批改结果已修正", "item": _resign_history_images(view)}


@router.post("/folders/{folder_name:path}/wrong-annotation/generate")
async def api_generate_wrong_annotation(folder_name: str, request: Request):
    """为判错/半对的题重新生成「为什么错」批注（老师点「重新生成」按钮）。

    body: { filename, engine, question_key? }；带 question_key 只重生成该题（老师明确要求，
    覆盖旧稿）；不带则整卷补齐错题批注（edited/manual 条目不覆盖）。同步返回完整 wrong_annotations。
    """
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    try:
        body = await request.json()
    except Exception:
        body = {}
    filename = str(body.get("filename") or "").strip()
    engine = str(body.get("engine") or "").strip()
    question_key = str(body.get("question_key") or "").strip()
    if not filename or not _safe_file_filename(filename):
        raise HTTPException(status_code=400, detail="文件名无效")
    if engine not in ("baidu", "smart_ref", "aliyun", "manual"):
        raise HTTPException(status_code=400, detail="engine 无效")

    with _grading_history_lock:
        data = _read_grading_history(safe, engine)
        item = (data.get("completed") or {}).get(filename)
    if not isinstance(item, dict):
        raise HTTPException(status_code=404, detail="未找到该试卷的批改记录")

    # 手动卷 blocks 在 result JSON 字符串里，智能卷在 item["blocks"]
    blocks = item.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        try:
            res_json = json.loads(item.get("result") or "{}")
            blocks = res_json.get("blocks") if isinstance(res_json.get("blocks"), list) else []
        except Exception:
            blocks = []
    if not blocks:
        raise HTTPException(status_code=409, detail="该试卷缺少逐题数据，无法生成批注")

    source_path = correct_docs_dir() / safe / filename
    grading_path = _get_grading_path(safe, source_path)
    if grading_path is None:
        grading_path = _ensure_img_in_folder(source_path, safe) or source_path
    source_image_path = str(grading_path) if grading_path and os.path.isfile(str(grading_path)) else ""

    from app.grading.wrong_annotations import (
        collect_wrong_question_groups,
        generate_wrong_annotations_for_blocks,
        normalize_wrong_annotations,
    )

    existing = normalize_wrong_annotations(item.get("wrong_annotations"))
    if question_key:
        # 老师明确点名重生成：只跑该题，覆盖旧稿（不论是否 edited）
        groups = collect_wrong_question_groups(blocks)
        if question_key not in groups:
            raise HTTPException(status_code=404, detail="该题不是错/半对，无需生成错因批注")
        generated = generate_wrong_annotations_for_blocks(
            blocks,
            source_image_path=source_image_path,
            existing={},  # 空 existing = 允许覆盖
            only_keys={question_key},
        )
    else:
        generated = generate_wrong_annotations_for_blocks(
            blocks,
            source_image_path=source_image_path,
            existing=existing,
        )
    if generated:
        existing.update(generated)
        with _grading_history_lock:
            data = _read_grading_history(safe, engine)
            item = (data.get("completed") or {}).get(filename)
            if isinstance(item, dict):
                item["wrong_annotations"] = existing
                _regenerate_wrong_annotation_marks(safe, item, blocks, existing)
                data["completed"][filename] = item
                _write_grading_history(safe, data, engine)
    return {
        "ok": True,
        "wrong_annotations": existing,
        "generated": generated,
        **(_wrong_annotation_variant_fields(item) if isinstance(item, dict) else {}),
    }


@router.post("/folders/{folder_name:path}/wrong-annotation/save")
async def api_save_wrong_annotation(folder_name: str, request: Request):
    """保存老师编辑/手写/删除后的判错批注（整体覆盖），并同步刷新打印变体图。

    body: { filename, engine, wrong_annotations }；给详情右栏轻量编辑用（不重画留痕）。
    """
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    try:
        body = await request.json()
    except Exception:
        body = {}
    filename = str(body.get("filename") or "").strip()
    engine = str(body.get("engine") or "").strip()
    if not filename or not _safe_file_filename(filename):
        raise HTTPException(status_code=400, detail="文件名无效")
    if engine not in ("baidu", "smart_ref", "aliyun", "manual"):
        raise HTTPException(status_code=400, detail="engine 无效")

    from app.grading.wrong_annotations import normalize_wrong_annotations

    wrong_annotations = normalize_wrong_annotations(body.get("wrong_annotations"))

    with _grading_history_lock:
        data = _read_grading_history(safe, engine)
        item = (data.get("completed") or {}).get(filename)
        if not isinstance(item, dict):
            raise HTTPException(status_code=404, detail="未找到该试卷的批改记录")
        blocks = item.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            try:
                res_json = json.loads(item.get("result") or "{}")
                blocks = res_json.get("blocks") if isinstance(res_json.get("blocks"), list) else []
            except Exception:
                blocks = []
        _prev_wrong_annotations = item.get("wrong_annotations")
        item["wrong_annotations"] = wrong_annotations
        _regenerate_wrong_annotation_marks(safe, item, blocks, wrong_annotations)
        data["completed"][filename] = item
        _write_grading_history(safe, data, engine)
        variant_fields = _wrong_annotation_variant_fields(item)
        # 判错批注人工编辑进台账（was→new 文本对照；AI 重生成走 generate 不记）
        try:
            from app.grading.correction_ledger import diff_note_rows, record_corrections

            _wa_rows = diff_note_rows(
                {"wrong_annotations": _prev_wrong_annotations},
                {"wrong_annotations": wrong_annotations},
            )
            if _wa_rows:
                record_corrections(get_grading_user_id(), safe, filename, engine, _wa_rows)
        except Exception:
            pass
    return {"ok": True, "wrong_annotations": wrong_annotations, **variant_fields}


@router.post("/folders/{folder_name:path}/ai-paper-summary")
async def api_ai_paper_summary(folder_name: str, request: Request, db: Session = Depends(get_db)):
    """用文本大模型为整张试卷生成一段「整卷总评」（供编辑批改里老师选用 AI 总评）。"""
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    try:
        body = await request.json()
    except Exception:
        body = {}
    filename = str(body.get("filename") or "").strip()
    engine = str(body.get("engine") or "").strip()
    if not filename or not _safe_file_filename(filename):
        raise HTTPException(status_code=400, detail="文件名无效")
    if engine not in ("baidu", "smart_ref", "aliyun"):
        raise HTTPException(status_code=400, detail="仅支持智能批改/参照答案批改")

    with _grading_history_lock:
        data = _read_grading_history(safe, engine)
    item = (data.get("completed") or {}).get(filename)
    if not isinstance(item, dict):
        raise HTTPException(status_code=404, detail="未找到该试卷的批改记录")
    blocks = item.get("blocks") or []
    if not isinstance(blocks, list) or not blocks:
        raise HTTPException(status_code=400, detail="该试卷无逐题结果")

    lines: list[str] = []
    for blk in blocks:
        if not isinstance(blk, dict):
            continue
        res = str(blk.get("result") or "").strip()
        comment = str(blk.get("comment") or "").strip()
        idx = blk.get("index")
        sub = blk.get("sub_index")
        label = f"第{idx}题" + (f"-作答区{sub}" if sub is not None else "")
        lines.append(f"{label}：{res}" + (f"，评语：{comment}" if comment else ""))
    detail = "\n".join(lines).strip()
    if not detail:
        raise HTTPException(status_code=400, detail="该试卷无逐题结果")

    prompt = (
        "你是一位资深教师。下面是这张试卷的逐题批改结果，请写一段 2～4 句话的「整卷总评」，"
        "概括整体完成情况、正确率与主要问题，并给出一句改进建议。"
        "只输出总评正文，不要编号、不要标题、不要 markdown、不要 JSON。\n\n"
        f"逐题结果：\n{detail}"
    )

    base_url, api_key, model = get_llm_config(db)
    if not api_key:
        raise HTTPException(status_code=500, detail="系统设置中未配置文本大模型 API Key，无法生成总评")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.35,
        **get_llm_thinking_extra(base_url),
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=120,
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"AI 服务请求失败: {str(e)}")
    try:
        res = resp.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="AI 服务返回非 JSON 响应")
    if resp.status_code != 200 or res.get("error"):
        msg = (res.get("error") or {}).get("message") if isinstance(res.get("error"), dict) else str(res)
        raise HTTPException(status_code=500, detail=f"AI 生成总评失败: {msg}")
    content = ((res.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    summary = str(content).strip()
    if not summary:
        raise HTTPException(status_code=500, detail="大模型未返回总评内容")
    return {"ok": True, "summary": summary}


@router.post("/folders/{folder_name:path}/manual-grade/clear")
async def api_clear_manual_grade(folder_name: str, request: Request):
    """清空答题卡（自主阅卷）分数并删除留痕图，恢复到仅分析状态。"""
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")

    try:
        body = await request.json()
    except Exception:
        body = {}

    filename = body.get("filename")
    if not filename:
        raise HTTPException(status_code=400, detail="参数缺失")

    with _grading_history_lock:
        data = _read_grading_history(safe, "manual")

    completed = data.get("completed", {})
    item = completed.get(filename)
    if not item or "manual_analyze" not in str(item.get("result", "")):
        raise HTTPException(status_code=404, detail="未找到自主阅卷记录")

    try:
        res_json = json.loads(item["result"])
        res_json["scores"] = {}
        res_json["deduction_items"] = {}
        if int(res_json.get("version") or 1) >= 2:
            res_json["decisions"] = {}
            for block in res_json.get("blocks") or []:
                if isinstance(block, dict):
                    block["status"] = "ungraded"
                    block["score"] = None
            res_json["manual_status"] = "ungraded"
            res_json["score_total"] = 0
        else:
            res_json["manual_status"] = "analyzed"
        item["result"] = json.dumps(res_json, ensure_ascii=False)
        item["score_total"] = None
        item["question_scores"] = {}
        item["deduction_items"] = {}

        _delete_modify_file_by_url(item.get("image_annotated"))
        _delete_modify_file_by_url(item.get("image_marks_only"))
        _delete_modify_file_by_url(item.get("image_marks_with_wrong_notes"))
        _delete_modify_file_by_url(item.get("image_annotated_with_wrong_notes"))

        item["image_annotated"] = ""
        item["image_marks_only"] = ""
        item["marks_only_filename"] = ""
        item.pop("marks_with_wrong_notes_filename", None)
        item.pop("image_marks_with_wrong_notes", None)
        item.pop("annotated_with_wrong_notes_filename", None)
        item.pop("image_annotated_with_wrong_notes", None)

        _persist_grading_success(safe, item, "manual")
        return {"ok": True, "message": "分数已清空", "item": item}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/folders/{folder_name:path}/scoring-config")
async def api_save_scoring_config(folder_name: str, request: Request):
    """保存或更新该文件夹的评分配置"""
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    
    try:
        body = await request.json()
    except Exception:
        body = {}
    
    scoring_config = body.get("scoring_config")
    if scoring_config is None:
        raise HTTPException(status_code=400, detail="请求体中缺少 scoring_config")

    full_score = body.get("full_score")
    question_structure = body.get("question_structure")
    major_scores = body.get("major_scores")
    major_order = body.get("major_order")
    major_titles = body.get("major_titles")
    paper_subs = body.get("paper_subs")

    with _grading_history_lock:
        data = _read_grading_history(safe)
        data["scoring_config"] = scoring_config
        if full_score is not None:
            data["full_score"] = full_score
        if isinstance(question_structure, dict):
            data["question_structure"] = question_structure
        if isinstance(major_scores, dict):
            data["major_scores"] = major_scores
        if isinstance(major_order, list):
            data["major_order"] = major_order
        if isinstance(major_titles, dict):
            data["major_titles"] = major_titles
        if isinstance(paper_subs, dict):
            data["paper_subs"] = paper_subs
        _write_grading_history(safe, data)

    return {"ok": True, "message": "评分配置已保存"}


from app.grading.essay_pdf import (
    build_essay_report_pdf_bytes,
    build_essay_images_pdf_bytes,
    EssayPdfItem,
)
from app.grading.doc_convert import pdf_to_images
from app.grading.print_marks import print_images
import tempfile
import uuid
from fastapi.responses import Response

@router.post("/folders/{folder_name:path}/essay-grade/pdf")
async def api_essay_grade_pdf(folder_name: str, body: dict = Body(...)):
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    
    items_data = body.get("items", [])
    items = [EssayPdfItem(**d) for d in items_data]
    # mode=images：只要「原卷 + 留痕」图片（与预览一致），不是 A4 文字报告
    mode = str(body.get("mode") or "report").strip().lower()

    try:
        if mode == "images":
            pdf_bytes = build_essay_images_pdf_bytes(
                modify_dir=modify_dir(),
                items=items,
                include_original=bool(body.get("include_original", True)),
                include_annotated=bool(body.get("include_annotated", True)),
            )
        else:
            pdf_bytes = build_essay_report_pdf_bytes(folder_name=safe, items=items)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成PDF失败: {e}")

    return Response(content=pdf_bytes, media_type="application/pdf")

@router.post("/folders/{folder_name:path}/essay-grade/print-pdf")
async def api_essay_grade_print_pdf(folder_name: str, request: Request, db: Session = Depends(get_db), body: dict = Body(...)):
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    _require_local_admin(request, db)  # M5：打印仅允许本机管理员，防远程触发真实打印
        
    items_data = body.get("items", [])
    items = [EssayPdfItem(**d) for d in items_data]
    printer_name = body.get("printer_name")
    paper_size = body.get("paper_size", "a4")
    paper_source = body.get("paper_source")
    print_mode = str(body.get("print_mode") or "single").strip().lower()
    duplex_mode = print_mode == "double"
    
    custom_paper_mm = None
    if paper_size == "custom":
        cw = body.get("custom_paper_width_mm")
        ch = body.get("custom_paper_height_mm")
        if cw and ch:
            custom_paper_mm = (float(cw), float(ch))
    
    if not items:
        raise HTTPException(status_code=400, detail="没有可打印的批改报告")

    printed_pages = 0
    errors: list[str] = []

    def _print_page_images(page_paths: list[str], *, duplex: bool) -> tuple[bool, str]:
        return print_images(
            page_paths,
            printer_name=printer_name,
            copies=1,
            duplex=duplex,
            paper_size=paper_size,
            custom_paper_mm=custom_paper_mm,
            paper_source=paper_source,
        )

    for item in items:
        temp_pdf = Path(tempfile.gettempdir()) / f"print_essay_{uuid.uuid4().hex}.pdf"
        temp_img_paths: list[str] = []
        try:
            pdf_bytes = build_essay_report_pdf_bytes(folder_name=safe, items=[item])
            temp_pdf.write_bytes(pdf_bytes)

            images = pdf_to_images(str(temp_pdf), dpi=300)
            for img in images:
                img_path = Path(tempfile.gettempdir()) / f"print_essay_page_{uuid.uuid4().hex}_{len(temp_img_paths)}.jpg"
                img.save(str(img_path), "JPEG", quality=95)
                temp_img_paths.append(str(img_path))
                img.close()

            if not temp_img_paths:
                errors.append(f"{item.name}: 报告无页面")
                continue

            if duplex_mode:
                idx = 0
                while idx < len(temp_img_paths):
                    if idx + 1 < len(temp_img_paths):
                        chunk = temp_img_paths[idx : idx + 2]
                        ok, msg = _print_page_images(chunk, duplex=True)
                        if ok:
                            printed_pages += 2
                        else:
                            errors.append(f"{item.name}: {msg}")
                            break
                        idx += 2
                    else:
                        ok, msg = _print_page_images([temp_img_paths[idx]], duplex=False)
                        if ok:
                            printed_pages += 1
                        else:
                            errors.append(f"{item.name}: {msg}")
                        break
            else:
                ok, msg = _print_page_images(temp_img_paths, duplex=False)
                if ok:
                    printed_pages += len(temp_img_paths)
                else:
                    errors.append(f"{item.name}: {msg}")
        except Exception as e:
            errors.append(f"{item.name}: {e}")
        finally:
            try:
                temp_pdf.unlink(missing_ok=True)
            except Exception:
                pass
            for p in temp_img_paths:
                try:
                    Path(p).unlink(missing_ok=True)
                except Exception:
                    pass

    if errors and printed_pages == 0:
        raise HTTPException(status_code=500, detail="；".join(errors[:3]))
    msg = f"已发送至打印机: {printer_name or '默认打印机'}"
    if duplex_mode:
        msg += f"（双面前后打印，共 {printed_pages} 页）"
    else:
        msg += f"（单面打印，共 {printed_pages} 页）"
    if errors:
        msg += f"；{len(errors)} 份失败"
    return {"ok": True, "msg": msg, "printed": printed_pages, "errors": errors}

@router.get("/printers")
async def api_list_printers(request: Request, db: Session = Depends(get_db)):
    """获取本机打印机列表及状态"""
    _require_local_admin(request, db)  # M5
    from app.grading.print_marks import list_printers_with_status
    ok, result = list_printers_with_status()
    if ok:
        return {"ok": True, "printers": result}
    else:
        return {"ok": False, "msg": str(result), "printers": []}


@router.get("/scanners")
async def api_list_scanners(request: Request, db: Session = Depends(get_db)):
    """获取本机可用扫描仪列表（Windows WIA）"""
    _require_local_admin(request, db)  # M5
    from app.grading.scanner_devices import list_scanners_with_status
    ok, result = list_scanners_with_status()
    if ok:
        return {"ok": True, "scanners": result}
    return {"ok": False, "msg": str(result), "scanners": []}

@router.post("/folders/{folder_name:path}/backfill-blocks")
async def api_backfill_blocks(folder_name: str, body: dict = Body(...)):
    """自动补全「编辑批改」依赖的逐题数据：检测历史里缺 blocks 的记录，用原引擎重新批改补齐。

    只覆盖缺 blocks 的那几张，不清空、不重批其它已有逐题数据的记录
    （区别于 grade-by-reference 的全量重批，后者会 _replace_folder_grading_run 清空整个文件夹历史）。
    """
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")

    requested_engine = str(body.get("engine") or "").strip().lower()
    read_engine = requested_engine if requested_engine in ("baidu", "smart_ref", "aliyun") else "default"

    with _grading_history_lock:
        data = _read_grading_history(safe, read_engine)
    completed = data.get("completed") or {}

    # 找出缺 blocks（逐题数据）的记录及其引擎
    missing_by_engine: dict[str, list[str]] = {}
    top_engine = str(data.get("engine") or "").strip()
    for name, item in completed.items():
        if not isinstance(item, dict):
            continue
        blocks = item.get("blocks")
        if isinstance(blocks, list) and len(blocks) > 0:
            continue
        item_engine = str(item.get("engine") or "").strip()
        if item_engine not in ("baidu", "smart_ref", "aliyun"):
            item_engine = top_engine if top_engine in ("baidu", "smart_ref", "aliyun") else ""
        if item_engine not in ("baidu", "smart_ref", "aliyun"):
            continue
        missing_by_engine.setdefault(item_engine, []).append(name)

    if not missing_by_engine:
        return {"ok": True, "job_id": None, "total": 0, "message": "没有缺逐题数据的记录，无需补全"}

    # 一次 job 只处理一个引擎；缺多引擎时优先补数量最多的那组（其余下次进入文件夹时再补）
    target_engine = max(missing_by_engine.items(), key=lambda kv: len(kv[1]))[0]
    missing_names = sorted(set(missing_by_engine[target_engine]))

    # 0924：补全走原引擎重新批改（大模型）⇒ 接闸；不计面（上传时已计，防双扣）
    quota_gate()
    job_id = str(uuid.uuid4())
    # 1015 冻死防线②：补全与全量批改共用同文件夹单飞闸，防双入口并行顶内存。
    # 检查+注册同锁原子完成（防 TOCTOU）。
    with _ref_grade_lock:
        gate = _find_active_ref_job_locked(
            safe,
            engine=target_engine,
            only_filename=None,
            only_filenames=set(missing_names),
            user_id=get_grading_user_id(),
        )
        if gate is not None:
            active_job_id, same_scope = gate
            if same_scope:
                active_total = _ref_grade_results.get(active_job_id, {}).get("total", len(missing_names))
                return {"ok": True, "job_id": active_job_id, "total": active_total, "already_running": True}
            raise HTTPException(
                status_code=409,
                detail="该文件夹已有批改任务进行中，请等待完成或取消后再发起",
            )
        _ref_grade_results[job_id] = {
            "completed": [],
            "failed": [],
            "in_progress": [],
            "done": False,
            "total": len(missing_names),
            "engine": target_engine,
            "manual_analyzed": False,
            "manual_paper_cut_tasks": {},
            "user_id": get_grading_user_id(),
            "folder": safe,
            "only_filename": None,
            "only_filenames": sorted(missing_names),
        }
        _ref_grade_stop_events[job_id] = threading.Event()
    threading.Thread(
        target=_run_ref_grade,
        args=(job_id, safe, target_engine, None, set(missing_names), get_grading_user_id()),
        daemon=True,
    ).start()

    return {"ok": True, "job_id": job_id, "total": len(missing_names), "engine": target_engine}


@router.post("/folders/{folder_name:path}/grade-by-reference")
async def api_start_grade_by_reference(folder_name: str, body: dict = Body(...)):
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    _quota_gate()  # 0924 额度 105% 硬停前置闸门

    engine = str(body.get("engine") or "aliyun").strip().lower()
    if engine == "aliyun":
        layout_status = reference_layout_status(
            safe,
            {page_no: source for page_no, (source, _grading) in _reference_standard_sources(safe).items()},
        )
        if not layout_status.get("confirmed"):
            raise HTTPException(
                status_code=409,
                detail="请先完成标准答案切题审查并点击确认保存",
            )
    only_filename = body.get("filename")
    only_filenames_list = body.get("filenames")

    only_filenames = None
    if isinstance(only_filenames_list, list) and len(only_filenames_list) > 0:
        only_filenames = set(str(x).strip() for x in only_filenames_list if str(x).strip())
        
    job_id = str(uuid.uuid4())
    
    # 获取总数
    dir_path = correct_docs_dir() / safe
    if not dir_path.is_dir():
        total = 0
    else:
        total = 0
        for item in dir_path.iterdir():
            if item.is_file() and item.suffix.lower() in _ALL_UPLOAD_EXTS:
                if not _is_standard_answer_filename(item.name) and not _is_answer_sheet_filename(item.name):
                    if only_filenames and item.name not in only_filenames:
                        continue
                    if only_filename and item.name != only_filename:
                        continue
                    total += 1

    if total <= 0:
        raise HTTPException(status_code=400, detail="没有找到本次需要批改的学生试卷")

    # 1015 冻死防线②：同文件夹单飞闸——同参数连点幂等返回在跑 job，异参数 409。
    # 检查和注册必须在同一把锁内原子完成（防 TOCTOU），且先注册再清历史：
    # 清历史（_replace_folder_grading_run）放锁外做 IO，失败则回滚注册。
    # 闸门必须在清空历史之前，否则第二次点击会把第一次还没跑完的批改历史
    # 清掉并再起一条 8 线程批次（事故根因之一）。
    with _ref_grade_lock:
        gate = _find_active_ref_job_locked(
            safe,
            engine=engine,
            only_filename=only_filename,
            only_filenames=only_filenames,
            user_id=get_grading_user_id(),
        )
        if gate is not None:
            active_job_id, same_scope = gate
            if same_scope:
                active_total = _ref_grade_results.get(active_job_id, {}).get("total", total)
                return {"ok": True, "job_id": active_job_id, "total": active_total, "already_running": True}
            raise HTTPException(
                status_code=409,
                detail="该文件夹已有批改任务进行中，请等待完成或取消后再发起",
            )
        _ref_grade_results[job_id] = {
            "completed": [],
            "failed": [],
            "in_progress": [],
            "done": False,
            "total": total,
            "engine": engine,
            "manual_analyzed": False,
            "manual_paper_cut_tasks": {},
            "user_id": get_grading_user_id(),
            # 批改完是否自动推钉钉（前端「自动推送钉钉/手动」开关，手动模式不推）
            "push_dingtalk": bool(body.get("push_dingtalk", True)),
            # 1015 单飞闸：记录本次范围，供 _find_active_ref_job_locked 比对
            "folder": safe,
            "only_filename": only_filename,
            "only_filenames": sorted(only_filenames) if only_filenames else None,
        }
        _ref_grade_stop_events[job_id] = threading.Event()

    try:
        # The folder detail represents one run only. Clear both the previous
        # smart/reference history and manual history before any worker can write.
        _replace_folder_grading_run(safe, engine)
    except Exception:
        with _ref_grade_lock:
            _ref_grade_results.pop(job_id, None)
            _ref_grade_stop_events.pop(job_id, None)
        raise

    threading.Thread(
        target=_run_ref_grade,
        args=(job_id, safe, engine, only_filename, only_filenames, get_grading_user_id()),
        daemon=True
    ).start()

    return {"ok": True, "job_id": job_id, "total": total}

@router.get("/folders/{folder_name:path}/grade-by-reference/status/{job_id}")
async def api_grade_by_reference_status(folder_name: str, job_id: str):
    with _ref_grade_lock:
        if job_id not in _ref_grade_results:
            raise HTTPException(status_code=404, detail="任务不存在或已清理")
        res = _ref_grade_results[job_id]
    _assert_job_owner(res)
    with _ref_grade_lock:
        res = _ref_grade_results[job_id]

        # H2：completed 里的图片直链是在「批改完成那一刻」签的短时下载票（10 分钟过期）。
        # 前端会持续轮询本接口，若页面停留/轮询超过 10 分钟后再点进详情，<img> 会拿到过期票 → 401「未登录」。
        # 这里每次轮询都按当前用户重签，保证返回给前端的永远是新鲜票。
        for _item in res["completed"]:
            if isinstance(_item, dict):
                _resign_history_images(_item)

        # 兼容旧版的 current_name (这里随意取in_progress的一个)
        current_name = None
        if res.get("in_progress"):
            current_name = res["in_progress"][0]

        return {
            "ok": True,
            "completed": res["completed"],
            "failed": res["failed"],
            "in_progress": res["in_progress"],
            "done": res["done"],
            "total": res.get("total", 0),
            "current_name": current_name,
            "manual_analyzed": res.get("manual_analyzed", False),
            "manual_paper_cut_tasks": res.get("manual_paper_cut_tasks", {})
        }

@router.post("/folders/{folder_name:path}/grade-by-reference/cancel")
async def api_cancel_grade_by_reference(folder_name: str, body: dict = Body(...)):
    job_id = body.get("job_id")
    if not job_id:
        raise HTTPException(status_code=400, detail="缺少 job_id")
        
    with _ref_grade_lock:
        _rg_data = _ref_grade_results.get(job_id)
    if _rg_data is not None:
        _assert_job_owner(_rg_data)
    ev = _ref_grade_stop_events.get(job_id)
    if ev:
        ev.set()
        
    with _ref_grade_lock:
        if job_id in _ref_grade_results:
            _ref_grade_results[job_id]["done"] = True

    return {"ok": True, "msg": "已请求取消批改"}


@router.post("/folders/{folder_name:path}/dingtalk-notify")
async def api_push_dingtalk_manual(folder_name: str, body: dict = Body(...)):
    """手动推送钉钉通知（前端「手动推送」模式下的按钮）。

    kind: grading_done=智能/参照批改完成 / essay=作文批改 / manual=自主阅卷
    """
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    kind = str(body.get("kind") or "grading_done").strip()
    if kind not in ("grading_done", "essay", "manual"):
        raise HTTPException(
            status_code=400, detail=f"kind 取值应为 grading_done/essay/manual，收到 {kind!r}"
        )
    from app.services.dingtalk_notify import push_dingtalk_now

    # 路由处于 grading 用户上下文（中间件绑定），collector 可直接用
    ok, message = push_dingtalk_now(get_grading_user_id(), safe, kind)
    return {"ok": ok, "message": message}


# ---- 答题卡按标准答案自动比对 ----

def _run_answer_key_grade(job_id: str, safe: str, answers: dict, ctx_uid: str) -> None:
    """异步逐张卷：取 manual 切题 blocks → 答案比对 → 复用 _save_manual_slot_decisions 落盘。

    线程体用 run_with_grading_user 恢复 grading 用户上下文——裸 threading.Thread 不继承
    ContextVar，否则首行 _read_grading_history 就会抛「grading user context 未设置」。
    """
    run_with_grading_user(ctx_uid, _run_answer_key_grade_impl, job_id, safe, answers)


def _run_answer_key_grade_impl(job_id: str, safe: str, answers: dict) -> None:
    with _grading_history_lock:
        data = _read_grading_history(safe, "manual")
    completed = data.get("completed") if isinstance(data.get("completed"), dict) else {}
    items = [
        (name, dict(item))
        for name, item in completed.items()
        if isinstance(item, dict) and "manual_analyze" in str(item.get("result", ""))
    ]

    def process_one(pair):
        name, item = pair
        with _ref_grade_lock:
            if job_id in _ref_grade_results:
                _ref_grade_results[job_id].setdefault("in_progress", []).append(name)
        stop_ev = _ref_grade_stop_events.get(job_id)
        if stop_ev and stop_ev.is_set():
            with _ref_grade_lock:
                if job_id in _ref_grade_results:
                    _ref_grade_results[job_id]["failed"].append({"name": name, "msg": "已停止批改"})
            return
        try:
            res_json = json.loads(item.get("result") or "{}")
            blocks = res_json.get("blocks") if isinstance(res_json.get("blocks"), list) else []
            if not blocks or not any(
                isinstance(b, dict) and (b.get("slot_id") or b.get("label"))
                for b in blocks
            ):
                raise RuntimeError("缺少作答区切题记录，请先完成答题卡切题分析")
            source_path = correct_docs_dir() / safe / name
            grading_path = _get_grading_path(safe, source_path)
            if grading_path is None:
                grading_path = _ensure_img_in_folder(source_path, safe) or source_path
            # C3 判分缓存身份：科目从 folder meta.json 取（预查/回写共用同一取值）
            from app.grading.response_log_db import _read_folder_meta

            decisions = grade_paper_by_answer_key(
                str(grading_path), blocks, answers, subject=(_read_folder_meta(safe) or {}).get("subject")
            )
            saved = _save_manual_slot_decisions(
                safe, name, item, res_json, decisions, generate_marks=True
            )
            with _ref_grade_lock:
                if job_id in _ref_grade_results:
                    _ref_grade_results[job_id]["completed"].append(saved)
        except Exception as e:
            with _ref_grade_lock:
                if job_id in _ref_grade_results:
                    _ref_grade_results[job_id]["failed"].append({"name": name, "msg": str(e)})
            _persist_grading_failure(safe, name, str(e), "manual")
        finally:
            with _ref_grade_lock:
                if job_id in _ref_grade_results:
                    in_progress = _ref_grade_results[job_id].setdefault("in_progress", [])
                    if name in in_progress:
                        in_progress.remove(name)

    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            ctx_uid = get_grading_user_id()
            list(executor.map(lambda p: run_with_grading_user(ctx_uid, process_one, p), items))
    finally:
        _ref_grade_stop_events.pop(job_id, None)
        with _ref_grade_lock:
            if job_id in _ref_grade_results:
                _ref_grade_results[job_id]["done"] = True


@router.post("/folders/{folder_name:path}/answer-key")
async def api_save_answer_key(folder_name: str, request: Request):
    """保存/解析标准答案：文字（1.A 2.C …）或上传答案图片（自动识别）。"""
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")

    raw_text = ""
    content_type = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" in content_type:
        form = await request.form()
        answer_text = str(form.get("answer_text") or "").strip()
        upload = form.get("file")
        if upload is not None and hasattr(upload, "file"):
            import tempfile

            content = upload.file.read()
            filename = getattr(upload, "filename", "") or ""
            ext = os.path.splitext(filename)[1].lower()
            if ext not in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".pdf", ".doc", ".docx"):
                ext = ".png"
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                if ext in (".pdf", ".doc", ".docx"):
                    raw_text = extract_answer_key_text_from_document(tmp_path)
                else:
                    raw_text = extract_answer_key_text_from_image(tmp_path)
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            if not raw_text.strip():
                raise HTTPException(
                    status_code=400,
                    detail="未能从上传的图片/文档中识别出答案（视觉识别失败）。请检查千问 API Key 是否已配置，或直接改用手动填写文字答案",
                )
        else:
            raw_text = answer_text
    else:
        try:
            body = await request.json()
        except Exception:
            body = {}
        raw_text = str(body.get("answer_text") or "").strip()

    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="答案为空")

    answers = parse_answer_key_text(raw_text)
    if not answers:
        raise HTTPException(
            status_code=400,
            detail="未能解析出题目答案，请按「1.A 2.C 3.√」格式填写，或换用答案图片",
        )

    with _grading_history_lock:
        data = _read_grading_history(safe, "manual")
        data["answer_key"] = {
            "raw": raw_text.strip(),
            "answers": answers,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_grading_history(safe, data, "manual")

    return {"ok": True, "answers": answers, "raw": raw_text.strip()}


@router.get("/folders/{folder_name:path}/answer-key")
async def api_get_answer_key(folder_name: str):
    """读取已保存的标准答案（用于前端回显）。"""
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    with _grading_history_lock:
        data = _read_grading_history(safe, "manual")
    info = data.get("answer_key")
    if not isinstance(info, dict):
        return {"ok": True, "answers": {}, "raw": ""}
    return {
        "ok": True,
        "answers": info.get("answers") or {},
        "raw": info.get("raw") or "",
        "updated_at": info.get("updated_at"),
    }


@router.post("/folders/{folder_name:path}/grade-by-answer-key")
async def api_start_grade_by_answer_key(folder_name: str):
    """按已保存的标准答案，对文件夹内每张答题卡自动比对并落盘（异步）。"""
    safe = _safe_folder_name(folder_name)
    if not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")
    _quota_gate()  # 0924 额度 105% 硬停前置闸门

    with _grading_history_lock:
        data = _read_grading_history(safe, "manual")
    answer_key_info = data.get("answer_key")
    answers = (
        answer_key_info.get("answers")
        if isinstance(answer_key_info, dict) and isinstance(answer_key_info.get("answers"), dict)
        else {}
    )
    if not answers:
        raise HTTPException(status_code=400, detail="请先上传或填写标准答案")

    completed = data.get("completed") if isinstance(data.get("completed"), dict) else {}
    total = sum(
        1
        for item in completed.values()
        if isinstance(item, dict) and "manual_analyze" in str(item.get("result", ""))
    )
    if total <= 0:
        raise HTTPException(status_code=400, detail="没有找到已切题的学生答题卡，请先完成切题分析")

    job_id = str(uuid.uuid4())
    ctx_uid = get_grading_user_id()
    with _ref_grade_lock:
        _ref_grade_results[job_id] = {
            "completed": [],
            "failed": [],
            "in_progress": [],
            "done": False,
            "total": total,
            "engine": "answer_key",
            "manual_analyzed": False,
            "manual_paper_cut_tasks": {},
            "user_id": ctx_uid,
        }
    _ref_grade_stop_events[job_id] = threading.Event()

    threading.Thread(
        target=_run_answer_key_grade,
        args=(job_id, safe, answers, ctx_uid),
        daemon=True,
    ).start()

    return {"ok": True, "job_id": job_id, "total": total}


@router.get("/folders/{folder_name:path}/grade-by-answer-key/status/{job_id}")
async def api_answer_key_grade_status(folder_name: str, job_id: str):
    return await api_grade_by_reference_status(folder_name, job_id)


@router.post("/folders/{folder_name:path}/grade-by-answer-key/cancel")
async def api_answer_key_grade_cancel(folder_name: str, body: dict = Body(...)):
    return await api_cancel_grade_by_reference(folder_name, body)


# ---- R1 低置信题批量清单（只读 · 摸底 confidence 数据分布）----
_BUCKET_KEYS = ("<0.3", "0.3-0.6", "0.6-0.8", ">=0.8")


def _bucket_conf(confidence: float) -> str:
    """把 confidence 归入分布桶：<0.3 / 0.3-0.6 / 0.6-0.8 / >=0.8。"""
    if confidence < 0.3:
        return "<0.3"
    if confidence < 0.6:
        return "0.3-0.6"
    if confidence < 0.8:
        return "0.6-0.8"
    return ">=0.8"


@router.get("/low-confidence-questions", response_model=ApiResponse[dict])
def api_low_confidence_questions(
    confidence_max: float = Query(0.6, description="confidence < 此值算低置信"),
    days: int = Query(7, description="回溯天数（created_at 窗口）"),
    engine: Optional[str] = Query(None, description="可选引擎过滤，仅过滤 items"),
    limit: int = Query(200, description="items 条数上限，clamp 到 [1, 500]"),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """低置信题批量清单：暴露 AI 批改没把握的题给老师复核（只读 SELECT）。

    total_low_conf / distribution / engines 基于全量低置信行（不含 engine 过滤），
    用于摸底各引擎 confidence 填充情况。
    """
    limit = max(1, min(limit, 500))
    since = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    low_conf = [
        ResponseLog.user_id == user_id,
        ResponseLog.confidence.isnot(None),
        ResponseLog.confidence < confidence_max,
        ResponseLog.created_at >= since,
    ]
    items_query = db.query(ResponseLog).filter(*low_conf)
    if engine:
        items_query = items_query.filter(ResponseLog.engine == engine)
    rows = items_query.order_by(ResponseLog.created_at.desc()).limit(limit).all()

    total_low_conf = db.query(func.count(ResponseLog.id)).filter(*low_conf).scalar() or 0
    distribution = {k: 0 for k in _BUCKET_KEYS}
    engines: dict[str, int] = {}
    for conf, eng in db.query(ResponseLog.confidence, ResponseLog.engine).filter(*low_conf).all():
        distribution[_bucket_conf(conf)] += 1
        name = eng or "unknown"
        engines[name] = engines.get(name, 0) + 1

    items = [
        {
            "id": r.id,
            "folder_safe": r.folder_safe,
            "paper_name": r.paper_name,
            "engine": r.engine,
            "question_id": r.question_id,
            "question_content": (r.question_content or "")[:200],
            "status": r.status,
            "score": r.score,
            "max_score": r.max_score,
            "confidence": r.confidence,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return ApiResponse(
        data={
            "items": items,
            "count": len(items),
            "total_low_conf": total_low_conf,
            "distribution": distribution,
            "engines": engines,
        }
    )


@router.get("/correction-stats", response_model=ApiResponse[dict])
def api_correction_stats(
    days: int = Query(30, description="回溯天数（created_at 窗口）"),
    include_voided: bool = Query(False, description="true 则把已作废（re-grade 重跑）行计入"),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """修正/复核记账矩阵（只读 SELECT）：教师推翻率、兜底拦截量的原料。

    matrix 按 (source, subject_family, was, new) 聚合；默认排除 voided
    （re-grade 全量重跑会把该文件夹旧行标记作废）。
    """
    window_days = max(1, days)
    from app.grading.correction_ledger import correction_stats

    matrix = correction_stats(db, user_id, days=window_days, include_voided=include_voided)
    totals_by_source: dict[str, int] = {}
    for row in matrix:
        src = str(row.get("source") or "unknown")
        totals_by_source[src] = totals_by_source.get(src, 0) + int(row.get("count") or 0)
    return ApiResponse(
        data={
            "matrix": matrix,
            "totals_by_source": totals_by_source,
            "window_days": window_days,
        }
    )


@router.get("/correction-ledger", response_model=ApiResponse[dict])
def api_correction_ledger(
    days: int = Query(30, description="回溯天数（created_at 窗口）"),
    include_voided: bool = Query(False, description="true 则包含已作废（re-grade 重跑）行"),
    limit: int = Query(200, description="返回条数上限（1-500）"),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """修正/复核记账明细（只读 SELECT）：台账查看页逐行列表。

    与 /correction-stats 同窗口同过滤；rows 含时间/学生卷/题号/改动前后/来源。
    """
    window_days = max(1, days)
    from app.grading.correction_ledger import correction_ledger_rows

    rows = correction_ledger_rows(
        db, user_id, days=window_days, include_voided=include_voided, limit=limit
    )
    return ApiResponse(
        data={
            "rows": rows,
            "count": len(rows),
            "window_days": window_days,
            "include_voided": include_voided,
        }
    )
