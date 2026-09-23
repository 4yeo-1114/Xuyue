# -*- coding: utf-8 -*-
"""A2-B1 作文批改结构化维度化 · 后端单元测试。

覆盖：
1. 模型 EssayRubric 新增 dimensions_json 列
2. DEFAULT_DIMENSIONS + prompt 维度化注入（grade_essay_with_qwen 维度段）
3. 维度分解析落盘（_extract_essay_grade_scores / _parse_essay_dimension_scores）
   - 无 <essay_dimensions> 标签：dimension_scores=None，score_total 正常
   - 有 <essay_dimensions>：正确解析、score_total 与维度分之和联动
   - 标签缺失 / JSON 非法 / 未知 key / 超范围：静默不崩，不阻断批改
4. rubrics CRUD 透传 dimensions_json（POST/GET/PUT）
"""

import json

import pytest

from app.grading import essay_grading
from app.grading import router as grading_router
from app.grading.router import _extract_essay_grade_scores, _parse_essay_dimension_scores
from app.models.essay_rubric import EssayRubric


# ---------------------------------------------------------------- 模型列

def test_essay_rubric_model_has_dimensions_json_column():
    cols = {c.name: c for c in EssayRubric.__table__.columns}
    assert "dimensions_json" in cols
    assert cols["dimensions_json"].nullable is True
    # 其余既有列不受影响
    for name in ("id", "user_id", "name", "content", "scoring_prompt", "topic_text", "topic_image_base64"):
        assert name in cols


def test_database_ensure_essay_rubric_extra_columns_includes_dimensions():
    # 静态检查补列清单，避免 ALTER 兜底漏列
    import inspect

    from app import database as db_module

    src = inspect.getsource(db_module._ensure_essay_rubric_extra_columns)
    assert "dimensions_json" in src
    assert "topic_text" in src
    assert "topic_image_base64" in src


# ---------------------------------------------------------------- DEFAULT_DIMENSIONS

def test_default_dimensions_are_five_and_sum_to_100():
    dims = essay_grading.DEFAULT_DIMENSIONS
    assert isinstance(dims, list) and len(dims) == 5
    assert sum(d["full_score"] for d in dims) == 100
    keys = [d["key"] for d in dims]
    assert keys == ["content", "structure", "language", "relevance", "presentation"]
    for d in dims:
        for field in ("key", "name", "full_score", "weight", "description", "order"):
            assert field in d, f"维度缺少字段 {field}: {d}"


def test_build_dimension_section_formats_full_scores_and_descriptions():
    text = essay_grading._build_dimension_section(essay_grading.DEFAULT_DIMENSIONS)
    assert "内容与立意（满分 25 分）：立意是否明确、材料是否充实、中心是否突出" in text
    assert "结构与思路（满分 20 分）：开头/中段/结尾是否完整、过渡与层次是否清晰" in text
    assert "扣题程度（满分 15 分）：是否紧扣题目要求（结合 topic 判断偏题/跑题）" in text


# ---------------------------------------------------------------- prompt 维度化注入

class _FakeCompletions:
    def __init__(self, captured, payload):
        self._captured = captured
        self._payload = payload

    def create(self, **kwargs):
        self._captured.update(kwargs)
        return _FakeResp(self._payload)


class _FakeChat:
    def __init__(self, captured, payload):
        self.completions = _FakeCompletions(captured, payload)


class _FakeClient:
    def __init__(self, captured, payload):
        self._captured = captured
        self._payload = payload

    @property
    def chat(self):
        return _FakeChat(self._captured, self._payload)


class _FakeResp:
    def __init__(self, payload):
        msg = type("Msg", (), {"content": payload})()
        self.choices = [type("Ch", (), {"message": msg})()]


def _run_grade_with_capture(payload, custom_prompts=None, dimensions=None, monkeypatch=None):
    captured = {}
    # grade_essay_with_qwen 内部 from app.grading.pipeline import _get_openai_client，
    # 因此要 patch 的是 pipeline 模块里的函数。
    monkeypatch.setattr("app.grading.pipeline._get_openai_client", lambda: _FakeClient(captured, payload))
    monkeypatch.setattr(essay_grading, "_resolve_essay_model", lambda: "test-model")
    result = essay_grading.grade_essay_with_qwen(
        "我的理想",
        "正文内容",
        "批改标准正文",
        custom_prompts or {},
        dimensions,
    )
    messages = captured["messages"]
    user_content = messages[0]["content"]
    return result, user_content


