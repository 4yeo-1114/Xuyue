import base64
import copy
import re
import requests
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Tuple

from PIL import Image

from app.grading.user_paths import correct_docs_dir

# 与项目现有的百度 access_token 获取逻辑保持一致
from app.grading.baidu_grading import _post_json, _build_url

PAPER_CUT_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/paper_cut_edu"


def _join_elem_words(elem: dict) -> str:
    parts = []
    for word in elem.get("elem_word", []) or []:
        text = str(word.get("word", "") or "").strip()
        if text:
            parts.append(text)
    return "".join(parts).strip()


def _join_elements_text(elements: list, allowed_types: tuple[str, ...]) -> str:
    parts = []
    for elem in elements or []:
        if str(elem.get("elem_type")) not in allowed_types:
            continue
        text = _join_elem_words(elem)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


_LEADING_NUMBER_RE = re.compile(r"^\s*(\d+)")
# 子题/作答区里，只有「数字 + 解/答/证明/计算/作」这类「题号+解答」头部才算独立题号；
# 纯数字或「3.4.5」「1.2.3」这类学生写的答案串不算，避免误当题号。
_LEADING_QNO_SOLUTION_RE = re.compile(r"^\s*(\d+)\s*[.．、]?\s*(?:解|答|证明|计算|作|Solution|Answer)")


def _extract_printed_no(text: str) -> Optional[int]:
    """从题干文本里取卷面印刷题号（开头的数字），如 "16."、"18.(3)"、"9[A][B][D]" → 16/18/9。"""
    m = _LEADING_NUMBER_RE.match(str(text or "").strip())
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _extract_sub_printed_no(text: str) -> Optional[int]:
    """从子题/作答区文本里取独立题号，仅认「N.解/N.答」这类题号头部，如 "15.解:(1)" → 15。"""
    m = _LEADING_QNO_SOLUTION_RE.match(str(text or "").strip())
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


# 单独成词的「数字 + 可选点号」题号词（"1." "2." …）；"18.(3)"、"9[A]" 这类混着括号/选项的词不算。
_NUMBER_WORD_RE = re.compile(r"^\s*(\d+)\s*[.．、]?\s*$")
# 选择题段头：整段是「二、选择题(9~12…13~14…)」这类章节标题，不是题目。
_CHOICE_HEADER_RE = re.compile(r"选择题|单选题|多选题")


def _word_bbox(word: dict) -> list[int]:
    loc = word.get("word_location") or {}
    left = int(loc.get("left") or 0)
    top = int(loc.get("top") or 0)
    w = int(loc.get("width") or 0)
    h = int(loc.get("height") or 0)
    return [left, top, left + w, top + h]


def _elem_bbox(elem: dict, fallback: list[int]) -> list[int]:
    loc = elem.get("elem_location", {})
    points = loc.get("points", []) if isinstance(loc, dict) else []
    if points and isinstance(points, list) and len(points) >= 4:
        try:
            xs = [p.get("x", 0) for p in points]
            ys = [p.get("y", 0) for p in points]
            return [min(xs), min(ys), max(xs), max(ys)]
        except Exception:
            return fallback
    return fallback


def _extract_number_words(elements: list) -> list[dict]:
    """从题干 elem_word 里取「题号词」（"1." "2." …），返回 [{num, bbox}] 按 y、x 排序。

    只有单独成词的「数字 + 可选点号」才算题号词；"18.(3)"、"9[A]" 这类混着括号/选项的
    词不算，避免把选择/计算题误判成多题号填空。
    """
    numbers: list[dict] = []
    for elem in elements:
        if str(elem.get("elem_type")) != "0":
            continue
        for w in elem.get("elem_word") or []:
            m = _NUMBER_WORD_RE.match(str(w.get("word") or "").strip())
            if not m:
                continue
            numbers.append({"num": int(m.group(1)), "bbox": _word_bbox(w)})
    numbers.sort(key=lambda n: (n["bbox"][1], n["bbox"][0]))
    return numbers


def _is_choice_header(stem_text: str) -> bool:
    return bool(_CHOICE_HEADER_RE.search(stem_text or ""))


def _choice_max_number(stem_text: str) -> int:
    nums = [int(x) for x in re.findall(r"\d+", stem_text or "")]
    return max(nums) if nums else 0


def _split_fillin_blocks(
    number_words: list[dict],
    sub_items: list,
    q_bbox: list[int],
    *,
    stem_text: str,
    option_text: str,
    interpretation_text: str,
    qus_type: str,
) -> list[dict]:
    """把「多题号填空」整段按印刷题号词位置拆成多题，返回 block 列表。

    题号词（"1." "2." …）在题干里按 2 列 × 多行排列，每个题号的作答区都在其右侧。
    每个手写作答区（elem_type 1/2）按「同一行、且题号在其左侧最近」归属到对应题号。
    """
    rows: list[list[dict]] = []
    for n in number_words:
        if rows and abs(n["bbox"][1] - rows[-1][-1]["bbox"][1]) <= 25:
            rows[-1].append(n)
        else:
            rows.append([n])

    owned: dict[int, list[dict]] = {n["num"]: [] for n in number_words}
    for row in rows:
        row.sort(key=lambda n: n["bbox"][0])
        ymid = (min(n["bbox"][1] for n in row) + max(n["bbox"][3] for n in row)) / 2
        for sub in sub_items:
            sb = _elem_bbox(sub, q_bbox)
            sx = (sb[0] + sb[2]) / 2
            sy = (sb[1] + sb[3]) / 2
            if abs(sy - ymid) > 32:
                continue  # 不是这一行的作答区
            owner = None
            for n in row:
                if n["bbox"][0] <= sx:
                    owner = n
                else:
                    break
            if owner is not None:
                owned[owner["num"]].append(sub)

    blocks: list[dict] = []
    for n in number_words:  # number_words 已按 y、x 排序，即阅读顺序
        num = n["num"]
        for sub_idx, sub in enumerate(owned.get(num, [])):
            sub_type = str(sub.get("elem_type"))
            s_bbox = _elem_bbox(sub, q_bbox)
            sub_text = _join_elem_words(sub)
            block_subqus_text = sub_text if sub_type == "1" else ""
            block_answer_text = sub_text if sub_type == "2" and sub_text else ""
            block_text = sub_text or stem_text or option_text or block_answer_text
            blocks.append(
                {
                    "index": num,
                    "sub_index": sub_idx + 1,
                    "bbox": s_bbox,
                    "baidu_question_bbox": q_bbox,
                    "text": block_text,
                    "stem_text": stem_text,
                    "subqus_text": block_subqus_text,
                    "answer_text": block_answer_text,
                    "option_text": option_text,
                    "interpretation_text": interpretation_text,
                    "elem_type": sub_type,
                    "is_sub": True,
                    "type": qus_type,
                }
            )
    return blocks


# 答题卡抬头字段关键词：姓名/班级/学号/考号/座位号等。这类字段打印文字只是短标签
# （如「姓名:班级:」），不携带真实题目内容，切题时应整体跳过，避免把学生姓名、班级、
# 考场号等当成可打分的作答区（即「把人家名字也切进去」的问题）。
_HEADER_LABELS = (
    "学生姓名",
    "准考证号",
    "填涂说明",
    "注意事项",
    "贴条形码",
    "条形码",
    "座位号",
    "姓名栏",
    "准考证",
    "密封线",
    "姓名",
    "班级",
    "学号",
    "考号",
    "考场",
    "学校",
    "年级",
    "专业",
)


