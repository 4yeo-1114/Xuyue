# -*- coding: utf-8 -*-
"""整卷总分（卷盒总分）合并与正反面语义（客户清单 #7「正反卷总分自动汇总合并」）。

一个学生一个卷盒（张三），正反面/多页拆成多个文件（张三_1.jpg=正面、张三_2.jpg=反面）。
合并口径与前端 computeBoxScoreGrade 完全一致：

  - 智能/参照/自主阅卷（sum）：每页独立计分 → 整卷总分 = 各页 score_total 累加
  - 作文批改（max）：score_total 是整卷总分，多页重复写同一总分 → 取最大值，不累加

同一卷盒若同时出现两类条目（同一份卷子两种通道都批过），作文整卷总分视为权威
（它本身就涵盖整面卷子），忽略逐页求和的通道条目。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Optional, Tuple

# 与 grading.router._paper_box_display_name / ImportScoresDialog.paperBoxName 同口径
_PAPER_BOX_RE = re.compile(r"^(?P<name>.+)_\d+$")
_PAGE_NO_RE = re.compile(r"^.+_(?P<page>\d+)$")

MERGE_SUM = "sum"
MERGE_MAX = "max"

SIDE_FRONT = "front"
SIDE_BACK = "back"
SIDE_EXTRA = "extra"

_SIDE_LABELS = {SIDE_FRONT: "正面", SIDE_BACK: "反面", SIDE_EXTRA: "附页"}


def paper_box_display_name(filename: str) -> str:
    """张三_1.jpg → 张三（卷盒名=去掉页码后缀的文件名）。"""
    stem = Path(str(filename or "")).stem
    match = _PAPER_BOX_RE.match(stem)
    return (match.group("name") if match else stem) or ""


def paper_box_page_no(filename: str) -> int:
    """张三_2.jpg → 2；无页号后缀按第 1 页。"""
    stem = Path(str(filename or "")).stem
    match = _PAGE_NO_RE.match(stem)
    if not match:
        return 1
    try:
        return max(1, int(match.group("page")))
    except Exception:
        return 1


def page_side(page_no: int) -> str:
    """页号 → 正反面语义：1=正面、2=反面、3 起=附页。"""
    try:
        n = int(page_no)
    except Exception:
        n = 1
    if n <= 1:
        return SIDE_FRONT
    if n == 2:
        return SIDE_BACK
    return SIDE_EXTRA


def page_side_label(page_no: int) -> str:
    """中文标签：正面 / 反面 / 附页。"""
    return _SIDE_LABELS[page_side(page_no)]


def merge_mode_for_engine(engine: Optional[str]) -> str:
    """作文通道整卷计分取最大值；其余通道逐页计分累加。"""
    return MERGE_MAX if str(engine or "").strip().lower() == "essay" else MERGE_SUM


def merge_score_values(values: Iterable[Optional[float]], mode: str) -> Optional[float]:
    """按口径合并各页分数；无任何有效分返回 None。保留 2 位小数（与前端一致）。"""
    nums = [float(v) for v in values if v is not None]
    if not nums:
        return None
    total = max(nums) if mode == MERGE_MAX else sum(nums)
    return round(total + 0.0, 2)


def build_box_totals(entries: Iterable[Tuple[str, Any, str]]) -> dict:
    """(文件名, score_total, mode) 流 → {卷盒名: 整卷总分明细}。

    返回结构（供持久化字段 box_totals 用）：
      {
        "张三": {
          "student": "张三",
          "total": 100.0,            # 整卷总分（None=尚无有效分）
          "merge": "sum",            # 合并口径 sum|max
          "pages": [                 # 按页号排序的正反面明细
            {"name": "张三_1.jpg", "page_no": 1, "side": "front", "side_label": "正面", "score": 40.0},
            {"name": "张三_2.jpg", "page_no": 2, "side": "back",  "side_label": "反面", "score": 60.0},
          ],
        },
      }
    """
    pages_by_box: dict[str, list] = {}
    for filename, raw, mode in entries:
        name = str(filename or "")
        if not name:
            continue
        box = paper_box_display_name(name)
        if not box:
            continue
        score: Optional[float]
        try:
            score = None if raw is None else float(raw)
        except (TypeError, ValueError):
            score = None
        pages_by_box.setdefault(box, []).append(
            {
                "name": name,
                "page_no": paper_box_page_no(name),
                "side": page_side(paper_box_page_no(name)),
                "side_label": page_side_label(paper_box_page_no(name)),
                "score": score,
                "mode": MERGE_MAX if str(mode or "").strip().lower() == MERGE_MAX else MERGE_SUM,
            }
        )

    totals: dict = {}
    for box, pages in pages_by_box.items():
        pages.sort(key=lambda p: (p["page_no"], p["name"]))
        # 作文整卷总分权威：同盒有 max 条目则只在 max 条目里取最大；否则逐页累加
        max_vals = [p["score"] for p in pages if p["mode"] == MERGE_MAX and p["score"] is not None]
        sum_vals = [p["score"] for p in pages if p["mode"] == MERGE_SUM and p["score"] is not None]
        if max_vals:
            total = merge_score_values(max_vals, MERGE_MAX)
            merge = MERGE_MAX
        elif sum_vals:
            total = merge_score_values(sum_vals, MERGE_SUM)
            merge = MERGE_SUM
        else:
            total = None
            merge = MERGE_SUM
        totals[box] = {
            "student": box,
            "total": total,
            "merge": merge,
            "pages": [
                {
                    "name": p["name"],
                    "page_no": p["page_no"],
                    "side": p["side"],
                    "side_label": p["side_label"],
                    "score": p["score"],
                }
                for p in pages
            ],
        }
    return totals
