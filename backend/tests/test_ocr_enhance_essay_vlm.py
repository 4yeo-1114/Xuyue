# -*- coding: utf-8 -*-
"""A7-B3 作文/参照 VLM 增强接线 + 配方收敛 · 单元测试。

覆盖：
1. essay_grading.baidu_essay_create_task：GRADING_OCR_ENHANCE=auto 时提交增强副本 base64；
   =off 时保持原始字节（不调用增强），行为与原来一致。
2. reference_vlm_grading.submit_paper_cut_vlm：GRADING_VLM_ENHANCE=true（1/true/yes/on）时
   payload enhance=true；默认 enhance=false（与原硬编码 False 一致）。
3. 配方收敛等价性：enhance_for_ocr(mode="auto") 与旧内联配方
   （ImageOps.autocontrast(cutoff=0.5) + Contrast.enhance(1.12) + Sharpness.enhance(1.25)
    + UnsharpMask(radius=1.0, percent=120, threshold=3)）像素级一致；
   _crop_to_data_url / _crop_regions_to_data_url 改为调用 enhance_for_ocr(mode="auto")。
"""

import base64
import os
from io import BytesIO

import pytest

from PIL import Image as PILImage
from PIL import ImageEnhance, ImageFilter, ImageOps

from app.grading import essay_grading
from app.grading import reference_vlm_grading
from app.grading.doc_convert import enhance_for_ocr

RED = (200, 20, 20)
GRAY = (180, 180, 180)


def _make_image(path, size=(80, 50), color=GRAY, fmt="JPEG"):
    img = PILImage.new("RGB", size, color)
    img.save(str(path), format=fmt)
    return img


def _decode_image(b64_or_bytes):
    if isinstance(b64_or_bytes, str):
        raw = base64.b64decode(b64_or_bytes)
    else:
        raw = b64_or_bytes
    return PILImage.open(BytesIO(raw)).convert("RGB")


def _assert_reddish(pixel, tol=10):
    assert abs(pixel[0] - RED[0]) <= tol, pixel
    assert abs(pixel[1] - RED[1]) <= tol, pixel
    assert abs(pixel[2] - RED[2]) <= tol, pixel


# ---------------------------------------------------------------- essay_grading

class _FakeEssayPost:
    def __init__(self, result=None):
        self.captured = {}
        self.result = result or {"result": {"task_id": "task-essay"}}

    def __call__(self, url, body):
        self.captured["url"] = url
        self.captured["payload"] = body
        return self.result


def test_essay_create_task_submits_enhanced_base64(monkeypatch, tmp_path):
    monkeypatch.setenv("GRADING_OCR_ENHANCE", "auto")
    img_path = tmp_path / "essay.png"
    _make_image(img_path, size=(80, 50), color=GRAY, fmt="PNG")

    fake_post = _FakeEssayPost()
    monkeypatch.setattr(essay_grading, "_post_json", fake_post)
    monkeypatch.setattr(essay_grading, "_baidu_access_token", lambda: "test-token")
    monkeypatch.setattr(
        essay_grading,
        "enhance_for_ocr",
        lambda img: PILImage.new("RGB", img.size, RED),
    )

    task_id = essay_grading.baidu_essay_create_task(str(img_path))
    assert task_id == "task-essay"

    submitted_img = _decode_image(fake_post.captured["payload"]["image"])
    assert submitted_img.size == (80, 50)
    _assert_reddish(submitted_img.getpixel((0, 0)))


def test_essay_create_task_env_off_keeps_original_bytes(monkeypatch, tmp_path):
    monkeypatch.setenv("GRADING_OCR_ENHANCE", "off")
    img_path = tmp_path / "essay.png"
    _make_image(img_path, size=(80, 50), color=GRAY, fmt="PNG")
    original_bytes = img_path.read_bytes()

    fake_post = _FakeEssayPost()
    monkeypatch.setattr(essay_grading, "_post_json", fake_post)
    monkeypatch.setattr(essay_grading, "_baidu_access_token", lambda: "test-token")

    # off 模式不应调用增强
    def boom(*_a, **_k):
        raise AssertionError("enhance_for_ocr should not be called when GRADING_OCR_ENHANCE=off")

    monkeypatch.setattr(essay_grading, "enhance_for_ocr", boom)

    task_id = essay_grading.baidu_essay_create_task(str(img_path))
    assert task_id == "task-essay"
    submitted = base64.b64decode(fake_post.captured["payload"]["image"])
    assert submitted == original_bytes


def test_essay_create_task_enhance_failure_falls_back_to_original_bytes(monkeypatch, tmp_path):
    """增强内部抛异常时应回退原始字节，不影响提交。"""
    monkeypatch.setenv("GRADING_OCR_ENHANCE", "auto")
    img_path = tmp_path / "essay.png"
    _make_image(img_path, size=(80, 50), color=GRAY, fmt="PNG")
    original_bytes = img_path.read_bytes()

    fake_post = _FakeEssayPost()
    monkeypatch.setattr(essay_grading, "_post_json", fake_post)
    monkeypatch.setattr(essay_grading, "_baidu_access_token", lambda: "test-token")

    def broken_enhance(*_a, **_k):
        raise RuntimeError("enhance exploded")

    monkeypatch.setattr(essay_grading, "enhance_for_ocr", broken_enhance)

    essay_grading.baidu_essay_create_task(str(img_path))
    submitted = base64.b64decode(fake_post.captured["payload"]["image"])
    assert submitted == original_bytes


# ---------------------------------------------------------------- submit_paper_cut_vlm

