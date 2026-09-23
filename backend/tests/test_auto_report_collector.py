# -*- coding: utf-8 -*-
"""自动报告 collector：分析范围按试卷框计学生人数。"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.ai_auto_report.collector import collect_smart_scoring_payload


def test_scope_note_uses_student_box_count_not_file_count():
    scored_items = [
        ("box_a__p1.jpg", {"score_total": 90, "result": "第1题：正确\n第2题：错误"}),
        ("box_a__p2.jpg", {"score_total": 10, "result": "第1题：正确\n第2题：正确"}),
        ("box_b__p1.jpg", {"score_total": 80, "result": "第1题：正确\n第2题：正确"}),
    ]

    def fake_box_name(filename: str) -> str:
        return filename.split("__", 1)[0]

    fake_file = MagicMock()
    fake_file.is_file.return_value = False

    with patch(
        "app.services.ai_auto_report.collector._iter_scored_ref_items",
        return_value=scored_items,
    ), patch(
        "app.services.ai_auto_report.collector._read_grading_history",
        return_value={"scoring_config": {}},
    ), patch(
        "app.services.ai_auto_report.collector._read_wrong_jsons",
        return_value=({}, {}),
    ), patch(
        "app.services.ai_auto_report.collector._paper_box_display_name",
        side_effect=fake_box_name,
    ), patch(
        "app.services.ai_auto_report.collector._parse_ai_result_to_counts",
        return_value=({"correct": 1, "wrong": 1, "blank": 0}, []),
    ), patch(
        "app.services.ai_auto_report.collector._wrong_titles_from_grading_result",
        return_value=[],
    ), patch(
        "app.services.ai_auto_report.collector._load_class_meta",
        return_value={},
    ), patch(
        "app.services.ai_auto_report.collector._wrong_images_for_boxes",
        return_value=[],
    ), patch(
        "app.services.ai_auto_report.collector.correct_docs_dir",
        return_value=Path("/tmp/grading"),
    ), patch(
        "app.services.ai_auto_report.collector._preview_url_for_file",
        return_value="",
    ):
        payload = collect_smart_scoring_payload("cls_x__midterm")

    assert payload["student_count"] == 2
    assert payload["scored_file_count"] == 3
    assert "2 名学生" in payload["scope_note"]
    assert "3 份试卷" not in payload["scope_note"]

    assert payload["student_count"] == 2
    assert payload["scored_file_count"] == 3
    assert "2 名学生" in payload["scope_note"]
    assert "3 份试卷" not in payload["scope_note"]


if __name__ == "__main__":
    test_scope_note_uses_student_box_count_not_file_count()
    print("ok")
