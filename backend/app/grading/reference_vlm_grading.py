# -*- coding: utf-8 -*-
"""Reference-answer grading based on Baidu paper_cut_edu_vlm + Qwen vision.

This module intentionally owns its own split-only JSON parsing and artifact
writing for reference-answer grading.
"""
from __future__ import annotations

import base64
import copy
import json
import os
import re
import shutil
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - reported at runtime
    OpenAI = None

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps
except ImportError:  # pragma: no cover - reported at runtime
    Image = None
    ImageDraw = None
    ImageEnhance = None
    ImageFilter = None
    ImageOps = None

from app.grading.baidu_grading import (
    _build_url,
    _check_baidu_api_error,
    _create_rate_limiter,
    _post_json,
)
from app.grading.doc_convert import enhance_for_ocr, ensure_image_path
from app.grading.pipeline import draw_marks_only_and_save, draw_real_marks_and_save, draw_manual_annotations, draw_blank_area_cross
from app.grading.user_paths import correct_docs_dir, ct_root, grading_paths
from app.utils.qwen_settings import DEFAULT_QWEN_MODEL, QWEN_CHAT_EXTRA_BODY, get_qwen_config
from app.grading.wrong_question_db import _infer_student_from_paper_name, _load_class_context


PAPER_CUT_VLM_CREATE_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/paper_cut_edu_vlm/create_task"

CORRECT = 1
WRONG = 2
UNANSWERED = 3
PARTIAL = 4

RESULT_TEXT = {
    CORRECT: "对",
    WRONG: "错",
    UNANSWERED: "未作答",
    PARTIAL: "半对",
}

_artifact_lock = threading.Lock()


@dataclass
class VlmQuestion:
    question_id: int
    display_index: int
    raw: dict
    bbox: list[int]
    question_bbox: list[int]
    answer_bbox: Optional[list[int]]
    answer_bboxes: list[list[int]]
    question_words: str
    answer_words: list[str]
    choices: list[str]
    question_type: str
    # A question may depend on several disjoint visual regions (for example a
    # stem on the left and a large diagram on the right).  question_bbox is
    # still kept as the union for compatibility with the existing pipeline.
    question_regions: list[list[int]] = field(default_factory=list)


@dataclass
class VlmGradingTask:
    task_id: int
    student_question: VlmQuestion
    standard_question: VlmQuestion
    student_answer_bbox: list[int]
    standard_answer_bbox: list[int]
    student_context_bbox: list[int]
    standard_context_bbox: list[int]
    sub_index: int
    has_mark_anchor: bool
    has_handwriting_location: bool
    is_answer_slot: bool
    anchor_source: str
    template_slot_id: Optional[int]


@dataclass
class VlmQuestionBatchTask:
    """One Qwen request containing all answer slots of one parent question."""

    batch_id: int
    student_question: VlmQuestion
    standard_question: VlmQuestion
    slots: list[VlmGradingTask]


@dataclass(frozen=True)
class VlmSlotTemplate:
    slot_id: int
    normalized_bbox: tuple[float, float, float, float]
    relative_bbox: tuple[float, float, float, float]
    question_index: int
    support_count: int
    source_keys: tuple[str, ...]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_text(value: Any, limit: int = 1200) -> str:
    if isinstance(value, list):
        text = "\n".join(str(x or "").strip() for x in value if str(x or "").strip())
    else:
        text = str(value or "").strip()
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    if len(text) > limit:
        return text[:limit] + "..."
    return text


_MATH_SUPERSCRIPT = str.maketrans(
    "0123456789+-nxy",
    "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻ⁿˣʸ",
)
_MATH_SUBSCRIPT = str.maketrans(
    "0123456789+-n",
    "₀₁₂₃₄₅₆₇₈₉₊₋ₙ",
)


def _math_fraction_text(numerator: str, denominator: str) -> str:
    numerator = numerator.strip()
    denominator = denominator.strip()
    if re.search(r"[\s+\-*/=]", numerator):
        numerator = f"({numerator})"
    if re.search(r"[\s+\-*/=]", denominator):
        denominator = f"({denominator})"
    return f"{numerator}⁄{denominator}"


def _normalize_math_text(value: Any) -> str:
    """Convert common model-generated math markup into readable Unicode."""
    text = str(value or "")
    if not text:
        return ""

    text = re.sub(r"\$\$([\s\S]+?)\$\$", lambda match: match.group(1), text)
    text = re.sub(r"\$([^$\n]+?)\$", lambda match: match.group(1), text)
    for _ in range(4):
        updated = re.sub(
            r"\\(?:dfrac|tfrac|frac)\{([^{}]+)\}\{([^{}]+)\}",
            lambda match: _math_fraction_text(match.group(1), match.group(2)),
            text,
        )
        if updated == text:
            break
        text = updated

    text = re.sub(
        r"\\sqrt\[(\d+)\]\{([^{}]+)\}",
        lambda match: f"{match.group(1)}√({match.group(2)})",
        text,
    )
    text = re.sub(r"\\sqrt\{([^{}]+)\}", lambda match: f"√({match.group(1)})", text)
    replacements = (
        (r"\\times\b", "×"),
        (r"\\div\b", "÷"),
        (r"\\cdot\b", "·"),
        (r"\\pm\b", "±"),
        (r"\\mp\b", "∓"),
        (r"\\leq?\b", "≤"),
        (r"\\geq?\b", "≥"),
        (r"\\ne(?:q)?\b", "≠"),
        (r"\\approx\b", "≈"),
        (r"\\infty\b", "∞"),
        (r"\\pi\b", "π"),
        (r"\\alpha\b", "α"),
        (r"\\beta\b", "β"),
        (r"\\gamma\b", "γ"),
        (r"\\theta\b", "θ"),
        (r"\\Delta\b", "Δ"),
        (r"\\(?:degree|circ)\b", "°"),
        (r"\\(?:left|right)\b", ""),
        (r"\\(?:quad|qquad)\b", " "),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"\\(?:text|mathrm)\{([^{}]*)\}", lambda match: match.group(1), text)
    text = re.sub(
        r"\^\{([0-9+\-nxy]+)\}",
        lambda match: match.group(1).translate(_MATH_SUPERSCRIPT),
        text,
    )
    text = re.sub(
        r"\^([0-9+\-nxy]+)",
        lambda match: match.group(1).translate(_MATH_SUPERSCRIPT),
        text,
    )
    text = re.sub(
        r"_\{([0-9+\-n]+)\}",
        lambda match: match.group(1).translate(_MATH_SUBSCRIPT),
        text,
    )
    text = re.sub(
        r"_([0-9+\-n]+)",
        lambda match: match.group(1).translate(_MATH_SUBSCRIPT),
        text,
    )
    text = re.sub(r"\\([A-Za-z]+)", lambda match: match.group(1), text)
    text = text.replace("$", "")
    return re.sub(r"[ \t]+", " ", text).strip()


def _safe_json_stem(name: Any) -> str:
    raw = str(name or "").strip() or "unnamed"
    cleaned = "".join(c for c in raw if c not in '/\\:*?"<>|').strip()
    return cleaned[:120] or "unnamed"


def _paper_box_name(paper_name: str) -> str:
    stem = Path(str(paper_name or "")).stem.strip()
    match = re.match(r"^(?P<name>.+)_\d+$", stem)
    return (match.group("name") if match else stem).strip() or stem or "unnamed"


def _paper_page_no(paper_name: str) -> int:
    stem = Path(str(paper_name or "")).stem.strip()
    match = re.match(r"^.+_(?P<page>\d+)$", stem)
    if not match:
        return 1
    return max(1, _to_int(match.group("page"), 1))


def _split_class_exam(folder_safe: str) -> tuple[str, str]:
    safe = str(folder_safe or "").strip()
    if not safe.startswith("cls_") or "__" not in safe:
        return "", safe
    prefix, exam_name = safe.split("__", 1)
    class_id = "".join(c for c in prefix[4:] if c.isalnum() or c in ("-", "_"))[:64]
    return class_id, exam_name.strip() or safe


def _grading_root() -> Path:
    root = grading_paths().root
    root.mkdir(parents=True, exist_ok=True)
    return root


def _relative_to_grading_root(path: Path) -> str:
    root = _grading_root().resolve()
    try:
        return path.resolve().relative_to(root).as_posix()
    except Exception:
        return path.as_posix()


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _ct_layout(folder_safe: str) -> dict[str, Any]:
    class_id, exam_name = _split_class_exam(folder_safe)
    if class_id:
        class_dir = ct_root() / f"cls_{class_id}"
        records_dir = class_dir / "records"
        analysis_dir = class_dir / "analysis"
        assets_dir = class_dir / "assets" / _safe_json_stem(exam_name)
        return {
            "class_id": class_id,
            "exam_name": exam_name,
            "records_path": records_dir / f"{_safe_json_stem(exam_name)}.json",
            "analysis_path": analysis_dir / f"{_safe_json_stem(exam_name)}.json",
            "assets_dir": assets_dir,
        }

    base = grading_paths().ct / "reference_vlm" / _safe_json_stem(folder_safe)
    return {
        "class_id": "",
        "exam_name": folder_safe,
        "records_path": base / "records.json",
        "analysis_path": base / "analysis.json",
        "assets_dir": base / "assets",
    }


def _reference_layout_path(folder_safe: str, *, pending: bool = False) -> Path:
    """Persist the teacher-confirmed split layout beside the uploaded papers."""
    suffix = ".pending.json" if pending else ".json"
    return correct_docs_dir() / str(folder_safe) / f".reference_vlm_layout{suffix}"


def _file_signature(path: Path) -> dict[str, int]:
    try:
        stat = path.stat()
        return {"size": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns)}
    except OSError:
        return {"size": -1, "mtime_ns": -1}


def _layout_bbox(value: Any, image_size: tuple[int, int]) -> Optional[list[int]]:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return None
    try:
        return _clamp_bbox([int(float(v)) for v in value[:4]], image_size)
    except (TypeError, ValueError):
        return None


def _bbox_union(boxes: list[list[int]], image_size: tuple[int, int]) -> Optional[list[int]]:
    valid = [box for box in boxes if _layout_bbox(box, image_size) is not None]
    if not valid:
        return None
    return _clamp_bbox(
        [
            min(box[0] for box in valid),
            min(box[1] for box in valid),
            max(box[2] for box in valid),
            max(box[3] for box in valid),
        ],
        image_size,
    )


def build_reference_layout_page(
    document: dict[str, Any],
    *,
    page_no: int,
    filename: str,
    image_url: str,
) -> dict[str, Any]:
    """Convert Baidu's OCR questions into the editable frontend layout."""
    questions = document.get("questions") if isinstance(document, dict) else []
    raw_size = document.get("image_size") if isinstance(document, dict) else None
    image_size = (
        (_to_int(raw_size[0]), _to_int(raw_size[1]))
        if isinstance(raw_size, (list, tuple)) and len(raw_size) >= 2
        else (0, 0)
    )
    output: list[dict[str, Any]] = []
    for q in questions or []:
        if not isinstance(q, VlmQuestion):
            continue
        region_boxes = q.question_regions or [q.question_bbox]
        regions = []
        for region_index, box in enumerate(region_boxes):
            normalized = _layout_bbox(box, image_size)
            if not normalized:
                continue
            regions.append(
                {
                    "region_id": f"q-{q.display_index}-r{region_index + 1}",
                    "label": f"{q.display_index}-{chr(65 + region_index)}",
                    "role": "question",
                    "order": region_index + 1,
                    "bbox": normalized,
                }
            )
        slots = []
        for slot_index, box in enumerate(q.answer_bboxes, start=1):
            normalized = _layout_bbox(box, image_size)
            if not normalized:
                continue
            slots.append(
                {
                    "slot_id": f"q-{q.display_index}-s{slot_index}",
                    "label": f"{q.display_index}_{slot_index}",
                    "order": slot_index,
                    "regions": [{"bbox": normalized}],
                    "bbox": normalized,
                    "has_handwriting_location": True,
                }
            )
        output.append(
            {
                "question_id": f"q-{q.display_index}",
                "display_no": q.display_index,
                "baidu_question_id": q.question_id,
                "question_type": q.question_type,
                "question_text": q.question_words,
                "regions": regions,
                "answer_slots": slots,
            }
        )
    return {
        "page_no": int(page_no),
        "filename": str(filename),
        "image_url": str(image_url),
        "image_size": [image_size[0], image_size[1]],
        "questions": output,
    }


def _layout_slot_boxes(slot: Any, image_size: tuple[int, int]) -> list[list[int]]:
    if not isinstance(slot, dict):
        return []
    values = slot.get("regions")
    if not isinstance(values, list):
        values = [{"bbox": slot.get("bbox")}]
    boxes = []
    for region in values:
        value = region.get("bbox") if isinstance(region, dict) else region
        normalized = _layout_bbox(value, image_size)
        if normalized:
            boxes.append(normalized)
    return boxes


def apply_reference_layout_to_document(
    document: dict[str, Any],
    layout_page: dict[str, Any],
) -> dict[str, Any]:
    """Apply teacher-edited regions to a cached OCR document.

    The raw Baidu response remains available; corrected fields are written to
    the copied question objects so the existing grading/result writer can use
    the same downstream contract.
    """
    corrected = copy.deepcopy(document or {})
    image_size_raw = corrected.get("image_size") or layout_page.get("image_size") or [0, 0]
    image_size = (_to_int(image_size_raw[0]), _to_int(image_size_raw[1]))
    questions = extract_vlm_questions(corrected.get("raw") or {}, image_path=str(corrected.get("image_path") or corrected.get("source_path") or ""))
    layout_questions = layout_page.get("questions") if isinstance(layout_page, dict) else []
    by_index = {
        _to_int(item.get("display_no"), 0): item
        for item in layout_questions or []
        if isinstance(item, dict)
    }
    for question in questions:
        edit = by_index.get(question.display_index)
        if not edit:
            continue
        region_boxes = []
        for region in edit.get("regions") or []:
            value = region.get("bbox") if isinstance(region, dict) else region
            normalized = _layout_bbox(value, image_size)
            if normalized:
                region_boxes.append(normalized)
        if region_boxes:
            question.question_regions = region_boxes
            question.question_bbox = _bbox_union(region_boxes, image_size) or question.question_bbox
        slot_boxes = []
        for slot in edit.get("answer_slots") or []:
            boxes = _layout_slot_boxes(slot, image_size)
            slot_box = _bbox_union(boxes, image_size)
            if slot_box:
                slot_boxes.append(slot_box)
        question.answer_bboxes = slot_boxes
        question.answer_bbox = _answer_bbox_union(slot_boxes, image_size)
        question.bbox = _mark_bbox_from_area(question.question_bbox, question.answer_bbox)
        question.raw["corrected_question_regions"] = copy.deepcopy(region_boxes)
        question.raw["corrected_answer_slots"] = copy.deepcopy(
            [
                {"slot_index": index, "bbox": box}
                for index, box in enumerate(slot_boxes, start=1)
            ]
        )
        location = question.raw.get("location")
        if not isinstance(location, dict):
            location = {}
            question.raw["location"] = location
        location["qus_location"] = question.question_bbox
        location["ans_location"] = slot_boxes
    corrected["questions"] = questions
    corrected["corrected_layout"] = copy.deepcopy(layout_page)
    return corrected


def save_reference_layout_prepare(
    folder_safe: str,
    pages: list[dict[str, Any]],
) -> str:
    prepare_id = uuid.uuid4().hex
    normalized_pages = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        item = copy.deepcopy(page)
        source_path = Path(str(item.get("source_path") or ""))
        if source_path.is_file():
            item["source_signature"] = _file_signature(source_path)
        item.pop("source_path", None)
        normalized_pages.append(item)
    payload = {
        "version": 1,
        "prepare_id": prepare_id,
        "created_at": _now_iso(),
        "pages": {
            str(_to_int(page.get("page_no"), 1)): page
            for page in normalized_pages
        },
    }
    _write_json(_reference_layout_path(folder_safe, pending=True), payload)
    return prepare_id


