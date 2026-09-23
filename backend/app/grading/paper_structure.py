# -*- coding: utf-8 -*-
"""整卷题目结构识别：分段转录 → 确定性解析 → 一致性推断。

用于统分（读卷面印的每题满分）和课堂讲评（读原题文字）。
核心问题：小学语文试卷常为两栏排版、分值印成「（X☆）」而非「（X分）」、大题/小题/小问
三级层级，且试卷可能截断（后面还有题）。整页直接让视觉模型吐 JSON 极易错乱，这里改成：
  1) 分段转录（两栏排版用横带不易漏，放大保证题号/分值可读）；
  2) 用正则做确定性解析（视觉模型的「结构化 JSON」输出不可靠，正则可控可测）；
  3) 一致性推断：大题总分 = 其下小题分值之和；差值即「缺失/截断」的题，用占位补上，
     保证统分覆盖整卷、不因漏切而少算分；卷首「合计/题序」作锚点，推断漏识别的大题。
"""
from __future__ import annotations

import base64
import io
import json
import re
from pathlib import Path
from typing import Optional

import requests

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

_DASHSCOPE_COMPAT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 大题号 / 阅读段号（括号内中文序号）
_CN_MAJOR_RE = r"[一二三四五六七八九十]+"

# ── 转录 ────────────────────────────────────────────────────────────────

def _call_qwen(api_key: str, messages: list, max_tokens: int = 6000, temperature: float = 0.1):
    payload = {
        "model": "qwen-vl-max",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "enable_thinking": False,
    }
    resp = requests.post(
        f"{_DASHSCOPE_COMPAT_URL}/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=180,
    )
    res_json = resp.json()
    if resp.status_code != 200 or "error" in res_json:
        return None
    return (res_json.get("choices") or [{}])[0].get("message", {}).get("content", "")


def _data_url(image: "Image.Image") -> str:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=92, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _transcribe_band(api_key: str, image: "Image.Image", hint: str) -> str:
    prompt = (
        f"这是小学语文试卷的{hint}。把这一区域里【所有含题号或分值的文字行】原样逐行转录，"
        "按从上到下、从左到右顺序。题号含大题号（一、二、三、四）、小题号（1. 2. 3. 4.）、"
        "括号小问（（一）（二）（1）（2）…）。分值原文照抄（如（35☆）（7☆）（2☆））。"
        "逐字照抄、不要漏行、不要概括、不要合并，只输出文本。"
    )
    content = _call_qwen(
        api_key,
        [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": _data_url(image)}},
            {"type": "text", "text": prompt},
        ]}],
    )
    return content or ""


def _detect_column_split(image: "Image.Image") -> Optional[int]:
    """检测两栏排版的中缝 x（竖空白缝），单栏返回 None。

    墨迹投影：每列（宽 1px）统计灰度<200 的像素（每隔 3 行抽 1 行加速），
    在页宽中部找连续墨迹最少的窄窗口；若窗口墨迹 ≈ 0（整条竖缝基本无字）且
    左右两栏都有实质内容，判定为两栏，返回中缝 x。避免把单栏留白边缘误判为分栏。
    """
    if Image is None:
        return None
    try:
        gray = image.convert("L")
    except Exception:
        return None
    W, H = gray.size
    if W < 400 or H < 400:
        return None
    px = gray.load()

    def _col_ink(x: int) -> int:
        c = 0
        for y in range(0, H, 3):
            if px[x, y] < 200:
                c += 1
        return c

    cols = [_col_ink(x) for x in range(W)]
    lo, hi = int(W * 0.28), int(W * 0.72)
    best_x, best_val = None, 1 << 30
    for x in range(lo + 3, hi - 3):
        win = sum(cols[x - 3:x + 4])
        if win < best_val:
            best_val, best_x = win, x
    if best_x is None:
        return None
    if best_val > max(3, H // 150):  # 中间有字横贯，不是空白分栏缝
        return None
    if sum(cols[:best_x]) < 100 or sum(cols[best_x:]) < 100:  # 一侧基本空白，不是两栏
        return None
    return best_x


def _transcribe_paper(api_key: str, image: "Image.Image", split_x: Optional[int] = None) -> str:
    """整卷转录。split_x 非空则按两栏分别转录（左栏再右栏）后拼接，避免两栏交错漏行。

    两栏排版下整页一次转录会按「从左到右」横跨两栏读，把右栏底部小题归位错误、或漏掉
    左栏底部小题；按竖栏裁剪后各自从上到下转录，再按「左栏→右栏」拼接，即为卷面阅读顺序。
    """
    if split_x is None:
        img = image.copy()
        if max(img.size) > 2400:
            img.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
        prompt = (
            "这是小学语文试卷扫描图。把整张试卷里【所有含题号或分值的文字行】原样逐行转录，"
            "按卷面从上到下、从左到右的顺序。题号含大题号（一、二、三、四）、小题号（1. 2. 3. 4.）、"
            "括号小问（（一）（二）（1）（2）…）。分值原文照抄（如（35☆）（7☆）（2☆））。"
            "逐字照抄、不要漏行、不要概括、不要合并，只输出文本。"
        )
        content = _call_qwen(
            api_key,
            [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": _data_url(img)}},
                {"type": "text", "text": prompt},
            ]}],
            max_tokens=8000,
        )
        return content or ""

    # 两栏：左栏再右栏，各自从上到下转录，拼接为完整卷面阅读顺序。
    W, H = image.size
    parts: list[str] = []
    for label, x0, x1 in (("左栏", 0, split_x), ("右栏", split_x, W)):
        col = image.crop((x0, 0, x1, H)).copy()
        if max(col.size) > 2400:
            col.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
        prompt = (
            f"这是小学语文试卷的{label}。把{label}里【所有含题号或分值的文字行】原样逐行转录，"
            "按从上到下、从左到右的顺序。题号含大题号（一、二、三、四）、小题号（1. 2. 3. 4.）、"
            "括号小问（（一）（二）（1）（2）…）。分值原文照抄（如（35☆）（7☆）（2☆））。"
            "逐字照抄、不要漏行、不要概括、不要合并，只输出文本。"
        )
        content = _call_qwen(
            api_key,
            [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": _data_url(col)}},
                {"type": "text", "text": prompt},
            ]}],
            max_tokens=8000,
        )
        parts.append(content or "")
    return "\n".join(parts)


