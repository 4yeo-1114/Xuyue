# -*- coding: utf-8 -*-
"""11.11-12 前半：一个空多个可接受答案的显式设置（29题词形半分不在本批）。

台账原话（龙欣 26.11.11）：「英语老师问题：27题多个正确答案怎么设置评分标准」。
设置口径：识别列表的答案文本用 | 分隔（全角｜同义）= 显式声明该空有多个可接受
答案，学生命中任一个即判对。锁定三点：
  1) 解析：≥2 段才算显式多解；「答案|」这类带空段的管道噪声不算；
  2) 多选字母集合规则让位：「A|C」= A、C 任一即可，不是多选「AC」，不能按
     少选半对改判（20261021 用户定的字母集合规则只对真多选生效，仍压 VL）；
  3) 判分提示词带显式规则句，每槽 metadata 给 standard_answer_variants。
"""

from __future__ import annotations

import pytest
from PIL import Image

from app.grading.reference_vlm_grading import (
    CORRECT,
    PARTIAL,
    VlmGradingTask,
    VlmQuestionBatchTask,
    _accepted_answer_variants,
    _batch_task_payload,
    _build_batch_qwen_prompt,
    _multi_select_letter_rule,
    extract_vlm_questions,
)


# ---------------------------------------------------------------- 1

def test_accepted_answer_variants_parsing():
    assert _accepted_answer_variants("甲|乙") == ["甲", "乙"]
    assert _accepted_answer_variants("甲｜乙｜丙") == ["甲", "乙", "丙"]
    # 带空段的管道噪声不算显式多解
    assert _accepted_answer_variants("答案|") == []
    assert _accepted_answer_variants("|") == []
    # 单答案维持原语义
    assert _accepted_answer_variants("答案") == []
    assert _accepted_answer_variants("") == []
    # 段内空白剥掉，别把「 甲 」原样给学生看
    assert _accepted_answer_variants(" 甲 | 乙 ") == ["甲", "乙"]


# ---------------------------------------------------------------- 2

def test_multi_select_rule_yields_to_explicit_variants():
    # 「A|C」= A、C 任一即可：学生答 A 应该由 VL 判对，不许字母集合规则
    # 把它压成「少选」半对
    assert _multi_select_letter_rule("A", "A|C") is None
    assert _multi_select_letter_rule("C", "A｜C") is None
    # 真多选「AC」不带 |：20261021 用户定规则照旧压 VL（少选=半对）
    assert _multi_select_letter_rule("A", "AC") == (PARTIAL, 0.5)
    assert _multi_select_letter_rule("CA", "AC") == (CORRECT, None)


# ---------------------------------------------------------------- 3

def _make_question(img_path, qus_id=1):
    raw = {
        "qus_results": [
            {
                "qus_id": qus_id,
                "location": {
                    "qus_location": [10, 10, 190, 60],
                    "ans_location": [[10, 70, 190, 110]],
                },
                "qus_elements": {"question_words": "把句子译成英语"},
            }
        ]
    }
    questions = extract_vlm_questions(raw, image_path=str(img_path))
    assert len(questions) == 1
    return questions[0]


def _make_task(question, standard_text):
    return VlmGradingTask(
        task_id=1,
        student_question=question,
        standard_question=question,
        student_answer_bbox=[10, 70, 190, 110],
        standard_answer_bbox=[10, 70, 190, 110],
        student_context_bbox=[10, 10, 190, 110],
        standard_context_bbox=[10, 10, 190, 110],
        sub_index=1,
        has_mark_anchor=False,
        has_handwriting_location=False,
        is_answer_slot=True,
        anchor_source="layout",
        template_slot_id=None,
        standard_answer_text=standard_text,
    )


@pytest.fixture()
def img(tmp_path):
    path = tmp_path / "standard.png"
    Image.new("RGB", (200, 400), "white").save(path)
    return path


def test_prompt_and_payload_carry_variants(img):
    question = _make_question(img)
    task = _make_task(
        question,
        "There is a dining hall and a gym in our school|There's a dining hall and a gym in our school",
    )
    batch = VlmQuestionBatchTask(
        batch_id=1,
        student_question=question,
        standard_question=question,
        slots=[task],
    )

    payload = _batch_task_payload(batch)
    assert payload["slots"][0]["standard_answer_variants"] == [
        "There is a dining hall and a gym in our school",
        "There's a dining hall and a gym in our school",
    ]

    prompt = _build_batch_qwen_prompt(batch, "学生甲")
    # 显式规则句进提示词：命中任一即判对
    assert "MULTIPLE ACCEPTABLE ANSWERS" in prompt
    assert "ANY ONE alternative" in prompt
    # metadata 带拆好的候选
    assert "standard_answer_variants" in prompt

    # 单答案不带候选，也不用全角竖线误伤
    task_plain = _make_task(question, "答案")
    payload_plain = _batch_task_payload(
        VlmQuestionBatchTask(
            batch_id=2,
            student_question=question,
            standard_question=question,
            slots=[task_plain],
        )
    )
    assert payload_plain["slots"][0]["standard_answer_variants"] == []
