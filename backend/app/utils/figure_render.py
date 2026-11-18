# -*- coding: utf-8 -*-
"""题目配图：AI 输出图形规格（figure 字段），代码把图真实画出来配在题下。

口径（1026 用户拍板）：题干需要哪个图就出哪个图；要么就出纯文字题。
- 提示词（FIGURE_POLICY_PROMPT）要求：需要用图的题必须给 figure 规格，
  规格与题干条件完全一致；不用图的题禁止引用任何图/表。
- process_question_figures 是出题链路唯一入口：
    有 figure 且画得出来 → 挂 figure_img（data URL，前端/打印直接用）；
    有 figure 但画不出来 → 剥掉 figure，题干仍在引用图 → 整题丢弃；
    无 figure 但题干引用图 → 剥开头「如图，」救一把，仍引用则整题丢弃。
  保证印在卷子上的题「要么带图，要么本来就不需要图」。

figure 规格（kind 五选一）：
  {"kind":"function","exprs":["x^2-4x+3"],"x_min":-1,"x_max":5,"y_min":-2,"y_max":10}
  {"kind":"geometry","points":{"A":[0,0],"B":[4,0],"C":[2,3]},
   "segments":[["A","B"],["B","C"],["C","A"]],"dashed":[],"circles":[],
   "polygons":[{"points":["A","B","C"],"fill":true}],"angles":[{"vertex":"A","p1":"B","p2":"C","label":"40°"}]}
  {"kind":"bar","categories":["一月","二月"],"values":[12,20]}
  {"kind":"line","categories":["一月","二月"],"values":[12,20]}
  {"kind":"pie","items":[["优",30],["良",40]]}
"""
from __future__ import annotations

import ast
import base64
import io
import logging
import math
import operator
import os
import re
import tempfile
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

# matplotlib 无显示环境 / 只读 HOME 时也要能画（服务器 systemd 环境）
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("MPLCONFIGDIR", tempfile.gettempdir())

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import Arc, Circle, Polygon as MplPolygon  # noqa: E402

from app.utils.exam_math_format import (  # noqa: E402
    question_has_figure_reference,
    strip_figure_leading_ref,
)

logger = logging.getLogger(__name__)


class FigureRenderError(ValueError):
    """figure 规格不合法或画不出来。"""


# ── 出题提示词（两条出题入口共用）────────────────────────────────────────
FIGURE_POLICY_PROMPT = """
【配图出题——必须严格遵守】
系统会按你给的规格把图真实地画出来印在题干下方，所以：
1. 需要看图的题（函数图象、几何图形、统计图表）：必须给 figure 字段输出作图规格，题干里才可以写「如图所示」；规格里的数据、坐标、标注必须与题干文字条件完全一致（图是题干的一部分，学生靠图获取条件）。
2. 不需要图的题：禁止出现「如图」「如下图」「见图」「图中」「如图1」「右图」「左图」「如表」「见表」「表中」等任何引用图/表的字样；几何、函数条件全部用文字写完整（边长、角度、坐标、点线关系）。
3. figure 规格只支持以下 kind，按题目需要选一种：
   - 函数图象：{"kind":"function","exprs":["x^2-4x+3"],"x_min":-1,"x_max":5,"y_min":-2,"y_max":10}
     exprs 是以 x 为变量的表达式（可用 + - * / ^ ( ) 和 sin cos tan sqrt log exp abs pi），一到三条曲线；x_min/x_max 必给；y_min/y_max 可省略（自动取值）。
   - 几何图：{"kind":"geometry","points":{"A":[0,0],"B":[4,0],"C":[2,3]},"segments":[["A","B"],["B","C"],["C","A"]],"dashed":[],"circles":[],"polygons":[],"angles":[]}
     points 点名→坐标（坐标必须与题中边长/角度一致）；segments 实线段（点名对）；dashed 虚线段；circles 形如 [{"center":"O","r":2}]；polygons 形如 [{"points":["A","B","C"],"fill":true}]（fill=阴影部分）；angles 形如 [{"vertex":"A","p1":"B","p2":"C","label":"40°"}]（画角弧并标注）。
   - 条形统计图：{"kind":"bar","categories":["一月","二月","三月"],"values":[12,20,15]}
   - 折线统计图：{"kind":"line","categories":["一月","二月","三月"],"values":[12,20,15]}
   - 扇形统计图：{"kind":"pie","items":[["优",30],["良",40],["及格",20]]}
   可选 "x_label"/"y_label" 给坐标轴命名（如 "时间"/"人数"）。
4. 画不出来的图宁可不要：改出纯文字题（按第 2 条），不要硬凑一个对不上的图。
"""


