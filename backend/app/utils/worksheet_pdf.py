# -*- coding: utf-8 -*-
"""作业纸 PDF 生成。

用途：小程序里布置作业后，生成一张可直接打印下发的作业纸（A4）。
特点：不落库、不留痕，纯排版输出，返回 PDF 字节。

支持两种题目来源：
1. **手写题目**：老师在小程序里敲题，或只给题量生成空白答题纸；
2. **上传题目**：
   - 图片（拍照/截图）—— 等比缩放后逐张排到卷头下方，放不下自动翻页；
   - PDF —— 原样插入（保持原版式，适合现成试卷）；
   - Word / 文本 —— 提取文字后重新排版。

中文字体策略与 app/services/portfolio/pdf.py 一致：
Windows 系统字体优先（宋体/黑体），服务器上回退 wqy-zenhei，最后回退内置 CID 字体。
"""
from __future__ import annotations

import io
import os
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Iterable, Optional, Sequence

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    FrameBreak,
    KeepTogether,
    NextPageTemplate,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ─── 字体 ────────────────────────────────────────────────────────────────
# 形如 (注册名, 文件路径)。按顺序尝试，第一个可用的生效。
_TITLE_FONT_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("XyHei", r"C:\Windows\Fonts\simhei.ttf"),        # 黑体（Windows）
    ("XyHei", r"C:\Windows\Fonts\msyhbd.ttc"),        # 微软雅黑粗体（Windows）
    ("XyHei", r"/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc"),  # 文泉驿正黑（Linux）
)
_BODY_FONT_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("XySong", r"C:\Windows\Fonts\simsun.ttc"),       # 宋体（Windows）
    ("XySong", r"C:\Windows\Fonts\msyh.ttc"),         # 微软雅黑（Windows）
    ("XySong", r"/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc"),  # 文泉驿正黑（Linux）
)

_FALLBACK_FONT = "STSong-Light"  # reportlab 内置 CID 中文字体
_RESOLVED: dict[str, str] = {}


def _register_ttf(name: str, path: str) -> bool:
    """注册单个字体文件；.ttc 需要指定 subfontIndex。"""
    try:
        if path.lower().endswith(".ttc"):
            try:
                pdfmetrics.registerFont(TTFont(name, path, subfontIndex=0))
            except TypeError:
                # 老版本 reportlab 不支持 subfontIndex，退化为整包注册
                pdfmetrics.registerFont(TTFont(name, path))
        else:
            pdfmetrics.registerFont(TTFont(name, path))
        return True
    except Exception:
        return False


def _resolve_font(candidates: Sequence[tuple[str, str]], cache_key: str) -> str:
    """按候选顺序挑第一个可注册的字体，返回注册名。"""
    cached = _RESOLVED.get(cache_key)
    if cached:
        return cached

    for name, path in candidates:
        if not os.path.exists(path):
            continue
        if _register_ttf(name, path):
            _RESOLVED[cache_key] = name
            return name

    # 尝试项目内自动下载的文泉驿字体（服务器场景）
    try:
        from app.grading.cjk_font import ensure_cjk_font_file

        downloaded = ensure_cjk_font_file()
        if downloaded and _register_ttf("XyWQY", downloaded):
            _RESOLVED[cache_key] = "XyWQY"
            return "XyWQY"
    except Exception:
        pass

    # 最后回退 reportlab 内置 CID 字体
    try:
        if _FALLBACK_FONT not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(UnicodeCIDFont(_FALLBACK_FONT))
    except Exception:
        pass
    _RESOLVED[cache_key] = _FALLBACK_FONT
    return _FALLBACK_FONT


def title_font() -> str:
    return _resolve_font(_TITLE_FONT_CANDIDATES, "title")


def body_font() -> str:
    return _resolve_font(_BODY_FONT_CANDIDATES, "body")


# ─── 文案映射 ────────────────────────────────────────────────────────────
SUBJECT_LABELS = {
    "chinese": "语文",
    "math": "数学",
    "english": "英语",
    "physics": "物理",
    "chemistry": "化学",
    "biology": "生物",
    "politics": "道德与法治",
    "history": "历史",
    "geography": "地理",
    "science": "科学",
    "it": "信息技术",
}

GRADE_LABELS = {
    "grade1": "一年级",
    "grade2": "二年级",
    "grade3": "三年级",
    "grade4": "四年级",
    "grade5": "五年级",
    "grade6": "六年级",
    "junior1": "七年级",
    "junior2": "八年级",
    "junior3": "九年级",
    "senior1": "高一",
    "senior2": "高二",
    "senior3": "高三",
}


