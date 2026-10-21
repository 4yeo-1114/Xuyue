"""判错原因批注：批改完成后为错/半对的题自动生成「为什么错」，老师可改可手写。

- 存储：grading_history item 级 ``wrong_annotations`` 映射（key=题号，与 question_notes 平级）：
  ``{"1": {"text": "错因：……", "source": "ai"|"manual", "edited": bool, "generated_at": "…"}}``
- 生成：学生/标准答案文本齐全走文本 LLM；缺失（百度路径）按 bbox 裁图走 VL，复用错题库分析。
- 生成失败静默留空，老师可手写或点重生成；已 edited / manual 的条目重生成不覆盖。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# 需要自动生成批注的判定结果（未作答不生成：没什么可解释）
_AUTO_RESULTS = ("错", "半对")


def normalize_wrong_annotations(raw: Any) -> dict:
    """把前端回传/历史存储的 wrong_annotations 规整成标准形状（过滤垃圾键值）。"""
    out: dict[str, dict] = {}
    if not isinstance(raw, dict):
        return out
    for key, val in raw.items():
        k = str(key or "").strip()
        if not k or not isinstance(val, dict):
            continue
        text = str(val.get("text") or "").strip()
        source = str(val.get("source") or "manual").strip().lower()
        if source not in ("ai", "manual"):
            source = "manual"
        out[k] = {
            "text": text,
            "source": source,
            "edited": bool(val.get("edited", source == "manual")),
            "generated_at": str(val.get("generated_at") or ""),
        }
    return out


def question_key_of(block: dict) -> str:
    """题号 key：与前端 questionKeyOf 规则一致（index → label 数字前缀 → slot_id）。"""
    idx = block.get("index")
    if idx is not None and str(idx).strip() and str(idx).strip() != "None":
        return str(idx).strip()
    label = str(block.get("label") or "").strip()
    if label:
        m = re.match(r"^(\d+)", label)
        if m:
            return m.group(1)
        return label
    return str(block.get("slot_id") or "").strip()


def _block_result(block: dict) -> str:
    """统一取判定：AI 引擎是 result（对|错|未作答|半对），手动卷是 status（correct|wrong|…）。"""
    res = str(block.get("result") or "").strip()
    if res:
        return res
    status = str(block.get("status") or "").strip().lower()
    return {
        "correct": "对",
        "wrong": "错",
        "partial": "半对",
        "unanswered": "未作答",
    }.get(status, "")


def collect_wrong_question_groups(blocks: list) -> dict[str, dict]:
    """按题聚合错/半对的题，收集生成所需文本。key=题号。"""
    groups: dict[str, dict] = {}
    for blk in blocks or []:
        if not isinstance(blk, dict):
            continue
        result = _block_result(blk)
        if result not in _AUTO_RESULTS:
            continue
        key = question_key_of(blk)
        if not key:
            continue
        g = groups.setdefault(
            key,
            {
                "question_content": "",
                "student_answer": "",
                "correct_answer": "",
                "comment": "",
                "result": result,
                "bbox": None,
            },
        )
        # 同题多空：半对优先于错（更精确描述）
        if result == "半对" or g["result"] != "半对":
            g["result"] = result
        for field, alt in (
            ("question_content", "stem_text"),
            ("student_answer", "answer_text"),
            ("correct_answer", "interpretation_text"),
        ):
            val = str(blk.get(field) or blk.get(alt) or "").strip()
            if val and not g[field]:
                g[field] = val
        comment = str(blk.get("comment") or "").strip()
        if comment and not g["comment"]:
            g["comment"] = comment
        bbox = blk.get("bbox")
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4 and g["bbox"] is None:
            g["bbox"] = list(bbox)
    return groups


_ANNOTATION_PROMPT = """你是一名中小学教师助手。下面这道题学生被判「{result}」，请写一句给学生看的错因批注，说明为什么错、该怎么改。

题目：{question_content}
学生作答：{student_answer}
参考答案：{correct_answer}
机器评语：{comment}