# ── 大题独立识别（更可靠，作锚点） ────────────────────────────────────────

def _extract_majors(api_key: str, image: "Image.Image") -> dict[str, int]:
    """专用一call：只读大题标题行（一、二、三、四…）+ 分值。任务小、更可靠。"""
    w, h = image.size
    img = image.copy()
    if max(w, h) > 2200:
        img.thumbnail((2200, 2200), Image.Resampling.LANCZOS)
    prompt = (
        "这是小学语文试卷扫描图。只找卷面上的【大题】标题行，大题号是中文序号（一、二、三、四…），"
        "标题行末尾通常带分值（如（33☆）（11☆））。把每个大题的题号和分值读出来。"
        "题号照抄（一/二/三/四…），分值是整数。只输出 JSON：\n"
        '{"majors":[{"major":"一","title":"积累与运用","score":33},{"major":"二","title":"观察与梳理","score":11}]}'
    )
    content = _call_qwen(
        api_key,
        [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": _data_url(img)}},
            {"type": "text", "text": prompt},
        ]}],
    )
    majors: dict[str, int] = {}
    if not content:
        return majors
    m = re.search(r"\{[\s\S]*\}", content)
    try:
        obj = json.loads(m.group(0)) if m else json.loads(content)
    except Exception:
        return majors
    arr = obj.get("majors") if isinstance(obj, dict) else None
    if not isinstance(arr, list):
        return majors
    for q in arr:
        if not isinstance(q, dict):
            continue
        major = str(q.get("major") or "").strip()
        if not re.fullmatch(_CN_MAJOR_RE, major):
            continue
        try:
            score = int(round(float(q.get("score"))))
        except (TypeError, ValueError):
            continue
        if score > 0:
            majors[major] = score
    return majors


_CN_SEQ = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]


def _cn_successor(s: str) -> str:
    """中文序号 +1（一→二，二→三…），到「十」为止；不认识返回空。"""
    try:
        i = _CN_SEQ.index(s)
    except ValueError:
        return ""
    return _CN_SEQ[i + 1] if i + 1 < len(_CN_SEQ) else ""


def infer_missing_sections(majors: dict, items: list[dict]) -> list[dict]:
    """推断整卷转录漏掉的阅读段头（如「（二）」），返回
    [{"major":"三","section":"二","score":17,"first_sub":"4"}]。

    整卷转录常漏掉页中/页首的阅读段头，导致该段小题被错归到上一段（统分界面把 4/5/6 全堆到
    （一）下）。这里用确定性算术补回，不再依赖视觉模型读段头（那会幻觉出「（二）26」这类错误）：

    - 已知阅读段（（一）（二）…）按出现顺序，逐个用「其下小题分值之和」消费小题（累积到 ≥ 段分值即止）；
    - 若某大题下消费完已知段后还有剩余小题、且大题总分 > 已知段分值之和，说明漏了一个阅读段；
    - 漏掉的段分值 = 大题总分 − 已知段分值之和，序号 = 已知段末位序号 +1，起点 = 第一个剩余小题。
    """
    by_major: dict[str, list[dict]] = {}
    for it in items:
        by_major.setdefault(it.get("major") or "", []).append(it)

    missing: list[dict] = []
    for major, lst in by_major.items():
        total = majors.get(major)
        if not total:
            continue
        secs = [it for it in lst if re.fullmatch(_CN_MAJOR_RE, str(it.get("sub") or "")) and not it.get("sub_sub")]
        if not secs:
            continue
        subs = [it for it in lst if str(it.get("sub") or "").isdigit() and not it.get("sub_sub")]
        known_sum = sum(int(s.get("score") or 0) for s in secs)
        if known_sum >= total:
            continue
        consumed = 0
        for s in secs:
            target = int(s.get("score") or 0)
            acc = 0
            while consumed < len(subs):
                acc += int(subs[consumed].get("score") or 0)
                consumed += 1
                if acc >= target:
                    break
        if consumed >= len(subs):
            continue
        first_sub = str(subs[consumed].get("sub") or "")
        if not first_sub:
            continue
        next_no = _cn_successor(str(secs[-1].get("sub") or ""))
        if not next_no:
            continue
        missing.append({
            "major": major,
            "section": next_no,
            "score": total - known_sum,
            "first_sub": first_sub,
        })
    return missing


