# -*- coding: utf-8 -*-
"""Reference-answer grading based on Baidu paper_cut_edu OCR JSON.

The LLM is only allowed to decide correctness and explanation text. The
backend owns all coordinates and the final correct_edu-shaped JSON contract.
"""
import hashlib
import json
import re
import time
import uuid
from collections import defaultdict
from typing import Any, Optional

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - handled at runtime
    OpenAI = None

from app.grading.baidu_grading import _parse_baidu_grade_result
from app.utils.qwen_settings import DEFAULT_QWEN_MODEL, QWEN_CHAT_EXTRA_BODY, get_qwen_config


CORRECT = 1
WRONG = 2
UNANSWERED = 3


def _bbox_to_area(bbox: Any) -> dict:
    if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
        return {"left_x": 0, "left_y": 0, "right_x": 0, "right_y": 0}
    try:
        x1, y1, x2, y2 = [int(float(v or 0)) for v in bbox[:4]]
    except Exception:
        x1 = y1 = x2 = y2 = 0
    return {
        "left_x": min(x1, x2),
        "left_y": min(y1, y2),
        "right_x": max(x1, x2),
        "right_y": max(y1, y2),
    }


def _safe_text(value: Any, limit: int = 1200) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _group_blocks(blocks: list[dict]) -> list[dict]:
    grouped: dict[int, list[dict]] = defaultdict(list)
    for block in blocks or []:
        try:
            idx = int(block.get("index") or 0)
        except Exception:
            idx = 0
        if idx > 0:
            grouped[idx].append(block)

    questions: list[dict] = []
    for idx in sorted(grouped):
        items = sorted(grouped[idx], key=lambda b: _to_int(b.get("sub_index"), 1))
        first = items[0]
        slots = []
        for block in items:
            sub_idx = _to_int(block.get("sub_index"), len(slots) + 1)
            slots.append(
                {
                    "slot_seq": sub_idx,
                    "elem_type": str(block.get("elem_type") or ""),
                    "text": _safe_text(block.get("text")),
                    "answer_text": _safe_text(block.get("answer_text")),
                    "sub_question_text": _safe_text(block.get("subqus_text")),
                    "reference_answer": _safe_text(block.get("interpretation_text") or block.get("answer_text")),
                }
            )
        questions.append(
            {
                "question_index": idx,
                "question_text": _safe_text(first.get("stem_text") or first.get("text")),
                "option_text": _safe_text(first.get("option_text")),
                "reference_answer": _safe_text(first.get("interpretation_text") or first.get("answer_text")),
                "slots": slots,
            }
        )
    return questions


