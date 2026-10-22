# -*- coding: utf-8 -*-
"""题干/作答区角色甄别 v3（2026-10-12 用户反馈：第三大题把题干卡片当成了作答区）。

百度切题的 slot 是它自己猜的「手写区」，没有题干/作答区概念：「分一分涂一涂」类题的
印刷图案卡片（圆形/三角形卡片长得像涂卡圈）会被框成假作答区，报告里凭空多出
「第3题-作答区1~7：未作答」噪音，form_guard/留痕/统分都被假块污染。

v1 教训：只对小裁剪图做语义判断、无题目上下文 → 误杀第一大题连线区、第二大题真圈选区
共 8 块。裁剪画面分不出「要圈的图」（作答区）和「要数的图」（素材），得靠题目语义。
v2 教训：整题判「作答动作发生在哪」当开关 → 第三大题标题「涂一涂」被读成给图案涂色，
判 on_items 0.95，卡片假块全部保留（用户问题没修掉）。整题判对 Q1/Q2 稳定正确，
对 Q3 稳定错误——不能当开关，只能当保险丝。
v3（本版）：每题一次组合调用（整卷缩略图红框 + 题目放大 + 字母角标小框），同屏产出
逐框 role（语义）+ has_marks（有无手写笔迹）+ 整题 answer_location。小框取景用
_trim_overlaps 收缩被大框重叠的小框 + _clipped_crop_boxes 自适应留边（同公式
ink_evidence：min(40,max(8,0.3*边长))，看见画在印刷图 bbox 外的手写圈——实测 Q2
圈选的圈整圈在框外，pad=2 时 VL 只看得见纯印刷误剔真作答区）但四边碰到同题邻块
bbox 就收住（防邻块串扰：Q3 卡片留边 20px 会把下方填空手写「橡皮：5」拉进图里）。
决策：
  保护阀：题内无作答证据（has_marks=true 或 result ∈ {对,错,半对}）时，
    仅 answer_location ∈ {elsewhere, mixed} 才允许清理——防「全空的圈一圈」被
    幻觉清空；有证据的题不受此阀限制，故第三大题即使整题判误报 on_items 也不被挡。
  比例护栏：一层候选（未作答）+ d) 候选（幻觉判分卡）合计不足题内框数
    之半 → 视为零星误判（如圈一圈里该圈没圈的图），整题不动。
  单面板纯视觉（防网格串扰）：一层候选、d) 候选与其余未作答框都过单面板
    （空白书写处/有笔迹=answer；纯印刷=stem），stem 且 conf>GRAY_MAX 进下一步；
    灰带 [GRAY_MIN,GRAY_MAX] → flagged。
  语义终审（分两路，2026-10-12 探针校准：毒源是题目放大图里的手写字）：
    a) 串扰矛盾：组合说 has_marks=true 但单面板视觉=纯印刷（填空宽框旁的卡片被
       串扰成 answer+有笔迹）→ 无上下文小网格再判语义，双 stem 才剔；
    b) 无证据题：整题无作答证据时的一层候选 → 带上下文终审确认 stem（防全空圈一圈）；
    c) 组合说 role=answer 且 has_marks≠True（圈一圈里该圈没圈的图）→ 组合与视觉在
       「无笔迹」上一致，组合语义可信用，直接留（已判对错的同型块也留）。
    d) 幻觉判分的题干卡：百度会把印刷图案卡幻觉判「对/错」（实测 7 卡全判对），
       只剔未作答永远清不掉。已批出对错半对且组合不是「answer+无笔迹」的框都进
       无上下文终审，视觉+终审双「纯印刷无笔迹」才剔——真作答区必有笔迹可看。
    一层候选（未作答+stem）一律带上下文终审确认 stem 才剔，无直接剔除通道
    （2026-10-12 Q2 回归：组合调用对「该圈没圈」的圈选目标会闪变 stem，题内有
    证据时直接剔把真作答区清了——纯印刷观感的块到底是要圈的目标还是分类素材，
    只有题目语义分得出，必须带上下文二审）。
  单槽题保护（2026-10-22 测试14）：题内只有一个作答区时一律不动块、不问 VL——
    选择题作答括号的小裁剪就是一对印刷括号，三层判定都会把它读成「题干素材」，
    剔掉唯一块=整题从报告/留痕消失（用户看到「选择题没批改」）。假块是成片的
    （比例护栏原话），单槽无从成片；多槽题逻辑不变。
  整题会被清空时全部保留（fail-safe，仅已判块走此闸；纯未作答假卡组整组剔是常态）。
    任何缺报/VL/解析失败 fail-open 不动块。
  剔除后同题剩余 sub_index 连续化。
范围仅百度切题产物（baidu_is_slot 且带 baidu_original_index）。env：
SLOT_ROLE_FILTER=0 关闭（默认开）；SLOT_ROLE_MAX_PER_PAPER 每卷候选上限（默认 60）。
"""
from __future__ import annotations

