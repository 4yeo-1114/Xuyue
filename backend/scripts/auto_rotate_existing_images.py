# -*- coding: utf-8 -*-
"""一次性摆正已上传的倒置/侧放答题卡图片（历史数据）。

用法（在 backend 目录、用 venv 里的 python 跑）：
  python scripts/auto_rotate_existing_images.py --dry-run          # 只检测打印，不落盘
  python scripts/auto_rotate_existing_images.py                    # 检测并就地旋转
  python scripts/auto_rotate_existing_images.py --folder <safe名>  # 只处理某个文件夹

只会处理 correct_documents/test_paper 与 test_paper_img 下的图片（jpg/jpeg/png），
资源库 zyk_data 不动。旋转前先保存一份 .bak 备份到原目录，失败不覆盖。
"""
import argparse
import glob
import os
import shutil
import sys
import time

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from PIL import Image  # noqa: E402
from app.grading.doc_convert import detect_image_orientation  # noqa: E402
from app.grading.user_paths import grading_data_all_root  # noqa: E402

_IMAGE_EXTS = (".jpg", ".jpeg", ".png")


def _rotate_in_place(path: str, deg: int, dry_run: bool) -> bool:
    if deg not in (90, 180, 270):
        return False
    if dry_run:
        return True
    bak = path + ".bak"
    try:
        if not os.path.exists(bak):
            shutil.copy2(path, bak)
        with Image.open(path) as im:
            out = im.rotate(-deg, expand=True).convert("RGB")
        ext = os.path.splitext(path)[1].lower()
        if ext in (".jpg", ".jpeg"):
            out.save(path, quality=95, optimize=True)
        elif ext == ".png":
            out.save(path, optimize=True)
        else:
            out.save(path)
        return True
    except Exception as e:
        print(f"  !! 旋转失败 {os.path.basename(path)}: {e}")
        return False


def _iter_student_dirs(root: str, folder_filter: str):
    for user_dir in glob.glob(os.path.join(root, "grading_data_*")):
        cd = os.path.join(user_dir, "correct_documents")
        if not os.path.isdir(cd):
            continue
        for sub in ("test_paper",):
            tp = os.path.join(cd, sub)
            if not os.path.isdir(tp):
                continue
            for folder in sorted(os.listdir(tp)):
                if folder_filter and folder != folder_filter:
                    continue
                fdir = os.path.join(tp, folder)
                if not os.path.isdir(fdir):
                    continue
                idir = os.path.join(cd, "test_paper_img", folder)
                yield folder, fdir, idir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--folder", default="")
    args = ap.parse_args()

    root = str(grading_data_all_root())
    print(f"扫描目录: {root}")
    total_checked = 0
    total_rotated = 0
    for folder, fdir, idir in _iter_student_dirs(root, args.folder):
        files = sorted(
            f for f in os.listdir(fdir)
            if os.path.splitext(f)[1].lower() in _IMAGE_EXTS
        )
        if not files:
            continue
        for fn in files:
            src = os.path.join(fdir, fn)
            deg = detect_image_orientation(Image.open(src))
            total_checked += 1
            mark = "DRY" if args.dry_run else "  OK"
            if deg:
                total_rotated += 1
                ok = _rotate_in_place(src, deg, args.dry_run)
                print(f"{mark} 旋转{deg}°  {folder}/{fn}")
                # 预览图同名，一并旋转（与源图相同角度，避免重复调 VLM）
                prev = os.path.join(idir, fn)
                if ok and os.path.isfile(prev):
                    _rotate_in_place(prev, deg, args.dry_run)
            else:
                print(f"    无需旋转  {folder}/{fn}")
            time.sleep(0.05)
    print(f"\n完成：检查 {total_checked} 张，需旋转 {total_rotated} 张（{('dry-run' if args.dry_run else '已落盘')}）。")


if __name__ == "__main__":
    main()
