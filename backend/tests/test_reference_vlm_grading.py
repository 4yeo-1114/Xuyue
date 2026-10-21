# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import tempfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw

from app.grading import reference_vlm_grading
from app.grading.router import _reference_standard_document
from app.grading.reference_vlm_grading import (
    PENDING,
    VlmGradingTask,
    VlmQuestion,
    VlmQuestionBatchTask,
    VlmSlotTemplate,
    _answer_table_slot_text,
    _answer_table_summary_text,
    _answer_text_for_slot,
    _build_grading_tasks,
    _build_batch_qwen_prompt,
    _build_blocks,
    _build_slot_qwen_prompt,
    _crop_to_data_url,
    _decision_from_cache_entry,
    _grading_policy_hint,
    _group_grading_tasks,
    _insert_grading_result,
    _insert_sub_grading_result,
    _json_object_from_text,
    _match_questions,
    _match_template_to_paper,
    _normalize_decision,
    _normalize_math_text,
    _normalize_batch_decision,
    _apply_conclusion_guard,
    _objective_letter_conflict,
    _table_quote_mismatch,
    _parse_printed_no,
    _question_for_no_or_bbox,
    _summarize_result_text,
    apply_reference_layout_to_document,
    build_reference_layout_page,
    build_reference_vlm_slot_template,
    confirm_reference_layout,
    draw_reference_vlm_marks_and_save,
    extract_vlm_questions,
    get_confirmed_reference_document,
    grade_reference_vlm_paper,
    load_or_build_reference_answer_table,
    load_reference_layout_for_editing,
    reference_layout_status,
    save_reference_answer_table_edits,
    invalidate_reference_answer_table,
    save_reference_layout_prepare,
    submit_paper_cut_vlm,
)


def _sample_root() -> Path:
    return Path(__file__).resolve().parent.parent / "试卷切题与识别"


# 这些用例会走到 grading_paths()/get_grading_user_id()（例如 router 层
# _reference_standard_sources → _get_grading_path → grading_paths()）。
# 测试环境未走 bind_grading_user_context 依赖，需手动给 ContextVar 注入测试用户。
from app.grading.user_paths import _grading_user_id

_grading_user_id.set("test-user-id")


def test_reference_grading_reads_confirmed_standard_document_by_page():
    confirmed_p2 = {"raw": {"page": 2}, "questions": [object()]}

    assert _reference_standard_document(2, {2: confirmed_p2}) is confirmed_p2
    assert _reference_standard_document(1, {2: confirmed_p2}) == {}


def test_qwen_json_parser_repairs_unescaped_latex_backslashes():
    payload = (
        r'{"question_id":17,"correctResult":1,"result":"对",'
        r'"reason":"分数 $\frac{3}{8}$ 表示 $3 \div 8$。",'
        r'"analysis":"答案为 8。","confidence":0.98}'
    )

    try:
        json.loads(payload)
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError("sample must contain invalid JSON escapes")

    parsed = _json_object_from_text(payload)

    assert parsed["question_id"] == 17
    assert parsed["reason"] == r"分数 $\frac{3}{8}$ 表示 $3 \div 8$。"


def test_reference_analysis_normalizes_math_notation():
    raw = (
        r"根据定义，$5^3 = 5 \times 5 \times 5 = 125$；"
        r"$\frac{3}{8} = 3 \div 8$，且 $x_1^2 \leq \sqrt{9}$。"
    )

    assert _normalize_math_text(raw) == (
        "根据定义，5³ = 5 × 5 × 5 = 125；"
        "3⁄8 = 3 ÷ 8，且 x₁² ≤ √(9)。"
    )


def test_extract_vlm_questions_and_build_blocks():
    # 注意：试卷切题与识别/ 下的 fixture 为合成数据（真实试卷数据从未入库），仅覆盖解析逻辑路径，非真实试卷截图/切题结果。
    root = _sample_root()
    raw = json.loads((root / "试卷切题与识别真实json数据.txt").read_text(encoding="utf-8"))
    questions = extract_vlm_questions(raw, image_path=str(root / "1.jpg"))
    assert len(questions) == 13
    assert questions[0].question_id == 1
    assert questions[0].question_bbox == [298, 436, 1319, 690]

    for idx, q in enumerate(questions):
        _insert_grading_result(
            q,
            {
                "question_id": q.question_id,
                "correctResult": 1 if idx % 2 == 0 else 2,
                "result": "对" if idx % 2 == 0 else "错",
                "reason": "smoke",
                "analysis": "smoke analysis",
                "confidence": 1,
            },
        )

    blocks = _build_blocks(questions)
    assert len(blocks) == 13
    assert blocks[0]["baidu_original_index"] == 1
    assert blocks[0]["baidu_question_bbox"] == [298, 436, 1319, 690]
    assert blocks[0]["bbox"][0] >= blocks[0]["baidu_question_bbox"][0]
    assert blocks[0]["result"] in ("对", "错")


def test_reference_layout_review_persists_split_regions_and_invalidates_on_replace(monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="reference_layout_review_"))
    folder = root / "exam"
    folder.mkdir()
    standard_path = folder / "标准答案.jpg"
    Image.new("RGB", (1200, 1600), "white").save(standard_path)
    monkeypatch.setattr(reference_vlm_grading, "correct_docs_dir", lambda: root)

    raw = {
        "qus_results": [
            {
                "qus_id": 1,
                "location": {
                    "qus_location": [{"coordinate": [100, 100, 700, 600]}],
                    "ans_location": [{"coordinate": [300, 420, 500, 520]}],
                },
                "qus_elements": {"question_words": "图形题"},
            }
        ]
    }
    document = {
        "raw": raw,
        "image_path": str(standard_path),
        "source_path": str(standard_path),
        "image_size": (1200, 1600),
        "questions": extract_vlm_questions(raw, image_path=str(standard_path)),
    }
    page = build_reference_layout_page(
        document,
        page_no=1,
        filename=standard_path.name,
        image_url="/preview",
    )
    page["questions"][0]["regions"].append(
        {"region_id": "diagram", "label": "1-B", "bbox": [780, 100, 1100, 700]}
    )
    prepare_id = save_reference_layout_prepare(
        "exam",
        [{**page, "source_path": str(standard_path), "image_path": str(standard_path), "raw": raw}],
    )
    result = confirm_reference_layout("exam", prepare_id, [page])
    assert result["status"] == "confirmed"
    assert reference_layout_status("exam", {1: standard_path})["confirmed"] is True

    loaded = get_confirmed_reference_document("exam", 1, standard_path, str(standard_path))
    assert loaded is not None
    assert len(loaded["questions"][0].question_regions) == 2
    assert loaded["questions"][0].answer_bboxes == [[300, 420, 500, 520]]

    editing = load_reference_layout_for_editing(
        "exam",
        {1: (standard_path, standard_path)},
        {1: "/saved-preview"},
    )
    assert editing["prepare_id"]
    assert editing["pages"][0]["image_url"] == "/saved-preview"
    assert len(editing["pages"][0]["questions"][0]["regions"]) == 2

    standard_path.write_bytes(standard_path.read_bytes() + b"replaced")
    stale = reference_layout_status("exam", {1: standard_path})
    assert stale["confirmed"] is False
    assert stale["stale_pages"] == [1]


def test_qwen_prompt_separates_objective_and_subjective_policies():
    out_dir = Path(tempfile.mkdtemp(prefix="reference_vlm_policy_"))
    image_path = out_dir / "paper.jpg"
    Image.new("RGB", (800, 600), "white").save(image_path)

    def make_questions(question_type, question_words, choices):
        raw = {
            "result": {
                "qus_result": [
                    {
                        "qus_id": 1,
                        "location": {
                            "qus_location": [{"coordinate": [100, 100, 700, 400]}],
                            "ans_location": [{"coordinate": [300, 250, 400, 300]}],
                        },
                        "qus_elements": {
                            "qus_type": question_type,
                            "question_words": question_words,
                            "answer_words": ["A"],
                            "choices": choices,
                        },
                    }
                ]
            }
        }
        return extract_vlm_questions(raw, image_path=str(image_path))

    objective_questions = make_questions(
        "单项选择题", "请选择正确答案", ["A. 甲", "B. 乙"]
    )
    objective_task = _build_grading_tasks(
        objective_questions,
        objective_questions,
        (800, 600),
        (800, 600),
    )[0]
    objective_prompt = _build_slot_qwen_prompt(objective_task, "student.jpg")
    assert _grading_policy_hint(objective_task) == "objective_strict"
    assert "Apply OBJECTIVE STRICT policy" in objective_prompt
    assert "image 1 is the sole ground truth" in objective_prompt
    assert "Any different, missing, or extra option/value is wrong" in objective_prompt
    assert "This is an objective question. Never apply semantic-equivalence tolerance" in objective_prompt
    assert "SUBJECTIVE SEMANTIC:" not in objective_prompt

    subjective_questions = make_questions(
        "简答题", "请说明这样做的原因", []
    )
    subjective_task = _build_grading_tasks(
        subjective_questions,
        subjective_questions,
        (800, 600),
        (800, 600),
    )[0]
    subjective_prompt = _build_slot_qwen_prompt(subjective_task, "student.jpg")
    assert _grading_policy_hint(subjective_task) == "subjective_semantic"
    assert "Apply SUBJECTIVE SEMANTIC policy" in subjective_prompt
    assert "Accept different wording or an equivalent valid expression" in subjective_prompt
    assert "OBJECTIVE STRICT:" not in subjective_prompt

    unknown_questions = make_questions("", "", [])
    unknown_task = _build_grading_tasks(
        unknown_questions,
        unknown_questions,
        (800, 600),
        (800, 600),
    )[0]
    unknown_prompt = _build_slot_qwen_prompt(unknown_task, "student.jpg")
    assert _grading_policy_hint(unknown_task) == "auto_detect_from_images"
    assert "First classify the visible question from image 1" in unknown_prompt


def test_vlm_crop_is_upscaled_enhanced_and_highlighted_after_resize():
    image = Image.new("RGB", (320, 180), (225, 225, 225))
    draw = ImageDraw.Draw(image)
    draw.line((20, 30, 295, 30), fill=(30, 30, 30), width=2)
    draw.text((90, 70), "A", fill=(45, 45, 45))

    data_url, payload = _crop_to_data_url(
        image,
        [0, 0, 320, 180],
        pad=0,
        highlight_bbox=[80, 55, 170, 120],
    )

    assert data_url.startswith("data:image/jpeg;base64,")
    with Image.open(BytesIO(payload)).convert("RGB") as enhanced:
        assert enhanced.size == (640, 360)
        red_pixels = [
            enhanced.getpixel((x, y))
            for y in range(enhanced.height)
            for x in range(enhanced.width)
            if enhanced.getpixel((x, y))[0] > 160
            and enhanced.getpixel((x, y))[1] < 100
            and enhanced.getpixel((x, y))[2] < 100
        ]
    assert red_pixels


def test_answer_location_uses_all_handwriting_boxes_and_marks_lower_right():
    out_dir = Path(tempfile.mkdtemp(prefix="reference_vlm_answer_bbox_"))
    image_path = out_dir / "paper.jpg"
    Image.new("RGB", (800, 600), "white").save(image_path)
    raw = {
        "result": {
            "qus_results": [
                {
                    "qus_id": 1,
                    "location": {
                        "qus_location": [10, 10, 500, 400],
                        "ans_location": [
                            {"x": 100, "y": 50, "w": 95, "h": 20},
                            {"x": 280, "y": 90, "w": 80, "h": 30},
                        ],
                    },
                    "qus_elements": {"answer_words": ["first", "second"]},
                }
            ]
        }
    }

    questions = extract_vlm_questions(raw, image_path=str(image_path))

    assert len(questions) == 1
    assert questions[0].answer_bbox == [100, 50, 360, 120]
    assert questions[0].bbox == [358, 118, 360, 120]

    _insert_grading_result(
        questions[0],
        {
            "question_id": 1,
            "correctResult": 1,
            "reason": "correct",
            "analysis": "correct",
            "confidence": 1,
        },
    )
    blocks = _build_blocks(questions)
    assert blocks[0]["bbox"] == questions[0].answer_bbox
    names = draw_reference_vlm_marks_and_save(
        str(image_path),
        blocks,
        str(out_dir),
        "answer-anchor",
    )
    with Image.open(out_dir / names[1]).convert("RGB") as marked:
        red_pixels = [
            (x, y)
            for y in range(marked.height)
            for x in range(marked.width)
            if marked.getpixel((x, y))[0] > 170
            and marked.getpixel((x, y))[1] < 130
            and marked.getpixel((x, y))[2] < 130
        ]
    assert red_pixels
    assert min(x for x, _y in red_pixels) >= 350
    assert abs(sum(y for _x, y in red_pixels) / len(red_pixels) - 120) < 40


def test_split_only_rectangles_and_duplicate_ids_keep_reading_order():
    out_dir = Path(tempfile.mkdtemp(prefix="reference_vlm_split_only_"))
    image_path = out_dir / "paper.jpg"
    Image.new("RGB", (800, 600), "white").save(image_path)
    raw = {
        "result": {
            "qus_result": [
                {
                    "qus_id": 7,
                    "location": {
                        "qus_location": [{"coordinate": [100, 100, 400, 220], "score": 0.9}],
                        "ans_location": [{"coordinate": [130, 150, 160, 180], "score": 0.9}],
                    },
                },
                {
                    "qus_id": 7,
                    "location": {
                        "qus_location": [{"coordinate": [100, 300, 400, 420], "score": 0.9}],
                        "ans_location": [{"coordinate": [330, 360, 360, 390], "score": 0.9}],
                    },
                },
            ]
        }
    }
    questions = extract_vlm_questions(raw, image_path=str(image_path))

    assert [q.question_id for q in questions] == [7, 7]
    assert [q.display_index for q in questions] == [1, 2]
    assert questions[0].question_bbox == [100, 100, 400, 220]
    assert questions[1].answer_bbox == [330, 360, 360, 390]
    assert _match_questions(questions, questions) == [(questions[0], questions[0]), (questions[1], questions[1])]


def test_split_only_orphan_duplicate_without_handwriting_is_skipped():
    out_dir = Path(tempfile.mkdtemp(prefix="reference_vlm_orphan_"))
    image_path = out_dir / "paper.jpg"
    Image.new("RGB", (800, 600), "white").save(image_path)
    raw = {
        "result": {
            "qus_result": [
                {
                    "qus_id": 7,
                    "location": {
                        "qus_location": [{"coordinate": [100, 100, 400, 250]}],
                        "ans_location": [{"coordinate": [120, 140, 150, 170]}],
                    },
                },
                {
                    "qus_id": 7,
                    "location": {
                        "qus_location": [{"coordinate": [100, 250, 400, 300]}],
                        "ans_location": [],
                        "pic_location": [],
                    },
                },
            ]
        }
    }

    questions = extract_vlm_questions(raw, image_path=str(image_path))

    assert len(questions) == 1
    assert questions[0].question_id == 7


def test_submit_paper_cut_uses_single_sync_only_split_request(monkeypatch):
    out_dir = Path(tempfile.mkdtemp(prefix="reference_vlm_submit_"))
    image_path = out_dir / "paper.jpg"
    Image.new("RGB", (20, 20), "white").save(image_path)
    captured = {}
    response = {
        "result": {
            "qus_result": [
                {"qus_id": 1, "location": {"qus_location": [{"x": 1, "y": 1, "w": 5, "h": 5}]}}
            ]
        }
    }

    monkeypatch.setattr(reference_vlm_grading, "_build_url", lambda url: url)
    monkeypatch.setattr(
        reference_vlm_grading,
        "_post_json",
        lambda _url, payload, **_kwargs: captured.setdefault("payload", payload) and response,
    )

    returned = submit_paper_cut_vlm(str(image_path))

    assert returned == response
    assert captured["payload"]["only_split"] is True


def test_draw_reference_vlm_marks_and_save():
    # 注意：试卷切题与识别/ 下的 fixture 为合成数据（真实试卷数据从未入库），仅覆盖解析逻辑路径，非真实试卷截图/切题结果。
    root = _sample_root()
    raw = json.loads((root / "试卷切题与识别真实json数据.txt").read_text(encoding="utf-8"))
    questions = extract_vlm_questions(raw, image_path=str(root / "1.jpg"))
    for idx, q in enumerate(questions):
        _insert_grading_result(
            q,
            {
                "question_id": q.question_id,
                "correctResult": 1 if idx % 2 == 0 else 2,
                "reason": "smoke",
                "analysis": "smoke analysis",
                "confidence": 1,
            },
        )

    blocks = _build_blocks(questions)
    out_dir = Path(tempfile.mkdtemp(prefix="reference_vlm_test_"))
    names = draw_reference_vlm_marks_and_save(str(root / "1.jpg"), blocks, str(out_dir), "smoke")
    assert all((out_dir / name).is_file() for name in names)


def test_draw_reference_vlm_marks_falls_back_to_question_lower_right():
    out_dir = Path(tempfile.mkdtemp(prefix="reference_vlm_question_fallback_"))
    image_path = out_dir / "paper.jpg"
    Image.new("RGB", (700, 500), "white").save(image_path)
    block = {
        "is_question": True,
        "result": "wrong",
        "bbox": [20, 20, 80, 80],
        "has_handwriting_location": False,
        "baidu_question_bbox": [100, 100, 500, 350],
    }

    names = draw_reference_vlm_marks_and_save(
        str(image_path),
        [block],
        str(out_dir),
        "question-fallback",
    )

    assert block["bbox"] == [20, 20, 80, 80]
    assert "reference_vlm_anchor_source" not in block
    with Image.open(out_dir / names[1]).convert("RGB") as marked:
        red_pixels = [
            (x, y)
            for y in range(marked.height)
            for x in range(marked.width)
            if marked.getpixel((x, y))[0] > 170
            and marked.getpixel((x, y))[1] < 130
            and marked.getpixel((x, y))[2] < 130
        ]
    assert red_pixels
    assert min(x for x, _y in red_pixels) >= 450
    assert abs(sum(y for _x, y in red_pixels) / len(red_pixels) - 350) < 45