def test_grade_essay_injects_default_dimension_section(monkeypatch):
    payload = "【作文分段概述】\n...\n<essay_score>83</essay_score>"
    _, user_content = _run_grade_with_capture(payload, monkeypatch=monkeypatch)
    assert "内容与立意（满分 25 分）：立意是否明确、材料是否充实、中心是否突出" in user_content
    assert "语言表达（满分 25 分）：用词、句式、文采、通顺度" in user_content
    assert "<essay_dimensions>" in user_content
    # 默认四段 Prompt 仍保留（缺省 custom_prompts 时回落默认值）
    assert "不得自行套用其他标准" in user_content   # 默认评分细则
    assert "每句写完整、不要省略" in user_content   # 默认旁批内容要求


def test_grade_essay_injects_custom_dimensions(monkeypatch):
    custom_dims = [
        {"key": "a", "name": "维度A", "full_score": 40, "weight": 0.4, "description": "描述A", "order": 1},
        {"key": "b", "name": "维度B", "full_score": 60, "weight": 0.6, "description": "描述B", "order": 2},
    ]
    payload = "【作文分段概述】\n...\n<essay_score>80</essay_score>"
    _, user_content = _run_grade_with_capture(payload, dimensions=custom_dims, monkeypatch=monkeypatch)
    assert "维度A（满分 40 分）：描述A" in user_content
    assert "维度B（满分 60 分）：描述B" in user_content
    assert "内容与立意" not in user_content


# ---------------------------------------------------------------- 维度分解析落盘

DEFAULT_DIMS = essay_grading.DEFAULT_DIMENSIONS


def _sample_result(score="83", dims_json=None):
    text = "【作文分段概述】\n开头：好。\n【老师总评】\n不错。"
    text += f"\n<essay_score>{score}</essay_score>"
    if dims_json is not None:
        text += f"\n<essay_dimensions>{dims_json}</essay_dimensions>"
    return text


def test_parse_dimensions_absent_when_no_tag():
    result = _sample_result(score="83")
    parsed = _extract_essay_grade_scores(result, DEFAULT_DIMS)
    assert parsed["score_total"] == 83.0
    assert parsed["dimension_scores"] is None
    assert parsed["score_text"] == "83"
    # 隐藏标签都被清理，正文板块保留
    assert "<essay_score>" not in parsed["clean_text"]
    assert "<essay_dimensions>" not in parsed["clean_text"]
    assert "【老师总评】" in parsed["clean_text"]


def test_parse_dimensions_valid_scores_and_total_synced():
    dims_json = json.dumps({"content": 20, "structure": 16, "language": 22, "relevance": 13, "presentation": 12}, ensure_ascii=False)
    result = _sample_result(score="83", dims_json=dims_json)
    parsed = _extract_essay_grade_scores(result, DEFAULT_DIMS)
    assert parsed["dimension_scores"] == {
        "content": 20, "structure": 16, "language": 22, "relevance": 13, "presentation": 12,
    }
    assert parsed["score_total"] == 83.0
    assert parsed["score_text"] == "83"
    assert "<essay_dimensions>" not in parsed["clean_text"]


def test_parse_dimensions_total_overrides_mismatched_essay_score():
    # <essay_score>85</essay_score> 与维度分之和 83 不一致 → 以维度分之和为准
    dims_json = json.dumps({"content": 20, "structure": 16, "language": 22, "relevance": 13, "presentation": 12}, ensure_ascii=False)
    result = _sample_result(score="85", dims_json=dims_json)
    parsed = _extract_essay_grade_scores(result, DEFAULT_DIMS)
    assert parsed["dimension_scores"] == {
        "content": 20, "structure": 16, "language": 22, "relevance": 13, "presentation": 12,
    }
    assert parsed["score_total"] == 83.0
    assert parsed["score_text"] == "83"


def test_parse_dimensions_sets_total_when_essay_score_missing():
    # 只有 <essay_dimensions>、没有 <essay_score> → 维度分之和成为 score_total
    dims_json = json.dumps({"content": 20, "structure": 16, "language": 22, "relevance": 13, "presentation": 12}, ensure_ascii=False)
    result = "【老师总评】\n不错。\n" + f"<essay_dimensions>{dims_json}</essay_dimensions>"
    parsed = _extract_essay_grade_scores(result, DEFAULT_DIMS)
    assert parsed["dimension_scores"] is not None
    assert parsed["score_total"] == 83.0
    assert parsed["score_text"] == "83"


