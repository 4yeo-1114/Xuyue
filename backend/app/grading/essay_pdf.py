# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import unicodedata
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import unquote

import fitz  # PyMuPDF
from PIL import Image

from app.grading.essay_text_layout import fix_punctuation_line_starts


@dataclass
class EssayPdfItem:
    name: str
    result: str = ""
    ocr_title: str = ""
    ocr_content: str = ""
    # 「留痕/原卷」图片直链（带短时下载票）。下载图片版 PDF 时用，报告版不需要。
    image_original: Optional[str] = None
    image_annotated: Optional[str] = None
    image_marks_only: Optional[str] = None


def _wrap_text(text: str) -> str:
    # 统一换行，避免插入 textbox 时出现奇怪的回车
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _usable_cn_font_file(path: str | None) -> str | None:
    """字体文件可用性检查：真实存在、可读且非空；否则返回 None。"""
    p = str(path or "").strip()
    if not p:
        return None
    try:
        if os.path.isfile(p) and os.access(p, os.R_OK) and os.path.getsize(p) > 0:
            return p
    except OSError:
        return None
    return None


def _cn_font_candidates():
    """按优先级产出可用中文字体文件路径（fallback 链）。

    顺序：GRADING_FONT_PATH 环境变量 → cjk_font.py 缓存的 wqy-zenhei
    → 项目 assets/fonts → Windows 常见中文字体 → Linux 常见中文字体。
    """
    # 1) 显式指定的字体路径（最高优先级）
    hit = _usable_cn_font_file(os.environ.get("GRADING_FONT_PATH", "").strip())
    if hit:
        yield hit

    # 2) cjk_font.py 缓存/下载的 bundled 字体（> 1MB 防止半截下载文件）
    try:
        from app.grading.cjk_font import bundled_cjk_font_path

        bundled = bundled_cjk_font_path()
        if (
            bundled.is_file()
            and bundled.stat().st_size > 1_000_000
            and os.access(str(bundled), os.R_OK)
        ):
            yield str(bundled)
    except Exception:
        pass

    # 3) 项目 assets/fonts 目录内的任意字体文件
    try:
        from app.grading.user_paths import project_root

        fonts_dir = project_root() / "assets" / "fonts"
        if fonts_dir.is_dir():
            for pattern in ("*.ttc", "*.ttf", "*.otf"):
                for fp in sorted(fonts_dir.glob(pattern)):
                    hit = _usable_cn_font_file(str(fp))
                    if hit:
                        yield hit
    except Exception:
        pass

    # 4) Windows 常见中文字体
    if os.name == "nt":
        win_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        for name in ("msyh.ttf", "msyh.ttc", "simsun.ttc", "simhei.ttf", "simkai.ttf", "simfang.ttf"):
            hit = _usable_cn_font_file(str(win_fonts / name))
            if hit:
                yield hit

    # 5) Linux 常见中文字体
    for path in (
        "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ):
        hit = _usable_cn_font_file(path)
        if hit:
            yield hit


def _pick_cn_fontfile() -> str | None:
    """选择 PDF 嵌入用的中文字体文件（Windows / Linux / 项目 assets/fonts）。

    沿 fallback 链返回首个可用字体文件；全部不可用时返回 None（由调用方兜底）。
    """
    for candidate in _cn_font_candidates():
        return candidate
    return None


import re
import datetime

def _insert_text(page: fitz.Page, pos, text: str, fontsize: float, fontname: str, fontfile: str | None, color=(0,0,0)):
    kwargs = {"fontsize": fontsize, "fontname": fontname, "color": color}
    if fontfile:
        kwargs["fontfile"] = fontfile
    page.insert_text(pos, text, **kwargs)


def _report_name_from_filename(name: str) -> str:
    stem = Path(str(name or "").strip()).stem.strip() or "未命名"
    # 去除类似于 "_2" 的后缀
    m = re.match(r"^(.*?)_\d+$", stem)
    if m:
        stem = m.group(1)
    return f"{stem}作文批改报告"


def _display_units(text: str) -> float:
    """显示宽度折算：全角（CJK/全角标点）按 1 个字宽，半角按 0.5 个字宽。

    11.11-7：英语作文正文是半角字，按「字数」硬裁会挤成半宽窄栏、右边大片空白。
    """
    units = 0.0
    for ch in text:
        units += 1.0 if unicodedata.east_asian_width(ch) in ("F", "W") else 0.5
    return units


# 拉丁词尽量整体成词、空白单独成 token、其余（CJK/标点）逐字
_MIXED_WRAP_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-]*|\s+|.", re.S)


