# -*- coding: utf-8 -*-
"""智能模型批改后的后台错题 JSON 库。

该模块只做文件型错题采集，不对外提供接口，不影响前端展示。
目录结构：
grading_data_all/grading_data_{user_id}/ct/cls_<class_id>/records/<exam_name>.json
grading_data_all/grading_data_{user_id}/ct/cls_<class_id>/analysis/<exam_name>.json
grading_data_all/grading_data_{user_id}/ct/cls_<class_id>/assets/<exam_name>/<paper_name>/*.jpg
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.utils.security import build_download_url


_ct_lock = threading.Lock()


def _grading_data_root() -> Path:
    try:
        from app.grading.user_paths import grading_paths
        root = grading_paths().root
        root.mkdir(parents=True, exist_ok=True)
        return root
    except Exception:
        from app.grading.user_paths import grading_data_all_root
        data = grading_data_all_root() / "_no_user_context"
        data.mkdir(parents=True, exist_ok=True)
        return data


def _ct_root() -> Path:
    try:
        from app.grading.user_paths import ct_root as _ct
        root = _ct()
        root.mkdir(parents=True, exist_ok=True)
        return root
    except Exception:
        root = _grading_data_root() / "ct"
        root.mkdir(parents=True, exist_ok=True)
        return root


def _normalize_ct_rel_path(rel_path: Optional[str]) -> Optional[str]:
    if not rel_path:
        return None
    parts = str(rel_path).replace("\\", "/").split("/")
    if parts and parts[0] == "ct":
        parts = parts[1:]
    normalized = "/".join(parts).lstrip("/")
    if not normalized or ".." in normalized:
        return None
    return normalized


def resolve_ct_image_path(path: str) -> Optional[Path]:
    """解析 CT 错题图片路径；精确路径不存在时按文件名在班级 assets 下回退查找。"""
    ct_root = _ct_root().resolve()
    normalized = _normalize_ct_rel_path(path) or ""
    if not normalized:
        return None

    full_path = (ct_root / normalized).resolve()
    if not str(full_path).startswith(str(ct_root)):
        return None
    if full_path.is_file():
        return full_path

    parts = normalized.split("/")
    if len(parts) < 3 or not parts[0].startswith("cls_") or parts[1] != "assets":
        return None

    cls_dir = parts[0]
    filename = parts[-1]
    student_hint = parts[-2] if len(parts) >= 5 else ""
    assets_root = ct_root / cls_dir / "assets"
    if not assets_root.is_dir():
        return None

    matches = [p for p in assets_root.rglob(filename) if p.is_file()]
    if not matches:
        return None
    if student_hint:
        hinted = [p for p in matches if student_hint in p.parts]
        if hinted:
            return hinted[0]
    return matches[0] if len(matches) == 1 else None


def ct_image_api_url_for_rel(rel_path: Optional[str]) -> Optional[str]:
    normalized = _normalize_ct_rel_path(rel_path)
    if not normalized:
        return None
    resolved = resolve_ct_image_path(normalized)
    if not resolved:
        return None
    actual_rel = resolved.relative_to(_ct_root()).as_posix()
    # C6/H2：错题图复用 /api/v1/ct/{rel} 短时下载票直链（img 标签无法带 Bearer，走 ticket）。
    try:
        from app.grading.user_paths import get_grading_user_id
        uid = get_grading_user_id()
    except Exception:
        uid = ""
    if uid:
        return build_download_url(f"ct/{actual_rel}", uid)
    # 兜底：无用户上下文时回退旧 ct-image 端点（仍受 Bearer 保护，仅作兼容）
    import urllib.parse
    return "/api/v1/student-analysis/ct-image?path=" + urllib.parse.quote(actual_rel)


def collect_wrong_question_images(folder_names: list[str]) -> list[dict]:
    """扫描考试错题裁剪图，仅返回磁盘上真实存在的图片 URL。"""
    results: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    def _append(student_name: str, title: str, q_rel: Optional[str], a_rel: Optional[str]) -> None:
        image_url = ct_image_api_url_for_rel(q_rel)
        answer_url = ct_image_api_url_for_rel(a_rel)
        if not image_url and not answer_url:
            return
        key = (student_name, title, image_url or answer_url or "")
        if key in seen:
            return
        seen.add(key)
        results.append({
            "student_name": student_name,
            "title": title,
            "image_url": image_url,
            "answer_url": answer_url,
        })

    for folder_safe in folder_names:
        class_id_str, exam_name = "", folder_safe
        if folder_safe.startswith("cls_") and "__" in folder_safe:
            class_id_str, exam_name = folder_safe.split("__", 1)

        ct_root = _ct_root()
        exam_assets_dir = ct_root / class_id_str / "assets" / exam_name

        if exam_assets_dir.is_dir():
            for student_dir in exam_assets_dir.iterdir():
                if not student_dir.is_dir():
                    continue
                student_name = student_dir.name
                # 多页卷（参照批改）的裁图落在 p1/p2 页面子目录，递归扫；作答图与题图同目录
                for q_file in sorted(student_dir.rglob("*_question.jpg")):
                    title_base = q_file.name.replace("_question.jpg", "")
                    a_file = q_file.parent / f"{title_base}_answer.jpg"
                    try:
                        q_rel = q_file.relative_to(ct_root.parent).as_posix()
                    except ValueError:
                        q_rel = f"ct/{class_id_str}/assets/{exam_name}/{student_name}/{q_file.name}"
                    a_rel = None
                    if a_file.is_file():
                        try:
                            a_rel = a_file.relative_to(ct_root.parent).as_posix()
                        except ValueError:
                            a_rel = f"ct/{class_id_str}/assets/{exam_name}/{student_name}/{a_file.name}"
                    title_parts = title_base.split("_")
                    title = title_base
                    if len(title_parts) >= 3:
                        title = f"第{title_parts[-2].replace('q', '')}题-区{title_parts[-1].replace('s', '')}"
                    _append(student_name, title, q_rel, a_rel)
            continue

        analysis_path = _analysis_json_path(folder_safe, create_class_dir=False)
        if not analysis_path or not analysis_path.is_file():
            continue
        analysis_data = _read_json(analysis_path)
        papers = analysis_data.get("papers", {})
        for student_name, student_paper in papers.items():
            if not isinstance(student_paper, dict):
                continue
            wq_list = student_paper.get("wrong_question_analysis", [])
            if not isinstance(wq_list, list):
                continue
            for wq in wq_list:
                if not isinstance(wq, dict):
                    continue
                title = wq.get("display_title", wq.get("question_key", ""))
                assets = wq.get("assets", {})
                q_img = assets.get("question_image", {})
                a_img = assets.get("answer_image", {})
                q_rel = q_img.get("relative_to_grading_data") if isinstance(q_img, dict) else None
                a_rel = a_img.get("relative_to_grading_data") if isinstance(a_img, dict) else None
                if q_rel or a_rel:
                    _append(student_name, title, q_rel, a_rel)

    return results


def collect_wrong_question_knowledge_points(folder_safe: str) -> dict[str, list[str]]:
    """读取错题库 analysis JSON，返回 display_title -> 去重知识点列表 的映射。

    供错题本详情接口透出「知识点串讲」数据；analysis 缺失或为空时返回空字典，
    调用方据此优雅降级（每题知识点评为空数组），不影响批改主链路。
    """
    analysis_path = _analysis_json_path(folder_safe, create_class_dir=False)
    if not analysis_path or not analysis_path.is_file():
        return {}
    analysis_data = _read_json(analysis_path)
    papers = analysis_data.get("papers", {})
    if not isinstance(papers, dict):
        return {}
    result: dict[str, list[str]] = {}
    for paper in papers.values():
        if not isinstance(paper, dict):
            continue
        items = paper.get("wrong_question_analysis", [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("display_title") or "").strip()
            analysis = item.get("analysis")
            if not title or not isinstance(analysis, dict):
                continue
            points = analysis.get("knowledge_points")
            if not isinstance(points, list):
                continue
            merged = result.setdefault(title, [])
            for point in points:
                text = str(point or "").strip()
                if text and text not in merged:
                    merged.append(text)
    return result


def _safe_class_token(class_id: Optional[str]) -> str:
    s = str(class_id or "").strip()
    if not s:
        return ""
    return "".join(c for c in s if c.isalnum() or c in ("-", "_"))[:64]


def _split_class_exam(folder_safe: str) -> tuple[str, str]:
    """从 cls_<class_id>__<exam_name> 文件夹名中取出 class_id 和考试名。"""
    safe = str(folder_safe or "").strip()
    if not safe.startswith("cls_") or "__" not in safe:
        return "", safe
    prefix, exam_name = safe.split("__", 1)
    return _safe_class_token(prefix[4:]), (exam_name.strip() or safe)


def _safe_json_stem(name: str) -> str:
    raw = str(name or "").strip() or "未命名考试"
    cleaned = "".join(c for c in raw if c not in '/\\:*?"<>|').strip()
    return cleaned[:120] or "未命名考试"


def _paper_box_name(paper_name: str) -> str:
    stem = Path(str(paper_name or "")).stem.strip()
    match = re.match(r"^(?P<name>.+)_\d+$", stem)
    return (match.group("name") if match else stem).strip() or stem


def _unique_list(items: list[Any]) -> list[str]:
    out: list[str] = []
    seen = set()
    for item in items:
        value = str(item or "").strip()
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


def _class_dir_for_exam(folder_safe: str, *, create_class_dir: bool = True) -> tuple[Optional[Path], str]:
    class_id, exam_name = _split_class_exam(folder_safe)
    if not class_id:
        return None, exam_name
    if create_class_dir:
        class_dir = ensure_class_wrong_question_dir(class_id)
    else:
        class_dir = _ct_root() / f"cls_{class_id}"
    return class_dir, exam_name


def _record_json_path(folder_safe: str, *, create_class_dir: bool = True) -> Optional[Path]:
    class_dir, exam_name = _class_dir_for_exam(folder_safe, create_class_dir=create_class_dir)
    if not class_dir:
        return None
    return class_dir / "records" / f"{_safe_json_stem(exam_name)}.json"


def _analysis_json_path(folder_safe: str, *, create_class_dir: bool = True) -> Optional[Path]:
    class_dir, exam_name = _class_dir_for_exam(folder_safe, create_class_dir=create_class_dir)
    if not class_dir:
        return None
    return class_dir / "analysis" / f"{_safe_json_stem(exam_name)}.json"


def _legacy_exam_json_path(folder_safe: str, *, create_class_dir: bool = False) -> Optional[Path]:
    class_dir, exam_name = _class_dir_for_exam(folder_safe, create_class_dir=create_class_dir)
    if not class_dir:
        return None
    return class_dir / f"{_safe_json_stem(exam_name)}.json"


def _exam_assets_dir(folder_safe: str, *, create_class_dir: bool = True) -> Optional[Path]:
    class_dir, exam_name = _class_dir_for_exam(folder_safe, create_class_dir=create_class_dir)
    if not class_dir:
        return None
    return class_dir / "assets" / _safe_json_stem(exam_name)


def _paper_assets_dir(folder_safe: str, paper_name: str, *, create: bool = True) -> Optional[Path]:
    exam_dir = _exam_assets_dir(folder_safe, create_class_dir=create)
    if not exam_dir:
        return None
    path = exam_dir / _safe_json_stem(Path(str(paper_name or "")).stem)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_class_wrong_question_dir(class_id: str) -> Path:
    token = _safe_class_token(class_id)
    if not token:
        raise ValueError("class_id 不能为空")
    path = _ct_root() / f"cls_{token}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cleanup_class_wrong_question_dir(class_id: str) -> None:
    token = _safe_class_token(class_id)
    if not token:
        return
    path = _ct_root() / f"cls_{token}"
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


def delete_exam_wrong_question_file(folder_safe: str) -> None:
    for path in (
        _record_json_path(folder_safe, create_class_dir=False),
        _analysis_json_path(folder_safe, create_class_dir=False),
        _legacy_exam_json_path(folder_safe, create_class_dir=False),
    ):
        if path and path.is_file():
            try:
                path.unlink()
            except Exception:
                pass
    assets = _exam_assets_dir(folder_safe, create_class_dir=False)
    if assets and assets.is_dir():
        shutil.rmtree(assets, ignore_errors=True)


def rename_exam_wrong_question_file(old_folder_safe: str, new_folder_safe: str) -> None:
    for old_path, new_path in (
        (
            _record_json_path(old_folder_safe, create_class_dir=False),
            _record_json_path(new_folder_safe),
        ),
        (
            _analysis_json_path(old_folder_safe, create_class_dir=False),
            _analysis_json_path(new_folder_safe),
        ),
        (
            _legacy_exam_json_path(old_folder_safe, create_class_dir=False),
            _legacy_exam_json_path(new_folder_safe, create_class_dir=True),
        ),
    ):
        if old_path and new_path and old_path.is_file():
            new_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                old_path.replace(new_path)
                _refresh_exam_metadata(new_folder_safe, new_path)
            except Exception:
                pass
    old_assets = _exam_assets_dir(old_folder_safe, create_class_dir=False)
    new_assets = _exam_assets_dir(new_folder_safe)
    if old_assets and new_assets and old_assets.is_dir() and old_assets != new_assets:
        try:
            if new_assets.exists():
                shutil.rmtree(new_assets, ignore_errors=True)
            new_assets.parent.mkdir(parents=True, exist_ok=True)
            old_assets.replace(new_assets)
        except Exception:
            pass


def remove_paper_from_exam_wrong_questions(folder_safe: str, paper_name: str) -> None:
    touched_paths: list[Path] = []
    for path in (
        _record_json_path(folder_safe, create_class_dir=False),
        _analysis_json_path(folder_safe, create_class_dir=False),
        _legacy_exam_json_path(folder_safe, create_class_dir=False),
    ):
        if path and path.is_file():
            _remove_paper_from_json(path, paper_name)
            touched_paths.append(path)
    paper_dir = _paper_assets_dir(folder_safe, paper_name, create=False)
    if paper_dir and paper_dir.is_dir():
        shutil.rmtree(paper_dir, ignore_errors=True)
    box_name = _paper_box_name(paper_name)
    if box_name and box_name != Path(str(paper_name or "")).stem:
        box_dir = _paper_assets_dir(folder_safe, box_name, create=False)
        source_prefix = _safe_json_stem(Path(str(paper_name or "")).stem)
        if box_dir and box_dir.is_dir():
            for old in box_dir.glob(f"{source_prefix}_q*_*.jpg"):
                try:
                    old.unlink()
                except Exception:
                    pass
            try:
                if not any(box_dir.iterdir()):
                    box_dir.rmdir()
            except Exception:
                pass
    for path in touched_paths:
        _delete_empty_exam_json(path)
    _cleanup_empty_exam_assets_dir(folder_safe)


def rename_paper_in_exam_wrong_questions(folder_safe: str, old_paper_name: str, new_paper_name: str) -> None:
    old_name = Path(str(old_paper_name or "")).name
    new_name = Path(str(new_paper_name or "")).name
    if not old_name or not new_name or old_name == new_name:
        return

    old_dir = _paper_assets_dir(folder_safe, old_name, create=False)
    new_dir = _paper_assets_path_no_create(folder_safe, new_name)
    replacements = _paper_asset_path_replacements(folder_safe, old_name, new_name)
    class_id, _ = _split_class_exam(folder_safe)
    _, students = _load_class_context(class_id)
    student = _infer_student_from_paper_name(new_name, students)

    with _ct_lock:
        for path in (
            _record_json_path(folder_safe, create_class_dir=False),
            _analysis_json_path(folder_safe, create_class_dir=False),
            _legacy_exam_json_path(folder_safe, create_class_dir=False),
        ):
            if path and path.is_file():
                _rename_paper_in_json_locked(path, old_name, new_name, student, replacements)

    if old_dir and new_dir and old_dir.is_dir() and old_dir != new_dir:
        try:
            new_dir.parent.mkdir(parents=True, exist_ok=True)
            if new_dir.exists():
                shutil.rmtree(new_dir, ignore_errors=True)
            old_dir.replace(new_dir)
        except Exception:
            pass


def upsert_baidu_wrong_questions(
    *,
    folder_safe: str,
    paper_name: str,
    raw_result: dict,
    blocks_with_result: Optional[list[dict]] = None,
    source_image_path: Optional[str] = None,
    run_ai_analysis: Optional[bool] = None,
) -> Optional[Path]:
    """将百度智能批改返回参数解析为每张试卷的错题 JSON 记录。"""
    source_paper_name = Path(str(paper_name or "")).name
    paper_name = _paper_box_name(source_paper_name)
    record_path = _record_json_path(folder_safe)
    analysis_path = _analysis_json_path(folder_safe)
    if not record_path or not analysis_path:
        return None

    class_id, exam_name = _split_class_exam(folder_safe)
    class_meta, students = _load_class_context(class_id)
    student = _infer_student_from_paper_name(paper_name, students)
    questions, wrong_questions, summary = _extract_wrong_questions(raw_result or {}, blocks_with_result or [])
    _tag_source_records(questions, source_paper_name=source_paper_name, paper_name=paper_name)
    _tag_source_records(wrong_questions, source_paper_name=source_paper_name, paper_name=paper_name)
    _attach_crops_and_analysis(
        folder_safe=folder_safe,
        paper_name=paper_name,
        wrong_questions=wrong_questions,
        source_image_path=source_image_path,
        run_ai_analysis=run_ai_analysis,
    )
    analysis_items = _split_analysis_from_wrong_questions(
        wrong_questions,
        paper_name=paper_name,
        analysis_file=analysis_path.name,
    )

    paper_record = {
        "paper_name": paper_name,
        "source_filenames": [source_paper_name],
        "student": student,
        "updated_at": _now(),
        "source": {
            "engine": "baidu",
            "provider": "baidu_correct_edu",
            "task_id": str((raw_result or {}).get("task_id") or "").strip(),
            "log_id": str((raw_result or {}).get("log_id") or "").strip(),
            "is_all_finished": bool((raw_result or {}).get("result", {}).get("isAllFinished", False)) if "result" in (raw_result or {}) else bool((raw_result or {}).get("isAllFinished", False)),
            "stat_result": (raw_result or {}).get("result", {}).get("stat_result") or {} if "result" in (raw_result or {}) else (raw_result or {}).get("stat_result") or {},
        },
        "summary": summary,
        "questions": questions,
        "wrong_questions": wrong_questions,
    }

    with _ct_lock:
        record_data = _read_json(record_path)
        if not record_data:
            record_data = _empty_exam_db(
                class_id,
                class_meta,
                folder_safe,
                exam_name,
                kind="wrong_question_records",
            )
        paper_record = _merge_baidu_paper_record(
            record_data.get("papers", {}).get(paper_name) if isinstance(record_data.get("papers"), dict) else None,
            paper_record,
            source_paper_name,
        )
        if source_paper_name != paper_name:
            _drop_legacy_page_record(record_data, source_paper_name)
        _upsert_paper_record(
            record_data,
            folder_safe=folder_safe,
            exam_name=exam_name,
            json_file=record_path.name,
            class_meta=class_meta,
            class_id=class_id,
            paper_name=paper_name,
            paper_record=paper_record,
        )
        _write_json(record_path, record_data)

        analysis_data = _read_json(analysis_path)
        if not analysis_data:
            analysis_data = _empty_exam_db(
                class_id,
                class_meta,
                folder_safe,
                exam_name,
                kind="wrong_question_analysis",
            )
        analysis_record = {
            "paper_name": paper_name,
            "source_filenames": [source_paper_name],
            "student": student,
            "updated_at": _now(),
            "source": paper_record["source"],
            "summary": _summarize_analysis_items(analysis_items),
            "wrong_question_analysis": analysis_items,
        }
        analysis_record = _merge_analysis_record(
            analysis_data.get("papers", {}).get(paper_name) if isinstance(analysis_data.get("papers"), dict) else None,
            analysis_record,
            source_paper_name,
        )
        if source_paper_name != paper_name:
            _drop_legacy_page_record(analysis_data, source_paper_name)
        _upsert_paper_record(
            analysis_data,
            folder_safe=folder_safe,
            exam_name=exam_name,
            json_file=analysis_path.name,
            class_meta=class_meta,
            class_id=class_id,
            paper_name=paper_name,
            paper_record=analysis_record,
            summary_fn=_summarize_analysis_exam,
        )
        _write_json(analysis_path, analysis_data)

        legacy_path = _legacy_exam_json_path(folder_safe, create_class_dir=False)
        if legacy_path and legacy_path.is_file():
            try:
                legacy_path.unlink()
            except Exception:
                pass
    return record_path


def _empty_exam_db(class_id: str, class_meta: dict, folder_safe: str, exam_name: str, *, kind: str) -> dict:
    return {
        "version": 1,
        "kind": kind,
        "created_at": _now(),
        "updated_at": _now(),
        "class": class_meta or {"id": class_id},
        "exam": {
            "folder_name": folder_safe,
            "name": exam_name,
        },
        "summary": {
            "paper_count": 0,
            "wrong_question_count": 0,
            "wrong_count": 0,
            "blank_count": 0,
        },
        "paper_order": [],
        "papers": {},
    }


def _tag_source_records(records: list[dict], *, source_paper_name: str, paper_name: str) -> None:
    page_stem = Path(str(source_paper_name or "")).stem
    source_prefix = _safe_json_stem(page_stem)
    for record in records:
        if not isinstance(record, dict):
            continue
        original_key = str(record.get("question_key") or "").strip()
        if original_key and not original_key.startswith(f"{source_prefix}_"):
            record["question_key"] = f"{source_prefix}_{original_key}"
        record["paper_name"] = paper_name
        record["source_filename"] = source_paper_name
        record["source_page"] = page_stem


def _summarize_question_records(questions: list[dict], wrong_questions: list[dict]) -> dict:
    counters = {
        "correct_count": 0,
        "wrong_count": 0,
        "blank_count": 0,
        "ungraded_count": 0,
        "total_answer_area_count": 0,
    }
    for item in questions:
        if isinstance(item, dict):
            _count_status(counters, _to_int(item.get("status_code"), 0))
    return {
        **counters,
        "question_count": len([x for x in questions if isinstance(x, dict)]),
        "wrong_question_count": len([x for x in wrong_questions if isinstance(x, dict)]),
        "collected_status": ["wrong", "blank"],
    }


def _merge_baidu_paper_record(existing: Any, incoming: dict, source_paper_name: str) -> dict:
    if not isinstance(existing, dict):
        return incoming
    merged = dict(existing)
    merged.update({k: v for k, v in incoming.items() if k not in ("questions", "wrong_questions", "source_filenames")})
    existing_questions = [
        x for x in existing.get("questions", [])
        if isinstance(x, dict) and x.get("source_filename") != source_paper_name
    ]
    existing_wrong = [
        x for x in existing.get("wrong_questions", [])
        if isinstance(x, dict) and x.get("source_filename") != source_paper_name
    ]
    incoming_questions = [x for x in incoming.get("questions", []) if isinstance(x, dict)]
    incoming_wrong = [x for x in incoming.get("wrong_questions", []) if isinstance(x, dict)]
    merged["questions"] = existing_questions + incoming_questions
    merged["wrong_questions"] = existing_wrong + incoming_wrong
    merged["source_filenames"] = _unique_list(
        list(existing.get("source_filenames") or []) + list(incoming.get("source_filenames") or []) + [source_paper_name]
    )
    merged["summary"] = _summarize_question_records(merged["questions"], merged["wrong_questions"])
    merged["updated_at"] = _now()
    return merged


def _merge_analysis_record(existing: Any, incoming: dict, source_paper_name: str) -> dict:
    if not isinstance(existing, dict):
        return incoming
    merged = dict(existing)
    merged.update({k: v for k, v in incoming.items() if k not in ("wrong_question_analysis", "source_filenames")})
    existing_items = [
        x for x in existing.get("wrong_question_analysis", [])
        if isinstance(x, dict) and x.get("source_filename") != source_paper_name
    ]
    incoming_items = [x for x in incoming.get("wrong_question_analysis", []) if isinstance(x, dict)]
    merged["wrong_question_analysis"] = existing_items + incoming_items
    merged["source_filenames"] = _unique_list(
        list(existing.get("source_filenames") or []) + list(incoming.get("source_filenames") or []) + [source_paper_name]
    )
    merged["summary"] = _summarize_analysis_items(merged["wrong_question_analysis"])
    merged["updated_at"] = _now()
    return merged


def _drop_legacy_page_record(data: dict, paper_name: str) -> None:
    papers = data.get("papers")
    if not isinstance(papers, dict):
        return
    papers.pop(paper_name, None)
    order = data.get("paper_order")
    if isinstance(order, list):
        data["paper_order"] = [x for x in order if x != paper_name]


def _upsert_paper_record(
    data: dict,
    *,
    folder_safe: str,
    exam_name: str,
    json_file: str,
    class_meta: dict,
    class_id: str,
    paper_name: str,
    paper_record: dict,
    summary_fn=None,
) -> None:
    data["class"] = class_meta or data.get("class") or {"id": class_id}
    data["exam"] = {
        "folder_name": folder_safe,
        "name": exam_name,
        "json_file": json_file,
    }
    data["updated_at"] = _now()
    papers = data.setdefault("papers", {})
    if not isinstance(papers, dict):
        papers = {}
        data["papers"] = papers
    papers[paper_name] = paper_record
    order = data.setdefault("paper_order", [])
    if not isinstance(order, list):
        order = []
        data["paper_order"] = order
    if paper_name not in order:
        order.append(paper_name)
    data["summary"] = (summary_fn or _summarize_exam)(papers)


def _remove_paper_from_json(path: Path, paper_name: str) -> None:
    with _ct_lock:
        data = _read_json(path)
        papers = data.get("papers")
        if not isinstance(papers, dict):
            return
        source_name = Path(str(paper_name or "")).name
        box_name = _paper_box_name(source_name)
        papers.pop(str(source_name or ""), None)
        if box_name in papers and box_name != source_name:
            record = papers.get(box_name)
            if isinstance(record, dict):
                if data.get("kind") == "wrong_question_analysis":
                    items = [
                        x for x in record.get("wrong_question_analysis", [])
                        if isinstance(x, dict) and x.get("source_filename") != source_name
                    ]
                    record["wrong_question_analysis"] = items
                    record["summary"] = _summarize_analysis_items(items)
                    remaining_sources = _unique_list([x.get("source_filename") for x in items if isinstance(x, dict)])
                else:
                    questions = [
                        x for x in record.get("questions", [])
                        if isinstance(x, dict) and x.get("source_filename") != source_name
                    ]
                    wrong_questions = [
                        x for x in record.get("wrong_questions", [])
                        if isinstance(x, dict) and x.get("source_filename") != source_name
                    ]
                    record["questions"] = questions
                    record["wrong_questions"] = wrong_questions
                    record["summary"] = _summarize_question_records(questions, wrong_questions)
                    remaining_sources = _unique_list([x.get("source_filename") for x in questions if isinstance(x, dict)])
                record["source_filenames"] = remaining_sources
                record["updated_at"] = _now()
                if not remaining_sources:
                    papers.pop(box_name, None)
        order = data.get("paper_order")
        if isinstance(order, list):
            data["paper_order"] = [x for x in order if x not in (source_name, box_name) or x in papers]
        if data.get("kind") == "wrong_question_analysis":
            data["summary"] = _summarize_analysis_exam(papers)
        else:
            data["summary"] = _summarize_exam(papers)
        data["updated_at"] = _now()
        _write_json(path, data)


def _delete_empty_exam_json(path: Path) -> None:
    data = _read_json(path)
    papers = data.get("papers")
    if isinstance(papers, dict) and papers:
        return
    try:
        path.unlink()
    except Exception:
        pass


def _cleanup_empty_exam_assets_dir(folder_safe: str) -> None:
    assets = _exam_assets_dir(folder_safe, create_class_dir=False)
    if not assets or not assets.is_dir():
        return
    try:
        if any(assets.iterdir()):
            return
        assets.rmdir()
    except Exception:
        pass


def _paper_assets_path_no_create(folder_safe: str, paper_name: str) -> Optional[Path]:
    exam_dir = _exam_assets_dir(folder_safe, create_class_dir=False)
    if not exam_dir:
        return None
    return exam_dir / _safe_json_stem(Path(str(paper_name or "")).stem)


def _paper_asset_path_replacements(folder_safe: str, old_paper_name: str, new_paper_name: str) -> list[tuple[str, str]]:
    old_dir = _paper_assets_path_no_create(folder_safe, old_paper_name)
    new_dir = _paper_assets_path_no_create(folder_safe, new_paper_name)
    if not old_dir or not new_dir:
        return []
    pairs: list[tuple[str, str]] = [
        (str(old_dir), str(new_dir)),
        (old_dir.as_posix(), new_dir.as_posix()),
    ]
    try:
        root = _grading_data_root()
        pairs.append((old_dir.relative_to(root).as_posix(), new_dir.relative_to(root).as_posix()))
    except Exception:
        pass
    out: list[tuple[str, str]] = []
    seen = set()
    for old, new in pairs:
        if old and old != new and (old, new) not in seen:
            out.append((old, new))
            seen.add((old, new))
    return out


def _rename_paper_in_json_locked(
    path: Path,
    old_paper_name: str,
    new_paper_name: str,
    student: dict,
    replacements: list[tuple[str, str]],
) -> None:
    data = _read_json(path)
    papers = data.get("papers")
    if not isinstance(papers, dict) or old_paper_name not in papers:
        return

    record = papers.pop(old_paper_name)
    record = _replace_paper_refs(record, old_paper_name, new_paper_name, replacements)
    if isinstance(record, dict):
        record["paper_name"] = new_paper_name
        record["student"] = student
        record["updated_at"] = _now()
    papers[new_paper_name] = record

    order = data.get("paper_order")
    if isinstance(order, list):
        renamed_order = [new_paper_name if x == old_paper_name else x for x in order]
        data["paper_order"] = list(dict.fromkeys(renamed_order))
        if new_paper_name not in data["paper_order"]:
            data["paper_order"].append(new_paper_name)

    if data.get("kind") == "wrong_question_analysis":
        data["summary"] = _summarize_analysis_exam(papers)
    else:
        data["summary"] = _summarize_exam(papers)
    data["updated_at"] = _now()
    _write_json(path, data)


def _replace_paper_refs(value: Any, old_paper_name: str, new_paper_name: str, replacements: list[tuple[str, str]]) -> Any:
    if isinstance(value, dict):
        return {
            key: _replace_paper_refs(
                new_paper_name if key == "paper_name" and val == old_paper_name else val,
                old_paper_name,
                new_paper_name,
                replacements,
            )
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [_replace_paper_refs(item, old_paper_name, new_paper_name, replacements) for item in value]
    if isinstance(value, str):
        if value == old_paper_name:
            return new_paper_name
        out = value
        for old, new in replacements:
            out = out.replace(old, new)
        return out
    return value


def _split_analysis_from_wrong_questions(wrong_questions: list[dict], *, paper_name: str, analysis_file: str) -> list[dict]:
    out: list[dict] = []
    for wq in wrong_questions:
        if not isinstance(wq, dict):
            continue
        analysis = wq.pop("analysis", _empty_analysis("skipped", "未生成分析"))
        assets = wq.get("assets") if isinstance(wq.get("assets"), dict) else {}
        ref = {
            "analysis_file": analysis_file,
            "paper_name": paper_name,
            "question_key": wq.get("question_key"),
            "source_filename": wq.get("source_filename"),
        }
        wq["analysis_ref"] = ref
        out.append(
            {
                "question_key": wq.get("question_key"),
                "display_title": wq.get("display_title"),
                "paper_name": paper_name,
                "source_filename": wq.get("source_filename"),
                "source_page": wq.get("source_page"),
                "status": wq.get("status"),
                "status_code": wq.get("status_code"),
                "question_index": wq.get("question_index"),
                "slot_index": wq.get("slot_index"),
                "question_id": wq.get("question_id"),
                "paper_subject": wq.get("paper_subject"),
                "question_type": wq.get("question_type"),
                "baidu_reason": wq.get("reason"),
                "assets": assets,
                "analysis": analysis,
            }
        )
    return out


def _refresh_exam_metadata(folder_safe: str, path: Path) -> None:
    class_id, exam_name = _split_class_exam(folder_safe)
    with _ct_lock:
        data = _read_json(path)
        if not data:
            return
        data["exam"] = {
            "folder_name": folder_safe,
            "name": exam_name,
            "json_file": path.name,
        }
        data["updated_at"] = _now()
        _write_json(path, data)


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_class_context(class_id: str) -> tuple[dict, list[dict]]:
    class_meta = {"id": class_id}
    students: list[dict] = []
    if not class_id:
        return class_meta, students
    try:
        from app.database import SessionLocal
        from app.models.class_model import Class
        from app.models.student import Student
    except Exception:
        return class_meta, students

    db = SessionLocal()
    try:
        c = db.query(Class).filter(Class.id == class_id).first()
        if c:
            class_meta = {
                "id": c.id,
                "name": c.name,
                "grade": c.grade,
                "school_level": c.school_level,
                "user_id": c.user_id,
            }
        rows = db.query(Student).filter(Student.class_id == class_id).all()
        students = [
            {
                "id": s.id,
                "name": s.name,
                "student_number": s.student_number,
                "class_id": s.class_id,
            }
            for s in rows
        ]
    except Exception:
        pass
    finally:
        try:
            db.close()
        except Exception:
            pass
    return class_meta, students


def _norm_identity(text: Any) -> str:
    s = str(text or "").strip().lower()
    return re.sub(r"[\s_\-－—.。·,，()（）\[\]【】{}《》<>]+", "", s)


def _infer_student_from_paper_name(paper_name: str, students: list[dict]) -> dict:
    stem = _paper_box_name(paper_name)
    norm_stem = _norm_identity(stem)
    fallback = {
        "id": None,
        "name": stem,
        "matched_by": "paper_name",
        "matched": False,
    }
    if not norm_stem or not students:
        return fallback

    candidates = []
    for s in students:
        name_norm = _norm_identity(s.get("name"))
        num_norm = _norm_identity(s.get("student_number"))
        if name_norm and norm_stem == name_norm:
            return _student_match(s, "name_exact")
        if num_norm and norm_stem == num_norm:
            return _student_match(s, "student_number_exact")
        if name_norm and len(name_norm) >= 2 and name_norm in norm_stem:
            candidates.append((len(name_norm), s, "name_contains"))
        elif num_norm and len(num_norm) >= 2 and num_norm in norm_stem:
            candidates.append((len(num_norm), s, "student_number_contains"))

    if candidates:
        _, s, matched_by = sorted(candidates, key=lambda x: x[0], reverse=True)[0]
        return _student_match(s, matched_by)
    return fallback


def _student_match(student: dict, matched_by: str) -> dict:
    # E09：学籍号(L4)不再进入出参/持久化 student 对象——仅用于内部按姓名/学号匹配，
    # 落盘与 AI 上下文不再携带 student_number（见 docs/contracts/13-data-classification.md）。
    return {
        "id": student.get("id"),
        "name": student.get("name"),
        "matched_by": matched_by,
        "matched": True,
    }


def _extract_wrong_questions(raw_result: dict, blocks_with_result: list[dict]) -> tuple[list[dict], list[dict], dict]:
    questions: list[dict] = []
    wrong_questions: list[dict] = []
    counters = {
        "correct_count": 0,
        "wrong_count": 0,
        "blank_count": 0,
        "ungraded_count": 0,
        "total_answer_area_count": 0,
    }
    block_map = _build_block_map(blocks_with_result)

    if "imageResults" in raw_result:
        image_results = raw_result.get("imageResults") or []
    else:
        image_results = raw_result.get("result", {}).get("imageResults") or []

    for image_index, image_item in enumerate(image_results, start=1):
        paper_subject = str((image_item or {}).get("paperSubject") or "").strip()
        for q in ((image_item or {}).get("result") or []):
            if not isinstance(q, dict):
                continue
            q_zero = _to_int(q.get("seqence"), 0)
            q_index = q_zero + 1
            q_correct = _to_int(q.get("correctResult"), 0)
            slots = q.get("slot") or []
            if isinstance(slots, list) and slots:
                for slot in slots:
                    if not isinstance(slot, dict):
                        continue
                    s_index = _to_int(slot.get("seqence"), 1)
                    status_code = _to_int(slot.get("correctResult"), q_correct)
                    _count_status(counters, status_code)
                    blk = block_map.get((q_index, s_index)) or {}
                    record = _wrong_question_record(
                        image_index=image_index,
                        paper_subject=paper_subject,
                        q=q,
                        q_index=q_index,
                        q_correct=q_correct,
                        slot=slot,
                        slot_index=s_index,
                        status_code=status_code,
                        block=blk,
                    )
                    questions.append(record)
                    if status_code in (2, 3):
                        wrong_questions.append(record)
            else:
                _count_status(counters, q_correct)
                blk = block_map.get((q_index, 1)) or {}
                record = _wrong_question_record(
                    image_index=image_index,
                    paper_subject=paper_subject,
                    q=q,
                    q_index=q_index,
                    q_correct=q_correct,
                    slot=None,
                    slot_index=1,
                    status_code=q_correct,
                    block=blk,
                )
                questions.append(record)
                if q_correct in (2, 3):
                    wrong_questions.append(record)

    summary = {
        **counters,
        "question_count": len(questions),
        "wrong_question_count": len(wrong_questions),
        "collected_status": ["错误", "未作答"],
    }
    return questions, wrong_questions, summary


def _build_block_map(blocks: list[dict]) -> dict[tuple[int, int], dict]:
    out = {}
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        q_index = _to_int(b.get("baidu_original_index", b.get("index")), 0)
        s_index = _to_int(b.get("sub_index"), 1)
        if q_index > 0:
            out[(q_index, s_index)] = b
    return out


def _wrong_question_record(
    *,
    image_index: int,
    paper_subject: str,
    q: dict,
    q_index: int,
    q_correct: int,
    slot: Optional[dict],
    slot_index: int,
    status_code: int,
    block: dict,
) -> dict:
    display_index = _to_int(block.get("index"), q_index) if block else q_index
    record = {
        "question_key": f"q{q_index}_s{slot_index}",
        "display_title": f"第{display_index}题-作答区{slot_index}" if slot else f"第{display_index}题",
        "image_index": image_index,
        "paper_subject": paper_subject,
        "question_index": q_index,
        "slot_index": slot_index,
        "status_code": status_code,
        "status": _status_text(status_code),
        "question_correct_result": q_correct,
        "question_id": str(q.get("questionId") or "").strip(),
        "question": str(q.get("question") or "").strip(),
        "question_type": _question_type(q),
        "question_area": q.get("questionArea") or [],
        "crop_url": str(q.get("cropUrl") or "").strip(),
        "is_finish": bool(q.get("isFinish", False)),
        "reason": str(((slot or {}).get("reason") if slot else q.get("reason")) or "").strip(),
        "baidu": {
            "question_seqence": q.get("seqence"),
            "slot_seqence": (slot or {}).get("seqence") if slot else None,
            "correct_result": status_code,
        },
    }
    if slot:
        record["slot_id"] = str(slot.get("slotId") or "").strip()
        record["handwriting_area"] = slot.get("handwritingArea") or {}
    else:
        record["slot_id"] = ""
        record["handwriting_area"] = {}
    if block:
        record["render"] = {
            "display_index": display_index,
            "bbox": block.get("bbox"),
            "comment": block.get("comment", ""),
        }
    return record


def _attach_crops_and_analysis(
    *,
    folder_safe: str,
    paper_name: str,
    wrong_questions: list[dict],
    source_image_path: Optional[str],
    run_ai_analysis: Optional[bool],
) -> None:
    if not wrong_questions:
        return

    paper_dir = _paper_assets_dir(folder_safe, paper_name)
    if not paper_dir:
        return

    source_prefix = ""
    first_record = wrong_questions[0] if wrong_questions else {}
    if isinstance(first_record, dict):
        source_prefix = _safe_json_stem(Path(str(first_record.get("source_filename") or "")).stem)
    cleanup_patterns = [f"{source_prefix}_q*_*.jpg"] if source_prefix else ["q*_*.jpg"]
    for pattern in cleanup_patterns:
        for old in paper_dir.glob(pattern):
            try:
                old.unlink()
            except Exception:
                pass

    source_path = Path(str(source_image_path or ""))
    if not source_path.is_file():
        for wq in wrong_questions:
            wq["assets"] = {
                "status": "missing_source_image",
                "message": "未找到本地试卷图片，无法裁剪错题图",
            }
            wq["analysis"] = _empty_analysis("skipped", "未找到本地试卷图片")
        return

    try:
        from PIL import Image
    except Exception:
        for wq in wrong_questions:
            wq["assets"] = {"status": "pillow_missing", "message": "未安装 Pillow，无法裁剪错题图"}
            wq["analysis"] = _empty_analysis("skipped", "未安装 Pillow")
        return

    try:
        with Image.open(str(source_path)) as img0:
            img = img0.convert("RGB")
            for wq in wrong_questions:
                _save_wrong_question_assets(
                    image=img,
                    paper_dir=paper_dir,
                    grading_data_root=_grading_data_root(),
                    record=wq,
                )
    except Exception as e:
        for wq in wrong_questions:
            wq["assets"] = {"status": "crop_failed", "message": str(e)}
            wq["analysis"] = _empty_analysis("skipped", f"裁剪失败：{e}")
        return

    if not _ai_analysis_enabled(run_ai_analysis):
        for wq in wrong_questions:
            wq["analysis"] = _empty_analysis("disabled", "AI 错题分析已关闭")
        return

    max_items = max(0, int(os.environ.get("WRONG_QUESTION_ANALYSIS_MAX_PER_PAPER", "20") or "20"))
    for idx, wq in enumerate(wrong_questions):
        if idx >= max_items:
            wq["analysis"] = _empty_analysis("skipped", "超过单张试卷错题分析数量上限")
            continue
        assets = wq.get("assets") if isinstance(wq.get("assets"), dict) else {}
        question_image = (assets.get("question_image") or {}).get("absolute_path") if isinstance(assets.get("question_image"), dict) else ""
        answer_image = (assets.get("answer_image") or {}).get("absolute_path") if isinstance(assets.get("answer_image"), dict) else ""
        wq["analysis"] = _analyze_wrong_question_with_vl(wq, question_image, answer_image)


def _save_wrong_question_assets(*, image, paper_dir: Path, grading_data_root: Path, record: dict) -> None:
    key = _safe_asset_stem(record.get("question_key") or "wrong")
    q_bbox = _bbox_from_area(record.get("question_area"))
    a_bbox = _bbox_from_area(record.get("handwriting_area"))
    render_bbox = record.get("render", {}).get("bbox") if isinstance(record.get("render"), dict) else None
    if not a_bbox and isinstance(render_bbox, list):
        a_bbox = _bbox_from_sequence(render_bbox)

    assets = {"status": "ok"}
    q_path = paper_dir / f"{key}_question.jpg"
    q_saved = _crop_and_save(image, q_bbox, q_path, pad=12)
    if q_saved:
        assets["question_image"] = _asset_info(q_path, grading_data_root, q_bbox)
    else:
        assets["question_image"] = {"status": "missing_bbox", "message": "百度未返回有效题目坐标"}

    a_path = paper_dir / f"{key}_answer.jpg"
    a_saved = _crop_and_save(image, a_bbox, a_path, pad=18)
    if a_saved:
        assets["answer_image"] = _asset_info(a_path, grading_data_root, a_bbox)
    else:
        assets["answer_image"] = {"status": "missing_bbox", "message": "百度未返回有效作答区坐标"}

    record["assets"] = assets


def _crop_and_save(image, bbox: Optional[list[int]], out_path: Path, *, pad: int) -> bool:
    if not bbox:
        return False
    w, h = image.size
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(w - 1, x1 - pad))
    y1 = max(0, min(h - 1, y1 - pad))
    x2 = max(1, min(w, x2 + pad))
    y2 = max(1, min(h, y2 + pad))
    if x2 <= x1 or y2 <= y1:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.crop((x1, y1, x2, y2)).save(str(out_path), quality=94)
    return True


def _asset_info(path: Path, grading_data_root: Path, bbox: Optional[list[int]]) -> dict:
    try:
        rel = path.relative_to(grading_data_root).as_posix()
    except Exception:
        rel = path.as_posix()
    return {
        "absolute_path": str(path),
        "relative_to_grading_data": rel,
        "bbox": bbox,
    }


def _bbox_from_area(area: Any) -> Optional[list[int]]:
    if isinstance(area, list):
        if not area:
            return None
        first = area[0]
        if isinstance(first, dict):
            return _bbox_from_area(first)
        return _bbox_from_sequence(area)
    if isinstance(area, dict):
        return _normalize_bbox(
            [
                area.get("left_x"),
                area.get("left_y"),
                area.get("right_x"),
                area.get("right_y"),
            ]
        )
    return None


def _bbox_from_sequence(values: Any) -> Optional[list[int]]:
    if not isinstance(values, (list, tuple)) or len(values) < 4:
        return None
    return _normalize_bbox(values[:4])


def _normalize_bbox(values: Any) -> Optional[list[int]]:
    try:
        x1, y1, x2, y2 = [int(float(v)) for v in values]
    except Exception:
        return None
    if x2 <= x1 or y2 <= y1:
        return None
    return [x1, y1, x2, y2]


def _safe_asset_stem(name: Any) -> str:
    raw = str(name or "").strip() or "wrong"
    cleaned = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in raw)
    return cleaned[:80] or "wrong"


def _ai_analysis_enabled(value: Optional[bool]) -> bool:
    if value is not None:
        return bool(value)
    raw = str(os.environ.get("WRONG_QUESTION_ANALYSIS_ENABLED", "1")).strip().lower()
    return raw not in ("0", "false", "no", "off")


def _empty_analysis(status: str, message: str = "") -> dict:
    return {
        "status": status,
        "message": message,
        "question_text": "",
        "student_answer": "",
        "estimated_correct_answer": "",
        "knowledge_points": [],
        "error_type": "",
        "error_reason": "",
        "explanation": "",
        "suggestion": "",
        "confidence": "unknown",
        "answer_source": "unknown",
        "needs_teacher_review": True,
    }


def _analyze_wrong_question_with_vl(record: dict, question_image_path: str, answer_image_path: str) -> dict:
    if not question_image_path or not Path(question_image_path).is_file():
        return _empty_analysis("skipped", "缺少错题题目裁剪图")
    try:
        from PIL import Image
        from app.grading.pipeline import _get_openai_client, _pil_image_to_data_url
        from app.utils.qwen_settings import QWEN_CHAT_EXTRA_BODY, resolve_qwen_model
    except Exception as e:
        return _empty_analysis("failed", f"分析依赖不可用：{e}")

    try:
        q_img = Image.open(question_image_path).convert("RGB")
        q_url = _pil_image_to_data_url(q_img, max_side=1600, quality=92)
        content = [
            {"type": "image_url", "image_url": {"url": q_url}},
        ]
        if answer_image_path and Path(answer_image_path).is_file():
            a_img = Image.open(answer_image_path).convert("RGB")
            a_url = _pil_image_to_data_url(a_img, max_side=900, quality=92)
            content.append({"type": "image_url", "image_url": {"url": a_url}})
        content.append({"type": "text", "text": _analysis_prompt(record)})

        client = _get_openai_client()
        model = resolve_qwen_model(env_var="WRONG_QUESTION_ANALYSIS_MODEL")
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            stream=False,
            extra_body=QWEN_CHAT_EXTRA_BODY,
        )
        text = (completion.choices[0].message.content or "").strip()
        parsed = _parse_json_object(text)
        if not parsed:
            return {**_empty_analysis("failed", "模型未返回合法 JSON"), "raw_text": text[:1000]}
        return _normalize_analysis(parsed)
    except Exception as e:
        return _empty_analysis("failed", str(e))


def _analysis_prompt(record: dict) -> str:
    return f"""你是一名教师助手，正在为错题库生成结构化错题分析。