def _build_prompt(standard_name: str, standard_blocks: list[dict], student_name: str, student_blocks: list[dict]) -> str:
    payload = {
        "standard_paper": {
            "name": standard_name or "标准答案",
            "role": "standard_answer",
            "questions": _group_blocks(standard_blocks),
        },
        "student_paper": {
            "name": student_name or "student",
            "role": "student_answer",
            "questions": _group_blocks(student_blocks),
        },
    }
    return (
        "你是一名严格的中小学试卷批改老师。下面给你两份百度 paper_cut_edu OCR 结构化结果："
        "名称为“标准答案”的试卷是本次唯一标准答案，student_paper 是待批改试卷。\n"
        "请先理解标准答案中每道题的题目、选项、参考答案、作答内容，再逐题批改学生卷。\n"
        "严格要求：\n"
        "1. 必须只按标准答案判分，不要凭空改变题目顺序。\n"
        "2. 只输出 JSON，不要输出 Markdown、解释性前后缀或代码块。\n"
        "3. 只能返回下方 schema 中已有字段，不能增加任何额外字段。\n"
        "4. question_index 和 slot_seq 必须来自 student_paper，不能生成新编号。\n"
        "5. correctResult 只能是 1、2、3：1=正确，2=错误，3=未作答/空白。\n"
        "6. reason 必须是简短 AI 解析，说明对照标准答案后的判断依据。\n"
        "7. 不要生成坐标、questionId、slotId、cropUrl、imageResults 等字段，这些由后端补齐。\n"
        "返回 schema："
        '{"questions":[{"question_index":1,"slots":[{"slot_seq":1,"correctResult":1,"reason":"..."}]}]}\n'
        "OCR JSON：\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def _get_client_and_model():
    if OpenAI is None:
        raise RuntimeError("需要安装 openai: pip install openai")
    api_key, model = get_qwen_config(default_model=DEFAULT_QWEN_MODEL)
    if not api_key:
        raise RuntimeError("系统设置中未配置千问 API Key")
    return (
        OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"),
        model or DEFAULT_QWEN_MODEL,
    )


def _strip_json_text(text: str) -> str:
    raw = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", raw, re.S | re.I)
    if fenced:
        raw = fenced.group(1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end >= start:
        raw = raw[start : end + 1]
    return raw


def _parse_llm_decisions(text: str) -> dict[tuple[int, int], dict]:
    try:
        data = json.loads(_strip_json_text(text))
    except Exception as exc:
        raise RuntimeError(f"千问返回的判题 JSON 无法解析: {exc}") from exc
    questions = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(questions, list):
        raise RuntimeError("千问返回缺少 questions 数组")

    decisions: dict[tuple[int, int], dict] = {}
    for q in questions:
        if not isinstance(q, dict):
            continue
        try:
            q_idx = int(q.get("question_index"))
        except Exception:
            continue
        slots = q.get("slots")
        if not isinstance(slots, list):
            continue
        for slot in slots:
            if not isinstance(slot, dict):
                continue
            try:
                slot_seq = int(slot.get("slot_seq"))
            except Exception:
                continue
            try:
                result = int(slot.get("correctResult"))
            except Exception:
                result = WRONG
            if result not in (CORRECT, WRONG, UNANSWERED):
                result = WRONG
            decisions[(q_idx, slot_seq)] = {
                "correctResult": result,
                "reason": _safe_text(slot.get("reason"), limit=500) or "已按标准答案完成批改。",
            }
    return decisions


def _call_qwen(standard_name: str, standard_blocks: list[dict], student_name: str, student_blocks: list[dict]) -> dict:
    client, model = _get_client_and_model()
    prompt = _build_prompt(standard_name, standard_blocks, student_name, student_blocks)
    completion = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        stream=False,
        timeout=180,
        extra_body=QWEN_CHAT_EXTRA_BODY,
    )
    text = (completion.choices[0].message.content or "").strip()
    return _parse_llm_decisions(text)


def _question_text(blocks: list[dict]) -> str:
    parts = []
    for key in ("stem_text", "subqus_text", "option_text"):
        for block in blocks:
            text = str(block.get(key) or "").strip()
            if text and text not in parts:
                parts.append(text)
    return "\n".join(parts).strip()


def _slot_default_result(block: dict) -> int:
    answer = str(block.get("answer_text") or block.get("text") or "").strip()
    return UNANSWERED if not answer else WRONG


def _build_correct_edu_json(
    student_name: str,
    student_blocks: list[dict],
    decisions: dict[tuple[int, int], dict],
    *,
    task_id: Optional[str] = None,
) -> dict:
    task_id = task_id or f"qwen_ref_{uuid.uuid4().hex}"
    image_id = hashlib.md5(f"{task_id}:{student_name}".encode("utf-8")).hexdigest()

    by_question: dict[int, list[dict]] = defaultdict(list)
    for block in student_blocks or []:
        try:
            idx = int(block.get("index") or 0)
        except Exception:
            idx = 0
        if idx > 0:
            by_question[idx].append(block)

    question_results = []
    for seq, q_idx in enumerate(sorted(by_question)):
        blocks = sorted(by_question[q_idx], key=lambda b: _to_int(b.get("sub_index"), 1))
        q_area = _bbox_to_area(blocks[0].get("baidu_question_bbox") or blocks[0].get("bbox"))
        slots = []
        slot_results = []
        for slot_pos, block in enumerate(blocks):
            slot_seq = _to_int(block.get("sub_index"), slot_pos + 1)
            decision = decisions.get((q_idx, slot_seq)) or {}
            correct_result = int(decision.get("correctResult") or _slot_default_result(block))
            if correct_result not in (CORRECT, WRONG, UNANSWERED):
                correct_result = WRONG
            slot_results.append(correct_result)
            slots.append(
                {
                    "correctResult": correct_result,
                    "reason": str(decision.get("reason") or "未在千问返回中找到该作答区，后端按默认规则标记。").strip(),
                    "handwritingArea": _bbox_to_area(block.get("bbox") or block.get("baidu_question_bbox")),
                    "seqence": slot_seq,
                    "slotId": f"{image_id}_{seq}_{slot_pos}",
                }
            )

        if slot_results and all(v == CORRECT for v in slot_results):
            question_result = CORRECT
        elif slot_results and all(v == UNANSWERED for v in slot_results):
            question_result = UNANSWERED
        else:
            question_result = WRONG

        question_results.append(
            {
                "correctResult": question_result,
                "questionId": f"{image_id}{seq + 1:02d}",
                "question": _question_text(blocks),
                "seqence": seq,
                "questionArea": [q_area],
                "isFinish": True,
                "slot": slots,
                "type": _to_int(blocks[0].get("type"), 4),
                "cropUrl": "",
            }
        )

    return {
        "error_code": 0,
        "error_msg": "",
        "result": {
            "task_id": task_id,
            "isAllFinished": True,
            "status": "Success",
            "stat_result": {
                "all": len(question_results),
                "correcting": 0,
                "corrected": len(question_results),
            },
            "imageResults": [
                {
                    "imageId": image_id,
                    "imageUrl": "",
                    "paperSubject": "",
                    "result": question_results,
                    "resize_ratio": 1,
                }
            ],
        },
        "log_id": str(int(time.time() * 1000)),
    }


def grade_reference_paper_cut_json(
    standard_name: str,
    standard_raw: dict,
    standard_blocks: list[dict],
    student_name: str,
    student_raw: dict,
    student_blocks: list[dict],
    *,
    stop_event=None,
) -> tuple[str, list, dict]:
    """Grade one student paper and return the same tuple as baidu_grade_single."""
    del standard_raw, student_raw
    if stop_event and stop_event.is_set():
        raise RuntimeError("已停止批改")
    decisions = _call_qwen(standard_name, standard_blocks, student_name, student_blocks)
    if stop_event and stop_event.is_set():
        raise RuntimeError("已停止批改")
    task_id = f"qwen_ref_{uuid.uuid4().hex}"
    smart_json = _build_correct_edu_json(student_name, student_blocks, decisions, task_id=task_id)
    return _parse_baidu_grade_result(smart_json, task_id)
