# -*- coding: utf-8 -*-
"""空白槽墨迹闸（2026-10-16「观察与梳理那么多空白你去打勾干什么」）。

判分双图同屏，image 1 标准答案写在同样的空上，VL 会把 image 1 的答案抄进
transcription 判「对」→ 空白被打勾。锁三件事：
1. 标准同位有墨迹、学生同位只有印刷线 → 对/错/半对 强制未作答（空心圈），
   reason 整句替换（防句尾「判对。」触发 conclusion_guard 翻待确认）、
   幻觉转写清空（防 read_guard 翻待确认）；
2. 真笔迹 / 小选择答案（std 同样小）不动；人工终态缓存命中豁免；
3. ink_evidence 痕迹随 sub_result → block 带出（verdict_cache 不入缓存）。
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from app.grading import verdict_cache
from app.grading.reference_vlm_grading import (
    CORRECT,
    PENDING,
    PARTIAL,
    UNANSWERED,
    WRONG,
    _BLANK_GUARD_REASON,
    _UNANSWERED_INK_REASON,
    _apply_blank_ink_guard,
    _apply_unanswered_ink_guard,
    _build_blocks,
    _insert_sub_grading_result,
    VlmGradingTask,
    VlmQuestion,
)

BBOX = [20, 20, 120, 60]  # 100×40 = 4000px


def _img() -> Image.Image:
    return Image.new("RGB", (200, 100), "white")


def _draw_ink(img: Image.Image, bbox, *, coverage: float = 0.5) -> None:
    """bbox 内画粗黑横线，凑出指定墨迹覆盖率（模拟手写）。"""
    x1, y1, x2, y2 = bbox
    area = (x2 - x1) * (y2 - y1)
    draw = ImageDraw.Draw(img)
    # 每条线宽 4px：条数 ≈ coverage * area / (4 * 线长)
    line_len = x2 - x1
    count = max(1, int(coverage * area / (4 * line_len)))
    step = max(4, (y2 - y1) // max(1, count))
    for y in range(y1, y2 - 3, step):
        draw.line([(x1, y), (x2, y)], fill="black", width=4)


def _draw_print_line(img: Image.Image, bbox) -> None:
    """印刷填空下划线：仅底部一条细线（实测空白槽墨迹 0.05–0.07）。"""
    x1, y1, x2, y2 = bbox
    ImageDraw.Draw(img).line([(x1, y2 - 1), (x2, y2 - 1)], fill=(120, 120, 120), width=2)


def _task() -> VlmGradingTask:
    def q(qid: int) -> VlmQuestion:
        return VlmQuestion(
            question_id=qid,
            display_index=1,
            raw={},
            bbox=[0, 0, 180, 90],
            question_bbox=[0, 0, 180, 90],
            answer_bbox=list(BBOX),
            answer_bboxes=[list(BBOX)],
            question_words="他是____笔下的人物",
            answer_words=["佩服"],
            choices=[],
            question_type="填空",
        )

    return VlmGradingTask(
        task_id=7,
        student_question=q(11),
        standard_question=q(21),
        student_answer_bbox=list(BBOX),
        standard_answer_bbox=list(BBOX),
        student_context_bbox=list(BBOX),
        standard_context_bbox=list(BBOX),
        sub_index=1,
        has_mark_anchor=True,
        has_handwriting_location=True,
        is_answer_slot=True,
        anchor_source="template",
        template_slot_id=None,
        standard_answer_text="佩服",
    )


def _decision(code: int = CORRECT, *, reason: str = "与标准答案一致，判对。") -> dict:
    return {
        "question_id": 7,
        "correctResult": code,
        "result": {1: "对", 2: "错", 3: "未作答", 4: "半对", 5: "待确认"}.get(code, "错"),
        "reason": reason,
        "analysis": reason,
        "confidence": 0.9,
        "partial_ratio": 0.6 if code == PARTIAL else None,
        "transcription": "佩服",
        "read_confidence": 0.95,
        "standard_quote": "",
        "located_no": None,
        "read_uncertain": False,
    }


def test_blank_guard_downgrades_hallucinated_correct():
    """标准空写满、学生空只有印刷线 → 对 强制未作答；reason 整句替换、转写清空。"""
    std_img, stu_img = _img(), _img()
    _draw_ink(std_img, BBOX, coverage=0.5)
    _draw_print_line(stu_img, BBOX)
    decision = _decision(CORRECT)

    assert _apply_blank_ink_guard(decision, _task(), std_img, stu_img) is True
    assert decision["correctResult"] == UNANSWERED
    assert decision["result"] == "未作答"
    assert decision["partial_ratio"] is None
    assert decision["reason"] == _BLANK_GUARD_REASON
    assert decision["analysis"] == _BLANK_GUARD_REASON
    assert decision["transcription"] == ""
    trace = decision["ink_evidence"]
    assert trace["action"] == "downgraded"
    assert trace["source"] == "std_ink_compare"
    assert trace["was_result"] == "对"
    assert trace["stu_ink"] < 0.12


def test_blank_guard_downgrades_wrong_and_partial_too():
    std_img, stu_img = _img(), _img()
    _draw_ink(std_img, BBOX, coverage=0.5)
    _draw_print_line(stu_img, BBOX)
    for code in (WRONG, PARTIAL):
        decision = _decision(code)
        assert _apply_blank_ink_guard(decision, _task(), std_img, stu_img) is True
        assert decision["correctResult"] == UNANSWERED
        assert decision["partial_ratio"] is None


def test_blank_guard_keeps_real_answers():
    """两侧同位都有手写（stu/std 比≈1）→ 不动。"""
    std_img, stu_img = _img(), _img()
    _draw_ink(std_img, BBOX, coverage=0.5)
    _draw_ink(stu_img, BBOX, coverage=0.5)
    decision = _decision(CORRECT)
    assert _apply_blank_ink_guard(decision, _task(), std_img, stu_img) is False
    assert decision["correctResult"] == CORRECT
    assert "ink_evidence" not in decision


def test_blank_guard_keeps_small_choice_when_std_also_small():
    """选择小答案两侧墨迹都小（真数据 Q3 'A' stu 0.08/std 0.08）→ 比值放行。"""
    std_img, stu_img = _img(), _img()
    # 各画一个小方块 ≈8% 覆盖
    for img in (std_img, stu_img):
        ImageDraw.Draw(img).rectangle([30, 30, 55, 55], fill="black")
    decision = _decision(CORRECT)
    assert _apply_blank_ink_guard(decision, _task(), std_img, stu_img) is False
    assert decision["correctResult"] == CORRECT


def test_blank_guard_exempts_human_cache():
    """人工终态缓存命中绝不自动翻。"""
    std_img, stu_img = _img(), _img()
    _draw_ink(std_img, BBOX, coverage=0.5)
    _draw_print_line(stu_img, BBOX)
    decision = _decision(CORRECT)
    hit = {"result": "对", "comment": "老师改的", "source": "human"}
    assert _apply_blank_ink_guard(decision, _task(), std_img, stu_img, cache_hit=hit) is False
    assert decision["correctResult"] == CORRECT
    # AI 缓存命中照闸
    decision2 = _decision(CORRECT)
    hit_ai = {"result": "对", "comment": "", "source": "ai"}
    assert _apply_blank_ink_guard(decision2, _task(), std_img, stu_img, cache_hit=hit_ai) is True
    assert decision2["correctResult"] == UNANSWERED


def test_blank_guard_leaves_unanswered_and_pending():
    """未作答/待确认不是本闸目标（不重写 reason、不盖痕迹）。"""
    std_img, stu_img = _img(), _img()
    _draw_ink(std_img, BBOX, coverage=0.5)
    _draw_print_line(stu_img, BBOX)
    for code in (UNANSWERED, PENDING):
        decision = _decision(code, reason="原判语")
        assert _apply_blank_ink_guard(decision, _task(), std_img, stu_img) is False
        assert decision["correctResult"] == code
        assert decision["reason"] == "原判语"


def test_ink_trace_survives_insert_and_blocks():
    """痕迹穿过 _insert_sub_grading_result 的二次归一化 → block → 拦缓存。"""
    std_img, stu_img = _img(), _img()
    _draw_ink(std_img, BBOX, coverage=0.5)
    _draw_print_line(stu_img, BBOX)
    task = _task()
    decision = _decision(CORRECT)
    assert _apply_blank_ink_guard(decision, task, std_img, stu_img) is True

    stu_q = task.student_question
    _insert_sub_grading_result(
        stu_q,
        decision,
        task_id=task.task_id,
        sub_index=1,
        answer_bbox=task.student_answer_bbox,
        has_mark_anchor=True,
        has_handwriting_location=True,
        is_answer_slot=True,
    )
    sub = stu_q.raw["sub_grading_results"][0]
    # 二次 _normalize_decision 不得翻待确认（reason 整句替换 + 转写清空的前提）
    assert sub["result"] == "未作答"
    assert sub["correctResult"] == UNANSWERED
    assert sub["reason"] == _BLANK_GUARD_REASON
    assert sub["ink_evidence"]["action"] == "downgraded"

    blocks = _build_blocks([stu_q])
    assert blocks[0]["result"] == "未作答"
    assert blocks[0]["ink_evidence"]["source"] == "std_ink_compare"
    assert verdict_cache._has_guard_trace(blocks[0]) is True


# ── 反向闸（1016 邓雨彤_1：师傅写清楚了却被判未作答，空心圈画到字上）─────


def test_unanswered_ink_guard_promotes_written_to_pending():
    """判未作答但学生同位有真笔迹 → 待确认（不画圈），reason 整句替换、转写清空。"""
    std_img, stu_img = _img(), _img()
    _draw_ink(std_img, BBOX, coverage=0.5)
    _draw_ink(stu_img, BBOX, coverage=0.5)  # 「师傅」写得清清楚楚
    decision = _decision(UNANSWERED, reason="学生未作答。")

    assert _apply_unanswered_ink_guard(decision, _task(), std_img, stu_img) is True
    assert decision["correctResult"] == PENDING
    assert decision["result"] == "待确认"
    assert decision["partial_ratio"] is None
    assert decision["reason"] == _UNANSWERED_INK_REASON
    assert decision["analysis"] == _UNANSWERED_INK_REASON
    assert decision["transcription"] == ""
    trace = decision["ink_evidence"]
    assert trace["action"] == "pending_high_ink"
    assert trace["source"] == "stu_ink_unanswered"
    assert trace["was_result"] == "未作答"
    assert trace["stu_ink"] >= 0.12


def test_unanswered_ink_guard_keeps_truly_blank():
    """真空白（只有印刷线，墨迹 0.03–0.07）→ 未作答不动，空心圈照画。"""
    std_img, stu_img = _img(), _img()
    _draw_ink(std_img, BBOX, coverage=0.5)
    _draw_print_line(stu_img, BBOX)
    decision = _decision(UNANSWERED, reason="原判语")
    assert _apply_unanswered_ink_guard(decision, _task(), std_img, stu_img) is False
    assert decision["correctResult"] == UNANSWERED
    assert decision["reason"] == "原判语"
    assert "ink_evidence" not in decision


def test_unanswered_ink_guard_leaves_other_results():
    """对/错/半对/待确认不是本闸目标（空白闸管对错半对）。"""
    std_img, stu_img = _img(), _img()
    _draw_ink(std_img, BBOX, coverage=0.5)
    _draw_ink(stu_img, BBOX, coverage=0.5)
    for code in (CORRECT, WRONG, PARTIAL, PENDING):
        decision = _decision(code, reason="原判语")
        assert _apply_unanswered_ink_guard(decision, _task(), std_img, stu_img) is False
        assert decision["correctResult"] == code
        assert decision["reason"] == "原判语"


def test_unanswered_ink_guard_exempts_human_cache():
    """人工终态缓存命中绝不自动翻。"""
    std_img, stu_img = _img(), _img()
    _draw_ink(std_img, BBOX, coverage=0.5)
    _draw_ink(stu_img, BBOX, coverage=0.5)
    decision = _decision(UNANSWERED)
    hit = {"result": "未作答", "comment": "老师认定没写", "source": "human"}
    assert _apply_unanswered_ink_guard(decision, _task(), std_img, stu_img, cache_hit=hit) is False
    assert decision["correctResult"] == UNANSWERED
    # AI 缓存命中照闸
    decision2 = _decision(UNANSWERED)
    hit_ai = {"result": "未作答", "comment": "", "source": "ai"}
    assert _apply_unanswered_ink_guard(decision2, _task(), std_img, stu_img, cache_hit=hit_ai) is True
    assert decision2["correctResult"] == PENDING


def test_unanswered_ink_trace_survives_insert_and_blocks():
    """痕迹穿过 _insert_sub_grading_result 的二次归一化 → block → 拦缓存。"""
    std_img, stu_img = _img(), _img()
    _draw_ink(std_img, BBOX, coverage=0.5)
    _draw_ink(stu_img, BBOX, coverage=0.5)
    task = _task()
    decision = _decision(UNANSWERED, reason="学生未作答。")
    assert _apply_unanswered_ink_guard(decision, task, std_img, stu_img) is True

    stu_q = task.student_question
    _insert_sub_grading_result(
        stu_q,
        decision,
        task_id=task.task_id,
        sub_index=1,
        answer_bbox=task.student_answer_bbox,
        has_mark_anchor=True,
        has_handwriting_location=True,
        is_answer_slot=True,
    )
    sub = stu_q.raw["sub_grading_results"][0]
    # 二次归一化后仍待确认（reason 含「待人工确认」挡 read_guard 追加）
    assert sub["result"] == "待确认"
    assert sub["correctResult"] == PENDING
    assert sub["reason"] == _UNANSWERED_INK_REASON
    assert sub["ink_evidence"]["action"] == "pending_high_ink"

    blocks = _build_blocks([stu_q])
    assert blocks[0]["result"] == "待确认"
    assert blocks[0]["ink_evidence"]["source"] == "stu_ink_unanswered"
    assert verdict_cache._has_guard_trace(blocks[0]) is True


def test_two_guards_compose_without_fighting():
    """空白闸与反向闸共用调用点：空白判未作答、有笔迹判待确认，互不踩。"""
    # ① 空白：对 → 未作答（反向闸不碰低墨迹）
    std_img, stu_img = _img(), _img()
    _draw_ink(std_img, BBOX, coverage=0.5)
    _draw_print_line(stu_img, BBOX)
    d1 = _decision(CORRECT)
    assert _apply_blank_ink_guard(d1, _task(), std_img, stu_img) is True
    assert _apply_unanswered_ink_guard(d1, _task(), std_img, stu_img) is False
    assert d1["correctResult"] == UNANSWERED
    # ② 有笔迹：未作答 → 待确认（空白闸不碰未作答）
    std_img2, stu_img2 = _img(), _img()
    _draw_ink(std_img2, BBOX, coverage=0.5)
    _draw_ink(stu_img2, BBOX, coverage=0.5)
    d2 = _decision(UNANSWERED)
    assert _apply_blank_ink_guard(d2, _task(), std_img2, stu_img2) is False
    assert _apply_unanswered_ink_guard(d2, _task(), std_img2, stu_img2) is True
    assert d2["correctResult"] == PENDING