def confirm_reference_layout(
    folder_safe: str,
    prepare_id: str,
    edited_pages: list[dict[str, Any]],
) -> dict[str, Any]:
    pending_path = _reference_layout_path(folder_safe, pending=True)
    pending = _read_json(pending_path)
    if not pending or str(pending.get("prepare_id")) != str(prepare_id):
        raise RuntimeError("切题审查数据已失效，请重新进行切题审查")
    pending_pages = pending.get("pages") if isinstance(pending.get("pages"), dict) else {}
    final_pages: dict[str, dict[str, Any]] = {}
    for edited in edited_pages or []:
        if not isinstance(edited, dict):
            continue
        page_no = str(_to_int(edited.get("page_no"), 0))
        source = pending_pages.get(page_no)
        if not isinstance(source, dict):
            raise RuntimeError(f"切题审查缺少 P{page_no} 数据")
        questions = edited.get("questions")
        if not isinstance(questions, list) or not questions:
            raise RuntimeError(f"标准答案 P{page_no} 至少需要一个题目框")
        corrected_raw = copy.deepcopy(source.get("raw") or {})
        try:
            corrected_document = apply_reference_layout_to_document(
                {
                    "raw": corrected_raw,
                    "image_path": source.get("image_path"),
                    "image_size": source.get("image_size") or [0, 0],
                },
                edited,
            )
            corrected_raw = corrected_document.get("raw") or corrected_raw
        except Exception:
            # The editable layout remains authoritative even if the optional
            # raw-JSON enrichment cannot be reconstructed at save time.
            pass
        final_pages[page_no] = {
            "page_no": _to_int(source.get("page_no"), 1),
            "filename": source.get("filename"),
            "source_signature": source.get("source_signature") or {},
            "image_path": source.get("image_path"),
            "image_size": source.get("image_size") or [0, 0],
            "raw": source.get("raw") or {},
            "corrected_raw": corrected_raw,
            "layout": {
                "page_no": _to_int(source.get("page_no"), 1),
                "filename": source.get("filename"),
                "image_url": edited.get("image_url") or source.get("image_url") or "",
                "image_size": source.get("image_size") or [0, 0],
                "questions": copy.deepcopy(questions),
            },
        }
    if not final_pages:
        raise RuntimeError("没有可保存的切题审查页面")
    if set(final_pages) != set(pending_pages):
        missing = sorted(set(pending_pages) - set(final_pages), key=lambda value: int(value or 0))
        raise RuntimeError(
            "必须完成所有标准答案页的切题审查，缺少："
            + "、".join(f"P{page}" for page in missing)
        )
    result = {
        "version": 1,
        "status": "confirmed",
        "updated_at": _now_iso(),
        "pages": final_pages,
    }
    _write_json(_reference_layout_path(folder_safe), result)
    try:
        pending_path.unlink(missing_ok=True)
    except OSError:
        pass
    return result


def load_reference_layout(folder_safe: str) -> dict[str, Any]:
    return _read_json(_reference_layout_path(folder_safe))


def load_reference_layout_for_editing(
    folder_safe: str,
    standard_sources: dict[int, tuple[Path, Path]],
    image_urls: Optional[dict[int, str]] = None,
) -> dict[str, Any]:
    """Open the confirmed layout for editing without running OCR again."""
    data = load_reference_layout(folder_safe)
    saved_pages = data.get("pages") if isinstance(data.get("pages"), dict) else {}
    if not standard_sources or not saved_pages:
        raise RuntimeError("尚未保存标准答案切题审查结果")

    pending_pages: list[dict[str, Any]] = []
    response_pages: list[dict[str, Any]] = []
    for page_no, (source_path, grading_path) in sorted(standard_sources.items()):
        saved = saved_pages.get(str(page_no))
        if not isinstance(saved, dict) or saved.get("source_signature") != _file_signature(source_path):
            raise RuntimeError(f"标准答案 P{page_no} 已变更，请重新进行切题审查")
        layout = copy.deepcopy(saved.get("layout"))
        if not isinstance(layout, dict):
            raise RuntimeError(f"标准答案 P{page_no} 缺少已保存的切题数据")
        if image_urls and image_urls.get(page_no):
            layout["image_url"] = image_urls[page_no]
        layout["page_no"] = page_no
        layout["filename"] = source_path.name
        pending_pages.append(
            {
                **copy.deepcopy(layout),
                "source_path": str(source_path),
                "image_path": str(grading_path),
                "raw": copy.deepcopy(saved.get("raw") or {}),
            }
        )
        response_pages.append(layout)

    prepare_id = save_reference_layout_prepare(folder_safe, pending_pages)
    return {"prepare_id": prepare_id, "pages": response_pages}


def delete_reference_layout(folder_safe: str, page_no: Optional[int] = None) -> None:
    """Invalidate reviewed layout data when a standard page is replaced/deleted."""
    for pending in (False, True):
        path = _reference_layout_path(folder_safe, pending=pending)
        data = _read_json(path)
        if not data:
            continue
        if page_no is None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            continue
        pages = data.get("pages") if isinstance(data.get("pages"), dict) else {}
        pages.pop(str(int(page_no)), None)
        if pages:
            data["pages"] = pages
            _write_json(path, data)
        else:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def reference_layout_status(
    folder_safe: str,
    standard_paths: dict[int, Path],
) -> dict[str, Any]:
    data = load_reference_layout(folder_safe)
    saved_pages = data.get("pages") if isinstance(data.get("pages"), dict) else {}
    reviewed_pages: list[int] = []
    stale_pages: list[int] = []
    for page_no, source_path in sorted(standard_paths.items()):
        saved = saved_pages.get(str(page_no))
        if not isinstance(saved, dict) or saved.get("source_signature") != _file_signature(source_path):
            stale_pages.append(page_no)
        else:
            reviewed_pages.append(page_no)
    return {
        "confirmed": bool(standard_paths) and not stale_pages and len(reviewed_pages) == len(standard_paths),
        "reviewed_pages": reviewed_pages,
        "stale_pages": stale_pages,
        "updated_at": data.get("updated_at"),
    }


def get_confirmed_reference_document(
    folder_safe: str,
    page_no: int,
    source_path: Path,
    image_path: str,
) -> Optional[dict[str, Any]]:
    data = load_reference_layout(folder_safe)
    pages = data.get("pages") if isinstance(data.get("pages"), dict) else {}
    saved = pages.get(str(page_no))
    if not isinstance(saved, dict) or saved.get("source_signature") != _file_signature(source_path):
        return None
    raw = saved.get("corrected_raw") or saved.get("raw")
    if not isinstance(raw, dict):
        return None
    layout_page = saved.get("layout") if isinstance(saved.get("layout"), dict) else {}
    document = {
        "name": saved.get("filename") or source_path.name,
        "source_path": str(source_path),
        "image_path": str(image_path),
        "raw": copy.deepcopy(raw),
    }
    with Image.open(image_path) as image:
        document["image_size"] = image.size
    return apply_reference_layout_to_document(document, layout_page)


def _remove_paper_from_reference_store(path: Path, paper_box: str, page_no: int) -> bool:
    data = _read_json(path)
    papers = data.get("papers") if isinstance(data.get("papers"), dict) else {}
    if paper_box not in papers:
        return False
    paper = papers.get(paper_box) if isinstance(papers.get(paper_box), dict) else {}
    pages = paper.get("pages") if isinstance(paper.get("pages"), dict) else {}
    if pages:
        pages.pop(str(page_no), None)
        if pages:
            is_analysis = "wrong_question_analysis" in paper and "questions" not in paper
            papers[paper_box] = _aggregate_reference_pages(
                paper_box,
                paper.get("student") if isinstance(paper.get("student"), dict) else {},
                pages,
                analysis=is_analysis,
            )
        else:
            papers.pop(paper_box, None)
    else:
        # Legacy records did not have a pages map and represented one page.
        papers.pop(paper_box, None)
    data["papers"] = papers
    if not papers:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        return False
    _update_exam_summary(data)
    _write_json(path, data)
    return paper_box in papers


def remove_reference_vlm_paper_artifacts(folder_safe: str, paper_name: str) -> None:
    """Remove all reference-VLM records and assets for one source paper."""
    layout = _ct_layout(folder_safe)
    paper_box = _paper_box_name(paper_name)
    page_no = _paper_page_no(paper_name)
    has_remaining_pages = False
    for key in ("records_path", "analysis_path"):
        path = layout.get(key)
        if isinstance(path, Path) and path.is_file():
            has_remaining_pages = (
                _remove_paper_from_reference_store(path, paper_box, page_no)
                or has_remaining_pages
            )

    assets_root = layout.get("assets_dir")
    if not isinstance(assets_root, Path):
        return
    paper_dir = assets_root / _safe_json_stem(paper_box)
    page_dir = paper_dir / f"p{page_no}"
    if page_dir.is_dir():
        shutil.rmtree(page_dir, ignore_errors=True)
    if has_remaining_pages and page_no == 1 and paper_dir.is_dir():
        for legacy_asset in paper_dir.glob("*.jpg"):
            try:
                legacy_asset.unlink()
            except Exception:
                pass
    if not has_remaining_pages and paper_dir.is_dir():
        shutil.rmtree(paper_dir, ignore_errors=True)

    raw_dir = assets_root / "_reference_vlm_json"
    raw_names = {
        f"{_safe_json_stem(paper_box)}_p{page_no}",
        _safe_json_stem(Path(str(paper_name or "")).stem),
    }
    if page_no == 1:
        raw_names.add(_safe_json_stem(paper_box))
    for name in raw_names:
        try:
            (raw_dir / f"{name}.json").unlink(missing_ok=True)
        except Exception:
            pass
    try:
        if raw_dir.is_dir() and not any(raw_dir.iterdir()):
            raw_dir.rmdir()
        if assets_root.is_dir() and not any(assets_root.iterdir()):
            assets_root.rmdir()
    except Exception:
        pass


def delete_reference_vlm_folder_artifacts(folder_safe: str) -> None:
    """Remove all reference-VLM JSON and assets for one grading folder."""
    layout = _ct_layout(folder_safe)
    for key in ("records_path", "analysis_path"):
        path = layout.get(key)
        if isinstance(path, Path):
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

    assets_root = layout.get("assets_dir")
    if isinstance(assets_root, Path) and assets_root.is_dir():
        shutil.rmtree(assets_root, ignore_errors=True)

    # Standalone folders use ct/reference_vlm/<folder>; remove the now-empty
    # parent as well so the records and JSON directory cannot be left behind.
    if not layout.get("class_id"):
        base = grading_paths().ct / "reference_vlm" / _safe_json_stem(folder_safe)
        if base.is_dir():
            shutil.rmtree(base, ignore_errors=True)


def _ensure_image_for_vlm(file_path: str) -> str:
    image_path, _created = ensure_image_path(file_path)
    return image_path


def submit_paper_cut_vlm(
    image_path: str,
    stop_event: Optional[threading.Event] = None,
    *,
    allow_empty: bool = False,
) -> dict:
    if stop_event and stop_event.is_set():
        raise RuntimeError("已停止批改")
    path = _ensure_image_for_vlm(image_path)
    img_base64 = base64.b64encode(Path(path).read_bytes()).decode("utf-8")
    # 手写场景设 GRADING_VLM_ENHANCE=true（1/true/yes/on）时透传百度侧增强；
    # 默认 false（与原硬编码行为一致）。
    enhance = os.environ.get("GRADING_VLM_ENHANCE", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    data = _post_json(
        _build_url(PAPER_CUT_VLM_CREATE_URL),
        {"image": img_base64, "only_split": True, "enhance": enhance},
        timeout=60,
        limiter=_create_rate_limiter,
    )
    _check_baidu_api_error(data)
    if not _questions_container(data) and not allow_empty:
        raise RuntimeError(f"百度仅切题接口未返回题目位置: {data}")
    return data


def recognize_reference_vlm_batch(
    items: list[tuple[str, str, str]],
    *,
    stop_event: Optional[threading.Event] = None,
    max_workers: Optional[int] = None,
    allow_empty: bool = False,
) -> tuple[dict[str, dict], dict[str, Exception]]:
    """Recognize all papers with Baidu paper_cut_edu_vlm.

    items: (cache_key, display_name, source_path)
    """
    if not items:
        return {}, {}
    workers = max_workers or int(os.environ.get("REFERENCE_VLM_BAIDU_WORKERS", "8") or "8")
    workers = max(1, min(workers, len(items)))
    results: dict[str, dict] = {}
    errors: dict[str, Exception] = {}

    def _one(item: tuple[str, str, str]) -> tuple[str, dict]:
        cache_key, display_name, source_path = item
        if stop_event and stop_event.is_set():
            raise RuntimeError("已停止批改")
        image_path = _ensure_image_for_vlm(source_path)
        raw = submit_paper_cut_vlm(
            image_path,
            stop_event=stop_event,
            allow_empty=allow_empty,
        )
        questions = extract_vlm_questions(raw, image_path=image_path)
        if not questions and not allow_empty:
            raise RuntimeError("百度仅切题接口未返回可批改题目")
        with Image.open(image_path) as image:
            image_size = image.size
        return cache_key, {
            "name": display_name,
            "source_path": source_path,
            "image_path": image_path,
            "task_id": "",
            "raw": raw,
            "questions": questions,
            "image_size": image_size,
        }

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(_one, item): item[0] for item in items}
        for future in as_completed(future_map):
            key = future_map[future]
            try:
                got_key, data = future.result()
                results[got_key] = data
            except Exception as exc:
                errors[key] = exc
    return results, errors


def _questions_container(raw: dict) -> list:
    if not isinstance(raw, dict):
        return []
    direct = raw.get("qus_results") or raw.get("qus_result")
    if isinstance(direct, list):
        return direct
    result = raw.get("result")
    if isinstance(result, dict):
        got = result.get("qus_results") or result.get("qus_result")
        if isinstance(got, list):
            return got
        nested = result.get("result")
        if isinstance(nested, dict):
            got = nested.get("qus_results") or nested.get("qus_result")
            if isinstance(got, list):
                return got
    return []


def _clear_existing_grading_fields(raw: dict) -> None:
    """Ensure a cached or previously enriched OCR document can be regraded."""
    grading_keys = (
        "sub_grading_results",
        "correctResult",
        "result",
        "reason",
        "ai_analysis",
        "grading_result",
    )
    for question in _questions_container(raw):
        if not isinstance(question, dict):
            continue
        for key in grading_keys:
            question.pop(key, None)


def _bbox_from_points(points: Any) -> Optional[list[float]]:
    if not isinstance(points, list) or len(points) < 2:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for point in points:
        if isinstance(point, dict):
            xs.append(_to_float(point.get("x")))
            ys.append(_to_float(point.get("y")))
        elif isinstance(point, (list, tuple)) and len(point) >= 2:
            xs.append(_to_float(point[0]))
            ys.append(_to_float(point[1]))
    if not xs or not ys:
        return None
    return [min(xs), min(ys), max(xs), max(ys)]


def _raw_location_to_bbox(location: Any) -> Optional[list[float]]:
    if not location:
        return None
    if isinstance(location, dict):
        if isinstance(location.get("coordinate"), (list, tuple)):
            return _raw_location_to_bbox(location.get("coordinate"))
        if isinstance(location.get("points"), list):
            return _bbox_from_points(location.get("points"))
        keys = ("left_x", "left_y", "right_x", "right_y")
        if all(k in location for k in keys):
            return [_to_float(location[k]) for k in keys]
        keys = ("x", "y", "width", "height")
        if all(k in location for k in keys):
            x = _to_float(location["x"])
            y = _to_float(location["y"])
            return [x, y, x + _to_float(location["width"]), y + _to_float(location["height"])]
        # Baidu's paper_cut_edu_vlm response examples use x/y/w/h for each
        # handwriting box in ans_location.
        keys = ("x", "y", "w", "h")
        if all(k in location for k in keys):
            x = _to_float(location["x"])
            y = _to_float(location["y"])
            return [x, y, x + _to_float(location["w"]), y + _to_float(location["h"])]
    if isinstance(location, list):
        if location and isinstance(location[0], dict):
            rectangles = [
                bbox
                for item in location
                if (bbox := _raw_location_to_bbox(item)) is not None
            ]
            if rectangles:
                return [
                    min(box[0] for box in rectangles),
                    min(box[1] for box in rectangles),
                    max(box[2] for box in rectangles),
                    max(box[3] for box in rectangles),
                ]
            return _bbox_from_points(location)
        if len(location) >= 4:
            return [_to_float(v) for v in location[:4]]
    return None


def _normalize_bbox(values: Any, image_size: tuple[int, int]) -> Optional[list[int]]:
    raw = _raw_location_to_bbox(values)
    if not raw or len(raw) < 4:
        return None
    w, h = image_size
    x1, y1, a, b = raw[:4]

    # The real paper_cut_edu_vlm sample uses [x1, y1, x2, y2]. Some docs name
    # the last two fields width/height, so accept that form when it is obvious.
    if a > x1 and b > y1 and a <= w * 1.08 and b <= h * 1.08:
        x2, y2 = a, b
    else:
        x2, y2 = x1 + a, y1 + b

    left = max(0, min(w - 1, int(round(min(x1, x2)))))
    top = max(0, min(h - 1, int(round(min(y1, y2)))))
    right = max(1, min(w, int(round(max(x1, x2)))))
    bottom = max(1, min(h, int(round(max(y1, y2)))))
    if right <= left or bottom <= top:
        return None
    return [left, top, right, bottom]


