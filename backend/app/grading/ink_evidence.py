# -*- coding: utf-8 -*-
"""VL 笔迹证据复核（《科目分层识别引擎方案 v1.0》A 项：印刷插图槽幻觉拦截）。

form_guard 只治「真空白槽」（ink≈0）；印刷插图槽 ink 恒 0.21–0.32，像素分不出
印刷品与手写笔迹——「插图+编造判分」幻觉（声称学生圈选了茄子/皮球）治不了。
本模块把判了 对/错/半对 的作答区裁剪编号后合成一张网格图，交 qwen-vl 逐面板
核对「有没有学生手写笔迹」：

- 无笔迹且判定置信 > GRAY_MAX（0.7）→ 降级未作答（字段集与 form_guard 强降级
  完全一致：未作答不画标记，留痕自动干净），痕迹记 block["ink_evidence"]；
- 无笔迹且置信 ∈ [GRAY_MIN, GRAY_MAX] → 只记 ink_evidence.suspicious，不改判；
- 无笔迹且置信 < GRAY_MIN → 什么都不做（低置信的 "false" 不进灰区标记）；
- 有笔迹 → 不动。

fail-safe：VL 异常 / JSON 解析空 / 图打不开 → 该批候选一律不动（fail-open）。
仲裁（2026-10-22 汪小燕_1）：块带 baidu_handwriting_bbox（百度笔迹检测已框出
手写区）时，VL「无笔迹」不许强降级，只标 suspicious——真笔迹被误报无笔迹、
对→未作答会把空心圆画到字上。细长条作答区切段拼格（_split_readable_segments），
否则缩成细线 VL 看不清笔迹必误报。
⛔ 不用多图一次请求（多图编号归属不可靠，串号=误降级）——只发单张合成网格图，
每面板烧录角标编号，>20 候选分片多次调用。ai-correct 人工修正不接此复核。

两段式确认（2026-10-10 e2e 校准）：网格模式 VL 注意力被 20 面板摊薄，首排真笔迹
被连排误判 false 且 confidence 退化成 1.0；单面板同图同提示词判 5/5 正确。因此网格
初筛判 false 的面板必须单面板（1 面板/次）二次确认，两次都判无笔迹才降级；
确认说有笔迹或确认失败 → 不动块（fail-open）。

env：INK_EVIDENCE_VL=0 关闭（默认开）；INK_EVIDENCE_MAX_PER_PAPER 每卷候选上限
（默认 96，超出不动；2026-10-16 从 24 调高——大卷 40+ 候选时 24 会饿死后半张，
观察与梳理空白打勾正是被上限漏掉的）；INK_EVIDENCE_MIN_INK 触发下限墨迹占比
（默认 0 不启用，现场调参用：空白槽归 form_guard，这里只看有内容的槽）。
"""
from __future__ import annotations

import json
import math
import os
import re
from typing import Any, Optional

from PIL import Image, ImageDraw

from app.grading.form_guard import _answer_bbox, _norm_result, ink_ratio
from app.grading.subject_family import GRAY_MAX, GRAY_MIN
from app.utils.qwen_settings import get_vl_model

VL_MODEL = get_vl_model()
_PANEL_LONG_SIDE = 400
_GRID_COLS = 5
_GRID_ROWS = 4
_BATCH_SIZE = _GRID_COLS * _GRID_ROWS  # 单张网格图 ≤20 面板
# 细长条切段：作答区长宽比超过此值时，400px 格里缩成细线 VL 看不清笔迹
# （2026-10-22 汪小燕_1：1966×141 的手写条缩到 396×43，VL 误报「无笔迹」），
# 沿长边切段后拼进同一格，段间小重叠防切断笔画。
_SEG_MAX_ASPECT = 2.5
_SEG_OVERLAP = 0.08
# 裁剪留边：学生圈选/连线常画在紧 bbox 外面（插图 bbox 只框印刷图），
# 留边太小 VL 只看得到印刷插图内部 → 有圈也被判无笔迹。按槽尺寸 30% 自适应，8~40px 封顶。
_CROP_PAD_MIN = 8
_CROP_PAD_MAX = 40
_CROP_PAD_RATIO = 0.3
_RESULT_CODES = {"对": 1, "错": 2, "未作答": 3, "半对": 4}

