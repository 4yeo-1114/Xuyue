from __future__ import annotations

import copy
import json
from pathlib import Path

from PIL import Image

from app.grading import manual_grading
from app.grading import router as grading_router


def _image(path: Path, size: tuple[int, int]) -> None:
    Image.new("RGB", size, "white").save(path)


def _raw_page() -> dict:
    def points(x1: int, y1: int, x2: int, y2: int) -> list[dict[str, int]]:
        return [
            {"x": x1, "y": y1},
            {"x": x2, "y": y1},
            {"x": x2, "y": y2},
            {"x": x1, "y": y2},
        ]

    return {
        "qus_result": [
            {
                "qus_type": "4",
                "qus_location": {"points": points(100, 100, 900, 500)},
                "qus_element": [
                    {
                        "elem_type": "2",
                        "elem_location": {"points": points(300, 250, 500, 350)},
                        "elem_word": [{"word": "答案一"}],
                    },
                    {
                        "elem_type": "2",
                        "elem_location": {"points": points(550, 250, 750, 350)},
                        "elem_word": [{"word": "答案二"}],
                    },
                ],
            }
        ]
    }


def test_manual_layout_persists_scores_and_scales_boxes(tmp_path, monkeypatch):
    folder = tmp_path / "exam"
    folder.mkdir()
    source = folder / "学生甲_1.jpg"
    target = folder / "学生乙_1.jpg"
    _image(source, (1000, 600))
    _image(target, (2000, 1200))
    monkeypatch.setattr(manual_grading, "correct_docs_dir", lambda: tmp_path)

    page = manual_grading.build_manual_layout_page(
        _raw_page(),
        page_no=1,
        filename=source.name,
        image_url="/source.jpg",
        image_path=str(source),
    )
    assert len(page["questions"]) == 1
    assert len(page["questions"][0]["answer_slots"]) == 2
    page["questions"][0]["answer_slots"][0]["max_score"] = 3
    page["questions"][0]["answer_slots"][1]["max_score"] = 2

    prepare_id = manual_grading.save_manual_layout_prepare(
        "exam",
        [{**copy.deepcopy(page), "source_path": str(source), "image_path": str(source), "raw": _raw_page()}],
    )
    confirmed = manual_grading.confirm_manual_layout("exam", prepare_id, [page])
    saved_slots = confirmed["pages"]["1"]["layout"]["questions"][0]["answer_slots"]
    assert [slot["max_score"] for slot in saved_slots] == [3.0, 2.0]

    blocks, image_size = manual_grading.manual_layout_blocks_for_image(
        confirmed["pages"]["1"]["layout"], str(target)
    )
    assert image_size == [2000, 1200]
    assert blocks[0]["bbox"] == [600, 500, 1000, 700]
    assert blocks[1]["bbox"] == [1100, 500, 1500, 700]
    assert [block["max_score"] for block in blocks] == [3.0, 2.0]


def test_manual_decisions_enforce_scores_and_completion(monkeypatch):
    persisted: list[dict] = []
    monkeypatch.setattr(
        grading_router,
        "_persist_grading_success",
        lambda _safe, item, _engine: persisted.append(copy.deepcopy(item)),
    )
    result = {
        "type": "manual_analyze",
        "version": 2,
        "manual_status": "ungraded",
        "blocks": [
            {"slot_id": "s1", "title": "第1题-作答区1", "bbox": [1, 1, 20, 20], "max_score": 4},
            {"slot_id": "s2", "title": "第1题-作答区2", "bbox": [21, 1, 40, 20], "max_score": 2},
            {"slot_id": "s3", "title": "第2题-作答区1", "bbox": [1, 21, 20, 40], "max_score": 3},
            {"slot_id": "s4", "title": "第2题-作答区2", "bbox": [21, 21, 40, 40], "max_score": 1},
        ],
    }
    item = {"name": "学生甲_1.jpg", "result": json.dumps(result, ensure_ascii=False)}
    decisions = {
        "s1": {"status": "correct"},
        "s2": {"status": "wrong"},
        "s3": {"status": "unanswered"},
        "s4": {"status": "partial", "score": 0.5},
    }

    saved = grading_router._save_manual_slot_decisions(
        "exam",
        item["name"],
        item,
        result,
        decisions,
        generate_marks=False,
    )
    parsed = json.loads(saved["result"])
    assert parsed["manual_status"] == "graded"
    assert parsed["score_total"] == 4.5
    assert parsed["max_score_total"] == 10.0
    assert parsed["scores"] == {
        "第1题-作答区1": 4.0,
        "第1题-作答区2": 0.0,
        "第2题-作答区1": 0.0,
        "第2题-作答区2": 0.5,
    }
    assert saved["score_total"] == 4.5
    assert persisted


