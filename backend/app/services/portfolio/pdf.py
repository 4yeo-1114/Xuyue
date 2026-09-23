"""
学期报告 PDF 出口（A0 §6.9，reportlab 渲染中文成档）。

中文渲染：优先 Windows 自带中文字体（微软雅黑/黑体/宋体），不可用时回退内置 CID 字体
STSong-Light（PDF 阅读器端渲染中文，跨平台兜底）。

合规：PDF 只读报告域数据 + 评语（confirmed > pending > ai_failed），绝不写库、不参与评分。
页脚标注「AI 辅助生成」提示（A0 §7.3）。
"""
from __future__ import annotations

import datetime
import logging
import os
from pathlib import Path
from typing import Optional

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

_FONT_NAME: Optional[str] = None
_FONT_TRIED = False

_DIM_CN = {
    "moral": "品德发展",
    "intellectual": "智育成长",
    "physical": "身心健康",
    "aesthetic": "审美素养",
    "labor": "劳动实践",
    "ai_literacy": "AI 素养",  # E02
}
_DIM_ORDER = ("intellectual", "moral", "physical", "aesthetic", "labor", "ai_literacy")


def _register_cjk_font() -> str:
    """注册中文字体，返回字体名。Windows TTF 优先；均不可用 → CID 字体 STSong-Light。"""
    global _FONT_NAME, _FONT_TRIED
    if _FONT_TRIED:
        return _FONT_NAME or "STSong-Light"
    _FONT_TRIED = True

    candidates = [
        ("MSYH", r"C:\Windows\Fonts\msyh.ttc"),
        ("MSYHBD", r"C:\Windows\Fonts\msyhbd.ttc"),
        ("SimHei", r"C:\Windows\Fonts\simhei.ttf"),
        ("SimSun", r"C:\Windows\Fonts\simsun.ttc"),
    ]
    for name, path in candidates:
        if not os.path.exists(path):
            continue
        try:
            if path.lower().endswith(".ttc"):
                try:
                    pdfmetrics.registerFont(TTFont(name, path, subfontIndex=0))
                except TypeError:
                    pdfmetrics.registerFont(TTFont(name, path))
            else:
                pdfmetrics.registerFont(TTFont(name, path))
            _FONT_NAME = name
            logger.info("[portfolio.pdf] 已注册中文字体 %s (%s)", name, path)
            return name
        except Exception as e:  # noqa: BLE001
            logger.warning("[portfolio.pdf] 注册字体 %s 失败: %s", name, e)
            continue

    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        _FONT_NAME = "STSong-Light"
        logger.info("[portfolio.pdf] 无 Windows 中文字体，回退内置 CID 字体 STSong-Light")
        return _FONT_NAME
    except Exception as e:  # noqa: BLE001
        logger.warning("[portfolio.pdf] 回退 STSong-Light 失败: %s", e)
        return "Helvetica"


def _font(bold: bool = False) -> str:
    base = _FONT_NAME or _register_cjk_font()
    if bold and base == "MSYH":
        try:
            if "MSYHBD" in pdfmetrics.getRegisteredFontNames():
                return "MSYHBD"
        except Exception:  # noqa: BLE001
            pass
    return base


def _fmt_ts(value) -> str:
    if not value:
        return "—"
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


