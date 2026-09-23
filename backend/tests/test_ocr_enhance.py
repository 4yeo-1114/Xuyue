# -*- coding: utf-8 -*-
"""A7-B2 共享图像预处理 enhance_for_ocr + OCR 参数透传 · 单元测试。

覆盖：
1. enhance_for_ocr：同尺寸断言、mode=off 原样返回、auto/aggressive 正常返回、
   env GRADING_OCR_ENHANCE=off 时缺省 mode 不增强、异常回退原图。
2. run_ocr：增强副本用于提交、返回 pil_image 为原图、unwarp/orientation env 开关
   正确映射到 optionalPayload。
3. baidu submit_task：增强副本 base64 提交、GRADING_BAIDU_ENHANCE=1 时 payload 含
   enhance、默认不传、GRADING_OCR_ENHANCE=off 保持原始字节。
"""

import base64
import json
import os
from io import BytesIO

import pytest

from PIL import Image as PILImage

from app.grading import baidu_grading
from app.grading import ocr as ocr_module
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
    """JPEG 有损压缩允许小幅偏移的红色断言。"""
    assert abs(pixel[0] - RED[0]) <= tol, pixel
    assert abs(pixel[1] - RED[1]) <= tol, pixel
    assert abs(pixel[2] - RED[2]) <= tol, pixel


# ---------------------------------------------------------------- enhance_for_ocr

def test_enhance_for_ocr_keeps_size_all_modes():
    img = PILImage.new("RGB", (120, 80), GRAY)
    for mode in ("off", "auto", "aggressive"):
        out = enhance_for_ocr(img, mode=mode)
        assert out.size == (120, 80), mode
        assert out.size == img.size, mode


def test_enhance_for_ocr_off_returns_same_object():
    img = PILImage.new("RGB", (64, 48), GRAY)
    out = enhance_for_ocr(img, mode="off")
    assert out is img


def test_enhance_for_ocr_auto_returns_copy_no_exception():
    img = PILImage.new("RGB", (64, 48), GRAY)
    out = enhance_for_ocr(img, mode="auto")
    assert out is not img
    assert isinstance(out, PILImage.Image)
    assert out.mode == "RGB"


def test_enhance_for_ocr_aggressive_returns_no_exception():
    img = PILImage.new("RGB", (64, 48), GRAY)
    out = enhance_for_ocr(img, mode="aggressive")
    assert out is not img
    assert isinstance(out, PILImage.Image)
    assert out.mode == "RGB"


def test_enhance_for_ocr_non_rgb_converted_to_rgb():
    rgba = PILImage.new("RGBA", (40, 30), (100, 150, 200, 128))
    out = enhance_for_ocr(rgba, mode="auto")
    assert out.size == (40, 30)
    assert out.mode == "RGB"
    gray = PILImage.new("L", (20, 20), 128)
    out_gray = enhance_for_ocr(gray, mode="aggressive")
    assert out_gray.size == (20, 20)
    assert out_gray.mode == "RGB"


def test_enhance_for_ocr_env_off_disables_default_mode(monkeypatch):
    monkeypatch.setenv("GRADING_OCR_ENHANCE", "off")
    img = PILImage.new("RGB", (40, 30), GRAY)
    out = enhance_for_ocr(img)  # mode 缺省 → env off
    assert out is img


def test_enhance_for_ocr_env_auto_and_aggressive(monkeypatch):
    monkeypatch.setenv("GRADING_OCR_ENHANCE", "auto")
    img = PILImage.new("RGB", (40, 30), GRAY)
    out = enhance_for_ocr(img)
    assert out.size == (40, 30)
    assert out is not img

    monkeypatch.setenv("GRADING_OCR_ENHANCE", "aggressive")
    out_agg = enhance_for_ocr(img)
    assert out_agg.size == (40, 30)
    assert isinstance(out_agg, PILImage.Image)


def test_enhance_for_ocr_invalid_mode_falls_back_to_original():
    img = PILImage.new("RGB", (40, 30), GRAY)
    out = enhance_for_ocr(img, mode="bogus")
    assert out is img


def test_enhance_for_ocr_aggressive_actually_changes_pixels():
    # 灰度渐变图：aggressive 的自适应对比度拉伸应产生与 auto 不同的像素
    def _gradient():
        img = PILImage.new("RGB", (60, 40), (0, 0, 0))
        px = img.load()
        for x in range(img.width):
            v = int(40 + x * (200 / (img.width - 1)))
            for y in range(img.height):
                px[x, y] = (v, v, v)
        return img

    img = _gradient()
    auto_out = enhance_for_ocr(img, mode="auto")
    agg_out = enhance_for_ocr(img, mode="aggressive")
    assert auto_out.size == agg_out.size == img.size
    assert auto_out.tobytes() != agg_out.tobytes()


