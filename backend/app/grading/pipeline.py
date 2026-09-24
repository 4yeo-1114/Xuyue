# -*- coding: utf-8 -*-
"""批改流程：OCR → 大模型判题 → 画 √/× → 总评。快速批改 + 参照批改。"""
import os
import re
import json
import math
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = ImageDraw = ImageFont = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from app.grading.ocr import run_ocr
from app.grading.doc_convert import ensure_image_path
from app.utils.qwen_settings import get_qwen_config


def _font_file_candidates() -> list[str]:
    """留痕字体候选路径（Windows 开发机 + Linux 服务器常见位置）。"""
    out: list[str] = []
    seen: set[str] = set()

    def _add(path: str) -> None:
        p = str(path or "").strip()
        if not p or p in seen:
            return
        seen.add(p)
        out.append(p)

    _add(os.environ.get("GRADING_FONT_PATH", "").strip())
    try:
        from app.grading.user_paths import project_root

        fonts_dir = project_root() / "assets" / "fonts"
        if fonts_dir.is_dir():
            for pattern in ("*.ttf", "*.ttc", "*.otf"):
                for fp in sorted(fonts_dir.glob(pattern)):
                    _add(str(fp))
    except Exception:
        pass
    if os.name == "nt":
        win_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        for name in ("msyh.ttc", "msyhbd.ttc", "msyhl.ttc", "simhei.ttf", "simsun.ttc"):
            _add(str(win_fonts / name))
    for name in ("msyh.ttc", "simhei.ttf", "arial.ttf"):
        _add(name)
    for path in (
        "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
        "/usr/share/fonts/chinese/wqy-zenhei/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/arphic/ukai.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        _add(path)
    return out


def _load_truetype_font(size: int, *, allow_default: bool = False):
    if ImageFont is None:
        return None
    last_err: Exception | None = None
    for path in _font_file_candidates():
        try:
            if os.path.isfile(path):
                return ImageFont.truetype(path, size)
            return ImageFont.truetype(path, size)
        except Exception as e:
            last_err = e
            continue
    if allow_default:
        if last_err:
            print(f"留痕字体加载失败，将使用默认字体: {last_err}")
        return ImageFont.load_default()
    return None


def _load_cjk_font(size: int):
    """中文留痕字体；优先系统/Windows 字体，缺失时再下载到 assets/fonts/。"""
    font = _load_truetype_font(size, allow_default=False)
    if font is not None:
        return font

    from app.grading.cjk_font import ensure_cjk_font_file

    ensure_cjk_font_file()
    font = _load_truetype_font(size, allow_default=False)
    if font is None:
        print(
            "未找到中文字体，作文旁批无法显示。"
            "请在后端目录执行: python3 scripts/setup_cjk_font.py"
            " 或设置 GRADING_FONT_PATH"
        )
    return font


def _load_ascii_font(size: int):
    """数字、+/- 等 ASCII 留痕（如 +5、0）。"""
    if ImageFont is None:
        return None
    for path in (
        os.environ.get("GRADING_FONT_PATH", "").strip(),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "arial.ttf",
    ):
        if not path:
            continue
        try:
            if os.path.isfile(path) or not path.startswith("/"):
                return ImageFont.truetype(path, size)
        except Exception:
            continue
    return _load_truetype_font(size, allow_default=True)


def _draw_vector_check(draw, cx: int, cy: int, size: int, color: str, width: int) -> None:
    """矢量勾号，不依赖字体（避免 Linux 无字体时 √ 变成红点）。"""
    s = max(12, int(size))
    w = max(2, int(width))
    x1, y1 = cx - int(s * 0.28), cy + int(s * 0.05)
    x2, y2 = cx - int(s * 0.06), cy + int(s * 0.30)
    x3, y3 = cx + int(s * 0.34), cy - int(s * 0.28)
    draw.line([(x1, y1), (x2, y2), (x3, y3)], fill=color, width=w, joint="curve")


def _draw_vector_cross(draw, cx: int, cy: int, size: int, color: str, width: int) -> None:
    """矢量叉号，不依赖字体。"""
    s = max(12, int(size * 0.32))
    w = max(2, int(width))
    draw.line([(cx - s, cy - s), (cx + s, cy + s)], fill=color, width=w)
    draw.line([(cx + s, cy - s), (cx - s, cy + s)], fill=color, width=w)


def _draw_vector_circle(draw, cx: int, cy: int, size: int, color: str, width: int) -> None:
    """未作答留痕：空心圆。"""
    radius = max(8, int(size * 0.30))
    draw.ellipse(
        [(cx - radius, cy - radius), (cx + radius, cy + radius)],
        outline=color,
        width=max(2, int(width)),
    )


def draw_blank_area_cross(draw, x1, y1, x2, y2, *, color: str = "#FF0000", line_width=None) -> None:
    """在未作答/空白区域右上角画叉，替代原来包住整个区域的大圆圈。"""
    if x2 <= x1 or y2 <= y1:
        return
    size = max(28, min(int((y2 - y1) * 0.9), 96))
    if line_width is None:
        line_width = max(3, int(size * 0.12))
    cx = int(x2 - size * 0.25)
    cy = int(y1 + size * 0.25)
    _draw_vector_cross(draw, cx, cy, size, color, line_width)


def _draw_vector_half_check(draw, cx: int, cy: int, size: int, color: str, width: int) -> None:
    """半对留痕：短上扬臂的半勾。"""
    s = max(12, int(size))
    w = max(2, int(width))
    points = [
        (cx - int(s * 0.28), cy + int(s * 0.02)),
        (cx - int(s * 0.06), cy + int(s * 0.28)),
        (cx + int(s * 0.16), cy - int(s * 0.08)),
    ]
    draw.line(points, fill=color, width=w, joint="curve")


def _draw_result_mark(
    draw,
    check_x: int,
    check_y: int,
    font_size: int,
    item: dict,
    mark_font,
    outline_color: str,
    fill_color: str,
    offsets: list,
    *,
    check_cross_scale: float = 1.0,
) -> None:
    """在作答区旁绘制对错（√/×）。"""
    result = str(item.get("result") or "")
    glyph_size = max(36, int(font_size * max(0.75, min(1.0, check_cross_scale))))
    cx = check_x + int(glyph_size * 0.35)
    cy = check_y + int(glyph_size * 0.5)
    line_w = max(3, int(glyph_size * 0.09))

    # 1) 对错符号：未作答画叉、半对画半勾、对/错画 √/×
    if result == "未作答":
        _draw_vector_cross(draw, cx, cy, glyph_size, fill_color, line_w)
    elif result == "半对":
        _draw_vector_half_check(draw, cx, cy, glyph_size, fill_color, line_w)
    else:
        mark = "√" if result == "对" else "×"
        font = _mark_font(glyph_size) if check_cross_scale != 1.0 else (mark_font or _load_cjk_font(font_size))
        if font is None:
            font = _load_cjk_font(glyph_size)
        if font is not None:
            for ox, oy in offsets:
                draw.text((check_x + ox, check_y + oy), mark, fill=outline_color, font=font)
            draw.text((check_x, check_y), mark, fill=fill_color, font=font)
        else:
            color = fill_color
            if result == "对":
                _draw_vector_check(draw, cx, cy, glyph_size, color, line_w)
            else:
                _draw_vector_cross(draw, cx, cy, glyph_size, color, line_w)

# 逐题视觉批改并发（DashScope 有账号级 QPS 限制，不宜盲目加大；可用环境变量覆盖）
GRADE_MAX_WORKERS = int(os.environ.get("GRADING_MAX_WORKERS", "16"))
# 单次 LLM 调用超时（秒）：默认 60，防止个别请求在 DashScope 排队时卡满 SDK 默认的 600s
GRADING_LLM_TIMEOUT = float(os.environ.get("GRADING_LLM_TIMEOUT", "60"))

PROMPT_BLOCK = """你是试卷批改助手。当前图片是试卷上的**第 {index} 个区域**（OCR 按顺序切出的一个块）。

【重要】只有**包含学生手写答题笔迹**的区域才需要批改并留痕；其余一律不批改。

请严格按以下规则判断：

1. **is_question: true**（需要批改、打 √/×）—— 仅当该区域内**明确可见学生手写的作答内容**（手写文字、算式、选项勾选等）。即：学生在该处写了答案，你才能判对错。

2. **is_question: false**（不批改、不留痕）—— 以下情况全部返回 false，不要判题：
   - 仅包含**题号、题干、小题标题**（如「第1题」「（1）」「一、选择题」、题目要求文字等印刷内容），即使有题号或题目要求，只要**没有学生手写答案**就为 false；
   - 试卷总标题、考试说明、注意事项、装订线等；
   - 空白区域或仅有印刷体、看不到手写笔迹的区域；
   - 任何**没有学生在该处写下答案**的区域。

总结：只对「学生在此处写了答案」的那一块判对错；题目标题、纯题干、纯题号等一律 is_question: false。

注意：本卷答案经 OCR 识别，可能存在个别错别字、缺字、串行或识别不清，请结合笔迹与上下文语义进行判断，不要因个别 OCR 误识别就直接判错；确无法辨认时才按最可能判定并在 comment 中说明。

只输出一个合法 JSON，不要 markdown 代码块或其它文字：
{{
  "is_question": true 或 false,
  "result": "对" 或 "半对" 或 "错"（仅当 is_question 为 true 且已作答时必填；主观题要点/步骤部分正确可判「半对」）,
  "partial_ratio": 0.0~1.0（仅当 result 为「半对」时填：该题应得满分的比例，如对六成填 0.6）,
  "comment": "简短评语（仅题目时必填）"
}}"""

PROMPT_BLOCK_REF = """你是阅卷老师，在做**参照标准答案批改**。**严禁在标题、题干、题号上留痕；只对「学生写答案的那一小块」留痕。**

本次输入**按顺序**两张图：
- **图1**：标准答案试卷在该区域的裁剪。
- **图2**：学生试卷同一位置的裁剪。

【第一步：is_question 判定——本块是否为「答案书写区」】

**以下一律 is_question: false，严禁判题、严禁打 √/×**：
- **标题**：试卷名称、考试名称、大题名称（如「一、选择题」「二、填空题」）、任何作为标题的文字；
- **题干**：题目要求、题目文字、小题说明、（1）（2）等小题标题、选项前的引导语、任何「出题内容」而非「答题空位」；
- **题号**：如「第1题」「（1）」「1.」及纯题号；
- 装订线、注意事项、说明、仅有印刷体无答题空位的整块。

**仅当以下情况才 is_question: true**：图1 中**明确是「写答案的位置」**——即标准答案**已书写答案内容**的那一行/那一格（如一行答案、一个填空、选项勾选位、算式书写区），而不是题目文字或标题。若本块主要是标题、题干、题号或大段题目文字，**必须** is_question: false。

【第二步：当 is_question 为 true 时的判题（按优先级）】

**未作答直接判错**：若该块是学生手写作答区，但图2中**没有学生手写笔迹**（空白、未填、未勾选），则**直接** result「错」，comment 可写「未作答」，留痕打 ×。**如果标准答案也是空白的则学生试卷一样要留痕打 ×。**

**有作答时再对比标准答案**：若图2中有学生手写，再与图1对比。**严格按标准答案批改**：
- result「对」：图1与图2必须是**同一道题的答案区域**，且答案**含义一致或等价**（表述不同、数值等价、选项一致等均可判对）。即：同一作答位置、意思接近即可判对。
- result「错」：以下任一情况必判错：
  1. **完全不同**：图1与图2是不同题目、不同试卷、完全无关的内容；
  2. **答错**：同一道题但学生答案与标准答案明显不同、错误；
  3. **无法对应**：学生所答并非图1对应的那道题。


注意：本卷答案经 OCR 识别，可能存在个别错别字、缺字、串行或识别不清，请结合笔迹与上下文语义进行判断，不要因个别 OCR 误识别就直接判错；确无法辨认时才按最可能判定并在 comment 中说明。

只输出一个合法 JSON，不要 markdown 或其它文字：
{{
  "is_question": true 或 false,
  "result": "对" 或 "半对" 或 "错"（仅当 is_question 为 true 时必填；主观题要点/步骤部分正确可判「半对」）,
  "partial_ratio": 0.0~1.0（仅当 result 为「半对」时填：该题应得满分的比例，如对六成填 0.6）,
  "comment": "简短评语（仅题目时必填，未作答可写「未作答」）"
}}"""

PROMPT_BLOCK_SMART_REF = """你是高级阅卷组长，正在进行【智能参照批改】（双重校验模式）。
当前处理的是试卷的**第 {index} 个区域**。

我已经让初级阅卷员对该区域的学生作答进行了初步批改。
同时，我也为你提供了该区域对应的【标准答案截图】。

本次输入按顺序为：
- **图1**：绝对权威、不可质疑的标准答案截图。
- **图2**：学生试卷在该区域的截图。

【初级阅卷员的判定结果】：
{initial_result}

请你严格对照【图1】（标准答案），检查初级阅卷员对【图2】（学生作答）的判定是否正确。
核心原则：
1. 【图1】是绝对真理！任何与【图1】内容一致的作答，必须毫不犹豫地判为“对”。
2. 不要被初级阅卷员的错误判断带偏。如果【图1】和【图2】内容完全一样或意思完全一致，但初级阅卷员判了“错”，你必须坚决推翻它，纠正为“对”。
3. 如果 is_question 为 false（说明这是题干或无作答区域），请直接输出原来的结果。
4. 如果学生未作答，但初级阅卷员没发现，请纠正为 is_question: true, result: "错", comment: "未作答"。
5. 允许学生步骤不全但意思正确、或者计算过程正确但结果错误时的酌情给分：若部分正确（要点对了一半左右），result 判「半对」并给出 partial_ratio；否则根据实际情况定。

注意：本卷答案经 OCR 识别，可能存在个别错别字、缺字、串行或识别不清，请结合笔迹与上下文语义进行判断，不要因个别 OCR 误识别就直接判错；确无法辨认时才按最可能判定并在 comment 中说明。

只输出一个合法 JSON，不要 markdown 或其它文字：
{{
  "is_question": true 或 false,
  "result": "对" 或 "半对" 或 "错"（仅当 is_question 为 true 时必填；主观题要点/步骤部分正确可判「半对」）,
  "partial_ratio": 0.0~1.0（仅当 result 为「半对」时填：该题应得满分的比例，如对六成填 0.6）,
  "comment": "简短评语（给出最终判决的理由）"
}}"""

PROMPT_SUMMARY = """根据以下各题的批改结果，写两段内容：

1. **总评**（2～4 句话）：概括整张试卷的完成情况、正确率、主要问题与改进建议。
2. **逐题讲解**：按题号列出每一道被批改的题目，每题一行或一小段，格式为「第X题：评语/讲解」。

各题批改结果：
{questions_text}

请直接输出总评与逐题讲解，无需再输出 JSON。格式示例：
总评：
（你的总评内容）

逐题讲解：
第X题：（讲解）
第Y题：（讲解）
"""


def _get_openai_client():
    if not OpenAI:
        raise RuntimeError("需要安装 openai: pip install openai")
    api_key, _ = get_qwen_config()
    if not api_key:
        raise RuntimeError("系统设置中未配置千问 API Key")
    return OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        timeout=GRADING_LLM_TIMEOUT,
        max_retries=1,
    )


