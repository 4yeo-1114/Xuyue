# -*- coding: utf-8 -*-
"""B 端红线输出侧过滤挂点验收测试。

覆盖 4 个 LLM 输出出口：
  1. ai_chat._iter_qwen_sse      — SSE 流式 feed/flush
  2. ai_auto_report.generator    — SSE 流式 feed/flush（restore_text 之后）
  3. portfolio.llm.generate_comment — 整段 filter_text
  4. exams.ai_generate_exam      — 整段 filter_dict（题干/内容/选项/子问题）

全部用 mock 的 LLM 响应（含红线词），断言输出被删除/替换。
"""
import json
from unittest.mock import MagicMock, patch

import pytest


# ── 工具 ──────────────────────────────────────────────────

def _sse_content(chunk: str) -> str:
    """从 _iter_qwen_sse / stream_auto_report 产出的 SSE 事件里解出 content。"""
    assert chunk.startswith("data: "), f"非法 SSE 事件: {chunk!r}"
    payload = chunk[len("data: "):].strip()
    if payload == "[DONE]":
        return ""
    return json.loads(payload)["choices"][0]["delta"]["content"]


def _json_content_delta(content: str) -> str:
    return "data: " + json.dumps(
        {"choices": [{"delta": {"content": content}}]}, ensure_ascii=False
    )


class _FakeSSEResponse:
    """最小 fake：只暴露 iter_lines(decode_unicode=True)。"""

    def __init__(self, lines):
        self._lines = list(lines)

    def iter_lines(self, decode_unicode=True):
        yield from self._lines


# ── 1. ai_chat._iter_qwen_sse 流式过滤 ────────────────────

def test_iter_qwen_sse_filters_redline_streaming():
    from app.routers.ai_chat import _iter_qwen_sse

    lines = [
        _json_content_delta("这个方案属于"),
        _json_content_delta("全脑开发"),
        _json_content_delta("，建议抓住"),
        _json_content_delta("窗口期"),
        "data: [DONE]",
    ]
    out = list(_iter_qwen_sse(_FakeSSEResponse(lines)))
    joined = "".join(_sse_content(c) for c in out)
    assert "全脑开发" not in joined
    assert "关键阶段" in joined  # 窗口期 → 关键阶段
    # [DONE] 事件必须保持最后一个（flush 的残留要在 [DONE] 之前发出）
    assert out[-1] == "data: [DONE]\n\n"


def test_iter_qwen_sse_on_content_receives_filtered():
    from app.routers.ai_chat import _iter_qwen_sse

    lines = [
        _json_content_delta("训练"),
        _json_content_delta("松果体激活"),
        _json_content_delta("毫无意义"),
        "data: [DONE]",
    ]
    acc: list[str] = []
    list(_iter_qwen_sse(_FakeSSEResponse(lines), on_content=acc.append))
    assert "松果体激活" not in "".join(acc)


# ── 2. ai_auto_report.generator 流式过滤（restore_text 之后）──

def test_stream_auto_report_filters_redline():
    from app.services.ai_auto_report import generator as gen

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.iter_lines.return_value = iter([
        _json_content_delta("该班普遍需要"),
        _json_content_delta("左右脑开发"),
        _json_content_delta("，错过"),
        _json_content_delta("窗口期"),
        "data: [DONE]",
    ])
    with (
        patch.object(gen, "get_qwen_config", return_value=("test-key", "qwen")),
        patch.object(gen.requests, "post", return_value=fake_resp),
    ):
        chunks = list(gen.stream_auto_report(db=None, payload={}))
    joined = "".join(_sse_content(c) for c in chunks)
    assert "左右脑开发" not in joined
    assert "关键阶段" in joined


# ── 3. portfolio.llm.generate_comment 整段过滤 ────────────

def test_generate_comment_filters_redline():
    from app.services.portfolio import llm as portfolio_llm

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "choices": [{"message": {"content": "建议进行全脑开发训练，抓住窗口期"}}],
        "usage": {"total_tokens": 8},
    }
    with (
        patch.object(portfolio_llm, "get_qwen_config", return_value=("test-key", "qwen-test")),
        patch.object(portfolio_llm.requests, "post", return_value=fake_resp),
    ):
        result = portfolio_llm.generate_comment(db=None, messages=[])
    assert result["ok"] is True
    assert "全脑开发" not in result["content"]
    assert "关键阶段" in result["content"]


# ── 4. exams.ai_generate_exam 整段 filter_dict ────────────

def test_exam_question_redline_filter_helper():
    """纯函数级：单题题干/内容/选项/子问题里的红线词被删除/替换。"""
    from app.routers.exams import _filter_redline_exam_question

    q = {
        "id": "q1",
        "type": "choice",
        "score": 5,
        "stem": "关于全脑开发的题目",
        "content": "下列哪项属于照相记忆训练？",
        "options": ["松果体激活", "普通学习", "照相记忆", "常规复习"],
        "subQuestions": [],
    }
    out = _filter_redline_exam_question(q)
    raw = json.dumps(out, ensure_ascii=False)
    for bad in ("全脑开发", "照相记忆", "松果体激活", "左右脑开发"):
        assert bad not in raw


def test_ai_generate_exam_filters_redline():
    """端到端（mock LLM）：组卷接口返回前对自然语言字段应用红线过滤。"""
    from app.routers import exams
    from app.routers.exams import AIGenerateExamRequest, RequirementItem

    body = AIGenerateExamRequest(
        topic="注意力训练",
        grade="小学",
        term="上学期",
        difficulty="中等",
        subject="语文",
        requirements=[RequirementItem(type="choice", count=1, score=5)],
    )
    mock_questions = [
        {
            "id": "q_1",
            "type": "choice",
            "score": 5,
            "stem": "关于全脑开发的题干",
            "content": "下列哪项属于全脑开发？",
            "options": ["松果体激活", "普通学习", "照相记忆", "常规复习"],
            "subQuestions": [],
        }
    ]
    llm_content = json.dumps(mock_questions, ensure_ascii=False)
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"choices": [{"message": {"content": llm_content}}]}

    with (
        patch.object(exams, "require_ai_access"),
        patch.object(exams, "assert_no_sensitive_input", return_value=False),
        patch.object(exams, "get_qwen_config", return_value=("test-key", "qwen")),
        patch.object(exams.requests, "post", return_value=fake_resp),
    ):
        result = exams.ai_generate_exam(body, user_id="U1", db=None)

    raw = json.dumps(result.data, ensure_ascii=False)
    for bad in ("全脑开发", "照相记忆", "松果体激活"):
        assert bad not in raw
    # E05 打标逻辑不受过滤影响
    assert result.data[0]["is_ai"] is True
