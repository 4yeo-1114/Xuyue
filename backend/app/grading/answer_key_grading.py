# -*- coding: utf-8 -*-
"""答题卡按标准答案自动比对：解析答案文本/图片 → 逐作答区抽取学生答案 → 判定对错。

与「答题卡（自主阅卷）」(manual) 复用同一套作答区模板（slot/bbox/label）。
答案比对面向客观题与填空（答案唯一/明确的题型），确定性、快、省；主观题仍走智能批改引擎。
"""
import json
import os
import re
import time
from collections import Counter
from typing import Optional

from PIL import Image

from app.grading.pipeline import (
    _enhance_crop_for_vl,
    _get_openai_client,
    _pil_image_to_data_url,
    _transcription_flagged,
)
from app.utils.qwen_settings import get_vl_model

# ---- 答案文本解析 ----

# 条目起点两种形态（答案体不再按字符集截断，避免把 0.5 / 1.08×10⁵ / -3 截碎）：
#   ①多空「5.1 B」：题号[._]空号 + 空白（空号后必须跟空白，防 9.0.5 被当 9 题第 0 空）
#   ②单空「1.A」「1. 0.5」：题号 + 分隔符
_ENTRY_START_RE = re.compile(r"(?:^|\s)(?:(\d{1,3})[._](\d)\s+(?=\S)|(\d{1,3})\s*[.．、:：]\s*)")
# 连续题号：1-5 ABCDA → 1=A 2=B 3=C 4=D 5=A。
# 答案部分只认选项字母串（A-D）：否则「2-3 m」这类数值答案行会被误当成题号范围。
_RANGE_RE = re.compile(r"^\s*(\d+)\s*[-–—]\s*(\d+)\s+([A-Da-d]{2,})\s*$")


def _split_entries(line: str) -> list[tuple[int, Optional[int], str]]:
    """把一行拆成 [(题号, 空号|None, 答案), ...]。

    题号必须递增（多空题同题号下空号递增）才算新条目起点；否则视为答案内部的数字
    （如「1. 0.5 2. …」里的 0、5 不能单独成为题号）。
    """
    cands: list[tuple[int, int, int, Optional[int]]] = []
    for m in _ENTRY_START_RE.finditer(line):
        if m.group(1) is not None:
            cands.append((m.start(), m.end(), int(m.group(1)), int(m.group(2))))
        else:
            cands.append((m.start(), m.end(), int(m.group(3)), None))
    starts: list[tuple[int, int, int, Optional[int]]] = []
    prev_no: Optional[int] = None
    prev_sub: Optional[int] = None
    for cand in cands:
        num, sub = cand[2], cand[3]
        if prev_no is None:
            starts.append(cand)
            prev_no, prev_sub = num, sub
            continue
        if sub is not None and num == prev_no and (prev_sub is None or sub > prev_sub):
            starts.append(cand)
            prev_sub = sub
            continue
        if num > prev_no:
            starts.append(cand)
            prev_no, prev_sub = num, sub
    out: list[tuple[int, Optional[int], str]] = []
    for i, cand in enumerate(starts):
        num, sub, seg_start = cand[2], cand[3], cand[1]
        seg_end = starts[i + 1][0] if i + 1 < len(starts) else len(line)
        segment = line[seg_start:seg_end].strip()
        if segment:
            out.append((num, sub, segment))
    return out


def _merge_line_entries(result: dict, line: str) -> None:
    """把一行按「题号.答案」逐条解析进 result（兼容 1.A 2.C 3.√ 这种一行多题）。"""
    for num, sub, ans in _split_entries(str(line or "").strip()):
        result.setdefault(f"{num}_{sub}" if sub is not None else f"{num}_1", ans)


def parse_answer_key_text(text: str) -> dict[str, str]:
    """把标准答案文本解析为 {题号_空号: 答案}（键与 slot 的 label「N_M」一致）。

    支持格式（可混用，可一行一条或空格分隔多条）：
      1.A 2.C 3.√         单空题（键 1_1 / 2_1 / 3_1）
      5.1 B 5.2 D         多空题（键 5_1 / 5_2）
      1-5 ABCDA           连续题号
      每行一题（PDF/图片识别常见）：
        1.不做功
        15.(1)18 km/h (2)1.08×10⁵ J   整行作为该题答案，避免把答案里的数字（1000 m 等）误当题号
    """
    result: dict[str, str] = {}
    text = str(text or "")
    lines = [l.strip() for l in re.split(r"[\n\r;；]+", text) if l.strip()]
    if not lines:
        return result

    # 每行一题判定：绝大多数行以「题号.答案」开头 → 整行即该题答案。
    # 每行一律整行保留为单空（不按空格拆），避免把「2 变大」「弹性势能 重力势能」
    # 这类填空题的多空答案拆成多条（按题计数，21 题 = 21 条）。
    line_led_re = re.compile(r"^(\d+)\s*[.、．:：]\s*(.+)$")
    led = [line_led_re.match(l) for l in lines]
    any_multi_entry = any(len(_split_entries(l)) >= 2 for l in lines)
    if (
        len(lines) >= 2
        and not any_multi_entry
        and sum(bool(m) for m in led) >= max(2, len(lines) - 1)
    ):
        for m in led:
            if not m:
                continue
            q = m.group(1)
            ans = m.group(2).strip()
            if not ans:
                continue
            # 重复题号保留第一次出现，不让后面的杂音覆盖已解析答案
            result.setdefault(f"{q}_1", ans)
        return result

    for line in lines:
        m = _RANGE_RE.match(line)
        if m:
            start = int(m.group(1))
            end = int(m.group(2))
            answers = m.group(3)
            if end < start:
                start, end = end, start
            span = end - start + 1
            parts = answers.split()
            if len(parts) == span:
                seq = parts
            else:
                seq = list(answers)
            for i, ans in enumerate(seq):
                if i >= span:
                    break
                result[f"{start + i}_1"] = ans.strip()
            continue
        _merge_line_entries(result, line)
    return result


# ---- 答案图片识别 ----

_ANSWER_KEY_IMAGE_PROMPT = (
    "这是试卷的标准答案。请提取每题答案，按「题号.答案」格式逐条输出，"
    "例如「1.A 2.C 3.√」。多空题按「题号.空号 答案」输出，例如「5.1 B 5.2 D」。"
    "只输出答案列表本身，不要任何解释、不要加序号以外的文字。"
)


def _extract_answer_key_text_from_pil(im) -> str:
    """单张 PIL 图像 → 千问 VL → 答案文本（失败返回空串）。"""
    try:
        client = _get_openai_client()
        data_url = _pil_image_to_data_url(im)
        completion = client.chat.completions.create(
            model=get_vl_model(),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": _ANSWER_KEY_IMAGE_PROMPT},
                    ],
                },
            ],
            stream=False,
            extra_body={"enable_thinking": False},
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception:
        return ""


def extract_answer_key_text_from_image(image_path: str) -> str:
    """用千问 VL 读取标准答案图片，返回可交给 parse_answer_key_text 的文本。"""
    try:
        with Image.open(image_path) as im:
            return _extract_answer_key_text_from_pil(im)
    except Exception:
        return ""


def extract_answer_key_text_from_document(path: str) -> str:
    """把标准答案文档（PDF/Word）逐页转图并识别，返回可解析的答案文本。"""
    from app.grading import doc_convert

    ext = os.path.splitext(path or "")[1].lower()
    try:
        if ext == ".pdf":
            images = doc_convert.pdf_to_images(path)
        elif ext in (".doc", ".docx"):
            images = doc_convert.docx_to_images(path)
        else:
            return ""
    except Exception:
        return ""
    parts: list[str] = []
    for im in images:
        text = _extract_answer_key_text_from_pil(im)
        if text:
            parts.append(text)
    return "\n".join(parts)


def extract_answer_key_from_image(image_path: str) -> dict[str, str]:
    """读取标准答案图片并解析为 {题号_空号: 答案}。"""
    return parse_answer_key_text(extract_answer_key_text_from_image(image_path))


# ---- 学生答案抽取 ----

_STUDENT_ANSWER_PROMPT = (
    "这是答题卡中的一个作答区。请只输出学生在该区域写下的答案内容本身"
    "（例如 A / B / √ / × / 42 / 单词 / 公式结果等），不要任何解释、不要带「答案」二字。"
    "如果该区域是空白、没有作答，只输出一个空字符串。\n"
    "⚠️ 划掉重写（非常重要）：学生常先写一个答案、用一两条斜线或横线划掉，再在旁边"
    "（上方/后面/下一行）写新的答案。这时**只输出没有被划掉的最终答案**；被划掉的答案"
    "一律不要写进来。判断「划掉」的依据是：有细长的直线/斜线**穿过字母或数字中间**——"
    "下划线、括号、自然的笔锋不算划掉。若存在两处未被划掉的写法，取位置更靠后/更靠下/更靠右的那个。\n"
    "看不清的单字用 [?] 占位，两种读法都像的写 [字1|字2]；不要猜、不要照着常见答案脑补。"
)


def _clean_student_answer(text: str) -> str:
    t = str(text or "").strip()
    t = re.sub(r"^答案(是|为)?\s*[:：]\s*", "", t)
    return t.strip("。．.、,，;；:： \t\n\r")


def _valid_bbox(bbox, width: int, height: int) -> Optional[list[int]]:
    if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
        return None
    try:
        x1, y1, x2, y2 = (int(v) for v in bbox[:4])
    except (TypeError, ValueError):
        return None
    if x1 >= x2 or y1 >= y2:
        return None
    x1 = max(0, min(width - 1, x1))
    y1 = max(0, min(height - 1, y1))
    x2 = max(1, min(width, x2))
    y2 = max(1, min(height, y2))
    if x1 >= x2 or y1 >= y2:
        return None
    return [x1, y1, x2, y2]


