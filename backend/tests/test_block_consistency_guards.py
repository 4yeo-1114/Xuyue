# -*- coding: utf-8 -*-
"""块一致性闸（1019 语文审计：一槽三源互不校验 → 判语/三列文本张冠李戴）。

锁四件事：
1. 取词匹配有界唯一（并框/漂移/远框宁缺勿串，不再无上限最近邻）；
2. located_no 改道有门槛（与模型引文一致才换，对不上转待确认，不再无条件换）；
3. 图中/评语题号与配对题号冲突 → 待确认（4₂ 挂第 4 题框在第 5 题这类错挂）；
4. 判未作答但标准=作答同文 → 待确认（灾难块形态 `[未作答] 标准=X 作答=X`）；
5. 槽框物理归属校验：不在本题区∩恰在唯一别区才换绑（宁缺勿乱）。
"""
from __future__ import annotations

from PIL import Image

from app.grading import reference_vlm_grading
from app.grading.reference_vlm_grading import (
    CORRECT,
    PENDING,
    UNANSWERED,
    WRONG,
    _answer_text_for_slot,
    _apply_question_no_guard,
    _apply_standard_text_conflict_guard,
    _apply_unanswered_text_guard,
    _bbox_match_position,
    _rebind_question_by_slot_bbox,
    VlmGradingTask,
    VlmQuestion,
    VlmQuestionBatchTask,
    grade_reference_vlm_paper,
)

BBOX = [20, 20, 120, 60]


def _q(
    qid: int,
    *,
    display_index: int = 1,
    printed_no=None,
    question_bbox=None,
    answer_words=None,
    answer_bboxes=None,
) -> VlmQuestion:
    return VlmQuestion(
        question_id=qid,
        display_index=display_index,
        raw={},
        bbox=[0, 0, 180, 90],
        question_bbox=question_bbox if question_bbox is not None else [0, 0, 180, 90],
        answer_bbox=list(BBOX),
        answer_bboxes=answer_bboxes if answer_bboxes is not None else [list(BBOX)],
        question_words="题干",
        answer_words=list(answer_words if answer_words is not None else ["佩服"]),
        choices=[],
        question_type="填空",
        printed_no=printed_no,
    )


