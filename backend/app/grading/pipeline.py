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
from app.utils.qwen_settings import get_qwen_config, get_vl_model


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


def _thin_font_file_candidates() -> list:
    """细体字模候选（批注专用，同字号笔画更细）；都缺就回退常规。"""
    out: list[str] = []
    seen: set[str] = set()

    def _add(path: str) -> None:
        p = str(path or "").strip()
        if not p or p in seen:
            return
        seen.add(p)
        out.append(p)

    _add(os.environ.get("GRADING_FONT_THIN_PATH", "").strip())
    try:
        from app.grading.user_paths import project_root

        fonts_dir = project_root() / "assets" / "fonts"
        if fonts_dir.is_dir():
            for pattern in ("*Light*.ttf", "*Light*.ttc", "*Light*.otf", "*light*.ttf", "*Thin*.ttf", "*Thin*.ttc"):
                for fp in sorted(fonts_dir.glob(pattern)):
                    _add(str(fp))
    except Exception:
        pass
    if os.name == "nt":
        win_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        for name in ("msyhl.ttc",):
            _add(str(win_fonts / name))
    for path in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Light.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Light.ttc",
    ):
        _add(path)
    return out


def _load_note_font(size: int):
    """批注/旁批字体：优先 Light 细体（笔画细），无细体时回退常规并配收细渲染。

    返回 ``(font, thin_face)``；``thin_face=True`` 表示字模本身已细、直接画即可。
    """
    if ImageFont is None:
        return None, False
    for path in _thin_font_file_candidates():
        try:
            return ImageFont.truetype(path, size), True
        except Exception:
            continue
    return _load_cjk_font(size), False


def _draw_note_line(draw, x: int, y_base: int, text: str, font, fill: str, *, thin_face: bool) -> None:
    """批注一行（基线对齐 anchor=\"ls\"）。非细体字模用 3x 超采样+腐蚀收细笔画。"""
    if not text or font is None:
        return
    if thin_face or not getattr(font, "path", None):
        draw.text((x, y_base), text, fill=fill, font=font, anchor="ls")
        return
    try:
        from PIL import ImageFilter

        ascent, descent = font.getmetrics()
        pad = 4
        ss = 3
        tw = int(draw.textlength(text, font=font)) + pad * 2
        th = ascent + descent + pad * 2
        if tw <= pad * 2 or th <= pad * 2:
            draw.text((x, y_base), text, fill=fill, font=font, anchor="ls")
            return
        big_font = ImageFont.truetype(font.path, font.size * ss)
        mask = Image.new("L", (tw * ss, th * ss), 0)
        md = ImageDraw.Draw(mask)
        md.text((pad * ss, pad * ss), text, fill=255, font=big_font)
        mask = mask.filter(ImageFilter.MinFilter(3))  # 高清下收细一圈笔画
        mask = mask.resize((tw, th), Image.LANCZOS)
        draw.bitmap((x - pad, y_base - ascent - pad), mask, fill=fill)
    except Exception:
        draw.text((x, y_base), text, fill=fill, font=font, anchor="ls")


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


def _circle_center_in_bbox(bbox, img_w: int, img_h: int) -> tuple[int, int]:
    """未作答空心圆的圆心：作答区正中（2026-10-19 用户要求画在答题区内）。

    √/× 的右缘落点是给「有笔迹的答案」避让用的；空白圈画到右缘外会圈到
    题干上。空白区没有笔迹，圈正中不盖任何东西，也绝不会跑到框外的题干。
    """
    x1, y1, x2, y2 = (float(v) for v in bbox[:4])
    cx = int(round((x1 + x2) / 2))
    cy = int(round((y1 + y2) / 2))
    return max(0, min(cx, img_w - 1)), max(0, min(cy, img_h - 1))


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
    bbox: list | None = None,
) -> None:
    """在作答区旁绘制对错（√/×）；未作答画空心圆 ○；待确认不画任何标记。

    2026-10-16 用户要求：学生没填答案必须有标注（画圈），不能什么都不标；
    待确认是 AI 拿不准（交老师拍板），仍不画，免得被当成已判。
    2026-10-19：空心圆改画在 bbox 正中（答题区内）——沿用 √/× 的右缘落点
    会圈到题干上。bbox 缺失时退回原 check 落点。
    """
    result = str(item.get("result") or "")
    if result == "待确认":
        return
    glyph_size = max(36, int(font_size * max(0.75, min(1.0, check_cross_scale))))
    cx = check_x + int(glyph_size * 0.35)
    cy = check_y + int(glyph_size * 0.5)
    line_w = max(3, int(glyph_size * 0.09))

    # 0) 未作答：空心圆 ○ 画在作答区正中（答题区内，别圈到题干）
    if result == "未作答":
        box = bbox if isinstance(bbox, (list, tuple)) and len(bbox) == 4 else item.get("bbox")
        if isinstance(box, (list, tuple)) and len(box) == 4:
            try:
                cx, cy = _circle_center_in_bbox(box, 1 << 30, 1 << 30)
            except (TypeError, ValueError):
                pass
        _draw_vector_circle(draw, cx, cy, glyph_size, fill_color, line_w)
        return

    # 1) 对错符号：半对画半勾、对/错画 √/×
    if result == "半对":
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

