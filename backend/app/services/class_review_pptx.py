# -*- coding: utf-8 -*-
"""课堂讲评 PPTX 生成器。

为「课堂讲评」页的「生成讲评 PPT」提供后端建片能力：封面 / 讲评概览 / 逐题讲评
（原题 + 知识点 + 错因 + 错答名单）/ 学生错答扫描（同类型错题）/ 同类变式练习。
复用 ai_resources 课件生成器的教育风主题（深靛蓝 + 琥珀点缀 + 微软雅黑），并在此
基础上补齐「图片嵌入」能力——原题/错答扫描为本地 .jpg，直接以 bytes 嵌入幻灯片。
"""
from __future__ import annotations

import io
from typing import List, Optional, Tuple


def _fit_picture_bytes(slide, data: bytes, left, top, max_w, max_h):
    """按原始宽高比把图片适配进给定盒子（居中），返回 picture shape 或 None。"""
    if not data:
        return None
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(data))
        iw, ih = im.size
        if iw <= 0 or ih <= 0:
            return None
    except Exception:
        return None
    ratio = min(max_w / iw, max_h / ih)
    w = iw * ratio
    h = ih * ratio
    l = left + (max_w - w) / 2
    t = top + (max_h - h) / 2
    try:
        return slide.shapes.add_picture(io.BytesIO(data), int(l), int(t), int(w), int(h))
    except Exception:
        return None