def _result_label(result, partial_ratio=None) -> str:
    """对/错/未作答 原样返回；半对 拼上比例（如 半对（0.6））。"""
    r = str(result or "")
    if r == "半对":
        if partial_ratio is None:
            return "半对"
        try:
            ratio = min(1.0, max(0.0, float(partial_ratio)))
            return f"半对（{ratio:g}）"
        except (TypeError, ValueError):
            return "半对"
    return r or "错"


def _coerce_partial_ratio(v):
    if v is None:
        return None
    try:
        r = float(v)
    except (TypeError, ValueError):
        return None
    return min(1.0, max(0.0, r))


def _parse_block_result(text: str) -> dict:
    raw = (text or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if m:
        raw = m.group(1).strip()
    start = raw.find("{")
    if start == -1:
        return {"is_question": False, "result": "", "comment": "", "partial_ratio": None}
    depth = 0
    for i in range(start, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    d = json.loads(raw[start : i + 1])
                    return {
                        "is_question": bool(d.get("is_question", False)),
                        "result": str(d.get("result", "")).strip() or "",
                        "comment": str(d.get("comment", "")).strip() or "",
                        "partial_ratio": _coerce_partial_ratio(d.get("partial_ratio")),
                    }
                except json.JSONDecodeError:
                    pass
                break
    return {"is_question": False, "result": "", "comment": "", "partial_ratio": None}


def _pil_image_to_data_url(pil_img, max_side: int = 0, quality: int = 95) -> str:
    """将 PIL 图转为 data URL 供大模型使用。max_side=0 表示不缩放，使用原图；quality 默认 95 保证清晰度。"""
    if Image is None or pil_img is None:
        raise RuntimeError("需要 Pillow")
    img = pil_img.convert("RGB")
    if max_side and max_side > 0:
        w, h = img.size
        if max(w, h) > max_side:
            ratio = max_side / max(w, h)
            new_w, new_h = int(w * ratio), int(h * ratio)
            resample = getattr(Image, "Resampling", None)
            lanczos = resample.LANCZOS if resample else getattr(Image, "LANCZOS", 1)
            img = img.resize((new_w, new_h), lanczos)
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    import base64
    b64 = base64.standard_b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def _grade_one_block(client, crop_data_url: str, index: int) -> dict:
    prompt = PROMPT_BLOCK.format(index=index)
    try:
        completion = client.chat.completions.create(
            model="qwen-vl-max",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": crop_data_url}},
                        {"type": "text", "text": prompt},
                    ],
                },
            ],
            stream=False,
            extra_body={"enable_thinking": False},
        )
        text = (completion.choices[0].message.content or "").strip()
        return _parse_block_result(text)
    except Exception:
        return {"is_question": False, "result": "", "comment": ""}


