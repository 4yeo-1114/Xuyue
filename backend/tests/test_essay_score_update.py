# -*- coding: utf-8 -*-
"""A2-B2 作文改分 + 局部重批 · 后端单元测试。

覆盖：
1. 默认改分（regenerate_report=False）：dimension_scores/score_total 更新、
   result 首行【作文得分】分数替换、其它【】板块原样保留、history 文件写回
2. 越权：非本人 / 不存在 → 404，history 不变
3. 非法维度（未知 key / 越界分数 / 非数字）→ 422，history 不变
4. total_score 缺省 = 维度分之和；显式 total_score 优先
5. regenerate_report=True：复用已存 ocr_title/ocr_content（不重新 OCR）调重评函数，
   result 整体替换、隐藏标签剥离
6. history 读接口对外剔除内部字段（rubric_text/prompts/dimensions）
7. regrade_essay_with_qwen 复用主函数
"""

import asyncio
import json

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.grading import essay_grading
from app.grading import user_paths
from app.grading import router as grading_router
from app.grading.router import EssayScoreUpdateBody

DEFAULT_DIMS = essay_grading.DEFAULT_DIMENSIONS
DIMS_JSON = json.dumps(DEFAULT_DIMS, ensure_ascii=False)


# ---------------------------------------------------------------- 工具

def _patch_project_root(monkeypatch, tmp_path):
    """把 grading_data_all 根目录重定向到 tmp_path，实现 per-user 文件系统隔离。"""
    monkeypatch.setattr(user_paths, "project_root", lambda: tmp_path)


def _set_user(user_id):
    return grading_router.set_grading_user_id(user_id)


def _write_history(user_id, safe, data):
    token = _set_user(user_id)
    try:
        grading_router._write_essay_history(safe, data)
    finally:
        grading_router.reset_grading_user_id(token)


def _read_history(user_id, safe):
    token = _set_user(user_id)
    try:
        return grading_router._read_essay_history(safe)
    finally:
        grading_router.reset_grading_user_id(token)


def _sample_completed(filename="张三.jpg"):
    return {
        "name": filename,
        "group_name": "张三",
        "group_pages": [filename],
        # 与 _run_essay_grade 持久化格式一致：首行【作文得分】 + 末尾隐藏 <essay_score> 标签
        "result": (
            "【作文得分】\n83 分\n\n"
            "【作文分段概述】\n开头：好。\n"
            "【老师总评】\n不错。\n"
            "【习作提升】\n提升内容。\n"
            "【写作指导】\n指导内容。\n"
            "<essay_score>83</essay_score>"
        ),
        "score_total": 83,
        "dimension_scores": {
            "content": 20, "structure": 16, "language": 22, "relevance": 13, "presentation": 12,
        },
        "ocr_title": "我的理想",
        "ocr_content": "正文内容",
        "rubric_text": "批改标准正文",
        "prompts": {"dimensions_json": DIMS_JSON},
        "dimensions": DEFAULT_DIMS,
        "image_original": None,
        "image_annotated": None,
        "image_marks_only": None,
        "marks_only_filename": None,
    }


def _history_data(filename="张三.jpg"):
    return {
        "version": 1,
        "completed": {filename: _sample_completed(filename)},
        "failed": {},
    }


def _call_score(safe, body, user_id):
    return asyncio.run(grading_router.api_update_essay_score(safe, body, user_id=user_id))


def _assert_unchanged_history(user_id, safe, filename="张三.jpg"):
    hist = _read_history(user_id, safe)
    item = hist["completed"][filename]
    assert item["score_total"] == 83
    assert item["result"].startswith("【作文得分】\n83 分")
    assert item["dimension_scores"]["content"] == 20


# ---------------------------------------------------------------- 路由 / 请求体

def test_score_route_registered():
    score_routes = [
        r for r in grading_router.router.routes
        if getattr(r, "path", "").endswith("/essay-grade/score")
    ]
    assert len(score_routes) == 1
    assert "POST" in (score_routes[0].methods or set())


def test_score_body_rejects_non_numeric_dimension():
    with pytest.raises(ValidationError):
        EssayScoreUpdateBody(filename="a.jpg", dimension_scores={"content": "abc"})


