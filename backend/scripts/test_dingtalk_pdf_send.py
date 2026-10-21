# -*- coding: utf-8 -*-
"""真实发送成绩报告 PDF 到已绑定的钉钉测试账号（media/upload → 文件消息全链路）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.dingtalk_pdf import send_report_pdf  # noqa: E402

TARGET = "08255256291939912825"  # 之前文字通知测试用的绑定账号

PAYLOAD = {
    "exam_name": "钉钉PDF功能测试",
    "class": {"class_name": "五年级二班", "grade": "小学五年级"},
    "score_summary": {"count": 42, "average": 78.6, "max": 100, "min": 32,
                      "full_score": 100},
    "score_ranking": [
        {"rank": i + 1, "student_box": f"学生{i+1}", "score_total": 100 - i,
         "wrong_count": i // 4}
        for i in range(42)
    ],
}


def main():
    ok, msg = send_report_pdf(TARGET, PAYLOAD, "smart_scoring")
    print(f"send -> ok={ok} msg={msg}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