def subject_label(value: Optional[str]) -> str:
    if not value:
        return ""
    return SUBJECT_LABELS.get(value, str(value))


def grade_label(value: Optional[str]) -> str:
    if not value:
        return ""
    return GRADE_LABELS.get(value, str(value))


# ─── 页面尺寸 ────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class PageSpec:
    """一种纸张规格：页面尺寸 + 页边距 + 默认分栏数。

    大纸（A3 / 8 开）默认双栏 —— 这是国内试卷的标准样式（对折成两半，
    正好一栏一半），也让字号和行距在视觉上保持和 A4 一致的密度，
    而不是把 A4 的内容原样丢到一张大纸上、下面留一大片空白。
    """

    key: str
    label: str
    width: float
    height: float
    margin_x: float = 2.0 * cm
    margin_top: float = 1.8 * cm
    margin_bottom: float = 1.8 * cm
    columns: int = 1
    column_gap: float = 1.2 * cm

    @property
    def frame_w(self) -> float:
        """正文可用总宽度（所有栏加起来）。"""
        return self.width - 2 * self.margin_x

    @property
    def usable_h(self) -> float:
        """正文可用高度。"""
        return self.height - self.margin_top - self.margin_bottom

    @property
    def column_w(self) -> float:
        """单栏宽度。"""
        n = max(1, self.columns)
        return (self.frame_w - self.column_gap * (n - 1)) / n


# 支持打印的纸张。16 开 / 8 开是国内学校印试卷最常用的两种。
_PAGE_SPECS: dict[str, PageSpec] = {
    "a4": PageSpec("a4", "A4（210×297mm）", *A4),
    "a3": PageSpec("a3", "A3（297×420mm）", 297 * mm, 420 * mm, columns=2),
    "b5": PageSpec(
        "b5", "B5（176×250mm）", 176 * mm, 250 * mm,
        margin_x=1.5 * cm, margin_top=1.5 * cm, margin_bottom=1.5 * cm,
    ),
    "16k": PageSpec(
        "16k", "16开（185×260mm）", 185 * mm, 260 * mm,
        margin_x=1.5 * cm, margin_top=1.5 * cm, margin_bottom=1.5 * cm,
    ),
    "8k": PageSpec("8k", "8开（260×370mm）", 260 * mm, 370 * mm, columns=2),
    "letter": PageSpec("letter", "Letter（216×279mm）", *letter),
}

DEFAULT_PAGE_SIZE = "a4"

# 排版方式：auto = 按纸张默认（大纸双栏）；single / double 强制单栏 / 双栏
_LAYOUT_MODES = ("auto", "single", "double")

# 单栏最小宽度（pt）。双栏时每栏低于这个宽度就不给分栏了。
MIN_COLUMN_W = 200.0


def apply_layout(spec: PageSpec, layout: Optional[str]) -> PageSpec:
    """按老师选的排版方式，覆盖纸张的默认分栏数。"""
    mode = str(layout or "auto").strip().lower()
    if mode not in _LAYOUT_MODES:
        mode = "auto"
    if mode == "single" and spec.columns != 1:
        return replace(spec, columns=1)
    if mode == "double" and spec.columns != 2:
        # 每栏至少 200pt（约 7cm）才像样，太窄的双栏排出来没法看
        if spec.frame_w >= 2 * MIN_COLUMN_W + spec.column_gap:
            return replace(spec, columns=2)
    return spec


def resolve_page_spec(key: Optional[str]) -> PageSpec:
    """把纸张代码解析成 PageSpec；不认识的一律回退 A4。"""
    if not key:
        return _PAGE_SPECS[DEFAULT_PAGE_SIZE]
    return _PAGE_SPECS.get(str(key).strip().lower(), _PAGE_SPECS[DEFAULT_PAGE_SIZE])


def page_spec_label(key: Optional[str]) -> str:
    """纸张代码 → 中文名，如 a4 → 「A4（210×297mm）」。"""
    return resolve_page_spec(key).label


def available_page_sizes() -> list[dict]:
    """供前端下拉用的纸张列表。"""
    return [{"value": s.key, "label": s.label} for s in _PAGE_SPECS.values()]

_ANSWER_LINE_COLOR = colors.HexColor("#C9CDD4")
_RULE_COLOR = colors.HexColor("#333333")

# 上传内容里两张图片之间的垂直间距
_UPLOAD_GAP = 10.0

