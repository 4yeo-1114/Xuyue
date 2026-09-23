import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from app.routers.class_analysis import (
    _build_warning_candidates,
    _db_report_to_dict,
    _normalize_final_analysis,
    _rank_scores,
    _resolve_full_image_paths,
)


def _student(student_id: str, name: str, number: str):
    return SimpleNamespace(id=student_id, name=name, student_number=number)


def test_rank_scores_keeps_ties_and_student_order():
    students = {
        "张三": _student("s1", "张三", "02"),
        "李四": _student("s2", "李四", "01"),
        "王五": _student("s3", "王五", "03"),
    }
    rows = _rank_scores({"张三": 90, "李四": 90, "王五": 80}, students)
    assert [(row["student_name"], row["rank"]) for row in rows] == [
        ("李四", 1),
        ("张三", 1),
        ("王五", 3),
    ]


def test_warning_candidates_are_relative_to_each_exam():
    rows = {
        "月考": [
            {"student_id": "s1", "student_name": "张三", "student_number": "01", "wrong_count": 9, "blank_count": 1, "wrong_titles": ["第1题"]},
            {"student_id": "s2", "student_name": "李四", "student_number": "02", "wrong_count": 2, "blank_count": 0},
            {"student_id": "s3", "student_name": "王五", "student_number": "03", "wrong_count": 1, "blank_count": 0},
            {"student_id": "s4", "student_name": "赵六", "student_number": "04", "wrong_count": 1, "blank_count": 0},
        ]
    }
    result = _build_warning_candidates(rows)
    assert [item["student_name"] for item in result] == ["张三"]
    assert result[0]["warning_exams"][0]["wrong_count"] == 10


def test_normalize_final_analysis_keeps_exam_order_and_allowed_warning_students():
    deterministic = {
        "exam_order": ["第一次", "第二次"],
        "students": [
            {"id": "s1", "name": "张三", "student_number": "01"},
            {"id": "s2", "name": "李四", "student_number": "02"},
        ],
        "exam_summaries": [
            {"average_score": 70},
            {"average_score": 75},
        ],
        "warning_candidates": [
            {
                "student_id": "s1",
                "student_name": "张三",
                "student_number": "01",
                "risk_level": "medium",
                "total_wrong_count": 8,
                "warning_exams": [
                    {"exam_name": "第二次", "wrong_count": 8, "class_average_wrong_count": 3.2}
                ],
            }
        ],
    }
    raw = {
        "overall_level": {"level": "良好", "summary": "整体进步"},
        "knowledge_heatmap": [
            {
                "knowledge_point": "二次函数",
                "values": [
                    {"exam_name": "第二次", "risk_score": 72, "evidence_count": 6},
                    {"exam_name": "不存在的考试", "risk_score": 100, "evidence_count": 99},
                ],
            }
        ],
        "weak_points": [
            {"knowledge_point": "二次函数", "affected_students": ["张三", "虚构学生"], "affected_student_count": 99}
        ],
        "student_warnings": [
            {"student_name": "张三", "reason": "错题集中", "suggestion": "复盘"},
            {"student_name": "虚构学生", "reason": "无效", "suggestion": "无效"},
        ],
    }
    normalized = _normalize_final_analysis(raw, deterministic)
    values = normalized["knowledge_heatmap"][0]["values"]
    assert [item["exam_name"] for item in values] == ["第一次", "第二次"]
    assert values[0]["risk_score"] is None
    assert values[1]["risk_score"] == 72
    assert normalized["weak_points"][0]["affected_students"] == ["张三"]
    assert normalized["weak_points"][0]["affected_student_count"] == 1
    assert [item["student_name"] for item in normalized["student_warnings"]] == ["张三"]


def test_resolve_full_image_paths_converts_every_pdf_page():
    root = Path(tempfile.mkdtemp(prefix="class_analysis_pdf_"))
    source_root = root / "papers"
    preview_root = root / "previews"
    folder = "exam_folder"
    (source_root / folder).mkdir(parents=True)
    pdf_path = source_root / folder / "student.pdf"
    first = Image.new("RGB", (120, 160), "white")
    second = Image.new("RGB", (120, 160), "lightgray")
    first.save(pdf_path, save_all=True, append_images=[second])

    with patch("app.routers.class_analysis.correct_docs_dir", return_value=source_root), patch(
        "app.routers.class_analysis.correct_docs_img_dir", return_value=preview_root
    ):
        pages = _resolve_full_image_paths(folder, "student.pdf")

    assert len(pages) == 2
    assert all(page.is_file() for page in pages)
    assert pages[0].name.endswith("page_0001.jpg")
    assert pages[1].name.endswith("page_0002.jpg")


def test_db_report_serialization_keeps_class_and_subject_separate():
    row = SimpleNamespace(
        id="db-row",
        report_uuid="report-version",
        class_id="class-1",
        class_name="七年级一班",
        subject="数学",
        exam_names_json='["月考","期中"]',
        imported_folder_names_json='["folder-1","folder-2"]',
        source_summary_json='{"overall_metrics":{"exam_count":2}}',
        analysis_json='{"overall_level":{"level":"良好"}}',
        generated_at=None,
        updated_at=None,
        # E05 · AI 内容统一标识：_db_report_to_dict 会读取 is_ai/ai_meta
        is_ai=1,
        ai_meta={"generator": "test", "model": "test-model"},
    )

    report = _db_report_to_dict(row)

    assert report["id"] == "report-version"
    assert report["class_id"] == "class-1"
    assert report["class_name"] == "七年级一班"
    assert report["subject"] == "数学"
    assert report["exam_names"] == ["月考", "期中"]