# ---------------------------------------------------------------- run_ocr

class _Resp:
    def __init__(self, status_code=200, json_body=None, text=""):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text

    def json(self):
        return self._json


class _FakeRequests:
    """同时模拟 ocr 模块的 requests.post（提交）与 requests.get（轮询 + 下载 jsonl）。"""

    def __init__(self, jsonl_text):
        self.jsonl_text = jsonl_text
        self.submitted_files = []
        self.submitted_data = []

    def post(self, url, headers=None, data=None, files=None, timeout=None):
        self.submitted_files.append(files)
        self.submitted_data.append(data)
        return _Resp(200, {"data": {"jobId": "job-123"}})

    def get(self, url, headers=None, timeout=None):
        if "jobs/" in url:
            return _Resp(
                200,
                {
                    "data": {
                        "state": "done",
                        "resultUrl": {"jsonUrl": "http://example.com/result.jsonl"},
                    }
                },
            )
        return _Resp(text=self.jsonl_text)


def _fake_jsonl(text="hello"):
    return json.dumps(
        {
            "result": {
                "layoutParsingResults": [
                    {
                        "prunedResult": {
                            "parsing_res_list": [
                                {
                                    "block_content": text,
                                    "block_label": "text",
                                    "block_bbox": [10, 20, 30, 40],
                                }
                            ]
                        }
                    }
                ]
            }
        }
    )


def test_run_ocr_submits_enhanced_copy_and_returns_original_image(monkeypatch, tmp_path):
    monkeypatch.setenv("GRADING_OCR_ENHANCE", "auto")
    img_path = tmp_path / "paper.png"
    _make_image(img_path, size=(80, 50), color=GRAY, fmt="PNG")

    fake = _FakeRequests(jsonl_text=_fake_jsonl())
    monkeypatch.setattr(ocr_module, "requests", fake)
    monkeypatch.setattr(
        ocr_module,
        "enhance_for_ocr",
        lambda img: PILImage.new("RGB", img.size, RED),
    )

    blocks, pil_image = ocr_module.run_ocr(str(img_path))

    # 增强副本被用于提交：提交的图片是红色（增强副本）
    assert fake.submitted_files
    files = fake.submitted_files[0]["file"]
    submitted_img = _decode_image(files[1].getvalue())
    assert submitted_img.size == (80, 50)
    _assert_reddish(submitted_img.getpixel((0, 0)))

    # 返回的 pil_image 为原图（灰色，非增强副本）
    assert pil_image.size == (80, 50)
    assert pil_image.getpixel((0, 0)) != RED

    # OCR 结果正常解析
    assert blocks and blocks[0]["text"] == "hello"
    assert blocks[0]["bbox"] == [10, 20, 30, 40]


def test_run_ocr_default_optional_payload(monkeypatch, tmp_path):
    monkeypatch.delenv("GRADING_PADDLE_ORIENTATION", raising=False)
    monkeypatch.delenv("GRADING_PADDLE_UNWARP", raising=False)
    img_path = tmp_path / "paper.jpg"
    _make_image(img_path)

    fake = _FakeRequests(jsonl_text=_fake_jsonl())
    monkeypatch.setattr(ocr_module, "requests", fake)

    ocr_module.run_ocr(str(img_path))
    payload = json.loads(fake.submitted_data[0]["optionalPayload"])
    assert payload["useDocOrientationClassify"] is False
    assert payload["useDocUnwarping"] is False
    assert payload["useChartRecognition"] is False


def test_run_ocr_orientation_unwarp_env_switches(monkeypatch, tmp_path):
    monkeypatch.setenv("GRADING_PADDLE_ORIENTATION", "0")
    monkeypatch.setenv("GRADING_PADDLE_UNWARP", "0")
    img_path = tmp_path / "paper.jpg"
    _make_image(img_path)

    fake = _FakeRequests(jsonl_text=_fake_jsonl())
    monkeypatch.setattr(ocr_module, "requests", fake)

    ocr_module.run_ocr(str(img_path))
    payload = json.loads(fake.submitted_data[0]["optionalPayload"])
    assert payload["useDocOrientationClassify"] is False
    assert payload["useDocUnwarping"] is False
    assert payload["useChartRecognition"] is False

    # 显式 =1 可重新开启（用于倾斜/卷曲的拍照件）
    monkeypatch.setenv("GRADING_PADDLE_ORIENTATION", "1")
    monkeypatch.setenv("GRADING_PADDLE_UNWARP", "1")
    fake2 = _FakeRequests(jsonl_text=_fake_jsonl())
    monkeypatch.setattr(ocr_module, "requests", fake2)
    ocr_module.run_ocr(str(img_path))
    payload = json.loads(fake2.submitted_data[0]["optionalPayload"])
    assert payload["useDocOrientationClassify"] is True
    assert payload["useDocUnwarping"] is True