# 支持的图片扩展名
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tif", ".tiff")


def _escape(text: str) -> str:
    """转义 reportlab 段落标记字符。"""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _body_style(size: float, leading: Optional[float] = None) -> ParagraphStyle:
    return ParagraphStyle(
        f"XyBody{size}",
        fontName=body_font(),
        fontSize=size,
        leading=leading or size * 1.6,
        textColor=colors.black,
        alignment=TA_LEFT,
    )


def _answer_lines(count: int, width: float, gap: float = 0.78 * cm):
    """生成 count 条答题横线（用表格底线绘制）。"""
    rows = [[Paragraph("&nbsp;", _body_style(9))] for _ in range(count)]
    return Table(
        rows,
        colWidths=[width],
        rowHeights=[gap] * count,
        style=TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 0.6, _ANSWER_LINE_COLOR),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        ),
    )


# ─── 卷头（标题 + 信息栏 + 提示）────────────────────────────────────────
def _header_flowables(
    *,
    title: str,
    subject: str,
    grade: str,
    class_name: str,
    teacher: str,
    note: str,
    count_text: str = "",
    spec: Optional[PageSpec] = None,
) -> list:
    """卷头部分的 flowable 列表，供「手写题目」和「上传题目」两种模式共用。"""
    subj = subject_label(subject)
    grd = grade_label(grade)
    if not title:
        title = f"{grd}{subj}作业".strip() or "作业"

    spec = spec or _PAGE_SPECS[DEFAULT_PAGE_SIZE]
    frame_w = spec.frame_w

    story = []

    story.append(
        Paragraph(
            _escape(title),
            ParagraphStyle(
                "XyTitle",
                fontName=title_font(),
                fontSize=20,
                leading=26,
                alignment=TA_CENTER,
                textColor=colors.black,
                spaceAfter=4,
            ),
        )
    )

    meta_bits = [b for b in (grd, subj) if b]
    if count_text:
        meta_bits.append(count_text)
    meta_bits.append(datetime.now().strftime("%Y 年 %m 月 %d 日"))
    story.append(
        Paragraph(
            _escape("　".join(meta_bits)),
            ParagraphStyle(
                "XyMeta",
                fontName=body_font(),
                fontSize=9.5,
                leading=14,
                alignment=TA_CENTER,
                textColor=colors.HexColor("#6B7280"),
                spaceAfter=6,
            ),
        )
    )

    info_cells = [
        f"班级：{_escape(class_name)}" if class_name else "班级：____________",
        "姓名：____________",
        "学号：__________",
    ]
    story.append(
        Table(
            [[Paragraph(c, _body_style(10.5)) for c in info_cells]],
            colWidths=[frame_w / len(info_cells)] * len(info_cells),
            style=TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            ),
        )
    )

    if teacher:
        story.append(
            Paragraph(
                f"布置老师：{_escape(teacher)}",
                ParagraphStyle(
                    "XyTeacher",
                    fontName=body_font(),
                    fontSize=9.5,
                    leading=14,
                    textColor=colors.HexColor("#6B7280"),
                    spaceAfter=4,
                ),
            )
        )

    story.append(Spacer(1, 2))
    story.append(
        Table(
            [[""]],
            colWidths=[frame_w],
            rowHeights=[1],
            style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1.1, _RULE_COLOR)]),
        )
    )
    story.append(Spacer(1, 8))

    if note:
        story.append(
            Paragraph(
                _escape(note),
                ParagraphStyle(
                    "XyNote",
                    fontName=body_font(),
                    fontSize=10,
                    leading=15,
                    textColor=colors.HexColor("#374151"),
                    spaceAfter=8,
                ),
            )
        )

    return story


def _measure_height(flowables: Sequence, width: float) -> float:
    """预估一组 flowable 排下来有多高（宽度给定）。

    必须把 spaceBefore / spaceAfter 算进去 —— reportlab 的 Frame 是「段落高度 +
    段前距 + 段后距」一起占位的，只累加 wrap() 的高度会偏小，导致卷头框装不下、
    内容溢出到下一栏（表现为左栏空着、正文全跑到右栏）。
    """
    height = 0.0
    for f in flowables:
        try:
            _, fh = f.wrap(width, 10000)
            height += float(fh)
        except Exception:
            height += 20.0
        for attr in ("getSpaceBefore", "getSpaceAfter"):
            fn = getattr(f, attr, None)
            if callable(fn):
                try:
                    height += float(fn() or 0)
                except Exception:
                    pass
    return height