def render_report_pdf(report: dict, comment: Optional[dict] = None,
                      school_name: str = None, version: int = None) -> bytes:
    """渲染学期报告 PDF → bytes。

    report: GET /portfolio/students/{id}/report 的 data dict（快照 payload 或实时聚合）。
    comment: 评语段 dict（缺省用 report['comment']）。
    school_name: 学校名（PDF 头部展示）。
    version: 报告版本号（快照 version；None = 实时）。
    """
    _register_cjk_font()
    comment = comment or report.get("comment") or {}

    from io import BytesIO
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=16 * mm,
        title="学生学期成长报告",
        author="Grade Buddy Scan",
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle", fontName=_font(bold=True), fontSize=20,
        leading=26, alignment=1, spaceAfter=4, textColor=colors.HexColor("#1a3c6e"),
    ))
    styles.add(ParagraphStyle(
        name="ReportSub", fontName=_font(), fontSize=10,
        leading=14, alignment=1, textColor=colors.HexColor("#666666"),
    ))
    styles.add(ParagraphStyle(
        name="H2", fontName=_font(bold=True), fontSize=13,
        leading=18, spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#1a3c6e"),
    ))
    styles.add(ParagraphStyle(
        name="Body", fontName=_font(), fontSize=10.5, leading=16,
        alignment=TA_LEFT, spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name="Gray", fontName=_font(), fontSize=10, leading=15,
        textColor=colors.HexColor("#999999"),
    ))

    name = report.get("name") or "该学生"
    grade = report.get("grade") or "—"
    term = report.get("term") or "—"
    data_status = report.get("data_status") or {}
    dims = report.get("dimensions") or {}
    profile = report.get("assessment_profile") or {}
    labels = profile.get("labels") or []
    baseline = report.get("baseline") or {}
    generated_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")

    flow: list = []

    # ── 标题区 ──
    flow.append(Paragraph("学生学期成长报告", styles["ReportTitle"]))
    flow.append(Paragraph(
        f"{school_name or '学校'} ｜ 学生：{name} ｜ 年级：{grade} ｜ 学期：{term}",
        styles["ReportSub"]))
    if version:
        flow.append(Paragraph(f"报告版本：v{version}（冻结快照）", styles["ReportSub"]))
    else:
        flow.append(Paragraph("报告版本：实时生成", styles["ReportSub"]))
    flow.append(Spacer(1, 6))
    flow.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a3c6e")))

    # ── 一、五育表现 ──
    flow.append(Paragraph("一、五育成长表现", styles["H2"]))
    for dim in _DIM_ORDER:
        cn = _DIM_CN.get(dim, dim)
        st = data_status.get(dim)
        d = dims.get(dim) or {}
        if st == "has_data":
            total = d.get("total", 0)
            detail_txt = ""
            if dim == "intellectual" and d.get("detail"):
                det = d["detail"]
                detail_txt = (
                    f"（订正错题 {det.get('corrected_wrong_questions', 0)} 道 · "
                    f"成绩提升 {det.get('rank_improvements', 0)} 次 · "
                    f"靶向报告 {det.get('targeted_reports', 0)} 份 · "
                    f"超班级均分 {det.get('above_class_avg', 0)} 次）"
                )
            flow.append(Paragraph(
                f"<b>{cn}</b>：已有数据，成长分 {total}{detail_txt}", styles["Body"]))
        else:
            flow.append(Paragraph(
                f"<b>{cn}</b>：数据待补充（本学期暂无有效记录，灰态占位不造假）",
                styles["Gray"]))

    # ── 二、班级相对位置（归一化基准线）──
    comp = (baseline.get("composite") or {}).get("intellectual")
    tier = (baseline.get("tier") or {}).get("intellectual")
    percentile = (baseline.get("percentile") or {}).get("intellectual")
    flow.append(Paragraph("二、智育班级相对位置", styles["H2"]))
    if comp is not None or tier is not None:
        bits = []
        if comp is not None:
            bits.append(f"综合分 {comp:.1f}（满分 100）")
        if tier:
            bits.append(f"档位 {tier}")
        if percentile is not None:
            bits.append(f"班级百分位 P{percentile:.0f}")
        flow.append(Paragraph("；".join(bits), styles["Body"]))
    else:
        flow.append(Paragraph("暂无足够的班级数据计算归一化基准线。", styles["Gray"]))

    # ── 三、行为画像白名单标签 ──
    flow.append(Paragraph("三、行为画像标签", styles["H2"]))
    if labels:
        flow.append(Paragraph("；".join(labels), styles["Body"]))
    else:
        flow.append(Paragraph("本学期暂无测评标签（不虚构）。", styles["Gray"]))

    # ── 四、学分银行（G2：账户余额 + 学期区间流水，纯读不写）──
    flow.append(Paragraph("四、学分银行", styles["H2"]))
    credit = report.get("credit")
    if credit and credit.get("balance") is not None:
        _hdr = lambda t: Paragraph(f"<b>{t}</b>", styles["Body"])
        _val = lambda v: Paragraph(str(v), styles["Body"])
        credit_tbl = Table(
            [
                [_hdr("当前余额"), _hdr("累计挣得"), _hdr("累计支出")],
                [_val(credit.get("balance", 0)),
                 _val(credit.get("total_earned", 0)),
                 _val(credit.get("total_spent", 0))],
                [_hdr("本学期挣得"), _hdr("本学期支出"), _hdr("流水笔数")],
                [_val(credit.get("term_earned", 0)),
                 _val(credit.get("term_spent", 0)),
                 _val(f'{credit.get("txn_count", 0)} 笔')],
            ],
            colWidths=[56 * mm, 56 * mm, 56 * mm],
        )
        credit_tbl.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f8")),
            ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#eef2f8")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        flow.append(credit_tbl)
    else:
        flow.append(Paragraph("学分数据暂未生成（学分银行账户尚未建立，不造假）。", styles["Gray"]))

    # ── 五、教师评语 ──
    flow.append(Paragraph("五、教师评语", styles["H2"]))
    cstatus = comment.get("status")
    content = comment.get("content")
    if cstatus == "confirmed":
        flow.append(Paragraph(content or "（已确认）", styles["Body"]))
        if comment.get("confirmed_at"):
            flow.append(Paragraph(
                f"教师确认时间：{_fmt_ts(comment.get('confirmed_at'))}", styles["Gray"]))
    elif cstatus == "pending":
        flow.append(Paragraph(content or "（AI 初稿待教师确认）", styles["Body"]))
        flow.append(Paragraph("以上为 AI 生成的评语初稿，尚待教师确认。", styles["Gray"]))
    elif cstatus == "ai_failed":
        flow.append(Paragraph(content or "本学期学业评语暂未生成，请联系班主任。", styles["Body"]))
        flow.append(Paragraph("评语生成失败（AI 网关不可用），请稍后重试或联系班主任。", styles["Gray"]))
    else:
        flow.append(Paragraph("本学期评语暂未生成。", styles["Gray"]))

    # ── 页脚 ──
    flow.append(Spacer(1, 10))
    flow.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
    flow.append(Paragraph(
        f"生成时间：{generated_at} ｜ 本报告为电子成档，用于学期成长留痕与升学材料参考。",
        styles["Gray"]))
    flow.append(Paragraph(
        "评语由 AI 辅助生成，教师确认后为最终版本。", styles["Gray"]))

    doc.build(flow)
    return buf.getvalue()