def _wrap_mixed_line(text: str, width: float) -> list[str]:
    """按显示宽度贪心折行（width 为全角字宽预算）：拉丁词不拆词，CJK 逐字断。"""
    lines: list[str] = []
    cur = ""
    cur_units = 0.0
    for tok in _MIXED_WRAP_TOKEN_RE.findall(text):
        tok_units = _display_units(tok)
        if cur and cur_units + tok_units > width:
            lines.append(cur)
            cur = ""
            cur_units = 0.0
        if not cur:
            # 续行行首丢掉折叠点空白；段首行（还没产生行）保留原有缩进
            if lines and tok.isspace():
                continue
            if tok_units > width:
                # 超宽词（长 URL 等）硬拆，宁可断词也不越出右缘
                chunk = ""
                for ch in tok:
                    if chunk and _display_units(chunk + ch) > width:
                        lines.append(chunk)
                        chunk = ""
                    chunk += ch
                cur = chunk
                cur_units = _display_units(chunk)
                continue
        cur += tok
        cur_units += tok_units
    if cur or not lines:
        lines.append(cur)
    return lines


def _split_body_lines(text: str, width: int) -> list[str]:
    lines: list[str] = []
    for para in (text or "").splitlines():
        p = para.rstrip()
        if not p:
            lines.append("")
            continue
        wrapped = _wrap_mixed_line(p, width=width)
        wrapped = fix_punctuation_line_starts(wrapped or [p])
        lines.extend(wrapped)
    return lines or ["（暂无批改结果）"]


def _compact_body_text(text: str) -> str:
    """压缩过密空行，保留原有板块结构。"""
    raw = _wrap_text(text)
    while "\n\n\n" in raw:
        raw = raw.replace("\n\n\n", "\n\n")
    return raw or "（暂无批改结果）"


def _chars_per_line(usable_width: float, fontsize: float) -> int:
    # CJK 字体大致接近方块字；中文字符宽度大约等于字体大小。
    # 使用 1.05 的系数作为安全余量，避免任何一行文字溢出右侧。
    # 返回值是「全角字宽预算」：半角字符按 0.5 折算（见 _display_units），
    # 英语正文一行约 90 个字母也能排满整幅宽，不再挤半宽窄栏（11.11-7）。
    return max(34, int(usable_width / max(1.0, fontsize * 1.05)))


def _ensure_page_font(page: fitz.Page, fontname: str, fontfile: str | None) -> tuple[str, str | None]:
    """把中文字体挂到页面上；失败时沿 fallback 链逐个尝试，极端情况才退回默认字体。"""
    # 首选：直接嵌入调用方传入的字体文件（成功路径与历史行为完全一致）
    if fontfile:
        try:
            page.insert_font(fontname=fontname, fontfile=fontfile)
            return fontname, fontfile
        except Exception:
            pass
    else:
        # 无字体文件（内置 "china-s" 路径）：现场找回一个真实字体文件，
        # 例如下载刚完成、或上一页构造时字体暂不可用。
        picked = _pick_cn_fontfile()
        if picked:
            try:
                page.insert_font(fontname="essay_cn", fontfile=picked)
                return "essay_cn", picked
            except Exception:
                pass
        return fontname, None

    # 传入字体不可用：沿 fallback 链尝试其余候选（跳过已失败的 fontfile）
    seen = {fontfile}
    for candidate in _cn_font_candidates():
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            page.insert_font(fontname="essay_cn", fontfile=candidate)
            return "essay_cn", candidate
        except Exception:
            continue

    # 兜底：所有候选都不可用，退回默认字体（宁可显示异常也不让 PDF 生成崩）
    return "helv", None


def _prepare_essay_pdf_text(text: str) -> str:
    """PDF 正文预处理：去掉评分标签、误带的「总览」行等。"""
    from app.grading.essay_grading import normalize_essay_result_text

    raw = normalize_essay_result_text(text or "")
    raw = re.sub(r"<essay_score>[\s\S]*?</essay_score>", "", raw, flags=re.I).strip()
    raw = re.sub(r"^总览\s*\n+", "", raw, flags=re.M)
    raw = re.sub(r"[０-９]", lambda x: chr(ord(x.group(0)) - 65248), raw)
    raw = raw.replace("．", ".")
    raw = re.sub(r"(?m)^(\d+)\.\s+", r"\1. ", raw)
    # 得分块后减少多余空行；各报告板块标题前收紧空行
    raw = re.sub(
        r"(【作文得分】\s*\n)[\s\u3000]*([^\n]+)",
        lambda m: f"{m.group(1)}{m.group(2).strip()}",
        raw,
    )
    raw = re.sub(r"(【作文得分】\s*\n[^\n]+分)\n{3,}", r"\1\n\n", raw)
    raw = re.sub(r"\n+(?=【)", "\n", raw)
    return _compact_body_text(raw)