def extract_student_answer(image_path: str, bbox) -> Optional[str]:
    """按作答区 bbox 裁剪并让千问 VL 读出学生答案。

    返回 None 表示抽取失败（VLM 异常，交由老师手动判）；返回 "" 表示空白未作答。
    """
    try:
        client = _get_openai_client()
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            width, height = im.size
            box = _valid_bbox(bbox, width, height)
            if box is None:
                return None
            crop = im.crop(tuple(box))
            data_url = _pil_image_to_data_url(_enhance_crop_for_vl(crop), max_side=1600)
        completion = client.chat.completions.create(
            model=get_vl_model(),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": _STUDENT_ANSWER_PROMPT},
                    ],
                },
            ],
            stream=False,
            extra_body={"enable_thinking": False},
        )
        return _clean_student_answer(completion.choices[0].message.content or "")
    except Exception:
        return None


def _flatten_answer_text(text: str, question_no: int) -> str:
    """读出的标准答案压成单行：换行→空格、分号→逗号（答案行按 ; 断行，防串题）。

    去掉误带的印刷题号「N.」前缀——仅当后面不是数字（避免误伤 1.08×10⁵ 这类答案）。
    """
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    value = value.replace(";", "，").replace("；", "，")
    if question_no > 0:
        value = re.sub(rf"^{question_no}\s*[.、．:：]\s*(?!\d)", "", value).strip()
    return value


def extract_answer_key_from_answer_card(image_path: str) -> tuple[dict[str, str], str]:
    """带标准答案的答题卡 → 与学生卷同一把刀切格 → 逐格读标准答案。

    切格走 build_manual_layout_page_from_boxes（学生答题卡同一链路），题号/label
    「N_M」与学生卷 block 完全同一编号体系，答案键按键对位即可进
    grade_paper_by_answer_key。每格读法：选择题格 OMR 涂黑检测 → VL 读涂卡；
    其余格 VL 转写（extract_student_answer）。

    返回 (answers{label: 答案}, 原文行)；原文行单空题「N.答案」、多空题
    「N.1 答案 N.2 答案」一行一题（与答案弹窗的解析格式互认）。
    切不出作答格/读不出任何答案抛 RuntimeError。
    """
    from pathlib import Path

    from app.grading.manual_grading import build_manual_layout_page_from_boxes

    page = build_manual_layout_page_from_boxes(
        image_path, page_no=1, filename=Path(str(image_path)).name, image_url=""
    )
    questions = [q for q in (page.get("questions") or []) if isinstance(q, dict)]
    if not questions:
        raise RuntimeError("答题卡切分未识别出作答格（请确认上传的是带印刷框线的答题卡）")

    answers: dict[str, str] = {}
    lines: list[str] = []
    for question in questions:
        kind = str(question.get("kind") or "")
        try:
            num = int(question.get("display_no") or 0)
        except (TypeError, ValueError):
            num = 0
        slot_vals: list[tuple[str, str]] = []
        for slot in question.get("answer_slots") or []:
            if not isinstance(slot, dict):
                continue
            label = str(slot.get("label") or "").strip()
            bbox = slot.get("bbox")
            if not label or not bbox:
                continue
            if kind == "choice":
                val = _omr_choice_answer(image_path, bbox)
                if not val:
                    val = _vl_read_choice_answer(image_path, bbox)
                val = val or ""
            else:
                val = extract_student_answer(image_path, bbox)
                val = "" if val is None else val
            val = _flatten_answer_text(val, num)
            answers[label] = val
            slot_vals.append((label, val))
        if not slot_vals:
            continue
        if len(slot_vals) == 1:
            lines.append(f"{num}.{slot_vals[0][1]}")
        else:
            parts = []
            for order, (label, val) in enumerate(slot_vals, start=1):
                sub = label.split("_", 1)[1] if "_" in label else str(order)
                parts.append(f"{num}.{sub} {val}")
            lines.append(" ".join(parts))
    if not answers:
        raise RuntimeError("未能从答题卡读出任何标准答案（请确认卡上有手写/涂卡的标准答案）")
    return answers, "\n".join(lines)


# ---- 归一化与比对 ----

_TRUE_MARKS = {"√", "✓", "✔", "对", "正确", "是"}
_FALSE_MARKS = {"×", "✗", "✘", "✖", "错", "错误", "否"}


def normalize_answer(s) -> str:
    """去空白、全角转半角、转大写，并统一 对/错 符号。"""
    if s is None:
        return ""
    text = str(s)
    out: list[str] = []
    for ch in text:
        if ch in (" ", "\t", "\n", "\r", "　", "\xa0"):
            continue
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        else:
            out.append(ch)
    text = "".join(out).strip().upper()
    if text in _TRUE_MARKS:
        return "对"
    if text in _FALSE_MARKS:
        return "错"
    return text


def match_answers(student: str, expected: str) -> str:
    """比较学生答案与标准答案，返回 对 / 错 / 未作答。"""
    s = normalize_answer(student)
    e = normalize_answer(expected)
    if not s:
        return "未作答"
    if not e:
        return "错"
    if s == e:
        return "对"
    # 多选题（标准答案为 A-D 多字母）：字母序列按字符排序后比较（ABD == DAB）；
    # 不等即错——少选/多选都不许走下面的「包含即对」误判成对
    # （少选=半对的比例分由选择题支路的字母集合比对给出，这里只兜底对/错）。
    if re.fullmatch(r"[A-Da-d]{2,}", e):
        s_letters = re.sub(r"[^A-Za-z]", "", s)
        return "对" if "".join(sorted(s_letters)) == "".join(sorted(e)) else "错"
    # 填空/简答：非纯数字且较长的答案互相包含时视为对（避免 12 误含 2 这类数字误判）
    if not e.isdigit() and not s.isdigit() and len(e) >= 2 and len(s) >= 2:
        if e in s or s in e:
            return "对"
    return "错"


def _block_answer_key(block: dict) -> str:
    label = str(block.get("label") or "").strip()
    if label and re.fullmatch(r"\d+_\d+", label):
        return label
    return f"{block.get('index')}_{block.get('sub_index')}"


def _snap_int(v: float) -> float:
    """得分归到整数（卷面最小分值单位 1，不允许小数点），四舍五入。"""
    if v <= 0:
        return 0.0
    return float(int(v + 0.5))


def _split_expected_blanks(expected: str, q: int) -> list[str]:
    """把「1 做功 1.2 不做功 1.3 功率」拆成 [做功, 不做功, 功率]（题号 q 用于识别 q.N 空号标记）。"""
    e = (expected or "").strip()
    if not e:
        return []
    # 第一空标记是被拆散后的裸「1」（"q.1" 被 parse 成 "q" 题号 + "1" 空号）
    if e.startswith("1 "):
        e = e[2:].strip()
    elif e == "1":
        return []
    if not e:
        return []
    marker = re.compile(rf"\b{q}\.(?:\d+)\s+")
    parts = marker.split(e)
    return [p.strip() for p in parts if p.strip()]


def _fillin_hit_ratio(student: str, expected: str, q: int, blanks: Optional[list] = None) -> float:
    """填空按空判分：逐空比对，返回命中空数 / 总空数（0~1）。

    blanks 传入时直接用该空列表（多空题已按空号拆好），不再对 expected 二次切分。
    """
    blanks = blanks if blanks else _split_expected_blanks(expected, q)
    if not blanks:
        return 0.0
    s = normalize_answer(student)
    if not s:
        return 0.0
    hit = 0
    for blank in blanks:
        b = normalize_answer(blank)
        if not b:
            continue
        # 单空内多个并列答案（空格/顿号/逗号分隔）：命中过半即算该空对
        items = [x for x in re.split(r"[、,，;；/]", b) if x.strip()]
        if len(items) >= 2:
            matched = sum(1 for x in items if x in s)
            if matched * 2 >= len(items):
                hit += 1
        elif b in s:
            hit += 1
    return hit / len(blanks)


# ---- 答案集合无序比对（20261112 用户定规则） ----

# 只掐首尾句读/括号引号；⚠️ 不剥 -/—/~：负号答案「-5」剥了会和「5」假相等。
_EDGE_PUNCT_RE = re.compile(
    r"^[\s。．.,，、;；:：!！?？·…（）()\[\]【】「」『』“”‘’\"']+"
    r"|[\s。．.,，、;；:：!！?？·…（）()\[\]【】「」『』“”‘’\"']+$"
)


def _set_rule_normalize(text: str) -> str:
    """答案集合无序比对的归一化：normalize_answer 后掐掉首尾标点（转写常带句读）。"""
    return _EDGE_PUNCT_RE.sub("", normalize_answer(text))


def _answer_set_is_objective(text: str) -> bool:
    """选项字母 / 判断对错类标准答案：按小问对位，不进无序集合比对。

    「A、B」「ABD」「√」这类答案换个空填就不对，跟「地图的三要素」文字填空不是
    一回事。剥掉常见分隔/括号后剩纯 A-D 字母（≤4）、或归一化后是对/错，即是。
    """
    t = _set_rule_normalize(text)
    if t in ("对", "错"):
        return True
    compact = re.sub(r"[\s、,，;；/|｜()（）\[\]【】.．:：]+", "", t)
    return bool(re.fullmatch(r"[A-D]{1,4}", compact))


def _answer_set_matches(students: list[str], standards: list[str]) -> bool:
    """学生各空答案多重集 == 标准各空答案多重集（归一化严格相等，含重复计数）。"""
    return Counter(_set_rule_normalize(s) for s in students) == Counter(
        _set_rule_normalize(e) for e in standards
    )