def test_manual_decisions_remain_ungraded_until_every_slot_is_done(monkeypatch):
    monkeypatch.setattr(grading_router, "_persist_grading_success", lambda *_args, **_kwargs: None)
    result = {
        "type": "manual_analyze",
        "version": 2,
        "blocks": [
            {"slot_id": "s1", "title": "A", "bbox": [1, 1, 2, 2], "max_score": 1},
            {"slot_id": "s2", "title": "B", "bbox": [2, 2, 3, 3], "max_score": 1},
        ],
    }
    item = {"name": "学生甲_1.jpg", "result": json.dumps(result)}

    saved = grading_router._save_manual_slot_decisions(
        "exam",
        item["name"],
        item,
        result,
        {"s1": {"status": "correct"}, "s2": {"status": "ungraded"}},
        generate_marks=False,
    )
    parsed = json.loads(saved["result"])
    assert parsed["manual_status"] == "ungraded"
    assert saved["score_total"] is None


def test_confirmed_layout_materializes_every_student_page(tmp_path, monkeypatch):
    papers = tmp_path / "papers"
    history = tmp_path / "history"
    exam = papers / "exam"
    exam.mkdir(parents=True)
    for filename in ("甲_1.jpg", "甲_2.jpg", "乙_1.jpg", "乙_2.jpg"):
        _image(exam / filename, (1000, 600))

    monkeypatch.setattr(grading_router, "correct_docs_dir", lambda: papers)
    monkeypatch.setattr(grading_router, "grading_history_dir", lambda: history)
    monkeypatch.setattr(grading_router, "_get_grading_path", lambda _safe, path: path)
    monkeypatch.setattr(grading_router, "_preview_url_for_file", lambda _safe, name: f"/{name}")
    monkeypatch.setattr(grading_router, "_delete_modify_file_by_url", lambda _url: None)
    # 引擎切换守卫要求写历史前先「建立权威 run」（replace 会写盖引擎戳的空历史）。
    # 这里跳过 replace 的清场副作用，但保留建立动作，否则后续 manual 落盘会被守卫丢弃。
    def _fake_replace(_safe: str, _engine: str) -> None:
        grading_router._write_grading_history(
            _safe,
            grading_router._empty_grading_history(_engine),
            _engine,
            authoritative=True,
        )

    monkeypatch.setattr(grading_router, "_replace_folder_grading_run", _fake_replace)

    def layout(page_no: int) -> dict:
        return {
            "page_no": page_no,
            "image_size": [1000, 600],
            "questions": [
                {
                    "display_no": page_no,
                    "question_type": "4",
                    "answer_slots": [
                        {
                            "slot_id": f"p{page_no}-s1",
                            "label": f"{page_no}_1",
                            "bbox": [100, 100, 300, 200],
                            "max_score": 5,
                        }
                    ],
                }
            ],
        }

    count = grading_router._materialize_manual_layout_history(
        "exam",
        {
            "updated_at": "now",
            "pages": {"1": {"layout": layout(1)}, "2": {"layout": layout(2)}},
        },
    )
    assert count == 4
    saved = json.loads((history / "exam__manual.json").read_text(encoding="utf-8"))
    assert set(saved["completed"]) == {"甲_1.jpg", "甲_2.jpg", "乙_1.jpg", "乙_2.jpg"}
    assert all(json.loads(item["result"])["manual_status"] == "ungraded" for item in saved["completed"].values())