# ── 成长纪念册 PDF（G1）───────────────────────────────────────────
#
# 对外可交付的综评材料：封面 + 教师评语 + 成长照片 + 成长记录，
# 复用 render_report_pdf 的 A4/中文字体/段落样式体系。纯读，绝不写库。

# 单张照片在网格内的最大尺寸（mm），超出按比例缩放，避免布局溢出
_ALBUM_IMG_MAX_W_MM = 54.0
_ALBUM_IMG_MAX_H_MM = 70.0
_ALBUM_GRID_COLS = 3
_ALBUM_USABLE_W_MM = 174.0  # A4 210 - 左右各 18mm 页边距


def _resolve_album_image(rel_path: str) -> Optional[Path]:
    """将 assets/memories 相对路径安全解析为绝对路径；非法/缺失返回 None（不抛异常）。

    与 routers/portfolio._resolve_memory_file 相同的防穿越语义（services 不反向依赖
    routers，故本地镜像一份安全规则）。
    """
    if not rel_path:
        return None
    safe = str(rel_path).replace("\\", "/")
    if safe.startswith("/") or ".." in safe.split("/"):
        return None
    root = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "memories"
    file_path = (root / safe).resolve()
    try:
        if not file_path.is_relative_to(root.resolve()):
            return None
    except Exception:  # noqa: BLE001
        return None
    return file_path if file_path.is_file() else None


