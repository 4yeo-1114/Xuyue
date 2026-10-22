# -*- coding: utf-8 -*-
"""Reference-answer grading based on Baidu paper_cut_edu_vlm + Qwen vision.

This module intentionally owns its own split-only JSON parsing and artifact
writing for reference-answer grading.
"""
from __future__ import annotations

import base64
import copy
import hashlib
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
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
except ImportError:  # pragma: no cover - reported at runtime
    Image = None
    ImageDraw = None
    ImageEnhance = None
    ImageFilter = None
    ImageFont = None
    ImageOps = None

from app.grading.form_guard import EMPTY_INK_RATIO, ink_ratio
from app.grading.baidu_grading import (
    _build_url,
    _check_baidu_api_error,
    _create_rate_limiter,
    _post_json,
)
from app.grading.doc_convert import enhance_for_ocr, ensure_image_path
from app.grading.pipeline import draw_marks_only_and_save, draw_real_marks_and_save, draw_manual_annotations
from app.grading.user_paths import correct_docs_dir, ct_root, grading_paths
from app.utils.qwen_settings import DEFAULT_QWEN_MODEL, QWEN_CHAT_EXTRA_BODY, get_qwen_config
from app.grading.wrong_question_db import _infer_student_from_paper_name, _load_class_context


PAPER_CUT_VLM_CREATE_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/paper_cut_edu_vlm/create_task"

CORRECT = 1
WRONG = 2
UNANSWERED = 3
PARTIAL = 4
PENDING = 5

RESULT_TEXT = {
    CORRECT: "对",
    WRONG: "错",
    UNANSWERED: "未作答",
    PARTIAL: "半对",
    PENDING: "待确认",
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
    # 题号（印刷题号，如 "9"）：题号优先配对的依据；解析不出为 None 时几何兜底。
    printed_no: Optional[str] = None


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
    # 标准答案完整识别文本（答案表优先，见 _standard_answer_text）：
    # 判分提示词的唯一判分依据 + 缓存键/response_logs 身份。None 时回退 answer_words。
    standard_answer_text: Optional[str] = None


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


_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_NUM_TOKEN_RE = re.compile(r"[零〇一二两三四五六七八九十百]{1,6}")
_PRINTED_NO_RE = re.compile(rf"第\s*(\d{{1,3}}|{_CN_NUM_TOKEN_RE.pattern})\s*[题小题]")
# 需要显式分隔符（"10、" "（3）" "2." "5题" "一、"），避免把 "2024年…" 的年份当题号。
_LEADING_NO_RE = re.compile(
    rf"^\s*[（(【\[]?\s*(\d{{1,3}}|{_CN_NUM_TOKEN_RE.pattern})\s*(?:[）)】\]、．.．:：]|题)"
)


def _cn_numeral_to_int(token: str) -> Optional[int]:
    """中文数字题号转 int："十一"→11，"二十三"→23，"一百"→100；认不出返回 None。"""
    text = str(token or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text in _CN_DIGITS:
        return _CN_DIGITS[text]
    total, current = 0, 0
    for ch in text:
        if ch in _CN_DIGITS:
            current = _CN_DIGITS[ch]
        elif ch == "十":
            total += (current or 1) * 10
            current = 0
        elif ch == "百":
            total += (current or 1) * 100
            current = 0
        else:
            return None
    return total + current


def _parse_printed_no(question_words: str) -> Optional[str]:
    """从题干文本解析印刷题号（"第9题…"→"9"，"10、…"→"10"，"（1）…"→"1"，"一、"→"1"）。

    解析出的题号只做跨卷配对锚（标准卷↔学生卷同号优先），不做绝对题号：
    切题切分不一致时两侧解析规则一致，配对仍然成立。解析不出返回 None，
    几何兜底继续可用。语文卷常用「一、二、三」编号，一并认。
    """
    text = str(question_words or "").strip()
    if not text:
        return None
    head = text[:32]
    match = _PRINTED_NO_RE.search(head)
    if match:
        value = _cn_numeral_to_int(match.group(1))
        return str(value) if value is not None else None
    match = _LEADING_NO_RE.match(text)
    if match:
        value = _cn_numeral_to_int(match.group(1))
        return str(value) if value is not None else None
    return None


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


def _layout_edit_binds_raw(edit: dict[str, Any]) -> bool:
    """这条切题编辑是「原题的修改」还是「老师新增题」。

    原题：question_id 形如 q-{display_no}（build_reference_layout_page 产出）；
    新增题：前端 nextId 生成的 question-<uuid>，只走合成、绝不按 display_no
    认领 raw 题——老师删掉尾题后新增会复用空出来的号（max+1），那是新题不是
    老题的修改。无 question_id 的旧数据按原题处理（保持老口径）。
    """
    qid = str(edit.get("question_id") or "")
    if not qid:
        return True
    return bool(re.fullmatch(r"q-\d+", qid))


def _synthesize_question_from_layout(
    edit: dict[str, Any],
    display_no: int,
    image_size: tuple[int, int],
) -> Optional[VlmQuestion]:
    """切题审查新增题合成标准题：raw 里没有对应题目时不再丢弃。

    老师在切题审查里补的题（如打印题第8-14题）此前只活在 layout 里，
    批改/答案表都只看 raw 提取结果，等于新增题整段消失、学生对应题被
    配到无关标准上。这里按 layout 框合成 VlmQuestion，与 raw 题同权。
    """
    region_boxes = []
    for region in edit.get("regions") or []:
        value = region.get("bbox") if isinstance(region, dict) else region
        normalized = _layout_bbox(value, image_size)
        if normalized:
            region_boxes.append(normalized)
    if not region_boxes:
        return None
    slot_boxes = []
    for slot in edit.get("answer_slots") or []:
        boxes = _layout_slot_boxes(slot, image_size)
        slot_box = _bbox_union(boxes, image_size)
        if slot_box:
            slot_boxes.append(slot_box)
    question_bbox = _bbox_union(region_boxes, image_size) or region_boxes[0]
    answer_bbox = _answer_bbox_union(slot_boxes, image_size)
    question_words = _safe_text(edit.get("question_text"))
    raw = {
        "synthetic_from_layout": True,
        "qus_id": display_no,
        # 切题身份戳：重建提取时按戳认 display_no，别再按容器位置重排
        "layout_display_index": display_no,
        "question_words": question_words,
        "qus_type": str(edit.get("question_type") or ""),
        "location": {
            "qus_location": question_bbox,
            "ans_location": copy.deepcopy(slot_boxes),
        },
        "corrected_question_regions": copy.deepcopy(region_boxes),
        "corrected_answer_slots": copy.deepcopy(
            [
                {"slot_index": index, "bbox": box}
                for index, box in enumerate(slot_boxes, start=1)
            ]
        ),
    }
    return VlmQuestion(
        question_id=display_no,
        display_index=display_no,
        raw=raw,
        bbox=_mark_bbox_from_area(question_bbox, answer_bbox),
        question_bbox=question_bbox,
        answer_bbox=answer_bbox,
        answer_bboxes=slot_boxes,
        question_words=question_words,
        answer_words=[],
        choices=[],
        question_type=str(edit.get("question_type") or ""),
        question_regions=region_boxes,
        printed_no=_parse_printed_no(question_words),
    )


def apply_reference_layout_to_document(
    document: dict[str, Any],
    layout_page: dict[str, Any],
) -> dict[str, Any]:
    """Apply teacher-edited regions to a cached OCR document.

    The raw Baidu response remains available; corrected fields are written to
    the copied question objects so the existing grading/result writer can use
    the same downstream contract. Layout questions without a raw counterpart
    (teacher-added in 切题审查) are synthesized so they reach grading too.
    """
    corrected = copy.deepcopy(document or {})
    image_size_raw = corrected.get("image_size") or layout_page.get("image_size") or [0, 0]
    image_size = (_to_int(image_size_raw[0]), _to_int(image_size_raw[1]))
    questions = extract_vlm_questions(corrected.get("raw") or {}, image_path=str(corrected.get("image_path") or corrected.get("source_path") or ""))
    layout_questions = layout_page.get("questions") if isinstance(layout_page, dict) else []
    by_index: dict[int, dict[str, Any]] = {}
    for item in layout_questions or []:
        if not isinstance(item, dict):
            continue
        display_no = _to_int(item.get("display_no"), 0)
        if display_no > 0 and display_no not in by_index:
            by_index[display_no] = item
    kept_questions: list[VlmQuestion] = []
    for question in questions:
        # 稳定身份戳：重建提取时按戳认 display_no，中段删除也不挪号
        question.raw["layout_display_index"] = question.display_index
        edit = by_index.get(question.display_index)
        if edit is not None and not _layout_edit_binds_raw(edit):
            edit = None
        if not edit:
            # 切题审查里没有的题 = 老师删掉了：打标让重建跳过，
            # 不能像以前那样 if not edit: continue 原样放回答案表/批改。
            question.raw["layout_deleted"] = True
            continue
        question.raw.pop("layout_deleted", None)
        had_slots = bool(question.answer_bboxes) or bool(question.raw.get("layout_slots_cleared"))
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
        # 老师把本题作答区删光：记一笔，别让题框兜底把大框当答题区画回来。
        # 本来就识别不出作答区的题（had_slots=False）保留题框兜底（批改整题红框）。
        if slot_boxes:
            question.raw.pop("layout_slots_cleared", None)
        elif had_slots:
            question.raw["layout_slots_cleared"] = True
        kept_questions.append(question)
    questions = kept_questions
    # 切题审查新增、raw 里没有的题：合成标准题并回写 raw，别再丢弃。
    existing_indexes = {question.display_index for question in questions}
    raw_dict = corrected.get("raw") if isinstance(corrected.get("raw"), dict) else None
    raw_container = _raw_questions_list(raw_dict) if raw_dict else None
    for edit in layout_questions or []:
        if not isinstance(edit, dict):
            continue
        display_no = _to_int(edit.get("display_no"), 0)
        if display_no <= 0 or display_no in existing_indexes:
            continue
        synthesized = _synthesize_question_from_layout(edit, display_no, image_size)
        if synthesized is None:
            continue
        questions.append(synthesized)
        existing_indexes.add(display_no)
        if isinstance(raw_container, list):
            raw_container.append(synthesized.raw)
    questions.sort(key=lambda q: q.display_index)
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


# ── 标准答案完整识别表（先逐题完整识别标准答案，再进卷批改）──────────
# 用户要求：① 按参考答案把每道题的答案完完整整识别出来，让 AI 明确知道每道题
# 的正确答案；② 再去看试卷，题号对照后找作答区、识别手写答案、与标准答案比对。
# 本块就是 ①：逐槽无上下文单区转写（组合图会跨题串扰），按卷缓存于文件夹；
# 提取失败的槽回退切题 answer_words，判分提示词里再回退 image 1 红框。

_ANSWER_TABLE_FILENAME = ".reference_answer_table.json"
_ANSWER_TABLE_LOCK = threading.Lock()

_ANSWER_EXTRACT_PROMPT = (
    "你是标准答案识别专用助手。图片是标准答案卷上某道题一个作答区的截图。"
    "请把图中文字逐字完整转写：禁止概括、禁止省略、禁止改写或补全、禁止用“等”字收尾。"
    "保留原有换行与序号。看不清的单字用 [?] 占位；两种读法都像的写 [字1|字2]；"
    "整段认不出写 [??]。若图中没有答案内容（只有横线、括号或空白），answer_text 输出空字符串。"
    "只输出 JSON：{\"answer_text\":\"...\"}"
)


def _answer_table_path(folder_safe: str) -> Path:
    return correct_docs_dir() / folder_safe / _ANSWER_TABLE_FILENAME


def _looks_like_template_noise(text: str) -> bool:
    """空白括号/下划线/标点等印刷模板残渣不算答案："（）" "是（ ）" "，" "《____》，"。"""
    value = str(text or "").strip()
    if not value:
        return True
    # 判断题空壳："是（ ）" "不( )" "（）"——括号内外只剩模板字。
    # 注意括号/下划线必须至少一个（+）：裸「是」「不」是判断题真答案，不能当噪声。
    if re.fullmatch(r"[是不]?[\s（）()_]+", value):
        return True
    stripped = re.sub(
        r"[\s（）()【】\[\]《》<>_—\-~…·、，,。.；;：:！!？?\"'“”‘’|｜]",
        "",
        value,
    )
    return stripped == ""


def _extract_slot_answer_text(client, model, image, bbox: list[int]) -> str:
    """单作答区无上下文完整转写（VL 串扰教训：绝不把多题裁进一张图）。

    空白卷安全：作答区几乎无墨迹直接回空串、不送 VL——纯白区问模型必出幻觉；
    有印刷答案（有墨）照常转写。墨迹检测失败按有墨处理（宁多识别不误跳）。
    印刷模板残渣（空括号/下划线/纯标点）按空答案处理——空白卷的括号也算墨迹，
    不滤掉 VL 会把「是（ ）」当答案抄回来。
    """
    try:
        if ink_ratio(image, bbox) < EMPTY_INK_RATIO:
            return ""
    except Exception:
        pass
    data_url, _payload = _crop_to_data_url(image, bbox, pad=8, min_long_side=400)
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": _ANSWER_EXTRACT_PROMPT},
                ],
            }
        ],
        stream=False,
        timeout=90,
        extra_body=QWEN_CHAT_EXTRA_BODY,
    )
    content = completion.choices[0].message.content or ""
    data = _json_object_from_text(content)
    if not isinstance(data, dict):
        return ""
    text = _normalize_math_text(_safe_text(data.get("answer_text"), limit=2000))
    return "" if _looks_like_template_noise(text) else text


def crop_reference_answer_table_region(
    image_path: str,
    bbox: list,
    *,
    pad: int = 8,
    max_side: int = 720,
) -> bytes:
    """答案表答题区缩略图：按 bbox 裁标准答案页原图，返回 JPEG 字节。

    前端 6889 跨域画布裁剪会污染画布，缩略图只能服务端裁好再给 <img>。
    bbox 是标准答案识别图（cache 页 image_path）坐标空间，勿换图源。
    """
    if Image is None:
        raise RuntimeError("需要安装 Pillow")
    with Image.open(image_path) as img:
        image = img.convert("RGB")
        w, h = image.size
        x1, y1, x2, y2 = (int(v) for v in bbox[:4])
        x1 = max(0, min(w - 1, x1 - pad))
        y1 = max(0, min(h - 1, y1 - pad))
        x2 = max(1, min(w, x2 + pad))
        y2 = max(1, min(h, y2 + pad))
        if x2 <= x1 or y2 <= y1:
            raise RuntimeError("答题区坐标无效")
        crop = image.crop((x1, y1, x2, y2))
        long_side = max(crop.size)
        if long_side > max_side:
            ratio = max_side / long_side
            resampling = getattr(Image, "Resampling", None)
            lanczos = resampling.LANCZOS if resampling else getattr(Image, "LANCZOS", 1)
            crop = crop.resize(
                (max(1, int(crop.width * ratio)), max(1, int(crop.height * ratio))),
                lanczos,
            )
        buf = BytesIO()
        crop.save(buf, format="JPEG", quality=88)
        return buf.getvalue()


# 拆条：切题常把一排小题答案并成一块（"1. D 2. B … 7. D"），按行内印刷题号
# 一题一行拆进答案表。题号前必须是行首/空白——"(1)(2)" 小问序号带括号永不触发。
_ANSWER_CHUNK_NO_RE = re.compile(r"(?:^|[\s\n])(\d{1,3})\s*[.、．:：]\s*")
# 答案表识别算法版本进 cache_token：拆条/补漏算法升级后旧缓存自动重建
#（手改覆盖层只看 source_signature，不受版本号影响）。
_ANSWER_TABLE_EXTRACT_VERSION = 5

_ANSWER_SCAN_PROMPT = (
    "你是标准答案识别专用助手。图片是标准答案卷（或其局部）的截图。"
    "把图中每道题的题号与答案完整转写成文本：每题一行，行首格式严格「题号. 答案」"
    "（题号用阿拉伯数字，例如「13. 空间」）。答案逐字完整转写，禁止概括、禁止省略、"
    "禁止用“等”字收尾。看不清的单字用 [?] 占位；两种读法都像的写 [字1|字2]。"
    "只输出 JSON：{\"answer_text\":\"...\"}"
)


def _parse_numbered_answer_chunks(text: str) -> dict[int, str]:
    """把 "1. D 2. B …" 转写拆成 {题号: 答案}；空块跳过，同号先到先得。"""
    source = str(text or "")
    found: dict[int, str] = {}
    matches = list(_ANSWER_CHUNK_NO_RE.finditer(source))
    for idx, match in enumerate(matches):
        value = _cn_numeral_to_int(match.group(1))
        if value is None or value <= 0:
            continue
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(source)
        chunk = source[match.end() : end].strip()
        if not chunk:
            continue
        found.setdefault(value, chunk)
    return found


def _split_entry_by_printed_numbers(entry: dict) -> list[dict]:
    """合并块按行内印刷题号拆条（"1. D 2. B … 7. D" → 7 条，每题一行）。

    仅当 ≥2 个题号、严格递增、且首号 == 条目印刷题号（条目没题号也认）才拆；
    编号回退/引用序号（乱序）一律不拆——宁可合并展示也不拆错。
    """
    slots = [slot for slot in (entry.get("slots") or []) if isinstance(slot, dict)]
    if not slots:
        return [entry]
    text = "\n".join(str(slot.get("answer_text") or "") for slot in slots)
    matches = list(_ANSWER_CHUNK_NO_RE.finditer(text))
    if len(matches) < 2:
        return [entry]
    numbers: list[int] = []
    for match in matches:
        value = _cn_numeral_to_int(match.group(1))
        if value is None or value <= 0:
            return [entry]
        numbers.append(value)
    for previous, current in zip(numbers, numbers[1:]):
        if current <= previous:
            return [entry]
    parent_no = str(entry.get("printed_no") or "").strip()
    if parent_no.isdigit() and int(parent_no) != numbers[0]:
        return [entry]
    question_bbox = entry.get("question_bbox") or [0, 0, 0, 0]
    base_bbox = slots[0].get("bbox") or question_bbox
    parent_display = _to_int(entry.get("display_index"), 0)
    children: list[dict] = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        if not chunk:
            continue
        number = numbers[idx]
        children.append(
            {
                # 1000+题号：同一拆条块重建后序号稳定（手改覆盖层按 display_index 存）
                "display_index": 1000 + number,
                "printed_no": str(number),
                # 拆自哪个切题块：合并块槽任务还原全文靠它认亲
                "source_display_index": parent_display,
                "question_bbox": question_bbox,
                "slots": [
                    {
                        "sub_index": 1,
                        "bbox": [_to_int(value) for value in base_bbox[:4]],
                        "answer_text": chunk,
                    }
                ],
                "full_answer": chunk,
            }
        )
    return children if len(children) >= 2 else [entry]