import os
from typing import Any, Optional

from PIL import Image, ImageDraw

from app.grading.form_guard import _answer_bbox, _norm_result
from app.grading.ink_evidence import (
    _CROP_PAD_MAX,
    _CROP_PAD_MIN,
    _CROP_PAD_RATIO,
    _ask_vl,
    _compose_labeled_crops,
    _env_flag,
    _env_int,
    _json_array_from_text,
)
from app.grading.subject_family import GRAY_MAX, GRAY_MIN

_ROLE_STEM_WORDS = ("stem", "题干", "素材", "question")
_ROLE_ANSWER_WORDS = ("answer", "作答", "作答区", "答题", "书写")
_LOC_ON_ITEMS_WORDS = ("on_items", "on-items", "物品", "图案上", "图上")
_LOC_ELSEWHERE_WORDS = ("elsewhere", "别处", "填空", "横线", "表格", "格子")

_PAGE_PANEL_LONG_SIDE = 900
_QUESTION_PANEL_LONG_SIDE = 600
# 小框裁剪外扩：默认 pad（最大40px）会把邻区题干标题/手写横线拉进图里，
# 污染角色判断（实测 2_1 误判 stem、3_6/3_7 误判 answer 都源于此），只留防裁边余量。
_SLOT_CROP_PAD = 2

_GRADED_RESULTS = {"对", "错", "半对"}

_COMBINED_PROMPT = (
    "整张图：最左是整张试卷缩略图（红框标出这道题），中间是这道题的放大图——"
    "请结合里面的题目要求来判断，但这两部分不需要输出。"
    "最右是这道题里被框出的小区域，每格左上角有字母编号（A、B、C…），只对它们输出。\n"
    "第一步，对每个字母小区域输出两项：\n"
    '  "role"：该区域是【题干素材】还是【作答区】——\n'
    '    "answer"（作答区）：学生动笔作答的地方——写答案的横线/括号/表格格，'
    "或者按题目要求要圈/连/勾/涂的图案本身（哪怕学生还没动笔、空着）；\n"
    '    "stem"（题干素材）：供读一读、数一数、分一分的印刷图文，老师批改时不核对它本身。\n'
    '  "has_marks"：该区域内是否有学生手写笔迹（手写文字/数字/圈画/勾画/连线/涂写）——'
    "印刷图案不算。\n"
    "注意1：印刷的圆形/三角形等【形状】卡片是图案，不是学生画的圈；学生笔迹是手写线条，"
    "印刷插图的阴影/网点/大面积涂色印刷不算笔迹。\n"
    "注意2：以框内主体为准；框边缘蹭进的邻区文字或笔迹（如相邻横线上露出的字）不算本框内容。\n"
    "例：「连一连」「把不同类的圈起来」题里被连/被圈的图案本身是作答区；"
    "「数一数填一填」题里供数数的印刷图案是素材，横线上写下的数字才是作答。\n"
    "第二步，综合判断这道题【批改时要核对的学生答案】出现在哪里：\n"
    '- "elsewhere"：答案是写在填空括号/横线/表格/空白格里的文字/数字，或涂在独立空白涂色格里；\n'
    '- "on_items"：答案就是在这些图案本身上动笔，批改看图案上有没有笔迹；\n'
    '- "mixed"：两者都有。\n'
    "只输出 JSON 数组，前几项是字母小区域，最后一项固定 id 为 QUESTION：\n"
    '[{"id":"A","role":"answer"或"stem","has_marks":true或false,"confidence":0.0~1.0}, '
    '{"id":"QUESTION","answer_location":"on_items"或"elsewhere"或"mixed","confidence":0.0~1.0}]'
)

