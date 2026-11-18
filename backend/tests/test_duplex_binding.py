# -*- coding: utf-8 -*-
"""11.13 台账 #2 双面打印翻页方式（长边/短边）· 后端单元测试。

覆盖：
1. images_to_pdf_bytes(rotate_first_of_pairs=True)：每对送打页的第 1 张转 180°、第 2 张不动
2. 落单页不转（单页报告就是正面）
3. build_essay_report_pdf_bytes：双面合印逐生补偶页（每个学生独占整张纸）；
   短边=每对首面 set_rotation(180)，长边（默认）=不转不补，与旧行为一致
"""

import io

import fitz
from PIL import Image, ImageDraw

from app.grading.essay_pdf import EssayPdfItem, build_essay_report_pdf_bytes
from app.grading.print_marks import images_to_pdf_bytes


def _asymmetric_png(tmp_path, name, w=400, h=600):
    """左上角画一个红色圆点的非对称图：转 180° 后点跑到右下，方向可判。"""
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    d.ellipse((20, 20, 80, 80), fill=(220, 30, 30))
    p = tmp_path / name
    im.save(str(p))
    return str(p)


def _red_dot_center(page) -> tuple:
    pix = page.get_pixmap()
    im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    px = im.load()
    w, h = im.size
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if r > 150 and g < 105 and b < 105 and (r - g) > 80:
                xs.append(x)
                ys.append(y)
    return (sum(xs) / len(xs), sum(ys) / len(ys), w, h)


# ---------------------------------------------------------------- 留痕 PDF

def test_images_to_pdf_rotates_first_of_pairs(tmp_path):
    paths = [_asymmetric_png(tmp_path, f"p{i}.png") for i in range(3)]
    pdf = images_to_pdf_bytes(paths, rotate_first_of_pairs=True)
    doc = fitz.open(stream=pdf, filetype="pdf")
    try:
        assert doc.page_count == 3
        for i in range(3):
            cx, cy, w, h = _red_dot_center(doc[i])
            if i % 2 == 0:
                # 对内第 1 张：转了 180°，红点沉到底部
                assert cy > h * 0.5, f"page {i} 应旋转（红点应在下半），cy={cy} h={h}"
            else:
                # 对内第 2 张：不动，红点在顶部
                assert cy < h * 0.5, f"page {i} 不应旋转（红点应在上半），cy={cy} h={h}"
    finally:
        doc.close()


def test_images_to_pdf_no_rotate_by_default(tmp_path):
    paths = [_asymmetric_png(tmp_path, f"q{i}.png") for i in range(2)]
    pdf = images_to_pdf_bytes(paths)
    doc = fitz.open(stream=pdf, filetype="pdf")
    try:
        for i in range(2):
            cx, cy, w, h = _red_dot_center(doc[i])
            assert cy < h * 0.5, f"page {i} 默认不转，红点应在上半，cy={cy}"
    finally:
        doc.close()


# ---------------------------------------------------------------- 报告 PDF

def _item(name, lines=3):
    body = "\n".join(f"第{i}行：正文内容。" for i in range(lines))
    return EssayPdfItem(name=name, result=f"【作文得分】\n88 分\n\n【老师总评】\n{body}")


def test_report_pdf_pads_each_item_to_even_pages():
    pdf = build_essay_report_pdf_bytes(
        folder_name="cls_t__1",
        items=[_item("甲_1.pdf"), _item("乙_1.pdf")],
        duplex_double=True,
    )
    doc = fitz.open(stream=pdf, filetype="pdf")
    try:
        # 每个学生 1 页 + 各补 1 张空白背页 = 4 页（各自独占一张双面纸）
        assert doc.page_count == 4
    finally:
        doc.close()


def test_report_pdf_no_pad_when_single_mode():
    pdf = build_essay_report_pdf_bytes(
        folder_name="cls_t__1",
        items=[_item("甲_1.pdf")],
    )
    doc = fitz.open(stream=pdf, filetype="pdf")
    try:
        assert doc.page_count == 1
        assert doc[0].rotation == 0
    finally:
        doc.close()


def test_report_pdf_short_binding_rotates_first_of_pairs():
    pdf = build_essay_report_pdf_bytes(
        folder_name="cls_t__1",
        items=[_item("甲_1.pdf"), _item("乙_1.pdf")],
        duplex_double=True,
        duplex_binding="short",
    )
    doc = fitz.open(stream=pdf, filetype="pdf")
    try:
        assert doc.page_count == 4
        rotations = [doc[i].rotation for i in range(4)]
        assert rotations == [180, 0, 180, 0], rotations
    finally:
        doc.close()


def test_report_pdf_short_single_page_not_rotated():
    # 单页报告（落单页）短边也不转：它就是正面
    pdf = build_essay_report_pdf_bytes(
        folder_name="cls_t__1",
        items=[_item("甲_1.pdf")],
        duplex_binding="short",
    )
    doc = fitz.open(stream=pdf, filetype="pdf")
    try:
        assert doc.page_count == 1
        assert doc[0].rotation == 0
    finally:
        doc.close()


def test_report_pdf_long_binding_unchanged():
    pdf = build_essay_report_pdf_bytes(
        folder_name="cls_t__1",
        items=[_item("甲_1.pdf"), _item("乙_1.pdf")],
        duplex_double=True,
        duplex_binding="long",
    )
    doc = fitz.open(stream=pdf, filetype="pdf")
    try:
        assert doc.page_count == 4
        assert all(doc[i].rotation == 0 for i in range(4))
    finally:
        doc.close()
