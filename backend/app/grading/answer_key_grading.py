# -*- coding: utf-8 -*-
"""答题卡按标准答案自动比对：解析答案文本/图片 → 逐作答区抽取学生答案 → 判定对错。

与「答题卡（自主阅卷）」(manual) 复用同一套作答区模板（slot/bbox/label）。
答案比对面向客观题与填空（答案唯一/明确的题型），确定性、快、省；主观题仍走智能批改引擎。
"""
import os
import re
from typing import Optional

from PIL import Image

from app.grading.pipeline import _get_openai_client, _pil_image_to_data_url

# ---- 答案文本解析 ----

# 单个条目：题号 [.空号] 分隔符 答案
#   1.A / 1、A / 1. A / 1 A / 5.1 B / 5.2 D / 4.42
# 空号只取一位数字：避免把「4.42」（4 题答案 42）误判成「4 题第 42 空」。
_ENTRY_RE = re.compile(r"(\d+)(?:[._\-](\d))?[.．、:：\-–—\s]+([^\s.．、:：\-–—,;，]+)")
# 连续题号：1-5 ABCDA  → 1=A 2=B 3=C 4=D 5=A
_RANGE_RE = re.compile(r"^\s*(\d+)\s*[-–—]\s*(\d+)\s+([^\s,;，;]+)\s*$")
# 子项标记：(1)(2)(3)… 出现即视为同一题的分项答案，整串保留不分拆
_SUBITEM_RE = re.compile(r"\(\d+\)")


def _merge_line_entries(result: dict, line: str) -> None:
    """把一行按「题号.答案」逐条解析进 result（兼容 1.A 2.C 3.√ 这种一行多题）。"""
    for entry in _ENTRY_RE.finditer(line):
        q = entry.group(1)
        sub = entry.group(2)
        ans = (entry.group(3) or "").strip()
        if not ans:
            continue
        result[f"{q}_{sub}" if sub else f"{q}_1"] = ans


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
    # 含 (1)(2) 子项的整行保留为单空（避免把答案里的数字/小数/单位误当题号）；
    # 否则按空格拆成多空（填空多空题，如「6. 2 变大」「7. 弹性势能 重力势能」）。
    line_led_re = re.compile(r"^(\d+)\s*[.、．:：]\s*(.+)$")
    led = [line_led_re.match(l) for l in lines]
    if len(lines) >= 2 and sum(bool(m) for m in led) >= max(2, len(lines) - 1):
        for m in led:
            q = m.group(1)
            ans = m.group(2).strip()
            if not ans:
                continue
            if _SUBITEM_RE.search(ans):
                result[f"{q}_1"] = ans
            else:
                for i, part in enumerate(ans.split(), 1):
                    result[f"{q}_{i}"] = part
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
            model="qwen-vl-max",
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
    "如果该区域是空白、没有作答，只输出一个空字符串。"
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
            data_url = _pil_image_to_data_url(crop, max_side=1600)
        completion = client.chat.completions.create(
            model="qwen-vl-max",
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
    # 多选题：字母序列按字符排序后比较（ABD == DAB）
    if e.isalpha() and len(e) > 1 and s.isalpha() and len(s) > 1:
        if "".join(sorted(s)) == "".join(sorted(e)):
            return "对"
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


# match_answers 返回中文对错，这里翻译成 _save_manual_slot_decisions 期望的英文状态码。
_STATUS_TO_MANUAL = {"对": "correct", "错": "wrong", "未作答": "unanswered"}


def grade_paper_by_answer_key(image_path: str, blocks, answer_key: dict) -> dict:
    """对一张卷的所有作答区做答案比对，返回 {slot_id: {status}}，并就地补充块字段。

    - 有标准答案的 slot：抽取学生答案 → 比对 → correct/wrong/unanswered。
    - 没有标准答案的 slot：保持 ungraded，交由老师手动判。
    - 抽取失败（VLM 异常）的 slot：保持 ungraded。
    """
    decisions: dict[str, dict] = {}
    answer_key = answer_key if isinstance(answer_key, dict) else {}
    if not isinstance(blocks, list):
        return decisions
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        # 选择题由专门扫描机器批改，系统不判分：跳过（保持 ungraded，不抽取、不比对）
        if block.get("kind") == "choice" or str(block.get("type")) == "4":
            continue
        slot_id = str(block.get("slot_id") or f"slot-{index + 1}")
        key = _block_answer_key(block)
        expected = answer_key.get(key)
        # 兼容：标准答案里若只有「题号」（无空号）却对应多空题时，退回到题号_1
        if expected is None:
            expected = answer_key.get(f"{block.get('index')}_1")
        if expected is None or not str(expected).strip():
            continue
        expected = str(expected).strip()
        student = extract_student_answer(image_path, block.get("bbox"))
        block["expected_answer"] = expected
        block["student_answer"] = student if isinstance(student, str) else None
        if student is None:
            continue
        status = match_answers(student, expected)
        decisions[slot_id] = {"status": _STATUS_TO_MANUAL.get(status, "ungraded")}
    return decisions