# ── 中文字体（Windows 微软雅黑/黑体，服务器文泉驿正黑，与 worksheet_pdf 同源）──
_CJK_FONT_CANDIDATES = (
    "Microsoft YaHei",
    "SimHei",
    "SimSun",
    "PingFang SC",
    "WenQuanYi Zen Hei",
    "WenQuanYi Micro Hei",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "Droid Sans Fallback",
)
_font_ready = False


def _setup_cjk_font() -> None:
    global _font_ready
    if _font_ready:
        return
    _font_ready = True
    try:
        names = {f.name for f in font_manager.fontManager.ttflist}
        for cand in _CJK_FONT_CANDIDATES:
            if cand in names:
                plt.rcParams["font.sans-serif"] = [cand, "DejaVu Sans"]
                break
        plt.rcParams["axes.unicode_minus"] = False
    except Exception:  # noqa: BLE001 - 字体探测失败不挡出图（拉丁字母照常）
        pass


# ── 安全求值：函数表达式只认白名单 AST 节点（LLM 输出当不可信输入）─────────
_BIN_OPS: Dict[type, Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: lambda a, b: a / b if b != 0 else float("nan"),
    ast.FloorDiv: lambda a, b: a // b if b != 0 else float("nan"),
    ast.Mod: lambda a, b: a % b if b != 0 else float("nan"),
    ast.Pow: lambda a, b: _safe_pow(a, b),
}
_UNARY_OPS: Dict[type, Callable[[float], float]] = {ast.UAdd: operator.pos, ast.USub: operator.neg}

_FUNCS: Dict[str, Callable[..., float]] = {
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "sqrt": lambda v: math.sqrt(v) if v >= 0 else float("nan"),
    "log": lambda v: math.log(v) if v > 0 else float("nan"),
    "log2": lambda v: math.log2(v) if v > 0 else float("nan"),
    "log10": lambda v: math.log10(v) if v > 0 else float("nan"),
    "exp": math.exp,
    "abs": abs,
    "floor": math.floor,
    "ceil": math.ceil,
    "min": min,
    "max": max,
}
_CONSTS = {"pi": math.pi, "e": math.e}
_expr_cache: Dict[str, ast.Expression] = {}


def _safe_pow(a: float, b: float) -> float:
    try:
        if abs(a) > 1e6 or abs(b) > 64:
            return float("nan")
        return float(a**b)
    except (OverflowError, ValueError):
        return float("nan")


def _eval_node(node: ast.AST, x: float) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, x)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id == "x":
            return x
        if node.id in _CONSTS:
            return _CONSTS[node.id]
        raise FigureRenderError(f"表达式里不允许的变量: {node.id}")
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand, x))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_eval_node(node.left, x), _eval_node(node.right, x))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
        fn = _FUNCS.get(node.func.id)
        if fn is None:
            raise FigureRenderError(f"表达式里不允许的函数: {node.func.id}")
        if not node.args or len(node.args) > 2:
            raise FigureRenderError(f"函数参数个数不对: {node.func.id}")
        try:
            return float(fn(*[_eval_node(a, x) for a in node.args]))
        except (ValueError, OverflowError):
            return float("nan")
    raise FigureRenderError("表达式含不允许的语法")