def test_header_field_is_skipped_by_is_header_field():
    assert manual_grading._is_header_field("姓名:班级:")
    assert manual_grading._is_header_field("考场/座位号:")
    assert manual_grading._is_header_field("准考证号")
    assert manual_grading._is_header_field("学生姓名")
    # 真实题目题干不应被误判
    assert not manual_grading._is_header_field("学校图书馆周末开放的时间是？")
    assert not manual_grading._is_header_field("在做功和功率的实验中，")
    assert not manual_grading._is_header_field("")


def test_parse_paper_cut_skips_name_header_but_keeps_questions():
    def points(x1, y1, x2, y2):
        return [
            {"x": x1, "y": y1},
            {"x": x2, "y": y1},
            {"x": x2, "y": y2},
            {"x": x1, "y": y2},
        ]

    raw = {
        "qus_result": [
            # 抬头字段：姓名/班级 + 手写姓名
            {
                "qus_type": "2",
                "qus_location": {"points": points(80, 200, 400, 350)},
                "qus_element": [
                    {
                        "elem_type": "0",
                        "elem_location": {"points": points(80, 200, 230, 350)},
                        "elem_word": [{"word": "姓名:"}, {"word": "班级:"}],
                    },
                    {
                        "elem_type": "2",
                        "elem_location": {"points": points(225, 250, 370, 290)},
                        "elem_word": [{"word": "魏梓熙"}],
                    },
                ],
            },
            # 真实题目
            {
                "qus_type": "2",
                "qus_location": {"points": points(80, 550, 850, 850)},
                "qus_element": [
                    {
                        "elem_type": "0",
                        "elem_location": {"points": points(80, 550, 850, 850)},
                        "elem_word": [{"word": "1."}],
                    },
                    {
                        "elem_type": "2",
                        "elem_location": {"points": points(140, 600, 270, 660)},
                        "elem_word": [{"word": "做功"}],
                    },
                ],
            },
        ]
    }
    blocks = manual_grading.parse_paper_cut_result(raw)
    assert [block["index"] for block in blocks] == [2]
    assert blocks[0]["text"] == "做功"
    assert all("魏梓熙" not in block["text"] for block in blocks)


# ── 试卷（手动批改）：标准答题区 → 自主阅卷切题页 ─────────────────────────


def _ref_page() -> dict:
    """标准答题区页（reference layout 已确认形状）：2 题，坐标在 1000×600 标准卷面上。"""
    return {
        "page_no": 1,
        "image_size": [1000, 600],
        "layout": {
            "page_no": 1,
            "image_size": [1000, 600],
            "questions": [
                {
                    "question_id": "q-1",
                    "display_no": 1,
                    "question_type": "填空题",
                    "question_text": "做功的两个必要因素",
                    "regions": [{"region_id": "q-1-r1", "bbox": [50, 50, 400, 150]}],
                    "answer_slots": [
                        {
                            "slot_id": "q-1-s1",
                            "label": "1_1",
                            "order": 1,
                            "bbox": [50, 160, 200, 220],
                            "regions": [{"bbox": [50, 160, 200, 220]}],
                            "has_handwriting_location": True,
                        }
                    ],
                },
                {
                    "question_id": "q-2",
                    "display_no": 2,
                    "question_type": "计算题",
                    "question_text": "计算功率",
                    "regions": [{"region_id": "q-2-r1", "bbox": [50, 250, 900, 550]}],
                    "answer_slots": [
                        {
                            "slot_id": "q-2-s1",
                            "label": "2_1",
                            "order": 1,
                            "bbox": [50, 300, 900, 550],
                            "regions": [{"bbox": [50, 300, 900, 550]}],
                            "has_handwriting_location": True,
                        }
                    ],
                },
            ],
        },
    }