def _apply_answer_set_rule(blocks, decisions: dict) -> None:
    """答案集合无序比对（20261112 用户定规则，「地图的三要素」三空不按顺序填也算对）。

    同题（同 index）≥2 个作答区都各有标准/学生答案：逐位比对没全对时，再看整题
    答案集合——学生各空答案的多重集与标准多重集归一化后完全一致（只是填的顺序
    不同）→ 整题各空一律判对。宁缺勿串：
    - 任一空 ungraded/未作答/读不准/缺标准或学生文本 → 整题不碰（交人工）；
    - 选择题块/纯选项字母或对错判断标准不适用（按小问对位，不许跨空对调）；
    - 只认归一化严格相等（词形近似/单位换算不进此规则）。
    """
    groups: dict = {}
    for index, block in enumerate(blocks or []):
        if not isinstance(block, dict):
            continue
        slot_id = str(block.get("slot_id") or f"slot-{index + 1}")
        groups.setdefault(str(block.get("index") or "").strip(), []).append((slot_id, block))
    for members in groups.values():
        if len(members) < 2:
            continue
        if all(
            str((decisions.get(slot_id) or {}).get("status") or "") == "correct"
            for slot_id, _ in members
        ):
            continue
        students: list[str] = []
        standards: list[str] = []
        for slot_id, block in members:
            dec = decisions.get(slot_id)
            expected = str(block.get("expected_answer") or "").strip()
            student = str(block.get("student_answer") or "").strip()
            if not isinstance(dec, dict) or str(dec.get("status") or "") not in (
                "correct",
                "wrong",
                "partial",
            ):
                break
            if not expected or not student or bool(block.get("read_uncertain")):
                break
            if block.get("kind") == "choice" or block.get("choice_options"):
                break
            if _answer_set_is_objective(expected):
                break
            students.append(student)
            standards.append(expected)
        else:
            if _answer_set_matches(students, standards):
                note = "各空答案与标准答案集合一致（顺序不同），整题判对"
                for slot_id, block in members:
                    decisions[slot_id] = {"status": "correct"}
                    block["reason"] = note
                    block["analysis"] = note


# ---- 连续错判复核 ----

# 同一页连续 ≥N 道选择题判错 → 打「疑似整块识别异常」复核标记（不改判定）。
CONSECUTIVE_WRONG_THRESHOLD = 3


def _flag_consecutive_wrong(blocks, decisions: dict, threshold: int = CONSECUTIVE_WRONG_THRESHOLD) -> None:
    """连续错判复核：按 index 排序后，连续 ≥threshold 道选择题判 wrong 的块打 needs_review。

    只打标记 + 追加原因，**不改判定结果**（选择题手写字母读错一整块会成片判错，
    老师复核比自动改判安全）。判定未出现的块（待确认/未作答）会打断连续链。
    """
    if not isinstance(decisions, dict) or threshold < 2:
        return
    rows: list[tuple] = []
    for pos, block in enumerate(blocks or []):
        if not isinstance(block, dict):
            continue
        if not (block.get("kind") == "choice" or block.get("choice_options")):
            continue
        try:
            idx = int(block.get("index") or 0)
        except (TypeError, ValueError):
            idx = 0
        rows.append((idx, pos, block))
    rows.sort(key=lambda r: (r[0], r[1]))
    run: list[dict] = []

    def _flush() -> None:
        if len(run) >= threshold:
            note = f"连续{len(run)}题判错，疑似整块识别异常，建议复核"
            for b in run:
                b["needs_review"] = True
                prev = str(b.get("reason") or "").strip()
                b["reason"] = f"{prev}；{note}" if prev and note not in prev else (prev or note)
                print(
                    f"[choice] index={b.get('index')} slot={b.get('slot_id')} 连续错判复核标记"
                )
        run.clear()

    for _, pos, block in rows:
        slot_id = str(block.get("slot_id") or f"slot-{pos + 1}")
        dec = decisions.get(slot_id)
        if isinstance(dec, dict) and str(dec.get("status") or "") == "wrong":
            run.append(block)
        else:
            _flush()
    _flush()


# ---- 选择题涂卡识别 ----

# 涂卡题 OCR 词形如 "9[A][B][D]"：括号里是「未涂」的选项字母，涂黑项被 2B 盖住、
# OCR 读不到 → 该字母从括号串里缺失。缺失字母即学生所涂选项。
# 实际 OCR 常把同排的 9 和 13 合并成一行（"9[A][B][D]13[B][C]"），或把一题的括号拆成
# 多个词（"9[A][B]" + "[D]"），或把行尾截断（"14[A]["）。因此：按行分组、行内按 x 排序
# 拼接后，用 finditer 逐段匹配（括号间允许空白）；行尾未闭合的 "[" 视为截断跳过。
_CHOICE_FIND_RE = re.compile(r"(\d{1,2})\s*((?:\[+[A-Z]\]\s*)+)")


def _parse_choice_answers(words) -> dict[int, str]:
    """从百度 OCR 词解析选择题涂卡答案，返回 {题号: 所涂字母串（按 ABCD 顺序）}。"""
    out: dict[int, str] = {}
    # 按行分组：同一排选择题的括号常被 OCR 拆成多个词
    rows: list[list] = []  # [[y_center, [word, ...]], ...]
    for w in words or []:
        bbox = w.get("bbox") or [0, 0, 0, 0]
        yc = (bbox[1] + bbox[3]) / 2
        placed = False
        for r in rows:
            if abs(r[0] - yc) < 12:
                r[1].append(w)
                placed = True
                break
        if not placed:
            rows.append([yc, [w]])
    for _, ws in rows:
        ws.sort(key=lambda w: (w.get("bbox") or [0, 0, 0, 0])[0])
        text = " ".join(str(w.get("words") or "") for w in ws)
        for m in _CHOICE_FIND_RE.finditer(text):
            num = int(m.group(1))
            # 不假设任何试卷的选择题题号区间：题号只在块上按 index 取用，
            # 词典里多出来的题号没有块消费也无害；这里不设白名单。
            # 匹配到的括号串后面紧跟未闭合的 "["，说明该题被 OCR 截断 → 跳过
            if text[m.end():].strip().startswith("["):
                continue
            shown = set(re.findall(r"\[+([A-Z])\]", m.group(2)))
            filled = "".join(c for c in "ABCD" if c not in shown)
            if num in out:
                out[num] = "".join(sorted(set(out[num] + filled)))
            else:
                out[num] = filled
    return out