def _is_header_field(stem_text: str) -> bool:
    """判断题干是否为答题卡抬头字段。

    判定方式：去掉冒号/空白/斜杠后，若剩余文本完全由抬头关键词组成（即逐项剥掉关键词后
    为空），则视为抬头字段。例如「姓名:班级:」→「姓名班级」→ 空；「学校图书馆」因
    「图书馆」剥不掉而不会被误判。
    """
    cleaned = re.sub(r"[\s:：/／　]", "", stem_text or "")
    if not cleaned:
        return False
    remainder = cleaned
    for keyword in _HEADER_LABELS:  # 已按长度降序，先剥长词（准考证号 优先于 考号）
        remainder = remainder.replace(keyword, "")
    return remainder == ""


# 选择题（客观题）判定：题干含「一项是/哪一项」，或存在选项文本（elem_type=3），
# 或文本中出现 ≥2 个 [A]/[B]/A. 之类的选项标记。选择题是 2B 涂卡，切题时应整题作为一个
# 干净作答区，而不是逐空切成多个凌乱的手写小块。
_CHOICE_KEYWORD_RE = re.compile(r"一项是|哪一项")
_CHOICE_OPTION_RE = re.compile(r"(?:\[[A-D]\]|[A-D][．.、])")


def _is_choice_question(blocks: list) -> bool:
    option_texts: list[str] = []
    stems: list[str] = []
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        option_texts.append(str(block.get("option_text") or ""))
        stems.append(str(block.get("stem_text") or "") + str(block.get("subqus_text") or ""))
    option_joined = " ".join(option_texts).strip()
    stem_joined = " ".join(stems).strip()
    if _CHOICE_KEYWORD_RE.search(stem_joined):
        return True
    if _CHOICE_OPTION_RE.search(option_joined):
        return True
    return len(_CHOICE_OPTION_RE.findall(stem_joined + option_joined)) >= 2


def _union_boxes(boxes: list) -> list:
    valid = [b for b in boxes if isinstance(b, (list, tuple)) and len(b) >= 4]
    if not valid:
        return [0, 0, 0, 0]
    xs = [int(b[0]) for b in valid] + [int(b[2]) for b in valid]
    ys = [int(b[1]) for b in valid] + [int(b[3]) for b in valid]
    return [min(xs), min(ys), max(xs), max(ys)]