def _column_frames(spec: PageSpec, top: float) -> list:
    """在 top 高度之下，横向排 spec.columns 个等宽栏。"""
    n = max(1, spec.columns)
    col_w = spec.column_w
    h = top - spec.margin_bottom
    frames = []
    for i in range(n):
        x = spec.margin_x + i * (col_w + spec.column_gap)
        frames.append(
            Frame(
                x,
                spec.margin_bottom,
                col_w,
                h,
                id=f"col{i}",
                leftPadding=0,
                rightPadding=0,
                topPadding=0,
                bottomPadding=0,
            )
        )
    return frames


def _make_doc(
    buf: io.BytesIO,
    footer_text: str,
    spec: Optional[PageSpec] = None,
    header_flowables: Optional[Sequence] = None,
):
    """建文档模板，返回 (doc, story_prefix)。

    单栏：整页一个框，卷头直接排在正文前面。
    多栏：卷头单独占首页顶部整宽，正文从下面的左右两栏开始流；
          第二页起用「只有两栏」的模板。
    """
    spec = spec or _PAGE_SPECS[DEFAULT_PAGE_SIZE]

    doc = BaseDocTemplate(
        buf,
        pagesize=(spec.width, spec.height),
        leftMargin=spec.margin_x,
        rightMargin=spec.margin_x,
        topMargin=spec.margin_top,
        bottomMargin=spec.margin_bottom,
        title=footer_text or "作业纸",
        author="叙阅",
    )

    def _draw_page(canvas, _doc):
        canvas.saveState()
        canvas.setFont(body_font(), 8)
        canvas.setFillColor(colors.HexColor("#8A8F99"))
        canvas.drawString(
            spec.margin_x, spec.margin_bottom - 0.5 * cm, footer_text or "叙阅"
        )
        canvas.drawRightString(
            spec.width - spec.margin_x,
            spec.margin_bottom - 0.5 * cm,
            f"第 {canvas.getPageNumber()} 页",
        )
        canvas.restoreState()

    top = spec.height - spec.margin_top

    # ── 单栏 ──
    if spec.columns <= 1:
        frame = Frame(
            spec.margin_x,
            spec.margin_bottom,
            spec.frame_w,
            spec.usable_h,
            id="body",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_draw_page)])
        return doc, list(header_flowables or [])

    # ── 多栏 ──
    body_frames = _column_frames(spec, top)

    if not header_flowables:
        doc.addPageTemplates(
            [PageTemplate(id="cols", frames=body_frames, onPage=_draw_page)]
        )
        return doc, []

    # 多留 6pt 余量，避免测量与实际渲染的细微出入把卷头顶出框外
    hdr_h = _measure_height(header_flowables, spec.frame_w) + 6
    hdr_h = min(hdr_h, spec.usable_h * 0.5)  # 卷头最多占半页，别把正文挤没
    hdr_frame = Frame(
        spec.margin_x,
        top - hdr_h,
        spec.frame_w,
        hdr_h,
        id="header",
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    first_frames = [hdr_frame] + _column_frames(spec, top - hdr_h - 6)

    doc.addPageTemplates(
        [
            PageTemplate(id="first", frames=first_frames, onPage=_draw_page),
            PageTemplate(id="cols", frames=body_frames, onPage=_draw_page),
        ]
    )
    # 卷头进整宽框 → NextPageTemplate 让第 2 页起只用两栏 → FrameBreak 把正文推进左栏
    prefix = list(header_flowables) + [NextPageTemplate("cols"), FrameBreak()]
    return doc, prefix


# ══════════════════════════════════════════════════════════════════════════
#  模式一：手写题目 / 空白答题纸
# ══════════════════════════════════════════════════════════════════════════
def _text_worksheet_pdf(
    *,
    title: str = "",
    subject: str = "",
    grade: str = "",
    class_name: str = "",
    teacher: str = "",
    questions: Optional[Iterable[str]] = None,
    question_count: Optional[int] = None,
    answer_lines: int = 2,
    note: str = "",
    spec: Optional[PageSpec] = None,
) -> bytes:
    spec = spec or _PAGE_SPECS[DEFAULT_PAGE_SIZE]
    subj = subject_label(subject)
    grd = grade_label(grade)
    if not title:
        title = f"{grd}{subj}作业".strip() or "作业"

    q_list = [str(q).strip() for q in (questions or []) if str(q).strip()]
    if not q_list:
        n = max(1, min(int(question_count or 0), 60))
        q_list = [""] * n

    lines_per_q = max(0, min(int(answer_lines or 0), 10))

    buf = io.BytesIO()
    header = _header_flowables(
        title=title,
        subject=subject,
        grade=grade,
        class_name=class_name,
        teacher=teacher,
        note=note,
        count_text=f"共 {len(q_list)} 题",
        spec=spec,
    )
    doc, story = _make_doc(buf, f"叙阅 · {title}", spec, header_flowables=header)

    for idx, q_text in enumerate(q_list, start=1):
        block = [
            Paragraph(
                f"{idx}. {_escape(q_text)}" if q_text else f"{idx}.",
                ParagraphStyle(
                    "XyQ",
                    fontName=body_font(),
                    fontSize=12,
                    leading=19,
                    spaceAfter=4,
                ),
            )
        ]
        if lines_per_q:
            block.append(_answer_lines(lines_per_q, spec.column_w))
        block.append(Spacer(1, 8))
        story.append(KeepTogether(block))

    doc.build(story)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════
#  模式二：上传题目（图片 / PDF / Word / 文本）
# ══════════════════════════════════════════════════════════════════════════
def detect_kind(filename: str, content_type: str = "") -> str:
    """按文件名后缀判断上传类型，返回 image / pdf / docx / text / unknown。"""
    name = (filename or "").lower()
    if name.endswith(_IMAGE_EXTS):
        return "image"
    if name.endswith(".pdf"):
        return "pdf"
    if name.endswith(".docx"):
        return "docx"
    if name.endswith((".txt", ".md", ".csv")):
        return "text"
    if name.endswith(".doc"):
        # 老的 .doc 二进制格式解析不了，提示用户转一下
        return "doc_legacy"

    ct = (content_type or "").lower()
    if ct.startswith("image/"):
        return "image"
    if "pdf" in ct:
        return "pdf"
    if "word" in ct or "officedocument" in ct:
        return "docx"
    if ct.startswith("text/"):
        return "text"
    return "unknown"


def _normalize_image(data: bytes, max_width: int = 1800) -> tuple[bytes, int, int]:
    """手机拍的照片可能很大、还带 EXIF 旋转。统一摆正、缩小，返回 (字节, 宽, 高)。

    输出 JPEG（无透明通道）或 PNG（有透明通道），这两种 fitz 都能直接嵌。
    """
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)  # 按 EXIF 摆正

    if img.width > max_width:
        ratio = max_width / float(img.width)
        img = img.resize(
            (max_width, max(1, int(img.height * ratio))), Image.Resampling.LANCZOS
        )

    out = io.BytesIO()
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        img.save(out, format="PNG", optimize=True)
    else:
        img.convert("RGB").save(out, format="JPEG", quality=88, optimize=True)

    return out.getvalue(), img.width, img.height