# ── 确定性解析（正则，替代不可靠的 LLM 结构化输出） ──────────────────────

def _regex_parse(transcript: str) -> tuple[dict[str, int], list[dict], int, list[str]]:
    """从转录文本正则解析出：majors、题目列表、合计、题序。

    返回 (majors, items, total_anchor, order)。items 每项含 major/sub/sub_sub/title/score。
    """
    majors: dict[str, int] = {}
    items: list[dict] = []
    total_anchor = 0
    order: list[str] = []

    lines = [ln.strip() for ln in transcript.splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("[第")]

    # 合计 / 题序 锚点
    for ln in lines:
        mt = re.search(r"合计[:：]\s*(\d+)", ln)
        if mt:
            total_anchor = int(mt.group(1))
        mo = re.search(r"题序\s*([一二三四五六七八九十\s]+)", ln)
        if mo:
            order = re.findall(_CN_MAJOR_RE, mo.group(1))

    # 分值括号原文可能是半角「(35☆)」或全角「（35☆）」，星号也可能 ★/☆，统一放宽。
    _score_re = r"[(（](\d+)[☆★][)）]"
    re_major = re.compile(r"^(" + _CN_MAJOR_RE + r")[、.．](.+?)[。．]?" + _score_re + r"\s*$")
    re_sub = re.compile(r"^(\d+)[、.．](.+?)[。．]?" + _score_re + r"\s*$")
    re_subsub = re.compile(r"^[（(](\d+)[)）](.+?)[。．]?" + _score_re + r"\s*$")
    re_section = re.compile(r"^[（(](" + _CN_MAJOR_RE + r")[)）](.+?)[。．]?" + _score_re + r"\s*$")

    cur_major = ""
    cur_sub = ""
    for ln in lines:
        m = re_major.match(ln)
        if m:
            cur_major = m.group(1)
            cur_sub = ""
            majors[cur_major] = int(m.group(3))
            items.append({"major": cur_major, "sub": "", "sub_sub": "", "title": m.group(2).strip(), "score": int(m.group(3))})
            continue
        m = re_section.match(ln)
        if m:
            # 阅读段（（一）（二））——归属于当前大题，视为该大题下的一个「小题」
            cur_sub = m.group(1)
            items.append({"major": cur_major, "sub": cur_sub, "sub_sub": "", "title": m.group(2).strip(), "score": int(m.group(3))})
            continue
        m = re_sub.match(ln)
        if m:
            cur_sub = m.group(1)
            items.append({"major": cur_major, "sub": cur_sub, "sub_sub": "", "title": m.group(2).strip(), "score": int(m.group(3))})
            continue
        m = re_subsub.match(ln)
        if m:
            items.append({"major": cur_major, "sub": cur_sub, "sub_sub": m.group(1), "title": m.group(2).strip(), "score": int(m.group(3))})
            continue
    return majors, items, total_anchor, order


def _fix_subsub_assignment(items: list[dict]) -> list[dict]:
    """校正「小问归属小题」：两栏排版会让左栏小题标题（如「4.句子练习」）插在右栏另一小题
    （如「3.选择题」）的后续小问（(4)(5)(6)(7)）之前，导致 (5)(6)(7) 被误归到小题 4。

    卷面上小问号是可靠的、且同一小题内连续（(1)(2)(3)…）。这里按「小问号衔接最紧」重新归属：
    - 小问号 == 1 的，信任正则当前归属（紧跟在小题标题后，归属正确）；
    - 小问号 > 1 的，归到「小问号 gap 最小且为正」的、且已被小问引用的小题（即它自然延续的那道小题）。
    只在小问当前引用到的小题之间重排，避免把读拼音/选字组词这类无分值小问的小题卷进来。
    """
    by_major: dict[str, list[dict]] = {}
    for it in items:
        by_major.setdefault(it.get("major"), []).append(it)

    for _major, lst in by_major.items():
        subsubs = [it for it in lst if it.get("sub_sub")]
        if not subsubs:
            continue
        referenced: list[str] = []
        for it in subsubs:
            s = it.get("sub")
            if s and s not in referenced:
                referenced.append(s)
        if len(referenced) <= 1:
            continue
        # 按题号数字排序（容忍阅读段号「一」等非数字）
        def _sub_key(s: str):
            try:
                return (0, int(s))
            except (TypeError, ValueError):
                return (1, s)
        referenced.sort(key=_sub_key)

        last: dict[str, int] = {s: 0 for s in referenced}
        for it in subsubs:
            try:
                n = int(str(it.get("sub_sub") or ""))
            except (TypeError, ValueError):
                continue
            if n <= 0:
                continue
            cur = it.get("sub")
            if n == 1:
                # 小题开头：信任正则当前归属，只登记
                if cur in last:
                    last[cur] = 1
                continue
            best, best_gap = None, None
            for s in referenced:
                gap = n - last.get(s, 0)
                if gap <= 0:
                    continue
                if best_gap is None or gap < best_gap:
                    best, best_gap = s, gap
            if best is not None:
                it["sub"] = best
                last[best] = n
    return items