def eval_math_expr(expr: str, x: float) -> float:
    """按白名单语法求 f(x)；非法表达式抛 FigureRenderError，定义域外返回 nan。"""
    s = (expr or "").strip().replace("×", "*").replace("÷", "/").replace("−", "-").replace("^", "**")
    s = re.sub(r"(\d)\s*[xX]\b", r"\1*x", s)  # 2x → 2*x
    s = re.sub(r"(\d)\s*\(", r"\1*(", s)  # 2( → 2*(
    s = re.sub(r"\)\s*(\d|[xX(])", r")*\1", s)  # )( / )x → )*(
    s = s.replace("X", "x")
    if not s:
        raise FigureRenderError("空表达式")
    tree = _expr_cache.get(s)
    if tree is None:
        try:
            tree = ast.parse(s, mode="eval")
        except SyntaxError as e:
            raise FigureRenderError(f"表达式解析失败: {expr}") from e
        _expr_cache[s] = tree
    return _eval_node(tree, float(x))


# ── 各 kind 渲染 ─────────────────────────────────────────────────────────
def _save_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def _finite(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _break_jumps(ys: List[float]) -> List[float]:
    """间断点（如 1/x 的极点）把线掐断，别拿直线连过去。"""
    finite = [y for y in ys if math.isfinite(y)]
    if len(finite) < 10:
        return ys
    span = max(finite) - min(finite)
    if span <= 0:
        return ys
    out = list(ys)
    for i in range(1, len(out)):
        a, b = out[i - 1], out[i]
        if math.isfinite(a) and math.isfinite(b) and abs(b - a) > span * 0.6:
            out[i] = float("nan")
    return out


def _render_function(spec: Dict[str, Any]) -> bytes:
    raw_exprs = spec.get("exprs")
    if not isinstance(raw_exprs, list):
        raw_exprs = [spec.get("expr")] if spec.get("expr") else []
    exprs = [str(e).strip() for e in raw_exprs if str(e or "").strip()]
    if not exprs:
        raise FigureRenderError("function 缺 exprs")
    if len(exprs) > 3:
        exprs = exprs[:3]

    x_min = _finite(spec.get("x_min"))
    x_max = _finite(spec.get("x_max"))
    if x_min is None or x_max is None or x_max <= x_min:
        raise FigureRenderError("function 需要 x_min < x_max")
    y_min = _finite(spec.get("y_min"))
    y_max = _finite(spec.get("y_max"))

    _setup_cjk_font()
    fig, ax = plt.subplots(figsize=(4.6, 3.4), dpi=150)

    n = 400
    xs = [x_min + (x_max - x_min) * i / (n - 1) for i in range(n)]
    all_ys: List[float] = []
    for expr in exprs:
        try:
            ys = [eval_math_expr(expr, xv) for xv in xs]
        except FigureRenderError:
            plt.close(fig)
            raise
        ys = _break_jumps(ys)
        all_ys.extend(y for y in ys if math.isfinite(y))
        ax.plot(xs, ys, linewidth=1.6, color="#1f2937")

    if y_min is None or y_max is None or y_max <= y_min:
        if all_ys:
            lo, hi = min(all_ys), max(all_ys)
            pad = max((hi - lo) * 0.15, 1.0)
            y_min = lo - pad if y_min is None else y_min
            y_max = hi + pad if y_max is None else y_max
        else:
            y_min = -5 if y_min is None else y_min
            y_max = 5 if y_max is None else y_max
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)

    # 纸笔卷风格坐标轴：只留左/下轴线，过零点
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_position("zero")
    ax.spines["bottom"].set_position("zero")
    ax.tick_params(labelsize=8)
    ax.set_xlabel(str(spec.get("x_label") or "x"), loc="right", fontsize=10)
    ax.set_ylabel(str(spec.get("y_label") or "y"), loc="top", rotation=0, fontsize=10, labelpad=8)
    ax.grid(True, linewidth=0.4, alpha=0.25)
    return _save_png(fig)