def build_essay_report_pdf_bytes(
    *,
    folder_name: str,
    items: List[EssayPdfItem],
    duplex_double: bool = False,
    duplex_binding: str = "long",
) -> bytes:
    """
    生成作文批改报告 PDF。
    注意：此 PDF 仅包含「AI 批改评语」的排版输出，不包含试卷图片与 OCR 原文。
    PDF 只负责 A4 固定字号排版，不截断正文、不动态缩小文字；单页长度由作文批改 prompt 控制。
    duplex_double（11.13 台账 #1/#2）：双面合印时每个学生的报告独占整张纸——
    页数为奇数时补一张空白背页，避免两个学生拼在一张纸上。
    duplex_binding="short"：短边翻页（像台历）——每对页的第 1 张（驱动首面）转 180°，
    打印窗口的翻页方式保持默认「沿长边」即可。
    """
    # A4 portrait in points (72dpi): 595 x 842
    page_w, page_h = 595, 842
    margin = 40  # 增加页边距，让排版更美观，且绝对不溢出
    header_h = 34

    doc = fitz.open()
    cn_font = _pick_cn_fontfile()
    if not cn_font:
        # 自动下载失败/被禁用时 graceful 处理：不中断 PDF 生成，回退到系统字体或内置兜底
        try:
            from app.grading.cjk_font import ensure_cjk_font_file

            cn_font = ensure_cjk_font_file() or _pick_cn_fontfile()
        except Exception:
            pass
    if cn_font:
        fontname = "essay_cn"
    else:
        fontname = "china-s"

    for it in items:
        report_name = _report_name_from_filename(it.name)
        body_text = _prepare_essay_pdf_text(it.result or "")

        item_start_page = doc.page_count
        page = doc.new_page(width=page_w, height=page_h)
        current_font, current_fontfile = _ensure_page_font(page, fontname, cn_font)

        usable_width = page_w - margin * 2
        body_top = margin + header_h + 16
        body_bottom = page_h - margin
        body_fontsize = 10.5  # 整体字体调小
        line_h = body_fontsize * 1.5
        body_lines = _split_body_lines(body_text, width=_chars_per_line(usable_width, body_fontsize))

        title_fontsize = 20.0
        if len(report_name) > 20:
            title_fontsize = 16.0
        if len(report_name) > 30:
            title_fontsize = 14.0

        _insert_text(page, (margin, margin + 22), report_name, title_fontsize, current_font, current_fontfile)

        # 显示批改时间
        time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        _insert_text(page, (page_w - margin - 120, margin + 22), f"批改时间：{time_str}", 10.0, current_font, current_fontfile, color=(0.4, 0.4, 0.4))

        try:
            page.draw_line(
                fitz.Point(margin, margin + header_h),
                fitz.Point(page_w - margin, margin + header_h),
                color=(0.72, 0.78, 0.86),
                width=0.7,
            )
        except Exception:
            pass

        y = body_top + body_fontsize
        line_index = 0
        while line_index < len(body_lines):
            if y > body_bottom - 40: # 留出底部空间显示总分
                page = doc.new_page(width=page_w, height=page_h)
                current_font, current_fontfile = _ensure_page_font(page, fontname, cn_font)
                _insert_text(page, (margin, margin + 22), f"{report_name}（续）", title_fontsize, current_font, current_fontfile)
                try:
                    page.draw_line(
                        fitz.Point(margin, margin + header_h),
                        fitz.Point(page_w - margin, margin + header_h),
                        color=(0.72, 0.78, 0.86),
                        width=0.7,
                    )
                except Exception:
                    pass
                y = body_top + body_fontsize

            line_text = body_lines[line_index]

            if not line_text.strip():
                y += line_h * 0.35
                line_index += 1
                continue

            if line_text.strip() == "【作文得分】":
                _insert_text(page, (margin, y), line_text, body_fontsize, current_font, current_fontfile)
                y += line_h * 0.75
                line_index += 1
                continue

            # 作文得分数字：1.6 倍字号标红，略向下偏移，左缘与标题【对齐
            if line_text.strip().endswith("分") and line_index > 0 and body_lines[line_index - 1].strip() == "【作文得分】":
                y += body_fontsize * 0.45
                score_fontsize = body_fontsize * 1.6
                score_line = line_text.strip().lstrip("\u3000")
                score_x = margin - body_fontsize * 0.22
                _insert_text(page, (score_x, y), score_line, score_fontsize, current_font, current_fontfile, color=(0.9, 0.1, 0.1))
                y += line_h * 1.05
                line_index += 1
                continue

            # 如果这一行是标题（例如 【xxx】），在上方添加一条分割线
            if re.match(r"^【.*】", line_text.strip()):
                if y > body_top + body_fontsize: # 不在第一行画
                    y += 2
                    try:
                        page.draw_line(
                            fitz.Point(margin, y - body_fontsize),
                            fitz.Point(page_w - margin, y - body_fontsize),
                            color=(0.9, 0.9, 0.9),
                            width=0.5,
                        )
                    except Exception:
                        pass
                    y += 4
            
            _insert_text(page, (margin, y), line_text, body_fontsize, current_font, current_fontfile)
            y += line_h
            line_index += 1
            
        # (已按要求移除 PDF 右下角的总分单独绘制逻辑，现在总分会作为文本里的【作文得分】一块自然排版)

        # 双面合印：学生报告页数为奇数时补一张空白背页，保证独占整张纸
        if duplex_double and (doc.page_count - item_start_page) % 2 == 1:
            doc.new_page(width=page_w, height=page_h)

    # 短边翻页：每对页的第 1 张（驱动首面，翻面后读到的那页）转 180°。
    # 只转完整对；末尾落单页（单页报告）不转（单面打印时它就是正面）。
    if duplex_binding == "short":
        for i in range(0, doc.page_count - 1, 2):
            doc[i].set_rotation(180)

    try:
        return doc.tobytes(garbage=4, deflate=True)
    except Exception:
        return doc.tobytes()


