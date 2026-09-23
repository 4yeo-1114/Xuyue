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
    monkeypatch.setattr(grading_router, "_replace_folder_grading_run", lambda _safe, _engine: None)

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