def test_score_body_defaults_total_and_regenerate():
    body = EssayScoreUpdateBody(filename="a.jpg", dimension_scores={"content": 20})
    assert body.total_score is None
    assert body.regenerate_report is False


# ---------------------------------------------------------------- 默认改分

def test_default_score_update_writes_history_and_keeps_sections(monkeypatch, tmp_path):
    _patch_project_root(monkeypatch, tmp_path)
    safe = "essay_folder"
    filename = "张三.jpg"
    _write_history("user-a", safe, _history_data(filename))

    body = EssayScoreUpdateBody(
        filename=filename,
        dimension_scores={
            "content": 22, "structure": 17, "language": 20, "relevance": 14, "presentation": 12,
        },
    )
    resp = _call_score(safe, body, "user-a")

    assert resp["ok"] is True
    comp = resp["completed"]
    assert comp["score_total"] == 85.0  # 维度分之和
    assert comp["dimension_scores"] == {
        "content": 22.0, "structure": 17.0, "language": 20.0, "relevance": 14.0, "presentation": 12.0,
    }
    # 首行分数替换
    assert comp["result"].startswith("【作文得分】\n85 分")
    # 末尾遗留隐藏 <essay_score> 标签同步为新总分，避免记录内新旧分不一致
    assert "<essay_score>85</essay_score>" in comp["result"]
    # 其它【】板块原样保留
    assert "【作文分段概述】\n开头：好。" in comp["result"]
    assert "【老师总评】\n不错。" in comp["result"]
    assert "【习作提升】\n提升内容。" in comp["result"]
    assert "【写作指导】\n指导内容。" in comp["result"]

    # history 文件写回
    hist = _read_history("user-a", safe)
    item = hist["completed"][filename]
    assert item["score_total"] == 85.0
    assert item["dimension_scores"]["content"] == 22.0
    assert item["result"].startswith("【作文得分】\n85 分")
    assert "【老师总评】\n不错。" in item["result"]


def test_default_score_update_explicit_total_score_priority(monkeypatch, tmp_path):
    _patch_project_root(monkeypatch, tmp_path)
    safe = "essay_folder"
    filename = "张三.jpg"
    _write_history("user-a", safe, _history_data(filename))

    body = EssayScoreUpdateBody(
        filename=filename,
        dimension_scores={
            "content": 22, "structure": 17, "language": 20, "relevance": 14, "presentation": 12,
        },
        total_score=90.0,  # 与维度分之和 85 不同，显式 total_score 优先
    )
    resp = _call_score(safe, body, "user-a")

    assert resp["completed"]["score_total"] == 90.0
    assert resp["completed"]["result"].startswith("【作文得分】\n90 分")
    assert "<essay_score>90</essay_score>" in resp["completed"]["result"]
    assert resp["completed"]["dimension_scores"]["content"] == 22.0


# ---------------------------------------------------------------- 越权 / 不存在

def test_score_update_non_owner_404(monkeypatch, tmp_path):
    _patch_project_root(monkeypatch, tmp_path)
    safe = "essay_folder"
    filename = "张三.jpg"
    _write_history("user-a", safe, _history_data(filename))

    body = EssayScoreUpdateBody(
        filename=filename,
        dimension_scores={"content": 22, "structure": 17, "language": 20, "relevance": 14, "presentation": 12},
    )
    with pytest.raises(HTTPException) as exc:
        _call_score(safe, body, "user-b")  # 非本人
    assert exc.value.status_code == 404

    # user-a 的历史不被影响
    _assert_unchanged_history("user-a", safe, filename)


def test_score_update_missing_filename_404(monkeypatch, tmp_path):
    _patch_project_root(monkeypatch, tmp_path)
    safe = "essay_folder"
    filename = "张三.jpg"
    _write_history("user-a", safe, _history_data(filename))

    body = EssayScoreUpdateBody(
        filename="不存在.jpg",
        dimension_scores={"content": 22},
    )
    with pytest.raises(HTTPException) as exc:
        _call_score(safe, body, "user-a")
    assert exc.value.status_code == 404


def test_score_update_empty_filename_422(monkeypatch, tmp_path):
    _patch_project_root(monkeypatch, tmp_path)
    safe = "essay_folder"
    _write_history("user-a", safe, _history_data())
    body = EssayScoreUpdateBody(filename="  ", dimension_scores={"content": 22})
    with pytest.raises(HTTPException) as exc:
        _call_score(safe, body, "user-a")
    assert exc.value.status_code == 422