def baidu_paper_cut(image_path: str) -> dict:
    """
    调用百度试卷切卷 API
    返回原始的 JSON 字典数据
    """
    with open(image_path, "rb") as f:
        img_base64 = base64.b64encode(f.read()).decode("utf-8")
        
    payload = {"image": img_base64}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    
    from app.grading.baidu_grading import _get_access_token, _rate_limiter
    max_retries = 12
    last_data = {}
    
    for attempt in range(max_retries):
        _rate_limiter.acquire()
        token = _get_access_token()
        url = f"{PAPER_CUT_URL}?access_token={token}"
        
        resp = requests.post(url, headers=headers, data=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        last_data = data
        
        ec = data.get("error_code")
        if ec in (110, "110", 111, "111"):
            _get_access_token(force_refresh=True)
            continue
        if ec in (18, "18"):
            wait = min(3.0, 0.3 * (2 ** min(attempt, 4)))
            time.sleep(wait)
            continue
            
        if ec:
            raise RuntimeError(f"百度切卷接口错误: {data.get('error_msg')}")
            
        return data
        
    raise RuntimeError(f"百度接口持续限流(QPS)，请稍后重试：{last_data}")


ACCURATE_BASIC_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate"


def _baidu_ocr_text(image_path: str) -> list[dict]:
    """调用百度通用文字识别（accurate，高精度 v1）读全卷印刷文字，返回 [{words, bbox}]。

    paper_cut_edu 是「试卷切题」OCR，按题干猜作答区，会把 15/16/17 这类题号漏掉；
    通用 OCR 逐字识别印刷题号更可靠，用于给框线检测出的作答框挂题号。
    注意：accurate_basic / general_basic 返回里没有 location，必须用 accurate（v1）才有坐标。
    """
    with open(image_path, "rb") as f:
        img_base64 = base64.b64encode(f.read()).decode("utf-8")

    payload = {"image": img_base64, "detect_direction": "false"}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    from app.grading.baidu_grading import _get_access_token, _rate_limiter

    _rate_limiter.acquire()
    token = _get_access_token()
    url = f"{ACCURATE_BASIC_URL}?access_token={token}"
    resp = requests.post(url, headers=headers, data=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("error_code"):
        raise RuntimeError(f"百度文字识别错误: {data.get('error_msg')}")

    out: list[dict] = []
    for w in data.get("words_result") or []:
        loc = w.get("location") or {}
        left = int(loc.get("left") or 0)
        top = int(loc.get("top") or 0)
        wd = int(loc.get("width") or 0)
        ht = int(loc.get("height") or 0)
        text = str(w.get("words") or "").strip()
        if text:
            out.append({"words": text, "bbox": [left, top, left + wd, top + ht]})
    return out


# 题号词：单独成词的「数字+点号」（"1." "15."），或「数字+点号+子题括号」（"18.(3)" "20.(1)"）。
# 只认 1~2 位数字：题号都是小数字，考号/学号（8 位）、公式里的常数（"120"、"6090"）都不算。
_NUMBER_TOKEN_RE = re.compile(r"^\s*(\d{1,2})\s*[.．、](?:\s*\(|$)")


def _ocr_question_numbers(image_path: str, words: Optional[list[dict]] = None) -> list[dict]:
    """识别卷面印刷题号（"1." "2." … "21."），返回 [{num, bbox}] 按 y、x 排序。

    只认「数字+点号」（或「数字+点号+括号」）的小号字：题号字符小（高 <=45px），
    且必带点号，从而排除选择题气泡里的裸数字、准考证号、公式常数等噪声。
    words 传入时复用已 OCR 的结果，避免重复调用百度。
    """
    numbers: list[dict] = []
    for w in (words if words is not None else _baidu_ocr_text(image_path)):
        text = w["words"]
        bbox = w["bbox"]
        if (bbox[3] - bbox[1]) > 45:  # 字号过滤：题号是小字
            continue
        m = _NUMBER_TOKEN_RE.match(text)
        if not m:
            continue
        numbers.append({"num": int(m.group(1)), "bbox": bbox})
    numbers.sort(key=lambda n: (n["bbox"][1], n["bbox"][0]))
    return numbers


# 选择题涂卡词：题号后紧跟括号选项，形如 "9[A][B][D]" / "13[B][C]"。
# 括号里是「未涂」的选项字母；涂黑项被 2B 盖住、OCR 读不到 → 该字母从括号串里缺失。
_CHOICE_TOKEN_RE = re.compile(r"^\s*(\d{1,2})\s*((?:\[[A-Z]\])+)\s*$")


def _choice_answer_tokens(words: list[dict]) -> list[dict]:
    """从通用 OCR 词解析选择题涂卡项，返回 [{num, filled, bbox}]。

    只取「题号 + 括号选项」整串词（与填空/计算题的裸数字题号区分开）；
    filled = 括号里缺失的字母（即学生所涂选项，按 ABCD 顺序，如 "C"/"AD"）。
    """
    tokens: list[dict] = []
    for w in words or []:
        text = str(w.get("words") or "").strip()
        m = _CHOICE_TOKEN_RE.match(text)
        if not m:
            continue
        num = int(m.group(1))
        shown = set(re.findall(r"\[([A-Z])\]", m.group(2)))
        filled = "".join(c for c in "ABCD" if c not in shown)
        tokens.append({"num": num, "filled": filled, "bbox": list(w.get("bbox") or [])})
    tokens.sort(key=lambda t: (t["bbox"][1], t["bbox"][0]))
    return tokens


def _match_choice_cell(cell: list[int], tokens: list[dict], used: set) -> Tuple[Optional[int], Optional[dict]]:
    """给一个选择题框线格找对应的涂卡词（题号）：优先中心点落在格内，否则取中心距最近。"""
    if not tokens:
        return None, None
    cx = (cell[0] + cell[2]) / 2.0
    cy = (cell[1] + cell[3]) / 2.0
    best_i, best_d = None, None
    for i, t in enumerate(tokens):
        if i in used:
            continue
        tx1, ty1, tx2, ty2 = t["bbox"]
        tcx = (tx1 + tx2) / 2.0
        tcy = (ty1 + ty2) / 2.0
        if tx1 - 4 <= cx <= tx2 + 4 and ty1 - 4 <= cy <= ty2 + 4:
            return i, t
        d = (cx - tcx) ** 2 + (cy - tcy) ** 2
        if best_d is None or d < best_d:
            best_d, best_i = d, i
    if best_i is None:
        return None, None
    return best_i, tokens[best_i]


def _build_choice_questions(
    choice_boxes: list[list[int]],
    tokens: list[dict],
    page_no: int,
) -> list[dict[str, Any]]:
    """把选择题框线格（每格一题）挂上 OCR 涂卡词题号，生成 kind=choice 的 question。

    格按阅读顺序（y、x）排序，逐个找中心点落点匹配的涂卡词取题号；
    匹配不到的格按「已知题号范围内的空号」顺序补。最终按题号排序输出。
    """
    cells = sorted(choice_boxes, key=lambda b: (b[1], b[0]))
    used: set = set()
    matched: list[tuple[int, list[int]]] = []
    unmatched: list[list[int]] = []
    for cell in cells:
        i, t = _match_choice_cell(cell, tokens, used)
        if i is not None and t is not None:
            used.add(i)
            matched.append((int(t["num"]), cell))
        else:
            unmatched.append(cell)
    if unmatched:
        known = sorted({n for n, _ in matched})
        lo = known[0] if known else 9
        free = [n for n in range(lo, lo + len(cells)) if n not in known]
        for cell in unmatched:
            n = free.pop(0) if free else ((known[-1] + 1) if known else 9)
            matched.append((n, cell))
    matched.sort(key=lambda p: p[0])
    return [_choice_question_dict(num, cell, page_no) for num, cell in matched]


def _choice_question_dict(num: int, bbox: list[int], page_no: int) -> dict[str, Any]:
    """构造单道选择题的 question 结构（与填空/计算题结构一致，kind=choice）。"""
    return {
        "question_id": f"p{page_no}-q{num}",
        "display_no": num,
        "baidu_question_id": num,
        "question_type": "",
        "kind": "choice",
        "question_text": "",
        "regions": [
            {
                "region_id": f"p{page_no}-q{num}-r1",
                "label": f"{num}-A",
                "role": "question",
                "order": 1,
                "bbox": bbox,
            }
        ],
        "answer_slots": [
            {
                "slot_id": f"p{page_no}-q{num}-s1",
                "label": f"{num}_1",
                "order": 1,
                "bbox": bbox,
                "regions": [{"bbox": bbox}],
                "has_handwriting_location": True,
                "max_score": 1.0,
            }
        ],
    }


def parse_paper_cut_result(raw_data: dict) -> list:
    """
    将百度的试卷切卷返回数据解析为可供前端使用的标准 block 格式
    """
    blocks = []
    qus_results = raw_data.get("qus_result", [])
    real_no = 0  # 只对真实题目计数（抬头字段不计入），作为印刷题号读不到时的兜底
    calc_next: Optional[int] = None  # 选择题之后的计算/解答题起始题号（用于没 OCR 到题号的题）

    for q in qus_results:
        # 提取题干坐标 (如果存在)
        q_loc = q.get("qus_location", {})
        points = q_loc.get("points", []) if isinstance(q_loc, dict) else []
        
        if points and isinstance(points, list) and len(points) >= 4:
            # 百度返回的是 {"points": [{"x": 1, "y": 2}, ...]}
            try:
                xs = [p.get("x", 0) for p in points]
                ys = [p.get("y", 0) for p in points]
                q_bbox = [min(xs), min(ys), max(xs), max(ys)]
            except Exception:
                q_bbox = [0, 0, 0, 0]
        else:
            q_bbox = [0, 0, 0, 0]
            
        elements = q.get("qus_element", [])

        elem_text = q.get("elem_text", {}) if isinstance(q.get("elem_text"), dict) else {}
        stem_text = str(elem_text.get("stem_text", "") or "").strip() or _join_elements_text(elements, ("0",))

        # 跳过答题卡抬头字段（姓名/班级/学号/考号/座位号等），别把学生姓名、班级当成作答区
        if _is_header_field(stem_text):
            continue
        real_no += 1

        # `返回参数.xlsx` 中对 elem_type 的定义：
        # 0:题干 1:子题 2:答案 3:选项 4:配图 5:参考答案
        # 答题卡（自主阅卷）里依然保留 1/2 作为可打分 block：1 更偏子题，2 更偏答案/作答区。
        sub_items = [elem for elem in elements if str(elem.get("elem_type")) in ("1", "2")]

        subqus_text = str(elem_text.get("subqus_text", "") or "").strip() or _join_elements_text(elements, ("1",))
        answer_text = str(elem_text.get("answer_text", "") or "").strip() or _join_elements_text(elements, ("2",))
        option_text = str(elem_text.get("option_text", "") or "").strip() or _join_elements_text(elements, ("3",))
        interpretation_text = str(elem_text.get("interpretation_text", "") or "").strip() or _join_elements_text(elements, ("5",))
        full_question_text = "\n".join([x for x in [stem_text, subqus_text] if x]).strip()

        # 选择题段头（「二、选择题(9~12…13~14…)」）：不是题目，整体跳过；借它推断后面计算题的起始题号。
        if _is_choice_header(stem_text):
            cm = _choice_max_number(stem_text)
            if cm:
                calc_next = cm + 1
            continue

        # 填空题整段（题干含多个题号词「1. 2. …」且无选项）：按印刷题号词拆成各题。
        number_words = _extract_number_words(elements)
        if (
            len(number_words) >= 3
            and min(n["num"] for n in number_words) == 1
            and sub_items
            and not any(str(e.get("elem_type")) == "3" for e in elements)
        ):
            blocks.extend(
                _split_fillin_blocks(
                    number_words,
                    sub_items,
                    q_bbox,
                    stem_text=stem_text,
                    option_text=option_text,
                    interpretation_text=interpretation_text,
                    qus_type=q.get("qus_type", "4"),
                )
            )
            continue

        # 用卷面印刷题号（题干开头的数字）作为题号；读不到再退回推断/真实题目序号。不用百度返回顺序自编号。
        printed_no = _extract_printed_no(stem_text) or _extract_printed_no(subqus_text)
        if printed_no:
            base_no = printed_no
            calc_next = printed_no + 1
        elif calc_next is not None:
            base_no = calc_next
            calc_next += 1
        else:
            base_no = real_no

        if sub_items:
            for s_idx, sub in enumerate(sub_items):
                sub_type = str(sub.get("elem_type"))
                s_loc = sub.get("elem_location", {})
                s_points = s_loc.get("points", []) if isinstance(s_loc, dict) else []
                if s_points and isinstance(s_points, list) and len(s_points) >= 4:
                    try:
                        xs = [p.get("x", 0) for p in s_points]
                        ys = [p.get("y", 0) for p in s_points]
                        s_bbox = [min(xs), min(ys), max(xs), max(ys)]
                    except Exception:
                        s_bbox = q_bbox
                else:
                    s_bbox = q_bbox

                sub_text = _join_elem_words(sub)
                block_subqus_text = sub_text if sub_type == "1" else (subqus_text or "")
                block_answer_text = sub_text if sub_type == "2" and sub_text else answer_text
                block_text = sub_text or full_question_text or option_text or block_answer_text
                # 子题/作答区文本若自带题号（如「15.解:」），优先用它；否则沿用母题题号。
                # 用严格版避免把纯数字填空答案（如「2」）误当成题号。
                block_no = _extract_sub_printed_no(sub_text) or base_no

                blocks.append({
                    "index": block_no,
                    "sub_index": s_idx + 1,
                    "bbox": s_bbox,
                    "baidu_question_bbox": q_bbox,
                    "text": block_text,
                    "stem_text": stem_text,
                    "subqus_text": block_subqus_text,
                    "answer_text": block_answer_text,
                    "option_text": option_text,
                    "interpretation_text": interpretation_text,
                    "elem_type": sub_type,
                    "is_sub": True,
                    "type": q.get("qus_type", "4")
                })
        else:
            blocks.append({
                "index": base_no,
                "sub_index": 1,
                "bbox": q_bbox,
                "baidu_question_bbox": q_bbox,
                "text": full_question_text or option_text or answer_text,
                "stem_text": stem_text,
                "subqus_text": subqus_text,
                "answer_text": answer_text,
                "option_text": option_text,
                "interpretation_text": interpretation_text,
                "elem_type": "0",
                "is_sub": False,
                "type": q.get("qus_type", "4")
            })
            
    return blocks


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _manual_layout_path(folder_safe: str, *, pending: bool = False) -> Path:
    suffix = ".pending.json" if pending else ".json"
    return correct_docs_dir() / str(folder_safe) / f".manual_layout{suffix}"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _file_signature(path: Path) -> dict[str, int]:
    try:
        stat = path.stat()
        return {"size": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns)}
    except OSError:
        return {"size": -1, "mtime_ns": -1}


def _valid_bbox(value: Any, image_size: tuple[int, int]) -> Optional[list[int]]:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return None
    try:
        width, height = image_size
        x1, y1, x2, y2 = [int(float(item)) for item in value[:4]]
        x1 = max(0, min(x1, max(0, width - 1)))
        y1 = max(0, min(y1, max(0, height - 1)))
        x2 = max(x1 + 1, min(x2, width))
        y2 = max(y1 + 1, min(y2, height))
        return [x1, y1, x2, y2]
    except (TypeError, ValueError):
        return None


def build_manual_layout_page(
    raw_data: dict,
    *,
    page_no: int,
    filename: str,
    image_url: str,
    image_path: str,
) -> dict[str, Any]:
    """Convert the first paper's Baidu JSON into the shared editable layout."""
    with Image.open(image_path) as image:
        image_size = (int(image.width), int(image.height))
    blocks = parse_paper_cut_result(raw_data)
    grouped: dict[int, list[dict[str, Any]]] = {}
    for block in blocks:
        try:
            question_no = max(1, int(block.get("index") or 1))
        except (TypeError, ValueError):
            question_no = 1
        grouped.setdefault(question_no, []).append(block)

    questions: list[dict[str, Any]] = []
    for question_no, question_blocks in sorted(grouped.items()):
        first = question_blocks[0]
        is_choice = _is_choice_question(question_blocks)
        question_box = _valid_bbox(first.get("baidu_question_bbox"), image_size)
        if not question_box:
            question_box = _valid_bbox(first.get("bbox"), image_size)
        if not question_box:
            continue
        slots: list[dict[str, Any]] = []
        seen_boxes: set[tuple[int, int, int, int]] = set()
        for block in question_blocks:
            box = _valid_bbox(block.get("bbox"), image_size) or question_box
            box_key = tuple(box)
            if box_key in seen_boxes:
                continue
            seen_boxes.add(box_key)
            order = len(slots) + 1
            slots.append(
                {
                    "slot_id": f"p{page_no}-q{question_no}-s{order}",
                    "label": f"{question_no}_{order}",
                    "order": order,
                    "bbox": box,
                    "regions": [{"bbox": box}],
                    "has_handwriting_location": str(block.get("elem_type")) == "2",
                    "max_score": 1.0,
                }
            )
        if not slots:
            slots.append(
                {
                    "slot_id": f"p{page_no}-q{question_no}-s1",
                    "label": f"{question_no}_1",
                    "order": 1,
                    "bbox": question_box,
                    "regions": [{"bbox": question_box}],
                    "has_handwriting_location": False,
                    "max_score": 1.0,
                }
            )
        # 选择题（客观题）：整题合并为一个干净作答区（题干框 ∪ 各涂点框），不再逐空切成手写小块。
        if is_choice:
            merged_box = _union_boxes([question_box] + [s.get("bbox") for s in slots])
            slots = [
                {
                    "slot_id": f"p{page_no}-q{question_no}-s1",
                    "label": f"{question_no}_1",
                    "order": 1,
                    "bbox": merged_box,
                    "regions": [{"bbox": merged_box}],
                    "has_handwriting_location": False,
                    "max_score": 1.0,
                }
            ]
        questions.append(
            {
                "question_id": f"p{page_no}-q{question_no}",
                "display_no": question_no,
                "baidu_question_id": question_no,
                "question_type": first.get("type", ""),
                "kind": "choice" if is_choice else "",
                "question_text": first.get("text", ""),
                "regions": [
                    {
                        "region_id": f"p{page_no}-q{question_no}-r1",
                        "label": f"{question_no}-A",
                        "role": "question",
                        "order": 1,
                        "bbox": question_box,
                    }
                ],
                "answer_slots": slots,
            }
        )
    return {
        "page_no": int(page_no),
        "filename": str(filename),
        "image_url": str(image_url),
        "image_size": [image_size[0], image_size[1]],
        "questions": questions,
    }


def _union_boxes(boxes: list[list[int]]) -> list[int]:
    """多个框的并集外接框。"""
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def _group_fillin_cells(cells: list[list[int]], numbers: list[dict]) -> list[dict]:
    """把填空作答格按网格结构分成「题号 × 一行两格」的题，返回 [{num|None, bbox}]。

    填空区是规则的 4 列 × 多行 网格，每道题 = 同一行里相邻的两格。先按行分组、行内按 x
    排序两两配对，结构不依赖题号是否齐全（个别题号 OCR 漏掉时该题只是 num=None，不会把
    相邻题的格吸走）。每对格的题号 = 其左侧同一行的题号词。
    """
    rows: list[list[list[int]]] = []
    for cell in sorted(cells, key=lambda b: (b[1], b[0])):
        if rows and abs(cell[1] - rows[-1][-1][1]) < 40:
            rows[-1].append(cell)
        else:
            rows.append([cell])
    regions: list[dict] = []
    for row in rows:
        row.sort(key=lambda b: b[0])
        for i in range(0, len(row), 2):
            pair = row[i : i + 2]
            bbox = _union_boxes(pair)
            cx = bbox[0]
            cy = (bbox[1] + bbox[3]) / 2
            owner = None
            for n in numbers:
                nb = n["bbox"]
                # 题号在格左侧、同一行，且紧挨该格（题号右缘到格左缘 < 150px，避免漏号时相邻题吸格）
                if nb[0] < cx and abs((nb[1] + nb[3]) / 2 - cy) < 40 and (cx - nb[2]) < 150:
                    if owner is None or nb[0] > owner["bbox"][0]:
                        owner = n
            regions.append({"num": owner["num"] if owner else None, "bbox": bbox})
    regions.sort(key=lambda r: (r["bbox"][1], r["bbox"][0]))  # 阅读顺序（先 y 后 x）
    return regions


def _group_calc_cells(
    cells: list[list[int]], numbers: list[dict], columns: list[tuple]
) -> list[dict]:
    """把计算/解答题作答格按「列 + 题号」归组，返回 [{num|None, bbox}]（阅读顺序）。

    框线检测可能把一道大题（如 15 题）过切成多个窄格；窄格（宽 < 列宽 45%）是同一题的
    碎片，连续窄格合并为一道；宽格各成一道。题号按「题号在框顶附近」就近匹配，匹配不到
    的 num=None，交由阅读顺序补齐。
    """
    col_cells: dict[int, list[list[int]]] = {}
    for cell in cells:
        cx = (cell[0] + cell[2]) / 2
        ci = -1
        for i, (c1, c2) in enumerate(columns):
            if c1 - 10 <= cx <= c2 + 10:
                ci = i
                break
        col_cells.setdefault(ci, []).append(cell)

    regions: list[dict] = []
    for ci in sorted(col_cells):
        ordered = sorted(col_cells[ci], key=lambda b: b[1])
        col_width = columns[ci][1] - columns[ci][0] if 0 <= ci < len(columns) else 1
        # 连续窄格（碎片）合并
        merged: list[tuple[bool, list[list[int]]]] = []
        for cell in ordered:
            is_frag = (cell[2] - cell[0]) < col_width * 0.45
            if is_frag and merged and merged[-1][0]:
                merged[-1][1].append(cell)
            else:
                merged.append((is_frag, [cell]))
        for _, group in merged:
            bbox = _union_boxes(group)
            best = None
            best_dist: Optional[float] = None
            for n in numbers:
                nb = n["bbox"]
                if nb[0] > bbox[2] + 60:
                    continue  # 题号不能在框右侧
                if not (bbox[1] - 10 <= nb[1] <= bbox[1] + 60):
                    continue  # 题号在框顶附近
                dist = (nb[0] - bbox[0]) ** 2 + (nb[1] - bbox[1]) ** 2
                if best_dist is None or dist < best_dist:
                    best_dist = dist
                    best = n
            regions.append({"num": best["num"] if best else None, "bbox": bbox})
    return regions


def _fill_region_numbers(regions: list[dict]) -> None:
    """按阅读顺序补齐缺号（num=None 的题）：中间缺号用「上一题号 + 1」，开头缺号用后锚点反推。

    标准答题卡题号按阅读顺序严格递增，OCR 只漏个别题号（如计算题的 17），据此补回。
    """
    prev: Optional[int] = None
    for r in regions:
        if r.get("num") is not None:
            prev = r["num"]
        elif prev is not None:
            prev += 1
            r["num"] = prev
    # 开头连续缺号（如选择题段被跳过、第一道计算题号没 OCR 到）：用第一个已知题号往前推
    first_known = next((r["num"] for r in regions if r.get("num") is not None), None)
    if first_known is not None and regions and regions[0].get("num") is None:
        cnt = 0
        for r in regions:
            if r.get("num") is None:
                cnt += 1
            else:
                break
        for i in range(cnt):
            regions[i]["num"] = first_known - (cnt - i)


def build_manual_layout_page_from_boxes(
    image_path: str,
    *,
    page_no: int,
    filename: str,
    image_url: str,
) -> dict[str, Any]:
    """按答题卡印刷框线切题 + 视觉题号对齐，生成与 build_manual_layout_page 相同结构的布局页。

    两步：
    1. 框线检测（detect_answer_card_boxes）切出各作答格，跳过选择题；
    2. 通用 OCR 识别印刷题号（"1." "15." "18.(3)"…），把每个格挂到它上方/左侧的题号上，
       填空格两两并成一道、计算题过切窄格并成一道。缺号按阅读顺序补齐。
    """
    from app.grading.answer_card_boxes import detect_answer_card_boxes

    result = detect_answer_card_boxes(image_path)
    if not result.get("valid"):
        raise RuntimeError(result.get("reason") or "框线检测未识别出有效答题卡")
    width, height = result["image_size"]

    # 视觉题号（先识别，再据框切割）：一次百度 OCR，同时喂给主观题号与选择题涂卡词。
    words = _baidu_ocr_text(image_path)
    numbers = _ocr_question_numbers(image_path, words=words)
    choice_tokens = _choice_answer_tokens(words)

    subjective: list[list[int]] = []
    choice_boxes: list[list[int]] = []
    for item in result["questions"]:
        bbox = _valid_bbox(item["bbox"], (width, height))
        if not bbox:
            continue
        if item.get("kind") == "choice":
            choice_boxes.append(bbox)  # 选择题格：既用于划分填空/计算段，也生成选择题 question
        else:
            subjective.append(bbox)

    # 填空格 vs 计算/解答格：填空在最左栏、选择题段之上；其余（含中/右栏）都是计算/解答。
    # （不能用格高区分——计算题过切的底部碎格可能很矮，会误判成填空格。）
    columns = result.get("columns") or []
    left_col = columns[0] if columns else None
    choice_top = min((b[1] for b in choice_boxes), default=None)
    fillin_cells: list[list[int]] = []
    calc_cells: list[list[int]] = []
    for b in subjective:
        in_left = left_col is not None and left_col[0] - 10 <= b[0] <= left_col[1] + 10
        if in_left and choice_top is not None and b[3] < choice_top:
            fillin_cells.append(b)
        else:
            calc_cells.append(b)

    fillin_regions = _group_fillin_cells(fillin_cells, numbers)
    calc_regions = _group_calc_cells(calc_cells, numbers, columns)
    # 填空、计算分开补缺号：填空从 1 起，计算题段独立锚定（右栏题号可靠，缺 15~17 时反推）。
    _fill_region_numbers(fillin_regions)
    _fill_region_numbers(calc_regions)
    regions = fillin_regions + calc_regions

    questions: list[dict[str, Any]] = []
    for idx, region in enumerate(regions, start=1):
        # display_no 用卷面印刷题号（1..8, 15..21），不是自编序号；缺号兜底退回序号。
        display_no = int(region.get("num") or 0) or idx
        bbox = region["bbox"]
        questions.append(
            {
                "question_id": f"p{page_no}-q{display_no}",
                "display_no": display_no,
                "baidu_question_id": display_no,
                "question_type": "",
                "kind": "",
                "question_text": "",
                "regions": [
                    {
                        "region_id": f"p{page_no}-q{display_no}-r1",
                        "label": f"{display_no}-A",
                        "role": "question",
                        "order": 1,
                        "bbox": bbox,
                    }
                ],
                "answer_slots": [
                    {
                        "slot_id": f"p{page_no}-q{display_no}-s1",
                        "label": f"{display_no}_1",
                        "order": 1,
                        "bbox": bbox,
                        "regions": [{"bbox": bbox}],
                        "has_handwriting_location": True,
                        "max_score": 1.0,
                    }
                ],
            }
        )
    # 选择题：框线格挂 OCR 涂卡词题号，生成 kind=choice 的题（display_no 9..14）。
    questions.extend(_build_choice_questions(choice_boxes, choice_tokens, page_no))
    # 按卷面题号排序，保证 1..21 阅读顺序（填空 1-8、选择 9-14、计算 15-21）。
    questions.sort(key=lambda q: int(q.get("display_no") or 0))
    return {
        "page_no": int(page_no),
        "filename": str(filename),
        "image_url": str(image_url),
        "image_size": [width, height],
        "questions": questions,
    }


def build_manual_layout_page_from_reference_layout(
    ref_page: dict[str, Any],
    *,
    page_no: int,
    filename: str,
    image_url: str,
    image_path: str,
    number_offset: int = 0,
) -> dict[str, Any]:
    """从标准答题区（reference layout）生成自主阅卷切题页，供「试卷（手动批改）」使用。

    与 build_manual_layout_page_from_boxes 同构（同一 page 结构），切题审查弹窗、
    confirm_manual_layout、_materialize_manual_layout_history 全链原样复用。区别只在
    框线来源：普通试卷没有答题卡印刷框线（detect_answer_card_boxes 会「未识别到题目」），
    改取标准答案识别列表已确认的题目/作答区框，等比缩放到模板卷面（第一份学生卷）坐标系。
    没画作答区的题用题干框兜底出一格，保证每题都能手动批（与选择题挂涂卡格同理）。

    number_offset：标准答题区题号按页各编各的（第 2 页又从 1 起），而答题卡链路/答案表/
    原始试卷分值/统分键都是全卷印刷题号（第 2 页第 1 题=第 14 题，见 _scoring_title_offsets
    同一口径）。这里 display_no 加偏移折算到全卷号，slot label/question_id/slot_id 一并按
    全卷号重生成（q-N-sM 不带页号跨页撞号，弃用）。
    """
    layout = ref_page.get("layout") if isinstance(ref_page, dict) else None
    if not isinstance(layout, dict):
        layout = ref_page if isinstance(ref_page, dict) else {}
    questions = layout.get("questions")
    if not isinstance(questions, list) or not questions:
        raise RuntimeError("标准答题区缺少题目框，请先在「标准答案识别列表」完成切题审查")
    ref_size = layout.get("image_size") or ref_page.get("image_size") or [0, 0]
    src_width = max(1, int(ref_size[0] or 1))
    src_height = max(1, int(ref_size[1] or 1))
    with Image.open(image_path) as image:
        target_size = [int(image.width), int(image.height)]
    scale_x = target_size[0] / src_width
    scale_y = target_size[1] / src_height
    number_offset = int(number_offset or 0)

    def scale_box(value: Any) -> list[int]:
        box = _valid_bbox(value, (src_width, src_height)) or [0, 0, src_width, src_height]
        return [
            round(box[0] * scale_x),
            round(box[1] * scale_y),
            round(box[2] * scale_x),
            round(box[3] * scale_y),
        ]

    output: list[dict[str, Any]] = []
    for fallback_index, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            continue
        try:
            page_local_no = int(question.get("display_no") or 0)
        except (TypeError, ValueError):
            page_local_no = 0
        display_no = (page_local_no or fallback_index) + number_offset
        raw_regions = [r for r in question.get("regions") or [] if isinstance(r, dict)]
        regions = [{**copy.deepcopy(r), "bbox": scale_box(r.get("bbox"))} for r in raw_regions]
        slots = []
        for slot_index, slot in enumerate(question.get("answer_slots") or [], start=1):
            if not isinstance(slot, dict):
                continue
            raw_slot_regions = [r for r in slot.get("regions") or [] if isinstance(r, dict)]
            raw_box = slot.get("bbox") or (raw_slot_regions[0].get("bbox") if raw_slot_regions else None)
            slot_box = scale_box(raw_box)
            slot_regions = [{**copy.deepcopy(r), "bbox": scale_box(r.get("bbox"))} for r in raw_slot_regions]
            slots.append(
                {
                    **copy.deepcopy(slot),
                    "slot_id": f"p{page_no}-q{display_no}-s{slot_index}",
                    "label": f"{display_no}_{slot_index}",
                    "order": slot_index,
                    "bbox": slot_box,
                    "regions": slot_regions or [{"bbox": slot_box}],
                    "has_handwriting_location": slot.get("has_handwriting_location") is not False,
                    # 标准答题区没有分值字段：先默认 1 分，apply_paper_scores_to_page/切题审查里可改。
                    "max_score": round(float(slot.get("max_score") or 1.0), 2),
                }
            )
        if not slots:
            fallback_box = regions[0]["bbox"] if regions else [0, 0, target_size[0], target_size[1]]
            slots.append(
                {
                    "slot_id": f"p{page_no}-q{display_no}-s1",
                    "label": f"{display_no}_1",
                    "order": 1,
                    "bbox": fallback_box,
                    "regions": [{"bbox": fallback_box}],
                    "has_handwriting_location": True,
                    "max_score": 1.0,
                }
            )
        output.append(
            {
                "question_id": f"p{page_no}-q{display_no}",
                "display_no": display_no,
                "baidu_question_id": question.get("baidu_question_id", display_no),
                "question_type": question.get("question_type") or "",
                "kind": question.get("kind") or "",
                "question_text": question.get("question_text") or "",
                "regions": regions,
                "answer_slots": slots,
            }
        )
    if not output:
        raise RuntimeError("标准答题区没有可批改题目")
    output.sort(key=lambda item: int(item.get("display_no") or 0))
    return {
        "page_no": int(page_no),
        "filename": str(filename),
        "image_url": str(image_url),
        "image_size": target_size,
        "questions": output,
    }


def _norm_bbox(bbox: list, size: tuple) -> tuple:
    width, height = size
    if width < 1 or height < 1:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        max(0.0, min(1.0, bbox[0] / width)),
        max(0.0, min(1.0, bbox[1] / height)),
        max(0.0, min(1.0, bbox[2] / width)),
        max(0.0, min(1.0, bbox[3] / height)),
    )