# ── 一致性推断 ───────────────────────────────────────────────────────────

def _cn_to_int(s: str) -> int:
    m = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
         "十一": 11, "十二": 12}
    return m.get(s, 0)


def _infer(majors: dict[str, int], items: list[dict], total_anchor: int, order: list[str]) -> dict:
    """推断缺失大题、大题下缺失小题（差值），返回完整结构。"""
    # 缺失大题：题序里有但 majors 里没有的，用 合计 - 已知 推断（若只剩一个未知）
    known_sum = sum(majors.values())
    missing_majors = [o for o in order if o not in majors]
    if len(missing_majors) == 1 and total_anchor > known_sum:
        majors[missing_majors[0]] = total_anchor - known_sum

    # 大题下直接小题之和 vs 大题总分 → 差值 = 缺失小题
    # 直接小题 = sub 非空且 sub_sub 为空
    sub_sum: dict[str, int] = {}
    for it in items:
        if it["sub"] and not it["sub_sub"]:
            sub_sum[it["major"]] = sub_sum.get(it["major"], 0) + it["score"]

    gaps: list[dict] = []
    for m, total in majors.items():
        s = sub_sum.get(m, 0)
        if s > 0 and total > s:
            gaps.append({"major": m, "total": total, "sum": s, "gap": total - s})

    return {"majors": majors, "items": items, "total": total_anchor, "order": order, "gaps": gaps}


def _reconcile_major_totals(majors: dict[str, int], items: list[dict], total_anchor: int, order: list[str]) -> dict[str, int]:
    """用卷首合计锚点校正大题总分。

    - 缺失一个大题（如四被截断）：合计 − 已知大题 = 缺失大题分。
    - 全部大题都在但和 ≠ 合计：找「当前值 ≠ 其直接小题之和，且小题之和 = 合计−其他大题」的大题校正。
    """
    if total_anchor <= 0 or not majors:
        return dict(majors)
    majors = dict(majors)
    # 直接小题之和（该大题识别完整时 == 大题真实总分）
    sub_sum: dict[str, int] = {}
    for it in items:
        if it["sub"] and not it["sub_sub"]:
            sub_sum[it["major"]] = sub_sum.get(it["major"], 0) + it["score"]

    known = sum(majors.values())
    missing = [o for o in order if o not in majors]
    if len(missing) == 1 and total_anchor >= known:
        majors[missing[0]] = total_anchor - known
        return majors

    if not missing and known != total_anchor:
        for m, v in list(majors.items()):
            s = sub_sum.get(m)
            inferred = total_anchor - (known - v)
            if s and s == inferred and inferred != v:
                majors[m] = inferred
                break
    return majors


def _extract_json_obj(content: str):
    """从 LLM 输出里稳健提取 JSON 对象/数组（容忍 ```json 围栏、前后废话）。"""
    if not content:
        return None
    text = re.sub(r"```(?:json)?", "", content).strip()
    for pat in (r"\{[\s\S]*\}", r"\[[\s\S]*\]"):
        m = re.search(pat, text)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                continue
    try:
        return json.loads(text)
    except Exception:
        return None


def _leaf_items_for_matching(items: list[dict]) -> list[dict]:
    """过滤出「叶子题」：只保留能直接被题目块对号入座的单题，去掉纯容器头。

    容器头（下面还有子题）：
      - 大题头（sub=""）：该大题下存在带 sub 的小题/小问；
      - 小题头（sub 是阿拉伯数字，且其下有 sub_sub 小问）；
      - 阅读段头（sub 是中文序号，如（一）（二））：其下还有小题。
    叶子：小问（sub_sub 非空）、无小问的普通小题、无小题的独立大题（如「二、观察与梳理」）。
    """
    container_majors = {it.get("major") for it in items if it.get("sub")}
    container_subs = {it.get("sub") for it in items if it.get("sub_sub")}
    leaves: list[dict] = []
    for it in items:
        major = it.get("major") or ""
        sub = it.get("sub") or ""
        sub_sub = it.get("sub_sub") or ""
        if sub_sub:
            leaves.append(it)
            continue
        if sub:
            # 阅读段头（（一）（二）等中文序号）——下面还有小题，属容器，跳过
            if re.fullmatch(_CN_MAJOR_RE, str(sub)):
                continue
            if sub not in container_subs:
                leaves.append(it)
            continue
        # 大题头：无小题的独立大题才保留
        if major not in container_majors:
            leaves.append(it)
    return leaves