def _answer_bboxes(ans_location: Any, image_size: tuple[int, int]) -> list[list[int]]:
    if not ans_location:
        return []
    if (
        isinstance(ans_location, list)
        and len(ans_location) >= 4
        and not isinstance(ans_location[0], (list, tuple, dict))
    ):
        candidates = [ans_location]
    elif isinstance(ans_location, list):
        candidates = ans_location
    else:
        candidates = [ans_location]

    return [
        bbox
        for item in candidates
        if (bbox := _normalize_bbox(item, image_size)) is not None
    ]


def _answer_bbox_union(ans_location: Any, image_size: tuple[int, int]) -> Optional[list[int]]:
    boxes = _answer_bboxes(ans_location, image_size)
    if not boxes:
        return None
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def _mark_bbox_from_area(area_bbox: list[int], answer_bbox: Optional[list[int]] = None) -> list[int]:
    if answer_bbox:
        # The shared mark renderer places the glyph at bbox.x_max and at the
        # vertical center. A tiny box ending at the handwriting union's lower
        # right corner is retained for question-level fallback marks.
        x2, y2 = answer_bbox[2], answer_bbox[3]
        return [max(0, x2 - 2), max(0, y2 - 2), x2, y2]

    base = answer_bbox or area_bbox
    x1, y1, x2, y2 = base
    w = max(1, x2 - x1)
    h = max(1, y2 - y1)
    mark_w = max(50, int(w * 0.35))
    mark_h = max(50, int(h * 0.38))
    left = max(x1, x2 - mark_w)
    top = max(y1, y2 - mark_h)
    return [left, top, x2, y2]


def _as_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x or "").strip() for x in value if str(x or "").strip()]
    text = str(value or "").strip()
    return [text] if text else []


def extract_vlm_questions(raw: dict, *, image_path: str) -> list[VlmQuestion]:
    if Image is None:
        raise RuntimeError("需要安装 Pillow")
    with Image.open(image_path) as img:
        image_size = img.size

    questions: list[VlmQuestion] = []
    for pos, item in enumerate(_questions_container(raw), start=1):
        if not isinstance(item, dict):
            continue
        location = item.get("location") if isinstance(item.get("location"), dict) else {}
        bbox = _normalize_bbox(location.get("qus_location") or item.get("qus_location"), image_size)
        if not bbox:
            continue
        elements = item.get("qus_elements") if isinstance(item.get("qus_elements"), dict) else {}
        if not elements and isinstance(item.get("qus_element"), dict):
            elements = item.get("qus_element") or {}
        question_id = _to_int(item.get("qus_id") or item.get("question_id") or item.get("id"), pos)
        ans_location = location.get("ans_location") or item.get("ans_location")
        answer_bboxes = _answer_bboxes(ans_location, image_size)
        answer_bbox = _answer_bbox_union(ans_location, image_size)
        answer_words = _as_text_list(
            elements.get("answer_words")
            or elements.get("ans_words")
            or item.get("answer_words")
            or item.get("ans_words")
        )
        choices = _as_text_list(elements.get("choices") or item.get("choices"))
        question_words = _safe_text(
            elements.get("question_words")
            or elements.get("qus_words")
            or item.get("question_words")
            or item.get("qus_words")
        )
        question_type = str(elements.get("qus_type") or item.get("qus_type") or "").strip()
        pic_location = location.get("pic_location") or item.get("pic_location")
        is_orphan_continuation = (
            bool(questions)
            and question_id == questions[-1].question_id
            and answer_bbox is None
            and not pic_location
            and (bbox[3] - bbox[1]) <= 80
        )
        if is_orphan_continuation:
            continue
        questions.append(
            VlmQuestion(
                question_id=question_id,
                display_index=pos,
                raw=item,
                bbox=_mark_bbox_from_area(bbox, answer_bbox),
                question_bbox=bbox,
                answer_bbox=answer_bbox,
                answer_bboxes=answer_bboxes,
                question_words=question_words,
                answer_words=answer_words,
                choices=choices,
                question_type=question_type,
                question_regions=[bbox],
            )
        )
    questions.sort(key=lambda q: q.display_index)
    for display_index, question in enumerate(questions, start=1):
        question.display_index = display_index
    return questions


def _crop_to_data_url(
    image,
    bbox: list[int],
    *,
    pad: int = 10,
    max_side: int = 1800,
    min_long_side: int = 1000,
    quality: int = 95,
    highlight_bbox: Optional[list[int]] = None,
    highlight_bboxes: Optional[list[tuple[list[int], str]]] = None,
) -> tuple[str, bytes]:
    w, h = image.size
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(w - 1, x1 - pad))
    y1 = max(0, min(h - 1, y1 - pad))
    x2 = max(1, min(w, x2 + pad))
    y2 = max(1, min(h, y2 + pad))
    if x2 <= x1 or y2 <= y1:
        raise RuntimeError("题目坐标无效，无法截图")
    crop = image.crop((x1, y1, x2, y2)).convert("RGB")
    original_crop_size = crop.size
    long_side = max(crop.size)
    ratio = 1.0
    if max_side and long_side > max_side:
        ratio = max_side / long_side
    elif min_long_side and long_side < min_long_side:
        ratio = min(2.0, min_long_side / max(1, long_side))
    if abs(ratio - 1.0) > 0.001:
        new_size = (
            max(1, int(round(crop.width * ratio))),
            max(1, int(round(crop.height * ratio))),
        )
        resampling = getattr(Image, "Resampling", None)
        lanczos = resampling.LANCZOS if resampling else getattr(Image, "LANCZOS", 1)
        crop = crop.resize(new_size, lanczos)

    crop = enhance_for_ocr(crop, mode="auto")

    highlights = list(highlight_bboxes or [])
    if highlight_bbox and not highlights:
        highlights = [(highlight_bbox, "")]
    if highlights and ImageDraw is not None:
        scale_x = crop.width / max(1, original_crop_size[0])
        scale_y = crop.height / max(1, original_crop_size[1])
        draw = ImageDraw.Draw(crop)
        width = max(3, min(10, int(min(crop.width, crop.height) * 0.012)))
        for source_bbox, label in highlights:
            hx1, hy1, hx2, hy2 = source_bbox
            hx1 = max(0, min(crop.width - 1, int(round((hx1 - x1) * scale_x))))
            hy1 = max(0, min(crop.height - 1, int(round((hy1 - y1) * scale_y))))
            hx2 = max(hx1 + 1, min(crop.width, int(round((hx2 - x1) * scale_x))))
            hy2 = max(hy1 + 1, min(crop.height, int(round((hy2 - y1) * scale_y))))
            draw.rectangle(
                (hx1, hy1, hx2 - 1, hy2 - 1),
                outline=(220, 25, 25),
                width=width,
            )
            if label:
                draw.text((hx1 + width, max(0, hy1 - 16)), str(label), fill=(220, 25, 25))
    buf = BytesIO()
    crop.save(buf, format="JPEG", quality=quality, subsampling=0)
    payload = buf.getvalue()
    b64 = base64.standard_b64encode(payload).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}", payload


def _crop_regions_to_data_url(
    image,
    bboxes: list[list[int]],
    *,
    highlight_bbox: Optional[list[int]] = None,
    highlight_bboxes: Optional[list[tuple[list[int], str]]] = None,
) -> tuple[str, bytes]:
    """Crop several disjoint regions into one ordered image packet.

    Keeping the regions separate avoids a huge rectangle full of irrelevant
    whitespace, while one packet preserves the existing two-image Qwen API.
    The regions are stacked in their declared order and never alter source
    coordinates used for marking.
    """
    valid = []
    for box in bboxes:
        try:
            normalized = _clamp_bbox(box, image.size)
        except Exception:
            continue
        if normalized not in valid:
            valid.append(normalized)
    if not valid:
        raise RuntimeError("题目区域为空，无法截图")
    if len(valid) == 1:
        return _crop_to_data_url(
            image,
            valid[0],
            pad=14,
            highlight_bbox=highlight_bbox,
            highlight_bboxes=highlight_bboxes,
        )

    crops = []
    for box in valid:
        x1, y1, x2, y2 = box
        crop = image.crop(
            (
                max(0, x1 - 14),
                max(0, y1 - 14),
                min(image.width, x2 + 14),
                min(image.height, y2 + 14),
            )
        ).convert("RGB")
        long_side = max(crop.size)
        ratio = min(1.0, 1700 / max(1, long_side))
        if long_side < 900:
            ratio = min(2.0, 900 / max(1, long_side))
        if abs(ratio - 1.0) > 0.001:
            resampling = getattr(Image, "Resampling", None)
            lanczos = resampling.LANCZOS if resampling else getattr(Image, "LANCZOS", 1)
            crop = crop.resize(
                (max(1, int(round(crop.width * ratio))), max(1, int(round(crop.height * ratio)))),
                lanczos,
            )
        crop = enhance_for_ocr(crop, mode="auto")
        highlights = list(highlight_bboxes or [])
        if highlight_bbox and not highlights:
            highlights = [(highlight_bbox, "")]
        if highlights and ImageDraw is not None:
            sx = crop.width / max(1, (x2 - x1) + 28)
            sy = crop.height / max(1, (y2 - y1) + 28)
            draw = ImageDraw.Draw(crop)
            width = max(3, min(10, int(min(crop.size) * 0.012)))
            for source_bbox, label in highlights:
                hx1, hy1, hx2, hy2 = source_bbox
                ix1, iy1 = max(x1, hx1), max(y1, hy1)
                ix2, iy2 = min(x2, hx2), min(y2, hy2)
                if ix2 <= ix1 or iy2 <= iy1:
                    continue
                rx1 = max(0, int(round((ix1 - x1 + 14) * sx)))
                ry1 = max(0, int(round((iy1 - y1 + 14) * sy)))
                rx2 = min(crop.width - 1, int(round((ix2 - x1 + 14) * sx)))
                ry2 = min(crop.height - 1, int(round((iy2 - y1 + 14) * sy)))
                draw.rectangle(
                    (rx1, ry1, rx2, ry2),
                    outline=(220, 25, 25),
                    width=width,
                )
                if label:
                    draw.text((rx1 + width, max(0, ry1 - 16)), str(label), fill=(220, 25, 25))
        crops.append(crop)

    gap = 18
    canvas = Image.new(
        "RGB",
        (max(crop.width for crop in crops), sum(crop.height for crop in crops) + gap * (len(crops) - 1)),
        "white",
    )
    top = 0
    for index, crop in enumerate(crops):
        canvas.paste(crop, (0, top))
        top += crop.height
        if index < len(crops) - 1:
            top += gap
    buf = BytesIO()
    canvas.save(buf, format="JPEG", quality=95, subsampling=0)
    payload = buf.getvalue()
    return f"data:image/jpeg;base64,{base64.standard_b64encode(payload).decode('utf-8')}", payload


def _clamp_bbox(bbox: list[int], image_size: tuple[int, int]) -> list[int]:
    width, height = image_size
    x1, y1, x2, y2 = bbox
    left = max(0, min(width - 1, int(round(min(x1, x2)))))
    top = max(0, min(height - 1, int(round(min(y1, y2)))))
    right = max(left + 1, min(width, int(round(max(x1, x2)))))
    bottom = max(top + 1, min(height, int(round(max(y1, y2)))))
    return [left, top, right, bottom]


def _scale_bbox(
    bbox: list[int],
    source_size: tuple[int, int],
    target_size: tuple[int, int],
) -> list[int]:
    source_w, source_h = source_size
    target_w, target_h = target_size
    if source_w < 1 or source_h < 1:
        return _clamp_bbox(bbox, target_size)
    x1, y1, x2, y2 = bbox
    return _clamp_bbox(
        [
            int(round(x1 * target_w / source_w)),
            int(round(y1 * target_h / source_h)),
            int(round(x2 * target_w / source_w)),
            int(round(y2 * target_h / source_h)),
        ],
        target_size,
    )


def _project_bbox_between_question_regions(
    bbox: list[int],
    source_question_bbox: list[int],
    target_question_bbox: list[int],
    target_size: tuple[int, int],
) -> Optional[list[int]]:
    """Project an answer slot by its relative position inside a matched question."""
    sx1, sy1, sx2, sy2 = source_question_bbox
    tx1, ty1, tx2, ty2 = target_question_bbox
    source_w = sx2 - sx1
    source_h = sy2 - sy1
    target_w = tx2 - tx1
    target_h = ty2 - ty1
    if min(source_w, source_h, target_w, target_h) <= 0:
        return None

    bx1, by1, bx2, by2 = bbox
    projected = _clamp_bbox(
        [
            tx1 + (bx1 - sx1) * target_w / source_w,
            ty1 + (by1 - sy1) * target_h / source_h,
            tx1 + (bx2 - sx1) * target_w / source_w,
            ty1 + (by2 - sy1) * target_h / source_h,
        ],
        target_size,
    )
    return projected if projected[2] > projected[0] and projected[3] > projected[1] else None


def _normalized_center_distance(
    left: list[int],
    left_size: tuple[int, int],
    right: list[int],
    right_size: tuple[int, int],
) -> float:
    left_w, left_h = left_size
    right_w, right_h = right_size
    if min(left_w, left_h, right_w, right_h) < 1:
        return float("inf")
    lx = ((left[0] + left[2]) / 2.0) / left_w
    ly = ((left[1] + left[3]) / 2.0) / left_h
    rx = ((right[0] + right[2]) / 2.0) / right_w
    ry = ((right[1] + right[3]) / 2.0) / right_h
    return ((lx - rx) ** 2 + (ly - ry) ** 2) ** 0.5


def _question_for_bbox(
    questions: list[VlmQuestion],
    bbox: list[int],
    image_size: tuple[int, int],
) -> Optional[VlmQuestion]:
    if not questions:
        return None
    cx = (bbox[0] + bbox[2]) / 2.0
    cy = (bbox[1] + bbox[3]) / 2.0
    containing = [
        question
        for question in questions
        if question.question_bbox[0] <= cx <= question.question_bbox[2]
        and question.question_bbox[1] <= cy <= question.question_bbox[3]
    ]
    if containing:
        return min(
            containing,
            key=lambda question: (question.question_bbox[2] - question.question_bbox[0])
            * (question.question_bbox[3] - question.question_bbox[1]),
        )
    return min(
        questions,
        key=lambda question: _normalized_center_distance(
            question.question_bbox, image_size, bbox, image_size
        ),
    )


def _slot_context_bbox(
    question: VlmQuestion,
    answer_bbox: list[int],
    image_size: tuple[int, int],
) -> list[int]:
    """Keep question context, but do not downscale a whole-page question crop."""
    image_w, image_h = image_size
    qx1, qy1, qx2, qy2 = _clamp_bbox(question.question_bbox, image_size)
    question_w = qx2 - qx1
    question_h = qy2 - qy1
    if question_w <= image_w * 0.82 and question_h <= image_h * 0.56:
        return [qx1, qy1, qx2, qy2]

    ax1, ay1, ax2, ay2 = _clamp_bbox(answer_bbox, image_size)
    horizontal_pad = max(110, min(460, int((ax2 - ax1) * 3.2)))
    top_pad = max(190, min(520, int((ay2 - ay1) * 6.0)))
    bottom_pad = max(100, min(300, int((ay2 - ay1) * 3.0)))
    return _clamp_bbox(
        [ax1 - horizontal_pad, ay1 - top_pad, ax2 + horizontal_pad, ay2 + bottom_pad],
        image_size,
    )


def _save_crop(image, bbox: Optional[list[int]], out_path: Path, *, pad: int) -> bool:
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
    image.crop((x1, y1, x2, y2)).convert("RGB").save(str(out_path), quality=94)
    return True


def _get_qwen_client_and_model():
    if OpenAI is None:
        raise RuntimeError("需要安装 openai: pip install openai")
    api_key, model = get_qwen_config(default_model=DEFAULT_QWEN_MODEL)
    if not api_key:
        raise RuntimeError("系统设置中未配置千问 API Key")
    return (
        OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"),
        model or DEFAULT_QWEN_MODEL,
    )