def _bbox_center(box: tuple) -> tuple:
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def _bbox_distance(left: tuple, right: tuple) -> float:
    lx, ly = _bbox_center(left)
    rx, ry = _bbox_center(right)
    return ((lx - rx) ** 2 + (ly - ry) ** 2) ** 0.5


def _median_float(values: list) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _median_box(boxes: list) -> tuple:
    if not boxes:
        return (0.0, 0.0, 0.0, 0.0)
    return tuple(_median_float([b[axis] for b in boxes]) for axis in range(4))


def _bbox_from_norm(box: tuple, size: tuple) -> list:
    width, height = size
    return [
        int(round(box[0] * width)),
        int(round(box[1] * height)),
        int(round(box[2] * width)),
        int(round(box[3] * height)),
    ]


def aggregate_manual_layout_pages(
    pages: list,
    *,
    reference_size: tuple,
    page_no: int,
    filename: str,
    image_url: str,
) -> dict:
    """把多张试卷同一页的切题结果聚合成一张模板页。

    按「几何位置」聚类取中位数，而不是按题号对齐——单张卷漏切某题（如 17 题）时，
    其余卷在该位置的作答区仍会聚成 cluster，从而把漏题补回。坐标先归一化再投影回
    reference_size（代表卷尺寸），保证下游按 image_size 线性缩放仍然成立。
    """
    slot_dets: list[dict] = []
    question_dets: list[dict] = []
    for src_idx, page in enumerate(pages or []):
        if not isinstance(page, dict):
            continue
        size = page.get("image_size")
        if not (isinstance(size, (list, tuple)) and len(size) >= 2):
            continue
        size = (int(size[0]), int(size[1]))
        for question in page.get("questions") or []:
            if not isinstance(question, dict):
                continue
            regions = question.get("regions")
            qbox = None
            if isinstance(regions, list) and regions and isinstance(regions[0], dict):
                qbox = regions[0].get("bbox")
            if not (isinstance(qbox, (list, tuple)) and len(qbox) >= 4):
                continue
            qbox = [int(v) for v in qbox[:4]]
            question_dets.append(
                {
                    "src": src_idx,
                    "box": _norm_bbox(qbox, size),
                    "qn": question.get("display_no"),
                    "text": question.get("question_text") or "",
                    "qtype": question.get("question_type") or "",
                    "kind": question.get("kind") or "",
                }
            )
            for slot in question.get("answer_slots") or []:
                if not isinstance(slot, dict):
                    continue
                bbox = slot.get("bbox")
                if not (isinstance(bbox, (list, tuple)) and len(bbox) >= 4):
                    continue
                bbox = [int(v) for v in bbox[:4]]
                slot_dets.append(
                    {
                        "src": src_idx,
                        "box": _norm_bbox(bbox, size),
                        "handwriting": bool(slot.get("has_handwriting_location")),
                        "max_score": slot.get("max_score"),
                    }
                )

    def _cluster(dets: list, threshold: float) -> list:
        """同页中心距离贪心聚类；每张卷对每个 cluster 至多贡献一个成员。"""
        clusters: list[dict] = []
        for det in dets:
            best = None
            for index, cluster in enumerate(clusters):
                if det["src"] in cluster["srcs"]:
                    continue
                distance = _bbox_distance(det["box"], cluster["box"])
                if distance > threshold:
                    continue
                if best is None or distance < best[0]:
                    best = (distance, index)
            if best is not None:
                cluster = clusters[best[1]]
                cluster["members"].append(det)
                cluster["srcs"].add(det["src"])
                cluster["box"] = _median_box([m["box"] for m in cluster["members"]])
            else:
                clusters.append({"members": [det], "srcs": {det["src"]}, "box": det["box"]})
        return clusters

    slot_clusters = _cluster(slot_dets, 0.03)
    question_clusters = _cluster(question_dets, 0.02)

    # 每个作答区 cluster 就近挂到母题 cluster（对象引用，避免排序后索引错位）
    for slot in slot_clusters:
        slot["question_cluster"] = (
            min(question_clusters, key=lambda qc: _bbox_distance(slot["box"], qc["box"]))
            if question_clusters
            else None
        )

    # 母题按位置（先 y 后 x）排序，display_no 取阅读顺序 1..N
    question_clusters.sort(key=lambda qc: (_bbox_center(qc["box"])[1], _bbox_center(qc["box"])[0]))

    def _representative(qc: dict, field: str):
        # 优先取代表卷(src=0)的非空值，否则取首个非空值
        for member in qc["members"]:
            if member.get("src") == 0 and member.get(field):
                return member[field]
        for member in qc["members"]:
            if member.get(field):
                return member[field]
        return ""

    ref_w, ref_h = reference_size
    questions: list[dict] = []
    for display_no, qc in enumerate(question_clusters, start=1):
        qbox = _bbox_from_norm(qc["box"], reference_size)
        q_slots = [sc for sc in slot_clusters if sc.get("question_cluster") is qc]
        q_slots.sort(key=lambda sc: (_bbox_center(sc["box"])[1], _bbox_center(sc["box"])[0]))
        answer_slots: list[dict] = []
        for order, sc in enumerate(q_slots, start=1):
            sbox = _bbox_from_norm(sc["box"], reference_size)
            handwriting = any(m.get("handwriting") for m in sc["members"])
            answer_slots.append(
                {
                    "slot_id": f"p{page_no}-q{display_no}-s{order}",
                    "label": f"{display_no}_{order}",
                    "order": order,
                    "bbox": sbox,
                    "regions": [{"bbox": sbox}],
                    "has_handwriting_location": handwriting,
                    "max_score": 1.0,
                }
            )
        if not answer_slots:
            answer_slots.append(
                {
                    "slot_id": f"p{page_no}-q{display_no}-s1",
                    "label": f"{display_no}_1",
                    "order": 1,
                    "bbox": qbox,
                    "regions": [{"bbox": qbox}],
                    "has_handwriting_location": False,
                    "max_score": 1.0,
                }
            )
        questions.append(
            {
                "question_id": f"p{page_no}-q{display_no}",
                "display_no": display_no,
                "baidu_question_id": display_no,
                "question_type": _representative(qc, "qtype"),
                "kind": _representative(qc, "kind"),
                "question_text": _representative(qc, "text"),
                "regions": [
                    {
                        "region_id": f"p{page_no}-q{display_no}-r1",
                        "label": f"{display_no}-A",
                        "role": "question",
                        "order": 1,
                        "bbox": qbox,
                    }
                ],
                "answer_slots": answer_slots,
            }
        )
    return {
        "page_no": int(page_no),
        "filename": str(filename),
        "image_url": str(image_url),
        "image_size": [ref_w, ref_h],
        "questions": questions,
    }