_SLOT_VISUAL_PROMPT = (
    "图中每个编号面板是试卷上一处被框出的小区域。只看画面构成，判断它是不是【学生作答的地方】：\n"
    '- "answer"：面板是空白书写处（填空括号、答题横线、空白格子、空白涂色格），'
    "或者已有学生手写笔迹（手写文字/数字/圈画/勾画/连线/涂写）。\n"
    '- "stem"：整框都是印刷图案/印刷文字素材（插图、图案卡片、图形素材、题干文字），'
    "看不出留白供书写，也没有手写笔迹。\n"
    "注意：印刷插图的阴影/网点/大面积涂色印刷不算笔迹；以框内主体为准，"
    "框边缘蹭进的邻区文字或笔迹不算本框内容。\n"
    "只输出 JSON 数组，格式："
    '[{"id": 面板编号, "role": "answer"或"stem", "confidence": 0.0~1.0}]。'
    "confidence 表示你对该判断本身的置信度。"
)

# 无上下文语义终审：仅小框网格（⛔ 不带题目放大图——实测毒源：填空横线旁的卡片
# 被放大图里的手写串扰成 answer+有笔迹，去掉上下文立刻判对）。
_SOLO_SEMANTIC_PROMPT = (
    "图中每个字母小区域是试卷上一处被框出的小区域，每格左上角有字母编号（A、B、C…）。"
    "只看框内内容，对每个字母输出两项：\n"
    '  "role"：该区域是【题干素材】还是【作答区】——\n'
    '    "answer"（作答区）：写答案的横线/括号/表格格，或要圈/连/勾/涂的图案本身；\n'
    '    "stem"（题干素材）：供读一读、数一数、分一分的印刷物品/图形卡片'
    "（卡片上哪怕画着铅笔、橡皮、钢笔、水果等物品插图，也只是图案本身）。\n"
    '  "has_marks"：有没有【学生手写】的字、数字，或【学生画的】圈、线、勾、涂？\n'
    "注意：印刷插图、阴影、网点、印刷涂色都不算笔迹；以框内主体为准，"
    "框边缘蹭进的邻区内容不算。\n"
    "只输出 JSON 数组："
    '[{"id":"A","role":"answer"或"stem","has_marks":true或false,"confidence":0.0~1.0}]'
)


def _as_role(value: Any) -> Optional[str]:
    text = str(value if value is not None else "").strip().lower()
    if not text:
        return None
    if any(w in text for w in _ROLE_ANSWER_WORDS):
        return "answer"
    if any(w in text for w in _ROLE_STEM_WORDS):
        return "stem"
    return None


def _as_location(value: Any) -> Optional[str]:
    text = str(value if value is not None else "").strip().lower()
    if not text:
        return None
    if "mixed" in text or "混合" in text or "都有" in text:
        return "mixed"
    if any(w in text for w in _LOC_ELSEWHERE_WORDS):
        return "elsewhere"
    if any(w in text for w in _LOC_ON_ITEMS_WORDS):
        return "on_items"
    return None


def _question_item_id(value: Any) -> bool:
    """识别固定 id=QUESTION 的整题项（⛔ 不能走 _as_id——它会把 QUESTION 收成首字母 Q，
    与第 17 个字母角标 Q 撞号，且 answer_location 永远解析不到）。"""
    return str(value if value is not None else "").strip().upper() == "QUESTION"


def _as_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    text = str(value if value is not None else "").strip().lower()
    if not text:
        return None
    if text in ("true", "yes", "1", "y"):
        return True
    if text in ("false", "no", "0", "n"):
        return False
    if any(w in text for w in ("无", "没", "否")):
        return False
    if any(w in text for w in ("有", "是")):
        return True
    return None


def _as_id(value: Any) -> Optional[str]:
    """角标归一：字母取大写首字母（"a."→"A"）；数字原样字符串。"""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return str(value)
    text = str(value).strip().upper()
    if not text:
        return None
    for ch in text:
        if "A" <= ch <= "Z":
            return ch
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits or None


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_confidence(item: dict) -> float:
    try:
        confidence = float(item.get("confidence"))
    except (TypeError, ValueError):
        return 0.0
    if not (confidence == confidence) or confidence < 0.0 or confidence > 1.0:
        return 0.0
    return confidence