输入图片：
图1是该错题所在区域的裁剪图，可能包含题干、图形、选项和学生作答。
图2如果存在，是学生作答区域的裁剪图。

百度批改信息：
题目：{record.get("display_title") or ""}
学科：{record.get("paper_subject") or ""}
题型编号：{record.get("question_type")}
判定：{record.get("status") or ""}
百度原因：{record.get("reason") or ""}

请只输出一个合法 JSON，不要 Markdown，不要解释。字段如下：
{{
  "question_text": "尽量识别题干；如果图片不清楚则写空字符串",
  "student_answer": "尽量识别学生作答；未作答则写空字符串",
  "estimated_correct_answer": "根据题图和批改原因推断参考答案；无法可靠推断则写空字符串",
  "knowledge_points": ["知识点1", "知识点2"],
  "error_type": "概念理解错误/计算错误/审题错误/步骤不完整/表达不规范/未作答/其他",
  "error_reason": "一句话说明错因",
  "explanation": "面向学生的简短讲解，80字以内",
  "suggestion": "后续练习建议，60字以内",
  "confidence": "high/medium/low",
  "answer_source": "ai_inferred/baidu_reason/unknown",
  "needs_teacher_review": true 或 false
}}

注意：
1. 没有标准答案时，estimated_correct_answer 只能是推断答案，confidence 不要轻易写 high。
2. 如果题图或学生答案识别不清，保留空字符串并把 needs_teacher_review 设为 true。
3. 不要编造看不清的题干细节。"""


def _parse_json_object(text: str) -> dict:
    raw = (text or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if m:
        raw = m.group(1).strip()
    start = raw.find("{")
    if start < 0:
        return {}
    depth = 0
    for i in range(start, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(raw[start : i + 1])
                    return data if isinstance(data, dict) else {}
                except Exception:
                    return {}
    return {}


def _normalize_analysis(data: dict) -> dict:
    points = data.get("knowledge_points")
    if not isinstance(points, list):
        points = []
    normalized = {
        "status": "done",
        "message": "",
        "question_text": str(data.get("question_text") or "").strip(),
        "student_answer": str(data.get("student_answer") or "").strip(),
        "estimated_correct_answer": str(data.get("estimated_correct_answer") or "").strip(),
        "knowledge_points": [str(x).strip() for x in points if str(x).strip()][:8],
        "error_type": str(data.get("error_type") or "其他").strip() or "其他",
        "error_reason": str(data.get("error_reason") or "").strip(),
        "explanation": str(data.get("explanation") or "").strip(),
        "suggestion": str(data.get("suggestion") or "").strip(),
        "confidence": str(data.get("confidence") or "unknown").strip().lower() or "unknown",
        "answer_source": str(data.get("answer_source") or "unknown").strip().lower() or "unknown",
        "needs_teacher_review": bool(data.get("needs_teacher_review", True)),
    }
    if normalized["confidence"] not in ("high", "medium", "low", "unknown"):
        normalized["confidence"] = "unknown"
    if normalized["answer_source"] not in ("ai_inferred", "baidu_reason", "unknown"):
        normalized["answer_source"] = "unknown"
    return normalized


def _question_type(q: dict) -> Any:
    for key in ("questionType", "question_type", "type", "qusType", "qus_type"):
        if key in q:
            return q.get(key)
    return None


def _count_status(counters: dict, code: int) -> None:
    counters["total_answer_area_count"] += 1
    if code == 1:
        counters["correct_count"] += 1
    elif code == 2:
        counters["wrong_count"] += 1
    elif code == 3:
        counters["blank_count"] += 1
    else:
        counters["ungraded_count"] += 1


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _status_text(code: int) -> str:
    return {0: "未批", 1: "正确", 2: "错误", 3: "未作答"}.get(code, "未知")


def _summarize_exam(papers: dict) -> dict:
    summary = {
        "paper_count": len(papers),
        "wrong_question_count": 0,
        "wrong_count": 0,
        "blank_count": 0,
        "correct_count": 0,
        "ungraded_count": 0,
        "total_answer_area_count": 0,
    }
    for paper in papers.values():
        if not isinstance(paper, dict):
            continue
        s = paper.get("summary") if isinstance(paper.get("summary"), dict) else {}
        for key in (
            "wrong_question_count",
            "wrong_count",
            "blank_count",
            "correct_count",
            "ungraded_count",
            "total_answer_area_count",
        ):
            summary[key] += int(s.get(key, 0) or 0)
    return summary


def _summarize_analysis_items(items: list[dict]) -> dict:
    summary = {
        "analysis_count": len(items),
        "done_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "disabled_count": 0,
        "needs_teacher_review_count": 0,
    }
    for item in items:
        analysis = item.get("analysis") if isinstance(item, dict) else {}
        if not isinstance(analysis, dict):
            analysis = {}
        status = str(analysis.get("status") or "unknown").lower()
        if status == "done":
            summary["done_count"] += 1
        elif status == "disabled":
            summary["disabled_count"] += 1
        elif status == "skipped":
            summary["skipped_count"] += 1
        else:
            summary["failed_count"] += 1
        if bool(analysis.get("needs_teacher_review", True)):
            summary["needs_teacher_review_count"] += 1
    return summary


def _summarize_analysis_exam(papers: dict) -> dict:
    summary = {
        "paper_count": len(papers),
        "analysis_count": 0,
        "done_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "disabled_count": 0,
        "needs_teacher_review_count": 0,
    }
    for paper in papers.values():
        if not isinstance(paper, dict):
            continue
        s = paper.get("summary") if isinstance(paper.get("summary"), dict) else {}
        for key in (
            "analysis_count",
            "done_count",
            "failed_count",
            "skipped_count",
            "disabled_count",
            "needs_teacher_review_count",
        ):
            summary[key] += int(s.get(key, 0) or 0)
    return summary