_INK_EVIDENCE_PROMPT = (
    "图中每个编号面板是学生试卷上一个「作答区」的裁剪小块。"
    "请逐个面板判断：是否存在【学生手写笔迹】"
    "（手写文字、数字、公式、圈选、勾画、连线、涂写）。\n"
    "印刷的题干、选项文字、印刷插图（图案/图形/卡通画）、印刷的填空横线/下划线和纯空白纸面都不算手写笔迹；"
    "只有学生后来添加的墨迹才算。用笔在印刷图上圈画、打勾、连线算有笔迹。"
    "空横线上没有写任何东西 = 无笔迹。\n"
    "只输出 JSON 数组，不要任何解释，格式："
    '[{"id": 面板编号, "has_handwriting": true或false, "confidence": 0.0~1.0}]。'
    "confidence 表示你对该判断本身的置信度。"
)


def _env_flag(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "off", "no", "disabled")


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.environ.get(name, "") or "").strip() or default)
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(str(os.environ.get(name, "") or "").strip() or default)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any) -> Optional[bool]:
    """稳健布尔解析：JSON 里 "false" 字符串不能被 bool() 误判为 True。"""
    if isinstance(value, bool):
        return value
    text = str(value if value is not None else "").strip().lower()
    if text in ("true", "1", "yes", "有", "是"):
        return True
    if text in ("false", "0", "no", "无", "否"):
        return False
    return None


def _json_array_from_text(text: str) -> list:
    """容错解析 VL 返回的 JSON 数组（围栏/前后缀杂讯都剥掉）；失败返回 []。"""
    raw = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.I)
    if fenced:
        raw = fenced.group(1).strip()
    start = raw.find("[")
    end = raw.rfind("]")
    if start < 0 or end < start:
        return []
    try:
        data = json.loads(raw[start : end + 1])
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _split_readable_segments(crop: Image.Image) -> list:
    """细长条切段（长宽比 > _SEG_MAX_ASPECT）：沿长边切 k 段拼格，让 VL 看得清笔迹。"""
    if crop.width <= 0 or crop.height <= 0:
        return [crop]
    aspect = max(crop.width, crop.height) / max(1, min(crop.width, crop.height))
    if aspect <= _SEG_MAX_ASPECT:
        return [crop]
    k = math.ceil(aspect / _SEG_MAX_ASPECT)
    long_side = crop.width if crop.width >= crop.height else crop.height
    seg_len = math.ceil(long_side / k)
    overlap = max(4, int(seg_len * _SEG_OVERLAP))
    segments: list = []
    pos = 0
    while pos < long_side:
        end = min(long_side, pos + seg_len)
        if crop.width >= crop.height:
            segments.append(crop.crop((pos, 0, end, crop.height)))
        else:
            segments.append(crop.crop((0, pos, crop.width, end)))
        if end >= long_side:
            break
        pos = end - overlap
    return segments or [crop]