def _short_title(title: str, max_len: int = 8) -> str:
    """把整句题干压缩成简短题型名（用于统分界面的题号标签，避免整句搬到界面上）。

    统分界面只需要「题号 + 简短题型名 + 分值」（如「读拼音写词语」「加点字读音」「心情」「人物」「作文」），
    而识别/转录里的 title 常常是完整题干（如「下列加点字的读音有误的一项是」）。LLM 已按提示生成短标题时
    原样返回；这里做确定性兜底，把过长的题干截短并去掉括号选项/结尾标点。
    """
    t = re.sub(r"\s+", " ", (title or "")).strip()
    if not t:
        return ""
    # 去掉结尾的括号选项，如「( A )」「（B）」
    t = re.sub(r"[（(]\s*[A-Za-zＡ-Ｚ]\s*[）)]\s*$", "", t)
    # 去掉结尾标点
    t = re.sub(r"[。．；;！？!?，,：:]+$", "", t).strip()
    if len(t) <= max_len:
        return t
    return t[:max_len].rstrip("，,、。．；;：: ")


def match_blocks_to_scores(
    api_key: str,
    transcript: str,
    majors: dict[str, int],
    total: int,
    order: list[str],
    block_descriptions: list[str],
    items: Optional[list[dict]] = None,
) -> Optional[dict[int, dict]]:
    """把系统切分的题目块（含内容描述）映射到卷面题目并确定每题满分。

    这是【文本】任务（不传图）：转录文本 + 大题分值 + 题目块描述都已是文本，用文本大模型做
    模糊匹配 + 算术推断，比视觉模型的「结构化 JSON」输出可靠得多。

    优先按「卷面识别出的题目结构（items，题号+分值）」直接对号入座——不再用「作答区数量」
    这类每张卷都不同的硬编码信号。items 已给出题号（major/sub/sub_sub）、标题与分值，LLM 只做
    「题目块 → items 里哪一题」的归属判断；items 缺失时才退回从转录里按题号自寻 + 算术推断。
    返回 {index: {major, sub, sub_sub, score, title}}，index 与 block_descriptions 顺序严格一致（1 起）。
    """
    if not block_descriptions:
        return None
    n = len(block_descriptions)
    majors_txt = "、".join(f"{m}{s}分" for m, s in majors.items())
    order_txt = "、".join(order) or "未知"
    blocks_txt = "\n".join(block_descriptions)

    # 卷面识别出的题目结构（题号+分值）：只保留「叶子题」作为权威列表给 LLM 对号入座，
    # 去掉纯容器头（大题头/小题头/阅读段头），避免 LLM 把题目块错配到大题头、取到错误分值。
    items_txt = ""
    if items:
        leaves = _leaf_items_for_matching(items)
        lines = []
        for idx, it in enumerate(leaves, 1):
            major = str(it.get("major") or "")
            sub = str(it.get("sub") or "")
            sub_sub = str(it.get("sub_sub") or "")
            title = str(it.get("title") or "").strip()
            score = it.get("score")
            if not title and not score:
                continue
            label = f"{major}、{sub}".strip("、")
            if sub_sub:
                label += f"（{sub_sub}）"
            try:
                score = int(score)
            except (TypeError, ValueError):
                score = 0
            lines.append(f"题{idx}：{label} {title}（{score}分）")
        items_txt = "\n".join(lines)

    items_block = (
        "【卷面已识别的题目清单】（每行一题，题号+标题+分值都已定好，绝对权威，照抄即可）：\n"
        + items_txt + "\n\n"
        if items_txt
        else ""
    )
    prompt = (
        "你是统分助手。系统已经切分好题目块（编号、顺序、内容都固定），你只负责给每块补上分值。\n\n"
        f"【卷面】合计 {total}分；大题顺序 {order_txt}；大题分值 {majors_txt}\n\n"
        + items_block
        + f"【题目块】（共 {n} 块，编号与顺序都是固定的，绝对不要改动、不要重排）：\n"
        + blocks_txt + "\n\n"
        "【卷面转录文本】（仅用于核对题目块内容）\n" + transcript + "\n\n"
        "要求：\n"
        f"1. 输出恰好 {n} 项，第1项对应「第1题」、第2项对应「第2题」…，与上面题目块逐一对应。"
        "禁止新增、删除、重排；禁止把上面没有的题（作文、阅读主观题）也列出来。\n"
        "2. 重要：题目块的顺序是按「两栏排版」的物理位置切的，可能与卷面大题逻辑顺序不一致"
        "（例如选择题各小问可能被切散、夹在大题之间）。务必按【每块的内容描述】去匹配卷面上的题，"
        "不要按卷面逻辑顺序重排、不要把你认为『应该在前』的题换到前面。\n"
        + (
            "3. 每个题目块对应【卷面已识别的题目清单】里的某一行：按块的内容描述找那一行，"
            "把该行的 major/sub/sub_sub/score 原样抄进输出（分值和题号一律照抄清单，不要自己另造）。"
            "title 字段不要照抄题目整句，改成 2-6 字的简短题型名（如「读拼音写词语」「加点字读音」「心情」「人物」「作文」）。\n"
            if items_txt
            else "3. 每块 score = 卷面印的该题分值（整数，禁止小数）。优先从转录里找对应题的「（X☆）」。\n"
        )
        + (
            "4. 转录里找不到某块的题时，按「大题总分 − 该大题已识别小题分值之和」推断该块满分。\n"
            "5. 大题总分必须满足合计：转录里大题分值若加起来不等于合计（如 33☆读成35☆、30☆读成28☆），"
            "据合计与小题之和校正，校正后 一+二+三+四=合计。\n"
        )
        + "6. major 用大题号（一/二/三/四），sub 用小题号（1/2/3…，阅读段用（一）（二）），sub_sub 用小问号（（1）（2）…）。\n"
        "7. 只输出一个 JSON 对象，不要解释、不要 markdown 代码块：\n"
        '{"blocks":[{"index":1,"major":"一","sub":"1","sub_sub":"","score":7,"title":"读拼音写词语"},'
        '{"index":3,"major":"一","sub":"3","sub_sub":"（1）","score":2,"title":"加点字读音"}]}\n'
    )
    content = _call_qwen(api_key, [{"role": "user", "content": prompt}], max_tokens=4000, temperature=0.0)
    if not content:
        return None
    obj = _extract_json_obj(content)
    if obj is None:
        return None
    arr = obj.get("blocks") if isinstance(obj, dict) else obj
    if not isinstance(arr, list):
        return None
    result: dict[int, dict] = {}
    for q in arr:
        if not isinstance(q, dict):
            continue
        try:
            idx = int(q.get("index"))
        except (TypeError, ValueError):
            continue
        if idx < 1 or idx > n:
            continue  # 只保留输入块范围内的 index，丢弃模型多列的主观题
        try:
            score = int(round(float(q.get("score"))))
        except (TypeError, ValueError):
            score = 0
        result[idx] = {
            "major": str(q.get("major") or "").strip(),
            "sub": str(q.get("sub") or "").strip(),
            "sub_sub": str(q.get("sub_sub") or "").strip(),
            "score": score,
            "title": _short_title(str(q.get("title") or "")),
        }
    return result or None


