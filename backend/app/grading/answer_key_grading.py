# -*- coding: utf-8 -*-
"""答题卡按标准答案自动比对：解析答案文本/图片 → 逐作答区抽取学生答案 → 判定对错。

与「答题卡（自主阅卷）」(manual) 复用同一套作答区模板（slot/bbox/label）。
答案比对面向客观题与填空（答案唯一/明确的题型），确定性、快、省；主观题仍走智能批改引擎。
"""
import json
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
    # 每行一律整行保留为单空（不按空格拆），避免把「2 变大」「弹性势能 重力势能」
    # 这类填空题的多空答案拆成多条（按题计数，21 题 = 21 条）。
    line_led_re = re.compile(r"^(\d+)\s*[.、．:：]\s*(.+)$")
    led = [line_led_re.match(l) for l in lines]
    if len(lines) >= 2 and sum(bool(m) for m in led) >= max(2, len(lines) - 1):
        for m in led:
            q = m.group(1)
            ans = m.group(2).strip()
            if not ans:
                continue
            result[f"{q}_1"] = ans
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


def _fillin_hit_ratio(student: str, expected: str, q: int) -> float:
    """填空按空判分：逐空比对，返回命中空数 / 总空数（0~1）。"""
    blanks = _split_expected_blanks(expected, q)
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
            if not (9 <= num <= 14):
                continue
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
            if data.get("error_code"):
                raise RuntimeError(data.get("error_msg"))
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
    except Exception:
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
    "这是答题卡中一道选择题的涂卡区域，四个选项 A、B、C、D 并排排列，"
    "学生涂黑（填涂）的选项方框会变黑。请判断学生涂黑了哪个选项。"
    "只输出涂黑的选项字母（按 A、B、C、D 顺序拼接，例如 C 或 AD），不要输出任何解释。"
    "若看不到涂黑或无法判断，只输出一个空行。"
)