def build_class_review_pptx(
    title: str,
    subject: str,
    subtitle: str,
    overview_items: List[str],
    question_blocks: List[dict],
    wrong_images: List[dict],
    variant_blocks: List[dict],
) -> bytes:
    """生成课堂讲评 PPTX 字节流。

    question_blocks: 每项 {label, accuracy, question_text, knowledge_points: [str],
                           variant_stem, variant_answer}
    wrong_images:    每项 {student_name, title, image_bytes, answer_bytes}
    variant_blocks:  每项 {label, variant_stem, variant_answer}（同 question_blocks 里的变式字段，独立章节用）
    """
    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.oxml.ns import qn
    except ImportError:
        raise RuntimeError("服务端未安装 python-pptx，无法生成 PPT，请联系管理员")

    # ── 主题配色（与 ai_resources 课件一致：教育风） ──
    PRIMARY = RGBColor(0x2B, 0x3A, 0x67)
    PRIMARY_SOFT = RGBColor(0x3A, 0x4C, 0x80)
    ACCENT = RGBColor(0xF5, 0x9E, 0x0B)
    WHITE = RGBColor(0xFF, 0xFF, 0xFF)
    BODY = RGBColor(0x33, 0x41, 0x55)
    MUTED = RGBColor(0x94, 0xA3, 0xB8)
    GOOD = RGBColor(0x10, 0xB9, 0x81)
    BAD = RGBColor(0xE1, 0x1D, 0x48)
    FONT = "微软雅黑"
    SLIDE_W = Inches(13.333)
    SLIDE_H = Inches(7.5)

    def _set_run_font(run, name=FONT):
        try:
            run.font.name = name
            rPr = run._r.get_or_add_rPr()
            ea = rPr.find(qn("a:ea"))
            if ea is None:
                ea = rPr.makeelement(qn("a:ea"), {})
                rPr.append(ea)
            ea.set("typeface", name)
        except Exception:
            pass

    def _fill_bg(slide, color):
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = color

    def _rect(slide, left, top, width, height, color):
        shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
        shp.fill.solid()
        shp.fill.fore_color.rgb = color
        shp.line.fill.background()
        try:
            shp.shadow.inherit = False
        except Exception:
            pass
        return shp

    def _add_textbox(slide, left, top, width, height, anchor=MSO_ANCHOR.TOP):
        tb = slide.shapes.add_textbox(left, top, width, height)
        tf = tb.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        return tf

    def _set_para(p, text, size, color, bold=False, align=PP_ALIGN.LEFT, space_after=Pt(6)):
        p.text = text
        p.alignment = align
        p.space_after = space_after
        for run in p.runs:
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.color.rgb = color
            _set_run_font(run)
        return p

    def _add_bullet(tf, text, first, size=14, accent=ACCENT, body=BODY):
        para = tf.paragraphs[0] if first else tf.add_paragraph()
        para.level = 0
        para.space_after = Pt(6)
        rm = para.add_run()
        rm.text = "▪  "
        rm.font.size = Pt(size)
        rm.font.bold = True
        rm.font.color.rgb = accent
        _set_run_font(rm)
        rt = para.add_run()
        rt.text = text
        rt.font.size = Pt(size)
        rt.font.color.rgb = body
        _set_run_font(rt)
        return para

    def _label_para(tf, text, first, color=PRIMARY):
        para = tf.paragraphs[0] if first else tf.add_paragraph()
        para.space_after = Pt(4)
        rm = para.add_run()
        rm.text = text
        rm.font.size = Pt(13)
        rm.font.bold = True
        rm.font.color.rgb = color
        _set_run_font(rm)
        return para

    def _content_header(slide, text, idx, total):
        _rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(1.0), PRIMARY)
        _rect(slide, Inches(0), Inches(1.0), SLIDE_W, Inches(0.06), ACCENT)
        tf = _add_textbox(slide, Inches(0.55), Inches(0), Inches(9.7), Inches(1.0), MSO_ANCHOR.MIDDLE)
        _set_para(tf.paragraphs[0], text, 20, WHITE, bold=True)
        tfn = _add_textbox(slide, Inches(12.0), Inches(0), Inches(0.9), Inches(1.0), MSO_ANCHOR.MIDDLE)
        _set_para(tfn.paragraphs[0], f"{idx} / {total}", 10, MUTED, align=PP_ALIGN.RIGHT)

    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    blank = prs.slide_layouts[6]

    # 先算总页数（封面 + 概览 + 逐题 + 错答 + 变式），供页码显示
    section_count = 1  # 封面
    if overview_items:
        section_count += 1
    section_count += len(question_blocks)
    wrong_slides = (len(wrong_images) + 7) // 8 if wrong_images else 0
    section_count += wrong_slides
    variant_slides = (len(variant_blocks) + 3) // 4 if variant_blocks else 0
    section_count += variant_slides
    total_slides = section_count
    _page = [0]

    def _new_content_slide():
        _page[0] += 1
        slide = prs.slides.add_slide(blank)
        _fill_bg(slide, WHITE)
        return slide

    # ── 封面 ──
    cover = prs.slides.add_slide(blank)
    _fill_bg(cover, PRIMARY)
    _rect(cover, Inches(0), Inches(6.15), SLIDE_W, Inches(1.35), ACCENT)
    _rect(cover, Inches(0), Inches(0), SLIDE_W, Inches(0.16), ACCENT)
    from pptx.enum.shapes import MSO_SHAPE as _MS
    _shp = cover.shapes.add_shape(_MS.OVAL, Inches(9.5), Inches(-1.0), Inches(4.6), Inches(4.6))
    _shp.fill.solid(); _shp.fill.fore_color.rgb = PRIMARY_SOFT; _shp.line.fill.background()
    tf = _add_textbox(cover, Inches(0.9), Inches(2.35), Inches(11.5), Inches(1.7), MSO_ANCHOR.MIDDLE)
    _set_para(tf.paragraphs[0], (title or f"{subject}课堂讲评")[:60], 34, WHITE, bold=True)
    if subtitle:
        tf2 = _add_textbox(cover, Inches(0.95), Inches(4.15), Inches(11.0), Inches(0.6))
        _set_para(tf2.paragraphs[0], subtitle, 16, RGBColor(0xFF, 0xE0, 0xB2))

    # ── 讲评概览 ──
    if overview_items:
        slide = _new_content_slide()
        _content_header(slide, "讲评概览", _page[0], total_slides)
        tfb = _add_textbox(slide, Inches(0.9), Inches(1.5), Inches(11.6), Inches(5.5), MSO_ANCHOR.TOP)
        first = True
        for item in overview_items:
            _add_bullet(tfb, item, first, size=16)
            first = False

    # ── 逐题讲评 ──
    for qb in question_blocks:
        slide = _new_content_slide()
        label = (qb.get("label") or "未标题").strip() or "未标题"
        accuracy = qb.get("accuracy")
        acc_text = f"{int(round(accuracy))}%" if isinstance(accuracy, (int, float)) else ""
        _content_header(slide, f"{label} · 原题与知识点", _page[0], total_slides)
        if acc_text:
            tfa = _add_textbox(slide, Inches(10.35), Inches(0), Inches(1.5), Inches(1.0), MSO_ANCHOR.MIDDLE)
            color = GOOD if (accuracy or 0) >= 80 else (ACCENT if (accuracy or 0) >= 60 else BAD)
            _set_para(tfa.paragraphs[0], acc_text, 16, color, bold=True, align=PP_ALIGN.RIGHT)

        # 左列：原题
        _rect(slide, Inches(0.55), Inches(1.35), Inches(0.12), Inches(0.42), ACCENT)
        left_tf = _add_textbox(slide, Inches(0.55), Inches(1.85), Inches(6.5), Inches(5.3), MSO_ANCHOR.TOP)
        _label_para(left_tf, "原题", True)
        qt = (qb.get("question_text") or "").strip()
        if qt:
            para = left_tf.add_paragraph()
            para.space_after = Pt(4)
            rt = para.add_run()
            rt.text = qt[:500]
            rt.font.size = Pt(14)
            rt.font.color.rgb = BODY
            _set_run_font(rt)
        else:
            para = left_tf.add_paragraph()
            para.space_after = Pt(4)
            rt = para.add_run()
            rt.text = "（暂无原题文本）"
            rt.font.size = Pt(14)
            rt.font.color.rgb = MUTED
            _set_run_font(rt)

        # 右列：知识点（详细，多条要点）
        right_tf = _add_textbox(slide, Inches(7.35), Inches(1.85), Inches(5.45), Inches(5.3), MSO_ANCHOR.TOP)
        kps = qb.get("knowledge_points") or []
        if kps:
            _label_para(right_tf, "知识点", True)
            for kp in kps[:4]:
                _add_bullet(right_tf, str(kp), False, size=12)

    # ── 同类型错题 · 学生错答扫描 ──
    if wrong_images:
        per_slide = 8
        for start in range(0, len(wrong_images), per_slide):
            slide = _new_content_slide()
            _content_header(slide, "同类型错题 · 学生错答扫描", _page[0], total_slides)
            batch = wrong_images[start:start + per_slide]
            cols = 4
            cell_w = Inches(3.0)
            cell_h = Inches(2.55)
            gap_x = Inches(0.12)
            gap_y = Inches(0.32)
            origin_x = Inches(0.55)
            origin_y = Inches(1.35)
            for i, item in enumerate(batch):
                row = i // cols
                col = i % cols
                left = origin_x + col * (cell_w + gap_x)
                top = origin_y + row * (cell_h + gap_y)
                data = item.get("answer_bytes") or item.get("image_bytes")
                _fit_picture_bytes(slide, data, left, top, cell_w, Inches(2.0))
                name = item.get("student_name") or ""
                ttl = item.get("title") or ""
                caption = f"{name} · {ttl}".strip(" ·")
                tfc = _add_textbox(slide, left, top + Inches(2.05), cell_w, Inches(0.4), MSO_ANCHOR.TOP)
                _set_para(tfc.paragraphs[0], caption[:28], 10, MUTED, align=PP_ALIGN.CENTER)
            if start + per_slide < len(wrong_images):
                tfn = _add_textbox(slide, Inches(0.55), Inches(7.08), Inches(9), Inches(0.4))
                _set_para(tfn.paragraphs[0], f"共 {len(wrong_images)} 张错答扫描，续下页", 10, MUTED)

    # ── 同类变式练习 ──
    if variant_blocks:
        per_slide = 3
        for start in range(0, len(variant_blocks), per_slide):
            slide = _new_content_slide()
            _content_header(slide, "同类变式练习", _page[0], total_slides)
            tfb = _add_textbox(slide, Inches(0.9), Inches(1.4), Inches(11.6), Inches(5.6), MSO_ANCHOR.TOP)
            first = True
            for vb in variant_blocks[start:start + per_slide]:
                label = (vb.get("label") or "").strip()
                stem = (vb.get("variant_stem") or "").strip()
                answer = (vb.get("variant_answer") or "").strip()
                _label_para(tfb, f"【{label}】{stem}" if label else stem, first, color=PRIMARY)
                first = False
                if answer:
                    _add_bullet(tfb, f"参考答案：{answer}", False, size=12, accent=GOOD, body=BODY)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