def _split_answer_entries_by_printed_numbers(entries: list[dict]) -> list[dict]:
    """整页拆条；题号/序号撞车的整条不拆（宁可合并展示也不丢答案、不造重复键）。"""
    split: list[dict] = []
    used_numbers: set[int] = set()
    used_display: set[int] = {
        _to_int(entry.get("display_index"), 0) for entry in entries if isinstance(entry, dict)
    }
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        children = _split_entry_by_printed_numbers(entry)
        if len(children) == 1 and children[0] is entry:
            split.append(entry)
            number = _to_int(entry.get("printed_no"), 0)
            if number > 0:
                used_numbers.add(number)  # 不拆的条目也占号，防后续拆条撞出重复题号
            continue
        child_numbers = [_to_int(child.get("printed_no"), 0) for child in children]
        child_display = [_to_int(child.get("display_index"), 0) for child in children]
        if any(number in used_numbers for number in child_numbers) or any(
            display in used_display for display in child_display
        ):
            split.append(entry)
            continue
        used_numbers.update(child_numbers)
        used_display.update(child_display)
        split.extend(children)
    return split


def _extract_scan_answer_chunks(client, model, image, bbox: list[int]) -> dict[int, str]:
    """局部/整页按「N. 答案」行转写（补漏号专用），返回 {题号: 答案}。"""
    data_url, _payload = _crop_to_data_url(image, bbox, pad=12, max_side=2400, min_long_side=1200)
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": _ANSWER_SCAN_PROMPT},
                ],
            }
        ],
        stream=False,
        timeout=120,
        extra_body=QWEN_CHAT_EXTRA_BODY,
    )
    content = completion.choices[0].message.content or ""
    data = _json_object_from_text(content)
    text = ""
    if isinstance(data, dict):
        text = _normalize_math_text(_safe_text(data.get("answer_text"), limit=8000))
    return _parse_numbered_answer_chunks(text)


def _fill_missing_answer_numbers(
    entries: list[dict],
    image,
    client,
    model,
    *,
    skip_printed_numbers: Optional[set[int]] = None,
    stop_event: Optional[threading.Event] = None,
) -> list[dict]:
    """补切题漏掉的题号（版面缝里的题，如 12 与 14 之间漏切的第 13 题）。

    只补 [最小题号, 最大题号] 区间里的缺号：按连续缺号分段，每段裁
    「上一题答完到下一题开始」的条带整段转写（分辨率高、少幻觉）；
    扫不到就不补（老师可在识别列表手填），已识别条目一概不动。
    skip_printed_numbers 是切题审查里老师删掉的题号：不算漏切、不许补回。
    """
    present: set[int] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        number = _to_int(entry.get("printed_no"), 0)
        if number > 0:
            present.add(number)
    if len(present) < 2:
        return entries
    skipped = {number for number in (skip_printed_numbers or set()) if number > 0}
    missing = [
        number
        for number in range(min(present), max(present) + 1)
        if number not in present and number not in skipped
    ]
    if not missing:
        return entries
    width, height = image.size
    by_no = {
        _to_int(entry.get("printed_no"), 0): entry
        for entry in entries
        if isinstance(entry, dict) and _to_int(entry.get("printed_no"), 0) > 0
    }

    def _band_for(run: list[int]) -> list[int]:
        lower = [number for number in by_no if number < run[0]]
        upper = [number for number in by_no if number > run[-1]]
        prev_entry = by_no.get(max(lower)) if lower else None
        next_entry = by_no.get(min(upper)) if upper else None

        def _bbox(entry: Optional[dict], default: list[int]) -> list[int]:
            values = (entry or {}).get("question_bbox") if entry else None
            box = [_to_int(value) for value in (values or default)[:4]]
            return box if len(box) == 4 else list(default)

        prev_bbox = _bbox(prev_entry, [0, 0, width, 0])
        next_bbox = _bbox(next_entry, [0, 0, width, height])
        top, bottom = prev_bbox[3], next_bbox[1]
        if bottom <= top:
            # 同一切题块内的缺号（拆条时空块）：整块重扫
            top, bottom = min(prev_bbox[1], next_bbox[1]), max(prev_bbox[3], next_bbox[3])
        return [0, max(0, top - 24), width, min(height, bottom + 24)]

    runs: list[list[int]] = []
    for number in missing:
        if runs and number == runs[-1][-1] + 1:
            runs[-1].append(number)
        else:
            runs.append([number])
    filled: dict[int, str] = {}
    for run in runs:
        if stop_event and stop_event.is_set():
            raise RuntimeError("已停止批改")
        band = _band_for(run)
        if band[3] <= band[1] or band[2] <= band[0]:
            continue
        try:
            found = _extract_scan_answer_chunks(client, model, image, band)
        except Exception:
            continue  # 扫段失败不挡答案表
        for number in run:
            text = str(found.get(number) or "").strip()
            if text:
                filled[number] = text
    if not filled:
        return entries
    result = list(entries)
    used_display = {_to_int(entry.get("display_index"), 0) for entry in result if isinstance(entry, dict)}
    for number in sorted(filled):
        display_index = 1000 + number
        if display_index in used_display:
            continue
        used_display.add(display_index)
        text = filled[number]
        result.append(
            {
                "display_index": display_index,
                "printed_no": str(number),
                "question_bbox": [0, 0, 0, 0],
                "slots": [{"sub_index": 1, "bbox": [0, 0, 0, 0], "answer_text": text}],
                "full_answer": text,
            }
        )
    return result


def _question_slot_bboxes(question: VlmQuestion) -> list[list[int]]:
    boxes = list(question.answer_bboxes or [])
    if not boxes and question.answer_bbox:
        boxes = [question.answer_bbox]
    if not boxes:
        # 老师把本题作答区删光（切题审查确认过 0 框）：不得拿题框当答题区回魂。
        # 从没识别出作答区的题才走题框兜底（无槽标准题整题红框，test 3024）。
        if question.raw.get("layout_slots_cleared"):
            return []
        boxes = [question.question_bbox]
    return boxes


def _layout_deleted_printed_nos(raw: dict) -> set[int]:
    """切题审查删掉的题的印刷题号：补漏号扫描不得把它们当「漏切的题」补回来。"""
    numbers: set[int] = set()
    for item in _questions_container(raw):
        if not isinstance(item, dict) or not item.get("layout_deleted"):
            continue
        elements = item.get("qus_elements") if isinstance(item.get("qus_elements"), dict) else {}
        if not elements and isinstance(item.get("qus_element"), dict):
            elements = item.get("qus_element") or {}
        words = _safe_text(
            elements.get("question_words")
            or elements.get("qus_words")
            or item.get("question_words")
            or item.get("qus_words")
        )
        value = _to_int(_parse_printed_no(words), 0)
        if value > 0:
            numbers.add(value)
    return numbers


def _strip_wrapping_parens(text: str) -> str:
    """去掉整体包住答案的印刷括号（「(轰然)」→「轰然」）；带内层括号的不动。"""
    value = str(text or "").strip()
    if len(value) >= 2 and value[0] in "（(" and value[-1] in "）)":
        inner = value[1:-1].strip()
        if inner and not any(ch in inner for ch in "（）()"):
            return inner
    return value


def extract_reference_answer_table(
    questions: list[VlmQuestion],
    image_path: str,
    *,
    skip_printed_numbers: Optional[set[int]] = None,
    stop_event: Optional[threading.Event] = None,
) -> list[dict]:
    """逐题逐作答区完整转写标准答案，返回答案表条目（每题 slots + full_answer）。"""
    if Image is None:
        raise RuntimeError("需要安装 Pillow")
    if not questions:
        return []
    client, model = _get_qwen_client_and_model()
    jobs: list[tuple[int, int, list[int]]] = []
    for question in questions:
        for sub_index, bbox in enumerate(_question_slot_bboxes(question), start=1):
            jobs.append((question.display_index, sub_index, bbox))
    results: dict[tuple[int, int], str] = {}
    with Image.open(image_path) as img0:
        image = img0.convert("RGB")

        def _one(job: tuple[int, int, list[int]]) -> tuple[int, int, str]:
            q_index, sub_index, bbox = job
            if stop_event and stop_event.is_set():
                raise RuntimeError("已停止批改")
            try:
                return (q_index, sub_index, _extract_slot_answer_text(client, model, image, bbox))
            except RuntimeError:
                raise
            except Exception:
                # 单槽识别失败按空处理：批改端回退 answer_words / image 1 红框
                return (q_index, sub_index, "")

        workers = max(
            1,
            min(len(jobs), int(os.environ.get("REFERENCE_ANSWER_TABLE_WORKERS", "4") or "4")),
        )
        if jobs:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                for q_index, sub_index, text in executor.map(_one, jobs):
                    results[(q_index, sub_index)] = text

    entries: list[dict] = []
    for question in questions:
        slot_entries = []
        for sub_index, bbox in enumerate(_question_slot_bboxes(question), start=1):
            slot_entries.append(
                {
                    "sub_index": sub_index,
                    "bbox": [_to_int(value) for value in bbox[:4]],
                    "answer_text": _strip_wrapping_parens(
                        results.get((question.display_index, sub_index), "")
                    ),
                }
            )
        first_text = str(slot_entries[0]["answer_text"]) if slot_entries else ""
        entries.append(
            {
                "display_index": question.display_index,
                # 题号兜底：题干没解析出印刷题号时，从答案转写首行（"8.(1)…"）认号
                "printed_no": question.printed_no or _parse_printed_no(first_text),
                "question_bbox": [_to_int(value) for value in question.question_bbox[:4]],
                "slots": slot_entries,
                "full_answer": "\n".join(
                    str(slot["answer_text"]).strip()
                    for slot in slot_entries
                    if str(slot.get("answer_text") or "").strip()
                ),
            }
        )
    # 按题号识别：合并块（1-7 题一块）按行内题号拆成一题一行；再补切题漏掉的题号
    entries = _split_answer_entries_by_printed_numbers(entries)
    # 空白卷全槽无答案：缺号补扫会把题干当答案抄回来，整段跳过（答案表只留题号+答题区）
    has_any_text = any(
        str(slot.get("answer_text") or "").strip()
        for entry in entries
        for slot in (entry.get("slots") or [])
        if isinstance(slot, dict)
    )
    if has_any_text:
        entries = _fill_missing_answer_numbers(
            entries,
            image,
            client,
            model,
            skip_printed_numbers=skip_printed_numbers,
            stop_event=stop_event,
        )
    return entries


def _manual_edits_overlay(saved: Any, cache_token: dict) -> dict:
    """老师手改答案的覆盖层；换源文件即作废（答案跟着旧图没意义），仅切题变更保留。"""
    if not isinstance(saved, dict):
        return {}
    edits = saved.get("manual_edits")
    if not isinstance(edits, dict):
        return {}
    by_index = edits.get("by_display_index")
    if not isinstance(by_index, dict) or not by_index:
        return {}
    saved_token = saved.get("cache_token") if isinstance(saved.get("cache_token"), dict) else {}
    if saved_token.get("source_signature") != cache_token.get("source_signature"):
        return {}
    return edits


def _find_slot_by_bbox(slots: list, target: Any, taken: set) -> Optional[int]:
    """按框找槽位下标：先精确、再中心距 ≤½ 对角线；不认就 None（宁缺勿串）。"""
    if not isinstance(target, (list, tuple)) or len(target) < 4:
        return None
    try:
        tb = [float(v) for v in target[:4]]
    except (TypeError, ValueError):
        return None
    best_pos, best_d = None, None
    for pos, slot in enumerate(slots):
        if pos in taken:
            continue
        bbox = slot.get("bbox") if isinstance(slot, dict) else None
        if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
            continue
        try:
            cb = [float(v) for v in bbox[:4]]
        except (TypeError, ValueError):
            continue
        if cb == tb:
            return pos
        d = (
            ((cb[0] + cb[2]) - (tb[0] + tb[2])) ** 2 + ((cb[1] + cb[3]) - (tb[1] + tb[3])) ** 2
        ) ** 0.5 / 2.0
        if best_d is None or d < best_d:
            best_pos, best_d = pos, d
    if best_pos is None or best_d is None:
        return None
    diag = ((tb[2] - tb[0]) ** 2 + (tb[3] - tb[1]) ** 2) ** 0.5
    return best_pos if best_d <= 0.5 * diag else None


def _apply_manual_edits_to_entries(entries: list, manual_edits: dict) -> list:
    """按 display_index 把手改答案覆盖进识别条目（幂等）；full_answer 由槽文本合成。

    槽对位优先按保存时的 bbox（1016 教训：切题重排后 sub_index 串位，旧 6 键
    手改硬盖 7 槽，整题答案错位+漏「神圣」）；存了 bbox 对不上框的宁缺勿串、
    不按号硬盖。没存 bbox 的旧覆盖层才回退 sub_index。
    """
    by_index = manual_edits.get("by_display_index") if isinstance(manual_edits, dict) else {}
    if not isinstance(by_index, dict):
        return entries
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        item = by_index.get(str(_to_int(entry.get("display_index"), 0)))
        if not isinstance(item, dict):
            continue
        printed = str(item.get("printed_no") or "").strip()
        if printed:
            entry["printed_no"] = printed
        slot_texts = item.get("slots") if isinstance(item.get("slots"), dict) else {}
        slot_bboxes = item.get("slot_bboxes") if isinstance(item.get("slot_bboxes"), dict) else {}
        slots = [slot for slot in (entry.get("slots") or []) if isinstance(slot, dict)]
        taken: set = set()
        for key, text in slot_texts.items():
            bbox = slot_bboxes.get(str(key)) if slot_bboxes else None
            if bbox is None:
                continue
            pos = _find_slot_by_bbox(slots, bbox, taken)
            if pos is None:
                continue
            slots[pos]["answer_text"] = str(text or "")
            taken.add(pos)
        for slot in slots:
            key = str(_to_int(slot.get("sub_index"), 0))
            if key in slot_bboxes:
                continue
            if key in slot_texts:
                slot["answer_text"] = str(slot_texts.get(key) or "")
        entry["slots"] = slots
        entry["full_answer"] = "\n".join(
            str(slot.get("answer_text") or "").strip()
            for slot in slots
            if str(slot.get("answer_text") or "").strip()
        )
        entry["edited"] = True
    return entries


# ── 答案纸（答案单独一张纸）：按印刷题号扫出 {题号: 答案} 合并进答案表 ──
# 空白卷模式：答案写在单独一张「答案纸」上，试卷只负责答题区。答案纸逐页整版
# 转写后按印刷题号落进对应条目；手改覆盖层在其后再盖回（老师永远有最后发言权）。
_ANSWER_SHEET_CACHE_FILENAME = ".answer_sheet_cache.json"
# 多空答案子号：（1）（2）/(1)(2)——与拆条题号正则不同，这里带括号才认
_SHEET_SLOT_SUB_NO_RE = re.compile(r"[（(](\d{1,3})[）)]")


def _answer_sheet_cache_path(folder_safe: str) -> Path:
    return correct_docs_dir() / folder_safe / _ANSWER_SHEET_CACHE_FILENAME


def _answer_sheet_texts_signature(texts: dict) -> str:
    """答案纸合并层指纹：内容一致就不触发答案表缓存重建；空表回空串。"""
    if not texts:
        return ""
    blob = json.dumps(
        {str(k): str(v) for k, v in texts.items()},
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.md5(blob).hexdigest()


# 无小问号多空答案的分隔符：先只按空白拆，再按空白+标点拆（两级，宁缺勿串）
_ANSWER_PART_WS_RE = re.compile(r"[\s　]+")
_ANSWER_PART_SEP_RE = re.compile(r"[\s　、,，;；。！？]+")


def _paren_open_excess(text: str) -> int:
    return (
        text.count("（")
        + text.count("(")
        - text.count("）")
        - text.count(")")
    )


def _split_plain_answer_to_parts(value: str, sep_re: re.Pattern) -> list[str]:
    """没小问号的答案按分隔符拆段。

    括号补充粘回前段（「骆驼祥子 (或：四世同堂)」不拆成两段）：
    以括号开头的段并进前一段（不留空）；前段括号没闭合的后续段以空格并回。
    """
    parts: list[str] = []
    for token in sep_re.split(value):
        token = token.strip()
        if not token:
            continue
        if parts and token.startswith(("（", "(")):
            parts[-1] = parts[-1] + token
        elif parts and _paren_open_excess(parts[-1]) > 0:
            parts[-1] = parts[-1] + " " + token
        else:
            parts.append(token)
    return parts


def _split_answer_text_to_slot_texts(text: str, count: int) -> list[str]:
    """答案纸一段答案拆进多空槽。

    ①（1）（2）小问号拆（带括号才认）；②没小问号按分隔符拆——空白卷答案纸的
    多空题就是「扼制 柳暗花明」「老舍 舒庆春 骆驼祥子(或：四世同堂)」这种写法，
    两级分隔（先空白、再空白+标点）恰好拆成 count 段才用；③拆不出整段进第一空。
    """
    raw = str(text or "")
    if count <= 1:
        return [raw]
    matches = list(_SHEET_SLOT_SUB_NO_RE.finditer(raw))
    if len(matches) >= 2:
        chunks: list[str] = []
        for idx, match in enumerate(matches):
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(raw)
            chunks.append(raw[match.end() : end].strip())
        if len(chunks) == count and all(chunks):
            return chunks
        # 小问号结构对不上空数：不猜，整段进第一空
        return [raw] + [""] * (count - 1)
    scan = _SHEET_SLOT_SUB_NO_RE.sub(" ", raw) if matches else raw
    for sep_re in (_ANSWER_PART_WS_RE, _ANSWER_PART_SEP_RE):
        parts = _split_plain_answer_to_parts(scan, sep_re)
        if len(parts) == count and all(parts):
            return parts
    return [raw] + [""] * (count - 1)


def _apply_answer_sheet_texts(entries: list, by_printed_no: dict) -> list:
    """答案纸把答案填进条目（覆盖槽文本）；手改覆盖层在其后再盖回。

    两段匹配：①按印刷题号直取；②行序兜底——空白卷切题常认不出印刷号
    （printed_no 大多空、零星几行带号），此时按行序一一配对。

    行序兜底只在「自洽」时启用（宁缺勿串）：答案纸题号恰为连续 1..N 且
    N == 条目数，且每个条目的印刷号要么空、要么正好等于它按 display_index
    排好的行序位次。部分行带号不再一票否决兜底——号与行序自洽时照样把
    没号的行按行序补齐；有一个号对不上位次（有串行风险）就整页不兜底。
    """
    if not isinstance(by_printed_no, dict) or not by_printed_no:
        return entries
    rows = [entry for entry in entries if isinstance(entry, dict)]
    for entry in rows:
        number = _to_int(entry.get("printed_no"), 0)
        text = by_printed_no.get(str(number)) if number > 0 else None
        if text is None or not str(text).strip():
            continue
        _fill_entry_slots_from_sheet_text(entry, str(text))
    # ②行序兜底：答案纸题号必须恰为完整连续 1..N 且 N == 条目数
    if not rows:
        return entries
    sheet_numbers = sorted(_to_int(key, 0) for key in by_printed_no.keys())
    want = list(range(1, len(rows) + 1))
    if sheet_numbers != want:
        return entries
    ordered = sorted(rows, key=lambda entry: _to_int(entry.get("display_index"), 0))
    # 自洽门槛：带号的条目，号必须正好等于它的行序位次，否则不兜底（防串行）
    for position, entry in enumerate(ordered, start=1):
        number = _to_int(entry.get("printed_no"), 0)
        if number > 0 and number != position:
            return entries
    for entry, number in zip(ordered, want):
        text = by_printed_no.get(str(number))
        if text is None or not str(text).strip():
            continue
        _fill_entry_slots_from_sheet_text(entry, str(text))
    return entries


def _fill_entry_slots_from_sheet_text(entry: dict, text: str) -> None:
    """把答案纸一段答案填进条目槽；full_answer 由槽文本合成。"""
    slots = [slot for slot in (entry.get("slots") or []) if isinstance(slot, dict)]
    if not slots:
        return
    slot_texts = _split_answer_text_to_slot_texts(text, len(slots))
    for slot, value in zip(slots, slot_texts):
        slot["answer_text"] = value
    entry["slots"] = slots
    entry["full_answer"] = "\n".join(
        str(slot.get("answer_text") or "").strip()
        for slot in slots
        if str(slot.get("answer_text") or "").strip()
    )


def load_or_build_answer_sheet_texts(folder_safe: str, pages: list) -> dict:
    """答案纸逐页整版扫描出 {印刷题号: 答案文本}，按各页文件签名缓存。

    pages: [(source_path, image_path), ...] 按页序。换任一页文件签名就整包重扫；
    扫描中途失败回空且不写缓存（下次自动重试）；全空结果也缓存（防重复烧 VL）。
    """
    if not pages:
        return {}
    if Image is None:
        raise RuntimeError("需要安装 Pillow")
    signature: dict[str, dict] = {}
    for index, (source_path, _image_path) in enumerate(pages, start=1):
        try:
            signature[str(index)] = _file_signature(Path(source_path))
        except Exception:
            signature[str(index)] = {}
    cache_path = _answer_sheet_cache_path(folder_safe)
    saved = _read_json(cache_path) or {}
    if saved.get("signature") == signature and isinstance(saved.get("by_printed_no"), dict):
        return {
            str(k): str(v) for k, v in saved.get("by_printed_no").items() if str(v or "").strip()
        }
    client, model = _get_qwen_client_and_model()
    by_no: dict[str, str] = {}
    try:
        for _source_path, image_path in pages:
            path = Path(image_path)
            if not path.is_file():
                return {}
            with Image.open(path) as img0:
                image = img0.convert("RGB")
                width, height = image.size
                chunks = _extract_scan_answer_chunks(client, model, image, [0, 0, width, height])
            for number, text in (chunks or {}).items():
                value = str(text or "").strip()
                if value:
                    by_no[str(number)] = value
    except Exception:
        traceback.print_exc()
        return {}
    _write_json(
        cache_path,
        {"signature": signature, "by_printed_no": by_no, "updated_at": _now_iso()},
    )
    return by_no


def read_answer_sheet_texts(folder_safe: str) -> dict:
    """只读答案纸扫描缓存（不触发扫描）；没有返回 {}。"""
    saved = _read_json(_answer_sheet_cache_path(folder_safe)) or {}
    raw = saved.get("by_printed_no")
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if str(v or "").strip()}