def _task(
    *,
    printed_no_stu=None,
    printed_no_std=None,
    student_question=None,
    standard_question=None,
) -> VlmGradingTask:
    stu = student_question or _q(11, printed_no=printed_no_stu)
    std = standard_question or _q(21, printed_no=printed_no_std)
    return VlmGradingTask(
        task_id=7,
        student_question=stu,
        standard_question=std,
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


def _decision(code: int = CORRECT, **extra) -> dict:
    data = {
        "question_id": 7,
        "correctResult": code,
        "result": {1: "对", 2: "错", 3: "未作答", 5: "待确认"}.get(code, "错"),
        "reason": "与标准答案一致，判对。",
        "analysis": "与标准答案一致，判对。",
        "confidence": 0.9,
        "partial_ratio": None,
        "transcription": "佩服",
        "read_confidence": 0.95,
        "standard_quote": "",
        "located_no": None,
        "read_uncertain": False,
    }
    data.update(extra)
    return data


# ── 1. 取词匹配有界唯一 ─────────────────────────────────────────────


def test_bbox_match_position_far_box_returns_none_instead_of_nearest():
    # 旧无上限最近邻会返回 0；现在漂到空地宁缺勿串
    assert _bbox_match_position([[10, 10, 50, 50]], [500, 500, 540, 540]) is None


def test_bbox_match_position_union_covering_two_slots_is_ambiguous():
    # 并框盖住两槽：任取一个都是串位 → None（上层回退转写）
    boxes = [[10, 10, 50, 50], [60, 10, 100, 50]]
    assert _bbox_match_position(boxes, [10, 10, 100, 50]) is None


def test_bbox_match_position_exact_and_jittered_still_match():
    boxes = [[10, 10, 50, 50], [60, 10, 100, 50]]
    assert _bbox_match_position(boxes, [60, 10, 100, 50]) == 1
    assert _bbox_match_position(boxes, [61, 12, 99, 48]) == 1
    assert _bbox_match_position(boxes, [10, 10, 50, 50]) == 0


def test_answer_text_for_slot_union_target_returns_none_not_shuffled_word():
    q = _q(
        1,
        answer_words=["3", "4"],
        answer_bboxes=[[10, 10, 50, 50], [60, 10, 100, 50]],
    )
    assert _answer_text_for_slot(q, [10, 10, 100, 50]) is None
    assert _answer_text_for_slot(q, [500, 500, 540, 540]) is None
    assert _answer_text_for_slot(q, [60, 10, 100, 50]) == "4"


# ── 2. located_no 改道有门槛 + 文本一致性 ───────────────────────────


def test_standard_text_conflict_quote_disagrees_with_shown_forces_pending():
    decision = _decision(
        CORRECT,
        standard_quote="第13题：空间",
        located_no=13,
        reason="该空考查写作顺序，判定正确。",
    )
    assert _apply_standard_text_conflict_guard(decision, "不矛盾。因为济南四周有一圈小山") is True
    assert decision["correctResult"] == PENDING
    assert decision["result"] == "待确认"
    assert decision["ink_evidence"]["source"] == "standard_text_conflict"


def test_standard_text_conflict_quote_agreeing_or_empty_keeps_verdict():
    agreed = _decision(CORRECT, standard_quote="第13题：空间")
    assert _apply_standard_text_conflict_guard(agreed, "空间") is False
    assert agreed["correctResult"] == CORRECT
    no_quote = _decision(CORRECT, standard_quote="")
    assert _apply_standard_text_conflict_guard(no_quote, "空间") is False
    assert no_quote["correctResult"] == CORRECT
    # 人工终态豁免
    human = _decision(CORRECT, standard_quote="第13题：空间")
    assert (
        _apply_standard_text_conflict_guard(
            human, "不矛盾", cache_hit={"source": "human"}
        )
        is False
    )
    assert human["correctResult"] == CORRECT


# ── 3. 题号冲突闸 ───────────────────────────────────────────────────


def test_question_no_guard_located_conflict_forces_pending():
    decision = _decision(CORRECT, located_no=5, reason="该空属于第5题，学生作答正确。")
    task = _task(printed_no_stu="4", printed_no_std="4")
    assert _apply_question_no_guard(decision, task) is True
    assert decision["correctResult"] == PENDING
    assert "第5题" in decision["reason"]
    assert decision["ink_evidence"]["source"] == "question_no_conflict"


def test_question_no_guard_comment_claim_without_located_no():
    decision = _decision(
        UNANSWERED,
        reason="该空对应第13题，标准答案为「空间」。学生此处留白，判为未答。",
    )
    task = _task(printed_no_stu="1")
    assert _apply_question_no_guard(decision, task) is True
    assert decision["correctResult"] == PENDING


def test_question_no_guard_agreeing_or_unknown_pairing_keeps_verdict():
    ok = _decision(CORRECT, located_no=4, reason="定位到印刷题号为第4题，判对。")
    assert _apply_question_no_guard(ok, _task(printed_no_stu="4")) is False
    assert ok["correctResult"] == CORRECT
    # 合并块两卷都无印刷题号 → fail-open
    unknown = _decision(CORRECT, located_no=13)
    assert _apply_question_no_guard(unknown, _task(printed_no_stu=None)) is False
    assert unknown["correctResult"] == CORRECT
    # 人工终态豁免
    human = _decision(CORRECT, located_no=5)
    assert (
        _apply_question_no_guard(
            human, _task(printed_no_stu="4"), cache_hit={"source": "human"}
        )
        is False
    )


# ── 4. 未作答同文闸 ─────────────────────────────────────────────────


def test_unanswered_identical_texts_force_pending():
    decision = _decision(UNANSWERED, reason="作答区无手写笔迹，按未作答处理")
    assert _apply_unanswered_text_guard(
        decision, "海日生残夜，江春入旧年", "海日生残夜 江春入旧年"
    ) is True
    assert decision["correctResult"] == PENDING
    assert decision["ink_evidence"]["source"] == "unanswered_text_identity"


def test_unanswered_different_texts_keep_circle():
    decision = _decision(UNANSWERED, reason="作答区无手写笔迹，按未作答处理")
    assert _apply_unanswered_text_guard(decision, "空间", "不矛盾。因为济南") is False
    assert decision["correctResult"] == UNANSWERED
    assert _apply_unanswered_text_guard(decision, "", "空间") is False
    # 对/错不受这道闸管
    right = _decision(CORRECT)
    assert _apply_unanswered_text_guard(right, "空间", "空间") is False
    assert right["correctResult"] == CORRECT


# ── 5. 槽框物理归属校验 ─────────────────────────────────────────────


def test_rebind_slot_outside_current_but_inside_unique_other():
    q4 = _q(4, printed_no="4", question_bbox=[100, 100, 400, 400])
    q5 = _q(5, printed_no="5", question_bbox=[500, 100, 800, 400])
    # 4₂ 的框挂在 Q4 名下，物理上落在 Q5 区内 → 换绑 Q5
    rebound = _rebind_question_by_slot_bbox([q4, q5], q4, [550, 200, 650, 260], (900, 500))
    assert rebound is q5
    # 框在本区 → 不动
    assert _rebind_question_by_slot_bbox([q4, q5], q4, [150, 150, 250, 200], (900, 500)) is q4
    # 都不覆盖 → 不动（宁缺勿乱）
    assert _rebind_question_by_slot_bbox([q4, q5], q4, [850, 450, 880, 480], (900, 500)) is q4


def test_rebind_slot_ambiguous_overlap_keeps_current():
    q12 = _q(12, question_bbox=[100, 100, 800, 500])
    q13 = _q(13, question_bbox=[300, 300, 600, 700])
    # 中心落在两题区重叠处 → 不换绑
    same = _rebind_question_by_slot_bbox([q12, q13], q12, [400, 400, 450, 450], (900, 800))
    assert same is q12


# ── 6. 全链路：located_no 改道有门槛（对照 test 3243 的兄弟串场景）──


def test_grade_paper_located_no_redirect_gated_by_quote(monkeypatch, tmp_path):
    # 引文与 located 行不一致（模型自相矛盾）→ 不改道、转待确认、痕迹带出
    std = _q(21, display_index=1, question_bbox=[269, 210, 1359, 375], answer_words=[])
    stu = _q(
        11,
        display_index=1,
        question_bbox=[269, 210, 1359, 375],
        answer_words=[],
        answer_bboxes=[[10, 10, 50, 50]],
    )
    std.answer_bboxes = []
    std.answer_bbox = None

    def _fake_vl(_client, _model, batch, _std_url, _stu_url, _student_name, family_hint="", answer_table_text=""):
        return {
            task.task_id: {
                "question_id": task.task_id,
                "correctResult": 1,
                "result": "对",
                "transcription": "B",
                "read_confidence": 0.95,
                "reason": "一致",
                "analysis": "一致",
                "confidence": 0.9,
                "located_no": 2,
                # 引文自称第 2 题 B，但表里第 2 题是「乙」——模型自相矛盾
                "standard_quote": "第2题：B",
            }
            for task in batch.slots
        }

    def _slot_task():
        return VlmGradingTask(
            task_id=7,
            student_question=stu,
            standard_question=std,
            student_answer_bbox=[10, 10, 50, 50],
            standard_answer_bbox=[269, 210, 1359, 375],
            student_context_bbox=[10, 10, 50, 50],
            standard_context_bbox=[269, 210, 1359, 375],
            sub_index=1,
            has_mark_anchor=True,
            has_handwriting_location=True,
            is_answer_slot=True,
            anchor_source="template",
            template_slot_id=None,
        )

    monkeypatch.setattr(reference_vlm_grading, "extract_vlm_questions", lambda raw, image_path="": [stu])
    monkeypatch.setattr(reference_vlm_grading, "_get_qwen_client_and_model", lambda: (object(), "test-model"))
    monkeypatch.setattr(reference_vlm_grading, "_call_qwen_for_question_batch", _fake_vl)
    monkeypatch.setattr(
        reference_vlm_grading, "_crop_regions_to_data_url", lambda *a, **k: ("data:fake", b"")
    )
    monkeypatch.setattr(reference_vlm_grading, "_save_reference_vlm_artifacts", lambda **_k: None)
    monkeypatch.setattr(reference_vlm_grading, "_build_grading_tasks", lambda *a, **k: [_slot_task()])
    monkeypatch.setattr(
        reference_vlm_grading,
        "_group_grading_tasks",
        lambda tasks: [
            VlmQuestionBatchTask(batch_id=1, student_question=stu, standard_question=std, slots=list(tasks))
        ],
    )

    std_img, stu_img = tmp_path / "std.png", tmp_path / "stu.png"
    for p in (std_img, stu_img):
        Image.new("RGB", (100, 100), "white").save(p)
    answer_table = {
        "questions": [
            {
                "display_index": 1001,
                "printed_no": "1",
                "source_display_index": 1,
                "question_bbox": [269, 210, 1359, 375],
                "slots": [{"sub_index": 1, "bbox": [269, 210, 1359, 375], "answer_text": "D"}],
                "full_answer": "D",
            },
            {
                "display_index": 1002,
                "printed_no": "2",
                "source_display_index": 1,
                "question_bbox": [269, 210, 1359, 375],
                "slots": [{"sub_index": 1, "bbox": [269, 210, 1359, 375], "answer_text": "乙"}],
                "full_answer": "乙",
            },
        ]
    }
    _result, blocks, _raw, _src = grade_reference_vlm_paper(
        "标准答案.jpg",
        {"raw": {}, "image_path": str(std_img), "questions": [std]},
        "学生_1.jpg",
        {"raw": {}, "image_path": str(stu_img)},
        folder_safe="located-no-gated-test",
        answer_table=answer_table,
    )
    # 不再无条件改道：引文 B 与 located 行「乙」对不上 → 保持预查文本（兄弟串 D\n乙）
    assert blocks[0]["correct_answer"] == "D\n乙"
    # 判语/展示对不上 → 待确认 + 缓存拦截痕迹
    assert blocks[0]["result"] == "待确认"
    assert isinstance(blocks[0].get("ink_evidence"), dict)