def _ocr_choice_answers(image_path: str, region=None) -> dict[int, str]:
    """OCR 选择题涂卡区域并解析答案；失败返回空 dict（保持 ungraded，交由老师）。

    region 传入 [x0,y0,x1,y1] 时先裁剪再 OCR（全页 OCR 易合并/丢括号，裁剪更稳）。
    """
    try:
        from app.grading.manual_grading import _baidu_ocr_text

        if region is not None:
            import base64
            import io
            import requests as _requests

            from app.grading.manual_grading import ACCURATE_BASIC_URL
            from app.grading.baidu_grading import _get_access_token, _rate_limiter

            with Image.open(image_path) as im:
                im = im.convert("RGB")
                w, h = im.size
                x0, y0, x1, y1 = (int(v) for v in region[:4])
                x0, y0 = max(0, x0), max(0, y0)
                x1, y1 = min(w, x1), min(h, y1)
                if x0 >= x1 or y0 >= y1:
                    return {}
                crop = im.crop((x0, y0, x1, y1))
                buf = io.BytesIO()
                crop.save(buf, format="PNG")
                img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            last_data = {}
            for attempt in range(12):
                _rate_limiter.acquire()
                token = _get_access_token()
                resp = _requests.post(
                    f"{ACCURATE_BASIC_URL}?access_token={token}",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    data={"image": img_b64, "detect_direction": "false"},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                last_data = data
                ec = data.get("error_code")
                if ec in (110, "110", 111, "111"):
                    _get_access_token(force_refresh=True)
                    continue
                # 18: Open api qps request limit reached —— 指数退避（对齐 manual 切题）
                if ec in (18, "18"):
                    wait = min(3.0, 0.3 * (2 ** min(attempt, 4)))
                    time.sleep(wait)
                    continue
                if ec:
                    raise RuntimeError(data.get("error_msg"))
                break
            else:
                raise RuntimeError(f"百度接口持续限流(QPS)，请稍后重试：{last_data}")
            words = []
            for wd in data.get("words_result") or []:
                loc = wd.get("location") or {}
                l = int(loc.get("left") or 0)
                t = int(loc.get("top") or 0)
                wdt = int(loc.get("width") or 0)
                ht = int(loc.get("height") or 0)
                txt = str(wd.get("words") or "").strip()
                if txt:
                    words.append({"words": txt, "bbox": [x0 + l, y0 + t, x0 + l + wdt, y0 + t + ht]})
            return _parse_choice_answers(words)

        return _parse_choice_answers(_baidu_ocr_text(image_path))
    except Exception as e:
        print(f"[choice] 全页 OCR 选项解析失败（转 VL 兜底）: {type(e).__name__}: {e}")
        return {}


def _omr_choice_answer(image_path: str, bbox) -> Optional[str]:
    """选择题涂卡 OMR 检测：识别「涂黑=连续宽暗块」，比 OCR 的「缺失字母=所涂选项」推断更稳。

    每个选项方括号：未涂 = 左竖线 + 字母 + 右竖线（3 段细块，各 ~5-8px，密度 0.2-0.3）；
    涂黑 = 一段连续宽块（~20-30px，密度 0.35+）。题号在最左侧（中心 < 42px）。
    步骤：找暗块 run → 去掉题号 → 取选项区 [left,right] → 四等分槽位 →
    每槽内若存在「宽 >=16px 且密度 >=0.32」的 run 即为涂黑。
    返回涂黑字母串（按 ABCD 顺序）；识别不出返回 None（多选/异常由 OCR 兜底）。
    """
    try:
        from app.grading.answer_card_boxes import _load_dark

        dark, H, W = _load_dark(image_path)
        x0, y0, x1, y1 = [int(v) for v in bbox[:4]]
        x0, x1 = max(0, x0), min(W, x1)
        y0, y1 = max(0, y0 - 8), min(H, y1 + 10)
        if x1 <= x0 + 40 or y1 <= y0:
            return None
        height = y1 - y0
        dens = dark[y0:y1, x0:x1].sum(axis=0) / float(height)  # 索引相对 x0
        active = dens > 0.06
        runs: list[tuple[int, int]] = []
        s = None
        for i, v in enumerate(active):
            if v and s is None:
                s = i
            elif not v and s is not None:
                if i - s >= 3:
                    runs.append((s, i))
                s = None
        if s is not None and len(active) - s >= 3:
            runs.append((s, len(active)))
        # 去掉题号（中心 < 42 的最左块）
        opt_runs = [r for r in runs if (r[0] + r[1]) / 2.0 >= 42]
        if len(opt_runs) < 4:
            return None
        left = min(r[0] for r in opt_runs)
        right = max(r[1] for r in opt_runs)
        if right - left < 40:
            return None
        w = (right - left) / 4.0
        letters = ""
        for i in range(4):
            a = left + i * w
            b = left + (i + 1) * w
            filled = any(
                (re - rs) >= 16
                and float(dens[rs:re].mean()) >= 0.36
                and (rs + re) / 2.0 >= a
                and (rs + re) / 2.0 < b
                for rs, re in opt_runs
            )
            if filled:
                letters += "ABCD"[i]
        return letters or None
    except Exception:
        return None


_CHOICE_READ_PROMPT = (
    "这是答题卡中一道选择题的作答区。学生的作答可能是两种形式之一："
    "①在 A、B、C、D 四个并排选项方框里把某一个涂黑（填涂）；"
    "②直接手写一个选项大写字母（A/B/C/D）填在格子里。"
    "请判断学生选的是哪个选项。\n"
    "注意：手写字母常有连笔，一个连笔的大写 B 可能看起来像数字 13 或 β，"
    "手写 A/C/D 也可能不规范——但这里的答案一定是 A、B、C、D 四个字母之一（或多选时的组合），"
    "绝不会是阿拉伯数字。请据此判断最接近的选项字母。\n"
    "只输出选项字母（按 A、B、C、D 顺序拼接，例如 C 或 AD），不要输出任何解释、不要输出数字。"
    "若格子空白、没有作答或完全无法辨认，只输出一个空行。"
)


# 手写字母识别：双读一致才算数；置信度低于此值且 OMR/OCR 都没明确答案时转人工确认。
CHOICE_READ_MIN_CONFIDENCE = 0.6
# 双读一致但「括号区域」没定位到（退回整块 bbox，可能把印刷选项字母一起读进来）
# 时置信度打折——0.9 * 0.8 = 0.72 仍能直接判，但明显低于正常定位。
CHOICE_NO_BRACKET_PENALTY = 0.8


def _bracket_crop_box(image, bbox, pad: int = 6):
    """在作答区 bbox 内定位「学生作答括号」：取中带最右一组手写墨迹。

    题目文字/印刷选项通常靠左，学生手写答案在右（括号里）。这里只用墨迹几何，
    不依赖任何试卷专属坐标：
    - 只取 bbox 纵向中部（避开排线上下的横线/页眉）；
    - 按列投影暗像素并聚类成「墨迹组」，丢弃纵向覆盖率过高（几乎贯穿整块）的竖线；
    - 取最右一组，宽度超过 bbox 一半视为整行印刷（定位失败）；
    - 纵向中部没有墨迹、但右侧有显著墨迹时，改取横向最右的一组；
    - 任何一步失败都**退回原 bbox**，调用方据此把置信度标低。

    返回 (box[x1,y1,x2,y2], located)。located=False 表示退回的是原 bbox。
    """
    import numpy as np

    width, height = image.size
    base = _valid_bbox(bbox, width, height)
    if base is None:
        return None, False
    # 与旧实现同样的外扩，容下越线/连笔
    x1, y1, x2, y2 = base
    x1, x2 = max(0, x1 - 8), min(width, x2 + 8)
    y1, y2 = max(0, y1 - 12), min(height, y2 + 12)
    fallback = (x1, y1, x2, y2)
    try:
        g = np.asarray(image.convert("L").crop(fallback), dtype=np.float32)
        h, w = g.shape
        if h < 12 or w < 24:
            return fallback, False
        # 局部背景（1/20 缩略再放大）→ 墨迹掩码；不用整页 _load_dark，省内存
        small = np.asarray(
            Image.fromarray(np.clip(g, 0, 255).astype(np.uint8)).resize(
                (max(1, w // 20), max(1, h // 20))
            )
        ).astype(np.float32)
        bg = np.asarray(
            Image.fromarray(np.clip(small, 0, 255).astype(np.uint8)).resize((w, h))
        ).astype(np.float32)
        dark = g < (bg - 18)
        rows_mid = dark[int(h * 0.2):int(h * 0.8), :]
        col_dark = rows_mid.any(axis=0)
        if not col_dark.any():
            rows_mid = dark
            col_dark = rows_mid.any(axis=0)
        col_cnt = rows_mid.sum(axis=0)
        row_span = dark.sum(axis=0)
        active = col_dark.astype(bool)
        # 聚类：间隙宽于 min(w*8%, 14px) 视为不同墨迹组
        gap_limit = max(3, int(min(w * 0.08, 14)))
        groups: list[list[int]] = []
        start = None
        last = None
        for i, on in enumerate(active):
            if on:
                if start is None:
                    start = i
                last = i
            elif start is not None and i - last > gap_limit:
                groups.append([start, last + 1])
                start = None
        if start is not None:
            groups.append([start, last + 1])
        # 丢弃纵向几乎贯穿整块的竖线/边框
        merged_h = int((y2 - y1) * 0.85)
        groups = [gp for gp in groups if int(row_span[gp[0]:gp[1]].max()) < merged_h]
        groups = [gp for gp in groups if int(col_cnt[gp[0]:gp[1]].sum()) >= 4]
        if not groups:
            return fallback, False
        gx1, gx2 = max(groups, key=lambda gp: gp[1])
        if gx2 - gx1 > (x2 - x1) * 0.6:
            return fallback, False
        bx1 = max(0, x1 + gx1 - pad)
        bx2 = min(width, x1 + gx2 + pad)
        if bx2 - bx1 < 8:
            return fallback, False
        return (bx1, y1, bx2, y2), True
    except Exception:
        return fallback, False


_CHOICE_LETTER_BODY_RE = re.compile(r"^[A-D](?:\s*[A-D/、,，和]+)*$")


def _parse_choice_letters(raw: str) -> list[str]:
    """从 VL 原始输出里取 A-D 字母（去重升序）。不加任何试卷专属假设。

    模型偶尔输出「答案：C」「Answer: B」这类前缀——先取冒号/等号后的主体，主体
    是纯字母串（含分隔符）时只认主体，避免把英文单词 "answer" 里的 A 误读成选项；
    没有前缀/主体不像字母串时才退回收全文 A-D 字母。
    """
    text = str(raw or "").strip()
    if not text:
        return []
    body = re.split(r"[:：=]", text)[-1].strip()
    candidate = body.upper()
    if candidate and _CHOICE_LETTER_BODY_RE.fullmatch(candidate):
        return sorted(set(re.findall(r"[A-D]", candidate)))
    return sorted(set(re.findall(r"[A-D]", text.upper())))


def _vl_read_choice_once(image, box) -> Optional[str]:
    """单次读：裁 box → 千问 → 原始文本。异常返回 None（与「读出空」区分开）。"""
    try:
        client = _get_openai_client()
        crop = image.crop((int(box[0]), int(box[1]), int(box[2]), int(box[3])))
        data_url = _pil_image_to_data_url(_enhance_crop_for_vl(crop), max_side=1600)
        completion = client.chat.completions.create(
            model=get_vl_model(),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": _CHOICE_READ_PROMPT},
                    ],
                },
            ],
            stream=False,
            extra_body={"enable_thinking": False},
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception:
        return None


def _vl_read_choice_answer_detailed(image_path: str, bbox) -> dict:
    """选择题手写字母识别（详细版）：gated 双读 + 括号区域定位 + 置信度。

    流程：bbox 内定位作答括号 → 读两次（第二次轻微外扩 + 1.5 倍放大）→
    两次字母集合一致才给结论。返回 dict：
      letters     "C"/"AD"（一致时），""（两次都空），None（不一致/异常/无法判断）
      confidence  0~1（不一致 0.2、异常 0.0、两次都空 0.85、
                  一致 0.9（括号定位失败 ×0.8）；多字母结论封顶 0.75）
      raw1/raw2   两次原始输出，便于老师/日志回溯
      bracket_located  是否定位到了作答括号（False = 退货整块 bbox）
      error       两次读取均异常（调用方按「识别失败」处理）
    """
    try:
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            width, height = im.size
            box = _valid_bbox(bbox, width, height)
            if box is None:
                return {"letters": None, "confidence": 0.0, "raw1": None, "raw2": None,
                        "bracket_located": False, "error": True}
            crop_box, located = _bracket_crop_box(im, box)
            if crop_box is None:
                crop_box, located = box, False
            # 第二次：围绕定位区域外扩 + 放大 1.5 倍读一遍（越线/连笔更容易看清）
            bx1, by1, bx2, by2 = crop_box
            pad_x = max(4, int((bx2 - bx1) * 0.2))
            pad_y = max(3, int((by2 - by1) * 0.15))
            wide = (
                max(0, bx1 - pad_x),
                max(0, by1 - pad_y),
                min(width, bx2 + pad_x),
                min(height, by2 + pad_y),
            )
            raw1 = _vl_read_choice_once(im, crop_box)
            raw2 = _vl_read_choice_once(im.resize((im.width * 3 // 2, im.height * 3 // 2),
                                                  Image.LANCZOS),
                                        tuple(v * 3 // 2 for v in wide))
    except Exception:
        return {"letters": None, "confidence": 0.0, "raw1": None, "raw2": None,
                "bracket_located": False, "error": True}
    if raw1 is None and raw2 is None:
        detail = {"letters": None, "confidence": 0.0, "raw1": raw1, "raw2": raw2,
                  "bracket_located": located, "error": True}
        print(f"[choice-vl] bbox={list(bbox or [])} 两次读取均异常")
        return detail
    l1 = _parse_choice_letters(raw1 or "")
    l2 = _parse_choice_letters(raw2 or "")
    base_conf = 0.9 if located else 0.9 * CHOICE_NO_BRACKET_PENALTY
    if l1 and l2 and l1 == l2:
        letters = "".join(l1)
        conf = base_conf if len(l1) == 1 else min(base_conf, 0.75)
    elif not l1 and not l2:
        letters, conf = "", 0.85
    else:
        letters, conf = None, 0.2
    print(
        f"[choice-vl] bbox={list(bbox or [])} crop={list(crop_box)} located={located} "
        f"raw1={raw1!r} raw2={raw2!r} → letters={letters!r} conf={conf:.2f}"
    )
    return {"letters": letters, "confidence": conf, "raw1": raw1, "raw2": raw2,
            "bracket_located": located, "error": False}


def _vl_read_choice_answer(image_path: str, bbox, *, detailed: bool = False):
    """选择题涂卡 VL 兜底：裁剪选项行让千问读出涂黑/手写字母。

    返回 None 表示 VLM 异常；返回 "" 表示无涂黑/无法判断（判未作答）；
    否则返回涂黑字母串（如 "C"、"AD"）。detailed=True 时返回
    _vl_read_choice_answer_detailed 的 dict（供内部拿置信度）。
    """
    doc = _vl_read_choice_answer_detailed(image_path, bbox)
    if detailed:
        return doc
    if doc.get("error"):
        return None
    return doc.get("letters")


# ---- 大题（主观题）千问 VL 语义比对 ----

_SUBJECTIVE_GRADE_PROMPT = (
    "你是一位公正、宽松的考试阅卷老师。下面给你一张「学生作答区」的裁剪图，以及这道题的文字标准答案。"
    "请对照标准答案，语义判定学生作答是否正确。\n"
    "标准答案（唯一判分依据）：\n{EXPECTED}\n\n"
    "总原则：宁对勿错、能对不半。只要核心结论和关键数值对就给分；只有明显缺失或明显错误才降档，"
    "不要吹毛求疵、不要抠字眼。\n"
    "【划掉重写·最高优先】学生常先写一个答案、用一两条斜线/横线划掉，再在旁边写新的答案。"
    "此时**只判没有被划掉的最终答案**：被划掉的不算作答、不抄进 student_answer；"
    "若两处都未被划掉，取位置更靠后/更靠下/更靠右的作为最终答案。"
    "判断「划掉」的依据是细长直线/斜线**穿过字母数字中间**——下划线、括号、自然笔锋不算。"
    "能看到划线但分不清哪处是最终答案 → correctResult 填 5（待确认），不要猜。\n"
    "判定规则：\n"
    "0. question_id 固定填 {QID}，不要改成卷面题号或别的数字。\n"
    "1. 只判这张裁剪图里的作答，不要把别的题算进来。\n"
    "2. 判「对」（correctResult=1）：所有小问的核心结论、关键数值都正确即判对。以下情况一律算对：\n"
    "   - 措辞不同但语义等价（如「物重」=「物体重力」=「物块重力」、「减小」=「变小」、"
    "「在斜面上匀速拉动物体」=「将木块匀速直线地拉动」）。\n"
    "   - 关键数值在作答中明确出现（单独列出或夹在计算过程里都算写出）。\n"
    "   - 单位笔误（1500cm 与 1500m、108000J 与 1.08×10⁵J）、符号化表达（用 W 表示功、mgh/t 写成 W/t）、"
    "书写不规范、过程简略、多余中间步骤。\n"
    "   只要看不出明显错误或缺失，就判「对」，不要降档。\n"
    "3. 只有「明显缺失某一小问」或「某小问结论/关键数值明显错误」，才判「半对」（correctResult=4、result=「半对」），"
    "partial_ratio = 写对的小问数 / 总小问数（0~1 的小数），向上取整到 0.1（如 3 小问对 2 小问给 0.7，不是 0.5）。"
    "correctResult 必须与 result 一致。\n"
    "4. 全部小问都错、或完全答非所问，判「错」（correctResult=2）。裁剪图空白、没有作答判 3（未作答）。\n"
    "5. student_answer 逐字抄录学生在图里写下的作答内容（空白则为空字符串）；看不清的单字用 [?] 占位，"
    "两种读法都像的写 [字1|字2]，不要猜、不要按标准答案脑补。\n"
    "6. 只要 student_answer 里有 [?] 或 [字1|字2]，且这一点影响对错判断，correctResult 填 5、result 填「待确认」，"
    "reason 写明哪部分认不清；宁可「待确认」交还老师，也不许硬判成对或错。\n"
    "7. reason / analysis 用中文，写明对错原因；不要用 TeX/LaTeX/反斜杠/美元符，"
    "用 Unicode 数学符号（如 √、²、×、÷、≈）。\n"
    "8. 只返回一个合法 JSON 对象，不要 Markdown 代码块、不要多余字段。\n\n"
    "JSON 结构：\n"
    '{"question_id":{QID},"correctResult":1,"result":"对","reason":"...","analysis":"...",'
    '"confidence":0.0,"partial_ratio":null,"student_answer":"学生写的内容"}'
)

_FILLIN_GRADE_PROMPT = (
    "你是一位公正、宽松的阅卷老师。下面给你一道「填空题」的作答区裁剪图，以及这道题每个空的标准答案。"
    "请对照标准答案，判定学生每个空是否填写正确。\n"
    "标准答案（唯一判分依据，按空列出）：\n{EXPECTED}\n\n"
    "总原则：严格对照标准答案。仅当学生填写内容与标准答案一致、或为明确等价写法（近义词、单位等价）时才判对；"
    "概念相反或明显不同（如把「等于」写成「小于」「大于」、把「减小」写成「增大」）判错。"
    "书写不规范但能辨认出是标准答案的判对。\n"
    "【划掉重写·最高优先】学生常先写一个答案、用一两条斜线/横线划掉，再在旁边写新的答案。"
    "此时**只判没有被划掉的最终答案**：被划掉的不算作答、不抄进 student_answer；"
    "若存在两处未被划掉的写法，取位置更靠后/更靠下/更靠右的作为最终答案。"
    "判断「划掉」的依据是细长直线/斜线**穿过字母数字中间**——下划线、括号、自然笔锋不算。"
    "若能看到划线但分不清哪一处是最终答案 → correctResult 填 5（待确认），不要猜。\n"
    "判定规则：\n"
    "0. question_id 固定填 {QID}，不要改成卷面题号或别的数字。\n"
    "1. 只判这张裁剪图里的填空作答，不要把别的题算进来。\n"
    "2. 某个空判「对」：学生填的内容与标准答案一致，或为等价写法。以下一律算对：\n"
    "   - 近义词（「减小」≈「变小」≈「降低」、「大于」≈「>」、「等于」≈「=」）。\n"
    "   - 单位/符号等价（「60J」≈「每秒做功60J」≈「1s做功60J」≈「每秒做的功为60J」）。\n"
    "   - 书写不规范但能辨认出确实是标准答案的判对。\n"
    "3. 某个空空白、或填的内容与标准答案明显不同，判「错」。字迹潦草到无法确认写的是什么时不要猜"
    "（见规则 7）：既不许照着标准答案脑补成对，也不许硬判成错。\n"
    "4. 全对 result=「对」correctResult=1；全错 result=「错」correctResult=2；"
    "部分对 result=「半对」correctResult=4。correctResult 必须与 result 一致。\n"
    "5. partial_ratio = 写对的空数 / 总空数（0~1 的小数），只有全错才给 0。\n"
    "6. student_answer 逐空抄录学生在图里写下的内容（空白则为空字符串），不要把相邻空的内容搞混；"
    "看不清的单字用 [?] 占位，两种读法都像的写 [字1|字2]。\n"
    "7. 只要 student_answer 里有 [?] 或 [字1|字2]，且这一点影响判分，correctResult 填 5、result 填「待确认」，"
    "reason 写明哪部分认不清；宁可「待确认」交还老师，也不许硬判成对或错。\n"
    "8. reason / analysis 用中文写明对错原因；不要用 TeX/LaTeX/反斜杠/美元符，"
    "用 Unicode 数学符号（如 √、²、×、÷、≈）。\n"
    "9. 只返回一个合法 JSON 对象，不要 Markdown 代码块、不要多余字段。\n\n"
    "JSON 结构：\n"
    '{"question_id":{QID},"correctResult":1,"result":"对","reason":"...","analysis":"...",'
    '"confidence":0.0,"partial_ratio":null,"student_answer":"学生写的内容"}'
)


def _format_fillin_blanks(expected: str, q: int) -> str:
    """把标准答案的原始空号文本（"1 做功 1.2 不做功"）整理成「第1空：做功；第2空：不做功」。"""
    blanks = _split_expected_blanks(expected, q)
    if not blanks:
        return str(expected or "").strip()
    return "；".join(f"第{i}空：{b}" for i, b in enumerate(blanks, 1))


_CODE_TO_STATUS = {1: "correct", 2: "wrong", 3: "unanswered", 4: "partial", 5: "ungraded"}


def _is_subjective_answer(expected: str, question_no: int = 0) -> bool:
    """判断标准答案是否为「计算大题」（需千问 VL 语义比对）。

    大题 15+ 分两类：
    - 计算题（15-17，空数少、学生写完整解题过程）→ VL 语义比对（字符串对不上完整过程）。
    - 实验题（18-21，空数多、离散填空）→ 与填空一样走字符串逐空快判（更稳、不吃非确定分）。
    """
    if question_no >= 15:
        blanks = _split_expected_blanks(expected, question_no) if expected else []
        return len(blanks) <= 4
    if not expected:
        return False
    if re.search(r"\(\d+\)", expected):
        return True
    return len(expected) > 30


def _uncertain_free_text(text) -> str:
    """把转写里的不确定标记去掉，得到「确定读出来的部分」。

    「[?]」删掉；「[甲|乙]」取两个候选都用不上——直接删除该位置（不猜是哪个）。
    用于判断「认不准的字是否影响判分」：删完之后答案仍然完全对得上 → 判对，不必待确认。
    """
    s = str(text or "")
    s = re.sub(r"\[\s*\?+\s*\]", "", s)
    s = re.sub(r"\[[^\[\]|]*\|[^\[\]]*\]", "", s)
    return s.strip()


def _looks_like_multiple_candidates(text, expected_text: str = "") -> bool:
    """转写里是否像「多答案并存」（划掉重写没认干净）——是则不能自动判。

    2026-11-18 客户反馈：学生划掉旧答案再写新的，留痕上 ? 和 ✓/× 混在一起。
    只在**短答案**上判断（长句里的空格是正常词间隔）：
    - 标准答案本身就是多空/多段时，转写的多段是正常逐空作答 → 不算歧义；
    - 出现两个及以上不同的单选项字母（如「A B」「A/B」）；
    - 短答案里被分隔符切成 ≥2 段像答案的内容（如「having be」）。
    """
    cleaned = _uncertain_free_text(text)
    if not cleaned:
        return False
    std = str(expected_text or "").strip()
    if std:
        std_parts = [
            p
            for p in re.split(r"[\s,，、;；/|\\→]+|或", re.sub(r"第\d+空[:：]", "", std))
            if p.strip()
        ]
        if len([p for p in std_parts if re.search(r"[0-9A-Za-z一-鿿]", p)]) >= 2:
            return False
    if len(cleaned) > 16:
        return False
    letters = re.findall(r"(?<![A-Za-z])[A-D](?![A-Za-z])", cleaned.upper())
    if len(set(letters)) >= 2:
        return True
    if len(cleaned) > 10:
        return False
    parts = [p.strip() for p in re.split(r"[\s,，、;；/|\\→]+|或", cleaned) if p.strip()]
    parts = [p for p in parts if re.search(r"[0-9A-Za-z一-鿿]", p)]
    return len(parts) >= 2


def _uncertain_region_is_irrelevant(transcription: str, expected_text: str) -> bool:
    """认不准的部分不影响对错时返回 True。

    判据（只做**保守放行**，任何一步不满足都返回 False，保持待确认）：
    去掉不确定标记后，确定部分包含标准答案的全部关键项（逐空）。
    """
    cleaned = _uncertain_free_text(transcription)
    if not cleaned:
        return False
    expected_blanks = _blanks_from_expected_text(expected_text)
    if not expected_blanks:
        return False
    s = normalize_answer(cleaned)
    hit = 0
    for blank in expected_blanks:
        b = normalize_answer(blank)
        if b and b in s:
            hit += 1
    return hit == len(expected_blanks)


def _blanks_from_expected_text(expected_text: str) -> list[str]:
    """把「第1空：A；第2空：B」或普通答案文本拆成空列表（去标记）。"""
    text = str(expected_text or "").strip()
    if not text:
        return []
    parts = [p for p in re.split(r"[；;]\s*", text) if p.strip()]
    out: list[str] = []
    for p in parts:
        p = re.sub(r"^第\s*\d+\s*空\s*[:：]\s*", "", p.strip())
        if p:
            out.append(p)
    return out or [text]


def _ai_grade_subjective(
    image_path: str,
    bbox,
    expected_text: str,
    question_id: int = 0,
    prompt_template: str = _SUBJECTIVE_GRADE_PROMPT,
    *,
    _retry: bool = True,
) -> Optional[dict]:
    """文本标准答案 + 学生作答裁剪图 → 千问 VL 语义判分。

    返回 {status: correct/wrong/unanswered/partial, partial_ratio, reason, analysis,
    student_answer}；任何异常返回 None（由调用方降级回字符串比对）。
    prompt_template 可换成 _FILLIN_GRADE_PROMPT 用于填空逐空判分。

    2026-11-17 提高确认率：第一次判「待确认」（读不准/自报不确定）时，用**放大 2 倍、
    留边更大**的裁图重问一次；第二次给出确定结论且不含不确定标记 → 采信第二次。
    仍不确定才保持待确认交人工。
    """
    result = _ai_grade_subjective_once(
        image_path, bbox, expected_text, question_id, prompt_template, pad=0, upscale=1
    )
    if result is None:
        return None
    if _retry and (result.get("status") == "ungraded" or result.get("read_uncertain")):
        retry = _ai_grade_subjective_once(
            image_path, bbox, expected_text, question_id, prompt_template, pad=24, upscale=2
        )
        if retry is not None and retry.get("status") not in (None, "ungraded") and not retry.get("read_uncertain"):
            retry["reason"] = (str(retry.get("reason") or "") + "（放大重读后确认）").strip()
            return retry
    return result


def _ai_grade_subjective_once(
    image_path: str,
    bbox,
    expected_text: str,
    question_id: int,
    prompt_template: str,
    *,
    pad: int = 0,
    upscale: int = 1,
) -> Optional[dict]:
    try:
        from app.grading.reference_vlm_grading import _json_object_from_text, _normalize_decision

        client = _get_openai_client()
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            width, height = im.size
            box = _valid_bbox(bbox, width, height)
            if box is None:
                return None
            x1, y1, x2, y2 = box
            if pad:
                # 重读时扩大取景：字迹常贴着框边/被框切掉一半
                x1 = max(0, x1 - pad)
                y1 = max(0, y1 - pad)
                x2 = min(width, x2 + pad)
                y2 = min(height, y2 + pad)
            crop = im.crop((x1, y1, x2, y2))
            if upscale > 1:
                # 重读时放大，提高小字/连笔的可辨性
                crop = crop.resize(
                    (max(1, crop.width * upscale), max(1, crop.height * upscale)),
                    getattr(Image, "LANCZOS", Image.BILINEAR),
                )
            data_url = _pil_image_to_data_url(_enhance_crop_for_vl(crop), max_side=1600)
        prompt = prompt_template.replace("{EXPECTED}", str(expected_text)).replace(
            "{QID}", str(int(question_id or 0))
        )
        completion = client.chat.completions.create(
            model=get_vl_model(),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": prompt},
                    ],
                },
            ],
            stream=False,
            timeout=180,
            extra_body={"enable_thinking": False},
        )
        raw = completion.choices[0].message.content or ""
        data = _json_object_from_text(raw)
        student_answer = str(data.get("student_answer") or "").strip() or None
        norm = _normalize_decision(data, int(question_id or 0))
        status = _CODE_TO_STATUS.get(norm["correctResult"])
        if status is None:
            return None
        # 读不准不判：转写含 [?]/[字|字] 或模型自报「待确认」→ ungraded（交老师手动判），不许蒙。
        # 但「认不准的字不影响判分」时放行（2026-11-17：字迹清晰仍大量待确认，老师认为漏批）：
        # 把 [?]/[甲|乙] 去掉后剩余确定内容仍完整包含标准答案 → 照常判对。
        read_uncertain = bool(
            (student_answer and _transcription_flagged(student_answer))
            or str(data.get("result") or "").strip() == "待确认"
        )
        # 2026-11-18 划掉重写：转写里同时出现多个候选答案（旧答案没划干净被一起读出来）
        # → 模型没分出最终答案，不许自动判，转待人工确认。
        if (
            student_answer
            and _looks_like_multiple_candidates(student_answer, expected_text)
            and not read_uncertain
        ):
            read_uncertain = True
            data["reason"] = (
                f"作答里同时出现多个候选答案（{str(student_answer)[:20]}），"
                "疑似划掉后重写，机器未确认最终答案，请人工确认"
            )
        if read_uncertain:
            if student_answer and _uncertain_region_is_irrelevant(student_answer, expected_text):
                # 不确定的只是一个边角字，关键答案都能确认 → 放行，按对处理
                status = "correct"
                read_uncertain = False
                data["reason"] = (str(data.get("reason") or "") + "（不确定的字不影响关键答案，已判对）").strip()
            elif status != "ungraded":
                status = "ungraded"
        # 模型偶发 correctResult=2(错) 但 result/reason 明确是「半对」：以中文判定为准，
        # 避免大题半对被误判成全错（用户明确要求按半对给分）。
        if status == "wrong" and (
            str(data.get("result") or "").strip() == "半对"
            or re.search(
                r"半对|部分正确|部分错误",
                str(data.get("reason") or "") + str(data.get("analysis") or ""),
            )
        ):
            status = "partial"
            try:
                pr = float(data.get("partial_ratio"))
                norm["partial_ratio"] = min(1.0, max(0.0, pr))
            except (TypeError, ValueError):
                norm["partial_ratio"] = 0.5
        return {
            "status": status,
            "partial_ratio": norm.get("partial_ratio"),
            "reason": norm.get("reason") or "",
            "analysis": norm.get("analysis") or "",
            "student_answer": student_answer,
            # C1：置信度随块落盘，激活 low-confidence 队列（此前恒 NULL）
            "confidence": norm.get("confidence"),
            "read_uncertain": read_uncertain,
        }
    except Exception:
        return None


# match_answers 返回中文对错，这里翻译成 _save_manual_slot_decisions 期望的英文状态码。
_STATUS_TO_MANUAL = {"对": "correct", "错": "wrong", "未作答": "unanswered", "半对": "partial"}


def _block_sub_index(block: dict) -> int:
    """块代表的空号：优先 label「N_M」的 M，其次 sub_index，都没有返回 1。"""
    label = str(block.get("label") or "").strip()
    m = re.fullmatch(r"\d+_(\d+)", label)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return 1
    try:
        return int(block.get("sub_index") or 1)
    except (TypeError, ValueError):
        return 1


def _expected_blanks_for_block(answer_key: dict, block: dict, primary) -> list[str]:
    """收集该块对应题号的全部空（N_1..N_k，按空号顺序），用于多空题消费。

    - 只有 1 个空 → 返回 [该空]（与旧版单空行为一致）；
    - 多个空 → 返回全部非空答案，交由填空判分按空列出（不再丢掉 N_2..N_k）；
    - 一个都没有 → 返回 []（调用方按「标准答案缺失」显式待人工确认）。
    """
    try:
        q = int(block.get("index") or 0)
    except (TypeError, ValueError):
        q = 0
    blanks: list[str] = []
    if q > 0:
        sub = 1
        while sub <= 20:
            value = answer_key.get(f"{q}_{sub}")
            if value is None:
                break
            blanks.append(str(value).strip())
            sub += 1
    if not blanks and primary is not None and str(primary).strip():
        blanks = [str(primary).strip()]
    return [b for b in blanks if b]


def grade_paper_by_answer_key(image_path: str, blocks, answer_key: dict, subject: Optional[str] = None) -> dict:
    """对一张卷的所有作答区做答案比对，返回 {slot_id: {status}}，并就地补充块字段。

    - 选择题：百度 OCR 读涂卡（缺失字母 = 所涂选项）→ 字母比对。
    - 大题（标准答案含 (N) 小问或较长）：千问 VL 语义比对，支持半对 partial + score。
    - 填空/客观：抽取学生答案 → 字符串快判。
    - 没有标准答案、或抽取/VL 失败的 slot：保持 ungraded，交由老师手动判。

    subject（C3 判分缓存身份）：与回写侧共用同一取值，缺省 None 也能成键
    （question_fingerprint 容忍缺席字段）；调用点从 folder meta.json 取。
    """
    from app.grading.verdict_cache import decision_status_from_result, lookup_block

    decisions: dict[str, dict] = {}
    answer_key = answer_key if isinstance(answer_key, dict) else {}
    if not isinstance(blocks, list):
        return decisions

    # 选择题：一次性 OCR 涂卡区域，得到 {题号: 所涂字母}（避免逐题重复调用百度）。
    # 用全页 OCR（region=None）：按 choice 块并集裁剪会把首排（9/13）题号裁掉
    # （块 bbox 只框住括号、不含上方题号，且部分卷整体上移 ~16px），导致 9/13 漏读。
    choice_answers: dict[int, str] = {}
    has_choice = any(
        isinstance(b, dict) and (b.get("kind") == "choice" or b.get("choice_options"))
        for b in blocks
    )
    if has_choice:
        choice_answers = _ocr_choice_answers(image_path, None)

    # 同一题号下是否存在多个独立块（块自己带了不同空号）——有的话每个块各判自己的空，
    # 不把整题所有空合并给第一个块。
    question_subs: dict[int, set] = {}
    for _b in blocks:
        if isinstance(_b, dict):
            try:
                _qk = int(_b.get("index") or 0)
            except (TypeError, ValueError):
                continue
            question_subs.setdefault(_qk, set()).add(_block_sub_index(_b))

    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        slot_id = str(block.get("slot_id") or f"slot-{index + 1}")
        key = _block_answer_key(block)
        expected = answer_key.get(key)
        # 多空题：标准答案有 N_1..N_k 而作答区只切出一个 slot 时，不能只消费 N_1 把
        # 其余空静默丢掉。多空时把全部空按空号顺序列为「第1空：…；第2空：…」交给
        # 填空判分分支逐空判；只有一个空时行为与旧版一致。
        # ⚠️ 该题如果有多个独立块（块各自带不同空号），每个块只判自己那个空，
        # 不合并（否则逐空判会被串成整题）。
        _block_sub = _block_sub_index(block)
        _merged_already = len(question_subs.get(int(block.get("index") or 0), set())) > 1
        if _block_sub > 1 or _merged_already:
            expected_blanks = [str(expected).strip()] if expected is not None and str(expected).strip() else []
            multi_blank = False
        else:
            expected_blanks = _expected_blanks_for_block(answer_key, block, expected)
            multi_blank = len(expected_blanks) > 1
        if expected_blanks:
            expected = (
                "；".join(f"第{i}空：{b}" for i, b in enumerate(expected_blanks, 1))
                if multi_blank
                else expected_blanks[0]
            )
        if not str(expected or "").strip():
            # 无标准答案：不再静默跳过，标记「待人工确认」，原因落到 block 上
            block["read_uncertain"] = True
            block["needs_review"] = True
            block["reason"] = f"标准答案缺失（键 {key} / {block.get('index')}_1），请人工确认"
            block["analysis"] = block["reason"]
            print(f"[fillin] slot={slot_id} index={block.get('index')} 无标准答案→待人工确认")
            continue
        expected = str(expected).strip()
        block["expected_answer"] = expected
        # 名字对齐 _row_from_block / 缓存键（response_logs 取 correct_answer）
        block["correct_answer"] = expected

        # 选择题：优先用墨迹密度 OMR 直接读「涂黑」的选项（涂黑区域 = 所涂选项，比 OCR 的
        # 「缺失字母=所涂选项」推断更可靠），OMR 读不出再退回全页 OCR → VL。
        # 题型不只靠 kind/choice_options：百度 only_split 切题不带题型，标准答案是单个
        # 选项字母（A-D）时同样是选择题，必须走读字母+集合比对分支（否则填空逐空比对
        # 会把连笔「B」读成的「13」硬判成错）。
        _expected_letter_only = bool(re.fullmatch(r"[A-D]", re.sub(r"[^A-Z]", "", normalize_answer(expected))))
        if block.get("kind") == "choice" or block.get("choice_options") or _expected_letter_only:
            student = _omr_choice_answer(image_path, block.get("bbox"))
            clear_source = "omr" if student else ""
            if not student:
                student = choice_answers.get(int(block.get("index") or 0))
                if student:
                    clear_source = "ocr"
            read_conf = 1.0 if clear_source else None
            if student is None:
                # 百度 OCR 漏读（同排合并/行尾截断）→ VL 兜底读涂卡/手写字母。
                # 走 _vl_read_choice_answer(detailed=True) 拿置信度（外部仍可调非 detailed
                # 版拿 str；测试 monkeypatch 返回 str 时按「无置信度信息」处理）。
                doc = _vl_read_choice_answer(image_path, block.get("bbox"), detailed=True)
                if isinstance(doc, dict):
                    student = doc.get("letters")
                    if not doc.get("error"):
                        read_conf = float(doc.get("confidence") or 0.0)
                    # VL 读不出一致字母（双读不一致/异常）时，若模型两次原始输出里
                    # 有唯一的 A-D 字母，按低置信（0.3）兜底比对——判错也留复核痕迹。
                    if student is None and not doc.get("error"):
                        cands = set(_parse_choice_letters(doc.get("raw1") or ""))
                        cands |= set(_parse_choice_letters(doc.get("raw2") or ""))
                        if len(cands) == 1:
                            student = cands.pop()
                            read_conf = 0.3
                    block["choice_read_confidence"] = read_conf
                else:  # 兼容被 monkeypatch 成返回 str 的旧实现
                    student = doc
                    block["choice_read_confidence"] = 1.0 if doc is not None else None
            block["student_answer"] = student
            if student is None:
                # 涂卡识别失败：不再静默 ungraded，显式交人工确认并留痕
                block["read_uncertain"] = True
                block["reason"] = "选择题作答识别失败（OMR/OCR/VL 均未读出），请人工确认"
                block["analysis"] = block["reason"]
                print(f"[choice] slot={slot_id} index={block.get('index')} 识别失败→待人工确认")
                continue
            # 手写字母识别置信度低（双读不一致/括号没定位到）且 OMR/OCR 都没有
            # 明确答案 → 不自动判，显式待确认交老师（用户反馈：读错相邻选项误判 ×）。
            if (
                read_conf is not None
                and read_conf < CHOICE_READ_MIN_CONFIDENCE
                and not clear_source
            ):
                block["read_uncertain"] = True
                block["reason"] = (
                    f"手写字母识别置信度低（{read_conf:.1f}），请人工确认"
                    f"（读得「{student}」，标准答案「{expected}」；双读不一致或括号未定位）"
                )
                block["analysis"] = block["reason"]
                print(
                    f"[choice] slot={slot_id} index={block.get('index')} "
                    f"低置信 {read_conf:.2f}<{CHOICE_READ_MIN_CONFIDENCE} 读出={student!r} →待人工确认"
                )
                continue
            s = normalize_answer(student)
            e = normalize_answer(expected)
            if not s:
                decisions[slot_id] = {"status": "unanswered"}
                continue
            # 识别不确定宁可不判：标准答案是单个选项字母时，读出的内容若不含任何
            # A-D 字母（如连笔「B」被读成「13」、「C」被读成「e」），属于看不懂，
            # 不能硬判成错 —— 显式「待人工确认」交老师。
            e_compact = re.sub(r"[^A-Z]", "", e)
            if re.fullmatch(r"[A-D]{1,4}", e_compact):
                raw_letters = re.sub(r"[^A-Z]", "", str(student).upper())
                if not raw_letters:
                    block["read_uncertain"] = True
                    block["reason"] = f"作答识别不确定：读出「{student}」，与标准答案「{expected}」无法可靠比对，请人工确认"
                    block["analysis"] = block["reason"]
                    print(f"[choice] slot={slot_id} index={block.get('index')} 读出={student!r} 标准={expected!r} →待人工确认")
                    continue
            # C3 判分缓存预查：同（题, 作答）命中直接复用判分，跳过比对
            hit = lookup_block(block, subject)
            if hit is not None:
                status = decision_status_from_result(hit.get("result"))
                if status:
                    dec = {"status": status, "partial_ratio": hit.get("partial_ratio")}
                    if status == "partial":
                        max_score = float(block.get("max_score") or 1)
                        dec["score"] = _snap_int((hit.get("partial_ratio") or 0.5) * max_score)
                    decisions[slot_id] = dec
                    continue
            # 多选题（标准答案多字母）字母集合比对（20261021 用户定规则）：
            # - 集合全同 → 对（整题满分）；
            # - 选错任意一个（含错选+少选混合）→ 错，0 分不给；
            # - 只少选没多选 → 半对，按选对选项数/正确选项数给分（整数）。
            # 学生串剥掉分隔符（「A、D」「A D」）再比，顺序无关（ABD == DAB）。
            e_letters = re.sub(r"[^A-Za-z]", "", e)
            s_letters = re.sub(r"[^A-Za-z]", "", s)
            if e.isalpha() and len(e) > 1 and s_letters:
                e_set = set(e_letters)
                s_set = set(s_letters)
                if s_set == e_set:
                    decisions[slot_id] = {"status": "correct"}
                elif s_set - e_set:
                    # 选错任意一个选项 → 错，不给分
                    decisions[slot_id] = {"status": "wrong"}
                else:
                    # 只少选没多选 → 半对，按选对选项数给分
                    max_score = float(block.get("max_score") or 1)
                    decisions[slot_id] = {
                        "status": "partial",
                        "score": _snap_int(len(s_set) / len(e_set) * max_score),
                        "partial_ratio": round(len(s_set) / len(e_set), 3),
                    }
                continue
            status = match_answers(student, expected)
            decisions[slot_id] = {"status": _STATUS_TO_MANUAL.get(status, "ungraded")}
            continue

        # 大题（主观题）：千问 VL 语义比对，支持半对。
        # 标准答案传「第1空：…；第2空：…」的清洗格式，避免把「1 超过 15.2 360W」这类
        # 被 parse 拆散的题号标记（1 / 15.2）误当成标准答案的一部分喂给 VL，导致误判。
        if _is_subjective_answer(expected, int(block.get("index") or 0)):
            q = int(block.get("index") or 0)
            _expected_text = expected if multi_blank else _format_fillin_blanks(expected, q)
            ai = _ai_grade_subjective(
                image_path, block.get("bbox"), _expected_text, q
            )
            if ai is not None:
                block["student_answer"] = ai.get("student_answer")
                block["reason"] = ai.get("reason")
                block["analysis"] = ai.get("analysis")
                block["confidence"] = ai.get("confidence")
                block["ai_grade"] = True
                if ai["status"] == "ungraded" or ai.get("read_uncertain"):
                    # 读不准不判：显式「待人工确认」并留痕（不再无声 ungraded）
                    block["read_uncertain"] = True
                    if not str(block.get("reason") or "").strip():
                        block["reason"] = "作答识别不确定，请人工确认"
                        block["analysis"] = block["reason"]
                    print(f"[fillin] slot={slot_id} index={block.get('index')} VL 读不准→待人工确认")
                    continue
                score = None
                if ai["status"] == "partial":
                    max_score = float(block.get("max_score") or 1)
                    score = _snap_int((ai.get("partial_ratio") or 0.5) * max_score)
                decisions[slot_id] = {"status": ai["status"], "score": score}
                continue
            # AI 失败降级回字符串比对（继续走下面填空逻辑）

        # 填空/客观：先用 VL 结合标准答案读手写（比纯提取更准，能纠正「舒→等于」这类误读），
        # 再用字符串按空快判（每空独立计分，命中空数/总空数，0.5 粒度）。VL 失败则退回纯提取。
        q = int(block.get("index") or 0)
        ai = _ai_grade_subjective(
            image_path,
            block.get("bbox"),
            expected if multi_blank else _format_fillin_blanks(expected, q),
            q,
            prompt_template=_FILLIN_GRADE_PROMPT,
        )
        student = ai.get("student_answer") if ai is not None else None
        ai_ratio = None
        if ai is not None:
            block["reason"] = ai.get("reason")
            block["analysis"] = ai.get("analysis")
            block["confidence"] = ai.get("confidence")
            block["ai_grade"] = True
            if ai.get("status") == "ungraded" or ai.get("read_uncertain"):
                # 读不准不判：显式「待人工确认」并留痕（不再无声 ungraded）
                block["student_answer"] = ai.get("student_answer")
                block["read_uncertain"] = True
                if not str(block.get("reason") or "").strip():
                    block["reason"] = "作答识别不确定，请人工确认"
                    block["analysis"] = block["reason"]
                print(f"[fillin] slot={slot_id} index={block.get('index')} VL 读不准→待人工确认")
                continue
            # 用 VL 的语义判定比例作为字符串快判的补充（纠正「每秒做的功为60J」≈「1s做功60J」这类等价误判）。
            # 只用来「向上修正」，不向下压分。
            if ai.get("status") == "correct":
                ai_ratio = 1.0
            elif ai.get("status") == "partial":
                pr = ai.get("partial_ratio")
                if pr is not None:
                    ai_ratio = float(pr)
        if student is None:
            student = extract_student_answer(image_path, block.get("bbox"))
        block["student_answer"] = student if isinstance(student, str) else None
        if student is None:
            # 抽取失败：显式待人工确认，不许无声消失
            block["read_uncertain"] = True
            if not str(block.get("reason") or "").strip():
                block["reason"] = "作答抽取失败（VL 与纯提取均未读出），请人工确认"
                block["analysis"] = block["reason"]
            print(f"[fillin] slot={slot_id} index={block.get('index')} 抽取失败→待人工确认")
            continue
        if isinstance(student, str) and _transcription_flagged(student):
            # 纯提取路径读出 [?]/[字|字]：同样不判，显式待人工确认
            block["read_uncertain"] = True
            if not str(block.get("reason") or "").strip():
                block["reason"] = "作答转写含不确定标记，请人工确认"
                block["analysis"] = block["reason"]
            print(f"[fillin] slot={slot_id} index={block.get('index')} 转写含[?]→待人工确认")
            continue
        if not normalize_answer(student or ""):
            decisions[slot_id] = {"status": "unanswered"}
            continue
        ratio = _fillin_hit_ratio(student, expected, q, blanks=expected_blanks if multi_blank else None)
        if ai_ratio is not None:
            ratio = max(ratio, ai_ratio)
        if ratio >= 1.0:
            decisions[slot_id] = {"status": "correct"}
        elif ratio > 0.0:
            max_score = float(block.get("max_score") or 1)
            decisions[slot_id] = {"status": "partial", "score": _snap_int(ratio * max_score)}
        else:
            decisions[slot_id] = {"status": "wrong"}
    # 答案集合无序比对（20261112 用户定规则）：整题各空只是填的顺序不同也算对。
    _apply_answer_set_rule(blocks, decisions)
    # 连续错判复核：集合规则落定后、兜底留痕前，给连续 ≥3 道判错的选择题打复核标记
    # （只加 needs_review + 原因，不改判定）。
    _flag_consecutive_wrong(blocks, decisions)
    # 收尾：任何「有标准答案但没有任何判定结果」的块，不许无声消失——
    # 统一标成显式「待人工确认」（block["result"]="待确认" 是前端已识别的状态），
    # 并留下原因。选择题分支已在上面各自留痕，这里兜底填空/客观题。
    for index, block in enumerate(blocks or []):
        if not isinstance(block, dict):
            continue
        slot_id = str(block.get("slot_id") or f"slot-{index + 1}")
        if slot_id in decisions:
            continue
        if not str(block.get("expected_answer") or "").strip():
            # 连标准答案都没有的块前面已记过原因；这里只补可见状态
            if block.get("needs_review"):
                block.setdefault("result", "待确认")
            continue
        if not str(block.get("reason") or "").strip():
            block["reason"] = "未判出结果（识别或判分失败），请人工确认"
            block["analysis"] = block["reason"]
        block["needs_review"] = True
        block["read_uncertain"] = True
        block["result"] = "待确认"
        print(f"[fillin] slot={slot_id} index={block.get('index')} 未产出判定→待人工确认")
    # C3 判分缓存回写：选择题（含命中复用）+ 主观/填空（只写不查——student_answer
    # 是本次 VL 产出，先有鸡后有蛋）。ungraded 不写；human 行永不被 ai 覆盖。
    _store_answer_key_cache(blocks, decisions, subject)
    return decisions


# decisions 英文状态 → result 中文（缓存行与 response_logs 同口径）
_RESULT_FOR_STATUS = {"correct": "对", "wrong": "错", "partial": "半对", "unanswered": "未作答"}


def _store_answer_key_cache(blocks, decisions: dict, subject) -> None:
    """把已判 slot 回填 result 文本后写入判分缓存（旁路静默，缓存永远可弃）。"""
    try:
        from app.grading.verdict_cache import store_blocks

        rows = []
        for index, block in enumerate(blocks or []):
            if not isinstance(block, dict):
                continue
            slot_id = str(block.get("slot_id") or f"slot-{index + 1}")
            decision = decisions.get(slot_id)
            if not isinstance(decision, dict):
                continue
            result = _RESULT_FOR_STATUS.get(str(decision.get("status") or ""))
            if not result:
                continue
            block["result"] = result
            if result == "半对":
                pr = decision.get("partial_ratio")
                if pr is None:
                    score = decision.get("score")
                    max_score = float(block.get("max_score") or 1)
                    try:
                        pr = (float(score) / max_score) if (score is not None and max_score > 0) else 0.5
                    except (TypeError, ValueError):
                        pr = 0.5
                block["partial_ratio"] = pr
            else:
                block["partial_ratio"] = None
            block["comment"] = str(block.get("analysis") or block.get("reason") or "").strip() or None
            rows.append(block)
        if rows:
            store_blocks(rows, subject, "answer_key", "ai")
    except Exception as e:
        print(f"判分缓存回写失败: {e}")