def clear_answer_sheet_cache(folder_safe: str) -> None:
    """作废答案纸扫描缓存（专窗点「重新识别」用），下次扫描全量重来。"""
    try:
        _answer_sheet_cache_path(folder_safe).unlink(missing_ok=True)
    except Exception:
        pass


def save_answer_sheet_texts(folder_safe: str, pages: list, by_printed_no: dict) -> dict:
    """保存答案纸识别结果（老师在专窗里改过答案后落盘）。

    签名对齐当前答案纸文件：后续 load_or_build_answer_sheet_texts 吃到这份
    人工修正版（signature 一致直接回缓存），合并进答案表的就是老师确认过的答案。
    """
    if not isinstance(by_printed_no, dict):
        raise RuntimeError("答案纸答案格式不正确")
    signature: dict[str, dict] = {}
    for index, (source_path, _image_path) in enumerate(pages or [], start=1):
        try:
            signature[str(index)] = _file_signature(Path(source_path))
        except Exception:
            signature[str(index)] = {}
    cleaned = {
        str(_to_int(key, 0) or str(key).strip()): str(value).strip()
        for key, value in by_printed_no.items()
        if str(value or "").strip()
    }
    cleaned = {key: value for key, value in cleaned.items() if key}
    _write_json(
        _answer_sheet_cache_path(folder_safe),
        {
            "signature": signature,
            "by_printed_no": cleaned,
            "edited": True,
            "updated_at": _now_iso(),
        },
    )
    return cleaned


def read_reference_answer_table_page(folder_safe: str, page_no: int) -> dict:
    """只读缓存答案表页（不触发识别）；没有返回 {}。"""
    data = _read_json(_answer_table_path(folder_safe)) or {}
    pages = data.get("pages") if isinstance(data.get("pages"), dict) else {}
    saved = pages.get(str(_to_int(page_no, 0)))
    page = copy.deepcopy(saved) if isinstance(saved, dict) else {}
    if isinstance(page.get("questions"), list):
        page["questions"] = _sorted_answer_table_entries(page["questions"])
    return page


def save_reference_answer_table_edits(folder_safe: str, page_no: int, edited_questions: list) -> dict:
    """保存老师对识别答案的手动修改（覆盖层持久化，自动重建时保留）。"""
    if not isinstance(edited_questions, list) or not edited_questions:
        raise RuntimeError("没有可保存的答案修改")
    page_key = str(_to_int(page_no, 0))
    path = _answer_table_path(folder_safe)
    with _ANSWER_TABLE_LOCK:
        data = _read_json(path) or {}
        pages = data.get("pages") if isinstance(data.get("pages"), dict) else {}
        saved = pages.get(page_key)
        if not isinstance(saved, dict) or not saved.get("questions"):
            raise RuntimeError("答案表尚未生成，请先识别标准答案")
        manual = saved.get("manual_edits") if isinstance(saved.get("manual_edits"), dict) else {}
        by_index = dict(
            manual.get("by_display_index") if isinstance(manual.get("by_display_index"), dict) else {}
        )
        for item in edited_questions:
            if not isinstance(item, dict):
                continue
            display_index = _to_int(item.get("display_index"), 0)
            if display_index <= 0:
                raise RuntimeError("答案修改缺少题号")
            # 现表槽框随覆盖层存档：切题重排后重建仍按框回填（sub_index 会串位）
            current_slots = {
                _to_int(slot.get("sub_index"), 0): slot
                for entry in (saved.get("questions") or [])
                if isinstance(entry, dict)
                and _to_int(entry.get("display_index"), 0) == display_index
                for slot in (entry.get("slots") or [])
                if isinstance(slot, dict)
            }
            slots_payload: dict[str, str] = {}
            slot_bboxes: dict[str, list] = {}
            for slot in item.get("slots") or []:
                if not isinstance(slot, dict):
                    continue
                sub_index = _to_int(slot.get("sub_index"), 0)
                if sub_index <= 0:
                    continue
                slots_payload[str(sub_index)] = str(slot.get("answer_text") or "")
                bbox = slot.get("bbox") or (current_slots.get(sub_index) or {}).get("bbox")
                if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
                    slot_bboxes[str(sub_index)] = [_to_int(value) for value in bbox[:4]]
            if not slots_payload:
                raise RuntimeError(f"第{display_index}题缺少作答区答案")
            overlay: dict[str, Any] = {"slots": slots_payload}
            if slot_bboxes:
                overlay["slot_bboxes"] = slot_bboxes
            printed = str(item.get("printed_no") or "").strip()
            if printed:
                overlay["printed_no"] = printed
            by_index[str(display_index)] = overlay
        manual = {"updated_at": _now_iso(), "by_display_index": by_index}
        entries = [entry for entry in (saved.get("questions") or []) if isinstance(entry, dict)]
        for entry in entries:
            entry.pop("edited", None)
        _apply_manual_edits_to_entries(entries, manual)
        saved["questions"] = _sorted_answer_table_entries(entries)
        saved["manual_edits"] = manual
        pages[page_key] = saved
        _write_json(path, {"version": 1, "updated_at": _now_iso(), "pages": pages})
        return copy.deepcopy(saved)


def invalidate_reference_answer_table(
    folder_safe: str,
    page_no: Optional[int] = None,
    *,
    reset_edits: bool = False,
) -> None:
    """丢弃答案表缓存强制重识别；reset_edits=True 连手动修改一起清掉。"""
    path = _answer_table_path(folder_safe)
    with _ANSWER_TABLE_LOCK:
        data = _read_json(path) or {}
        pages = data.get("pages") if isinstance(data.get("pages"), dict) else {}
        keys = [str(_to_int(page_no, 0))] if page_no else list(pages.keys())
        changed = False
        for key in keys:
            saved = pages.get(key)
            if not isinstance(saved, dict):
                continue
            if reset_edits:
                saved.pop("manual_edits", None)
                for entry in saved.get("questions") or []:
                    if isinstance(entry, dict):
                        entry.pop("edited", None)
            saved["cache_token"] = {"invalidated_at": _now_iso()}
            pages[key] = saved
            changed = True
        if changed:
            _write_json(path, {"version": 1, "updated_at": _now_iso(), "pages": pages})
    # 重新识别 = 全链路重来：答案纸扫描缓存一并作废（扫错/扫漏这次重试）
    clear_answer_sheet_cache(folder_safe)


def load_or_build_reference_answer_table(
    folder_safe: str,
    page_no: int,
    standard_doc: dict,
    *,
    answer_sheet_texts: Optional[dict] = None,
    stop_event: Optional[threading.Event] = None,
) -> dict:
    """标准答案完整识别表：按卷缓存（源文件签名或切题审查变更即重建）。

    批改作业开始前调用（先懂标准答案，再看试卷）；返回
    {"questions": [每题 slots/full_answer], ...}，失败返回 {}（判分回退旧路径）。
    answer_sheet_texts 是答案纸（答案单独一张纸）扫出的 {印刷题号: 答案}：
    合并顺序 = 识别 → 答案纸 → 手改覆盖层（手改最后盖回，老师有最终发言权）。
    老师手动修改过的题带 manual_edits 覆盖层：切题变更重建时保留、换源文件才作废。
    """
    questions = standard_doc.get("questions")
    image_path = str(standard_doc.get("image_path") or standard_doc.get("source_path") or "")
    if not (isinstance(questions, list) and questions):
        raw = standard_doc.get("raw") if isinstance(standard_doc.get("raw"), dict) else {}
        if raw and image_path and Path(image_path).is_file():
            questions = extract_vlm_questions(raw, image_path=image_path)
    if not (isinstance(questions, list) and questions):
        return {}
    if not image_path or not Path(image_path).is_file():
        return {}
    source_path = Path(str(standard_doc.get("source_path") or image_path))
    try:
        signature = _file_signature(source_path)
    except Exception:
        signature = {}
    layout = load_reference_layout(folder_safe) or {}
    if answer_sheet_texts is None:
        # 防呆：调用方没带答案纸文本时回读扫描缓存，避免无参调用把已合并的答案抹掉
        cached_sheet = _read_json(_answer_sheet_cache_path(folder_safe)) or {}
        raw_sheet = cached_sheet.get("by_printed_no")
        answer_sheet_texts = raw_sheet if isinstance(raw_sheet, dict) else {}
    sheet_texts = {
        str(k): str(v) for k, v in (answer_sheet_texts or {}).items() if str(v or "").strip()
    }
    cache_token = {
        "source_signature": signature,
        "layout_updated_at": str(layout.get("updated_at") or ""),
        # 算法版本：拆条/补漏升级后旧缓存自动重建（手改覆盖层只看 source_signature 不受影响）
        "extract_version": _ANSWER_TABLE_EXTRACT_VERSION,
        # 答案纸答案也进缓存指纹：换/传答案纸即重建合并结果；没传答案纸为空串
        "answer_sheet_signature": _answer_sheet_texts_signature(sheet_texts),
    }
    path = _answer_table_path(folder_safe)
    data = _read_json(path) or {}
    pages = data.get("pages") if isinstance(data.get("pages"), dict) else {}
    saved = pages.get(str(page_no))
    if (
        isinstance(saved, dict)
        and saved.get("cache_token") == cache_token
        and isinstance(saved.get("questions"), list)
        and saved.get("questions")
    ):
        # 保存/重建时已把手改覆盖层并进 questions，这里直接用缓存
        saved["questions"] = _sorted_answer_table_entries(saved["questions"])
        # 旧缓存没有 image_size：就地补上，前端画答题区框总览要用（批改图坐标系）
        if not saved.get("image_size"):
            size = standard_doc.get("image_size")
            if isinstance(size, (list, tuple)) and len(size) >= 2:
                saved["image_size"] = [_to_int(size[0]), _to_int(size[1])]
        return saved
    manual_edits = _manual_edits_overlay(saved, cache_token)
    raw_for_flags = standard_doc.get("raw") if isinstance(standard_doc.get("raw"), dict) else {}
    entries = extract_reference_answer_table(
        questions,
        image_path,
        skip_printed_numbers=_layout_deleted_printed_nos(raw_for_flags) if raw_for_flags else None,
        stop_event=stop_event,
    )
    if not entries:
        return {}
    if sheet_texts:
        # 答案纸先按印刷题号填，手改覆盖层再盖回
        _apply_answer_sheet_texts(entries, sheet_texts)
    if manual_edits:
        _apply_manual_edits_to_entries(entries, manual_edits)
    entries = _sorted_answer_table_entries(entries)
    doc_size = standard_doc.get("image_size")
    page_payload = {
        "page_no": _to_int(page_no, 1),
        "cache_token": cache_token,
        "image_path": image_path,
        # 批改图尺寸：前端答题区框总览按这个坐标系铺 SVG（与切题审查同款拉伸对齐）
        "image_size": (
            [_to_int(doc_size[0]), _to_int(doc_size[1])]
            if isinstance(doc_size, (list, tuple)) and len(doc_size) >= 2
            else None
        ),
        "updated_at": _now_iso(),
        "questions": entries,
    }
    if manual_edits:
        page_payload["manual_edits"] = manual_edits
    with _ANSWER_TABLE_LOCK:
        data = _read_json(path) or {}
        pages = data.get("pages") if isinstance(data.get("pages"), dict) else {}
        pages[str(page_no)] = page_payload
        _write_json(path, {"version": 1, "updated_at": _now_iso(), "pages": pages})
    return page_payload


def _answer_table_slot_text(
    answer_table: Optional[dict],
    question: VlmQuestion,
    target_bbox: Optional[list[int]],
    *,
    prefer_no: Optional[str] = None,
) -> Optional[str]:
    """答案表取本槽标准答案文本；多槽对不上号返回 None（宁缺勿串）。

    查条顺序：①prefer_no 印刷题号直取对应行（拆条后一题一行，与判分查表同通道）；
    ②切题 display_index 精确匹配；③拆条兄弟拼回（合并块没有整条目时还原全文）；
    ④question_bbox 兜底。
    """
    if not isinstance(answer_table, dict):
        return None
    entries = answer_table.get("questions")
    if not isinstance(entries, list) or not entries:
        return None
    entry: Optional[dict] = None
    want_no = str(prefer_no or "").strip()
    if want_no:
        for candidate in entries:
            if isinstance(candidate, dict) and str(candidate.get("printed_no") or "").strip() == want_no:
                entry = candidate
                break
    if entry is None:
        for candidate in entries:
            if isinstance(candidate, dict) and _to_int(candidate.get("display_index"), -1) == question.display_index:
                entry = candidate
                break
    if entry is None:
        siblings = [
            candidate
            for candidate in entries
            if isinstance(candidate, dict)
            and _to_int(candidate.get("source_display_index"), -1) == question.display_index
        ]
        if siblings:
            texts = [
                str(candidate.get("full_answer") or "").strip()
                for candidate in _sorted_answer_table_entries(siblings)
            ]
            joined = "\n".join(text for text in texts if text)
            return joined or None
    if entry is None:
        target = [_to_float(value) for value in (question.question_bbox or [])[:4]]
        for candidate in entries:
            if not isinstance(candidate, dict):
                continue
            bbox = [_to_float(value) for value in (candidate.get("question_bbox") or [])[:4]]
            if len(bbox) == 4 and bbox == target:
                entry = candidate
                break
    if entry is None:
        return None
    slots = [slot for slot in (entry.get("slots") or []) if isinstance(slot, dict)]
    if not slots:
        return str(entry.get("full_answer") or "").strip() or None
    if len(slots) == 1:
        text = str(slots[0].get("answer_text") or "").strip()
        return text or (str(entry.get("full_answer") or "").strip() or None)
    pos = _bbox_match_position([slot.get("bbox") for slot in slots], target_bbox)
    if pos is None:
        return None
    return str(slots[pos].get("answer_text") or "").strip() or None


def _answer_table_sort_key(entry: dict) -> tuple:
    """答案表按印刷题号升序（认不出题号的排后面，再按切题序）。"""
    if not isinstance(entry, dict):
        return (2, 0, 0)
    no = str(entry.get("printed_no") or "").strip()
    if no.isdigit():
        return (0, int(no), _to_int(entry.get("display_index"), 0))
    return (1, 0, _to_int(entry.get("display_index"), 0))


def _sorted_answer_table_entries(entries: list) -> list:
    try:
        return sorted(entries, key=_answer_table_sort_key)
    except Exception:
        return entries


def _answer_table_summary_text(answer_table: Optional[dict]) -> str:
    """完整答案表文本（每题一行）：进判分提示词，先认题号再对照本表。"""
    if not isinstance(answer_table, dict):
        return ""
    entries = answer_table.get("questions")
    if not isinstance(entries, list) or not entries:
        return ""
    lines = []
    for entry in _sorted_answer_table_entries(entries):
        if not isinstance(entry, dict):
            continue
        full = str(entry.get("full_answer") or "").strip()
        if not full:
            continue
        no = str(entry.get("printed_no") or "").strip() or str(_to_int(entry.get("display_index"), 0))
        # 转写不可靠（[?] 等）的行不给错文（错文会反判学生），按协议标〈文本缺失〉
        # ——提示词已有兜底条款，模型对该行改以 image 1 红框内标准答案为准。
        lines.append(f"第{no}题：{_unreliable_as_text_missing(full) or full}")
    return "\n".join(lines)


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


def _encode_image_for_vlm(path: str) -> str:
    """送 VLM 前压图（1015 内存防线）：同尺寸重编码，只降质量不改像素。

    为什么不能缩尺寸：extract_vlm_questions/_normalize_bbox 用磁盘原图
    Image.open(image_path).size 归一化坐标，若送小图，返回的像素坐标会
    落在原图错误区域。同尺寸重编码则坐标空间完全一致，零副作用。

    压不小（重编码后更大或差不多）就用原字节；任何异常回退原字节。
    """
    raw = Path(path).read_bytes()
    if Image is None or len(raw) < 300 * 1024:
        # 小图不折腾；没有 PIL 直接原样
        return base64.b64encode(raw).decode("utf-8")
    try:
        with Image.open(path) as im:
            # 手写卷面都是 RGB/灰度；调色板/带透明的先铺白底再压 JPEG
            if im.mode not in ("RGB", "L"):
                background = Image.new("RGB", im.size, (255, 255, 255))
                converted = im.convert("RGBA")
                background.paste(converted, mask=converted.split()[-1])
                work = background
            else:
                work = im
            buf = BytesIO()
            work.save(buf, format="JPEG", quality=82, optimize=True)
        compressed = buf.getvalue()
        if len(compressed) >= len(raw):
            return base64.b64encode(raw).decode("utf-8")
        return base64.b64encode(compressed).decode("utf-8")
    except Exception:
        return base64.b64encode(raw).decode("utf-8")


