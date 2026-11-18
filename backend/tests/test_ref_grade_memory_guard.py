# -*- coding: utf-8 -*-
"""1015 冻死防线单测：参照批改单飞闸 + 送 VLM 前同尺寸压图。

背景：2026-10-15 生产两次 grade-by-reference 连点 → 双批次×8 线程整页 base64
→ 8G 内存顶穿（swappiness=0）→ 整机用户态僵死。防线：
  1. 同文件夹单飞闸（同参数幂等返回在跑 job，异参数 409）
  2. 送 VLM 前同尺寸重编码压图（坐标空间不变，bbox 归一化零影响）
  3. REFERENCE_VLM_BAIDU_WORKERS 默认 8→4
"""
import base64
import io
import threading
from pathlib import Path

import pytest
from PIL import Image

from app.grading import reference_vlm_grading
from app.grading.router import (
    _find_active_ref_job_locked,
    _ref_grade_lock,
    _ref_grade_results,
    _ref_grade_stop_events,
)


# ---------------------------------------------------------------- 压图

def _make_jpeg(path: Path, size=(1600, 2000), quality=95):
    """生成一张足够大（>300KB）的模拟卷面 JPEG。随机噪声 JPEG 压不动，体积稳定超阈值。"""
    import os
    w, h = size
    img = Image.frombytes("RGB", size, os.urandom(w * h * 3))
    img.save(path, format="JPEG", quality=quality)
    return path


def test_encode_image_small_files_pass_through(tmp_path):
    """<300KB 直接原字节 base64，不折腾重编码。"""
    small = tmp_path / "small.jpg"
    Image.new("RGB", (20, 20), "white").save(small)
    encoded = reference_vlm_grading._encode_image_for_vlm(str(small))
    assert base64.b64decode(encoded) == small.read_bytes()


def test_encode_image_large_jpeg_shrinks_and_keeps_dimensions(tmp_path):
    """大图同尺寸重编码：体积变小、宽高不变（bbox 归一化依赖磁盘图 size）。"""
    big = tmp_path / "big.jpg"
    _make_jpeg(big)
    original = big.read_bytes()
    assert len(original) > 300 * 1024, "测试图必须大于直通阈值"

    encoded = reference_vlm_grading._encode_image_for_vlm(str(big))
    compressed = base64.b64decode(encoded)

    assert len(compressed) < len(original), "重编码应显著减小体积"
    with Image.open(io.BytesIO(compressed)) as re, Image.open(big) as orig:
        assert re.size == orig.size, "必须同尺寸，否则 VLM 坐标落到原图错误区域"


def test_encode_image_png_gets_same_size_jpeg(tmp_path):
    """PNG 大图：铺白底转 JPEG，尺寸不变、体积变小。"""
    png = tmp_path / "big.png"
    _make_jpeg(png, quality=100)  # 先造噪声图
    Image.open(png).convert("RGB").save(png, format="PNG")  # 再存成 PNG（噪声 PNG 很大）
    assert png.stat().st_size > 300 * 1024

    encoded = reference_vlm_grading._encode_image_for_vlm(str(png))
    compressed = base64.b64decode(encoded)
    assert len(compressed) < png.stat().st_size
    with Image.open(io.BytesIO(compressed)) as re:
        assert re.size == (1600, 2000)
        assert re.format == "JPEG"


def test_encode_image_never_grows(tmp_path):
    """已经压得很小的 JPEG（高质量低噪声）：重编码不划算时回退原字节。"""
    tiny_content = tmp_path / "flat.jpg"
    Image.new("RGB", (800, 800), "white").save(tiny_content, format="JPEG", quality=95)
    raw = tiny_content.read_bytes()
    encoded = reference_vlm_grading._encode_image_for_vlm(str(tiny_content))
    out = base64.b64decode(encoded)
    # 要么原样返回，要么真的更小；绝不能更大
    assert out == raw or len(out) < len(raw)


def test_encode_image_falls_back_on_broken_file(tmp_path):
    """坏文件回退原字节（绝不因压图把批改搞挂）。"""
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"\xff\xd8\xff\xe0" + b"not-a-real-jpeg" * 30000)  # >300KB 假 JPEG
    encoded = reference_vlm_grading._encode_image_for_vlm(str(broken))
    assert base64.b64decode(encoded) == broken.read_bytes()


# ---------------------------------------------------------------- 单飞闸

@pytest.fixture()
def clean_ref_jobs():
    with _ref_grade_lock:
        saved = dict(_ref_grade_results)
        _ref_grade_results.clear()
    yield
    with _ref_grade_lock:
        _ref_grade_results.clear()
        _ref_grade_results.update(saved)


def _register(job_id, folder, *, done=False, engine="aliyun", only_filename=None,
              only_filenames=None, user_id="U1", total=10):
    _entry = {
        "completed": [],
        "failed": [],
        "in_progress": [],
        "done": done,
        "total": total,
        "engine": engine,
        "user_id": user_id,
        "folder": folder,
        "only_filename": only_filename,
        "only_filenames": sorted(only_filenames) if only_filenames else None,
    }
    with _ref_grade_lock:
        _ref_grade_results[job_id] = _entry