def _count_paren_blanks(text: str) -> int:
    """数文本里「（中文）/(中文)」这类学生填空括号的数量。

    只算「含汉字的括号」，自动排除题号（1）、选项字母（A）、拼音（zhǎn）、
    圈码（②）等非填空括号。视觉数空会漏数题干里散落的括号，转录原文里
    每个填空都带「（答案）」，从这里数更稳。
    """
    return len(re.findall(r"[（(]\s*[一-鿿][^\s（）()]{0,15}\s*[）)]", text or ""))


def _transcript_segments(transcript: str) -> dict:
    """把转录原文按题号分段，返回 {(major, sub, sub_sub): 该题内容原文}。

    供确定性数空使用。只把「无分值括号的内容行」归到当前题号下；题号头行
    （带（X☆））只用来切换当前段、不纳入内容。分不出题号的内容行不写回。
    """
    _score_re = r"[(（](\d+)[☆★][)）]"
    re_major = re.compile(r"^(" + _CN_MAJOR_RE + r")[、.．]")
    re_section = re.compile(r"^[（(](" + _CN_MAJOR_RE + r")[)）]")
    re_sub = re.compile(r"^(\d+)[、.．]")
    re_subsub = re.compile(r"^[（(](\d+)[)）]")

    seg: dict = {}
    cur = ("", "", "")
    for ln in (transcript or "").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("[第"):
            continue
        m = re_major.match(ln)
        if m and re.search(_score_re, ln):
            cur = (m.group(1), "", "")
            continue
        m = re_section.match(ln)
        if m and re.search(_score_re, ln):
            cur = (cur[0], m.group(1), "")
            continue
        m = re_sub.match(ln)
        if m and re.search(_score_re, ln):
            cur = (cur[0], m.group(1), "")
            continue
        m = re_subsub.match(ln)
        if m and re.search(_score_re, ln):
            cur = (cur[0], cur[1], m.group(1))
            continue
        # 内容行（无分值括号的正文）
        if cur[0]:
            seg.setdefault(cur, []).append(ln)
    return {k: "\n".join(v) for k, v in seg.items()}