def save_manual_layout_prepare(folder_safe: str, pages: list[dict[str, Any]]) -> str:
    prepare_id = uuid.uuid4().hex
    saved_pages: dict[str, dict[str, Any]] = {}
    for page in pages:
        if not isinstance(page, dict):
            continue
        item = copy.deepcopy(page)
        source_path = Path(str(item.get("source_path") or ""))
        item["source_signature"] = _file_signature(source_path)
        saved_pages[str(int(item.get("page_no") or 1))] = item
    _write_json(
        _manual_layout_path(folder_safe, pending=True),
        {
            "version": 2,
            "prepare_id": prepare_id,
            "created_at": _now_iso(),
            "pages": saved_pages,
        },
    )
    return prepare_id


def _validate_manual_layout_questions(page_no: int, questions: Any) -> list[dict[str, Any]]:
    if not isinstance(questions, list) or not questions:
        raise RuntimeError(f"模板试卷 P{page_no} 至少需要一个题目框")
    normalized = copy.deepcopy(questions)
    slot_count = 0
    for question in normalized:
        if not isinstance(question, dict):
            raise RuntimeError(f"模板试卷 P{page_no} 包含无效题目")
        slots = question.get("answer_slots")
        if not isinstance(slots, list):
            slots = []
            question["answer_slots"] = slots
        for index, slot in enumerate(slots, start=1):
            if not isinstance(slot, dict):
                raise RuntimeError(f"模板试卷 P{page_no} 包含无效作答区")
            slot_count += 1
            slot["slot_id"] = str(slot.get("slot_id") or f"p{page_no}-q{question.get('display_no')}-s{index}")
            try:
                max_score = float(slot.get("max_score"))
            except (TypeError, ValueError):
                raise RuntimeError(f"作答区 {slot.get('label') or slot['slot_id']} 未设置分数上限")
            if max_score <= 0:
                raise RuntimeError(f"作答区 {slot.get('label') or slot['slot_id']} 的分数上限必须大于 0")
            slot["max_score"] = round(max_score, 2)
    if slot_count == 0:
        raise RuntimeError(f"模板试卷 P{page_no} 至少需要一个作答区")
    return normalized