class _FakePostJson:
    def __init__(self, result=None):
        self.captured = {}
        self.result = result or {
            "result": {
                "qus_result": [
                    {"qus_id": 1, "location": {"qus_location": [{"x": 1, "y": 1, "w": 5, "h": 5}]}}
                ]
            }
        }

    def __call__(self, url, payload, **kwargs):
        self.captured["url"] = url
        self.captured["payload"] = payload
        return self.result


def _run_submit_paper_cut(monkeypatch, tmp_path):
    image_path = tmp_path / "paper.jpg"
    Image = PILImage
    Image.new("RGB", (20, 20), "white").save(image_path)

    fake_post = _FakePostJson()
    monkeypatch.setattr(reference_vlm_grading, "_build_url", lambda url: url)
    monkeypatch.setattr(reference_vlm_grading, "_post_json", fake_post)
    monkeypatch.setattr(reference_vlm_grading, "_ensure_image_for_vlm", lambda p: p)

    reference_vlm_grading.submit_paper_cut_vlm(str(image_path))
    return fake_post.captured["payload"]


def test_submit_paper_cut_vlm_enhance_env_true(monkeypatch, tmp_path):
    monkeypatch.setenv("GRADING_VLM_ENHANCE", "1")
    payload = _run_submit_paper_cut(monkeypatch, tmp_path)
    assert payload["only_split"] is True
    assert payload["enhance"] is True


def test_submit_paper_cut_vlm_enhance_env_true_variants(monkeypatch, tmp_path):
    for value in ("true", "yes", "on", "True", "ON"):
        monkeypatch.setenv("GRADING_VLM_ENHANCE", value)
        payload = _run_submit_paper_cut(monkeypatch, tmp_path)
        assert payload["enhance"] is True, value


def test_submit_paper_cut_vlm_enhance_default_false(monkeypatch, tmp_path):
    monkeypatch.delenv("GRADING_VLM_ENHANCE", raising=False)
    payload = _run_submit_paper_cut(monkeypatch, tmp_path)
    assert payload["only_split"] is True
    assert payload["enhance"] is False


def test_submit_paper_cut_vlm_enhance_env_off_false(monkeypatch, tmp_path):
    monkeypatch.setenv("GRADING_VLM_ENHANCE", "0")
    payload = _run_submit_paper_cut(monkeypatch, tmp_path)
    assert payload["enhance"] is False


# ---------------------------------------------------------------- 配方收敛等价性

def _legacy_crop_enhance(img):
    """旧内联配方（reference_vlm_grading 原实现），用于等价性对照。"""
    out = img.convert("RGB")
    out = ImageOps.autocontrast(out, cutoff=0.5)
    out = ImageEnhance.Contrast(out).enhance(1.12)
    out = ImageEnhance.Sharpness(out).enhance(1.25)
    out = out.filter(ImageFilter.UnsharpMask(radius=1.0, percent=120, threshold=3))
    return out


def _gradient_image(size=(90, 60)):
    img = PILImage.new("RGB", size, (0, 0, 0))
    px = img.load()
    for x in range(size[0]):
        v = int(30 + x * (200 / max(1, size[0] - 1)))
        for y in range(size[1]):
            px[x, y] = (v, int(v * 0.7), int(v * 0.3))
    return img


def test_enhance_for_ocr_auto_equals_legacy_crop_recipe(monkeypatch):
    """增强配方收敛：enhance_for_ocr(mode=auto) 像素级等于旧内联配方。"""
    monkeypatch.setenv("GRADING_OCR_ENHANCE", "auto")
    img = _gradient_image()
    shared = enhance_for_ocr(img, mode="auto")
    legacy = _legacy_crop_enhance(img)
    assert shared.size == legacy.size == img.size
    assert shared.tobytes() == legacy.tobytes()


def test_enhance_for_ocr_auto_equals_legacy_on_varied_images(monkeypatch):
    """多张不同内容的图片下收敛配方仍与旧配方一致。"""
    monkeypatch.setenv("GRADING_OCR_ENHANCE", "auto")
    cases = [
        PILImage.new("RGB", (64, 48), (40, 90, 160)),
        PILImage.new("RGB", (64, 48), (230, 220, 210)),
        _gradient_image((120, 80)),
    ]
    for img in cases:
        shared = enhance_for_ocr(img, mode="auto")
        legacy = _legacy_crop_enhance(img)
        assert shared.tobytes() == legacy.tobytes()


def test_crop_to_data_url_calls_enhance_for_ocr_auto(monkeypatch):
    monkeypatch.setenv("GRADING_OCR_ENHANCE", "auto")
    image = _gradient_image((320, 180))
    calls = []

    def fake_enhance(img, mode="auto"):
        calls.append(mode)
        return img  # 不做真实增强，仅验证接线

    monkeypatch.setattr(reference_vlm_grading, "enhance_for_ocr", fake_enhance)

    data_url, payload = reference_vlm_grading._crop_to_data_url(
        image, [0, 0, 320, 180], pad=0
    )
    assert data_url.startswith("data:image/jpeg;base64,")
    assert payload
    assert calls == ["auto"]


def test_crop_regions_to_data_url_calls_enhance_for_ocr_auto(monkeypatch):
    monkeypatch.setenv("GRADING_OCR_ENHANCE", "auto")
    image = _gradient_image((400, 300))
    calls = []

    def fake_enhance(img, mode="auto"):
        calls.append(mode)
        return img

    monkeypatch.setattr(reference_vlm_grading, "enhance_for_ocr", fake_enhance)

    # 两个不相交区域走 for 循环内的增强路径
    data_url, payload = reference_vlm_grading._crop_regions_to_data_url(
        image, [[0, 0, 100, 80], [200, 150, 300, 240]]
    )
    assert data_url.startswith("data:image/jpeg;base64,")
    assert payload
    assert calls == ["auto", "auto"]
