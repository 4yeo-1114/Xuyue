"""G1 成长册 PDF 合成测试。

直接调用 app.services.portfolio.pdf.render_growth_album_pdf（不碰 DB），
mock 最小 report/comment/memories/growth_records 数据，断言：
- 返回 bytes 且以 %PDF 开头
- 空照片/空记录仍生成 PDF（不抛异常）
- 封面含学生姓名/学期文案（有 PyMuPDF 时抽查 PDF 文本流）
- 真实照片 + 成长记录能正常合成
- 缺失/损坏照片文件自动跳过，不抛异常
"""
from app.services.portfolio.pdf import render_growth_album_pdf

try:
    import fitz  # PyMuPDF

    HAS_FITZ = True
except Exception:  # noqa: BLE001
    HAS_FITZ = False


def _pdf_text(pdf_bytes: bytes) -> str:
    """抽 PDF 文本流（仅断言用，非生产路径）。"""
    if not HAS_FITZ:
        return ""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)


def _base_report() -> dict:
    return {
        "student_id": "stu-1",
        "name": "张小明",
        "grade": "三年级",
        "term": "2025-2026-1",
        "dimensions": {},
        "data_status": {},
        "baseline": {},
        "assessment_profile": {},
    }


def _confirmed_comment() -> dict:
    return {"status": "confirmed", "content": "学习认真，乐于助人，进步明显。",
            "confirmed_at": "2026-01-15T10:00:00+00:00"}


# ── 基础成档 ───────────────────────────────────────

def test_returns_pdf_bytes_with_valid_header():
    pdf = render_growth_album_pdf(
        _base_report(),
        comment=_confirmed_comment(),
        memories=[],
        growth_records=[],
        school_name="实验小学",
        student_name="张小明",
        term="2025-2026-1",
    )
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF")


def test_empty_photos_and_records_do_not_raise():
    """空照片 + 空记录（含 comment=None）仍生成 PDF，不抛异常。"""
    pdf = render_growth_album_pdf(_base_report(), comment=None, memories=[], growth_records=[])
    assert pdf.startswith(b"%PDF")


def test_cover_contains_student_name_and_term():
    pdf = render_growth_album_pdf(
        _base_report(),
        comment={"status": "pending", "content": "AI 初稿评语"},
        memories=[],
        growth_records=[],
        school_name="实验小学",
        student_name="张小明",
        term="2025-2026-1",
    )
    assert pdf.startswith(b"%PDF")
    if HAS_FITZ:
        text = _pdf_text(pdf)
        assert "成长纪念册" in text
        assert "张小明" in text
        assert "2025-2026-1" in text
        assert "实验小学" in text


# ── 评语三态语义 ───────────────────────────────────

def test_pending_comment_marks_ai_draft():
    pdf = render_growth_album_pdf(
        _base_report(),
        comment={"status": "pending", "content": "AI 初稿评语"},
        memories=[],
        growth_records=[],
    )
    if HAS_FITZ:
        text = _pdf_text(pdf)
        assert "AI 初稿评语" in text
        assert "尚待教师确认" in text


def test_absent_comment_renders_fallback():
    pdf = render_growth_album_pdf(
        _base_report(),
        comment={"status": "absent", "content": None},
        memories=[],
        growth_records=[],
    )
    assert pdf.startswith(b"%PDF")
    if HAS_FITZ:
        assert "评语暂未生成" in _pdf_text(pdf)


# ── 真实照片 + 成长记录 ────────────────────────────

def test_with_real_photo_and_growth_records(tmp_path):
    from PIL import Image

    img = Image.new("RGB", (200, 150), (200, 60, 60))
    img_path = tmp_path / "photo.jpg"
    img.save(img_path, "JPEG")

    pdf = render_growth_album_pdf(
        _base_report(),
        comment=_confirmed_comment(),
        memories=[
            {"id": "m1", "image_path": "2026-08/photo.jpg",
             "file_path": str(img_path), "caption": "运动会合影"},
        ],
        growth_records=[
            {
                "dimension": "intellectual",
                "note": "数学订正错题 5 道",
                "growth_points": 5,
                "occurred_at": "2026-03-01T00:00:00+00:00",
                "indicator_name": "作业订正",
            },
            {
                "dimension": "moral",
                "note": "主动帮助同学搬运器材",
                "growth_point": 3,
                "occurred_at": "2026-04-10",
                "indicator_name": "乐于助人",
            },
        ],
        school_name="实验小学",
        student_name="张小明",
        term="2025-2026-1",
    )
    assert pdf.startswith(b"%PDF")
    if HAS_FITZ:
        text = _pdf_text(pdf)
        assert "数学订正错题" in text
        assert "主动帮助同学" in text
        # 维度中文名分组展示
        assert "智育成长" in text
        assert "品德发展" in text


def test_missing_image_file_skipped_without_error(tmp_path):
    """file_path 指向不存在文件 → 自动跳过，整体仍成 PDF。"""
    pdf = render_growth_album_pdf(
        _base_report(),
        comment={"status": "absent", "content": None},
        memories=[
            {"id": "m1", "image_path": "2026-08/missing.jpg",
             "file_path": str(tmp_path / "missing.jpg"), "caption": "不存在的照片"},
        ],
        growth_records=[],
        school_name="实验小学",
        student_name="张小明",
        term="2025-2026-1",
    )
    assert pdf.startswith(b"%PDF")
    if HAS_FITZ:
        assert "暂无成长照片" in _pdf_text(pdf)


def test_many_photos_render_grid_without_error(tmp_path):
    """多张照片 → 网格布局，仍正常成档（覆盖 3 列换行）。"""
    from PIL import Image

    pdfs = []
    for i in range(4):
        img = Image.new("RGB", (120, 90), (i * 50, 30, 120))
        p = tmp_path / f"photo_{i}.jpg"
        img.save(p, "JPEG")
        pdfs.append({"id": f"m{i}", "image_path": f"2026-08/photo_{i}.jpg",
                     "file_path": str(p), "caption": f"照片{i}"})

    pdf = render_growth_album_pdf(
        _base_report(),
        comment=_confirmed_comment(),
        memories=pdfs,
        growth_records=[],
        school_name="实验小学",
        student_name="张小明",
        term="2025-2026-1",
    )
    assert pdf.startswith(b"%PDF")
