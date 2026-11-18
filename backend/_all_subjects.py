# -*- coding: utf-8 -*-
"""全科目回归：7 个试卷文件夹各取一份样本，跑完整批改链路，统计覆盖与漏批。

指标口径：
- 块数：切题产出的作答区数量（选择题 + 填空 + 判断 + 主观）
- 有判定：产出了 对/错/半对/未作答 的块
- 显式待确认：未判定但带原因/痕迹的块（老师端可见）
- 静默漏批：既没判定也没痕迹的块 —— 必须为 0
- 无标准答案：本次未给这些块造答案键，用于验证「缺答案」路径也会留痕
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

OUT = Path(tempfile.gettempdir()) / "xuyue_probe"
OUT.mkdir(parents=True, exist_ok=True)

PAPERS_ROOT = Path(r"D:\叙阅源码包_20261115\叙阅迁移包_20260920\手写试卷")
ENV_FILE = Path(r"D:\叙阅本地化安装包_20261116\app\.env")

SAMPLES = [
    ("2105科学", PAPERS_ROOT / "2105班科学期中试卷" / "2105班科学期中试卷" / "S22C-6i26111015220_0003.pdf"),
    ("2212英语", PAPERS_ROOT / "2212班期中英语试卷" / "2212班期中英语试卷" / "S22C-6i26110815230_0001.pdf"),
    ("21地理", PAPERS_ROOT / "初一21班地理" / "地理" / "20261110035410351_0001.pdf"),
    ("25英语", PAPERS_ROOT / "初一25班英语11.16" / "20261116012944770_0001.pdf"),
    ("26英语", PAPERS_ROOT / "初一26班英语" / "26班" / "20261110011834585_0001.pdf"),
    ("26语文", PAPERS_ROOT / "初一26班语文11.16" / "初一26班语文11.16" / "20261115222603450_0001.pdf"),
    ("2206数学", PAPERS_ROOT / "数学" / "2206班数学阶段性测试卷" / "S22C-6i26110713110_0001.pdf"),
]


def load_keys() -> None:
    txt = ENV_FILE.read_text(encoding="utf-8")
    for key in ("BAIDU_ACCESS_TOKEN", "BAIDU_API_KEY", "BAIDU_SECRET_KEY", "DASHSCOPE_API_KEY"):
        m = re.search(rf"^{key}=(.*)$", txt, re.M)
        if m and m.group(1).strip():
            os.environ[key] = m.group(1).strip()


def render(pdf: Path, tag: str) -> Path:
    png = OUT / f"all_{tag}_p1.png"
    if png.is_file():
        return png
    import fitz
    from PIL import Image

    doc = fitz.open(str(pdf))
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72), alpha=False)
    Image.frombytes("RGB", [pix.width, pix.height], pix.samples).save(png)
    doc.close()
    return png


def run_one(tag: str, pdf: Path) -> dict:
    from app.grading.reference_vlm_grading import (
        _printed_number_candidates,
        build_reference_layout_page,
        recognize_reference_vlm_batch,
    )
    from app.grading.manual_grading import (
        _baidu_ocr_text,
        build_manual_layout_page_from_reference_layout,
        manual_layout_blocks_for_image,
    )
    from app.grading.answer_key_grading import grade_paper_by_answer_key

    png = render(pdf, tag)
    cache, errors = recognize_reference_vlm_batch([(tag, tag, str(png))], allow_empty=True)
    if errors or tag not in cache:
        return {"tag": tag, "error": str(errors or "切题无返回")}
    doc = cache[tag]
    pns = _printed_number_candidates(_baidu_ocr_text(str(png)))
    ref = build_reference_layout_page(doc, page_no=1, filename=png.name, image_url="", printed_numbers=pns)
    page = build_manual_layout_page_from_reference_layout(
        ref, page_no=1, filename=png.name, image_url="", image_path=str(png), number_offset=0
    )
    blocks, _ = manual_layout_blocks_for_image(page, str(png))

    # 答案键：给前 70% 的块造答案，后 30% 故意不给（验证「缺答案」也留痕）
    answer_key: dict[str, str] = {}
    cut = max(1, int(len(blocks) * 0.7))
    for b in blocks[:cut]:
        q = int(b.get("index") or 0)
        answer_key[f"{q}_1"] = "占位答案"  # 故意恒错，用于观察判定路径覆盖
    decisions = grade_paper_by_answer_key(str(png), blocks, answer_key)

    judged = review = silent = 0
    pending_reasons: dict[str, int] = {}
    for b in blocks:
        slot = str(b.get("slot_id") or "")
        status = str((decisions.get(slot) or {}).get("status") or "ungraded")
        trace = bool(b.get("reason") or b.get("analysis") or b.get("read_uncertain") or b.get("needs_review"))
        if status in ("correct", "wrong", "partial", "unanswered"):
            judged += 1
        elif trace:
            review += 1
            key = "缺标准答案" if "标准答案缺失" in str(b.get("reason") or "") else "识别/判分不确定"
            pending_reasons[key] = pending_reasons.get(key, 0) + 1
        else:
            silent += 1
    return {
        "tag": tag,
        "questions": len(ref["questions"]),
        "blocks": len(blocks),
        "judged": judged,
        "review": review,
        "silent": silent,
        "pending_reasons": pending_reasons,
        "with_key": cut,
        "no_key": len(blocks) - cut,
    }


def main() -> None:
    load_keys()
    rows = []
    for tag, pdf in SAMPLES:
        try:
            row = run_one(tag, pdf)
        except Exception as e:
            import traceback

            traceback.print_exc()
            row = {"tag": tag, "error": f"{type(e).__name__}: {e}"}
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    print("\n" + "=" * 100)
    print(f"{'科目':<10}{'题数':>6}{'块数':>6}{'有判定':>8}{'待确认':>8}{'静默漏批':>10}  待确认构成")
    print("=" * 100)
    total_blocks = total_silent = total_review = total_judged = 0
    for r in rows:
        if "error" in r:
            print(f"{r['tag']:<10}  ERROR: {r['error'][:60]}")
            continue
        total_blocks += r["blocks"]
        total_silent += r["silent"]
        total_review += r["review"]
        total_judged += r["judged"]
        print(
            f"{r['tag']:<10}{r['questions']:>6}{r['blocks']:>6}{r['judged']:>8}{r['review']:>8}"
            f"{r['silent']:>10}  {r['pending_reasons']}"
        )
    print("-" * 100)
    print(f"{'合计':<10}{'':>6}{total_blocks:>6}{total_judged:>8}{total_review:>8}{total_silent:>10}")
    rate = total_silent / total_blocks if total_blocks else 0.0
    print(f"静默漏批率 = {total_silent}/{total_blocks} = {rate:.2%}")
    (OUT / "all_subjects.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