def test_multiple_answer_slots_have_independent_results_and_mark_anchors(monkeypatch):
    out_dir = Path(tempfile.mkdtemp(prefix="reference_vlm_multi_slot_"))
    image_path = out_dir / "paper.jpg"
    Image.new("RGB", (700, 500), "white").save(image_path)
    raw = {
        "result": {
            "qus_result": [
                {
                    "qus_id": 1,
                    "location": {
                        "qus_location": [{"coordinate": [20, 20, 650, 450]}],
                        "ans_location": [
                            {"coordinate": [120, 110, 210, 160]},
                            {"coordinate": [400, 260, 490, 310]},
                        ],
                    },
                }
            ]
        }
    }
    standard_raw = json.loads(json.dumps(raw))
    standard_questions = extract_vlm_questions(standard_raw, image_path=str(image_path))
    student_questions = extract_vlm_questions(raw, image_path=str(image_path))
    tasks = _build_grading_tasks(
        standard_questions,
        student_questions,
        (700, 500),
        (700, 500),
    )
    assert [(task.sub_index, task.has_mark_anchor) for task in tasks] == [(1, True), (2, True)]
    batches = _group_grading_tasks(tasks)
    assert len(batches) == 1
    batch_prompt = _build_batch_qwen_prompt(batches[0], "student_1.jpg")
    assert "1_1" in batch_prompt
    assert "1_2" in batch_prompt
    normalized_batch = _normalize_batch_decision(
        {
            "question_id": batches[0].batch_id,
            "slots": [
                {
                    "slot_key": "1_1",
                    "correctResult": 1,
                    "result": "对",
                    "reason": "slot 1",
                    "analysis": "analysis 1",
                    "confidence": 1.0,
                },
                {
                    "slot_key": "1_2",
                    "correctResult": 2,
                    "result": "错",
                    "reason": "slot 2",
                    "analysis": "analysis 2",
                    "confidence": 1.0,
                },
            ],
        },
        batches[0],
    )
    assert set(normalized_batch) == {1, 2}
    try:
        _normalize_batch_decision(
            {
                "question_id": batches[0].batch_id,
                "slots": [
                    {
                        "slot_key": "1_1",
                        "correctResult": 1,
                        "result": "对",
                        "reason": "slot 1",
                        "analysis": "analysis 1",
                        "confidence": 1.0,
                    }
                ],
            },
            batches[0],
        )
    except RuntimeError as exc:
        assert "缺少作答区" in str(exc)
    else:
        raise AssertionError("missing slot_key must fail closed")

    monkeypatch.setattr(reference_vlm_grading, "_get_qwen_client_and_model", lambda: (object(), "test-model"))
    seen_task_ids = []

    def fake_qwen_batch(_client, _model, batch, _std_url, _stu_url, _student_name, family_hint="", **_kwargs):
        seen_task_ids.append(batch.batch_id)
        return {
            task.task_id: {
                "question_id": task.task_id,
                "correctResult": 1 if task.sub_index == 1 else 2,
                "result": "对" if task.sub_index == 1 else "错",
                "reason": f"slot {task.sub_index}",
                "analysis": f"analysis {task.sub_index}",
                "confidence": 1.0,
            }
            for task in batch.slots
        }

    monkeypatch.setattr(reference_vlm_grading, "_call_qwen_for_question_batch", fake_qwen_batch)
    monkeypatch.setattr(reference_vlm_grading, "_save_reference_vlm_artifacts", lambda **_kwargs: None)
    standard_doc = {"raw": standard_raw, "image_path": str(image_path), "questions": standard_questions}
    student_doc = {"raw": raw, "image_path": str(image_path), "questions": student_questions}

    _result, blocks, enriched_raw, _mark_source = grade_reference_vlm_paper(
        "standard.jpg",
        standard_doc,
        "student_1.jpg",
        student_doc,
        folder_safe="reference-vlm-test",
    )

    sub_results = enriched_raw["result"]["qus_result"][0]["sub_grading_results"]
    assert seen_task_ids == [1]
    assert [item["correctResult"] for item in sub_results] == [1, 2]
    assert [item["answer_bbox"] for item in sub_results] == [[120, 110, 210, 160], [400, 260, 490, 310]]
    assert [block["sub_index"] for block in blocks] == [1, 2]
    assert all(block["has_handwriting_location"] for block in blocks)
    assert [block["bbox"][2:] for block in blocks] == [[210, 160], [490, 310]]


def test_remove_reference_vlm_paper_artifacts_keeps_other_papers(monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="reference_vlm_delete_paper_"))
    records_path = root / "records.json"
    analysis_path = root / "analysis.json"
    assets_dir = root / "assets"
    paper_dir = assets_dir / "student_a"
    raw_dir = assets_dir / "_reference_vlm_json"
    paper_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    (paper_dir / "q1_answer.jpg").write_bytes(b"asset")
    (raw_dir / "student_a.json").write_text("{}", encoding="utf-8")
    (raw_dir / "student_b.json").write_text("{}", encoding="utf-8")
    store = {
        "papers": {"student_a": {"summary": {}}, "student_b": {"summary": {}}},
        "summary": {},
    }
    records_path.write_text(json.dumps(store), encoding="utf-8")
    analysis_path.write_text(json.dumps(store), encoding="utf-8")
    monkeypatch.setattr(
        reference_vlm_grading,
        "_ct_layout",
        lambda _safe: {
            "class_id": "",
            "records_path": records_path,
            "analysis_path": analysis_path,
            "assets_dir": assets_dir,
        },
    )

    reference_vlm_grading.remove_reference_vlm_paper_artifacts("exam", "student_a_1.jpg")

    assert not paper_dir.exists()
    assert not (raw_dir / "student_a.json").exists()
    assert (raw_dir / "student_b.json").exists()
    assert set(json.loads(records_path.read_text(encoding="utf-8"))["papers"]) == {"student_b"}
    assert set(json.loads(analysis_path.read_text(encoding="utf-8"))["papers"]) == {"student_b"}


def test_delete_modify_url_strips_cache_query(monkeypatch):
    from app.grading import router as grading_router

    root = Path(tempfile.mkdtemp(prefix="reference_vlm_delete_mark_"))
    mark_path = root / "annotated_ref_exam_student_a.jpg"
    mark_path.write_bytes(b"mark")
    monkeypatch.setattr(grading_router, "modify_dir", lambda: root)

    grading_router._delete_modify_file_by_url(
        "/api/v1/grading/modify/annotated_ref_exam_student_a.jpg?t=123"
    )

    assert not mark_path.exists()


def test_finished_job_does_not_import_completed_items_from_old_history(monkeypatch):
    from app.grading import router as grading_router

    job_id = "reference-vlm-current-job"
    grading_router._ref_grade_results[job_id] = {
        "completed": [],
        "failed": [{"name": "标准答案", "msg": "百度 token 已过期"}],
        "in_progress": ["student.jpg"],
        "done": False,
        "total": 1,
        "engine": "aliyun",
    }
    monkeypatch.setattr(
        grading_router,
        "_read_grading_history",
        lambda *_args, **_kwargs: {
            "completed": {"student.jpg": {"name": "student.jpg", "result": "旧结果"}}
        },
    )

    try:
        grading_router._sync_ref_job_from_history(job_id, "exam")
        result = grading_router._ref_grade_results[job_id]
        assert result["completed"] == []
        assert result["failed"][0]["name"] == "标准答案"
    finally:
        grading_router._ref_grade_results.pop(job_id, None)


def test_delete_reference_vlm_folder_artifacts_removes_all_saved_data(monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="reference_vlm_delete_folder_"))
    records_path = root / "records.json"
    analysis_path = root / "analysis.json"
    assets_dir = root / "assets"
    assets_dir.mkdir(parents=True)
    records_path.write_text("{}", encoding="utf-8")
    analysis_path.write_text("{}", encoding="utf-8")
    (assets_dir / "orphan.jpg").write_bytes(b"asset")
    monkeypatch.setattr(
        reference_vlm_grading,
        "_ct_layout",
        lambda _safe: {
            "class_id": "class-1",
            "records_path": records_path,
            "analysis_path": analysis_path,
            "assets_dir": assets_dir,
        },
    )

    reference_vlm_grading.delete_reference_vlm_folder_artifacts("cls_class-1__exam")

    assert not records_path.exists()
    assert not analysis_path.exists()
    assert not assets_dir.exists()


def test_batch_slot_template_fills_baidu_locations_missing_from_one_paper():
    root = Path(tempfile.mkdtemp(prefix="reference_vlm_slot_template_"))
    image_path = root / "paper.jpg"
    Image.new("RGB", (1000, 800), "white").save(image_path)

    def make_raw(xs):
        return {
            "result": {
                "qus_result": [
                    {
                        "qus_id": 1,
                        "location": {
                            "qus_location": [{"coordinate": [20, 100, 950, 400]}],
                            "ans_location": [
                                {"coordinate": [x, 200, x + 45, 250]} for x in xs
                            ],
                        },
                    }
                ]
            }
        }

    standard_questions = extract_vlm_questions(
        make_raw([100, 500, 700]), image_path=str(image_path)
    )
    complete_questions = extract_vlm_questions(
        make_raw([100, 300, 500, 700]), image_path=str(image_path)
    )
    missing_questions = extract_vlm_questions(
        make_raw([100, 500, 700]), image_path=str(image_path)
    )
    documents = {
        "__standard__": {"questions": standard_questions, "image_size": (1000, 800)},
        "complete.jpg": {"questions": complete_questions, "image_size": (1000, 800)},
        "missing.jpg": {"questions": missing_questions, "image_size": (1000, 800)},
    }

    template = build_reference_vlm_slot_template(documents)
    tasks = _build_grading_tasks(
        standard_questions,
        missing_questions,
        (1000, 800),
        (1000, 800),
        slot_template=template,
    )

    assert len(template) == 4
    assert len(tasks) == 4
    assert [task.student_answer_bbox[0] for task in tasks] == [100, 300, 500, 700]
    assert [task.anchor_source for task in tasks].count("batch_template_projection") == 1
    assert all(task.has_mark_anchor for task in tasks)


def test_standard_answer_slot_projects_into_blank_student_question():
    root = Path(tempfile.mkdtemp(prefix="reference_vlm_blank_projection_"))
    image_path = root / "paper.jpg"
    Image.new("RGB", (1200, 800), "white").save(image_path)

    standard_raw = {
        "result": {
            "qus_result": [
                {
                    "qus_id": 1,
                    "location": {
                        "qus_location": [{"coordinate": [100, 100, 900, 400]}],
                        "ans_location": [{"coordinate": [600, 200, 700, 250]}],
                    },
                }
            ]
        }
    }
    student_raw = {
        "result": {
            "qus_result": [
                {
                    "qus_id": 1,
                    "location": {
                        "qus_location": [{"coordinate": [200, 150, 1000, 450]}],
                        "ans_location": [],
                    },
                }
            ]
        }
    }
    standard_questions = extract_vlm_questions(
        standard_raw, image_path=str(image_path)
    )
    student_questions = extract_vlm_questions(
        student_raw, image_path=str(image_path)
    )
    template = build_reference_vlm_slot_template(
        {
            "__standard__": {
                "questions": standard_questions,
                "image_size": (1200, 800),
            },
            "blank.jpg": {
                "questions": student_questions,
                "image_size": (1200, 800),
            },
        }
    )

    tasks = _build_grading_tasks(
        standard_questions,
        student_questions,
        (1200, 800),
        (1200, 800),
        slot_template=template,
    )

    assert len(tasks) == 1
    assert tasks[0].student_answer_bbox == [700, 250, 800, 300]
    assert tasks[0].anchor_source == "standard_answer_projection"
    assert tasks[0].has_mark_anchor is True
    assert tasks[0].has_handwriting_location is False
    assert tasks[0].is_answer_slot is True


def test_projected_template_prefers_matching_direct_handwriting_slot():
    root = Path(tempfile.mkdtemp(prefix="reference_vlm_direct_recovery_"))
    image_path = root / "paper.jpg"
    Image.new("RGB", (1200, 800), "white").save(image_path)

    def make_raw(question_bbox, answer_bboxes):
        return {
            "result": {
                "qus_result": [
                    {
                        "qus_id": 1,
                        "location": {
                            "qus_location": [{"coordinate": question_bbox}],
                            "ans_location": [
                                {"coordinate": bbox} for bbox in answer_bboxes
                            ],
                        },
                    }
                ]
            }
        }

    standard_questions = extract_vlm_questions(
        make_raw([100, 100, 900, 400], [[600, 200, 700, 250]]),
        image_path=str(image_path),
    )
    student_questions = extract_vlm_questions(
        make_raw([200, 150, 1000, 450], [[700, 250, 800, 300]]),
        image_path=str(image_path),
    )
    template = build_reference_vlm_slot_template(
        {
            "__standard__": {
                "questions": standard_questions,
                "image_size": (1200, 800),
            },
            "student.jpg": {
                "questions": student_questions,
                "image_size": (1200, 800),
            },
        }
    )

    tasks = _build_grading_tasks(
        standard_questions,
        student_questions,
        (1200, 800),
        (1200, 800),
        slot_template=template,
    )

    assert len(tasks) == 1
    assert tasks[0].student_answer_bbox == [700, 250, 800, 300]
    assert tasks[0].anchor_source == "baidu_direct"
    assert tasks[0].has_handwriting_location is True


def test_template_merges_nested_baidu_boxes_without_duplicate_tasks():
    root = Path(tempfile.mkdtemp(prefix="reference_vlm_nested_direct_"))
    image_path = root / "paper.jpg"
    Image.new("RGB", (1000, 800), "white").save(image_path)

    def make_raw(answer_bboxes):
        return {
            "result": {
                "qus_result": [
                    {
                        "qus_id": 1,
                        "location": {
                            "qus_location": [
                                {"coordinate": [50, 80, 950, 500]}
                            ],
                            "ans_location": [
                                {"coordinate": bbox} for bbox in answer_bboxes
                            ],
                        },
                    }
                ]
            }
        }

    standard_questions = extract_vlm_questions(
        make_raw([[200, 150, 800, 300]]), image_path=str(image_path)
    )
    student_questions = extract_vlm_questions(
        make_raw(
            [
                [520, 180, 570, 230],
                [650, 235, 710, 280],
                [70, 410, 120, 450],
            ]
        ),
        image_path=str(image_path),
    )
    template = build_reference_vlm_slot_template(
        {
            "__standard__": {
                "questions": standard_questions,
                "image_size": (1000, 800),
            }
        }
    )

    tasks = _build_grading_tasks(
        standard_questions,
        student_questions,
        (1000, 800),
        (1000, 800),
        slot_template=template,
    )

    assert len(tasks) == 1
    assert tasks[0].standard_answer_bbox == [200, 150, 800, 300]
    assert tasks[0].student_answer_bbox == [520, 180, 710, 280]
    assert tasks[0].anchor_source == "baidu_direct"
    assert tasks[0].has_handwriting_location is True
    assert tasks[0].template_slot_id == template[0].slot_id


def test_draft_box_near_projected_slot_never_enters_red_box():
    # 草稿大框擦着答题区一个角就并进红框 = 草稿泄漏。
    # 判定必须按「墨迹有多少比例落在答题区内」，不是「重叠/小框」。
    root = Path(tempfile.mkdtemp(prefix="reference_vlm_draft_merge_"))
    image_path = root / "paper.jpg"
    Image.new("RGB", (1000, 800), "white").save(image_path)

    def make_raw(answer_bboxes):
        return {
            "result": {
                "qus_result": [
                    {
                        "qus_id": 1,
                        "location": {
                            "qus_location": [{"coordinate": [50, 80, 950, 500]}],
                            "ans_location": [
                                {"coordinate": bbox} for bbox in answer_bboxes
                            ],
                        },
                    }
                ]
            }
        }

    standard_questions = extract_vlm_questions(
        make_raw([[400, 200, 500, 250]]), image_path=str(image_path)
    )
    student_questions = extract_vlm_questions(
        make_raw(
            [
                [410, 205, 480, 245],  # 真作答：整块在答题区里
                [420, 225, 850, 380],  # 草稿：大框只擦到投影框一个角
            ]
        ),
        image_path=str(image_path),
    )
    template = build_reference_vlm_slot_template(
        {
            "__standard__": {
                "questions": standard_questions,
                "image_size": (1000, 800),
            }
        }
    )

    tasks = _build_grading_tasks(
        standard_questions,
        student_questions,
        (1000, 800),
        (1000, 800),
        slot_template=template,
    )

    assert len(tasks) == 1
    assert tasks[0].student_answer_bbox == [410, 205, 480, 245]
    assert tasks[0].anchor_source == "baidu_direct"


def test_draft_box_alone_never_replaces_projected_slot():
    # 答题区里没写、旁边有草稿：红框保持投影位，草稿既不许顶替也不许
    # 多生出整题任务——批改范围永远锁死在标准答题区。
    root = Path(tempfile.mkdtemp(prefix="reference_vlm_draft_only_"))
    image_path = root / "paper.jpg"
    Image.new("RGB", (1000, 800), "white").save(image_path)

    standard_questions = extract_vlm_questions(
        {
            "result": {
                "qus_result": [
                    {
                        "qus_id": 1,
                        "location": {
                            "qus_location": [{"coordinate": [50, 80, 950, 500]}],
                            "ans_location": [{"coordinate": [400, 200, 500, 250]}],
                        },
                    }
                ]
            }
        },
        image_path=str(image_path),
    )
    student_questions = extract_vlm_questions(
        {
            "result": {
                "qus_result": [
                    {
                        "qus_id": 1,
                        "location": {
                            "qus_location": [{"coordinate": [50, 80, 950, 500]}],
                            "ans_location": [{"coordinate": [420, 225, 850, 380]}],
                        },
                    },
                    {
                        "qus_id": 2,
                        "location": {
                            "qus_location": [{"coordinate": [50, 550, 950, 750]}],
                            "ans_location": [{"coordinate": [80, 600, 400, 700]}],
                        },
                    },
                ]
            }
        },
        image_path=str(image_path),
    )
    template = build_reference_vlm_slot_template(
        {
            "__standard__": {
                "questions": standard_questions,
                "image_size": (1000, 800),
            }
        }
    )

    tasks = _build_grading_tasks(
        standard_questions,
        student_questions,
        (1000, 800),
        (1000, 800),
        slot_template=template,
    )

    assert len(tasks) == 1
    assert tasks[0].student_answer_bbox == [400, 200, 500, 250]
    assert tasks[0].anchor_source == "standard_answer_projection"
    assert all(task.is_answer_slot for task in tasks)


def test_giant_student_region_falls_back_to_normalized_slot_box():
    # 学生切题把题区撑大 4 倍时，相对投影会拉成巨框。
    # 形状/占比不可比 → 退回整页归一化落点，红框必须就是标准答题区的大小。
    root = Path(tempfile.mkdtemp(prefix="reference_vlm_giant_region_"))
    image_path = root / "paper.jpg"
    Image.new("RGB", (1200, 800), "white").save(image_path)

    standard_questions = extract_vlm_questions(
        {
            "result": {
                "qus_result": [
                    {
                        "qus_id": 1,
                        "location": {
                            "qus_location": [{"coordinate": [100, 100, 900, 300]}],
                            "ans_location": [{"coordinate": [400, 200, 500, 250]}],
                        },
                    }
                ]
            }
        },
        image_path=str(image_path),
    )
    student_questions = extract_vlm_questions(
        {
            "result": {
                "qus_result": [
                    {
                        "qus_id": 1,
                        "location": {
                            "qus_location": [{"coordinate": [50, 50, 950, 750]}],
                            "ans_location": [],
                        },
                    }
                ]
            }
        },
        image_path=str(image_path),
    )
    template = build_reference_vlm_slot_template(
        {
            "__standard__": {
                "questions": standard_questions,
                "image_size": (1200, 800),
            }
        }
    )

    tasks = _build_grading_tasks(
        standard_questions,
        student_questions,
        (1200, 800),
        (1200, 800),
        slot_template=template,
    )

    assert len(tasks) == 1
    assert tasks[0].student_answer_bbox == [400, 200, 500, 250]
    assert tasks[0].anchor_source == "standard_answer_projection"