# ---------------------------------------------------------------- 图片版 PDF

def _filename_from_image_url(url: str) -> str:
    """从 /api/v1/grading/modify/xxx.jpg?ticket=... 取出文件名（去掉票据与编码）。"""
    if not url or not isinstance(url, str):
        return ""
    base = url.split("?", 1)[0]
    name = base.rsplit("/", 1)[-1]
    return unquote(name).strip()


def _fit_page_size(w: int, h: int, max_pt: float = 1684.0) -> tuple:
    """按图片比例算 PDF 页尺寸（pt）。超大图等比缩到 max_pt 以内。"""
    scale = min(1.0, max_pt / max(w, h)) if max(w, h) > 0 else 1.0
    return max(1.0, w * scale), max(1.0, h * scale)


# 试卷抬头（校徽 + 校名）遮盖区域，按图片宽高比例：(left, top, right, bottom)。
# 右边界取 0.35 是留足余量又不碰到中间那行「第 X 单元作文」。
HEADER_MASK_RATIO = (0.0, 0.0, 0.35, 0.05)


def _has_school_header(name: str) -> bool:
    """该页顶部是否有校徽抬头。

    作文纸只有每个学生的**第 1 页**印了校徽/校名；第 2 页起顶部直接是作文正文，
    盖上白块会把学生的字涂掉，所以只有第 1 页才遮。
    """
    m = re.search(r"_(\d+)\.[^.]+$", str(name or ""))
    if not m:
        return True  # 没有 _页码 后缀，当单页处理
    return m.group(1) == "1"


def build_essay_images_pdf_bytes(
    *,
    modify_dir: Path,
    items: List[EssayPdfItem],
    include_original: bool = True,
    include_annotated: bool = True,
    mask_header: bool = True,
) -> bytes:
    """把作文的「原卷 + 留痕」图片拼成 PDF：每张图一页，页尺寸贴合图片本身。

    与 build_essay_report_pdf_bytes 的区别：这里不做文字排版，只还原预览里
    看到的那几张图，供老师直接下载/打印。
    mask_header=True 时把左上角的校徽/校名用白块盖掉（对外展示时不露学校标识）。
    """
    doc = fitz.open()
    for it in items:
        wanted = []
        if include_original:
            wanted.append(it.image_original)
        if include_annotated:
            wanted.append(it.image_annotated)
        for url in wanted:
            name = _filename_from_image_url(url or "")
            if not name:
                continue
            path = modify_dir / name
            if not path.is_file():
                continue
            try:
                with Image.open(path) as im:
                    w, h = im.size
            except Exception:
                continue
            pw, ph = _fit_page_size(w, h)
            page = doc.new_page(width=pw, height=ph)
            try:
                page.insert_image(fitz.Rect(0, 0, pw, ph), filename=str(path))
            except Exception:
                continue
            if mask_header and _has_school_header(name):
                try:
                    mx0, my0, mx1, my1 = HEADER_MASK_RATIO
                    page.draw_rect(
                        fitz.Rect(pw * mx0, ph * my0, pw * mx1, ph * my1),
                        color=(1, 1, 1),
                        fill=(1, 1, 1),
                    )
                except Exception:
                    pass

    if doc.page_count == 0:
        raise RuntimeError("没有可用的留痕/原卷图片")
    try:
        return doc.tobytes(garbage=4, deflate=True)
    except Exception:
        return doc.tobytes()

