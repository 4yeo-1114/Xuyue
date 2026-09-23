# -*- coding: utf-8 -*-
"""按 zyk_resources.py 的 RESOURCES 数据，为每个知识点生成「教学视频 PDF」和「公开课件 PPT PDF」。

数据格式（与 build_zyk_sample 的 SAMPLE 一致）：
    RESOURCES = [
        {
            "grade": "一年级", "subject": "数学", "knowledge": "1~5的认识和加减法",
            "videos": [ {"title": "...", "intro": "...", "fit": "...", "url": "..."} ],
            "ppts":   [ {"title": "...", "intro": "...", "fit": "...", "url": "..."} ],
        },
        ...
    ]

运行方式（在 grade-buddy-scan-back_end 目录下）：
    /d/anconda/python scripts/fill_zyk.py
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
_scripts = Path(__file__).resolve().parent
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from app.grading.user_paths import shared_zyk_dir
from build_zyk_sample import build_link_pdf
from zyk_resources import RESOURCES


def main() -> None:
    root = shared_zyk_dir()
    made = 0
    for entry in RESOURCES:
        folder = root / entry["grade"] / entry["subject"] / entry["knowledge"]
        folder.mkdir(parents=True, exist_ok=True)
        kp = entry["knowledge"]
        if entry.get("videos"):
            build_link_pdf(
                folder / f"教学视频-{kp}.pdf",
                f"{entry['grade']}·{entry['subject']}·{kp} 教学视频链接",
                entry["videos"],
            )
            made += 1
        if entry.get("ppts"):
            build_link_pdf(
                folder / f"公开课件PPT-{kp}.pdf",
                f"{entry['grade']}·{entry['subject']}·{kp} 公开课件 PPT 链接",
                entry["ppts"],
            )
            made += 1
    print(f"共生成 {made} 份 PDF，落在共享资源库：{root}")


if __name__ == "__main__":
    main()