@pytest.mark.parametrize(
    "dims_json",
    [
        "{invalid json",                 # JSON 非法
        '"just a string"',               # 非 dict
        '[{"a": 1}]',                    # 列表而非 dict
        '{"bad_key": 20}',               # 未知维度 key
        '{"content": 999}',              # 超出满分
        '{"content": -1}',               # 负分
        '{"content": "twenty"}',         # 非数字
        "{}",                            # 空 dict
    ],
)
def test_parse_dimensions_invalid_inputs_fail_silently(dims_json):
    result = _sample_result(score="83", dims_json=dims_json)
    parsed = _extract_essay_grade_scores(result, DEFAULT_DIMS)
    assert parsed["dimension_scores"] is None
    # 不阻断：score_total 仍取 <essay_score>
    assert parsed["score_total"] == 83.0
    assert parsed["score_text"] == "83"
    assert "<essay_dimensions>" not in parsed["clean_text"]


def test_parse_dimensions_tag_present_but_not_last_line_still_parses():
    result = "【老师总评】\n不错。\n<essay_dimensions>{}</essay_dimensions>\n<essay_score>83</essay_score>".replace("{}", json.dumps({"content": 25}))
    # content 25 未超出满分，但缺 4 个维度 key → 未知 key 之外缺失维度本身不判失败（key 级校验只校验出现的 key）
    parsed = _extract_essay_grade_scores(result, DEFAULT_DIMS)
    assert parsed["dimension_scores"] == {"content": 25}
    assert parsed["score_total"] == 25.0


def test_parse_dimension_scores_missing_dimensions_config_returns_none():
    result = _sample_result(score="83", dims_json=json.dumps({"content": 20}))
    # 无维度配置 → 无从校验，整体丢弃
    parsed = _extract_essay_grade_scores(result, None)
    assert parsed["dimension_scores"] is None
    assert parsed["score_total"] == 83.0


# ---------------------------------------------------------------- CRUD 透传

class _FakeRubricQuery:
    def __init__(self, session):
        self._session = session

    def filter(self, *args, **kwargs):
        return self

    def filter_by(self, **kwargs):
        return self

    def order_by(self, *args):
        return self

    def all(self):
        return list(self._session.rubrics)

    def first(self):
        return self._session.rubrics[0] if self._session.rubrics else None

    def delete(self, synchronize_session=False):
        n = len(self._session.rubrics)
        self._session.rubrics = []
        return n


class _FakeSession:
    def __init__(self, rubrics=None):
        self.rubrics = list(rubrics or [])
        self.added = []
        self.committed = 0

    def query(self, model):
        return _FakeRubricQuery(self)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed += 1
        for obj in self.added:
            self.rubrics.append(obj)
        self.added = []

    def refresh(self, obj):
        pass

    def close(self):
        pass


class _FakeRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


DIMS_JSON = json.dumps(
    essay_grading.DEFAULT_DIMENSIONS, ensure_ascii=False
)


def test_rubric_create_persists_dimensions_json():
    db = _FakeSession()
    req = _FakeRequest({
        "name": "满分100五维",
        "content": "",
        "dimensions_json": DIMS_JSON,
    })
    import asyncio

    resp = asyncio.run(
        grading_router.api_create_rubric(req, user_id="u-dim", db=db)
    )
    assert resp["ok"] is True
    assert resp["rubric"]["dimensions_json"] == DIMS_JSON
    assert len(db.rubrics) == 1
    assert db.rubrics[0].dimensions_json == DIMS_JSON
    assert db.rubrics[0].user_id == "u-dim"


def test_rubric_get_returns_dimensions_json():
    db = _FakeSession(rubrics=[EssayRubric(
        id="r1",
        user_id="u-dim",
        name="默认",
        content="",
        dimensions_json=DIMS_JSON,
    )])
    import asyncio

    resp = asyncio.run(
        grading_router.api_get_rubrics(user_id="u-dim", db=db)
    )
    assert resp["ok"] is True
    assert len(resp["rubrics"]) == 1
    assert resp["rubrics"][0]["id"] == "r1"
    assert resp["rubrics"][0]["dimensions_json"] == DIMS_JSON


def test_rubric_update_replaces_dimensions_json():
    db = _FakeSession(rubrics=[EssayRubric(
        id="r1",
        user_id="u-dim",
        name="默认",
        content="",
        dimensions_json=DIMS_JSON,
    )])
    new_dims = json.dumps([
        {"key": "a", "name": "维度A", "full_score": 100, "weight": 1.0, "description": "单维", "order": 1},
    ], ensure_ascii=False)
    req = _FakeRequest({"name": "改名", "dimensions_json": new_dims})
    import asyncio

    resp = asyncio.run(
        grading_router.api_update_rubric("r1", req, user_id="u-dim", db=db)
    )
    assert resp["ok"] is True
    assert resp["rubric"]["dimensions_json"] == new_dims
    assert resp["rubric"]["name"] == "改名"
    assert db.rubrics[0].dimensions_json == new_dims