def _grade_one_block_reference(client, standard_answer_data_url: str, student_crop_data_url: str, index: int) -> dict:
    prompt = PROMPT_BLOCK_REF.format(index=index)
    try:
        completion = client.chat.completions.create(
            model="qwen-vl-max",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": standard_answer_data_url}},
                        {"type": "image_url", "image_url": {"url": student_crop_data_url}},
                        {"type": "text", "text": prompt},
                    ],
                },
            ],
            stream=False,
            extra_body={"enable_thinking": False},
        )
        text = (completion.choices[0].message.content or "").strip()
        return _parse_block_result(text)
    except Exception:
        return {"is_question": False, "result": "", "comment": ""}


def _grade_one_block_smart_ref(client, standard_answer_data_url: str, student_crop_data_url: str, index: int, initial_result: dict) -> dict:
    prompt = PROMPT_BLOCK_SMART_REF.format(index=index, initial_result=json.dumps(initial_result, ensure_ascii=False))
    try:
        completion = client.chat.completions.create(
            model="qwen-vl-max",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": standard_answer_data_url}},
                        {"type": "image_url", "image_url": {"url": student_crop_data_url}},
                        {"type": "text", "text": prompt},
                    ],
                },
            ],
            stream=False,
            extra_body={"enable_thinking": False},
        )
        text = (completion.choices[0].message.content or "").strip()
        return _parse_block_result(text)
    except Exception:
        return initial_result