def _docx_text(data: bytes) -> str:
    """提取 Word 正文（段落 + 表格文字）。"""
    from docx import Document

    doc = Document(io.BytesIO(data))
    lines = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]

    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                lines.append("　".join(cells))

    return "\n".join(lines)


def _text_to_pdf(
    text: str, title: str, footnote: str = "", spec: Optional[PageSpec] = None
) -> bytes:
    """把纯文本排成整页（自动分页）。"""
    spec = spec or _PAGE_SPECS[DEFAULT_PAGE_SIZE]
    buf = io.BytesIO()
    doc, story = _make_doc(buf, f"叙阅 · {title}", spec)

    if footnote:
        story.append(
            Paragraph(
                _escape(footnote),
                ParagraphStyle(
                    "XyUpNote",
                    fontName=body_font(),
                    fontSize=9.5,
                    leading=15,
                    textColor=colors.HexColor("#6B7280"),
                    spaceAfter=10,
                ),
            )
        )

    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            story.append(Spacer(1, 6))
            continue
        story.append(
            Paragraph(
                _escape(line),
                ParagraphStyle(
                    "XyUpText",
                    fontName=body_font(),
                    fontSize=11.5,
                    leading=20,
                    spaceAfter=2,
                ),
            )
        )

    if not story:
        story.append(Paragraph("（文件内容为空）", _body_style(11)))

    doc.build(story)
    return buf.getvalue()