【认读纪律——先认字，后判分】
1. 先逐字辨认学生手写笔迹，把读到的原文写进 "transcription"（只转写手写内容，不转写印刷体；看清的照写；看不清的单字用 [?] 占位；两种读法都像的写 [字1|字2]；整段认不出写 [??]）。transcription 会展示给老师，请忠实转写，不要润色、不要补全。
2. "read_confidence" 是你对「转写」本身的把握（不是对判分的）：全部看清填 0.9 以上；个别字含糊填 0.5~0.8；大片认不出填 0.4 以下。
3. 判分只能以 transcription 为依据，转写定下来之后再判 对/半对/错。
4. 转写里看不清的字**必须**标 [?] / [?? / [字1|字2]——宁可标出来也绝不许蒙认。判分时若认不清的字影响对错，你仍按最可能的情况给出判定，并在 comment 里写明哪部分认不清、你的判定依据；转写会被程序复核，蒙认会被拦下。
5. 字认得清、只是题意或上下文不足以判断对错时，按最可能的情况照常判 对/半对/错，并在 comment 里说明你的依据和保留。

只输出一个合法 JSON，不要 markdown 代码块或其它文字：
{{
  "is_question": true 或 false,
  "transcription": "学生手写笔迹的逐字转写（is_question 为 false 时留空）",
  "read_confidence": 0.0~1.0,
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

【认读纪律——先认字，后判分】
1. 先逐字辨认图2里学生手写笔迹，把读到的原文写进 "transcription"（只转写手写内容，不转写印刷体；看清的照写；看不清的单字用 [?] 占位；两种读法都像的写 [字1|字2]；整段认不出写 [??]）。transcription 会展示给老师，请忠实转写，不要润色、不要补全。
2. "read_confidence" 是你对「转写」本身的把握（不是对判分的）：全部看清填 0.9 以上；个别字含糊填 0.5~0.8；大片认不出填 0.4 以下。
3. 判分只能以 transcription 为依据与图1标准答案比对，转写定下来之后再判 对/半对/错。
4. 转写里看不清的字**必须**标 [?] / [?? / [字1|字2]——宁可标出来也绝不许蒙认。判分时若认不清的字影响对错，你仍按最可能的情况给出判定，并在 comment 里写明哪部分认不清、你的判定依据；转写会被程序复核，蒙认会被拦下。
5. 字认得清、只是题意或上下文不足以判断对错时，按最可能的情况照常判 对/半对/错，并在 comment 里说明你的依据和保留。

只输出一个合法 JSON，不要 markdown 或其它文字：
{{
  "is_question": true 或 false,
  "transcription": "图2 学生手写笔迹的逐字转写（is_question 为 false 时留空）",
  "read_confidence": 0.0~1.0,
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

【认读纪律——先认字，后判分】
1. 先逐字辨认图2里学生手写笔迹，把读到的原文写进 "transcription"（只转写手写内容，不转写印刷体；看清的照写；看不清的单字用 [?] 占位；两种读法都像的写 [字1|字2]；整段认不出写 [??]）。transcription 会展示给老师，请忠实转写，不要润色、不要补全。
2. "read_confidence" 是你对「转写」本身的把握（不是对判分的）：全部看清填 0.9 以上；个别字含糊填 0.5~0.8；大片认不出填 0.4 以下。
3. 判分只能以 transcription 为依据与图1标准答案比对，转写定下来之后再判 对/半对/错。
4. 转写里看不清的字**必须**标 [?] / [?? / [字1|字2]——宁可标出来也绝不许蒙认。判分时若认不清的字影响对错，你仍按最可能的情况给出判定，并在 comment 里写明哪部分认不清、你的判定依据；转写会被程序复核，蒙认会被拦下。
5. 字认得清、只是题意或上下文不足以判断对错时，按最可能的情况照常判 对/半对/错，并在 comment 里说明你的依据和保留。

只输出一个合法 JSON，不要 markdown 或其它文字：
{{
  "is_question": true 或 false,
  "transcription": "图2 学生手写笔迹的逐字转写（is_question 为 false 时留空）",
  "read_confidence": 0.0~1.0,
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
        return {"is_question": False, "result": "", "comment": "", "partial_ratio": None,
                "transcription": "", "read_confidence": None}
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
                        "transcription": str(d.get("transcription", "")).strip(),
                        "read_confidence": _coerce_partial_ratio(d.get("read_confidence")),
                    }
                except json.JSONDecodeError:
                    pass
                break
    return {"is_question": False, "result": "", "comment": "", "partial_ratio": None,
            "transcription": "", "read_confidence": None}


# 转写不确定标记：[?] / [?? / [字1|字2]
_UNCERTAIN_TRANSCRIPTION_RE = re.compile(r"\[\?|\[[^\]]*\|[^\]]*\]")


def _transcription_flagged(transcription: str) -> bool:
    return bool(_UNCERTAIN_TRANSCRIPTION_RE.search(str(transcription or "")))


def _apply_read_guard(res: dict) -> dict:
    """转写不确定/模型自报低置信 → 判「待确认」，不许蒙。

    判定权在代码不在模型：模型只负责转写+判定，一旦转写里有认不清标记
    （[?]/[??/[字|字]）或自报 read_confidence < 0.7，无论它判了什么，
    一律改判「待确认」——蒙错一个 ×（学生明明写了却被判错）比多一张
    「待确认」贵得多。模型自判「待确认」也保留（补标记、comment 带转写）。
    """
    if not res.get("is_question"):
        return res
    tr = str(res.get("transcription") or "")
    rc = res.get("read_confidence")
    try:
        rc_f = float(rc) if rc is not None else None
    except (TypeError, ValueError):
        rc_f = None
    flagged = _transcription_flagged(tr)
    uncertain = flagged or (rc_f is not None and rc_f < 0.7)
    if uncertain and str(res.get("result") or "") not in ("", "待确认"):
        res["result"] = "待确认"
    if str(res.get("result") or "") == "待确认":
        res["read_uncertain"] = True
        tr_show = tr[:80] + ("…" if len(tr) > 80 else "")
        # 认读问题说「识别不清」；模型因别的原因自判待确认则只说「待人工确认」
        prefix = "识别不清，待人工确认" if uncertain else "待人工确认"
        note = f"{prefix}（AI 读到：{tr_show or '无法辨认'}）"
        base = str(res.get("comment") or "").strip()
        if "待人工确认" not in base:
            res["comment"] = f"{note}；{base}" if base else note
    return res


def _enhance_crop_for_vl(pil_img):
    """喂 VL 前把裁剪块弄清楚：小图放大 + 自动对比度 + 轻锐化。

    潦草/浅淡笔迹靠这一步抬识别率；纯 Pillow 实现，不依赖外部超分模型。
    """
    if pil_img is None or Image is None:
        return pil_img
    try:
        from PIL import ImageFilter, ImageOps

        img = pil_img.convert("RGB")
        w, h = img.size
        if min(w, h) < 220 and min(w, h) > 0:
            scale = 220.0 / min(w, h)
            resample = getattr(Image, "Resampling", None)
            lanczos = resample.LANCZOS if resample else getattr(Image, "LANCZOS", 1)
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), lanczos)
        img = ImageOps.autocontrast(img, cutoff=1)
        img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=2))
        return img
    except Exception:
        return pil_img


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
            model=get_vl_model(),
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
        return _apply_read_guard(_parse_block_result(text))
    except Exception:
        return {"is_question": False, "result": "", "comment": ""}


def _grade_one_block_reference(client, standard_answer_data_url: str, student_crop_data_url: str, index: int) -> dict:
    prompt = PROMPT_BLOCK_REF.format(index=index)
    try:
        completion = client.chat.completions.create(
            model=get_vl_model(),
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
        return _apply_read_guard(_parse_block_result(text))
    except Exception:
        return {"is_question": False, "result": "", "comment": ""}


def _grade_one_block_smart_ref(client, standard_answer_data_url: str, student_crop_data_url: str, index: int, initial_result: dict, family_hint: str = "") -> dict:
    prompt = PROMPT_BLOCK_SMART_REF.format(index=index, initial_result=json.dumps(initial_result, ensure_ascii=False))
    if family_hint:
        prompt = f"{prompt}\n\n【科目族提示】{family_hint}"
    try:
        completion = client.chat.completions.create(
            model=get_vl_model(),
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
        return _apply_read_guard(_parse_block_result(text))
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
    # 无坐标的补块(bbox全0)不画，防止符号落到图片左上角
    if x2 <= x1 or y2 <= y1 or (x2 <= 0 and y2 <= 0):
        return
    size = max(30.0, min(80.0, image_width * 0.025))
    x = min(image_width - size, x2 - size * 0.25)
    y = min(image_height - size, max(y1, y2 - size))
    stroke_width = max(4, int(round(size * 0.08)))
    color = "#FF0000"
    result = str(item.get("result") or "")
    # 未作答画空心圆（2026-10-16：没填答案不能什么都不标）；待确认仍不画（交老师拍板）
    # 2026-10-19：圈画在答题区正中——右缘落点会圈到题干上
    if result == "未作答":
        cx, cy = _circle_center_in_bbox((x1, y1, x2, y2), image_width, image_height)
        _draw_vector_circle(
            draw,
            cx,
            cy,
            int(round(size)),
            color,
            stroke_width,
        )
        return
    if result == "待确认":
        return

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


def _mark_check_x(
    item: dict,
    x_min: int,
    x_max: int,
    font_size: int,
    check_cross_scale: float,
    margin_x: int,
    mark_right_shift: int,
    img_w: int,
    edge: int,
) -> int:
    """√/× 的横坐标。

    百度切出的作答区（slot）宽度适中（能容下符号又不至于盖住整块手写）时，
    把标记贴进作答框右缘**内侧**，让标记落在学生答案上；
    其余情况（题目级大块、数字小框、太宽的作答区）保持原来的右缘外侧，
    避免掉到右边邻近的题干印刷图形上。
    """
    glyph_w = max(36, int(font_size * max(0.75, min(1.0, check_cross_scale))))
    width = x_max - x_min
    if item.get("baidu_is_slot") and 2 * glyph_w <= width <= int(glyph_w * 3.5):
        return max(x_min, x_max - glyph_w)
    return min(x_max - margin_x + mark_right_shift, img_w - edge - int(font_size * 0.4))


def _mark_keepout_rects(blocks: list, w: int, h: int) -> list:
    """√/× 标记的禁占矩形（带余量），批注排版避让用。

    坐标复刻 draw_marks_only_and_save 的落点公式；scale 0.9/1.0 与 manual_style
    两种画法取并集，宁多勿漏——批注宁可往下让，也不能压在留痕符号上。
    """
    rects: list = []
    font_size, _offsets, margin_x, _margin_y = _adaptive_mark_params(w, h)
    edge = max(40, int(60 * font_size / 52))
    mark_right_shift = max(0, int(os.environ.get("MARK_RIGHT_SHIFT_PX", "28")))
    manual_size = max(30.0, min(80.0, w * 0.025))
    for item in blocks or []:
        if not isinstance(item, dict) or not item.get("is_question"):
            continue
        # 待确认不画标记故不占位；未作答画 ○ 也是标记，批注要避让
        if str(item.get("result") or "") == "待确认":
            continue
        bbox = item.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        try:
            x_min, y_min, x_max, y_max = (int(float(v)) for v in bbox[:4])
        except (TypeError, ValueError):
            continue
        if x_max <= x_min or y_max <= y_min or (x_max <= 0 and y_max <= 0):
            continue
        if str(item.get("result") or "") == "未作答":
            # 空心圆画在作答区正中（2026-10-19）：占位跟着挪到框内正中
            ccx, ccy = _circle_center_in_bbox((x_min, y_min, x_max, y_max), w, h)
            radii = [max(8, int(max(36, int(font_size * max(0.75, min(1.0, scale)))) * 0.30)) for scale in (0.9, 1.0)]
            radii.append(max(8, int(manual_size * 0.30)))
            for radius in radii:
                rects.append((ccx - radius - 8, ccy - radius - 8, ccx + radius + 8, ccy + radius + 8))
            continue
        for scale in (0.9, 1.0):
            glyph = max(36, int(font_size * max(0.75, min(1.0, scale))))
            cx = _mark_check_x(
                item, x_min, x_max, font_size, scale, margin_x, mark_right_shift, w, edge
            )
            cy = int((y_min + y_max) / 2 - font_size * 0.5)
            cy = max(0, min(cy, h - font_size - 2))
            rects.append((cx - 8, cy - 8, cx + glyph + 8, cy + glyph + 8))
        mx = min(w - manual_size, x_max - manual_size * 0.25)
        my = min(h - manual_size, max(y_min, y_max - manual_size))
        rects.append((mx - 8, my - 8, mx + manual_size + 8, my + manual_size + 8))
    return rects


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
        # 补块(supplemented)等无坐标的题 bbox=[0,0,0,0]：跳过不画，
        # 否则对错符号会落在图片左上角(0,0)——每张卷都会多出一个孤立的×
        if x_max <= x_min or y_max <= y_min or (x_max <= 0 and y_max <= 0):
            continue
        center_y = (y_min + y_max) / 2
        check_x = _mark_check_x(item, x_min, x_max, font_size, check_cross_scale, margin_x, mark_right_shift, w, edge)
        check_y = int(center_y - font_size * 0.5)
        check_y = max(0, min(check_y, h - font_size - 2))
        _draw_result_mark(
            draw, check_x, check_y, font_size, item, mark_font,
            outline_color, fill_color, offsets, check_cross_scale=check_cross_scale,
            bbox=bbox,
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
        # 同 draw_real_marks_and_save：无坐标的补块不画，避免×落在图片左上角
        if x_max <= x_min or y_max <= y_min or (x_max <= 0 and y_max <= 0):
            continue
        center_y = (y_min + y_max) / 2
        check_x = _mark_check_x(item, x_min, x_max, font_size, check_cross_scale, margin_x, mark_right_shift, w, edge)
        check_y = int(center_y - font_size * 0.5)
        check_y = max(0, min(check_y, h - font_size - 2))
        _draw_result_mark(
            draw, check_x, check_y, font_size, item, mark_font,
            outline_color, fill_color, offsets, check_cross_scale=check_cross_scale,
            bbox=bbox,
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

    note_font, note_thin = _load_note_font(max(28, int(min(img_w, img_h) * 0.016)))
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
            _draw_note_line(draw, x, ty, ln, note_font, "#d62727", thin_face=note_thin)
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


def draw_wrong_annotations_variant(
    marks_only_path: str,
    out_path: str,
    blocks: list,
    wrong_annotations,
    question_notes=None,
    paper_note: str = "",
    *,
    paper_mode: bool = False,
) -> bool:
    """从留痕图生成「带错因批注」变体：错因（大红 #e60000）+同题老师批注（红 #d62727）。

    落点规则（2026-10-16 定，用户要求「批注在这道题目的右下角」）：
    ① 首选**本题自己的题框右下角**——红笔旁批风格，右齐题框右缘、贴题框底，
    只用「本题作答区底沿以下」的框内空带；可压本题印刷内容（不加白底），
    但不得压任何作答区/√×留痕/别题框。放不下按 1.0/0.85/0.7 缩字。
    ② 次选作答区正下方（字顶过块底与题框底，2026-10-12「不得压印刷题干」）；
    ⛔ 不许「锚太靠右就飞整页左边距」——双页拼版会把右半页批注压到左半页题干标题上。
    ③ 都落不下沉到画布底白带，加「第N题」前缀；画布不够高向下加高白边。

    paper_mode=True（卷面底图，屏幕预览用）：白块会盖掉学生字迹，因此只在该题
    已烧进老师批注时才盖字重排；老师批注原位不动就不重画；整卷总评位置没变就不动。
    """
    wrong_annotations = wrong_annotations if isinstance(wrong_annotations, dict) else {}
    question_notes = question_notes if isinstance(question_notes, dict) else {}
    paper_note = str(paper_note or "").strip()
    if not wrong_annotations or not os.path.isfile(marks_only_path):
        return False
    try:
        from PIL import Image, ImageDraw

        img = Image.open(marks_only_path).convert("RGB")
    except Exception:
        return False
    img_w, img_h = img.size
    orig_h = img_h

    note_font, note_thin = _load_note_font(max(28, int(min(img_w, img_h) * 0.016)))
    if note_font is None:
        return False
    try:
        char_w = max(12, ImageDraw.Draw(img).textlength("中", font=note_font))
    except Exception:
        char_w = note_font.size
    margin = max(24, int(img_w * 0.03))
    full_chars = max(6, int((img_w - margin * 2) / char_w))
    line_h = int(note_font.size * 1.4)

    def _wrap_plain(text: str, max_chars: int) -> list:
        lines: list = []
        for seg in str(text or "").split("\n"):
            seg = seg.rstrip()
            while len(seg) > max_chars:
                lines.append(seg[:max_chars])
                seg = seg[max_chars:]
            if seg:
                lines.append(seg)
        return lines

    # 行首禁则：收尾标点不打头，挤回上一行行尾（与旧烧录 wrap 的区别只在标点处）
    def _wrap(text: str, max_chars: int) -> list:
        lines = _wrap_plain(text, max_chars)
        for i in range(1, len(lines)):
            while lines[i] and lines[i][0] in "！？：；。，、）】》」』〉…%,.!?;:" and lines[i - 1]:
                lines[i - 1] += lines[i][0]
                lines[i] = lines[i][1:]
        return lines

    # 按题聚合锚点（同 draw_manual_annotations：取该题最靠下的作答区 bbox）
    # 题号 key 与 wrong_annotations 存储键一致（question_key_of：index → label 数字前缀 → slot_id）
    # 遮挡禁区=所有作答区+所有题框：批注一律不得压印刷题干/作答内容。⛔ 不许「锚太靠右
    # 就飞整页左边距」——双页拼版会把右半页的错因压到左半页题干标题上（用户投诉：那是题干）。
    from app.grading.wrong_annotations import question_key_of

    anchors: dict[str, tuple[int, int, int]] = {}  # key -> (x_min, y_max, 题框底)
    own_qboxes: dict[str, set[tuple[int, int, int, int]]] = {}
    own_ans_bottom: dict[str, int] = {}
    blocked: list[tuple[int, int, int, int]] = []
    for blk in blocks or []:
        if not isinstance(blk, dict):
            continue
        key = question_key_of(blk)
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
        blocked.append((x_min, y_min, x_max, y_max))
        if y_max > own_ans_bottom.get(key, 0):
            own_ans_bottom[key] = y_max
        q_bottom = y_max
        qb = blk.get("baidu_question_bbox")
        if isinstance(qb, (list, tuple)) and len(qb) == 4:
            try:
                qx1, qy1, qx2, qy2 = (int(float(v)) for v in qb[:4])
                if qx2 > qx1 and qy2 > qy1:
                    blocked.append((qx1, qy1, qx2, qy2))
                    q_bottom = max(q_bottom, qy2)
                    own_qboxes.setdefault(key, set()).add((qx1, qy1, qx2, qy2))
            except (TypeError, ValueError):
                pass
        cur = anchors.get(key)
        if cur is None or y_max > cur[1]:
            anchors[key] = (max(margin, min(x_min, img_w - margin)), y_max, q_bottom)

    # √/× 墨迹在作答区右缘外侧（bbox 不含），并入禁区：批注不压留痕符号
    blocked.extend(_mark_keepout_rects(blocks, img_w, orig_h))

    def _lookup(mapping: dict, key: str):
        val = mapping.get(key)
        if val is None:
            try:
                val = mapping.get(int(key))
            except (TypeError, ValueError):
                val = None
        return val

    global_bottom = max((a[1] for a in anchors.values()), default=0)
    excl_bottom = max((b[3] for b in blocked), default=0)
    font_size = int(note_font.size)

    # ---- 排版：批注在本列换行；落点不得压任何块/题框，落不下就沉到画布底白带 ----
    entries: list = []
    for key, (x, y_max, q_bottom) in sorted(anchors.items(), key=lambda kv: kv[1][1]):
        w_entry = _lookup(wrong_annotations, key)
        wrong_text = str((w_entry or {}).get("text") if isinstance(w_entry, dict) else w_entry or "").strip()
        note_text = str(_lookup(question_notes, key) or "").strip()
        if not wrong_text and not note_text:
            continue
        cover_x = x
        avail = img_w - margin - x
        if avail < char_w * 6:
            # 极靠右：只许向左让出最小行宽，⛔ 不飞整页左边距（双页拼版会压别题题干）
            x = max(margin, min(x, img_w - margin - int(char_w * 6)))
            avail = img_w - margin - x
        max_chars_x = max(6, int(avail / char_w))
        qbox_set = own_qboxes.get(key) or set()
        own_box = None
        if qbox_set:
            own_box = (
                min(b[0] for b in qbox_set),
                min(b[1] for b in qbox_set),
                max(b[2] for b in qbox_set),
                max(b[3] for b in qbox_set),
            )
        entries.append({
            "key": key,
            "x": x,
            "cover_x": cover_x,
            "old_y": y_max + int(line_h * 0.4),
            "block_y": y_max,
            "q_bottom": q_bottom,
            "wrong_raw": wrong_text,
            "note_raw": note_text,
            "own_qbox": own_box,
            "own_rects": qbox_set,
            "own_ans_bottom": own_ans_bottom.get(key, 0),
            "max_chars_x": max_chars_x,
            "wrong": _wrap(wrong_text, max_chars_x) if wrong_text else [],
            "note": _wrap(note_text, max_chars_x) if note_text else [],
            "old_note": _wrap(note_text, full_chars) if note_text else [],
        })

    placed: list[tuple[int, int, int, int]] = []
    in_place: list[tuple[int, int, int, int]] = []

    def _hits(rect: tuple[int, int, int, int], extra: list | None = None) -> bool:
        rx1, ry1, rx2, ry2 = rect
        for bx1, by1, bx2, by2 in blocked + in_place + (extra or []):
            if rx1 < bx2 and rx2 > bx1 and ry1 < by2 and ry2 > by1:
                return True
        return False

    def _measure(e: dict) -> tuple[int, int]:
        n_lines = len(e["wrong"]) + len(e["note"])
        text_h = max(1, n_lines) * line_h + int(line_h * 0.3)
        text_w = max((len(ln) for ln in (e["wrong"] + e["note"])), default=6) * char_w
        return text_h, text_w

    sink: list = []

    def _hits_corner(rect: tuple[int, int, int, int], own_rects: set) -> bool:
        """候选A 遮挡检查：本题自己的题框可压（红笔旁批），其余禁区照旧。"""
        rx1, ry1, rx2, ry2 = rect
        for bx1, by1, bx2, by2 in blocked:
            if own_rects and (bx1, by1, bx2, by2) in own_rects:
                continue
            if rx1 < bx2 and rx2 > bx1 and ry1 < by2 and ry2 > by1:
                return True
        for bx1, by1, bx2, by2 in in_place:
            if rx1 < bx2 and rx2 > bx1 and ry1 < by2 and ry2 > by1:
                return True
        return False

    def _place_in_question_corner(e: dict) -> bool:
        """候选A（2026-10-16 用户要求）：写进本题题框右下角的空带。

        只用「本题作答区底沿 → 题框底」的框内底带，右齐题框右缘、贴框底起排；
        压到作答区/留痕/别题框就贴带上移，放不下按 1.0/0.85/0.7 缩字再试。
        成功改写 e 的行集/字体/落点，失败原样返回 False 交下级联。
        """
        own = e.get("own_qbox")
        if not own:
            return False
        qx1, qy1, qx2, qy2 = own
        band_floor = max(qy1, int(e.get("own_ans_bottom") or 0))
        if qy2 - band_floor < 16:
            return False
        for scale in (1.0, 0.85, 0.7):
            f_size = max(12, int(font_size * scale))
            if scale == 1.0:
                s_font, s_thin = note_font, note_thin
            else:
                s_font, s_thin = _load_note_font(f_size)
            if s_font is None:
                continue
            try:
                s_char_w = max(10, ImageDraw.Draw(img).textlength("中", font=s_font))
            except Exception:
                s_char_w = max(10, int(getattr(s_font, "size", f_size)))
            s_size = int(getattr(s_font, "size", f_size))
            s_line_h = int(s_size * 1.4)
            pad = max(6, int(s_char_w * 0.5))
            wrap_chars = max(4, int((qx2 - qx1 - pad * 2) / s_char_w))
            wrong_lines = _wrap(e["wrong_raw"], wrap_chars) if e["wrong_raw"] else []
            note_lines = _wrap(e["note_raw"], wrap_chars) if e["note_raw"] else []
            n_lines = len(wrong_lines) + len(note_lines)
            if not n_lines:
                return False
            text_h = n_lines * s_line_h + int(s_line_h * 0.3)
            text_w = max((len(ln) for ln in (wrong_lines + note_lines)), default=4) * s_char_w
            text_w = min(text_w, max(1, qx2 - qx1 - pad * 2))
            top = qy2 - pad - text_h
            guard = 0
            while guard < 40:
                if top < band_floor:
                    break
                rect = (qx2 - pad - text_w, top, qx2 - pad, top + text_h)
                if not _hits_corner(rect, e["own_rects"]):
                    e["rect"] = rect
                    e["x"] = rect[0]
                    e["y"] = top + s_size  # 首行基线（anchor="ls"）
                    e["h"] = text_h
                    e["wrong"] = wrong_lines
                    e["note"] = note_lines
                    e["font"] = s_font
                    e["thin"] = s_thin
                    e["line_h"] = s_line_h
                    in_place.append(rect)
                    return True
                top -= int(s_line_h * 0.9)
                guard += 1
        return False

    # 阶段0：题框右下角（用户要求「批注在这道题目的右下角」）
    # 阶段1：能原位就原位——作答区正下方（字顶过块底与题框底），不压内容、不压已就位批注
    for e in entries:
        if _place_in_question_corner(e):
            continue
        text_h, text_w = _measure(e)
        top = max(e["block_y"], e["q_bottom"]) + int(font_size * 0.35)
        rect = (e["x"], top, min(img_w - 2, e["x"] + text_w), top + text_h)
        if _hits(rect):
            sink.append(e)
            continue
        e["rect"] = rect
        e["y"] = top + font_size  # 首行基线（anchor="ls"）
        e["h"] = text_h
        in_place.append(rect)
    # 阶段2：挤不下的沉到画布底白带，加「第N题」前缀（离题远也能对上号），彼此错开
    for e in sink:
        if e["wrong_raw"] and str(e["key"]).isdigit():
            e["wrong"] = _wrap(f"第{e['key']}题 {e['wrong_raw']}", e["max_chars_x"])
        text_h, text_w = _measure(e)
        top = excl_bottom + int(line_h * 0.3)
        rect = (e["x"], top, min(img_w - 2, e["x"] + text_w), top + text_h)
        guard = 0
        while _hits(rect, placed) and guard < 40:
            top += line_h
            rect = (e["x"], top, min(img_w - 2, e["x"] + text_w), top + text_h)
            guard += 1
        e["rect"] = rect
        e["y"] = top + font_size
        e["h"] = text_h
        placed.append(rect)

    for e in entries:
        # 试卷底图上老师批注原位不动（同位重画=叠同样的字）
        if paper_mode and not e["wrong"] and abs(e["rect"][1] - (e["old_y"] - font_size)) <= int(line_h * 0.5):
            if e["old_y"] + len(e["old_note"]) * line_h <= orig_h - int(line_h * 0.2):
                e["draw"] = False
                continue
        e["draw"] = True

    prev_bottom = max((e["rect"][3] for e in entries), default=0)

    # 整卷总评：新位置=新栈底；旧位置按烧录公式（含原图贴底钳制）算出后盖掉
    paper_lines = _wrap(paper_note, full_chars) if paper_note else []
    move_paper = False
    old_paper_y = new_paper_y = 0
    if paper_note:
        old_notes_bottom = 0
        for e in entries:
            if e["old_note"]:
                old_notes_bottom = max(
                    old_notes_bottom, e["old_y"] + len(e["old_note"]) * line_h
                )
        old_paper_y = max(global_bottom + int(line_h * 0.8), old_notes_bottom + int(line_h * 0.4))
        if old_paper_y + line_h > orig_h:
            old_paper_y = max(margin, orig_h - len(paper_lines) * line_h - int(line_h * 0.4))
        new_paper_y = max(global_bottom + int(line_h * 0.8), prev_bottom + int(line_h * 0.4))
        # 试卷底上总评位置没变就不动（同位重画=叠同样的字），免得平白多一条白底
        move_paper = (not paper_mode) or abs(new_paper_y - old_paper_y) >= int(line_h * 0.5)
        required_bottom = new_paper_y + len(paper_lines) * line_h + int(line_h * 0.4)
    else:
        required_bottom = prev_bottom + int(line_h * 0.4)

    # 画布按内容高度向下加高白边：批注按字数完整留痕，不允许贴底截半
    if required_bottom > orig_h:
        img_h = int(required_bottom + line_h * 0.2)
        grown = Image.new("RGB", (img_w, img_h), "#ffffff")
        grown.paste(img, (0, 0))
        img = grown
    draw = ImageDraw.Draw(img)

    # 先盖旧（全部盖完再画新字，防止后盖的白块削掉先画的批注尾巴）
    if move_paper:
        draw.rectangle(
            [margin - 4, old_paper_y - int(line_h * 0.7), img_w - margin,
             min(orig_h, old_paper_y + len(paper_lines) * line_h + int(line_h * 0.3))],
            fill="#ffffff",
        )
    for e in entries:
        if not e["note"] or not e["draw"]:
            continue
        draw.rectangle(
            [e["cover_x"] - 4, e["old_y"] - int(line_h * 0.7), img_w - margin,
             min(orig_h, e["old_y"] + len(e["old_note"]) * line_h + int(line_h * 0.3))],
            fill="#ffffff",
        )

    # 再画新：错因（大红 #e60000）→ 老师批注（红 #d62727）→ 整卷总评
    for e in entries:
        if not e["draw"]:
            continue
        e_font = e.get("font") or note_font
        e_thin = e.get("thin") if e.get("thin") is not None else note_thin
        e_lh = int(e.get("line_h") or line_h)
        ty = e["y"]
        for ln in e["wrong"]:
            _draw_note_line(draw, e["x"], ty, ln, e_font, "#e60000", thin_face=e_thin)
            ty += e_lh
        for ln in e["note"]:
            _draw_note_line(draw, e["x"], ty, ln, e_font, "#d62727", thin_face=e_thin)
            ty += e_lh
    if move_paper:
        ty = new_paper_y
        for ln in paper_lines:
            _draw_note_line(draw, margin, ty, ln, note_font, "#d62727", thin_face=note_thin)
            ty += line_h

    try:
        img.save(out_path, quality=95)
        return True
    except Exception:
        return False


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
        crop_url = _pil_image_to_data_url(_enhance_crop_for_vl(crop))
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
        if res.get("transcription"):
            blk["transcription"] = res["transcription"]
        if res.get("read_uncertain"):
            blk["read_uncertain"] = True
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


def real_grade_pipeline_smart_ref(standard_answer_path: str, student_image_path: str, precomputed_std: dict = None, stop_event=None, family_hint: str = "") -> tuple:
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
            student_crop_url = _pil_image_to_data_url(_enhance_crop_for_vl(crop))
            
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
        final_result = _grade_one_block_smart_ref(client, s_url, c_url, blk["index"], initial_result, family_hint=family_hint)
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
            if res.get("transcription"):
                blk["transcription"] = res["transcription"]
            if res.get("read_uncertain"):
                blk["read_uncertain"] = True
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
        student_crop_url = _pil_image_to_data_url(_enhance_crop_for_vl(crop))
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
        if res.get("transcription"):
            blk["transcription"] = res["transcription"]
        if res.get("read_uncertain"):
            blk["read_uncertain"] = True
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
