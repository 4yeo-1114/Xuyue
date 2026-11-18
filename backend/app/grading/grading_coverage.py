# -*- coding: utf-8 -*-
"""批改覆盖率 / 判定原子性（客户反馈：第14题 10/10 学生都没有任何判定标记）。

背景
----
`_build_blocks` / `_summarize_result_text` 的口径是「没判过的题不进结果」——这对
切题碎片是对的（防造假「错」行），但对**正题**是灾难：标准卷有第 14 题，学生卷
却没吐出它的任何块，于是第 14 题既不进明细、也不进统计、也不报错，10/10 个学生
都静默缺题。另一类是「块在、判定空」：块产出了但 status/result 全空（判分没落、
VL 没回、闸门跳过了回填），前端看到一行没有任何对错标记，同样没人知道。

本模块只做**统计与显式标记**，纯逻辑、无 IO：
  - expected_question_numbers：标准卷「应有题号」
  - judged_question_numbers：批改块里「每题判定情况」
  - coverage_report：应有 vs 实有 vs 已判的覆盖率报告
  - ensure_atomicity：把未判定/缺题**就地**标成显式「待确认 + needs_review」，
    并把缺题说明以 actions 形式返回给调用方（打日志 / 前端提示）

绝不静默：任何「未判定」都必须留下可见痕迹。

题号口径
--------
- standard_questions 元素可以是 VlmQuestion（有 printed_no / display_index）、
  任意带同名属性的对象，或 dict（raw 切题条目，同名字段）。printed_no 为空或
  解析不出时退回 display_index。
- blocks 的题号取 block["index"]（`_build_blocks` 里就是 q.display_index，即
  切题审查后的「第N题」），缺失时依次退回 printed_no → baidu_real_name。
- 调用方请用**同一份标准卷**的切题结果同时生成 expected 与 blocks，保证两边题号
  同口径；否则会误报缺题（题号来自两张表，模块无法也无权替你对齐）。
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Optional

__all__ = [
    "expected_question_numbers",
    "judged_question_numbers",
    "coverage_report",
    "ensure_atomicity",
]

# 与 answer_key_grading._CODE_TO_STATUS / reference_vlm_grading.RESULT_TEXT 同口径：
# 1=对 2=错 3=未作答 4=半对 5=待确认
_CODE_TO_STATUS = {1: "correct", 2: "wrong", 3: "unanswered", 4: "partial", 5: "pending"}

# 英文状态 → 归一状态。ungraded/空 = 未判定（不是「已判成某个值」）。
_STATUS_ALIASES = {
    "correct": "correct",
    "right": "correct",
    "wrong": "wrong",
    "incorrect": "wrong",
    "partial": "partial",
    "unanswered": "unanswered",
    "blank": "unanswered",
    "pending": "pending",
    "ungraded": "ungraded",
    "unjudged": "ungraded",
    "needs_review": "pending",
}

# 中文 result → 归一状态。注意「半对（0.6）」这类比例后缀，用前缀匹配。
_RESULT_PREFIXES = (
    ("对", "correct"),
    ("正确", "correct"),
    ("错", "wrong"),
    ("错误", "wrong"),
    ("半对", "partial"),
    ("部分对", "partial"),
    ("未作答", "unanswered"),
    ("未答", "unanswered"),
    ("空白", "unanswered"),
    ("待确认", "pending"),
    ("待人工", "pending"),
    ("待批", "pending"),
    ("未批", "ungraded"),
)

_NUM_RE = re.compile(r"\d+")

_UNJUDGED_REASON = "该题未产出判定，请人工确认"
_MISSING_REASON = "标准卷有此题，但批改块中没有该题任何块，可能切题/投影失配，请人工确认"


# ── 小工具 ────────────────────────────────────────────────────────────────


def _field(obj: Any, name: str) -> Any:
    """对象属性 / dict 同名字段两形态取值；没有就 None。"""
    if obj is None:
        return None
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


def _pos_int(value: Any) -> Optional[int]:
    """宽松转正整数：14 / "14" / " 14 " / "第14题" → 14；空/0/负数/乱码 → None。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = int(value)
        return number if number > 0 else None
    match = _NUM_RE.search(str(value).strip())
    if not match:
        return None
    number = int(match.group(0))
    return number if number > 0 else None