# ---------------------------------------------------------------- 非法维度

@pytest.mark.parametrize(
    "dim_scores, msg",
    [
        ({"bad_key": 20}, "未知维度"),
        ({"content": 999}, "超出范围"),
        ({"content": -1}, "超出范围"),
    ],
)
def test_score_update_invalid_dimensions_422(monkeypatch, tmp_path, dim_scores, msg):
    _patch_project_root(monkeypatch, tmp_path)
    safe = "essay_folder"
    filename = "张三.jpg"
    _write_history("user-a", safe, _history_data(filename))

    body = EssayScoreUpdateBody(filename=filename, dimension_scores=dim_scores)
    with pytest.raises(HTTPException) as exc:
        _call_score(safe, body, "user-a")
    assert exc.value.status_code == 422
    assert msg in str(exc.value.detail)

    _assert_unchanged_history("user-a", safe, filename)


def test_score_update_empty_dimension_scores_422(monkeypatch, tmp_path):
    _patch_project_root(monkeypatch, tmp_path)
    safe = "essay_folder"
    filename = "张三.jpg"
    _write_history("user-a", safe, _history_data(filename))
    body = EssayScoreUpdateBody(filename=filename, dimension_scores={})
    with pytest.raises(HTTPException) as exc:
        _call_score(safe, body, "user-a")
    assert exc.value.status_code == 422


def test_score_update_custom_dimensions_config_used(monkeypatch, tmp_path):
    """rubric 自定义维度配置时，改分校验以该配置为准。"""
    _patch_project_root(monkeypatch, tmp_path)
    safe = "essay_folder"
    filename = "张三.jpg"
    item = _sample_completed(filename)
    item["dimensions"] = [
        {"key": "a", "name": "维度A", "full_score": 40, "weight": 0.4, "description": "描述A", "order": 1},
        {"key": "b", "name": "维度B", "full_score": 60, "weight": 0.6, "description": "描述B", "order": 2},
    ]
    item["prompts"] = {"dimensions_json": json.dumps(item["dimensions"], ensure_ascii=False)}
    _write_history("user-a", safe, {"version": 1, "completed": {filename: item}, "failed": {}})

    # 未知 key（相对自定义配置）→ 422
    body = EssayScoreUpdateBody(filename=filename, dimension_scores={"content": 25})
    with pytest.raises(HTTPException) as exc:
        _call_score(safe, body, "user-a")
    assert exc.value.status_code == 422
    assert "未知维度" in str(exc.value.detail)

    # 合法 key → 成功，总分 = 维度分之和
    body = EssayScoreUpdateBody(filename=filename, dimension_scores={"a": 30, "b": 50})
    resp = _call_score(safe, body, "user-a")
    assert resp["completed"]["score_total"] == 80.0
    assert resp["completed"]["dimension_scores"] == {"a": 30.0, "b": 50.0}


# ---------------------------------------------------------------- 局部重批