def _escape_unsafe_json_string_backslashes(value: str) -> str:
    """Escape model-generated TeX slashes without altering JSON structure."""
    output: list[str] = []
    in_string = False
    index = 0
    hex_digits = set("0123456789abcdefABCDEF")
    while index < len(value):
        char = value[index]
        if char == '"':
            in_string = not in_string
            output.append(char)
            index += 1
            continue
        if in_string and char == "\\":
            if index + 1 >= len(value):
                output.append("\\\\")
                index += 1
                continue
            next_char = value[index + 1]
            if next_char in ('"', "\\", "/"):
                output.extend((char, next_char))
                index += 2
                continue
            if (
                next_char == "u"
                and index + 5 < len(value)
                and all(item in hex_digits for item in value[index + 2 : index + 6])
            ):
                output.extend(value[index : index + 6])
                index += 6
                continue
            # On the recovery path, preserve all other sequences literally.
            # This includes TeX commands such as \frac, whose leading \f is
            # technically valid JSON but would otherwise become a form feed.
            output.append("\\\\")
            index += 1
            continue
        output.append(char)
        index += 1
    return "".join(output)


def _json_object_from_text(text: str) -> dict:
    raw = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.I)
    if fenced:
        raw = fenced.group(1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError(f"千问未返回 JSON 对象: {raw[:200]}")
    candidate = raw[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        if "Invalid \\escape" in str(exc):
            repaired = _escape_unsafe_json_string_backslashes(candidate)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError as repaired_exc:
                exc = repaired_exc
        raise RuntimeError(f"千问返回 JSON 解析失败: {exc}; 原文: {raw[:300]}") from exc


def _normalize_decision(data: dict, question_id: int) -> dict:
    if not isinstance(data, dict):
        data = {}
    returned_id = _to_int(data.get("question_id"), question_id)
    if returned_id != question_id:
        raise RuntimeError(f"千问返回题号不一致: expected={question_id}, got={returned_id}")

    result_text = str(data.get("result") or "").strip()
    code = _to_int(data.get("correctResult"), 0)
    if code not in (CORRECT, WRONG, UNANSWERED, PARTIAL):
        if result_text == "对":
            code = CORRECT
        elif result_text == "未作答":
            code = UNANSWERED
        elif result_text == "半对":
            code = PARTIAL
        else:
            code = WRONG
    result_text = RESULT_TEXT.get(code, "错")
    partial_ratio = None
    if code == PARTIAL:
        partial_ratio = min(1.0, max(0.0, _to_float(data.get("partial_ratio"), 0.5)))
    reason = _normalize_math_text(_safe_text(data.get("reason"), limit=500))
    analysis = _normalize_math_text(_safe_text(data.get("analysis"), limit=1000))
    if not reason:
        reason = "已按标准答案完成判定"
    if not analysis:
        analysis = reason if code != CORRECT else "作答与标准答案一致。"
    confidence = _to_float(data.get("confidence"), 0.0)
    if confidence < 0 or confidence > 1:
        confidence = 0.0
    return {
        "question_id": question_id,
        "correctResult": code,
        "result": result_text,
        "reason": reason,
        "analysis": analysis,
        "confidence": round(confidence, 3),
        "partial_ratio": partial_ratio,
    }


def _question_payload(question: VlmQuestion) -> dict:
    return {
        "parent_question_index": question.display_index,
        "qus_id": question.question_id,
        "qus_type": question.question_type,
        "question_words": question.question_words,
        "answer_words": question.answer_words,
        "choices": question.choices,
        "location": {
            "qus_location": question.question_bbox,
            "ans_location": question.answer_bboxes,
        },
        "question_regions": question.question_regions or [question.question_bbox],
    }


def _grading_policy_hint(task: VlmGradingTask) -> str:
    question = task.standard_question
    text = f"{question.question_type} {question.question_words}".lower()
    objective_keywords = (
        "选择",
        "选出",
        "选项",
        "单选",
        "多选",
        "判断",
        "对错",
        "是非",
        "填空",
        "填充",
        "匹配",
        "连线",
        "排序",
        "choice",
        "select",
        "multiple choice",
        "true or false",
        "true/false",
        "judgment",
        "fill in",
        "matching",
    )
    subjective_keywords = (
        "简答",
        "解答",
        "论述",
        "说明理由",
        "作文",
        "写作",
        "证明",
        "short answer",
        "essay",
        "explain",
        "proof",
    )
    if question.choices or any(keyword in text for keyword in objective_keywords):
        return "objective_strict"
    if any(keyword in text for keyword in subjective_keywords):
        return "subjective_semantic"
    return "auto_detect_from_images"


def _task_payload(task: VlmGradingTask) -> dict:
    return {
        "question_id": task.task_id,
        "sub_index": task.sub_index,
        "grading_policy_hint": _grading_policy_hint(task),
        "standard_image_is_ground_truth": True,
        "is_answer_slot": task.is_answer_slot,
        "template_slot_id": task.template_slot_id,
        "anchor_source": task.anchor_source,
        "standard_answer_slot": {
            "parent_question": _question_payload(task.standard_question),
            "target_answer_bbox": task.standard_answer_bbox,
            "context_bbox": task.standard_context_bbox,
        },
        "student_answer_slot": {
            "parent_question": _question_payload(task.student_question),
            "target_answer_bbox": task.student_answer_bbox,
            "context_bbox": task.student_context_bbox,
            "has_handwriting_location": task.has_handwriting_location,
            "has_mark_anchor": task.has_mark_anchor,
        },
    }


def _build_slot_qwen_prompt(task: VlmGradingTask, student_name: str) -> str:
    policy_hint = _grading_policy_hint(task)
    payload = {"grading_task": _task_payload(task)}
    authority_rule = (
        "- STANDARD-ANSWER AUTHORITY: image 1 is the sole ground truth. Never replace, correct, extend, "
        "or second-guess its answer using your own solution or outside knowledge.\n"
    )
    objective_rule = (
        "- OBJECTIVE STRICT: the student's selected option set, true/false value, fixed answer, matching, "
        "or ordering must be exactly the same as the highlighted standard answer. Any different, missing, "
        "or extra option/value is wrong. Do not accept alternative answers, synonyms, partial correctness, "
        "or a plausible answer that differs from image 1. Compare answer identity rather than handwriting style.\n"
    )
    subjective_rule = (
        "- SUBJECTIVE SEMANTIC: understand the standard answer's conclusion, key ideas, reasoning, and required "
        "points. Accept different wording or an equivalent valid expression only when the essential meaning "
        "matches; mark wrong when a required core point is missing or contradicted. When only part of the "
        "required points are met (some right, some missing or wrong), use 4 (半对) and set partial_ratio to "
        "the fraction of full credit earned (0 to 1, e.g. 0.6).\n"
    )
    if policy_hint == "objective_strict":
        policy_instruction = (
            "Backend metadata identifies this as an OBJECTIVE question. Apply OBJECTIVE STRICT policy."
        )
        policy_rules = authority_rule + objective_rule
        comparison_rule = (
            "3. This is an objective question. Never apply semantic-equivalence tolerance; compare strictly "
            "against the answer identity shown in image 1.\n"
        )
    elif policy_hint == "subjective_semantic":
        policy_instruction = (
            "Backend metadata identifies this as a SUBJECTIVE question. Apply SUBJECTIVE SEMANTIC policy."
        )
        policy_rules = authority_rule + subjective_rule
        comparison_rule = (
            "3. This is a subjective question. Judge semantic equivalence against the core meaning and required "
            "points in image 1, without requiring identical wording.\n"
        )
    else:
        policy_instruction = (
            "Backend metadata is insufficient. First classify the visible question from image 1. "
            "For choice, true/false, fixed-answer fill-in, matching, ordering, or another objectively "
            "scored item, apply OBJECTIVE STRICT policy. Otherwise apply SUBJECTIVE SEMANTIC policy."
        )
        policy_rules = authority_rule + objective_rule + subjective_rule
        comparison_rule = (
            "3. After classifying the visible question, apply exactly one policy. Never apply subjective "
            "semantic-equivalence tolerance to an objective question.\n"
        )
    return "".join(
        [
            "You are a strict school-exam grader. The user content contains exactly two images in order: ",
            "image 1 is the standard-answer context packet and image 2 is the student-answer context packet. ",
            "A packet may stack several disjoint regions belonging to the same question. The red rectangle ",
            "marks the answer region. Grade only the corresponding answer in that region, while using every ",
            "stacked question/diagram region as context. Do not grade another answer in either packet.\n\n",
            "The two highlighted rectangles are one corresponding answer slot. Understand the question and ",
            "standard answer visible in image 1, then compare only the highlighted student answer in image 2. ",
            f"The student paper is: {student_name}.\n\n",
            policy_instruction,
            "\n\nMandatory grading policies:\n",
            policy_rules,
            "\nRules:\n",
            "1. Return question_id exactly as supplied. It is a backend task id, not the printed question number.\n",
            "2. correctResult must be 1 for correct, 2 for wrong, 3 for blank/unanswered, or 4 for partially correct (半对). ",
            "A blank highlighted student area is 3. When the answer is partially correct (some required points right, "
            "some missing or wrong), use 4 and set partial_ratio to the fraction of full credit earned (0 to 1, e.g. 0.6).\n",
            comparison_rule,
            "4. If the highlighted answers cannot be matched or read reliably, use 2 and explain the issue in reason.\n",
            "5. Write reason and analysis in Chinese. Keep a correct-answer analysis brief; explain the error ",
            "and the correct approach for a wrong answer.\n",
            "6. In reason and analysis, use plain Chinese text and Unicode math symbols only. Do not use TeX, "
            "LaTeX, Markdown, dollar-sign delimiters, caret exponent notation, or any backslash character. "
            "For example, write “5³ = 5 × 5 × 5 = 125”, “3⁄8”, “√2”, “x²”, “a₁”, “≤”, and “÷”.\n",
            "7. Do not invent or change any coordinate. Return exactly one valid JSON object with no Markdown "
            "and no extra fields. Every backslash required by JSON itself must be escaped correctly.\n\n",
            "JSON schema:\n",
            '{"question_id":1,"correctResult":1,"result":"\\u5bf9","reason":"...","analysis":"...","confidence":0.0,"partial_ratio":null}\n\n',
            "Task metadata (coordinates are read-only and the red rectangles are authoritative):\n",
            json.dumps(payload, ensure_ascii=False),
        ]
    )


def _call_qwen_for_question(
    client,
    model: str,
    task: VlmGradingTask,
    std_image_url: str,
    stu_image_url: str,
    student_name: str,
) -> dict:
    prompt = _build_slot_qwen_prompt(task, student_name)
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": std_image_url}},
                    {"type": "image_url", "image_url": {"url": stu_image_url}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        stream=False,
        timeout=180,
        extra_body=QWEN_CHAT_EXTRA_BODY,
    )
    content = completion.choices[0].message.content or ""
    return _normalize_decision(_json_object_from_text(content), task.task_id)


def _slot_key(task: VlmGradingTask) -> str:
    return f"{task.student_question.display_index}_{task.sub_index}"


def _group_grading_tasks(tasks: list[VlmGradingTask]) -> list[VlmQuestionBatchTask]:
    """Group the immutable slot tasks into one request per parent question."""
    groups: dict[int, list[VlmGradingTask]] = {}
    order: list[int] = []
    for task in tasks:
        key = id(task.student_question)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(task)
    return [
        VlmQuestionBatchTask(
            batch_id=groups[key][0].task_id,
            student_question=groups[key][0].student_question,
            standard_question=groups[key][0].standard_question,
            slots=groups[key],
        )
        for key in order
    ]


def _batch_context_regions(
    batch: VlmQuestionBatchTask,
    *,
    standard: bool,
    source_size: tuple[int, int],
    target_size: tuple[int, int],
) -> list[list[int]]:
    """Return one context packet containing all slots for a parent question."""
    regions = batch.standard_question.question_regions or [batch.standard_question.question_bbox]
    if standard:
        projected = list(regions)
        slot_boxes = [task.standard_answer_bbox for task in batch.slots]
    else:
        projected = [
            _project_bbox_between_question_regions(
                region,
                batch.standard_question.question_bbox,
                batch.student_question.question_bbox,
                target_size,
            )
            or _scale_bbox(region, source_size, target_size)
            for region in regions
        ]
        slot_boxes = [task.student_answer_bbox for task in batch.slots]
    for box in slot_boxes:
        if box not in projected:
            projected.append(box)
    return projected


def _batch_task_payload(batch: VlmQuestionBatchTask) -> dict:
    return {
        "question_id": batch.batch_id,
        "parent_question_index": batch.student_question.display_index,
        "standard_image_is_ground_truth": True,
        "slots": [
            {
                "slot_key": _slot_key(task),
                "sub_index": task.sub_index,
                "is_answer_slot": task.is_answer_slot,
                "anchor_source": task.anchor_source,
                "standard_answer_slot": {
                    "target_answer_bbox": task.standard_answer_bbox,
                    "context_bbox": task.standard_context_bbox,
                },
                "student_answer_slot": {
                    "target_answer_bbox": task.student_answer_bbox,
                    "context_bbox": task.student_context_bbox,
                    "has_handwriting_location": task.has_handwriting_location,
                    "has_mark_anchor": task.has_mark_anchor,
                },
            }
            for task in batch.slots
        ],
        "standard_question": _question_payload(batch.standard_question),
        "student_question": _question_payload(batch.student_question),
    }


def _build_batch_qwen_prompt(batch: VlmQuestionBatchTask, student_name: str) -> str:
    policy_hint = _grading_policy_hint(batch.slots[0])
    payload = {"grading_task": _batch_task_payload(batch)}
    authority_rule = (
        "- STANDARD-ANSWER AUTHORITY: image 1 is the sole ground truth. Never replace, correct, extend, "
        "or second-guess its answer using your own solution or outside knowledge.\n"
    )
    objective_rule = (
        "- OBJECTIVE STRICT: every student's selected option, true/false value, fixed answer, matching, "
        "or ordering must be exactly the same as the corresponding labeled slot in image 1. Any different, "
        "missing, or extra option/value is wrong.\n"
    )
    subjective_rule = (
        "- SUBJECTIVE SEMANTIC: understand the standard answer's conclusion, key ideas, reasoning, and "
        "required points. Accept different wording only when the essential meaning matches.\n"
    )
    if policy_hint == "objective_strict":
        policy_instruction = "This is an OBJECTIVE question. Apply OBJECTIVE STRICT policy."
        policy_rules = authority_rule + objective_rule
    elif policy_hint == "subjective_semantic":
        policy_instruction = "This is a SUBJECTIVE question. Apply SUBJECTIVE SEMANTIC policy."
        policy_rules = authority_rule + subjective_rule
    else:
        policy_instruction = (
            "Classify the visible question first. Use OBJECTIVE STRICT for fixed-answer items and "
            "SUBJECTIVE SEMANTIC for open responses."
        )
        policy_rules = authority_rule + objective_rule + subjective_rule
    expected_slots = ", ".join(_slot_key(task) for task in batch.slots)
    return "".join(
        [
            "You are a strict school-exam grader. The user content contains exactly two images in order: ",
            "image 1 is the standard-answer packet and image 2 is the student-answer packet. ",
            "Each packet contains one parent question and all of its answer slots. ",
            "Every answer slot has a visible red rectangle and a red label such as 1_1 or 1_2. ",
            "The labels and red rectangles correspond by order in both images. ",
            "Compare every labeled slot independently; do not let one slot's answer affect another slot.\n\n",
            f"The student paper is: {student_name}.\n",
            f"Expected slot keys, which must all be returned exactly once: {expected_slots}\n\n",
            policy_instruction,
            "\n\nMandatory grading policies:\n",
            policy_rules,
            "\nRules:\n",
            f"1. Return question_id exactly as supplied: {batch.batch_id}. It identifies this parent-question batch.\n",
            "2. Return one item in slots for every expected slot key. Do not omit, merge, reorder, duplicate, "
            "or invent a slot key.\n",
            "3. Each slot correctResult must be 1 for correct, 2 for wrong, or 3 for blank/unanswered. "
            "A blank highlighted student slot is 3.\n",
            "4. Use only the corresponding labeled red slot in image 1 and image 2. Do not grade another slot.\n",
            "5. Write reason and analysis in Chinese. Keep correct-slot analysis brief; explain the error "
            "and correct approach for a wrong slot.\n",
            "6. Use plain Chinese text and Unicode math symbols only. Do not use TeX, LaTeX, Markdown, "
            "dollar-sign delimiters, caret exponent notation, or backslash characters.\n",
            "7. Do not return coordinates or extra fields. Return exactly one valid JSON object with this schema:\n",
            '{"question_id":1,"slots":[{"slot_key":"1_1","correctResult":1,"result":"对",'
            '"reason":"...","analysis":"...","confidence":0.0}]}\n\n',
            "Task metadata is read-only; image labels and red rectangles are authoritative:\n",
            json.dumps(payload, ensure_ascii=False),
        ]
    )


def _normalize_batch_decision(
    data: dict,
    batch: VlmQuestionBatchTask,
) -> dict[int, dict]:
    if not isinstance(data, dict):
        raise RuntimeError(f"Qwen batch result must be a JSON object, got {type(data).__name__}")
    returned_id = _to_int(data.get("question_id"), -1)
    if returned_id != batch.batch_id:
        raise RuntimeError(
            f"千问批次题号不一致: expected={batch.batch_id}, got={returned_id}"
        )
    items = data.get("slots")
    if not isinstance(items, list):
        raise RuntimeError("千问批量结果缺少 slots 数组")
    expected = {_slot_key(task): task for task in batch.slots}
    normalized: dict[int, dict] = {}
    for item in items:
        if not isinstance(item, dict):
            raise RuntimeError("千问批量结果包含非对象作答区")
        key = str(item.get("slot_key") or "").strip()
        if key not in expected:
            raise RuntimeError(f"千问返回未知或错误作答区标识: {key or '<empty>'}")
        task = expected[key]
        if task.task_id in normalized:
            raise RuntimeError(f"千问重复返回作答区: {key}")
        decision = dict(item)
        returned_slot_task_id = decision.get("task_id")
        if returned_slot_task_id is not None and _to_int(returned_slot_task_id, -1) != task.task_id:
            raise RuntimeError(f"千问作答区任务号不一致: {key}")
        decision["question_id"] = task.task_id
        normalized[task.task_id] = _normalize_decision(decision, task.task_id)
    missing = sorted(set(expected) - {str(item.get("slot_key") or "").strip() for item in items if isinstance(item, dict)})
    if missing:
        raise RuntimeError("千问批量结果缺少作答区: " + "、".join(missing))
    if len(normalized) != len(expected):
        raise RuntimeError("千问批量结果作答区数量不一致")
    return normalized


def _call_qwen_for_question_batch(
    client,
    model: str,
    batch: VlmQuestionBatchTask,
    std_image_url: str,
    stu_image_url: str,
    student_name: str,
) -> dict[int, dict]:
    prompt = _build_batch_qwen_prompt(batch, student_name)
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": std_image_url}},
                    {"type": "image_url", "image_url": {"url": stu_image_url}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        stream=False,
        timeout=180,
        extra_body=QWEN_CHAT_EXTRA_BODY,
    )
    content = completion.choices[0].message.content or ""
    return _normalize_batch_decision(_json_object_from_text(content), batch)


def _task_context_regions(
    task: VlmGradingTask,
    *,
    standard: bool,
    source_size: tuple[int, int],
    target_size: tuple[int, int],
) -> list[list[int]]:
    regions = task.standard_question.question_regions or [task.standard_question.question_bbox]
    if standard:
        projected = list(regions)
    else:
        projected = [
            _project_bbox_between_question_regions(
                region,
                task.standard_question.question_bbox,
                task.student_question.question_bbox,
                target_size,
            )
            or _scale_bbox(region, source_size, target_size)
            for region in regions
        ]
    answer_bbox = task.standard_answer_bbox if standard else task.student_answer_bbox
    if answer_bbox not in projected:
        projected.append(answer_bbox)
    return projected


def _match_questions(standard_questions: list[VlmQuestion], student_questions: list[VlmQuestion]) -> list[tuple[VlmQuestion, VlmQuestion]]:
    standard_ordered = sorted(standard_questions, key=lambda q: q.display_index)
    student_ordered = sorted(student_questions, key=lambda q: q.display_index)
    standard_ids = [q.question_id for q in standard_ordered]
    student_ids = [q.question_id for q in student_ordered]
    if len(standard_ordered) != len(student_ordered) or standard_ids != student_ids:
        raise RuntimeError(
            "题目匹配失败，已停止参照答案批改，避免错题错位。"
            f"标准答案题号顺序: {standard_ids}；学生题号顺序: {student_ids}"
        )
    return list(zip(standard_ordered, student_ordered))


def _slot_match_threshold(name: str, default: float) -> float:
    value = _to_float(os.environ.get(name), default)
    return min(0.35, max(0.005, value))


def _median(values: list[float], default: float = 0.0) -> float:
    if not values:
        return default
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _normalized_bbox_tuple(
    bbox: list[int], image_size: tuple[int, int]
) -> tuple[float, float, float, float]:
    width, height = image_size
    if width < 1 or height < 1:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        max(0.0, min(1.0, bbox[0] / width)),
        max(0.0, min(1.0, bbox[1] / height)),
        max(0.0, min(1.0, bbox[2] / width)),
        max(0.0, min(1.0, bbox[3] / height)),
    )


def _relative_bbox_tuple(
    bbox: list[int], region_bbox: list[int]
) -> tuple[float, float, float, float]:
    rx1, ry1, rx2, ry2 = region_bbox
    width = rx2 - rx1
    height = ry2 - ry1
    if width <= 0 or height <= 0:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        (bbox[0] - rx1) / width,
        (bbox[1] - ry1) / height,
        (bbox[2] - rx1) / width,
        (bbox[3] - ry1) / height,
    )


