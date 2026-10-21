# -*- coding: utf-8 -*-
"""成绩报告 PDF 构建冒烟：三种 payload 口径各出一份 PDF，校验 %PDF 头与体积。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.dingtalk_pdf import (  # noqa: E402
    _report_filename,
    build_score_report_pdf,
)

SMART = {
    "exam_name": "第三单元测试",
    "class": {"class_name": "五年级二班", "grade": "小学五年级"},
    "score_summary": {"count": 42, "average": 78.6, "max": 100, "min": 32,
                      "full_score": 100},
    "score_ranking": [
        {"rank": i + 1, "student_box": f"学生{i+1}（卷{i+1:03d}）",
         "score_total": 100 - i, "wrong_count": i // 4}
        for i in range(42)
    ],
    "scope_note": "统计范围：已统分的 42 份",
}

GRADING_DONE = {
    "exam_name": "第二单元测试",
    "class": {"class_name": "五年级二班", "grade": "小学五年级"},
    "score_summary": {"count": 40, "average": None, "max": None, "min": None,
                      "full_score": None},
    "score_ranking": [
        {"rank": i + 1, "student_box": f"学生{i+1}", "score_total": None,
         "wrong_count": 3 - i % 3}
        for i in range(40)
    ],
}

ESSAY = {
    "exam_name": "命题作文《春天》",
    "class": {"class_name": "五年级二班", "grade": "小学五年级"},
    "score_summary": {"count": 3, "average": 85.0, "max": 92, "min": 78,
                      "full_score": 100},
    "students": [
        {"student_box": "张三", "score_total": 92},
        {"student_box": "李四", "score_total": 85},
        {"student_box": "王五", "score_total": 78},
    ],
}


def main():
    ok = True
    for kind, payload in [("smart_scoring", SMART),
                          ("grading_done", GRADING_DONE),
                          ("essay", ESSAY)]:
        try:
            data = build_score_report_pdf(payload, kind)
            assert data[:5] == b"%PDF-", f"{kind}: not a PDF"
            assert 1000 < len(data) < 5_000_000, f"{kind}: size={len(data)}"
            out = Path(__file__).with_name(f"_tmp_report_{kind}.pdf")
            out.write_bytes(data)
            print(f"{kind} OK size={len(data)} -> {out.name} "
                  f"file={_report_filename(payload)}")
        except Exception as e:
            ok = False
            print(f"{kind} FAILED: {e}")
    # 无 ranking / 无摘要的极端空 payload 不应崩
    try:
        data = build_score_report_pdf({}, "smart_scoring")
        assert data[:5] == b"%PDF-"
        print("empty payload OK")
    except Exception as e:
        ok = False
        print(f"empty payload FAILED: {e}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