要求：
1. 用中文，一句话，60字以内，口语化、面向学生。
2. 判「错」以「错因：」开头；判「半对」以「半对：」开头，说明哪里不完整或不规范。
3. 只输出这句话本身，不要引号、序号或解释。
"""


def _strip_wrapping(text: str) -> str:
    """去掉模型偶尔加的引号/Markdown 包裹。"""
    out = str(text or "").strip()
    out = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", out).strip()
    if len(out) >= 2 and out[0] == out[-1] and out[0] in ("「", "\"", "'", "“", "‘"):
        out = out[1:-1].strip()
    return out


def generate_wrong_annotation_text(
    *,
    question_content: str,
    student_answer: str,
    correct_answer: str,
    result: str,
    comment: str = "",
) -> str:
    """文本 LLM 生成一句错因批注；失败返回空串（调用方静默处理）。"""
    from openai import OpenAI

    from app.database import SessionLocal
    from app.utils.qwen_settings import get_llm_config, get_llm_thinking_extra

    # 必须带 db 会话：LLM key 存在 SystemSettings 里，不传 db 只读 env，key 为空会静默失败
    db = SessionLocal()
    try:
        base_url, api_key, model = get_llm_config(db)
    finally:
        db.close()
    if not api_key:
        return ""
    prompt = _ANNOTATION_PROMPT.format(
        result=result or "错",
        question_content=question_content or "（未识别到题干）",
        student_answer=student_answer or "（未识别到学生作答）",
        correct_answer=correct_answer or "（无标准答案）",
        comment=comment or "（无）",
    )
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
            extra_body=get_llm_thinking_extra(base_url),
        )
        return _strip_wrapping(completion.choices[0].message.content or "")
    except Exception:
        return ""


def generate_wrong_annotation_from_images(
    *,
    question_image_path: str,
    answer_image_path: str,
    record: dict,
) -> str:
    """文本缺失时（百度路径）裁图走 VL 复用错题库分析，取错因+讲解合成一句。"""
    from app.grading.wrong_question_db import _analyze_wrong_question_with_vl

    analysis = _analyze_wrong_question_with_vl(record, question_image_path, answer_image_path)
    if str(analysis.get("status") or "") != "done":
        return ""
    reason = str(analysis.get("error_reason") or "").strip()
    explanation = str(analysis.get("explanation") or "").strip()
    prefix = "半对：" if str(record.get("status") or "") == "半对" else "错因："
    parts = [p for p in (reason, explanation) if p]
    if not parts:
        return ""
    text = parts[0] if len(parts) == 1 else f"{parts[0]}；{parts[1]}"
    return _strip_wrapping(f"{prefix}{text}" if not text.startswith(("错因", "半对")) else text)


def _crop_paths_for_group(group: dict, source_image_path: str) -> tuple[str, str]:
    """按题 bbox 从批改原图裁出题目区/作答区临时图（失败返回空串走文本兜底）。"""
    if not source_image_path or not Path(source_image_path).is_file():
        return "", ""
    bbox = group.get("bbox")
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return "", ""
    try:
        from PIL import Image

        from app.grading.wrong_question_db import _safe_asset_stem

        img = Image.open(source_image_path).convert("RGB")
        w, h = img.size
        x0, y0, x1, y1 = (int(float(v)) for v in bbox[:4])
        pad = max(20, int(min(w, h) * 0.03))
        x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
        x1, y1 = min(w, x1 + pad), min(h, y1 + pad)
        if x1 <= x0 or y1 <= y0:
            return "", ""
        crop = img.crop((x0, y0, x1, y1))
        from app.grading.user_paths import modify_dir

        stem = _safe_asset_stem(f"wa_{group.get('key') or 'q'}")
        q_path = Path(modify_dir()) / f"{stem}_wa_question.jpg"
        crop.save(str(q_path), quality=92)
        return str(q_path), str(q_path)  # 同一张图：题目+作答同框，够 VL 参考
    except Exception:
        return "", ""


def generate_wrong_annotations_for_blocks(
    blocks: list,
    *,
    source_image_path: str = "",
    existing: Optional[dict] = None,
    only_keys: Optional[set] = None,
) -> dict[str, dict]:
    """为一批 blocks 里的错/半对题生成批注；existing 里 edited/manual 的条目不覆盖。

    返回增量映射 ``{题号: annotation}``（只含本次生成成功的）。
    """
    groups = collect_wrong_question_groups(blocks)
    if only_keys is not None:
        groups = {k: v for k, v in groups.items() if k in only_keys}
    if not groups:
        return {}
    existing = normalize_wrong_annotations(existing)
    generated: dict[str, dict] = {}
    now = datetime.now().isoformat(timespec="seconds")
    for key, group in groups.items():
        prev = existing.get(key)
        if prev and (prev.get("edited") or prev.get("source") == "manual"):
            continue  # 老师改过/手写的不覆盖
        text = generate_wrong_annotation_text(
            question_content=group["question_content"],
            student_answer=group["student_answer"],
            correct_answer=group["correct_answer"],
            result=group["result"],
            comment=group["comment"],
        )
        if not text:
            # 文本不足或 LLM 失败：裁图走 VL（百度路径兜底）
            has_text = bool(group["student_answer"] or group["correct_answer"] or group["comment"])
            if not has_text and source_image_path:
                q_path, a_path = _crop_paths_for_group({**group, "key": key}, source_image_path)
                if q_path:
                    text = generate_wrong_annotation_from_images(
                        question_image_path=q_path,
                        answer_image_path=a_path,
                        record={
                            "display_title": group["question_content"],
                            "status": group["result"],
                            "reason": group["comment"],
                        },
                    )
        if text:
            generated[key] = {
                "text": text,
                "source": "ai",
                "edited": False,
                "generated_at": now,
            }
    return generated