def test_peer_slot_projects_when_standard_and_student_locations_are_empty():
    root = Path(tempfile.mkdtemp(prefix="reference_vlm_peer_projection_"))
    image_path = root / "paper.jpg"
    Image.new("RGB", (1200, 800), "white").save(image_path)

    def make_raw(question_bbox, answer_bboxes):
        return {
            "result": {
                "qus_result": [
                    {
                        "qus_id": 1,
                        "location": {
                            "qus_location": [{"coordinate": question_bbox}],
                            "ans_location": [
                                {"coordinate": bbox} for bbox in answer_bboxes
                            ],
                        },
                    }
                ]
            }
        }

    standard_questions = extract_vlm_questions(
        make_raw([100, 100, 900, 400], []), image_path=str(image_path)
    )
    peer_questions = extract_vlm_questions(
        make_raw([200, 150, 1000, 450], [[700, 250, 800, 300]]),
        image_path=str(image_path),
    )
    blank_questions = extract_vlm_questions(
        make_raw([300, 200, 1100, 500], []), image_path=str(image_path)
    )
    template = build_reference_vlm_slot_template(
        {
            "__standard__": {
                "questions": standard_questions,
                "image_size": (1200, 800),
            },
            "peer.jpg": {
                "questions": peer_questions,
                "image_size": (1200, 800),
            },
            "blank.jpg": {
                "questions": blank_questions,
                "image_size": (1200, 800),
            },
        }
    )

    tasks = _build_grading_tasks(
        standard_questions,
        blank_questions,
        (1200, 800),
        (1200, 800),
        slot_template=template,
    )

    assert len(tasks) == 1
    assert tasks[0].standard_answer_bbox == [600, 200, 700, 250]
    assert tasks[0].student_answer_bbox == [800, 300, 900, 350]
    assert tasks[0].anchor_source == "batch_template_projection"
    assert tasks[0].has_mark_anchor is True
    assert tasks[0].has_handwriting_location is False


def test_unanswered_projected_slot_draws_circle():
    """未作答画空心圆（2026-10-16 用户要求：没填答案不能什么都不标）。"""
    out_dir = Path(tempfile.mkdtemp(prefix="reference_vlm_blank_circle_"))
    image_path = out_dir / "paper.png"
    Image.new("RGB", (600, 400), "white").save(image_path)
    block = {
        "is_question": True,
        "result": "未作答",
        "baidu_correct_result": 3,
        "baidu_is_slot": True,
        "has_handwriting_location": False,
        "has_mark_anchor": True,
        "bbox": [300, 180, 420, 240],
        "reference_vlm_answer_bbox": [300, 180, 420, 240],
        "baidu_question_bbox": [100, 80, 500, 300],
    }

    names = draw_reference_vlm_marks_and_save(
        str(image_path), [block], str(out_dir), "blank-circle"
    )

    with Image.open(out_dir / names[1]).convert("RGB") as marked:
        red_pixels = [
            (x, y)
            for y in range(marked.height)
            for x in range(marked.width)
            if marked.getpixel((x, y))[0] > 170
            and marked.getpixel((x, y))[1] < 130
            and marked.getpixel((x, y))[2] < 130
        ]

    assert red_pixels, "未作答空要画出红圈"


def test_grade_reference_vlm_paper_writes_qwen_json_into_enriched_raw(monkeypatch):
    root = _sample_root()
    # 注意：试卷切题与识别/ 下的 fixture 为合成数据（真实试卷数据从未入库），仅覆盖解析逻辑路径，非真实试卷截图/切题结果。
    image_path = str(root / "1.jpg")
    source_raw = json.loads(
        (root / "试卷切题与识别真实json数据.txt").read_text(encoding="utf-8")
    )
    standard_raw = json.loads(json.dumps(source_raw, ensure_ascii=False))
    source_raw["result"]["qus_result"][0]["sub_grading_results"] = [
        {
            "question_id": 1,
            "sub_index": 1,
            "correctResult": 2,
            "result": "错",
            "reason": "旧批改结果",
            "analysis": "旧批改结果",
            "confidence": 1.0,
            "answer_bbox": [1, 1, 2, 2],
        }
    ]
    standard_doc = {
        "raw": standard_raw,
        "image_path": image_path,
        "questions": extract_vlm_questions(standard_raw, image_path=image_path),
    }
    student_doc = {
        "raw": source_raw,
        "image_path": image_path,
        "questions": extract_vlm_questions(source_raw, image_path=image_path),
    }

    monkeypatch.setattr(reference_vlm_grading, "_get_qwen_client_and_model", lambda: (object(), "test-model"))
    monkeypatch.setattr(
        reference_vlm_grading,
        "_call_qwen_for_question_batch",
        lambda _client, _model, batch, _std_url, _stu_url, _student_name, family_hint="", **_kwargs: {
            task.task_id: {
                "question_id": task.task_id,
                "correctResult": 1,
                "result": "对",
                "reason": "答案一致",
                "analysis": "作答正确",
                "confidence": 1.0,
            }
            for task in batch.slots
        },
    )
    monkeypatch.setattr(reference_vlm_grading, "_save_reference_vlm_artifacts", lambda **_kwargs: None)

    _result, blocks, enriched_raw, _mark_source = grade_reference_vlm_paper(
        "标准答案.jpg",
        standard_doc,
        "测试学生_1.jpg",
        student_doc,
        folder_safe="reference-vlm-test",
    )

    enriched_questions = extract_vlm_questions(enriched_raw, image_path=image_path)
    expected_block_count = sum(
        len(q.raw.get("sub_grading_results") or []) for q in enriched_questions
    )
    assert len(blocks) == expected_block_count > 0
    assert all(q.raw.get("correctResult") == 1 for q in enriched_questions)
    assert all(isinstance(q.raw.get("grading_result"), dict) for q in enriched_questions)
    assert all(q.raw.get("ai_analysis") == "作答正确" for q in enriched_questions)
    assert "旧批改结果" not in json.dumps(enriched_raw, ensure_ascii=False)


def test_standard_answer_filename_page_protocol():
    from app.grading import router as grading_router

    assert grading_router._standard_answer_page_no("标准答案.jpg") == 1
    assert grading_router._standard_answer_page_no("标准答案_1.pdf") == 1
    assert grading_router._standard_answer_page_no("标准答案_2.png") == 2
    assert grading_router._standard_answer_page_no("学生_2.jpg") is None
    assert grading_router._is_standard_answer_filename("标准答案_12.docx") is True


def test_list_folder_files_returns_all_standard_answer_pages(monkeypatch):
    import asyncio
    from app.grading import router as grading_router

    root = Path(tempfile.mkdtemp(prefix="reference_vlm_list_pages_"))
    exam_dir = root / "exam"
    exam_dir.mkdir()
    for filename in ("标准答案.jpg", "标准答案_2.jpg", "学生_1.jpg"):
        (exam_dir / filename).write_bytes(b"image")

    monkeypatch.setattr(grading_router, "correct_docs_dir", lambda: root)
    monkeypatch.setattr(
        grading_router,
        "_preview_url_for_file",
        lambda _safe, filename: f"/preview/{filename}",
    )

    result = asyncio.run(grading_router.api_list_files("exam"))

    assert [item["page_no"] for item in result["standard_answers"]] == [1, 2]
    assert [item["filename"] for item in result["standard_answers"]] == [
        "标准答案.jpg",
        "标准答案_2.jpg",
    ]
    assert result["standard_answer"]["page_no"] == 1
    assert [item["name"] for item in result["files"]] == ["学生_1.jpg"]