def detect_blank_counts(api_key: str, image_paths: list, leaves: list[dict], transcript: str = "") -> dict:
    """视觉「重切作答区」：对每道叶子题逐题聚焦数空 + 判题型，返回
    {(major, sub, sub_sub, score): {"blanks": int, "kind": str}}。

    百度 correct_edu 的 slot 切分会把阅读段合并成少数几题、且空数少算，导致
    「整题满分 ÷ 错误空数」得出 0.4/0.6 这种脏每空分。这里用 qwen-vl-max 直接看卷面数空。
    实测：整页多题打包数空时，视觉模型会把阅读选段里密集的括号漏数（摔跤 4 vs 8、观察 8 vs 11），
    但每次只盯着一道题数就能数全（摔跤 8 空）。所以改成逐题聚焦数空，空数口径与判卷常识一致：
      - 填空/读拼音/选字/选词：每个需要学生填写的括号（ ）、横线、空白格算 1 空；
      - 选择题：1 空（只选一个选项字母）；
      - 主观/作文/简答：1 空。
    kind ∈ {blank, choice, subjective}。作文/主观题用题面关键词直接判 1 空（跳过视觉调用省时），
    其余逐题数空；多页卷按页尝试，取第一个非 0 结果；数不出的题不写回（由调用方回退均分）。
    """
    if Image is None or not leaves:
        return {}

    _SUBJECTIVE_KW = ("作文", "习作", "表达", "交流", "写作", "简答", "口语", "写话", "写一写")
    # 选择题（单选）确定性信号：题干含「一项是 / 哪一项」必是单选，固定 1 空。
    # 这类题题干常嵌着多个括号（如「绝(②)活…」），视觉数空会把题干括号误数成作答区。
    _CHOICE_PAT = re.compile(r"一项是|哪一项")

    # 从转录原文确定性数括号（每个空都带「（答案）」），用于填空类兜底纠正视觉漏数。
    det_counts: dict = {}
    det_segs: dict = {}
    if transcript:
        det_segs = _transcript_segments(transcript)
        for _k, _txt in det_segs.items():
            _c = _count_paren_blanks(_txt)
            if _c > 0:
                det_counts[_k] = _c

    merged: dict = {}
    for it in leaves:
        if not isinstance(it, dict):
            continue
        major = str(it.get("major") or "").strip()
        sub = str(it.get("sub") or "").strip()
        sub_sub = str(it.get("sub_sub") or "").strip()
        title = str(it.get("title") or "").strip()
        try:
            score = int(it.get("score") or 0)
        except (TypeError, ValueError):
            score = 0
        if not major and not sub and not title:
            continue
        key = (major, sub, sub_sub, score)

        # 作文/主观题：固定 1 空，跳过视觉调用
        if any(k in title for k in _SUBJECTIVE_KW):
            merged[key] = {"blanks": 1, "kind": "subjective"}
            continue
        # 选择题（单选）：题干含「一项是 / 哪一项」确定性判 1 空，跳过视觉数空。
        # 题干内嵌的括号是题目本身的内容、不是作答区，视觉模型会误数成多空，导致 0.4/0.6 脏每空分。
        if _CHOICE_PAT.search(title):
            merged[key] = {"blanks": 1, "kind": "choice"}
            continue

        label = f"{major}、{sub}".strip("、")
        if sub_sub:
            label += f"（{sub_sub}）"
        # 把该题在转录里的完整内容喂给视觉（短题型名太泛，视觉定位不到题目就漏数）；无转录内容时退回短标题。
        _seg = det_segs.get((major, sub, sub_sub), "") if det_segs else ""
        stem_full = (_seg or title).strip()
        stem = stem_full if len(stem_full) <= 300 else stem_full[:300].rstrip("，,、。．；;：: ") + "…"
        prompt = (
            "这是小学语文试卷的一页。请只盯着下面这一道题数空，别的题不要管：\n\n"
            f"【{label}】{stem}（{score}分）\n\n"
            "任务：数清这道题需要学生作答的【空】的数量。\n"
            "· 填空题/读拼音/选字组词/选词填空：数题内【所有】需要填写的括号（ ）、横线、空白格；"
            "选段/文段里嵌入的每一个括号都要数，一个括号算 1 空；不要漏掉文段里分散的任何一个括号；\n"
            "· 选择题：1 空（只选一个选项字母）；\n"
            "· 主观题/作文/简答：1 空。\n"
            "请务必【逐个】数：先把每一个空在心里编号，把每个空该填的字/词按顺序用「|」连起来填进 check，"
            "再根据 check 里的项数填 blanks，两者必须一致。\n"
            "如果这道题【不在这一页】，blanks 填 0。\n"
            "只输出一个 JSON 对象，不要解释、不要 markdown，形如：\n"
            '{"blanks": 8, "kind": "blank", "check": "站|围|转|抱|拽|推|钩|掀"}'
            "（kind 取值：blank / choice / subjective；选择/主观类 check 填「-」）"
        )

        found = False
        for image_path in image_paths:
            if not image_path:
                continue
            try:
                with Image.open(image_path) as src:
                    img = src.convert("RGB")
            except Exception:
                continue
            if max(img.size) > 2200:
                img = img.copy()
                img.thumbnail((2200, 2200), Image.Resampling.LANCZOS)
            content = _call_qwen(
                api_key,
                [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": _data_url(img)}},
                    {"type": "text", "text": prompt},
                ]}],
                max_tokens=1200,
                temperature=0.0,
            )
            if not content:
                continue
            obj = _extract_json_obj(content)
            if isinstance(obj, list):
                obj = obj[0] if obj else {}
            if not isinstance(obj, dict):
                continue
            try:
                blanks = int(obj.get("blanks") or obj.get("blank") or 0)
            except (TypeError, ValueError):
                blanks = 0
            if blanks <= 0:
                continue
            kind = str(obj.get("kind") or obj.get("type") or "").strip() or "blank"
            # 填空类：转录原文数出的括号数更全，取两者较大值兜底视觉漏数（视觉常漏散落的括号）。
            if kind != "choice":
                blanks = max(blanks, det_counts.get((major, sub, sub_sub), 0))
            merged[key] = {"blanks": blanks, "kind": kind}
            found = True
            break

        if not found:
            # 数不出/题不在任何页：不写回，调用方回退「满分 ÷ 百度 slot 数」的旧逻辑
            continue

    return merged