def _compose_labeled_crops(
    image: Image.Image, bboxes: list, *, labels: list | None = None, pad: int | None = None
) -> Optional[Image.Image]:
    """候选作答区裁剪图烧录角标编号后拼成一张网格图。

    ⛔ 不做 bbox 高亮（那是判分对图的逻辑）；默认编号从 1 起按传入顺序，
    与 VL 返回的 id 一一对应。labels 传入时烧录自定义角标（如字母 A/B/C，
    供「上下文面板+小框」同屏时与面板计数隔离）。pad 传入时覆盖默认外扩
    （角色甄别用小 pad，防邻区题干/笔迹污染裁剪图）。空 bboxes 返回 None。
    """
    if image.mode != "RGB":
        image = image.convert("RGB")
    w, h = image.size
    panels: list[Image.Image] = []
    for bbox in bboxes:
        try:
            bw = abs(int(bbox[2]) - int(bbox[0]))
            bh = abs(int(bbox[3]) - int(bbox[1]))
            crop_pad = (
                max(0, int(pad))
                if pad is not None
                else min(
                    _CROP_PAD_MAX,
                    max(_CROP_PAD_MIN, round(_CROP_PAD_RATIO * max(bw, bh))),
                )
            )
            x1 = max(0, int(bbox[0]) - crop_pad)
            y1 = max(0, int(bbox[1]) - crop_pad)
            x2 = min(w, int(bbox[2]) + crop_pad)
            y2 = min(h, int(bbox[3]) + crop_pad)
        except Exception:
            x1 = y1 = x2 = y2 = 0
        cell = Image.new("RGB", (_PANEL_LONG_SIDE, _PANEL_LONG_SIDE), "white")
        if x2 > x1 and y2 > y1:
            crop = image.crop((x1, y1, x2, y2))
            segments = _split_readable_segments(crop)
            # 横条切段竖着叠、竖条切段横着排；同一编号整格共用（角标只烧一次）。
            # 多段时顶部留 34px 白带给角标，防编号框盖住第一段笔迹。
            top_band = 34 if len(segments) > 1 else 0
            if crop.width >= crop.height:
                cols, rows = 1, len(segments)
            else:
                cols, rows = len(segments), 1
            sub_w = _PANEL_LONG_SIDE // cols
            sub_h = (_PANEL_LONG_SIDE - top_band) // rows
            resample = getattr(Image, "LANCZOS", Image.BILINEAR)
            for i, seg in enumerate(segments):
                scale = min(sub_w / max(1, seg.width), sub_h / max(1, seg.height))
                seg = seg.resize(
                    (
                        max(1, int(seg.width * scale)),
                        max(1, int(seg.height * scale)),
                    ),
                    resample,
                )
                cell.paste(
                    seg,
                    (
                        (i % cols) * sub_w + (sub_w - seg.width) // 2,
                        top_band + (i // cols) * sub_h + (sub_h - seg.height) // 2,
                    ),
                )
        panels.append(cell)
    if not panels:
        return None
    for pos, panel in enumerate(panels, start=1):
        draw = ImageDraw.Draw(panel)
        draw.rectangle([0, 0, 52, 30], fill="white", outline="black", width=2)
        tag = str(labels[pos - 1]) if labels and pos - 1 < len(labels) else str(pos)
        draw.text((10, 7), tag, fill="black")
    cols = min(_GRID_COLS, len(panels))
    rows = math.ceil(len(panels) / cols)
    grid = Image.new(
        "RGB", (cols * _PANEL_LONG_SIDE, rows * _PANEL_LONG_SIDE), "white"
    )
    for pos, panel in enumerate(panels):
        grid.paste(
            panel,
            ((pos % cols) * _PANEL_LONG_SIDE, (pos // cols) * _PANEL_LONG_SIDE),
        )
    return grid


def _ask_vl(client, grid: Image.Image, *, prompt: str | None = None) -> list:
    """单张合成网格图 → VL → [{id, ...}]（失败抛异常）；prompt 可替换（slot_role 复用）。"""
    from app.grading.pipeline import _get_openai_client, _pil_image_to_data_url

    if client is None:
        client = _get_openai_client()
    data_url = _pil_image_to_data_url(grid)
    completion = client.chat.completions.create(
        model=VL_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": prompt or _INK_EVIDENCE_PROMPT},
                ],
            },
        ],
        stream=False,
        timeout=180,
        extra_body={"enable_thinking": False},
    )
    raw = completion.choices[0].message.content or ""
    return [item for item in _json_array_from_text(raw) if isinstance(item, dict)]