def _header_pdf(flowables: list, spec: Optional[PageSpec] = None) -> bytes:
    """把卷头渲染成一张「刚好包住内容」的窄页 PDF，便于贴到大页顶部。"""
    spec = spec or _PAGE_SPECS[DEFAULT_PAGE_SIZE]

    height = 0.0
    for f in flowables:
        try:
            _, fh = f.wrap(spec.frame_w, 10000)
            height += float(fh)
        except Exception:
            height += 20.0

    page_h = spec.margin_top + height + 6
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=(spec.width, page_h),
        leftMargin=spec.margin_x,
        rightMargin=spec.margin_x,
        topMargin=spec.margin_top,
        bottomMargin=0,
    )
    doc.build(flowables)
    return buf.getvalue()


def _uploads_worksheet_pdf(
    *,
    title: str,
    subject: str,
    grade: str,
    class_name: str,
    teacher: str,
    note: str,
    uploads: Sequence[dict],
    extra_answer_lines: int = 0,
    spec: Optional[PageSpec] = None,
) -> bytes:
    """卷头 + 上传内容（图片流式排版，PDF 整页插入，Word/文本重排）。"""
    import fitz

    spec = spec or _PAGE_SPECS[DEFAULT_PAGE_SIZE]

    subj = subject_label(subject)
    grd = grade_label(grade)
    if not title:
        title = f"{grd}{subj}作业".strip() or "作业"

    header = _header_flowables(
        title=title,
        subject=subject,
        grade=grade,
        class_name=class_name,
        teacher=teacher,
        note=note,
        count_text=f"共 {len(uploads)} 份材料" if uploads else "",
        spec=spec,
    )

    out = fitz.open()
    page = out.new_page(width=spec.width, height=spec.height)

    # ── 贴卷头 ──
    hdr_bytes = _header_pdf(header, spec)
    hdr = fitz.open("pdf", hdr_bytes)
    hdr_h = hdr[0].rect.height
    page.show_pdf_page(fitz.Rect(0, 0, spec.width, hdr_h), hdr, 0)

    y = hdr_h + _UPLOAD_GAP
    max_y = spec.height - spec.margin_bottom
    usable_w = spec.frame_w
    usable_h = max_y - spec.margin_top

    def _new_page():
        return out.new_page(width=spec.width, height=spec.height)

    for up in uploads:
        kind = up.get("kind")
        data = up.get("data") or b""
        name = up.get("name") or "材料"

        if kind == "image":
            # 上传时若已摆正/压缩过（带 width/height），这里直接复用，避免二次重编码
            if up.get("width") and up.get("height"):
                img_bytes, iw, ih = data, int(up["width"]), int(up["height"])
            else:
                img_bytes, iw, ih = _normalize_image(data)
            w = float(usable_w)
            h = ih * (w / float(iw))
            if h > usable_h:  # 单张图比整页还高 → 缩到页高
                h = float(usable_h)
                w = iw * (h / float(ih))

            if y + h > max_y:  # 本页放不下 → 翻页
                page = _new_page()
                y = spec.margin_top

            page.insert_image(
                fitz.Rect(spec.margin_x, y, spec.margin_x + w, y + h), stream=img_bytes
            )
            y += h + _UPLOAD_GAP

        elif kind == "pdf":
            src = fitz.open("pdf", data)
            # insert_pdf 追加在末尾；此刻之前的页面都是本任务已排好的，顺序天然正确
            out.insert_pdf(src)
            src.close()
            page = _new_page()
            y = spec.margin_top

        else:  # docx / text
            if kind == "docx":
                try:
                    text = _docx_text(data)
                except Exception as exc:  # noqa: BLE001
                    text = f"（Word 文件解析失败：{exc}）"
            else:
                text = data.decode("utf-8", errors="replace")

            text_pdf = _text_to_pdf(text, title, footnote=f"—— {name} ——", spec=spec)
            src = fitz.open("pdf", text_pdf)
            out.insert_pdf(src)
            src.close()
            page = _new_page()
            y = spec.margin_top

    # ── 需要的话，在最后补答题横线 ──
    if extra_answer_lines > 0:
        lines_pdf = _answer_lines_pdf(extra_answer_lines, spec)
        src = fitz.open("pdf", lines_pdf)
        out.insert_pdf(src)
        src.close()

    result = out.tobytes()
    out.close()
    return result


