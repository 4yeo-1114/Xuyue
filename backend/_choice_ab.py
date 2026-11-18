# -*- coding: utf-8 -*-
"""选择题链路 A/B 诊断脚本（只读业务代码，产物落 %TEMP%\\xuyue_probe）。

用法：
    python _choice_ab.py before
    python _choice_ab.py after

流程 = 生产链路：百度 paper_cut_edu_vlm 切题 → 参考布局 → manual_analyze blocks
→ grade_paper_by_answer_key（选择题判分）→ 打印逐题表格 + 准确率。
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))

OUT = Path(tempfile.gettempdir()) / "xuyue_probe"
OUT.mkdir(parents=True, exist_ok=True)

PAPER = Path(r"D:\叙阅源码包_20261115\叙阅迁移包_20260920\手写试卷\2105班科学期中试卷\2105班科学期中试卷\S22C-6i26111015220_0003.pdf")
KEY_SRC = Path(r"D:\叙阅本地化安装包_20261116\app\.env")

# 学生卷面实际手写答案（人工核对 0003 页原图），作为「应得满分」的基准答案键。
STUDENT_CHOICE = {
    1: "C", 2: "C", 3: "B", 4: "A", 5: "B", 6: "B", 7: "A", 8: "C",
    9: "C", 10: "C", 11: "A", 12: "C", 13: "A", 14: "B", 15: "B",
}


def load_keys() -> None:
    txt = KEY_SRC.read_text(encoding="utf-8")
    for key in ("BAIDU_ACCESS_TOKEN", "BAIDU_API_KEY", "BAIDU_SECRET_KEY", "DASHSCOPE_API_KEY"):
        m = re.search(rf"^{key}=(.*)$", txt, re.M)
        if m and m.group(1).strip():
            os.environ[key] = m.group(1).strip()


def render_page() -> Path:
    png = OUT / "kx_0003_page.png"
    if png.is_file():
        return png
    import fitz
    from PIL import Image

    doc = fitz.open(str(PAPER))
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72), alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    img.save(png)
    return png


def build_blocks(png: Path):
    from app.grading.reference_vlm_grading import (
        build_reference_layout_page,
        recognize_reference_vlm_batch,
    )
    from app.grading.manual_grading import (
        build_manual_layout_page_from_reference_layout,
        manual_layout_blocks_for_image,
    )

    cache, errors = recognize_reference_vlm_batch([("kx", "科学卷", str(png))], allow_empty=True)
    if errors:
        raise RuntimeError(f"切题失败: {errors}")
    doc = cache["kx"]
    from app.grading.manual_grading import _baidu_ocr_text
    from app.grading.reference_vlm_grading import _printed_number_candidates

    words = _baidu_ocr_text(str(png))
    printed_numbers = _printed_number_candidates(words)
    (OUT / "kx_printed_numbers.json").write_text(
        json.dumps(printed_numbers, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    ref = build_reference_layout_page(
        doc, page_no=1, filename=png.name, image_url="", printed_numbers=printed_numbers
    )
    (OUT / "kx_reference_layout.json").write_text(
        json.dumps(ref, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    page = build_manual_layout_page_from_reference_layout(
        ref, page_no=1, filename=png.name, image_url="", image_path=str(png), number_offset=0
    )
    blocks, size = manual_layout_blocks_for_image(page, str(png))
    (OUT / "kx_blocks.json").write_text(
        json.dumps(blocks, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return blocks


def run(tag: str) -> None:
    load_keys()
    png = render_page()
    blocks = build_blocks(png)

    from app.grading.answer_key_grading import grade_paper_by_answer_key

    answer_key = {f"{q}_1": a for q, a in STUDENT_CHOICE.items()}
    decisions = grade_paper_by_answer_key(str(png), blocks, answer_key, subject="科学")

    rows = []
    for b in blocks:
        idx = b.get("index")
        if idx not in STUDENT_CHOICE:
            continue
        slot_id = str(b.get("slot_id") or "")
        dec = decisions.get(slot_id) or {}
        rows.append(
            {
                "题号": idx,
                "标准": STUDENT_CHOICE[idx],
                "读取": b.get("student_answer"),
                "判定": dec.get("status", "ungraded"),
                "label": b.get("label"),
                "kind": b.get("kind") or "",
                "bbox": b.get("bbox"),
                "reason": (b.get("reason") or b.get("analysis") or "")[:40],
            }
        )

    graded = [r for r in rows if r["判定"] in ("correct", "wrong", "partial")]
    correct = [r for r in rows if r["判定"] == "correct"]
    wrong = [r for r in rows if r["判定"] in ("wrong", "partial")]
    ungraded = [r for r in rows if r["判定"] not in ("correct", "wrong", "partial")]

    print(f"\n{'='*96}\n[{tag}] 选择题判分结果  题目数={len(rows)}  有判定={len(graded)}  对={len(correct)}  错={len(wrong)}  未判={len(ungraded)}")
    print(f"{'='*96}")
    print(f"{'题':>3} {'标准':<4} {'读取':<6} {'判定':<10} {'label':<8} {'kind':<8} {'bbox':<28} 说明")
    for r in rows:
        print(
            f"{r['题号']:>3} {r['标准']:<4} {str(r['读取']):<6} {r['判定']:<10} "
            f"{str(r['label']):<8} {r['kind']:<8} {str(r['bbox']):<28} {r['reason']}"
        )
    acc = len(correct) / len(rows) if rows else 0.0
    acc_graded = len(correct) / len(graded) if graded else 0.0
    print(f"\n准确率(占全部题) = {len(correct)}/{len(rows)} = {acc:.1%}")
    print(f"准确率(占有判定) = {len(correct)}/{len(graded)} = {acc_graded:.1%}")
    if ungraded:
        print(f"未判定题号: {[r['题号'] for r in ungraded]}")
    if wrong:
        print(f"错判题号: {[(r['题号'], r['标准'], r['读取']) for r in wrong]}")

    (OUT / f"kx_result_{tag}.json").write_text(
        json.dumps({"rows": rows, "accuracy": acc}, ensure_ascii=False, indent=1), encoding="utf-8"
    )


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "before")