def submit_paper_cut_vlm(
    image_path: str,
    stop_event: Optional[threading.Event] = None,
    *,
    allow_empty: bool = False,
) -> dict:
    if stop_event and stop_event.is_set():
        raise RuntimeError("已停止批改")
    path = _ensure_image_for_vlm(image_path)
    img_base64 = _encode_image_for_vlm(path)
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
    # 1015 内存防线：默认并发 8→4。每线程整页 base64 常驻（手机卷面 ~1.2MB
    # → base64 ~1.6MB + JSON 请求体副本），8G 机器上 8 线程双批次即事故形态。
    workers = max_workers or int(os.environ.get("REFERENCE_VLM_BAIDU_WORKERS", "4") or "4")
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


def _raw_questions_list(raw: dict) -> Optional[list]:
    """与 _questions_container 相同查找，但找不到时返回 None（不给一次性空表）。"""
    if not isinstance(raw, dict):
        return None
    for key in ("qus_results", "qus_result"):
        if isinstance(raw.get(key), list):
            return raw[key]
    result = raw.get("result")
    if isinstance(result, dict):
        for key in ("qus_results", "qus_result"):
            if isinstance(result.get(key), list):
                return result[key]
        nested = result.get("result")
        if isinstance(nested, dict):
            for key in ("qus_results", "qus_result"):
                if isinstance(nested.get(key), list):
                    return nested[key]
    return None


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
    used_layout_stamp = False
    for pos, item in enumerate(_questions_container(raw), start=1):
        if not isinstance(item, dict):
            continue
        # 切题审查删掉的题（老师判它不存在）：直接跳过，别借重建回魂
        if item.get("layout_deleted"):
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
        # 切题戳：display_no 的稳定身份（重建提取时不再按容器位置/密序重排）
        stamped = _to_int(item.get("layout_display_index"), 0)
        if stamped > 0:
            used_layout_stamp = True
        display_index = stamped if stamped > 0 else pos
        is_orphan_continuation = (
            stamped <= 0  # 带切题身份的条目绝不当续块丢掉
            and bool(questions)
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
                display_index=display_index,
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
                printed_no=_parse_printed_no(question_words),
            )
        )
    questions.sort(key=lambda q: q.display_index)
    # 无切题戳的全新 raw 才做密序重排（老口径：跳过续块后按序补号）；
    # 带戳的 corrected_raw 必须保留原号——display_no 是切题审查的匹配键，
    # 中段删除后重排会把老师的修改套到别的题上。
    if not used_layout_stamp:
        for display_index, question in enumerate(questions, start=1):
            question.display_index = display_index
    return questions


_SLOT_LABEL_FONT_CACHE: dict[int, Any] = {}


def _slot_label_font(size: int):
    """槽位标签字体（ASCII 槽键即可）；跨平台候选同 pipeline 留痕字体。"""
    if ImageFont is None:
        return None
    font = _SLOT_LABEL_FONT_CACHE.get(size)
    if font is None:
        from app.grading.pipeline import _load_truetype_font

        font = _load_truetype_font(size, allow_default=True)
        _SLOT_LABEL_FONT_CACHE[size] = font
    return font


