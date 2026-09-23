# -*- coding: utf-8 -*-
"""A7-B1 批改 prompt 层 OCR 噪声容错 · 单元测试。

纯文本断言为主：
1. 三个判题 prompt（PROMPT_BLOCK / PROMPT_BLOCK_REF / PROMPT_BLOCK_SMART_REF）
   均含 OCR 噪声宽容条款（关键词 OCR / 错别字 / 语义），且既有段落未被破坏。
2. 作文系统 prompt（ESSAY_SYSTEM_PROMPT_TEMPLATE）含 OCR 噪声宽容条款，
   A2 维度化评分（essay_dimensions）关键词仍在。
3. 构造含错别字的伪 OCR 文本走 prompt 组装函数，断言宽容条款注入组装后的文本。
"""

import pytest

from app.grading import pipeline
from app.grading import essay_grading


# 三个判题 prompt 共用的 OCR 噪声宽容条款（与 pipeline.py 中插入文案逐字一致）
OCR_TOLERANCE_NOTE = (
    "注意：本卷答案经 OCR 识别，可能存在个别错别字、缺字、串行或识别不清，"
    "请结合笔迹与上下文语义进行判断，不要因个别 OCR 误识别就直接判错；"
    "确无法辨认时才按最可能判定并在 comment 中说明。"
)

# 作文系统 prompt 的 OCR 噪声宽容条款（与 essay_grading.py 中插入文案逐字一致）
ESSAY_OCR_TOLERANCE_NOTE = (
    "正文来自手写 OCR，可能存在错别字或漏字，"
    "请按上下文语义理解内容，不要逐字扣错字，正常进行评分与评语。"
)


# ---------------------------------------------------------------- 三个判题 prompt 常量

@pytest.mark.parametrize(
    "prompt",
    [
        pipeline.PROMPT_BLOCK,
        pipeline.PROMPT_BLOCK_REF,
        pipeline.PROMPT_BLOCK_SMART_REF,
    ],
    ids=["PROMPT_BLOCK", "PROMPT_BLOCK_REF", "PROMPT_BLOCK_SMART_REF"],
)
def test_grading_prompts_contain_ocr_tolerance_note(prompt):
    assert OCR_TOLERANCE_NOTE in prompt
    for kw in ("OCR", "错别字", "语义"):
        assert kw in prompt


def test_prompt_block_existing_paragraphs_preserved():
    text = pipeline.PROMPT_BLOCK
    # 既有 is_question 判定逻辑仍在
    assert "is_question: true" in text
    assert "is_question: false" in text
    assert "学生手写" in text
    # 输出格式要求仍在
    assert "只输出一个合法 JSON" in text
    assert '"is_question": true 或 false' in text


def test_prompt_block_ref_existing_paragraphs_preserved():
    text = pipeline.PROMPT_BLOCK_REF
    assert "标准答案" in text
    assert "is_question" in text
    assert "严格按标准答案批改" in text
    assert "只输出一个合法 JSON" in text


def test_prompt_block_smart_ref_existing_paragraphs_preserved():
    text = pipeline.PROMPT_BLOCK_SMART_REF
    assert "双重校验" in text
    assert "核心原则" in text
    assert "初级阅卷员" in text
    assert "只输出一个合法 JSON" in text


# ---------------------------------------------------------------- 作文系统 prompt

def test_essay_system_prompt_contains_ocr_tolerance_note():
    tpl = essay_grading.ESSAY_SYSTEM_PROMPT_TEMPLATE
    assert ESSAY_OCR_TOLERANCE_NOTE in tpl
    for kw in ("OCR", "错别字", "漏字", "语义"):
        assert kw in tpl


def test_essay_system_prompt_existing_paragraphs_preserved():
    tpl = essay_grading.ESSAY_SYSTEM_PROMPT_TEMPLATE
    # A2 维度化评分关键词未被破坏
    assert "<essay_dimensions>" in tpl
    assert "<essay_score>" in tpl
    # 既有板块/结构仍在
    assert "【作文分段概述】" in tpl
    assert "【老师总评】" in tpl
    assert "六、异常情况" in tpl
    assert "重新拍照或扫描" in tpl


# ---------------------------------------------------------------- prompt 组装注入（monkeypatch fake client）

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


def _capture_block_prompt(client_call):
    """调用组装函数，返回组装后消息里的 text prompt（提取最后一段 text 内容）。"""
    captured = {}
    payload = '{"is_question": false, "result": "", "comment": ""}'
    client = _FakeClient(captured, payload)
    client_call(client)
    content = captured["messages"][0]["content"]
    text_parts = [c["text"] for c in content if c.get("type") == "text"]
    assert text_parts, "组装后的消息未找到 text 部分"
    return text_parts[0]


def test_grade_one_block_prompt_injects_ocr_tolerance():
    prompt_text = _capture_block_prompt(
        lambda client: pipeline._grade_one_block(client, "data:image/jpeg;base64,AA", 3)
    )
    assert OCR_TOLERANCE_NOTE in prompt_text
    assert "{index}" not in prompt_text  # format 已填充


def test_grade_one_block_reference_prompt_injects_ocr_tolerance():
    prompt_text = _capture_block_prompt(
        lambda client: pipeline._grade_one_block_reference(
            client,
            "data:image/jpeg;base64,BB",
            "data:image/jpeg;base64,CC",
            3,
        )
    )
    assert OCR_TOLERANCE_NOTE in prompt_text
    assert "{index}" not in prompt_text


def test_grade_one_block_smart_ref_prompt_injects_ocr_tolerance():
    prompt_text = _capture_block_prompt(
        lambda client: pipeline._grade_one_block_smart_ref(
            client,
            "data:image/jpeg;base64,DD",
            "data:image/jpeg;base64,EE",
            3,
            {"is_question": False, "result": "", "comment": ""},
        )
    )
    assert OCR_TOLERANCE_NOTE in prompt_text
    assert "{index}" not in prompt_text
    assert "初级阅卷员" in prompt_text  # 既有段落仍在


def test_grade_essay_user_prompt_injects_ocr_tolerance(monkeypatch):
    captured = {}
    payload = "【作文分段概述】\n开头：好。\n【老师总评】\n不错。\n<essay_score>83</essay_score>"
    monkeypatch.setattr("app.grading.pipeline._get_openai_client", lambda: _FakeClient(captured, payload))
    monkeypatch.setattr(essay_grading, "_resolve_essay_model", lambda: "test-model")

    # 含错别字的伪 OCR 作文正文：一位/医生/帮助 均被误识别
    fake_ocr_content = "我长大后想成为一为医升，帮主别人。"
    essay_grading.grade_essay_with_qwen(
        "我的理想",
        fake_ocr_content,
        "批改标准正文",
        {},
        None,
    )

    user_content = captured["messages"][0]["content"]
    assert ESSAY_OCR_TOLERANCE_NOTE in user_content
    assert fake_ocr_content in user_content  # OCR 文本原样进入 user prompt
    assert "<essay_dimensions>" in user_content  # A2 维度段未破坏
    assert "【老师总评】" in user_content
