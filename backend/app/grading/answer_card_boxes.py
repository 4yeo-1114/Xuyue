"""按印刷框线检测答题卡作答区（不依赖百度 OCR 切题）。

背景：百度 paper_cut_edu 是「试卷切题」OCR，按题干文字去猜作答区，用于有印刷框线
的标准答题卡时会漏题（如空白的填空题）、把 2B 涂卡选择题切成凌乱手写小块。本模块
直接用图像处理检测答题卡的印刷框线，重建各栏作答区：

- 竖长线 -> 栏（列）边界；
- 每栏内横跨整栏的横线 -> 作答框边界；
- 选择题栏内的气泡网格 -> 按「题组 × 行」拆成每道客观题。

仅依赖 numpy + PIL（项目里未装 OpenCV/scipy）。
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
from PIL import Image


def _load_dark(image_path: str):
    im = Image.open(image_path).convert("L")
    a = np.asarray(im)
    H, W = a.shape
    small = np.asarray(im.resize((max(1, W // 20), max(1, H // 20)))).astype(np.float32)
    bg = np.asarray(
        Image.fromarray(np.clip(small, 0, 255).astype(np.uint8)).resize((W, H))
    ).astype(np.float32)
    dark = a.astype(np.float32) < (bg - 18)
    return dark, H, W


def _runs(arr, mn: int):
    """arr 为 bool 数组，返回所有长度 >= mn 的连续 True 段 (start, end)。"""
    rl = np.diff(np.concatenate(([0], arr.astype(np.int8), [0])))
    st = np.where(rl == 1)[0]
    en = np.where(rl == -1)[0]
    return [(int(s), int(e)) for s, e in zip(st, en) if e - s >= mn]


def _cluster(segs, gap: int):
    """segs: [(coord, start, end), ...]，按 coord 聚类（间距 <= gap），合并范围。"""
    segs = sorted(segs)
    out: list[tuple[int, int, int]] = []
    for v, s, e in segs:
        if out and v - out[-1][0] <= gap:
            o = out[-1]
            out[-1] = (int((o[0] + v) / 2), min(o[1], s), max(o[2], e))
        else:
            out.append((v, s, e))
    return out


def _detect_columns(dark, H: int, W: int) -> list[tuple[int, int]]:
    """长竖线（>=300px）聚类后，相邻间距 >300px 的区间视为一个栏（列）。"""
    vsegs = []
    for x in range(W):
        for s, e in _runs(dark[:, x], 300):
            vsegs.append((x, s, e))
    vlines = _cluster(vsegs, 15)
    xs = [v[0] for v in vlines]
    return [(xs[i], xs[i + 1]) for i in range(len(xs) - 1) if xs[i + 1] - xs[i] > 300]


def _band_boundaries(dark, H: int, x1: int, x2: int, frac: float = 0.85):
    """横跨整栏（>= frac*栏宽）的横线，作为作答框边界。"""
    w = x2 - x1
    hs = []
    for y in range(H):
        for s, e in _runs(dark[y, x1 + 3 : x2 - 3], int(w * frac)):
            hs.append((y, x1 + 3 + s, x1 + 3 + e))
    return _cluster(hs, 6)


def _subjective_boxes(dark, H: int, x1: int, x2: int) -> list[tuple[int, int]]:
    """主观题栏：相邻框边界之间 >=45px 的区段 = 一道题的作答框。"""
    bl = _band_boundaries(dark, H, x1, x2)
    ys = [v[0] for v in bl]
    boxes = []
    for i in range(len(ys) - 1):
        if ys[i + 1] - ys[i] >= 45:
            boxes.append((ys[i], ys[i + 1]))
    return boxes


def _column_bubble_edges(dark, H: int, x1: int, x2: int) -> list[tuple[int, int, int]]:
    """栏内所有短竖线（12-220px），即气泡/括号的左右边，返回 (x, y1, y2)。"""
    edges = []
    for x in range(x1, x2):
        for s, e in _runs(dark[:, x], 12):
            if e - s <= 220:
                edges.append((x, s, e))
    return _cluster(edges, 6)


def _hlines(dark, H: int, x1: int, x2: int, ry1: int, ry2: int, minlen: int) -> list[int]:
    """区域内所有横线的 y 坐标（聚类后），minlen 为横段最小像素长。"""
    cands = []
    for y in range(ry1, ry2):
        if _runs(dark[y, x1 + 3 : x2 - 3], minlen):
            cands.append(y)
    out: list[int] = []
    for y in sorted(set(cands)):
        if out and y - out[-1] <= 8:
            out[-1] = int((out[-1] + y) / 2)
        else:
            out.append(y)
    return out


def _content_bands(dark, x1: int, x2: int, ry1: int, ry2: int,
                   thr: int = 8, min_gap: int = 8, min_h: int = 10) -> list[tuple[int, int]]:
    """把区域按「行暗像素 > thr」切成内容带，间隙 >= min_gap 才断开，过滤过矮的带。"""
    bands: list[tuple[int, int]] = []
    start = None
    for y in range(ry1, ry2):
        if int(dark[y, x1:x2].sum()) > thr:
            if start is None:
                start = y
        else:
            if start is not None:
                if y - start >= min_h:
                    bands.append((start, y - 1))
                start = None
    if start is not None and ry2 - start >= min_h:
        bands.append((start, ry2 - 1))
    merged: list[tuple[int, int]] = []
    for b in bands:
        if merged and b[0] - merged[-1][1] - 1 < min_gap:
            merged[-1] = (merged[-1][0], b[1])
        else:
            merged.append(b)
    return merged


def _question_starts(dark, x1: int, x2: int, ry1: int, ry2: int) -> list[int]:
    """题号区（左边缘 x1+12..x1+50）从空到内容的跃迁行，即每道印刷题的起始 y。"""
    la, lb = x1 + 12, x1 + 50
    starts: list[int] = []
    empty_run = 0
    for y in range(ry1, ry2):
        if int(dark[y, la:lb].sum()) >= 3:
            if empty_run >= 4 and (y - ry1) > 8:
                starts.append(y)
            empty_run = 0
        else:
            empty_run += 1
    return starts


def _content_column_bands(dark, x1: int, x2: int, ry1: int, ry2: int,
                          thr: int = 8, min_gap: int = 80, min_w: int = 20) -> list[tuple[int, int]]:
    """把区域按「列暗像素 > thr」切成内容列，间隙 >= min_gap 才断开（用于选择题括号分列）。"""
    bands: list[tuple[int, int]] = []
    start = None
    for x in range(x1, x2):
        if int(dark[ry1:ry2, x].sum()) > thr:
            if start is None:
                start = x
        else:
            if start is not None:
                if x - start >= min_w:
                    bands.append((start, x - 1))
                start = None
    if start is not None and x2 - start >= min_w:
        bands.append((start, x2 - 1))
    merged: list[tuple[int, int]] = []
    for b in bands:
        if merged and b[0] - merged[-1][1] - 1 < min_gap:
            merged[-1] = (merged[-1][0], b[1])
        else:
            merged.append(b)
    return merged


def _underline_columns(dark, x1: int, x2: int, ry1: int, ry2: int) -> list[tuple[int, int]]:
    """填空题作答区若是「下划线」（无竖边框），用长横段按 x 中心聚类成列。

    竖线检测会把印刷文字笔画误当边框，只测到宽文字列、漏掉窄空（本例填空题 4 列
    只出 2 列）。这里扫描区域内的长横段（下划线，长度 90~200px，避开整行边框与
    短文字笔画），按 x 中心聚类（间距 <=70px 归并，即同一列内各行的下划线对齐），
    返回各列 x 范围 [(x1, x2), ...]，按 x 排序。
    """
    edge = 6
    segs: list[tuple[int, int]] = []
    for y in range(ry1 + edge, ry2 - edge):
        for s, e in _runs(dark[y, x1 + edge : x2 - edge], 90):
            if e - s >= 200:  # 整行边框不是下划线
                continue
            segs.append((x1 + edge + s, x1 + edge + e))
    if not segs:
        return []
    pts = sorted([((s + e) / 2.0, s, e) for s, e in segs])
    groups: list[list[tuple[float, int, int]]] = []
    for c, s, e in pts:
        if groups and c - groups[-1][-1][0] <= 70:
            groups[-1].append((c, s, e))
        else:
            groups.append([(c, s, e)])
    return [(min(p[1] for p in g), max(p[2] for p in g)) for g in groups]


def _vertical_box_columns(dark, x1: int, x2: int, ry1: int, ry2: int) -> list[tuple[int, int]]:
    """封闭框线型填空：用竖边聚类成列（旧逻辑），返回 [(x1, x2), ...]。"""
    edges = []
    for x in range(x1, x2):
        for s, e in _runs(dark[ry1:ry2, x], 12):
            if e - s <= 220:
                edges.append((x, ry1 + s, ry1 + e))
    vlines = _cluster(edges, 6)
    vlines.sort(key=lambda v: v[0])
    groups: list[list[tuple[int, int, int]]] = []
    for v in vlines:
        if groups and v[0] - groups[-1][-1][0] <= 60:
            groups[-1].append(v)
        else:
            groups.append([v])
    cols = [(min(v[0] for v in g), max(v[0] for v in g)) for g in groups if max(v[0] for v in g) - min(v[0] for v in g) > 80]
    cols.sort(key=lambda c: c[0])
    return cols


def _left_column_questions(dark, H: int, x1: int, x2: int) -> list[tuple[int, int, int, int, bool]]:
    """左栏逐带拆分。返回 [(x1, y1, x2, y2, is_choice), ...]，阅读顺序（列左->右，行上->下）。

    三种带：
    - 高框网格（写答区，框高 >=35px）：填空题 -> 主观（is_choice=False）
    - 括号选项网格（选择题 [A][B][C][D]）：客观（is_choice=True）
    - 空白/文本区（计算/解答）：整带一道主观题
    """
    bl = _band_boundaries(dark, H, x1, x2)
    ys = [v[0] for v in bl]
    regions = [(ys[i], ys[i + 1]) for i in range(len(ys) - 1) if ys[i + 1] - ys[i] >= 80]

    questions: list[tuple[int, int, int, int, bool]] = []
    for ry1, ry2 in regions:
        # 高行（框高 >=35px）
        lines = _hlines(dark, H, x1, x2, ry1, ry2, 80)
        rows_tall = [(lines[i], lines[i + 1]) for i in range(len(lines) - 1) if lines[i + 1] - lines[i] >= 35]

        # 填空列：优先按「下划线」聚类（无竖边框的下划线填空），识别不到再退回竖边检测（封闭框线）
        cols = _underline_columns(dark, x1, x2, ry1, ry2)
        if len(cols) < 2:
            cols = _vertical_box_columns(dark, x1, x2, ry1, ry2)

        if len(cols) >= 2 and len(rows_tall) >= 2:
            # 填空题写答区：题组 × 行 = 每道主观题
            for cx1, cx2 in cols:
                for rtop, rbot in rows_tall:
                    questions.append((cx1, rtop, cx2, rbot, False))
            continue

        # 选择题：内容列（括号选项分列）× 每列内容行；列边界扩展到相邻列中点以补全题号/选项
        cbands = _content_column_bands(dark, x1, x2, ry1, ry2)
        if len(cbands) >= 2:
            for i, (cx1, cx2) in enumerate(cbands):
                ex1 = x1 if i == 0 else (cbands[i - 1][1] + cx1) // 2
                if i + 1 < len(cbands):
                    ex2 = (cx2 + cbands[i + 1][0]) // 2
                else:
                    ex2 = min(x2, cx2 + 45)
                rb = _content_bands(dark, cx1, cx2, ry1, ry2)
                if len(rb) >= 2:
                    for t, b in rb:
                        questions.append((ex1, t, ex2, b, True))
                else:
                    questions.append((ex1, ry1, ex2, ry2, True))
            continue

        # 空白/文本区：整带一道主观题（计算/解答）
        top, bot = ry1, ry2
        for y in range(ry1, ry2):
            if int(dark[y, x1:x2].sum()) > 8:
                if top == ry1:
                    top = y
                bot = y
        questions.append((x1, top, x2, bot, False))
    return questions


def detect_answer_card_boxes(image_path: str) -> dict[str, Any]:
    """检测答题卡框线，返回作答区。

    返回:
      {
        "valid": bool,           # 是否识别为「带印刷框线的多栏答题卡」
        "image_size": [W, H],
        "questions": [           # 按阅读顺序（先左栏、再中/右栏）
            {"bbox": [x1,y1,x2,y2], "kind": "choice"|"subjective"},
            ...
        ],
        "columns": [[x1,x2], ...],
        "reason": str,           # valid=False 时的原因
      }
    """
    dark, H, W = _load_dark(image_path)
    cols = _detect_columns(dark, H, W)
    if len(cols) < 2:
        return {
            "valid": False,
            "image_size": [W, H],
            "questions": [],
            "columns": cols,
            "reason": "未检测到多栏框线",
        }

    questions: list[dict[str, Any]] = []
    for ci, (cx1, cx2) in enumerate(cols):
        if ci == 0:
            # 最左栏逐带分类：写答区=主观，括号选项=客观，文本区=主观
            for x1, y1, x2, y2, is_choice in _left_column_questions(dark, H, cx1, cx2):
                questions.append({"bbox": [x1, y1, x2, y2], "kind": "choice" if is_choice else "subjective"})
        else:
            boxes = _subjective_boxes(dark, H, cx1, cx2)
            questions.extend(
                {"bbox": [cx1, y1, cx2, y2], "kind": "subjective"}
                for y1, y2 in boxes
            )

    if len(questions) < 3:
        return {
            "valid": False,
            "image_size": [W, H],
            "questions": [],
            "columns": cols,
            "reason": f"检测到的作答区过少（{len(questions)} 个）",
        }

    return {
        "valid": True,
        "image_size": [W, H],
        "questions": questions,
        "columns": cols,
        "reason": "",
    }