def verify_handwriting_with_vl(
    image_path: str, blocks: list, *, client=None
) -> list:
    """对 blocks 就地执行 VL 笔迹证据复核；返回变更清单（形状对齐 form_guard）。

    候选（双条件防题干块误入）：(baidu_is_slot 或 has_handwriting_location) 且
    _answer_bbox 非空，result ∈ {对,错,半对}，且未被 form_guard 降级。
    任何 VL/解析失败只影响该批候选（不动块），绝不抛出阻断批改。
    """
    if not _env_flag("INK_EVIDENCE_VL", True) or not blocks:
        return []
    max_per_paper = max(1, _env_int("INK_EVIDENCE_MAX_PER_PAPER", 96))
    min_ink = _env_float("INK_EVIDENCE_MIN_INK", 0.0)
    try:
        image = Image.open(image_path).convert("RGB")
    except Exception:
        return []
    changes: list = []
    with image:
        candidates: list = []
        for blk in blocks:
            if len(candidates) >= max_per_paper:
                break  # 超上限 fail-open：其余候选不动
            if not isinstance(blk, dict):
                continue
            # ⛔ 不能只看 reference_vlm_answer_bbox——题干块也有它
            if not (blk.get("baidu_is_slot") or blk.get("has_handwriting_location")):
                continue
            guard = blk.get("form_guard")
            if isinstance(guard, dict) and guard.get("action") == "downgraded":
                continue
            if _norm_result(blk.get("result")) not in ("对", "错", "半对"):
                continue
            bbox = _answer_bbox(blk)
            if bbox is None:
                continue
            if min_ink > 0 and ink_ratio(image, bbox) < min_ink:
                continue
            candidates.append((blk, bbox))
        if not candidates:
            return []
        for start in range(0, len(candidates), _BATCH_SIZE):
            batch = candidates[start : start + _BATCH_SIZE]
            try:
                grid = _compose_labeled_crops(image, [b for _blk, b in batch])
                if grid is None:
                    continue
                items = _ask_vl(client, grid)
            except Exception:
                continue  # fail-safe：本批不动
            by_id: dict = {}
            for item in items:
                try:
                    by_id[int(item.get("id"))] = item
                except Exception:
                    continue
            for pos, (blk, bbox) in enumerate(batch, start=1):
                item = by_id.get(pos)
                if not item:
                    continue  # 模型漏报的面板不动（fail-open）
                has_handwriting = _as_bool(item.get("has_handwriting"))
                if has_handwriting is None:
                    continue
                if has_handwriting:
                    continue
                # 两段式：网格初筛说无笔迹 → 单面板二次确认（网格 conf 退化、
                # 首排易误杀真笔迹），以确认面板的判定与置信为准。
                try:
                    # 确认段用小 pad：默认外扩（30%≤40px）会把邻区笔迹/题干
                    # 拉进裁剪图，空白槽被邻空笔迹污染 → 确认说"有"放行幻觉。
                    confirm_grid = _compose_labeled_crops(image, [bbox], pad=8)
                    confirm_items = (
                        _ask_vl(client, confirm_grid) if confirm_grid is not None else []
                    )
                except Exception:
                    continue  # 确认失败 fail-open：不动块
                confirm_item = next(
                    (c for c in confirm_items if isinstance(c, dict)), None
                )
                if not confirm_item:
                    continue
                confirm_has = _as_bool(confirm_item.get("has_handwriting"))
                if confirm_has is None or confirm_has:
                    continue  # 确认见到笔迹（或解析不出）→ 不动块
                try:
                    confidence = float(confirm_item.get("confidence"))
                except (TypeError, ValueError):
                    confidence = 0.0
                if not (confidence == confidence) or confidence < 0.0 or confidence > 1.0:
                    confidence = 0.0  # NaN/越界按零置信处理（进「什么都不做」档）
                was_result = _norm_result(blk.get("result"))
                trace = {
                    "has_handwriting": False,
                    "confidence": round(confidence, 3),
                    "was_result": was_result,
                    "confirmed": True,
                }
                if confidence > GRAY_MAX and blk.get("baidu_handwriting_bbox"):
                    # 仲裁：百度笔迹检测已框出手写区（handwritingArea 非空），
                    # VL「无笔迹」只当看走眼，绝不能强降级——2026-10-22 汪小燕_1
                    # 两题真笔迹被误报无笔迹、对→未作答，空心圆画到字上。只标记。
                    blk["ink_evidence"] = {
                        "action": "flagged",
                        "suspicious": True,
                        "reason": "引擎已检测到笔迹，VL 判无",
                        **trace,
                    }
                    changes.append(
                        {
                            "index": blk.get("index"),
                            "sub_index": blk.get("sub_index"),
                            "action": "flagged",
                            "reason": "引擎已检测到笔迹，VL 判无",
                            **trace,
                        }
                    )
                elif confidence > GRAY_MAX:
                    # 强降级字段集与 form_guard 完全一致
                    blk["result"] = "未作答"
                    blk["comment"] = ""
                    blk["partial_ratio"] = None
                    blk["baidu_correct_result"] = _RESULT_CODES["未作答"]
                    blk["ink_evidence"] = {"action": "downgraded", **trace}
                    changes.append(
                        {
                            "index": blk.get("index"),
                            "sub_index": blk.get("sub_index"),
                            "action": "downgraded",
                            **trace,
                        }
                    )
                elif confidence >= GRAY_MIN:
                    blk["ink_evidence"] = {"action": "flagged", "suspicious": True, **trace}
                    changes.append(
                        {
                            "index": blk.get("index"),
                            "sub_index": blk.get("sub_index"),
                            "action": "flagged",
                            **trace,
                        }
                    )
    return changes