# ── 题目块 → 卷面题（已改为由 match_blocks_to_scores 按识别出的题目结构对号入座） ──
# 旧的 _deterministic_match_blocks 用「作答区数量」（7空=读拼音、6空=选字组词…）做硬编码匹配，
# 那是某一张卷的特例、换卷就错。现改为：识别出的 items（题号+分值）作为权威清单喂给 LLM，
# LLM 只做「题目块 → items 哪一题」的归属判断，不再依赖作答区数量。


def _merge_column_items(items_wp: list[dict], items_tc: list[dict]) -> list[dict]:
    """合并整页转录与分栏转录的题目。

    分栏转录对「阅读大题」（sub 是中文序号（一）（二）…，编号按阅读段重排）更完整、更准，
    但会把全宽的「4.句子练习」这类小题切丢；整页转录对全宽大题更完整。因此：
      - 阅读大题（sub 出现中文序号段头的大题）→ 用分栏结果；
      - 其余大题 → 用整页结果。
    按大题在原转录中的出现顺序拼接（分栏结果里多出的大题追加到末尾）。
    """
    def _is_reading(it: dict) -> bool:
        return bool(re.fullmatch(_CN_MAJOR_RE, str(it.get("sub") or "")) and not it.get("sub_sub"))

    reading_majors = {it.get("major") for it in (items_wp + items_tc) if _is_reading(it)}
    if not reading_majors:
        return items_wp

    def _group(items: list[dict]) -> tuple[dict[str, list[dict]], list[str]]:
        g: dict[str, list[dict]] = {}
        order: list[str] = []
        for it in items:
            m = it.get("major") or ""
            if m not in g:
                g[m] = []
                order.append(m)
            g[m].append(it)
        return g, order

    g_wp, order_wp = _group(items_wp)
    g_tc, order_tc = _group(items_tc)
    result: list[dict] = []
    seen: set[str] = set()
    for m in order_wp:
        seen.add(m)
        if m in reading_majors and m in g_tc:
            result.extend(g_tc[m])
        else:
            result.extend(g_wp[m])
    for m in order_tc:
        if m not in seen:
            result.extend(g_tc[m])
    return result


def recognize_paper_structure(api_key: str, image_path: Path) -> Optional[dict]:
    """识别整张试卷结构。失败返回 None。

    返回：
      - majors: {大题号: 总分}
      - items:  [{major, sub, sub_sub, title, score}]（大题/小题/小问/阅读段，正则解析）
      - total:  卷面合计分（锚点）
      - order:  卷首题序（如 [一,二,三,四]）
      - gaps:   [{major, total, sum, gap}] 大题总分大于小题之和的差值（缺失/截断）
      - transcript: 分段转录原文
    """
    if Image is None:
        return None
    try:
        with Image.open(image_path) as src:
            image = src.convert("RGB")
    except Exception:
        return None

    transcript = _transcribe_paper(api_key, image)
    if not transcript.strip():
        return None

    majors_from_llm = _extract_majors(api_key, image)  # 独立大题锚点
    regex_majors, items, total_anchor, order = _regex_parse(transcript)

    # 两栏排版：分栏转录补读阅读大题（整页转录会把两栏的阅读小题漏行/错归），
    # 阅读大题用分栏结果、其余大题用整页结果合并。
    split_x = _detect_column_split(image)
    if split_x is not None:
        tc = _transcribe_paper(api_key, image, split_x)
        if tc.strip():
            _, items_tc, _, _ = _regex_parse(tc)
            items = _merge_column_items(items, items_tc)

    items = _fix_subsub_assignment(items)

    # 大题总分以独立识别为准（专门读大题标题行，比整卷转录的 OCR 更可靠；转录常把 33 读成 35）。
    # 转录里识别到、独立识别漏掉的大题用转录值补。
    majors = dict(majors_from_llm)
    for m, s in regex_majors.items():
        majors.setdefault(m, s)

    # 用合计锚点补齐缺失大题 / 校正误读分值
    majors = _reconcile_major_totals(majors, items, total_anchor, order)

    # 若大题一个都没识别到，回退用合计+题序兜底（至少给出题号序列）
    if not majors and order:
        majors = {o: 0 for o in order}

    result = _infer(majors, items, total_anchor, order)
    if not result.get("majors"):
        return None
    result["transcript"] = transcript
    return result