def _answer_lines_pdf(count: int, spec: Optional[PageSpec] = None) -> bytes:
    """生成若干页答题横线（上传内容之后追加用）。"""
    spec = spec or _PAGE_SPECS[DEFAULT_PAGE_SIZE]
    buf = io.BytesIO()
    doc, story = _make_doc(buf, "叙阅 · 答题区", spec)
    story.extend([
        Paragraph(
            "答题区",
            ParagraphStyle(
                "XyAnsTitle",
                fontName=title_font(),
                fontSize=14,
                leading=20,
                spaceAfter=10,
            ),
        )
    ])
    for _ in range(max(1, min(int(count), 200))):
        story.append(_answer_lines(1, spec.column_w, gap=1.1 * cm))
        story.append(Spacer(1, 4))
    doc.build(story)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════
#  模式三：AI 生成 / 结构化题目
# ══════════════════════════════════════════════════════════════════════════
# 题型 → 默认答题横线数（老师可在小程序里整体覆盖）
_ANSWER_LINES_BY_TYPE = {
    "choice": 0,        # 选择题：勾选项即可，不留线
    "judge": 0,         # 判断题
    "fill": 1,          # 填空题
    "cloze": 0,         # 完形填空：空在文内
    "short_answer": 3,  # 简答
    "essay": 8,         # 作文/论述
    "calculation": 4,   # 计算
    "application": 4,   # 应用/解答
    "reading": 3,       # 阅读理解
    "matching": 2,      # 连线
    "ordering": 1,      # 排序
}
_OPTION_LABELS = "ABCDEFGH"

QUESTION_TYPE_LABELS = {
    "choice": "选择题",
    "fill": "填空题",
    "judge": "判断题",
    "short_answer": "简答题",
    "essay": "作文题",
    "matching": "连线题",
    "ordering": "排序题",
    "reading": "阅读理解",
    "cloze": "完形填空",
    "calculation": "计算题",
    "application": "解答题",
}


def _question_flowables(
    idx: int,
    q: dict,
    *,
    default_lines: Optional[int] = None,
    show_score: bool = True,
    spec: Optional[PageSpec] = None,
) -> list:
    """把一道结构化题目（AI 生成或老师手编）渲染成 flowable 列表。"""
    spec = spec or _PAGE_SPECS[DEFAULT_PAGE_SIZE]
    qtype = str(q.get("type") or "short_answer").strip().lower()
    stem = str(q.get("stem") or "").strip()
    content = str(q.get("content") or "").strip()
    options = [str(o).strip() for o in (q.get("options") or []) if str(o).strip()]
    subs = [str(s).strip() for s in (q.get("subQuestions") or []) if str(s).strip()]

    try:
        score = float(q.get("score") or 0)
    except (TypeError, ValueError):
        score = 0.0

    head = f"{idx}."
    if show_score and score:
        head += f"（{score:g} 分）"

    blocks: list = []

    # 背景材料（阅读理解的原文放这里）
    if stem:
        blocks.append(
            Paragraph(
                _escape(stem),
                ParagraphStyle(
                    "XyQStem",
                    fontName=body_font(),
                    fontSize=10.5,
                    leading=18,
                    textColor=colors.HexColor("#374151"),
                    leftIndent=12,
                    spaceAfter=6,
                ),
            )
        )

    # 题目内容
    blocks.append(
        Paragraph(
            f"{head} {_escape(content)}" if content else head,
            ParagraphStyle(
                "XyQItem", fontName=body_font(), fontSize=12, leading=19, spaceAfter=4
            ),
        )
    )

    # 选项（选择题 / 连线题左列 / 排序题乱序项）
    for i, opt in enumerate(options):
        label = _OPTION_LABELS[i] if i < len(_OPTION_LABELS) else str(i + 1)
        blocks.append(
            Paragraph(
                f"　　{label}. {_escape(opt)}",
                ParagraphStyle(
                    "XyQOpt", fontName=body_font(), fontSize=11.5, leading=19, spaceAfter=2
                ),
            )
        )

    # 子问题（简答/阅读的小问，连线题右列）
    for j, sub in enumerate(subs, start=1):
        blocks.append(
            Paragraph(
                f"　　（{j}）{_escape(sub)}",
                ParagraphStyle(
                    "XyQSub", fontName=body_font(), fontSize=11.5, leading=19, spaceAfter=2
                ),
            )
        )

    # 答题横线
    lines = default_lines
    if lines is None:
        lines = _ANSWER_LINES_BY_TYPE.get(qtype, 3)
    lines = max(0, min(int(lines), 30))
    if lines:
        blocks.append(Spacer(1, 2))
        blocks.append(_answer_lines(lines, spec.column_w))

    blocks.append(Spacer(1, 8))

    # 内容不多时整体不拆页，避免一道题被劈成两半
    if len(blocks) <= 8 and lines <= 4:
        return [KeepTogether(blocks)]
    return blocks