def _render_geometry(spec: Dict[str, Any]) -> bytes:
    raw_points = spec.get("points")
    if not isinstance(raw_points, dict) or len(raw_points) < 2:
        raise FigureRenderError("geometry 需要至少 2 个 points")

    points: Dict[str, Tuple[float, float]] = {}
    for name, xy in raw_points.items():
        if isinstance(xy, (list, tuple)) and len(xy) >= 2:
            px, py = _finite(xy[0]), _finite(xy[1])
            if px is not None and py is not None:
                points[str(name)] = (px, py)
    if len(points) < 2:
        raise FigureRenderError("geometry 坐标不合法")

    def _pair_list(key: str) -> List[Tuple[str, str]]:
        out = []
        for item in spec.get(key) or []:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                a, b = str(item[0]), str(item[1])
                if a in points and b in points and a != b:
                    out.append((a, b))
        return out

    segments = _pair_list("segments")
    dashed = _pair_list("dashed")

    circles = []
    for c in spec.get("circles") or []:
        if not isinstance(c, dict):
            continue
        center = str(c.get("center") or "")
        r = _finite(c.get("r"))
        if center in points and r is not None and r > 0:
            circles.append((center, r))

    polygons = []
    for p in spec.get("polygons") or []:
        if not isinstance(p, dict):
            continue
        names = [str(n) for n in (p.get("points") or [])]
        if len(names) >= 3 and all(n in points for n in names):
            polygons.append((names, bool(p.get("fill"))))

    angles = []
    for a in spec.get("angles") or []:
        if not isinstance(a, dict):
            continue
        v, p1, p2 = str(a.get("vertex") or ""), str(a.get("p1") or ""), str(a.get("p2") or "")
        if v in points and p1 in points and p2 in points:
            angles.append((v, p1, p2, str(a.get("label") or "")))

    if not segments and not dashed and not circles and not polygons:
        raise FigureRenderError("geometry 没有任何可画的线/圆/多边形")

    _setup_cjk_font()
    fig, ax = plt.subplots(figsize=(4.6, 3.6), dpi=150)
    ax.set_aspect("equal")

    xs_all = [p[0] for p in points.values()]
    ys_all = [p[1] for p in points.values()]
    for center, r in circles:
        cx, cy = points[center]
        xs_all.extend([cx - r, cx + r])
        ys_all.extend([cy - r, cy + r])
    pad_x = max((max(xs_all) - min(xs_all)) * 0.12, 0.5)
    pad_y = max((max(ys_all) - min(ys_all)) * 0.12, 0.5)
    ax.set_xlim(min(xs_all) - pad_x, max(xs_all) + pad_x)
    ax.set_ylim(min(ys_all) - pad_y, max(ys_all) + pad_y)
    # 角弧半径随图幅缩放（固定值在大坐标图上会成巨型弧）
    arc_r = max(min(max(xs_all) - min(xs_all), max(ys_all) - min(ys_all)) * 0.1, 0.15)

    for names, fill in polygons:
        pts = [points[n] for n in names]
        patch = MplPolygon(
            pts,
            closed=True,
            facecolor="#e5e7eb" if fill else "none",
            edgecolor="#1f2937",
            linewidth=1.4,
            hatch="////" if fill else None,
            alpha=0.9 if fill else 1.0,
        )
        ax.add_patch(patch)

    for center, r in circles:
        cx, cy = points[center]
        ax.add_patch(Circle((cx, cy), r, fill=False, edgecolor="#1f2937", linewidth=1.4))

    for a, b in segments:
        (x1, y1), (x2, y2) = points[a], points[b]
        ax.plot([x1, x2], [y1, y2], color="#1f2937", linewidth=1.5)
    for a, b in dashed:
        (x1, y1), (x2, y2) = points[a], points[b]
        ax.plot([x1, x2], [y1, y2], color="#4b5563", linewidth=1.2, linestyle="--")

    # 角弧：两射线夹角的短弧 + 可选标注
    for v, p1, p2, label in angles:
        vx, vy = points[v]
        a1 = math.degrees(math.atan2(points[p1][1] - vy, points[p1][0] - vx))
        a2 = math.degrees(math.atan2(points[p2][1] - vy, points[p2][0] - vx))
        span = (a2 - a1) % 360.0
        if span > 180.0:
            a1, span = a2, (a1 - a2) % 360.0
        ax.add_patch(
            Arc((vx, vy), 2 * arc_r, 2 * arc_r, angle=0, theta1=a1, theta2=a1 + span, color="#1f2937", linewidth=1.1)
        )
        if label:
            mid = math.radians(a1 + span / 2.0)
            ax.text(
                vx + arc_r * 1.35 * math.cos(mid),
                vy + arc_r * 1.35 * math.sin(mid),
                label,
                fontsize=8,
                color="#1f2937",
                ha="center",
                va="center",
            )

    for name, (px, py) in points.items():
        ax.plot([px], [py], marker="o", markersize=3.5, color="#111827")
        ax.annotate(name, (px, py), textcoords="offset points", xytext=(4, 4), fontsize=9)

    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    return _save_png(fig)


