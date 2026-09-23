# -*- coding: utf-8 -*-
"""Paddle OCR 远程 API 调用，返回试卷各文字块 bbox 与 PIL 图。"""
import json
import os
import time
from io import BytesIO

try:
    from PIL import Image
except ImportError:
    Image = None
try:
    import requests
except ImportError:
    requests = None

try:
    from app.grading.doc_convert import enhance_for_ocr
except Exception:  # pragma: no cover - 导入失败则提交时不增强（旁路降级）
    enhance_for_ocr = None

JOB_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
PADDLE_OCR_TOKEN = os.environ.get("PADDLE_OCR_TOKEN", "93e5e43194e7da7f15f28c1078bc862d2d6a65bb")
MODEL = "PaddleOCR-VL-1.5"


def _env_ocr_flag(name: str, default: bool) -> bool:
    """读环境变量布尔开关：0/false/no/off → False；1/true/yes/on → True；其余走默认值。"""
    val = os.environ.get(name, "").strip().lower()
    if val in ("0", "false", "no", "off"):
        return False
    if val in ("1", "true", "yes", "on"):
        return True
    return default


def run_ocr(image_path: str, max_wait_seconds: int | None = None):
    """返回 (blocks, pil_image)。pil_image 为原图（未增强），供批改裁图用，避免坐标漂移。

    轮询超时默认从环境变量 GRADING_OCR_TIMEOUT 读取（默认 120 秒）。
    PaddleOCR-VL-1.5 是视觉大模型，整张试卷在开启方向分类 + 去卷曲时经常超过 30 秒。
    为提速，方向分类 + 去卷曲两项默认关闭（GRADING_PADDLE_ORIENTATION /
    GRADING_PADDLE_UNWARP 默认 0）；上传入口已用 normalize_uploaded_image_orientation
    修正 EXIF 旋转，仅当确有倾斜/卷曲的拍照件时才用环境变量 =1 重新开启。

    OCR 提交前用 enhance_for_ocr 对同尺寸增强副本做预处理（按 GRADING_OCR_ENHANCE，默认 auto），
    增强图仅用于提交，返回的 pil_image 始终是原图，保证 bbox 坐标与调用方裁图语义一致。
    注意：useDocUnwarping 开启可能改变 OCR 侧 bbox 坐标语义，若开启后批改裁图异常，
    可用环境变量 GRADING_PADDLE_UNWARP=0 关回（安全阀）。
    """
    if not requests or not Image:
        raise RuntimeError("需要安装 requests 和 Pillow: pip install requests Pillow")
    if max_wait_seconds is None:
        try:
            max_wait_seconds = int(os.environ.get("GRADING_OCR_TIMEOUT", "120"))
        except ValueError:
            max_wait_seconds = 120
    path = os.path.abspath(image_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"图片不存在: {path}")
    with open(path, "rb") as f:
        original_image_data = f.read()
    original_img = Image.open(BytesIO(original_image_data)).convert("RGB")
    headers = {"Authorization": f"bearer {PADDLE_OCR_TOKEN}"}
    optional_payload = {
        "useDocOrientationClassify": _env_ocr_flag("GRADING_PADDLE_ORIENTATION", default=False),
        "useDocUnwarping": _env_ocr_flag("GRADING_PADDLE_UNWARP", default=False),
        "useChartRecognition": False,
    }
    data = {"model": MODEL, "optionalPayload": json.dumps(optional_payload)}
    # OCR 用增强副本提交（同尺寸增强，不缩放不裁剪，bbox 坐标仍与原始图对齐）
    ocr_img = enhance_for_ocr(original_img) if enhance_for_ocr else original_img
    submit_buffer = BytesIO()
    ocr_img.save(submit_buffer, format="JPEG", quality=95)
    submit_buffer.seek(0)
    job_response = requests.post(
        JOB_URL,
        headers=headers,
        data=data,
        files={"file": ("image.jpg", submit_buffer, "image/jpeg")},
        timeout=10,
    )
    if job_response.status_code != 200:
        raise RuntimeError(f"OCR 提交失败: {job_response.status_code} {job_response.text[:200]}")
    job_id = job_response.json().get("data", {}).get("jobId")
    if not job_id:
        raise RuntimeError("OCR 未返回 jobId")
    deadline = time.time() + max_wait_seconds
    jsonl_url = None
    while time.time() < deadline:
        res = requests.get(f"{JOB_URL}/{job_id}", headers=headers, timeout=5)
        state = res.json().get("data", {}).get("state")
        if state == "done":
            jsonl_url = res.json().get("data", {}).get("resultUrl", {}).get("jsonUrl")
            break
        if state == "failed":
            raise RuntimeError("OCR 任务失败")
        time.sleep(2)
    if not jsonl_url:
        raise RuntimeError("OCR 超时未返回结果")
    jsonl_response = requests.get(jsonl_url, timeout=10)
    lines = [ln.strip() for ln in jsonl_response.text.strip().split("\n") if ln.strip()]
    blocks = []
    total_boxes = 0
    for line in lines:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        result = data.get("result", {})
        layout_results = result.get("layoutParsingResults", [])
        for page_res in layout_results:
            pruned = page_res.get("prunedResult", {})
            parsing_list = pruned.get("parsing_res_list", [])
            for block in parsing_list:
                text = block.get("block_content", "")
                label_type = block.get("block_label", "text")
                polygon_points = block.get("block_polygon_points", [])
                bbox = block.get("block_bbox", [])
                if polygon_points:
                    points = [(float(p[0]), float(p[1])) for p in polygon_points]
                    right_bottom_x, right_bottom_y = int(points[2][0]), int(points[2][1])
                    xs, ys = [p[0] for p in points], [p[1] for p in points]
                    x_min, y_min = int(min(xs)), int(min(ys))
                    x_max, y_max = int(max(xs)), int(max(ys))
                elif bbox and len(bbox) == 4:
                    x_min, y_min, x_max, y_max = [int(x) for x in bbox]
                    right_bottom_x, right_bottom_y = x_max, y_max
                else:
                    continue
                total_boxes += 1
                blocks.append({
                    "index": total_boxes,
                    "bbox": [x_min, y_min, x_max, y_max],
                    "right_bottom": (right_bottom_x, right_bottom_y),
                    "text": text,
                    "label": label_type,
                })
    return blocks, original_img