def _structured_worksheet_pdf(
    *,
    title: str,
    subject: str,
    grade: str,
    class_name: str,
    teacher: str,
    note: str,
    question_items: Sequence[dict],
    answer_lines_override: Optional[int] = None,
    spec: Optional[PageSpec] = None,
) -> bytes:
    """卷头 + 结构化题目（AI 生成或老师手编的题目列表）。"""
    spec = spec or _PAGE_SPECS[DEFAULT_PAGE_SIZE]
    subj = subject_label(subject)
    grd = grade_label(grade)
    if not title:
        title = f"{grd}{subj}作业".strip() or "作业"

    items = [q for q in question_items if isinstance(q, dict)]

    total_score = 0.0
    for q in items:
        try:
            total_score += float(q.get("score") or 0)
        except (TypeError, ValueError):
            pass

    count_text = f"共 {len(items)} 题"
    if total_score:
        count_text += f" · 满分 {total_score:g} 分"

    buf = io.BytesIO()
    header = _header_flowables(
        title=title,
        subject=subject,
        grade=grade,
        class_name=class_name,
        teacher=teacher,
        note=note,
        count_text=count_text,
        spec=spec,
    )
    doc, story = _make_doc(buf, f"叙阅 · {title}", spec, header_flowables=header)

    for idx, q in enumerate(items, start=1):
        story.extend(
            _question_flowables(
                idx, q, default_lines=answer_lines_override, spec=spec
            )
        )

    if not items:
        story.append(Paragraph("（没有题目）", _body_style(11)))

    doc.build(story)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════
#  对外入口
# ══════════════════════════════════════════════════════════════════════════
def build_worksheet_pdf(
    *,
    title: str = "",
    subject: str = "",
    grade: str = "",
    class_name: str = "",
    teacher: str = "",
    questions: Optional[Iterable[str]] = None,
    question_count: Optional[int] = None,
    answer_lines: int = 2,
    note: str = "",
    uploads: Optional[Sequence[dict]] = None,
    upload_answer_lines: int = 0,
    question_items: Optional[Sequence[dict]] = None,
    answer_lines_override: Optional[int] = None,
    page_size: Optional[str] = None,
    layout: Optional[str] = None,
) -> bytes:
    """生成作业纸 PDF，返回字节内容。

    参数：
        title                 作业标题，留空时按「年级+学科」自动生成
        subject               学科代码或中文
        grade                 年级代码或中文
        class_name            班级（打印在信息栏，可留空由老师手写）
        teacher               布置老师
        questions             题目文本列表；有值时按题目渲染，无值时只留答题横线
        question_count        questions 为空时按此数量生成空白题
        answer_lines          每题答题横线数（手写题目模式）
        note                  卷首提示语
        uploads               上传的题目材料，形如
                              [{'kind': 'image'|'pdf'|'docx'|'text', 'name': str, 'data': bytes}]
                              有值时走「上传材料」模式，其余出题参数被忽略
        upload_answer_lines   上传内容之后追加的答题横线行数，0 表示不加
        question_items        结构化题目列表（AI 生成或老师手编），形如
                              [{'type': 'choice', 'stem': '', 'content': '', 'score': 5,
                                'options': [...], 'subQuestions': [...]}]
        answer_lines_override 覆盖每题的默认答题行数（None = 按题型自动）
        page_size            纸张规格：a4 / a3 / b5 / 16k / 8k / letter，默认 a4
        layout               排版方式：auto（按纸张，大纸默认双栏）/ single / double

    优先级：uploads > question_items > questions/question_count
    """
    spec = apply_layout(resolve_page_spec(page_size), layout)

    if question_items:
        return _structured_worksheet_pdf(
            title=title,
            subject=subject,
            grade=grade,
            class_name=class_name,
            teacher=teacher,
            note=note,
            question_items=question_items,
            answer_lines_override=answer_lines_override,
            spec=spec,
        )

    if uploads:
        return _uploads_worksheet_pdf(
            title=title,
            subject=subject,
            grade=grade,
            class_name=class_name,
            teacher=teacher,
            note=note,
            uploads=uploads,
            extra_answer_lines=upload_answer_lines,
            spec=spec,
        )

    return _text_worksheet_pdf(
        title=title,
        subject=subject,
        grade=grade,
        class_name=class_name,
        teacher=teacher,
        questions=questions,
        question_count=question_count,
        answer_lines=answer_lines,
        note=note,
        spec=spec,
    )