def _bbox_from_relative(
    bbox: tuple[float, float, float, float],
    region_bbox: list[int],
    image_size: tuple[int, int],
) -> list[int]:
    x1, y1, x2, y2 = region_bbox
    width = x2 - x1
    height = y2 - y1
    return _clamp_bbox(
        [
            x1 + bbox[0] * width,
            y1 + bbox[1] * height,
            x1 + bbox[2] * width,
            y1 + bbox[3] * height,
        ],
        image_size,
    )


def _normalized_bbox_center(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def _normalized_bbox_distance(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    lx, ly = _normalized_bbox_center(left)
    rx, ry = _normalized_bbox_center(right)
    return ((lx - rx) ** 2 + (ly - ry) ** 2) ** 0.5


def _bbox_intersection_over_min(
    left: list[int], right: list[int]
) -> float:
    """Return overlap against the smaller box, so nested OCR boxes match."""
    intersection_width = max(0, min(left[2], right[2]) - max(left[0], right[0]))
    intersection_height = max(0, min(left[3], right[3]) - max(left[1], right[1]))
    intersection = intersection_width * intersection_height
    if intersection <= 0:
        return 0.0
    left_area = max(1, (left[2] - left[0]) * (left[3] - left[1]))
    right_area = max(1, (right[2] - right[0]) * (right[3] - right[1]))
    return intersection / min(left_area, right_area)


def _bbox_from_normalized(
    bbox: tuple[float, float, float, float],
    image_size: tuple[int, int],
    *,
    offset: tuple[float, float] = (0.0, 0.0),
) -> list[int]:
    width, height = image_size
    dx, dy = offset
    return _clamp_bbox(
        [
            int(round((bbox[0] + dx) * width)),
            int(round((bbox[1] + dy) * height)),
            int(round((bbox[2] + dx) * width)),
            int(round((bbox[3] + dy) * height)),
        ],
        image_size,
    )


def build_reference_vlm_slot_template(documents: dict[str, dict]) -> list[VlmSlotTemplate]:
    """Merge answer locations from all OCR results into one page template."""
    detections: list[dict[str, Any]] = []
    for source_key, document in documents.items():
        if not isinstance(document, dict):
            continue
        questions = document.get("questions")
        if not isinstance(questions, list):
            continue
        raw_size = document.get("image_size")
        if isinstance(raw_size, (list, tuple)) and len(raw_size) >= 2:
            image_size = (_to_int(raw_size[0]), _to_int(raw_size[1]))
        else:
            image_path = str(document.get("image_path") or document.get("source_path") or "")
            if not image_path or not Path(image_path).is_file() or Image is None:
                continue
            with Image.open(image_path) as image:
                image_size = image.size
        if min(image_size) < 1:
            continue
        for question in questions:
            if not isinstance(question, VlmQuestion):
                continue
            for bbox in question.answer_bboxes:
                normalized = _normalized_bbox_tuple(bbox, image_size)
                detections.append(
                    {
                        "source_key": str(source_key),
                        "bbox": normalized,
                        "relative_bbox": _relative_bbox_tuple(
                            bbox, question.question_bbox
                        ),
                        "question_index": question.display_index,
                    }
                )

    if not detections:
        return []
    detections.sort(
        key=lambda item: (
            0 if item["source_key"] == "__standard__" else 1,
            item["source_key"],
            _normalized_bbox_center(item["bbox"])[1],
            _normalized_bbox_center(item["bbox"])[0],
        )
    )
    cluster_distance = _slot_match_threshold(
        "REFERENCE_VLM_TEMPLATE_CLUSTER_DISTANCE", 0.021
    )
    relative_cluster_distance = _slot_match_threshold(
        "REFERENCE_VLM_TEMPLATE_RELATIVE_CLUSTER_DISTANCE", 0.055
    )
    clusters: list[dict[str, Any]] = []
    for detection in detections:
        candidates: list[tuple[float, int]] = []
        for index, cluster in enumerate(clusters):
            if detection["source_key"] in cluster["source_keys"]:
                continue
            page_distance = _normalized_bbox_distance(
                detection["bbox"], cluster["bbox"]
            )
            relative_distance = _normalized_bbox_distance(
                detection["relative_bbox"], cluster["relative_bbox"]
            )
            same_question = detection["question_index"] in cluster["question_indices"]
            eligible_distances = []
            if page_distance <= cluster_distance:
                eligible_distances.append(page_distance)
            if same_question and relative_distance <= relative_cluster_distance:
                eligible_distances.append(relative_distance)
            if eligible_distances:
                candidates.append((min(eligible_distances), index))
        candidates.sort(key=lambda item: item[0])
        if candidates:
            cluster = clusters[candidates[0][1]]
            cluster["members"].append(detection["bbox"])
            cluster["relative_members"].append(detection["relative_bbox"])
            cluster["question_index_members"].append(detection["question_index"])
            cluster["source_keys"].add(detection["source_key"])
            cluster["question_indices"].add(detection["question_index"])
            if detection["source_key"] == "__standard__":
                cluster["standard_bbox"] = detection["bbox"]
                cluster["standard_question_index"] = detection["question_index"]
            cluster["bbox"] = cluster.get("standard_bbox") or tuple(
                _median([member[axis] for member in cluster["members"]])
                for axis in range(4)
            )
            cluster["relative_bbox"] = tuple(
                _median(
                    [member[axis] for member in cluster["relative_members"]]
                )
                for axis in range(4)
            )
        else:
            clusters.append(
                {
                    "bbox": detection["bbox"],
                    "relative_bbox": detection["relative_bbox"],
                    "members": [detection["bbox"]],
                    "relative_members": [detection["relative_bbox"]],
                    "question_index_members": [detection["question_index"]],
                    "source_keys": {detection["source_key"]},
                    "question_indices": {detection["question_index"]},
                    "standard_bbox": (
                        detection["bbox"]
                        if detection["source_key"] == "__standard__"
                        else None
                    ),
                    "standard_question_index": (
                        detection["question_index"]
                        if detection["source_key"] == "__standard__"
                        else None
                    ),
                }
            )

    clusters.sort(
        key=lambda cluster: (
            _normalized_bbox_center(cluster["bbox"])[1],
            _normalized_bbox_center(cluster["bbox"])[0],
        )
    )
    return [
        VlmSlotTemplate(
            slot_id=index,
            normalized_bbox=tuple(cluster["bbox"]),
            relative_bbox=tuple(cluster["relative_bbox"]),
            question_index=_to_int(
                cluster.get("standard_question_index"),
                _to_int(
                    _median(cluster.get("question_index_members") or []), 0
                ),
            ),
            support_count=len(cluster["source_keys"]),
            source_keys=tuple(sorted(cluster["source_keys"])),
        )
        for index, cluster in enumerate(clusters, start=1)
    ]


def _match_template_to_paper(
    slot_template: list[VlmSlotTemplate],
    questions: list[VlmQuestion],
    image_size: tuple[int, int],
) -> tuple[dict[int, tuple[VlmQuestion, int, list[int], float]], tuple[float, float], bool]:
    paper_slots = [
        (question, sub_index, bbox, _normalized_bbox_tuple(bbox, image_size))
        for question in questions
        for sub_index, bbox in enumerate(question.answer_bboxes, start=1)
    ]
    if not paper_slots:
        return {}, (0.0, 0.0), False
    broad_distance = _slot_match_threshold(
        "REFERENCE_VLM_TEMPLATE_INITIAL_DISTANCE", 0.065
    )

    def assign(offset: tuple[float, float], max_distance: float):
        dx, dy = offset
        candidates: list[tuple[float, int, int]] = []
        for template_index, template_slot in enumerate(slot_template):
            shifted = tuple(
                value + (dx if index % 2 == 0 else dy)
                for index, value in enumerate(template_slot.normalized_bbox)
            )
            for paper_index, (_question, _sub_index, _bbox, normalized) in enumerate(paper_slots):
                candidates.append(
                    (
                        _normalized_bbox_distance(shifted, normalized),
                        template_index,
                        paper_index,
                    )
                )
        candidates.sort(key=lambda item: item[0])
        used_template: set[int] = set()
        used_paper: set[int] = set()
        assigned: dict[int, tuple[int, float]] = {}
        for distance, template_index, paper_index in candidates:
            if distance > max_distance:
                break
            if template_index in used_template or paper_index in used_paper:
                continue
            used_template.add(template_index)
            used_paper.add(paper_index)
            assigned[template_index] = (paper_index, distance)
        return assigned

    initial = assign((0.0, 0.0), broad_distance)
    x_offsets: list[float] = []
    y_offsets: list[float] = []
    for template_index, (paper_index, _distance) in initial.items():
        tx, ty = _normalized_bbox_center(slot_template[template_index].normalized_bbox)
        px, py = _normalized_bbox_center(paper_slots[paper_index][3])
        x_offsets.append(px - tx)
        y_offsets.append(py - ty)
    offset = (_median(x_offsets), _median(y_offsets))
    final_distance = _slot_match_threshold(
        "REFERENCE_VLM_TEMPLATE_MATCH_DISTANCE", 0.035
    )
    assigned = assign(offset, final_distance)
    matches: dict[int, tuple[VlmQuestion, int, list[int], float]] = {}
    residuals: list[float] = []
    for template_index, (paper_index, distance) in assigned.items():
        question, sub_index, bbox, _normalized = paper_slots[paper_index]
        matches[template_index] = (question, sub_index, bbox, distance)
        residuals.append(distance)
    max_residual = _slot_match_threshold(
        "REFERENCE_VLM_TEMPLATE_MAX_REGISTRATION_ERROR", 0.015
    )
    registration_reliable = len(matches) >= 3 and _median(residuals, 1.0) <= max_residual
    return matches, offset, registration_reliable


def _build_template_grading_tasks(
    standard_questions: list[VlmQuestion],
    student_questions: list[VlmQuestion],
    standard_size: tuple[int, int],
    student_size: tuple[int, int],
    slot_template: list[VlmSlotTemplate],
) -> list[VlmGradingTask]:
    standard_matches, standard_offset, _standard_reliable = _match_template_to_paper(
        slot_template, standard_questions, standard_size
    )
    student_matches, student_offset, _student_registration_reliable = _match_template_to_paper(
        slot_template, student_questions, student_size
    )
    specs: list[dict[str, Any]] = []
    used_student_slots: set[tuple[int, int]] = set()
    reserved_student_slots = {
        (id(match[0]), match[1]) for match in student_matches.values()
    }
    projected_direct_distance = _slot_match_threshold(
        "REFERENCE_VLM_PROJECTED_DIRECT_MATCH_DISTANCE", 0.035
    )
    for template_index, template_slot in enumerate(slot_template):
        standard_match = standard_matches.get(template_index)
        student_match = student_matches.get(template_index)
        if standard_match:
            standard_question = standard_match[0]
            standard_bbox = standard_match[2]
        else:
            standard_question = next(
                (
                    question
                    for question in standard_questions
                    if question.display_index == template_slot.question_index
                ),
                None,
            )
            if standard_question is not None:
                standard_bbox = _bbox_from_relative(
                    template_slot.relative_bbox,
                    standard_question.question_bbox,
                    standard_size,
                )
            else:
                standard_bbox = _bbox_from_normalized(
                    template_slot.normalized_bbox,
                    standard_size,
                    offset=standard_offset,
                )
                standard_question = _question_for_bbox(
                    standard_questions, standard_bbox, standard_size
                )
        if standard_question is None:
            continue

        recovered_student_slot: Optional[tuple[int, list[int]]] = None
        if student_match:
            student_bbox = student_match[2]
            student_question = student_match[0]
        else:
            mapped_question_bbox = _scale_bbox(
                standard_question.question_bbox, standard_size, student_size
            )
            student_question = _question_for_bbox(
                student_questions, mapped_question_bbox, student_size
            )
            if student_question is None:
                continue

        projected_student_bbox = _project_bbox_between_question_regions(
            standard_bbox,
            standard_question.question_bbox,
            student_question.question_bbox,
            student_size,
        ) or _bbox_from_normalized(
            template_slot.normalized_bbox, student_size, offset=student_offset
        )
        if not student_match:
            student_bbox = projected_student_bbox

        if not student_match:
            direct_candidates = sorted(
                (
                    (
                        _normalized_center_distance(
                            projected_student_bbox,
                            student_size,
                            direct_bbox,
                            student_size,
                        ),
                        sub_index,
                        direct_bbox,
                    )
                    for sub_index, direct_bbox in enumerate(
                        student_question.answer_bboxes, start=1
                    )
                    if (id(student_question), sub_index) not in used_student_slots
                    and (id(student_question), sub_index) not in reserved_student_slots
                ),
                key=lambda item: item[0],
            )
            if direct_candidates and direct_candidates[0][0] <= projected_direct_distance:
                _distance, sub_index, direct_bbox = direct_candidates[0]
                student_bbox = direct_bbox
                recovered_student_slot = (sub_index, direct_bbox)

        if student_match:
            used_student_slots.add((id(student_match[0]), student_match[1]))
            anchor_source = "baidu_direct"
            has_mark_anchor = True
            has_handwriting_location = True
        elif recovered_student_slot:
            used_student_slots.add((id(student_question), recovered_student_slot[0]))
            anchor_source = "baidu_direct"
            has_mark_anchor = True
            has_handwriting_location = True
        elif "__standard__" in template_slot.source_keys:
            anchor_source = "standard_answer_projection"
            has_mark_anchor = True
            has_handwriting_location = False
        else:
            anchor_source = "batch_template_projection"
            has_mark_anchor = True
            has_handwriting_location = False
        specs.append(
            {
                "standard_question": standard_question,
                "student_question": student_question,
                "standard_bbox": standard_bbox,
                "student_bbox": student_bbox,
                "has_mark_anchor": has_mark_anchor,
                "has_handwriting_location": has_handwriting_location,
                "anchor_source": anchor_source,
                "template_slot_id": template_slot.slot_id,
                "projected_student_bbox": projected_student_bbox,
            }
        )

    # The reviewed standard-answer template is authoritative for slot count.
    # Any unmatched student OCR box may refine a template slot's physical
    # handwriting anchor, but must never create a second grading task.
    overlap_threshold = min(
        1.0,
        max(
            0.1,
            _to_float(
                os.environ.get("REFERENCE_VLM_DIRECT_SLOT_OVERLAP_RATIO"),
                0.65,
            ),
        ),
    )
    recovered_by_spec: dict[int, list[list[int]]] = {}
    for student_question in student_questions:
        for student_sub_index, student_bbox in enumerate(
            student_question.answer_bboxes, start=1
        ):
            if (id(student_question), student_sub_index) in used_student_slots:
                continue
            candidates: list[tuple[int, float, float, int]] = []
            for spec_index, spec in enumerate(specs):
                if spec["student_question"] is not student_question:
                    continue
                projected_bbox = spec["projected_student_bbox"]
                overlap = _bbox_intersection_over_min(
                    projected_bbox, student_bbox
                )
                distance = _normalized_center_distance(
                    projected_bbox,
                    student_size,
                    student_bbox,
                    student_size,
                )
                if (
                    overlap < overlap_threshold
                    and distance > projected_direct_distance
                ):
                    continue
                candidates.append(
                    (
                        0 if overlap >= overlap_threshold else 1,
                        -overlap,
                        distance,
                        spec_index,
                    )
                )
            if not candidates:
                continue
            candidates.sort()
            spec_index = candidates[0][3]
            recovered_by_spec.setdefault(spec_index, []).append(student_bbox)
            used_student_slots.add((id(student_question), student_sub_index))

    for spec_index, recovered_boxes in recovered_by_spec.items():
        spec = specs[spec_index]
        direct_boxes = list(recovered_boxes)
        if spec["has_handwriting_location"]:
            direct_boxes.append(spec["student_bbox"])
        merged_bbox = _bbox_union(direct_boxes, student_size)
        if merged_bbox:
            spec["student_bbox"] = merged_bbox
            spec["has_mark_anchor"] = True
            spec["has_handwriting_location"] = True
            spec["anchor_source"] = "baidu_direct"

    grouped_specs: dict[int, list[dict[str, Any]]] = {}
    for spec in specs:
        grouped_specs.setdefault(id(spec["student_question"]), []).append(spec)
    ordered_specs: list[dict[str, Any]] = []
    for student_question in sorted(student_questions, key=lambda item: item.display_index):
        group = grouped_specs.get(id(student_question), [])
        if not group:
            continue
        centers_x = [
            (spec["student_bbox"][0] + spec["student_bbox"][2]) / 2.0
            for spec in group
        ]
        centers_y = [
            (spec["student_bbox"][1] + spec["student_bbox"][3]) / 2.0
            for spec in group
        ]
        horizontal = (max(centers_x) - min(centers_x)) > (
            max(centers_y) - min(centers_y)
        ) * 1.8
        if horizontal:
            group.sort(
                key=lambda spec: (
                    (spec["student_bbox"][0] + spec["student_bbox"][2]) / 2.0,
                    (spec["student_bbox"][1] + spec["student_bbox"][3]) / 2.0,
                )
            )
        else:
            group.sort(
                key=lambda spec: (
                    (spec["student_bbox"][1] + spec["student_bbox"][3]) / 2.0,
                    (spec["student_bbox"][0] + spec["student_bbox"][2]) / 2.0,
                )
            )
        ordered_specs.extend(group)
    specs = ordered_specs
    tasks: list[VlmGradingTask] = []
    sub_counts: dict[int, int] = {}
    for spec in specs:
        student_question = spec["student_question"]
        question_key = id(student_question)
        sub_counts[question_key] = sub_counts.get(question_key, 0) + 1
        tasks.append(
            VlmGradingTask(
                task_id=len(tasks) + 1,
                student_question=student_question,
                standard_question=spec["standard_question"],
                student_answer_bbox=_clamp_bbox(spec["student_bbox"], student_size),
                standard_answer_bbox=_clamp_bbox(spec["standard_bbox"], standard_size),
                student_context_bbox=_slot_context_bbox(
                    student_question, spec["student_bbox"], student_size
                ),
                standard_context_bbox=_slot_context_bbox(
                    spec["standard_question"], spec["standard_bbox"], standard_size
                ),
                sub_index=sub_counts[question_key],
                has_mark_anchor=spec["has_mark_anchor"],
                has_handwriting_location=spec["has_handwriting_location"],
                is_answer_slot=True,
                anchor_source=spec["anchor_source"],
                template_slot_id=spec["template_slot_id"],
            )
        )

    graded_question_ids = {id(task.student_question) for task in tasks}
    for student_question in student_questions:
        if id(student_question) in graded_question_ids:
            continue
        mapped_standard_bbox = _scale_bbox(
            student_question.question_bbox, student_size, standard_size
        )
        standard_question = _question_for_bbox(
            standard_questions, mapped_standard_bbox, standard_size
        )
        if standard_question is None:
            continue
        tasks.append(
            VlmGradingTask(
                task_id=len(tasks) + 1,
                student_question=student_question,
                standard_question=standard_question,
                student_answer_bbox=student_question.question_bbox,
                standard_answer_bbox=standard_question.question_bbox,
                student_context_bbox=student_question.question_bbox,
                standard_context_bbox=standard_question.question_bbox,
                sub_index=1,
                has_mark_anchor=False,
                has_handwriting_location=False,
                is_answer_slot=False,
                anchor_source="none",
                template_slot_id=None,
            )
        )
    return tasks


def _build_grading_tasks(
    standard_questions: list[VlmQuestion],
    student_questions: list[VlmQuestion],
    standard_size: tuple[int, int],
    student_size: tuple[int, int],
    slot_template: Optional[list[VlmSlotTemplate]] = None,
) -> list[VlmGradingTask]:
    """Build one immutable grading task for every reliably located answer slot.

    Baidu may split a printed parent question differently between papers, so
    answer slots are matched globally by normalized page position. Parent
    question ids are retained only for JSON write-back and for the crop
    context. This prevents a duplicated or shifted qus_id from moving a
    decision to another handwriting area.
    """
    if not standard_questions or not student_questions:
        raise RuntimeError("No gradable question was returned by paper_cut_edu_vlm")
    if slot_template:
        tasks = _build_template_grading_tasks(
            standard_questions,
            student_questions,
            standard_size,
            student_size,
            slot_template,
        )
        if tasks:
            return tasks

    standard_slots = [
        (question, slot_index, bbox)
        for question in standard_questions
        for slot_index, bbox in enumerate(question.answer_bboxes, start=1)
    ]
    student_slots = [
        (question, slot_index, bbox)
        for question in student_questions
        for slot_index, bbox in enumerate(question.answer_bboxes, start=1)
    ]
    strict_distance = _slot_match_threshold("REFERENCE_VLM_SLOT_MATCH_DISTANCE", 0.035)
    loose_distance = _slot_match_threshold("REFERENCE_VLM_SLOT_FALLBACK_DISTANCE", 0.065)
    candidates = sorted(
        (
            (
                _normalized_center_distance(std_bbox, standard_size, stu_bbox, student_size),
                standard_index,
                student_index,
            )
            for standard_index, (_std_q, _std_sub, std_bbox) in enumerate(standard_slots)
            for student_index, (_stu_q, _stu_sub, stu_bbox) in enumerate(student_slots)
        ),
        key=lambda item: item[0],
    )
    used_standard: set[int] = set()
    used_student: set[int] = set()
    matched: dict[int, tuple[int, bool]] = {}

    def assign_candidates(max_distance: float, *, is_confident: bool) -> None:
        for distance, standard_index, student_index in candidates:
            if distance > max_distance:
                break
            if standard_index in used_standard or student_index in used_student:
                continue
            used_standard.add(standard_index)
            used_student.add(student_index)
            matched[standard_index] = (student_index, is_confident)

    # Only a tight layout match is allowed to become a handwriting mark
    # anchor. A looser fallback can still receive an AI analysis, but cannot
    # produce a potentially misplaced check/cross.
    assign_candidates(strict_distance, is_confident=True)
    assign_candidates(loose_distance, is_confident=False)

    tasks: list[VlmGradingTask] = []
    used_sub_indices: dict[int, set[int]] = {}

    def next_sub_index(question: VlmQuestion, preferred: int) -> int:
        used = used_sub_indices.setdefault(id(question), set())
        index = max(1, preferred)
        while index in used:
            index += 1
        used.add(index)
        return index

    def append_task(
        standard_question: VlmQuestion,
        student_question: VlmQuestion,
        standard_answer_bbox: list[int],
        student_answer_bbox: list[int],
        *,
        preferred_sub_index: int,
        has_mark_anchor: bool,
        has_handwriting_location: bool,
        is_answer_slot: bool,
        anchor_source: str = "none",
    ) -> None:
        tasks.append(
            VlmGradingTask(
                task_id=len(tasks) + 1,
                student_question=student_question,
                standard_question=standard_question,
                student_answer_bbox=_clamp_bbox(student_answer_bbox, student_size),
                standard_answer_bbox=_clamp_bbox(standard_answer_bbox, standard_size),
                student_context_bbox=_slot_context_bbox(
                    student_question, student_answer_bbox, student_size
                ),
                standard_context_bbox=_slot_context_bbox(
                    standard_question, standard_answer_bbox, standard_size
                ),
                sub_index=next_sub_index(student_question, preferred_sub_index),
                has_mark_anchor=has_mark_anchor,
                has_handwriting_location=has_handwriting_location,
                is_answer_slot=is_answer_slot,
                anchor_source=anchor_source,
                template_slot_id=None,
            )
        )

    for standard_index, (standard_question, standard_sub_index, standard_bbox) in enumerate(standard_slots):
        match = matched.get(standard_index)
        if match is not None:
            student_index, _has_confident_anchor = match
            student_question, student_sub_index, student_bbox = student_slots[student_index]
            append_task(
                standard_question,
                student_question,
                standard_bbox,
                student_bbox,
                preferred_sub_index=student_sub_index,
                has_mark_anchor=True,
                has_handwriting_location=True,
                is_answer_slot=True,
                anchor_source="baidu_direct",
            )
            continue

        # The standard slot exists but Baidu did not locate a student
        # handwriting box. Its relative position inside the matched question
        # is still a stable answer-area anchor for blank-answer grading.
        mapped_question_bbox = _scale_bbox(
            standard_question.question_bbox, standard_size, student_size
        )
        student_question = _question_for_bbox(
            student_questions, mapped_question_bbox, student_size
        )
        if student_question is None:
            continue
        mapped_student_bbox = _project_bbox_between_question_regions(
            standard_bbox,
            standard_question.question_bbox,
            student_question.question_bbox,
            student_size,
        ) or _scale_bbox(standard_bbox, standard_size, student_size)
        append_task(
            standard_question,
            student_question,
            standard_bbox,
            mapped_student_bbox,
            preferred_sub_index=standard_sub_index,
            has_mark_anchor=True,
            has_handwriting_location=False,
            is_answer_slot=True,
            anchor_source="standard_answer_projection",
        )

    # A direct student ans_location is always a valid mark position, even
    # when the standard-answer OCR missed the corresponding slot.
    for student_index, (student_question, student_sub_index, student_bbox) in enumerate(student_slots):
        if student_index in used_student:
            continue
        mapped_standard_bbox = _scale_bbox(student_bbox, student_size, standard_size)
        standard_question = _question_for_bbox(
            standard_questions, mapped_standard_bbox, standard_size
        )
        if standard_question is None:
            continue
        append_task(
            standard_question,
            student_question,
            mapped_standard_bbox,
            student_bbox,
            preferred_sub_index=student_sub_index,
            has_mark_anchor=True,
            has_handwriting_location=True,
            is_answer_slot=True,
            anchor_source="baidu_direct",
        )

    # Questions without any answer-location data are still reviewed as a
    # whole, but never gain an invented handwriting mark location.
    graded_question_ids = {id(task.student_question) for task in tasks}
    for student_question in student_questions:
        if id(student_question) in graded_question_ids:
            continue
        mapped_standard_bbox = _scale_bbox(
            student_question.question_bbox, student_size, standard_size
        )
        standard_question = _question_for_bbox(
            standard_questions, mapped_standard_bbox, standard_size
        )
        if standard_question is None:
            continue
        append_task(
            standard_question,
            student_question,
            standard_question.question_bbox,
            student_question.question_bbox,
            preferred_sub_index=1,
            has_mark_anchor=False,
            has_handwriting_location=False,
            is_answer_slot=False,
        )

    if not tasks:
        raise RuntimeError("paper_cut_edu_vlm returned no answer slots or question regions to grade")
    return tasks


def _status_from_code(code: int) -> str:
    return RESULT_TEXT.get(code, "错")


def _result_label(code: int, partial_ratio=None) -> str:
    """把状态码拼成展示文本；半对 带上比例（如 半对（0.6））。"""
    text = _status_from_code(code)
    if code == PARTIAL and partial_ratio is not None:
        try:
            ratio = min(1.0, max(0.0, float(partial_ratio)))
            return f"半对（{ratio:g}）"
        except (TypeError, ValueError):
            pass
    return text


def _aggregate_question_grading(question: VlmQuestion) -> None:
    sub_results = question.raw.get("sub_grading_results")
    if not isinstance(sub_results, list) or not sub_results:
        return
    sub_results.sort(
        key=lambda item: (
            _to_int(item.get("sub_index"), 0) if isinstance(item, dict) else 0,
            _to_int(item.get("question_id"), 0) if isinstance(item, dict) else 0,
        )
    )
    codes = [
        _to_int(item.get("correctResult"), WRONG)
        for item in sub_results
        if isinstance(item, dict)
    ]
    if codes and all(code == CORRECT for code in codes):
        aggregate_code = CORRECT
        aggregate_ratio = None
    elif codes and all(code == UNANSWERED for code in codes):
        aggregate_code = UNANSWERED
        aggregate_ratio = None
    elif not any(code == WRONG for code in codes) and any(code == PARTIAL for code in codes):
        # 无错、且至少一个「半对」→ 整题判半对；比例取各半对作答区的均值。
        aggregate_code = PARTIAL
        aggregate_ratio = None
        partial_ratios: list[float] = []
        for item in sub_results:
            if not isinstance(item, dict):
                continue
            if _to_int(item.get("correctResult"), WRONG) != PARTIAL:
                continue
            ratio_val = item.get("partial_ratio")
            if ratio_val is None:
                continue
            try:
                ratio = float(ratio_val)
            except (TypeError, ValueError):
                continue
            partial_ratios.append(min(1.0, max(0.0, ratio)))
        if partial_ratios:
            aggregate_ratio = round(sum(partial_ratios) / len(partial_ratios), 2)
    else:
        aggregate_code = WRONG
        aggregate_ratio = None

    summaries: list[str] = []
    for item in sub_results:
        if not isinstance(item, dict):
            continue
        analysis = str(item.get("analysis") or item.get("reason") or "").strip()
        summaries.append(
            f"\u4f5c\u7b54\u533a{_to_int(item.get('sub_index'), 1)}"
            f"\uff1a{_status_from_code(_to_int(item.get('correctResult'), WRONG))}"
            + (f" - {analysis}" if analysis else "")
        )
    combined = "\n".join(summaries)
    analyses = [
        str(item.get("analysis") or item.get("reason") or "").strip()
        for item in sub_results
        if isinstance(item, dict)
    ]
    aggregate_analysis = analyses[0] if len(set(analyses)) == 1 else combined
    grading = {
        "question_id": question.display_index,
        "correctResult": aggregate_code,
        "result": _status_from_code(aggregate_code),
        "reason": aggregate_analysis,
        "analysis": aggregate_analysis,
        "partial_ratio": aggregate_ratio,
        "confidence": min(
            [
                _to_float(item.get("confidence"), 0.0)
                for item in sub_results
                if isinstance(item, dict)
            ]
            or [0.0]
        ),
    }
    question.raw["correctResult"] = aggregate_code
    question.raw["result"] = grading["result"]
    question.raw["partial_ratio"] = aggregate_ratio
    question.raw["reason"] = grading["reason"]
    question.raw["ai_analysis"] = grading["analysis"]
    question.raw["grading_result"] = grading


def _insert_sub_grading_result(
    question: VlmQuestion,
    decision: dict,
    *,
    task_id: int,
    sub_index: int,
    answer_bbox: list[int],
    has_mark_anchor: bool,
    has_handwriting_location: bool,
    is_answer_slot: bool,
    anchor_source: str = "none",
    template_slot_id: Optional[int] = None,
) -> None:
    if not isinstance(decision, dict):
        raise RuntimeError(
            f"Question task {task_id} Qwen result must be a JSON object, "
            f"got {type(decision).__name__}"
        )
    normalized = _normalize_decision(decision, task_id)
    sub_result = {
        "question_id": task_id,
        "sub_index": sub_index,
        "correctResult": normalized["correctResult"],
        "result": normalized["result"],
        "reason": normalized["reason"],
        "analysis": normalized["analysis"],
        "confidence": normalized["confidence"],
        "partial_ratio": normalized.get("partial_ratio"),
        "answer_bbox": list(answer_bbox),
        "has_handwriting_location": bool(has_handwriting_location),
        "has_mark_anchor": bool(has_mark_anchor),
        "is_answer_slot": bool(is_answer_slot),
        "anchor_source": str(anchor_source or "none"),
        "template_slot_id": template_slot_id,
    }
    existing = question.raw.get("sub_grading_results")
    if not isinstance(existing, list):
        existing = []
        question.raw["sub_grading_results"] = existing
    if any(
        isinstance(item, dict)
        and _to_int(item.get("question_id"), -1) == task_id
        for item in existing
    ):
        raise RuntimeError(f"Duplicate Qwen task id while writing slot result: {task_id}")
    existing.append(sub_result)
    _aggregate_question_grading(question)


def _insert_grading_result(question: VlmQuestion, decision: dict) -> None:
    # Compatibility helper for callers that still provide one result per
    # parent question. The reference-VLM pipeline itself uses the slot-level
    # writer above.
    task_id = _to_int(decision.get("question_id") if isinstance(decision, dict) else None, question.display_index)
    _insert_sub_grading_result(
        question,
        decision,
        task_id=task_id,
        sub_index=1,
        answer_bbox=question.answer_bbox or question.question_bbox,
        has_mark_anchor=bool(question.answer_bbox),
        has_handwriting_location=bool(question.answer_bbox),
        is_answer_slot=bool(question.answer_bbox),
    )


def _build_blocks(questions: list[VlmQuestion]) -> list[dict]:
    blocks: list[dict] = []
    for q in sorted(questions, key=lambda item: item.display_index):
        sub_results = q.raw.get("sub_grading_results")
        if isinstance(sub_results, list) and sub_results:
            for sub_result in sorted(
                (item for item in sub_results if isinstance(item, dict)),
                key=lambda item: (_to_int(item.get("sub_index"), 0), _to_int(item.get("question_id"), 0)),
            ):
                answer_bbox = sub_result.get("answer_bbox")
                if not isinstance(answer_bbox, list) or len(answer_bbox) < 4:
                    answer_bbox = q.answer_bbox or q.question_bbox
                answer_bbox = [int(_to_float(value)) for value in answer_bbox[:4]]
                code = _to_int(sub_result.get("correctResult"), WRONG)
                blocks.append(
                    {
                        "baidu_original_index": q.question_id,
                        "baidu_real_name": str(q.display_index),
                        "index": q.display_index,
                        "sub_index": _to_int(sub_result.get("sub_index"), 1),
                        "is_question": True,
                        "result": _result_label(code, sub_result.get("partial_ratio")),
                        "partial_ratio": sub_result.get("partial_ratio"),
                        "comment": str(
                            sub_result.get("analysis") or sub_result.get("reason") or ""
                        ).strip(),
                        # Use the complete handwriting area, matching the
                        # intelligent-model renderer's bbox contract.
                        "bbox": answer_bbox,
                        "has_handwriting_location": bool(
                            sub_result.get("has_handwriting_location")
                        ),
                        "has_mark_anchor": bool(
                            sub_result.get(
                                "has_mark_anchor",
                                sub_result.get("has_handwriting_location"),
                            )
                        ),
                        "baidu_correct_result": code,
                        "baidu_question_bbox": q.question_bbox,
                        "baidu_is_slot": bool(sub_result.get("is_answer_slot")),
                        "reference_vlm_question_id": q.question_id,
                        "reference_vlm_task_id": _to_int(sub_result.get("question_id"), 0),
                        "reference_vlm_answer_bbox": answer_bbox,
                        "reference_vlm_anchor_source": str(
                            sub_result.get("anchor_source") or "none"
                        ),
                        "reference_vlm_template_slot_id": sub_result.get(
                            "template_slot_id"
                        ),
                    }
                )
            continue
        grading = q.raw.get("grading_result") if isinstance(q.raw.get("grading_result"), dict) else {}
        code = _to_int(grading.get("correctResult"), _to_int(q.raw.get("correctResult"), WRONG))
        result_text = _result_label(code, grading.get("partial_ratio"))
        blocks.append(
            {
                "baidu_original_index": q.question_id,
                "baidu_real_name": str(q.display_index),
                "index": q.display_index,
                "sub_index": 1,
                "is_question": True,
                "result": result_text,
                "partial_ratio": grading.get("partial_ratio"),
                "comment": str(grading.get("analysis") or grading.get("reason") or "").strip(),
                "bbox": q.bbox,
                "has_handwriting_location": bool(q.answer_bbox),
                "has_mark_anchor": bool(q.answer_bbox),
                "baidu_correct_result": code,
                "baidu_question_bbox": q.question_bbox,
                "baidu_is_slot": False,
                "reference_vlm_question_id": q.question_id,
            }
        )
    return blocks


def _summarize_result_text(questions: list[VlmQuestion]) -> str:
    total = 0
    correct = wrong = unanswered = partial = 0
    lines: list[str] = []
    for q in sorted(questions, key=lambda item: item.display_index):
        sub_results = q.raw.get("sub_grading_results")
        if isinstance(sub_results, list) and sub_results:
            for sub_result in sorted(
                (item for item in sub_results if isinstance(item, dict)),
                key=lambda item: (_to_int(item.get("sub_index"), 0), _to_int(item.get("question_id"), 0)),
            ):
                total += 1
                code = _to_int(sub_result.get("correctResult"), WRONG)
                if code == CORRECT:
                    correct += 1
                elif code == UNANSWERED:
                    unanswered += 1
                elif code == PARTIAL:
                    partial += 1
                else:
                    wrong += 1
                analysis = str(sub_result.get("analysis") or sub_result.get("reason") or "").strip()
                lines.append(
                    f"\u7b2c{q.display_index}\u9898-\u4f5c\u7b54\u533a"
                    f"{_to_int(sub_result.get('sub_index'), 1)}"
                    f"\uff1a{_result_label(code, sub_result.get('partial_ratio'))} - {analysis}"
                )
            continue
        total += 1
        grading = q.raw.get("grading_result") if isinstance(q.raw.get("grading_result"), dict) else {}
        code = _to_int(grading.get("correctResult"), WRONG)
        if code == CORRECT:
            correct += 1
        elif code == UNANSWERED:
            unanswered += 1
        elif code == PARTIAL:
            partial += 1
        else:
            wrong += 1
        analysis = str(grading.get("analysis") or grading.get("reason") or "").strip()
        lines.append(f"第{q.display_index}题：{_result_label(code, grading.get('partial_ratio'))} - {analysis}")
    header = f"总题量：{total}；正确：{correct}；错误：{wrong}；半对：{partial}；未作答：{unanswered}"
    return "\n".join([header, "逐题讲解：", *lines])


def _asset_info(path: Path, bbox: Optional[list[int]]) -> dict:
    return {
        "absolute_path": str(path),
        "relative_to_grading_data": _relative_to_grading_root(path),
        "bbox": bbox,
    }


def _empty_exam_db(class_id: str, exam_name: str, folder_safe: str, kind: str) -> dict:
    return {
        "kind": kind,
        "class_id": class_id,
        "exam_name": exam_name,
        "folder_safe": folder_safe,
        "updated_at": _now_iso(),
        "papers": {},
        "summary": {},
    }


def _update_exam_summary(data: dict) -> None:
    papers = data.get("papers") if isinstance(data.get("papers"), dict) else {}
    total_questions = 0
    total_wrong = 0
    total_correct = 0
    total_unanswered = 0
    for paper in papers.values():
        if not isinstance(paper, dict):
            continue
        summary = paper.get("summary") if isinstance(paper.get("summary"), dict) else {}
        total_questions += _to_int(summary.get("question_count"), 0)
        total_wrong += _to_int(summary.get("wrong_count"), 0)
        total_correct += _to_int(summary.get("correct_count"), 0)
        total_unanswered += _to_int(summary.get("blank_count"), 0)
    data["updated_at"] = _now_iso()
    data["summary"] = {
        "paper_count": len(papers),
        "question_count": total_questions,
        "correct_count": total_correct,
        "wrong_count": total_wrong,
        "blank_count": total_unanswered,
    }


def _reference_pages_from_existing(paper: Any, *, analysis: bool) -> dict[str, dict]:
    if not isinstance(paper, dict):
        return {}
    pages = paper.get("pages")
    if isinstance(pages, dict):
        return {
            str(key): copy.deepcopy(value)
            for key, value in pages.items()
            if isinstance(value, dict)
        }

    source_filenames = paper.get("source_filenames")
    if not isinstance(source_filenames, list) or not source_filenames:
        return {}
    source_filename = str(source_filenames[0] or "").strip()
    if not source_filename:
        return {}
    page_no = _paper_page_no(source_filename)
    page = {
        "page_no": page_no,
        "source_filename": source_filename,
        "updated_at": paper.get("updated_at") or _now_iso(),
        "source": copy.deepcopy(paper.get("source") or {}),
        "summary": copy.deepcopy(paper.get("summary") or {}),
    }
    if analysis:
        page["wrong_question_analysis"] = copy.deepcopy(
            paper.get("wrong_question_analysis") or []
        )
    else:
        page["questions"] = copy.deepcopy(paper.get("questions") or [])
        page["wrong_questions"] = copy.deepcopy(paper.get("wrong_questions") or [])
    return {str(page_no): page}


def _aggregate_reference_pages(
    paper_box: str,
    student: dict,
    pages: dict[str, dict],
    *,
    analysis: bool,
) -> dict:
    ordered_pages = sorted(
        (
            (_to_int(key, _to_int(value.get("page_no"), 1)), value)
            for key, value in pages.items()
            if isinstance(value, dict)
        ),
        key=lambda item: item[0],
    )
    normalized_pages = {str(page_no): value for page_no, value in ordered_pages}
    source_filenames = [
        str(page.get("source_filename") or "").strip()
        for _page_no, page in ordered_pages
        if str(page.get("source_filename") or "").strip()
    ]
    summary = {
        "question_count": sum(
            _to_int((page.get("summary") or {}).get("question_count"), 0)
            for _page_no, page in ordered_pages
        ),
        "correct_count": sum(
            _to_int((page.get("summary") or {}).get("correct_count"), 0)
            for _page_no, page in ordered_pages
        ),
        "wrong_count": sum(
            _to_int((page.get("summary") or {}).get("wrong_count"), 0)
            for _page_no, page in ordered_pages
        ),
        "blank_count": sum(
            _to_int((page.get("summary") or {}).get("blank_count"), 0)
            for _page_no, page in ordered_pages
        ),
        "wrong_question_count": sum(
            _to_int((page.get("summary") or {}).get("wrong_question_count"), 0)
            for _page_no, page in ordered_pages
        ),
    }
    sources_by_page = {
        str(page_no): copy.deepcopy(page.get("source") or {})
        for page_no, page in ordered_pages
    }
    latest_source = copy.deepcopy(ordered_pages[-1][1].get("source") or {}) if ordered_pages else {}
    result = {
        "paper_name": paper_box,
        "source_filenames": source_filenames,
        "student": copy.deepcopy(student) if isinstance(student, dict) else {"name": paper_box},
        "updated_at": _now_iso(),
        "source": latest_source,
        "sources_by_page": sources_by_page,
        "summary": summary,
        "pages": normalized_pages,
    }
    if analysis:
        result["wrong_question_analysis"] = [
            copy.deepcopy(question)
            for _page_no, page in ordered_pages
            for question in (page.get("wrong_question_analysis") or [])
            if isinstance(question, dict)
        ]
    else:
        result["questions"] = [
            copy.deepcopy(question)
            for _page_no, page in ordered_pages
            for question in (page.get("questions") or [])
            if isinstance(question, dict)
        ]
        result["wrong_questions"] = [
            copy.deepcopy(question)
            for _page_no, page in ordered_pages
            for question in (page.get("wrong_questions") or [])
            if isinstance(question, dict)
        ]
    return result


def _safe_infer_student(paper_box: str, students: Any) -> dict:
    normalized: list[dict] = []
    if isinstance(students, list):
        for item in students:
            if isinstance(item, dict):
                normalized.append(item)
            elif hasattr(item, "_mapping"):
                try:
                    normalized.append(dict(item._mapping))
                except Exception:
                    continue
    try:
        student = _infer_student_from_paper_name(paper_box, normalized)
        if isinstance(student, dict):
            return student
    except Exception:
        print(f"参照答案批改学生匹配失败 [{paper_box}]")
        print(traceback.format_exc())
    return {"name": paper_box, "matched_by": "filename", "matched": False}


def _save_reference_vlm_artifacts(
    *,
    folder_safe: str,
    paper_name: str,
    source_filename: str,
    source_image_path: str,
    enriched_raw: dict,
    questions: list[VlmQuestion],
) -> None:
    layout = _ct_layout(folder_safe)
    records_path = layout["records_path"]
    analysis_path = layout["analysis_path"]
    assets_root = layout["assets_dir"]
    if not isinstance(records_path, Path) or not isinstance(analysis_path, Path) or not isinstance(assets_root, Path):
        return

    class_id = str(layout.get("class_id") or "")
    exam_name = str(layout.get("exam_name") or folder_safe)
    paper_box = _paper_box_name(paper_name)
    page_no = _paper_page_no(source_filename or paper_name)
    paper_dir = assets_root / _safe_json_stem(paper_box) / f"p{page_no}"
    paper_dir.mkdir(parents=True, exist_ok=True)

    raw_dir = assets_root / "_reference_vlm_json"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_json_path = raw_dir / f"{_safe_json_stem(paper_box)}_p{page_no}.json"
    _write_json(raw_json_path, enriched_raw)

    wrong_questions: list[dict] = []
    questions_records: list[dict] = []
    correct_count = wrong_count = blank_count = 0

    try:
        img0 = Image.open(source_image_path).convert("RGB") if Image is not None else None
    except Exception:
        img0 = None

    try:
        for q in sorted(questions, key=lambda item: item.display_index):
            sub_results = q.raw.get("sub_grading_results")
            if isinstance(sub_results, list) and sub_results:
                for sub_result in sorted(
                    (item for item in sub_results if isinstance(item, dict)),
                    key=lambda item: (
                        _to_int(item.get("sub_index"), 0),
                        _to_int(item.get("question_id"), 0),
                    ),
                ):
                    code = _to_int(sub_result.get("correctResult"), WRONG)
                    if code == CORRECT:
                        correct_count += 1
                    elif code == UNANSWERED:
                        blank_count += 1
                    else:
                        wrong_count += 1
                    sub_index = _to_int(sub_result.get("sub_index"), 1)
                    answer_bbox = sub_result.get("answer_bbox")
                    if not isinstance(answer_bbox, list) or len(answer_bbox) < 4:
                        answer_bbox = q.answer_bbox or q.question_bbox
                    answer_bbox = [int(_to_float(value)) for value in answer_bbox[:4]]
                    record = {
                        "question_key": f"p{page_no}_q{q.display_index}_s{sub_index}",
                        "display_title": f"\u7b2c{q.display_index}\u9898-\u4f5c\u7b54\u533a{sub_index}",
                        "page_no": page_no,
                        "question_index": q.display_index,
                        "baidu_question_id": q.question_id,
                        "display_index": q.display_index,
                        "slot_index": sub_index,
                        "qwen_task_id": _to_int(sub_result.get("question_id"), 0),
                        "status_code": code,
                        "status": _status_from_code(code),
                        "question_type": q.question_type,
                        "question": q.question_words,
                        "student_answer": q.answer_words,
                        "choices": q.choices,
                        "reason": str(sub_result.get("reason") or "").strip(),
                        "analysis": str(sub_result.get("analysis") or "").strip(),
                        "render": {
                            # Keep the persisted render bbox identical to the
                            # bbox consumed by the shared mark renderer.
                            "bbox": answer_bbox,
                            "question_bbox": q.question_bbox,
                            "answer_bbox": answer_bbox,
                            "has_handwriting_location": bool(
                                sub_result.get("has_handwriting_location")
                            ),
                            "has_mark_anchor": bool(
                                sub_result.get(
                                    "has_mark_anchor",
                                    sub_result.get("has_handwriting_location"),
                                )
                            ),
                            "anchor_source": str(
                                sub_result.get("anchor_source") or "none"
                            ),
                            "template_slot_id": sub_result.get("template_slot_id"),
                            "comment": str(
                                sub_result.get("analysis") or sub_result.get("reason") or ""
                            ).strip(),
                        },
                        "source_filename": source_filename,
                        "provider": "baidu_paper_cut_edu_vlm_qwen",
                    }
                    if img0 is not None and code in (WRONG, UNANSWERED):
                        q_path = paper_dir / f"{record['question_key']}_question.jpg"
                        a_path = paper_dir / f"{record['question_key']}_answer.jpg"
                        q_saved = _save_crop(img0, q.question_bbox, q_path, pad=12)
                        a_saved = _save_crop(img0, answer_bbox, a_path, pad=18)
                        assets = {"status": "ok"}
                        if q_saved:
                            assets["question_image"] = _asset_info(q_path, q.question_bbox)
                        if a_saved:
                            assets["answer_image"] = _asset_info(a_path, answer_bbox)
                        record["assets"] = assets
                    elif code in (WRONG, UNANSWERED):
                        record["assets"] = {
                            "status": "missing_source_image",
                            "message": "source image is unavailable",
                        }
                    questions_records.append(record)
                    if code in (WRONG, UNANSWERED):
                        wrong_questions.append(copy.deepcopy(record))
                continue
            grading = q.raw.get("grading_result") if isinstance(q.raw.get("grading_result"), dict) else {}
            code = _to_int(grading.get("correctResult"), WRONG)
            if code == CORRECT:
                correct_count += 1
            elif code == UNANSWERED:
                blank_count += 1
            else:
                wrong_count += 1
            record = {
                "question_key": f"p{page_no}_q{q.display_index}_s1",
                "display_title": f"第{q.display_index}题",
                "page_no": page_no,
                "question_index": q.display_index,
                "baidu_question_id": q.question_id,
                "display_index": q.display_index,
                "slot_index": 1,
                "status_code": code,
                "status": _status_from_code(code),
                "question_type": q.question_type,
                "question": q.question_words,
                "student_answer": q.answer_words,
                "choices": q.choices,
                "reason": str(grading.get("reason") or "").strip(),
                "analysis": str(grading.get("analysis") or "").strip(),
                "render": {
                    "bbox": q.bbox,
                    "question_bbox": q.question_bbox,
                    "comment": str(grading.get("analysis") or grading.get("reason") or "").strip(),
                },
                "source_filename": source_filename,
                "provider": "baidu_paper_cut_edu_vlm_qwen",
            }
            if img0 is not None and code in (WRONG, UNANSWERED):
                q_path = paper_dir / f"{record['question_key']}_question.jpg"
                a_path = paper_dir / f"{record['question_key']}_answer.jpg"
                q_saved = _save_crop(img0, q.question_bbox, q_path, pad=12)
                a_saved = _save_crop(img0, q.answer_bbox or q.bbox, a_path, pad=18)
                assets = {"status": "ok"}
                if q_saved:
                    assets["question_image"] = _asset_info(q_path, q.question_bbox)
                if a_saved:
                    assets["answer_image"] = _asset_info(a_path, q.answer_bbox or q.bbox)
                record["assets"] = assets
            elif code in (WRONG, UNANSWERED):
                record["assets"] = {"status": "missing_source_image", "message": "未找到本地试卷图片，无法裁剪错题图。"}
            questions_records.append(record)
            if code in (WRONG, UNANSWERED):
                wrong_questions.append(copy.deepcopy(record))
    finally:
        try:
            if img0 is not None:
                img0.close()
        except Exception:
            pass

    summary = {
        "question_count": len(questions_records),
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "blank_count": blank_count,
        "wrong_question_count": len(wrong_questions),
    }
    source = {
        "engine": "aliyun",
        "provider": "baidu_paper_cut_edu_vlm_qwen",
        "task_id": str((enriched_raw.get("result") or {}).get("task_id") or enriched_raw.get("task_id") or "").strip(),
        "log_id": str(enriched_raw.get("log_id") or "").strip(),
        "raw_json": _relative_to_grading_root(raw_json_path),
    }

    class_id_from_ctx, _ = _split_class_exam(folder_safe)
    try:
        _class_meta, students = _load_class_context(class_id_from_ctx)
    except Exception:
        students = []
    student = _safe_infer_student(paper_box, students)
    student_record = student if isinstance(student, dict) else {"name": paper_box, "matched_by": "filename"}
    page_record = {
        "page_no": page_no,
        "source_filename": source_filename,
        "updated_at": _now_iso(),
        "source": source,
        "summary": summary,
        "questions": questions_records,
        "wrong_questions": wrong_questions,
    }
    analysis_page_record = {
        "page_no": page_no,
        "source_filename": source_filename,
        "updated_at": page_record["updated_at"],
        "source": source,
        "summary": summary,
        "wrong_question_analysis": wrong_questions,
    }

    with _artifact_lock:
        record_data = _read_json(records_path)
        if not record_data:
            record_data = _empty_exam_db(class_id, exam_name, folder_safe, "reference_vlm_wrong_question_records")
        record_papers = record_data.setdefault("papers", {})
        record_pages = _reference_pages_from_existing(
            record_papers.get(paper_box), analysis=False
        )
        record_pages[str(page_no)] = page_record
        record_papers[paper_box] = _aggregate_reference_pages(
            paper_box, student_record, record_pages, analysis=False
        )
        _update_exam_summary(record_data)
        _write_json(records_path, record_data)

        analysis_data = _read_json(analysis_path)
        if not analysis_data:
            analysis_data = _empty_exam_db(class_id, exam_name, folder_safe, "reference_vlm_wrong_question_analysis")
        analysis_papers = analysis_data.setdefault("papers", {})
        analysis_pages = _reference_pages_from_existing(
            analysis_papers.get(paper_box), analysis=True
        )
        analysis_pages[str(page_no)] = analysis_page_record
        analysis_papers[paper_box] = _aggregate_reference_pages(
            paper_box, student_record, analysis_pages, analysis=True
        )
        _update_exam_summary(analysis_data)
        _write_json(analysis_path, analysis_data)


def draw_reference_vlm_marks_and_save(
    image_path: str,
    blocks_with_result: list,
    result_dir: str,
    file_stem: str,
    *,
    check_cross_scale: float = 0.9,
    question_notes: Optional[dict] = None,
    paper_note: Optional[str] = None,
) -> tuple[str, str, str]:
    """Draw checks/crosses and circle inferred answer areas for unanswered slots."""
    mark_blocks: list[dict] = []
    blank_areas: list[list[int]] = []

    def valid_bbox(value: Any) -> Optional[list[int]]:
        if not isinstance(value, (list, tuple)) or len(value) < 4:
            return None
        bbox = [int(_to_float(item)) for item in value[:4]]
        return bbox if bbox[2] > bbox[0] and bbox[3] > bbox[1] else None

    for block in blocks_with_result:
        if not isinstance(block, dict):
            continue
        code = _to_int(block.get("baidu_correct_result"), WRONG)
        if code == UNANSWERED:
            answer_bbox = valid_bbox(block.get("reference_vlm_answer_bbox"))
            question_bbox = valid_bbox(block.get("baidu_question_bbox"))
            if block.get("baidu_is_slot") and answer_bbox:
                blank_areas.append(answer_bbox)
            elif question_bbox:
                blank_areas.append(_mark_bbox_from_area(question_bbox))
            continue

        if block.get("has_mark_anchor", block.get("has_handwriting_location")):
            mark_blocks.append(block)
            continue

        question_bbox = valid_bbox(block.get("baidu_question_bbox"))
        if not question_bbox:
            continue

        fallback_block = dict(block)
        fallback_block["bbox"] = _mark_bbox_from_area(question_bbox, question_bbox)
        fallback_block["reference_vlm_anchor_source"] = "question_bbox_fallback"
        mark_blocks.append(fallback_block)

    orig_name, ann_name = draw_real_marks_and_save(
        image_path,
        mark_blocks,
        result_dir,
        file_stem,
        check_cross_scale=check_cross_scale,
    )
    marks_only = draw_marks_only_and_save(
        image_path,
        mark_blocks,
        result_dir,
        file_stem,
        check_cross_scale=check_cross_scale,
    )

    for output_name in (ann_name, marks_only):
        output_path = Path(result_dir) / output_name
        if not output_path.is_file():
            continue
        with Image.open(output_path) as source:
            image = source.convert("RGB")
        draw = ImageDraw.Draw(image)
        if blank_areas:
            for area in blank_areas:
                draw_blank_area_cross(draw, area[0], area[1], area[2], area[3])
        # 老师手动批注（每道题一句 + 整卷总评）写到卷面留痕上
        img_w, img_h = image.size
        draw_manual_annotations(draw, img_w, img_h, blocks_with_result, question_notes, paper_note)
        image.save(output_path, quality=95)
    return orig_name, ann_name, marks_only


def grade_reference_vlm_paper(
    standard_name: str,
    standard_doc: dict,
    student_name: str,
    student_doc: dict,
    *,
    folder_safe: str,
    slot_template: Optional[list[VlmSlotTemplate]] = None,
    stop_event: Optional[threading.Event] = None,
) -> tuple[str, list, dict, str]:
    """Grade one paper and return (result_text, blocks, enriched_vlm_json, mark_image_path)."""
    if stop_event and stop_event.is_set():
        raise RuntimeError("已停止批改")
    if Image is None:
        raise RuntimeError("需要安装 Pillow")

    standard_raw = standard_doc.get("raw") or {}
    student_raw = student_doc.get("raw") or {}
    student_image_path = str(student_doc.get("image_path") or student_doc.get("source_path") or "")
    standard_image_path = str(standard_doc.get("image_path") or standard_doc.get("source_path") or "")
    if not Path(student_image_path).is_file():
        raise RuntimeError("学生试卷图片不存在，无法批改")
    if not Path(standard_image_path).is_file():
        raise RuntimeError("标准答案图片不存在，无法批改")

    enriched_raw = copy.deepcopy(student_raw)
    _clear_existing_grading_fields(enriched_raw)
    standard_questions = standard_doc.get("questions")
    if not isinstance(standard_questions, list) or not standard_questions:
        standard_questions = extract_vlm_questions(standard_raw, image_path=standard_image_path)
    # Parse from the copy that will be saved so inserted grading fields are
    # guaranteed to belong to enriched_raw instead of the recognition cache.
    student_questions = extract_vlm_questions(enriched_raw, image_path=student_image_path)
    if not student_questions:
        raise RuntimeError("Student paper OCR JSON contains no gradable questions")
    client, model = _get_qwen_client_and_model()

    with Image.open(standard_image_path) as std_img0, Image.open(student_image_path) as stu_img0:
        std_img = std_img0.convert("RGB")
        stu_img = stu_img0.convert("RGB")
        tasks = _build_grading_tasks(
            standard_questions,
            student_questions,
            std_img.size,
            stu_img.size,
            slot_template=slot_template,
        )
        batches = _group_grading_tasks(tasks)
        qwen_tasks: list[tuple[VlmQuestionBatchTask, str, str]] = []
        for batch in batches:
            std_regions = _batch_context_regions(
                batch,
                standard=True,
                source_size=std_img.size,
                target_size=std_img.size,
            )
            stu_regions = _batch_context_regions(
                batch,
                standard=False,
                source_size=std_img.size,
                target_size=stu_img.size,
            )
            std_highlights = [
                (_clamp_bbox(task.standard_answer_bbox, std_img.size), _slot_key(task))
                for task in batch.slots
            ]
            stu_highlights = [
                (_clamp_bbox(task.student_answer_bbox, stu_img.size), _slot_key(task))
                for task in batch.slots
            ]
            std_url, _std_bytes = _crop_regions_to_data_url(
                std_img,
                std_regions,
                highlight_bboxes=std_highlights,
            )
            stu_url, _stu_bytes = _crop_regions_to_data_url(
                stu_img,
                stu_regions,
                highlight_bboxes=stu_highlights,
            )
            qwen_tasks.append((batch, std_url, stu_url))

    workers = max(
        1,
        min(len(qwen_tasks), int(os.environ.get("REFERENCE_VLM_QWEN_WORKERS", "6") or "6")),
    )

    decisions: dict[int, dict[int, dict]] = {}
    def _grade_one(qwen_task: tuple[VlmQuestionBatchTask, str, str]) -> dict[int, dict]:
        batch, std_url, stu_url = qwen_task
        if stop_event and stop_event.is_set():
            raise RuntimeError("已停止批改")
        return _call_qwen_for_question_batch(
            client,
            model,
            batch,
            std_url,
            stu_url,
            student_name,
        )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(_grade_one, batch_task): batch_task[0].batch_id
            for batch_task in qwen_tasks
        }
        for future in as_completed(future_map):
            batch_id = future_map[future]
            try:
                decisions[batch_id] = future.result()
            except Exception as exc:
                batch = next(
                    (item for item in batches if item.batch_id == batch_id),
                    None,
                )
                display_index = batch.student_question.display_index if batch else batch_id
                raise RuntimeError(
                    f"第{display_index}题千问图片批改失败: {type(exc).__name__}: {exc}"
                ) from exc

    for batch in batches:
        batch_decisions = decisions.get(batch.batch_id) or {}
        for task in batch.slots:
            q = task.student_question
            decision = batch_decisions.get(task.task_id)
            if not decision:
                raise RuntimeError(
                    f"第{q.display_index}题作答区{task.sub_index}缺少千问判题结果，"
                    "已停止写入，避免 JSON 错插"
                )
            _insert_sub_grading_result(
                q,
                decision,
                task_id=task.task_id,
                sub_index=task.sub_index,
                answer_bbox=task.student_answer_bbox,
                has_mark_anchor=task.has_mark_anchor,
                has_handwriting_location=task.has_handwriting_location,
                is_answer_slot=task.is_answer_slot,
                anchor_source=task.anchor_source,
                template_slot_id=task.template_slot_id,
            )

    blocks = _build_blocks(student_questions)
    result_text = _summarize_result_text(student_questions)
    _save_reference_vlm_artifacts(
        folder_safe=folder_safe,
        paper_name=student_name,
        source_filename=student_name,
        source_image_path=student_image_path,
        enriched_raw=enriched_raw,
        questions=student_questions,
    )
    return result_text, blocks, enriched_raw, student_image_path