def test_reference_layout_page_scales_boxes_and_defaults_scores(tmp_path):
    template = tmp_path / "学生甲_1.jpg"
    target = tmp_path / "学生乙_1.jpg"
    _image(template, (2000, 1200))  # 标准卷面 1000×600 的等比放大（2 倍）
    _image(target, (2000, 1200))

    page = manual_grading.build_manual_layout_page_from_reference_layout(
        _ref_page(),
        page_no=1,
        filename=template.name,
        image_url="/学生甲_1.jpg",
        image_path=str(template),
    )
    assert page["image_size"] == [2000, 1200]
    assert [q["display_no"] for q in page["questions"]] == [1, 2]
    assert page["questions"][0]["question_type"] == "填空题"
    assert page["questions"][0]["question_text"] == "做功的两个必要因素"
    # 框等比缩放 2 倍；标准答题区没有分值，默认 1 分
    assert page["questions"][0]["answer_slots"][0]["bbox"] == [100, 320, 400, 440]
    assert page["questions"][1]["answer_slots"][0]["bbox"] == [100, 600, 1800, 1100]
    assert [s["max_score"] for s in page["questions"][0]["answer_slots"]] == [1.0]

    # 原始试卷分值按 display_no 注入；下游 blocks 缩放到学生卷沿用同一套结构
    manual_grading.apply_paper_scores_to_page(page, {1: 5.0, 2: 8.0})
    assert page["questions"][0]["answer_slots"][0]["max_score"] == 5.0
    assert page["questions"][1]["answer_slots"][0]["max_score"] == 8.0

    confirmed = {
        "pages": {
            "1": {
                "layout": {
                    "image_size": page["image_size"],
                    "questions": page["questions"],
                }
            }
        }
    }
    blocks, image_size = manual_grading.manual_layout_blocks_for_image(
        confirmed["pages"]["1"]["layout"], str(target)
    )
    assert image_size == [2000, 1200]
    assert blocks[0]["bbox"] == [100, 320, 400, 440]
    assert [b["max_score"] for b in blocks] == [5.0, 8.0]
    assert [b["index"] for b in blocks] == [1, 2]


def test_reference_layout_page_fallback_slot_and_missing_raises(tmp_path):
    template = tmp_path / "学生甲_1.jpg"
    _image(template, (1000, 600))

    # 没画作答区的题（如选择题）：用题干框兜底出一格，保证这题能手动批
    slotless = _ref_page()
    slotless["layout"]["questions"] = [
        {
            "question_id": "q-9",
            "display_no": 9,
            "question_type": "选择题",
            "regions": [{"region_id": "q-9-r1", "bbox": [50, 50, 900, 150]}],
            "answer_slots": [],
        }
    ]
    page = manual_grading.build_manual_layout_page_from_reference_layout(
        slotless,
        page_no=1,
        filename=template.name,
        image_url="/学生甲_1.jpg",
        image_path=str(template),
    )
    slot = page["questions"][0]["answer_slots"][0]
    assert slot["bbox"] == [50, 50, 900, 150]
    assert slot["slot_id"] == "p1-q9-s1" and slot["label"] == "9_1"
    assert slot["max_score"] == 1.0

    # 没有题目框 → 报错（提示先去标准答案识别列表切题）
    empty = {"layout": {"image_size": [1000, 600], "questions": []}}
    try:
        manual_grading.build_manual_layout_page_from_reference_layout(
            empty, page_no=1, filename="x.jpg", image_url="/x.jpg", image_path=str(template)
        )
    except RuntimeError as exc:
        assert "标准答题区" in str(exc)
    else:
        raise AssertionError("空标准答题区应报错")


def test_reference_layout_page_number_offset_across_pages(tmp_path):
    """第 2 页题号按统分口径折算到全卷号（第 2 页第 1 题=第 14 题），slot/label 同步重编。"""
    template = tmp_path / "学生甲_2.jpg"
    _image(template, (1000, 600))
    page = manual_grading.build_manual_layout_page_from_reference_layout(
        _ref_page(),
        page_no=2,
        filename=template.name,
        image_url="/学生甲_2.jpg",
        image_path=str(template),
        number_offset=13,
    )
    assert [q["display_no"] for q in page["questions"]] == [14, 15]
    assert page["questions"][0]["question_id"] == "p2-q14"
    slot = page["questions"][0]["answer_slots"][0]
    assert slot["slot_id"] == "p2-q14-s1" and slot["label"] == "14_1"
    # 原始试卷分值按全卷号命中（第 14 题不是页内第 1 题）
    manual_grading.apply_paper_scores_to_page(page, {14: 7.0, 15: 9.0})
    assert [s["max_score"] for s in page["questions"][0]["answer_slots"]] == [7.0]
    assert [s["max_score"] for s in page["questions"][1]["answer_slots"]] == [9.0]