def _make_photo_cell(file_path: str, caption: str, styles) -> Optional[list]:
    """生成单个照片单元格（Image + 可选说明）；图片不可读/尺寸非法 → None（跳过）。"""
    try:
        with PILImage.open(file_path) as im:
            w, h = im.size
    except Exception:  # noqa: BLE001
        return None
    if not w or not h:
        return None
    max_w = _ALBUM_IMG_MAX_W_MM * mm
    max_h = _ALBUM_IMG_MAX_H_MM * mm
    ratio = min(max_w / w, max_h / h, 1.0)
    cell: list = [Image(file_path, width=w * ratio, height=h * ratio)]
    if caption:
        cell.append(Spacer(1, 2))
        cell.append(Paragraph(caption, styles["PhotoCaption"]))
    return cell


def _build_album_photos(memories: list, styles) -> list:
    """成长照片网格；无照片或全部文件缺失 → 灰态占位文案。"""
    flow: list = []
    cells = []
    for mem in memories or []:
        if not isinstance(mem, dict):
            continue
        file_path = mem.get("file_path") or _resolve_album_image(mem.get("image_path"))
        if not file_path:
            continue
        cell = _make_photo_cell(file_path, mem.get("caption"), styles)
        if cell is not None:
            cells.append(cell)

    if not cells:
        flow.append(Paragraph("本学期暂无成长照片（数据待补充）。", styles["Gray"]))
        return flow

    rows: list = []
    row: list = []
    for cell in cells:
        row.append(cell)
        if len(row) == _ALBUM_GRID_COLS:
            rows.append(row)
            row = []
    if row:
        while len(row) < _ALBUM_GRID_COLS:
            row.append("")
        rows.append(row)

    cell_w = _ALBUM_USABLE_W_MM / _ALBUM_GRID_COLS
    table = Table(rows, colWidths=[cell_w * mm] * _ALBUM_GRID_COLS, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    flow.append(table)
    return flow


def _build_album_growth_records(growth_records: list, styles) -> list:
    """成长记录按维度分组列表；无记录 → 灰态占位文案。"""
    flow: list = []
    grouped: dict = {}
    for rec in growth_records or []:
        if not isinstance(rec, dict):
            continue
        dim = rec.get("dimension") or "other"
        grouped.setdefault(dim, []).append(rec)

    ordered_dims = [d for d in _DIM_ORDER if d in grouped]
    ordered_dims += [d for d in grouped if d not in _DIM_ORDER]
    if not ordered_dims:
        flow.append(Paragraph("本学期暂无成长记录（数据待补充）。", styles["Gray"]))
        return flow

    for dim in ordered_dims:
        cn = _DIM_CN.get(dim, dim)
        flow.append(Paragraph(cn, styles["H3"]))
        for rec in grouped[dim]:
            note = (rec.get("note") or "").strip() or "（无备注）"
            pts = rec.get("growth_points")
            if pts is None:
                pts = rec.get("growth_point")
            ts = _fmt_ts(rec.get("occurred_at"))
            bits = []
            if rec.get("indicator_name"):
                bits.append(f"指标：{rec['indicator_name']}")
            if ts != "—":
                bits.append(ts)
            meta = " ｜ ".join(bits)
            flow.append(Paragraph(f"· {note}", styles["Body"]))
            flow.append(Paragraph(f"　{meta}（成长分 +{int(pts or 0)}）", styles["Gray"]))

    return flow


def render_growth_album_pdf(
    report: dict,
    comment: Optional[dict] = None,
    memories: Optional[list] = None,
    growth_records: Optional[list] = None,
    school_name: str = None,
    student_name: str = None,
    term: str = None,
) -> bytes:
    """渲染「成长纪念册」PDF → bytes。

    report: GET /portfolio/students/{id}/report 的 data dict（提供 name/term 兜底）。
    comment: get_comment_section 返回的评语段 dict（confirmed > pending > ai_failed > absent）。
    memories: 成长照片列表，每项 dict 至少含 image_path（相对路径）或 file_path（已解析绝对路径）
        + 可选 caption。缺失/损坏文件自动跳过；全部不可用 → 灰态占位。
    growth_records: 成长记录列表（dimension/note/growth_points/growth_point/occurred_at/indicator_name）。
    school_name/student_name/term: 封面展示值，缺省回退 report 字段。
    """
    _register_cjk_font()
    comment = comment or {}
    memories = memories or []
    growth_records = growth_records or []
    school_name = school_name or "学校"
    student_name = student_name or (report or {}).get("name") or "该学生"
    term = term or (report or {}).get("term") or "—"

    from io import BytesIO
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=16 * mm,
        title="成长纪念册",
        author="Grade Buddy Scan",
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="CoverSchool", fontName=_font(bold=True), fontSize=16,
        leading=22, alignment=1, textColor=colors.HexColor("#666666"),
    ))
    styles.add(ParagraphStyle(
        name="CoverTitle", fontName=_font(bold=True), fontSize=30,
        leading=38, alignment=1, textColor=colors.HexColor("#1a3c6e"),
    ))
    styles.add(ParagraphStyle(
        name="CoverSub", fontName=_font(), fontSize=14,
        leading=20, alignment=1, textColor=colors.HexColor("#333333"),
    ))
    styles.add(ParagraphStyle(
        name="H2", fontName=_font(bold=True), fontSize=13,
        leading=18, spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#1a3c6e"),
    ))
    styles.add(ParagraphStyle(
        name="H3", fontName=_font(bold=True), fontSize=11.5,
        leading=16, spaceBefore=8, spaceAfter=2, textColor=colors.HexColor("#1a3c6e"),
    ))
    styles.add(ParagraphStyle(
        name="Body", fontName=_font(), fontSize=10.5, leading=16,
        alignment=TA_LEFT, spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name="Gray", fontName=_font(), fontSize=10, leading=15,
        textColor=colors.HexColor("#999999"),
    ))
    styles.add(ParagraphStyle(
        name="PhotoCaption", fontName=_font(), fontSize=8, leading=10,
        alignment=1, textColor=colors.HexColor("#666666"),
    ))

    flow: list = []

    # ── 封面 ──
    flow.append(Spacer(1, 55 * mm))
    flow.append(Paragraph(school_name, styles["CoverSchool"]))
    flow.append(Spacer(1, 14 * mm))
    flow.append(Paragraph("成长纪念册", styles["CoverTitle"]))
    flow.append(Spacer(1, 12 * mm))
    flow.append(Paragraph(f"学生：{student_name}", styles["CoverSub"]))
    flow.append(Paragraph(f"学期：{term}", styles["CoverSub"]))
    flow.append(PageBreak())

    # ── 一、教师评语 ──
    flow.append(Paragraph("一、教师评语", styles["H2"]))
    cstatus = comment.get("status")
    content = comment.get("content")
    if cstatus == "confirmed":
        flow.append(Paragraph(content or "（已确认）", styles["Body"]))
        if comment.get("confirmed_at"):
            flow.append(Paragraph(
                f"教师确认时间：{_fmt_ts(comment.get('confirmed_at'))}", styles["Gray"]))
    elif cstatus == "pending":
        flow.append(Paragraph(content or "（AI 初稿待教师确认）", styles["Body"]))
        flow.append(Paragraph("以上为 AI 生成的评语初稿，尚待教师确认。", styles["Gray"]))
    elif cstatus == "ai_failed":
        flow.append(Paragraph(content or "本学期学业评语暂未生成，请联系班主任。", styles["Body"]))
        flow.append(Paragraph("评语生成失败（AI 网关不可用），请稍后重试或联系班主任。", styles["Gray"]))
    else:
        flow.append(Paragraph("本学期评语暂未生成。", styles["Gray"]))

    # ── 二、成长照片 ──
    flow.append(Paragraph("二、成长照片", styles["H2"]))
    flow += _build_album_photos(memories, styles)

    # ── 三、成长记录 ──
    flow.append(Paragraph("三、成长记录", styles["H2"]))
    flow += _build_album_growth_records(growth_records, styles)

    # ── 页脚 ──
    flow.append(Spacer(1, 10))
    flow.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
    flow.append(Paragraph(
        "成长纪念册为学期成长留痕的对外交付材料，由学校综合综评生成。",
        styles["Gray"]))
    flow.append(Paragraph(
        "评语由 AI 辅助生成，教师确认后为最终版本。", styles["Gray"]))

    doc.build(flow)
    return buf.getvalue()
