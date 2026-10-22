"""形态校验兜底（《科目分层识别引擎方案 v1.0》「一套兜底保险」落地）。

判分与笔迹证据矛盾时拦截，路由/判分错误不静默错判：

- 强矛盾（自动改）：作答区被判 对/错/半对 但该区几乎无笔迹 → 降级「未作答」并清空评语
  （与留痕规则一致：未作答不画任何标记）。顺带把 smart_ref 提示词的空槽编码
  （result=错 + comment=未作答）归一为真「未作答」。注意：只治真空白槽——
  槽内含印刷插图时（小学圈图题常见）ink 恒高，规则不触发，幻觉判分仍靠手动修正端点。
- 弱矛盾（只标记）：有笔迹却被判未作答、判错却无理由 → 仅打 form_guard.suspicious，不改判。

只对「作答区」生效：baidu_is_slot=True 或有 reference_vlm_answer_bbox /
has_handwriting_location 的块；题干大块（bbox=questionArea 含印刷内容）跳过
ink 检查——否则印刷字全算笔迹，检查失效。ai-correct 人工修正不接此兜底。
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
from PIL import Image

# 阈值实测校准（2026-10-09，王浩然_1 真实卷回放）：
# - 强规则治「真空白作答区被编判分」——含 smart_ref 空白槽编码（错+comment=未作答）。纯白槽 ink≈0。
# - ⚠️ 插图槽拦不住：印刷插图本身即墨（茄子/皮球槽 ink≈0.21–0.32），像素分不出印刷品与手写笔迹，
#   「插图+编造判分」类幻觉（判错并声称学生圈选）仍走手动修正端点处理。
# - 弱规则在插图题上会误标（仅标记不改判）：印刷插图槽 result=未作答 时 ink>0.01 必触发。
EMPTY_INK_RATIO = 0.002  # 作答区暗像素占比低于此视为无笔迹
SUSPICIOUS_INK_RATIO = 0.01  # 作答区暗像素占比高于此视为有笔迹
_INK_BBOX_PAD = 4  # bbox 外扩像素，防 handwritingArea 贴太紧漏检笔迹
_RESULT_CODES = {"对": 1, "错": 2, "未作答": 3, "半对": 4}
# 反向闸阈值同 reference_vlm_grading._BLANK_INK_STU_MAX：真笔迹下限；
# 空白只有印刷线时实测 0.028–0.073。
UNANSWERED_INK_MIN = 0.12
_UNANSWERED_INK_REASON = "作答区有笔迹但机改判未作答，待人工确认"


def _norm_result(result: Any) -> str:
    """归一判分文本：「半对（0.6）」→「半对」。"""
    text = str(result or "").strip()
    if text.startswith("半对"):
        return "半对"
    return text


def _answer_bbox(block: dict) -> Optional[list]:
    """取「作答区」bbox；非作答区块（题干大块）返回 None 跳过 ink 检查。"""
    candidates = [block.get("reference_vlm_answer_bbox")]
    if block.get("baidu_is_slot") or block.get("has_handwriting_location"):
        candidates.append(block.get("bbox"))
    for box in candidates:
        if isinstance(box, (list, tuple)) and len(box) >= 4:
            try:
                x1, y1, x2, y2 = (float(v) for v in box[:4])
            except (TypeError, ValueError):
                continue
            if x2 > x1 and y2 > y1:
                return [x1, y1, x2, y2]
    return None


def ink_ratio(image: Image.Image, bbox: list) -> float:
    """作答区暗像素占比：裁剪 → 灰度 → 暗 = 灰度 < 局部背景 - 18（同 _load_dark 思路）。

    ⚠️ 墨迹占比 >30% 时背景分位会塌进墨里（bg≈墨色）→ 恒返回 0，
    密集手写会被误判成纯空白——调用方需用 dark_fraction 复核（2026-10-22）。
    """
    w, h = image.size
    x1 = max(0, int(bbox[0]) - _INK_BBOX_PAD)
    y1 = max(0, int(bbox[1]) - _INK_BBOX_PAD)
    x2 = min(w, int(bbox[2]) + _INK_BBOX_PAD)
    y2 = min(h, int(bbox[3]) + _INK_BBOX_PAD)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    if image.mode != "L":
        image = image.convert("L")
    gray = image.crop((x1, y1, x2, y2))
    a = np.asarray(gray).astype(np.float32)
    if a.size == 0:
        return 0.0
    # 作答区纸面占大头 → 70 分位作背景；纯白区 ratio≈0，有笔迹则明显升高
    bg = float(np.percentile(a, 70))
    dark = a < (bg - 18)
    return float(dark.mean())


def dark_fraction(image: Image.Image, bbox: list) -> float:
    """绝对暗像素比（灰度<200）：不依赖背景分位，墨迹再密也量得出。"""
    w, h = image.size
    x1 = max(0, int(bbox[0]) - _INK_BBOX_PAD)
    y1 = max(0, int(bbox[1]) - _INK_BBOX_PAD)
    x2 = min(w, int(bbox[2]) + _INK_BBOX_PAD)
    y2 = min(h, int(bbox[3]) + _INK_BBOX_PAD)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    if image.mode != "L":
        image = image.convert("L")
    gray = image.crop((x1, y1, x2, y2))
    a = np.asarray(gray).astype(np.float32)
    if a.size == 0:
        return 0.0
    return float((a < 200.0).mean())


def apply_form_guard(image_path: str, blocks: list) -> list:
    """对 blocks 就地执行形态校验；返回变更清单（供摘要/日志用）。

    强矛盾：result ∈ {对,错,半对} 且 ink_ratio < EMPTY_INK_RATIO
      → result=未作答、comment=""、partial_ratio=None、baidu_correct_result=3，
        block 记 form_guard:{action:"downgraded", ink_ratio, was_result}。
    弱矛盾：未作答但有笔迹 / 判错无理由
      → block 记 form_guard:{suspicious:true, reason}，不改判。
    """
    if not blocks:
        return []
    try:
        image = Image.open(image_path)
    except Exception:
        return []
    if image.mode != "L":
        image = image.convert("L")
    changes: list = []
    with image:
        for blk in blocks:
            if not isinstance(blk, dict):
                continue
            bbox = _answer_bbox(blk)
            if bbox is None:
                continue
            ratio = ink_ratio(image, bbox)
            result = _norm_result(blk.get("result"))
            # 双复核：ink_ratio 在墨迹>30% 时塌成 0（背景分位落进墨里），密集
            # 手写会被误降成未作答 → 绝对暗像素比再说一遍「有墨不降」
            if (
                result in ("对", "错", "半对")
                and ratio < EMPTY_INK_RATIO
                and dark_fraction(image, bbox) < 0.05
            ):
                blk["result"] = "未作答"
                blk["comment"] = ""
                blk["partial_ratio"] = None
                blk["baidu_correct_result"] = _RESULT_CODES["未作答"]
                blk["form_guard"] = {
                    "action": "downgraded",
                    "ink_ratio": round(ratio, 5),
                    "was_result": result,
                }
                changes.append(
                    {
                        "index": blk.get("index"),
                        "sub_index": blk.get("sub_index"),
                        "action": "downgraded",
                        "was_result": result,
                        "ink_ratio": round(ratio, 5),
                    }
                )
                continue
            reason = None
            if result == "未作答" and ratio > SUSPICIOUS_INK_RATIO:
                reason = "有笔迹判未作答"
            elif result == "错" and not str(blk.get("comment") or "").strip():
                reason = "判错无理由"
            if reason:
                blk["form_guard"] = {
                    "suspicious": True,
                    "reason": reason,
                    "ink_ratio": round(ratio, 5),
                }
                changes.append(
                    {
                        "index": blk.get("index"),
                        "sub_index": blk.get("sub_index"),
                        "action": "flagged",
                        "reason": reason,
                        "ink_ratio": round(ratio, 5),
                    }
                )
    return changes


def apply_unanswered_ink_guard(image_path: str, blocks: list) -> list:
    """反向闸：判「未作答」但作答区有手写笔迹 → 改「待确认」（不画圈，交老师拍板）。

    空白闸的反向缺口（同 reference_vlm_grading._apply_unanswered_ink_guard 语义）：
    有字被判没作答 ≠ 学生没写，绝不能画空心圆压到字上。只对有真实作答区框的块
    生效（baidu_handwriting_bbox 非空——百度笔迹检测确实框出了手写区）；bbox 兜底
    成 questionArea 的块不适用：题干印刷字全算墨迹，量不准。人工终态/已降级不动。
    """
    if not blocks:
        return []
    try:
        image = Image.open(image_path)
    except Exception:
        return []
    if image.mode != "L":
        image = image.convert("L")
    changes: list = []
    with image:
        for blk in blocks:
            if not isinstance(blk, dict):
                continue
            if _norm_result(blk.get("result")) != "未作答":
                continue
            guard = blk.get("form_guard")
            if isinstance(guard, dict) and guard.get("action") in ("downgraded", "pending_high_ink"):
                continue
            box = blk.get("baidu_handwriting_bbox")
            if not (isinstance(box, (list, tuple)) and len(box) >= 4):
                continue
            try:
                ratio = ink_ratio(image, [float(v) for v in box[:4]])
            except Exception:
                continue
            if ratio < UNANSWERED_INK_MIN:
                continue
            blk["result"] = "待确认"
            blk["comment"] = _UNANSWERED_INK_REASON
            blk["partial_ratio"] = None
            blk["baidu_correct_result"] = 5  # 待确认（同 reference_vlm PENDING 码）
            blk["form_guard"] = {
                "action": "pending_high_ink",
                "ink_ratio": round(ratio, 5),
                "was_result": "未作答",
            }
            changes.append(
                {
                    "index": blk.get("index"),
                    "sub_index": blk.get("sub_index"),
                    "action": "pending_high_ink",
                    "ink_ratio": round(ratio, 5),
                }
            )
    return changes