def test_prepare_manual_layout_source_reference_branch(tmp_path, monkeypatch):
    import pytest
    from fastapi import HTTPException

    template = tmp_path / "学生甲_1.jpg"
    _image(template, (2000, 1200))
    captured: dict = {}

    monkeypatch.setattr(grading_router, "_safe_folder_name", lambda _name: "exam")
    monkeypatch.setattr(
        grading_router,
        "_manual_template_sources",
        lambda _safe: {1: (template, template)},
    )
    monkeypatch.setattr(grading_router, "_preview_url_for_file", lambda _safe, name: f"/{name}")
    monkeypatch.setattr(grading_router, "load_paper_scores", lambda _safe: {1: 6.0})
    monkeypatch.setattr(
        grading_router,
        "load_reference_layout",
        lambda _safe: {"status": "confirmed", "pages": {"1": _ref_page()}},
    )

    def _capture_prepare(_safe, pages):
        captured["pages"] = copy.deepcopy(pages)
        return "prep-1"

    monkeypatch.setattr(grading_router, "save_manual_layout_prepare", _capture_prepare)

    res = grading_router.api_prepare_manual_layout("exam", {"source": "reference"})
    assert res["ok"] and res["prepare_id"] == "prep-1"
    page = res["pages"][0]
    assert page["questions"][0]["answer_slots"][0]["max_score"] == 6.0
    assert page["questions"][0]["answer_slots"][0]["bbox"] == [100, 320, 400, 440]
    assert captured["pages"][0]["source_path"] == str(template)

    # 标准答题区没确认 → 400，提示先去标准答案识别列表
    monkeypatch.setattr(grading_router, "load_reference_layout", lambda _safe: {})
    with pytest.raises(HTTPException) as exc_info:
        grading_router.api_prepare_manual_layout("exam", {"source": "reference"})
    assert exc_info.value.status_code == 400
    assert "标准答题区" in exc_info.value.detail

    # 无效来源 → 400
    with pytest.raises(HTTPException) as exc_info:
        grading_router.api_prepare_manual_layout("exam", {"source": "bogus"})
    assert exc_info.value.status_code == 400


def test_prepare_manual_layout_reference_renumbers_across_pages(tmp_path, monkeypatch):
    """多页切题：页内题号连续折算到全卷号（P1 两题 + P2 两题 → P2 编 3、4）。"""
    template1 = tmp_path / "学生甲_1.jpg"
    template2 = tmp_path / "学生甲_2.jpg"
    _image(template1, (1000, 600))
    _image(template2, (1000, 600))

    monkeypatch.setattr(grading_router, "_safe_folder_name", lambda _name: "exam")
    monkeypatch.setattr(
        grading_router,
        "_manual_template_sources",
        lambda _safe: {1: (template1, template1), 2: (template2, template2)},
    )
    monkeypatch.setattr(grading_router, "_preview_url_for_file", lambda _safe, name: f"/{name}")
    monkeypatch.setattr(grading_router, "load_paper_scores", lambda _safe: {})
    monkeypatch.setattr(
        grading_router,
        "load_reference_layout",
        lambda _safe: {"status": "confirmed", "pages": {"1": _ref_page(), "2": _ref_page()}},
    )
    monkeypatch.setattr(grading_router, "save_manual_layout_prepare", lambda _safe, _pages: "prep-2")

    res = grading_router.api_prepare_manual_layout("exam", {"source": "reference"})
    assert [q["display_no"] for q in res["pages"][0]["questions"]] == [1, 2]
    assert [q["display_no"] for q in res["pages"][1]["questions"]] == [3, 4]
    assert res["pages"][1]["questions"][0]["question_id"] == "p2-q3"
    assert res["pages"][1]["questions"][0]["answer_slots"][0]["label"] == "3_1"
