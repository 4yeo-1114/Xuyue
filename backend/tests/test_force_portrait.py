# -*- coding: utf-8 -*-
"""台账#8 复印机横向扫描摆正：上传进门把宽>高的竖版卷转正（1=顺时针 90°、2=逆时针 90°）。

留痕印记是按画面正向画的字形，图横着、字正着 = 印记相对内容歪 90°。
在上传进门转正后，下游（落点、印记、打印、PDF）全部按设计工作。
"""
from __future__ import annotations

import os

from PIL import Image

from app.grading import doc_convert


def test_force_turn_parsing(monkeypatch):
    for raw, want in (
        ("1", 1),
        ("true", 1),
        ("YES", 1),
        ("on", 1),
        ("cw", 1),
        ("2", 2),
        ("ccw", 2),
        ("0", 0),
        ("off", 0),
        ("junk", 0),
    ):
        monkeypatch.setenv("GRADING_UPLOAD_FORCE_PORTRAIT", raw)
        assert doc_convert._force_portrait_turn() == want, raw


def test_force_turn_settings_fallback(monkeypatch):
    """环境变量没配时读 config.settings（.env 的键 os.environ 看不见）。"""
    from types import SimpleNamespace

    monkeypatch.delenv("GRADING_UPLOAD_FORCE_PORTRAIT", raising=False)
    monkeypatch.setattr(
        "app.config.settings",
        SimpleNamespace(GRADING_UPLOAD_FORCE_PORTRAIT="2"),
    )
    assert doc_convert._force_portrait_turn() == 2


def test_force_turn_env_overrides_settings(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("GRADING_UPLOAD_FORCE_PORTRAIT", "1")
    monkeypatch.setattr(
        "app.config.settings",
        SimpleNamespace(GRADING_UPLOAD_FORCE_PORTRAIT="2"),
    )
    assert doc_convert._force_portrait_turn() == 1


def _mk_landscape(path):
    """200×100 横图，左上角 10×10 红块当方向标（PNG 无损，不惧 JPEG 压缩）。"""
    im = Image.new("RGB", (200, 100), "white")
    for x in range(10):
        for y in range(10):
            im.putpixel((x, y), (255, 0, 0))
    im.save(path)


def _red_center(im):
    w, h = im.size
    sx = sy = 0
    n = 0
    for x in range(w):
        for y in range(h):
            r, g, b = im.getpixel((x, y))
            if r > 180 and g < 80 and b < 80:
                sx += x
                sy += y
                n += 1
    if not n:
        return None
    return (sx / n, sy / n)


def test_landscape_rotated_clockwise_by_default_path(monkeypatch, tmp_path):
    """1=顺时针（rotate(-90)）：左上角标记转后落在右上角。"""
    p = tmp_path / "land.png"
    _mk_landscape(p)
    monkeypatch.setattr(doc_convert, "detect_image_orientation", lambda im: 0)
    monkeypatch.setenv("GRADING_UPLOAD_FORCE_PORTRAIT", "1")
    assert doc_convert.normalize_uploaded_image_orientation(p) is True
    with Image.open(p) as im:
        assert im.size == (100, 200)
        cx, cy = _red_center(im)
        assert cx > 70 and cy < 30, (cx, cy)


def test_landscape_rotated_counterclockwise(monkeypatch, tmp_path):
    """2=逆时针（rotate(90)）：左上角标记转后落在左下角。"""
    p = tmp_path / "land.png"
    _mk_landscape(p)
    monkeypatch.setattr(doc_convert, "detect_image_orientation", lambda im: 0)
    monkeypatch.setenv("GRADING_UPLOAD_FORCE_PORTRAIT", "2")
    assert doc_convert.normalize_uploaded_image_orientation(p) is True
    with Image.open(p) as im:
        assert im.size == (100, 200)
        cx, cy = _red_center(im)
        assert cx < 30 and cy > 170, (cx, cy)


def test_landscape_untouched_when_off(monkeypatch, tmp_path):
    p = tmp_path / "land.png"
    _mk_landscape(p)
    monkeypatch.setattr(doc_convert, "detect_image_orientation", lambda im: 0)
    monkeypatch.setenv("GRADING_UPLOAD_FORCE_PORTRAIT", "0")
    assert doc_convert.normalize_uploaded_image_orientation(p) is True
    with Image.open(p) as im:
        assert im.size == (200, 100)
        cx, cy = _red_center(im)
        assert cx < 30 and cy < 30, (cx, cy)


def test_portrait_untouched_by_force(monkeypatch, tmp_path):
    p = tmp_path / "port.png"
    im = Image.new("RGB", (100, 200), "white")
    for x in range(10):
        for y in range(10):
            im.putpixel((x, y), (255, 0, 0))
    im.save(p)
    monkeypatch.setattr(doc_convert, "detect_image_orientation", lambda im: 0)
    monkeypatch.setenv("GRADING_UPLOAD_FORCE_PORTRAIT", "1")
    assert doc_convert.normalize_uploaded_image_orientation(p) is True
    with Image.open(p) as out:
        assert out.size == (100, 200)
        cx, cy = _red_center(out)
        assert cx < 30 and cy < 30, (cx, cy)