def _valid_question_bbox(blk: dict, fallback: list) -> list:
    qb = blk.get("baidu_question_bbox")
    if isinstance(qb, (list, tuple)) and len(qb) == 4:
        try:
            x1, y1, x2, y2 = (int(v) for v in qb)
            if x2 > x1 and y2 > y1:
                return [x1, y1, x2, y2]
        except Exception:
            pass
    return list(fallback)


def _union_bbox(bboxes: list) -> list:
    xs1 = [b[0] for b in bboxes]
    ys1 = [b[1] for b in bboxes]
    xs2 = [b[2] for b in bboxes]
    ys2 = [b[3] for b in bboxes]
    return [min(xs1), min(ys1), max(xs2), max(ys2)]


def _expand(bbox: list, margin: int) -> list:
    return [bbox[0] - margin, bbox[1] - margin, bbox[2] + margin, bbox[3] + margin]


def _trim_overlaps(bboxes: list) -> list:
    """小框与大很多的框重叠时，把小框收缩出大框范围（只用于取裁剪图）。

    实测：「分一分」的卡片框底边会压进下方宽幅填空横线框（3_6/3_7 ⊂ 3_8 顶边），
    裁剪图带上手写笔迹 → 误判 answer。收缩后小框只剩自己的主体。
    仅当对方面积 ≥ 3 倍才修剪；取收缩后剩余面积最大的一边；无剩余则原样。
    """
    out = [list(b) for b in bboxes]
    for i, a in enumerate(bboxes):
        area_a = max(1, (a[2] - a[0]) * (a[3] - a[1]))
        for j, b in enumerate(bboxes):
            if i == j:
                continue
            area_b = max(1, (b[2] - b[0]) * (b[3] - b[1]))
            if area_b < area_a * 3:
                continue  # 只让大很多的框修剪小框
            ox1, oy1 = max(a[0], b[0]), max(a[1], b[1])
            ox2, oy2 = min(a[2], b[2]), min(a[3], b[3])
            if ox2 <= ox1 or oy2 <= oy1:
                continue  # 无重叠
            cands = []
            if oy1 - a[1] > 0:
                cands.append([a[0], a[1], a[2], oy1])  # 去下叠
            if a[3] - oy2 > 0:
                cands.append([a[0], oy2, a[2], a[3]])  # 去上叠
            if ox1 - a[0] > 0:
                cands.append([a[0], a[1], ox1, a[3]])  # 去右叠
            if a[2] - ox2 > 0:
                cands.append([ox2, a[1], a[2], a[3]])  # 去左叠
            if not cands:
                continue  # 整框被包住 → 不动（fail-open）
            best = max(cands, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
            out[i] = best
    return out


def _compose_question_context(image: Image.Image, q_bbox: list) -> Optional[Image.Image]:
    """整卷缩略图（红框标出本题） + 题目放大图，横向拼成两面板合成图。"""
    if image.mode != "RGB":
        image = image.convert("RGB")
    W, H = image.size

    page = image.copy()
    scale = _PAGE_PANEL_LONG_SIDE / max(W, H)
    page = page.resize(
        (max(1, int(W * scale)), max(1, int(H * scale))),
        getattr(Image, "LANCZOS", Image.BILINEAR),
    )
    draw = ImageDraw.Draw(page)
    x1, y1, x2, y2 = (int(v) for v in q_bbox)
    draw.rectangle(
        [x1 * scale - 2, y1 * scale - 2, x2 * scale + 2, y2 * scale + 2],
        outline=(255, 0, 0),
        width=3,
    )
    canvas = Image.new("RGB", (_PAGE_PANEL_LONG_SIDE, _PAGE_PANEL_LONG_SIDE), "white")
    canvas.paste(page, ((_PAGE_PANEL_LONG_SIDE - page.width) // 2, (_PAGE_PANEL_LONG_SIDE - page.height) // 2))

    try:
        crop = image.crop((max(0, x1), max(0, y1), min(W, x2), min(H, y2)))
    except Exception:
        return None
    if crop.width <= 0 or crop.height <= 0:
        return None
    q_scale = _QUESTION_PANEL_LONG_SIDE / max(crop.width, crop.height)
    crop = crop.resize(
        (max(1, int(crop.width * q_scale)), max(1, int(crop.height * q_scale))),
        getattr(Image, "LANCZOS", Image.BILINEAR),
    )
    q_panel = Image.new("RGB", (_QUESTION_PANEL_LONG_SIDE, _QUESTION_PANEL_LONG_SIDE), "white")
    q_panel.paste(
        crop,
        ((_QUESTION_PANEL_LONG_SIDE - crop.width) // 2, (_QUESTION_PANEL_LONG_SIDE - crop.height) // 2),
    )

    out = Image.new("RGB", (_PAGE_PANEL_LONG_SIDE + _QUESTION_PANEL_LONG_SIDE, _PAGE_PANEL_LONG_SIDE), "white")
    out.paste(canvas, (0, 0))
    out.paste(q_panel, (_PAGE_PANEL_LONG_SIDE, 0))
    return out


def _clipped_crop_boxes(boxes: list, walls: list | None = None) -> list:
    """自适应留边取景框：留边按框尺寸自适应（把画在 bbox 外的手写圈收进图——
    实测 Q2 圈选的圈整圈在印刷图框外，pad=2 时 VL 只看得见纯印刷，误判
    「stem+无笔迹」剔掉真作答区），但四边碰到同题邻块（walls，默认 boxes 自身）
    的 bbox 就收住（防串扰：Q3 卡片留边 20px 会把下方填空手写拉进图里）。
    邻块压过来也永不收缩到原框以内；walls 按同下标跳过自己（含被
    _trim_overlaps 裁过的自身原框）。"""
    walls = boxes if walls is None else walls
    out: list = []
    for i, box in enumerate(boxes):
        try:
            x1, y1, x2, y2 = (int(v) for v in box)
        except Exception:
            out.append(box)
            continue
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        pad = min(
            _CROP_PAD_MAX,
            max(_CROP_PAD_MIN, round(_CROP_PAD_RATIO * max(x2 - x1, y2 - y1))),
        )
        left, top, right, bottom = x1 - pad, y1 - pad, x2 + pad, y2 + pad
        for j, wall in enumerate(walls):
            if j == i:
                continue
            try:
                wx1, wy1, wx2, wy2 = (int(v) for v in wall)
            except Exception:
                continue
            if wx2 < wx1:
                wx1, wx2 = wx2, wx1
            if wy2 < wy1:
                wy1, wy2 = wy2, wy1
            # 各侧独立收：邻块压进哪侧的留边区就收住哪一侧
            if wy2 > top and wy1 < bottom:
                if wx2 > left and wx1 < x1:
                    left = max(left, min(wx2, x1))
                if wx1 < right and wx2 > x2:
                    right = min(right, max(wx1, x2))
            if wx2 > left and wx1 < right:
                if wy2 > top and wy1 < y1:
                    top = max(top, min(wy2, y1))
                if wy1 < bottom and wy2 > y2:
                    bottom = min(bottom, max(wy1, y2))
        out.append((left, top, right, bottom))
    return out


def _compose_question_and_slots(
    image: Image.Image, q_bbox: list, slot_bboxes: list, labels: list, *, pad: int | None = None
) -> Optional[Image.Image]:
    """上下文两面板 + 字母角标小框网格，三段横拼。pad 传 0 表示小框已是取景框
    （_clipped_crop_boxes 产出，留边已含、邻块已裁），不要再外扩。"""
    context = _compose_question_context(image, q_bbox)
    if context is None:
        return None
    slots = _compose_labeled_crops(
        image,
        slot_bboxes,
        labels=labels,
        pad=_SLOT_CROP_PAD if pad is None else pad,
    )
    if slots is None:
        return None
    out = Image.new(
        "RGB",
        (context.width + slots.width, max(context.height, slots.height)),
        "white",
    )
    out.paste(context, (0, 0))
    out.paste(slots, (context.width, 0))
    return out


def _first_item(items: list) -> Optional[dict]:
    return next((i for i in items if isinstance(i, dict)), None)


def _renumber_sub_indexes(blocks: list) -> None:
    """同题剩余作答区的 sub_index 连续化（剔除假块后不留跳号）。"""
    groups: dict = {}
    for blk in blocks:
        if not isinstance(blk, dict) or not blk.get("baidu_is_slot"):
            continue
        if _safe_int(blk.get("sub_index")) is None:
            continue
        groups.setdefault(blk.get("index"), []).append(blk)
    for items in groups.values():
        items.sort(key=lambda b: _safe_int(b.get("sub_index")) or 0)
        for i, b in enumerate(items, start=1):
            b["sub_index"] = i


def filter_stem_slots(image_path: str, blocks: list, *, client=None) -> list:
    """就地剔除题干素材假块并重编号；返回变更清单（action="removed_stem"）。

    候选：baidu_is_slot 且带 baidu_original_index（仅百度切题产物）。任何 VL/解析
    失败只影响该题（不动块），绝不抛出阻断批改。决策细则见模块 docstring。
    """
    if not _env_flag("SLOT_ROLE_FILTER", True) or not blocks:
        return []
    max_per_paper = max(1, _env_int("SLOT_ROLE_MAX_PER_PAPER", 60))
    try:
        image = Image.open(image_path).convert("RGB")
    except Exception:
        return []

    candidates: list = []
    for blk in blocks:
        if len(candidates) >= max_per_paper:
            break  # 超上限 fail-open：其余不动
        if not isinstance(blk, dict):
            continue
        if not (blk.get("baidu_is_slot") and "baidu_original_index" in blk):
            continue
        if _answer_bbox(blk) is None:
            continue
        candidates.append(blk)
    if not candidates:
        return []

    changes: list = []
    removed_ids: set = set()
    with image:
        groups: dict = {}
        for blk in candidates:
            groups.setdefault(blk.get("baidu_original_index"), []).append(blk)

        for _q_key, group in groups.items():
            # 单槽题一律不动（2026-10-22 测试14「选择题没批改」根因）：选择题作答
            # 括号常是题内唯一作答区，小裁剪只有一对印刷括号，组合/视觉/终审三层都
            # 会把它读成「题干素材」→ 唯一块被剔 → 整题从报告/留痕消失。本闸的原理
            # 是「假块是成片的」（分一分的卡片行），单槽无从成片；误剔只会让整题消失，
            # 比留一行噪音严重得多 → 直接跳过（顺带省 VL 调用）。
            if len(group) == 1:
                continue
            slot_bboxes = [_answer_bbox(b) for b in group]
            # 取图用修剪框：小框被大框重叠时收缩出大框范围（防邻区笔迹/内容污染）
            crop_bboxes = _trim_overlaps(slot_bboxes)
            # 再自适应留边+邻块裁剪：看见画在框外的手写圈，同时不串邻块
            view_bboxes = _clipped_crop_boxes(crop_bboxes, walls=slot_bboxes)
            q_bbox = _valid_question_bbox(
                group[0], _union_bbox([_expand(b, 40) for b in slot_bboxes])
            )
            labels = [chr(ord("A") + i) for i in range(len(group))]
            # 组合调用：逐框 role + has_marks + 整题 answer_location（一次 VL）
            try:
                composed = _compose_question_and_slots(image, q_bbox, view_bboxes, labels, pad=0)
                items = _ask_vl(client, composed, prompt=_COMBINED_PROMPT) if composed is not None else []
            except Exception:
                continue  # fail-safe：本题不动
            by_label: dict = {}
            location = None
            for item in items:
                if not isinstance(item, dict):
                    continue
                if _question_item_id(item.get("id")):
                    location = _as_location(item.get("answer_location"))
                    continue
                item_id = _as_id(item.get("id"))
                if item_id is not None:
                    by_label[item_id] = item
            if not by_label:
                continue  # 全缺报 fail-open

            slot_infos: dict = {}  # pos(1-based) -> (role, has_marks, conf)
            for pos, letter in enumerate(labels, start=1):
                item = by_label.get(letter) or by_label.get(str(pos))
                if not item:
                    continue  # 缺报不动（fail-open per-slot）
                slot_infos[pos] = (
                    _as_role(item.get("role")),
                    _as_bool(item.get("has_marks")),
                    _safe_confidence(item),
                )

            # 保护阀：题内无作答证据（手写笔迹 或 已被批出对错半对）时，
            # 仅 elsewhere/mixed 才允许清理——防「全空的圈一圈」被幻觉清空；
            # 有证据的题不受此阀限制，故第三大题即使整题判仍误报 on_items 也不再被挡住。
            has_evidence = any(
                m is True or _norm_result(group[pos - 1].get("result")) in _GRADED_RESULTS
                for pos, (_r, m, _c) in slot_infos.items()
            )
            if not has_evidence and location not in ("elsewhere", "mixed"):
                continue

            # 一层候选：stem + 无手写 + 未作答 + 高置信
            tier1_positions = []
            for pos, blk in enumerate(group, start=1):
                if _norm_result(blk.get("result")) != "未作答":
                    continue
                role, has_marks, confidence = slot_infos.get(pos, (None, None, 0.0))
                if role != "stem" or has_marks is True:
                    continue
                if confidence <= GRAY_MAX:
                    continue
                tier1_positions.append(pos)
            # d) 幻觉判分的题干卡：已批出对错半对，但百度会把印刷图案卡幻觉判「对」
            #（实测 7 卡全对，只剔未作答就永远清不掉）。除「answer+无笔迹」（2_2 型，
            # 信组合留）外的已判框都进双确认通道。
            tier_d_positions = []
            for pos, blk in enumerate(group, start=1):
                if _norm_result(blk.get("result")) not in _GRADED_RESULTS:
                    continue
                role, has_marks, confidence = slot_infos.get(pos, (None, None, 0.0))
                if role is None or confidence <= GRAY_MAX:
                    continue
                if role == "answer" and has_marks is not True:
                    continue
                tier_d_positions.append(pos)

            # 单面板纯视觉：一层候选、d) 候选与其余未作答框都过（防组合调用被邻区
            # 串扰——实测填空宽框 3_8 的手写会把同排卡片 F/G 串成 answer+有笔迹）。
            visual_stem: dict = {}  # pos -> 视觉置信
            for pos, blk in enumerate(group, start=1):
                if pos not in tier_d_positions and _norm_result(blk.get("result")) != "未作答":
                    continue
                bbox = view_bboxes[pos - 1]
                try:
                    panel = _compose_labeled_crops(image, [bbox], pad=0)
                    panel_items = (
                        _ask_vl(client, panel, prompt=_SLOT_VISUAL_PROMPT)
                        if panel is not None
                        else []
                    )
                except Exception:
                    continue  # 确认失败 fail-open：不动块
                panel_item = next(
                    (c for c in panel_items if isinstance(c, dict) and _safe_int(c.get("id")) == 1),
                    None,
                )
                if not panel_item or _as_role(panel_item.get("role")) != "stem":
                    continue  # 视觉见到作答处（或解析不出）→ 不动块
                panel_conf = _safe_confidence(panel_item)
                if panel_conf > GRAY_MAX:
                    visual_stem[pos] = panel_conf
                elif panel_conf >= GRAY_MIN:
                    blk["slot_role"] = {
                        "action": "flagged",
                        "suspicious": True,
                        "role": "stem",
                        "confidence": round(panel_conf, 3),
                        "was_result": blk.get("result"),
                        "confirmed": True,
                    }

            # 比例护栏（过视觉后按「像纯印刷」的候选算）：不足半数 → 零星误判
            #（如圈一圈里该圈没圈的图），整题不剔。假块是成片的（「分一分」的卡片行）。
            stem_like = [p for p in visual_stem if p in tier1_positions or p in tier_d_positions]
            if stem_like and len(stem_like) * 2 < len(group):
                continue

            # 语义终审分流（实测校准）：
            #   a) 串扰矛盾：组合说 has_marks=true 但单面板视觉=纯印刷——毒源是题目
            #      放大图里的手写字（填空横线旁的卡片被串扰成 answer+有笔迹），上下文
            #      即毒 → 无上下文小网格再判语义，双 stem 才剔；
            #   b) 一层候选（未作答+stem）一律带上下文终审确认 stem（防 2_2 型
            #      「该圈没圈」的圈选目标被闪变 stem 后直接剔——Q2 回归）；
            #   c) 组合说 role=answer 且 has_marks≠True（如圈一圈里该圈没圈的图 2_2）：
            #      组合与视觉在「无笔迹」上一致，组合语义可信用，直接留。
            solo_positions = []  # a)/d) 无上下文终审
            ctx_positions = []   # b) 带上下文终审
            for pos in sorted(visual_stem):
                if pos in tier_d_positions:
                    solo_positions.append(pos)  # d) 幻觉判分卡：无上下文终审定生死
                elif pos in tier1_positions:
                    ctx_positions.append(pos)  # 一层候选无直接剔除通道，必须上下文二审
                elif slot_infos.get(pos, (None, None, 0.0))[1] is True:
                    solo_positions.append(pos)
            repair_stem: set = set()
            if ctx_positions:
                try:
                    repair_composed = _compose_question_and_slots(
                        image,
                        q_bbox,
                        [view_bboxes[p - 1] for p in ctx_positions],
                        [labels[p - 1] for p in ctx_positions],
                        pad=0,
                    )
                    repair_items = (
                        _ask_vl(client, repair_composed, prompt=_COMBINED_PROMPT)
                        if repair_composed is not None
                        else []
                    )
                except Exception:
                    repair_items = []  # 终审失败 fail-open：依赖它的框不动
                repair_by_label: dict = {}
                for item in repair_items:
                    if not isinstance(item, dict):
                        continue
                    if _question_item_id(item.get("id")):
                        continue
                    item_id = _as_id(item.get("id"))
                    if item_id is None:
                        continue
                    repair_by_label[item_id] = item
                for pos in ctx_positions:
                    item = repair_by_label.get(labels[pos - 1])
                    if not item:
                        continue  # 缺报 fail-open
                    if _as_role(item.get("role")) != "stem":
                        continue  # 终审说作答区 → 留（如圈一圈里该圈没圈的图）
                    if _as_bool(item.get("has_marks")) is True:
                        continue
                    if _safe_confidence(item) <= GRAY_MAX:
                        continue
                    repair_stem.add(pos)
            solo_stem: set = set()
            if solo_positions:
                try:
                    solo_composed = _compose_labeled_crops(
                        image,
                        [view_bboxes[p - 1] for p in solo_positions],
                        labels=[labels[p - 1] for p in solo_positions],
                        pad=0,
                    )
                    solo_items = (
                        _ask_vl(client, solo_composed, prompt=_SOLO_SEMANTIC_PROMPT)
                        if solo_composed is not None
                        else []
                    )
                except Exception:
                    solo_items = []  # 终审失败 fail-open：依赖它的框不动
                solo_by_label: dict = {}
                for item in solo_items:
                    if not isinstance(item, dict):
                        continue
                    if _question_item_id(item.get("id")):
                        continue
                    item_id = _as_id(item.get("id"))
                    if item_id is None:
                        continue
                    solo_by_label[item_id] = item
                for pos in solo_positions:
                    item = solo_by_label.get(labels[pos - 1])
                    if not item:
                        continue  # 缺报 fail-open
                    if _as_role(item.get("role")) != "stem":
                        continue
                    if _as_bool(item.get("has_marks")) is True:
                        continue
                    if _safe_confidence(item) <= GRAY_MAX:
                        continue
                    solo_stem.add(pos)

            # 剔除：视觉 stem 且语义达标——
            #   d) 幻觉判分卡：还需无上下文终审 stem+无笔迹（真作答区必有笔迹可看）；
            #   一层候选：还需带上下文终审 stem（无直接剔除通道，防 2_2 型被剔）；
            #   串扰矛盾框：还需无上下文终审 stem；c) 型（2_2）直接留。
            to_remove: list = []
            for pos, vis_conf in sorted(visual_stem.items()):
                if pos in tier_d_positions:
                    if pos not in solo_stem:
                        continue
                elif pos in tier1_positions:
                    if pos not in repair_stem:
                        continue  # 上下文终审没确认 stem → 留
                elif pos in solo_positions:
                    if pos not in solo_stem:
                        continue
                else:
                    continue  # c) 组合语义可信用 → 留
                to_remove.append((pos, vis_conf))
            # fail-safe：整题会被连锅端且候选含已判块（d) 通道）→ 只撤已判块的
            # 剔除（防真作答区被幻觉连锅端）；纯未作答假卡组整组剔是常态，不拦。
            to_remove_d = {p for p, _ in to_remove if p in tier_d_positions}
            if to_remove_d and len(to_remove) >= len(group):
                to_remove = [(p, c) for p, c in to_remove if p not in to_remove_d]
            for pos, vis_conf in to_remove:
                blk = group[pos - 1]
                removed_ids.add(id(blk))
                changes.append(
                    {
                        "index": blk.get("index"),
                        "sub_index": blk.get("sub_index"),
                        "action": "removed_stem",
                        "role": "stem",
                        "confidence": round(vis_conf, 3),
                        "was_result": blk.get("result"),
                        "confirmed": True,
                    }
                )

    if not removed_ids:
        return changes
    remaining = [b for b in blocks if not (isinstance(b, dict) and id(b) in removed_ids)]
    blocks[:] = remaining
    _renumber_sub_indexes(blocks)
    return changes