def confirm_manual_layout(
    folder_safe: str,
    prepare_id: str,
    edited_pages: list[dict[str, Any]],
) -> dict[str, Any]:
    pending_path = _manual_layout_path(folder_safe, pending=True)
    pending = _read_json(pending_path)
    if not pending or str(pending.get("prepare_id")) != str(prepare_id):
        raise RuntimeError("切题审查数据已失效，请重新进行切题分析")
    pending_pages = pending.get("pages") if isinstance(pending.get("pages"), dict) else {}
    final_pages: dict[str, dict[str, Any]] = {}
    for edited in edited_pages or []:
        if not isinstance(edited, dict):
            continue
        page_no = int(edited.get("page_no") or 0)
        source = pending_pages.get(str(page_no))
        if not isinstance(source, dict):
            raise RuntimeError(f"切题审查缺少 P{page_no} 数据")
        questions = _validate_manual_layout_questions(page_no, edited.get("questions"))
        final_pages[str(page_no)] = {
            "page_no": page_no,
            "filename": source.get("filename"),
            "source_path": source.get("source_path"),
            "source_signature": source.get("source_signature") or {},
            "image_path": source.get("image_path"),
            "image_size": source.get("image_size") or [0, 0],
            "raw": source.get("raw") or {},
            "layout": {
                "page_no": page_no,
                "filename": source.get("filename"),
                "image_url": edited.get("image_url") or source.get("image_url") or "",
                "image_size": source.get("image_size") or [0, 0],
                "questions": questions,
            },
        }
    if not final_pages or set(final_pages) != set(pending_pages):
        missing = sorted(set(pending_pages) - set(final_pages), key=int)
        raise RuntimeError("必须保存全部模板页" + ("，缺少：" + "、".join(f"P{x}" for x in missing) if missing else ""))
    result = {
        "version": 2,
        "status": "confirmed",
        "updated_at": _now_iso(),
        "pages": final_pages,
    }
    _write_json(_manual_layout_path(folder_safe), result)
    try:
        pending_path.unlink(missing_ok=True)
    except OSError:
        pass
    return result