def test_gate_blocks_second_job_and_flags_same_scope(clean_ref_jobs):
    _register("job1", "cls_C1__月考", only_filenames={"a.jpg", "b.jpg"})
    with _ref_grade_lock:
        gate = _find_active_ref_job_locked(
            "cls_C1__月考", engine="aliyun", only_filename=None,
            only_filenames={"b.jpg", "a.jpg"}, user_id="U1",
        )
    assert gate == ("job1", True), "同参数连点应幂等返回在跑 job"


def test_gate_rejects_different_scope(clean_ref_jobs):
    _register("job1", "cls_C1__月考", only_filenames={"a.jpg"})
    with _ref_grade_lock:
        gate = _find_active_ref_job_locked(
            "cls_C1__月考", engine="aliyun", only_filename=None,
            only_filenames={"b.jpg"}, user_id="U1",
        )
    assert gate == ("job1", False), "同文件夹异参数应报冲突（409 语义）"


def test_gate_rejects_different_user_and_engine(clean_ref_jobs):
    _register("job1", "cls_C1__月考", user_id="U1", engine="aliyun")
    with _ref_grade_lock:
        assert _find_active_ref_job_locked(
            "cls_C1__月考", engine="aliyun", only_filename=None,
            only_filenames=None, user_id="U2",
        ) == ("job1", False)
        assert _find_active_ref_job_locked(
            "cls_C1__月考", engine="baidu", only_filename=None,
            only_filenames=None, user_id="U1",
        ) == ("job1", False)


def test_gate_ignores_done_jobs_and_other_folders(clean_ref_jobs):
    _register("done1", "cls_C1__月考", done=True)
    _register("other", "cls_C2__期末")
    with _ref_grade_lock:
        assert _find_active_ref_job_locked(
            "cls_C1__月考", engine="aliyun", only_filename=None,
            only_filenames=None, user_id="U1",
        ) is None


def test_gate_single_flight_concurrent_start(clean_ref_jobs):
    """并发双开：只允许一个注册成功，模拟事故场景的连点。"""
    results = []
    barrier = threading.Barrier(2)

    def _try(tag):
        barrier.wait()
        with _ref_grade_lock:
            gate = _find_active_ref_job_locked(
                "cls_C1__月考", engine="aliyun", only_filename=None,
                only_filenames=None, user_id="U1",
            )
            if gate is not None:
                results.append((tag, "rejected", gate))
            else:
                # 持锁中直插（_register 会再抢锁死锁，这里必须 lock-free 写入）
                _ref_grade_results[f"job-{tag}"] = {
                    "completed": [], "failed": [], "in_progress": [],
                    "done": False, "total": 10, "engine": "aliyun",
                    "user_id": "U1", "folder": "cls_C1__月考",
                    "only_filename": None, "only_filenames": None,
                }
                results.append((tag, "started", None))

    t1 = threading.Thread(target=_try, args=("A",))
    t2 = threading.Thread(target=_try, args=("B",))
    t1.start(); t2.start(); t1.join(); t2.join()

    started = [r for r in results if r[1] == "started"]
    rejected = [r for r in results if r[1] == "rejected"]
    assert len(started) == 1 and len(rejected) == 1, results


# ---------------------------------------------------------------- 并发默认值

def test_baidu_vlm_workers_default_is_adaptive():
    """默认并发按内存自适应：<15G 保守 4（1015 内存防线保留），>=15G 提到 8；
    环境变量覆盖一切。"""
    import os
    import inspect
    from app.services import perf_tuning
    src = inspect.getsource(reference_vlm_grading.recognize_reference_vlm_batch)
    assert 'env_workers("REFERENCE_VLM_BAIDU_WORKERS", 4, 8)' in src
    old = perf_tuning._ram_gb_cache
    try:
        perf_tuning._ram_gb_cache = 8.0
        assert perf_tuning.env_workers("REFERENCE_VLM_BAIDU_WORKERS", 4, 8) == 4
        perf_tuning._ram_gb_cache = 15.7
        assert perf_tuning.env_workers("REFERENCE_VLM_BAIDU_WORKERS", 4, 8) == 8
    finally:
        perf_tuning._ram_gb_cache = old
    saved = os.environ.get("REFERENCE_VLM_BAIDU_WORKERS")
    try:
        os.environ["REFERENCE_VLM_BAIDU_WORKERS"] = "5"
        assert perf_tuning.env_workers("REFERENCE_VLM_BAIDU_WORKERS", 4, 8) == 5
    finally:
        if saved is None:
            os.environ.pop("REFERENCE_VLM_BAIDU_WORKERS", None)
        else:
            os.environ["REFERENCE_VLM_BAIDU_WORKERS"] = saved