def _question_no_for_standard(q: Any) -> Optional[int]:
    return _pos_int(_field(q, "printed_no")) or _pos_int(_field(q, "display_index"))


def _question_no_for_block(block: Mapping) -> Optional[int]:
    return (
        _pos_int(block.get("index"))
        or _pos_int(block.get("printed_no"))
        or _pos_int(block.get("baidu_real_name"))
    )


def _normalize_status(block: Mapping) -> Optional[str]:
    """块判定状态 → correct/wrong/partial/unanswered/pending/ungraded（未判定）。

    优先级：status > result > baidu_correct_result 码（与 response_log_db 同序）。
    返回 None 表示这个块既不是判定、也不是可识别的「未判定」——按未判定处理。
    """
    raw = block.get("status")
    if isinstance(raw, str) and raw.strip():
        token = raw.strip().lower()
        if token in _STATUS_ALIASES:
            return _STATUS_ALIASES[token]
        # 未知英文状态：交回中文/码兜底，再兜不住就是未判定（宁可报出来）

    result = str(block.get("result") or "").strip().lower()
    if result:
        for en, normalized in _STATUS_ALIASES.items():
            if result == en:
                return normalized
        for prefix, normalized in _RESULT_PREFIXES:
            if result.startswith(prefix):
                return normalized
        # 有文本但认不出（如自定结果文案）：算「有判定」，不当缺批误报
        return "other"

    code = block.get("baidu_correct_result")
    if code is not None and not isinstance(code, bool):
        try:
            return _CODE_TO_STATUS.get(int(code))
        except (TypeError, ValueError):
            pass

    return None


def _is_unjudged(normalized: Optional[str]) -> bool:
    return normalized in (None, "ungraded")


def _is_judged(normalized: Optional[str]) -> bool:
    # pending 是「交人工」不是「没判」：它必须可见，但不算覆盖到了
    return normalized in ("correct", "wrong", "partial", "unanswered", "other")


# ── API ──────────────────────────────────────────────────────────────────


def expected_question_numbers(standard_questions) -> list[int]:
    """从标准卷切题结果里取出「应有题号」列表（去重、升序）。

    standard_questions 元素可能是对象（有 printed_no / display_index 属性）
    或 dict（同名字段）。printed_no 为空/解析不出时退回 display_index。
    解析不出题号的碎片条目不进表（防误报缺题）。
    """
    numbers: set[int] = set()
    for item in standard_questions or []:
        number = _question_no_for_standard(item)
        if number is not None:
            numbers.add(number)
    return sorted(numbers)


def judged_question_numbers(blocks) -> dict[int, dict]:
    """从批改结果 blocks 里统计每题判定情况。

    返回 {题号: {"total": 槽数, "judged": 已判定槽数, "pending": 待确认槽数,
                 "statuses": {归一状态: 槽数}}}
    判定状态取自 block["status"]（correct/wrong/partial/unanswered）或
    block["result"]（对/错/半对/未作答/待确认），再兜底 baidu_correct_result 码。
    「对/错/半对/未作答」算已判定；「待确认」单列；空 / ungraded 算未判定。
    没有题号的块（切题碎片）不进统计。
    """
    summary: dict[int, dict] = {}
    for block in blocks or []:
        if not isinstance(block, Mapping):
            continue
        number = _question_no_for_block(block)
        if number is None:
            continue
        status = _normalize_status(block) or "ungraded"
        entry = summary.setdefault(
            number, {"total": 0, "judged": 0, "pending": 0, "statuses": {}}
        )
        entry["total"] += 1
        entry["statuses"][status] = entry["statuses"].get(status, 0) + 1
        if status == "pending":
            entry["pending"] += 1
        elif _is_judged(status):
            entry["judged"] += 1
    return summary


