# -*- coding: utf-8 -*-
"""进门压图单测——1016 不花钱项①。

验证：①大图压缩变小且同尺寸 ②小图不动 ③方向修正过必写回（哪怕变大）
④压不小保留原文件字节（never-grow）⑤PNG 无损 optimize 不改尺寸 ⑥质量可配。
"""
import io

import pytest

from app.grading import doc_convert


pytestmark = pytest.mark.skipif(
    not doc_convert.Image, reason="Pillow 未安装"
)


@pytest.fixture(autouse=True)
def _no_baidu(monkeypatch):
    """单测不打百度方向检测（网络旁路）。"""
    monkeypatch.setenv("GRADING_UPLOAD_AUTO_ROTATE", "off")
    monkeypatch.delenv("GRADING_UPLOAD_FORCE_PORTRAIT", raising=False)


def _make_jpeg(path, size=(1600, 1200), quality=95, orientation=None):
    import random

    from PIL import Image

    # 随机噪声图：JPEG 压不动，q95 存盘必然 >300KB，q85 重编码必有收益
    rng = random.Random(42)
    im = Image.new("RGB", size)
    im.putdata(
        [(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(size[0] * size[1])]
    )
    kwargs = {"quality": quality}
    if orientation is not None:
        exif = Image.Exif()
        exif[0x0112] = orientation
        kwargs["exif"] = exif
    im.save(str(path), format="JPEG", **kwargs)
    return path


def test_large_jpeg_compressed_same_size(tmp_path):
    p = _make_jpeg(tmp_path / "big.jpg")
    from PIL import Image

    before = p.stat().st_size
    with Image.open(p) as im:
        w0, h0 = im.size
    assert doc_convert.normalize_uploaded_image_orientation(p)
    after = p.stat().st_size
    assert after < before, f"大图应压小: {before} -> {after}"
    with Image.open(p) as im:
        assert im.size == (w0, h0), "同尺寸重编码，绝不缩放（bbox 归一化依赖磁盘尺寸）"


def test_small_jpeg_untouched(tmp_path):
    p = tmp_path / "tiny.jpg"
    from PIL import Image

    Image.new("RGB", (200, 150), (10, 20, 30)).save(str(p), format="JPEG", quality=95)
    before_bytes = p.read_bytes()
    before = p.stat().st_size
    assert before < doc_convert._UPLOAD_COMPRESS_MIN_BYTES
    assert doc_convert.normalize_uploaded_image_orientation(p)
    assert p.stat().st_size == before
    assert p.read_bytes() == before_bytes, "小图（<300KB）不动原文件"


def test_exif_rotation_forces_writeback(tmp_path):
    """EXIF 方向标签落实到像素后必须写回——哪怕压缩结果比原文件大。"""
    import io

    import app.grading.doc_convert as dc

    p = _make_jpeg(tmp_path / "exif.jpg", size=(400, 300), orientation=6)
    before = p.stat().st_size

    def fake_bigger_but_valid(rgb, ext):
        # 合法 JPEG + 尾部填充：保证比原文件大，但 PIL 仍能打开（尾部字节被忽略）
        buf = io.BytesIO()
        rgb.save(buf, format="JPEG", quality=95)
        return buf.getvalue() + b"\0" * (before + 1)

    orig = dc._compress_normalized_image
    dc._compress_normalized_image = fake_bigger_but_valid
    try:
        assert dc.normalize_uploaded_image_orientation(p)
    finally:
        dc._compress_normalized_image = orig
    assert p.stat().st_size > before, "rotated=True 时即便变大也必须写回"
    from PIL import Image

    with Image.open(p) as im:
        assert im.size == (300, 400), "EXIF orientation=6 应把 400x300 转成 300x400"
        assert not im.getexif().get(0x0112), "方向标签应已落实并清除"


def test_never_grow_keeps_original_bytes(tmp_path):
    """没动过方向且压不小 → 原文件字节原样保留（避免二次有损反而变大）。"""
    p = _make_jpeg(tmp_path / "flat.jpg", size=(1600, 1200), quality=95)
    before = p.stat().st_size
    assert before >= doc_convert._UPLOAD_COMPRESS_MIN_BYTES, "测试图必须过 300KB 门槛才走到压缩分支"
    before_bytes = p.read_bytes()

    import app.grading.doc_convert as dc

    orig = dc._compress_normalized_image
    dc._compress_normalized_image = lambda rgb, ext: b"y" * (before + 1)
    try:
        assert dc.normalize_uploaded_image_orientation(p)
    finally:
        dc._compress_normalized_image = orig
    assert p.read_bytes() == before_bytes, "压不小且无旋转，必须保留原文件字节"


def test_png_same_size_and_no_grow(tmp_path):
    import random

    p = tmp_path / "doc.png"
    from PIL import Image

    # 噪声 PNG 压不动，正好走 never-grow 分支；并过 300KB 门槛
    rng = random.Random(7)
    im = Image.new("RGB", (700, 700))
    im.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(700 * 700)])
    im.save(str(p), format="PNG")
    before = p.stat().st_size
    assert before >= doc_convert._UPLOAD_COMPRESS_MIN_BYTES, "噪声 PNG 应超 300KB"

    from PIL import Image as I

    with I.open(p) as im:
        w0, h0 = im.size
    assert doc_convert.normalize_uploaded_image_orientation(p)
    assert p.stat().st_size <= before, "PNG 压不小则保留原字节（never-grow）"
    with I.open(p) as im:
        assert im.size == (w0, h0)


def test_quality_env_respected(monkeypatch):
    monkeypatch.setenv("GRADING_UPLOAD_JPEG_QUALITY", "60")
    assert doc_convert._upload_jpeg_quality() == 60
    monkeypatch.setenv("GRADING_UPLOAD_JPEG_QUALITY", "5")
    assert doc_convert._upload_jpeg_quality() == 60, "下限 60 防误配伤画质"
    monkeypatch.setenv("GRADING_UPLOAD_JPEG_QUALITY", "200")
    assert doc_convert._upload_jpeg_quality() == 95, "上限 95"
    monkeypatch.setenv("GRADING_UPLOAD_JPEG_QUALITY", "abc")
    assert doc_convert._upload_jpeg_quality() == 85, "非法值回落默认 85"