def load_manual_layout(folder_safe: str) -> dict[str, Any]:
    return _read_json(_manual_layout_path(folder_safe))


def load_manual_layout_for_editing(
    folder_safe: str,
    template_sources: dict[int, tuple[Path, Path]],
    image_urls: Optional[dict[int, str]] = None,
) -> dict[str, Any]:
    data = load_manual_layout(folder_safe)
    pages = data.get("pages") if isinstance(data.get("pages"), dict) else {}
    if not pages:
        raise RuntimeError("尚未完成自主阅卷切题分析")
    pending_pages: list[dict[str, Any]] = []
    response_pages: list[dict[str, Any]] = []
    for page_no, (source_path, grading_path) in sorted(template_sources.items()):
        saved = pages.get(str(page_no))
        if not isinstance(saved, dict) or saved.get("source_signature") != _file_signature(source_path):
            raise RuntimeError(f"模板试卷 P{page_no} 已变更，请重新进行切题分析")
        layout = copy.deepcopy(saved.get("layout") or {})
        layout["image_url"] = (image_urls or {}).get(page_no) or layout.get("image_url") or ""
        layout["filename"] = source_path.name
        layout["page_no"] = page_no
        pending_pages.append(
            {
                **copy.deepcopy(layout),
                "source_path": str(source_path),
                "image_path": str(grading_path),
                "raw": copy.deepcopy(saved.get("raw") or {}),
            }
        )
        response_pages.append(layout)
    prepare_id = save_manual_layout_prepare(folder_safe, pending_pages)
    return {"prepare_id": prepare_id, "pages": response_pages}