def coverage_report(standard_questions, blocks) -> dict:
    """产出覆盖率报告：

    {
      "expected": [题号...],          # 标准卷应有题号
      "appeared": [题号...],          # 批改块里出现过的题号（升序）
      "judged":   [题号...],          # 至少有一个槽产出判定的题号
      "missing":  [应有但完全没出现的题号],      # 第14题这类
      "unexpected": [出现了但标准卷没有的题号],  # 题号口径不一致的线索
      "unjudged": [出现了但没有任何判定结果的题号],  # 纯待确认不算（见下）
      "pending":  [判为待确认的题号],
      "stats": {"expected": n, "judged": k, "missing": m, "unjudged": u,
                "pending": p, "appeared": a, "unexpected": x,
                "coverage": 已判题数/应有题数}
    }

    coverage 分母只数**应有**题号（标准卷没这题、块里冒出来的不算覆盖），
    取值 0.0~1.0，保留 4 位小数；标准卷为空时记 1.0（没有「应有」可言）。
    """
    expected = expected_question_numbers(standard_questions)
    per_question = judged_question_numbers(blocks)
    appeared = sorted(per_question)

    expected_set = set(expected)
    missing = [number for number in expected if number not in per_question]
    unexpected = [number for number in appeared if number not in expected_set]
    # 纯待确认不算 unjudged：它已有可见判定（交人工），只是没覆盖到答案——
    # 已经在缺批里报出来了，再重复报「没有判定」会让两个口径互相污染。
    unjudged = [
        number
        for number in appeared
        if per_question[number]["total"] > 0
        and per_question[number]["judged"] == 0
        and per_question[number]["pending"] == 0
    ]
    pending = [
        number for number in appeared if per_question[number]["pending"] > 0
    ]
    judged = [number for number in appeared if per_question[number]["judged"] > 0]

    judged_expected = sum(1 for number in expected if number in set(judged))
    coverage = (judged_expected / len(expected)) if expected else 1.0

    return {
        "expected": expected,
        "appeared": appeared,
        "judged": judged,
        "missing": missing,
        "unexpected": unexpected,
        "unjudged": unjudged,
        "pending": pending,
        "stats": {
            "expected": len(expected),
            "judged": len(judged),
            "missing": len(missing),
            "unjudged": len(unjudged),
            "pending": len(pending),
            "appeared": len(appeared),
            "unexpected": len(unexpected),
            "coverage": round(coverage, 4),
        },
    }


def _append_reason(block: dict, text: str) -> None:
    """reason 追加说明（幂等：已含该句就不重复追加）；comment/analysis 同步，供展示。"""
    reason = str(block.get("reason") or "").strip()
    if text in reason:
        return
    block["reason"] = f"{reason}；{text}" if reason else text
    # analysis 是 comment 的落库字段（_build_blocks 同口径），有则同步
    if "analysis" in block:
        block["analysis"] = block["reason"]


def ensure_atomicity(blocks, report) -> list[dict]:
    """对「未判定 / 缺题」的题目做显式标记，绝不静默。

    - 已出现但未判定（status 空 / ungraded）的块（含一题多槽里部分未判的槽）：
      block["needs_review"]=True、block["read_uncertain"]=True、
      block["result"]="待确认"、block["reason"] 追加「该题未产出判定，请人工确认」；
      同一条说明也写进 actions（action="mark_unjudged"）。
    - report 里 missing 的题号没有块可标：产出
      {"index": 题号, "action": "missing_question", "reason": ...}
      供调用方写日志 / 前端提示（action="missing_question"）。

    就地修改 blocks；返回 actions 列表（便于打印日志）。重复调用幂等。
    无题号的切题碎片块不在 blocks 里也不标（`_build_blocks` 同口径，防造假行），
    它们的缺失由 missing 题号说明覆盖。
    """
    actions: list[dict] = []

    for block in blocks or []:
        if not isinstance(block, Mapping):
            continue
        if not _is_unjudged(_normalize_status(block)):
            continue
        number = _question_no_for_block(block)
        if number is None:
            # 无题号的切题碎片：_build_blocks 故意不把它摊成结果行，这里也不许
            # 把它「救」成一行假「待确认」。真正的缺失由 missing 分支报。
            continue
        # 就地修改：只对真正的 dict 生效（Mapping 只读实现不改，仍记 action）
        if isinstance(block, dict):
            block["needs_review"] = True
            block["read_uncertain"] = True
            block["result"] = "待确认"
            _append_reason(block, _UNJUDGED_REASON)
        actions.append(
            {
                "index": number,
                "sub_index": _pos_int(block.get("sub_index")),
                "action": "mark_unjudged",
                "reason": _UNJUDGED_REASON,
            }
        )

    for number in (report or {}).get("missing") or []:
        actions.append(
            {
                "index": number,
                "action": "missing_question",
                "reason": _MISSING_REASON,
            }
        )

    return actions