def _stats_series(spec: Dict[str, Any]) -> Tuple[List[str], List[List[float]], List[str]]:
    categories = [str(c) for c in (spec.get("categories") or []) if str(c).strip()]
    raw_series = spec.get("series")
    labels = [str(s) for s in (spec.get("series_labels") or [])]
    if isinstance(raw_series, list) and raw_series and isinstance(raw_series[0], list):
        series = []
        for row in raw_series:
            vals = [_finite(v) for v in row]
            series.append([v if v is not None else 0.0 for v in vals])
        if not labels or len(labels) != len(series):
            labels = [f"系列{i + 1}" for i in range(len(series))]
    else:
        vals = [_finite(v) for v in (spec.get("values") or [])]
        series = [[v if v is not None else 0.0 for v in vals]]
        labels = labels or [str(spec.get("series_label") or "")]
    if len(categories) < 2:
        raise FigureRenderError("统计图需要至少 2 个 categories")
    for row in series:
        if len(row) != len(categories):
            raise FigureRenderError("统计图 values 长度要与 categories 一致")
    return categories, series, labels


def _render_bar(spec: Dict[str, Any]) -> bytes:
    categories, series, labels = _stats_series(spec)
    _setup_cjk_font()
    fig, ax = plt.subplots(figsize=(4.8, 3.2), dpi=150)
    if len(series) == 1:
        xs = range(len(categories))
        ax.bar(xs, series[0], width=0.55, facecolor="#dbeafe", edgecolor="#2563eb", linewidth=1.1)
        for i, v in enumerate(series[0]):
            ax.text(i, v, f"{v:g}", ha="center", va="bottom", fontsize=8)
    else:
        width = 0.8 / len(series)
        xs = list(range(len(categories)))
        for k, row in enumerate(series):
            pos = [x + (k - (len(series) - 1) / 2) * width for x in xs]
            ax.bar(pos, row, width=width, label=labels[k] if labels[k] else None)
        if any(labels):
            ax.legend(fontsize=8)
    ax.set_xticks(range(len(categories)))
    ax.set_xticklabels(categories, fontsize=9)
    ax.tick_params(axis="y", labelsize=8)
    ax.set_xlabel(str(spec.get("x_label") or ""), fontsize=9)
    ax.set_ylabel(str(spec.get("y_label") or ""), fontsize=9)
    ax.yaxis.grid(True, linewidth=0.4, alpha=0.3)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return _save_png(fig)


def _render_line(spec: Dict[str, Any]) -> bytes:
    categories, series, labels = _stats_series(spec)
    _setup_cjk_font()
    fig, ax = plt.subplots(figsize=(4.8, 3.2), dpi=150)
    xs = list(range(len(categories)))
    for k, row in enumerate(series):
        ax.plot(
            xs,
            row,
            marker="o",
            markersize=4.5,
            linewidth=1.7,
            label=labels[k] if labels[k] else None,
        )
        for i, v in enumerate(row):
            ax.annotate(f"{v:g}", (i, v), textcoords="offset points", xytext=(0, 6), fontsize=7.5, ha="center")
    if any(labels):
        ax.legend(fontsize=8)
    ax.set_xticks(xs)
    ax.set_xticklabels(categories, fontsize=9)
    ax.tick_params(axis="y", labelsize=8)
    ax.set_xlabel(str(spec.get("x_label") or ""), fontsize=9)
    ax.set_ylabel(str(spec.get("y_label") or ""), fontsize=9)
    ax.yaxis.grid(True, linewidth=0.4, alpha=0.3)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return _save_png(fig)


