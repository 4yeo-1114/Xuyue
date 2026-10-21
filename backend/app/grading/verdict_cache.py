# -*- coding: utf-8 -*-
"""判分缓存（C 项：同（题, 作答）二次出现直接复用判分，人工修正为最高优先级判据）。

键 = question_fingerprint(subject, question_type, question_content, correct_answer)
   + ":" + text_fingerprint(student_answer)。

红线（cache_key 先行拦截，比计划更严）：
- question_content / correct_answer / student_answer **任一为空 → None**——
  空身份文本同键必串判（多槽拼接文本互串是历史坑，见
  reference_vlm_grading._answer_text_for_slot 宁缺勿串）；
- 带 form_guard.suspicious / form_guard downgraded / ink_evidence 痕迹的
  **AI** 判分不入缓存（幻觉不入缓存，防全班放大）；source="human" 例外——
  人工终态是最高判据，幻觉被老师推翻后正应进缓存（飞轮）；
- human 可覆盖 ai 行；ai 永不覆盖 human 行。

v1 范围（诚实声明）：aliyun 全链路（预查+回写）；answer_key 选择题（预查+回写）；
answer_key 主观/填空只写不查（student_answer 是同一次 VL 调用产出）；
smart_ref/baidu 不进缓存（块无文本）。

env：VERDICT_CACHE=1 开启（默认关）——真卷回放比对开/关一致率后再开。
缓存永远可弃：任何 DB 异常 → 当作未命中/未写入，绝不阻断批改。
"""
from __future__ import annotations

import os
from typing import Any, Optional

from app.database import SessionLocal
from app.grading.form_guard import _norm_result
from app.grading.response_log_db import _text_or_none
from app.models.verdict_cache import VerdictCache
from app.utils.question_fingerprint import question_fingerprint, text_fingerprint

_RESULTS = ("对", "错", "半对", "未作答")


def _env_flag(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "off", "no", "disabled")


def cache_enabled() -> bool:
    """env 开关 VERDICT_CACHE（默认关）。"""
    return _env_flag("VERDICT_CACHE", False)


def cache_key(
    subject: Any,
    question_type: Any,
    question_content: Any,
    correct_answer: Any,
    student_answer: Any,
) -> Optional[str]:
    """算缓存键；身份文本三缺一 → None（不缓存不命中，安全红线）。

    ⛔ list 型文本先 join（_text_or_none）：str(list) 会把 "['x']" 污染进键。
    """
    q_text = _text_or_none(question_content)
    c_text = _text_or_none(correct_answer)
    s_text = _text_or_none(student_answer)
    if not q_text or not c_text or not s_text:
        return None
    q_fp = question_fingerprint(
        str(subject or "").strip() or None,
        str(question_type or "").strip() or None,
        q_text,
        c_text,
    )
    return f"{q_fp}:{text_fingerprint(s_text)}"


def block_cache_key(block: dict, subject: Any = None) -> Optional[str]:
    """从批改块算缓存键（字段兜底对齐 _row_from_block）；缺身份文本返回 None。"""
    if not isinstance(block, dict):
        return None
    return cache_key(
        subject if subject is not None else block.get("subject"),
        block.get("question_type"),
        block.get("question_content") or block.get("question") or block.get("question_text"),
        block.get("correct_answer") or block.get("expected_answer"),
        block.get("student_answer"),
    )


def _has_guard_trace(block: dict) -> bool:
    """块是否带兜底/复核痕迹（幻觉嫌疑，AI 判分不得入缓存）。"""
    guard = block.get("form_guard")
    if isinstance(guard, dict) and (guard.get("action") == "downgraded" or guard.get("suspicious")):
        return True
    return isinstance(block.get("ink_evidence"), dict)


def lookup_block(block: dict, subject: Any = None) -> Optional[dict]:
    """单块查缓存（answer_key 选择题预查用）；键缺失/未命中返回 None。"""
    key = block_cache_key(block, subject)
    if not key:
        return None
    return lookup_many([key]).get(key)


def decision_status_from_result(result: Any) -> Optional[str]:
    """对/错/半对/未作答 → manual status 英文值（缓存命中合成 decisions 用）。"""
    return {
        "对": "correct",
        "错": "wrong",
        "半对": "partial",
        "未作答": "unanswered",
    }.get(_norm_result(result))


def lookup_many(keys: list) -> dict:
    """批量查缓存：返回 {key: {result, comment, partial_ratio, source, subject_family}}。

    命中行 hit_count += 1（轻 UPDATE，失败不影响返回）。任何异常 → {}（当未命中）。
    """
    if not cache_enabled():
        return {}
    wanted = [str(k) for k in (keys or []) if k]
    if not wanted:
        return {}
    db = SessionLocal()
    try:
        rows = db.query(VerdictCache).filter(VerdictCache.cache_key.in_(wanted)).all()
        found: dict = {}
        for row in rows:
            found[row.cache_key] = {
                "result": row.result,
                "comment": row.comment,
                "partial_ratio": row.partial_ratio,
                "source": row.source,
                "subject_family": row.subject_family,
            }
            try:
                row.hit_count = int(row.hit_count or 0) + 1
            except (TypeError, ValueError):
                row.hit_count = 1
        try:
            db.commit()
        except Exception:
            db.rollback()
        return found
    except Exception:
        return {}
    finally:
        db.close()


def store_blocks(
    blocks: list,
    subject: Any,
    engine: str,
    source: str,
    subject_family: Any = None,
) -> int:
    """把判分块写入缓存；返回写入/更新行数。

    - 跳过 cache_key 为 None 的块（身份文本红线）；
    - AI 判分跳过带 form_guard/ink_evidence 痕迹的块；human 例外（人工终态优先）；
    - human 可覆盖 ai 行；ai 永不覆盖 human 行；
    - 未知判分文本不入缓存。
    """
    if not cache_enabled():
        return 0
    is_human = str(source or "").strip() == "human"
    pending: dict = {}
    for blk in blocks or []:
        if not isinstance(blk, dict):
            continue
        if not is_human and _has_guard_trace(blk):
            continue
        key = block_cache_key(blk, subject)
        if not key:
            continue
        result = _norm_result(blk.get("result"))
        if result not in _RESULTS:
            continue
        comment = str(blk.get("comment") or "").strip() or None
        partial = blk.get("partial_ratio")
        try:
            partial = float(partial) if partial is not None else None
        except (TypeError, ValueError):
            partial = None
        pending[key] = {
            "question_fingerprint": key.split(":", 1)[0],
            "student_answer_hash": key.split(":", 1)[1],
            "result": result,
            "comment": comment,
            "partial_ratio": partial,
            "source": "human" if is_human else "ai",
            "subject_family": str(blk.get("subject_family") or subject_family or "").strip() or None,
            "engine": str(engine or "").strip() or None,
        }
    if not pending:
        return 0
    db = SessionLocal()
    written = 0
    try:
        existing = {
            row.cache_key: row
            for row in db.query(VerdictCache).filter(VerdictCache.cache_key.in_(list(pending.keys()))).all()
        }
        for key, data in pending.items():
            row = existing.get(key)
            if row is None:
                db.add(VerdictCache(cache_key=key, hit_count=0, **data))
                written += 1
                continue
            if not is_human and row.source == "human":
                continue  # ai 永不覆盖 human 行
            row.result = data["result"]
            row.comment = data["comment"]
            row.partial_ratio = data["partial_ratio"]
            row.source = data["source"]
            if data["subject_family"]:
                row.subject_family = data["subject_family"]
            written += 1
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"判分缓存写入失败: {e}")
    finally:
        db.close()
    return written