def test_reference_grading_pairs_standard_and_student_by_page(monkeypatch):
    from app.grading import router as grading_router

    root = Path(tempfile.mkdtemp(prefix="reference_vlm_multi_page_"))
    exam_dir = root / "exam"
    exam_dir.mkdir()
    for filename in ("标准答案.jpg", "标准答案_2.jpg", "学生_1.jpg", "学生_2.jpg"):
        Image.new("RGB", (80, 60), "white").save(exam_dir / filename)

    seen_pairs = {}
    template_standards = []

    def fake_recognize(items, **_kwargs):
        documents = {}
        for key, _display_name, source_path in items:
            documents[key] = {
                "marker": Path(source_path).stem,
                "image_path": source_path,
                "questions": [],
                "image_size": (80, 60),
                "raw": {"result": {}},
            }
        return documents, {}

    def fake_template(documents):
        marker = documents["__standard__"]["marker"]
        template_standards.append(marker)
        return [marker]

    def fake_grade(standard_name, standard_doc, student_name, student_doc, **kwargs):
        seen_pairs[student_name] = {
            "standard_name": standard_name,
            "standard_marker": standard_doc["marker"],
            "student_marker": student_doc["marker"],
            "template": kwargs.get("slot_template"),
        }
        return json.dumps({"ok": True}), [], {"result": {}}, student_doc["image_path"]

    monkeypatch.setattr(grading_router, "correct_docs_dir", lambda: root)
    monkeypatch.setattr(grading_router, "_get_grading_path", lambda _safe, path: path)
    # aliyun 引擎要求先有已确认的标准答案切题布局，mock 确认文档让其进入逐页配对流程
    monkeypatch.setattr(
        grading_router,
        "get_confirmed_reference_document",
        lambda _safe, page_no, source_path, image_path: {
            "marker": Path(source_path).stem,
            "image_path": str(image_path),
            "image_size": (80, 60),
            "raw": {"result": {}},
            "questions": [],
        },
    )
    monkeypatch.setattr(grading_router, "recognize_reference_vlm_batch", fake_recognize)
    monkeypatch.setattr(grading_router, "build_reference_vlm_slot_template", fake_template)
    monkeypatch.setattr(grading_router, "grade_reference_vlm_paper", fake_grade)
    monkeypatch.setattr(grading_router, "_persist_grading_success", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(grading_router, "_persist_grading_failure", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(grading_router, "get_grading_user_id", lambda: "test-user")
    monkeypatch.setattr(
        grading_router,
        "run_with_grading_user",
        lambda _user_id, fn, *args: fn(*args),
    )

    job_id = "multi-page-pairing"
    grading_router._ref_grade_results[job_id] = {
        "completed": [],
        "failed": [],
        "in_progress": [],
        "done": False,
        "total": 0,
        "engine": "aliyun",
    }
    try:
        grading_router._run_ref_grade_impl(job_id, "exam", "aliyun")
        result = grading_router._ref_grade_results[job_id]
    finally:
        grading_router._ref_grade_results.pop(job_id, None)

    assert result["failed"] == []
    assert {item["name"] for item in result["completed"]} == {"学生_1.jpg", "学生_2.jpg"}
    assert seen_pairs["学生_1.jpg"] == {
        "standard_name": "标准答案 P1",
        "standard_marker": "标准答案",
        "student_marker": "学生_1",
        "template": ["标准答案"],
    }
    assert seen_pairs["学生_2.jpg"] == {
        "standard_name": "标准答案 P2",
        "standard_marker": "标准答案_2",
        "student_marker": "学生_2",
        "template": ["标准答案_2"],
    }
    assert sorted(template_standards) == ["标准答案", "标准答案_2"]


def test_reference_grading_never_falls_back_when_standard_page_is_missing(monkeypatch):
    from app.grading import router as grading_router

    root = Path(tempfile.mkdtemp(prefix="reference_vlm_missing_page_"))
    exam_dir = root / "exam"
    exam_dir.mkdir()
    for filename in ("标准答案.jpg", "学生_2.jpg"):
        Image.new("RGB", (80, 60), "white").save(exam_dir / filename)

    grade_calls = []
    monkeypatch.setattr(grading_router, "correct_docs_dir", lambda: root)
    monkeypatch.setattr(grading_router, "_get_grading_path", lambda _safe, path: path)
    monkeypatch.setattr(
        grading_router,
        "recognize_reference_vlm_batch",
        lambda _items, **_kwargs: ({}, {}),
    )
    monkeypatch.setattr(
        grading_router,
        "grade_reference_vlm_paper",
        lambda *_args, **_kwargs: grade_calls.append(True),
    )
    monkeypatch.setattr(grading_router, "_persist_grading_success", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(grading_router, "_persist_grading_failure", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(grading_router.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(grading_router, "get_grading_user_id", lambda: "test-user")
    monkeypatch.setattr(
        grading_router,
        "run_with_grading_user",
        lambda _user_id, fn, *args: fn(*args),
    )

    job_id = "missing-standard-page"
    grading_router._ref_grade_results[job_id] = {
        "completed": [],
        "failed": [],
        "in_progress": [],
        "done": False,
        "total": 0,
        "engine": "aliyun",
    }
    try:
        grading_router._run_ref_grade_impl(job_id, "exam", "aliyun")
        result = grading_router._ref_grade_results[job_id]
    finally:
        grading_router._ref_grade_results.pop(job_id, None)

    assert grade_calls == []
    assert result["completed"] == []
    assert len(result["failed"]) == 1
    assert result["failed"][0]["name"] == "学生_2.jpg"
    # aliyun 引擎要求每页标准答案先完成切题审查；标准 P2 缺失时学生 P2 不会被批改，
    # 也不会回退使用 P1。grade_calls 为空即证明未发生回退批改。
    assert "标准答案 P2" in result["failed"][0]["msg"]
    assert "切题审查" in result["failed"][0]["msg"]


def test_reference_artifacts_merge_pages_and_delete_only_requested_page(monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="reference_vlm_page_store_"))
    records_path = root / "records.json"
    analysis_path = root / "analysis.json"
    assets_dir = root / "assets"
    image_path = root / "paper.jpg"
    Image.new("RGB", (80, 60), "white").save(image_path)

    monkeypatch.setattr(
        reference_vlm_grading,
        "_ct_layout",
        lambda _safe: {
            "class_id": "",
            "exam_name": "exam",
            "records_path": records_path,
            "analysis_path": analysis_path,
            "assets_dir": assets_dir,
        },
    )
    monkeypatch.setattr(reference_vlm_grading, "_grading_root", lambda: root)
    monkeypatch.setattr(reference_vlm_grading, "_load_class_context", lambda _class_id: ({}, []))

    for page_no in (1, 2):
        reference_vlm_grading._save_reference_vlm_artifacts(
            folder_safe="exam",
            paper_name=f"student_{page_no}.jpg",
            source_filename=f"student_{page_no}.jpg",
            source_image_path=str(image_path),
            enriched_raw={"result": {"page": page_no}},
            questions=[],
        )

    records = json.loads(records_path.read_text(encoding="utf-8"))
    paper = records["papers"]["student"]
    assert set(paper["pages"]) == {"1", "2"}
    assert paper["source_filenames"] == ["student_1.jpg", "student_2.jpg"]
    assert (assets_dir / "_reference_vlm_json" / "student_p1.json").is_file()
    assert (assets_dir / "_reference_vlm_json" / "student_p2.json").is_file()

    reference_vlm_grading.remove_reference_vlm_paper_artifacts(
        "exam", "student_2.jpg"
    )

    records_after = json.loads(records_path.read_text(encoding="utf-8"))
    paper_after = records_after["papers"]["student"]
    assert set(paper_after["pages"]) == {"1"}
    assert paper_after["source_filenames"] == ["student_1.jpg"]
    assert (assets_dir / "_reference_vlm_json" / "student_p1.json").is_file()
    assert not (assets_dir / "_reference_vlm_json" / "student_p2.json").exists()


# ---- C1 管道补齐：块级 confidence / 题干 / 槽级答案文本 ----


def _make_question(
    *,
    question_id=1,
    display_index=1,
    question_words="题干文本",
    answer_words=None,
    answer_bboxes=None,
    question_type="填空题",
    question_bbox=None,
    printed_no=None,
):
    boxes = answer_bboxes or []
    return VlmQuestion(
        question_id=question_id,
        display_index=display_index,
        raw={},
        bbox=list(question_bbox or [0, 0, 100, 100]),
        question_bbox=list(question_bbox or [0, 0, 100, 100]),
        answer_bbox=boxes[0] if boxes else None,
        answer_bboxes=boxes,
        question_words=question_words,
        answer_words=answer_words or [],
        choices=[],
        question_type=question_type,
        printed_no=printed_no,
    )


def test_answer_text_for_slot_single_box_joins_words():
    q = _make_question(answer_words=["x=1", "y=2"], answer_bboxes=[[10, 10, 50, 50]])
    assert _answer_text_for_slot(q, [10, 10, 50, 50]) == "x=1\ny=2"


def test_answer_text_for_slot_multi_box_picks_by_position():
    q = _make_question(
        answer_words=["3", "4"],
        answer_bboxes=[[10, 10, 50, 50], [60, 10, 100, 50]],
    )
    assert _answer_text_for_slot(q, [60, 10, 100, 50]) == "4"
    # 钳位/缩放后的 bbox 精确匹配失败时按中心点归属本槽
    assert _answer_text_for_slot(q, [61, 12, 99, 48]) == "4"
    assert _answer_text_for_slot(q, [10, 10, 50, 50]) == "3"


def test_answer_text_for_slot_multi_box_unaligned_returns_none():
    # 多作答区但文本数对不上：宁缺勿串，返回 None（缓存身份键防线）
    q = _make_question(
        answer_words=["3"],
        answer_bboxes=[[10, 10, 50, 50], [60, 10, 100, 50]],
    )
    assert _answer_text_for_slot(q, [10, 10, 50, 50]) is None
    assert _answer_text_for_slot(_make_question(answer_words=[]), None) is None


def test_build_blocks_carries_identity_fields_from_standard_threading():
    std = _make_question(
        question_id=7,
        question_words="计算1+1",
        answer_words=["2"],
        answer_bboxes=[[10, 10, 50, 50]],
    )
    stu = _make_question(
        question_id=3,
        question_words="计算 1+1（学生OCR）",
        answer_words=["3"],
        answer_bboxes=[[12, 12, 52, 52]],
    )
    _insert_sub_grading_result(
        stu,
        {
            "question_id": 1,
            "correctResult": 2,
            "result": "错",
            "reason": "r",
            "analysis": "a",
            "confidence": 0.42,
        },
        task_id=1,
        sub_index=1,
        answer_bbox=[12, 12, 52, 52],
        has_mark_anchor=True,
        has_handwriting_location=True,
        is_answer_slot=True,
        correct_answer=_answer_text_for_slot(std, [10, 10, 50, 50]),
        question_content=std.question_words,
    )
    blocks = _build_blocks([stu], standard_by_id={7: std})
    assert len(blocks) == 1
    block = blocks[0]
    assert block["confidence"] == 0.42
    # 题干/标准答案取标准卷侧（跨学生稳定），学生作答取本槽识别文本
    assert block["question_content"] == "计算1+1"
    assert block["correct_answer"] == "2"
    assert block["student_answer"] == "3"
    assert block["question_type"] == "填空题"


def test_build_blocks_multi_slot_keeps_answers_per_slot():
    std = _make_question(
        question_id=8,
        question_words="填空组",
        answer_words=["3", "4"],
        answer_bboxes=[[10, 10, 50, 50], [60, 10, 100, 50]],
    )
    stu = _make_question(
        question_id=9,
        question_words="填空组",
        answer_words=["3", "5"],
        answer_bboxes=[[10, 10, 50, 50], [60, 10, 100, 50]],
    )
    for sub_index, (std_box, stu_box, code) in enumerate(
        [
            ([10, 10, 50, 50], [10, 10, 50, 50], 1),
            ([60, 10, 100, 50], [60, 10, 100, 50], 2),
        ],
        start=1,
    ):
        _insert_sub_grading_result(
            stu,
            {
                "question_id": sub_index,
                "correctResult": code,
                "result": "对" if code == 1 else "错",
                "reason": "r",
                "analysis": "a",
                "confidence": 0.9,
            },
            task_id=sub_index,
            sub_index=sub_index,
            answer_bbox=stu_box,
            has_mark_anchor=True,
            has_handwriting_location=True,
            is_answer_slot=True,
            correct_answer=_answer_text_for_slot(std, std_box),
            question_content=std.question_words,
        )
    blocks = _build_blocks([stu])
    # 两槽答案各归各（⛔ 不得互串整题拼接文本）
    assert [b["correct_answer"] for b in blocks] == ["3", "4"]
    assert [b["student_answer"] for b in blocks] == ["3", "5"]


def test_build_blocks_non_slot_has_no_student_answer_identity():
    stu = _make_question(
        question_id=4,
        question_words="未配对题",
        answer_words=["7"],
        answer_bboxes=[[1, 1, 9, 9]],
    )
    std = _make_question(
        question_id=4,
        question_words="未配对题",
        answer_words=["7"],
        answer_bboxes=[[1, 1, 9, 9]],
    )
    stu.raw["correctResult"] = 2
    blocks = _build_blocks([stu], standard_by_id={4: std})
    assert len(blocks) == 1
    # 非槽级块（未配对作答区的默认判分）不产出 student_answer，防进缓存当真判分复用
    assert blocks[0]["student_answer"] is None
    assert blocks[0]["correct_answer"] == "7"
    assert blocks[0]["question_content"] == "未配对题"
    assert blocks[0]["confidence"] is None
    # 无 standard_by_id 时题干回退学生侧、标准答案留空
    blocks = _build_blocks([stu])
    assert blocks[0]["question_content"] == "未配对题"
    assert blocks[0]["correct_answer"] is None


# ---- C3 判分缓存：全命中 batch 零 VL / 部分命中 cache 值覆盖 VL 值 ----


def _enable_verdict_cache(monkeypatch):
    """VERDICT_CACHE=1 + sqlite SessionLocal（范本 tests/test_verdict_cache.py）。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.grading import verdict_cache as vc
    from app.models.verdict_cache import VerdictCache

    monkeypatch.setenv("VERDICT_CACHE", "1")
    engine = create_engine("sqlite:///:memory:")
    VerdictCache.__table__.create(bind=engine)
    monkeypatch.setattr(vc, "SessionLocal", sessionmaker(bind=engine))
    return engine


def _cache_questions_and_tasks():
    """一对标准/学生卷问题（2 作答槽）+ 2 个判分任务。

    槽身份（_slot_cache_identity / _build_blocks 双侧一致）：
    - task 101：question_type=填空题(学生) / 解方程(标准) / 2(标准槽答) / x=2(学生槽答)
    - task 102：同上，3 / x=3。
    """
    std = _make_question(
        question_id=1,
        display_index=1,
        question_words="解方程",
        answer_words=["2", "3"],
        answer_bboxes=[[10, 10, 40, 40], [50, 10, 80, 40]],
        question_type="填空题",
    )
    stu = _make_question(
        question_id=1,
        display_index=1,
        question_words="解方程",
        answer_words=["x=2", "x=3"],
        answer_bboxes=[[10, 10, 40, 40], [50, 10, 80, 40]],
        question_type="填空题",
    )

    def _task(task_id, sub_index, box):
        return VlmGradingTask(
            task_id=task_id,
            student_question=stu,
            standard_question=std,
            student_answer_bbox=list(box),
            standard_answer_bbox=list(box),
            student_context_bbox=[0, 0, 100, 100],
            standard_context_bbox=[0, 0, 100, 100],
            sub_index=sub_index,
            has_mark_anchor=True,
            has_handwriting_location=True,
            is_answer_slot=True,
            anchor_source="handwriting",
            template_slot_id=None,
        )

    tasks = [_task(101, 1, [10, 10, 40, 40]), _task(102, 2, [50, 10, 80, 40])]
    return std, stu, tasks


def _cache_identity_block(correct_answer, student_answer, result="对", comment="历史判定"):
    """与 _slot_cache_identity 完全同键的 store_blocks 块（学生侧题型 + 标准侧题干/答案）。"""
    return {
        "question_type": "填空题",
        "question_content": "解方程",
        "correct_answer": correct_answer,
        "student_answer": student_answer,
        "result": result,
        "comment": comment,
    }


def _patch_cache_pipeline(monkeypatch, std, stu, tasks, batches, vl_calls, crop_calls):
    def _fake_vl(_client, _model, batch, _std_url, _stu_url, _student_name, family_hint="", **_kwargs):
        vl_calls.append(batch.batch_id)
        # VL 把所有槽都判「错」——命中槽若最终是「对」，只能来自缓存覆盖
        return {
            task.task_id: {
                "question_id": task.task_id,
                "correctResult": 2,
                "result": "错",
                "reason": "vl判错",
                "analysis": "vl判错",
                "confidence": 0.9,
            }
            for task in batch.slots
        }

    def _fake_crop(_img, _regions, highlight_bboxes=None):
        crop_calls.append(1)
        return ("data:fake", b"")

    monkeypatch.setattr(reference_vlm_grading, "extract_vlm_questions", lambda raw, image_path="": [stu])
    monkeypatch.setattr(reference_vlm_grading, "_get_qwen_client_and_model", lambda: (object(), "test-model"))
    monkeypatch.setattr(reference_vlm_grading, "_call_qwen_for_question_batch", _fake_vl)
    monkeypatch.setattr(reference_vlm_grading, "_crop_regions_to_data_url", _fake_crop)
    monkeypatch.setattr(reference_vlm_grading, "_save_reference_vlm_artifacts", lambda **_k: None)
    monkeypatch.setattr(reference_vlm_grading, "_build_grading_tasks", lambda *a, **k: tasks)
    monkeypatch.setattr(reference_vlm_grading, "_group_grading_tasks", lambda _tasks: batches)


def test_grade_cache_full_hit_skips_all_vl_calls(monkeypatch, tmp_path):
    _enable_verdict_cache(monkeypatch)
    from app.grading.verdict_cache import store_blocks

    std, stu, tasks = _cache_questions_and_tasks()
    # 两槽都预置人工终态缓存 → 两个 batch 均全命中
    store_blocks(
        [
            _cache_identity_block("2", "x=2"),
            _cache_identity_block("3", "x=3"),
        ],
        "数学",
        "aliyun",
        "human",
    )

    std_img, stu_img = tmp_path / "std.png", tmp_path / "stu.png"
    for p in (std_img, stu_img):
        Image.new("RGB", (100, 100), "white").save(p)

    vl_calls, crop_calls = [], []
    batches = [
        VlmQuestionBatchTask(batch_id=1, student_question=stu, standard_question=std, slots=[tasks[0]]),
        VlmQuestionBatchTask(batch_id=2, student_question=stu, standard_question=std, slots=[tasks[1]]),
    ]
    _patch_cache_pipeline(monkeypatch, std, stu, tasks, batches, vl_calls, crop_calls)

    _result, blocks, _raw, _src = grade_reference_vlm_paper(
        "标准答案.jpg",
        {"raw": {}, "image_path": str(std_img), "questions": [std]},
        "学生_1.jpg",
        {"raw": {}, "image_path": str(stu_img)},
        folder_safe="cache-test",
        cache_subject="数学",
    )

    assert vl_calls == []  # 全命中 batch 零 VL 调用
    assert crop_calls == []  # 且零裁剪
    by_sub = {b["sub_index"]: b for b in blocks}
    assert by_sub[1]["result"] == "对" and by_sub[1]["comment"] == "历史判定"
    assert by_sub[2]["result"] == "对" and by_sub[2]["comment"] == "历史判定"


def test_grade_cache_partial_hit_overrides_vl_for_hit_slot(monkeypatch, tmp_path):
    _enable_verdict_cache(monkeypatch)
    from app.grading.verdict_cache import store_blocks

    std, stu, tasks = _cache_questions_and_tasks()
    # 只预置 101 槽（对/历史判定）；102 槽未命中 → 照调 VL
    store_blocks([_cache_identity_block("2", "x=2")], "数学", "aliyun", "human")

    std_img, stu_img = tmp_path / "std.png", tmp_path / "stu.png"
    for p in (std_img, stu_img):
        Image.new("RGB", (100, 100), "white").save(p)

    vl_calls, crop_calls = [], []
    batches = [
        VlmQuestionBatchTask(batch_id=1, student_question=stu, standard_question=std, slots=list(tasks)),
    ]
    _patch_cache_pipeline(monkeypatch, std, stu, tasks, batches, vl_calls, crop_calls)

    _result, blocks, _raw, _src = grade_reference_vlm_paper(
        "标准答案.jpg",
        {"raw": {}, "image_path": str(std_img), "questions": [std]},
        "学生_1.jpg",
        {"raw": {}, "image_path": str(stu_img)},
        folder_safe="cache-test",
        cache_subject="数学",
    )

    assert vl_calls == [1]  # 部分命中照调 VL（不拆批只问缺槽）
    assert len(crop_calls) == 2  # std + stu 各裁一次
    by_sub = {b["sub_index"]: b for b in blocks}
    # 命中槽：缓存覆盖 VL 的「错」（人工终态权威）
    assert by_sub[1]["result"] == "对" and by_sub[1]["comment"] == "历史判定"
    # 未命中槽：走 VL 判分
    assert by_sub[2]["result"] == "错" and by_sub[2]["comment"] == "vl判错"


# ---- 参照答案批改重构：标准答案完整识别 + 题号优先配对 + 待确认兜底 ----


def _slot_task(std, stu, *, task_id=1, sub_index=1, std_box=None, stu_box=None, standard_answer_text=None):
    return VlmGradingTask(
        task_id=task_id,
        student_question=stu,
        standard_question=std,
        student_answer_bbox=list(stu_box or [10, 10, 50, 50]),
        standard_answer_bbox=list(std_box or [10, 10, 50, 50]),
        student_context_bbox=[0, 0, 100, 100],
        standard_context_bbox=[0, 0, 100, 100],
        sub_index=sub_index,
        has_mark_anchor=True,
        has_handwriting_location=True,
        is_answer_slot=True,
        anchor_source="baidu_direct",
        template_slot_id=None,
        standard_answer_text=standard_answer_text,
    )


def test_parse_printed_no_extracts_question_numbers():
    assert _parse_printed_no("第9题 补写出下列名篇名句中的空缺部分") == "9"
    assert _parse_printed_no("10、阅读下面的文字，完成各题") == "10"
    assert _parse_printed_no("（1）明月几时有") == "1"
    assert _parse_printed_no("3. 解方程") == "3"
    assert _parse_printed_no("5题") == "5"
    # 语文卷中文数字题号
    assert _parse_printed_no("一、补写出下列名篇名句中的空缺部分") == "1"
    assert _parse_printed_no("（三）古代诗歌阅读") == "3"
    assert _parse_printed_no("第十二题 写作") == "12"
    assert _parse_printed_no("二十三、语言文字运用") == "23"
    # 年份/普通文本不得误判成题号
    assert _parse_printed_no("2024年春节，小明回到故乡") is None
    assert _parse_printed_no("补写出下列名篇名句中的空缺部分") is None
    assert _parse_printed_no("") is None


def test_match_template_prefers_printed_no_over_geometry():
    # 学生卷两题相邻位置与模板相反（切题位移 0.2 页高）：纯几何会互相配错，
    # 题号优先必须按印刷题号配对（同号对距离 0.2 < 防呆上限 0.35）。
    size = (400, 600)
    std_q1 = _make_question(
        display_index=1,
        printed_no="1",
        question_words="第1题 默写",
        answer_bboxes=[[10, 150, 200, 180]],
        question_bbox=[0, 0, 400, 220],
    )
    std_q2 = _make_question(
        display_index=2,
        printed_no="2",
        question_words="第2题 默写",
        answer_bboxes=[[10, 270, 200, 300]],
        question_bbox=[0, 230, 400, 330],
    )
    template = [
        VlmSlotTemplate(
            slot_id=1,
            normalized_bbox=(10 / 400, 150 / 600, 200 / 400, 180 / 600),
            relative_bbox=(0.025, 0.25, 0.5, 0.30),
            question_index=1,
            support_count=1,
            source_keys=("__standard__",),
        ),
        VlmSlotTemplate(
            slot_id=2,
            normalized_bbox=(10 / 400, 270 / 600, 200 / 400, 300 / 600),
            relative_bbox=(0.025, 0.45, 0.5, 0.50),
            question_index=2,
            support_count=1,
            source_keys=("__standard__",),
        ),
    ]
    # 学生卷：第1题在下、第2题在上（几何位置与模板槽互换）
    stu_q1 = _make_question(
        question_id=11,
        display_index=1,
        printed_no="1",
        question_words="第1题 默写",
        answer_bboxes=[[10, 270, 200, 300]],
        question_bbox=[0, 230, 400, 330],
    )
    stu_q2 = _make_question(
        question_id=12,
        display_index=2,
        printed_no="2",
        question_words="第2题 默写",
        answer_bboxes=[[10, 150, 200, 180]],
        question_bbox=[0, 0, 400, 220],
    )
    expected_no = {0: "1", 1: "2"}

    matches, _offset, _reliable = _match_template_to_paper(
        template, [stu_q1, stu_q2], size, expected_no
    )
    assert matches[0][0] is stu_q1  # 模板第1题 → 学生第1题（几何靠下也认）
    assert matches[1][0] is stu_q2
    assert matches[0][2] == [10, 270, 200, 300]

    # 对照：不带题号时几何会配错（模板槽1 → 学生上方框（第2题））
    wrong, _o, _r = _match_template_to_paper(template, [stu_q1, stu_q2], size)
    assert wrong[0][0] is stu_q2


def test_question_for_no_or_bbox_prefers_same_printed_no():
    size = (400, 600)
    q1 = _make_question(display_index=1, printed_no="1", question_bbox=[0, 0, 400, 220])
    q2 = _make_question(display_index=2, printed_no="2", question_bbox=[0, 320, 400, 560])
    # bbox 落在第2题区域，但题号是 1 → 仍选第1题
    assert _question_for_no_or_bbox([q1, q2], "1", [10, 450, 200, 480], size) is q1
    # 无题号 → 几何兜底
    assert _question_for_no_or_bbox([q1, q2], None, [10, 450, 200, 480], size) is q2


def test_normalize_decision_read_guard_forces_pending_and_is_idempotent():
    data = {
        "question_id": 3,
        "correctResult": 2,
        "result": "错",
        "transcription": "我[?]得",
        "read_confidence": 0.5,
        "reason": "字迹潦草判错",
        "analysis": "字迹潦草判错",
        "confidence": 0.9,
    }
    first = _normalize_decision(data, 3)
    assert first["correctResult"] == PENDING
    assert first["result"] == "待确认"
    assert first["read_uncertain"] is True
    assert "待人工确认" in first["reason"]
    assert "AI 读到" in first["reason"]
    # 两遍归一化（_insert_sub_grading_result 会再跑一次）必须幂等
    second = _normalize_decision(first, 3)
    assert second["correctResult"] == PENDING
    assert second["read_uncertain"] is True
    assert second["reason"] == first["reason"]
    assert second["result"] == "待确认"


def test_normalize_decision_clean_transcription_keeps_verdict():
    data = {
        "question_id": 4,
        "correctResult": 2,
        "result": "错",
        "transcription": "x=3",
        "read_confidence": 0.95,
        "reason": "答案应为 x=2",
        "analysis": "答案应为 x=2",
        "confidence": 0.9,
    }
    decision = _normalize_decision(data, 4)
    assert decision["correctResult"] == 2
    assert decision["read_uncertain"] is False
    assert "待人工确认" not in decision["reason"]


def test_normalize_decision_pending_on_flagged_standard_answer():
    # 标准答案本身识别不清 → 无法比对，强制待确认（不许蒙）
    data = {
        "question_id": 5,
        "correctResult": 1,
        "result": "对",
        "transcription": "答",
        "read_confidence": 0.95,
        "reason": "与标准答案一致",
        "analysis": "与标准答案一致",
        "confidence": 0.9,
    }
    decision = _normalize_decision(data, 5, standard_answer_text="参见[?]图")
    assert decision["correctResult"] == PENDING
    assert decision["read_uncertain"] is True
    assert "标准答案识别不清" in decision["reason"]


_TABLE = (
    "第1题：D\n"
    "第2题：B\n"
    "第4题：扼制 柳暗花明\n"
    "第8题：(1)海日生残夜 江春入旧年 (2)夕阳西下 断肠人在天涯\n"
)


def test_table_quote_mismatch_catches_wrong_row_and_corrupted_quote():
    # 查错行：自称第2题标准是 A（表里第2题是 B，A 是第3题的）
    assert _table_quote_mismatch("第2题：A", 2, _TABLE) is not None
    # 抄错字：把「扼制」记成「遏制」
    assert _table_quote_mismatch("第4题：遏制 柳暗花明", 4, _TABLE) is not None
    # 引文在表里根本找不到（幻觉标准）
    assert _table_quote_mismatch("第8题(4)：乡书何处达 归雁洛阳边", 8, _TABLE) is not None
    # 正确引文（含/不含标点与前后空白）都放行
    assert _table_quote_mismatch("第2题：B", 2, _TABLE) is None
    assert _table_quote_mismatch("第4题：扼制 柳暗花明", 4, _TABLE) is None
    assert _table_quote_mismatch("B", 2, _TABLE) is None
    # 无 located_no → 只要表里有出处就放行
    assert _table_quote_mismatch("扼制 柳暗花明", None, _TABLE) is None
    # 没有引文/没有表 → 无从校验
    assert _table_quote_mismatch("", 2, _TABLE) is None
    assert _table_quote_mismatch("第2题：B", 2, "") is None


def test_table_quote_mismatch_accepts_partial_slot_quotes():
    # 2026-10-16 七年级文件夹2：模型只抄一个空（"第1题：肢体"）对多空整行时
    # 被误判「引文不一致」→ PENDING → 该题不画批改痕迹（有的卷改有的卷不改）。
    table = (
        "第1题：肢体 无比 芝麻 师傅 神圣 侵犯 轰然\n"
        "第8题：(1)海日生残夜 江春入旧年 (2)夕阳西下 断肠人在天涯\n"
    )
    # 只抄一个空 / 带小问号的局部引文：放行
    assert _table_quote_mismatch("第1题：肢体", 1, table) is None
    assert _table_quote_mismatch("肢体", 1, table) is None
    assert _table_quote_mismatch("第8题：(1)海日生残夜", 8, table) is None
    assert _table_quote_mismatch("第8题(2)：夕阳西下 断肠人在天涯", 8, table) is None
    # 行头题号与本题不符：查错行照旧拦（旧口径 target in nq 会放行）
    assert _table_quote_mismatch("第2题：肢体", 1, table) is not None
    # 抄错字的局部引文照旧拦
    assert _table_quote_mismatch("第1题：肢休", 1, table) is not None


def test_normalize_decision_table_quote_mismatch_forces_pending():
    # 刘欣怡 4_1 复现：模型自称标准是「遏制」（表里是「扼制」），判学生错 → 应转待确认
    data = {
        "question_id": 7,
        "correctResult": 2,
        "result": "错",
        "transcription": "扼制 柳暗花明",
        "read_confidence": 0.95,
        "located_no": 4,
        "standard_quote": "第4题：遏制 柳暗花明",
        "reason": "学生写「扼制」与标准「遏制」不一致，故判错。",
        "analysis": "学生写「扼制」与标准「遏制」不一致，故判错。",
        "confidence": 0.9,
    }
    decision = _normalize_decision(data, 7, answer_table_text=_TABLE)
    assert decision["correctResult"] == PENDING
    assert decision["result"] == "待确认"
    assert "标准引文" in decision["reason"]
    assert "待人工确认" in decision["reason"]
    # 引文正确时维持原判
    data2 = dict(data, standard_quote="第4题：扼制 柳暗花明")
    decision2 = _normalize_decision(data2, 7, answer_table_text=_TABLE)
    assert decision2["correctResult"] == 2


def test_apply_conclusion_guard_conflicting_reason_forces_pending():
    # 王浩然 10_1 复现：理由以「故判错」收尾却返回对
    flipped = _apply_conclusion_guard(
        {"correctResult": 1, "result": "对", "reason": "与标准答案不一致，故判错。", "partial_ratio": None}
    )
    assert flipped["correctResult"] == PENDING
    assert flipped["result"] == "待确认"
    assert flipped["reason"].startswith("判语与结论矛盾，待人工确认")
    # 对的判错：理由「故判对」却返回错
    flipped2 = _apply_conclusion_guard(
        {"correctResult": 2, "result": "错", "reason": "与标准一致，故判对。"}
    )
    assert flipped2["correctResult"] == PENDING
    # 无矛盾不动
    ok = _apply_conclusion_guard({"correctResult": 1, "result": "对", "reason": "与标准一致，故判对。"})
    assert ok["correctResult"] == 1
    ok2 = _apply_conclusion_guard({"correctResult": 2, "result": "错", "reason": "与标准不一致，故判错。"})
    assert ok2["correctResult"] == 2
    # 理由里两个结论都出现（引用学生原文）→ 不误伤
    ok3 = _apply_conclusion_guard(
        {"correctResult": 2, "result": "错", "reason": "学生写「故判对」但与标准不一致，故判错。"}
    )
    assert ok3["correctResult"] == 2


def test_normalize_decision_conclusion_conflict_forces_pending():
    data = {
        "question_id": 8,
        "correctResult": 1,
        "result": "对",
        "transcription": "日月堂",
        "read_confidence": 0.9,
        "reason": "学生写「日月堂」与标准「日月之行」不一致，不符合标准答案，故判错。",
        "analysis": "不符合标准答案，故判错。",
        "confidence": 0.9,
    }
    decision = _normalize_decision(data, 8)
    assert decision["correctResult"] == PENDING
    assert decision["result"] == "待确认"
    # 陈志强 1_1 复现：结论句是「…判错。」不带「故」字，同样要拦
    data2 = {
        "question_id": 9,
        "correctResult": 1,
        "result": "对",
        "transcription": "A",
        "read_confidence": 0.95,
        "located_no": 2,
        "standard_quote": "第2题：2. B",
        "reason": "该槽位对应第2题。标准答案为B。学生作答为A，与标准答案不符，判错。",
        "analysis": "与标准答案不符，判错。",
        "confidence": 0.9,
    }
    decision2 = _normalize_decision(data2, 9, answer_table_text=_TABLE)
    # 字母 A≠B 却判对 → 字母矛盾闸也触发
    assert decision2["correctResult"] == PENDING
    assert "待人工确认" in decision2["reason"]


def test_objective_letter_conflict_guards_letter_verdicts():
    # 刘欣怡 1_1 复现：字母一致却判错
    assert _objective_letter_conflict("A", "第3题：3. A", 2) == "选项字母与标准一致却判错"
    # 字母不一致却判对
    assert _objective_letter_conflict("A.", "第2题：2. B", 1) == "选项字母与标准不一致却判对"
    # 大小写不敏感；全角括号/点号容忍（字母一致+判对=一致，不触发）
    assert _objective_letter_conflict("（b）", "5. B", 1) is None
    assert _objective_letter_conflict("B", "5. B", 1) is None
    # 主观题/多字答案不触发
    assert _objective_letter_conflict("扼制", "第4题：扼制 柳暗花明", 2) is None
    assert _objective_letter_conflict("江春入旧年", "第8题：…", 1) is None
    # 标准不是单字母（如多空默写）→ 不触发
    assert _objective_letter_conflict("A", "第8题：(1)海日生残夜 江春入旧年", 1) is None
    # 半对 + 字母不一致 → 同样矛盾
    assert _objective_letter_conflict("C", "第3题：3. A", 4) == "选项字母与标准不一致却判对"


def test_normalize_decision_letter_conflict_second_pass_ignores_machine_pairing():
    # 一遍判定 B/B 判对成立；二遍归一化（_insert_sub_grading_result）即使拿到错误的
    # 机器盲配文本 D 也不得翻案成待确认——字母闸只信随 decision 保留的 standard_quote
    data = {
        "question_id": 12,
        "correctResult": 1,
        "result": "对",
        "transcription": "B",
        "read_confidence": 0.95,
        "located_no": 2,
        "standard_quote": "第2题：2. B",
        "reason": "学生作答与标准一致，故判对。",
        "analysis": "学生作答与标准一致，故判对。",
        "confidence": 0.9,
    }
    first = _normalize_decision(data, 12, answer_table_text=_TABLE)
    assert first["correctResult"] == 1
    assert first["standard_quote"] == "第2题：2. B"
    second = _normalize_decision(first, 12, standard_answer_text="D")
    assert second["correctResult"] == 1
    assert second["reason"] == first["reason"]


def test_aggregate_any_pending_makes_question_pending():
    stu = _make_question(display_index=6, answer_bboxes=[[10, 10, 50, 50], [60, 10, 100, 50]])
    _insert_sub_grading_result(
        stu,
        {"question_id": 1, "correctResult": 1, "result": "对", "reason": "r", "analysis": "a", "confidence": 0.9},
        task_id=1,
        sub_index=1,
        answer_bbox=[10, 10, 50, 50],
        has_mark_anchor=True,
        has_handwriting_location=True,
        is_answer_slot=True,
    )
    _insert_sub_grading_result(
        stu,
        {"question_id": 2, "correctResult": 2, "result": "错", "transcription": "看[??]", "read_confidence": 0.3,
         "reason": "r", "analysis": "a", "confidence": 0.5},
        task_id=2,
        sub_index=2,
        answer_bbox=[60, 10, 100, 50],
        has_mark_anchor=True,
        has_handwriting_location=True,
        is_answer_slot=True,
    )
    # 任一作答区待确认 → 整题待确认
    assert stu.raw["correctResult"] == PENDING
    assert stu.raw["result"] == "待确认"
    text = _summarize_result_text([stu])
    assert "待确认：1" in text
    assert "第6题-作答区2：待确认" in text  # 逐槽行如实标出待确认


def test_draw_skips_pending_marks():
    captured = {}

    def _fake_real(image_path, mark_blocks, result_dir, file_stem, check_cross_scale=0.9):
        captured["real"] = list(mark_blocks)
        return "orig.jpg", "ann.jpg"

    def _fake_marks(image_path, mark_blocks, result_dir, file_stem, check_cross_scale=0.9):
        captured["marks"] = list(mark_blocks)
        return "marks_only.jpg"

    reference_vlm_grading.draw_real_marks_and_save = _fake_real
    reference_vlm_grading.draw_marks_only_and_save = _fake_marks
    try:
        blocks = [
            {"baidu_correct_result": PENDING, "has_mark_anchor": True, "bbox": [1, 1, 9, 9]},
            {"baidu_correct_result": 3, "has_mark_anchor": True, "bbox": [1, 11, 9, 19]},
            {"baidu_correct_result": 1, "has_mark_anchor": True, "bbox": [1, 21, 9, 29]},
        ]
        draw_reference_vlm_marks_and_save("paper.jpg", blocks, tempfile.mkdtemp(), "stem")
    finally:
        import importlib
        importlib.reload(reference_vlm_grading)
    # 只有待确认不画；未作答要画空心圆（2026-10-16：没填答案不能什么都不标）
    assert [b["bbox"] for b in captured["real"]] == [[1, 11, 9, 19], [1, 21, 9, 29]]
    assert captured["marks"] == captured["real"]


def test_cache_entry_pending_roundtrip():
    hit = {"result": "待确认", "comment": "识别不清，待人工确认（AI 读到：[?]…）", "partial_ratio": None}
    decision = _decision_from_cache_entry(hit, 9)
    assert decision["correctResult"] == PENDING
    assert decision["result"] == "待确认"
    assert decision["read_uncertain"] is True


def test_prompts_carry_standard_answer_text_and_transcription_discipline():
    std = _make_question(
        question_words="第1题 填空",
        answer_words=["x=2"],
        answer_bboxes=[[10, 10, 50, 50]],
    )
    stu = _make_question(
        question_id=2,
        question_words="第1题 填空",
        answer_words=["x=3"],
        answer_bboxes=[[10, 10, 50, 50]],
    )
    task = _slot_task(std, stu, standard_answer_text="x=2")
    prompt = _build_slot_qwen_prompt(task, "学生.jpg")
    assert "【标准答案（标准答案识别文本，唯一判分依据）】" in prompt
    assert "x=2" in prompt
    assert "STANDARD-ANSWER TEXT AUTHORITY" in prompt
    assert "image 1 is the sole ground truth" in prompt  # 〈文本缺失〉槽回退图1
    assert "TRANSCRIPTION FIRST" in prompt
    assert "[?]" in prompt and "[字1|字2]" in prompt
    assert '"transcription":"..."' in prompt
    # 缺标准答案文本 → 明示文本缺失 + 图1 兜底
    blank_std = _make_question(question_words="", answer_words=[], answer_bboxes=[])
    blank_stu = _make_question(question_id=2, question_words="", answer_words=[], answer_bboxes=[])
    blank_task = _slot_task(blank_std, blank_stu, standard_answer_text=None)
    blank_prompt = _build_slot_qwen_prompt(blank_task, "学生.jpg")
    assert "〈文本缺失〉" in blank_prompt
    assert "STANDARD-ANSWER AUTHORITY" in blank_prompt

    batch = VlmQuestionBatchTask(batch_id=7, student_question=stu, standard_question=std, slots=[task])
    batch_prompt = _build_batch_qwen_prompt(batch, "学生.jpg")
    assert "作答区 1_1：x=2" in batch_prompt
    assert "〈文本缺失〉的槽以 image 1 对应红框为准" in batch_prompt
    assert "or 4 for partially correct" in batch_prompt  # 批量提示词补齐半对
    assert '"transcription":"..."' in batch_prompt


def test_answer_table_slot_text_prefers_table_and_guards_cross_question():
    std = _make_question(
        display_index=2,
        printed_no="2",
        answer_words=["3", "4"],  # 切题 OCR 兜底值，不应覆盖答案表
        answer_bboxes=[[10, 10, 50, 50], [60, 10, 100, 50]],
    )
    table = {
        "questions": [
            {
                "display_index": 2,
                "printed_no": "2",
                "question_bbox": [0, 0, 100, 100],
                "slots": [
                    {"sub_index": 1, "bbox": [10, 10, 50, 50], "answer_text": "甲"},
                    {"sub_index": 2, "bbox": [60, 10, 100, 50], "answer_text": "乙"},
                ],
                "full_answer": "甲\n乙",
            }
        ]
    }
    assert _answer_table_slot_text(table, std, [10, 10, 50, 50]) == "甲"
    assert _answer_table_slot_text(table, std, [61, 12, 99, 48]) == "乙"
    other = _make_question(display_index=9, question_bbox=[300, 300, 380, 380])
    assert _answer_table_slot_text(table, other, [300, 300, 380, 380]) is None
    assert _answer_table_slot_text({}, std, [10, 10, 50, 50]) is None


def test_standard_answer_text_prefers_table_then_answer_words():
    std = _make_question(
        question_words="解方程",
        answer_words=["x=2"],
        answer_bboxes=[[10, 10, 50, 50]],
    )
    stu = _make_question(
        question_id=2,
        answer_words=["x=3"],
        answer_bboxes=[[10, 10, 50, 50]],
    )
    from app.grading.reference_vlm_grading import _standard_answer_text

    with_table = _slot_task(std, stu, standard_answer_text="标准表答案")
    assert _standard_answer_text(with_table) == "标准表答案"
    fallback = _slot_task(std, stu, standard_answer_text=None)
    assert _standard_answer_text(fallback) == "x=2"


def test_answer_table_cache_hits_until_layout_changes(monkeypatch, tmp_path):
    calls = []

    def _fake_extract(questions, image_path, *, skip_printed_numbers=None, stop_event=None):
        calls.append(image_path)
        return [
            {
                "display_index": 1,
                "printed_no": "1",
                "question_bbox": [0, 0, 100, 100],
                "slots": [{"sub_index": 1, "bbox": [10, 10, 50, 50], "answer_text": "答"}],
                "full_answer": "答",
            }
        ]

    monkeypatch.setattr(reference_vlm_grading, "extract_reference_answer_table", _fake_extract)
    monkeypatch.setattr(reference_vlm_grading, "correct_docs_dir", lambda: tmp_path)
    monkeypatch.setattr(reference_vlm_grading, "load_reference_layout", lambda folder: {"updated_at": "t1"})
    image_path = tmp_path / "std.png"
    Image.new("RGB", (50, 50), "white").save(image_path)
    doc = {
        "raw": {},
        "image_path": str(image_path),
        "questions": [_make_question(answer_bboxes=[[10, 10, 50, 50]], printed_no="1")],
    }
    first = load_or_build_reference_answer_table("ans-table-test", 1, doc)
    assert calls == [str(image_path)]
    assert first["questions"][0]["full_answer"] == "答"
    second = load_or_build_reference_answer_table("ans-table-test", 1, doc)
    assert calls == [str(image_path)]  # 缓存命中不再识别
    assert second["questions"][0]["full_answer"] == "答"
    # 切题审查变更 → 缓存失效重建
    monkeypatch.setattr(reference_vlm_grading, "load_reference_layout", lambda folder: {"updated_at": "t2"})
    load_or_build_reference_answer_table("ans-table-test", 1, doc)
    assert len(calls) == 2


def test_answer_table_manual_edits_survive_rebuild_and_drop_on_source_change(monkeypatch, tmp_path):
    # 老师手改的答案是覆盖层：切题变更重建时保留，换标准答案源文件才作废
    calls = []

    def _fake_extract(questions, image_path, *, skip_printed_numbers=None, stop_event=None):
        calls.append(image_path)
        return [
            {
                "display_index": 1,
                "printed_no": "1",
                "question_bbox": [0, 0, 100, 100],
                "slots": [{"sub_index": 1, "bbox": [10, 10, 50, 50], "answer_text": "答"}],
                "full_answer": "答",
            }
        ]

    monkeypatch.setattr(reference_vlm_grading, "extract_reference_answer_table", _fake_extract)
    monkeypatch.setattr(reference_vlm_grading, "correct_docs_dir", lambda: tmp_path)
    monkeypatch.setattr(reference_vlm_grading, "load_reference_layout", lambda folder: {"updated_at": "t1"})
    image_path = tmp_path / "std.png"
    Image.new("RGB", (50, 50), "white").save(image_path)
    doc = {
        "raw": {},
        "image_path": str(image_path),
        "source_path": str(image_path),
        "questions": [_make_question(answer_bboxes=[[10, 10, 50, 50]], printed_no="1")],
    }
    first = load_or_build_reference_answer_table("ans-edit-test", 1, doc)
    assert first["questions"][0]["full_answer"] == "答"

    saved = save_reference_answer_table_edits(
        "ans-edit-test",
        1,
        [{"display_index": 1, "printed_no": "3", "slots": [{"sub_index": 1, "answer_text": "正解"}]}],
    )
    assert saved["questions"][0]["full_answer"] == "正解"
    assert saved["questions"][0]["printed_no"] == "3"
    assert saved["questions"][0]["edited"] is True

    # 缓存命中：读到的是改过的答案
    second = load_or_build_reference_answer_table("ans-edit-test", 1, doc)
    assert len(calls) == 1
    assert second["questions"][0]["full_answer"] == "正解"
    assert second["questions"][0]["printed_no"] == "3"

    # 切题变更重建：自动识别结果照旧被手改覆盖层救回
    monkeypatch.setattr(reference_vlm_grading, "load_reference_layout", lambda folder: {"updated_at": "t2"})
    third = load_or_build_reference_answer_table("ans-edit-test", 1, doc)
    assert len(calls) == 2
    assert third["questions"][0]["full_answer"] == "正解"
    assert third["questions"][0]["printed_no"] == "3"
    assert third["questions"][0]["edited"] is True

    # 换源文件：手改作废，重新识别
    Image.new("RGB", (60, 60), "black").save(image_path)
    fourth = load_or_build_reference_answer_table("ans-edit-test", 1, doc)
    assert len(calls) == 3
    assert fourth["questions"][0]["full_answer"] == "答"
    assert fourth["questions"][0].get("edited") is None


def test_save_answer_table_edits_requires_table_and_keeps_multi_blank(monkeypatch, tmp_path):
    monkeypatch.setattr(reference_vlm_grading, "correct_docs_dir", lambda: tmp_path)
    try:
        save_reference_answer_table_edits("ans-edit-empty", 1, [{"display_index": 1, "slots": [{"sub_index": 1, "answer_text": "x"}]}])
    except RuntimeError as exc:
        assert "答案表尚未生成" in str(exc)
    else:
        raise AssertionError("无答案表时保存必须报错")

    monkeypatch.setattr(reference_vlm_grading, "load_reference_layout", lambda folder: {"updated_at": "t1"})

    def _fake_extract(questions, image_path, *, skip_printed_numbers=None, stop_event=None):
        return [
            {
                "display_index": 8,
                "printed_no": "8",
                "question_bbox": [0, 0, 100, 100],
                "slots": [
                    {"sub_index": 1, "bbox": [10, 10, 50, 50], "answer_text": "旧1"},
                    {"sub_index": 2, "bbox": [60, 10, 100, 50], "answer_text": "旧2"},
                ],
                "full_answer": "旧1\n旧2",
            }
        ]

    monkeypatch.setattr(reference_vlm_grading, "extract_reference_answer_table", _fake_extract)
    image_path = tmp_path / "std.png"
    Image.new("RGB", (50, 50), "white").save(image_path)
    doc = {
        "raw": {},
        "image_path": str(image_path),
        "source_path": str(image_path),
        "questions": [_make_question(answer_bboxes=[[10, 10, 50, 50], [60, 10, 100, 50]], printed_no="8")],
    }
    load_or_build_reference_answer_table("ans-edit-multi", 1, doc)
    saved = save_reference_answer_table_edits(
        "ans-edit-multi",
        1,
        [
            {
                "display_index": 8,
                "printed_no": "8",
                "slots": [
                    {"sub_index": 1, "answer_text": "海日生残夜"},
                    {"sub_index": 2, "answer_text": "江春入旧年"},
                ],
            }
        ],
    )
    entry = saved["questions"][0]
    assert entry["full_answer"] == "海日生残夜\n江春入旧年"
    assert [slot["answer_text"] for slot in entry["slots"]] == ["海日生残夜", "江春入旧年"]
    # 答案表摘要行跟手改一致（判分提示词/引文回验都吃这一行）
    assert _answer_table_summary_text(saved) == "第8题：海日生残夜\n江春入旧年"

    # 强制重识别 + reset_edits → 手动修改全部丢弃
    invalidate_reference_answer_table("ans-edit-multi", 1, reset_edits=True)
    rebuilt = load_or_build_reference_answer_table("ans-edit-multi", 1, doc)
    assert rebuilt["questions"][0]["full_answer"] == "旧1\n旧2"
    assert rebuilt["questions"][0].get("edited") is None


def test_grade_paper_uses_answer_table_for_identity_and_prompt(monkeypatch, tmp_path):
    # 答案表文本（非切题 OCR 文本）必须成为 correct_answer/缓存身份/提示词依据
    std = _make_question(
        question_words="第2题 默写",
        answer_words=["切题OCR答案"],
        answer_bboxes=[[10, 10, 50, 50]],
    )
    stu = _make_question(
        question_id=2,
        question_words="第2题 默写",
        answer_words=["学生作答"],
        answer_bboxes=[[10, 10, 50, 50]],
    )
    captured_prompts = []

    def _fake_vl(_client, _model, batch, _std_url, _stu_url, _student_name, family_hint="", answer_table_text=""):
        captured_prompts.append(
            reference_vlm_grading._build_batch_qwen_prompt(
                batch, _student_name, answer_table_text=answer_table_text
            )
        )
        return {
            task.task_id: {
                "question_id": task.task_id,
                "correctResult": 1,
                "result": "对",
                "transcription": "答案",
                "read_confidence": 0.95,
                "reason": "一致",
                "analysis": "一致",
                "confidence": 0.9,
            }
            for task in batch.slots
        }

    monkeypatch.setattr(reference_vlm_grading, "extract_vlm_questions", lambda raw, image_path="": [stu])
    monkeypatch.setattr(reference_vlm_grading, "_get_qwen_client_and_model", lambda: (object(), "test-model"))
    monkeypatch.setattr(reference_vlm_grading, "_call_qwen_for_question_batch", _fake_vl)
    monkeypatch.setattr(
        reference_vlm_grading,
        "_crop_regions_to_data_url",
        lambda *a, **k: ("data:fake", b""),
    )
    monkeypatch.setattr(reference_vlm_grading, "_save_reference_vlm_artifacts", lambda **_k: None)
    monkeypatch.setattr(reference_vlm_grading, "_build_grading_tasks", lambda *a, **k: [_slot_task(std, stu)])
    monkeypatch.setattr(reference_vlm_grading, "_group_grading_tasks", lambda tasks: [
        VlmQuestionBatchTask(batch_id=1, student_question=stu, standard_question=std, slots=list(tasks))
    ])

    std_img, stu_img = tmp_path / "std.png", tmp_path / "stu.png"
    for p in (std_img, stu_img):
        Image.new("RGB", (100, 100), "white").save(p)
    answer_table = {
        "questions": [
            {
                "display_index": 1,
                "printed_no": "2",
                "question_bbox": [0, 0, 100, 100],
                "slots": [{"sub_index": 1, "bbox": [10, 10, 50, 50], "answer_text": "标准表答案"}],
                "full_answer": "标准表答案",
            }
        ]
    }
    _result, blocks, _raw, _src = grade_reference_vlm_paper(
        "标准答案.jpg",
        {"raw": {}, "image_path": str(std_img), "questions": [std]},
        "学生_1.jpg",
        {"raw": {}, "image_path": str(stu_img)},
        folder_safe="answer-table-test",
        answer_table=answer_table,
    )
    assert "标准表答案" in captured_prompts[0]
    # 每槽不再给机器配对文本（folder8 实测：模型会照错配对判分），判分依据只在完整表
    assert "作答区 1_1：标准表答案" not in captured_prompts[0]
    assert "作答区 1_1：按该空所属印刷题号查【参考答案完整表】判分" in captured_prompts[0]
    assert '"standard_answer_text_is_ground_truth": false' in captured_prompts[0]
    assert '"code_pairing_hint_unreliable": true' in captured_prompts[0]
    # 完整答案表整体进提示词（先认题号再对照本表）
    assert "【参考答案完整表" in captured_prompts[0]
    assert "第2题：标准表答案" in captured_prompts[0]
    assert "先认图像2红框旁的印刷题号" in captured_prompts[0]
    assert blocks[0]["correct_answer"] == "标准表答案"
    assert blocks[0]["result"] == "对"
    assert blocks[0]["read_uncertain"] is False


def test_apply_reference_layout_synthesizes_layout_only_questions(tmp_path):
    # 切题审查新增题（raw 里没有）不能丢：folder8 的第8-14题就是这样消失的
    image_path = tmp_path / "std.png"
    Image.new("RGB", (100, 100), "white").save(image_path)
    raw = {
        "qus_results": [
            {
                "qus_id": 1,
                "location": {
                    "qus_location": [10, 10, 90, 40],
                    "ans_location": [[10, 50, 90, 80]],
                },
                "qus_elements": {"question_words": "第1题 填空", "answer_words": ["a"]},
            }
        ]
    }
    document = {"raw": raw, "image_path": str(image_path), "image_size": [100, 100]}
    layout_page = {
        "image_size": [100, 100],
        "questions": [
            {
                "display_no": 1,
                "question_text": "第1题 填空",
                "regions": [{"bbox": [10, 10, 90, 40]}],
                "answer_slots": [{"regions": [{"bbox": [10, 50, 90, 80]}]}],
            },
            {
                "display_no": 2,
                "question_text": "第2题 简答",
                "regions": [{"bbox": [5, 82, 95, 88]}],
                "answer_slots": [{"regions": [{"bbox": [5, 88, 95, 94]}]}],
            },
            {
                "display_no": 3,
                "question_text": "",
                "regions": [{"bbox": [5, 94, 60, 100]}],
                "answer_slots": [],
            },
        ],
    }
    corrected = apply_reference_layout_to_document(document, layout_page)
    questions = corrected["questions"]
    assert [q.display_index for q in questions] == [1, 2, 3]
    synthesized = {q.display_index: q for q in questions}
    q2 = synthesized[2]
    assert q2.question_bbox == [5, 82, 95, 88]
    assert q2.answer_bboxes == [[5, 88, 95, 94]]
    assert q2.question_words == "第2题 简答"
    assert q2.printed_no == "2"
    q3 = synthesized[3]
    assert q3.question_bbox == [5, 94, 60, 100]
    assert q3.answer_bboxes == []  # 无作答区 → 答案表提取时回退题目框
    assert q3.printed_no is None
    # raw 容器同步补上合成题，corrected_raw 自洽
    assert len(reference_vlm_grading._questions_container(corrected["raw"])) == 3
    # 幂等：拿已补全的 raw 再 apply 一遍不应重复合成
    again = apply_reference_layout_to_document(corrected, layout_page)
    assert [q.display_index for q in again["questions"]] == [1, 2, 3]
    assert len(reference_vlm_grading._questions_container(again["raw"])) == 3


def test_apply_reference_layout_deletes_questions_missing_from_layout(tmp_path):
    # 用户 2026-10-16 投诉「答题区框里删除的答题区保存后还在」：P2 删掉的两道题
    # （raw pos=4/5）在 corrected_raw 原样存活、答案表里回魂。layout 里没有的题
    # 必须打 layout_deleted 并从 questions 剔除。
    image_path = tmp_path / "std.png"
    Image.new("RGB", (100, 100), "white").save(image_path)
    raw = {
        "qus_results": [
            {
                "qus_id": i,
                "location": {
                    "qus_location": [5, 10 * i, 95, 10 * i + 8],
                    "ans_location": [[5, 10 * i + 8, 95, 10 * i + 15]],
                },
                "qus_elements": {"question_words": f"第{i}题 填空"},
            }
            for i in range(1, 6)
        ]
    }
    document = {"raw": raw, "image_path": str(image_path), "image_size": [100, 100]}
    # 老师删掉了 display_no 4、5 两题（P2 真数据同款）
    layout_page = {
        "image_size": [100, 100],
        "questions": [
            {
                "question_id": f"q-{i}",
                "baidu_question_id": i,
                "display_no": i,
                "regions": [{"bbox": [5, 10 * i, 95, 10 * i + 8]}],
                "answer_slots": [{"slot_id": f"q-{i}-s1", "regions": [{"bbox": [5, 10 * i + 8, 95, 10 * i + 15]}]}],
            }
            for i in (1, 2, 3)
        ],
    }
    corrected = apply_reference_layout_to_document(document, layout_page)
    assert [q.display_index for q in corrected["questions"]] == [1, 2, 3]
    container = reference_vlm_grading._questions_container(corrected["raw"])
    assert [bool(item.get("layout_deleted")) for item in container] == [False, False, False, True, True]
    # 重建提取（答案表/批改入口）也必须跳过被删题
    reextracted = extract_vlm_questions(corrected["raw"], image_path=str(image_path))
    assert [q.display_index for q in reextracted] == [1, 2, 3]
    # 幂等：corrected 再 apply 不长回来、也不误删别的题
    again = apply_reference_layout_to_document(corrected, layout_page)
    assert [q.display_index for q in again["questions"]] == [1, 2, 3]
    assert len(reference_vlm_grading._questions_container(again["raw"])) == 5


def test_apply_reference_layout_mid_list_delete_keeps_numbering(tmp_path):
    # 中段删除后 display_no 不能挪号：否则重建时老师的修改会套到别的题上
    image_path = tmp_path / "std.png"
    Image.new("RGB", (100, 100), "white").save(image_path)
    raw = {
        "qus_results": [
            {
                "qus_id": i,
                "location": {
                    "qus_location": [5, 10 * i, 95, 10 * i + 8],
                    "ans_location": [[5, 10 * i + 8, 95, 10 * i + 15]],
                },
                "qus_elements": {"question_words": f"第{i}题 填空"},
            }
            for i in (1, 2, 3)
        ]
    }
    document = {"raw": raw, "image_path": str(image_path), "image_size": [100, 100]}
    # 删掉第 2 题；第 3 题的作答区被老师改过（10×38→10×45）
    layout_page = {
        "image_size": [100, 100],
        "questions": [
            {
                "question_id": "q-1",
                "display_no": 1,
                "regions": [{"bbox": [5, 10, 95, 18]}],
                "answer_slots": [{"regions": [{"bbox": [5, 18, 95, 25]}]}],
            },
            {
                "question_id": "q-3",
                "display_no": 3,
                "regions": [{"bbox": [5, 30, 95, 38]}],
                "answer_slots": [{"regions": [{"bbox": [5, 38, 95, 45]}]}],
            },
        ],
    }
    corrected = apply_reference_layout_to_document(document, layout_page)
    assert [q.display_index for q in corrected["questions"]] == [1, 3]
    by_index = {q.display_index: q for q in corrected["questions"]}
    assert by_index[3].answer_bboxes == [[5, 38, 95, 45]], "第3题的修改应仍挂在第3题"
    assert by_index[1].answer_bboxes == [[5, 18, 95, 25]]
    # 带戳重建：display_no 稳定，修改不挪位
    reextracted = extract_vlm_questions(corrected["raw"], image_path=str(image_path))
    assert [q.display_index for q in reextracted] == [1, 3]
    again = apply_reference_layout_to_document(corrected, layout_page)
    by_index2 = {q.display_index: q for q in again["questions"]}
    assert by_index2[3].answer_bboxes == [[5, 38, 95, 45]]
    assert by_index2[1].answer_bboxes == [[5, 18, 95, 25]]


def test_apply_reference_layout_add_only_edit_does_not_steal_deleted_raw(tmp_path):
    # 删尾题后新增会复用空出来的 display_no（前端 max+1）：那是新题，
    # 不许认领被删 raw 题的身份（question-<uuid> 只走合成）
    image_path = tmp_path / "std.png"
    Image.new("RGB", (100, 100), "white").save(image_path)
    raw = {
        "qus_results": [
            {
                "qus_id": 1,
                "location": {
                    "qus_location": [5, 10, 95, 18],
                    "ans_location": [[5, 18, 95, 25]],
                },
                "qus_elements": {"question_words": "第1题 填空"},
            },
            {
                "qus_id": 2,
                "location": {
                    "qus_location": [5, 30, 95, 38],
                    "ans_location": [[5, 38, 95, 45]],
                },
                "qus_elements": {"question_words": "第2题 填空"},
            },
        ]
    }
    document = {"raw": raw, "image_path": str(image_path), "image_size": [100, 100]}
    layout_page = {
        "image_size": [100, 100],
        "questions": [
            {
                "question_id": "q-1",
                "baidu_question_id": 1,
                "display_no": 1,
                "regions": [{"bbox": [5, 10, 95, 18]}],
                "answer_slots": [{"regions": [{"bbox": [5, 18, 95, 25]}]}],
            },
            {
                "question_id": "question-3f2c…",
                "display_no": 2,  # 新增题复用了被删第2题的号
                "regions": [{"bbox": [5, 50, 95, 58]}],
                "answer_slots": [{"regions": [{"bbox": [5, 58, 95, 65]}]}],
            },
        ],
    }
    corrected = apply_reference_layout_to_document(document, layout_page)
    assert [q.display_index for q in corrected["questions"]] == [1, 2]
    by_index = {q.display_index: q for q in corrected["questions"]}
    assert by_index[2].question_bbox == [5, 50, 95, 58], "新增题应按编辑框合成"
    assert by_index[2].answer_bboxes == [[5, 58, 95, 65]]
    assert by_index[2].raw.get("synthetic_from_layout") is True
    container = reference_vlm_grading._questions_container(corrected["raw"])
    assert bool(container[1].get("layout_deleted")) is True, "被删的原第2题不能复活"


def test_question_slot_bboxes_cleared_slots_do_not_fall_back_to_frame():
    # 老师把某题作答区删光：不得拿题框当答题区回魂；从没识别出作答区的题保留兜底
    cleared = _make_question(answer_bboxes=[[10, 10, 90, 40]])
    cleared.answer_bboxes = []
    cleared.answer_bbox = None
    cleared.raw["layout_slots_cleared"] = True
    assert reference_vlm_grading._question_slot_bboxes(cleared) == []
    never_had = _make_question(answer_bboxes=[], question_bbox=[5, 5, 95, 95])
    assert reference_vlm_grading._question_slot_bboxes(never_had) == [[5, 5, 95, 95]]


def test_layout_deleted_printed_nos_extracted():
    # 切题审查删掉的题号不算「漏切」：补漏扫描不得把它们补回来
    assert reference_vlm_grading._layout_deleted_printed_nos(
        {
            "qus_results": [
                {
                    "qus_id": 3,
                    "layout_deleted": True,
                    "qus_elements": {"question_words": "第3题 阅读"},
                },
                {
                    "qus_id": 4,
                    "qus_elements": {"question_words": "第4题 作文"},
                },
            ]
        }
    ) == {3}


def test_answer_table_summary_text_labels_by_printed_no():
    table = {
        "questions": [
            {"display_index": 3, "printed_no": "14", "full_answer": "   "},
            {"display_index": 1, "printed_no": "8", "full_answer": "8.(1)海日生残夜"},
            {"display_index": 2, "printed_no": None, "full_answer": "9.杨花和子规鸟"},
        ]
    }
    text = _answer_table_summary_text(table)
    assert "第8题：8.(1)海日生残夜" in text
    assert "第2题：9.杨花和子规鸟" in text  # 题号缺失回退 display_index
    assert "第14题" not in text  # 空答案条目跳过
    # 按印刷题号升序输出（认不出题号的排后面）
    assert text.splitlines()[0].startswith("第8题")
    assert text.splitlines()[1].startswith("第2题")
    assert _answer_table_summary_text({}) == ""
    assert _answer_table_summary_text(None) == ""


def test_extract_answer_table_backfills_printed_no_from_text(monkeypatch, tmp_path):
    image_path = tmp_path / "key.png"
    Image.new("RGB", (100, 100), "white").save(image_path)
    question = _make_question(
        display_index=3,
        question_words="",  # 切题没题干 → printed_no None
        answer_bboxes=[[5, 10, 95, 40]],
    )
    monkeypatch.setattr(reference_vlm_grading, "_get_qwen_client_and_model", lambda: (object(), "m"))
    monkeypatch.setattr(
        reference_vlm_grading,
        "_extract_slot_answer_text",
        lambda _c, _m, _img, _bbox: "8.（1）海日生残夜",
    )
    from app.grading.reference_vlm_grading import extract_reference_answer_table

    entries = extract_reference_answer_table([question], str(image_path))
    assert entries[0]["printed_no"] == "8"  # 从转写首行认号
    assert entries[0]["full_answer"] == "8.（1）海日生残夜"


def test_split_answer_entries_by_printed_numbers_splits_merged_block():
    # 用户真实数据：切题把 1-7 题答案并成一块 → 必须按行内题号一题一行
    entry = {
        "display_index": 1,
        "printed_no": "1",
        "question_bbox": [269, 210, 1359, 375],
        "slots": [
            {
                "sub_index": 1,
                "bbox": [269, 210, 1359, 375],
                "answer_text": "1. D 2. B 3. A 4. 扼制 柳暗花明\n5. B 6. B 7. D",
            }
        ],
        "full_answer": "1. D 2. B 3. A 4. 扼制 柳暗花明\n5. B 6. B 7. D",
    }
    children = reference_vlm_grading._split_answer_entries_by_printed_numbers([entry])
    assert [child["printed_no"] for child in children] == ["1", "2", "3", "4", "5", "6", "7"]
    assert [child["full_answer"] for child in children] == [
        "D",
        "B",
        "A",
        "扼制 柳暗花明",
        "B",
        "B",
        "D",
    ]
    assert [child["display_index"] for child in children] == [1001, 1002, 1003, 1004, 1005, 1006, 1007]
    assert all(child["source_display_index"] == 1 for child in children)


def test_split_answer_entries_keeps_subquestions_and_rejects_bad_markers():
    split = reference_vlm_grading._split_answer_entries_by_printed_numbers
    # Q8 四小问："（1）（2）…" 带括号不触发拆条
    entry8 = {
        "display_index": 2,
        "printed_no": "8",
        "question_bbox": [281, 362, 2062, 585],
        "slots": [
            {
                "sub_index": 1,
                "bbox": [281, 362, 2062, 585],
                "answer_text": "8.(1)海日生残夜 江春入旧年 (2)我寄愁心与明月 随君直到夜郎西",
            }
        ],
        "full_answer": "8.(1)海日生残夜 江春入旧年 (2)我寄愁心与明月 随君直到夜郎西",
    }
    assert split([entry8]) == [entry8]
    # 编号乱序（引用/枚举回退）不拆
    scrambled = {
        "display_index": 3,
        "printed_no": "1",
        "question_bbox": [0, 0, 100, 100],
        "slots": [{"sub_index": 1, "bbox": [0, 0, 100, 100], "answer_text": "1. D 2. B 1. C"}],
        "full_answer": "1. D 2. B 1. C",
    }
    assert split([scrambled]) == [scrambled]
    # 首号对不上条目题号不拆
    mismatch = {
        "display_index": 4,
        "printed_no": "9",
        "question_bbox": [0, 0, 100, 100],
        "slots": [{"sub_index": 1, "bbox": [0, 0, 100, 100], "answer_text": "1. D 2. B"}],
        "full_answer": "1. D 2. B",
    }
    assert split([mismatch]) == [mismatch]
    # 拆出的题号撞车 → 整条不拆（不丢答案、不造重复键）
    taken = {
        "display_index": 5,
        "printed_no": "1",
        "question_bbox": [0, 0, 50, 50],
        "slots": [{"sub_index": 1, "bbox": [0, 0, 50, 50], "answer_text": "甲"}],
        "full_answer": "甲",
    }
    merged = {
        "display_index": 6,
        "printed_no": "1",
        "question_bbox": [0, 50, 50, 100],
        "slots": [{"sub_index": 1, "bbox": [0, 50, 50, 100], "answer_text": "1. D 2. B"}],
        "full_answer": "1. D 2. B",
    }
    out = split([taken, merged])
    assert [item["display_index"] for item in out] == [5, 6]


def test_fill_missing_answer_numbers_reads_gap_band(monkeypatch):
    # 12 与 14 之间漏切的第 13 题：只裁两题之间的条带补缺号
    entries = [
        {
            "display_index": 6,
            "printed_no": "12",
            "question_bbox": [282, 781, 1349, 867],
            "slots": [{"sub_index": 1, "bbox": [282, 781, 1349, 867], "answer_text": "12. 描绘秀美。"}],
            "full_answer": "12. 描绘秀美。",
        },
        {
            "display_index": 7,
            "printed_no": "14",
            "question_bbox": [285, 909, 2065, 1070],
            "slots": [{"sub_index": 1, "bbox": [285, 909, 2065, 1070], "answer_text": "14. 不矛盾。"}],
            "full_answer": "14. 不矛盾。",
        },
    ]
    captured = []
    monkeypatch.setattr(
        reference_vlm_grading,
        "_extract_scan_answer_chunks",
        lambda _c, _m, _img, bbox: captured.append(list(bbox)) or {13: "空间"},
    )
    image = Image.new("RGB", (2078, 1070), "white")
    filled = reference_vlm_grading._fill_missing_answer_numbers(entries, image, object(), "m")
    assert [item["printed_no"] for item in filled] == ["12", "14", "13"]
    assert filled[-1]["display_index"] == 1013
    assert filled[-1]["full_answer"] == "空间"
    # 条带夹在 12 题答完（867）与 14 题开始（909）之间
    assert captured and captured[0][1] <= 867 and captured[0][3] >= 909
    # 题号已连齐 → 一次扫描都不发
    captured.clear()
    complete = [
        dict(entries[0], printed_no="1", display_index=1),
        dict(entries[1], printed_no="2", display_index=2),
    ]
    out = reference_vlm_grading._fill_missing_answer_numbers(complete, image, object(), "m")
    assert out == complete and captured == []


def test_extract_answer_table_splits_merged_block_and_fills_gap(monkeypatch, tmp_path):
    # 用户语文卷真实转写：1-7 一块、8 四小问、13 漏切 → 拆条 + 补 13
    image_path = tmp_path / "key.png"
    Image.new("RGB", (2078, 1070), "white").save(image_path)
    texts = {
        (269, 210): "1. D 2. B 3. A 4. 扼制 柳暗花明\n5. B 6. B 7. D",
        (281, 362): "8.(1)海日生残夜 江春入旧年 (2)我寄愁心与明月 随君直到夜郎西 (3)日月之行 若出其中 星汉灿烂 若出其里\n(4)夕阳西下 断肠人在天涯",
        (272, 571): "9.杨花和子规鸟。渲染了无限悲凉感伤的气氛。",
        (283, 642): "10.诗人听说友人将左迁龙标时的惆怅和恋恋不舍之情。",
        (285, 711): "11. 老舍 舒庆春 骆驼祥子(或:四世同堂)",
        (282, 781): "12. 描绘济南城冬天雪后山景的秀美。",
        (285, 909): "14. 不矛盾。因为济南四周有一圈小山。",
    }
    boxes = list(texts.keys())
    questions = [
        _make_question(display_index=index, question_words="", question_bbox=box, answer_bboxes=[box])
        for index, box in enumerate(boxes, start=1)
    ]
    monkeypatch.setattr(reference_vlm_grading, "_get_qwen_client_and_model", lambda: (object(), "m"))
    monkeypatch.setattr(
        reference_vlm_grading,
        "_extract_slot_answer_text",
        lambda _c, _m, _img, bbox: texts.get((bbox[0], bbox[1]), ""),
    )
    monkeypatch.setattr(
        reference_vlm_grading,
        "_extract_scan_answer_chunks",
        lambda _c, _m, _img, _bbox: {13: "空间"},
    )
    entries = reference_vlm_grading.extract_reference_answer_table(questions, str(image_path))
    by_no = {item["printed_no"]: item for item in entries}
    assert sorted(by_no, key=int) == [str(number) for number in range(1, 15)]
    assert [by_no[str(number)]["full_answer"] for number in (1, 2, 3, 4, 5, 6, 7)] == [
        "D",
        "B",
        "A",
        "扼制 柳暗花明",
        "B",
        "B",
        "D",
    ]
    assert by_no["8"]["full_answer"].startswith("8.(1)海日生残夜")  # 小问不拆
    assert by_no["13"]["full_answer"] == "空间"  # 缺号补齐
    assert by_no["3"]["display_index"] == 1003
    assert by_no["3"]["source_display_index"] == 1


def test_answer_table_slot_text_prefers_printed_no_and_joins_split_siblings():
    table = {
        "questions": [
            {
                "display_index": 1001,
                "printed_no": "1",
                "source_display_index": 1,
                "question_bbox": [0, 0, 100, 100],
                "slots": [{"sub_index": 1, "bbox": [0, 0, 100, 100], "answer_text": "D"}],
                "full_answer": "D",
            },
            {
                "display_index": 1002,
                "printed_no": "2",
                "source_display_index": 1,
                "question_bbox": [0, 0, 100, 100],
                "slots": [{"sub_index": 1, "bbox": [0, 0, 100, 100], "answer_text": "B"}],
                "full_answer": "B",
            },
        ]
    }
    merged = _make_question(display_index=1, question_words="", question_bbox=[0, 0, 100, 100])
    # 按学生印刷题号直取对应行（与判分查表同通道）
    assert _answer_table_slot_text(table, merged, [0, 0, 100, 100], prefer_no="2") == "B"
    assert _answer_table_slot_text(table, merged, [0, 0, 100, 100], prefer_no="1") == "D"
    # 没题号提示 → 拆条兄弟拼回全文
    assert _answer_table_slot_text(table, merged, [0, 0, 100, 100]) == "D\nB"


def test_grade_paper_slot_text_follows_split_table_by_printed_no(monkeypatch, tmp_path):
    # 拆条后：学生第2题的 correct_answer 是 B，不是合并块全文
    std = _make_question(display_index=1, question_words="", question_bbox=[269, 210, 1359, 375])
    stu = _make_question(
        question_id=2,
        display_index=1,
        question_words="2. 下列词语",
        printed_no="2",
        answer_words=["B"],
        answer_bboxes=[[10, 10, 50, 50]],
    )
    captured_prompts = []

    def _fake_vl(_client, _model, batch, _std_url, _stu_url, _student_name, family_hint="", answer_table_text=""):
        captured_prompts.append(
            reference_vlm_grading._build_batch_qwen_prompt(
                batch, _student_name, answer_table_text=answer_table_text
            )
        )
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
            }
            for task in batch.slots
        }

    monkeypatch.setattr(reference_vlm_grading, "extract_vlm_questions", lambda raw, image_path="": [stu])
    monkeypatch.setattr(reference_vlm_grading, "_get_qwen_client_and_model", lambda: (object(), "test-model"))
    monkeypatch.setattr(reference_vlm_grading, "_call_qwen_for_question_batch", _fake_vl)
    monkeypatch.setattr(
        reference_vlm_grading,
        "_crop_regions_to_data_url",
        lambda *a, **k: ("data:fake", b""),
    )
    monkeypatch.setattr(reference_vlm_grading, "_save_reference_vlm_artifacts", lambda **_k: None)
    monkeypatch.setattr(reference_vlm_grading, "_build_grading_tasks", lambda *a, **k: [_slot_task(std, stu)])
    monkeypatch.setattr(reference_vlm_grading, "_group_grading_tasks", lambda tasks: [
        VlmQuestionBatchTask(batch_id=1, student_question=stu, standard_question=std, slots=list(tasks))
    ])

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
                "slots": [{"sub_index": 1, "bbox": [269, 210, 1359, 375], "answer_text": "B"}],
                "full_answer": "B",
            },
        ]
    }
    _result, blocks, _raw, _src = grade_reference_vlm_paper(
        "标准答案.jpg",
        {"raw": {}, "image_path": str(std_img), "questions": [std]},
        "学生_1.jpg",
        {"raw": {}, "image_path": str(stu_img)},
        folder_safe="answer-table-split-test",
        answer_table=answer_table,
    )
    # 按学生印刷题号取行：第2题拿 B（不是合并块兄弟拼接的 "D\nB"）
    assert blocks[0]["correct_answer"] == "B"
    # 判分提示词里的完整表也是一题一行
    assert "第1题：D" in captured_prompts[0]
    assert "第2题：B" in captured_prompts[0]


def test_grade_paper_correct_answer_realigns_from_judge_located_no(monkeypatch, tmp_path):
    # 学生切题 OCR 认不出印刷题号（prefer_no 落空 → 机器配对拼整块 "D\nB"），
    # 但判分模型回填 located_no=2：correct_answer 元数据必须跟判分所依的第2题行
    std = _make_question(display_index=1, question_words="", question_bbox=[269, 210, 1359, 375])
    stu = _make_question(
        question_id=2,
        display_index=1,
        question_words="",
        answer_words=[],  # 切题 OCR 无文本：student_answer 退回判分转写
        answer_bboxes=[[10, 10, 50, 50]],
    )

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
                "standard_quote": "第2题：B",
            }
            for task in batch.slots
        }

    monkeypatch.setattr(reference_vlm_grading, "extract_vlm_questions", lambda raw, image_path="": [stu])
    monkeypatch.setattr(reference_vlm_grading, "_get_qwen_client_and_model", lambda: (object(), "test-model"))
    monkeypatch.setattr(reference_vlm_grading, "_call_qwen_for_question_batch", _fake_vl)
    monkeypatch.setattr(
        reference_vlm_grading,
        "_crop_regions_to_data_url",
        lambda *a, **k: ("data:fake", b""),
    )
    monkeypatch.setattr(reference_vlm_grading, "_save_reference_vlm_artifacts", lambda **_k: None)
    monkeypatch.setattr(reference_vlm_grading, "_build_grading_tasks", lambda *a, **k: [_slot_task(std, stu)])
    monkeypatch.setattr(reference_vlm_grading, "_group_grading_tasks", lambda tasks: [
        VlmQuestionBatchTask(batch_id=1, student_question=stu, standard_question=std, slots=list(tasks))
    ])

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
                "slots": [{"sub_index": 1, "bbox": [269, 210, 1359, 375], "answer_text": "B"}],
                "full_answer": "B",
            },
        ]
    }
    _result, blocks, _raw, _src = grade_reference_vlm_paper(
        "标准答案.jpg",
        {"raw": {}, "image_path": str(std_img), "questions": [std]},
        "学生_1.jpg",
        {"raw": {}, "image_path": str(stu_img)},
        folder_safe="answer-table-located-no-test",
        answer_table=answer_table,
    )
    # 判分回填：元数据跟 located_no=2 的行（B），不是机器配对的兄弟拼接 "D\nB"
    assert blocks[0]["correct_answer"] == "B"
    # 切题 OCR 无文本时 student_answer 退回判分转写，老师面板不留白
    assert blocks[0]["student_answer"] == "B"


def test_build_blocks_student_answer_falls_back_to_transcription_only_when_ocr_empty():
    # OCR 有文本：仍用 OCR 文本（缓存身份键口径不变）；OCR 空：用判分转写
    stu = _make_question(
        question_id=5,
        question_words="第5题",
        answer_words=["3"],
        answer_bboxes=[[10, 10, 50, 50]],
    )
    _insert_sub_grading_result(
        stu,
        {
            "question_id": 1,
            "correctResult": 1,
            "result": "对",
            "transcription": "转写内容",
            "reason": "r",
            "analysis": "a",
            "confidence": 0.9,
        },
        task_id=1,
        sub_index=1,
        answer_bbox=[10, 10, 50, 50],
        has_mark_anchor=True,
        has_handwriting_location=True,
        is_answer_slot=True,
        correct_answer="3",
        question_content="第5题",
    )
    assert _build_blocks([stu])[0]["student_answer"] == "3"

    stu2 = _make_question(
        question_id=6,
        question_words="第6题",
        answer_words=[],
        answer_bboxes=[[10, 10, 50, 50]],
    )
    _insert_sub_grading_result(
        stu2,
        {
            "question_id": 1,
            "correctResult": 1,
            "result": "对",
            "transcription": "转写内容",
            "reason": "r",
            "analysis": "a",
            "confidence": 0.9,
        },
        task_id=1,
        sub_index=1,
        answer_bbox=[10, 10, 50, 50],
        has_mark_anchor=True,
        has_handwriting_location=True,
        is_answer_slot=True,
        correct_answer="标准",
        question_content="第6题",
    )
    assert _build_blocks([stu2])[0]["student_answer"] == "转写内容"


def test_prompt_with_answer_table_teaches_number_first():
    std = _make_question(question_words="第1题", answer_words=["x=2"], answer_bboxes=[[10, 10, 50, 50]])
    stu = _make_question(question_id=2, question_words="第1题", answer_words=["x=3"], answer_bboxes=[[10, 10, 50, 50]])
    task = _slot_task(std, stu, standard_answer_text="x=2")
    prompt = _build_slot_qwen_prompt(task, "学生.jpg", answer_table_text="第3题：A\n第1题：x=2")
    assert "【参考答案完整表" in prompt
    assert "第3题：A" in prompt and "第1题：x=2" in prompt
    assert "先认图像2红框旁的印刷题号" in prompt
    assert "【本槽代码初步对照" in prompt  # 机器配对降级为「禁止作为判分依据」
    assert "禁止作为判分依据" in prompt
    assert "judge that slot ONLY against the 第N题 entry" in prompt
    assert "无法定位题号" in prompt  # 认不出题号→待确认，不许猜配对
    assert "each red slot holds just one blank" in prompt  # 多空题只判该空
    assert "STANDARD-ANSWER TEXT AUTHORITY" in prompt
    assert "image 1 is the sole ground truth" in prompt
    # 无表路径维持原契约（既有锁词测试依赖）
    plain = _build_slot_qwen_prompt(task, "学生.jpg")
    assert "【参考答案完整表" not in plain
    assert "【标准答案（标准答案识别文本，唯一判分依据）】" in plain

    batch = VlmQuestionBatchTask(batch_id=7, student_question=stu, standard_question=std, slots=[task])
    batch_prompt = _build_batch_qwen_prompt(batch, "学生.jpg", answer_table_text="第1题：x=2")
    assert "【参考答案完整表" in batch_prompt
    # 每槽行不再带机器配对文本（防模型照错配对判分），改为指路完整表
    assert "作答区 1_1：x=2" not in batch_prompt
    assert "作答区 1_1：按该空所属印刷题号查【参考答案完整表】判分" in batch_prompt
    assert '"standard_answer_text_is_ground_truth": false' in batch_prompt
    assert "〈文本缺失〉的槽以 image 1 对应红框为准" in batch_prompt


def test_build_tasks_no_slot_standard_uses_question_bbox_as_red_box():
    # 打字版答案行/切题审查整行框：标准题无细分作答区时，红框标整行，
    # 不能把学生框按页比缩放出来的碎片当标准答案区（跨版面缩放无对齐意义）
    std = _make_question(
        display_index=1,
        question_words="",
        answer_words=[],
        answer_bboxes=[],
        question_bbox=[280, 380, 2040, 580],
    )
    stu = _make_question(
        question_id=2,
        display_index=1,
        question_words="",
        answer_words=[],
        answer_bboxes=[[100, 100, 400, 160]],
        question_bbox=[100, 90, 400, 170],
    )
    tasks = _build_grading_tasks([std], [stu], (2078, 1070), (3626, 2558))
    assert len(tasks) == 1
    assert tasks[0].standard_answer_bbox == [280, 380, 2040, 580]
    assert tasks[0].student_answer_bbox == [100, 100, 400, 160]


def _fake_vl_client(content: str):
    """假 VL 客户端：记录 chat.completions.create 调用次数，固定返回 content。"""
    state = {"calls": 0}

    def _create(**_kwargs):
        state["calls"] += 1
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
    )
    return client, state


def test_extract_slot_answer_text_blank_region_skips_vl():
    # 空白作答区：墨迹闸直接回空串、一次 VL 都不发——纯白区问模型必出幻觉
    image = Image.new("RGB", (200, 200), "white")
    client, state = _fake_vl_client('{"answer_text": "幻觉答案"}')
    text = reference_vlm_grading._extract_slot_answer_text(
        client, "m", image, [50, 50, 150, 120]
    )
    assert text == ""
    assert state["calls"] == 0


def test_extract_slot_answer_text_ink_region_still_sends_vl():
    # 有墨迹（印刷答案/横线括号）照常转写：闸不误跳
    image = Image.new("RGB", (200, 200), "white")
    ImageDraw.Draw(image).rectangle([60, 60, 120, 110], fill="black")
    client, state = _fake_vl_client('{"answer_text": "D"}')
    text = reference_vlm_grading._extract_slot_answer_text(
        client, "m", image, [50, 50, 150, 120]
    )
    assert text == "D"
    assert state["calls"] == 1


def test_extract_answer_table_blank_paper_skips_gap_fill(monkeypatch, tmp_path):
    # 空白卷：全槽无答案 → 缺号补扫整段跳过（否则补扫会把题干当答案抄回来）
    image_path = tmp_path / "blank.png"
    Image.new("RGB", (200, 200), "white").save(image_path)
    questions = [
        _make_question(
            display_index=1,
            printed_no="1",
            question_words="1. 下列加点字注音",
            question_bbox=[10, 10, 180, 70],
            answer_bboxes=[[10, 30, 180, 70]],
        ),
        # 题号跳到 3：留缺口诱惑补扫
        _make_question(
            display_index=2,
            printed_no="3",
            question_words="3. 古诗默写",
            question_bbox=[10, 90, 180, 180],
            answer_bboxes=[[10, 130, 180, 180]],
        ),
    ]
    monkeypatch.setattr(
        reference_vlm_grading, "_get_qwen_client_and_model", lambda: (object(), "m")
    )
    monkeypatch.setattr(reference_vlm_grading, "_extract_slot_answer_text", lambda *_: "")

    def _fail_gap_fill(*_args, **_kwargs):
        raise AssertionError("空白卷不该触发缺号补扫")

    monkeypatch.setattr(reference_vlm_grading, "_extract_scan_answer_chunks", _fail_gap_fill)
    entries = reference_vlm_grading.extract_reference_answer_table(questions, str(image_path))
    # 答案表只留题号 + 答题区，答案全空
    assert [entry["printed_no"] for entry in entries] == ["1", "3"]
    assert all(entry["full_answer"] == "" for entry in entries)
    assert [entry["slots"][0]["answer_text"] for entry in entries] == ["", ""]
    assert entries[0]["slots"][0]["bbox"] == [10, 30, 180, 70]
    assert entries[1]["slots"][0]["bbox"] == [10, 130, 180, 180]


def test_crop_reference_answer_table_region_returns_jpeg(tmp_path):
    image_path = tmp_path / "std.png"
    Image.new("RGB", (800, 600), "white").save(image_path)
    # 正常框：返回 JPEG，长边压到 max_side 以内
    data = reference_vlm_grading.crop_reference_answer_table_region(
        str(image_path), [0, 0, 800, 600], pad=0, max_side=720
    )
    assert data[:2] == b"\xff\xd8"  # JPEG SOI
    with Image.open(BytesIO(data)) as thumb:
        assert thumb.format == "JPEG"
        assert max(thumb.size) <= 720
    # bbox 出界不炸：钳位到图内照常返回
    edge = reference_vlm_grading.crop_reference_answer_table_region(
        str(image_path), [-50, -50, 850, 650], pad=0
    )
    assert edge[:2] == b"\xff\xd8"
    # 零面积框报错，前端可提示坐标无效
    try:
        reference_vlm_grading.crop_reference_answer_table_region(
            str(image_path), [10, 10, 10, 10], pad=0
        )
    except RuntimeError as exc:
        assert "坐标无效" in str(exc)
    else:
        raise AssertionError("零面积 bbox 应报 RuntimeError")


def test_apply_answer_sheet_texts_fills_slots_by_printed_no():
    # 答案纸按印刷题号落进条目：单空直填、多空按（1）（2）子号拆、拆不出整段进第一空
    entries = [
        {
            "display_index": 1,
            "printed_no": "1",
            "question_bbox": [0, 0, 10, 10],
            "slots": [{"sub_index": 1, "bbox": [0, 0, 10, 10], "answer_text": ""}],
            "full_answer": "",
        },
        {
            "display_index": 2,
            "printed_no": "8",
            "question_bbox": [0, 0, 10, 10],
            "slots": [
                {"sub_index": 1, "bbox": [0, 0, 10, 10], "answer_text": ""},
                {"sub_index": 2, "bbox": [0, 0, 10, 10], "answer_text": ""},
            ],
            "full_answer": "",
        },
        {
            "display_index": 3,
            "printed_no": "9",
            "question_bbox": [0, 0, 10, 10],
            "slots": [
                {"sub_index": 1, "bbox": [0, 0, 10, 10], "answer_text": ""},
                {"sub_index": 2, "bbox": [0, 0, 10, 10], "answer_text": ""},
            ],
            "full_answer": "",
        },
    ]
    texts = {"1": "D", "8": "（1）海日生残夜（2）江春入旧年", "99": "多出来的题不认"}
    reference_vlm_grading._apply_answer_sheet_texts(entries, texts)
    assert entries[0]["slots"][0]["answer_text"] == "D"
    assert entries[0]["full_answer"] == "D"
    assert [slot["answer_text"] for slot in entries[1]["slots"]] == ["海日生残夜", "江春入旧年"]
    assert entries[1]["full_answer"] == "海日生残夜\n江春入旧年"
    # 子号拆不开（只有一个子号）：整段进第一空，第二空留白
    assert [slot["answer_text"] for slot in entries[2]["slots"]] == ["", ""]
    reference_vlm_grading._apply_answer_sheet_texts(entries, {"9": "对影成三人"})
    assert [slot["answer_text"] for slot in entries[2]["slots"]] == ["对影成三人", ""]


def test_split_answer_text_to_slot_texts_plain_multi_blank():
    # 无小问号的多空题（用户实况）：空格分段恰好等于空数就逐空填，不能只塞第一空
    # 第4题两空：「扼制 柳暗花明」
    assert reference_vlm_grading._split_answer_text_to_slot_texts(
        "扼制 柳暗花明", 2
    ) == ["扼制", "柳暗花明"]
    # 第11题三空：「老舍 舒庆春 骆驼祥子(或：四世同堂)」——括号补充粘住不动
    assert reference_vlm_grading._split_answer_text_to_slot_texts(
        "老舍 舒庆春 骆驼祥子(或：四世同堂)", 3
    ) == ["老舍", "舒庆春", "骆驼祥子(或：四世同堂)"]
    assert reference_vlm_grading._split_answer_text_to_slot_texts(
        "老舍 舒庆春 骆驼祥子 (或：四世同堂)", 3
    ) == ["老舍", "舒庆春", "骆驼祥子(或：四世同堂)"]
    # 段数对不上空数：宁缺勿串，整段进第一空
    assert reference_vlm_grading._split_answer_text_to_slot_texts(
        "扼制 柳暗花明 红", 2
    ) == ["扼制 柳暗花明 红", ""]
    # 只有一个段：整段进第一空
    assert reference_vlm_grading._split_answer_text_to_slot_texts(
        "对影成三人", 2
    ) == ["对影成三人", ""]


def test_load_or_build_answer_sheet_texts_caches_by_signature(monkeypatch, tmp_path):
    # 答案纸按文件签名缓存：同页文件不重扫；换文件整包重扫；扫描失败不写缓存
    img = tmp_path / "答案.png"
    Image.new("RGB", (100, 100), "white").save(img)
    cache_path = tmp_path / "sheet.json"
    monkeypatch.setattr(
        reference_vlm_grading, "_answer_sheet_cache_path", lambda _f: cache_path
    )
    monkeypatch.setattr(
        reference_vlm_grading, "_get_qwen_client_and_model", lambda: (object(), "m")
    )
    calls = []

    def _fake_scan(_client, _model, _image, _bbox):
        calls.append(1)
        return {1: "A", 2: "B"}

    monkeypatch.setattr(reference_vlm_grading, "_extract_scan_answer_chunks", _fake_scan)
    pages = [(str(img), str(img))]
    first = reference_vlm_grading.load_or_build_answer_sheet_texts("f", pages)
    assert first == {"1": "A", "2": "B"}
    again = reference_vlm_grading.load_or_build_answer_sheet_texts("f", pages)
    assert again == {"1": "A", "2": "B"}
    assert len(calls) == 1  # 同签名直接吃缓存，不重烧 VL
    # 换答案纸文件 → 整包重扫
    img2 = tmp_path / "答案2.png"
    Image.new("RGB", (120, 120), "white").save(img2)
    monkeypatch.setattr(
        reference_vlm_grading, "_extract_scan_answer_chunks", lambda *_a, **_k: {1: "C"}
    )
    second = reference_vlm_grading.load_or_build_answer_sheet_texts(
        "f", [(str(img2), str(img2))]
    )
    assert second == {"1": "C"}
    # 扫描失败回空且不写缓存：下次自动重试，不会把空结果钉死
    cache_path.unlink()
    monkeypatch.setattr(
        reference_vlm_grading,
        "_extract_scan_answer_chunks",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("VL挂了")),
    )
    assert (
        reference_vlm_grading.load_or_build_answer_sheet_texts(
            "f", [(str(img2), str(img2))]
        )
        == {}
    )
    assert not cache_path.exists()


def test_answer_table_sheet_texts_merge_before_manual_edits(monkeypatch, tmp_path):
    # 合并顺序 = 识别 → 答案纸 → 手改覆盖层：手改永远盖得回来，换纸重建也不丢
    monkeypatch.setattr(reference_vlm_grading, "correct_docs_dir", lambda: tmp_path)
    monkeypatch.setattr(
        reference_vlm_grading, "load_reference_layout", lambda folder: {"updated_at": "t1"}
    )
    image_path = tmp_path / "std.png"
    Image.new("RGB", (50, 50), "white").save(image_path)
    doc = {
        "raw": {},
        "image_path": str(image_path),
        "questions": [_make_question(answer_bboxes=[[10, 10, 50, 50]], printed_no="1")],
    }
    monkeypatch.setattr(
        reference_vlm_grading,
        "extract_reference_answer_table",
        lambda questions, image_path, *, skip_printed_numbers=None, stop_event=None: [
            {
                "display_index": 1,
                "printed_no": "1",
                "question_bbox": [0, 0, 100, 100],
                "slots": [{"sub_index": 1, "bbox": [10, 10, 50, 50], "answer_text": ""}],
                "full_answer": "",
            }
        ],
    )
    page = load_or_build_reference_answer_table(
        "ans-sheet-test", 1, doc, answer_sheet_texts={"1": "纸答案"}
    )
    assert page["questions"][0]["slots"][0]["answer_text"] == "纸答案"
    # 同一份答案纸 → 缓存命中
    again = load_or_build_reference_answer_table(
        "ans-sheet-test", 1, doc, answer_sheet_texts={"1": "纸答案"}
    )
    assert again["questions"][0]["slots"][0]["answer_text"] == "纸答案"
    # 手改盖过答案纸
    saved = save_reference_answer_table_edits(
        "ans-sheet-test",
        1,
        [{"display_index": 1, "printed_no": "1", "slots": [{"sub_index": 1, "answer_text": "手改"}]}],
    )
    assert saved["questions"][0]["slots"][0]["answer_text"] == "手改"
    # 换答案纸 → 缓存指纹变重建；手改仍在且盖在新纸答案上
    page2 = load_or_build_reference_answer_table(
        "ans-sheet-test", 1, doc, answer_sheet_texts={"1": "新纸答案"}
    )
    assert page2["questions"][0]["slots"][0]["answer_text"] == "手改"
    # 放弃手改重识别 → 新纸答案生效
    invalidate_reference_answer_table("ans-sheet-test", 1, reset_edits=True)
    page3 = load_or_build_reference_answer_table(
        "ans-sheet-test", 1, doc, answer_sheet_texts={"1": "新纸答案"}
    )
    assert page3["questions"][0]["slots"][0]["answer_text"] == "新纸答案"


def test_invalidate_reference_answer_table_clears_sheet_cache(monkeypatch, tmp_path):
    # 重新识别 = 全链路重来：答案纸扫描缓存一并作废（扫错/扫漏这次重试）
    monkeypatch.setattr(reference_vlm_grading, "correct_docs_dir", lambda: tmp_path)
    cache_path = tmp_path / "ans-inv" / ".answer_sheet_cache.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text("{}", encoding="utf-8")
    invalidate_reference_answer_table("ans-inv")
    assert not cache_path.exists()


def test_apply_answer_sheet_texts_order_fallback_when_unnumbered():
    # 空白卷切题认不出印刷题号（printed_no 全空）：答案纸 1..N 恰好 N 行才按行序兜底
    def _rows(count: int) -> list:
        return [
            {
                "display_index": i,
                "printed_no": None,
                "question_bbox": [0, 0, 10, 10],
                "slots": [{"sub_index": 1, "bbox": [0, 0, 10, 10], "answer_text": ""}],
                "full_answer": "",
            }
            for i in range(1, count + 1)
        ]

    # 条目 3 行、答案纸 1..3 → 按行序一一配对
    entries = _rows(3)
    reference_vlm_grading._apply_answer_sheet_texts(
        entries, {"1": "A", "2": "B", "3": "C"}
    )
    assert [e["slots"][0]["answer_text"] for e in entries] == ["A", "B", "C"]
    # 宁缺勿串：答案纸题号不连续（1、2、4）→ 一行都不配
    entries = _rows(3)
    reference_vlm_grading._apply_answer_sheet_texts(
        entries, {"1": "A", "2": "B", "4": "D"}
    )
    assert [e["slots"][0]["answer_text"] for e in entries] == ["", "", ""]
    # 数目对不上（2 行答案配 3 行条目）→ 一行都不配
    entries = _rows(3)
    reference_vlm_grading._apply_answer_sheet_texts(entries, {"1": "A", "2": "B"})
    assert [e["slots"][0]["answer_text"] for e in entries] == ["", "", ""]
    # 零星题号且与行序自洽（2 号就在第 2 行）→ 兜底照启用，整页补齐
    entries = _rows(3)
    entries[1]["printed_no"] = "2"
    reference_vlm_grading._apply_answer_sheet_texts(
        entries, {"1": "A", "2": "B", "3": "C"}
    )
    assert [e["slots"][0]["answer_text"] for e in entries] == ["A", "B", "C"]


def test_apply_answer_sheet_texts_order_fallback_partial_numbers_real_case():
    # 用户实况回归：空白卷切题 14 行里只有第 14 行认出印刷号 14，其余全空
    # ——按题号只中 1 行，行序兜底必须照样把整页 14 行全填上
    entries = [
        {
            "display_index": i,
            "printed_no": "14" if i == 14 else "",
            "question_bbox": [0, 0, 10, 10],
            "slots": [{"sub_index": 1, "bbox": [0, 0, 10, 10], "answer_text": ""}],
            "full_answer": "",
        }
        for i in range(1, 15)
    ]
    texts = {str(i): f"答{i}" for i in range(1, 15)}
    reference_vlm_grading._apply_answer_sheet_texts(entries, texts)
    assert [e["slots"][0]["answer_text"] for e in entries] == [
        f"答{i}" for i in range(1, 15)
    ]

    # 零星题号与行序矛盾（3 号出现在第 2 行）→ 兜底禁用，只按题号命中那行
    entries = [
        {
            "display_index": i,
            "printed_no": "3" if i == 2 else "",
            "question_bbox": [0, 0, 10, 10],
            "slots": [{"sub_index": 1, "bbox": [0, 0, 10, 10], "answer_text": ""}],
            "full_answer": "",
        }
        for i in range(1, 4)
    ]
    reference_vlm_grading._apply_answer_sheet_texts(
        entries, {"1": "A", "2": "B", "3": "C"}
    )
    assert [e["slots"][0]["answer_text"] for e in entries] == ["", "C", ""]


def test_looks_like_template_noise_filters_blank_template():
    # 空白卷印刷括号/下划线/标点不算答案（墨迹闸拦不住印刷件）
    for noise in ["", "   ", "（）", "（ ）", "是（ ）", "不( )", "，", "《____》，", "____", "。（）"]:
        assert reference_vlm_grading._looks_like_template_noise(noise), noise
    for real in ["D", "对", "海日生残夜", "是", "（1）A（2）B", "x=1"]:
        assert not reference_vlm_grading._looks_like_template_noise(real), real


def test_save_answer_sheet_texts_aligns_signature_to_current_files(monkeypatch, tmp_path):
    # 老师专窗改完落盘：签名对齐当前答案纸，后续扫描直接吃这份人工修正版
    monkeypatch.setattr(reference_vlm_grading, "correct_docs_dir", lambda: tmp_path)
    monkeypatch.setattr(
        reference_vlm_grading, "_get_qwen_client_and_model", lambda: (object(), "m")
    )
    img = tmp_path / "答案.png"
    Image.new("RGB", (80, 80), "white").save(img)
    pages = [(str(img), str(img))]
    scans = []
    monkeypatch.setattr(
        reference_vlm_grading,
        "_extract_scan_answer_chunks",
        lambda *_a, **_k: scans.append(1) or {1: "机器答案"},
    )
    saved = reference_vlm_grading.save_answer_sheet_texts(
        "ans-save-test", pages, {"1": "老师改过", "2": "  ", "03": "手写补充"}
    )
    assert saved == {"1": "老师改过", "3": "手写补充"}
    # 同文件再 load：签名一致 → 吃缓存的人工修正版，不重烧 VL
    loaded = reference_vlm_grading.load_or_build_answer_sheet_texts(
        "ans-save-test", pages
    )
    assert loaded == {"1": "老师改过", "3": "手写补充"}
    assert scans == []
    assert reference_vlm_grading.read_answer_sheet_texts("ans-save-test") == {
        "1": "老师改过",
        "3": "手写补充",
    }