def _render_pie(spec: Dict[str, Any]) -> bytes:
    items = spec.get("items")
    labels: List[str] = []
    values: List[float] = []
    for it in items or []:
        if isinstance(it, (list, tuple)) and len(it) >= 2:
            v = _finite(it[1])
            if v is not None and v > 0:
                labels.append(str(it[0]))
                values.append(v)
    if len(values) < 2:
        raise FigureRenderError("pie 需要至少 2 个正值 items")
    _setup_cjk_font()
    fig, ax = plt.subplots(figsize=(4.4, 3.4), dpi=150)
    ax.pie(
        values,
        labels=labels,
        autopct="%1.0f%%",
        startangle=90,
        counterclock=False,
        wedgeprops={"edgecolor": "white", "linewidth": 1},
        textprops={"fontsize": 9},
        pctdistance=0.72,
    )
    return _save_png(fig)


_RENDERERS: Dict[str, Callable[[Dict[str, Any]], bytes]] = {
    "function": _render_function,
    "geometry": _render_geometry,
    "bar": _render_bar,
    "line": _render_line,
    "pie": _render_pie,
}


def render_figure_png(spec: Any) -> bytes:
    """figure 规格 → PNG 字节；规格不合法抛 FigureRenderError。"""
    if not isinstance(spec, dict):
        raise FigureRenderError("figure 不是对象")
    kind = str(spec.get("kind") or "").strip().lower()
    renderer = _RENDERERS.get(kind)
    if renderer is None:
        raise FigureRenderError(f"不支持的 figure kind: {kind!r}")
    return renderer(spec)


def render_figure_data_url(spec: Any) -> str:
    png = render_figure_png(spec)
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


# ── 出题链路入口 ─────────────────────────────────────────────────────────
# 救题启发：剥掉开头「如图，」后，剩余文字得还有「给定条件」才算完整
# （数字/等量/几何符号/已知若设）。否则像「如图所示，求面积。」剥成
# 「求面积。」看着没引用图了，其实是没条件的残题，照样丢。
_RESCUE_GIVEN_RE = re.compile(
    r"\d|[=＝]|已知|若|设|假设|给定|边长|半径|直径|坐标|△|□|⊙|平行|垂直|相等|长为|宽为|高为|面积为"
)


def _looks_self_contained(text: str) -> bool:
    return bool(_RESCUE_GIVEN_RE.search(text or ""))


def process_question_figures(questions: List[Any]) -> List[Any]:
    """出题收尾：给要图的题画出真图；画不出/引用图没图的题整题丢弃。

    保证结果里每道题要么带 figure_img（可写「如图所示」），要么文字不依赖图/表。
    """
    out: List[Any] = []
    for q in questions or []:
        if not isinstance(q, dict):
            out.append(q)
            continue

        fig = q.get("figure")
        if isinstance(fig, dict) and fig:
            try:
                q["figure_img"] = render_figure_data_url(fig)
            except Exception as exc:  # noqa: BLE001 - 画不出就降级，不挡出题主流程
                logger.warning("figure render failed (kind=%s): %s", fig.get("kind"), exc)
                q.pop("figure", None)
                q.pop("figure_img", None)
        else:
            q.pop("figure", None)
            q.pop("figure_img", None)

        if q.get("figure_img"):
            out.append(q)  # 有真图：题干写「如图所示」是合法引用
            continue

        if not question_has_figure_reference(q):
            out.append(q)  # 纯文字题
            continue

        # 引用图却没图：剥开头「如图，」救一把，条件写全了才留
        for key in ("stem", "content"):
            if isinstance(q.get(key), str):
                q[key] = strip_figure_leading_ref(q[key])
        if question_has_figure_reference(q):
            continue  # 中段还在引用图/表 → 丢
        text = f"{q.get('stem') or ''}{q.get('content') or ''}"
        if not _looks_self_contained(text):
            continue  # 剥完只剩壳的残题 → 丢
        out.append(q)
    return out