def _vl_read_choice_answer(image_path: str, bbox) -> Optional[str]:
    """选择题涂卡 VL 兜底：裁剪选项行让千问读出涂黑字母。

    返回 None 表示 VLM 异常；返回 "" 表示无涂黑/无法判断（判未作答）；
    否则返回涂黑字母串（如 "C"、"AD"）。
    """
    try:
        client = _get_openai_client()
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            width, height = im.size
            box = _valid_bbox(bbox, width, height)
            if box is None:
                return None
            x1, y1, x2, y2 = box
            x1 = max(0, x1 - 8)
            x2 = min(width, x2 + 8)
            y1 = max(0, y1 - 12)
            y2 = min(height, y2 + 12)
            crop = im.crop((x1, y1, x2, y2))
            data_url = _pil_image_to_data_url(crop, max_side=1600)
        completion = client.chat.completions.create(
            model="qwen-vl-max",
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
        raw = (completion.choices[0].message.content or "").strip()
        return "".join(sorted(set(re.findall(r"[A-D]", raw.upper()))))
    except Exception:
        return None


# ---- 大题（主观题）千问 VL 语义比对 ----

_SUBJECTIVE_GRADE_PROMPT = (
    "你是一位公正、宽松的考试阅卷老师。下面给你一张「学生作答区」的裁剪图，以及这道题的文字标准答案。"
    "请对照标准答案，语义判定学生作答是否正确。\n"
    "标准答案（唯一判分依据）：\n{EXPECTED}\n\n"
    "总原则：宁对勿错、能对不半。只要核心结论和关键数值对就给分；只有明显缺失或明显错误才降档，"
    "不要吹毛求疵、不要抠字眼。\n"
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
    "5. student_answer 抄录学生在图里写下的作答内容（空白则为空字符串）。\n"
    "6. reason / analysis 用中文，写明对错原因；不要用 TeX/LaTeX/反斜杠/美元符，"
    "用 Unicode 数学符号（如 √、²、×、÷、≈）。\n"
    "7. 只返回一个合法 JSON 对象，不要 Markdown 代码块、不要多余字段。\n\n"
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
    "判定规则：\n"
    "0. question_id 固定填 {QID}，不要改成卷面题号或别的数字。\n"
    "1. 只判这张裁剪图里的填空作答，不要把别的题算进来。\n"
    "2. 某个空判「对」：学生填的内容与标准答案一致，或为等价写法。以下一律算对：\n"
    "   - 近义词（「减小」≈「变小」≈「降低」、「大于」≈「>」、「等于」≈「=」）。\n"
    "   - 单位/符号等价（「60J」≈「每秒做功60J」≈「1s做功60J」≈「每秒做的功为60J」）。\n"
    "   - 手写字迹潦草不清时，结合标准答案判断学生想写的是不是那个词，不要因为字迹潦草就判错。\n"
    "3. 某个空空白、或填的内容与标准答案明显不同，判「错」。\n"
    "4. 全对 result=「对」correctResult=1；全错 result=「错」correctResult=2；"
    "部分对 result=「半对」correctResult=4。correctResult 必须与 result 一致。\n"
    "5. partial_ratio = 写对的空数 / 总空数（0~1 的小数），只有全错才给 0。\n"
    "6. student_answer 逐空抄录学生在图里写下的内容（空白则为空字符串），不要把相邻空的内容搞混。\n"
    "7. reason / analysis 用中文写明对错原因；不要用 TeX/LaTeX/反斜杠/美元符，"
    "用 Unicode 数学符号（如 √、²、×、÷、≈）。\n"
    "8. 只返回一个合法 JSON 对象，不要 Markdown 代码块、不要多余字段。\n\n"
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


_CODE_TO_STATUS = {1: "correct", 2: "wrong", 3: "unanswered", 4: "partial"}


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


def _ai_grade_subjective(
    image_path: str,
    bbox,
    expected_text: str,
    question_id: int = 0,
    prompt_template: str = _SUBJECTIVE_GRADE_PROMPT,
) -> Optional[dict]:
    """文本标准答案 + 学生作答裁剪图 → 千问 VL 语义判分。

    返回 {status: correct/wrong/unanswered/partial, partial_ratio, reason, analysis,
    student_answer}；任何异常返回 None（由调用方降级回字符串比对）。
    prompt_template 可换成 _FILLIN_GRADE_PROMPT 用于填空逐空判分。
    """
    try:
        from app.grading.reference_vlm_grading import _json_object_from_text, _normalize_decision

        client = _get_openai_client()
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            width, height = im.size
            box = _valid_bbox(bbox, width, height)
            if box is None:
                return None
            crop = im.crop(tuple(box))
            data_url = _pil_image_to_data_url(crop, max_side=1600)
        prompt = prompt_template.replace("{EXPECTED}", str(expected_text)).replace(
            "{QID}", str(int(question_id or 0))
        )
        completion = client.chat.completions.create(
            model="qwen-vl-max",
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
        }
    except Exception:
        return None


# match_answers 返回中文对错，这里翻译成 _save_manual_slot_decisions 期望的英文状态码。
_STATUS_TO_MANUAL = {"对": "correct", "错": "wrong", "未作答": "unanswered", "半对": "partial"}


def grade_paper_by_answer_key(image_path: str, blocks, answer_key: dict) -> dict:
    """对一张卷的所有作答区做答案比对，返回 {slot_id: {status}}，并就地补充块字段。

    - 选择题：百度 OCR 读涂卡（缺失字母 = 所涂选项）→ 字母比对。
    - 大题（标准答案含 (N) 小问或较长）：千问 VL 语义比对，支持半对 partial + score。
    - 填空/客观：抽取学生答案 → 字符串快判。
    - 没有标准答案、或抽取/VL 失败的 slot：保持 ungraded，交由老师手动判。
    """
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

    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
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
        block["expected_answer"] = expected

        # 选择题：优先用墨迹密度 OMR 直接读「涂黑」的选项（涂黑区域 = 所涂选项，比 OCR 的
        # 「缺失字母=所涂选项」推断更可靠），OMR 读不出再退回全页 OCR → VL。
        if block.get("kind") == "choice" or block.get("choice_options"):
            student = _omr_choice_answer(image_path, block.get("bbox"))
            if not student:
                student = choice_answers.get(int(block.get("index") or 0))
            if student is None:
                # 百度 OCR 漏读（同排合并/行尾截断）→ VL 兜底读涂卡
                student = _vl_read_choice_answer(image_path, block.get("bbox"))
            block["student_answer"] = student
            if student is None:
                continue  # 涂卡识别失败，保持 ungraded
            s = normalize_answer(student)
            e = normalize_answer(expected)
            if not s:
                decisions[slot_id] = {"status": "unanswered"}
                continue
            # 多选题：按每个选项（空）独立计分，选对几个给几分（整数），选错不多扣
            if e.isalpha() and len(e) > 1 and s.isalpha():
                e_set = set(e)
                s_set = set(s)
                hit = len(s_set & e_set)
                if s_set == e_set:
                    decisions[slot_id] = {"status": "correct"}
                elif hit == 0:
                    decisions[slot_id] = {"status": "wrong"}
                else:
                    # 多选按选对的选项数给部分分（用户要求「按空给分」；涂卡识别有噪声，
                    # 不因误识别的多余选项就整题判 0）
                    max_score = float(block.get("max_score") or 1)
                    decisions[slot_id] = {
                        "status": "partial",
                        "score": _snap_int(hit / len(e_set) * max_score),
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
            ai = _ai_grade_subjective(
                image_path, block.get("bbox"), _format_fillin_blanks(expected, q), q
            )
            if ai is not None:
                block["student_answer"] = ai.get("student_answer")
                block["reason"] = ai.get("reason")
                block["analysis"] = ai.get("analysis")
                block["ai_grade"] = True
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
            _format_fillin_blanks(expected, q),
            q,
            prompt_template=_FILLIN_GRADE_PROMPT,
        )
        student = ai.get("student_answer") if ai is not None else None
        ai_ratio = None
        if ai is not None:
            block["reason"] = ai.get("reason")
            block["analysis"] = ai.get("analysis")
            block["ai_grade"] = True
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
            continue
        if not normalize_answer(student or ""):
            decisions[slot_id] = {"status": "unanswered"}
            continue
        ratio = _fillin_hit_ratio(student, expected, q)
        if ai_ratio is not None:
            ratio = max(ratio, ai_ratio)
        if ratio >= 1.0:
            decisions[slot_id] = {"status": "correct"}
        elif ratio > 0.0:
            max_score = float(block.get("max_score") or 1)
            decisions[slot_id] = {"status": "partial", "score": _snap_int(ratio * max_score)}
        else:
            decisions[slot_id] = {"status": "wrong"}
    return decisions
