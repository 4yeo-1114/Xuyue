# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import tempfile
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from app.grading import reference_vlm_grading
from app.grading.router import _reference_standard_document
from app.grading.reference_vlm_grading import (
    _build_grading_tasks,
    _build_batch_qwen_prompt,
    _build_blocks,
    _build_slot_qwen_prompt,
    _crop_to_data_url,
    _grading_policy_hint,
    _group_grading_tasks,
    _insert_grading_result,
    _json_object_from_text,
    _match_questions,
    _normalize_math_text,
    _normalize_batch_decision,
    build_reference_layout_page,
    build_reference_vlm_slot_template,
    confirm_reference_layout,
    draw_reference_vlm_marks_and_save,
    extract_vlm_questions,
    get_confirmed_reference_document,
    grade_reference_vlm_paper,
    load_reference_layout_for_editing,
    reference_layout_status,
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

    def fake_qwen_batch(_client, _model, batch, _std_url, _stu_url, _student_name):
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


def test_unanswered_projected_slot_draws_circle_without_cross():
    out_dir = Path(tempfile.mkdtemp(prefix="reference_vlm_blank_circle_"))
    image_path = out_dir / "paper.jpg"
    Image.new("RGB", (600, 400), "white").save(image_path)
    block = {
        "is_question": True,
        "result": "未作答",
        "baidu_correct_result": 3,
        "baidu_is_slot": True,
        "has_handwriting_location": False,
        "has_mark_anchor": True,
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
        center = marked.getpixel((360, 210))

    assert red_pixels
    assert 285 <= min(x for x, _y in red_pixels) <= 305
    assert 415 <= max(x for x, _y in red_pixels) <= 435
    assert 165 <= min(y for _x, y in red_pixels) <= 185
    assert 235 <= max(y for _x, y in red_pixels) <= 255
    assert center[0] > 200 and center[1] > 200 and center[2] > 200


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
        lambda _client, _model, batch, _std_url, _stu_url, _student_name: {
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