def test_score_update_regenerate_reuses_stored_ocr(monkeypatch, tmp_path):
    _patch_project_root(monkeypatch, tmp_path)
    safe = "essay_folder"
    filename = "张三.jpg"
    _write_history("user-a", safe, _history_data(filename))

    captured = {}

    def fake_regrade(title, content, rubric_text, custom_prompts, dimensions):
        captured.update(
            title=title,
            content=content,
            rubric_text=rubric_text,
            prompts=custom_prompts,
            dimensions=dimensions,
        )
        return (
            "【作文分段概述】\n开头：新。\n"
            "【老师总评】\n新评。\n"
            "<essay_score>90</essay_score>\n"
            "<essay_dimensions>{"
            '"content":22,"structure":17,"language":20,"relevance":14,"presentation":12'
            "}</essay_dimensions>"
        )

    monkeypatch.setattr(essay_grading, "regrade_essay_with_qwen", fake_regrade)

    body = EssayScoreUpdateBody(
        filename=filename,
        dimension_scores={
            "content": 22, "structure": 17, "language": 20, "relevance": 14, "presentation": 12,
        },
        regenerate_report=True,
    )
    resp = _call_score(safe, body, "user-a")

    # 复用已存 OCR 文本与配置，不重新 OCR
    assert captured["title"] == "我的理想"
    assert captured["content"] == "正文内容"
    assert captured["rubric_text"] == "批改标准正文"
    assert captured["prompts"]["dimensions_json"] == DIMS_JSON
    # 改后维度分已注入为 full_score
    assert captured["dimensions"] == [
        {"key": "content", "name": "内容与立意", "full_score": 22.0, "weight": 0.25, "description": "立意是否明确、材料是否充实、中心是否突出", "order": 1},
        {"key": "structure", "name": "结构与思路", "full_score": 17.0, "weight": 0.20, "description": "开头/中段/结尾是否完整、过渡与层次是否清晰", "order": 2},
        {"key": "language", "name": "语言表达", "full_score": 20.0, "weight": 0.25, "description": "用词、句式、文采、通顺度", "order": 3},
        {"key": "relevance", "name": "扣题程度", "full_score": 14.0, "weight": 0.15, "description": "是否紧扣题目要求（结合 topic 判断偏题/跑题）", "order": 4},
        {"key": "presentation", "name": "卷面与篇幅", "full_score": 12.0, "weight": 0.15, "description": "字数是否达标、卷面/书写", "order": 5},
    ]

    # result 整体替换：首行为新总分 + 剥离隐藏标签后的新正文
    comp = resp["completed"]
    assert comp["score_total"] == 85.0
    assert comp["result"].startswith("【作文得分】\n85 分")
    assert "<essay_score>" not in comp["result"]
    assert "<essay_dimensions>" not in comp["result"]
    assert "【老师总评】\n新评。" in comp["result"]
    assert "开头：好。" not in comp["result"]  # 旧正文整体被替换

    # history 写回
    hist = _read_history("user-a", safe)
    item = hist["completed"][filename]
    assert item["score_total"] == 85.0
    assert item["result"].startswith("【作文得分】\n85 分")
    assert "【老师总评】\n新评。" in item["result"]


def test_score_update_regenerate_missing_ocr_content_422(monkeypatch, tmp_path):
    _patch_project_root(monkeypatch, tmp_path)
    safe = "essay_folder"
    filename = "张三.jpg"
    item = _sample_completed(filename)
    item["ocr_content"] = ""
    _write_history("user-a", safe, {"version": 1, "completed": {filename: item}, "failed": {}})

    body = EssayScoreUpdateBody(
        filename=filename,
        dimension_scores={"content": 22, "structure": 17, "language": 20, "relevance": 14, "presentation": 12},
        regenerate_report=True,
    )
    with pytest.raises(HTTPException) as exc:
        _call_score(safe, body, "user-a")
    assert exc.value.status_code == 422


# ---------------------------------------------------------------- history 对外字段

def test_essay_grading_history_strips_internal_fields(monkeypatch, tmp_path):
    _patch_project_root(monkeypatch, tmp_path)
    safe = "essay_folder"
    filename = "张三.jpg"
    _write_history("user-a", safe, _history_data(filename))

    token = _set_user("user-a")
    try:
        resp = asyncio.run(grading_router.api_get_essay_grading_history(safe))
    finally:
        grading_router.reset_grading_user_id(token)

    assert resp["ok"] is True
    assert len(resp["completed"]) == 1
    item = resp["completed"][0]
    assert item["name"] == filename
    assert "rubric_text" not in item
    assert "prompts" not in item
    assert "dimensions" not in item
    assert item["score_total"] == 83
    assert item["result"].startswith("【作文得分】\n83 分")


# ---------------------------------------------------------------- 重评函数

def test_regrade_essay_with_qwen_delegates_to_grade(monkeypatch):
    called = {}

    def fake_grade(title, content, rubric_text, custom_prompts, dimensions):
        called.update(title=title, content=content, rubric_text=rubric_text, prompts=custom_prompts, dimensions=dimensions)
        return "new-result"

    monkeypatch.setattr(essay_grading, "grade_essay_with_qwen", fake_grade)
    out = essay_grading.regrade_essay_with_qwen("题", "文", "标准", {"a": 1}, [{"key": "x"}])
    assert out == "new-result"
    assert called == {"title": "题", "content": "文", "rubric_text": "标准", "prompts": {"a": 1}, "dimensions": [{"key": "x"}]}
