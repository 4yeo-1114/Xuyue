# -*- coding: utf-8 -*-
"""把「课程教学」里的 课件PPT-*.pdf（幻灯片图拼的 PDF）转成真正的 .pptx（每页一张满幅图）。

为什么是 PDF：智慧平台只公开每页幻灯片的图片（SlideN.jpg），可编辑 .pptx 原件在私有桶 403。
本脚本把 PDF 里嵌的原始幻灯片图直接抽出，装进 16:9 的 .pptx，可用 PowerPoint/WPS 打开/放映/增删页。
（原始文字是图片，不能直接改字；要改可在上面叠文本框。）

运行：venv python scripts/zyk_pdf_to_pptx.py [--delete-pdf] [--workers N]
幂等：已存在且比 pdf 新的 .pptx 跳过。
"""
import io
import sys
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import fitz  # PyMuPDF
from pptx import Presentation
from pptx.util import Inches

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
from app.grading.user_paths import shared_zyk_dir

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


def convert_one(pdf: Path, delete_pdf: bool) -> str:
    pptx = pdf.with_suffix(".pptx")
    if pptx.exists() and pptx.stat().st_mtime >= pdf.stat().st_mtime:
        return "skip"
    doc = fitz.open(str(pdf))
    try:
        prs = Presentation()
        prs.slide_width = SLIDE_W
        prs.slide_height = SLIDE_H
        blank = prs.slide_layouts[6]
        n = 0
        for page in doc:
            imgs = page.get_images(full=True)
            slide = prs.slides.add_slide(blank)
            if imgs:
                info = doc.extract_image(imgs[0][0])
                data = info["image"]
            else:
                pix = page.get_pixmap(dpi=150)
                data = pix.tobytes("png")
            slide.shapes.add_picture(io.BytesIO(data), 0, 0, width=SLIDE_W, height=SLIDE_H)
            n += 1
        if n == 0:
            return "empty"
        prs.save(str(pptx))
        if delete_pdf:
            pdf.unlink()
        return f"ok:{n}"
    finally:
        doc.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delete-pdf", action="store_true", help="转换成功后删除原 PDF")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    root = shared_zyk_dir() / "课程教学"
    pdfs = sorted(root.rglob("课件PPT-*.pdf"))
    print(f"待转换 {len(pdfs)} 个 PPT PDF", flush=True)

    ok = skip = fail = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(convert_one, p, args.delete_pdf): p for p in pdfs}
        for i, fut in enumerate(as_completed(futs), 1):
            p = futs[fut]
            try:
                r = fut.result()
            except Exception as e:  # noqa: BLE001
                fail += 1
                print(f"[FAIL] {p.name}: {e}", flush=True)
                continue
            if r == "skip":
                skip += 1
            elif r == "empty":
                fail += 1
                print(f"[EMPTY] {p.name}", flush=True)
            else:
                ok += 1
            if i % 200 == 0 or i == len(pdfs):
                print(f"[{i}/{len(pdfs)}] ok={ok} skip={skip} fail={fail}", flush=True)
    print(f"完成 ok={ok} skip={skip} fail={fail}", flush=True)


if __name__ == "__main__":
    main()