def _call_summary(client, questions_text: str) -> str:
    if not questions_text.strip():
        return "暂无批改题目。"
    prompt = PROMPT_SUMMARY.format(questions_text=questions_text)
    try:
        _, qwen_model = get_qwen_config()
        completion = client.chat.completions.create(
            model=qwen_model or "qwen-plus",
            messages=[{"role": "user", "content": prompt}],
            stream=False,
            extra_body={"enable_thinking": False},
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception:
        return questions_text


def _default_font():
    if ImageFont is None:
        return None
    return _load_cjk_font(36) or _load_ascii_font(36)


def _mark_font(size: int = 44):
    """留痕用字体（勾叉 √/× 与分数）；有中文字体时用原字体样式，无字体时由矢量兜底。"""
    if ImageFont is None:
        return _default_font()
    return _load_cjk_font(size) or _load_ascii_font(size)


def _adaptive_mark_params(w: int, h: int):
    """根据试卷尺寸计算留痕字号与偏移，整体字号更大、更醒目。"""
    area = w * h
    diag = math.sqrt(area)
    font_size = max(48, min(100, int(diag * 0.028)))  # 稍微缩小一点整体字号
    scale = font_size / 44.0
    
    # 描边偏移：只保留 1px 四方向浅描边，勾叉/加分笔画更细（原 2px 八方向太粗）
    offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    margin_x = max(12, int(20 * scale))
    margin_y = max(32, int(40 * scale))
    return font_size, offsets, margin_x, margin_y


def _draw_manual_total_score_mark(draw, w: int, h: int, score_total) -> None:
    """Render the manual total with the same baseline and sizing as the live SVG."""
    try:
        value = round(float(score_total), 2)
    except (TypeError, ValueError):
        return
    if not math.isfinite(value):
        return
    score_text = str(int(value)) if value.is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")
    font_size = max(39, min(82, int(w * 0.048)))
    font = _load_cjk_font(font_size) or _load_ascii_font(font_size)
    if font is None:
        return
    x = max(32, int(w * 0.035))
    baseline_y = max(96, int(h * 0.12))
    prefix = "得分："
    label = f"{prefix}{score_text}"
    color = "#dc2626"
    try:
        draw.text((x, baseline_y), label, fill=color, font=font, anchor="ls")
    except Exception:
        try:
            ascent = int(font.getmetrics()[0])
        except Exception:
            ascent = font_size
        draw.text((x, baseline_y - ascent), label, fill=color, font=font)
    underline_x = x + font_size * 2.7
    underline_width = font_size * max(0.72, len(score_text) * 0.62)
    underline_y = baseline_y + font_size * 0.18
    draw.line(
        [(int(underline_x), int(underline_y)), (int(underline_x + underline_width), int(underline_y))],
        fill=color,
        width=max(2, int(font_size * 0.055)),
    )


def _draw_manual_result_mark(draw, image_width: int, image_height: int, item: dict) -> None:
    """Draw one manual-grading mark using the live UI's size and placement."""
    bbox = item.get("bbox")
    if not bbox or len(bbox) != 4:
        return
    try:
        x1, y1, x2, y2 = [float(value) for value in bbox]
    except (TypeError, ValueError):
        return
    size = max(30.0, min(80.0, image_width * 0.025))
    x = min(image_width - size, x2 - size * 0.25)
    y = min(image_height - size, max(y1, y2 - size))
    stroke_width = max(4, int(round(size * 0.08)))
    color = "#FF0000"
    result = str(item.get("result") or "")

    def point(px: float, py: float) -> tuple[int, int]:
        return int(round(x + size * px)), int(round(y + size * py))

    is_partial = result == "半对"
    mark = "√" if result in ("对", "半对") else "×"
    font = _mark_font(max(1, int(round(size))))
    if font is not None:
        baseline_y = y + size * 0.82
        try:
            draw.text(
                (int(round(x)), int(round(baseline_y))),
                mark,
                fill=color,
                font=font,
                anchor="ls",
            )
        except Exception:
            try:
                ascent = int(font.getmetrics()[0])
            except Exception:
                ascent = int(round(size))
            draw.text(
                (int(round(x)), int(round(baseline_y - ascent))),
                mark,
                fill=color,
                font=font,
            )
        if is_partial:
            draw.line(
                [point(0.28, 0.43), point(0.62, 0.52)],
                fill=color,
                width=stroke_width,
            )
        return
    if result in ("对", "半对"):
        draw.line([point(0.10, 0.54), point(0.34, 0.78), point(0.84, 0.18)], fill=color, width=stroke_width, joint="curve")
        if is_partial:
            draw.line([point(0.28, 0.43), point(0.62, 0.52)], fill=color, width=stroke_width)
    else:
        draw.line([point(0.20, 0.20), point(0.80, 0.80)], fill=color, width=stroke_width)
        draw.line([point(0.80, 0.20), point(0.20, 0.80)], fill=color, width=stroke_width)


def draw_real_marks_and_save(
    image_path: str,
    blocks_with_result: list,
    result_dir: str,
    file_stem: str,
    *,
    check_cross_scale: float = 1.0,
    score_total=None,
    manual_style: bool = False,
) -> tuple:
    if Image is None or ImageDraw is None:
        raise RuntimeError("需要安装 Pillow")
    path = os.path.abspath(image_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"图片不存在: {path}")
    os.makedirs(result_dir, exist_ok=True)
    ext = os.path.splitext(path)[1].lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png"):
        ext = ".jpg"
    original_name = f"original_{file_stem}{ext}"
    annotated_name = f"annotated_{file_stem}{ext}"
    original_path = os.path.join(result_dir, original_name)
    annotated_path = os.path.join(result_dir, annotated_name)
    img = Image.open(path).convert("RGB")
    w, h = img.size
    img.save(original_path, quality=95)
    draw = ImageDraw.Draw(img)
    font_size, offsets, margin_x, margin_y = _adaptive_mark_params(w, h)
    mark_font = _mark_font(font_size)
    outline_color, fill_color = "#CC0000", "#FF0000"  # 大红色（政府红头红），更醒目
    edge = max(40, int(60 * font_size / 52))
    mark_right_shift = max(0, int(os.environ.get("MARK_RIGHT_SHIFT_PX", "28")))
    for item in blocks_with_result:
        if not item.get("is_question"):
            continue
        if manual_style:
            _draw_manual_result_mark(draw, w, h, item)
            continue
        bbox = item.get("bbox")
        if not bbox or len(bbox) != 4:
            rb = item.get("right_bottom")
            if rb and len(rb) == 2:
                bbox = [rb[0] - 50, rb[1] - 30, rb[0], rb[1]]
            else:
                continue
        x_min, y_min, x_max, y_max = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
        center_y = (y_min + y_max) / 2
        check_x = min(x_max - margin_x + mark_right_shift, w - edge - int(font_size * 0.4))
        check_y = int(center_y - font_size * 0.5)
        check_y = max(0, min(check_y, h - font_size - 2))
        _draw_result_mark(
            draw, check_x, check_y, font_size, item, mark_font,
            outline_color, fill_color, offsets, check_cross_scale=check_cross_scale,
        )
    if score_total is not None:
        _draw_manual_total_score_mark(draw, w, h, score_total)
    img.save(annotated_path, quality=95)
    return (original_name, annotated_name)


def draw_marks_only_and_save(
    image_path: str,
    blocks_with_result: list,
    result_dir: str,
    file_stem: str,
    *,
    check_cross_scale: float = 1.0,
    score_total=None,
    manual_style: bool = False,
) -> str:
    if Image is None or ImageDraw is None:
        raise RuntimeError("需要安装 Pillow")
    path = os.path.abspath(image_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"图片不存在: {path}")
    os.makedirs(result_dir, exist_ok=True)
    ext = os.path.splitext(path)[1].lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png"):
        ext = ".jpg"
    marks_only_name = f"marks_only_{file_stem}{ext}"
    marks_only_path = os.path.join(result_dir, marks_only_name)
    img_ref = Image.open(path).convert("RGB")
    w, h = img_ref.size
    dpi_save = img_ref.info.get("dpi")
    img_ref.close()
    img = Image.new("RGB", (w, h), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    font_size, offsets, margin_x, margin_y = _adaptive_mark_params(w, h)
    mark_font = _mark_font(font_size)
    outline_color, fill_color = "#CC0000", "#FF0000"  # 大红色（政府红头红），更醒目
    edge = max(40, int(60 * font_size / 52))
    mark_right_shift = max(0, int(os.environ.get("MARK_RIGHT_SHIFT_PX", "28")))
    for item in blocks_with_result:
        if not item.get("is_question"):
            continue
        if manual_style:
            _draw_manual_result_mark(draw, w, h, item)
            continue
        bbox = item.get("bbox")
        if not bbox or len(bbox) != 4:
            rb = item.get("right_bottom")
            if rb and len(rb) == 2:
                bbox = [rb[0] - 50, rb[1] - 30, rb[0], rb[1]]
            else:
                continue
        x_min, y_min, x_max, y_max = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
        center_y = (y_min + y_max) / 2
        check_x = min(x_max - margin_x + mark_right_shift, w - edge - int(font_size * 0.4))
        check_y = int(center_y - font_size * 0.5)
        check_y = max(0, min(check_y, h - font_size - 2))
        _draw_result_mark(
            draw, check_x, check_y, font_size, item, mark_font,
            outline_color, fill_color, offsets, check_cross_scale=check_cross_scale,
        )
    if score_total is not None:
        _draw_manual_total_score_mark(draw, w, h, score_total)
    save_kw = {"quality": 95}
    if dpi_save and isinstance(dpi_save, tuple) and len(dpi_save) >= 2 and dpi_save[0] > 0:
        save_kw["dpi"] = (round(dpi_save[0]), round(dpi_save[1] if dpi_save[1] else dpi_save[0]))
    img.save(marks_only_path, **save_kw)
    return marks_only_name


def draw_manual_annotations(draw, img_w: int, img_h: int, blocks: list, question_notes, paper_note) -> None:
    """在卷面留痕图上绘制老师手动批注：每道题一句（画在该题结尾下方）+ 整卷总评（画卷面底部）。

    - blocks：批改结果 blocks，按 ``index`` 聚合，取每道题最靠下的作答区 bbox 作为「题结尾」。
    - question_notes：``{ "<题号>": "批注文字" }``，每道题一个。
    - paper_note：整卷总评字符串，画在全卷最后一道题下方。
    仅绘制老师手写批注；AI 自动评语（comment）仍只出现在结果文本框。
    """
    question_notes = question_notes if isinstance(question_notes, dict) else {}
    paper_note = str(paper_note or "").strip()
    if not question_notes and not paper_note:
        return

    note_font = _load_cjk_font(max(28, int(min(img_w, img_h) * 0.016)))
    if note_font is None:
        return

    try:
        char_w = max(12, draw.textlength("中", font=note_font))
    except Exception:
        char_w = note_font.size
    margin = max(24, int(img_w * 0.03))
    max_chars = max(6, int((img_w - margin * 2) / char_w))
    line_h = int(note_font.size * 1.4)

    def _draw_lines(text: str, x: int, y: int) -> int:
        """把 text 从 (x, y) 向下逐行绘制（自动换行，超出图片底边则截断），返回下一行起始 y。"""
        lines: list = []
        for seg in str(text or "").split("\n"):
            seg = seg.rstrip()
            while len(seg) > max_chars:
                lines.append(seg[:max_chars])
                seg = seg[max_chars:]
            if seg:
                lines.append(seg)
        ty = y
        for ln in lines:
            if ty + line_h > img_h:
                break
            draw.text((x, ty), ln, fill="#d62727", font=note_font, anchor="ls")
            ty += line_h
        return ty

    # 1) 按题号聚合每道题的「结尾」：取该题所有有效作答区里 y_max 最大的那个 bbox
    anchors: dict[str, tuple[int, int]] = {}
    for blk in blocks:
        if not isinstance(blk, dict):
            continue
        idx = blk.get("index")
        key = str(idx) if idx is not None else ""
        if not key or key == "None":
            continue
        bbox = blk.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        try:
            x_min, y_min, x_max, y_max = (int(float(v)) for v in bbox[:4])
        except (TypeError, ValueError):
            continue
        if x_max <= x_min or y_max <= y_min:
            continue
        cur = anchors.get(key)
        if cur is None or y_max > cur[1]:
            anchors[key] = (max(margin, min(x_min, img_w - margin)), y_max)

    global_bottom = max((a[1] for a in anchors.values()), default=0)

    # 2) 逐题批注（按卷面从上到下顺序）
    notes_bottom = 0
    if question_notes:
        for key, (x, y_max) in sorted(anchors.items(), key=lambda kv: kv[1][1]):
            text = question_notes.get(key)
            if text is None:
                try:
                    text = question_notes.get(int(key))
                except (TypeError, ValueError):
                    text = None
            text = str(text or "").strip()
            if not text:
                continue
            ty = _draw_lines(text, x, y_max + int(line_h * 0.4))
            notes_bottom = max(notes_bottom, ty)

    # 3) 整卷总评（全卷最后一道题下方；空间不足则贴着图片底部向上排）
    if paper_note:
        y_start = max(global_bottom + int(line_h * 0.8), notes_bottom + int(line_h * 0.4))
        if y_start + line_h > img_h:
            est_lines = max(1, math.ceil(len(paper_note) / max_chars))
            y_start = max(margin, img_h - est_lines * line_h - int(line_h * 0.4))
        _draw_lines(paper_note, margin, y_start)


def _baidu_fallback_grade(image_path: str, ocr_exc: Exception) -> tuple:
    """PaddleOCR 公共口不可用时降级到百度 correct_edu（自有配额）完成整卷批改。"""
    from app.grading.baidu_grading import baidu_grade_single

    try:
        result_text, blocks, _raw = baidu_grade_single(image_path)
    except Exception as _baidu_exc:
        raise RuntimeError(
            f"OCR 提交失败且百度批改降级也失败：OCR={ocr_exc}；百度={_baidu_exc}"
        ) from _baidu_exc
    if not blocks:
        return "未识别到任何题目，请换图或检查百度批改配置。", [], None, None
    return result_text, blocks, None, None


def real_grade_pipeline(image_path: str) -> tuple:
    """快速批改：OCR → 每块大模型判题 → 总评。支持图片、PDF、Word（转首页图像）。返回 (result_text, blocks_with_result, original_img, None)。

    布局 OCR 优先走 PaddleOCR 公共口；当公共口不可用（如 10010「任务队列已满」/ 超时 / 网络异常）时，
    自动降级到百度 correct_edu 智能作业批改（自有配额），保证快速批改入口不因公共口挤爆而整体失败。
    """
    image_path, _ = ensure_image_path(image_path)
    try:
        blocks, original_img = run_ocr(image_path)
    except Exception as _ocr_exc:
        return _baidu_fallback_grade(image_path, _ocr_exc)
    if not blocks:
        return "未识别到任何文字块，请换图或检查 OCR 配置。", [], None, None
    client = _get_openai_client()
    tasks = []
    for blk in blocks:
        x_min, y_min, x_max, y_max = blk["bbox"]
        crop = original_img.crop((
            max(0, x_min - 2), max(0, y_min - 2),
            min(original_img.width, x_max + 2), min(original_img.height, y_max + 2),
        ))
        crop_url = _pil_image_to_data_url(crop)
        tasks.append((blk, crop_url))

    def _grade_task(item):
        blk, crop_url = item
        return blk, _grade_one_block(client, crop_url, blk["index"])

    with ThreadPoolExecutor(max_workers=GRADE_MAX_WORKERS) as executor:
        results = list(executor.map(_grade_task, tasks))
    for blk, res in results:
        blk["is_question"] = res["is_question"]
        blk["result"] = res["result"]
        blk["comment"] = res["comment"]
        blk["partial_ratio"] = res.get("partial_ratio")
    questions_text_parts = [
        f"第{blk['index']}题：result={blk['result']}, comment={blk['comment']}"
        for blk in blocks
        if blk.get("is_question") and (blk.get("result") or blk.get("comment"))
    ]
    questions_text = "\n".join(questions_text_parts)
    summary = _call_summary(client, questions_text)
    result_lines = [summary, "\n\n--- 逐题详情 ---\n"]
    for blk in blocks:
        if not blk.get("is_question"):
            continue
        result_lines.append(f"第{blk['index']}题：{_result_label(blk.get('result'), blk.get('partial_ratio'))} — {blk.get('comment', '')}")
    result_text = "\n".join(result_lines)
    # 必须返回元组：调用方（router._run_one_paper 等）解包 result, blocks, img, None
    return result_text, blocks, original_img, None


def real_grade_pipeline_smart_ref(standard_answer_path: str, student_image_path: str, precomputed_std: dict = None, stop_event=None) -> tuple:
    """智能参照批改（双重校验）：
    第一步：调用真实百度接口（baidu_grade_single）完成盲批和坐标提取。
    第二步：对照标准答案（同样使用百度接口切分）调用 Qwen 进行复核。
    返回 (result_text, blocks_with_result, baidu_raw, None)。
    """
    from app.grading.baidu_grading import baidu_grade_single
    
    # 1. 执行真实的百度智能盲批（处理学生试卷）
    student_image_path, _ = ensure_image_path(student_image_path)
    result_text, blocks_with_result, baidu_raw = baidu_grade_single(student_image_path, stop_event=stop_event)
    
    if not blocks_with_result:
        return result_text, blocks_with_result, baidu_raw, None

    # 2. 处理标准答案（放弃 PaddleOCR，改用百度接口获取同源坐标）
    # 为了防止百度报错，我们把标准答案当成普通试卷发给百度批一次，只取它的坐标(blocks)和原图
    std_blocks, std_raw = [], None
    if os.path.isfile(standard_answer_path):
        std_abs = os.path.abspath(standard_answer_path)
        std_abs_resolved = os.path.realpath(std_abs) if os.path.exists(std_abs) else std_abs
        student_abs = os.path.abspath(student_image_path)
        student_abs_resolved = os.path.realpath(student_abs) if os.path.exists(student_abs) else student_abs
        is_same_file = std_abs_resolved == student_abs_resolved

        if is_same_file:
            # 如果传的是同一张图，直接复用刚才的 blocks
            std_blocks = blocks_with_result
            std_img = Image.open(student_image_path).convert("RGB")
        else:
            _, std_blocks, std_raw = baidu_grade_single(standard_answer_path, stop_event=stop_event)
            std_img = Image.open(standard_answer_path).convert("RGB")
    else:
        return result_text, blocks_with_result, baidu_raw, None
        
    full_std_url = _pil_image_to_data_url(std_img)

    # 准备大图用于抠图
    try:
        original_img = Image.open(student_image_path).convert("RGB")
    except Exception:
        return result_text, blocks_with_result, baidu_raw, None

    # 建立标准答案的 题号 -> 截图URL 的精确映射
    std_url_map = {}
    for s_blk in std_blocks:
        s_bbox = s_blk.get("bbox")
        s_idx = s_blk.get("index")
        if not s_bbox or len(s_bbox) != 4 or not s_idx:
            continue
        sx1, sy1, sx2, sy2 = s_bbox
        try:
            s_crop = std_img.crop((
                max(0, sx1 - 2), max(0, sy1 - 2),
                min(std_img.width, sx2 + 2), min(std_img.height, sy2 + 2),
            ))
            std_url_map[s_idx] = _pil_image_to_data_url(s_crop)
        except Exception:
            pass

    client = _get_openai_client()
    tasks = []
    
    # 构造复审任务
    for blk in blocks_with_result:
        if not blk.get("is_question"):
            continue
        
        # 将百度的结果转换为 Qwen 需要的 initial_result 格式
        initial_result = {
            "is_question": True,
            "result": blk.get("result", ""),
            "comment": blk.get("comment", "")
        }
        
        bbox = blk.get("bbox")
        idx = blk.get("index")
        if not bbox or len(bbox) != 4 or not idx:
            continue
            
        x_min, y_min, x_max, y_max = bbox
        try:
            crop = original_img.crop((
                max(0, x_min - 2), max(0, y_min - 2),
                min(original_img.width, x_max + 2), min(original_img.height, y_max + 2),
            ))
            student_crop_url = _pil_image_to_data_url(crop)
            
            # 同源坐标对齐：直接通过百度解析出的题号(index)去拿标准答案对应的截图
            std_url = std_url_map.get(idx, full_std_url)
                
            tasks.append((blk, std_url, student_crop_url, initial_result))
        except Exception:
            continue

    def _task_smart_ref(item):
        blk, s_url, c_url, initial_result = item
        if stop_event and stop_event.is_set():
            return blk, initial_result
        # 调用 Qwen 对照标准答案复审
        final_result = _grade_one_block_smart_ref(client, s_url, c_url, blk["index"], initial_result)
        return blk, final_result

    # 3. 多线程执行 Qwen 复审
    with ThreadPoolExecutor(max_workers=GRADE_MAX_WORKERS) as executor:
        results = list(executor.map(_task_smart_ref, tasks))
        
    # 4. 合并结果
    for blk, res in results:
        blk["is_question"] = res.get("is_question", blk.get("is_question", True))
        if blk["is_question"]:
            blk["result"] = res.get("result", blk.get("result", ""))
            blk["comment"] = res.get("comment", blk.get("comment", ""))
            blk["partial_ratio"] = res.get("partial_ratio", blk.get("partial_ratio"))
        else:
            blk["result"] = ""
            blk["comment"] = ""
            blk["partial_ratio"] = None

    # 5. Qwen 重新生成总评
    questions_text_parts = [
        f"第{blk.get('baidu_real_name', blk.get('index', '?'))}题-作答区{blk.get('sub_index', '1')}：result={blk.get('result', '')}, comment={blk.get('comment', '')}"
        for blk in blocks_with_result
        if blk.get("is_question") and (blk.get("result") or blk.get("comment"))
    ]
    questions_text = "\n".join(questions_text_parts)
    summary = _call_summary(client, questions_text)
    
    result_lines = [summary, "\n\n--- 逐题详情 ---\n"]
    for blk in blocks_with_result:
        if not blk.get("is_question"):
            continue
        real_name = blk.get("baidu_real_name", blk.get("index", "?"))
        if blk.get("baidu_is_slot"):
            result_lines.append(f"第{real_name}题-作答区{blk.get('sub_index', '1')}：{_result_label(blk.get('result'), blk.get('partial_ratio'))} — {blk.get('comment', '')}")
        else:
            result_lines.append(f"第{real_name}题：{_result_label(blk.get('result'), blk.get('partial_ratio'))} — {blk.get('comment', '')}")
    
    result_text = "\n".join(result_lines)
    
    # 完美兼容百度的 baidu_raw 返回，使得 draw_baidu_marks_and_save 可以无缝工作
    return result_text, blocks_with_result, baidu_raw, None


def prepare_standard_answer_for_reference(standard_answer_path: str):
    """参照批改前预计算：对标准答案做一次 OCR 并生成各块 data URL。支持图片、PDF、Word。"""
    try:
        standard_answer_path, _ = ensure_image_path(standard_answer_path)
        std_blocks, std_img = run_ocr(standard_answer_path)
        full_std_url = _pil_image_to_data_url(std_img) if std_img else ""
        if not full_std_url and os.path.isfile(standard_answer_path):
            std_img = Image.open(standard_answer_path).convert("RGB")
            full_std_url = _pil_image_to_data_url(std_img)
        std_crop_urls = []
        std_bboxes = []
        if std_img and std_blocks:
            for sblk in std_blocks:
                x_min, y_min, x_max, y_max = sblk["bbox"]
                std_bboxes.append([x_min, y_min, x_max, y_max])
                crop = std_img.crop((
                    max(0, x_min - 2), max(0, y_min - 2),
                    min(std_img.width, x_max + 2), min(std_img.height, y_max + 2),
                ))
                std_crop_urls.append(_pil_image_to_data_url(crop))
        return {"full_std_url": full_std_url, "std_crop_urls": std_crop_urls, "std_bboxes": std_bboxes,
                "std_w": std_img.width if std_img else 0, "std_h": std_img.height if std_img else 0}
    except Exception:
        return None


def real_grade_pipeline_by_reference(standard_answer_path: str, student_image_path: str, precomputed_std: dict = None) -> tuple:
    """参照批改：以标准答案为参照对单张学生卷批改。返回 (result_text, blocks_with_result, original_img, None)。"""
    if precomputed_std and isinstance(precomputed_std, dict):
        full_std_url = precomputed_std.get("full_std_url")
        std_crop_urls = list(precomputed_std.get("std_crop_urls") or [])
        std_bboxes = list(precomputed_std.get("std_bboxes") or [])
        std_w = precomputed_std.get("std_w") or 1
        std_h = precomputed_std.get("std_h") or 1
        if not full_std_url and os.path.isfile(standard_answer_path):
            std_img = Image.open(standard_answer_path).convert("RGB")
            full_std_url = _pil_image_to_data_url(std_img)
    else:
        pre = prepare_standard_answer_for_reference(standard_answer_path)
        if not pre:
            return "标准答案预处理失败。", [], None, None
        full_std_url = pre["full_std_url"]
        std_crop_urls = list(pre.get("std_crop_urls") or [])
        std_bboxes = list(pre.get("std_bboxes") or [])
        std_w = pre.get("std_w") or 1
        std_h = pre.get("std_h") or 1

    student_image_path, _ = ensure_image_path(student_image_path)
    std_abs = os.path.abspath(standard_answer_path)
    std_abs_resolved = os.path.realpath(std_abs) if os.path.exists(std_abs) else std_abs
    student_abs = os.path.abspath(student_image_path)
    student_abs_resolved = os.path.realpath(student_abs) if os.path.exists(student_abs) else student_abs
    is_same_file = std_abs_resolved == student_abs_resolved

    blocks, original_img = run_ocr(student_image_path)
    if not blocks:
        return "未识别到任何文字块，请换图或检查 OCR 配置。", [], None, None
    stu_w, stu_h = original_img.width or 1, original_img.height or 1

    def _best_std_index_for_student(s_bbox):
        """按 bbox 中心位置匹配：学生块对应标准答案中位置最接近的块。"""
        if not std_bboxes:
            return 0
        sx = (s_bbox[0] + s_bbox[2]) / 2
        sy = (s_bbox[1] + s_bbox[3]) / 2
        snx, sny = sx / stu_w, sy / stu_h
        best_i, best_d = 0, float("inf")
        for i, stdb in enumerate(std_bboxes):
            tx = (stdb[0] + stdb[2]) / 2
            ty = (stdb[1] + stdb[3]) / 2
            tnx, tny = tx / std_w, ty / std_h
            d = (snx - tnx) ** 2 + (sny - tny) ** 2
            if d < best_d:
                best_d, best_i = d, i
        return best_i

    while len(std_crop_urls) < len(blocks):
        std_crop_urls.append(full_std_url)

    client = _get_openai_client()
    tasks = []
    for i, blk in enumerate(blocks):
        x_min, y_min, x_max, y_max = blk["bbox"]
        crop = original_img.crop((
            max(0, x_min - 2), max(0, y_min - 2),
            min(original_img.width, x_max + 2), min(original_img.height, y_max + 2),
        ))
        student_crop_url = _pil_image_to_data_url(crop)
        if is_same_file:
            std_url = student_crop_url
        elif std_bboxes and std_crop_urls:
            best_i = _best_std_index_for_student([x_min, y_min, x_max, y_max])
            std_url = std_crop_urls[min(best_i, len(std_crop_urls) - 1)]
        else:
            std_url = std_crop_urls[i] if i < len(std_crop_urls) else full_std_url
        tasks.append((blk, std_url, student_crop_url))

    def _task(item):
        blk, s_url, c_url = item
        return blk, _grade_one_block_reference(client, s_url, c_url, blk["index"])

    with ThreadPoolExecutor(max_workers=GRADE_MAX_WORKERS) as executor:
        results = list(executor.map(_task, tasks))
    for blk, res in results:
        blk["is_question"] = res["is_question"]
        blk["result"] = res["result"]
        blk["comment"] = res["comment"]
        blk["partial_ratio"] = res.get("partial_ratio")
    questions_text_parts = [
        f"第{blk['index']}题：result={blk['result']}, comment={blk['comment']}"
        for blk in blocks
        if blk.get("is_question") and (blk.get("result") or blk.get("comment"))
    ]
    questions_text = "\n".join(questions_text_parts)
    summary = _call_summary(client, questions_text)
    result_lines = [summary, "\n\n--- 逐题详情 ---\n"]
    for blk in blocks:
        if not blk.get("is_question"):
            continue
        result_lines.append(f"第{blk['index']}题：{_result_label(blk.get('result'), blk.get('partial_ratio'))} — {blk.get('comment', '')}")
    result_text = "\n".join(result_lines)
    return result_text, blocks, original_img, None
