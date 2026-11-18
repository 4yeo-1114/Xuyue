# -*- coding: utf-8 -*-
"""11.13 台账 #3「作文不打印批注，只保留分数」· 后端单元测试。

覆盖：
1. 只分数变体：文件名规则（marks_only_essay_nocomment_*）、分数画上、旁批/尾批不画
2. 多页作文：分数只在组内第一页，其余页为空白变体（不画任何字）
3. 复用：已有且不旧于主留痕时不再重写；主留痕更新（改分/重批）后自动重画
4. 端点 /essay-grade/score-only-marks：批量生成、缺记录返回 error、缺 files 400
"""

import os
import time

import pytest
from PIL import Image

from app.grading import user_paths
from app.grading import router as grading_router


# ---------------------------------------------------------------- 工具

def _patch_project_root(monkeypatch, tmp_path):
    monkeypatch.setattr(user_paths, "project_root", lambda: tmp_path)


def _set_user(user_id):
    return grading_router.set_grading_user_id(user_id)


def _sample_item(filename, *, score="68", comments=None, group_pages=None):
    segs = comments or {
        "opening": "开头旁批一句",
        "middle1": "中间一旁批一句",
        "middle2": "中间二旁批一句",
        "ending": "结尾旁批一句",
    }
    result = "【作文得分】\n%s 分\n\n【作文分段概述】\n开头：%s\n中间一：%s\n中间二：%s\n结尾：%s\n\n【老师总评】\n总评内容。\n<essay_score>%s</essay_score>" % (
        score,
        segs.get("opening", ""),
        segs.get("middle1", ""),
        segs.get("middle2", ""),
        segs.get("ending", ""),
        score,
    )
    item = {
        "name": filename,
        "result": result,
        "score_total": float(score) if str(score).replace(".", "", 1).isdigit() else None,
    }
    if group_pages:
        item["group_pages"] = list(group_pages)
    return item


def _plant_original(filename, w=900, h=1300):
    orig = user_paths.correct_docs_dir() / "cls_t__1" / filename
    orig.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), "white").save(str(orig))
    return orig


def _red_pixels(path):
    im = Image.open(str(path)).convert("RGB")
    px = im.load()
    w, h = im.size
    pts = []
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if r > 150 and g < 105 and b < 105 and (r - g) > 80:
                pts.append((x, y))
    return pts, (w, h)


# ---------------------------------------------------------------- 1. 只分数变体

def test_score_only_variant_name_and_content(monkeypatch, tmp_path):
    _patch_project_root(monkeypatch, tmp_path)
    token = _set_user("u1")
    try:
        filename = "张三_1.jpg"
        _plant_original(filename)
        item = _sample_item(filename)
        out = grading_router._render_essay_score_only_marks("cls_t__1", filename, item)

        name = out["marks_only_filename"]
        assert name == "marks_only_essay_nocomment_cls_t__1_张三_1.jpg"
        path = user_paths.modify_dir() / name
        assert path.is_file()

        pts, (w, h) = _red_pixels(path)
        # 分数画上了（红色存在）
        assert len(pts) >= 8
        # 旁批/尾批不画：红色只允许出现在顶部（分数区），下方无红
        assert all(y < int(h * 0.3) for x, y in pts), "旁批/尾批被画进了只分数变体"
    finally:
        user_paths.reset_grading_user_id(token)


def test_score_only_multi_page_blank_after_first(monkeypatch, tmp_path):
    _patch_project_root(monkeypatch, tmp_path)
    token = _set_user("u1")
    try:
        f1, f2 = "李四_1.jpg", "李四_2.jpg"
        _plant_original(f1)
        _plant_original(f2)
        item1 = _sample_item(f1, score="42", group_pages=[f1, f2])
        item2 = _sample_item(f2, score="42", group_pages=[f1, f2])

        out1 = grading_router._render_essay_score_only_marks("cls_t__1", f1, item1)
        out2 = grading_router._render_essay_score_only_marks("cls_t__1", f2, item2)

        assert out1["marks_only_filename"] == "marks_only_essay_nocomment_cls_t__1_李四_1.jpg"
        assert out2["marks_only_filename"] == "marks_only_essay_nocomment_cls_t__1_李四_2.jpg"

        pts1, _ = _red_pixels(user_paths.modify_dir() / out1["marks_only_filename"])
        pts2, _ = _red_pixels(user_paths.modify_dir() / out2["marks_only_filename"])
        # 第一页有分数；第二页（非首页）空白不画
        assert len(pts1) >= 8
        assert len(pts2) == 0
    finally:
        user_paths.reset_grading_user_id(token)


# ---------------------------------------------------------------- 3. 复用/重画

def test_reuse_until_main_marks_newer(monkeypatch, tmp_path):
    _patch_project_root(monkeypatch, tmp_path)
    token = _set_user("u1")
    try:
        filename = "王五_1.jpg"
        _plant_original(filename)
        item = _sample_item(filename, score="55")

        out = grading_router._render_essay_score_only_marks("cls_t__1", filename, item)
        variant = user_paths.modify_dir() / out["marks_only_filename"]
        assert variant.is_file()
        m1 = variant.stat().st_mtime

        # 再调：复用不重写（时间戳不前进）
        grading_router._render_essay_score_only_marks("cls_t__1", filename, item)
        assert variant.stat().st_mtime == m1

        # 主留痕更新（模拟改分/重批重绘）→ 变体自动重画
        main = user_paths.modify_dir() / "marks_only_essay_cls_t__1_王五_1.jpg"
        main.write_bytes(b"x")
        os.utime(str(main), (m1 + 10, m1 + 10))
        time.sleep(0.05)
        grading_router._render_essay_score_only_marks("cls_t__1", filename, item)
        assert variant.stat().st_mtime > m1
    finally:
        user_paths.reset_grading_user_id(token)


# ---------------------------------------------------------------- 4. 端点

def test_endpoint_batch_and_errors(monkeypatch, tmp_path):
    _patch_project_root(monkeypatch, tmp_path)
    token = _set_user("u1")
    try:
        f1 = "赵六_1.jpg"
        _plant_original(f1)
        item = _sample_item(f1, score="73")
        data = {"completed": {f1: item}, "failed": {}, "version": 1}
        grading_router._write_essay_history("cls_t__1", data)

        # 缺 files → 400
        with pytest.raises(Exception) as ei:
            grading_router.api_essay_score_only_marks("cls_t__1", {})
        assert getattr(ei.value, "status_code", None) == 400

        res = grading_router.api_essay_score_only_marks(
            "cls_t__1", {"files": [f1, "不存在_1.jpg"]}
        )
        assert res["ok"] is True
        got = res["files"][f1]
        assert got["marks_only_filename"] == "marks_only_essay_nocomment_cls_t__1_赵六_1.jpg"
        assert (user_paths.modify_dir() / got["marks_only_filename"]).is_file()
        assert "error" in res["files"]["不存在_1.jpg"]

        pts, (w, h) = _red_pixels(user_paths.modify_dir() / got["marks_only_filename"])
        assert len(pts) >= 8
        assert all(y < int(h * 0.3) for x, y in pts)
    finally:
        user_paths.reset_grading_user_id(token)