# ---------------------------------------------------------------- baidu submit_task

class _FakePostJson:
    def __init__(self, result=None):
        self.captured = {}
        self.result = result or {"result": {"task_id": "task-1"}}

    def __call__(self, url, payload, limiter=None):
        self.captured["url"] = url
        self.captured["payload"] = payload
        return self.result


def test_submit_task_submits_enhanced_base64(monkeypatch, tmp_path):
    monkeypatch.setenv("GRADING_OCR_ENHANCE", "auto")
    monkeypatch.setenv("GRADING_BAIDU_ENHANCE", "")
    monkeypatch.setenv("GRADING_BAIDU_DETECT_DIRECTION", "")
    img_path = tmp_path / "paper.png"
    _make_image(img_path, size=(80, 50), color=GRAY, fmt="PNG")

    fake_post = _FakePostJson()
    monkeypatch.setattr(baidu_grading, "_post_json", fake_post)
    monkeypatch.setattr(baidu_grading, "_build_url", lambda url: url)
    monkeypatch.setattr(
        baidu_grading,
        "enhance_for_ocr",
        lambda img: PILImage.new("RGB", img.size, RED),
    )

    task_id = baidu_grading.submit_task(str(img_path))
    assert task_id == "task-1"

    submitted_img = _decode_image(fake_post.captured["payload"]["image"])
    assert submitted_img.size == (80, 50)
    _assert_reddish(submitted_img.getpixel((0, 0)))

    # 默认不透传 baidu 侧开关
    assert "enhance" not in fake_post.captured["payload"]
    assert "detect_direction" not in fake_post.captured["payload"]


def test_submit_task_env_off_keeps_original_bytes(monkeypatch, tmp_path):
    monkeypatch.setenv("GRADING_OCR_ENHANCE", "off")
    img_path = tmp_path / "paper.png"
    _make_image(img_path, size=(80, 50), color=GRAY, fmt="PNG")
    original_bytes = img_path.read_bytes()

    fake_post = _FakePostJson()
    monkeypatch.setattr(baidu_grading, "_post_json", fake_post)
    monkeypatch.setattr(baidu_grading, "_build_url", lambda url: url)

    # off 模式不应调用增强
    def boom(*_a, **_k):
        raise AssertionError("enhance_for_ocr should not be called when GRADING_OCR_ENHANCE=off")

    monkeypatch.setattr(baidu_grading, "enhance_for_ocr", boom)

    baidu_grading.submit_task(str(img_path))
    submitted = base64.b64decode(fake_post.captured["payload"]["image"])
    assert submitted == original_bytes


def test_submit_task_baidu_enhance_and_detect_direction_passthrough(monkeypatch, tmp_path):
    monkeypatch.setenv("GRADING_OCR_ENHANCE", "off")
    monkeypatch.setenv("GRADING_BAIDU_ENHANCE", "1")
    monkeypatch.setenv("GRADING_BAIDU_DETECT_DIRECTION", "1")
    img_path = tmp_path / "paper.jpg"
    _make_image(img_path)

    fake_post = _FakePostJson()
    monkeypatch.setattr(baidu_grading, "_post_json", fake_post)
    monkeypatch.setattr(baidu_grading, "_build_url", lambda url: url)

    baidu_grading.submit_task(str(img_path))
    payload = fake_post.captured["payload"]
    assert payload["enhance"] is True
    assert payload["detect_direction"] is True


def test_submit_task_baidu_default_not_passed(monkeypatch, tmp_path):
    monkeypatch.setenv("GRADING_OCR_ENHANCE", "off")
    monkeypatch.setenv("GRADING_BAIDU_ENHANCE", "")
    monkeypatch.setenv("GRADING_BAIDU_DETECT_DIRECTION", "")
    img_path = tmp_path / "paper.jpg"
    _make_image(img_path)

    fake_post = _FakePostJson()
    monkeypatch.setattr(baidu_grading, "_post_json", fake_post)
    monkeypatch.setattr(baidu_grading, "_build_url", lambda url: url)

    baidu_grading.submit_task(str(img_path))
    payload = fake_post.captured["payload"]
    assert "enhance" not in payload
    assert "detect_direction" not in payload