def _draw_slot_label(
    draw,
    hx1: int,
    hy1: int,
    label: str,
    *,
    edge: int,
    crop_size: tuple[int, int],
) -> None:
    """槽位键画成大号红字白底标签。

    串槽根因：旧标签是默认小号字，模型读不出就按红框视觉顺序硬填槽键。
    标签放大后优先贴红框左上角上方，顶到裁图边才压进框内左上角。
    """
    if not label:
        return
    cw, ch = crop_size
    font_size = max(22, min(64, int(min(cw, ch) * 0.05)))
    font = _slot_label_font(font_size)
    text = str(label)
    try:
        tb = draw.textbbox((0, 0), text, font=font)
        tw, th = max(1, tb[2] - tb[0]), max(1, tb[3] - tb[1])
    except Exception:
        tw, th = max(1, int(font_size * 0.62 * len(text))), font_size
    pad = max(2, font_size // 6)
    lx = max(0, min(hx1 + edge, cw - tw - 2 * pad))
    ly = hy1 - th - 2 * pad
    if ly < 0:
        ly = min(hy1 + edge, max(0, ch - th - 2 * pad))
    draw.rectangle(
        (lx - pad, ly - pad, lx + tw + pad, ly + th + pad),
        fill=(255, 255, 255),
    )
    draw.text((lx, ly), text, fill=(220, 25, 25), font=font)


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
                _draw_slot_label(
                    draw,
                    hx1,
                    hy1,
                    label,
                    edge=width,
                    crop_size=(crop.width, crop.height),
                )
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
                    _draw_slot_label(
                        draw,
                        rx1,
                        ry1,
                        label,
                        edge=width,
                        crop_size=(crop.width, crop.height),
                    )
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


def _question_for_no_or_bbox(
    questions: list[VlmQuestion],
    printed_no: Optional[str],
    bbox: list[int],
    image_size: tuple[int, int],
) -> Optional[VlmQuestion]:
    """题号优先找题：印刷题号一致的候选里挑几何最近的；无题号/无同号候选再全量几何。"""
    if printed_no:
        same_no = [question for question in questions if question.printed_no == printed_no]
        if same_no:
            return _question_for_bbox(same_no, bbox, image_size)
    return _question_for_bbox(questions, bbox, image_size)


def _question_for_slot_box(
    questions: list[VlmQuestion],
    printed_no: Optional[str],
    slot_bbox: list[int],
    image_size: tuple[int, int],
) -> Optional[VlmQuestion]:
    """答题区落点找题：题号优先；再按答题区框与题区的最大重叠；最后中心最近。

    学生卷切题与标准卷不一致时，按整道题框缩放定位会掉进两题之间的缝里
    （10_1 会绑到上一题），按答题区自身位置的最大重叠才落在正确题上。
    """
    if not questions:
        return None
    if printed_no:
        same_no = [question for question in questions if question.printed_no == printed_no]
        if same_no:
            return _question_for_bbox(same_no, slot_bbox, image_size)
    slot_area = max(
        1, (slot_bbox[2] - slot_bbox[0]) * (slot_bbox[3] - slot_bbox[1])
    )
    best: Optional[VlmQuestion] = None
    best_fraction = 0.0
    for question in questions:
        if not question.question_bbox:
            continue
        overlap_w = max(
            0,
            min(slot_bbox[2], question.question_bbox[2])
            - max(slot_bbox[0], question.question_bbox[0]),
        )
        overlap_h = max(
            0,
            min(slot_bbox[3], question.question_bbox[3])
            - max(slot_bbox[1], question.question_bbox[1]),
        )
        fraction = (overlap_w * overlap_h) / slot_area
        if fraction > best_fraction:
            best = question
            best_fraction = fraction
    if best is not None and best_fraction > 0:
        return best
    return _question_for_bbox(questions, slot_bbox, image_size)


def _slot_context_bbox(
    question: VlmQuestion,
    answer_bbox: list[int],
    image_size: tuple[int, int],
) -> list[int]:
    """Keep question context, but do not downscale a whole-page question crop."""
    image_w, image_h = image_size
    qx1, qy1, qx2, qy2 = _clamp_bbox(question.question_bbox, image_size)
    # 红框可能落在题框外（学生切题切分不一致、跨题绑到真实墨迹）：
    # 上下文必须把红框圈进来，否则裁片里根本没有要批的作答。
    if answer_bbox:
        ax1, ay1, ax2, ay2 = _clamp_bbox(answer_bbox, image_size)
        qx1, qy1 = min(qx1, ax1), min(qy1, ay1)
        qx2, qy2 = max(qx2, ax2), max(qy2, ay2)
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


def _escape_unescaped_quotes_in_strings(candidate: str) -> str:
    """字符串值里未转义的 ASCII 引号 → 全角引号（模型常在 reason 里写 "B" 炸 JSON）。"""
    out: list[str] = []
    in_string = False
    escaped = False
    for i, ch in enumerate(candidate):
        if not in_string:
            out.append(ch)
            if ch == '"':
                in_string = True
        elif escaped:
            out.append(ch)
            escaped = False
        elif ch == "\\":
            out.append(ch)
            escaped = True
        elif ch == '"':
            j = i + 1
            while j < len(candidate) and candidate[j] in " \t\r\n":
                j += 1
            if j >= len(candidate) or candidate[j] in ",}]}:":
                out.append(ch)
                in_string = False
            else:
                out.append("“")  # 值内引号：转全角，保持 JSON 字符串完整
        else:
            out.append(ch)
    return "".join(out)


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
        repaired = _escape_unescaped_quotes_in_strings(candidate)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass
        if "Invalid \\escape" in str(exc):
            repaired = _escape_unsafe_json_string_backslashes(candidate)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError as repaired_exc:
                exc = repaired_exc
            combined = _escape_unsafe_json_string_backslashes(
                _escape_unescaped_quotes_in_strings(candidate)
            )
            try:
                return json.loads(combined)
            except json.JSONDecodeError as combined_exc:
                exc = combined_exc
        raise RuntimeError(f"千问返回 JSON 解析失败: {exc}; 原文: {raw[:300]}") from exc


# ── 转写读不准兜底（判定权收归代码）───────────────────────────────────
# 与 pipeline._apply_read_guard 同规则：转写带 [?]/[字1|字2] 标记或
# read_confidence<0.7 → 强制「待确认」。模型不得自选待确认——提示词里
# 不给这个选项（给了逃生口就滥用）；代码侧兜底才能拦住潦草蒙判。

_UNCERTAIN_TRANSCRIPTION_RE = re.compile(r"\[\?|\[[^\]]*\|[^\]]*\]")

# 看图直判兜底（对齐批改君「image 1 即标准答案」）：答案表某行转写带 [?] 等不可靠标记时，
# 不把错文当文本权威（错文会反判学生），也不让 read_guard 把整槽打成待确认（会淹没老师），
# 按协议落「〈文本缺失〉」——判分走提示词里已有的兜底条款「〈文本缺失〉的槽以 image 1 对应红框为准」。
_TEXT_MISSING = "〈文本缺失〉"


def _transcription_flagged(text: str) -> bool:
    return bool(_UNCERTAIN_TRANSCRIPTION_RE.search(str(text or "")))


def _unreliable_as_text_missing(text: Optional[str]) -> Optional[str]:
    """转写带 [?]/[字1|字2] 即不可靠 → 输出〈文本缺失〉哨兵；空/None 原样返回。"""
    value = str(text or "").strip()
    if not value:
        return text
    return _TEXT_MISSING if _transcription_flagged(value) else value


def _apply_read_guard(decision: dict) -> dict:
    """转写/标准答案识别不清 → 强制「待确认」（code 5）。幂等：重复归一化不再改写。"""
    transcription = str(decision.get("transcription") or "")
    raw_confidence = decision.get("read_confidence")
    try:
        confidence_val = float(raw_confidence) if raw_confidence is not None else None
    except (TypeError, ValueError):
        confidence_val = None
    standard_flagged = _transcription_flagged(decision.get("standard_answer_text"))
    uncertain = (
        _transcription_flagged(transcription)
        or standard_flagged
        or (confidence_val is not None and confidence_val < 0.7)
    )
    is_pending = _to_int(decision.get("correctResult"), 0) == PENDING
    if not uncertain and not is_pending:
        decision["read_uncertain"] = False
        return decision
    if not is_pending:
        decision["correctResult"] = PENDING
        decision["result"] = RESULT_TEXT[PENDING]
        decision["partial_ratio"] = None
    decision["read_uncertain"] = True
    base = str(decision.get("reason") or "").strip()
    if "待人工确认" not in base:
        if standard_flagged:
            note = "标准答案识别不清，待人工确认"
        elif _transcription_flagged(transcription) or (
            confidence_val is not None and confidence_val < 0.7
        ):
            shown = transcription.strip()[:80]
            note = f"识别不清，待人工确认（AI 读到：{shown}…）" if shown else "识别不清，待人工确认"
        else:
            note = "待人工确认"
        decision["reason"] = f"{note}；{base}" if base else note
    if not str(decision.get("analysis") or "").strip():
        decision["analysis"] = decision["reason"]
    return decision


def _standard_answer_text(task: "VlmGradingTask") -> Optional[str]:
    """本槽标准答案文本：答案表（完整识别）优先，answer_words（切题 OCR）兜底。"""
    explicit = getattr(task, "standard_answer_text", None)
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    return _answer_text_for_slot(task.standard_question, task.standard_answer_bbox)


def _table_quote_mismatch(quote: str, located_no: Optional[int], answer_table_text: str) -> Optional[str]:
    """表引文回验：模型自称引用的【参考答案完整表】行必须真实存在且属于 located_no。

    防两类查表事故反判学生：①查错行（把第3题答案当第2题标准）；②抄错字
   （把「扼制」记成「遏制」再嫌学生写错）。对得上/无从校验返回 None。
    引文允许只抄一个空（"第1题：肢体" vs 多空整行）或带小问号（"(1)…"）：
    比对前把「第N题：」行头和「(N)」小问号剥掉，行头题号不符直接判不一致。
    """
    quote = str(quote or "").strip()
    if not quote or not answer_table_text:
        return None
    # 引文是〈文本缺失〉行：表文本作废、该槽只认 image 1 → 无从校验，放行
    if _TEXT_MISSING in quote:
        return None

    def norm(s: str) -> str:
        s = re.sub(r"^第\d+题(?:[（(]\d+[）)])?\s*[:：]\s*", "", str(s or "").strip())
        s = re.sub(r"[（(]\d{1,3}[）)]", "", s)
        return re.sub(r"[\s，。、；：？！（）()《》“”‘’\[\]{}\"'，.,;:!?]", "", s)

    nq = norm(quote)
    if not nq:
        return None
    quote_no = re.match(r"第(\d+)题", quote)
    quote_no_value = int(quote_no.group(1)) if quote_no else None
    if located_no and quote_no_value and quote_no_value != located_no:
        return f"标准引文题号（第{quote_no_value}题）与本题第{located_no}题不一致"
    blocks: dict[int, str] = {}
    for part in re.split(r"(?=第\d+题\s*[:：])", answer_table_text):
        m = re.match(r"第(\d+)题\s*[:：]([\s\S]*)", part)
        if m:
            blocks.setdefault(int(m.group(1)), m.group(2))
    located = located_no or quote_no_value
    if located and located in blocks:
        # 目标行是〈文本缺失〉：表无原文可对质，引文抄 image 1 答案属正常行为 → 放行
        if _TEXT_MISSING in blocks[located]:
            return None
        target = norm(blocks[located])
        if nq in target or target in nq:
            return None
        return f"标准引文与答案表第{located}题不一致"
    for text in blocks.values():
        target = norm(text)
        if nq in target or target in nq:
            return None
    return "标准引文在参考答案完整表中找不到"


def _apply_conclusion_guard(decision: dict) -> dict:
    """判语结论与判定矛盾 → 待确认（例：理由以「…判错。」收尾却给了对）。

    只看最后一句结论，避免引用学生原文里的「判对/判错」误伤。
    """
    reason = str(decision.get("reason") or "")
    code = _to_int(decision.get("correctResult"), 0)
    sentences = [p for p in re.split(r"[。！？!?；;]", reason) if p.strip()]
    tail = sentences[-1] if sentences else reason
    says_wrong = any(t in tail for t in ("判错", "判为错", "判定为错", "判定错误", "判为错误", "判未作答", "判为未作答", "判定为未作答"))
    says_right = any(t in tail for t in ("判对", "判为对", "判定为对", "判正确", "判为正确", "判定正确", "判定为正确"))
    conflict = (
        (code in (CORRECT, PARTIAL) and says_wrong and not says_right)
        or (code in (WRONG, UNANSWERED) and says_right and not says_wrong)
    )
    if not conflict:
        return decision
    decision["correctResult"] = PENDING
    decision["result"] = RESULT_TEXT[PENDING]
    decision["partial_ratio"] = None
    base = reason.strip()
    note = "判语与结论矛盾，待人工确认"
    decision["reason"] = f"{note}；{base}" if base else note
    decision["analysis"] = decision["reason"]
    return decision


def _choice_letters(text: Any) -> str:
    """剥出选项字母串（去「第N题:」前缀/数字/空白/括号/标点）→ 大写；有非字母残留返回空串。"""
    s = re.sub(r"^第\d+题[:：]", "", str(text or "").strip())
    s = re.sub(r"^\d+", "", s)
    s = re.sub(r"[\s（）()\[\]【】{}<>《》.,。，、;；:：!?？！/|\\]", "", s)
    s = s.upper()
    return s if re.fullmatch(r"[A-D]+", s) else ""


def _multi_select_letter_rule(transcription: str, standard_text: str) -> Optional[tuple]:
    """多选题（标准答案 2-4 个 A-D 字母）确定性字母集合判定（20261021 用户定规则）。

    - 集合全同 → 对；
    - 选错任意一个（含错选+少选混合）→ 错 0 分；
    - 只少选没多选 → 半对（partial_ratio = 选对数/正确数）。
    转写/标准剥不出纯 A-D 字母串则返回 None 不改判（交 VL/人工）；返回 (code, partial_ratio)。
    """
    e = _choice_letters(standard_text)
    s = _choice_letters(transcription)
    if len(e) < 2 or not s:
        return None
    s_set, e_set = set(s), set(e)
    if s_set == e_set:
        return (CORRECT, None)
    if s_set - e_set:
        return (WRONG, None)
    return (PARTIAL, round(len(s_set) / len(e_set), 3))


def _objective_letter_conflict(transcription: str, standard_text: str, code: int) -> Optional[str]:
    """客观选项字母与判定矛盾（字母一致却判错 / 不一致却判对）→ 转人工。

    只在两侧都只剩一个 A-D 字母时生效，主观题不受影响。
    """
    t = re.sub(r"[\s（）()\[\]【】{}<>《》.,。，、;；:：!?？！]", "", str(transcription or ""))
    if not re.fullmatch(r"[A-Da-d]", t):
        return None
    s = re.sub(r"^第\d+题[:：]", "", str(standard_text or "").strip())
    s = re.sub(r"[\s（）()\[\]【】{}<>《》.,。，、;；:：!?？！]", "", s)
    s = re.sub(r"^\d+", "", s)
    if not re.fullmatch(r"[A-Da-d]", s):
        return None
    same = t.upper() == s.upper()
    if same and code == WRONG:
        return "选项字母与标准一致却判错"
    if not same and code in (CORRECT, PARTIAL):
        return "选项字母与标准不一致却判对"
    return None


def _normalize_decision(
    data: dict,
    question_id: int,
    *,
    standard_answer_text: Optional[str] = None,
    answer_table_text: str = "",
) -> dict:
    if not isinstance(data, dict):
        data = {}
    returned_id = _to_int(data.get("question_id"), question_id)
    if returned_id != question_id:
        raise RuntimeError(f"千问返回题号不一致: expected={question_id}, got={returned_id}")

    result_text = str(data.get("result") or "").strip()
    code = _to_int(data.get("correctResult"), 0)
    if code not in (CORRECT, WRONG, UNANSWERED, PARTIAL, PENDING):
        if result_text == "对":
            code = CORRECT
        elif result_text == "未作答":
            code = UNANSWERED
        elif result_text == "半对":
            code = PARTIAL
        elif result_text == "待确认":
            code = PENDING
        else:
            code = WRONG
    result_text = RESULT_TEXT.get(code, "错")
    partial_ratio = None
    if code == PARTIAL:
        partial_ratio = min(1.0, max(0.0, _to_float(data.get("partial_ratio"), 0.5)))
    reason = _normalize_math_text(_safe_text(data.get("reason"), limit=500))
    analysis = _normalize_math_text(_safe_text(data.get("analysis"), limit=1000))
    if not reason:
        reason = "识别不清，待人工确认" if code == PENDING else "已按标准答案完成判定"
    if not analysis:
        analysis = reason if code != CORRECT else "作答与标准答案一致。"
    confidence = _to_float(data.get("confidence"), 0.0)
    if confidence < 0 or confidence > 1:
        confidence = 0.0
    read_confidence = data.get("read_confidence")
    try:
        read_confidence = float(read_confidence) if read_confidence is not None else None
    except (TypeError, ValueError):
        read_confidence = None
    decision = {
        "question_id": question_id,
        "correctResult": code,
        "result": result_text,
        "reason": reason,
        "analysis": analysis,
        "confidence": round(confidence, 3),
        "partial_ratio": partial_ratio,
        # 转写证据（随 decision 走两遍归一化，read_guard 幂等依赖它）
        "transcription": str(data.get("transcription") or "").strip(),
        "read_confidence": read_confidence,
        "standard_answer_text": (
            str(standard_answer_text if standard_answer_text is not None else data.get("standard_answer_text") or "").strip()
        ),
        # 表引文随 decision 走两遍归一化（_insert_sub_grading_result 会再跑一次），保证幂等
        "standard_quote": str(data.get("standard_quote") or "").strip(),
        "located_no": _to_int(data.get("located_no"), 0) or None,
        "read_uncertain": False,
    }
    # 表引文回验：自称的「第N题标准」必须与答案表原文对得上，对不上转人工（防查错行/抄错字反判学生）
    def _force_pending(note: str) -> None:
        if decision["correctResult"] == PENDING:
            return
        decision["correctResult"] = PENDING
        decision["result"] = RESULT_TEXT[PENDING]
        decision["partial_ratio"] = None
        base = str(decision.get("reason") or "").strip()
        full = f"{note}，待人工确认"
        decision["reason"] = f"{full}；{base}" if base else full
        decision["analysis"] = decision["reason"]

    if answer_table_text:
        mismatch = _table_quote_mismatch(
            str(data.get("standard_quote") or ""),
            _to_int(data.get("located_no"), 0) or None,
            answer_table_text,
        )
        if mismatch:
            _force_pending(mismatch)
    # 选项字母矛盾闸：字母一致却判错/不一致却判对 → 转人工
    # 有表时只信 standard_quote（机器盲配文本不可作字母依据）；无表时才用 standard_answer_text
    quote_for_letter = str(data.get("standard_quote") or "").strip()
    if not quote_for_letter and not answer_table_text:
        quote_for_letter = decision.get("standard_answer_text") or ""
    letter_conflict = _objective_letter_conflict(
        decision.get("transcription") or "",
        quote_for_letter,
        decision["correctResult"],
    )
    if letter_conflict:
        _force_pending(letter_conflict)
    # 多选题确定性字母集合判定（压过 VL 的宽容/误判，与答案表链同规则）：
    # 选错任意一个=错；只少选=半对（按选对比例）；全同=对。已转人工的不覆盖。
    ms = _multi_select_letter_rule(decision.get("transcription") or "", quote_for_letter)
    if ms and decision["correctResult"] != PENDING:
        ms_code, ms_ratio = ms
        decision["correctResult"] = ms_code
        decision["result"] = RESULT_TEXT[ms_code]
        decision["partial_ratio"] = ms_ratio
        ms_note = {CORRECT: "多选选项集合与标准一致", WRONG: "多选含错误选项", PARTIAL: "多选少选"}[ms_code]
        decision["reason"] = f"{ms_note}，按选项集合判定"
        decision["analysis"] = decision["reason"]
    _apply_conclusion_guard(decision)
    return _apply_read_guard(decision)


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


def _task_payload(task: VlmGradingTask, *, has_table: bool = False) -> dict:
    # 答案表在场时机器配对（位置盲猜）不再进元数据当「标准答案」：
    # folder8 实测模型会把 standard_answer_text_is_ground_truth 当系统定义，压过题号对照。
    standard_text = None if has_table else _standard_answer_text(task)
    payload = {
        "question_id": task.task_id,
        "sub_index": task.sub_index,
        "grading_policy_hint": "auto_detect_from_images" if has_table else _grading_policy_hint(task),
        "standard_answer_text_is_ground_truth": bool(standard_text),
        "standard_answer_text": standard_text,
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
    if has_table:
        payload["code_pairing_hint_unreliable"] = True
    return payload


_TRANSCRIPTION_RULE = (
    "TRANSCRIPTION FIRST: before judging, transcribe ONLY the student's handwritten answer from the "
    "red slot of image 2 into \"transcription\", character by character. Mark every uncertain single "
    "character as [?], every character with two plausible readings as [字1|字2], and a totally "
    "unreadable segment as [??]. Never guess a blurry character, never summarize, never complete the "
    "handwriting using the standard answer. Then set read_confidence: 0.9+ only when every transcribed "
    "character is clearly readable, 0.5-0.8 when some characters are uncertain, below 0.5 when large "
    "parts are unreadable.\n"
)


def _authority_rule(has_text: bool, *, has_table: bool = False) -> str:
    if has_table:
        return (
            "- STANDARD-ANSWER TEXT AUTHORITY: the 【参考答案完整表】 text is the sole ground truth. "
            "For each red slot, first locate the printed question number that governs its answer blank: "
            "the number is printed at the start of the question (often above or to the left of the blank, "
            "not necessarily beside the red rectangle), so scan the slot's full context in image 2. "
            "Then judge that slot ONLY against the 第N题 entry of the number N you located. "
            "The backend's machine pairing (【本槽代码初步对照】 and any metadata) is a blind position guess "
            "and is often wrong: never judge by it, never treat it as the demanded answer, and when it "
            "disagrees with the number you located it is simply wrong. "
            "If one printed question has several blanks or sub-parts, each red slot holds just one blank: "
            "judge it against only that blank's part of the table entry (for example 第8题(2)的后半句), and "
            "writing that blank's content correctly is 对 even though the entry lists more. "
            "Choose the blank by where the red rectangle sits among the printed blanks; when you cannot be "
            "certain which blank it is, or when the transcription matches a different demanded phrase of "
            "the same entry, judge by CONTENT instead of position: correctly writing any demanded phrase "
            "of that entry is 对, and a sibling blank's order mix-up must never cause a wrong verdict. "
            "If you truly cannot locate any printed number for a slot and cannot tell which question its "
            "blank belongs to, return correctResult 5 with reason starting 无法定位题号 — never guess a "
            "pairing, and never use 5 for merely hard-to-read handwriting (transcribe it with [?] marks "
            "and judge it). "
            "Option letters are case-insensitive: b is B. "
            "For fill-in-the-blank phrase recall (默写/填空), only the demanded phrase's characters matter: "
            "punctuation marks (，。、；：？！?!,.;:) and spacing between characters are never part of the "
            "demanded answer and never cause a wrong verdict. "
            "Match this slot's transcription against EVERY demanded phrase of the located entry: if it "
            "equals one or more demanded phrases (ignoring punctuation and spacing), or contains one full "
            "demanded phrase together with another sibling blank's phrase (even a misspelled or partial "
            "attempt at that sibling, or sibling content in the same area), it is 对. Judge it 错 only "
            "when the transcription matches none of the demanded phrases, contains wrong characters "
            "inside a demanded phrase, or adds unrelated extra characters that are not sibling blanks. "
            "Never use other slots' transcriptions or verdicts to decide this slot. "
            "If the writing is an incomplete fragment of exactly one demanded phrase: when the pen "
            "strokes visibly continue past the red rectangle edge (the crop cut the writing off), return "
            "correctResult 5 with reason starting 框被截断 — a crop defect must never fail the student; "
            "when the writing clearly stops inside the area, it is 错 (默写 must be complete). "
            "When the demanded answer is a descriptive phrase or sentence (景物、气氛、情感、原因、作用、"
            "翻译、赏析) rather than a fixed term, option letter, or number, apply SUBJECTIVE SEMANTIC: "
            "accept synonyms and alternate names for the same thing (for example 杜鹃 for 子规) and never "
            "fail correct content over terminology variants. "
            "Never replace, correct, extend, or second-guess the table using your own solution or outside "
            "knowledge. If a table entry is missing (marked 〈文本缺失〉), image 1 is the sole ground truth "
            "for that slot only.\n"
        )
    if has_text:
        return (
            "- STANDARD-ANSWER TEXT AUTHORITY: the 【标准答案】 text is the sole ground truth. "
            "Never replace, correct, extend, or second-guess it using your own solution or outside "
            "knowledge. If a slot's text is missing (marked 〈文本缺失〉), image 1 is the sole ground "
            "truth for that slot only.\n"
        )
    return (
        "- STANDARD-ANSWER AUTHORITY: image 1 is the sole ground truth. Never replace, correct, extend, "
        "or second-guess its answer using your own solution or outside knowledge.\n"
    )


def _build_slot_qwen_prompt(
    task: VlmGradingTask,
    student_name: str,
    family_hint: str = "",
    answer_table_text: str = "",
) -> str:
    policy_hint = "" if answer_table_text else _grading_policy_hint(task)
    standard_text = _standard_answer_text(task)
    payload = {"grading_task": _task_payload(task, has_table=bool(answer_table_text))}
    authority_rule = _authority_rule(bool(standard_text) or bool(answer_table_text), has_table=bool(answer_table_text))
    objective_rule = (
        "- OBJECTIVE STRICT: the student's selected option set, true/false value, fixed answer, matching, "
        "or ordering must be exactly the same as the highlighted standard answer. Any different, missing, "
        "or extra option/value is wrong. Do not accept alternative answers, synonyms, partial correctness, "
        "MULTI-SELECT EXCEPTION (standard answer has 2+ option letters like AD): if the student's letter set "
        "equals the standard set, mark 对 (correctResult=1); if ANY picked letter is outside the standard set, "
        "mark 错 (correctResult=2) with NO credit even when some correct letters were also picked; if picks are "
        "a non-empty subset of the standard set (only missing, no wrong picks), mark 半对 (correctResult=4) "
        "with partial_ratio = (correct letters picked) / (total standard letters). "
        "Missing-only is NOT wrong for multi-select. "
        "or a plausible answer that differs from the standard answer. Compare answer identity rather than handwriting style.\n"
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
            "against the standard answer identity given above.\n"
        )
    elif policy_hint == "subjective_semantic":
        policy_instruction = (
            "Backend metadata identifies this as a SUBJECTIVE question. Apply SUBJECTIVE SEMANTIC policy."
        )
        policy_rules = authority_rule + subjective_rule
        comparison_rule = (
            "3. This is a subjective question. Judge semantic equivalence against the core meaning and required "
            "points of the standard answer given above, without requiring identical wording.\n"
        )
    else:
        if answer_table_text:
            policy_instruction = (
                "First classify the visible question from image 1 and the printed question number you "
                "located: its 【参考答案完整表】 entry tells you the type. For choice, true/false, "
                "fixed-answer fill-in, matching, ordering, or another objectively scored item, "
                "Apply OBJECTIVE STRICT policy. Otherwise Apply SUBJECTIVE SEMANTIC policy."
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
    table_block = ""
    standard_heading = "【标准答案（标准答案识别文本，唯一判分依据）】：\n"
    if answer_table_text:
        table_block = (
            "【参考答案完整表（标准答案识别文本；先认图像2红框旁的印刷题号，再对照本表判分）】\n"
            + answer_table_text
            + "\n\n"
        )
        standard_heading = (
            "【本槽代码初步对照（禁止作为判分依据：机器按位置盲猜，经常错误；"
            "以红框所属印刷题号在完整表查到的答案为准）】：\n"
        )
        standard_text_block = (
            standard_heading + "按该空所属印刷题号查【参考答案完整表】判分（〈文本缺失〉的槽以 image 1 对应红框为准）。\n\n"
        )
    else:
        standard_text_block = (
            standard_heading
            + (standard_text if standard_text else "〈文本缺失〉以 image 1 红框内标准答案为准")
            + "\n\n"
        )
    code5_note = (
        "Use 5 (待确认) only per the authority rule: when the governing printed question number cannot be "
        "located (reason starting 无法定位题号), or when the crop clearly truncates the writing (reason "
        "starting 框被截断); never use 5 for hard-to-read handwriting.\n"
        if answer_table_text
        else ""
    )
    quote_note = (
        "Also return located_no and standard_quote: located_no is the printed question number you located "
        "(an integer), and standard_quote is the VERBATIM 【参考答案完整表】 line for that number which you "
        "judged against, including its 第N题 prefix. Copy every character exactly; never correct, reword, "
        "or borrow another question's line. The backend checks the quote against the table entry of "
        "located_no and routes a mismatch to human review as 待确认.\n"
        if answer_table_text
        else ""
    )
    comparison_target = (
        "the 【参考答案完整表】 entry for the printed question number that governs the slot"
        if answer_table_text
        else "the standard answer given above"
    )
    return "".join(
        [
            "You are a strict school-exam grader. The user content contains exactly two images in order: ",
            "image 1 is the standard-answer context packet and image 2 is the student-answer context packet. ",
            "A packet may stack several disjoint regions belonging to the same question. The red rectangle ",
            "marks the answer region. Grade only the corresponding answer in that region, while using every ",
            "stacked question/diagram region as context. Do not grade another answer in either packet.\n\n",
            table_block,
            standard_text_block,
            "The two highlighted rectangles are one corresponding answer slot. Understand the question and ",
            "standard answer, then compare only the highlighted student answer in image 2. ",
            f"The student paper is: {student_name}.\n\n",
            policy_instruction,
            "\n\nMandatory grading policies:\n",
            policy_rules,
            _TRANSCRIPTION_RULE,
            "\nRules:\n",
            "1. Return question_id exactly as supplied. It is a backend task id, not the printed question number.\n",
            "2. correctResult must be 1 for correct, 2 for wrong, 3 for blank/unanswered, or 4 for partially correct (半对). ",
            "A blank highlighted student area is 3. When the answer is partially correct (some required points right, "
            "some missing or wrong), use 4 and set partial_ratio to the fraction of full credit earned (0 to 1, e.g. 0.6).\n",
            "   CRITICAL — image 1 is the STANDARD-ANSWER packet: the teacher usually wrote the standard answers on "
            "the SAME blanks. NEVER copy image 1's text into \"transcription\" and never treat image 1's writing as "
            "student work. Judge ONLY what is handwritten in image 2's red rectangle. If the student rectangle shows "
            "no handwriting (an empty printed line or empty blank), correctResult must be 3 even when the corresponding "
            "image 1 rectangle is filled with the standard answer.\n",
            code5_note,
            quote_note,
            comparison_rule,
            f"4. Judge strictly by comparing \"transcription\" against {comparison_target}. Hard-to-read "
            "handwriting must be marked in the transcription and still get your best judgment; the backend routes "
            "uncertain transcriptions to human review automatically. Never force a wrong verdict just because the "
            "handwriting is ugly, and never invent an answer you could not read.\n",
            "5. Write reason and analysis in Chinese. Keep a correct-answer analysis brief; explain the error ",
            "and the correct approach for a wrong answer.\n",
            "6. In reason and analysis, use plain Chinese text and Unicode math symbols only. Do not use TeX, "
            "LaTeX, Markdown, dollar-sign delimiters, caret exponent notation, or any backslash character. "
            "Never use the ASCII double-quote character inside text fields; write 「」 instead. "
            "For example, write “5³ = 5 × 5 × 5 = 125”, “3⁄8”, “√2”, “x²”, “a₁”, “≤”, and “÷”.\n",
            "7. Do not invent or change any coordinate. Return exactly one valid JSON object with no Markdown "
            "and no extra fields. Every backslash required by JSON itself must be escaped correctly.\n\n",
            "JSON schema:\n",
            (
                '{"question_id":1,"correctResult":1,"result":"\\u5bf9","transcription":"...","read_confidence":0.9,'
                '"located_no":1,"standard_quote":"第1题：...","reason":"...","analysis":"...",'
                '"confidence":0.0,"partial_ratio":null}\n\n'
                if answer_table_text
                else '{"question_id":1,"correctResult":1,"result":"\\u5bf9","transcription":"...","read_confidence":0.9,'
                '"reason":"...","analysis":"...","confidence":0.0,"partial_ratio":null}\n\n'
            ),
            "Task metadata (coordinates are read-only and the red rectangles are authoritative):\n",
            json.dumps(payload, ensure_ascii=False),
            f"\n\nSUBJECT-FAMILY HINT (科目族提示): {family_hint}" if family_hint else "",
        ]
    )


def _call_qwen_for_question(
    client,
    model: str,
    task: VlmGradingTask,
    std_image_url: str,
    stu_image_url: str,
    student_name: str,
    family_hint: str = "",
    answer_table_text: str = "",
) -> dict:
    prompt = _build_slot_qwen_prompt(
        task, student_name, family_hint=family_hint, answer_table_text=answer_table_text
    )
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
    return _normalize_decision(
        _json_object_from_text(content),
        task.task_id,
        standard_answer_text=_standard_answer_text(task),
        answer_table_text=answer_table_text,
    )


def _slot_key(task: VlmGradingTask) -> str:
    return f"{task.student_question.display_index}_{task.sub_index}"


def _slot_visual_order_key(task: VlmGradingTask) -> tuple[int, int]:
    """批量槽位按学生卷红框视觉顺序（先上后下、先左后右）排列。

    模型在多槽批里按红框视觉阅读顺序读内容，再硬填进槽键列表；列表顺序
    与红框视觉顺序一致时，它按位置猜也能猜对（串槽修复的一半）。
    """
    box = task.student_answer_bbox or [0, 0, 0, 0]
    try:
        return (int(box[1]), int(box[0]))
    except Exception:
        return (0, 0)


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
            slots=sorted(groups[key], key=_slot_visual_order_key),
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
        if box in projected:
            continue
        # 特写段向上多留一条抬头带：槽键标签画在红框上方时不压手写首字
        try:
            x1, y1, x2, y2 = [int(v) for v in box]
            projected.append([x1, max(0, y1 - 40), x2, y2])
        except Exception:
            projected.append(box)
    return projected


def _batch_task_payload(batch: VlmQuestionBatchTask, *, has_table: bool = False) -> dict:
    payload = {
        "question_id": batch.batch_id,
        "parent_question_index": batch.student_question.display_index,
        "standard_answer_text_is_ground_truth": not has_table,
        "slots": [
            {
                "slot_key": _slot_key(task),
                "sub_index": task.sub_index,
                "is_answer_slot": task.is_answer_slot,
                "anchor_source": task.anchor_source,
                # 答案表在场时不给机器配对文本（防模型照错配对判分）：判分依据只在完整表
                "standard_answer_text": None if has_table else _standard_answer_text(task),
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
    if has_table:
        payload["code_pairing_hint_unreliable"] = True
    return payload


def _build_batch_qwen_prompt(
    batch: VlmQuestionBatchTask,
    student_name: str,
    family_hint: str = "",
    answer_table_text: str = "",
) -> str:
    policy_hint = "" if answer_table_text else _grading_policy_hint(batch.slots[0])
    payload = {"grading_task": _batch_task_payload(batch, has_table=bool(answer_table_text))}
    authority_rule = _authority_rule(True, has_table=bool(answer_table_text))
    objective_rule = (
        "- OBJECTIVE STRICT: every student's selected option, true/false value, fixed answer, matching, "
        "or ordering must be exactly the same as the corresponding labeled slot standard answer. Any different, "
        "missing, or extra option/value is wrong.\n"
        "MULTI-SELECT EXCEPTION (standard answer has 2+ option letters like AD): if the student's letter set "
        "equals the standard set, mark 对 (correctResult=1); if ANY picked letter is outside the standard set, "
        "mark 错 (correctResult=2) with NO credit even when some correct letters were also picked; if picks are "
        "a non-empty subset of the standard set (only missing, no wrong picks), mark 半对 (correctResult=4) "
        "with partial_ratio = (correct letters picked) / (total standard letters). "
        "Missing-only is NOT wrong for multi-select.\n"
    )
    subjective_rule = (
        "- SUBJECTIVE SEMANTIC: understand the standard answer's conclusion, key ideas, reasoning, and "
        "required points. Accept different wording only when the essential meaning matches. When only "
        "part of the required points are met, use 4 (半对) and set partial_ratio (0 to 1).\n"
    )
    if policy_hint == "objective_strict":
        policy_instruction = "This is an OBJECTIVE question. Apply OBJECTIVE STRICT policy."
        policy_rules = authority_rule + objective_rule
    elif policy_hint == "subjective_semantic":
        policy_instruction = "This is a SUBJECTIVE question. Apply SUBJECTIVE SEMANTIC policy."
        policy_rules = authority_rule + subjective_rule
    else:
        if answer_table_text:
            policy_instruction = (
                "First classify the visible question from image 1 and the printed question number you "
                "located: its 【参考答案完整表】 entry tells you the type. For choice, true/false, "
                "fixed-answer fill-in, matching, ordering, or another objectively scored item, "
                "Apply OBJECTIVE STRICT policy. Otherwise Apply SUBJECTIVE SEMANTIC policy."
            )
        else:
            policy_instruction = (
                "Classify the visible question first. Use OBJECTIVE STRICT for fixed-answer items and "
                "SUBJECTIVE SEMANTIC for open responses."
            )
        policy_rules = authority_rule + objective_rule + subjective_rule
    expected_slots = ", ".join(_slot_key(task) for task in batch.slots)
    if answer_table_text:
        # 答案表在场：每槽不再给机器配对文本（folder8 实测模型会照错配对判分）
        standard_text_lines = "".join(
            f"- 作答区 {_slot_key(task)}：按该空所属印刷题号查【参考答案完整表】判分"
            "（回填 located_no，且把所查行原文一字不差照抄进 standard_quote）\n"
            for task in batch.slots
        )
    else:
        standard_text_lines = "".join(
            f"- 作答区 {_slot_key(task)}：{_standard_answer_text(task) or '〈文本缺失〉'}\n"
            for task in batch.slots
        )
    table_block = ""
    standard_heading = "【标准答案识别文本（唯一判分依据；〈文本缺失〉的槽以 image 1 对应红框为准）】\n"
    if answer_table_text:
        table_block = (
            "【参考答案完整表（标准答案识别文本；先认图像2红框旁的印刷题号，再对照本表判分）】\n"
            + answer_table_text
            + "\n\n"
        )
        standard_heading = (
            "【本槽代码初步对照（禁止作为判分依据：机器按位置盲猜，经常错误；"
            "以红框所属印刷题号在完整表查到的答案为准；〈文本缺失〉的槽以 image 1 对应红框为准）】\n"
        )
    code5_note = (
        "Use 5 (待确认) only per the authority rule: when the governing printed question number cannot be "
        "located (reason starting 无法定位题号), or when the crop clearly truncates the writing (reason "
        "starting 框被截断); never use 5 for hard-to-read handwriting.\n"
        if answer_table_text
        else ""
    )
    quote_note = (
        "Also return located_no and standard_quote for every slot: located_no is the printed question "
        "number you located (an integer), and standard_quote is the VERBATIM 【参考答案完整表】 line for "
        "that number which you judged against, including its 第N题 prefix. Copy every character exactly; "
        "never correct, reword, or borrow another question's line. The backend checks the quote against "
        "the table entry of located_no and routes a mismatch to human review as 待确认.\n"
        if answer_table_text
        else ""
    )
    comparison_target = (
        "the 【参考答案完整表】 entry for the printed question number that governs that slot's blank"
        if answer_table_text
        else "its standard answer above"
    )
    if answer_table_text:
        schema_line = (
            '{"question_id":1,"slots":[{"slot_key":"1_1","correctResult":1,"result":"对","transcription":"...",'
            '"read_confidence":0.9,"located_no":1,"standard_quote":"第1题：...","reason":"...","analysis":"...",'
            '"confidence":0.0,"partial_ratio":null}]}'
        )
    else:
        schema_line = (
            '{"question_id":1,"slots":[{"slot_key":"1_1","correctResult":1,"result":"对","transcription":"...",'
            '"read_confidence":0.9,"reason":"...","analysis":"...","confidence":0.0,"partial_ratio":null}]}'
        )
    return "".join(
        [
            "You are a strict school-exam grader. The user content contains exactly two images in order: ",
            "image 1 is the standard-answer packet and image 2 is the student-answer packet. ",
            "Each packet contains one parent question and all of its answer slots. ",
            "Every answer slot has a visible red rectangle and a large red label on a white background such as 1_1 or 1_2. ",
            "Bind by label only: a rectangle's slot key is the large label text printed on the white tag at its "
            "top-left corner. Never bind a rectangle to a slot key by its position, by top-to-bottom order in "
            "the image, or by the order of slot keys listed below. ",
            "Compare every labeled slot independently; do not let one slot's answer affect another slot.\n\n",
            table_block,
            standard_heading,
            standard_text_lines,
            "\n",
            f"The student paper is: {student_name}.\n",
            f"Expected slot keys, which must all be returned exactly once: {expected_slots} "
            "(this list order is not the image order; bind each returned slot to the label on its red rectangle)\n\n",
            policy_instruction,
            "\n\nMandatory grading policies:\n",
            policy_rules,
            _TRANSCRIPTION_RULE.replace(
                "the red slot of image 2", "each labeled red slot of image 2"
            ).replace(
                "into \"transcription\"",
                "into that slot's \"transcription\"",
            ),
            "\nRules:\n",
            f"1. Return question_id exactly as supplied: {batch.batch_id}. It identifies this parent-question batch.\n",
            "2. Return one item in slots for every expected slot key. Do not omit, merge, reorder, duplicate, "
            "or invent a slot key.\n",
            "3. Each slot correctResult must be 1 for correct, 2 for wrong, 3 for blank/unanswered, or 4 for "
            "partially correct (半对, with partial_ratio 0 to 1). A blank highlighted student slot is 3.\n",
            "   CRITICAL — image 1 is the STANDARD-ANSWER packet: the teacher usually wrote the standard answers on "
            "the SAME blanks. NEVER copy image 1's text into a slot's \"transcription\" and never treat image 1's "
            "writing as student work. Judge ONLY what is handwritten in that slot's image 2 rectangle. If a student "
            "rectangle shows no handwriting (an empty printed line or empty blank), its correctResult must be 3 even "
            "when the corresponding image 1 rectangle is filled with the standard answer.\n",
            code5_note,
            quote_note,
            "4. Use only the corresponding labeled red slot in image 1 and image 2. Do not grade another slot. "
            "Read the large label beside each red rectangle to know its slot key; never assign results by order.\n",
            f"5. Judge each slot strictly by comparing its \"transcription\" against {comparison_target}. "
            "Hard-to-read handwriting must be marked in the transcription and still get your best judgment; the "
            "backend routes uncertain transcriptions to human review automatically. Never force a wrong verdict "
            "just because the handwriting is ugly.\n",
            "6. Write reason and analysis in Chinese. Keep correct-slot analysis brief; explain the error "
            "and correct approach for a wrong slot.\n",
            "7. Use plain Chinese text and Unicode math symbols only. Do not use TeX, LaTeX, Markdown, "
            "dollar-sign delimiters, caret exponent notation, or backslash characters. "
            "Never use the ASCII double-quote character inside text fields; write 「」 instead.\n",
            "8. Do not return coordinates or extra fields. Return exactly one valid JSON object with this schema:\n",
            schema_line,
            "\n\n",
            "Task metadata is read-only; image labels and red rectangles are authoritative:\n",
            json.dumps(payload, ensure_ascii=False),
            f"\n\nSUBJECT-FAMILY HINT (科目族提示): {family_hint}" if family_hint else "",
        ]
    )


def _normalize_batch_decision(
    data: dict,
    batch: VlmQuestionBatchTask,
    *,
    answer_table_text: str = "",
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
        normalized[task.task_id] = _normalize_decision(
            decision,
            task.task_id,
            standard_answer_text=_standard_answer_text(task),
            answer_table_text=answer_table_text,
        )
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
    family_hint: str = "",
    answer_table_text: str = "",
) -> dict[int, dict]:
    prompt = _build_batch_qwen_prompt(
        batch, student_name, family_hint=family_hint, answer_table_text=answer_table_text
    )
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
    return _normalize_batch_decision(
        _json_object_from_text(content), batch, answer_table_text=answer_table_text
    )


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


def _ink_coverage_inside_bbox(
    projected_bbox: list[int], ink_bbox: list[int]
) -> float:
    """墨迹有多大比例落在投影答题区内（按墨迹自身面积算）。

    用「重叠/小框」会被大墨迹骗过：一个擦着答题区边的草稿/邻空答案，
    交集相对小投影框就是 1.0。按墨迹自身面积算，只有真正写在答题区里的
    墨迹（覆盖率高）才算该空的作答。
    """
    intersection_width = max(
        0, min(projected_bbox[2], ink_bbox[2]) - max(projected_bbox[0], ink_bbox[0])
    )
    intersection_height = max(
        0, min(projected_bbox[3], ink_bbox[3]) - max(projected_bbox[1], ink_bbox[1])
    )
    intersection = intersection_width * intersection_height
    if intersection <= 0:
        return 0.0
    ink_area = max(1, (ink_bbox[2] - ink_bbox[0]) * (ink_bbox[3] - ink_bbox[1]))
    return intersection / ink_area


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


def _question_regions_comparable(
    source_question_bbox: list[int],
    target_question_bbox: list[int],
    source_size: tuple[int, int],
    target_size: tuple[int, int],
) -> bool:
    """学生题区与标准题区是否“装着同一段内容”（形状/占比都接近）。

    切题把两题并成一块时题区比例会走形，相对位置投影随之爆炸，
    这种情况要退回按整页归一化的位置。
    """
    sx1, sy1, sx2, sy2 = source_question_bbox
    tx1, ty1, tx2, ty2 = target_question_bbox
    source_w, source_h = sx2 - sx1, sy2 - sy1
    target_w, target_h = tx2 - tx1, ty2 - ty1
    if min(source_w, source_h, target_w, target_h) <= 0:
        return False
    aspect_ratio = (target_w / target_h) / (source_w / source_h)
    if not 0.67 <= aspect_ratio <= 1.5:
        return False
    source_w_ratio = source_w / max(1, source_size[0])
    source_h_ratio = source_h / max(1, source_size[1])
    target_w_ratio = target_w / max(1, target_size[0])
    target_h_ratio = target_h / max(1, target_size[1])
    source_area = max(1e-6, source_w_ratio * source_h_ratio)
    target_area = max(1e-6, target_w_ratio * target_h_ratio)
    area_ratio = target_area / source_area
    return 0.4 <= area_ratio <= 2.5


def _projection_within_sane_scale(
    source_bbox: list[int],
    projected_bbox: list[int],
    source_size: tuple[int, int],
    target_size: tuple[int, int],
) -> bool:
    """投影框不能比按页缩放的原框大太多/拉太扁，否则是切题错位拉爆出来的巨框。"""
    scaled = _scale_bbox(source_bbox, source_size, target_size)
    scaled_w = max(1, scaled[2] - scaled[0])
    scaled_h = max(1, scaled[3] - scaled[1])
    projected_w = max(1, projected_bbox[2] - projected_bbox[0])
    projected_h = max(1, projected_bbox[3] - projected_bbox[1])
    aspect_ratio = (projected_w / projected_h) / (scaled_w / scaled_h)
    if not 0.45 <= aspect_ratio <= 2.2:
        return False
    area_ratio = (projected_w * projected_h) / (scaled_w * scaled_h)
    return 0.25 <= area_ratio <= 4.0


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
    expected_no_by_template: Optional[dict[int, Optional[str]]] = None,
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

    def assign(
        offset: tuple[float, float],
        max_distance: float,
        *,
        same_no_only: bool = False,
        reserved_templates: Optional[set[int]] = None,
        reserved_papers: Optional[set[int]] = None,
    ):
        dx, dy = offset
        candidates: list[tuple[float, int, int]] = []
        for template_index, template_slot in enumerate(slot_template):
            if reserved_templates and template_index in reserved_templates:
                continue
            expected_no = (expected_no_by_template or {}).get(template_index)
            shifted = tuple(
                value + (dx if index % 2 == 0 else dy)
                for index, value in enumerate(template_slot.normalized_bbox)
            )
            for paper_index, (question, _sub_index, _bbox, normalized) in enumerate(paper_slots):
                if reserved_papers and paper_index in reserved_papers:
                    continue
                if same_no_only and (not expected_no or question.printed_no != expected_no):
                    # 题号优先通道：只接受题号一致的候选（宁缺勿串，缺口留给几何兜底）
                    continue
                candidates.append(
                    (
                        _normalized_bbox_distance(shifted, normalized),
                        template_index,
                        paper_index,
                    )
                )
        candidates.sort(key=lambda item: item[0])
        used_template: set[int] = set(reserved_templates or ())
        used_paper: set[int] = set(reserved_papers or ())
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
    # 题号优先：先只认题号一致的配对（跨卷切题切分不一致时几何会错位）。
    # 同号配对不受几何阈值约束（版式/切题位移再大，题号一致就是同一题），
    # 只留 0.35 页面尺寸的防呆上限；剩余槽再几何兜底。
    assigned: dict[int, tuple[int, float]] = {}
    if expected_no_by_template:
        no_match_distance = _slot_match_threshold(
            "REFERENCE_VLM_TEMPLATE_NO_MATCH_DISTANCE", 0.35
        )
        assigned.update(assign(offset, no_match_distance, same_no_only=True))
        extra = assign(
            offset,
            final_distance,
            reserved_templates=set(assigned),
            reserved_papers={paper_index for paper_index, _distance in assigned.values()},
        )
        assigned.update(extra)
    else:
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


def _rebind_question_by_slot_bbox(
    questions: list[VlmQuestion],
    current: VlmQuestion,
    slot_bbox: Optional[list[int]],
    image_size: tuple[int, int],
) -> VlmQuestion:
    """槽框物理归属校验：中心不在本题题区、却落在唯一别的题区里 → 换绑那道题。

    1019 语文审计（红框 4₂ 落在第 5 题括号内却按第 4 题配答案/投影）：
    物理位置是权威，题号标签会错。只做「不在本区 ∩ 恰在唯一别区」的铁证
    换绑；两题区重叠、都不覆盖、题区缺失一律保持原样（宁缺勿乱）。
    """
    if not slot_bbox or len(slot_bbox) < 4 or not current.question_bbox:
        return current
    cx = (_to_float(slot_bbox[0]) + _to_float(slot_bbox[2])) / 2.0
    cy = (_to_float(slot_bbox[1]) + _to_float(slot_bbox[3])) / 2.0

    def _inside(question: VlmQuestion) -> bool:
        box = question.question_bbox or []
        if len(box) < 4:
            return False
        x1, y1, x2, y2 = (_to_float(v) for v in box[:4])
        return x1 <= cx <= x2 and y1 <= cy <= y2

    if _inside(current):
        return current
    holders = [
        question
        for question in questions
        if question is not current and _inside(question)
    ]
    if len(holders) == 1:
        return holders[0]
    return current


def _build_template_grading_tasks(
    standard_questions: list[VlmQuestion],
    student_questions: list[VlmQuestion],
    standard_size: tuple[int, int],
    student_size: tuple[int, int],
    slot_template: list[VlmSlotTemplate],
) -> list[VlmGradingTask]:
    # 题号优先：模板槽的印刷题号取标准卷题（question_index=标准卷 display_index），
    # 两张卷的配对都按「同题号优先」走，几何只做兜底。
    expected_no_by_template: dict[int, Optional[str]] = {}
    for template_index, template_slot in enumerate(slot_template):
        source_question = next(
            (
                question
                for question in standard_questions
                if question.display_index == template_slot.question_index
            ),
            None,
        )
        expected_no_by_template[template_index] = (
            source_question.printed_no if source_question is not None else None
        )
    standard_matches, standard_offset, _standard_reliable = _match_template_to_paper(
        slot_template,
        standard_questions,
        standard_size,
        expected_no_by_template,
    )
    student_matches, student_offset, _student_registration_reliable = _match_template_to_paper(
        slot_template,
        student_questions,
        student_size,
        expected_no_by_template,
    )
    specs: list[dict[str, Any]] = []
    used_student_slots: set[tuple[int, int]] = set()
    reserved_student_slots = {
        (id(match[0]), match[1]) for match in student_matches.values()
    }
    # 墨迹只有实质性落在标准答题区（投影框）内才算该空的作答：
    # 草稿在空白处、印刷词库在题干上，距离再近也不许替换/扩张红框。
    overlap_threshold = min(
        1.0,
        max(
            0.05,
            _to_float(
                os.environ.get("REFERENCE_VLM_DIRECT_SLOT_OVERLAP_RATIO"),
                0.35,
            ),
        ),
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
                standard_question = _question_for_no_or_bbox(
                    standard_questions,
                    expected_no_by_template.get(template_index),
                    standard_bbox,
                    standard_size,
                )
        if standard_question is None:
            continue

        # 槽框物理归属校验（1019：4₂ 标签挂第 4 题、框却在第 5 题括号内）：
        # 换绑后题号/答案行/相对投影全跟着物理位置走，不再信错挂的题号标签。
        standard_question = _rebind_question_by_slot_bbox(
            standard_questions,
            standard_question,
            standard_bbox,
            standard_size,
        )

        # 整页归一化落点（带批改配准偏移）：标准答题区在学生卷上的直接投影，
        # 也是绑题和相对投影失真时的兜底红框。
        normalized_slot_bbox = _bbox_from_normalized(
            template_slot.normalized_bbox, student_size, offset=student_offset
        )
        recovered_student_slot: Optional[tuple[VlmQuestion, int, list[int]]] = None
        if student_match:
            student_bbox = student_match[2]
            student_question = student_match[0]
        else:
            student_question = _question_for_slot_box(
                student_questions,
                standard_question.printed_no,
                normalized_slot_bbox,
                student_size,
            )
            if student_question is None:
                continue

        relative_projection = _project_bbox_between_question_regions(
            standard_bbox,
            standard_question.question_bbox,
            student_question.question_bbox,
            student_size,
        )
        if (
            relative_projection
            and _question_regions_comparable(
                standard_question.question_bbox,
                student_question.question_bbox,
                standard_size,
                student_size,
            )
            and _projection_within_sane_scale(
                standard_bbox, relative_projection, standard_size, student_size
            )
        ):
            projected_student_bbox = relative_projection
        else:
            projected_student_bbox = normalized_slot_bbox
        if not student_match:
            student_bbox = projected_student_bbox

        if not student_match:
            # 判定口径 = 墨迹自身有多大比例落在投影答题区内（覆盖率），
            # 不是「重叠/小框」：大草稿擦到小投影也会拿 1.0。
            # 取覆盖率最高的墨迹；同覆盖率才比中心距离。
            direct_candidates = sorted(
                (
                    (
                        -_ink_coverage_inside_bbox(projected_student_bbox, direct_bbox),
                        _normalized_center_distance(
                            projected_student_bbox,
                            student_size,
                            direct_bbox,
                            student_size,
                        ),
                        owner_question,
                        sub_index,
                        direct_bbox,
                    )
                    for owner_question in student_questions
                    for sub_index, direct_bbox in enumerate(
                        owner_question.answer_bboxes, start=1
                    )
                    if (id(owner_question), sub_index) not in used_student_slots
                    and (id(owner_question), sub_index) not in reserved_student_slots
                    and _ink_coverage_inside_bbox(projected_student_bbox, direct_bbox)
                    >= overlap_threshold
                ),
                key=lambda item: (item[0], item[1]),
            )
            if direct_candidates:
                _neg_coverage, _distance, owner_question, sub_index, direct_bbox = (
                    direct_candidates[0]
                )
                student_bbox = direct_bbox
                recovered_student_slot = (owner_question, sub_index, direct_bbox)

        if student_match:
            used_student_slots.add((id(student_match[0]), student_match[1]))
            anchor_source = "baidu_direct"
            has_mark_anchor = True
            has_handwriting_location = True
        elif recovered_student_slot:
            owner_question, sub_index, _direct_bbox = recovered_student_slot
            used_student_slots.add((id(owner_question), sub_index))
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
    # 只收实质性落在投影答题区内的墨迹（覆盖率≥overlap_threshold）：
    # 草稿/词库/邻空答案只要不是真写在该空里就不并入红框。
    recovered_by_spec: dict[int, list[list[int]]] = {}
    for student_question in student_questions:
        for student_sub_index, student_bbox in enumerate(
            student_question.answer_bboxes, start=1
        ):
            if (id(student_question), student_sub_index) in used_student_slots:
                continue
            candidates: list[tuple[float, float, int]] = []
            for spec_index, spec in enumerate(specs):
                projected_bbox = spec["projected_student_bbox"]
                overlap = _ink_coverage_inside_bbox(
                    projected_bbox, student_bbox
                )
                if overlap < overlap_threshold:
                    continue
                distance = _normalized_center_distance(
                    projected_bbox,
                    student_size,
                    student_bbox,
                    student_size,
                )
                candidates.append((-overlap, distance, spec_index))
            if not candidates:
                continue
            candidates.sort()
            spec_index = candidates[0][2]
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
        standard_question = _question_for_no_or_bbox(
            standard_questions,
            student_question.printed_no,
            mapped_standard_bbox,
            standard_size,
        )
        if standard_question is None:
            continue
        # 标准题带答题区（答案识别出来的作答区）时绝不整题红框兜底：
        # 整题框会把草稿、印刷选项、词库全批进去。答题区由逐槽任务批改，
        # 这里跳过的是学生切题切出来的重复题块（槽已在他处批过）。
        if standard_question.answer_bboxes or standard_question.raw.get("layout_slots_cleared"):
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

    def assign_candidates(max_distance: float, *, is_confident: bool, same_no_only: bool = False) -> None:
        for distance, standard_index, student_index in candidates:
            if distance > max_distance:
                break
            if standard_index in used_standard or student_index in used_student:
                continue
            if same_no_only:
                std_no = standard_slots[standard_index][0].printed_no
                stu_no = student_slots[student_index][0].printed_no
                if not std_no or std_no != stu_no:
                    continue
            used_standard.add(standard_index)
            used_student.add(student_index)
            matched[standard_index] = (student_index, is_confident)

    # Only a tight layout match is allowed to become a handwriting mark
    # anchor. A looser fallback can still receive an AI analysis, but cannot
    # produce a potentially misplaced check/cross.
    # 题号优先：先配题号一致的（同号不受几何阈值约束，防呆上限 0.35），
    # 再几何补缺。
    assign_candidates(
        max(strict_distance, 0.35), is_confident=True, same_no_only=True
    )
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
        normalized_slot_bbox = _scale_bbox(standard_bbox, standard_size, student_size)
        student_question = _question_for_slot_box(
            student_questions,
            standard_question.printed_no,
            normalized_slot_bbox,
            student_size,
        )
        if student_question is None:
            continue
        relative_projection = _project_bbox_between_question_regions(
            standard_bbox,
            standard_question.question_bbox,
            student_question.question_bbox,
            student_size,
        )
        if (
            relative_projection
            and _question_regions_comparable(
                standard_question.question_bbox,
                student_question.question_bbox,
                standard_size,
                student_size,
            )
            and _projection_within_sane_scale(
                standard_bbox, relative_projection, standard_size, student_size
            )
        ):
            mapped_student_bbox = relative_projection
        else:
            mapped_student_bbox = normalized_slot_bbox
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

    # 零散学生墨迹（草稿/词库/涂改）不再单独立任务：标准题带细分答题区时，
    # 只批答题区里的作答。仅标准题确实没有作答区（打字版答案行/整行框）时，
    # 学生墨迹才作为整行的落笔位置。
    for student_index, (student_question, student_sub_index, student_bbox) in enumerate(student_slots):
        if student_index in used_student:
            continue
        mapped_standard_bbox = _scale_bbox(student_bbox, student_size, standard_size)
        standard_question = _question_for_no_or_bbox(
            standard_questions,
            student_question.printed_no,
            mapped_standard_bbox,
            standard_size,
        )
        if standard_question is None:
            continue
        if standard_question.answer_bboxes or standard_question.raw.get("layout_slots_cleared"):
            continue
        # 标准题没有细分作答区（如打字版答案行/切题审查整行框）时，
        # 红框直接标整行（与答案表初步对照同一区域），别拿学生框按页比
        # 缩放出来的碎片当标准答案区——跨版面缩放没有对齐意义。
        if standard_question.question_bbox:
            standard_bbox = list(standard_question.question_bbox)
        else:
            standard_bbox = mapped_standard_bbox
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

    # Questions without any answer-location data are still reviewed as a
    # whole, but never gain an invented handwriting mark location.
    # 标准题带答题区时绝不整题红框（草稿/印刷字都在题框里），答题区已逐槽批。
    graded_question_ids = {id(task.student_question) for task in tasks}
    for student_question in student_questions:
        if id(student_question) in graded_question_ids:
            continue
        mapped_standard_bbox = _scale_bbox(
            student_question.question_bbox, student_size, standard_size
        )
        standard_question = _question_for_no_or_bbox(
            standard_questions,
            student_question.printed_no,
            mapped_standard_bbox,
            standard_size,
        )
        if standard_question is None:
            continue
        if standard_question.answer_bboxes or standard_question.raw.get("layout_slots_cleared"):
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
    elif any(code == PENDING for code in codes):
        # 任一作答区待确认 → 整题待确认（交人工拍板后再统分）
        aggregate_code = PENDING
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


def _bbox_match_position(
    boxes: list, target_bbox: Optional[list[int]]
) -> Optional[int]:
    """找 target_bbox 在 boxes 中的下标：先逐值精确，再唯一实质重叠。

    ⛔ 不做无上限最近邻（1019 语文审计：投影框/并框对不上槽时硬取最近，
    标准/作答整列张冠李戴）。只认「覆盖率≥0.5 的重叠且候选唯一」——并框
    盖住多槽、漂到空地、擦边不足都返回 None，宁缺勿串（上层回退转写/留空）。
    """
    if not boxes or not isinstance(target_bbox, (list, tuple)) or len(target_bbox) < 4:
        return None
    target = [_to_float(value) for value in target_bbox[:4]]
    for pos, bbox in enumerate(boxes):
        current = [_to_float(value) for value in (bbox or [])[:4]]
        if len(current) == 4 and current == target:
            return pos
    area_t = max(0.0, target[2] - target[0]) * max(0.0, target[3] - target[1])
    hits: list[tuple[float, int]] = []
    for pos, bbox in enumerate(boxes):
        current = [_to_float(value) for value in (bbox or [])[:4]]
        if len(current) != 4:
            continue
        inter_w = max(0.0, min(target[2], current[2]) - max(target[0], current[0]))
        inter_h = max(0.0, min(target[3], current[3]) - max(target[1], current[1]))
        inter = inter_w * inter_h
        if inter <= 0:
            continue
        area_c = max(0.0, current[2] - current[0]) * max(0.0, current[3] - current[1])
        denom = min(area_t, area_c)
        if denom <= 0:
            continue
        # 覆盖率 = 交集 / 较小框：同槽轻微抖动仍接近 1，边缘擦碰 <0.5
        if inter / denom >= 0.5:
            hits.append((inter / denom, pos))
    if len(hits) == 1:
        return hits[0][1]
    return None


def _answer_text_for_slot(
    question: VlmQuestion, target_bbox: Optional[list[int]]
) -> Optional[str]:
    """取单个作答区的答案文本（标准卷=标准答案，学生卷=作答识别）。

    answer_words 是整题识别文本，与 answer_bboxes 并非天然按槽对齐：
    - 单作答区（含无 bbox）：join 整题文本即本槽文本；
    - 多作答区且文本数=作答区数：按位置取本槽（顺序对齐约定）；
    - 多作答区且数量对不上：返回 None——⛔ 不拿整题拼接文本冒充本槽，
      否则多槽互串缓存键 / response_logs（宁缺勿串）。
    """
    words = [
        str(word).strip()
        for word in (question.answer_words or [])
        if str(word or "").strip()
    ]
    if not words:
        return None
    boxes = question.answer_bboxes or []
    if len(boxes) <= 1:
        return "\n".join(words)
    if len(words) != len(boxes):
        return None
    pos = _bbox_match_position(boxes, target_bbox)
    if pos is None:
        return None
    return words[pos]


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
    correct_answer: Optional[str] = None,
    question_content: Optional[str] = None,
) -> None:
    if not isinstance(decision, dict):
        raise RuntimeError(
            f"Question task {task_id} Qwen result must be a JSON object, "
            f"got {type(decision).__name__}"
        )
    normalized = _normalize_decision(
        decision, task_id, standard_answer_text=correct_answer
    )
    # 空白闸墨迹痕迹（_normalize_decision 重建 dict 会丢自定义键）：从入参读，
    # 随 sub_result → block 带出去 → verdict_cache._has_guard_trace 拦缓存。
    guard_trace = decision.get("ink_evidence") if isinstance(decision, dict) else None
    sub_result = {
        "question_id": task_id,
        "sub_index": sub_index,
        "correctResult": normalized["correctResult"],
        "result": normalized["result"],
        "reason": normalized["reason"],
        "analysis": normalized["analysis"],
        "confidence": normalized["confidence"],
        "partial_ratio": normalized.get("partial_ratio"),
        "transcription": normalized.get("transcription") or "",
        "read_uncertain": bool(normalized.get("read_uncertain")),
        "ink_evidence": guard_trace if isinstance(guard_trace, dict) else None,
        "answer_bbox": list(answer_bbox),
        "has_handwriting_location": bool(has_handwriting_location),
        "has_mark_anchor": bool(has_mark_anchor),
        "is_answer_slot": bool(is_answer_slot),
        "anchor_source": str(anchor_source or "none"),
        "template_slot_id": template_slot_id,
        # 标准卷该作答区的答案文本/题干（跨学生稳定）：缓存键/response_logs 用它，
        # 学生卷识别噪声不进身份键。配对按作答区位置（_build_grading_tasks），
        # ⛔ 不能按 question_id 反查标准卷（两卷切题 id 可能不同）。
        "correct_answer": correct_answer,
        "question_content": question_content,
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


def _build_blocks(
    questions: list[VlmQuestion],
    standard_by_id: Optional[dict] = None,
) -> list[dict]:
    """把 VlmQuestion 判分结果摊平成批改块（含 C1 文本/置信度管道字段）。

    standard_by_id：question_id -> 标准卷 VlmQuestion，仅给非槽级块兜底
    correct_answer/question_content（⚠️ 跨卷 question_id 不可靠，槽级块一律用
    _insert_sub_grading_result 按位置线程化的 sub_result 文本，不走 id 反查）。
    非槽级块 ⛔ 不写 student_answer：此路多是未配对作答区的默认判分块，
    带上文本进缓存会把假"错"当成真判分复用放大。
    """
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
                        "read_uncertain": bool(sub_result.get("read_uncertain")),
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
                        # C1 管道字段：confidence 进 low-confidence 队列；
                        # question_content/correct_answer 取标准卷侧（跨学生稳定），
                        # student_answer 取本槽文本（list ⛔ 不得直接 str()）。
                        "confidence": sub_result.get("confidence"),
                        "question_content": (
                            str(
                                sub_result.get("question_content") or q.question_words or ""
                            ).strip()
                            or None
                        ),
                        # 切题 OCR 有文本用文本（缓存身份键同口径）；OCR 空时
                        # 退回判分转写（TRANSCRIPTION FIRST 逐字读出的手写原文），
                        # 否则老师看到的学生作答整列空白。转写只在 OCR 空时进
                        # student_answer：非空 OCR 槽的缓存键保持 OCR 文本不变。
                        "student_answer": _answer_text_for_slot(q, answer_bbox)
                        or (str(sub_result.get("transcription") or "").strip() or None),
                        "question_type": str(q.question_type or "").strip() or None,
                        "correct_answer": (
                            str(sub_result.get("correct_answer") or "").strip() or None
                        ),
                        # 空白闸等兜底痕迹：verdict_cache._has_guard_trace 据此
                        # 拒绝 AI 判分入缓存（human 例外）
                        "ink_evidence": (
                            sub_result.get("ink_evidence")
                            if isinstance(sub_result.get("ink_evidence"), dict)
                            else None
                        ),
                    }
                )
            continue
        grading = q.raw.get("grading_result") if isinstance(q.raw.get("grading_result"), dict) else {}
        code = _to_int(grading.get("correctResult"), _to_int(q.raw.get("correctResult"), WRONG))
        result_text = _result_label(code, grading.get("partial_ratio"))
        std_q = (standard_by_id or {}).get(q.question_id) if isinstance(standard_by_id, dict) else None
        std_words: list[str] = []
        std_question_words = ""
        if isinstance(std_q, VlmQuestion):
            std_words = [
                str(word).strip()
                for word in (std_q.answer_words or [])
                if str(word or "").strip()
            ]
            std_question_words = str(std_q.question_words or "")
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
                "confidence": grading.get("confidence"),
                "question_content": (
                    str(std_question_words or q.question_words or "").strip() or None
                ),
                # 见函数 docstring：非槽级块不产出 student_answer（防默认判分进缓存）
                "student_answer": None,
                "question_type": str(q.question_type or "").strip() or None,
                "correct_answer": "\n".join(std_words) or None,
            }
        )
    return blocks


def _summarize_result_text(questions: list[VlmQuestion]) -> str:
    total = 0
    correct = wrong = unanswered = partial = pending = 0
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
                elif code == PENDING:
                    pending += 1
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
        elif code == PENDING:
            pending += 1
        else:
            wrong += 1
        analysis = str(grading.get("analysis") or grading.get("reason") or "").strip()
        lines.append(f"第{q.display_index}题：{_result_label(code, grading.get('partial_ratio'))} - {analysis}")
    header = f"总题量：{total}；正确：{correct}；错误：{wrong}；半对：{partial}；未作答：{unanswered}；待确认：{pending}"
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
    """Draw checks/crosses for graded answer areas; unanswered slots get a hollow
    circle (2026-10-16: never leave a blank with no mark at all). Pending slots
    stay unmarked so the teacher's verdict isn't prejudged."""
    mark_blocks: list[dict] = []

    def valid_bbox(value: Any) -> Optional[list[int]]:
        if not isinstance(value, (list, tuple)) or len(value) < 4:
            return None
        bbox = [int(_to_float(item)) for item in value[:4]]
        return bbox if bbox[2] > bbox[0] and bbox[3] > bbox[1] else None

    for block in blocks_with_result:
        if not isinstance(block, dict):
            continue
        code = _to_int(block.get("baidu_correct_result"), WRONG)
        if code == PENDING:
            # 待确认交人工拍板，不画勾叉（错叉会误导成已判错）
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
        # 老师手动批注（每道题一句 + 整卷总评）写到卷面留痕上
        img_w, img_h = image.size
        draw_manual_annotations(draw, img_w, img_h, blocks_with_result, question_notes, paper_note)
        image.save(output_path, quality=95)
    return orig_name, ann_name, marks_only


# ── C3 判分缓存（aliyun 预查 / 命中合成）────────────────────────────────

_CACHE_RESULT_TO_CODE = {
    "对": CORRECT,
    "错": WRONG,
    "未作答": UNANSWERED,
    "半对": PARTIAL,
    "待确认": PENDING,
}


def _slot_cache_identity(task: VlmGradingTask) -> tuple:
    """槽缓存身份文本——与 _build_blocks 回写侧（store_blocks 键）严格一致：
    question_type 走学生侧、question_content/correct_answer 走标准侧（答案表
    完整识别文本优先）、student_answer 按 int 化作答框取本槽文本（宁缺勿串）。"""
    std_q = task.standard_question
    stu_q = task.student_question
    stu_bbox = [int(_to_float(v)) for v in (task.student_answer_bbox or [])[:4]]
    return (
        str(stu_q.question_type or "").strip() or None,
        str(std_q.question_words or "").strip() or None,
        _standard_answer_text(task),
        _answer_text_for_slot(stu_q, stu_bbox),
    )


def _lookup_task_cache(tasks: list[VlmGradingTask], cache_subject: str) -> dict:
    """C3 预查：task_id -> 缓存命中行；缓存关闭 / 无键返回 {}（当全未命中）。"""
    from app.grading.verdict_cache import cache_enabled, cache_key, lookup_many

    hits: dict = {}
    if not cache_enabled():
        return hits
    key_by_task: dict = {}
    for task in tasks:
        question_type, question_content, correct_answer, student_answer = _slot_cache_identity(task)
        key = cache_key(
            cache_subject, question_type, question_content, correct_answer, student_answer
        )
        if key:
            key_by_task[task.task_id] = key
    if not key_by_task:
        return hits
    found = lookup_many(list(key_by_task.values()))
    for task_id, key in key_by_task.items():
        hit = found.get(key)
        if hit:
            hits[task_id] = hit
    return hits


def _decision_from_cache_entry(hit: dict, task_id: int) -> dict:
    """缓存命中行 → 千问 decision 同形 dict（走 _normalize_decision 保证形状一致）。"""
    from app.grading.form_guard import _norm_result

    result = _norm_result(hit.get("result"))
    code = _CACHE_RESULT_TO_CODE.get(result, WRONG)
    comment = str(hit.get("comment") or "").strip()
    return _normalize_decision(
        {
            "question_id": task_id,
            "correctResult": code,
            "result": result,
            "reason": comment or "判分缓存复用",
            "analysis": comment or "判分缓存复用",
            "partial_ratio": hit.get("partial_ratio"),
            "confidence": 1.0,
        },
        task_id,
    )


# ── 空白槽墨迹闸（判定权收归代码）────────────────────────────────────
# 2026-10-16「观察与梳理那么多空白你去打勾干什么」投诉根因：判分是双图同屏，
# image 1 标准答案老师已写在同样的空上，VL 会把 image 1 的答案抄进
# transcription 判「对」→ 空白被打勾。form_guard 绝对阈值 0.002 对印刷
# 下划线（墨迹 0.06）是瞎的；ink_evidence VL 也可能把印刷线当笔迹。
# 同位墨迹对照校准（邓雨彤_1 第12题，std/stu 同分辨率同 bbox）：
#   真笔迹 stu/std 0.70–1.07（含选择小答案）；空白仅印刷线 0.15–0.30。
# 规则 stu_ink < 0.12 且 stu_ink < 0.5×std_ink 干净分开两侧。
_BLANK_INK_STU_MAX = 0.12  # 学生槽绝对墨迹上限（空白印刷线实测 0.059–0.073）
_BLANK_INK_RATIO = 0.5  # 学生/标准墨迹比上限（空白实测 ≤0.30，真笔迹 ≥0.70）
_BLANK_GUARD_REASON = "作答区无手写笔迹，按未作答处理"


def _apply_blank_ink_guard(
    decision: dict,
    task: "VlmGradingTask",
    std_img,
    stu_img,
    *,
    cache_hit: Optional[dict] = None,
) -> bool:
    """学生槽无手写、标准槽同位有答案 → 强制「未作答」。返回是否降级。

    只动 对/错/半对；人工终态（缓存 source=human）绝不翻。reason/analysis
    整句替换（残留「…判对。」句尾会触发 _apply_conclusion_guard 矛盾翻待确认），
    幻觉转写一并清空（防 read_guard 因 [?] 标记再翻待确认，未作答要落空心圈）。
    墨迹对不上/量不出来 fail-open 不动。decision["ink_evidence"] 留痕迹：
    块上带它 → verdict_cache 不入缓存（幻觉未作答复用会放大）。
    """
    if isinstance(cache_hit, dict) and str(cache_hit.get("source") or "").strip() == "human":
        return False
    code = _to_int(decision.get("correctResult"), 0)
    if code not in (CORRECT, WRONG, PARTIAL):
        return False
    try:
        std_bbox = _clamp_bbox(task.standard_answer_bbox, std_img.size)
        stu_bbox = _clamp_bbox(task.student_answer_bbox, stu_img.size)
        std_ink = float(ink_ratio(std_img, std_bbox))
        stu_ink = float(ink_ratio(stu_img, stu_bbox))
    except Exception:
        return False
    if not (stu_ink < _BLANK_INK_STU_MAX and stu_ink < _BLANK_INK_RATIO * std_ink):
        return False
    decision["correctResult"] = UNANSWERED
    decision["result"] = RESULT_TEXT[UNANSWERED]
    decision["partial_ratio"] = None
    decision["reason"] = _BLANK_GUARD_REASON
    decision["analysis"] = _BLANK_GUARD_REASON
    decision["transcription"] = ""
    decision["read_confidence"] = 1.0
    decision["read_uncertain"] = False
    decision["ink_evidence"] = {
        "action": "downgraded",
        "source": "std_ink_compare",
        "stu_ink": round(stu_ink, 4),
        "std_ink": round(std_ink, 4),
        "was_result": RESULT_TEXT.get(code, "错"),
    }
    return True


_UNANSWERED_INK_REASON = "作答区有笔迹但未识别出答案，待人工确认"


def _apply_unanswered_ink_guard(
    decision: dict,
    task: "VlmGradingTask",
    std_img,
    stu_img,
    *,
    cache_hit: Optional[dict] = None,
) -> bool:
    """学生槽有手写笔迹、VL 判「未作答」→ 强制「待确认」。返回是否改判。

    空白闸的反向缺口（1016 邓雨彤_1 投诉：shī fu 一空「师傅」写得清清楚楚
    却被判未作答，空心圈直接画到字上）：未作答 + 学生同位墨迹 ≥0.12（真笔迹
    下限；空白只有印刷线 0.028–0.073）= VL 没读出来 ≠ 学生没写。转「待确认」
    交人工——待确认不画记号，绝不把圈画到字上。人工终态缓存命中豁免同空白闸。
    reason 整句替换 + 转写清空（同空白闸：防 conclusion/read_guard 二次翻转）。
    decision["ink_evidence"] 留痕迹 → verdict_cache 不入缓存。
    """
    if isinstance(cache_hit, dict) and str(cache_hit.get("source") or "").strip() == "human":
        return False
    code = _to_int(decision.get("correctResult"), 0)
    if code != UNANSWERED:
        return False
    try:
        std_bbox = _clamp_bbox(task.standard_answer_bbox, std_img.size)
        stu_bbox = _clamp_bbox(task.student_answer_bbox, stu_img.size)
        std_ink = float(ink_ratio(std_img, std_bbox))
        stu_ink = float(ink_ratio(stu_img, stu_bbox))
    except Exception:
        return False
    if stu_ink < _BLANK_INK_STU_MAX:
        return False
    decision["correctResult"] = PENDING
    decision["result"] = RESULT_TEXT[PENDING]
    decision["partial_ratio"] = None
    decision["reason"] = _UNANSWERED_INK_REASON
    decision["analysis"] = _UNANSWERED_INK_REASON
    decision["transcription"] = ""
    decision["read_confidence"] = 1.0
    decision["read_uncertain"] = False
    decision["ink_evidence"] = {
        "action": "pending_high_ink",
        "source": "stu_ink_unanswered",
        "stu_ink": round(stu_ink, 4),
        "std_ink": round(std_ink, 4),
        "was_result": RESULT_TEXT.get(code, "未作答"),
    }
    return True


# ── 块一致性闸（1019 语文审计：一槽三源互不校验 → 判语/三列文本张冠李戴）──
# 判语看的是裁剪图，展示的标准列来自查表/配对，学生列来自 OCR 位置取词，
# 三条链各自会错、错了照样拼一块。出块前互检，对不上一律待确认（不画记号）。
_NORM_COMPARE_RE = re.compile(r"[\s，。、；：？！（）()《》“”‘’\[\]{}\"'，.,;:!?第题：:]")


def _norm_compare_text(value: str) -> str:
    """比对用归一化：去「第N题：」行头/小问号/标点空白，只留内容字。"""
    text = str(value or "").strip()
    text = re.sub(r"^第\s*\d+\s*题(?:[（(]\d+[）)])?\s*[:：]\s*", "", text)
    text = re.sub(r"[（(]\d{1,3}[）)]", "", text)
    return _NORM_COMPARE_RE.sub("", text)


def _texts_agree(left: str, right: str) -> bool:
    """两段文本内容一致（含一边只抄一空/半句的包含关系）；都空不作数。"""
    a, b = _norm_compare_text(left), _norm_compare_text(right)
    if not a or not b:
        return False
    return a in b or b in a


# 评语里「本槽是第 N 题」的自称（只认点名本槽的句式，不抓「第(2)小题」小问号）
_CLAIMED_NO_RES = (
    re.compile(r"(?:该空|本空|此空|该红框|此框|该作答区)(?:应)?(?:属于|对应|位于|是)第\s*(\d{1,3})\s*题"),
    re.compile(r"定位到印刷题号为第\s*(\d{1,3})\s*题"),
    re.compile(r"印刷题号(?:为|是)?\s*第?\s*(\d{1,3})\s*题"),
    re.compile(r"对应印刷题号\s*(\d{1,3})"),
)


def _claimed_question_nos(decision: dict) -> set[int]:
    """从 reason/analysis 里抽出评语自称的本槽印刷题号集合。"""
    text = f"{decision.get('reason') or ''}\n{decision.get('analysis') or ''}"
    found: set[int] = set()
    for pattern in _CLAIMED_NO_RES:
        for match in pattern.finditer(text):
            value = _to_int(match.group(1), 0)
            if value:
                found.add(value)
    return found


def _force_pending_with_trace(
    decision: dict,
    note: str,
    *,
    trace_source: str,
    extra: Optional[dict] = None,
) -> None:
    """强制待确认 + 留 ink_evidence 痕迹（verdict_cache 不入缓存）。"""
    if decision.get("correctResult") == PENDING:
        return
    was = RESULT_TEXT.get(_to_int(decision.get("correctResult"), 0), "错")
    decision["correctResult"] = PENDING
    decision["result"] = RESULT_TEXT[PENDING]
    decision["partial_ratio"] = None
    base = str(decision.get("reason") or "").strip()
    full = f"{note}，待人工确认"
    decision["reason"] = f"{full}；{base}" if base else full
    decision["analysis"] = decision["reason"]
    evidence = {"action": "pending_conflict", "source": trace_source, "was_result": was}
    if extra:
        evidence.update(extra)
    decision["ink_evidence"] = evidence


def _apply_question_no_guard(
    decision: dict,
    task: "VlmGradingTask",
    *,
    cache_hit: Optional[dict] = None,
) -> bool:
    """图中/评语自称题号与机器配对题号不一致 → 待确认。

    4₂ 标签落在第 5 题括号内这类槽位错挂：判分所依的题号和配对元数据
    对不上，块上判语/文本必乱。只在配对题号可知且冲突时落闸（合并块
    无题号 fail-open）；人工终态豁免。"""
    if isinstance(cache_hit, dict) and str(cache_hit.get("source") or "").strip() == "human":
        return False
    paired = str(
        task.student_question.printed_no or task.standard_question.printed_no or ""
    ).strip()
    if not paired or not paired.isdigit():
        return False
    claimed = _claimed_question_nos(decision)
    located = _to_int(decision.get("located_no"), 0) or None
    if located:
        claimed.add(located)
    if not claimed:
        return False
    if int(paired) in claimed and len(claimed) == 1:
        return False
    if int(paired) in claimed:
        # 配对号和异号自称同时出现（评语摇摆）→ 也是存疑
        claimed.discard(int(paired))
    _force_pending_with_trace(
        decision,
        f"图中题号（第{'/'.join(str(n) for n in sorted(claimed))}题）与配对第{paired}题不一致",
        trace_source="question_no_conflict",
        extra={"paired_no": paired, "claimed_nos": sorted(claimed)},
    )
    return True


def _apply_standard_text_conflict_guard(
    decision: dict,
    correct_text: Optional[str],
    *,
    cache_hit: Optional[dict] = None,
) -> bool:
    """模型引文（判分真实所依的标准答案）与展示标准列对不上 → 待确认。

    一槽三源里最毒的形态：判语按第 13 题「空间」判的，标准列却挂着
    第 14 题「不矛盾…」。引文一字不差照抄是提示词硬要求，对不上就是
    文本线程串位，宁可交人工也不展示错乱三列。"""
    if isinstance(cache_hit, dict) and str(cache_hit.get("source") or "").strip() == "human":
        return False
    quote = str(decision.get("standard_quote") or "").strip()
    if not quote or not correct_text or not str(correct_text).strip():
        return False
    # 展示标准列是〈文本缺失〉：没有文本权威可对质（该槽只认 image 1），
    # 引文抄 image 1 答案与之「不一致」不构成串位证据 → 不拦
    if _TEXT_MISSING in str(correct_text):
        return False
    if _texts_agree(quote, correct_text):
        return False
    _force_pending_with_trace(
        decision,
        "判分所依标准引文与展示标准答案不一致",
        trace_source="standard_text_conflict",
        extra={"quote": quote[:96], "shown": str(correct_text)[:96]},
    )
    return True


def _apply_unanswered_text_guard(
    decision: dict,
    student_text: Optional[str],
    correct_text: Optional[str],
    *,
    cache_hit: Optional[dict] = None,
) -> bool:
    """判未作答但标准列=学生列同文 → 文本线程串位实锤，转待确认。

    邓雨彤灾难块形态之一：`[未作答] 标准=X 作答=X`——文本明明同文，
    判语说没写。两者必有一列是别处抄来的，绝不能落空心圈。"""
    if isinstance(cache_hit, dict) and str(cache_hit.get("source") or "").strip() == "human":
        return False
    if _to_int(decision.get("correctResult"), 0) != UNANSWERED:
        return False
    stu = _norm_compare_text(student_text)
    std = _norm_compare_text(correct_text)
    if not stu or not std or stu != std:
        return False
    _force_pending_with_trace(
        decision,
        "判未作答但标准与作答文本相同",
        trace_source="unanswered_text_identity",
    )
    return True


def grade_reference_vlm_paper(
    standard_name: str,
    standard_doc: dict,
    student_name: str,
    student_doc: dict,
    *,
    folder_safe: str,
    slot_template: Optional[list[VlmSlotTemplate]] = None,
    stop_event: Optional[threading.Event] = None,
    family_hint: str = "",
    cache_subject: str = "",
    answer_table: Optional[dict] = None,
) -> tuple[str, list, dict, str]:
    """Grade one paper and return (result_text, blocks, enriched_vlm_json, mark_image_path).

    answer_table：标准答案完整识别表（load_or_build_reference_answer_table 产出）。
    判分提示词以表内文本为唯一判分依据；缺槽回退 answer_words，再回退 image 1。
    """
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
        # 标准答案完整识别文本就位（答案表优先，answer_words 兜底见 _standard_answer_text）
        if answer_table:
            for task in tasks:
                # 转写不可靠的表文本改落〈文本缺失〉哨兵（不给错文、也不给空——
                # 空会漏进 answer_words 兜底）：判分转 image 1 红框，read_guard 不误伤
                task.standard_answer_text = _unreliable_as_text_missing(
                    _answer_table_slot_text(
                        answer_table,
                        task.standard_question,
                        task.standard_answer_bbox,
                        # 按学生印刷题号取行（与判分查表同通道）：合并块拆条后
                        # 第 N 题各自拿到自己的标准答案，不是整块全文
                        prefer_no=task.student_question.printed_no or task.standard_question.printed_no,
                    )
                )
        # 完整答案表进提示词：先认题号，再对照本表（用户要求 AI 明确知道每道题答案）
        answer_table_text = _answer_table_summary_text(answer_table)
        batches = _group_grading_tasks(tasks)
        # C3 判分缓存预查：同（题, 作答）命中直接复用判分。全命中 batch 不提交
        # VL（省图省调用）；部分命中照调 VL，结果回来后对命中槽覆盖为缓存值。
        cache_hits = _lookup_task_cache(tasks, cache_subject)
        qwen_tasks: list[tuple[VlmQuestionBatchTask, str, str]] = []
        for batch in batches:
            if cache_hits and all(slot.task_id in cache_hits for slot in batch.slots):
                continue  # 全命中：本批零 VL 调用
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
            family_hint=family_hint,
            answer_table_text=answer_table_text,
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

    # 空白闸要同位墨迹对照（std/stu 图上面的 with 已关）：重开一次套住回填循环，
    # 打开失败就跳过闸（fail-open，判分照常入库）。
    try:
        std_guard_img = Image.open(standard_image_path).convert("RGB")
        stu_guard_img = Image.open(student_image_path).convert("RGB")
    except Exception:
        std_guard_img = stu_guard_img = None
    try:
        for batch in batches:
            batch_decisions = decisions.get(batch.batch_id) or {}
            for task in batch.slots:
                q = task.student_question
                hit = cache_hits.get(task.task_id) if cache_hits else None
                # C3：命中槽一律以缓存值入库（含人工终态，权威高于本次 VL；全命中批
                # 无 VL 结果时也由此补齐 decision）
                decision = (
                    _decision_from_cache_entry(hit, task.task_id)
                    if hit is not None
                    else batch_decisions.get(task.task_id)
                )
                if not decision:
                    raise RuntimeError(
                        f"第{q.display_index}题作答区{task.sub_index}缺少千问判题结果，"
                        "已停止写入，避免 JSON 错插"
                    )
                # 空白槽闸：标准有答案、学生同位只有印刷线 → VL 抄了 image 1，
                # 强制未作答（人工终态命中豁免在闸内判）。必须在入库前落，
                # _insert_sub_grading_result 会再跑一次 _normalize_decision。
                if std_guard_img is not None:
                    _apply_blank_ink_guard(
                        decision, task, std_guard_img, stu_guard_img, cache_hit=hit
                    )
                    # 反向闸：判未作答但学生同位有笔迹（VL 没读出来≠没写）
                    # → 转待确认不画圈，绝不把空心圈画到字上（1016 师傅投诉）。
                    _apply_unanswered_ink_guard(
                        decision, task, std_guard_img, stu_guard_img, cache_hit=hit
                    )
                # 判分回填：模型已在图上定位本槽印刷题号（located_no），标准答案
                # 元数据跟着判分查表同通道取行——学生切题无印刷题号时机器配对会
                # 拼整块（1-7 题兄弟串）或串到别的行。located_no 是判分真实所依，
                # 比预查配对稳（同一卷面布局跨学生稳定）。缓存命中结果无 located_no，
                # 保持预查身份文本，与命中键一致。
                # 1019 加闸：改道不再无条件换——与模型引文（判分真实所依）一致才换；
                # 引文缺失时只在配对题号未知或同号时换。换完仍和引文/题号对不上的，
                # 下面的一致性闸一律转待确认（一槽三源互检，宁缺勿串）。
                correct = _standard_answer_text(task)
                located_no = _to_int(decision.get("located_no"), 0) or None
                if answer_table and located_no:
                    # 与预查同规则：转写不可靠的行落〈文本缺失〉，展示列不落错文
                    located_text = _unreliable_as_text_missing(
                        _answer_table_slot_text(
                            answer_table,
                            task.standard_question,
                            task.standard_answer_bbox,
                            prefer_no=str(located_no),
                        )
                    )
                    if located_text:
                        quote = str(decision.get("standard_quote") or "").strip()
                        paired_no = str(
                            task.student_question.printed_no
                            or task.standard_question.printed_no
                            or ""
                        ).strip()
                        if quote:
                            if _texts_agree(located_text, quote):
                                correct = located_text
                        elif not paired_no or paired_no == str(located_no):
                            correct = located_text
                _apply_question_no_guard(decision, task, cache_hit=hit)
                _apply_standard_text_conflict_guard(decision, correct, cache_hit=hit)
                _apply_unanswered_text_guard(
                    decision,
                    _answer_text_for_slot(q, task.student_answer_bbox),
                    correct,
                    cache_hit=hit,
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
                    # 标准卷侧文本（跨学生稳定）：缓存键/response_logs 身份用它，
                    # 学生卷识别噪声不进身份键。⛔ 不按 question_id 反查标准卷。
                    correct_answer=correct,
                    question_content=(
                        str(task.standard_question.question_words or "").strip() or None
                    ),
                )
    finally:
        for _guard_img in (std_guard_img, stu_guard_img):
            try:
                if _guard_img is not None:
                    _guard_img.close()
            except Exception:
                pass

    standard_by_id = {
        std.question_id: std
        for std in (standard_questions or [])
        if isinstance(std, VlmQuestion)
    }
    blocks = _build_blocks(student_questions, standard_by_id=standard_by_id)
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
