# -*- coding: utf-8 -*-
"""按 zyk_catalog.py 的目录，批量创建「年级 → 学科 → 知识点」三级文件夹骨架。

运行方式（在 grade-buddy-scan-back_end 目录下）：
    /d/anconda/python scripts/build_zyk_skeleton.py
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
from zyk_catalog import CATALOG


def main() -> None:
    root = shared_zyk_dir()
    grade_count = 0
    subject_count = 0
    kp_count = 0

    for grade, subjects in CATALOG.items():
        grade_count += 1
        for subject, points in subjects.items():
            subject_count += 1
            for kp in points:
                folder = root / grade / subject / kp
                folder.mkdir(parents=True, exist_ok=True)
                kp_count += 1

    print(f"共享资源库根目录：{root}")
    print(f"年级：{grade_count}  学科（年级×科）：{subject_count}  知识点文件夹：{kp_count}")
    print("骨架建好了（已存在的文件夹自动跳过）。")


if __name__ == "__main__":
    main()