def manual_layout_status(
    folder_safe: str,
    template_sources: dict[int, tuple[Path, Path]],
) -> dict[str, Any]:
    data = load_manual_layout(folder_safe)
    pages = data.get("pages") if isinstance(data.get("pages"), dict) else {}
    reviewed: list[int] = []
    stale: list[int] = []
    for page_no, (source_path, _grading_path) in sorted(template_sources.items()):
        saved = pages.get(str(page_no))
        if isinstance(saved, dict) and saved.get("source_signature") == _file_signature(source_path):
            reviewed.append(page_no)
        else:
            stale.append(page_no)
    return {
        "confirmed": bool(template_sources) and not stale and len(reviewed) == len(template_sources),
        "reviewed_pages": reviewed,
        "stale_pages": stale,
        "updated_at": data.get("updated_at"),
    }


def delete_manual_layout(folder_safe: str) -> None:
    for pending in (False, True):
        try:
            _manual_layout_path(folder_safe, pending=pending).unlink(missing_ok=True)
        except OSError:
            pass


# ---- 原始试卷分值（paper_scores）----

def _paper_scores_path(folder_safe: str) -> Path:
    return correct_docs_dir() / str(folder_safe) / ".paper_scores.json"


def load_paper_scores(folder_safe: str) -> dict[int, float]:
    """读取已确认的原始试卷分值 {题号: 分值}。"""
    data = _read_json(_paper_scores_path(folder_safe))
    out: dict[int, float] = {}
    for key, value in data.items():
        try:
            no = int(key)
            score = float(value)
        except (TypeError, ValueError):
            continue
        if no > 0 and score > 0:
            out[no] = round(score, 2)
    return out


def save_paper_scores(folder_safe: str, scores: dict) -> None:
    """持久化原始试卷分值 {题号: 分值}（键统一为字符串题号）。"""
    data: dict[str, float] = {}
    for key, value in (scores or {}).items():
        try:
            no = int(key)
            score = float(value)
        except (TypeError, ValueError):
            continue
        if no > 0 and score > 0:
            data[str(no)] = round(score, 2)
    _write_json(_paper_scores_path(folder_safe), data)


def apply_paper_scores_to_page(page: dict[str, Any], scores: dict[int, float]) -> dict[str, Any]:
    """把 {题号: 分值} 注入切题页各题 answer_slots[].max_score（按 display_no 匹配）。"""
    if not scores:
        return page
    for question in page.get("questions") or []:
        if not isinstance(question, dict):
            continue
        try:
            no = int(question.get("display_no") or 0)
        except (TypeError, ValueError):
            no = 0
        if no not in scores:
            continue
        value = round(float(scores[no]), 2)
        for slot in question.get("answer_slots") or []:
            if isinstance(slot, dict):
                slot["max_score"] = value
    return page


def manual_layout_blocks_for_image(
    layout_page: dict[str, Any],
    image_path: str,
) -> tuple[list[dict[str, Any]], list[int]]:
    """Scale the confirmed template coordinates to a student's page."""
    source_size = layout_page.get("image_size") or [0, 0]
    source_width = max(1, int(source_size[0] or 1))
    source_height = max(1, int(source_size[1] or 1))
    with Image.open(image_path) as image:
        target_size = [int(image.width), int(image.height)]
    scale_x = target_size[0] / source_width
    scale_y = target_size[1] / source_height

    def scale_box(value: Any) -> list[int]:
        box = _valid_bbox(value, (source_width, source_height)) or [0, 0, source_width, source_height]
        return [
            round(box[0] * scale_x),
            round(box[1] * scale_y),
            round(box[2] * scale_x),
            round(box[3] * scale_y),
        ]

    blocks: list[dict[str, Any]] = []
    for question in layout_page.get("questions") or []:
        if not isinstance(question, dict):
            continue
        question_no = int(question.get("display_no") or len(blocks) + 1)
        for slot_index, slot in enumerate(question.get("answer_slots") or [], start=1):
            if not isinstance(slot, dict):
                continue
            bbox = slot.get("bbox")
            if not bbox and isinstance(slot.get("regions"), list) and slot["regions"]:
                region = slot["regions"][0]
                bbox = region.get("bbox") if isinstance(region, dict) else region
            slot_id = str(slot.get("slot_id") or f"q{question_no}-s{slot_index}")
            label = str(slot.get("label") or f"{question_no}_{slot_index}")
            max_score = round(float(slot.get("max_score") or 1), 2)
            blocks.append(
                {
                    "index": question_no,
                    "sub_index": slot_index,
                    "slot_id": slot_id,
                    "title": f"第{question_no}题-作答区{slot_index}",
                    "label": label,
                    "bbox": scale_box(bbox),
                    "max_score": max_score,
                    "status": "ungraded",
                    "score": None,
                    "type": question.get("question_type", ""),
                    "kind": question.get("kind") or "",
                    "has_handwriting_location": slot.get("has_handwriting_location") is not False,
                    "is_sub": True,
                    # C1 管道字段：题干/题型进块（response_logs / 判分缓存身份键用）。
                    # 答题卡链路没有独立标准答案文本，correct_answer 由
                    # grade_paper_by_answer_key 命中答案表后回填。
                    "question_content": str(question.get("question_text") or "").strip() or None,
                    "question_type": str(question.get("question_type") or "").strip() or None,
                }
            )
    return blocks, target_size
